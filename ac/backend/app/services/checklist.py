"""Evidence checklist for a monthly request (bills and records the operator must provide)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.access_control import EvidenceDocument

REQUIRED = [
    ("ELECTRICITY_BILL", "Electricity (light) bill"),
    ("PRODUCTION_RECORD", "Production record / production bill"),
    ("FUEL_BILL", "Fuel bill (natural gas / diesel)"),
]
OPTIONAL = [
    ("CALIBRATION_CERTIFICATE", "Calibration certificate"),
    ("MAINTENANCE_RECORD", "Maintenance / repair record"),
    ("METER_PHOTO", "Meter photo"),
    ("OTHER", "Other supporting document"),
]
DOCUMENT_TYPES = {slot for slot, _ in REQUIRED + OPTIONAL}
LABELS = dict(REQUIRED + OPTIONAL)


def checklist(db: Session, company_id: str, claim_id: str) -> dict:
    docs = db.scalars(select(EvidenceDocument).where(
        EvidenceDocument.company_id == company_id, EvidenceDocument.claim_id == claim_id)).all()
    slots = []
    for slot, label in REQUIRED + OPTIONAL:
        mine = [d for d in docs if d.document_type == slot]
        verified = sum(d.verification_status == "VERIFIED" for d in mine)
        pending = sum(d.verification_status == "PENDING" for d in mine)
        rejected = sum(d.verification_status == "REJECTED" for d in mine)
        status = "VERIFIED" if verified else "PROVIDED" if pending else "MISSING"
        slots.append({"slot": slot, "label": label, "required": slot in dict(REQUIRED), "status": status,
                      "count": len(mine), "verified": verified, "pending": pending, "rejected": rejected})
    missing = [s["slot"] for s in slots if s["required"] and s["status"] == "MISSING"]
    return {"slots": slots, "missing_required": missing, "documents_total": len(docs),
            "calibration_verified": any(s["slot"] == "CALIBRATION_CERTIFICATE" and s["verified"] for s in slots)}
