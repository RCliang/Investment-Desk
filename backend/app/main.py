from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="InvestLens API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routers import chain, data, report, plan
app.include_router(chain.router)
app.include_router(data.router)
app.include_router(report.router)
app.include_router(plan.router)


@app.on_event("startup")
async def startup():
    from app.db import async_engine, Base
    from app.models.models import ChainAnalysis, DataCache, Report, InvestmentPlan
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
