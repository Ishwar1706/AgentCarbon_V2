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
from app.models.workflows import AuditorApplication, Company
from app.services import sensor_rollup
from app.services.company_data import (
    COMPANY_PROFILES, ensure_company_bundles, read_company_dataset,
)
from app.services.sensor_profiles import FLEETS, sensor_profiles
from app.services.sensor_sim import generate_historical

log = logging.getLogger("agentcarbon.provision")

DEMO_USERS = [
    ("admin@agentcarbon.demo", "Platform Admin", "ADMIN", None),
    ("auditor@agentcarbon.demo", "Verified Auditor", "AUDITOR", None),
    ("viewer@agentcarbon.demo", "Regulator Viewer", "REGULATOR_VIEWER", None),
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
            for month in range(1, 6):
                sensor_rollup.seal_period(db, company_id, month)
            log.info("Simulated 5 months of sensor data for %s (%d sensors)", company_id, len(profiles))


def provision_users(db: Session) -> None:
    def ensure(email: str, name: str, role: str, company_id: str | None) -> User:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, full_name=name, role=role, company_id=company_id,
                        password_hash=hash_password(settings.demo_password))
            db.add(user)
            db.commit()
        return user

    for email, name, role, company_id in DEMO_USERS:
        user = ensure(email, name, role, company_id)
        if role == "AUDITOR" and not db.scalar(
                select(AuditorApplication).where(AuditorApplication.applicant_user_id == user.id)):
            db.add(AuditorApplication(
                application_id="AUD-DEMO-001", applicant_user_id=user.id,
                organization="Independent Carbon Assurance (demo)",
                credentials="Demo verified auditor", status="APPROVED"))
            db.commit()
    for company_id, email in OPERATOR_EMAILS.items():
        ensure(email, f"{COMPANY_PROFILES[company_id]['legal_name']} Operator", "PLANT_OPERATOR", company_id)


def provision_all(db: Session) -> None:
    provision_companies_and_sensors(db)
    if settings.demo_mode:
        provision_users(db)
