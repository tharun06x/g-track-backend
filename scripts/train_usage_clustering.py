#!/usr/bin/env python3
"""Training script for usage pattern clustering model.

This script generates synthetic multi-device household data and trains
the K-means clustering model to identify usage behavior patterns.
"""

import os
import sys
import random
from datetime import datetime, timedelta, UTC
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.usage_clustering import train_clustering_model


def generate_synthetic_household_data(num_devices: int = 10, days: int = 90) -> list[dict]:
    """Generate realistic synthetic usage data for multiple households.

    Creates three distinct household types:
    1. Light users (students, single occupants): 0.3-0.5 kg/day
    2. Normal families: 0.7-1.2 kg/day
    3. Heavy users (large families, commercial): 1.5-2.5 kg/day

    Each device has realistic cooking patterns with meals and peaks.
    """
    random.seed(42)
    records = []

    # Define three household profiles
    profiles = [
        # Light users (30% of households)
        {
            "pct": 0.3,
            "daily_consumption": random.uniform(0.3, 0.5),
            "sessions_per_day": random.uniform(1.5, 2.5),
            "peak_hour": random.choice([12, 13, 19, 20]),  # Lunch and dinner
            "weekend_multiplier": random.uniform(0.9, 1.1),  # Similar to weekdays
        },
        # Normal families (50% of households)
        {
            "pct": 0.5,
            "daily_consumption": random.uniform(0.8, 1.2),
            "sessions_per_day": random.uniform(2.5, 3.5),
            "peak_hour": random.choice([12, 13, 19, 20, 21]),
            "weekend_multiplier": random.uniform(1.1, 1.4),  # More weekend usage
        },
        # Heavy users (20% of households)
        {
            "pct": 0.2,
            "daily_consumption": random.uniform(1.6, 2.5),
            "sessions_per_day": random.uniform(4.0, 6.0),
            "peak_hour": random.choice([12, 19, 20, 21]),
            "weekend_multiplier": random.uniform(1.3, 1.8),  # Much higher weekend usage
        },
    ]

    current_device_id = 1

    for profile_idx, profile in enumerate(profiles):
        num_profile_devices = int(num_devices * profile["pct"])
        if profile_idx == len(profiles) - 1:
            # Ensure we don't have rounding errors
            num_profile_devices = num_devices - (current_device_id - 1)

        for _ in range(num_profile_devices):
            device_id = f"device_{current_device_id:03d}"
            current_device_id += 1

            # Generate data for this device
            current_weight = 100.0  # Start with full cylinder
            current_time = datetime.now(UTC) - timedelta(days=days)

            daily_consumption = profile["daily_consumption"]
            peak_hour = profile["peak_hour"]
            sessions_per_day = profile["sessions_per_day"]
            weekend_multiplier = profile["weekend_multiplier"]

            while current_time < datetime.now(UTC):
                # Simulate refill (reset to ~95 kg when it gets too low)
                if current_weight < 10:
                    current_weight = 95.0

                # Generate hour-by-hour readings
                for hour in range(24):
                    current_time += timedelta(hours=1)
                    if current_time > datetime.now(UTC):
                        break

                    is_weekend = current_time.weekday() >= 5
                    consumption_multiplier = (
                        weekend_multiplier if is_weekend else 1.0
                    )

                    # Peak hour has more consumption
                    if hour == peak_hour or hour == (peak_hour - 1):
                        hour_consumption = (
                            daily_consumption
                            * consumption_multiplier
                            * 0.3  # 30% of daily in peak hours
                        )
                    elif 12 <= hour <= 21:
                        # Active hours
                        hour_consumption = (
                            daily_consumption
                            * consumption_multiplier
                            * 0.04
                        )
                    else:
                        # Idle hours (minimal consumption)
                        hour_consumption = random.uniform(0.01, 0.03)

                    # Add some randomness
                    hour_consumption *= random.uniform(0.7, 1.3)

                    current_weight -= hour_consumption

                    if current_weight < 0:
                        current_weight = 0

                    records.append(
                        {
                            "device_id": device_id,
                            "timestamp": current_time,
                            "weight": max(0, current_weight),
                        }
                    )

    print(f"Generated {len(records)} readings from {num_devices} synthetic devices")
    return records


def main():
    """Generate data and train clustering model."""
    print("=" * 60)
    print("Usage Pattern Clustering - Training Script")
    print("=" * 60)

    # Generate synthetic data
    records = generate_synthetic_household_data(num_devices=15, days=90)

    # Train clustering model
    print("\nTraining K-means clustering model with elbow method...")
    result = train_clustering_model(records)

    # Display results
    if "error" in result:
        print(f"Error: {result['error']}")
        return

    print(f"\nTraining Results:")
    print(f"  Devices clustered: {result['devices_clustered']}")
    print(f"  Optimal K (clusters): {result['optimal_k']}")
    print(f"  Model saved to: {result['model_path']}")
    print(f"  Scaler saved to: {result['scaler_path']}")

    if result["inertias"]:
        print(f"\n  Inertia values by K:")
        for i, inertia in enumerate(result["inertias"], 1):
            print(f"    K={i}: {inertia:.2f}")

    print(f"\nCluster Profiles:")
    for cluster_id, profile in result["cluster_profiles"].items():
        print(f"\n  Cluster {cluster_id}:")
        print(f"    Devices: {profile['device_count']}")
        print(
            f"    Avg daily consumption: {profile['avg_daily_consumption']:.2f} kg/day"
        )
        print(f"    Median peak hour: {profile['median_peak_hour']:02d}:00")
        print(
            f"    Weekend multiplier: {profile['avg_weekend_multiplier']:.2f}x"
        )
        print(
            f"    Sessions per day: {profile['avg_sessions_per_day']:.1f}"
        )
        print(
            f"    Cylinder lifetime: {profile['avg_cylinder_lifetime_days']:.1f} days"
        )

    print("\n" + "=" * 60)
    print("Clustering model training complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
