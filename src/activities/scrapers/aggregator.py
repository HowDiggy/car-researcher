import asyncio
import logging
from typing import List, Dict, Any, Optional
from src.models.domain import VehicleListing
from src.activities.scrapers.carscom import CarsComScraper
from src.activities.scrapers.cargurus import CarGurusScraper
from src.config.settings import settings

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

        return self.deduplicate_listings(raw_listings, radius_miles=radius_miles)

    @staticmethod
    def deduplicate_listings(
        listings: List[VehicleListing],
        radius_miles: Optional[int] = None,
    ) -> List[VehicleListing]:
        """
        Deduplicate listings across platforms.
        - Primary key: 17-digit VIN
        - Secondary key: normalized (make, model, year, mileage, price)
        """
        vin_map: Dict[str, VehicleListing] = {}
        fingerprint_map: Dict[str, VehicleListing] = {}

        for l in listings:
            # Filter by radius if distance is populated
            if radius_miles and l.distance_miles is not None:
                if l.distance_miles > float(radius_miles):
                    continue

            # Deduplication by VIN
            if l.vin and len(l.vin) == 17:
                vin_upper = l.vin.upper()
                if vin_upper in vin_map:
                    existing = vin_map[vin_upper]
                    # Keep the listing with lower price or more detailed info
                    if l.price < existing.price:
                        vin_map[vin_upper] = l
                else:
                    vin_map[vin_upper] = l
                continue

            # Secondary fallback: fingerprint hash
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
