#!/usr/bin/env python3
"""
Sensor Simulation Script for G-TRACK
Simulates a gas cylinder sensor sending weight data to the backend
Weight range: 2kg to 14kg (fluctuating)
Send interval: 2 seconds
Default readings: 50
"""

import asyncio
import aiohttp
import random
from datetime import datetime
from typing import Optional
import json

# Configuration
# Use localhost for local development, or update to your remote backend
#BACKEND_HOST = "http://localhost:8000"  # Local development
BACKEND_HOST = "https://g-track-backend-94gv.onrender.com"  # Remote production
SENSOR_ENDPOINT = f"{BACKEND_HOST}/api/v1/sensor/readings"

# Sensor Configuration
DEVICE_ID = "SYNTH-2"
USER_ID = "3ebf297c23974fd18037"  # Change this to your user ID
TOTAL_GAS_WEIGHT = 14.0  # kg
SEND_INTERVAL = 5  # seconds

# Simulation state
current_weight = TOTAL_GAS_WEIGHT
min_weight = 2.0  # Minimum weight (kg)
max_weight = 14.0  # Maximum weight (kg)
connection_status = True
simulation_running = True


class GasSensorSimulator:
    """Simulates a gas cylinder sensor with realistic weight decay"""
    
    def __init__(
        self,
        device_id: str = DEVICE_ID,
        user_id: str = USER_ID,
        initial_weight: float = TOTAL_GAS_WEIGHT,
        min_weight: float = min_weight,
        max_weight: float = max_weight,
    ):
        self.device_id = device_id
        self.user_id = user_id
        self.current_weight = initial_weight
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.connection_status = True
        self.session: Optional[aiohttp.ClientSession] = None
        self.reading_count = 0
        
    async def init_session(self):
        """Initialize aiohttp session"""
        self.session = aiohttp.ClientSession()
        
    async def close_session(self):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()
    
    def calculate_next_weight(self) -> float:
        """
        Simulate realistic gas consumption with fluctuations
        - Weight fluctuates between 2kg and 14kg
        - Can increase or decrease (simulating consumption and refills)
        - Consumption: 0.05-0.2 kg
        - Refill events: 0.1-0.5 kg increase (10% chance)
        """
        # 10% chance of refill (weight increases)
        if random.random() < 0.1:
            change = random.uniform(0.1, 0.5)  # Refill increase
        else:
            # 90% consumption (weight decreases)
            change = -random.uniform(0.05, 0.2)
        
        new_weight = self.current_weight + change
        
        # Clamp to min/max range
        if new_weight > self.max_weight:
            new_weight = self.max_weight
        elif new_weight < self.min_weight:
            new_weight = self.min_weight
            
        return new_weight
    
    async def send_reading(self) -> bool:
        """Send sensor reading to backend"""
        if not self.session:
            await self.init_session()
        
        # Update weight
        self.current_weight = self.calculate_next_weight()
        self.reading_count += 1
        
        # Prepare payload
        payload = {
            "device_id": self.device_id,
            "weight": round(self.current_weight, 2),
            "user_id": self.user_id,
            "connection_status": self.connection_status,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        try:
            async with self.session.post(
                SENSOR_ENDPOINT,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15)  # Increased to 15s for slow backends
            ) as response:
                
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                if response.status == 201:
                    print(f"[{timestamp}] ✅ Reading #{self.reading_count} sent successfully")
                    print(f"   Device ID: {self.device_id}")
                    print(f"   Current Weight: {self.current_weight:.2f} kg")
                    print(f"   Connection Status: {'Connected' if self.connection_status else 'Disconnected'}")
                    print(f"   Response: {response.status} Created")
                    print()
                    return True
                else:
                    error_text = await response.text()
                    print(f"[{timestamp}] ❌ Failed to send reading #{self.reading_count}")
                    print(f"   Status Code: {response.status}")
                    print(f"   Error: {error_text}")
                    print()
                    return False
                    
        except asyncio.TimeoutError:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] ⏱️  Timeout sending reading #{self.reading_count}")
            print()
            return False
        except aiohttp.ClientError as e:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] 🔌 Connection error: {e}")
            print()
            return False
        except Exception as e:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] ⚠️  Unexpected error: {e}")
            print()
            return False
    
    def simulate_connection_issue(self):
        """Randomly simulate connection issues (5% chance)"""
        if random.random() < 0.05:
            self.connection_status = not self.connection_status
            status_text = "CONNECTED" if self.connection_status else "DISCONNECTED"
            print(f"   ⚠️  Connection status changed: {status_text}\n")
    
    def print_status(self):
        """Print current simulation status"""
        # Calculate percentage within the range (2-14kg)
        range_span = self.max_weight - self.min_weight
        position_in_range = self.current_weight - self.min_weight
        percentage = (position_in_range / range_span) * 100 if range_span > 0 else 0
        
        bar_length = 30
        filled = int(bar_length * percentage / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        print(f"\n{'='*70}")
        print(f"Gas Cylinder Simulation Status")
        print(f"{'='*70}")
        print(f"Device ID: {self.device_id}")
        print(f"User ID: {self.user_id}")
        print(f"Current Weight: {self.current_weight:.2f} kg (Range: {self.min_weight} - {self.max_weight} kg)")
        print(f"Position in Range: {percentage:.1f}%")
        print(f"[{bar}]")
        print(f"Readings Sent: {self.reading_count}")
        print(f"Backend: {BACKEND_HOST}")
        print(f"{'='*70}\n")


async def run_simulation(duration_seconds: Optional[int] = None, test_count: int = 0):
    """
    Run the sensor simulation
    
    Args:
        duration_seconds: How long to run (None = infinite)
        test_count: Number of readings to send (0 = infinite)
    """
    simulator = GasSensorSimulator()
    await simulator.init_session()
    
    print("\n" + "="*70)
    print("🚀 G-TRACK Sensor Simulation Started")
    print("="*70)
    print(f"Backend Host: {BACKEND_HOST}")
    print(f"Endpoint: {SENSOR_ENDPOINT}")
    print(f"Device ID: {DEVICE_ID}")
    print(f"User ID: {USER_ID}")
    print(f"Weight Range: {min_weight} - {max_weight} kg")
    print(f"Send Interval: {SEND_INTERVAL} seconds")
    if duration_seconds:
        print(f"Duration: {duration_seconds} seconds")
    if test_count > 0:
        print(f"Number of Readings: {test_count}")
    print("="*70 + "\n")
    
    try:
        start_time = datetime.now()
        reading_number = 0
        
        while True:
            # Check if we should stop
            if test_count > 0 and reading_number >= test_count:
                print(f"✅ Simulation complete! Sent {test_count} readings.")
                break
            
            if duration_seconds:
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed > duration_seconds:
                    print(f"✅ Simulation complete! Ran for {duration_seconds} seconds.")
                    break
            
            # Send reading
            await simulator.send_reading()
            simulator.simulate_connection_issue()
            reading_number += 1
            
            # Print status every 10 readings
            if reading_number % 10 == 0:
                simulator.print_status()
            
            # Wait before next reading
            await asyncio.sleep(SEND_INTERVAL)
            
    except KeyboardInterrupt:
        print("\n⏹️  Simulation stopped by user")
        simulator.print_status()
    except Exception as e:
        print(f"\n❌ Simulation error: {e}")
    finally:
        await simulator.close_session()
        print("\n✨ Sensor simulation ended\n")


async def test_single_reading():
    """Send a single test reading"""
    simulator = GasSensorSimulator()
    await simulator.init_session()
    
    print("\n" + "="*70)
    print("🧪 Testing Single Sensor Reading")
    print("="*70)
    print(f"Backend: {BACKEND_HOST}")
    print(f"Endpoint: {SENSOR_ENDPOINT}\n")
    
    try:
        success = await simulator.send_reading()
        if success:
            print("✅ Test successful!")
        else:
            print("❌ Test failed!")
    finally:
        await simulator.close_session()


async def main():
    """Main entry point"""
    import sys
    
    print("\nG-TRACK Sensor Simulation\n")
    print("Usage:")
    print("  python sensor_simulation.py [command] [options]")
    print("\nCommands:")
    print("  run [seconds]    - Run simulation for N seconds (default: infinite)")
    print("  test [count]     - Send N test readings (default: 50)")
    print("  single           - Send a single test reading")
    print("  continuous       - Run continuous simulation (press Ctrl+C to stop)")
    print("\nExamples:")
    print("  python sensor_simulation.py test 50         # Send 50 test readings (default)")
    print("  python sensor_simulation.py test 100        # Send 100 test readings")
    print("  python sensor_simulation.py run 60          # Run for 60 seconds")
    print("  python sensor_simulation.py continuous      # Run indefinitely")
    print()
    
    if len(sys.argv) < 2:
        # Default: run test with 50 readings
        await run_simulation(test_count=50)
    else:
        command = sys.argv[1].lower()
        
        if command == "test":
            count = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            await run_simulation(test_count=count)
        elif command == "run":
            duration = int(sys.argv[2]) if len(sys.argv) > 2 else None
            await run_simulation(duration_seconds=duration)
        elif command == "single":
            await test_single_reading()
        elif command == "continuous":
            await run_simulation()
        else:
            print(f"Unknown command: {command}")
            print("Use 'test', 'run', 'single', or 'continuous'")


if __name__ == "__main__":
    asyncio.run(main())
