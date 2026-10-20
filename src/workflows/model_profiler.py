from datetime import timedelta
from typing import Dict, Any, List
from src.workflows.temporal_compat import workflow, RetryPolicy

with workflow.unsafe.imports_passed_through():
    from src.activities.gov_apis import (
        fetch_nhtsa_recalls_activity,
        fetch_nhtsa_complaints_activity,
        fetch_epa_data_activity,
    )


@workflow.defn
class ModelProfilerWorkflow:
    """Workflow to aggregate model-level intelligence (Recalls, Complaints, EPA Range & MPGe)."""

    @workflow.run
    async def run(self, make: str, model: str, year: int) -> Dict[str, Any]:
        workflow.logger.info(f"Starting ModelProfilerWorkflow for {year} {make} {model}")

        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=30),
            maximum_attempts=4,
        )

        # 1. Fetch Recalls from NHTSA
        recalls: List[Dict[str, Any]] = await workflow.execute_activity(
            fetch_nhtsa_recalls_activity,
            args=[make, model, year],
            start_to_close_timeout=timedelta(seconds=45),
            retry_policy=retry_policy,
        )

        # 2. Fetch Complaints from NHTSA
        complaints: List[Dict[str, Any]] = await workflow.execute_activity(
            fetch_nhtsa_complaints_activity,
            args=[make, model, year],
            start_to_close_timeout=timedelta(seconds=45),
            retry_policy=retry_policy,
        )

        # 3. Fetch EPA Specs & MPGe
        epa_specs: List[Dict[str, Any]] = await workflow.execute_activity(
            fetch_epa_data_activity,
            args=[make, model, year],
            start_to_close_timeout=timedelta(seconds=45),
            retry_policy=retry_policy,
        )

        return {
            "make": make,
            "model": model,
            "year": year,
            "recalls_count": len(recalls),
            "recalls": recalls,
            "complaints_count": len(complaints),
            "complaints": complaints,
            "epa_specs": epa_specs,
        }
