from typing import List, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Search Profile
    search_name: str = "Bay Area EV Watchlist"
    search_zip_code: str = "94103"
    search_radius_miles: int = 60
    search_min_price: int = 20000
    search_max_price: int = 60000
    search_min_year: int = 2021
    search_max_year: int = 2026
    search_powertrains: List[str] = Field(default_factory=lambda: ["BEV"])

    # Target Vehicles Scope (Mainstream + Upmarket / Luxury EVs)
    search_target_models: List[TargetVehicleConfig] = Field(
        default_factory=lambda: [
            # Mainstream Bang-For-Buck
            TargetVehicleConfig(make="Hyundai", model="Ioniq 5", min_year=2022),
            TargetVehicleConfig(make="Hyundai", model="Ioniq 6", min_year=2023),
            TargetVehicleConfig(make="Kia", model="EV6", min_year=2022),
            TargetVehicleConfig(make="Tesla", model="Model Y", min_year=2022),
            TargetVehicleConfig(make="Tesla", model="Model 3", min_year=2022),
            TargetVehicleConfig(make="Ford", model="Mustang Mach-E", min_year=2022),
            TargetVehicleConfig(make="Chevrolet", model="Bolt EUV", min_year=2022, max_year=2023),

            # Upmarket & Luxury EV Depreciation Bargains
            TargetVehicleConfig(make="BMW", model="i4", min_year=2022),
            TargetVehicleConfig(make="Mercedes-Benz", model="EQS", min_year=2022),
            TargetVehicleConfig(make="Mercedes-Benz", model="EQE", min_year=2023),
            TargetVehicleConfig(make="Cadillac", model="Lyriq", min_year=2023),
            TargetVehicleConfig(make="Genesis", model="GV60", min_year=2023),
            TargetVehicleConfig(make="Polestar", model="2", min_year=2022),
            TargetVehicleConfig(make="Audi", model="Q4 e-tron", min_year=2022),
        ]
    )

    # Database Settings
    database_url: str = "postgresql+asyncpg://researcher:researcher_pass@localhost:5432/researcher"
    database_echo: bool = False

    # Temporal Settings
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue_default: str = "car-research-queue"
    temporal_task_queue_scrapers: str = "car-scraper-queue"

    # Scraper Settings
    scraper_headless: bool = True
    scraper_concurrency: int = 3
    scraper_residential_proxy_url: Optional[str] = None

    # Alerts & Notifications
    discord_webhook_url: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None


settings = Settings()
