import csv
import io
import logging
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

try:
    from sqlalchemy import text
    from sqlalchemy.orm.attributes import flag_modified
    from src.db.engine import get_db_session
    from src.db.models import Listing
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

from src.config.settings import settings
from src.activities.gov_apis import GovAPIClient
from src.activities.notifications import NotificationService

logger = logging.getLogger(__name__)

# In-memory cache for NHTSA/EPA model profiles so modal opens instantaneously on repeat views
_MODEL_PROFILE_CACHE: Dict[str, Dict[str, Any]] = {}


def _infer_make_model_year(title: str, raw_data: Dict[str, Any]) -> Tuple[str, str, int]:
    """Extract make, model, and year from raw_data or listing title."""
    year = int(raw_data.get("year") or 0)
    make = str(raw_data.get("make") or "").strip()
    model = str(raw_data.get("model") or "").strip()

    if not year:
        m_yr = re.search(r"\b(202\d)\b", title or "")
        year = int(m_yr.group(1)) if m_yr else 2023

    if not make or not model:
        # Match against known watchlist makes
        title_clean = re.sub(r"^\b202\d\b\s*", "", (title or "").strip())
        for target in settings.search_target_models:
            if title_clean.lower().startswith(target.make.lower()):
                make = make or target.make
                rem = title_clean[len(target.make):].strip()
                model = model or (rem.split()[0] if rem else target.model)
                break
        if not make and title_clean:
            parts = title_clean.split()
            make = parts[0]
            model = parts[1] if len(parts) > 1 else ""

    return make, model, year


