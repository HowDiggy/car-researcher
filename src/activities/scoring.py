from typing import Dict, Any, List, Optional
from src.models.domain import VehicleListing, DealScoreResult

# Baseline original MSRP estimates when not explicitly decoded from Monroney/vPIC
MODEL_BASE_MSRP_LOOKUP: Dict[str, int] = {
    # Luxury / Upmarket EVs
    "mercedes-benz:eqs": 105000,
    "mercedes-benz:eqe": 76000,
    "cadillac:lyriq": 62000,
    "genesis:gv60": 60000,
    "bmw:i4": 56000,
    "audi:q4 e-tron": 50000,
    "polestar:2": 51000,
    # Mainstream EVs
    "tesla:model y": 52000,
    "tesla:model 3": 43000,
    "ford:mustang mach-e": 47000,
    "hyundai:ioniq 5": 44000,
    "hyundai:ioniq 6": 43000,
    "kia:ev6": 45000,
    "chevrolet:bolt euv": 33000,
}


class DealScorer:
    """Calculates Fair Market Value delta, composite deal score, and recommendation."""

    @classmethod
    def get_estimated_original_msrp(cls, make: str, model: str) -> int:
        key = f"{make.strip().lower()}:{model.strip().lower()}"
        return MODEL_BASE_MSRP_LOOKUP.get(key, 48000)

    @classmethod
    def calculate_fair_market_value(
        cls,
        base_model_msrp: int,
        age_years: float,
        mileage: int,
        is_luxury: bool = False,
    ) -> int:
        """
        Estimate Fair Market Value based on empirical depreciation and mileage regression.
        Luxury EVs (EQS, Lyriq, i4) drop even faster due to 3-year off-lease glut and high starting MSRP:
        - Year 1: ~25-30% drop (Luxury) vs ~20-25% (Standard)
        - Year 2: ~40-48% drop (Luxury) vs ~35-40% (Standard)
        - Year 3: ~50-60% drop (Luxury) vs ~45-50% (Standard)
        - Mileage adjustment: ±$0.12 per mile delta from 12,000 miles/year.
        """
        if is_luxury:
            if age_years <= 1.0:
                retention_rate = 0.72
            elif age_years <= 2.0:
                retention_rate = 0.56
            elif age_years <= 3.0:
                retention_rate = 0.45
            elif age_years <= 4.0:
                retention_rate = 0.38
            else:
                retention_rate = max(0.25, 0.35 - (age_years - 4) * 0.05)
        else:
            if age_years <= 1.0:
                retention_rate = 0.77
            elif age_years <= 2.0:
                retention_rate = 0.65
            elif age_years <= 3.0:
                retention_rate = 0.55
            elif age_years <= 4.0:
                retention_rate = 0.48
            else:
                retention_rate = max(0.30, 0.45 - (age_years - 4) * 0.05)

        base_depreciated = base_model_msrp * retention_rate

        # Mileage adjustment (assuming standard 12,000 miles/year)
        expected_mileage = max(1000, int(age_years * 12000))
        mileage_delta = mileage - expected_mileage
        mileage_penalty = mileage_delta * 0.12  # $0.12 per mile

        estimated_value = int(base_depreciated - mileage_penalty)
        return max(5000, estimated_value)

    @classmethod
    def score_listing(
        cls,
        listing: VehicleListing,
        market_value: Optional[int] = None,
        base_msrp: Optional[int] = None,
        current_year: int = 2026,
    ) -> DealScoreResult:
        """Calculate composite 0-100 deal score and recommendation."""
        age_years = max(0.5, float(current_year - listing.year))

        if base_msrp is None:
            base_msrp = cls.get_estimated_original_msrp(listing.make, listing.model)

        is_luxury = any(
            lux_brand in listing.make.lower()
            for lux_brand in ["mercedes", "bmw", "cadillac", "audi", "genesis", "porsche", "polestar"]
        )

        if market_value is None:
            market_value = cls.calculate_fair_market_value(
                base_model_msrp=base_msrp,
                age_years=age_years,
                mileage=listing.mileage,
                is_luxury=is_luxury,
            )

        price_delta = listing.price - market_value
        breakdown: Dict[str, float] = {}

        # 1. Price Delta Score (Weight: 50%)
        pct_diff = price_delta / market_value
        price_score = max(0.0, min(100.0, 70.0 - (pct_diff * 250.0)))
        breakdown["price_score"] = round(price_score, 1)

        # 2. History & Title Score (Weight: 25%)
        history_score = 100.0
        if listing.title_status.lower() != "clean":
            history_score -= 50.0  # Heavy penalty for salvage/rebuilt/lemon
        if listing.accident_count > 0:
            history_score -= min(40.0, listing.accident_count * 20.0)
        if listing.owner_count is not None:
            if listing.owner_count == 1:
                history_score += 5.0
            elif listing.owner_count >= 3:
                history_score -= 15.0
        history_score = max(0.0, min(100.0, history_score))
        breakdown["history_score"] = round(history_score, 1)

        # 3. Market Leverage / Days on Market Score (Weight: 15%)
        dom = listing.raw_data.get("days_on_market", 30)
        if dom > 60:
            leverage_score = 95.0
        elif dom > 30:
            leverage_score = 80.0
        else:
            leverage_score = 65.0
        breakdown["leverage_score"] = round(leverage_score, 1)

        # 4. Proximity Score (Weight: 10%)
        dist = listing.distance_miles if listing.distance_miles is not None else 30.0
        if dist <= 20.0:
            proximity_score = 100.0
        elif dist <= 40.0:
            proximity_score = 85.0
        elif dist <= 60.0:
            proximity_score = 70.0
        else:
            proximity_score = max(20.0, 70.0 - (dist - 60.0))
        breakdown["proximity_score"] = round(proximity_score, 1)

        # Composite Calculation
        final_score = (
            0.50 * price_score
            + 0.25 * history_score
            + 0.15 * leverage_score
            + 0.10 * proximity_score
        )
        final_score = round(max(0.0, min(100.0, final_score)), 1)

        # Recommendation Tier
        if final_score >= 85.0 and listing.title_status.lower() == "clean":
            recommendation = "EXCELLENT_DEAL"
        elif final_score >= 75.0:
            recommendation = "GOOD_VALUE"
        elif final_score >= 60.0:
            recommendation = "FAIR_MARKET"
        else:
            recommendation = "OVERPRICED_OR_HIGH_RISK"

        return DealScoreResult(
            listing_id=listing.platform_id,
            market_value=market_value,
            price_delta=price_delta,
            deal_score=final_score,
            recommendation=recommendation,
            score_breakdown=breakdown,
        )


# -------------------------------------------------------------
# Temporal Activity Wrapper
# -------------------------------------------------------------
async def score_listing_activity(
    listing_dict: Dict[str, Any],
    base_msrp: Optional[int] = None,
) -> Dict[str, Any]:
    """Temporal activity to compute deal score."""
    listing = VehicleListing(
        vin=listing_dict.get("vin"),
        platform=listing_dict.get("platform", "cargurus"),
        platform_id=listing_dict.get("platform_id", "unknown"),
        url=listing_dict.get("url", ""),
        title=listing_dict.get("title", ""),
        price=int(listing_dict.get("price", 0)),
        mileage=int(listing_dict.get("mileage", 0)),
        make=listing_dict.get("make", ""),
        model=listing_dict.get("model", ""),
        year=int(listing_dict.get("year", 2023)),
        exterior_color=listing_dict.get("exterior_color"),
        distance_miles=listing_dict.get("distance_miles"),
        title_status=listing_dict.get("title_status", "clean"),
        accident_count=int(listing_dict.get("accident_count", 0)),
        owner_count=listing_dict.get("owner_count"),
        raw_data=listing_dict.get("raw_data", {}),
    )
    result = DealScorer.score_listing(listing, base_msrp=base_msrp)
    return result.__dict__
