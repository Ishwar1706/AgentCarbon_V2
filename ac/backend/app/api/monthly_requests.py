"""The operator's monthly update: form (declared figures + expected credits), evidence checklist, submit."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.access_control import AuditorDecision, EvidenceDocument
from app.models.workflows import InfoRequest, MonthlyRequest
from app.services import checklist as checklist_service
from app.services import credits, periods
from app.services.company_access import Ctx, claim_for_period, company_context
from app.services.documents import document_view
from app.services.info_requests import info_request_view

router = APIRouter(prefix="/requests", tags=["monthly-requests"])
operator = company_context("PLANT_OPERATOR", require_dataset=True)
viewer = company_context("PLANT_OPERATOR", "AUDITOR", require_dataset=True)
EDITABLE = {"DRAFT", "INFO_REQUESTED"}


class FormBody(BaseModel):
    expected_credits_tco2e: float = Field(ge=0, le=1_000_000)
    declared_electricity_kwh: float = Field(gt=0, le=1e9)
    declared_production_units: int = Field(ge=0, le=10_000_000)
    declared_natural_gas_scm: float = Field(ge=0, le=1e9)
    declared_diesel_litres: float = Field(ge=0, le=1e9)
    notes: str | None = Field(default=None, max_length=2000)


def _form(req: MonthlyRequest | None) -> dict | None:
    if req is None:
        return None
    return {"request_id": req.request_id, "status": req.status, "expected_credits_tco2e": req.expected_credits_tco2e,
            "declared_electricity_kwh": req.declared_electricity_kwh,
            "declared_production_units": req.declared_production_units,
            "declared_natural_gas_scm": req.declared_natural_gas_scm,
            "declared_diesel_litres": req.declared_diesel_litres, "notes": req.notes or "",
            "submitted_at": req.submitted_at.isoformat() if req.submitted_at else None,
            "updated_at": req.updated_at.isoformat()}


def _get(db: Session, company_id: str, period: str) -> MonthlyRequest | None:
    return db.scalar(select(MonthlyRequest).where(MonthlyRequest.company_id == company_id,
                                                  MonthlyRequest.period == period))


@router.get("/{period}")
def get_request(period: str, ctx: Ctx = Depends(viewer), db: Session = Depends(get_db)):
    periods.valid(period)
    claim = claim_for_period(ctx.company_id, period)
    if claim is None:
        return {"available": False, "period": period, "label": periods.label(period),
                "message": f"No data available for {periods.label(period)}."}
    claim_id = claim["claim_id"]
    req = _get(db, ctx.company_id, period)
    declared = (credits.dataset_values(claim) if req is None else
                {"electricity_kwh": req.declared_electricity_kwh, "production_units": req.declared_production_units,
                 "natural_gas_scm": req.declared_natural_gas_scm, "diesel_litres": req.declared_diesel_litres})
    expected = credits.prefill(ctx.company_id, claim)["expected_credits_tco2e"] if req is None else req.expected_credits_tco2e
    docs = db.scalars(select(EvidenceDocument).where(
        EvidenceDocument.company_id == ctx.company_id, EvidenceDocument.claim_id == claim_id
    ).order_by(EvidenceDocument.uploaded_at.desc())).all()
    infos = db.scalars(select(InfoRequest).where(InfoRequest.company_id == ctx.company_id, InfoRequest.claim_id == claim_id)
                       .order_by(InfoRequest.created_at.desc())).all()
    decision = db.scalar(select(AuditorDecision).where(
        AuditorDecision.company_id == ctx.company_id, AuditorDecision.claim_id == claim_id
    ).order_by(AuditorDecision.decided_at.desc(), AuditorDecision.id.desc()))
    return {
        "available": True, "period": period, "label": periods.label(period), "claim_id": claim_id,
        "request": _form(req), "editable": req is None or req.status in EDITABLE,
        "prefill": credits.prefill(ctx.company_id, claim),
        "evaluation": credits.evaluate(ctx.company_id, claim, declared, float(expected)),
        "plant_records": {**credits.dataset_values(claim),
                          "verified_electricity_kwh": round(float(claim["verified_electricity_kwh"]), 2)},
        "checklist": checklist_service.checklist(db, ctx.company_id, claim_id),
        "documents": [document_view(d) for d in docs],
        "info_requests": [info_request_view(db, i) for i in infos],
        "decision": None if decision is None else {"decision": decision.decision, "comments": decision.comments,
                                                  "decided_at": decision.decided_at.isoformat()},
    }


@router.put("/{period}")
def save_request(period: str, body: FormBody, ctx: Ctx = Depends(operator), db: Session = Depends(get_db)):
    claim = claim_for_period(ctx.company_id, period)
    if claim is None:
        raise HTTPException(404, f"No data available for {periods.label(periods.valid(period))}.")
    req = _get(db, ctx.company_id, period)
    if req is not None and req.status not in EDITABLE:
        raise HTTPException(409, f"This request is {req.status} and can no longer be edited.")
    if req is None:
        req = MonthlyRequest(request_id=f"MR-{uuid.uuid4().hex[:10].upper()}", company_id=ctx.company_id,
                             period=period, claim_id=claim["claim_id"], status="DRAFT",
                             created_by_user_id=ctx.user.id)
        db.add(req)
    req.expected_credits_tco2e = body.expected_credits_tco2e
    req.declared_electricity_kwh = body.declared_electricity_kwh
    req.declared_production_units = body.declared_production_units
    req.declared_natural_gas_scm = body.declared_natural_gas_scm
    req.declared_diesel_litres = body.declared_diesel_litres
    req.notes = body.notes
    db.commit()
    return _form(req)


@router.post("/{period}/submit")
def submit_request(period: str, ctx: Ctx = Depends(operator), db: Session = Depends(get_db)):
    req = _get(db, ctx.company_id, period)
    if req is None:
        raise HTTPException(409, "Save the form first, then submit.")
    if req.status not in EDITABLE:
        raise HTTPException(409, f"This request is already {req.status}.")
    req.status, req.submitted_at = "SUBMITTED", datetime.now(timezone.utc)
    db.commit()
    return _form(req)
