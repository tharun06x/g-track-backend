"""
services/state_manager.py — In-memory device state cache for G-Track.

Why this exists:
  The sensor ingestion endpoint previously performed a DB SELECT on every
  incoming IoT reading to fetch the previous weight for throttle comparison.
  On Render's free tier (pool_size=3, max_overflow=2), a 1-reading/second
  ESP32 device alone can exhaust all 5 DB connections, causing TimeoutErrors.

  This module keeps the latest device state in process RAM as a plain dict.
  A DB SELECT for throttling is now a pure dictionary lookup (~100 ns vs ~30 ms).
  The DB is only touched for durable INSERTs of meaningful weight changes.

Thread-safety note:
  FastAPI / Uvicorn runs a single-threaded async event loop (1 gunicorn worker
  on Render Free Tier — see main.py). All coroutines are cooperative, so
  there are no concurrent writes to _cache. No asyncio.Lock is needed.

Cache warm-up:
  On a cold start (Render spin-down/deploy), _cache is empty. sensor.py
  detects a cache miss on the first request for a device_id and performs
  ONE DB SELECT to warm the cache. All subsequent requests are cache-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# State dataclass
# ---------------------------------------------------------------------------

@dataclass
class DeviceState:
    """Latest known state for one IoT device."""
    device_id: str
    current_weight: float
    timestamp: datetime
    user_id: str | None = None
    connection_status: bool | None = None


# ---------------------------------------------------------------------------
# Singleton manager
# ---------------------------------------------------------------------------

class _DeviceStateManager:
    """
    Singleton in-memory store mapping device_id → DeviceState.

    Designed to be imported and used directly as a module-level singleton
    (``from services.state_manager import device_state``).
    """

    def __init__(self) -> None:
        self._cache: dict[str, DeviceState] = {}

    # ── Read ────────────────────────────────────────────────────────────────

    def get(self, device_id: str) -> DeviceState | None:
        """Return the cached state for *device_id*, or None on a cold cache."""
        return self._cache.get(device_id)

    def all(self) -> dict[str, DeviceState]:
        """Return a shallow copy of the entire cache (for diagnostics)."""
        return dict(self._cache)

    # ── Write ───────────────────────────────────────────────────────────────

    def update(
        self,
        device_id: str,
        current_weight: float,
        timestamp: datetime,
        user_id: str | None = None,
        connection_status: bool | None = None,
    ) -> DeviceState:
        """
        Upsert device state.

        If a state already exists, user_id and connection_status are only
        overwritten when the caller provides a non-None value, so a device
        that omits user_id on subsequent readings doesn't lose its resolved
        user_id.
        """
        existing = self._cache.get(device_id)

        resolved_user_id = user_id if user_id is not None else (
            existing.user_id if existing else None
        )
        resolved_conn = connection_status if connection_status is not None else (
            existing.connection_status if existing else None
        )

        state = DeviceState(
            device_id=device_id,
            current_weight=current_weight,
            timestamp=timestamp,
            user_id=resolved_user_id,
            connection_status=resolved_conn,
        )
        self._cache[device_id] = state
        return state

    def warm_from_db_row(
        self,
        device_id: str,
        current_weight: float,
        timestamp: datetime,
        user_id: str | None,
        connection_status: bool | None,
    ) -> DeviceState:
        """
        Populate the cache from a DB row fetched during cold-start warm-up.
        Identical to update() but named differently for clarity in call sites.
        """
        return self.update(
            device_id=device_id,
            current_weight=current_weight,
            timestamp=timestamp,
            user_id=user_id,
            connection_status=connection_status,
        )

    def invalidate(self, device_id: str) -> None:
        """Remove a device from the cache (e.g., device decommissioned)."""
        self._cache.pop(device_id, None)

    def size(self) -> int:
        """Return the number of devices currently tracked in RAM."""
        return len(self._cache)


# ---------------------------------------------------------------------------
# Module-level singleton — import this everywhere
# ---------------------------------------------------------------------------

device_state = _DeviceStateManager()
