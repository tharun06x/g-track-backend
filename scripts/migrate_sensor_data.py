import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv

async def migrate_db():
    load_dotenv()
    db_url = os.getenv("SQLALCHEMY_DATABASE_URL")
    if not db_url:
        print("No DB URL")
        return

    print(f"Connecting to {db_url}")
    # Using execution_options(isolation_level="AUTOCOMMIT") prevents the whole script from failing if one statement fails
    engine = create_async_engine(db_url, connect_args={"ssl": True}, execution_options={"isolation_level": "AUTOCOMMIT"})

    async with engine.connect() as conn:
        print("Recovering and migrating schema...")
        
        # Check tables
        res = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name='sensor_unit_old'"))
        has_old = res.fetchone() is not None
        
        res = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name='sensor_unit'"))
        has_new = res.fetchone() is not None

        # 1. If sensor_unit_old exists, but sensor_unit doesn't, just rename it back to recover
        if has_old and not has_new:
            print("Recovering: sensor_unit_old exists but sensor_unit doesn't. Renaming back.")
            await conn.execute(text("ALTER TABLE sensor_unit_old RENAME TO sensor_unit"))
            has_old = False
            has_new = True

        # 2. If both exist, we need to drop the new one because it might be incomplete, and rename old back
        if has_old and has_new:
            print("Recovering: Both exist. Dropping incomplete sensor_unit and renaming sensor_unit_old back.")
            await conn.execute(text("DROP TABLE sensor_unit CASCADE"))
            await conn.execute(text("ALTER TABLE sensor_unit_old RENAME TO sensor_unit"))
            has_old = False
            has_new = True

        print("State normalized. Starting migration...")

        # Get the user_id that owns SYNTH-2. If none, grab an admin or the first user.
        res = await conn.execute(text("SELECT user_id FROM users LIMIT 1"))
        user_id_row = res.fetchone()
        user_id = user_id_row[0] if user_id_row else 'UNKNOWN'
        
        # Check if SYNTH-2 has an owner
        res = await conn.execute(text("SELECT user_id FROM sensor_unit WHERE sensor_id = 'SYNTH-2' LIMIT 1"))
        owner_row = res.fetchone()
        if owner_row:
            user_id = owner_row[0]
            
        print(f"Using user_id: {user_id} for synthetic data")

        # Rename old table
        print("Renaming sensor_unit -> sensor_unit_old")
        await conn.execute(text("ALTER TABLE sensor_unit RENAME TO sensor_unit_old"))
        
        # Create new table with composite PK
        print("Creating new sensor_unit table")
        await conn.execute(text("""
        CREATE TABLE sensor_unit (
            sensor_id VARCHAR(30) NOT NULL, 
            current_weight FLOAT NOT NULL, 
            connection_status BOOLEAN, 
            timestamp TIMESTAMP WITH TIME ZONE NOT NULL, 
            user_id VARCHAR(20) NOT NULL, 
            PRIMARY KEY (sensor_id, timestamp), 
            FOREIGN KEY(user_id) REFERENCES users (user_id)
        )
        """))
        
        # Insert old live data
        print("Inserting old live data")
        await conn.execute(text("""
        INSERT INTO sensor_unit (sensor_id, current_weight, connection_status, timestamp, user_id)
        SELECT sensor_id, current_weight, connection_status, timestamp, user_id FROM sensor_unit_old
        """))
        
        # Insert synthetic data
        print("Inserting synthetic data")
        await conn.execute(text(f"""
        INSERT INTO sensor_unit (sensor_id, current_weight, connection_status, timestamp, user_id)
        SELECT device_id, weight, true, timestamp, '{user_id}' 
        FROM synthetic_sensor_reading
        ON CONFLICT (sensor_id, timestamp) DO NOTHING
        """))
        
        # Drop old table to clean up old indexes
        print("Dropping sensor_unit_old and its indexes")
        await conn.execute(text("DROP TABLE sensor_unit_old CASCADE"))
        
        # Recreate indexes
        print("Recreating indexes")
        await conn.execute(text("CREATE INDEX ix_sensor_device_time ON sensor_unit (user_id, timestamp)"))
        await conn.execute(text("CREATE INDEX ix_sensor_unit_sensor_id ON sensor_unit (sensor_id)"))
        await conn.execute(text("CREATE INDEX ix_sensor_unit_timestamp ON sensor_unit (timestamp)"))
        await conn.execute(text("CREATE INDEX ix_sensor_unit_user_id ON sensor_unit (user_id)"))
        
        print("Migration complete!")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(migrate_db())
