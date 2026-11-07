import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.access_control import AuditorDecision
from app.models.workflows import ClaimWorkflow
from app.services.company_access import ALL_VIEWERS, Ctx, claim_or_404, company_context
from app.services.registry import latest_completed_run

router = APIRouter(prefix="/auditor", tags=["auditor"])
STATUS_MAP = {"APPROVE": "APPROVED", "REJECT": "REJECTED",
              "REQUEST_MORE_EVIDENCE": "MORE_EVIDENCE_REQUESTED", "ESCALATE": "ESCALATED"}


class DecisionBody(BaseModel):
    claim_id: str
    decision: str
    comments: str = Field(min_length=5, max_length=2000)


def _view(d: AuditorDecision) -> dict:
    return {"decision_id": d.decision_id, "claim_id": d.claim_id, "decision": d.decision, "comments": d.comments,
            "verification_run_id": d.verification_run_id, "decided_at": d.decided_at.isoformat()}


@router.post("/decisions", status_code=201)
def decide(body: DecisionBody, ctx: Ctx = Depends(company_context("AUDITOR", require_dataset=True)),
           db: Session = Depends(get_db)):
    claim_or_404(ctx.company_id, body.claim_id)
    if body.decision not in STATUS_MAP:
        raise HTTPException(400, f"decision must be one of {sorted(STATUS_MAP)}")
    run = latest_completed_run(db, ctx.company_id, body.claim_id)
    if run is None:
        raise HTTPException(409, "Run a verification for this claim before recording a decision.")
    decision = AuditorDecision(decision_id=f"DEC-{uuid.uuid4().hex[:12].upper()}", company_id=ctx.company_id,
                               claim_id=body.claim_id, verification_run_id=run.run_id, decision=body.decision,
                               comments=body.comments, auditor_user_id=ctx.user.id)
    db.add(decision)
    flow = db.get(ClaimWorkflow, body.claim_id)
    if flow:
        flow.status = STATUS_MAP[body.decision]
    else:
        db.add(ClaimWorkflow(claim_id=body.claim_id, company_id=ctx.company_id, status=STATUS_MAP[body.decision]))
    db.commit()
    return _view(decision)


@router.get("/decisions")
def decisions(claim_id: str = Query(...), ctx: Ctx = Depends(company_context(*ALL_VIEWERS)),
              db: Session = Depends(get_db)):
    return [_view(d) for d in db.scalars(select(AuditorDecision).where(
        AuditorDecision.company_id == ctx.company_id, AuditorDecision.claim_id == claim_id
    ).order_by(AuditorDecision.decided_at.desc(), AuditorDecision.id.desc()))]
