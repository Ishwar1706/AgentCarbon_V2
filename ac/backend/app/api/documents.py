import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.access_control import EvidenceDocument
from app.models.workflows import InfoRequest, MonthlyRequest
from app.services import periods
from app.services.company_access import ALL_VIEWERS, Ctx, claim_for_period, company_context
from app.services.documents import document_view, store_upload

router = APIRouter(prefix="/documents", tags=["documents"])
LOCKED = {"APPROVED", "REJECTED"}


@router.post("/upload", status_code=201)
def upload(period: str = Form(...), document_type: str = Form(...), data_label: str = Form("USER_UPLOADED"),
           info_request_id: str = Form(""), file: UploadFile = File(...),
           ctx: Ctx = Depends(company_context("PLANT_OPERATOR", require_dataset=True)),
           db: Session = Depends(get_db)):
    periods.valid(period)
    claim = claim_for_period(ctx.company_id, period)
    if claim is None:
        raise HTTPException(404, f"No data available for {periods.label(period)}.")
    claim_id = claim["claim_id"]
    request = db.scalar(select(MonthlyRequest).where(MonthlyRequest.claim_id == claim_id))
    if request and request.status in LOCKED:
        raise HTTPException(409, f"This month is already {request.status}; uploads are closed.")
    if info_request_id:
        info = db.get(InfoRequest, info_request_id)
        if not info or info.company_id != ctx.company_id or info.claim_id != claim_id or info.status != "OPEN":
            raise HTTPException(400, "That information request is not open for this month.")
    meta = store_upload(file, document_type, data_label)
    doc = EvidenceDocument(document_id=f"DOC-{uuid.uuid4().hex[:12].upper()}", company_id=ctx.company_id,
                           claim_id=claim_id, info_request_id=info_request_id or None, document_type=document_type,
                           data_label=data_label, uploaded_by_user_id=ctx.user.id, **meta)
    db.add(doc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        (settings.path("upload_dir") / meta["stored_filename"]).unlink(missing_ok=True)
        raise HTTPException(409, "This exact file was already uploaded for this month.")
    return document_view(doc)


@router.get("")
def list_documents(period: str = Query(...), ctx: Ctx = Depends(company_context(*ALL_VIEWERS)),
                   db: Session = Depends(get_db)):
    claim_id = periods.claim_id(ctx.company_id, periods.valid(period))
    return [document_view(d) for d in db.scalars(select(EvidenceDocument).where(
        EvidenceDocument.company_id == ctx.company_id, EvidenceDocument.claim_id == claim_id
    ).order_by(EvidenceDocument.uploaded_at.desc()))]


@router.get("/{document_id}/download")
def download(document_id: str, ctx: Ctx = Depends(company_context(*ALL_VIEWERS)), db: Session = Depends(get_db)):
    doc = db.scalar(select(EvidenceDocument).where(EvidenceDocument.document_id == document_id,
                                                   EvidenceDocument.company_id == ctx.company_id))
    path = settings.path("upload_dir") / doc.stored_filename if doc else None
    if not doc or not path.exists():
        raise HTTPException(404, "Document not found.")
    return FileResponse(path, media_type=doc.content_type, filename=doc.original_filename,
                        headers={"X-Content-Type-Options": "nosniff"})


class VerifyBody(BaseModel):
    status: str  # VERIFIED | REJECTED
    note: str | None = None


@router.patch("/{document_id}/verify")
def verify(document_id: str, body: VerifyBody, ctx: Ctx = Depends(company_context("AUDITOR")),
           db: Session = Depends(get_db)):
    if body.status not in {"VERIFIED", "REJECTED"}:
        raise HTTPException(400, "status must be VERIFIED or REJECTED")
    if body.status == "REJECTED" and not (body.note or "").strip():
        raise HTTPException(400, "Give a reason when rejecting a document.")
    doc = db.scalar(select(EvidenceDocument).where(EvidenceDocument.document_id == document_id,
                                                   EvidenceDocument.company_id == ctx.company_id))
    if not doc:
        raise HTTPException(404, "Document not found.")
    doc.verification_status, doc.auditor_note = body.status, body.note
    doc.verified_by_user_id, doc.verified_at = ctx.user.id, datetime.now(timezone.utc)
    db.commit()
    return document_view(doc)
