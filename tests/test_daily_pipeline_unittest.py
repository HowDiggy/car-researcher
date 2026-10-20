import unittest
import asyncio
from unittest.mock import AsyncMock, patch
from src.workflows.daily_pipeline import DailyCarResearchPipelineWorkflow
from src.activities.notifications import NotificationService


class TestDailyPipeline(unittest.TestCase):
    def test_notification_service_formatting(self):
        sample_deals = [
            {
                "listing": {
                    "title": "2023 Mercedes-Benz EQS 450+ Sedan",
                    "price": 45000,
                    "mileage": 22000,
                    "distance_miles": 18.5,
                    "title_status": "clean",
                    "url": "https://example.com/eqs",
                    "platform": "carscom",
                    "platform_id": "eqs-123",
                },
                "score_data": {
                    "market_value": 52000,
                    "price_delta": -7000,
                    "deal_score": 91.5,
                    "recommendation": "EXCELLENT_DEAL",
                },
            }
        ]
        md = NotificationService.format_deal_digest_markdown(sample_deals)
        self.assertIn("TOP VEHICLE DEALS FOUND", md)
        self.assertIn("2023 Mercedes-Benz EQS 450+", md)
        self.assertIn("$45,000", md)
        self.assertIn("-$7,000 below market", md)
        self.assertIn("91.5/100", md)
        self.assertIn("EXCELLENT_DEAL", md)
        self.assertIn("18.5 mi", md)

    def test_workflow_signal_and_query(self):
        wf = DailyCarResearchPipelineWorkflow()
        initial_summary = wf.get_summary()
        self.assertEqual(initial_summary["total_scraped"], 0)
        self.assertFalse(initial_summary["is_completed"])

        async def run_signal():
            await wf.add_target_model({"make": "Lucid", "model": "Air", "min_year": 2023})

        asyncio.run(run_signal())
        self.assertEqual(len(wf._dynamic_models), 1)
        self.assertEqual(wf._dynamic_models[0]["make"], "Lucid")

    def test_workflow_mock_execution(self):
        wf = DailyCarResearchPipelineWorkflow()

        mock_listings = [
            {
                "vin": "W1KCG2EB6NA123456",
                "platform": "carscom",
                "platform_id": "cc-eqs",
                "url": "https://example.com/eqs",
                "title": "2023 Mercedes EQS 450+",
                "price": 45000,
                "mileage": 25000,
                "make": "Mercedes-Benz",
                "model": "EQS",
                "year": 2023,
                "distance_miles": 15.0,
                "title_status": "clean",
                "accident_count": 0,
                "owner_count": 1,
                "raw_data": {"days_on_market": 45},
            }
        ]

        async def run_pipeline():
            with patch("src.workflows.temporal_compat._MockWorkflow.execute_activity") as mock_exec:
                async def mock_activity_side_effect(activity_fn, *args, **kwargs):
                    fn_name = getattr(activity_fn, "__name__", "")
                    if "scrape" in fn_name:
                        return mock_listings
                    elif "score" in fn_name:
                        return {
                            "market_value": 52000,
                            "price_delta": -7000,
                            "deal_score": 92.0,
                            "recommendation": "EXCELLENT_DEAL",
                            "score_breakdown": {"price_score": 95.0},
                        }
                    elif "persist" in fn_name:
                        return {"persisted_count": 1, "status": "success"}
                    elif "notification" in fn_name:
                        return {"deals_count": 1, "markdown_report": "# Sample Deals Report"}
                    return {}

                mock_exec.side_effect = mock_activity_side_effect

                res = await wf.run(
                    custom_targets=[{"make": "Mercedes-Benz", "model": "EQS", "min_year": 2023}],
                    zip_code="94103",
                    radius_miles=60,
                )
                self.assertEqual(res["status"], "completed")
                self.assertEqual(res["total_listings_scraped"], 1)
                self.assertEqual(res["total_deals_scored"], 1)
                self.assertEqual(res["top_deals_found"], 1)
                self.assertTrue(wf._is_completed)

        asyncio.run(run_pipeline())

    def test_batch_scoring_with_peer_medians(self):
        from src.activities.scoring import score_listings_batch_activity

        batch = [
            {
                "vin": "W1KCG2EB6NA100001",
                "platform": "carscom",
                "platform_id": "cc-1",
                "url": "https://cars.com/1",
                "title": "2023 Mercedes-Benz EQS 450+",
                "price": 38000,
                "mileage": 25000,
                "make": "Mercedes-Benz",
                "model": "EQS 450+",
                "year": 2023,
                "distance_miles": 15.0,
                "raw_data": {"extra_bloat": "x" * 1000, "days_on_market": 45},
            },
            {
                "vin": "W1KCG2EB6NA100002",
                "platform": "carscom",
                "platform_id": "cc-2",
                "url": "https://cars.com/2",
                "title": "2023 Mercedes-Benz EQS 450+",
                "price": 44000,
                "mileage": 26000,
                "make": "Mercedes-Benz",
                "model": "EQS 450+",
                "year": 2023,
                "distance_miles": 15.0,
                "raw_data": {"days_on_market": 45},
            },
            {
                "vin": "W1KCG2EB6NA100003",
                "platform": "carscom",
                "platform_id": "cc-3",
                "url": "https://cars.com/3",
                "title": "2023 Mercedes-Benz EQS 450+",
                "price": 47000,
                "mileage": 24000,
                "make": "Mercedes-Benz",
                "model": "EQS 450+",
                "year": 2023,
                "distance_miles": 15.0,
                "raw_data": {"days_on_market": 45},
            },
        ]

        scored = asyncio.run(score_listings_batch_activity(batch))
        self.assertEqual(len(scored), 3)
        # Cheapest car ($38k) should score higher than the $44k and $47k cars
        self.assertGreater(scored[0]["score_data"]["deal_score"], scored[1]["score_data"]["deal_score"])
        self.assertGreater(scored[1]["score_data"]["deal_score"], scored[2]["score_data"]["deal_score"])
        # Compact payload check: extra_bloat should be pruned from raw_data
        self.assertNotIn("extra_bloat", scored[0]["listing"]["raw_data"])


if __name__ == "__main__":
    unittest.main()
