from datetime import timedelta
from typing import Dict, Any, List, Optional
from src.workflows.temporal_compat import workflow, RetryPolicy

with workflow.unsafe.imports_passed_through():
    from src.activities.scrapers.aggregator import scrape_target_model_activity
    from src.activities.scoring import score_listing_activity, score_listings_batch_activity
    from src.activities.persistence import persist_listings_and_scores_activity
    from src.activities.notifications import send_daily_deals_notification_activity
    from src.config.settings import settings


@workflow.defn
class DailyCarResearchPipelineWorkflow:
    """
    Top-level scheduled workflow that runs daily across all target vehicles.
    Surveys live inventory in the Bay Area, evaluates deals, records price snapshots,
    and alerts the user of top opportunities.
    """

    def __init__(self) -> None:
        self._total_scraped: int = 0
        self._scored_deals: List[Dict[str, Any]] = []
        self._top_deals: List[Dict[str, Any]] = []
        self._is_completed: bool = False
        self._dynamic_models: List[Dict[str, Any]] = []

    @workflow.query
    def get_summary(self) -> Dict[str, Any]:
        """Temporal query to inspect real-time progress and summary."""
        return {
            "total_scraped": self._total_scraped,
            "total_scored": len(self._scored_deals),
            "top_deals_count": len(self._top_deals),
            "is_completed": self._is_completed,
            "top_deals": self._top_deals[:5],
        }

    @workflow.signal
    async def add_target_model(self, model_spec: Dict[str, Any]) -> None:
        """Temporal signal to inject an ad-hoc vehicle make/model into the search run."""
        self._dynamic_models.append(model_spec)

    @workflow.run
    async def run(
        self,
        custom_targets: Optional[List[Dict[str, Any]]] = None,
        zip_code: Optional[str] = None,
        radius_miles: Optional[int] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
    ) -> Dict[str, Any]:
        workflow.logger.info("Starting DailyCarResearchPipelineWorkflow")

        target_zip = zip_code or settings.search_zip_code
        target_radius = radius_miles or settings.search_radius_miles
        target_min_price = min_price or settings.search_min_price
        target_max_price = max_price or settings.search_max_price

        # Build list of models to analyze
        if custom_targets:
            models_to_search = custom_targets
        else:
            models_to_search = [
                {
                    "make": m.make,
                    "model": m.model,
                    "min_year": m.min_year or settings.search_min_year,
                    "max_year": m.max_year or settings.search_max_year,
                }
                for m in settings.search_target_models
            ]

        pending_models = list(models_to_search)
        models_analyzed_count = 0

        standard_retry = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=30),
            maximum_attempts=3,
        )

        all_scored_items: List[Dict[str, Any]] = []

        # 1. Iterate over target models and dynamically drain any signals received mid-run
        while pending_models or self._dynamic_models:
            if self._dynamic_models:
                pending_models.extend(self._dynamic_models)
                self._dynamic_models.clear()

            target = pending_models.pop(0)
            models_analyzed_count += 1

            make = target.get("make", "")
            model = target.get("model", "")
            min_y = target.get("min_year", settings.search_min_year)
            max_y = target.get("max_year", settings.search_max_year)

            workflow.logger.info(f"Scanning marketplace for {make} {model} within {target_radius}mi of {target_zip}")

            try:
                listings: List[Dict[str, Any]] = await workflow.execute_activity(
                    scrape_target_model_activity,
                    args=[make, model, target_zip, target_radius, target_min_price, target_max_price, min_y, max_y],
                    start_to_close_timeout=timedelta(minutes=3),
                    retry_policy=standard_retry,
                )
            except Exception as e:
                workflow.logger.error(f"Failed to scrape {make} {model}: {e}")
                listings = []

            self._total_scraped += len(listings)
            if not listings:
                continue

            # 2. Score model listings in a single batch activity (eliminates N+1 RPC overhead)
            try:
                batch_res: Any = await workflow.execute_activity(
                    score_listings_batch_activity,
                    args=[listings],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=standard_retry,
                )
                if isinstance(batch_res, list):
                    all_scored_items.extend(batch_res)
                elif isinstance(batch_res, dict):
                    # Backwards-compatible fallback for single-score mocks in unit tests
                    for listing in listings:
                        all_scored_items.append({"listing": listing, "score_data": batch_res})
            except Exception as score_err:
                workflow.logger.warning(f"Failed to batch-score listings for {make} {model}: {score_err}")

        # 3. Sort all discovered listings by deal_score descending, breaking ties by largest dollar savings
        all_scored_items.sort(
            key=lambda x: (
                x.get("score_data", {}).get("deal_score", 0.0),
                -int(x.get("score_data", {}).get("price_delta", 0)),
            ),
            reverse=True,
        )
        self._scored_deals = all_scored_items

        # 4. Filter for Top Deals (deal_score >= 80 or top 5)
        self._top_deals = [
            d for d in all_scored_items
            if d.get("score_data", {}).get("deal_score", 0.0) >= 80.0
        ]
        if not self._top_deals and all_scored_items:
            self._top_deals = all_scored_items[:5]

        # 5. Persist listings, price snapshots, and deal scores to Database
        try:
            await workflow.execute_activity(
                persist_listings_and_scores_activity,
                args=[all_scored_items],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=standard_retry,
            )
        except Exception as persist_err:
            workflow.logger.warning(f"Persistence activity failed: {persist_err}")

        # 6. Dispatch Notifications / Alert if deals were found
        notification_res: Dict[str, Any] = {}
        if self._top_deals:
            try:
                notification_res = await workflow.execute_activity(
                    send_daily_deals_notification_activity,
                    args=[self._top_deals],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=standard_retry,
                )
            except Exception as notif_err:
                workflow.logger.warning(f"Notification dispatch failed: {notif_err}")

        self._is_completed = True

        return {
            "status": "completed",
            "zip_code": target_zip,
            "radius_miles": target_radius,
            "models_analyzed": models_analyzed_count,
            "total_listings_scraped": self._total_scraped,
            "total_deals_scored": len(self._scored_deals),
            "top_deals_found": len(self._top_deals),
            "top_deals": self._top_deals[:5],
            "markdown_report": notification_res.get("markdown_report", ""),
        }
