from dataclasses import dataclass, field
from datetime import datetime, date
from typing import List, Optional, Dict, Any


@dataclass
class VehicleModelSpec:
    make: str
    model: str
    year: int
    trim: Optional[str] = None
    generation_code: Optional[str] = None
    powertrain_type: str = "BEV"
    base_msrp: Optional[int] = None
    specs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NHTSARecall:
    campaign_number: str
    component: str
    summary: str
    consequence: str
    remedy: str
    report_date: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class NHTSAComplaint:
    odi_number: str
    component: str
    summary: str
    crash: bool = False
    fire: bool = False
    number_of_injuries: int = 0
    number_of_deaths: int = 0
    date_filed: Optional[str] = None


@dataclass
class EPAFuelEconomy:
    vehicle_id: str
    make: str
    model: str
    year: int
    comb_mpge: Optional[float] = None
    city_mpge: Optional[float] = None
    hwy_mpge: Optional[float] = None
    range_miles: Optional[int] = None
    annual_fuel_cost: Optional[int] = None
    fuel_type: str = "Electricity"
    raw_specs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VehicleListing:
    vin: Optional[str]
    platform: str  # 'cargurus', 'autotrader', 'carscom', 'facebook'
    platform_id: str
    url: str
    title: str
    price: int
    mileage: int
    make: str
    model: str
    year: int
    exterior_color: Optional[str] = None
    interior_color: Optional[str] = None
    trim_detail: Optional[str] = None
    seller_type: Optional[str] = None  # 'dealer', 'private'
    seller_name: Optional[str] = None
    seller_rating: Optional[float] = None
    location_city: Optional[str] = None
    location_state: Optional[str] = None
    distance_miles: Optional[float] = None
    title_status: str = "clean"  # 'clean', 'salvage', 'rebuilt', 'lemon'
    accident_count: int = 0
    owner_count: Optional[int] = None
    photos: List[str] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PriceSnapshot:
    listing_id: str
    price: int
    days_on_market: Optional[int] = None
    recorded_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DealScoreResult:
    listing_id: str
    market_value: int
    price_delta: int  # price - market_value (negative means below market)
    deal_score: float  # 0 to 100
    recommendation: str  # 'EXCELLENT_DEAL', 'FAIR_PRICE', 'OVERPRICED', 'PASS'
    score_breakdown: Dict[str, float] = field(default_factory=dict)
