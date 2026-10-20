import json
import unittest
from src.dashboard.queries import DashboardRepository
from src.dashboard.app import DashboardApp


def _sample_deals():
    return [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "vin": "W1KCG2DB6PA043095",
            "platform": "cars_com",
            "platform_id": "cc-101",
            "url": "https://www.cars.com/vehicledetail/cc-101/",
            "title": "2023 Mercedes-Benz EQS 450+ Base",
            "price": 39988,
            "mileage": 16479,
            "exterior_color": "Obsidian Black",
            "interior_color": "Black",
            "trim_detail": "EQS 450+",
            "seller_name": "Mercedes-Benz of Stevens Creek",
            "location_city": "San Jose",
            "distance_miles": 41.2,
            "title_status": "clean",
            "accident_count": 0,
            "owner_count": 1,
            "photos": ["https://images.cars.com/phototab/1.jpg"],
            "raw_data": {"make": "Mercedes-Benz", "model": "EQS", "year": 2023},
            "market_value": 52778,
            "price_delta": -12790,
            "deal_score": 87.6,
            "recommendation": "Excellent Deal - Strong Buy",
            "score_breakdown": {
                "price_score": 98.4,
                "history_score": 100.0,
                "leverage_score": 50.0,
                "proximity_score": 79.0,
                "estimated_msrp": 105550,
            },
            "price_change": -1500,
            "days_on_market": 12,
            "snapshot_count": 3,
            "price_history": [
                {"time": "2026-10-20 04:00:00", "price": 39988, "mileage": 16479, "price_change": -1500, "days_on_market": 12},
                {"time": "2026-10-18 04:00:00", "price": 41488, "mileage": 16479, "price_change": 0, "days_on_market": 10},
            ],
        },
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "vin": "W1KCG4EB5PA031214",
            "platform": "cars_com",
            "platform_id": "cc-102",
            "url": "https://www.cars.com/vehicledetail/cc-102/",
            "title": "2023 Mercedes-Benz EQS 580 4MATIC",
            "price": 50995,
            "mileage": 19576,
            "exterior_color": "Polar White",
            "interior_color": "Macchiato Beige",
            "trim_detail": "EQS 580 4MATIC",
            "seller_name": "Autobahn Motors",
            "location_city": "Belmont",
            "distance_miles": 19.6,
            "title_status": "clean",
            "accident_count": 0,
            "owner_count": 1,
            "photos": [],
            "raw_data": {"make": "Mercedes-Benz", "model": "EQS", "year": 2023},
            "market_value": 63522,
            "price_delta": -12527,
            "deal_score": 89.2,
            "recommendation": "Excellent Deal - Strong Buy",
            "score_breakdown": {
                "price_score": 94.6,
                "history_score": 100.0,
                "leverage_score": 50.0,
                "proximity_score": 100.0,
                "estimated_msrp": 127100,
            },
            "price_change": 0,
            "days_on_market": 5,
            "snapshot_count": 2,
        },
        {
            "id": "33333333-3333-3333-3333-333333333333",
            "vin": "KNDC4DLC6P5123456",
            "platform": "cargurus",
            "platform_id": "cg-201",
            "url": "https://www.cargurus.com/Cars/cg-201",
            "title": "2023 Kia EV6 Wind AWD",
            "price": 29500,
            "mileage": 22000,
            "exterior_color": "Yacht Blue",
            "interior_color": "Black",
            "trim_detail": "Wind AWD",
            "seller_name": "Oakland Kia",
            "location_city": "Oakland",
            "distance_miles": 10.5,
            "title_status": "clean",
            "accident_count": 0,
            "owner_count": 1,
            "photos": [],
            "raw_data": {"make": "Kia", "model": "EV6", "year": 2023},
            "market_value": 31000,
            "price_delta": -1500,
            "deal_score": 76.5,
            "recommendation": "Good Value - Worth Investigating",
            "score_breakdown": {
                "price_score": 69.3,
                "history_score": 100.0,
                "leverage_score": 50.0,
                "proximity_score": 100.0,
                "estimated_msrp": 52600,
            },
            "price_change": 0,
            "days_on_market": 18,
            "snapshot_count": 1,
        },
    ]


