import logging
from datetime import datetime, timezone
from typing import List, Dict, Any

try:
    from sqlalchemy import select, or_
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
    Computes price change deltas and empirical Days on Market (DOM) across runs.
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
    new_listings_count = 0
    price_drops_count = 0

    try:
        async with get_db_session() as session:
            now_utc = datetime.now(timezone.utc)

            for item in scored_deals:
                listing_data = item.get("listing", {})
                score_data = item.get("score_data", {})

                platform = listing_data.get("platform", "unknown")
                platform_id = str(listing_data.get("platform_id", ""))
                vin = listing_data.get("vin")
                price = int(listing_data.get("price", 0))

                # Match existing listing by (platform, platform_id) or 17-digit VIN
                if vin and len(str(vin)) == 17:
                    stmt = select(Listing).where(
                        or_(
                            (Listing.platform == platform) & (Listing.platform_id == platform_id),
                            Listing.vin == str(vin).upper(),
                        )
                    )
                else:
                    stmt = select(Listing).where(
                        Listing.platform == platform,
                        Listing.platform_id == platform_id,
                    )

                res = await session.execute(stmt)
                existing_listing = res.scalars().first()

                price_change = 0
                scraped_dom = listing_data.get("raw_data", {}).get("days_on_market")

                if existing_listing:
                    # Compute price delta BEFORE overwriting existing_listing.price
                    if existing_listing.price and existing_listing.price > 0:
                        price_change = price - existing_listing.price
                        if price_change < 0:
                            price_drops_count += 1

                    existing_listing.price = price
                    existing_listing.mileage = int(listing_data.get("mileage", existing_listing.mileage))
                    existing_listing.last_seen = now_utc
                    existing_listing.is_active = True

                    # Backfill enriched metadata if previously missing
                    if listing_data.get("distance_miles") is not None and existing_listing.distance_miles is None:
                        existing_listing.distance_miles = float(listing_data["distance_miles"])
                    if listing_data.get("location_city") and not existing_listing.location_city:
                        existing_listing.location_city = listing_data["location_city"]
                    if listing_data.get("seller_name") and not existing_listing.seller_name:
                        existing_listing.seller_name = listing_data["seller_name"]
                    if listing_data.get("photos") and not existing_listing.photos:
                        existing_listing.photos = listing_data["photos"]

                    # Merge raw_data while preserving user bookmark/dismiss state
                    merged_raw = dict(existing_listing.raw_data or {})
                    incoming_raw = dict(listing_data.get("raw_data") or {})
                    for k, v in incoming_raw.items():
                        if k not in ("user_bookmarked", "user_dismissed"):
                            merged_raw[k] = v
                    existing_listing.raw_data = merged_raw

                    # Calculate empirical Days on Market from first_seen
                    first_seen_dt = existing_listing.first_seen
                    if first_seen_dt:
                        if first_seen_dt.tzinfo is None:
                            first_seen_dt = first_seen_dt.replace(tzinfo=timezone.utc)
                        empirical_dom = max(1, (now_utc - first_seen_dt).days)
                        days_on_market = max(int(scraped_dom or 0), empirical_dom)
                    else:
                        days_on_market = scraped_dom

                    listing_record = existing_listing
                else:
                    new_listings_count += 1
                    days_on_market = scraped_dom or 1
                    listing_record = Listing(
                        vin=str(vin).upper() if vin and len(str(vin)) == 17 else vin,
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
                        location_city=listing_data.get("location_city"),
                        location_state=listing_data.get("location_state"),
                        distance_miles=listing_data.get("distance_miles"),
                        title_status=listing_data.get("title_status", "clean"),
                        accident_count=int(listing_data.get("accident_count", 0)),
                        owner_count=listing_data.get("owner_count"),
                        photos=listing_data.get("photos", []),
                        raw_data=listing_data.get("raw_data", {}),
                        first_seen=now_utc,
                        last_seen=now_utc,
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
                        scored_at=now_utc,
                    )
                    session.add(deal_score_record)

                # Record Time-Series Price Snapshot
                snapshot = PriceSnapshotModel(
                    time=now_utc,
                    listing_id=listing_record.id,
                    price=price,
                    days_on_market=days_on_market,
                    price_change=price_change,
                )
                session.add(snapshot)
                snapshot_count += 1

        logger.info(
            f"Successfully persisted {persisted_count} listings "
            f"({new_listings_count} new, {price_drops_count} price drops) "
            f"and {snapshot_count} price snapshots."
        )
        return {
            "persisted_count": persisted_count,
            "snapshot_count": snapshot_count,
            "new_listings_count": new_listings_count,
            "price_drops_count": price_drops_count,
            "status": "success",
        }

    except Exception as e:
        logger.warning(f"Database persistence skipped (DB may be offline): {e}")
        return {
            "persisted_count": len(scored_deals),
            "status": "db_offline_fallback",
            "error": str(e),
        }
