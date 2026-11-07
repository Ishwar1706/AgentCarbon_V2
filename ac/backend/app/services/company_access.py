"""One place that decides which company a user may see (fixes cross-company leaks)."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import is_verified_auditor, require_roles
from app.models.access_control import User
from app.models.workflows import Company
from app.services.company_data import get_claim


@dataclass
class Ctx:
    user: User
    company: Company

    @property
    def company_id(self) -> str:
        return self.company.company_id


def resolve_company(
    db: Session, user: User, company_id: str | None, require_dataset: bool = False
) -> Company:
    if user.role == "PLANT_OPERATOR":
        if not user.company_id:
            raise HTTPException(403, "Company access is pending admin verification.")
        if company_id and company_id != user.company_id:
            raise HTTPException(403, "You may only access your own company.")
        selected = user.company_id
    else:
        if user.role == "AUDITOR" and not is_verified_auditor(db, user):
            raise HTTPException(403, "Auditor verification by an administrator is required first.")
        if not company_id:
            raise HTTPException(400, "Select a company first.")
        selected = company_id
    company = db.get(Company, selected)
    if company is None or (
        user.role != "ADMIN" and company.verification_status not in {"VERIFIED", "DEMO"}
    ):
        raise HTTPException(404, "Company was not found or is not available.")
    if require_dataset and not company.has_dataset:
        raise HTTPException(404, "This company has no imported monthly dataset yet.")
    return company


def company_context(*roles: str, require_dataset: bool = False):
    def dependency(
        company_id: str | None = Query(default=None),
        db: Session = Depends(get_db),
        user: User = Depends(require_roles(*roles)),
    ) -> Ctx:
        return Ctx(user=user, company=resolve_company(db, user, company_id, require_dataset))

    return dependency


ALL_VIEWERS = ("PLANT_OPERATOR", "AUDITOR", "REGULATOR_VIEWER", "ADMIN")


def claim_or_404(company_id: str, claim_id: str) -> dict:
    claim = get_claim(company_id, claim_id)
    if claim is None:
        raise HTTPException(404, "Claim was not found for this company.")
    return claim
