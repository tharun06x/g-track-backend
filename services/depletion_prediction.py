from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from random import Random
from typing import Any

import pandas as pd
from joblib import dump, load
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split

MODEL_PATH = Path("models") / "gas_depletion_linear_regression.joblib"

FEATURE_COLUMNS = [
    "current_weight",
    "rolling_7day_avg",
    "rolling_30day_avg",
    "day_of_week",
    "days_since_refill",
]


@dataclass
class DepletionTrainResult:
    model_path: str
    rows_used: int
    mae_days: float


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def rule_based_days_remaining(current_weight: float, rolling_7day_avg_consumption: float) -> float | None:
    """Level-1 baseline predictor: current_weight / rolling_7day_avg_consumption."""
    if rolling_7day_avg_consumption <= 1e-6:
        return None
    return max(current_weight, 0.0) / rolling_7day_avg_consumption


def latest_depletion_features(feature_rows: list[dict[str, Any]]) -> dict[str, float] | None:
    if not feature_rows:
        return None
    latest = feature_rows[-1]
    return {
        "current_weight": _safe_float(latest.get("weight")),
        "rolling_7day_avg": _safe_float(latest.get("rolling_7day_avg_consumption")),
        "rolling_30day_avg": _safe_float(latest.get("rolling_30day_avg_consumption")),
        "day_of_week": _safe_float(latest.get("day_of_week")),
        "days_since_refill": _safe_float(latest.get("days_since_refill")),
    }


def build_training_dataset(feature_rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Build supervised rows from completed cylinder lifecycles.

    Target: actual_days_lasted (days from snapshot until next refill starts).
    """
    if not feature_rows:
        return pd.DataFrame(columns=FEATURE_COLUMNS + ["actual_days_lasted"])

    df = pd.DataFrame(feature_rows).copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(["device_id", "timestamp"]).reset_index(drop=True)
    df["is_refill"] = df["is_refill"].fillna(False).astype(bool)

    df["cycle_id"] = df.groupby("device_id")["is_refill"].cumsum()
    max_cycle = df.groupby("device_id")["cycle_id"].transform("max")
    complete_cycles = df["cycle_id"] < max_cycle
    working = df[complete_cycles].copy()
    if working.empty:
        return pd.DataFrame(columns=FEATURE_COLUMNS + ["actual_days_lasted"])

    cycle_end = (
        working.groupby(["device_id", "cycle_id"], sort=False)["timestamp"]
        .transform("max")
    )
    working["actual_days_lasted"] = (
        cycle_end - working["timestamp"]
    ).dt.total_seconds() / 86400.0

    training_df = pd.DataFrame(
        {
            "current_weight": working["weight"].astype(float),
            "rolling_7day_avg": working["rolling_7day_avg_consumption"].astype(float),
            "rolling_30day_avg": working["rolling_30day_avg_consumption"].astype(float),
            "day_of_week": working["day_of_week"].astype(float),
            "days_since_refill": working["days_since_refill"].astype(float),
            "actual_days_lasted": working["actual_days_lasted"].astype(float),
        }
    )

    training_df = training_df.dropna()
    training_df = training_df[(training_df["rolling_7day_avg"] > 0) & (training_df["actual_days_lasted"] >= 0)]
    return training_df.reset_index(drop=True)


def train_linear_regression_model(
    training_df: pd.DataFrame,
    model_path: Path = MODEL_PATH,
    test_size: float = 0.2,
    random_state: int = 42,
) -> DepletionTrainResult:
    if training_df.empty:
        raise ValueError("Training dataframe is empty")

    X = training_df[FEATURE_COLUMNS]
    y = training_df["actual_days_lasted"]

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=test_size,
        random_state=random_state,
    )

    model = LinearRegression()
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    mae = mean_absolute_error(y_test, preds)

    model_path.parent.mkdir(parents=True, exist_ok=True)
    dump(model, model_path)

    return DepletionTrainResult(
        model_path=str(model_path),
        rows_used=len(training_df),
        mae_days=float(mae),
    )


def load_trained_model(model_path: Path = MODEL_PATH) -> LinearRegression | None:
    if not model_path.exists():
        return None
    return load(model_path)


def predict_days_remaining_ml(model: LinearRegression, features: dict[str, float]) -> float:
    row = [[features[col] for col in FEATURE_COLUMNS]]
    return float(model.predict(row)[0])


def generate_synthetic_lifecycle_records(
    lifecycle_count: int = 80,
    seed: int = 7,
) -> list[dict[str, Any]]:
    """Create synthetic sensor histories for model bootstrapping."""
    rng = Random(seed)
    records: list[dict[str, Any]] = []
    device_count = 8

    start_time = datetime(2026, 1, 1, tzinfo=UTC)
    device_clock = {f"SYNTH-{i + 1}": start_time for i in range(device_count)}

    for idx in range(lifecycle_count):
        device_id = f"SYNTH-{(idx % device_count) + 1}"
        t = device_clock[device_id]

        start_weight = rng.uniform(28.0, 32.0)
        weight = start_weight
        duration_days = rng.randint(18, 42)
        step_hours = 3
        steps = max(1, int((duration_days * 24) / step_hours))

        for _ in range(steps):
            hour = t.hour
            weekday = t.weekday()

            base_use = rng.uniform(0.01, 0.05)  # kg per 3h
            if hour in (6, 7, 8, 12, 13, 19, 20, 21):
                base_use *= rng.uniform(1.6, 2.4)
            if hour <= 4:
                base_use *= rng.uniform(0.05, 0.25)
            if weekday >= 5:
                base_use *= rng.uniform(1.05, 1.2)

            use = max(base_use + rng.uniform(-0.01, 0.01), 0.002)
            weight = max(weight - use, rng.uniform(1.0, 2.5))

            records.append(
                {
                    "device_id": device_id,
                    "timestamp": t,
                    "weight": round(weight, 3),
                }
            )
            t += timedelta(hours=step_hours)

        # Refill jump creates clear lifecycle boundary.
        refill_weight = start_weight + rng.uniform(-0.5, 0.8)
        records.append(
            {
                "device_id": device_id,
                "timestamp": t,
                "weight": round(refill_weight, 3),
            }
        )

        device_clock[device_id] = t + timedelta(hours=3)

    return records
