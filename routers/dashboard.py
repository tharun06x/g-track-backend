"""
routers/dashboard.py — Dashboard summary endpoint for G-Track.

Issues fixed (original):
  - Issue 10: 3 sequential DB queries replaced with asyncio.gather().

Architecture change (this revision):
  ┌─────────────────────────────────────────────────────────────────────┐
  │  Field              │ Before              │ After                   │
  ├─────────────────────┼─────────────────────┼─────────────────────────┤
  │ remaining_gas       │ DB SELECT every req │ RAM lookup (0 DB)       │
  │ gas_used_today      │ DB query every req  │ TTL cache (10-min)      │
  │ avg_daily_usage     │ DB query every req  │ TTL cache (10-min)      │
  │ predicted_empty     │ computed from above │ computed from above     │
  └─────────────────────┴─────────────────────┴─────────────────────────┘

TTL Cache design:
  A simple Python dict maps device_id → (timestamp, cached_result).
  On each request, if the cached_at timestamp is < 10 minutes old,
  the cached value is returned immediately (0 DB queries).
  After 10 minutes, the cache entry is re-fetched from DB.

  No external libraries needed — pure Python datetime arithmetic.

  In the rare case where the state_manager cache is also cold (fresh
  backend restart) AND the TTL cache is cold, ALL 3 queries fall back
  to the DB via asyncio.gather() exactly as before. This ensures the
  dashboard is never broken, even after a Render spin-down.

DB connection budget:
  Before: every dashboard load = 3 DB connections (via asyncio.gather)
  After:  first load after restart = 3 DB connections (warm-up)
          subsequent loads within 10 min = 0 DB connections
          every 10 min = 2 DB connections (today_usage + avg; weight from RAM)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import TokenPayload, get_current_user
from database import get_db
from models import Sensor_unit
from services.state_manager import device_state

router = APIRouter(prefix="/api/v1/dashboard")

# ---------------------------------------------------------------------------
# TTL cache — stores (cached_at: datetime, payload: dict) per device_id
# ---------------------------------------------------------------------------
# Keyed by device_id. Stores heavy, infrequently-changing aggregates only.
# Remaining gas (current weight) is always served fresh from RAM.

_TTL_SECONDS = 600  # 10 minutes

_dashboard_cache: dict[str, tuple[datetime, dict]] = {}


def _get_cached_aggregates(device_id: str) -> dict | None:
    """Return cached aggregates if the entry is still within TTL, else None."""
    entry = _dashboard_cache.get(device_id)
    if entry is None:
        return None
    cached_at, payload = entry
    age = (datetime.now(UTC) - cached_at).total_seconds()
    if age < _TTL_SECONDS:
        return payload
    # Expired — remove and signal a DB re-fetch
    del _dashboard_cache[device_id]
    return None


def _store_cached_aggregates(device_id: str, payload: dict) -> None:
    """Write aggregates into the TTL cache."""
    _dashboard_cache[device_id] = (datetime.now(UTC), payload)


# ---------------------------------------------------------------------------
# Dashboard summary endpoint
# ---------------------------------------------------------------------------

@router.get("/summary")
async def get_dashboard_summary(
    device_id: str,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Return current gas status and usage statistics for a device.

    Serving strategy (in priority order):
      1. remaining_gas   → in-memory state_manager (zero DB queries)
      2. today/avg usage → TTL cache (zero DB if < 10 min old)
      3. Full DB fallback if both caches are cold (first load after restart)
    """
    today = date.today()
    thirty_days_ago = today - timedelta(days=30)

    # ── remaining_gas from RAM ───────────────────────────────────────────────
    cached_state = device_state.get(device_id)
    remaining_gas_from_ram: float | None = (
        cached_state.current_weight if cached_state is not None else None
    )

    # ── aggregates from TTL cache ────────────────────────────────────────────
    cached_agg = _get_cached_aggregates(device_id)

    if cached_agg is not None and remaining_gas_from_ram is not None:
        # ── Fully cached path — ZERO DB queries ─────────────────────────────
        gas_used_today = cached_agg["gas_used_today"]
        avg_daily_usage = cached_agg["avg_daily_usage"]
        remaining_gas = remaining_gas_from_ram

    elif cached_agg is not None and remaining_gas_from_ram is None:
        # ── State manager cold, TTL cache warm — only fetch latest weight ───
        latest_query = (
            select(Sensor_unit.current_weight)
            .where(Sensor_unit.sensor_id == device_id)
            .where(Sensor_unit.timestamp <= func.now())
            .order_by(Sensor_unit.timestamp.desc())
            .limit(1)
        )
        remaining_gas = (await db.execute(latest_query)).scalar()
        gas_used_today = cached_agg["gas_used_today"]
        avg_daily_usage = cached_agg["avg_daily_usage"]

    else:
        # ── Full DB fallback — both caches cold (post-restart) ───────────────
        # Build the 3 queries exactly as before (Issue 10 fix retained)

        latest_query = (
            select(Sensor_unit.current_weight)
            .where(Sensor_unit.sensor_id == device_id)
            .where(Sensor_unit.timestamp <= func.now())
            .order_by(Sensor_unit.timestamp.desc())
            .limit(1)
        )

        today_usage_query = select(
            (func.max(Sensor_unit.current_weight) - func.min(Sensor_unit.current_weight)).label("usage")
        ).where(
            Sensor_unit.sensor_id == device_id,
            func.date(Sensor_unit.timestamp) == today,
            Sensor_unit.timestamp <= func.now(),
        )

        daily_sub = (
            select(
                func.date(Sensor_unit.timestamp).label("day"),
                (func.max(Sensor_unit.current_weight) - func.min(Sensor_unit.current_weight)).label("daily_usage"),
            )
            .where(
                Sensor_unit.sensor_id == device_id,
                func.date(Sensor_unit.timestamp) >= thirty_days_ago,
                Sensor_unit.timestamp <= func.now(),
            )
            .group_by(func.date(Sensor_unit.timestamp))
            .subquery()
        )
        avg_query = select(func.avg(daily_sub.c.daily_usage).label("avg_daily_usage"))

        # Fire all three concurrently (Issue 10 fix)
        latest_result, today_result, avg_result = await asyncio.gather(
            db.execute(latest_query),
            db.execute(today_usage_query),
            db.execute(avg_query),
        )

        remaining_gas = latest_result.scalar()
        gas_used_today = today_result.scalar() or 0.0
        avg_daily_usage = avg_result.scalar() or 0.0

        # Populate TTL cache so the next request skips DB
        _store_cached_aggregates(device_id, {
            "gas_used_today": round(float(gas_used_today), 2),
            "avg_daily_usage": round(float(avg_daily_usage), 2),
        })

    # ── Estimate depletion date ──────────────────────────────────────────────
    avg_daily_usage_f = float(avg_daily_usage) if avg_daily_usage else 0.0
    predicted_empty_date = None
    if avg_daily_usage_f > 0 and remaining_gas is not None:
        days_left = remaining_gas / avg_daily_usage_f
        predicted_empty_date = str(today + timedelta(days=int(days_left)))

    return {
        "remaining_gas": remaining_gas,
        "gas_used_today": round(float(gas_used_today), 2),
        "avg_daily_usage": round(avg_daily_usage_f, 2),
        "predicted_empty_date": predicted_empty_date,
    }
