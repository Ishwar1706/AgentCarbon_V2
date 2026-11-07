from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.workflows import ClaimWorkflow
from app.services.company_access import Ctx, claim_or_404, company_context

router = APIRouter(prefix="/claims", tags=["claims"])


@router.post("/{claim_id}/submit")
def submit_claim(claim_id: str, ctx: Ctx = Depends(company_context("PLANT_OPERATOR", "ADMIN", require_dataset=True)),
                 db: Session = Depends(get_db)):
    claim_or_404(ctx.company_id, claim_id)
    flow = db.get(ClaimWorkflow, claim_id)
    if flow and flow.status != "MORE_EVIDENCE_REQUESTED":
        raise HTTPException(409, f"Claim is already {flow.status}.")
    if flow:
        flow.status, flow.submitted_at = "SUBMITTED", datetime.now(timezone.utc)
    else:
        db.add(ClaimWorkflow(claim_id=claim_id, company_id=ctx.company_id, status="SUBMITTED",
                             submitted_by_user_id=ctx.user.id))
    db.commit()
    return {"claim_id": claim_id, "status": "SUBMITTED"}
