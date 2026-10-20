import json
import logging
import re
from typing import List, Optional, Dict, Any
import urllib.parse

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

from src.activities.scrapers.base import BaseListingScraper
from src.models.domain import VehicleListing

logger = logging.getLogger(__name__)

CARGURUS_SEARCH_BASE = "https://www.cargurus.com/Cars/inventorysearch"


class CarGurusScraper(BaseListingScraper):
    """Scraper for CarGurus listings with API network response interception."""

    def __init__(
        self,
        headless: bool = True,
        proxy_url: Optional[str] = None,
        timeout: float = 35.0,
    ):
        super().__init__(
            platform_name="cargurus",
            headless=headless,
            proxy_url=proxy_url,
            timeout=timeout,
        )

    def build_search_url(
        self,
        make: str,
        model: str,
        zip_code: str = "94103",
        radius_miles: int = 60,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
    ) -> str:
        """Build CarGurus search URL."""
        params: Dict[str, Any] = {
            "zip": zip_code,
            "distance": radius_miles,
        }
        if min_price:
            params["minPrice"] = min_price
        if max_price:
            params["maxPrice"] = max_price
        if min_year:
            params["startYear"] = min_year
        if max_year:
            params["endYear"] = max_year

        query = urllib.parse.urlencode(params)
        return f"{CARGURUS_SEARCH_BASE}?{query}#resultsPage=1"

    def parse_api_listing_payload(self, raw_data: Dict[str, Any]) -> List[VehicleListing]:
        """Parse raw JSON payload returned by CarGurus internal inventory endpoints."""
        listings: List[VehicleListing] = []
        items = raw_data.get("listings") or raw_data.get("results") or []

        for item in items:
            try:
                listing_id = str(item.get("id") or item.get("listingId") or "")
                vin = item.get("vin")
                price = int(item.get("price") or item.get("expectedPrice") or 0)
                mileage = int(item.get("mileage") or 0)
                year = int(item.get("year") or item.get("carYear") or 2023)
                make = item.get("makeName") or item.get("make") or ""
                model = item.get("modelName") or item.get("model") or ""
                trim = item.get("trimName") or item.get("trim") or ""
                title = item.get("listingTitle") or f"{year} {make} {model} {trim}".strip()

                url_path = item.get("url") or item.get("vdpUrl") or f"/Cars/detail/{listing_id}"
                full_url = f"https://www.cargurus.com{url_path}" if url_path.startswith("/") else url_path

                seller_info = item.get("seller") or {}
                seller_name = seller_info.get("name") if isinstance(seller_info, dict) else item.get("dealerName")
                dom = item.get("daysOnMarket") or item.get("daysOnCarGurus")

                if price <= 0:
                    continue

                listings.append(
                    VehicleListing(
                        vin=vin,
                        platform=self.platform_name,
                        platform_id=listing_id or vin or str(abs(hash(full_url))),
                        url=full_url,
                        title=title,
                        price=price,
                        mileage=mileage,
                        make=make,
                        model=model,
                        year=year,
                        exterior_color=item.get("exteriorColorName") or item.get("exteriorColor"),
                        interior_color=item.get("interiorColorName") or item.get("interiorColor"),
                        trim_detail=trim,
                        seller_name=seller_name,
                        distance_miles=float(item.get("distance")) if item.get("distance") else None,
                        raw_data={"days_on_market": dom, **item},
                    )
                )
            except Exception as e:
                logger.debug(f"Failed to parse individual CarGurus item: {e}")

        return listings

    def parse_html_page(self, html: str, source_url: str) -> List[VehicleListing]:
        """Extract listings from rendered HTML (JSON-LD or preloaded state)."""
        listings: List[VehicleListing] = []

        # 1. Search for JSON-LD Car schema via regex
        jsonld_pattern = re.compile(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            re.DOTALL | re.IGNORECASE,
        )
        for match in jsonld_pattern.finditer(html):
            raw = match.group(1).strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") in ["Car", "Vehicle", "Product"]:
                        l = self._convert_jsonld(item, source_url)
                        if l:
                            listings.append(l)
            except Exception:
                pass

        if listings:
            return listings

        # 2. Search for PRELOADED_STATE or script blobs
        match = re.search(r"(\{.*\"listings\".*\})", html)
        if match:
            try:
                blob = json.loads(match.group(1))
                return self.parse_api_listing_payload(blob)
            except Exception:
                pass

        return listings

    def _convert_jsonld(self, data: Dict[str, Any], source_url: str) -> Optional[VehicleListing]:
        vin = data.get("vehicleIdentificationNumber")
        offers = data.get("offers") or {}
        price = 0
        if isinstance(offers, dict):
            try:
                price = int(float(str(offers.get("price", 0)).replace("$", "").replace(",", "")))
            except ValueError:
                price = 0

        if price <= 0:
            return None

        name = data.get("name") or "CarGurus Vehicle"
        brand = data.get("brand")
        make = brand.get("name") if isinstance(brand, dict) else str(brand or "")

        return VehicleListing(
            vin=vin,
            platform=self.platform_name,
            platform_id=str(data.get("productID") or vin or abs(hash(name))),
            url=data.get("url") or source_url,
            title=name,
            price=price,
            mileage=int(data.get("mileageFromOdometer", {}).get("value", 0) if isinstance(data.get("mileageFromOdometer"), dict) else 0),
            make=make,
            model=data.get("model") or "",
            year=int(str(data.get("vehicleModelDate", 2023))[:4]),
            raw_data=data,
        )

    async def scrape_listings(
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
        """Scrape CarGurus listings using Playwright with network interception."""
        url = self.build_search_url(
            make=make,
            model=model,
            zip_code=zip_code,
            radius_miles=radius_miles,
            min_price=min_price,
            max_price=max_price,
            min_year=min_year,
            max_year=max_year,
        )
        logger.info(f"CarGurusScraper: Loading {url}")
        captured_listings: List[VehicleListing] = []

        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=self.headless,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                )
                context = await browser.new_context(
                    user_agent=self.get_random_user_agent(),
                    viewport={"width": 1440, "height": 900},
                )
                page = await context.new_page()

                async def handle_response(response):
                    nonlocal captured_listings
                    if "ajaxFetchSubsetListings" in response.url or "graphql" in response.url:
                        try:
                            data = await response.json()
                            results = self.parse_api_listing_payload(data)
                            if results:
                                captured_listings.extend(results)
                        except Exception:
                            pass

                page.on("response", handle_response)
                await page.goto(url, wait_until="domcontentloaded", timeout=int(self.timeout * 1000))
                await self.random_delay(2.0, 4.0)

                await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2);")
                await self.random_delay(1.5, 2.5)

                if not captured_listings:
                    html = await page.content()
                    captured_listings = self.parse_html_page(html, url)

                await browser.close()
                return captured_listings

        except Exception as e:
            logger.warning(f"CarGurus Playwright fallback: {e}")
            return []
