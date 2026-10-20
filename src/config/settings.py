from typing import List, Optional
import os
import json

try:
    from pydantic import BaseModel, Field
    from pydantic_settings import BaseSettings, SettingsConfigDict
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False
    from dataclasses import dataclass, field


DEFAULT_TARGET_MODELS = [
    # Mainstream Bang-For-Buck
    {"make": "Hyundai", "model": "Ioniq 5", "min_year": 2022},
    {"make": "Hyundai", "model": "Ioniq 6", "min_year": 2023},
    {"make": "Kia", "model": "EV6", "min_year": 2022},
    {"make": "Tesla", "model": "Model Y", "min_year": 2022},
    {"make": "Tesla", "model": "Model 3", "min_year": 2022},
    {"make": "Ford", "model": "Mustang Mach-E", "min_year": 2022},
    {"make": "Chevrolet", "model": "Bolt EUV", "min_year": 2022, "max_year": 2023},

    # Upmarket & Luxury EV Depreciation Bargains
    {"make": "BMW", "model": "i4", "min_year": 2022},
    {"make": "Mercedes-Benz", "model": "EQS", "min_year": 2022},
    {"make": "Mercedes-Benz", "model": "EQE", "min_year": 2023},
    {"make": "Cadillac", "model": "Lyriq", "min_year": 2023},
    {"make": "Genesis", "model": "GV60", "min_year": 2023},
    {"make": "Polestar", "model": "2", "min_year": 2022},
    {"make": "Audi", "model": "Q4 e-tron", "min_year": 2022},
]

if HAS_PYDANTIC:
    class TargetVehicleConfig(BaseModel):
        make: str
        model: str
        min_year: Optional[int] = None
        max_year: Optional[int] = None
        trims: Optional[List[str]] = None

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore"
        )

        search_name: str = "Bay Area EV Watchlist"
        search_zip_code: str = "94103"
        search_radius_miles: int = 60
        search_min_price: int = 20000
        search_max_price: int = 60000
        search_min_year: int = 2021
        search_max_year: int = 2026
        search_powertrains: List[str] = Field(default_factory=lambda: ["BEV"])

        search_target_models: List[TargetVehicleConfig] = Field(
            default_factory=lambda: [TargetVehicleConfig(**m) for m in DEFAULT_TARGET_MODELS]
        )

        database_url: str = "postgresql+asyncpg://researcher:researcher_pass@localhost:5432/researcher"
        database_echo: bool = False

        temporal_host: str = "localhost:7233"
        temporal_namespace: str = "default"
        temporal_task_queue_default: str = "car-research-queue"
        temporal_task_queue_scrapers: str = "car-scraper-queue"

        scraper_headless: bool = True
        scraper_concurrency: int = 3
        scraper_residential_proxy_url: Optional[str] = None

        discord_webhook_url: Optional[str] = None
        telegram_bot_token: Optional[str] = None
        telegram_chat_id: Optional[str] = None

else:
    @dataclass
    class TargetVehicleConfig:
        make: str
        model: str
        min_year: Optional[int] = None
        max_year: Optional[int] = None
        trims: Optional[List[str]] = None

    @dataclass
    class Settings:
        search_name: str = "Bay Area EV Watchlist"
        search_zip_code: str = "94103"
        search_radius_miles: int = 60
        search_min_price: int = 20000
        search_max_price: int = 60000
        search_min_year: int = 2021
        search_max_year: int = 2026
        search_powertrains: List[str] = field(default_factory=lambda: ["BEV"])

        search_target_models: List[TargetVehicleConfig] = field(
            default_factory=lambda: [TargetVehicleConfig(**m) for m in DEFAULT_TARGET_MODELS]
        )

        database_url: str = "postgresql+asyncpg://researcher:researcher_pass@localhost:5432/researcher"
        database_echo: bool = False

        temporal_host: str = "localhost:7233"
        temporal_namespace: str = "default"
        temporal_task_queue_default: str = "car-research-queue"
        temporal_task_queue_scrapers: str = "car-scraper-queue"

        scraper_headless: bool = True
        scraper_concurrency: int = 3
        scraper_residential_proxy_url: Optional[str] = None

        discord_webhook_url: Optional[str] = None
        telegram_bot_token: Optional[str] = None
        telegram_chat_id: Optional[str] = None


settings = Settings()
