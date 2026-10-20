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

CARS_COM_BASE_URL = "https://www.cars.com/shopping/results/"


class CarsComScraper(BaseListingScraper):
    """Scraper for Cars.com inventory listings supporting JSON-LD, NEXT_DATA, and DOM parsing."""

    def __init__(
        self,
        headless: bool = True,
        proxy_url: Optional[str] = None,
        timeout: float = 30.0,
    ):
        super().__init__(
            platform_name="carscom",
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
        page: int = 1,
    ) -> str:
        """Construct a standardized search URL for Cars.com."""
        make_slug = make.lower().replace(" ", "_").replace("-", "_")
        clean_model = model.lower().replace(" ", "_").replace("-", "_")

        # Handle specific platform model slug deviations
        if make_slug == "bmw" and clean_model == "i4":
            model_slug = "bmw-i4_gran_coupe"
            use_keyword = False
        elif "mercedes" in make_slug and ("eqs" in clean_model or "eqe" in clean_model):
            model_slug = None
            use_keyword = True
        else:
            model_slug = f"{make_slug}-{clean_model}"
            use_keyword = False

        params: Dict[str, Any] = {
            "stock_type": "all",
            "makes[]": make_slug,
            "zip": zip_code,
            "maximum_distance": radius_miles,
            "page_size": 50,
            "page": page,
        }
        if use_keyword:
            params["keyword"] = model.upper()
        elif model_slug:
            params["models[]"] = model_slug

        if min_price:
            params["list_price_min"] = min_price
        if max_price:
            params["list_price_max"] = max_price
        if min_year:
            params["year_min"] = min_year
        if max_year:
            params["year_max"] = max_year

        query = urllib.parse.urlencode(params, doseq=True)
        return f"{CARS_COM_BASE_URL}?{query}"

    def parse_html_listings(self, html_content: str, source_url: str) -> List[VehicleListing]:
        """Extract listings using CarsWeb.SearchController hydration, JSON-LD, or DOM parsing."""
        listings: List[VehicleListing] = []

        # Strategy 1: CarsWeb.SearchController.index JSON Blob
        search_controller_match = re.search(
            r'<script[^>]*id=["\']CarsWeb\.SearchController\.index["\'][^>]*>(.*?)</script>',
            html_content,
            re.DOTALL | re.IGNORECASE,
        )
        if search_controller_match:
            try:
                controller_data = json.loads(search_controller_match.group(1).strip())
                results = controller_data.get("srp_results", {}).get("results", [])
                for item in results:
                    if item.get("__typename") == "SrpListingGridCard":
                        ctx_str = item.get("analytics", {}).get("context", "")
                        if ctx_str:
                            ctx = json.loads(ctx_str)
                            listing = self._convert_search_controller_to_listing(ctx, source_url)
                            if listing:
                                listings.append(listing)
                if listings:
                    logger.info(f"CarsComScraper: Extracted {len(listings)} listings via CarsWeb.SearchController.index.")
                    return listings
            except Exception as e:
                logger.debug(f"CarsWeb.SearchController.index parse error: {e}")

        # Strategy 1: JSON-LD Extraction
        jsonld_pattern = re.compile(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            re.DOTALL | re.IGNORECASE,
        )
        for match in jsonld_pattern.finditer(html_content):
            raw_json = match.group(1).strip()
            if not raw_json:
                continue
            try:
                data = json.loads(raw_json)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    item_type = item.get("@type", "")
                    if item_type in ["Car", "Vehicle", "Product"] or "vehicleIdentificationNumber" in item:
                        listing = self._convert_jsonld_to_listing(item, source_url)
                        if listing:
                            listings.append(listing)
            except Exception as e:
                logger.debug(f"JSON-LD regex parse error: {e}")

        if listings:
            logger.info(f"CarsComScraper: Extracted {len(listings)} listings via JSON-LD.")
            return listings

        # Strategy 2: Next.js __NEXT_DATA__ State Blob
        next_data_match = re.search(
            r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
            html_content,
            re.DOTALL | re.IGNORECASE,
        )
        if next_data_match:
            try:
                next_data = json.loads(next_data_match.group(1).strip())
                page_props = next_data.get("props", {}).get("pageProps", {})
                inventory = (
                    page_props.get("listings")
                    or page_props.get("vehicles")
                    or page_props.get("initialState", {}).get("inventory", {}).get("listings", [])
                )
                for item in inventory:
                    listing = self._convert_next_data_to_listing(item, source_url)
                    if listing:
                        listings.append(listing)

                if listings:
                    logger.info(f"CarsComScraper: Extracted {len(listings)} listings via __NEXT_DATA__.")
                    return listings
            except Exception as e:
                logger.debug(f"__NEXT_DATA__ parse error: {e}")

        # Strategy 3: BeautifulSoup DOM fallback if available
        if HAS_BS4:
            soup = BeautifulSoup(html_content, "html.parser")
            cards = soup.select(".vehicle-card, [data-qa='vehicle-card'], div.vehicle-details")
            for card in cards:
                try:
                    listing = self._convert_dom_card_to_listing(card, source_url)
                    if listing:
                        listings.append(listing)
                except Exception as card_err:
                    logger.debug(f"Card parse error: {card_err}")

        logger.info(f"CarsComScraper: Extracted {len(listings)} listings.")
        return listings

    def _convert_search_controller_to_listing(self, item: Dict[str, Any], source_url: str) -> Optional[VehicleListing]:
        """Convert a CarsWeb.SearchController.index analytics item into a VehicleListing domain model."""
        price_val = item.get("price")
        try:
            price = int(float(str(price_val).replace("$", "").replace(",", "")))
        except (ValueError, TypeError):
            price = 0

        if price <= 0:
            return None

        mileage_val = item.get("mileage")
        try:
            mileage = int(float(str(mileage_val).replace(",", "")))
        except (ValueError, TypeError):
            mileage = 0

        year_val = item.get("year")
        try:
            year = int(str(year_val)[:4])
        except (ValueError, TypeError):
            year = 2023

        make = item.get("make") or ""
        model = item.get("model") or ""
        trim = item.get("trim") or ""
        title = f"{year} {make} {model} {trim}".strip()
        listing_id = str(item.get("listingId") or "")
        url = f"https://www.cars.com/vehicledetail/{listing_id}/" if listing_id else source_url

        seller = item.get("seller") or {}
        seller_name = seller.get("dealerName") if isinstance(seller, dict) else None

        return VehicleListing(
            vin=item.get("vin"),
            platform=self.platform_name,
            platform_id=listing_id or item.get("vin") or str(abs(hash(url))),
            url=url,
            title=title,
            price=price,
            mileage=mileage,
            make=make,
            model=model,
            year=year,
            trim_detail=trim,
            exterior_color=item.get("exteriorColor"),
            seller_name=seller_name,
            raw_data=item,
        )

    def _convert_jsonld_to_listing(self, data: Dict[str, Any], source_url: str) -> Optional[VehicleListing]:
        """Convert a Schema.org Car JSON-LD dictionary into a VehicleListing domain model."""
        vin = data.get("vehicleIdentificationNumber")
        name = data.get("name") or data.get("vehicleConfiguration") or "Vehicle"
        brand_data = data.get("brand")
        make = brand_data.get("name") if isinstance(brand_data, dict) else str(brand_data or "")
        model = data.get("model") or ""
        year_val = data.get("vehicleModelDate") or data.get("productionDate")

        try:
            year = int(str(year_val)[:4]) if year_val else 2023
        except (ValueError, TypeError):
            year = 2023

        offers = data.get("offers") or {}
        price = 0
        if isinstance(offers, dict):
            price_raw = offers.get("price")
            if price_raw:
                try:
                    price = int(float(str(price_raw).replace("$", "").replace(",", "")))
                except ValueError:
                    price = 0

        mileage_obj = data.get("mileageFromOdometer") or {}
        mileage = 0
        if isinstance(mileage_obj, dict):
            mileage_raw = mileage_obj.get("value")
            if mileage_raw:
                try:
                    mileage = int(float(str(mileage_raw).replace(",", "")))
                except ValueError:
                    mileage = 0

        images = data.get("image") or []
        if isinstance(images, str):
            images = [images]

        listing_id = str(data.get("productID") or data.get("identifier") or vin or abs(hash(name + str(price))))
        target_url = data.get("url") or source_url
        if not target_url.startswith("http"):
            target_url = f"https://www.cars.com{target_url}"

        seller = offers.get("seller") if isinstance(offers, dict) else {}
        seller_name = seller.get("name") if isinstance(seller, dict) else None

        if price <= 0:
            return None

        return VehicleListing(
            vin=vin,
            platform=self.platform_name,
            platform_id=listing_id,
            url=target_url,
            title=name,
            price=price,
            mileage=mileage,
            make=make,
            model=model,
            year=year,
            exterior_color=data.get("color"),
            seller_type="dealer" if seller_name else "private",
            seller_name=seller_name,
            photos=images[:5],
            raw_data=data,
        )

    def _convert_next_data_to_listing(self, item: Dict[str, Any], source_url: str) -> Optional[VehicleListing]:
        """Convert Next.js internal payload item to VehicleListing."""
        listing_id = str(item.get("id") or item.get("listing_id") or "")
        vin = item.get("vin")
        price = int(item.get("price") or item.get("list_price") or 0)
        mileage = int(item.get("mileage") or 0)
        make = item.get("make") or ""
        model = item.get("model") or ""
        year = int(item.get("year") or 2023)
        title = item.get("title") or f"{year} {make} {model}"
        url = item.get("url") or source_url
        if not url.startswith("http"):
            url = f"https://www.cars.com{url}"

        if price <= 0:
            return None

        return VehicleListing(
            vin=vin,
            platform=self.platform_name,
            platform_id=listing_id or vin or str(abs(hash(url))),
            url=url,
            title=title,
            price=price,
            mileage=mileage,
            make=make,
            model=model,
            year=year,
            exterior_color=item.get("exterior_color"),
            interior_color=item.get("interior_color"),
            trim_detail=item.get("trim"),
            seller_name=item.get("dealer_name"),
            distance_miles=float(item.get("distance")) if item.get("distance") else None,
            raw_data=item,
        )

    def _convert_dom_card_to_listing(self, card: Any, source_url: str) -> Optional[VehicleListing]:
        """Extract attributes from HTML element card (when bs4 is available)."""
        title_el = card.select_one(".title, h2, h3, a.vehicle-card-link")
        price_el = card.select_one(".primary-price, .price, [data-qa='primary-price']")
        mileage_el = card.select_one(".mileage, [data-qa='mileage']")
        link_el = card.select_one("a.vehicle-card-link, a[href*='/vehicledetail/']")

        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            return None

        price = 0
        if price_el:
            price_digits = re.sub(r"[^\d]", "", price_el.get_text(strip=True))
            if price_digits:
                price = int(price_digits)

        mileage = 0
        if mileage_el:
            mileage_digits = re.sub(r"[^\d]", "", mileage_el.get_text(strip=True))
            if mileage_digits:
                mileage = int(mileage_digits)

        href = link_el.get("href") if link_el else ""
        listing_url = f"https://www.cars.com{href}" if href.startswith("/") else (href or source_url)
        listing_id = card.get("data-listing-id") or card.get("id") or str(abs(hash(listing_url)))

        year_match = re.search(r"\b(20\d\d)\b", title)
        year = int(year_match.group(1)) if year_match else 2023

        if price <= 0:
            return None

        return VehicleListing(
            vin=card.get("data-vin"),
            platform=self.platform_name,
            platform_id=str(listing_id),
            url=listing_url,
            title=title,
            price=price,
            mileage=mileage,
            make="",
            model="",
            year=year,
            raw_data={"scraped_via": "dom_card"},
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
        """Perform search query against Cars.com using async HTTP or Playwright."""
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
        logger.info(f"CarsComScraper: Fetching {url}")

        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=self.headless,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                )
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                    extra_http_headers={
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                        "Sec-CH-UA": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
                        "Sec-CH-UA-Mobile": "?0",
                        "Sec-CH-UA-Platform": '"Linux"',
                        "Sec-Fetch-Dest": "document",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "none",
                        "Sec-Fetch-User": "?1",
                        "Upgrade-Insecure-Requests": "1",
                    },
                )
                await context.add_init_script(
                    'Object.defineProperty(navigator, "webdriver", {get: () => undefined}); window.chrome = { runtime: {} };'
                )
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=int(self.timeout * 1000))
                await page.wait_for_timeout(1500)
                html = await page.content()
                await browser.close()
                return self.parse_html_listings(html, url)
        except Exception as pw_err:
            logger.warning(f"Playwright execution fallback to direct HTTP: {pw_err}")

        # Direct HTTP Fallback
        import urllib.request
        import asyncio

        def _fetch() -> str:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": self.get_random_user_agent(),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8", errors="ignore")

        try:
            html = await asyncio.to_thread(_fetch)
            return self.parse_html_listings(html, url)
        except Exception as http_err:
            logger.error(f"Failed to fetch Cars.com search page: {http_err}")
            return []
