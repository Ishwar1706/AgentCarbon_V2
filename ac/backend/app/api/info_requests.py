"""Auditor -> operator requests for missing documents / information, and the operator's replies."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.workflows import InfoRequest, MonthlyRequest
from app.services import periods
from app.services.checklist import DOCUMENT_TYPES
from app.services.company_access import Ctx, claim_for_period, company_context
from app.services.info_requests import info_request_view

router = APIRouter(prefix="/info-requests", tags=["info-requests"])
auditor = company_context("AUDITOR", require_dataset=True)
operator = company_context("PLANT_OPERATOR", require_dataset=True)
both = company_context("PLANT_OPERATOR", "AUDITOR", require_dataset=True)


class Item(BaseModel):
    kind: str  # DOCUMENT | INFORMATION
    doc_type: str = ""
    label: str = Field(min_length=3, max_length=300)


class CreateBody(BaseModel):
    period: str
    title: str = Field(min_length=3, max_length=200)
    message: str = Field(default="", max_length=2000)
    items: list[Item] = Field(min_length=1, max_length=12)


class ReplyBody(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)
    note: str | None = Field(default=None, max_length=2000)


class CloseBody(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


@router.post("", status_code=201)
def create(body: CreateBody, ctx: Ctx = Depends(auditor), db: Session = Depends(get_db)):
    periods.valid(body.period)
    claim = claim_for_period(ctx.company_id, body.period)
    if claim is None:
        raise HTTPException(404, f"No data available for {periods.label(body.period)}.")
    request = db.scalar(select(MonthlyRequest).where(MonthlyRequest.claim_id == claim["claim_id"]))
    if request is None or request.status == "DRAFT":
        raise HTTPException(409, "The operator has not submitted this month yet.")
    if request.status in {"APPROVED", "REJECTED"}:
        raise HTTPException(409, f"This month is already {request.status}.")
    items = []
    for n, item in enumerate(body.items, 1):
        if item.kind not in {"DOCUMENT", "INFORMATION"}:
            raise HTTPException(400, "item kind must be DOCUMENT or INFORMATION")
        if item.kind == "DOCUMENT" and item.doc_type not in DOCUMENT_TYPES:
            raise HTTPException(400, f"doc_type must be one of {sorted(DOCUMENT_TYPES)}")
        items.append({"item_id": f"i{n}", "kind": item.kind, "doc_type": item.doc_type if item.kind == "DOCUMENT" else "",
                      "label": item.label})
    info = InfoRequest(request_id=f"IR-{uuid.uuid4().hex[:10].upper()}", company_id=ctx.company_id,
                       claim_id=claim["claim_id"], period=body.period, created_by_user_id=ctx.user.id,
                       title=body.title, message=body.message, items_json=json.dumps(items))
    db.add(info)
    request.status = "INFO_REQUESTED"
    db.commit()
    return info_request_view(db, info)


@router.get("")
def list_requests(status: str | None = Query(default=None), period: str | None = Query(default=None),
                  ctx: Ctx = Depends(both), db: Session = Depends(get_db)):
    query = select(InfoRequest).where(InfoRequest.company_id == ctx.company_id).order_by(InfoRequest.created_at.desc())
    if status:
        query = query.where(InfoRequest.status == status)
    if period:
        query = query.where(InfoRequest.period == period)
    return [info_request_view(db, i) for i in db.scalars(query.limit(100))]


@router.get("/summary")
def summary(ctx: Ctx = Depends(both), db: Session = Depends(get_db)):
    rows = db.scalars(select(InfoRequest).where(InfoRequest.company_id == ctx.company_id)).all()
    return {"open": sum(r.status == "OPEN" for r in rows),
            "unseen": sum(r.status == "OPEN" and not r.operator_seen for r in rows),
            "responded": sum(r.status == "RESPONDED" for r in rows)}


def _own(db: Session, ctx: Ctx, request_id: str) -> InfoRequest:
    req = db.get(InfoRequest, request_id)
    if req is None or req.company_id != ctx.company_id:
        raise HTTPException(404, "Request not found.")
    return req


@router.post("/{request_id}/seen")
def mark_seen(request_id: str, ctx: Ctx = Depends(operator), db: Session = Depends(get_db)):
    req = _own(db, ctx, request_id)
    req.operator_seen = True
    db.commit()
    return {"ok": True}


@router.post("/{request_id}/reply")
def reply(request_id: str, body: ReplyBody, ctx: Ctx = Depends(operator), db: Session = Depends(get_db)):
    req = _own(db, ctx, request_id)
    if req.status != "OPEN":
        raise HTTPException(409, f"This request is {req.status}.")
    req.answers_json = json.dumps({k: v.strip()[:2000] for k, v in body.answers.items()})
    view = info_request_view(db, req)
    missing = [i["label"] for i in view["items"] if not i["fulfilled"]]
    if missing:
        raise HTTPException(400, "Still missing: " + "; ".join(missing))
    req.status, req.response_note = "RESPONDED", body.note
    req.responded_at, req.operator_seen = datetime.now(timezone.utc), True
    request = db.scalar(select(MonthlyRequest).where(MonthlyRequest.claim_id == req.claim_id))
    if request and request.status == "INFO_REQUESTED":
        still_open = db.scalar(select(InfoRequest.request_id).where(
            InfoRequest.claim_id == req.claim_id, InfoRequest.status == "OPEN",
            InfoRequest.request_id != req.request_id))
        if not still_open:
            request.status = "SUBMITTED"
    db.commit()
    return info_request_view(db, req)


@router.post("/{request_id}/close")
def close(request_id: str, body: CloseBody, ctx: Ctx = Depends(auditor), db: Session = Depends(get_db)):
    req = _own(db, ctx, request_id)
    if req.status == "CLOSED":
        raise HTTPException(409, "Already closed.")
    req.status, req.closed_at, req.close_note = "CLOSED", datetime.now(timezone.utc), body.note
    request = db.scalar(select(MonthlyRequest).where(MonthlyRequest.claim_id == req.claim_id))
    if request and request.status == "INFO_REQUESTED":
        still_open = db.scalar(select(InfoRequest.request_id).where(
            InfoRequest.claim_id == req.claim_id, InfoRequest.status == "OPEN",
            InfoRequest.request_id != req.request_id))
        if not still_open:
            request.status = "SUBMITTED"
    db.commit()
    return info_request_view(db, req)
