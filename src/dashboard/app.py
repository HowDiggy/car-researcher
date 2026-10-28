import asyncio
import json
import logging
import re
import urllib.parse
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

from src.config.settings import settings
from src.workflows.temporal_compat import HAS_TEMPORAL
from src.dashboard.queries import DashboardRepository
from src.dashboard.templates import (
    render_full_dashboard_page,
    render_deals_section,
    render_listing_history_modal,
    render_model_profile_modal,
    render_scan_status_banner,
)

logger = logging.getLogger(__name__)


def _parse_int(val: Optional[str]) -> Optional[int]:
    if not val:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _parse_float(val: Optional[str]) -> Optional[float]:
    if not val:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


class DashboardApp:
    """
    Async Web Dashboard Controller & HTTP/ASGI server.
    Supports zero-dependency unit testing and native asyncio serving inside Docker.
    """

    def __init__(self, repo: Optional[DashboardRepository] = None):
        self.repo = repo or DashboardRepository()

    @staticmethod
    def _extract_filters(params: Dict[str, str]) -> Dict[str, Any]:
        return {
            "tab": params.get("tab", "all") or "all",
            "view": params.get("view", "grid") or "grid",
            "make_filter": params.get("make", "") or "",
            "q": params.get("q", "") or "",
            "max_price": _parse_int(params.get("max_price")),
            "max_mileage": _parse_int(params.get("max_mileage")),
            "max_distance": _parse_float(params.get("max_distance")),
            "sort": params.get("sort", "score_desc") or "score_desc",
        }

    async def _get_filtered_state(self, params: Dict[str, str]) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
        filters = self._extract_filters(params)
        all_deals = await self.repo.fetch_all_Normalized_deals()
        kpis = self.repo.compute_kpis(all_deals)
        filtered = self.repo.filter_and_sort_deals(
            all_deals,
            tab=filters["tab"],
            make_filter=filters["make_filter"],
            search_query=filters["q"],
            max_price=filters["max_price"],
            max_mileage=filters["max_mileage"],
            max_distance=filters["max_distance"],
            sort_by=filters["sort"],
        )
        return filtered, kpis, filters

    async def trigger_scan_workflow(self, target_spec: str) -> Tuple[Optional[str], Optional[str]]:
        """Trigger a Temporal DailyCarResearchPipelineWorkflow run from the dashboard."""
        if not HAS_TEMPORAL:
            return None, "Temporal SDK not installed in this environment."

        try:
            from temporalio.client import Client
            from src.workflows.daily_pipeline import DailyCarResearchPipelineWorkflow

            custom_targets = None
            if target_spec and target_spec != "ALL" and "|" in target_spec:
                make, model = target_spec.split("|", 1)
                custom_targets = [{"make": make.strip(), "model": model.strip(), "min_year": 2022}]

            client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
            workflow_id = f"dashboard-scan-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
            await client.start_workflow(
                DailyCarResearchPipelineWorkflow.run,
                args=[custom_targets, settings.search_zip_code, settings.search_radius_miles],
                id=workflow_id,
                task_queue=settings.temporal_task_queue_default,
            )
            return workflow_id, None
        except Exception as e:
            logger.error(f"Dashboard failed to start Temporal scan: {e}")
            return None, str(e)

    async def query_scan_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """Query a running or completed Temporal workflow for real-time progress."""
        if not HAS_TEMPORAL:
            return {"is_completed": True, "total_scraped": 0, "total_scored": 0, "top_deals_count": 0}

        try:
            from temporalio.client import Client
            client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
            handle = client.get_workflow_handle(workflow_id)
            try:
                summary = await handle.query("get_summary")
                return summary
            except Exception:
                desc = await handle.describe()
                is_done = desc.status is not None and int(desc.status) != 1
                return {"is_completed": is_done, "total_scraped": 0, "total_scored": 0, "top_deals_count": 0}
        except Exception as e:
            logger.warning(f"Failed to query workflow {workflow_id}: {e}")
            return {"is_completed": True, "total_scraped": 0, "total_scored": 0, "top_deals_count": 0}

    async def handle_request(
        self,
        method: str,
        path: str,
        query_params: Optional[Dict[str, str]] = None,
        body_params: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, Dict[str, str], bytes]:
        """
        Route an HTTP request and return (status_code, headers_dict, body_bytes).
        """
        q_params = query_params or {}
        b_params = body_params or {}
        clean_path = path.rstrip("/") or "/"

        # 1. Main Dashboard HTML Page
        if method in ("GET", "HEAD") and clean_path == "/":
            deals, kpis, filters = await self._get_filtered_state(q_params)
            html_body = render_full_dashboard_page(deals, kpis, filters) if method == "GET" else ""
            return 200, {"Content-Type": "text/html; charset=utf-8"}, html_body.encode("utf-8")

        # 2. HTMX Partial: Filtered Deals Grid / Table
        if method == "GET" and clean_path == "/partials/deals":
            deals, kpis, filters = await self._get_filtered_state(q_params)
            html_body = render_deals_section(deals, kpis, filters)
            return 200, {"Content-Type": "text/html; charset=utf-8"}, html_body.encode("utf-8")

        # 3. HTMX Partial: Listing Price History & Score Breakdown Modal
        m_hist = re.match(r"^/partials/listing/([^/]+)/history$", clean_path)
        if method == "GET" and m_hist:
            listing_id = urllib.parse.unquote(m_hist.group(1))
            history_data = await self.repo.get_listing_history(listing_id)
            html_body = render_listing_history_modal(history_data)
            return 200, {"Content-Type": "text/html; charset=utf-8"}, html_body.encode("utf-8")

        # 4. HTMX Partial: NHTSA & EPA Model Intelligence Modal
        if method == "GET" and clean_path == "/partials/model-profile":
            make = q_params.get("make", "Mercedes-Benz")
            model = q_params.get("model", "EQS")
            year = _parse_int(q_params.get("year")) or 2023
            profile = await self.repo.get_model_intelligence(make, model, year)
            html_body = render_model_profile_modal(profile)
            return 200, {"Content-Type": "text/html; charset=utf-8"}, html_body.encode("utf-8")

        # 5. HTMX Action: Toggle Bookmark / Star
        m_bm = re.match(r"^/api/listing/([^/]+)/bookmark$", clean_path)
        if method == "POST" and m_bm:
            listing_id = urllib.parse.unquote(m_bm.group(1))
            await self.repo.toggle_user_flag(listing_id, "user_bookmarked")
            merged_params = {**q_params, **b_params}
            deals, kpis, filters = await self._get_filtered_state(merged_params)
            html_body = render_deals_section(deals, kpis, filters)
            return 200, {"Content-Type": "text/html; charset=utf-8"}, html_body.encode("utf-8")

        # 6. HTMX Action: Toggle Dismiss / Hide
        m_dis = re.match(r"^/api/listing/([^/]+)/dismiss$", clean_path)
        if method == "POST" and m_dis:
            listing_id = urllib.parse.unquote(m_dis.group(1))
            await self.repo.toggle_user_flag(listing_id, "user_dismissed")
            merged_params = {**q_params, **b_params}
            deals, kpis, filters = await self._get_filtered_state(merged_params)
            html_body = render_deals_section(deals, kpis, filters)
            return 200, {"Content-Type": "text/html; charset=utf-8"}, html_body.encode("utf-8")

        # 7. HTMX Action: Trigger Temporal Marketplace Scan
        if method == "POST" and clean_path == "/api/scan":
            target_spec = b_params.get("target") or q_params.get("target") or "ALL"
            wf_id, err = await self.trigger_scan_workflow(target_spec)
            if err or not wf_id:
                banner = (
                    f'<div class="bg-rose-950/80 border border-rose-700 text-rose-200 px-4 py-2.5 rounded-xl mb-5 text-xs">'
                    f'⚠️ Could not trigger scan: {err}</div>'
                )
            else:
                banner = render_scan_status_banner(wf_id, {"is_completed": False, "total_scraped": 0, "total_scored": 0})
            return 200, {"Content-Type": "text/html; charset=utf-8"}, banner.encode("utf-8")

        # 8. HTMX Poller: Query Temporal Scan Progress
        m_scan = re.match(r"^/api/scan/([^/]+)/status$", clean_path)
        if method == "GET" and m_scan:
            wf_id = urllib.parse.unquote(m_scan.group(1))
            summary = await self.query_scan_workflow(wf_id)
            banner = render_scan_status_banner(wf_id, summary)
            return 200, {"Content-Type": "text/html; charset=utf-8"}, banner.encode("utf-8")

        # 9. Export CSV
        if method == "GET" and clean_path == "/api/export/csv":
            deals, _, _ = await self._get_filtered_state(q_params)
            csv_text = self.repo.export_deals_csv(deals)
            headers = {
                "Content-Type": "text/csv; charset=utf-8",
                "Content-Disposition": 'attachment; filename="bay_area_ev_deals.csv"',
            }
            return 200, headers, csv_text.encode("utf-8")

        # 10. Export Markdown
        if method == "GET" and clean_path == "/api/export/markdown":
            deals, _, _ = await self._get_filtered_state(q_params)
            md_text = self.repo.export_deals_markdown(deals)
            headers = {
                "Content-Type": "text/markdown; charset=utf-8",
            }
            return 200, headers, md_text.encode("utf-8")

        # 11. JSON REST API for programmatic access
        if method == "GET" and clean_path == "/api/deals":
            deals, kpis, filters = await self._get_filtered_state(q_params)
            payload = json.dumps({"kpis": kpis, "filters": filters, "count": len(deals), "deals": deals}, default=str)
            return 200, {"Content-Type": "application/json"}, payload.encode("utf-8")

        # 12. Healthcheck endpoint
        if method == "GET" and clean_path == "/api/health":
            payload = json.dumps({"status": "ok", "service": "car-researcher-dashboard"})
            return 200, {"Content-Type": "application/json"}, payload.encode("utf-8")

        return 404, {"Content-Type": "text/plain"}, b"Not Found"


