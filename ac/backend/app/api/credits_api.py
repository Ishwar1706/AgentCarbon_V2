"""Credit buyers: auditor-approved, registry-anchored credits only."""
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_roles
from app.models.access_control import User
from app.models.verification import AuditRegistryRecord
from app.models.workflows import Company
from app.services import registry

router = APIRouter(prefix="/credits", tags=["credits"])
buyer = require_roles("CREDIT_BUYER")


def _approved(db: Session) -> list[AuditRegistryRecord]:
    return db.scalars(select(AuditRegistryRecord).where(AuditRegistryRecord.auditor_decision == "APPROVE")
                      .order_by(AuditRegistryRecord.block_number.desc())).all()


def _view(db: Session, r: AuditRegistryRecord) -> dict:
    report = json.loads(r.payload_json)
    company = db.get(Company, r.company_id)
    cr, cons = report.get("credits", {}), report["consensus"]
    return {
        "claim_id": r.claim_id, "company_id": r.company_id, "company_name": company.legal_name if company else r.company_id,
        "period": report["claim"]["period"], "label": report["claim"]["label"],
        "approved_credits_tco2e": cr.get("approvable_credits_tco2e", 0.0),
        "expected_credits_tco2e": cr.get("expected_credits_tco2e", 0.0),
        "supported_credits_tco2e": cr.get("supported_credits_tco2e", 0.0),
        "ai_recommendation": r.recommendation, "confidence_score": cons.get("confidence_score"),
        "execution_mode": report.get("execution_mode"), "auditor": (report.get("auditor_decision") or {}).get("auditor"),
        "auditor_comment": (report.get("auditor_decision") or {}).get("comments"),
        "block_number": r.block_number, "record_hash": r.record_hash, "registered_at": r.registered_at.isoformat(),
    }


@router.get("")
def list_credits(_: User = Depends(buyer), db: Session = Depends(get_db)):
    return [_view(db, r) for r in _approved(db)]


@router.get("/summary")
def summary(_: User = Depends(buyer), db: Session = Depends(get_db)):
    rows = [_view(db, r) for r in _approved(db)]
    chain = registry.verify_chain(db)
    return {"credit_lots": len(rows), "companies": len({r["company_id"] for r in rows}),
            "total_credits_tco2e": round(sum(r["approved_credits_tco2e"] for r in rows), 2),
            "registry_valid": chain["valid"], "registry_blocks": chain["block_count"]}


def _record(db: Session, claim_id: str) -> AuditRegistryRecord:
    r = db.scalar(select(AuditRegistryRecord).where(AuditRegistryRecord.claim_id == claim_id,
                                                    AuditRegistryRecord.auditor_decision == "APPROVE"))
    if r is None:
        raise HTTPException(404, "This credit is not available.")
    return r


@router.get("/{claim_id}/verify")
def verify(claim_id: str, _: User = Depends(buyer), db: Session = Depends(get_db)):
    return registry.verify_record(db, _record(db, claim_id))


@router.get("/{claim_id}/report")
def report(claim_id: str, format: str = Query(default="html", pattern="^(html|json)$"),
           _: User = Depends(buyer), db: Session = Depends(get_db)):
    data = json.loads(_record(db, claim_id).payload_json)
    if format == "json":
        return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="{claim_id}.json"'})
    return HTMLResponse(registry.report_to_html(data))
