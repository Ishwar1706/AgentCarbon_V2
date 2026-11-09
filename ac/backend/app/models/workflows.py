from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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


class BuyerApplication(Base):
    __tablename__ = "buyer_applications"
    application_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    applicant_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    organization: Mapped[str] = mapped_column(String(200))
    purpose: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    admin_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ClaimWorkflow(Base):
    __tablename__ = "claim_workflows"
    claim_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(30), default="NOT_SUBMITTED", index=True)
    submitted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MonthlyRequest(Base):
    """The operator's monthly update: declared figures and the credits they expect to earn."""
    __tablename__ = "monthly_requests"
    __table_args__ = (UniqueConstraint("company_id", "period", name="uq_company_period_request"),)
    request_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(80), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    claim_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    # DRAFT | SUBMITTED | INFO_REQUESTED | APPROVED | REJECTED | ESCALATED
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True)
    expected_credits_tco2e: Mapped[float] = mapped_column(Float, default=0.0)
    declared_electricity_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    declared_production_units: Mapped[int] = mapped_column(Integer, default=0)
    declared_natural_gas_scm: Mapped[float] = mapped_column(Float, default=0.0)
    declared_diesel_litres: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class InfoRequest(Base):
    """An auditor's request to the operator for missing documents or information."""
    __tablename__ = "info_requests"
    request_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(80), index=True)
    claim_id: Mapped[str] = mapped_column(String(120), index=True)
    period: Mapped[str] = mapped_column(String(7))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    items_json: Mapped[str] = mapped_column(Text, default="[]")
    # OPEN | RESPONDED | CLOSED
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    answers_json: Mapped[str] = mapped_column(Text, default="{}")
    response_note: Mapped[str | None] = mapped_column(Text)
    operator_seen: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_note: Mapped[str | None] = mapped_column(Text)
