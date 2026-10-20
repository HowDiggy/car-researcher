import asyncio
import argparse
import logging
import sys
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config.settings import settings
from src.workflows.daily_pipeline import DailyCarResearchPipelineWorkflow
from src.workflows.temporal_compat import HAS_TEMPORAL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("car-researcher")


async def run_standalone_pipeline(
    make: Optional[str] = None,
    model: Optional[str] = None,
    radius: Optional[int] = None,
) -> None:
    """Execute pipeline in standalone mode without requiring a live Temporal cluster."""
    print("=" * 70)
    print("🚗 CAR RESEARCHER AI PIPELINE (STANDALONE RUN)")
    print(f"📍 Location Anchor: Bay Area ZIP {settings.search_zip_code}")
    print(f"🎯 Search Radius: {radius or settings.search_radius_miles} miles")
    print(f"💰 Price Budget: ${settings.search_min_price:,} - ${settings.search_max_price:,}")
    print("=" * 70)

    custom_targets = None
    if make and model:
        custom_targets = [{"make": make, "model": model, "min_year": 2022}]

    wf = DailyCarResearchPipelineWorkflow()
    result = await wf.run(
        custom_targets=custom_targets,
        zip_code=settings.search_zip_code,
        radius_miles=radius or settings.search_radius_miles,
        min_price=settings.search_min_price,
        max_price=settings.search_max_price,
    )

    print("\n" + "=" * 70)
    print("📊 DAILY PIPELINE RUN SUMMARY")
    print("=" * 70)
    print(f"Models Analyzed:       {result.get('models_analyzed', 0)}")
    print(f"Total Listings Found:  {result.get('total_listings_scraped', 0)}")
    print(f"Total Deals Scored:    {result.get('total_deals_scored', 0)}")
    print(f"Top Deals Discovered:  {result.get('top_deals_found', 0)}")
    print("=" * 70 + "\n")

    report = result.get("markdown_report", "")
    if report:
        print(report)
    else:
        print("No active listings currently met the threshold score in this run.")


async def start_temporal_worker() -> None:
    """Start Temporal worker processes to handle distributed activities and workflows."""
    if not HAS_TEMPORAL:
        logger.error("temporalio library is not installed. Please install dependencies or run in Docker.")
        sys.exit(1)

    from temporalio.client import Client
    from temporalio.worker import Worker

    from src.workflows.daily_pipeline import DailyCarResearchPipelineWorkflow
    from src.workflows.model_profiler import ModelProfilerWorkflow
    from src.activities.gov_apis import (
        fetch_nhtsa_recalls_activity,
        fetch_nhtsa_complaints_activity,
        fetch_epa_data_activity,
        decode_vin_activity,
    )
    from src.activities.scrapers.aggregator import scrape_target_model_activity
    from src.activities.scoring import score_listing_activity
    from src.activities.persistence import persist_listings_and_scores_activity
    from src.activities.notifications import send_daily_deals_notification_activity

    logger.info(f"Connecting to Temporal Server at {settings.temporal_host}...")
    client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)

    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue_default,
        workflows=[DailyCarResearchPipelineWorkflow, ModelProfilerWorkflow],
        activities=[
            fetch_nhtsa_recalls_activity,
            fetch_nhtsa_complaints_activity,
            fetch_epa_data_activity,
            decode_vin_activity,
            scrape_target_model_activity,
            score_listing_activity,
            persist_listings_and_scores_activity,
            send_daily_deals_notification_activity,
        ],
    )

    logger.info(f"Temporal Worker online on task queue: {settings.temporal_task_queue_default}. Waiting for jobs...")
    await worker.run()


def main():
    parser = argparse.ArgumentParser(description="Car Researcher AI Agent Pipeline")
    parser.add_argument("--run-once", action="store_true", help="Execute single pipeline run locally")
    parser.add_argument("--make", type=str, help="Filter to specific make (e.g., 'Mercedes-Benz')")
    parser.add_argument("--model", type=str, help="Filter to specific model (e.g., 'EQS')")
    parser.add_argument("--radius", type=int, help="Search radius in miles (default: 60)")
    parser.add_argument("--start-worker", action="store_true", help="Start Temporal worker daemon")

    args = parser.parse_args()

    if args.start_worker:
        asyncio.run(start_temporal_worker())
    elif args.run_once or args.make or args.model:
        asyncio.run(run_standalone_pipeline(make=args.make, model=args.model, radius=args.radius))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
