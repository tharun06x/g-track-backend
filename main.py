from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import close_db, init_db
from routers import dashboard, refill, settings, users


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield
    await close_db()


app = FastAPI(lifespan=lifespan)
app.include_router(dashboard.router)
app.include_router(refill.router)
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