class TestDashboardUnit(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repo = DashboardRepository(fallback_deals=_sample_deals())
        self.app = DashboardApp(repo=self.repo)

    async def test_main_dashboard_page_and_kpis(self):
        status, headers, body = await self.app.handle_request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        html_str = body.decode("utf-8")
        self.assertIn("Bay Area EV Deal Surveillance", html_str)
        self.assertIn("2023 Mercedes-Benz EQS 580 4MATIC", html_str)
        self.assertIn("2023 Kia EV6 Wind AWD", html_str)
        self.assertIn("Scan Marketplace", html_str)

    async def test_partials_deals_filtering_and_table_view(self):
        # Filter by make=Kia and table view
        status, _, body = await self.app.handle_request(
            "GET",
            "/partials/deals",
            query_params={"make": "Kia", "view": "table"},
        )
        self.assertEqual(status, 200)
        html_str = body.decode("utf-8")
        self.assertIn("<table", html_str)
        self.assertIn("2023 Kia EV6 Wind AWD", html_str)
        self.assertNotIn("EQS 580 4MATIC", html_str)

        # Filter by tab=price_drops
        status2, _, body2 = await self.app.handle_request(
            "GET",
            "/partials/deals",
            query_params={"tab": "price_drops"},
        )
        self.assertEqual(status2, 200)
        html_drops = body2.decode("utf-8")
        self.assertIn("2023 Mercedes-Benz EQS 450+ Base", html_drops)
        self.assertNotIn("2023 Kia EV6 Wind AWD", html_drops)

    async def test_bookmark_and_dismiss_toggles(self):
        target_id = "11111111-1111-1111-1111-111111111111"

        # 1. Bookmark listing 1
        status, _, _ = await self.app.handle_request("POST", f"/api/listing/{target_id}/bookmark")
        self.assertEqual(status, 200)

        # Verify it shows up in the 'bookmarked' tab
        _, _, bm_body = await self.app.handle_request("GET", "/partials/deals", query_params={"tab": "bookmarked"})
        self.assertIn("2023 Mercedes-Benz EQS 450+ Base", bm_body.decode("utf-8"))

        # 2. Dismiss listing 3 (Kia EV6)
        kia_id = "33333333-3333-3333-3333-333333333333"
        await self.app.handle_request("POST", f"/api/listing/{kia_id}/dismiss")

        # Verify Kia is hidden from 'all' active tab
        _, _, all_body = await self.app.handle_request("GET", "/partials/deals", query_params={"tab": "all"})
        self.assertNotIn("2023 Kia EV6 Wind AWD", all_body.decode("utf-8"))

        # Verify Kia appears in 'dismissed' tab
        _, _, dis_body = await self.app.handle_request("GET", "/partials/deals", query_params={"tab": "dismissed"})
        self.assertIn("2023 Kia EV6 Wind AWD", dis_body.decode("utf-8"))

    async def test_listing_history_modal(self):
        target_id = "11111111-1111-1111-1111-111111111111"
        status, _, body = await self.app.handle_request("GET", f"/partials/listing/{target_id}/history")
        self.assertEqual(status, 200)
        html_str = body.decode("utf-8")
        self.assertIn("TimescaleDB Price Snapshots", html_str)
        self.assertIn("W1KCG2DB6PA043095", html_str)
        self.assertIn("$39,988", html_str)
        self.assertIn("-$1,500", html_str)

    async def test_exports_and_json_api(self):
        # CSV export
        status_csv, headers_csv, body_csv = await self.app.handle_request("GET", "/api/export/csv")
        self.assertEqual(status_csv, 200)
        self.assertIn("text/csv", headers_csv["Content-Type"])
        csv_text = body_csv.decode("utf-8")
        self.assertIn("W1KCG2DB6PA043095", csv_text)
        self.assertIn("W1KCG4EB5PA031214", csv_text)

        # Markdown export
        status_md, headers_md, body_md = await self.app.handle_request("GET", "/api/export/markdown")
        self.assertEqual(status_md, 200)
        self.assertIn("text/markdown", headers_md["Content-Type"])
        md_text = body_md.decode("utf-8")
        self.assertIn("TOP VEHICLE DEALS FOUND", md_text)

        # JSON API
        status_json, _, body_json = await self.app.handle_request("GET", "/api/deals")
        self.assertEqual(status_json, 200)
        payload = json.loads(body_json.decode("utf-8"))
        self.assertEqual(payload["count"], 3)
        self.assertEqual(payload["kpis"]["excellent_count"], 2)


if __name__ == "__main__":
    unittest.main()
