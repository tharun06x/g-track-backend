"""
Verify that the database has been populated correctly.
"""

import asyncio
import os
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

load_dotenv()
db_url = os.getenv("SQLALCHEMY_DATABASE_URL")


async def verify_db():
    engine = create_async_engine(db_url)
    
    async with engine.connect() as conn:
        # List all tables
        tables_result = await conn.execute(text("""
            SELECT name FROM sqlite_master 
            WHERE type='table' 
            ORDER BY name
        """))
        tables = [row[0] for row in tables_result]
        
        print("=" * 60)
        print("DATABASE TABLES")
        print("=" * 60)
        for table in tables:
            result = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.scalar()
            print(f"  {table:.<45} {count:>5} rows")
        
        print("\n" + "=" * 60)
        print("CLUSTERING MODEL METADATA")
        print("=" * 60)
        
        result = await conn.execute(text("""
            SELECT model_id, model_version, optimal_k, is_active, trained_at
            FROM clustering_model_metadata
        """))
        
        rows = result.fetchall()
        if rows:
            for row in rows:
                print(f"  Model V{row[1]}: k={row[2]}, active={row[3]}")
                print(f"    ID: {row[0]}")
                print(f"    Trained: {row[4]}")
        else:
            print("  No clustering models found")
        
        print("\n" + "=" * 60)
        print("SAMPLE SYNTHETIC FEATURES")
        print("=" * 60)
        
        result = await conn.execute(text("""
            SELECT device_id, timestamp, weight, 
                   rolling_7day_avg_consumption, 
                   rolling_30day_avg_consumption
            FROM synthetic_feature_row
            LIMIT 3
        """))
        
        rows = result.fetchall()
        for row in rows:
            print(f"  Device: {row[0]}")
            print(f"    Time: {row[1]}")
            print(f"    Weight: {row[2]:.2f} kg")
            if row[3]:
                print(f"    7-day avg: {row[3]:.3f} kg/day")
            if row[4]:
                print(f"    30-day avg: {row[4]:.3f} kg/day")
            print()
        
        print("✓ Database verification complete!")
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(verify_db())
