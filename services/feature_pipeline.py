from __future__ import annotations

from typing import Any

import pandas as pd


def build_features(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build model-ready feature rows from raw sensor records.

    Expected input records:
    [{"device_id": "...", "timestamp": datetime, "weight": float}, ...]
    """
    if not records:
        return []

    df = pd.DataFrame(records).copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(["device_id", "timestamp"]).reset_index(drop=True)

    grp = df.groupby("device_id", sort=False)

    # Core delta/rate features.
    df["prev_weight"] = grp["weight"].shift(1)
    df["weight_delta"] = df["weight"] - df["prev_weight"]
    df["time_gap_hours"] = grp["timestamp"].diff().dt.total_seconds() / 3600.0
    df["consumption_per_hour"] = df["weight_delta"] / df["time_gap_hours"]

    # Time features.
    df["hour_of_day"] = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.dayofweek
    df["is_weekend"] = df["day_of_week"] >= 5
    df["date_only"] = df["timestamp"].dt.date

    # Refill detection and cylinder age.
    refill_threshold_kg = 2.0
    df["is_refill"] = df["weight_delta"] > refill_threshold_kg

    last_refill = df["timestamp"].where(df["is_refill"])
    last_refill = last_refill.groupby(df["device_id"]).ffill()
    df["days_since_refill"] = (df["timestamp"] - last_refill).dt.total_seconds() / 86400.0

    # Daily aggregation feature.
    daily_consumption = (
        df.groupby(["device_id", "date_only"], sort=False)["weight_delta"]
        .sum(min_count=1)
        .rename("consumption_per_day")
    )
    df = df.merge(
        daily_consumption,
        how="left",
        left_on=["device_id", "date_only"],
        right_index=True,
    )

    # Rolling/window features with time-based windows.
    def _rolling_for_device(device_df: pd.DataFrame) -> pd.DataFrame:
        device_id = device_df.name
        d = device_df.set_index("timestamp").sort_index()

        d["rolling_mean_1h"] = d["consumption_per_hour"].rolling("1h", min_periods=1).mean()
        d["rolling_mean_24h"] = d["consumption_per_hour"].rolling("24h", min_periods=1).mean()
        d["rolling_std_1h"] = d["consumption_per_hour"].rolling("1h", min_periods=2).std()
        d["rolling_std_24h"] = d["consumption_per_hour"].rolling("24h", min_periods=2).std()

        # Positive consumption rate in kg/day for depletion forecasting.
        positive_hourly = (-d["consumption_per_hour"]).clip(lower=0)
        d["rolling_7day_avg_consumption"] = positive_hourly.rolling("168h", min_periods=1).mean() * 24.0
        d["rolling_30day_avg_consumption"] = positive_hourly.rolling("720h", min_periods=1).mean() * 24.0

        # Biggest single drop (positive kg) in the last hour.
        drop_amount = (-d["weight_delta"]).clip(lower=0)
        d["rolling_max_drop_1h"] = drop_amount.rolling("1h", min_periods=1).max()

        d = d.reset_index()
        d["device_id"] = device_id
        return d

    df = df.groupby("device_id", group_keys=False, sort=False).apply(_rolling_for_device).reset_index(drop=True)

    # Idle usage feature: average rate in 00:00-05:59 mapped by device/day.
    idle_mask = df["hour_of_day"].between(0, 5)
    idle_daily = (
        df[idle_mask]
        .groupby(["device_id", "date_only"], sort=False)["consumption_per_hour"]
        .mean()
        .rename("idle_drop_rate")
    )
    df = df.merge(
        idle_daily,
        how="left",
        left_on=["device_id", "date_only"],
        right_index=True,
    )

    # Session detection from sustained negative deltas.
    active_drop_threshold = -0.05
    new_session_gap_hours = 1.0

    def _session_features(device_df: pd.DataFrame) -> pd.DataFrame:
        device_id = device_df.name
        d = device_df.sort_values("timestamp").copy()
        d["active_consumption"] = d["weight_delta"] < active_drop_threshold
        d["gap_hours"] = d["timestamp"].diff().dt.total_seconds() / 3600.0

        new_session = d["active_consumption"] & (
            ~d["active_consumption"].shift(1, fill_value=False)
            | (d["gap_hours"] > new_session_gap_hours)
            | (d["date_only"] != d["date_only"].shift(1))
        )
        d["session_id"] = new_session.cumsum().where(d["active_consumption"])

        session_count = (
            d.groupby("date_only", sort=False)["session_id"]
            .nunique(dropna=True)
            .rename("session_count_today")
        )
        d = d.merge(session_count, how="left", left_on="date_only", right_index=True)
        d["session_count_today"] = d["session_count_today"].fillna(0).astype(int)

        session_spans = (
            d.dropna(subset=["session_id"])
            .groupby(["date_only", "session_id"], sort=False)["timestamp"]
            .agg(["min", "max"])
        )
        if not session_spans.empty:
            session_spans["duration_hours"] = (
                session_spans["max"] - session_spans["min"]
            ).dt.total_seconds() / 3600.0
            avg_session_duration = session_spans.groupby(level=0)["duration_hours"].mean()
            d = d.merge(
                avg_session_duration.rename("avg_session_duration"),
                how="left",
                left_on="date_only",
                right_index=True,
            )
        else:
            d["avg_session_duration"] = pd.NA

        d["device_id"] = device_id
        return d

    df = df.groupby("device_id", group_keys=False, sort=False).apply(_session_features).reset_index(drop=True)

    # Clean up serialization output.
    df = df.drop(columns=["prev_weight", "time_gap_hours", "active_consumption", "gap_hours", "session_id"], errors="ignore")
    df = df.where(pd.notnull(df), None)

    return df.to_dict(orient="records")
