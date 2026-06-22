from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.models import InvestmentPlan

router = APIRouter(prefix="/api/plan", tags=["plan"])


class PlanCreate(BaseModel):
    stock_code: str
    stock_name: str
    direction: str
    position_ratio: float
    target_price: float | None = None
    stop_loss_price: float | None = None
    reason: str | None = None


class PlanUpdate(BaseModel):
    position_ratio: float | None = None
    target_price: float | None = None
    stop_loss_price: float | None = None
    status: str | None = None
    reason: str | None = None


@router.post("/create")
async def create_plan(req: PlanCreate, db: Session = Depends(get_db)):
    if req.direction not in ("buy", "sell"):
        raise HTTPException(400, "direction must be 'buy' or 'sell'")
    if not 0 < req.position_ratio <= 100:
        raise HTTPException(400, "position_ratio must be between 0 and 100")
    plan = InvestmentPlan(**req.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return _plan_to_dict(plan)


@router.get("/list")
async def list_plans(db: Session = Depends(get_db)):
    plans = db.query(InvestmentPlan).order_by(InvestmentPlan.created_at.desc()).all()
    return [_plan_to_dict(p) for p in plans]


@router.put("/{plan_id}")
async def update_plan(plan_id: int, req: PlanUpdate, db: Session = Depends(get_db)):
    plan = db.query(InvestmentPlan).filter(InvestmentPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, "Plan not found")
    updates = req.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] not in ("pending", "executing", "closed", "stopped"):
        raise HTTPException(400, f"Invalid status: {updates['status']}")
    for key, val in updates.items():
        setattr(plan, key, val)
    plan.updated_at = datetime.now()
    db.commit()
    db.refresh(plan)
    return _plan_to_dict(plan)


@router.delete("/{plan_id}")
async def delete_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.query(InvestmentPlan).filter(InvestmentPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, "Plan not found")
    db.delete(plan)
    db.commit()
    return {"ok": True}


def _plan_to_dict(plan: InvestmentPlan) -> dict:
    return {
        "id": plan.id, "stock_code": plan.stock_code, "stock_name": plan.stock_name,
        "direction": plan.direction, "position_ratio": plan.position_ratio,
        "target_price": plan.target_price, "stop_loss_price": plan.stop_loss_price,
        "reason": plan.reason, "status": plan.status,
        "created_at": plan.created_at.isoformat(), "updated_at": plan.updated_at.isoformat(),
    }
