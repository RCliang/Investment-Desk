from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.models import ChainAnalysis
from app.services.llm_service import analyze_chain
from datetime import datetime, timedelta
import json

router = APIRouter(prefix="/api/chain", tags=["chain"])


class AnalyzeRequest(BaseModel):
    industry: str


@router.post("/analyze")
async def analyze(req: AnalyzeRequest, db: Session = Depends(get_db)):
    cutoff = datetime.now() - timedelta(days=7)
    cached = db.query(ChainAnalysis).filter(
        ChainAnalysis.industry == req.industry,
        ChainAnalysis.created_at >= cutoff,
    ).order_by(ChainAnalysis.created_at.desc()).first()

    if cached:
        return json.loads(cached.result_json)

    result = analyze_chain(req.industry)

    record = ChainAnalysis(
        industry=req.industry,
        result_json=json.dumps(result, ensure_ascii=False),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return result


@router.get("/history")
async def history(db: Session = Depends(get_db)):
    records = db.query(ChainAnalysis).order_by(ChainAnalysis.created_at.desc()).limit(20).all()
    return [{"id": r.id, "industry": r.industry, "created_at": r.created_at.isoformat()} for r in records]


@router.get("/{analysis_id}")
async def get_analysis(analysis_id: int, db: Session = Depends(get_db)):
    record = db.query(ChainAnalysis).filter(ChainAnalysis.id == analysis_id).first()
    if not record:
        raise HTTPException(404, "Analysis not found")
    return {"id": record.id, "industry": record.industry, "result": json.loads(record.result_json), "created_at": record.created_at.isoformat()}
