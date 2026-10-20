from src.config.settings import Settings, TargetVehicleConfig


def test_settings_bay_area_defaults():
    s = Settings(
        search_zip_code="94103",
        search_radius_miles=60,
        search_min_price=20000,
        search_max_price=55000,
    )
    assert s.search_zip_code == "94103"
    assert s.search_radius_miles == 60
    assert s.search_min_price == 20000
    assert s.search_max_price == 55000
    assert "BEV" in s.search_powertrains


def test_target_vehicle_models_parsing():
    s = Settings()
    assert len(s.search_target_models) >= 10
    makes = [m.make for m in s.search_target_models]
    assert "Hyundai" in makes
    assert "Tesla" in makes
    assert "Ford" in makes
    assert "BMW" in makes
    assert "Mercedes-Benz" in makes
    assert "Cadillac" in makes
