import unittest
import json
from src.activities.scrapers.carscom import CarsComScraper
from src.activities.scrapers.cargurus import CarGurusScraper
from src.activities.scrapers.aggregator import MarketplaceAggregator
from src.models.domain import VehicleListing


class TestScrapers(unittest.TestCase):
    def setUp(self):
        self.carscom = CarsComScraper()
        self.cargurus = CarGurusScraper()

    def test_carscom_search_url_builder(self):
        url = self.carscom.build_search_url(
            make="BMW",
            model="i4",
            zip_code="94103",
            radius_miles=60,
            min_price=25000,
            max_price=45000,
            min_year=2022,
            max_year=2024,
        )
        self.assertIn("zip=94103", url)
        self.assertIn("maximum_distance=60", url)
        self.assertIn("list_price_min=25000", url)
        self.assertIn("list_price_max=45000", url)
        self.assertIn("year_min=2022", url)
        self.assertIn("year_max=2024", url)
        self.assertIn("bmw", url)

    def test_carscom_jsonld_parsing(self):
        sample_html = """
        <html>
        <head>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "Car",
                "productID": "car-12345",
                "name": "2023 Mercedes-Benz EQS 450+ Sedan",
                "vehicleIdentificationNumber": "W1KCG2EB6NA123456",
                "url": "/vehicledetail/car-12345/",
                "vehicleModelDate": "2023",
                "brand": {"@type": "Brand", "name": "Mercedes-Benz"},
                "model": "EQS",
                "mileageFromOdometer": {"@type": "QuantitativeValue", "value": 22400},
                "offers": {
                    "@type": "Offer",
                    "price": 46995,
                    "priceCurrency": "USD",
                    "seller": {"@type": "AutoDealer", "name": "SF Bay Auto Gallery"}
                }
            }
            </script>
        </head>
        <body></body>
        </html>
        """
        listings = self.carscom.parse_html_listings(sample_html, "https://www.cars.com/test")
        self.assertEqual(len(listings), 1)
        l = listings[0]
        self.assertEqual(l.vin, "W1KCG2EB6NA123456")
        self.assertEqual(l.price, 46995)
        self.assertEqual(l.mileage, 22400)
        self.assertEqual(l.make, "Mercedes-Benz")
        self.assertEqual(l.model, "EQS")
        self.assertEqual(l.year, 2023)
        self.assertEqual(l.seller_name, "SF Bay Auto Gallery")

    def test_carscom_search_controller_index_parsing(self):
        sample_html = """
        <html>
        <head>
            <script id="CarsWeb.SearchController.index" type="application/json">
            {
                "srp_results": {
                    "results": [
                        {
                            "__typename": "SrpListingGridCard",
                            "analytics": {
                                "context": "{\\"trim\\":\\"Standard Range\\",\\"listingId\\":\\"097078bf-24b3-4ee2-b583-73e7f2109f1c\\",\\"mileage\\":\\"26879\\",\\"model\\":\\"Model 3\\",\\"price\\":\\"24794\\",\\"make\\":\\"Tesla\\",\\"vin\\":\\"5YJ3E1EA5LF738257\\",\\"year\\":\\"2020\\",\\"seller\\":{\\"dealerName\\":\\"Ever Cars SF\\"}}"
                            }
                        }
                    ]
                }
            }
            </script>
        </head>
        <body></body>
        </html>
        """
        listings = self.carscom.parse_html_listings(sample_html, "https://www.cars.com/test")
        self.assertEqual(len(listings), 1)
        l = listings[0]
        self.assertEqual(l.vin, "5YJ3E1EA5LF738257")
        self.assertEqual(l.price, 24794)
        self.assertEqual(l.mileage, 26879)
        self.assertEqual(l.make, "Tesla")
        self.assertEqual(l.model, "Model 3")
        self.assertEqual(l.year, 2020)
        self.assertEqual(l.seller_name, "Ever Cars SF")
        self.assertIn("097078bf-24b3-4ee2-b583-73e7f2109f1c", l.url)

    def test_cargurus_api_payload_parsing(self):
        sample_payload = {
            "listings": [
                {
                    "id": "cg-888999",
                    "vin": "KM8KRDAF3PU999999",
                    "price": 28500,
                    "mileage": 18200,
                    "carYear": 2023,
                    "makeName": "Hyundai",
                    "modelName": "Ioniq 5",
                    "trimName": "SEL AWD",
                    "dealerName": "Silicon Valley Hyundai",
                    "daysOnMarket": 42,
                    "distance": 14.2,
                }
            ]
        }
        listings = self.cargurus.parse_api_listing_payload(sample_payload)
        self.assertEqual(len(listings), 1)
        l = listings[0]
        self.assertEqual(l.vin, "KM8KRDAF3PU999999")
        self.assertEqual(l.price, 28500)
        self.assertEqual(l.mileage, 18200)
        self.assertEqual(l.make, "Hyundai")
        self.assertEqual(l.model, "Ioniq 5")
        self.assertEqual(l.distance_miles, 14.2)
        self.assertEqual(l.raw_data.get("days_on_market"), 42)

    def test_aggregator_deduplication_by_vin(self):
        # Two listings from different platforms with identical VIN
        l1 = VehicleListing(
            vin="W1KCG2EB6NA123456",
            platform="carscom",
            platform_id="cc-1",
            url="https://cars.com/1",
            title="2023 Mercedes EQS 450+",
            price=47000,
            mileage=22000,
            make="Mercedes-Benz",
            model="EQS",
            year=2023,
            distance_miles=25.0,
        )
        l2 = VehicleListing(
            vin="W1KCG2EB6NA123456",
            platform="cargurus",
            platform_id="cg-1",
            url="https://cargurus.com/1",
            title="2023 Mercedes EQS 450+",
            price=46500, # Same car, listed $500 cheaper on CarGurus
            mileage=22000,
            make="Mercedes-Benz",
            model="EQS",
            year=2023,
            distance_miles=25.0,
        )
        # Third car outside the 60-mile radius
        l3 = VehicleListing(
            vin="1FTFW1ED5MFC77777",
            platform="carscom",
            platform_id="cc-2",
            url="https://cars.com/2",
            title="Far Away EV",
            price=30000,
            mileage=15000,
            make="Ford",
            model="Mustang Mach-E",
            year=2022,
            distance_miles=120.0, # 120 miles away!
        )

        deduped = MarketplaceAggregator.deduplicate_listings([l1, l2, l3], radius_miles=60)
        # Should drop l3 (too far) and combine l1/l2 (duplicate VIN)
        self.assertEqual(len(deduped), 1)
        winner = deduped[0]
        self.assertEqual(winner.vin, "W1KCG2EB6NA123456")
        self.assertEqual(winner.price, 46500) # Picked lower price


if __name__ == "__main__":
    unittest.main()
