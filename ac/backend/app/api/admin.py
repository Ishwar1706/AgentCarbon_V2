import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_roles
from app.models.access_control import User
from app.models.workflows import AuditorApplication, Company, CompanyApplication

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_roles("ADMIN"))])


class Review(BaseModel):
    action: str  # APPROVE | REJECT
    note: str | None = None


@router.get("/applications")
def applications(db: Session = Depends(get_db)):
    out = []
    for a in db.scalars(select(CompanyApplication).order_by(CompanyApplication.created_at.desc())):
        user = db.get(User, a.applicant_user_id)
        out.append({"type": "COMPANY", "application_id": a.application_id, "name": a.legal_name,
                    "detail": f"{a.city}, {a.state} · {a.industry}", "applicant": user.email if user else "",
                    "status": a.status, "note": a.admin_note, "created_at": a.created_at.isoformat()})
    for a in db.scalars(select(AuditorApplication).order_by(AuditorApplication.created_at.desc())):
        user = db.get(User, a.applicant_user_id)
        out.append({"type": "AUDITOR", "application_id": a.application_id, "name": a.organization,
                    "detail": a.credentials, "applicant": user.email if user else "",
                    "status": a.status, "note": a.admin_note, "created_at": a.created_at.isoformat()})
    return out


@router.post("/applications/{application_id}/review")
def review(application_id: str, body: Review, db: Session = Depends(get_db)):
    if body.action not in {"APPROVE", "REJECT"}:
        raise HTTPException(400, "action must be APPROVE or REJECT")
    status = "APPROVED" if body.action == "APPROVE" else "REJECTED"
    company_app = db.get(CompanyApplication, application_id)
    if company_app:
        if company_app.status != "PENDING":
            raise HTTPException(409, "Application was already reviewed.")
        company_app.status, company_app.admin_note = status, body.note
        if status == "APPROVED":
            company = Company(
                company_id=f"co-{uuid.uuid4().hex[:8]}", legal_name=company_app.legal_name,
                state=company_app.state, city=company_app.city, industry=company_app.industry,
                verification_status="VERIFIED", has_dataset=False)
            db.add(company)
            db.flush()
            db.get(User, company_app.applicant_user_id).company_id = company.company_id
        db.commit()
        return {"status": status}
    auditor_app = db.get(AuditorApplication, application_id)
    if auditor_app:
        if auditor_app.status != "PENDING":
            raise HTTPException(409, "Application was already reviewed.")
        auditor_app.status, auditor_app.admin_note = status, body.note
        db.commit()
        return {"status": status}
    raise HTTPException(404, "Application not found.")
