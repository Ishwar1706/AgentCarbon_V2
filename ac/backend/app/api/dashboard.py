"""Company dashboards: overview, monthly comparison, trust, energy (all company-scoped, calendar months)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.access_control import AuditorDecision
from app.models.verification import VerificationRun
from app.models.workflows import MonthlyRequest
from app.services import credits, periods, sensor_rollup
from app.services.company_access import ALL_VIEWERS, Ctx, claim_for_period, company_context
from app.services.company_data import company_claims, read_company_dataset, records
from app.services.company_trust_service import get_company_trust_analysis

router = APIRouter(tags=["dashboard"])
viewer = company_context(*ALL_VIEWERS, require_dataset=True)
DEFAULT_PERIOD = periods.DATASET_PERIODS[-1]


def _no_data(period: str) -> dict:
    return {"available": False, "period": period, "label": periods.label(period),
            "message": f"No data available for {periods.label(period)}."}


def _latest_run(db: Session, company_id: str, claim_id: str):
    return db.scalar(select(VerificationRun).where(
        VerificationRun.claim_id == claim_id, VerificationRun.company_id == company_id,
        VerificationRun.status == "COMPLETED").order_by(VerificationRun.created_at.desc()))


def _claim_rows(db: Session, company_id: str) -> list[dict]:
    reqs = {r.claim_id: r for r in db.scalars(select(MonthlyRequest).where(MonthlyRequest.company_id == company_id))}
    out = []
    for c in records(company_claims(company_id)):
        period = periods.from_month_number(int(c["month_number"]))
        run = _latest_run(db, company_id, c["claim_id"])
        decision = db.scalar(select(AuditorDecision).where(
            AuditorDecision.claim_id == c["claim_id"], AuditorDecision.company_id == company_id
        ).order_by(AuditorDecision.decided_at.desc(), AuditorDecision.id.desc()))
        req = reqs.get(c["claim_id"])
        out.append({
            "claim_id": c["claim_id"], "period": period, "label": periods.label(period),
            "month_number": int(c["month_number"]),
            "request_status": req.status if req else "NOT_STARTED",
            "plant_reported_emissions_kgco2e": c["claimed_total_kgco2e"],
            "verified_total_kgco2e": c["verified_total_kgco2e"], "discrepancy_percent": c["claim_discrepancy_percent"],
            "expected_credits_tco2e": req.expected_credits_tco2e if req else None,
            "latest_run_id": run.run_id if run else None,
            "recommendation": run.final_recommendation if run else None,
            "execution_mode": run.execution_mode if run else None,
            "auditor_decision": decision.decision if decision else None,
        })
    return out


@router.get("/dashboard/claims")
def claims(ctx: Ctx = Depends(viewer), db: Session = Depends(get_db)):
    return _claim_rows(db, ctx.company_id)


@router.get("/dashboard/monthly-comparison")
def monthly_comparison(ctx: Ctx = Depends(viewer), db: Session = Depends(get_db)):
    _, trust = get_company_trust_analysis(ctx.company_id)
    trust_by_month = {int(r["month_number"]): r for r in records(trust)}
    sensors = {s["period"]: s for s in sensor_rollup.list_period_summaries(db, ctx.company_id)}
    out = []
    for c in records(company_claims(ctx.company_id)):
        m = int(c["month_number"])
        period = periods.from_month_number(m)
        t, s = trust_by_month.get(m, {}), sensors.get(period, {})
        out.append({
            "period": period, "label": periods.label(period), "scenario": c["month_scenario"],
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
def overview(period: str = Query(default=DEFAULT_PERIOD), ctx: Ctx = Depends(viewer), db: Session = Depends(get_db)):
    periods.valid(period)
    claim = claim_for_period(ctx.company_id, period)
    if claim is None:
        return _no_data(period)
    req = db.scalar(select(MonthlyRequest).where(MonthlyRequest.claim_id == claim["claim_id"]))
    if req:
        declared = {"electricity_kwh": req.declared_electricity_kwh, "production_units": req.declared_production_units,
                    "natural_gas_scm": req.declared_natural_gas_scm, "diesel_litres": req.declared_diesel_litres}
        expected = req.expected_credits_tco2e
    else:
        declared = credits.dataset_values(claim)
        expected = credits.prefill(ctx.company_id, claim)["expected_credits_tco2e"]
    claimed_total = credits.declared_emissions(ctx.company_id, claim, declared)
    verified = float(claim["verified_total_kgco2e"])
    month = int(claim["month_number"])
    _, trust = get_company_trust_analysis(ctx.company_id)
    t = records(trust[trust["month_number"] == month])
    sensors = sensor_rollup.get_period_summary(db, ctx.company_id, period)
    rows = _claim_rows(db, ctx.company_id)
    run = _latest_run(db, ctx.company_id, claim["claim_id"])
    return {
        "available": True, "period": period, "label": periods.label(period),
        "company": {"company_id": ctx.company_id, "legal_name": ctx.company.legal_name},
        "claim": {"claim_id": claim["claim_id"], "request_status": req.status if req else "NOT_STARTED",
                  "claimed_total_kgco2e": round(claimed_total, 2), "verified_total_kgco2e": round(verified, 2),
                  "discrepancy_percent": round(abs(verified - claimed_total) / verified * 100, 3),
                  "vehicles_produced": int(declared["production_units"]),
                  "recommendation": run.final_recommendation if run else None},
        "credits": credits.evaluate(ctx.company_id, claim, declared, float(expected)),
        "trust": t[0] if t else None,
        "sensors": {k: v for k, v in (sensors or {}).items() if k != "sensors"} or None,
        "totals": {"periods_with_data": len(rows), "approved": sum(r["request_status"] == "APPROVED" for r in rows),
                   "awaiting_review": sum(r["request_status"] == "SUBMITTED" for r in rows)},
    }


@router.get("/dashboard/shop-energy")
def shop_energy(ctx: Ctx = Depends(viewer)):
    frame = read_company_dataset(ctx.company_id, "shop_energy_readings.csv")
    cols = ["paint_shop_kwh", "body_shop_kwh", "press_shop_kwh", "assembly_shop_kwh", "utilities_kwh"]
    grouped = frame.groupby("month_number")[cols].sum().round(1).reset_index()
    grouped["period"] = grouped["month_number"].map(lambda m: periods.from_month_number(int(m)))
    grouped["label"] = grouped["period"].map(periods.label)
    return records(grouped)


@router.get("/dashboard/daily-emissions")
def daily_emissions(period: str = Query(default=DEFAULT_PERIOD), ctx: Ctx = Depends(viewer)):
    periods.valid(period)
    month = periods.month_number(period)
    if month is None:
        return []
    frame = read_company_dataset(ctx.company_id, "daily_carbon_emissions.csv")
    frame = frame[frame["month_number"] == month]
    return records(frame[["day_in_month", "date", "claimed_total_kgco2e", "verified_total_kgco2e",
                         "emission_discrepancy_percent"]].round(2))


@router.get("/trust/monthly-summary")
def trust_summary(ctx: Ctx = Depends(viewer)):
    _, summary = get_company_trust_analysis(ctx.company_id)
    rows = records(summary)
    for r in rows:
        r["period"] = periods.from_month_number(int(r["month_number"]))
        r["label"] = periods.label(r["period"])
    return rows


@router.get("/trust/timeline")
def trust_timeline(period: str = Query(default=DEFAULT_PERIOD), points: int = Query(default=240, ge=20, le=1000),
                   ctx: Ctx = Depends(viewer)):
    periods.valid(period)
    month = periods.month_number(period)
    if month is None:
        return []
    analysis, _ = get_company_trust_analysis(ctx.company_id)
    part = analysis[analysis["month_number"] == month]
    step = max(1, len(part) // points)
    part = part.iloc[::step]
    cols = ["timestamp", "Usage_kWh", "main_incomer_meter_kwh", "static_fused_kwh", "dynamic_fused_kwh",
            "main_meter_trust", "trust_state", "fault_detected"]
    return records(part[cols])
