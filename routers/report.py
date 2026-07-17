"""
routers/report.py — Analytics and ML reporting endpoints for G-Track.

Issues fixed:
  - Issue 6:  Depletion-prediction endpoint previously loaded ALL sensor rows
              (potentially 50 000+) into memory, built a full DataFrame, then
              discarded everything except the last row.  Now bounded to a 35-day
              rolling window — enough for the 30-day rolling avg features with
              a 5-day margin.
  - Issue 7:  All three clustering endpoints (assignments, profiles, benchmark)
              did a full-table scan of sensor_unit with no WHERE clause.  All
              now use a 90-day rolling window.  The benchmark endpoint previously
              executed the full-table scan TWICE; now it runs once per request.
  - Issue 15: load_trained_model() is called at module import via a singleton;
              the model is only re-read from disk when the file changes (mtime
              check).  See services/depletion_prediction.py for the cache impl.
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Sensor_unit, Synthetic_device, Synthetic_feature_row, Synthetic_sensor_reading
from services.depletion_prediction import (
    latest_depletion_features,
    load_trained_model,
    predict_days_remaining_ml,
    rule_based_days_remaining,
)
from services.feature_pipeline import build_features
from services.leak_detection import get_cylinder_remaining_weight
from services.usage_clustering import (
    compute_device_features,
    get_cluster_recommendations,
    load_clustering_model,
    predict_device_cluster,
    train_clustering_model,
)

router = APIRouter(prefix="/api/v1/reports")

# ---------------------------------------------------------------------------
# Rolling-window constants
# ---------------------------------------------------------------------------
# Depletion prediction needs 30 days of history for the rolling avg features.
# Add a 5-day margin so the window boundary doesn't clip the latest features.
_DEPLETION_WINDOW_DAYS = 35

# Clustering is a heavier, analytical workload. 90 days of data is more than
# sufficient to characterise usage patterns without loading years of history.
_CLUSTER_WINDOW_DAYS = 90


def _cluster_cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=_CLUSTER_WINDOW_DAYS)


def _depletion_cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=_DEPLETION_WINDOW_DAYS)


# ---------------------------------------------------------------------------
# Data overview
# ---------------------------------------------------------------------------

@router.get("/device/data-overview")
async def get_device_data_overview(
    device_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Return live + synthetic table insights for a device."""
    live_latest_query = (
        select(Sensor_unit)
        .where(Sensor_unit.sensor_id == device_id)
        .where(Sensor_unit.timestamp <= func.now())
        .order_by(Sensor_unit.timestamp.desc())
        .limit(1)
    )
    live_latest_result = await db.execute(live_latest_query)
    live_latest = live_latest_result.scalar_one_or_none()

    synthetic_device_query = select(Synthetic_device).where(Synthetic_device.device_id == device_id)
    synthetic_device_result = await db.execute(synthetic_device_query)
    synthetic_device = synthetic_device_result.scalar_one_or_none()

    synthetic_readings_count_query = select(func.count()).where(
        Synthetic_sensor_reading.device_id == device_id
    )
    synthetic_readings_count_result = await db.execute(synthetic_readings_count_query)
    synthetic_readings_count = int(synthetic_readings_count_result.scalar() or 0)

    synthetic_features_count_query = select(func.count()).where(
        Synthetic_feature_row.device_id == device_id
    )
    synthetic_features_count_result = await db.execute(synthetic_features_count_query)
    synthetic_features_count = int(synthetic_features_count_result.scalar() or 0)

    latest_synthetic_reading_query = (
        select(Synthetic_sensor_reading)
        .where(Synthetic_sensor_reading.device_id == device_id)
        .order_by(Synthetic_sensor_reading.timestamp.desc())
        .limit(1)
    )
    latest_synthetic_reading_result = await db.execute(latest_synthetic_reading_query)
    latest_synthetic_reading = latest_synthetic_reading_result.scalar_one_or_none()

    latest_feature_query = (
        select(Synthetic_feature_row)
        .where(Synthetic_feature_row.device_id == device_id)
        .order_by(Synthetic_feature_row.timestamp.desc())
        .limit(1)
    )
    latest_feature_result = await db.execute(latest_feature_query)
    latest_feature = latest_feature_result.scalar_one_or_none()

    refill_events_query = select(func.count()).where(
        Synthetic_sensor_reading.device_id == device_id,
        Synthetic_sensor_reading.is_refill.is_(True),
    )
    refill_events_result = await db.execute(refill_events_query)
    refill_events = int(refill_events_result.scalar() or 0)

    return {
        "device_id": device_id,
        "has_live_sensor_data": live_latest is not None,
        "has_synthetic_device": synthetic_device is not None,
        "live_latest": (
            {
                "current_weight": live_latest.current_weight,
                "connection_status": live_latest.connection_status,
                "timestamp": live_latest.timestamp,
            }
            if live_latest is not None
            else None
        ),
        "synthetic_device": (
            {
                "dataset_version": synthetic_device.dataset_version,
                "lifecycle_count": synthetic_device.lifecycle_count,
                "created_at": synthetic_device.created_at,
            }
            if synthetic_device is not None
            else None
        ),
        "synthetic_rows": {
            "sensor_readings": synthetic_readings_count,
            "feature_rows": synthetic_features_count,
            "refill_events": refill_events,
        },
        "latest_synthetic_reading": (
            {
                "weight": latest_synthetic_reading.weight,
                "is_refill": latest_synthetic_reading.is_refill,
                "timestamp": latest_synthetic_reading.timestamp,
            }
            if latest_synthetic_reading is not None
            else None
        ),
        "latest_feature": (
            {
                "weight": latest_feature.weight,
                "weight_delta": latest_feature.weight_delta,
                "consumption_per_day": latest_feature.consumption_per_day,
                "rolling_7day_avg_consumption": latest_feature.rolling_7day_avg_consumption,
                "rolling_30day_avg_consumption": latest_feature.rolling_30day_avg_consumption,
                "days_since_refill": latest_feature.days_since_refill,
                "session_count_today": latest_feature.session_count_today,
                "idle_drop_rate": latest_feature.idle_drop_rate,
                "timestamp": latest_feature.timestamp,
            }
            if latest_feature is not None
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Gas usage stats
# ---------------------------------------------------------------------------

@router.get("/gas-usage/stats")
async def get_gas_stats(
    device_id: str,
    granularity: Literal["daily", "monthly", "yearly"],
    db: Annotated[AsyncSession, Depends(get_db)],
    year: Optional[int] = None,
    month: Optional[int] = None,
):
    if granularity == "daily":
        time_label = func.date(Sensor_unit.timestamp).label("period")
    elif granularity == "monthly":
        time_label = func.extract("month", Sensor_unit.timestamp).label("period")
    else:  # yearly
        time_label = func.extract("year", Sensor_unit.timestamp).label("period")

    usage_calc = (func.max(Sensor_unit.current_weight) - func.min(Sensor_unit.current_weight)).label("usage")
    query = select(time_label, usage_calc).where(
        Sensor_unit.sensor_id == device_id,
        Sensor_unit.timestamp <= func.now(),
    )
    if year:
        query = query.where(func.extract("year", Sensor_unit.timestamp) == year)
    if month and granularity == "daily":
        query = query.where(func.extract("month", Sensor_unit.timestamp) == month)

    query = query.group_by(time_label).order_by(time_label)
    result = await db.execute(query)
    return result.mappings().all()


# ---------------------------------------------------------------------------
# Cylinder remaining weight
# ---------------------------------------------------------------------------

@router.get("/cylinder/remaining-weight")
async def get_cylinder_weight(
    device_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get the remaining weight of a gas cylinder with consumption metrics."""
    result = await get_cylinder_remaining_weight(db, device_id)

    if result is None:
        return {
            "device_id": device_id,
            "message": "No sensor readings found for this device",
            "error": True,
        }

    return {
        **result,
        "error": False,
    }


# ---------------------------------------------------------------------------
# Feature pipeline
# ---------------------------------------------------------------------------

@router.get("/gas-usage/features")
async def get_gas_usage_features(
    device_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
):
    query = (
        select(Sensor_unit.sensor_id, Sensor_unit.timestamp, Sensor_unit.current_weight)
        .where(Sensor_unit.sensor_id == device_id)
        .order_by(Sensor_unit.timestamp.asc())
    )
    if start is not None:
        query = query.where(Sensor_unit.timestamp >= start)
    if end is not None:
        query = query.where(Sensor_unit.timestamp <= end)

    result = await db.execute(query)
    rows = result.all()

    records = [
        {
            "device_id": row.sensor_id,
            "timestamp": row.timestamp,
            "weight": row.current_weight,
        }
        for row in rows
    ]
    return build_features(records)


# ---------------------------------------------------------------------------
# Depletion prediction  (Issue 6 fix)
# ---------------------------------------------------------------------------

@router.get("/gas-usage/depletion-prediction")
async def get_depletion_prediction(
    device_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Predict days of gas remaining using rule-based and ML models.

    Issue 6 fix: query is bounded to the last 35 days instead of loading the
    entire sensor_unit history into memory.  The feature pipeline needs at most
    30 days of history for the rolling-average features; the extra 5 days are
    a safety margin.  This reduces peak memory from ~10 MB/request (50K rows)
    to < 200 KB/request (~1 000 rows) on a 6-month-old device.

    Issue 15 fix: load_trained_model() returns a cached singleton; the model
    file is only re-read from disk when its mtime changes (i.e., after retraining).
    """
    cutoff = _depletion_cutoff()
    query = (
        select(Sensor_unit.sensor_id, Sensor_unit.timestamp, Sensor_unit.current_weight)
        .where(Sensor_unit.sensor_id == device_id)
        .where(Sensor_unit.timestamp >= cutoff)          # ← bounded window
        .order_by(Sensor_unit.timestamp.asc())
    )
    result = await db.execute(query)
    rows = result.all()

    records = [
        {
            "device_id": row.sensor_id,
            "timestamp": row.timestamp,
            "weight": row.current_weight,
        }
        for row in rows
    ]

    feature_rows = build_features(records)
    latest = latest_depletion_features(feature_rows)
    if latest is None:
        return {
            "device_id": device_id,
            "message": "No readings available for depletion prediction",
        }

    baseline_days = rule_based_days_remaining(
        current_weight=latest["current_weight"],
        rolling_7day_avg_consumption=latest["rolling_7day_avg"],
    )

    model = load_trained_model()   # Returns cached singleton (Issue 15)
    ml_days = None
    if model is not None:
        ml_days = predict_days_remaining_ml(model, latest)

    return {
        "device_id": device_id,
        "features": latest,
        "rule_based_days_remaining": baseline_days,
        "ml_days_remaining": ml_days,
        "model_loaded": model is not None,
    }


# ---------------------------------------------------------------------------
# Clustering — train  (Issue 7 fix: 90-day window)
# ---------------------------------------------------------------------------

@router.post("/gas-usage/clustering/train")
async def train_clustering(
    db: Annotated[AsyncSession, Depends(get_db)],
    k: Optional[int] = Query(default=None),
):
    """Train K-means clustering model on recent device data.

    Issue 7 fix: query bounded to the last 90 days; previously scanned the
    entire sensor_unit table (full table scan) for every train request.
    """
    cutoff = _cluster_cutoff()
    query = (
        select(Sensor_unit.sensor_id, Sensor_unit.timestamp, Sensor_unit.current_weight)
        .where(Sensor_unit.timestamp >= cutoff)
    )
    result = await db.execute(query)
    rows = result.all()

    records = [
        {
            "device_id": row.sensor_id,
            "timestamp": row.timestamp,
            "weight": row.current_weight,
        }
        for row in rows
    ]

    return train_clustering_model(records, k=k)


# ---------------------------------------------------------------------------
# Clustering — assignments  (Issue 7 fix: 90-day window)
# ---------------------------------------------------------------------------

@router.get("/gas-usage/clustering/assignments")
async def get_cluster_assignments(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get cluster assignments for all devices."""
    kmeans, scaler = load_clustering_model()
    if kmeans is None:
        return {"error": "Clustering model not trained yet. Call POST /gas-usage/clustering/train first."}

    cutoff = _cluster_cutoff()
    query = (
        select(Sensor_unit.sensor_id, Sensor_unit.timestamp, Sensor_unit.current_weight)
        .where(Sensor_unit.timestamp >= cutoff)
    )
    result = await db.execute(query)
    rows = result.all()

    records = [
        {
            "device_id": row.sensor_id,
            "timestamp": row.timestamp,
            "weight": row.current_weight,
        }
        for row in rows
    ]

    features_df = compute_device_features(records)
    if features_df.empty:
        return {"error": "No devices found"}

    feature_cols = [
        "avg_daily_consumption",
        "peak_hour",
        "weekend_multiplier",
        "session_count_per_day",
        "cylinder_lifetime_days",
    ]
    X = features_df[feature_cols].values
    X_scaled = scaler.transform(X)
    clusters = kmeans.predict(X_scaled)
    features_df["cluster"] = clusters

    return {
        "total_devices": len(features_df),
        "num_clusters": kmeans.n_clusters,
        "assignments": features_df[["device_id", "cluster"]].to_dict("records"),
    }


# ---------------------------------------------------------------------------
# Clustering — profiles  (Issue 7 fix: 90-day window)
# ---------------------------------------------------------------------------

@router.get("/gas-usage/clustering/profiles")
async def get_cluster_profiles(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get aggregated cluster profiles and characteristics."""
    kmeans, scaler = load_clustering_model()
    if kmeans is None:
        return {"error": "Clustering model not trained yet. Call POST /gas-usage/clustering/train first."}

    cutoff = _cluster_cutoff()
    query = (
        select(Sensor_unit.sensor_id, Sensor_unit.timestamp, Sensor_unit.current_weight)
        .where(Sensor_unit.timestamp >= cutoff)
    )
    result = await db.execute(query)
    rows = result.all()

    records = [
        {
            "device_id": row.sensor_id,
            "timestamp": row.timestamp,
            "weight": row.current_weight,
        }
        for row in rows
    ]

    features_df = compute_device_features(records)
    if features_df.empty:
        return {"error": "No devices found"}

    feature_cols = [
        "avg_daily_consumption",
        "peak_hour",
        "weekend_multiplier",
        "session_count_per_day",
        "cylinder_lifetime_days",
    ]
    X = features_df[feature_cols].values
    X_scaled = scaler.transform(X)
    clusters = kmeans.predict(X_scaled)
    features_df["cluster"] = clusters

    cluster_profiles: dict = {}
    for cluster_id in range(kmeans.n_clusters):
        cluster_devices = features_df[features_df["cluster"] == cluster_id]
        cluster_profiles[str(cluster_id)] = {
            "device_count": len(cluster_devices),
            "avg_daily_consumption_kg": float(cluster_devices["avg_daily_consumption"].mean()),
            "median_peak_hour": int(cluster_devices["peak_hour"].median()),
            "avg_weekend_multiplier": float(cluster_devices["weekend_multiplier"].mean()),
            "avg_sessions_per_day": float(cluster_devices["session_count_per_day"].mean()),
            "avg_cylinder_lifetime_days": float(cluster_devices["cylinder_lifetime_days"].mean()),
            "refill_frequency_estimate_days": float(
                cluster_devices["cylinder_lifetime_days"].mean()
                / max(cluster_devices["session_count_per_day"].mean(), 0.1) * 30
            ),
        }

    return {
        "total_devices": len(features_df),
        "num_clusters": kmeans.n_clusters,
        "profiles": cluster_profiles,
    }


# ---------------------------------------------------------------------------
# Clustering — recommendations
# ---------------------------------------------------------------------------

@router.get("/gas-usage/clustering/recommendations")
async def get_cluster_recommendation(cluster_id: int):
    """Get personalised recommendations for a cluster."""
    return get_cluster_recommendations(cluster_id)


# ---------------------------------------------------------------------------
# Clustering — benchmark  (Issue 7 fix: one query instead of two)
# ---------------------------------------------------------------------------

@router.get("/gas-usage/clustering/benchmark/{device_id}")
async def benchmark_device(
    device_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Benchmark a device against its cluster peers.

    Issue 7 fix: the original code ran two separate full-table scans — one for
    the target device and one for all devices.  Now a single bounded query
    fetches all device data; device-specific rows are filtered in Python from
    the already-loaded DataFrame, eliminating the second DB round-trip.
    """
    kmeans, scaler = load_clustering_model()
    if kmeans is None:
        return {"error": "Clustering model not trained yet. Call POST /gas-usage/clustering/train first."}

    # Single query for ALL devices within the rolling window
    cutoff = _cluster_cutoff()
    query = (
        select(Sensor_unit.sensor_id, Sensor_unit.timestamp, Sensor_unit.current_weight)
        .where(Sensor_unit.timestamp >= cutoff)
        .order_by(Sensor_unit.timestamp.asc())
    )
    result = await db.execute(query)
    rows = result.all()

    if not rows:
        return {"error": "No sensor data found in the clustering window"}

    records_all = [
        {
            "device_id": row.sensor_id,
            "timestamp": row.timestamp,
            "weight": row.current_weight,
        }
        for row in rows
    ]

    # Check the target device has any data within the window
    device_rows = [r for r in records_all if r["device_id"] == device_id]
    if not device_rows:
        return {"error": f"No data found for device {device_id} in the last {_CLUSTER_WINDOW_DAYS} days"}

    # Compute features for the target device only (for its cluster prediction)
    device_result = predict_device_cluster(device_rows)
    if device_result is None:
        return {"error": "Could not compute features for device"}

    cluster_id = device_result["cluster"]

    # Compute features for ALL devices (for peer comparison)
    features_all = compute_device_features(records_all)
    feature_cols = [
        "avg_daily_consumption",
        "peak_hour",
        "weekend_multiplier",
        "session_count_per_day",
        "cylinder_lifetime_days",
    ]
    X_all = features_all[feature_cols].values
    X_scaled_all = scaler.transform(X_all)
    clusters_all = kmeans.predict(X_scaled_all)
    features_all["cluster"] = clusters_all

    cluster_devices = features_all[features_all["cluster"] == cluster_id]

    device_features = device_result["features"]
    cluster_avg = {
        "avg_daily_consumption": float(cluster_devices["avg_daily_consumption"].mean()),
        "peak_hour": int(cluster_devices["peak_hour"].median()),
        "weekend_multiplier": float(cluster_devices["weekend_multiplier"].mean()),
        "session_count_per_day": float(cluster_devices["session_count_per_day"].mean()),
        "cylinder_lifetime_days": float(cluster_devices["cylinder_lifetime_days"].mean()),
    }
    percentile_rank = {
        "avg_daily_consumption": float(
            (cluster_devices["avg_daily_consumption"] <= device_features["avg_daily_consumption"]).sum()
            / max(len(cluster_devices), 1) * 100
        ),
        "session_count_per_day": float(
            (cluster_devices["session_count_per_day"] <= device_features["session_count_per_day"]).sum()
            / max(len(cluster_devices), 1) * 100
        ),
    }

    return {
        "device_id": device_id,
        "cluster": cluster_id,
        "cluster_peers": len(cluster_devices),
        "device_features": device_features,
        "cluster_average": cluster_avg,
        "percentile_rank": percentile_rank,
        "recommendation": get_cluster_recommendations(cluster_id),
    }
