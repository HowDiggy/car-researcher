import abc
import asyncio
import random
import logging
from typing import List, Dict, Any, Optional
from src.models.domain import VehicleListing

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]


class BaseListingScraper(abc.ABC):
    """Abstract base class for vehicle marketplace scrapers."""

    def __init__(
        self,
        platform_name: str,
        headless: bool = True,
        proxy_url: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.platform_name = platform_name
        self.headless = headless
        self.proxy_url = proxy_url
        self.timeout = timeout

    @abc.abstractmethod
    async def scrape_listings(
        self,
        make: str,
        model: str,
        zip_code: str,
        radius_miles: int,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
    ) -> List[VehicleListing]:
        """Scrape vehicle listings matching search filters."""
        pass

    async def random_delay(self, min_sec: float = 1.5, max_sec: float = 3.5) -> None:
        """Introduce randomized jitter to mimic human browsing behavior."""
        delay = random.uniform(min_sec, max_sec)
        await asyncio.sleep(delay)

    def get_random_user_agent(self) -> str:
        """Return a modern desktop user-agent string."""
        return random.choice(USER_AGENTS)
