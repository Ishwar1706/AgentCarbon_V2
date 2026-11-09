"""First-run setup: companies, sensor fleets, five months of simulated sensor data, demo users."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.access_control import User
from app.models.sensor import Sensor, SensorReading
from app.models.workflows import AuditorApplication, BuyerApplication, Company
from app.services import periods, sensor_rollup
from app.services.company_data import (
    COMPANY_PROFILES, ensure_company_bundles, read_company_dataset,
)
from app.services.sensor_profiles import FLEETS, sensor_profiles
from app.services.sensor_sim import generate_historical

log = logging.getLogger("agentcarbon.provision")

DEMO_USERS = [
    ("admin@agentcarbon.demo", "Platform Admin", "ADMIN", None, "AgentCarbon"),
    ("auditor@agentcarbon.demo", "Verified Auditor", "AUDITOR", None, "Independent Carbon Assurance (demo)"),
    ("buyer@agentcarbon.demo", "Credit Buyer", "CREDIT_BUYER", None, "GreenFuture Offsets (demo buyer)"),
]
OPERATOR_EMAILS = {
    "sim-northstar-mobility": "northstar@agentcarbon.demo",
    "sim-ironwood-automotive": "ironwood@agentcarbon.demo",
    "sim-crestline-motors": "crestline@agentcarbon.demo",
    "sim-redwood-vehicle-systems": "redwood@agentcarbon.demo",
    "sim-summit-auto-works": "summit@agentcarbon.demo",
}


def _insert_frame(db: Session, sensor_id: str, frame: pd.DataFrame) -> None:
    frame = frame.assign(sensor_id=sensor_id, received_at=datetime.now(timezone.utc))
    records = frame.to_dict("records")
    for i in range(0, len(records), 5000):
        db.execute(insert(SensorReading), records[i:i + 5000])
    db.commit()


def provision_companies_and_sensors(db: Session) -> None:
    ensure_company_bundles()
    for company_id, profile in COMPANY_PROFILES.items():
        company = db.get(Company, company_id)
        if company is None:
            company = Company(
                company_id=company_id, legal_name=profile["legal_name"],
                city=profile["city"], state=profile["state"],
                industry="Automobile manufacturing (synthetic)",
                verification_status="VERIFIED", has_dataset=True)
            db.add(company)
            db.commit()
        if company_id not in FLEETS:
            continue
        existing = {s.sensor_id for s in db.scalars(select(Sensor).where(Sensor.company_id == company_id))}
        profiles = sensor_profiles(company_id, profile["legal_name"])
        for p in profiles:
            if p["sensor_id"] not in existing:
                db.add(Sensor(sensor_id=p["sensor_id"], company_id=company_id, zone=p["zone"],
                              location=p["location"], sensor_type="SCD40"))
        db.commit()
        has_data = db.scalar(select(func.count(SensorReading.id)).join(
            Sensor, Sensor.sensor_id == SensorReading.sensor_id).where(Sensor.company_id == company_id))
        if not has_data:
            base = read_company_dataset(company_id, "historical_scd40_readings.csv")
            for p in profiles:
                _insert_frame(db, p["sensor_id"], generate_historical(p, base))
            for period in periods.DATASET_PERIODS:
                sensor_rollup.seal_period(db, company_id, period)
            log.info("Simulated 5 months of sensor data for %s (%d sensors)", company_id, len(profiles))


def provision_users(db: Session) -> None:
    def ensure(email: str, name: str, role: str, company_id: str | None, org: str | None) -> User:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, full_name=name, role=role, company_id=company_id, organization=org,
                        account_status="ACTIVE", password_hash=hash_password(settings.demo_password))
            db.add(user)
            db.commit()
        return user

    for email, name, role, company_id, org in DEMO_USERS:
        user = ensure(email, name, role, company_id, org)
        if role == "AUDITOR" and not db.scalar(
                select(AuditorApplication).where(AuditorApplication.applicant_user_id == user.id)):
            db.add(AuditorApplication(application_id="AUD-DEMO-001", applicant_user_id=user.id,
                                      organization=org, credentials="Demo verified auditor", status="APPROVED"))
            db.commit()
        if role == "CREDIT_BUYER" and not db.scalar(
                select(BuyerApplication).where(BuyerApplication.applicant_user_id == user.id)):
            db.add(BuyerApplication(application_id="BUY-DEMO-001", applicant_user_id=user.id, organization=org,
                                    purpose="Demo credit buyer", status="APPROVED"))
            db.commit()
    for company_id, email in OPERATOR_EMAILS.items():
        name = COMPANY_PROFILES[company_id]["legal_name"]
        ensure(email, f"{name} Operator", "PLANT_OPERATOR", company_id, name)


_PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 100]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n# {label}\n")


def seed_sample_credits(db: Session) -> None:
    """Demo only: finish two clean months end-to-end so the credit buyer has registered credits to inspect."""
    import hashlib
    import json
    import uuid

    from app.agents.orchestrator import execute_run
    from app.models.access_control import AuditorDecision, EvidenceDocument
    from app.models.verification import VerificationRun
    from app.models.workflows import MonthlyRequest
    from app.services import credits, registry
    from app.services.company_data import get_claim

    auditor = db.scalar(select(User).where(User.email == "auditor@agentcarbon.demo"))
    if auditor is None:
        log.warning("Sample credits were not seeded: demo auditor account is missing.")
        return
    for company_id in ("sim-northstar-mobility", "sim-ironwood-automotive"):
        period = "2026-01"
        claim = get_claim(company_id, periods.claim_id(company_id, period))
        if claim is None:
            log.warning("Sample credit was not seeded for %s: %s data is missing.", company_id, period)
            continue
        if db.scalar(select(MonthlyRequest).where(MonthlyRequest.claim_id == claim["claim_id"])):
            log.info("Sample credit seed skipped for %s: a monthly request already exists.", company_id)
            continue
        operator = db.scalar(select(User).where(User.company_id == company_id, User.role == "PLANT_OPERATOR"))
        pre = credits.prefill(company_id, claim)
        db.add(MonthlyRequest(
            request_id=f"MR-{uuid.uuid4().hex[:10].upper()}", company_id=company_id, period=period,
            claim_id=claim["claim_id"], status="SUBMITTED", expected_credits_tco2e=pre["expected_credits_tco2e"],
            declared_electricity_kwh=pre["electricity_kwh"], declared_production_units=pre["production_units"],
            declared_natural_gas_scm=pre["natural_gas_scm"], declared_diesel_litres=pre["diesel_litres"],
            notes="Sample month (demo data).", created_by_user_id=operator.id if operator else None,
            submitted_at=datetime.now(timezone.utc)))
        for slot in ("ELECTRICITY_BILL", "PRODUCTION_RECORD", "FUEL_BILL"):
            content = _PDF.replace(b"{label}", f"{slot} {claim['claim_id']} synthetic".encode())
            stored = f"{uuid.uuid4().hex}.pdf"
            (settings.path("upload_dir") / stored).write_bytes(content)
            db.add(EvidenceDocument(
                document_id=f"DOC-{uuid.uuid4().hex[:12].upper()}", company_id=company_id, claim_id=claim["claim_id"],
                document_type=slot, original_filename=f"{slot.lower()}_{period}.pdf", stored_filename=stored,
                content_type="application/pdf", size_bytes=len(content), sha256_hash=hashlib.sha256(content).hexdigest(),
                data_label="SYNTHETIC_DEMO", verification_status="VERIFIED",
                uploaded_by_user_id=operator.id if operator else auditor.id, verified_by_user_id=auditor.id,
                verified_at=datetime.now(timezone.utc)))
        run = VerificationRun(run_id=f"RUN-{uuid.uuid4().hex[:12].upper()}", company_id=company_id,
                              claim_id=claim["claim_id"], period=period, month_number=1,
                              requested_mode="DETERMINISTIC", created_by_user_id=auditor.id)
        db.add(run)
        db.commit()
        execute_run(run.run_id)
        db.expire_all()
        run = db.get(VerificationRun, run.run_id)
        if run.status != "COMPLETED":
            log.warning("sample credit run failed for %s: %s", company_id, run.error)
            continue
        decision = AuditorDecision(
            decision_id=f"DEC-{uuid.uuid4().hex[:12].upper()}", company_id=company_id, claim_id=claim["claim_id"],
            verification_run_id=run.run_id, decision="APPROVE",
            comments="Sample approval: figures match the verified data and all evidence is on file.",
            auditor_user_id=auditor.id)
        db.add(decision)
        db.get(MonthlyRequest, db.scalar(select(MonthlyRequest.request_id).where(
            MonthlyRequest.claim_id == claim["claim_id"]))).status = "APPROVED"
        db.commit()
        registry.register(db, run, decision, auditor)
        log.info("Seeded registered Jan 2026 sample credit for %s.", company_id)


def provision_all(db: Session) -> None:
    provision_companies_and_sensors(db)
    if settings.demo_mode:
        provision_users(db)
        seed_sample_credits(db)
