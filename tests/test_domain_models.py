from src.models.domain import (
    VehicleModelSpec,
    NHTSARecall,
    NHTSAComplaint,
    EPAFuelEconomy,
    VehicleListing,
    DealScoreResult,
)


def test_vehicle_listing_model():
    listing = VehicleListing(
        vin="5YJ3E1EB8NF123456",
        platform="cargurus",
        platform_id="cg-12345",
        url="https://cargurus.com/Cars/l-12345",
        title="2022 Tesla Model 3 Long Range AWD",
        price=31990,
        mileage=24000,
        make="Tesla",
        model="Model 3",
        year=2022,
        exterior_color="Solid Black",
        distance_miles=18.5,
    )
    assert listing.price == 31990
    assert listing.title_status == "clean"
    assert listing.distance_miles == 18.5


def test_deal_score_result():
    res = DealScoreResult(
        listing_id="listing-123",
        market_value=35000,
        price_delta=-3010,
        deal_score=88.5,
        recommendation="EXCELLENT_DEAL",
        score_breakdown={"price_delta_score": 92.0, "history_score": 85.0},
    )
    assert res.price_delta == -3010
    assert res.recommendation == "EXCELLENT_DEAL"
