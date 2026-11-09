"""Information requests from an auditor to an operator, with automatic fulfilment tracking."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.access_control import EvidenceDocument, User
from app.models.workflows import InfoRequest
from app.services import periods


def item_status(db: Session, req: InfoRequest, item: dict, answers: dict) -> dict:
    """An item is fulfilled by a document of the right type (uploaded for this request or after it)
    or, for information items, a non-empty written answer."""
    if item["kind"] == "DOCUMENT":
        docs = db.scalars(select(EvidenceDocument).where(
            EvidenceDocument.claim_id == req.claim_id, EvidenceDocument.document_type == item["doc_type"],
            EvidenceDocument.verification_status != "REJECTED")).all()
        ok = any(d.info_request_id == req.request_id or d.uploaded_at >= req.created_at for d in docs)
        return {**item, "fulfilled": ok, "answer": ""}
    answer = (answers.get(item["item_id"]) or "").strip()
    return {**item, "fulfilled": bool(answer), "answer": answer}


def info_request_view(db: Session, req: InfoRequest) -> dict:
    items = json.loads(req.items_json or "[]")
    answers = json.loads(req.answers_json or "{}")
    author = db.get(User, req.created_by_user_id)
    return {
        "request_id": req.request_id, "claim_id": req.claim_id, "period": req.period,
        "label": periods.label(req.period), "company_id": req.company_id, "title": req.title,
        "message": req.message, "status": req.status, "operator_seen": req.operator_seen,
        "items": [item_status(db, req, i, answers) for i in items],
        "response_note": req.response_note, "close_note": req.close_note,
        "created_by": author.full_name if author else "Auditor",
        "created_at": req.created_at.isoformat(),
        "responded_at": req.responded_at.isoformat() if req.responded_at else None,
        "closed_at": req.closed_at.isoformat() if req.closed_at else None,
    }
