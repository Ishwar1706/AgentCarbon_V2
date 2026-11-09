"""Year calendar for the month picker: which months have data and where each request stands."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.access_control import AuditorDecision
from app.models.verification import VerificationRun
from app.models.workflows import InfoRequest, MonthlyRequest
from app.services import periods, sensor_rollup
from app.services.company_access import Ctx, company_context
from app.services.company_data import company_claims

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("")
def calendar_for_year(year: int = Query(default=periods.DATASET_YEAR, ge=2000, le=2100),
                      ctx: Ctx = Depends(company_context("PLANT_OPERATOR", "AUDITOR")),
                      db: Session = Depends(get_db)):
    claim_periods = set()
    if ctx.company.has_dataset:
        claim_periods = {periods.from_month_number(int(m)) for m in company_claims(ctx.company_id)["month_number"]}
    sensor_periods = set(sensor_rollup.period_list(db, ctx.company_id))
    requests = {r.period: r for r in db.scalars(select(MonthlyRequest).where(MonthlyRequest.company_id == ctx.company_id))}
    open_info: dict[str, int] = {}
    for i in db.scalars(select(InfoRequest).where(InfoRequest.company_id == ctx.company_id, InfoRequest.status == "OPEN")):
        open_info[i.period] = open_info.get(i.period, 0) + 1
    months = []
    for m in range(1, 13):
        p = f"{year}-{m:02d}"
        req = requests.get(p)
        run = db.scalar(select(VerificationRun).where(
            VerificationRun.company_id == ctx.company_id, VerificationRun.period == p,
            VerificationRun.status == "COMPLETED").order_by(VerificationRun.created_at.desc()))
        months.append({
            "period": p, "label": periods.label(p), "claim_data": p in claim_periods, "sensor_data": p in sensor_periods,
            "request_status": req.status if req else ("NOT_STARTED" if p in claim_periods else None),
            "recommendation": run.final_recommendation if run else None,
            "open_info_requests": open_info.get(p, 0),
        })
    return {"year": year, "months": months, "dataset_year": periods.DATASET_YEAR}
