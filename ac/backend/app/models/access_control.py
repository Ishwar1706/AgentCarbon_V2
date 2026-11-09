from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(Text)
    # PLANT_OPERATOR | AUDITOR | CREDIT_BUYER | ADMIN
    role: Mapped[str] = mapped_column(String(40), index=True)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.company_id"), index=True)
    organization: Mapped[str | None] = mapped_column(String(200))
    # PENDING (awaiting admin) | ACTIVE | REJECTED | SUSPENDED
    account_status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvidenceDocument(Base):
    __tablename__ = "evidence_documents"
    __table_args__ = (UniqueConstraint("claim_id", "sha256_hash", name="uq_claim_document_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    company_id: Mapped[str] = mapped_column(String(80), index=True)
    claim_id: Mapped[str] = mapped_column(String(120), index=True)
    info_request_id: Mapped[str | None] = mapped_column(String(60), index=True)
    document_type: Mapped[str] = mapped_column(String(80))
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256_hash: Mapped[str] = mapped_column(String(64), index=True)
    data_label: Mapped[str] = mapped_column(String(40), default="USER_UPLOADED")
    verification_status: Mapped[str] = mapped_column(String(40), default="PENDING")
    auditor_note: Mapped[str | None] = mapped_column(Text)
    uploaded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    verified_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditorDecision(Base):
    __tablename__ = "auditor_decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    decision_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    company_id: Mapped[str] = mapped_column(String(80), index=True)
    claim_id: Mapped[str] = mapped_column(String(120), index=True)
    verification_run_id: Mapped[str] = mapped_column(String(100))
    decision: Mapped[str] = mapped_column(String(50))
    comments: Mapped[str] = mapped_column(Text)
    auditor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
