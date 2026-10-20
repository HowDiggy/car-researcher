import unittest
from unittest.mock import AsyncMock, patch
import asyncio
from src.models.domain import VehicleListing, DealScoreResult, NHTSARecall
from src.activities.gov_apis import GovAPIClient
from src.activities.scoring import DealScorer, BayAreaGeoLookup


class TestCarResearcherDomain(unittest.TestCase):
    def test_vehicle_listing_initialization(self):
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
        self.assertEqual(listing.price, 31990)
        self.assertEqual(listing.title_status, "clean")
        self.assertEqual(listing.distance_miles, 18.5)

    def test_deal_score_initialization(self):
        res = DealScoreResult(
            listing_id="listing-123",
            market_value=35000,
            price_delta=-3010,
            deal_score=88.5,
            recommendation="EXCELLENT_DEAL",
            score_breakdown={"price_delta_score": 92.0, "history_score": 85.0},
        )
        self.assertEqual(res.price_delta, -3010)
        self.assertEqual(res.recommendation, "EXCELLENT_DEAL")

    def test_deal_scorer_algorithm(self):
        # Great deal scenario: $4,000 below market, 1 owner, 0 accidents, 15 miles away
        listing = VehicleListing(
            vin="KM8KRDAF3PU123456",
            platform="cargurus",
            platform_id="cg-999",
            url="https://example.com/ioniq5",
            title="2023 Hyundai Ioniq 5 SEL",
            price=25000,
            mileage=20000,
            make="Hyundai",
            model="Ioniq 5",
            year=2023,
            distance_miles=15.0,
            title_status="clean",
            accident_count=0,
            owner_count=1,
            raw_data={"days_on_market": 45},
        )
        score_res = DealScorer.score_listing(
            listing,
            market_value=29000, # price is $4,000 below market
        )
        self.assertEqual(score_res.price_delta, -4000)
        self.assertGreaterEqual(score_res.deal_score, 85.0)
        self.assertEqual(score_res.recommendation, "EXCELLENT_DEAL")

    def test_deal_scorer_penalizes_salvage(self):
        # Salvage title scenario
        listing = VehicleListing(
            vin="KM8KRDAF3PU123456",
            platform="cargurus",
            platform_id="cg-998",
            url="https://example.com/ioniq5-salvage",
            title="2023 Hyundai Ioniq 5 SEL Salvage",
            price=19000,
            mileage=20000,
            make="Hyundai",
            model="Ioniq 5",
            year=2023,
            distance_miles=15.0,
            title_status="salvage",
            accident_count=2,
            owner_count=3,
        )
        score_res = DealScorer.score_listing(listing, market_value=29000)
        self.assertNotEqual(score_res.recommendation, "EXCELLENT_DEAL")
        self.assertLess(score_res.score_breakdown["history_score"], 60.0)

    def test_deal_scorer_luxury_vehicle(self):
        # Mercedes-Benz EQS original MSRP ~$105k, now priced at $45k with 30k miles
        listing = VehicleListing(
            vin="W1KCG2EB6NA123456",
            platform="cargurus",
            platform_id="cg-eqs-01",
            url="https://example.com/eqs",
            title="2022 Mercedes-Benz EQS 450+ Sedan",
            price=45000,
            mileage=30000,
            make="Mercedes-Benz",
            model="EQS",
            year=2022,
            distance_miles=22.0,
            title_status="clean",
            accident_count=0,
            owner_count=1,
            raw_data={"days_on_market": 55},
        )
        score_res = DealScorer.score_listing(listing)
        self.assertIsNotNone(score_res.market_value)
        # Should recognize base MSRP around 105k and calculate fair market value
        self.assertGreater(score_res.market_value, 40000)
        self.assertIn(score_res.recommendation, ["EXCELLENT_DEAL", "GOOD_VALUE", "FAIR_MARKET"])

    def test_gov_api_vin_decoding_mock(self):
        mock_payload = {
            "Results": [
                {"Variable": "Make", "Value": "HYUNDAI"},
                {"Variable": "Model", "Value": "Ioniq 5"},
                {"Variable": "Model Year", "Value": "2023"},
                {"Variable": "ElectrificationLevel", "Value": "BEV (Battery Electric Vehicle)"},
            ]
        }
        client = GovAPIClient()

        async def run_test():
            with patch.object(client, "_get_json", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = mock_payload

                data = await client.decode_vin("KM8KRDAF3PU123456")
                self.assertEqual(data.get("Make"), "HYUNDAI")
                self.assertEqual(data.get("Model"), "Ioniq 5")
                self.assertEqual(data.get("Model Year"), "2023")

        asyncio.run(run_test())

    def test_trim_aware_msrp_lookup(self):
        # Differentiate trims within the same model line
        msrp_eqs_base = DealScorer.get_estimated_original_msrp("Mercedes-Benz", "EQS 450+", trim_detail="Base")
        msrp_eqs_580 = DealScorer.get_estimated_original_msrp("Mercedes-Benz", "EQS 580", trim_detail="4MATIC")
        msrp_eqs_amg = DealScorer.get_estimated_original_msrp("Mercedes-Benz", "AMG EQS", trim_detail="4MATIC+")
        self.assertEqual(msrp_eqs_base, 105000)
        self.assertEqual(msrp_eqs_580, 126000)
        self.assertEqual(msrp_eqs_amg, 147500)

        msrp_i4_35 = DealScorer.get_estimated_original_msrp("BMW", "i4", trim_detail="eDrive35")
        msrp_i4_m50 = DealScorer.get_estimated_original_msrp("BMW", "i4", trim_detail="M50")
        self.assertLess(msrp_i4_35, msrp_i4_m50)

    def test_non_saturating_score_differentiation(self):
        # A car 25% below FMV must score strictly higher than a car 12% below FMV
        base_kwargs = dict(
            vin="W1KCG2EB6NA123456",
            platform="carscom",
            platform_id="cc-1",
            url="https://example.com/1",
            title="2023 Mercedes-Benz EQS 450+",
            mileage=25000,
            make="Mercedes-Benz",
            model="EQS",
            year=2023,
            distance_miles=20.0,
        )
        car_12pct_below = VehicleListing(price=44000, **base_kwargs)
        car_25pct_below = VehicleListing(price=37500, **base_kwargs)

        score_12 = DealScorer.score_listing(car_12pct_below, market_value=50000)
        score_25 = DealScorer.score_listing(car_25pct_below, market_value=50000)
        self.assertGreater(score_25.deal_score, score_12.deal_score)

    def test_bay_area_zip_distance_resolver(self):
        dist_sf, city_sf = BayAreaGeoLookup.resolve_zip("94103")
        self.assertEqual(city_sf, "San Francisco")
        self.assertLessEqual(dist_sf, 5.0)

        dist_wc, city_wc = BayAreaGeoLookup.resolve_zip("94596")
        self.assertEqual(city_wc, "Walnut Creek")
        self.assertLessEqual(dist_wc, 30.0)

        dist_la, city_la = BayAreaGeoLookup.resolve_zip("90210")
        self.assertEqual(city_la, "Out of Region")
        self.assertGreater(dist_la, 100.0)


if __name__ == "__main__":
    unittest.main()
