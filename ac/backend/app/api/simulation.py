from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.company_access import ALL_VIEWERS, Ctx, company_context
from app.services.live_engine import engine

router = APIRouter(prefix="/simulation", tags=["simulation"])
controller = company_context("PLANT_OPERATOR")


class StartBody(BaseModel):
    interval_seconds: float = Field(default=2.0, ge=0.5, le=60)


class AdvanceBody(BaseModel):
    steps: int = Field(default=96, ge=1, le=2880)  # 96 steps = one simulated day


class FaultBody(BaseModel):
    sensor_id: str
    kind: str = "STUCK"
    hours: float = Field(default=24, ge=0.25, le=720)
    magnitude: float = Field(default=0, ge=0, le=5000)


def _guard(fn):
    try:
        return fn()
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.get("/status")
def status(ctx: Ctx = Depends(company_context(*ALL_VIEWERS)), db: Session = Depends(get_db)):
    return _guard(lambda: engine.status(db, ctx.company_id))


@router.post("/start")
def start(body: StartBody, ctx: Ctx = Depends(controller), db: Session = Depends(get_db)):
    _guard(lambda: engine.start(db, ctx.company_id, body.interval_seconds))
    return engine.status(db, ctx.company_id)


@router.post("/stop")
def stop(ctx: Ctx = Depends(controller), db: Session = Depends(get_db)):
    engine.stop(ctx.company_id)
    return engine.status(db, ctx.company_id)


@router.post("/advance")
def advance(body: AdvanceBody, ctx: Ctx = Depends(controller), db: Session = Depends(get_db)):
    return _guard(lambda: engine.advance(db, ctx.company_id, body.steps))


@router.post("/complete-month")
def complete_month(ctx: Ctx = Depends(controller), db: Session = Depends(get_db)):
    return _guard(lambda: engine.complete_month(db, ctx.company_id))


@router.post("/fault")
def inject(body: FaultBody, ctx: Ctx = Depends(controller), db: Session = Depends(get_db)):
    _guard(lambda: engine.inject_fault(db, ctx.company_id, body.sensor_id, body.kind.upper(), body.hours, body.magnitude))
    return engine.status(db, ctx.company_id)


@router.delete("/fault/{sensor_id}")
def clear(sensor_id: str, ctx: Ctx = Depends(controller), db: Session = Depends(get_db)):
    engine.clear_fault(db, ctx.company_id, sensor_id)
    return engine.status(db, ctx.company_id)
