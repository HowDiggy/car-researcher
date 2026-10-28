import asyncio
import logging
from typing import List, Dict, Any, Optional
from src.models.domain import VehicleListing
from src.activities.scrapers.carscom import CarsComScraper
from src.activities.scrapers.cargurus import CarGurusScraper
from src.config.settings import settings
from src.workflows.temporal_compat import activity

logger = logging.getLogger(__name__)


class MarketplaceAggregator:
    """Coordinates multi-platform scraping, deduplication, and cross-platform listing merging."""

    def __init__(
        self,
        headless: bool = True,
        concurrency: int = 3,
        proxy_url: Optional[str] = None,
    ):
        self.headless = headless
        self.semaphore = asyncio.Semaphore(concurrency)
        self.proxy_url = proxy_url

        self.scrapers = [
            CarsComScraper(headless=headless, proxy_url=proxy_url),
            CarGurusScraper(headless=headless, proxy_url=proxy_url),
        ]

    async def search_single_model(
        self,
        make: str,
        model: str,
        zip_code: str = "94103",
        radius_miles: int = 60,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
    ) -> List[VehicleListing]:
        """Query all scrapers concurrently for a single vehicle model and deduplicate."""
        async with self.semaphore:
            tasks = [
                scraper.scrape_listings(
                    make=make,
                    model=model,
                    zip_code=zip_code,
                    radius_miles=radius_miles,
                    min_price=min_price,
                    max_price=max_price,
                    min_year=min_year,
                    max_year=max_year,
                )
                for scraper in self.scrapers
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        raw_listings: List[VehicleListing] = []
        for res in results:
            if isinstance(res, list):
                raw_listings.extend(res)
            elif isinstance(res, Exception):
                logger.error(f"Scraper task encountered error: {res}")

        return self.deduplicate_listings(
            raw_listings,
            radius_miles=radius_miles,
            min_price=min_price,
            max_price=max_price,
            min_year=min_year,
            max_year=max_year,
            target_make=make,
            target_model=model,
        )

    @staticmethod
    def _merge_listing_metadata(primary: VehicleListing, secondary: VehicleListing) -> VehicleListing:
        """Merge missing metadata from a duplicate listing into the winning (lowest-price) listing."""
        for attr in (
            "exterior_color",
            "interior_color",
            "trim_detail",
            "seller_type",
            "seller_name",
            "seller_rating",
            "location_city",
            "location_state",
            "distance_miles",
            "owner_count",
        ):
            if getattr(primary, attr, None) is None and getattr(secondary, attr, None) is not None:
                setattr(primary, attr, getattr(secondary, attr))

        if not primary.photos and secondary.photos:
            primary.photos = list(secondary.photos)

        # Conservative safety: retain higher reported accident count or non-clean title
        if secondary.accident_count > primary.accident_count:
            primary.accident_count = secondary.accident_count
        if primary.title_status.lower() == "clean" and secondary.title_status.lower() != "clean":
            primary.title_status = secondary.title_status

        return primary

    @classmethod
    def deduplicate_listings(
        cls,
        listings: List[VehicleListing],
        radius_miles: Optional[int] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
        target_make: Optional[str] = None,
        target_model: Optional[str] = None,
    ) -> List[VehicleListing]:
        """
        Deduplicate and validate listings across platforms.
        - Primary key: 17-digit VIN (retains lowest price and merges metadata)
        - Secondary key: normalized (make, model, year, mileage_bucket, price)
        - Post-scrape guardrails: enforces radius, price, year, and make/model match
        """
        vin_map: Dict[str, VehicleListing] = {}
        fingerprint_map: Dict[str, VehicleListing] = {}

        for l in listings:
            # 1. Geospatial Constraint: Drop if distance exceeds radius
            if l.distance_miles is None:
                seller_zip = l.raw_data.get("seller_zip")
                if not seller_zip and isinstance(l.raw_data.get("seller"), dict):
                    seller_zip = l.raw_data["seller"].get("zip")
                if seller_zip:
                    from src.activities.scoring import BayAreaGeoLookup
                    est_d, est_c = BayAreaGeoLookup.resolve_zip(seller_zip)
                    if est_d is not None:
                        l.distance_miles = est_d
                    if est_c and not l.location_city:
                        l.location_city = est_c

            if radius_miles and l.distance_miles is not None:
                if l.distance_miles > float(radius_miles):
                    continue

            # 2. Price & Year Post-Scrape Guardrails (protects against sponsored/reset cards)
            if min_price and l.price < int(min_price * 0.75):
                continue
            if max_price and l.price > max_price:
                continue
            if min_year and l.year < min_year:
                continue
            if max_year and l.year > max_year:
                continue

            # 3. Target Make/Model Verification (protects against unrelated sponsored listings)
            if target_make and l.make:
                norm_target_make = target_make.lower().replace("-", " ").strip()
                norm_listing_make = l.make.lower().replace("-", " ").strip()
                if norm_target_make not in norm_listing_make and norm_listing_make not in norm_target_make:
                    continue

            if target_model and (l.model or l.title):
                norm_target_model = target_model.lower().replace("-", " ").strip()
                haystack = f"{l.model} {l.trim_detail or ''} {l.title}".lower().replace("-", " ")
                # Verify primary model token appears in the listing model/title
                primary_token = norm_target_model.split()[0]
                if primary_token not in haystack:
                    continue

            # 4. Deduplication by 17-digit VIN
            if l.vin and len(l.vin) == 17:
                vin_upper = l.vin.upper()
                if vin_upper in vin_map:
                    existing = vin_map[vin_upper]
                    if l.price < existing.price:
                        vin_map[vin_upper] = cls._merge_listing_metadata(l, existing)
                    else:
                        vin_map[vin_upper] = cls._merge_listing_metadata(existing, l)
                else:
                    vin_map[vin_upper] = l
                continue

            # 5. Secondary fallback: fingerprint hash
            clean_make = l.make.lower().strip()
            clean_model = l.model.lower().strip()
            mileage_bucket = l.mileage // 500
            fp = f"{clean_make}:{clean_model}:{l.year}:{mileage_bucket}:{l.price}"

            if fp not in fingerprint_map:
                fingerprint_map[fp] = l

        return list(vin_map.values()) + list(fingerprint_map.values())


# -------------------------------------------------------------
# Temporal Activity Wrapper
# -------------------------------------------------------------
@activity.defn
async def scrape_target_model_activity(
    make: str,
    model: str,
    zip_code: str = "94103",
    radius_miles: int = 60,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    min_year: Optional[int] = None,
    max_year: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Temporal activity to execute marketplace scraping for a specific vehicle."""
    aggregator = MarketplaceAggregator(
        headless=settings.scraper_headless,
        concurrency=settings.scraper_concurrency,
        proxy_url=settings.scraper_residential_proxy_url,
    )
    listings = await aggregator.search_single_model(
        make=make,
        model=model,
        zip_code=zip_code,
        radius_miles=radius_miles,
        min_price=min_price,
        max_price=max_price,
        min_year=min_year,
        max_year=max_year,
    )
    return [l.__dict__ for l in listings]
