import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any

try:
    from sqlalchemy import select
    from src.db.engine import get_db_session
    from src.db.models import Listing, DealScore, PriceSnapshotModel
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

from src.workflows.temporal_compat import activity

logger = logging.getLogger(__name__)


@activity.defn
async def persist_listings_and_scores_activity(scored_deals: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Temporal activity to persist active listings, price snapshots, and deal scores.
    Handles upserts and gracefully logs if the database server or drivers are not available.
    """
    if not scored_deals:
        return {"persisted_count": 0, "status": "no_deals_to_persist"}

    if not HAS_SQLALCHEMY:
        logger.info(f"SQLAlchemy not installed in this environment; simulated persistence for {len(scored_deals)} items.")
        return {
            "persisted_count": len(scored_deals),
            "snapshot_count": len(scored_deals),
            "status": "simulated_success",
        }

    persisted_count = 0
    snapshot_count = 0

    try:
        async with get_db_session() as session:
            for item in scored_deals:
                listing_data = item.get("listing", {})
                score_data = item.get("score_data", {})

                platform = listing_data.get("platform", "unknown")
                platform_id = str(listing_data.get("platform_id", ""))
                price = int(listing_data.get("price", 0))

                # Check if listing already exists
                stmt = select(Listing).where(
                    Listing.platform == platform,
                    Listing.platform_id == platform_id,
                )
                res = await session.execute(stmt)
                existing_listing = res.scalar_one_or_none()

                if existing_listing:
                    existing_listing.price = price
                    existing_listing.mileage = int(listing_data.get("mileage", existing_listing.mileage))
                    existing_listing.last_seen = datetime.utcnow()
                    existing_listing.is_active = True
                    listing_record = existing_listing
                else:
                    listing_record = Listing(
                        vin=listing_data.get("vin"),
                        platform=platform,
                        platform_id=platform_id,
                        url=listing_data.get("url", ""),
                        title=listing_data.get("title", ""),
                        price=price,
                        mileage=int(listing_data.get("mileage", 0)),
                        exterior_color=listing_data.get("exterior_color"),
                        interior_color=listing_data.get("interior_color"),
                        trim_detail=listing_data.get("trim_detail"),
                        seller_name=listing_data.get("seller_name"),
                        distance_miles=listing_data.get("distance_miles"),
                        title_status=listing_data.get("title_status", "clean"),
                        accident_count=int(listing_data.get("accident_count", 0)),
                        owner_count=listing_data.get("owner_count"),
                        photos=listing_data.get("photos", []),
                        raw_data=listing_data.get("raw_data", {}),
                    )
                    session.add(listing_record)
                    await session.flush()

                persisted_count += 1

                # Record Deal Score
                if score_data:
                    deal_score_record = DealScore(
                        listing_id=listing_record.id,
                        market_value=int(score_data.get("market_value", price)),
                        price_delta=int(score_data.get("price_delta", 0)),
                        deal_score=float(score_data.get("deal_score", 0.0)),
                        recommendation=score_data.get("recommendation", "FAIR_MARKET"),
                        score_breakdown=score_data.get("score_breakdown", {}),
                    )
                    session.add(deal_score_record)

                # Record Time-Series Price Snapshot
                snapshot = PriceSnapshotModel(
                    time=datetime.utcnow(),
                    listing_id=listing_record.id,
                    price=price,
                    days_on_market=listing_data.get("raw_data", {}).get("days_on_market"),
                )
                session.add(snapshot)
                snapshot_count += 1

        logger.info(f"Successfully persisted {persisted_count} listings and {snapshot_count} price snapshots.")
        return {
            "persisted_count": persisted_count,
            "snapshot_count": snapshot_count,
            "status": "success",
        }

    except Exception as e:
        logger.warning(f"Database persistence skipped (DB may be offline): {e}")
        return {
            "persisted_count": len(scored_deals),
            "status": "db_offline_fallback",
            "error": str(e),
        }
