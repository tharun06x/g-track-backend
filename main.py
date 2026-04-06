from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import close_db, init_db
from routers import dashboard, refill, report, sensor, settings, users, distributor, admin, complaints


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield
    await close_db()


app = FastAPI(lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_origin_regex=r"https://.*(onrender\.com|vercel\.app|netlify\.app)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(dashboard.router)
app.include_router(distributor.router)
app.include_router(admin.router)
app.include_router(complaints.router)
app.include_router(refill.router)
app.include_router(report.router)
app.include_router(sensor.router)
app.include_router(settings.router)
app.include_router(users.router)

api_version = 1.0

@app.get("/", include_in_schema=False, name="home")
def root():
    return {"Status": f"G-Track {api_version} API Running"}

@app.get("/health")
def health():
    return {
        "status": "Running",
        "version": api_version,
    }





