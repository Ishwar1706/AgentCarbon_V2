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
from app.services.company_access import ALL_VIEWERS, Ctx, claim_or_404, company_context
from app.services.documents import store_upload

router = APIRouter(prefix="/documents", tags=["documents"])


def _view(d: EvidenceDocument) -> dict:
    return {"document_id": d.document_id, "claim_id": d.claim_id, "document_type": d.document_type,
            "original_filename": d.original_filename, "content_type": d.content_type, "size_bytes": d.size_bytes,
            "sha256_hash": d.sha256_hash, "data_label": d.data_label, "verification_status": d.verification_status,
            "auditor_note": d.auditor_note, "uploaded_at": d.uploaded_at.isoformat()}


@router.post("/upload", status_code=201)
def upload(claim_id: str = Form(...), document_type: str = Form(...), data_label: str = Form("USER_UPLOADED"),
           file: UploadFile = File(...),
           ctx: Ctx = Depends(company_context("PLANT_OPERATOR", "ADMIN", require_dataset=True)),
           db: Session = Depends(get_db)):
    claim_or_404(ctx.company_id, claim_id)
    meta = store_upload(file, document_type, data_label)
    doc = EvidenceDocument(document_id=f"DOC-{uuid.uuid4().hex[:12].upper()}", company_id=ctx.company_id,
                           claim_id=claim_id, document_type=document_type, data_label=data_label,
                           uploaded_by_user_id=ctx.user.id, **meta)
    db.add(doc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        (settings.path("upload_dir") / meta["stored_filename"]).unlink(missing_ok=True)
        raise HTTPException(409, "This exact file was already uploaded for the claim.")
    return _view(doc)


@router.get("")
def list_documents(claim_id: str = Query(...), ctx: Ctx = Depends(company_context(*ALL_VIEWERS)),
                   db: Session = Depends(get_db)):
    return [_view(d) for d in db.scalars(select(EvidenceDocument).where(
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
    doc = db.scalar(select(EvidenceDocument).where(EvidenceDocument.document_id == document_id,
                                                   EvidenceDocument.company_id == ctx.company_id))
    if not doc:
        raise HTTPException(404, "Document not found.")
    doc.verification_status, doc.auditor_note = body.status, body.note
    doc.verified_by_user_id, doc.verified_at = ctx.user.id, datetime.now(timezone.utc)
    db.commit()
    return _view(doc)
