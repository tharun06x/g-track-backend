# G-Track Backend

FastAPI backend for G-Track, a gas cylinder tracking system with user, distributor, admin, refill, complaint, dashboard, sensor, and reporting APIs.

## What It Includes

- JWT-based authentication
- PostgreSQL-backed async database access
- Sensor reading ingestion
- Dashboard and reporting endpoints
- Refill and complaint workflows
- Distributor and admin management
- ML-backed depletion prediction, feature generation, and clustering

## Auth Routes

- `/api/v1/users/register` - consumer registration
- `/api/v1/users/login` - consumer login
- `/api/v1/users/me` - current consumer profile
- `/api/v1/distributors/register` - distributor registration
- `/api/v1/distributors/login` - distributor login
- `/api/v1/distributors/me` - current distributor profile
- `/api/v1/admin/login` - admin login
- `/api/v1/admin/register` - admin registration

## Model Scope

- `users`, `distributor`, `admin`
- `refill_request`, `complaint`, `alert_log`, `sensor_unit`
- `synthetic_device`, `synthetic_sensor_reading`, `synthetic_feature_row`
- `device_cluster_assignment`, `clustering_model_metadata`

## Requirements

- Python 3.13+
- PostgreSQL
- A `.env` file with `SQLALCHEMY_DATABASE_URL` and JWT settings

## Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn main:app --reload
```

Open `http://localhost:8000/docs` for the interactive API docs.

## Docker

```bash
docker-compose up -d
```

## Main Routes

- `/api/v1/users` - user registration, login, profile, CRUD
- `/api/v1/distributors` - distributor registration, login, profile, CRUD
- `/api/v1/admin` - admin login, registration, trouble requests, distributor requests
- `/api/v1/sensor` - sensor readings
- `/api/v1/refill` - refill requests and approvals
- `/api/v1/complaints` - complaint creation and review
- `/api/v1/dashboard` - dashboard summary
- `/api/v1/reports` - gas usage, depletion prediction, clustering, device summaries
- `/api/v1/settings` - user settings

## Key Files

- [main.py](main.py)
- [database.py](database.py)
- [auth.py](auth.py)
- [routers/](routers)
- [docs/](docs)

## Notes

- The app initializes the database on startup and closes it on shutdown.
- CORS is configured for common local frontend ports and deployed frontend domains.

## Roadmap

### Phase 1

- Add Alembic migrations for schema changes and repeatable database updates.
- Expand authorization routes and role-based access control for user, distributor, and admin flows.

### Phase 2

- Refine the model structure as the schema stabilizes.
- Clean up shared schemas, relationships, and table naming where needed.

### Phase 3

- Introduce Redis for caching, background jobs, or rate limiting if the workload needs it.
- Add any supporting infrastructure and config required for production use.

## License

See [LICENSE](LICENSE).