async def _handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, app: DashboardApp) -> None:
    """Lightweight async HTTP/1.1 connection handler."""
    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=10.0)
        if not request_line:
            return
        parts = request_line.decode("utf-8", errors="ignore").strip().split(" ")
        if len(parts) < 2:
            return
        method, raw_target = parts[0].upper(), parts[1]

        # Read headers
        content_length = 0
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if not line or line in (b"\r\n", b"\n"):
                break
            hdr = line.decode("utf-8", errors="ignore").strip()
            if hdr.lower().startswith("content-length:"):
                try:
                    content_length = int(hdr.split(":", 1)[1].strip())
                except ValueError:
                    content_length = 0

        body_bytes = b""
        if content_length > 0:
            body_bytes = await asyncio.wait_for(reader.readexactly(content_length), timeout=5.0)

        parsed_url = urllib.parse.urlsplit(raw_target)
        query_params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed_url.query, keep_blank_values=True).items()}

        body_params: Dict[str, str] = {}
        if body_bytes:
            body_str = body_bytes.decode("utf-8", errors="ignore")
            body_params = {k: v[0] for k, v in urllib.parse.parse_qs(body_str, keep_blank_values=True).items()}

        status_code, resp_headers, resp_body = await app.handle_request(
            method=method,
            path=parsed_url.path,
            query_params=query_params,
            body_params=body_params,
        )

        status_text = {200: "OK", 404: "Not Found", 500: "Internal Server Error"}.get(status_code, "OK")
        header_lines = [
            f"HTTP/1.1 {status_code} {status_text}",
            f"Content-Length: {len(resp_body)}",
            "Connection: close",
        ]
        for hk, hv in resp_headers.items():
            header_lines.append(f"{hk}: {hv}")

        raw_response = ("\r\n".join(header_lines) + "\r\n\r\n").encode("utf-8") + resp_body
        writer.write(raw_response)
        await writer.drain()
    except Exception as e:
        logger.debug(f"Dashboard HTTP connection error: {e}")
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def start_dashboard_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Initialize DB tables if needed and run the async Web Dashboard server."""
    try:
        from src.db.engine import init_db
        await init_db()
    except Exception as e:
        logger.warning(f"Dashboard DB init check: {e}")

    app = DashboardApp()
    server = await asyncio.start_server(lambda r, w: _handle_client(r, w, app), host=host, port=port)
    logger.info(f"🌐 Car Researcher Web Dashboard live at http://{host}:{port}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    asyncio.run(start_dashboard_server())
