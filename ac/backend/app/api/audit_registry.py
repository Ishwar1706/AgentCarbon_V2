from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import current_user
from app.models.access_control import User
from app.models.verification import AuditRegistryRecord
from app.models.workflows import MonthlyRequest
from app.services import periods, registry
from app.services.company_access import Ctx, claim_for_period, company_context

router = APIRouter(tags=["audit"])
reader = company_context("AUDITOR", "PLANT_OPERATOR", require_dataset=True)


def _view(r: AuditRegistryRecord) -> dict:
    period = periods.period_from_claim(r.claim_id) or ""
    return {"claim_id": r.claim_id, "period": period, "label": periods.label(period) if period else "",
            "block_number": r.block_number, "run_id": r.run_id, "decision_id": r.decision_id,
            "recommendation": r.recommendation, "auditor_decision": r.auditor_decision,
            "evidence_bundle_hash": r.evidence_bundle_hash, "trust_snapshot_hash": r.trust_snapshot_hash,
            "report_hash": r.report_hash, "previous_hash": r.previous_hash, "record_hash": r.record_hash,
            "registry_mode": r.registry_mode, "registered_at": r.registered_at.isoformat()}


@router.post("/audit/register/{period}", status_code=201)
def register(period: str, ctx: Ctx = Depends(company_context("AUDITOR", require_dataset=True)),
             db: Session = Depends(get_db)):
    claim = claim_for_period(ctx.company_id, period)
    if claim is None:
        raise HTTPException(404, f"No data available for {periods.label(periods.valid(period))}.")
    claim_id = claim["claim_id"]
    if db.scalar(select(AuditRegistryRecord).where(AuditRegistryRecord.claim_id == claim_id)):
        raise HTTPException(409, "This month is already in the registry; entries are immutable.")
    request = db.scalar(select(MonthlyRequest).where(MonthlyRequest.claim_id == claim_id))
    if request is None or request.status == "DRAFT":
        raise HTTPException(409, "The operator has not submitted this month yet.")
    run = registry.latest_completed_run(db, ctx.company_id, claim_id)
    decision = registry.latest_decision(db, ctx.company_id, claim_id)
    if not run or not decision:
        raise HTTPException(409, "A completed verification run and an auditor decision are required first.")
    return _view(registry.register(db, run, decision, ctx.user))


@router.get("/audit/records")
def records(ctx: Ctx = Depends(reader), db: Session = Depends(get_db)):
    return [_view(r) for r in db.scalars(select(AuditRegistryRecord).where(
        AuditRegistryRecord.company_id == ctx.company_id).order_by(AuditRegistryRecord.block_number))]


@router.get("/audit/records/{period}/verify")
def verify(period: str, ctx: Ctx = Depends(reader), db: Session = Depends(get_db)):
    claim_id = periods.claim_id(ctx.company_id, periods.valid(period))
    record = db.scalar(select(AuditRegistryRecord).where(
        AuditRegistryRecord.claim_id == claim_id, AuditRegistryRecord.company_id == ctx.company_id))
    if not record:
        raise HTTPException(404, "This month is not in the registry.")
    return registry.verify_record(db, record)


@router.get("/audit/chain/verify")
def verify_chain(_: User = Depends(current_user), db: Session = Depends(get_db)):
    chain = registry.verify_chain(db)
    return {"block_count": chain["block_count"], "valid": chain["valid"]}


@router.get("/reports/{period}")
def report(period: str, format: str = Query(default="html", pattern="^(html|json)$"),
           ctx: Ctx = Depends(company_context("AUDITOR", require_dataset=True)), db: Session = Depends(get_db)):
    claim = claim_for_period(ctx.company_id, period)
    if claim is None:
        raise HTTPException(404, f"No data available for {periods.label(periods.valid(period))}.")
    run = registry.latest_completed_run(db, ctx.company_id, claim["claim_id"])
    if not run:
        raise HTTPException(404, "No completed verification run exists for this month yet.")
    data = registry.build_report(db, run, registry.latest_decision(db, ctx.company_id, claim["claim_id"]))
    if format == "json":
        return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="{claim["claim_id"]}.json"'})
    return HTMLResponse(registry.report_to_html(data))
