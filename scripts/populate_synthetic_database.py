"""
Populate the database with synthetic dataset for ML model training.

This script:
1. Generates synthetic sensor readings
2. Stores them in the Synthetic_sensor_reading table
3. Computes features using the feature pipeline
4. Stores computed features in Synthetic_feature_row table
5. Trains clustering and depletion models
6. Records model metadata
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment before importing database
from dotenv import load_dotenv
load_dotenv()

# Now import database components
import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from models import (
    Base,
    Synthetic_device,
    Synthetic_sensor_reading,
    Synthetic_feature_row,
    Clustering_model_metadata,
    Depletion_prediction_metadata,
)
from services.depletion_prediction import (
    generate_synthetic_lifecycle_records,
    build_training_dataset,
    train_linear_regression_model,
)
from services.feature_pipeline import build_features
from services.usage_clustering import train_clustering_model, load_clustering_model

DATABASE_URL = os.getenv("SQLALCHEMY_DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_database():
    """Create all tables and clear existing synthetic data."""
    async with engine.begin() as conn:
        # Drop all synthetic tables first (idempotent)
        await conn.run_sync(Base.metadata.drop_all)
        # Recreate all tables
        await conn.run_sync(Base.metadata.create_all)
    print("✓ Database tables created (cleared existing synthetic data)")


async def populate_synthetic_sensor_data(session: AsyncSession, dataset_version: int = 1):
    """Generate and store synthetic sensor readings."""
    print(f"\n[1] Populating Synthetic Sensor Readings (version {dataset_version})...")
    
    # Generate synthetic data
    synthetic_records = generate_synthetic_lifecycle_records(lifecycle_count=100, seed=42)
    
    if not synthetic_records:
        print("✗ No synthetic records generated")
        return []
    
    # Ensure all records have is_refill field
    for record in synthetic_records:
        if "is_refill" not in record:
            record["is_refill"] = False
    
    # Process by device
    devices_by_id = {}
    readings = []
    
    for record in synthetic_records:
        device_id = record["device_id"]
        
        # Create device entry if not exists
        if device_id not in devices_by_id:
            device = Synthetic_device(
                device_id=device_id,
                dataset_version=dataset_version,
                lifecycle_count=0,
            )
            session.add(device)
            devices_by_id[device_id] = device
        
        # Track refills per device
        if record.get("is_refill", False):
            devices_by_id[device_id].lifecycle_count += 1
        
        # Create reading entry
        reading_id = f"SYNTH-READ-{uuid.uuid4().hex[:12]}"
        reading = Synthetic_sensor_reading(
            reading_id=reading_id,
            device_id=device_id,
            weight=record["weight"],
            timestamp=record["timestamp"],
            is_refill=record.get("is_refill", False),
        )
        session.add(reading)
        readings.append(reading)
    
    await session.commit()
    print(f"✓ Created {len(synthetic_records)} readings from {len(devices_by_id)} devices")
    return synthetic_records


async def compute_and_store_features(session: AsyncSession, synthetic_records: list):
    """Compute features from synthetic readings and store in database."""
    print("\n[2] Computing and Storing Features...")
    
    if not synthetic_records:
        print("✗ No synthetic records to process")
        return []
    
    # Build features using the feature pipeline
    features = build_features(synthetic_records)
    
    if not features:
        print("✗ No features computed")
        return []
    
    # Store features in database
    feature_count = 0
    for feature_row in features:
        feature_id = f"SYNTH-FEAT-{uuid.uuid4().hex[:12]}"
        
        feature_record = Synthetic_feature_row(
            feature_id=feature_id,
            device_id=feature_row.get("device_id"),
            timestamp=feature_row.get("timestamp"),
            weight=feature_row.get("weight"),
            prev_weight=feature_row.get("prev_weight"),
            weight_delta=feature_row.get("weight_delta"),
            time_gap_hours=feature_row.get("time_gap_hours"),
            consumption_per_hour=feature_row.get("consumption_per_hour"),
            consumption_per_day=feature_row.get("consumption_per_day"),
            hour_of_day=feature_row.get("hour_of_day"),
            day_of_week=feature_row.get("day_of_week"),
            is_weekend=feature_row.get("is_weekend"),
            is_refill=feature_row.get("is_refill"),
            days_since_refill=feature_row.get("days_since_refill"),
            rolling_mean_1h=feature_row.get("rolling_mean_1h"),
            rolling_mean_24h=feature_row.get("rolling_mean_24h"),
            rolling_std_1h=feature_row.get("rolling_std_1h"),
            rolling_std_24h=feature_row.get("rolling_std_24h"),
            rolling_7day_avg_consumption=feature_row.get("rolling_7day_avg_consumption"),
            rolling_30day_avg_consumption=feature_row.get("rolling_30day_avg_consumption"),
            rolling_max_drop_1h=feature_row.get("rolling_max_drop_1h"),
            session_count_today=feature_row.get("session_count_today"),
            idle_drop_rate=feature_row.get("idle_drop_rate"),
        )
        session.add(feature_record)
        feature_count += 1
    
    await session.commit()
    print(f"✓ Stored {feature_count} computed features")
    return features


async def train_and_store_depletion_model(session: AsyncSession, synthetic_records: list):
    """Train depletion prediction model and store metadata."""
    print("\n[3] Training Depletion Prediction Model...")
    
    # Build training dataset from synthetic records
    training_df = build_training_dataset(synthetic_records)
    
    if training_df.empty:
        print("✗ No training data available")
        return
    
    print(f"   Training data: {len(training_df)} rows")
    
    # Train model
    try:
        result = train_linear_regression_model(training_df)
        print(f"✓ Model trained with MAE: {result.mae_days:.2f} days")
        print(f"   Model saved to: {result.model_path}")
        
        # Store metadata
        model_metadata = Depletion_prediction_metadata(
            model_id=f"DEPLETION-{uuid.uuid4().hex[:12]}",
            model_version=1,
            model_type="linear_regression",
            mae_days=result.mae_days,
            rows_used=result.rows_used,
            is_active=True,
            model_path=result.model_path,
        )
        session.add(model_metadata)
        await session.commit()
        print("✓ Model metadata stored in database")
        
    except Exception as e:
        print(f"✗ Error training model: {e}")


async def train_and_store_clustering_model(session: AsyncSession, synthetic_records: list):
    """Train clustering model and store metadata."""
    print("\n[4] Training Usage Pattern Clustering Model...")
    
    if not synthetic_records:
        print("✗ No synthetic records available")
        return
    
    try:
        result = train_clustering_model(synthetic_records)
        optimal_k = result.get("optimal_k", 2)
        
        print(f"✓ Clustering model trained")
        print(f"   Optimal K: {optimal_k}")
        print(f"   Model saved to: {result.get('model_path')}")
        
        # Store metadata
        inertias = result.get("inertias", [])
        model_metadata = Clustering_model_metadata(
            model_id=f"CLUSTERING-{uuid.uuid4().hex[:12]}",
            model_version=1,
            optimal_k=optimal_k,
            inertias=inertias,
            is_active=True,
            model_path=result.get("model_path"),
            scaler_path=result.get("scaler_path"),
            training_records_count=len(synthetic_records),
        )
        session.add(model_metadata)
        await session.commit()
        print("✓ Clustering model metadata stored in database")
        
    except Exception as e:
        print(f"✗ Error training clustering model: {e}")


async def verify_database_population(session: AsyncSession):
    """Verify that all data was stored correctly."""
    print("\n[5] Verifying Database Population...")
    
    try:
        # Count synthetic devices
        from sqlalchemy import func, select
        
        device_count = await session.execute(select(func.count(Synthetic_device.device_id)))
        device_count = device_count.scalar()
        
        reading_count = await session.execute(select(func.count(Synthetic_sensor_reading.reading_id)))
        reading_count = reading_count.scalar()
        
        feature_count = await session.execute(select(func.count(Synthetic_feature_row.feature_id)))
        feature_count = feature_count.scalar()
        
        depletion_models = await session.execute(select(func.count(Depletion_prediction_metadata.model_id)))
        depletion_models = depletion_models.scalar()
        
        clustering_models = await session.execute(select(func.count(Clustering_model_metadata.model_id)))
        clustering_models = clustering_models.scalar()
        
        print(f"\n{'='*60}")
        print(f"SYNTHETIC DATABASE POPULATION SUMMARY")
        print(f"{'='*60}")
        print(f"Synthetic Devices:           {device_count}")
        print(f"Sensor Readings:             {reading_count}")
        print(f"Computed Features:           {feature_count}")
        print(f"Depletion Models:            {depletion_models}")
        print(f"Clustering Models:           {clustering_models}")
        print(f"{'='*60}")
        
        if all([device_count > 0, reading_count > 0, feature_count > 0, depletion_models > 0, clustering_models > 0]):
            print("✓ DATABASE POPULATION SUCCESSFUL\n")
        else:
            print("✗ Some data may be missing\n")
            
    except Exception as e:
        print(f"✗ Error verifying database: {e}")


async def main():
    """Main entry point."""
    print("=" * 60)
    print("SYNTHETIC DATABASE POPULATION")
    print("=" * 60)
    
    try:
        # Initialize database
        await init_database()
        
        # Create async session
        async with AsyncSessionLocal() as session:
            # Populate data
            synthetic_records = await populate_synthetic_sensor_data(session, dataset_version=1)
            await compute_and_store_features(session, synthetic_records)
            await train_and_store_depletion_model(session, synthetic_records)
            await train_and_store_clustering_model(session, synthetic_records)
            await verify_database_population(session)
        
        print("✓ All operations completed successfully!")
        
    except Exception as e:
        print(f"\n✗ Error during database population: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
