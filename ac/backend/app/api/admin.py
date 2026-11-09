"""Administrator: verify / approve / reject accounts and maintain them. Nothing else."""
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import hash_password, require_roles
from app.models.access_control import User
from app.models.workflows import AuditorApplication, BuyerApplication, Company, CompanyApplication

router = APIRouter(prefix="/admin", tags=["admin"])
admin_only = require_roles("ADMIN")


class Review(BaseModel):
    action: str  # APPROVE | REJECT
    note: str | None = None


class StatusChange(BaseModel):
    status: str  # ACTIVE | SUSPENDED
    note: str | None = None


def _rows(db: Session) -> list[dict]:
    out = []
    for a in db.scalars(select(CompanyApplication)):
        user = db.get(User, a.applicant_user_id)
        out.append({"type": "COMPANY_OPERATOR", "application_id": a.application_id, "name": a.legal_name,
                    "detail": f"{a.city}, {a.state} · {a.industry}" + (f" · Reg: {a.registration_reference}" if a.registration_reference else ""),
                    "applicant": user.email if user else "", "applicant_name": user.full_name if user else "",
                    "status": a.status, "note": a.admin_note, "created_at": a.created_at})
    for a in db.scalars(select(AuditorApplication)):
        user = db.get(User, a.applicant_user_id)
        out.append({"type": "AUDITOR", "application_id": a.application_id, "name": a.organization,
                    "detail": a.credentials, "applicant": user.email if user else "",
                    "applicant_name": user.full_name if user else "",
                    "status": a.status, "note": a.admin_note, "created_at": a.created_at})
    for a in db.scalars(select(BuyerApplication)):
        user = db.get(User, a.applicant_user_id)
        out.append({"type": "CREDIT_BUYER", "application_id": a.application_id, "name": a.organization,
                    "detail": a.purpose, "applicant": user.email if user else "",
                    "applicant_name": user.full_name if user else "",
                    "status": a.status, "note": a.admin_note, "created_at": a.created_at})
    out.sort(key=lambda r: r["created_at"], reverse=True)
    for r in out:
        r["created_at"] = r["created_at"].isoformat()
    return out


@router.get("/summary", dependencies=[Depends(admin_only)])
def summary(db: Session = Depends(get_db)):
    pending = sum(r["status"] == "PENDING" for r in _rows(db))
    by_role = dict(db.execute(select(User.role, func.count()).group_by(User.role)).all())
    return {"pending_applications": pending, "accounts_by_role": by_role}


@router.get("/applications", dependencies=[Depends(admin_only)])
def applications(db: Session = Depends(get_db)):
    return _rows(db)


@router.post("/applications/{application_id}/review", dependencies=[Depends(admin_only)])
def review(application_id: str, body: Review, db: Session = Depends(get_db)):
    if body.action not in {"APPROVE", "REJECT"}:
        raise HTTPException(400, "action must be APPROVE or REJECT")
    approved = body.action == "APPROVE"
    status = "APPROVED" if approved else "REJECTED"
    for model in (CompanyApplication, AuditorApplication, BuyerApplication):
        app = db.get(model, application_id)
        if app is None:
            continue
        if app.status != "PENDING":
            raise HTTPException(409, "Application was already reviewed.")
        app.status, app.admin_note = status, body.note
        user = db.get(User, app.applicant_user_id)
        user.account_status = "ACTIVE" if approved else "REJECTED"
        if approved and model is CompanyApplication:
            company = Company(
                company_id=f"co-{uuid.uuid4().hex[:8]}", legal_name=app.legal_name, state=app.state,
                city=app.city, industry=app.industry, verification_status="VERIFIED", has_dataset=False)
            db.add(company)
            db.flush()
            user.company_id = company.company_id
        db.commit()
        return {"status": status}
    raise HTTPException(404, "Application not found.")


@router.get("/accounts", dependencies=[Depends(admin_only)])
def accounts(role: str | None = Query(default=None), status: str | None = Query(default=None),
             q: str | None = Query(default=None), db: Session = Depends(get_db)):
    query = select(User).order_by(User.created_at.desc())
    if role:
        query = query.where(User.role == role)
    if status:
        query = query.where(User.account_status == status)
    if q:
        like = f"%{q.lower()}%"
        query = query.where(func.lower(User.email).like(like) | func.lower(User.full_name).like(like))
    out = []
    for u in db.scalars(query.limit(300)):
        company = db.get(Company, u.company_id) if u.company_id else None
        out.append({"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role,
                    "organization": company.legal_name if company else u.organization,
                    "account_status": u.account_status, "created_at": u.created_at.isoformat()})
    return out


@router.post("/accounts/{user_id}/status")
def set_status(user_id: int, body: StatusChange, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    if body.status not in {"ACTIVE", "SUSPENDED"}:
        raise HTTPException(400, "status must be ACTIVE or SUSPENDED")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Account not found.")
    if user.id == admin.id:
        raise HTTPException(400, "You cannot change your own account status.")
    if user.account_status in {"PENDING", "REJECTED"}:
        raise HTTPException(409, "Review this account's application first.")
    user.account_status = body.status
    db.commit()
    return {"id": user.id, "account_status": user.account_status}


@router.post("/accounts/{user_id}/reset-password")
def reset_password(user_id: int, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Account not found.")
    temp = secrets.token_urlsafe(9) + "#1"
    user.password_hash = hash_password(temp)
    db.commit()
    return {"email": user.email, "temporary_password": temp,
            "notice": "Share this once with the user. They should change it after signing in."}
