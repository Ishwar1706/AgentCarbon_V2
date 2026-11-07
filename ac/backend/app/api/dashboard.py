"""Company dashboards: claims, monthly comparison, trust, energy (all company-scoped)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.access_control import AuditorDecision
from app.models.verification import VerificationRun
from app.models.workflows import ClaimWorkflow
from app.services import sensor_rollup
from app.services.company_access import ALL_VIEWERS, Ctx, claim_or_404, company_context
from app.services.company_data import company_claims, read_company_dataset, records
from app.services.company_trust_service import get_company_trust_analysis

router = APIRouter(tags=["dashboard"])
viewer = company_context(*ALL_VIEWERS, require_dataset=True)


def _claim_rows(db: Session, company_id: str) -> list[dict]:
    claims = records(company_claims(company_id))
    flows = {w.claim_id: w for w in db.scalars(select(ClaimWorkflow).where(ClaimWorkflow.company_id == company_id))}
    out = []
    for c in claims:
        run = db.scalar(select(VerificationRun).where(
            VerificationRun.claim_id == c["claim_id"], VerificationRun.company_id == company_id,
            VerificationRun.status == "COMPLETED").order_by(VerificationRun.created_at.desc()))
        decision = db.scalar(select(AuditorDecision).where(
            AuditorDecision.claim_id == c["claim_id"], AuditorDecision.company_id == company_id
        ).order_by(AuditorDecision.decided_at.desc(), AuditorDecision.id.desc()))
        out.append({
            "claim_id": c["claim_id"], "month_number": c["month_number"], "month_label": c["month_label"],
            "period_start": c["period_start"], "period_end": c["period_end"],
            "claimed_total_kgco2e": c["claimed_total_kgco2e"], "verified_total_kgco2e": c["verified_total_kgco2e"],
            "discrepancy_percent": c["claim_discrepancy_percent"], "vehicles_produced": c["vehicles_produced"],
            "workflow_status": flows[c["claim_id"]].status if c["claim_id"] in flows else "NOT_SUBMITTED",
            "latest_run_id": run.run_id if run else None,
            "recommendation": run.final_recommendation if run else None,
            "execution_mode": run.execution_mode if run else None,
            "auditor_decision": decision.decision if decision else None,
        })
    return out


@router.get("/dashboard/claims")
def claims(ctx: Ctx = Depends(viewer), db: Session = Depends(get_db)):
    return _claim_rows(db, ctx.company_id)


@router.get("/dashboard/claims/{claim_id}")
def claim_detail(claim_id: str, ctx: Ctx = Depends(viewer), db: Session = Depends(get_db)):
    claim_or_404(ctx.company_id, claim_id)
    return next(r for r in _claim_rows(db, ctx.company_id) if r["claim_id"] == claim_id)


@router.get("/dashboard/monthly-comparison")
def monthly_comparison(ctx: Ctx = Depends(viewer), db: Session = Depends(get_db)):
    _, trust = get_company_trust_analysis(ctx.company_id)
    trust_by_month = {int(r["month_number"]): r for r in records(trust)}
    sensors = {s["month_number"]: s for s in sensor_rollup.list_period_summaries(db, ctx.company_id)}
    out = []
    for c in records(company_claims(ctx.company_id)):
        m = int(c["month_number"])
        t, s = trust_by_month.get(m, {}), sensors.get(m, {})
        out.append({
            "month_number": m, "month_label": c["month_label"], "scenario": c["month_scenario"],
            "claimed_total_kgco2e": c["claimed_total_kgco2e"], "verified_total_kgco2e": c["verified_total_kgco2e"],
            "discrepancy_percent": c["claim_discrepancy_percent"],
            "minimum_meter_trust": t.get("minimum_main_meter_trust"),
            "dynamic_mae_kwh": t.get("dynamic_mae_kwh"), "static_mae_kwh": t.get("static_mae_kwh"),
            "sensor_completeness_percent": s.get("completeness_percent"),
            "sensor_avg_co2_ppm": s.get("avg_co2_ppm"), "sensor_count": s.get("sensor_count"),
            "flagged_sensors": s.get("flagged_sensor_count"),
        })
    return out


@router.get("/dashboard/overview")
def overview(month_number: int = Query(default=1, ge=1, le=60), ctx: Ctx = Depends(viewer), db: Session = Depends(get_db)):
    rows = _claim_rows(db, ctx.company_id)
    claim = next((r for r in rows if r["month_number"] == month_number), rows[0])
    _, trust = get_company_trust_analysis(ctx.company_id)
    t = records(trust[trust["month_number"] == claim["month_number"]])
    sensors = sensor_rollup.get_period_summary(db, ctx.company_id, claim["month_number"])
    return {
        "company": {"company_id": ctx.company_id, "legal_name": ctx.company.legal_name},
        "claim": claim, "trust": t[0] if t else None,
        "sensors": {k: v for k, v in (sensors or {}).items() if k != "sensors"} or None,
        "totals": {
            "claims": len(rows), "approved": sum(r["auditor_decision"] == "APPROVE" for r in rows),
            "needs_attention": sum(r["discrepancy_percent"] > 5 for r in rows),
        },
    }


@router.get("/dashboard/shop-energy")
def shop_energy(ctx: Ctx = Depends(viewer)):
    frame = read_company_dataset(ctx.company_id, "shop_energy_readings.csv")
    cols = ["paint_shop_kwh", "body_shop_kwh", "press_shop_kwh", "assembly_shop_kwh", "utilities_kwh"]
    grouped = frame.groupby("month_number")[cols].sum().round(1).reset_index()
    return records(grouped)


@router.get("/dashboard/daily-emissions")
def daily_emissions(month_number: int = Query(default=1, ge=1, le=60), ctx: Ctx = Depends(viewer)):
    frame = read_company_dataset(ctx.company_id, "daily_carbon_emissions.csv")
    frame = frame[frame["month_number"] == month_number]
    return records(frame[["day_in_month", "date", "claimed_total_kgco2e", "verified_total_kgco2e",
                         "emission_discrepancy_percent"]].round(2))


@router.get("/trust/monthly-summary")
def trust_summary(ctx: Ctx = Depends(viewer)):
    _, summary = get_company_trust_analysis(ctx.company_id)
    return records(summary)


@router.get("/trust/timeline")
def trust_timeline(month_number: int = Query(default=1, ge=1, le=60), points: int = Query(default=240, ge=20, le=1000),
                   ctx: Ctx = Depends(viewer)):
    analysis, _ = get_company_trust_analysis(ctx.company_id)
    part = analysis[analysis["month_number"] == month_number]
    step = max(1, len(part) // points)
    part = part.iloc[::step]
    cols = ["timestamp", "Usage_kWh", "main_incomer_meter_kwh", "static_fused_kwh", "dynamic_fused_kwh",
            "main_meter_trust", "trust_state", "fault_detected"]
    return records(part[cols])
