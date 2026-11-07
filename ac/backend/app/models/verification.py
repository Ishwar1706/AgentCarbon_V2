from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.access_control import utcnow


class VerificationRun(Base):
    __tablename__ = "verification_runs"
    run_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(80), index=True)
    claim_id: Mapped[str] = mapped_column(String(120), index=True)
    month_number: Mapped[int] = mapped_column(Integer, default=0)
    requested_mode: Mapped[str] = mapped_column(String(20), default="AUTO")
    execution_mode: Mapped[str] = mapped_column(String(30), default="PENDING")
    status: Mapped[str] = mapped_column(String(20), default="QUEUED", index=True)
    progress_json: Mapped[str] = mapped_column(Text, default="[]")
    result_json: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    deterministic_recommendation: Mapped[str | None] = mapped_column(String(60))
    final_recommendation: Mapped[str | None] = mapped_column(String(60))
    confidence_score: Mapped[float | None] = mapped_column(Float)
    primary_reason: Mapped[str | None] = mapped_column(Text)
    claimed_emissions_kgco2e: Mapped[float | None] = mapped_column(Float)
    verified_emissions_kgco2e: Mapped[float | None] = mapped_column(Float)
    discrepancy_percent: Mapped[float | None] = mapped_column(Float)
    evidence_bundle_hash: Mapped[str | None] = mapped_column(String(64))
    trust_snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    report_hash: Mapped[str | None] = mapped_column(String(64))
    llm_total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    llm_call_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditRegistryRecord(Base):
    """Hash-chained, append-only audit ledger (local tamper-evident registry)."""
    __tablename__ = "audit_registry_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[str] = mapped_column(String(80), index=True)
    claim_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    run_id: Mapped[str] = mapped_column(String(60))
    decision_id: Mapped[str] = mapped_column(String(80))
    evidence_bundle_hash: Mapped[str] = mapped_column(String(64))
    trust_snapshot_hash: Mapped[str] = mapped_column(String(64))
    report_hash: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(String(60))
    auditor_decision: Mapped[str] = mapped_column(String(50))
    previous_hash: Mapped[str] = mapped_column(String(64))
    record_hash: Mapped[str] = mapped_column(String(64), unique=True)
    block_number: Mapped[int] = mapped_column(Integer)
    registry_mode: Mapped[str] = mapped_column(String(30), default="LOCAL_HASH_CHAIN")
    registered_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
