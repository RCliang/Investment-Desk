import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.models import Report, ChainAnalysis
from app.services.llm_service import generate_report_stream, analyze_chain
from sse_starlette.sse import EventSourceResponse
from datetime import datetime

router = APIRouter(prefix="/api/report", tags=["report"])


class GenerateRequest(BaseModel):
    industry: str
    chain_analysis_id: int | None = None


@router.post("/generate")
async def generate(req: GenerateRequest, db: Session = Depends(get_db)):
    chain_data = ""
    if req.chain_analysis_id:
        record = db.query(ChainAnalysis).filter(ChainAnalysis.id == req.chain_analysis_id).first()
        if record:
            chain_data = record.result_json

    if not chain_data:
        chain_result = analyze_chain(req.industry)
        chain_data = json.dumps(chain_result, ensure_ascii=False, default=str)

    async def event_stream():
        full_content = ""
        for chunk in generate_report_stream(req.industry, chain_data):
            full_content += chunk
            yield {"data": chunk}

        report = Report(industry=req.industry, content_md=full_content)
        db.add(report)
        db.commit()

    return EventSourceResponse(event_stream())


@router.get("/list")
async def list_reports(db: Session = Depends(get_db)):
    records = db.query(Report).order_by(Report.created_at.desc()).limit(20).all()
    return [{"id": r.id, "industry": r.industry, "created_at": r.created_at.isoformat()} for r in records]


@router.get("/{report_id}")
async def get_report(report_id: int, db: Session = Depends(get_db)):
    record = db.query(Report).filter(Report.id == report_id).first()
    if not record:
        raise HTTPException(404, "Report not found")
    return {"id": record.id, "industry": record.industry, "content": record.content_md, "created_at": record.created_at.isoformat()}
