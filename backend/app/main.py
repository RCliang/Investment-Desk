from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS

app = FastAPI(title="InvestLens API", version="0.1.0")

# Parse CORS origins from environment variable
# If CORS_ORIGINS is empty or not set, allow all origins (development)
# Otherwise, parse comma-separated list
if CORS_ORIGINS:
    allowed_origins = [origin.strip() for origin in CORS_ORIGINS.split(",")]
else:
    # Allow all origins if not configured (for development)
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routers import chain, data, report, plan, chainkb, refresh, research
app.include_router(chain.router)
app.include_router(data.router)
app.include_router(report.router)
app.include_router(plan.router)
app.include_router(chainkb.router)
app.include_router(refresh.router)
app.include_router(research.router)


@app.on_event("startup")
async def startup():
    from app.db import async_engine, Base
    from app.models.models import ChainAnalysis, DataCache, Report, InvestmentPlan
    # v1 chain knowledge base tables (must be imported so create_all sees them)
    from app.models import chain_models  # noqa: F401
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.on_event("startup")
async def startup_scheduler():
    """Start APScheduler after tables exist (assumes startup() ran first)."""
    from app.services.scheduler import start_scheduler
    start_scheduler()


@app.on_event("shutdown")
async def shutdown_scheduler():
    from app.services.scheduler import shutdown_scheduler
    shutdown_scheduler()
