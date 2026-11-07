from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.access_control import utcnow


class Company(Base):
    __tablename__ = "companies"
    company_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    legal_name: Mapped[str] = mapped_column(String(200), index=True)
    state: Mapped[str] = mapped_column(String(100), default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    industry: Mapped[str] = mapped_column(String(120), default="")
    verification_status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    has_dataset: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CompanyApplication(Base):
    __tablename__ = "company_applications"
    application_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    applicant_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    legal_name: Mapped[str] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(100))
    city: Mapped[str] = mapped_column(String(100))
    industry: Mapped[str] = mapped_column(String(120))
    registration_reference: Mapped[str | None] = mapped_column(String(150))
    status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    admin_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditorApplication(Base):
    __tablename__ = "auditor_applications"
    application_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    applicant_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    organization: Mapped[str] = mapped_column(String(200))
    credentials: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    admin_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ClaimWorkflow(Base):
    """Lifecycle of one monthly claim: NOT_SUBMITTED -> SUBMITTED -> auditor decision."""
    __tablename__ = "claim_workflow"
    claim_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(40), default="SUBMITTED", index=True)
    submitted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
