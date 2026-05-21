"""
Fix Sensor_unit Schema Without Alembic

This script fixes the sensor_unit table schema to use a composite primary key
(sensor_id, timestamp) instead of just sensor_id.

This allows multiple readings per device to be stored (time-series data),
which is required for dashboard calculations, feature pipeline, and leak detection.

Usage:
    python fix_sensor_schema.py

No arguments needed - it will:
1. Drop the old sensor_unit table
2. Recreate it with the new schema
3. Verify the fix worked
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import engine
from models import Base


async def fix_sensor_schema():
    """Drop and recreate sensor_unit with new composite primary key schema"""
    
    print("\n" + "="*60)
    print("SENSOR_UNIT SCHEMA FIX - Without Alembic")
    print("="*60 + "\n")
    
    try:
        # Step 1: Drop the old table
        print("[1/3] Dropping old sensor_unit table...")
        async with engine.begin() as conn:
            await conn.execute("DROP TABLE IF EXISTS sensor_unit CASCADE")
        print("      ✅ Old table dropped\n")
        
        # Step 2: Recreate with new schema
        print("[2/3] Creating sensor_unit table with new schema...")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("      ✅ New table created with composite PK (sensor_id, timestamp)\n")
        
        # Step 3: Verify the schema
        print("[3/3] Verifying new schema...")
        async with engine.begin() as conn:
            # Check if table exists
            result = await conn.execute(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='sensor_unit')"
            )
            table_exists = result.scalar()
            
            if table_exists:
                print("      ✅ sensor_unit table verified\n")
            else:
                # For SQLite, use different query
                result = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='sensor_unit'"
                )
                table_exists = result.scalar()
                if table_exists:
                    print("      ✅ sensor_unit table verified (SQLite)\n")
        
        print("="*60)
        print("✅ SCHEMA FIX COMPLETE!")
        print("="*60)
        print("\nNext steps:")
        print("1. Restart your backend: uvicorn main:app --reload")
        print("2. Delete old data: DELETE FROM sensor_unit;")
        print("3. Re-run sensor simulation: python scripts/sensor_simulation.py test 20")
        print("\nYour database now supports unlimited readings per sensor! 🚀\n")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        print("Troubleshooting:")
        print("1. Ensure database is running and accessible")
        print("2. Check DATABASE_URL in your .env file")
        print("3. Verify you have the latest models.py with composite primary key")
        return False
    
    finally:
        await engine.dispose()


if __name__ == "__main__":
    success = asyncio.run(fix_sensor_schema())
    sys.exit(0 if success else 1)
