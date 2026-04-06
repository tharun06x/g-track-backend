from datetime import datetime
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession 

from database import get_db
from models import Sensor_unit
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
    find_optimal_k,
    get_cluster_recommendations,
    load_clustering_model,
    predict_device_cluster,
    train_clustering_model,
)

router=APIRouter(prefix='/api/v1/reports')

@router.get("/gas-usage/stats")
async def get_gas_stats(
    device_id: str,
    granularity: Literal["daily", "monthly", "yearly"],
    db: Annotated[AsyncSession, Depends(get_db)],
    year: Optional[int] = None,
    month: Optional[int] = None):
    if granularity == "daily":
        time_label = func.date(Sensor_unit.timestamp).label("period")
    elif granularity == "monthly":
        time_label = func.extract('month', Sensor_unit.timestamp).label("period")
    else: # yearly
        time_label = func.extract('year', Sensor_unit.timestamp).label("period")

    usage_calc = (func.max(Sensor_unit.current_weight) - func.min(Sensor_unit.current_weight)).label("usage")
    query = select(time_label, usage_calc).where(Sensor_unit.sensor_id == device_id)
    if year:
        query = query.where(func.extract('year', Sensor_unit.timestamp) == year)
    if month and granularity == "daily":
        query = query.where(func.extract('month', Sensor_unit.timestamp) == month)

    query = query.group_by(time_label).order_by(time_label)
    result = await db.execute(query)
    return result.mappings().all()


@router.get("/cylinder/remaining-weight")
async def get_cylinder_weight(
    device_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get the remaining weight of a gas cylinder with consumption metrics.
    
    Returns:
    - remaining_weight: Current weight in kg
    - previous_weight: Previous reading weight in kg
    - current_drop_rate: Current consumption rate in kg/s
    - last_update: Timestamp of the latest sensor reading
    - connection_status: Sensor connection status
    """
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


@router.get('/gas-usage/features')
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
            "timestamp": row.date,
            "weight": row.current_weight,
        }
        for row in rows
    ]
    return build_features(records)


@router.get('/gas-usage/depletion-prediction')
async def get_depletion_prediction(
    device_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    query = (
        select(Sensor_unit.sensor_id, Sensor_unit.date, Sensor_unit.current_weight)
        .where(Sensor_unit.sensor_id == device_id)
        .order_by(Sensor_unit.date.asc())
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

    model = load_trained_model()
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


@router.post('/gas-usage/clustering/train')
async def train_clustering(
    db: Annotated[AsyncSession, Depends(get_db)],
    k: Optional[int] = Query(default=None),
):
    """Train K-means clustering model on all devices in the database.
    
    Returns cluster assignments and profiles.
    """
    query = select(Sensor_unit.sensor_id, Sensor_unit.date, Sensor_unit.current_weight)
    result = await db.execute(query)
    rows = result.all()

    records = [
        {
            "device_id": row.sensor_id,
            "timestamp": row.date,
            "weight": row.current_weight,
        }
        for row in rows
    ]

    result = train_clustering_model(records, k=k)
    return result


@router.get('/gas-usage/clustering/assignments')
async def get_cluster_assignments(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get cluster assignments for all devices."""
    kmeans, scaler = load_clustering_model()
    if kmeans is None:
        return {"error": "Clustering model not trained yet. Call POST /gas-usage/clustering/train first."}

    query = select(Sensor_unit.sensor_id, Sensor_unit.date, Sensor_unit.current_weight)
    result = await db.execute(query)
    rows = result.all()

    records = [
        {
            "device_id": row.sensor_id,
            "timestamp": row.date,
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


@router.get('/gas-usage/clustering/profiles')
async def get_cluster_profiles(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get aggregated cluster profiles and characteristics."""
    kmeans, scaler = load_clustering_model()
    if kmeans is None:
        return {"error": "Clustering model not trained yet. Call POST /gas-usage/clustering/train first."}

    query = select(Sensor_unit.sensor_id, Sensor_unit.date, Sensor_unit.current_weight)
    result = await db.execute(query)
    rows = result.all()

    records = [
        {
            "device_id": row.sensor_id,
            "timestamp": row.date,
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

    # Compute cluster profiles
    cluster_profiles = {}
    for cluster_id in range(kmeans.n_clusters):
        cluster_devices = features_df[features_df["cluster"] == cluster_id]
        profile = {
            "device_count": len(cluster_devices),
            "avg_daily_consumption_kg": float(
                cluster_devices["avg_daily_consumption"].mean()
            ),
            "median_peak_hour": int(cluster_devices["peak_hour"].median()),
            "avg_weekend_multiplier": float(
                cluster_devices["weekend_multiplier"].mean()
            ),
            "avg_sessions_per_day": float(
                cluster_devices["session_count_per_day"].mean()
            ),
            "avg_cylinder_lifetime_days": float(
                cluster_devices["cylinder_lifetime_days"].mean()
            ),
            "refill_frequency_estimate_days": float(
                cluster_devices["cylinder_lifetime_days"].mean() 
                / max(cluster_devices["session_count_per_day"].mean(), 0.1) * 30
            ),
        }
        cluster_profiles[str(cluster_id)] = profile

    return {
        "total_devices": len(features_df),
        "num_clusters": kmeans.n_clusters,
        "profiles": cluster_profiles,
    }


@router.get('/gas-usage/clustering/recommendations')
async def get_cluster_recommendation(
    cluster_id: int,
):
    """Get personalized recommendations for a cluster."""
    return get_cluster_recommendations(cluster_id)


@router.get('/gas-usage/clustering/benchmark/{device_id}')
async def benchmark_device(
    device_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Benchmark a device against its cluster peers."""
    kmeans, scaler = load_clustering_model()
    if kmeans is None:
        return {"error": "Clustering model not trained yet. Call POST /gas-usage/clustering/train first."}

    # Get device data
    query = (
        select(Sensor_unit.sensor_id, Sensor_unit.date, Sensor_unit.current_weight)
        .where(Sensor_unit.sensor_id == device_id)
        .order_by(Sensor_unit.date.asc())
    )
    result = await db.execute(query)
    rows = result.all()

    if not rows:
        return {"error": f"No data found for device {device_id}"}

    records = [
        {
            "device_id": row.sensor_id,
            "timestamp": row.date,
            "weight": row.current_weight,
        }
        for row in rows
    ]

    device_result = predict_device_cluster(records)
    if device_result is None:
        return {"error": "Could not compute features for device"}

    cluster_id = device_result["cluster"]

    # Get all cluster data for comparison
    query_all = select(Sensor_unit.sensor_id, Sensor_unit.date, Sensor_unit.current_weight)
    result_all = await db.execute(query_all)
    rows_all = result_all.all()

    records_all = [
        {
            "device_id": row.sensor_id,
            "timestamp": row.date,
            "weight": row.current_weight,
        }
        for row in rows_all
    ]

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

    # Compute benchmark metrics
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
