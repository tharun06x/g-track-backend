# G-Track Backend

FastAPI backend for **G-Track**, an advanced IoT LPG gas cylinder tracking and monitoring system. It provides real-time sensor ingestion, automated leak alerts, and comprehensive user/distributor workflows.

## 🚀 Architecture & Performance Optimizations

This backend is heavily optimized to run on low-resource environments (like the **Render Free Tier**) while handling high-frequency IoT data:

*   **In-Memory State Manager:** The backend completely decouples high-frequency IoT reads from the database. Current device states are stored in process RAM (`services/state_manager.py`), reducing DB read queries from 1-per-second to **zero** during normal operation.
*   **Real-Time WebSockets:** Frontend clients receive live weight updates directly via WebSockets (`routers/ws.py`), eliminating the need for database polling.
*   **TTL Dashboard Caching:** Heavy analytical queries (daily usage, 30-day averages) are cached in memory for 10 minutes, protecting the database connection pool from frontend refresh spam.
*   **Async Background Tasks:** Email notifications (leak alerts, refill reminders) are handled in background tasks, ensuring the ESP32 IoT device gets a near-instant `<50ms` HTTP response regardless of SMTP latency.
*   **Database Throttling:** Sensor POSTs are intelligently debounced. The database is only written to when a meaningful weight change occurs or after 5 minutes, preventing the `sensor_unit` table from ballooning while still pushing live updates to the WebSocket.

## 📡 Core Workflows

- **IoT Ingestion:** Devices POST weight readings. The backend computes drop rates, fires leak alerts if the threshold is crossed, and broadcasts the weight to connected clients.
- **Consumer App:** Users can monitor gas levels, receive low-gas warnings, log complaints, and request automatic refills.
- **Distributor Portal:** Distributors manage users, approve refill requests, and track fleet analytics.
- **Machine Learning / Analytics:** Support for synthetic data generation, usage clustering (k-means), and depletion prediction algorithms.

## 🔗 Main API Routes

### Real-Time & Sensor
- `WS  /api/v1/ws/sensor/{device_id}` - Live WebSocket stream for real-time weight updates.
- `POST /api/v1/sensor/readings` - IoT ingestion endpoint.

### Dashboard & Analytics
- `GET /api/v1/dashboard/summary` - Today's usage, 30-day average, and depletion estimate.
- `GET /api/v1/reports/*` - Gas usage reports, depletion prediction models, and clustering.

### Auth & Users
- `/api/v1/users/*` - Consumer registration, login, and profile management.
- `/api/v1/distributors/*` - Distributor registration, login, and profile.
- `/api/v1/admin/*` - Admin portal login and management.

### Operations
- `/api/v1/refill/*` - Refill requests and approvals.
- `/api/v1/complaints/*` - Complaint creation and review.

## 🛠 Setup & Installation

### Requirements
- Python 3.13+
- PostgreSQL
- A `.env` file (see `.env.example` for required keys like `SQLALCHEMY_DATABASE_URL` and `JWT_SECRET_KEY`).

### Local Development

1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Run the server:
   ```bash
   uvicorn main:app --reload
   ```
3. Open `http://localhost:8000/docs` for the interactive Swagger API documentation.

### Docker

You can easily spin up the backend and a local PostgreSQL instance using Docker:
```bash
docker-compose up -d --build
```

## 📂 Key Project Files
- `main.py` - Application factory, CORS, and router registration.
- `database.py` - SQLAlchemy async engine configured for strict connection pooling (pool_size=3).
- `services/state_manager.py` - In-memory RAM cache for device state.
- `services/ws_manager.py` - Active WebSocket connection tracker and broadcaster.

## 📄 License
See [LICENSE](LICENSE).
