"""Reports and the hash-chained audit registry (local, tamper-evident; not a public blockchain)."""
from __future__ import annotations

import html
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.evidence import sha256_json
from app.core.config import settings
from app.models.access_control import AuditorDecision, User
from app.models.verification import AuditRegistryRecord, VerificationRun

GENESIS = "0" * 64


def latest_completed_run(db: Session, company_id: str, claim_id: str) -> VerificationRun | None:
    return db.scalar(select(VerificationRun).where(
        VerificationRun.company_id == company_id, VerificationRun.claim_id == claim_id,
        VerificationRun.status == "COMPLETED").order_by(VerificationRun.created_at.desc()))


def latest_decision(db: Session, company_id: str, claim_id: str) -> AuditorDecision | None:
    return db.scalar(select(AuditorDecision).where(
        AuditorDecision.company_id == company_id, AuditorDecision.claim_id == claim_id
    ).order_by(AuditorDecision.decided_at.desc(), AuditorDecision.id.desc()))


def build_report(db: Session, run: VerificationRun, decision: AuditorDecision | None) -> dict:
    result = json.loads(run.result_json)
    auditor = db.get(User, decision.auditor_user_id) if decision else None
    return {
        "report_version": "2.0", "company_id": run.company_id, "claim_id": run.claim_id,
        "run_id": run.run_id, "execution_mode": run.execution_mode,
        "claim": result["evidence_packet"]["claim"], "consensus": result["consensus"],
        "agent_assessments": result["agent_assessments"], "debate_messages": result["debate_messages"],
        "evidence_summary": {
            "sensors": {k: v for k, v in result["evidence_packet"]["sensors"].items() if k != "sensors"},
            "documents": result["evidence_packet"]["documents"],
            "trust": result["evidence_packet"]["trust"],
        },
        "auditor_decision": None if not decision else {
            "decision_id": decision.decision_id, "decision": decision.decision,
            "comments": decision.comments, "auditor": auditor.full_name if auditor else None,
            "decided_at": decision.decided_at.isoformat()},
        "integrity": result["integrity"],
        "notice": "Synthetic demonstration data. The auditor decision is the final authority.",
    }


def report_to_html(report: dict) -> str:
    esc = lambda v: html.escape(str(v))  # noqa: E731
    c, cons = report["claim"], report["consensus"]
    decision = report["auditor_decision"]
    rows = "".join(f"<tr><td>{esc(a['agent_name'])}</td><td>{esc(a['status'])}</td><td>{esc(a['risk_level'])}</td>"
                   f"<td>{esc(a['summary'])}</td></tr>" for a in report["agent_assessments"])
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{esc(report['claim_id'])}</title>
<style>body{{font-family:Arial,sans-serif;max-width:900px;margin:30px auto;color:#222}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ccc;padding:6px;text-align:left;font-size:14px}}code{{word-break:break-all}}</style></head><body>
<h1>AgentCarbon Verification Report</h1><p>{esc(report['claim_id'])} — {esc(report['company_id'])}</p>
<h2>Claim</h2><p>Claimed {esc(c['claimed_total_kgco2e'])} kgCO2e vs verified {esc(c['verified_total_kgco2e'])} kgCO2e
({esc(c['discrepancy_percent'])}% {esc(c['direction'])}).</p>
<h2>Recommendation</h2><p><b>{esc(cons['final_recommendation'])}</b> (confidence {esc(cons['confidence_score'])}, mode {esc(report['execution_mode'])})</p>
<p>{esc(cons['primary_reason'])}</p>
<h2>Agents</h2><table><tr><th>Agent</th><th>Status</th><th>Risk</th><th>Summary</th></tr>{rows}</table>
<h2>Auditor decision</h2><p>{esc(decision['decision'] + ' — ' + decision['comments']) if decision else 'Pending'}</p>
<h2>Integrity</h2><p>Report hash: <code>{esc(report['integrity']['report_hash'])}</code></p>
<p><i>{esc(report['notice'])}</i></p></body></html>"""


def write_report_files(report: dict) -> dict[str, str]:
    directory: Path = settings.path("report_dir")
    base = report["claim_id"].replace("/", "_")
    (directory / f"{base}.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (directory / f"{base}.html").write_text(report_to_html(report), encoding="utf-8")
    return {"json": f"{base}.json", "html": f"{base}.html"}


# ------------------------------------------------------------------ ledger
def record_hash(previous: str, payload_hash: str, claim_id: str, block: int) -> str:
    return sha256_json({"previous": previous, "payload": payload_hash, "claim": claim_id, "block": block})


def register(db: Session, run: VerificationRun, decision: AuditorDecision, user: User) -> AuditRegistryRecord:
    report = build_report(db, run, decision)
    payload_hash = sha256_json(report)
    last = db.scalar(select(AuditRegistryRecord).order_by(AuditRegistryRecord.block_number.desc()))
    block = (last.block_number + 1) if last else 1
    previous = last.record_hash if last else GENESIS
    record = AuditRegistryRecord(
        company_id=run.company_id, claim_id=run.claim_id, run_id=run.run_id, decision_id=decision.decision_id,
        evidence_bundle_hash=run.evidence_bundle_hash, trust_snapshot_hash=run.trust_snapshot_hash,
        report_hash=payload_hash, payload_json=json.dumps(report, default=str), recommendation=run.final_recommendation,
        auditor_decision=decision.decision, previous_hash=previous,
        record_hash=record_hash(previous, payload_hash, run.claim_id, block), block_number=block,
        registered_by_user_id=user.id)
    db.add(record)
    db.commit()
    write_report_files(report)
    return record


def verify_record(db: Session, record: AuditRegistryRecord) -> dict:
    snapshot = json.loads(record.payload_json)
    payload_ok = sha256_json(snapshot) == record.report_hash
    run = db.get(VerificationRun, record.run_id)
    run_ok = bool(run and run.evidence_bundle_hash == record.evidence_bundle_hash
                  and run.trust_snapshot_hash == record.trust_snapshot_hash)
    prior = db.scalar(select(AuditRegistryRecord).where(AuditRegistryRecord.block_number == record.block_number - 1))
    previous = prior.record_hash if prior else GENESIS
    chain_ok = record.previous_hash == previous and record.record_hash == record_hash(
        record.previous_hash, record.report_hash, record.claim_id, record.block_number)
    newer = latest_decision(db, record.company_id, record.claim_id)
    return {
        "claim_id": record.claim_id, "block_number": record.block_number,
        "payload_hash_matches": payload_ok, "evidence_matches_run": run_ok, "chain_link_valid": chain_ok,
        "newer_decision_exists": bool(newer and newer.decision_id != record.decision_id),
        "status": "VERIFIED" if (payload_ok and run_ok and chain_ok) else "TAMPER_DETECTED",
        "record_hash": record.record_hash,
    }


def verify_chain(db: Session) -> dict:
    records = db.scalars(select(AuditRegistryRecord).order_by(AuditRegistryRecord.block_number)).all()
    results = [verify_record(db, r) for r in records]
    return {"block_count": len(records), "valid": all(r["status"] == "VERIFIED" for r in results),
            "records": results}
