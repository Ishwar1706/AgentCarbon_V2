import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.orchestrator import start_run
from app.core.config import settings
from app.core.database import get_db
from app.core.security import current_user
from app.models.access_control import User
from app.models.verification import VerificationRun
from app.services.company_access import Ctx, claim_or_404, company_context

router = APIRouter(prefix="/verifications", tags=["verifications"])
runner = company_context("AUDITOR", "PLANT_OPERATOR", "ADMIN", require_dataset=True)
reader = company_context("AUDITOR", "PLANT_OPERATOR", "REGULATOR_VIEWER", "ADMIN", require_dataset=True)


class RunBody(BaseModel):
    claim_id: str
    mode: str = "AUTO"  # AUTO | AGENTIC | DETERMINISTIC


def _brief(r: VerificationRun) -> dict:
    return {"run_id": r.run_id, "claim_id": r.claim_id, "status": r.status, "requested_mode": r.requested_mode,
            "execution_mode": r.execution_mode, "final_recommendation": r.final_recommendation,
            "confidence_score": r.confidence_score, "llm_calls": r.llm_call_count, "llm_tokens": r.llm_total_tokens,
            "created_at": r.created_at.isoformat(), "completed_at": r.completed_at.isoformat() if r.completed_at else None}


@router.get("/status")
def system_status(_: User = Depends(current_user)):
    return {"groq_configured": settings.groq_configured, "model": settings.groq_model,
            "default_mode": "AGENTIC" if settings.groq_configured else "DETERMINISTIC",
            "debate_rounds": settings.agent_debate_rounds}


@router.post("/run", status_code=202)
def run(body: RunBody, ctx: Ctx = Depends(runner), db: Session = Depends(get_db)):
    claim = claim_or_404(ctx.company_id, body.claim_id)
    mode = body.mode.upper()
    if mode not in {"AUTO", "AGENTIC", "DETERMINISTIC"}:
        raise HTTPException(400, "mode must be AUTO, AGENTIC or DETERMINISTIC")
    if ctx.user.role == "PLANT_OPERATOR":
        mode = "DETERMINISTIC"  # operators may pre-check; only auditors spend LLM budget
    if mode == "AGENTIC" and not settings.groq_configured:
        raise HTTPException(400, "GROQ_API_KEY is not configured on the server.")
    busy = db.scalar(select(VerificationRun).where(
        VerificationRun.claim_id == body.claim_id, VerificationRun.status.in_(["QUEUED", "RUNNING"])))
    if busy:
        raise HTTPException(409, f"A run is already in progress for this claim ({busy.run_id}).")
    record = VerificationRun(run_id=f"RUN-{uuid.uuid4().hex[:12].upper()}", company_id=ctx.company_id,
                             claim_id=body.claim_id, month_number=int(claim["month_number"]),
                             requested_mode=mode, created_by_user_id=ctx.user.id)
    db.add(record)
    db.commit()
    start_run(record.run_id)
    return _brief(record)


@router.get("/runs")
def runs(claim_id: str | None = Query(default=None), ctx: Ctx = Depends(reader), db: Session = Depends(get_db)):
    query = select(VerificationRun).where(VerificationRun.company_id == ctx.company_id)
    if claim_id:
        query = query.where(VerificationRun.claim_id == claim_id)
    return [_brief(r) for r in db.scalars(query.order_by(VerificationRun.created_at.desc()).limit(50))]


@router.get("/runs/{run_id}")
def run_detail(run_id: str, ctx: Ctx = Depends(reader), db: Session = Depends(get_db)):
    record = db.get(VerificationRun, run_id)
    if record is None or record.company_id != ctx.company_id:
        raise HTTPException(404, "Run not found for this company.")
    data = _brief(record)
    data.update(progress=json.loads(record.progress_json or "[]"), error=record.error,
                result=json.loads(record.result_json) if record.result_json else None)
    return data
