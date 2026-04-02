from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Alert_log, Users

# kg/s. Can be overridden via environment variable.
LEAK_THRESHOLD = float(os.getenv("LEAK_THRESHOLD", "0.001"))


def compute_drop_rate(previous_weight: float, current_weight: float, seconds_elapsed: float) -> float | None:
    if seconds_elapsed <= 0:
        return None
    return (previous_weight - current_weight) / seconds_elapsed


async def fire_alert_immediately(
    db: AsyncSession,
    user_id: str | None,
    drop_rate: float,
    threshold: float = LEAK_THRESHOLD,
) -> str | None:
    """Persist a leak alert record immediately in the current request context."""
    if user_id is None:
        return None

    result = await db.execute(
        select(Users.name).where(Users.user_id == user_id)
    )
    user_name = result.scalar_one_or_none()
    if user_name is None:
        return None

    alert_id = uuid.uuid4().hex[:20]
    alert = Alert_log(
        alert_id=alert_id,
        alert_type=f"gas_leak: rate={drop_rate:.6f}kg/s threshold={threshold:.6f}kg/s",
        delivery_status=False,
        time_stamp=datetime.now(UTC),
        user_id=user_name,
    )
    db.add(alert)
    return alert_id