class DashboardRepository:
    """Data access layer for the Web Dashboard with zero-dependency in-memory fallback."""

    def __init__(self, fallback_deals: Optional[List[Dict[str, Any]]] = None):
        self._fallback_deals: List[Dict[str, Any]] = fallback_deals or []

    async def fetch_all_Normalized_deals(self) -> List[Dict[str, Any]]:
        """Fetch all active listings joined with their latest deal_scores and price_snapshots."""
        if not HAS_SQLALCHEMY or self._fallback_deals:
            return [self._normalize_record(d) for d in self._fallback_deals]

        sql = text("""
            SELECT
                l.id::text AS id,
                l.vin,
                l.platform,
                l.platform_id,
                l.url,
                l.title,
                l.price,
                l.mileage,
                l.exterior_color,
                l.interior_color,
                l.trim_detail,
                l.seller_name,
                l.location_city,
                l.distance_miles,
                l.title_status,
                l.accident_count,
                l.owner_count,
                l.photos,
                l.raw_data,
                l.first_seen,
                l.last_seen,
                ds.market_value,
                ds.price_delta,
                ds.deal_score,
                ds.recommendation,
                ds.score_breakdown,
                ps.price_change,
                ps.days_on_market,
                ps.snapshot_count
            FROM listings l
            LEFT JOIN LATERAL (
                SELECT market_value, price_delta, deal_score, recommendation, score_breakdown
                FROM deal_scores
                WHERE listing_id = l.id
                ORDER BY scored_at DESC
                LIMIT 1
            ) ds ON true
            LEFT JOIN LATERAL (
                SELECT
                    price_change,
                    days_on_market,
                    (SELECT COUNT(*) FROM price_snapshots WHERE listing_id = l.id) AS snapshot_count
                FROM price_snapshots
                WHERE listing_id = l.id
                ORDER BY time DESC
                LIMIT 1
            ) ps ON true
            WHERE l.is_active = true
        """)

        records: List[Dict[str, Any]] = []
        try:
            async with get_db_session() as session:
                res = await session.execute(sql)
                for row in res.mappings():
                    records.append(self._normalize_record(dict(row)))
        except Exception as e:
            logger.warning(f"Dashboard DB query fallback: {e}")

        return records

    @staticmethod
    def _normalize_record(row: Dict[str, Any]) -> Dict[str, Any]:
        """Standardize a DB or fallback dict into a unified dashboard deal item."""
        raw = row.get("raw_data") or {}
        if isinstance(raw, str):
            import json
            try:
                raw = json.loads(raw)
            except Exception:
                raw = {}

        title = row.get("title") or "Vehicle Listing"
        make, model, year = _infer_make_model_year(title, raw)
        if row.get("make"):
            make = row["make"]
        if row.get("model"):
            model = row["model"]
        if row.get("year"):
            year = int(row["year"])

        price = int(row.get("price") or 0)
        market_value = int(row.get("market_value") or price)
        price_delta = int(row.get("price_delta") if row.get("price_delta") is not None else (price - market_value))
        deal_score = float(row.get("deal_score") or 0.0)
        recommendation = row.get("recommendation") or "FAIR_MARKET"
        breakdown = row.get("score_breakdown") or {}

        photos = row.get("photos") or []
        thumb = photos[0] if photos else raw.get("primaryThumbnail")

        pct_savings = round((price_delta / market_value) * 100, 1) if market_value > 0 else 0.0

        return {
            "id": str(row.get("id") or row.get("platform_id") or ""),
            "vin": row.get("vin") or "N/A",
            "platform": (row.get("platform") or "carscom").upper(),
            "platform_id": row.get("platform_id") or "",
            "url": row.get("url") or "#",
            "title": title,
            "make": make,
            "model": model,
            "year": year,
            "trim_detail": row.get("trim_detail") or raw.get("trim") or "",
            "price": price,
            "mileage": int(row.get("mileage") or 0),
            "exterior_color": row.get("exterior_color") or raw.get("exteriorColor") or "Unknown",
            "seller_name": row.get("seller_name") or "Bay Area Dealer",
            "location_city": row.get("location_city") or "Bay Area",
            "distance_miles": float(row["distance_miles"]) if row.get("distance_miles") is not None else None,
            "title_status": (row.get("title_status") or "clean").upper(),
            "accident_count": int(row.get("accident_count") or 0),
            "owner_count": row.get("owner_count"),
            "thumbnail": thumb,
            "market_value": market_value,
            "price_delta": price_delta,
            "pct_savings": pct_savings,
            "deal_score": round(deal_score, 1),
            "recommendation": recommendation,
            "score_breakdown": {
                "price_score": float(breakdown.get("price_score", 75.0)),
                "history_score": float(breakdown.get("history_score", 100.0)),
                "leverage_score": float(breakdown.get("leverage_score", 65.0)),
                "proximity_score": float(breakdown.get("proximity_score", 85.0)),
            },
            "price_change": int(row.get("price_change") or 0),
            "days_on_market": int(row.get("days_on_market") or raw.get("days_on_market") or 1),
            "snapshot_count": int(row.get("snapshot_count") or 1),
            "is_bookmarked": bool(raw.get("user_bookmarked", False)),
            "is_dismissed": bool(raw.get("user_dismissed", False)),
            "drivetrain": raw.get("drivetrain") or "",
            "cpo": bool(raw.get("cpoIndicator", False)),
            "first_seen": row.get("first_seen"),
            "last_seen": row.get("last_seen"),
        }

    @staticmethod
    def filter_and_sort_deals(
        all_deals: List[Dict[str, Any]],
        tab: str = "all",
        make_filter: str = "",
        search_query: str = "",
        max_price: Optional[int] = None,
        max_mileage: Optional[int] = None,
        max_distance: Optional[float] = None,
        sort_by: str = "score_desc",
    ) -> List[Dict[str, Any]]:
        """Filter and sort normalized deals in-memory."""
        filtered: List[Dict[str, Any]] = []
        q = (search_query or "").strip().lower()
        mf = (make_filter or "").strip().lower()

        for d in all_deals:
            # Tab filter
            if tab == "dismissed":
                if not d["is_dismissed"]:
                    continue
            else:
                # All non-dismissed views hide dismissed cards
                if d["is_dismissed"]:
                    continue
                if tab in ("saved", "bookmarked") and not d["is_bookmarked"]:
                    continue
                elif tab == "excellent" and d["deal_score"] < 85.0:
                    continue
                elif tab == "good" and d["deal_score"] < 75.0:
                    continue
                elif tab in ("drops", "price_drops") and d["price_change"] >= 0:
                    continue

            # Make/Model dropdown filter
            if mf:
                hay = f"{d['make']} {d['model']} {d['title']}".lower()
                if mf not in hay:
                    continue

            # Text search filter
            if q:
                hay = f"{d['title']} {d['vin']} {d['seller_name']} {d['location_city']} {d['exterior_color']} {d['trim_detail']}".lower()
                if q not in hay:
                    continue

            # Numeric sliders / inputs
            if max_price and d["price"] > max_price:
                continue
            if max_mileage and d["mileage"] > max_mileage:
                continue
            if max_distance and d["distance_miles"] is not None and d["distance_miles"] > max_distance:
                continue

            filtered.append(d)

        # Sorting
        if sort_by == "savings_asc":
            filtered.sort(key=lambda x: (x["price_delta"], -x["deal_score"]))
        elif sort_by == "price_asc":
            filtered.sort(key=lambda x: (x["price"], -x["deal_score"]))
        elif sort_by == "mileage_asc":
            filtered.sort(key=lambda x: (x["mileage"], -x["deal_score"]))
        elif sort_by == "distance_asc":
            filtered.sort(key=lambda x: (x["distance_miles"] if x["distance_miles"] is not None else 999.0, -x["deal_score"]))
        else:
            # Default: score_desc, breaking ties by biggest dollar savings
            filtered.sort(key=lambda x: (x["deal_score"], -x["price_delta"]), reverse=True)

        return filtered

    @staticmethod
    def compute_kpis(all_deals: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute top-level KPI telemetry metrics across active (non-dismissed) inventory."""
        active = [d for d in all_deals if not d["is_dismissed"]]
        excellent = [d for d in active if d["deal_score"] >= 85.0]
        saved = [d for d in active if d["is_bookmarked"]]
        dismissed = [d for d in all_deals if d["is_dismissed"]]
        drops = [d for d in active if d["price_change"] < 0]

        discounts = [abs(d["price_delta"]) for d in active if d["price_delta"] < 0]
        max_savings = max(discounts) if discounts else 0
        avg_discount = int(sum(discounts) / len(discounts)) if discounts else 0

        return {
            "total_active": len(active),
            "excellent_count": len(excellent),
            "saved_count": len(saved),
            "dismissed_count": len(dismissed),
            "price_drops_count": len(drops),
            "max_savings": max_savings,
            "avg_discount": avg_discount,
        }

    async def get_listing_history(self, listing_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single listing and all of its TimescaleDB price_snapshots."""
        all_deals = await self.fetch_all_Normalized_deals()
        target = next((d for d in all_deals if d["id"] == listing_id or d["platform_id"] == listing_id), None)
        if not target:
            return None

        snapshots: List[Dict[str, Any]] = []
        if HAS_SQLALCHEMY and not self._fallback_deals:
            sql = text("""
                SELECT time, price, days_on_market, price_change
                FROM price_snapshots
                WHERE listing_id = CAST(:lid AS uuid)
                ORDER BY time DESC
                LIMIT 30
            """)
            try:
                async with get_db_session() as session:
                    res = await session.execute(sql, {"lid": target["id"]})
                    for row in res.mappings():
                        snapshots.append({
                            "time": row["time"].strftime("%Y-%m-%d %H:%M UTC") if isinstance(row["time"], datetime) else str(row["time"]),
                            "price": int(row["price"]),
                            "days_on_market": int(row["days_on_market"] or 1),
                            "price_change": int(row["price_change"] or 0),
                        })
            except Exception as e:
                logger.warning(f"Failed to query price_snapshots for {listing_id}: {e}")

        if not snapshots:
            snapshots.append({
                "time": "Latest Snapshot",
                "price": target["price"],
                "days_on_market": target["days_on_market"],
                "price_change": target["price_change"],
            })

        return {
            "deal": target,
            "snapshots": snapshots,
        }

    async def toggle_user_flag(self, listing_id: str, flag_key: str) -> Optional[bool]:
        """Toggle user_bookmarked or user_dismissed on a listing in PostgreSQL or fallback store."""
        if self._fallback_deals or not HAS_SQLALCHEMY:
            for d in self._fallback_deals:
                if str(d.get("id")) == listing_id or str(d.get("platform_id")) == listing_id:
                    raw = d.setdefault("raw_data", {})
                    new_val = not bool(raw.get(flag_key, False))
                    raw[flag_key] = new_val
                    return new_val
            return None

        try:
            async with get_db_session() as session:
                import uuid
                try:
                    uid = uuid.UUID(listing_id)
                    listing = await session.get(Listing, uid)
                except ValueError:
                    listing = None

                if not listing:
                    return None

                raw = dict(listing.raw_data or {})
                new_val = not bool(raw.get(flag_key, False))
                raw[flag_key] = new_val
                listing.raw_data = raw
                flag_modified(listing, "raw_data")
                await session.flush()
                return new_val
        except Exception as e:
            logger.error(f"Failed to toggle {flag_key} for {listing_id}: {e}")
            return None

    async def get_model_intelligence(self, make: str, model: str, year: int) -> Dict[str, Any]:
        """Fetch NHTSA Recalls, Complaints, and EPA Range for a vehicle model (with caching)."""
        # Clean submodel numbers for NHTSA/EPA lookup (e.g. 'EQS 450+' -> 'EQS', 'i4 Gran Coupe' -> 'i4')
        clean_model = model.strip()
        if "eqs" in clean_model.lower():
            clean_model = "EQS"
        elif "eqe" in clean_model.lower():
            clean_model = "EQE"
        elif "i4" in clean_model.lower():
            clean_model = "i4"

        cache_key = f"{make.lower()}:{clean_model.lower()}:{year}"
        if cache_key in _MODEL_PROFILE_CACHE:
            return _MODEL_PROFILE_CACHE[cache_key]

        client = GovAPIClient(timeout=10.0)
        recalls = await client.get_recalls(make, clean_model, year)
        complaints = await client.get_complaints(make, clean_model, year)
        epa_options = await client.get_epa_fuel_economy(make, clean_model, year)

        crash_count = sum(1 for c in complaints if c.crash)
        fire_count = sum(1 for c in complaints if c.fire)
        injury_count = sum(c.number_of_injuries for c in complaints)

        profile = {
            "make": make,
            "model": clean_model,
            "year": year,
            "recalls_count": len(recalls),
            "recalls": [r.__dict__ for r in recalls[:10]],
            "complaints_count": len(complaints),
            "crash_count": crash_count,
            "fire_count": fire_count,
            "injury_count": injury_count,
            "complaints": [c.__dict__ for c in complaints[:10]],
            "epa_specs": [e.__dict__ for e in epa_options[:6]],
        }
        _MODEL_PROFILE_CACHE[cache_key] = profile
        return profile

    @staticmethod
    def export_deals_csv(deals: List[Dict[str, Any]]) -> str:
        """Serialize filtered deals into a CSV string."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Rank",
            "Deal Score",
            "Recommendation",
            "Year",
            "Make",
            "Model",
            "Trim",
            "Price ($)",
            "Fair Market Value ($)",
            "Price Delta ($)",
            "Savings (%)",
            "Mileage",
            "Distance (mi)",
            "City",
            "Dealer",
            "Title Status",
            "VIN",
            "Platform",
            "URL",
        ])
        for idx, d in enumerate(deals, 1):
            writer.writerow([
                idx,
                d["deal_score"],
                d["recommendation"],
                d["year"],
                d["make"],
                d["model"],
                d["trim_detail"],
                d["price"],
                d["market_value"],
                d["price_delta"],
                f"{d['pct_savings']}%",
                d["mileage"],
                d["distance_miles"] if d["distance_miles"] is not None else "",
                d["location_city"],
                d["seller_name"],
                d["title_status"],
                d["vin"],
                d["platform"],
                d["url"],
            ])
        return output.getvalue()

    @staticmethod
    def export_deals_markdown(deals: List[Dict[str, Any]]) -> str:
        """Format filtered deals into a Markdown report."""
        wrapped = [
            {
                "listing": d,
                "score_data": {
                    "market_value": d["market_value"],
                    "price_delta": d["price_delta"],
                    "deal_score": d["deal_score"],
                    "recommendation": d["recommendation"],
                },
            }
            for d in deals
        ]
        return NotificationService.format_deal_digest_markdown(wrapped)
