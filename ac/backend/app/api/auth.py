import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    check_login_allowed, clear_login_failures, create_token, current_user, hash_password,
    is_verified_auditor, record_login_failure, verify_password,
)
from app.models.access_control import User
from app.models.workflows import AuditorApplication, Company, CompanyApplication
from app.services.provisioning import DEMO_USERS, OPERATOR_EMAILS

router = APIRouter(prefix="/auth", tags=["auth"])


class CompanySignup(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=100)
    full_name: str = Field(min_length=2, max_length=200)
    legal_name: str = Field(min_length=2, max_length=200)
    state: str = Field(min_length=2, max_length=100)
    city: str = Field(min_length=2, max_length=100)
    industry: str = Field(default="Automobile manufacturing", max_length=120)
    registration_reference: str | None = Field(default=None, max_length=150)


class AuditorSignup(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=100)
    full_name: str = Field(min_length=2, max_length=200)
    organization: str = Field(min_length=2, max_length=200)
    credentials: str = Field(min_length=5, max_length=2000)


def _user_payload(db: Session, user: User) -> dict:
    company = db.get(Company, user.company_id) if user.company_id else None
    return {
        "id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role,
        "company_id": user.company_id, "company_name": company.legal_name if company else None,
        "auditor_verified": is_verified_auditor(db, user) if user.role == "AUDITOR" else None,
    }


@router.post("/login")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = form.username.strip().lower()
    check_login_allowed(request, email)
    user = db.scalar(select(User).where(User.email == email))
    if not user or not user.is_active or not verify_password(form.password, user.password_hash):
        record_login_failure(request, email)
        raise HTTPException(401, "Incorrect email or password.")
    clear_login_failures(request, email)
    return {"access_token": create_token(user), "token_type": "bearer", "user": _user_payload(db, user)}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _user_payload(db, user)


@router.get("/demo-accounts")
def demo_accounts():
    """Only populated in DEMO_MODE; lets the login page offer one-click demo sign-in."""
    if not settings.demo_mode:
        return {"demo_mode": False, "accounts": []}
    accounts = [{"email": e, "role": r, "label": n} for e, n, r, _ in DEMO_USERS]
    accounts += [{"email": e, "role": "PLANT_OPERATOR", "label": cid.replace("sim-", "").replace("-", " ").title()}
                 for cid, e in OPERATOR_EMAILS.items()]
    return {"demo_mode": True, "password": settings.demo_password, "accounts": accounts}


def _new_user(db: Session, email: str, password: str, name: str, role: str) -> User:
    if db.scalar(select(User).where(User.email == email.lower())):
        raise HTTPException(409, "An account with this email already exists.")
    user = User(email=email.lower(), full_name=name, role=role, password_hash=hash_password(password))
    db.add(user)
    db.flush()
    return user


@router.post("/register/company", status_code=201)
def register_company(payload: CompanySignup, db: Session = Depends(get_db)):
    user = _new_user(db, payload.email, payload.password, payload.full_name, "PLANT_OPERATOR")
    db.add(CompanyApplication(
        application_id=f"CAPP-{uuid.uuid4().hex[:10].upper()}", applicant_user_id=user.id,
        legal_name=payload.legal_name, state=payload.state, city=payload.city,
        industry=payload.industry, registration_reference=payload.registration_reference))
    db.commit()
    return {"message": "Registered. An administrator must verify your company before data access."}


@router.post("/register/auditor", status_code=201)
def register_auditor(payload: AuditorSignup, db: Session = Depends(get_db)):
    user = _new_user(db, payload.email, payload.password, payload.full_name, "AUDITOR")
    db.add(AuditorApplication(
        application_id=f"AAPP-{uuid.uuid4().hex[:10].upper()}", applicant_user_id=user.id,
        organization=payload.organization, credentials=payload.credentials))
    db.commit()
    return {"message": "Registered. An administrator must verify your auditor credentials."}
