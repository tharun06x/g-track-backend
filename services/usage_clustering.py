"""Usage Pattern Clustering - ML Feature 4.

Groups devices/households by gas consumption behavior using K-means clustering.
Features: avg_daily_consumption, peak_hour, weekend_multiplier, session_count_per_day, cylinder_lifetime_days.
"""

from __future__ import annotations

import os
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

CLUSTERING_MODEL_PATH = "models/usage_clustering_model.joblib"
CLUSTERING_SCALER_PATH = "models/usage_clustering_scaler.joblib"

# Clustering configuration
DEFAULT_K = 3
MAX_K = 6  # For elbow method
INERTIA_THRESHOLD = 0.01  # To decide elbow point


def compute_device_features(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Aggregate per-device metrics from raw sensor records.

    Input: List of sensor records with device_id, timestamp, weight.
    Output: DataFrame with one row per device, containing clustering features.

    Features:
    - avg_daily_consumption (kg/day)
    - peak_hour (hour of day when usage is highest, 0-23)
    - weekend_multiplier (weekend_avg / weekday_avg)
    - session_count_per_day (number of cooking sessions per day on average)
    - cylinder_lifetime_days (days from first to last reading)
    """
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records).copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(["device_id", "timestamp"]).reset_index(drop=True)

    # Compute consumption and consumption patterns per device
    grp = df.groupby("device_id", sort=False)

    results = []

    for device_id, device_df in grp:
        device_df = device_df.sort_values("timestamp").copy()

        # --- Lifetime ---
        first_ts = device_df["timestamp"].min()
        last_ts = device_df["timestamp"].max()
        lifetime_days = (last_ts - first_ts).total_seconds() / 86400.0

        # --- Daily consumption ---
        device_df["time_gap_hours"] = device_df["timestamp"].diff().dt.total_seconds() / 3600.0
        device_df["weight_delta"] = device_df["weight"].diff()

        # Positive consumption (weight decreasing) in kg
        device_df["consumption_kg"] = (-device_df["weight_delta"]).clip(lower=0)

        daily_agg = (
            device_df.groupby(device_df["timestamp"].dt.date)
            .agg({"consumption_kg": "sum"})
            .reset_index()
        )
        daily_agg.columns = ["date", "daily_consumption"]
        avg_daily_consumption = daily_agg["daily_consumption"].mean()

        # --- Peak hour (when usage is highest on average) ---
        device_df["hour"] = device_df["timestamp"].dt.hour
        hourly_consumption = device_df.groupby("hour")["consumption_kg"].sum()
        if len(hourly_consumption) > 0:
            peak_hour = hourly_consumption.idxmax()
        else:
            peak_hour = 12  # Default to noon

        # --- Weekend multiplier ---
        device_df["day_of_week"] = device_df["timestamp"].dt.dayofweek
        device_df["is_weekend"] = device_df["day_of_week"] >= 5

        weekday_consumption = device_df[~device_df["is_weekend"]]["consumption_kg"].sum()
        weekend_consumption = device_df[device_df["is_weekend"]]["consumption_kg"].sum()

        weekday_days = device_df[~device_df["is_weekend"]]["timestamp"].dt.date.nunique()
        weekend_days = device_df[device_df["is_weekend"]]["timestamp"].dt.date.nunique()

        weekday_avg = weekday_consumption / max(weekday_days, 1)
        weekend_avg = weekend_consumption / max(weekend_days, 1)

        weekend_multiplier = weekend_avg / max(weekday_avg, 0.001)

        # --- Session count (cooking session detection) ---
        # Session = drop larger than session_threshold (0.5 kg) with gap > 1 hour from previous drop
        device_df = device_df[device_df["timestamp"].notna()].copy()
        device_df["date"] = device_df["timestamp"].dt.date

        sessions_per_day = []
        for date, date_df in device_df.groupby("date"):
            date_df = date_df.sort_values("timestamp").copy()
            drops = date_df[date_df["consumption_kg"] > 0.5].copy()

            if len(drops) == 0:
                sessions_per_day.append(0)
                continue

            drops["time_gap_from_prev"] = (
                drops["timestamp"].diff().dt.total_seconds() / 3600.0
            )

            # A session starts if no prior drop or gap > 1 hour
            session_starts = (
                drops["time_gap_from_prev"].isna()
                | (drops["time_gap_from_prev"] > 1.0)
            )
            num_sessions = session_starts.sum()
            sessions_per_day.append(num_sessions)

        avg_sessions_per_day = (
            np.mean(sessions_per_day)
            if sessions_per_day
            else 0.0
        )

        results.append(
            {
                "device_id": device_id,
                "avg_daily_consumption": avg_daily_consumption,
                "peak_hour": float(peak_hour),
                "weekend_multiplier": weekend_multiplier,
                "session_count_per_day": avg_sessions_per_day,
                "cylinder_lifetime_days": lifetime_days,
            }
        )

    return pd.DataFrame(results)


def find_optimal_k(features_scaled: np.ndarray, max_k: int = MAX_K) -> tuple[int, list[float]]:
    """Use elbow method to find optimal number of clusters.

    Returns:
    - optimal_k: Recommended number of clusters
    - inertias: List of inertia values for each k
    """
    inertias = []

    for k in range(1, max_k + 1):
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        kmeans.fit(features_scaled)
        inertias.append(kmeans.inertia_)

    # Elbow detection: find biggest drop-off in improvement
    # (second derivative approximation)
    if len(inertias) >= 3:
        diffs = np.diff(inertias)
        second_diffs = np.diff(diffs)

        # Find elbow as point with max second derivative
        elbow_idx = np.argmax(second_diffs) + 1
        optimal_k = elbow_idx + 1
    else:
        optimal_k = min(2, max_k)

    return optimal_k, inertias


def train_clustering_model(
    records: list[dict[str, Any]],
    k: int | None = None,
    force_k: bool = False,
) -> dict[str, Any]:
    """Train K-means clustering model on device features.

    Args:
    - records: Raw sensor data (device_id, timestamp, weight)
    - k: Specific number of clusters. If None, uses elbow method.
    - force_k: If True, use provided k even if elbow suggests different value.

    Returns:
    - Dictionary with model info, cluster assignments, etc.
    """
    features_df = compute_device_features(records)

    if features_df.empty:
        return {"error": "No device records to cluster"}

    feature_cols = [
        "avg_daily_consumption",
        "peak_hour",
        "weekend_multiplier",
        "session_count_per_day",
        "cylinder_lifetime_days",
    ]
    X = features_df[feature_cols].values

    # Standardize features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Determine optimal k
    if k is None or not force_k:
        optimal_k, inertias = find_optimal_k(X_scaled, MAX_K)
        if k is not None and k != optimal_k and not force_k:
            print(f"Elbow method suggests k={optimal_k}, but k={k} was provided. Using elbow.")
    else:
        optimal_k = k
        inertias = []

    # Train final model
    kmeans = KMeans(n_clusters=optimal_k, random_state=42, n_init=10)
    cluster_labels = kmeans.fit_predict(X_scaled)

    features_df["cluster"] = cluster_labels

    # Save models
    os.makedirs("models", exist_ok=True)
    joblib.dump(kmeans, CLUSTERING_MODEL_PATH)
    joblib.dump(scaler, CLUSTERING_SCALER_PATH)

    # Compute cluster profiles
    cluster_profiles = {}
    for cluster_id in range(optimal_k):
        cluster_devices = features_df[features_df["cluster"] == cluster_id]
        profile = {
            "device_count": len(cluster_devices),
            "avg_daily_consumption": float(
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
        }
        cluster_profiles[str(cluster_id)] = profile

    return {
        "model_path": CLUSTERING_MODEL_PATH,
        "scaler_path": CLUSTERING_SCALER_PATH,
        "optimal_k": optimal_k,
        "inertias": inertias,
        "devices_clustered": len(features_df),
        "cluster_assignments": features_df[["device_id", "cluster"]].to_dict("records"),
        "cluster_profiles": cluster_profiles,
    }


def load_clustering_model() -> tuple[KMeans, StandardScaler] | tuple[None, None]:
    """Load trained clustering model and scaler."""
    if not os.path.exists(CLUSTERING_MODEL_PATH):
        return None, None
    if not os.path.exists(CLUSTERING_SCALER_PATH):
        return None, None

    kmeans = joblib.load(CLUSTERING_MODEL_PATH)
    scaler = joblib.load(CLUSTERING_SCALER_PATH)
    return kmeans, scaler


def predict_device_cluster(
    device_records: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Predict cluster for a new device.

    Args:
    - device_records: Sensor records for a single device

    Returns:
    - Dictionary with cluster assignment and profile match
    """
    kmeans, scaler = load_clustering_model()
    if kmeans is None or scaler is None:
        return None

    feature_df = compute_device_features(device_records)
    if feature_df.empty:
        return None

    feature_cols = [
        "avg_daily_consumption",
        "peak_hour",
        "weekend_multiplier",
        "session_count_per_day",
        "cylinder_lifetime_days",
    ]
    X = feature_df[feature_cols].values
    X_scaled = scaler.transform(X)

    cluster_label = kmeans.predict(X_scaled)[0]

    return {
        "device_id": feature_df["device_id"].iloc[0],
        "cluster": int(cluster_label),
        "features": feature_df[feature_cols].iloc[0].to_dict(),
    }


def get_cluster_recommendations(cluster_id: int) -> dict[str, str]:
    """Generate personalized recommendations based on cluster profile."""
    recommendations_map = {
        0: {
            "title": "Light User Profile",
            "description": "You have minimal gas consumption patterns.",
            "recommendation": "Refills are infrequent. Consider seasonal adjustments for your usage.",
            "benchmark": "You use less gas than typical households.",
        },
        1: {
            "title": "Normal Family User",
            "description": "You follow typical household consumption patterns.",
            "recommendation": "Regular refills recommended. Plan ahead based on seasonal patterns.",
            "benchmark": "Your usage is in line with similar households.",
        },
        2: {
            "title": "Heavy User Profile",
            "description": "You have higher than average gas consumption.",
            "recommendation": "Frequent refills needed. Consider energy efficiency improvements.",
            "benchmark": "You consume significantly more gas than typical households.",
        },
        3: {
            "title": "Commercial/High-Volume User",
            "description": "Very high consumption, possibly commercial use.",
            "recommendation": "Consider bulk refill contracts and efficiency audits.",
            "benchmark": "You are in the top tier of consumption.",
        },
    }

    return recommendations_map.get(
        cluster_id,
        {
            "title": "Unknown Cluster",
            "description": "Unable to determine cluster profile.",
            "recommendation": "Please submit more usage data for better clustering.",
            "benchmark": "Insufficient data for clustering.",
        },
    )
