import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from datetime import datetime, timezone

from app.core.database import get_db
from app.models.access_control import AuditorDecision
from app.models.workflows import InfoRequest, MonthlyRequest
from app.services import periods
from app.services.company_access import Ctx, claim_for_period, company_context
from app.services.registry import latest_completed_run

router = APIRouter(prefix="/auditor", tags=["auditor"])
auditor = company_context("AUDITOR", require_dataset=True)
STATUS_MAP = {"APPROVE": "APPROVED", "REJECT": "REJECTED", "ESCALATE": "ESCALATED"}


class DecisionBody(BaseModel):
    period: str
    decision: str
    comments: str = Field(min_length=5, max_length=2000)


def _view(d: AuditorDecision) -> dict:
    return {"decision_id": d.decision_id, "claim_id": d.claim_id, "decision": d.decision, "comments": d.comments,
            "verification_run_id": d.verification_run_id, "decided_at": d.decided_at.isoformat()}


@router.post("/decisions", status_code=201)
def decide(body: DecisionBody, ctx: Ctx = Depends(auditor), db: Session = Depends(get_db)):
    periods.valid(body.period)
    claim = claim_for_period(ctx.company_id, body.period)
    if claim is None:
        raise HTTPException(404, f"No data available for {periods.label(body.period)}.")
    if body.decision not in STATUS_MAP:
        raise HTTPException(400, f"decision must be one of {sorted(STATUS_MAP)}")
    request = db.scalar(select(MonthlyRequest).where(MonthlyRequest.claim_id == claim["claim_id"]))
    if request is None or request.status == "DRAFT":
        raise HTTPException(409, "The operator has not submitted this month yet.")
    run = latest_completed_run(db, ctx.company_id, claim["claim_id"])
    if run is None:
        raise HTTPException(409, "Run a verification for this month before recording a decision.")
    decision = AuditorDecision(decision_id=f"DEC-{uuid.uuid4().hex[:12].upper()}", company_id=ctx.company_id,
                               claim_id=claim["claim_id"], verification_run_id=run.run_id, decision=body.decision,
                               comments=body.comments, auditor_user_id=ctx.user.id)
    db.add(decision)
    request.status = STATUS_MAP[body.decision]
    if body.decision in {"APPROVE", "REJECT"}:  # a final decision closes any still-open questions
        for info in db.scalars(select(InfoRequest).where(InfoRequest.claim_id == claim["claim_id"],
                                                         InfoRequest.status.in_(["OPEN", "RESPONDED"]))):
            info.status, info.closed_at = "CLOSED", datetime.now(timezone.utc)
            info.close_note = f"Closed by the auditor's {body.decision.lower()} decision."
    db.commit()
    return _view(decision)


@router.get("/decisions")
def decisions(period: str = Query(...), ctx: Ctx = Depends(company_context("AUDITOR")), db: Session = Depends(get_db)):
    claim_id = periods.claim_id(ctx.company_id, periods.valid(period))
    return [_view(d) for d in db.scalars(select(AuditorDecision).where(
        AuditorDecision.company_id == ctx.company_id, AuditorDecision.claim_id == claim_id
    ).order_by(AuditorDecision.decided_at.desc(), AuditorDecision.id.desc()))]
