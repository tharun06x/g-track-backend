#!/usr/bin/env python3
"""Quick test of clustering functionality."""

import random
from datetime import datetime, timedelta, UTC
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.usage_clustering import (
    compute_device_features,
    find_optimal_k,
    get_cluster_recommendations,
    predict_device_cluster,
    train_clustering_model,
)


def generate_test_data():
    """Generate minimal test data."""
    random.seed(42)
    records = []
    
    # Create 5 light users
    start_time = datetime.now(UTC) - timedelta(days=30)
    for device_num in range(5):
        device_id = f"light_user_{device_num}"
        weight = 100.0
        for day in range(30):
            for hour in range(24):
                # 0.3 kg/day consumption
                weight -= 0.3 / 24 * random.uniform(0.7, 1.3)
                records.append({
                    "device_id": device_id,
                    "timestamp": start_time + timedelta(days=day, hours=hour),
                    "weight": max(0, weight),
                })
    
    # Create 5 heavy users
    for device_num in range(5):
        device_id = f"heavy_user_{device_num}"
        weight = 100.0
        for day in range(30):
            for hour in range(24):
                # 2.0 kg/day consumption
                weight -= 2.0 / 24 * random.uniform(0.7, 1.3)
                records.append({
                    "device_id": device_id,
                    "timestamp": start_time + timedelta(days=day, hours=hour),
                    "weight": max(0, weight),
                })
    
    return records


def test_feature_computation():
    """Test 1: Feature computation."""
    print("TEST 1: Feature Computation")
    print("-" * 50)
    
    records = generate_test_data()
    features = compute_device_features(records)
    
    print(f"✓ Computed features for {len(features)} devices")
    print("\nSample features:")
    for i, row in features.iterrows():
        print(f"  {row['device_id']}:")
        print(f"    - Consumption: {row['avg_daily_consumption']:.2f} kg/day")
        print(f"    - Peak hour: {row['peak_hour']:.0f}:00")
        print(f"    - Weekend multiplier: {row['weekend_multiplier']:.2f}x")
        print(f"    - Lifetime: {row['cylinder_lifetime_days']:.0f} days")
    
    return records


def test_clustering(records):
    """Test 2: Clustering."""
    print("\n\nTEST 2: Clustering (K-means + Elbow)")
    print("-" * 50)
    
    result = train_clustering_model(records)
    
    print(f"✓ Trained model with k={result['optimal_k']}")
    print(f"\nCluster Profiles:")
    for cluster_id, profile in result["cluster_profiles"].items():
        print(f"\n  Cluster {cluster_id}:")
        print(f"    - Devices: {profile['device_count']}")
        print(f"    - Avg consumption: {profile['avg_daily_consumption']:.2f} kg/day")
        print(f"    - Avg sessions/day: {profile['avg_sessions_per_day']:.1f}")
    
    return result


def test_prediction():
    """Test 3: Prediction for new device."""
    print("\n\nTEST 3: Predict Cluster for New Device")
    print("-" * 50)
    
    # Create a new light user device
    records = []
    start_time = datetime.now(UTC) - timedelta(days=15)
    weight = 100.0
    for day in range(15):
        for hour in range(24):
            weight -= 0.35 / 24 * random.uniform(0.7, 1.3)
            records.append({
                "device_id": "new_device_test",
                "timestamp": start_time + timedelta(days=day, hours=hour),
                "weight": max(0, weight),
            })
    
    result = predict_device_cluster(records)
    print(f"✓ Predicted cluster for new device")
    print(f"  Device: {result['device_id']}")
    print(f"  Cluster: {result['cluster']}")
    print(f"  Features:")
    for key, val in result['features'].items():
        if isinstance(val, float):
            print(f"    - {key}: {val:.2f}")
        else:
            print(f"    - {key}: {val}")


def test_recommendations():
    """Test 4: Recommendations."""
    print("\n\nTEST 4: Cluster Recommendations")
    print("-" * 50)
    
    for cluster_id in range(3):
        rec = get_cluster_recommendations(cluster_id)
        print(f"\nCluster {cluster_id}:")
        print(f"  Title: {rec['title']}")
        print(f"  Recommendation: {rec['recommendation']}")


def main():
    """Run all tests."""
    print("=" * 50)
    print("CLUSTERING FEATURE - TESTS")
    print("=" * 50)
    
    records = test_feature_computation()
    test_clustering(records)
    test_prediction()
    test_recommendations()
    
    print("\n" + "=" * 50)
    print("✓ ALL TESTS PASSED")
    print("=" * 50)


if __name__ == "__main__":
    main()
