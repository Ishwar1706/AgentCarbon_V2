"""Builds the company-specific evidence packet every agent reasons over."""
from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.workflows import InfoRequest, MonthlyRequest
from app.services import checklist as checklist_service
from app.services import credits, periods, sensor_rollup
from app.services.company_data import get_claim, read_company_dataset, records
from app.services.company_trust_service import get_company_trust_analysis


def sha256_json(data: Any) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _suffix(source_id: str) -> str:
    for key in ("MTR-MAIN-001", "MTR-UTILITY-001", "MTR-EMS-001", "MTR-REFERENCE-001", "SCD40-PAINT-001"):
        if str(source_id).endswith(key):
            return key
    return str(source_id)


def build_packet(db: Session, company_id: str, claim_id: str) -> dict[str, Any]:
    claim = get_claim(company_id, claim_id)
    if claim is None:
        raise ValueError("No data available for this month.")
    month = int(claim["month_number"])
    period = periods.from_month_number(month)
    p_start, p_end = date.fromisoformat(claim["period_start"]), date.fromisoformat(claim["period_end"])
    request = db.scalar(select(MonthlyRequest).where(MonthlyRequest.claim_id == claim_id))

    # ---- what the operator declared (or, before they submit, the plant's own figures)
    ds = credits.dataset_values(claim)
    if request and request.status != "DRAFT":
        declared = {"electricity_kwh": request.declared_electricity_kwh, "production_units": request.declared_production_units,
                    "natural_gas_scm": request.declared_natural_gas_scm, "diesel_litres": request.declared_diesel_litres}
        expected_credits, source = request.expected_credits_tco2e, "OPERATOR_FORM"
    else:
        declared, source = dict(ds), "DATASET_PREFILL"
        expected_credits = credits.prefill(company_id, claim)["expected_credits_tco2e"]
    declared_total = credits.declared_emissions(company_id, claim, declared)
    factors = credits.factors(company_id, claim)
    verified_total = float(claim["verified_total_kgco2e"])
    verified_elec = float(claim["verified_electricity_kwh"])
    diff = verified_total - declared_total
    pct = abs(diff) / verified_total * 100 if verified_total else 0.0
    variances = {
        "electricity_vs_verified_percent": round(credits.variance_percent(declared["electricity_kwh"], verified_elec), 2),
        "production_vs_plant_records_percent": round(credits.variance_percent(declared["production_units"], ds["production_units"]), 2),
        "natural_gas_vs_plant_records_percent": round(credits.variance_percent(declared["natural_gas_scm"], ds["natural_gas_scm"]), 2),
        "diesel_vs_plant_records_percent": round(credits.variance_percent(declared["diesel_litres"], ds["diesel_litres"]), 2),
    }
    claim_block = {
        "claim_id": claim_id, "period": period, "label": periods.label(period), "month_number": month,
        "period_start": claim["period_start"], "period_end": claim["period_end"],
        "claimed_total_kgco2e": round(declared_total, 2), "verified_total_kgco2e": round(verified_total, 2),
        "discrepancy_kgco2e": round(diff, 2), "discrepancy_percent": round(pct, 3),
        "direction": "MATCHED" if pct <= 1 else ("UNDER_REPORTED" if diff > 0 else "OVER_REPORTED"),
        "claimed_scope2_kgco2": round(declared["electricity_kwh"] * factors["electricity"], 2),
        "verified_scope2_kgco2": round(float(claim["verified_scope2_kgco2"]), 2),
        "scope1_total_kgco2e": round(declared["natural_gas_scm"] * factors["gas"] + declared["diesel_litres"] * factors["diesel"], 2),
        "vehicles_produced": int(declared["production_units"]),
        "verified_intensity_kgco2e_per_vehicle": round(float(claim["verified_intensity_kgco2e_per_vehicle"]), 2),
        "request_status": request.status if request else "NOT_SUBMITTED",
    }
    declared_block = {
        "source": source, **{k: round(float(v), 2) for k, v in declared.items()},
        "plant_records": {k: round(float(v), 2) for k, v in ds.items()},
        "verified_electricity_kwh": round(verified_elec, 2),
        "variances": variances,
        "max_variance_percent": max(variances["production_vs_plant_records_percent"],
                                    variances["natural_gas_vs_plant_records_percent"],
                                    variances["diesel_vs_plant_records_percent"]),
        "operator_notes": (request.notes or "")[:500] if request else "",
    }
    credit_block = credits.evaluate(company_id, claim, declared, float(expected_credits))

    # ---- meter trust (dynamic trust engine over the four electricity meters)
    analysis, summary = get_company_trust_analysis(company_id)
    row = summary[summary["month_number"] == month]
    month_rows = analysis[analysis["month_number"] == month]
    trust_block: dict[str, Any] = {"available": not row.empty}
    if not row.empty:
        r = records(row)[0]
        states = month_rows["trust_state"].value_counts().to_dict()
        trust_block.update({
            "result_count": int(len(month_rows)),
            "static_mae_kwh": r["static_mae_kwh"], "dynamic_mae_kwh": r["dynamic_mae_kwh"],
            "mae_reduction_percent": r["mae_reduction_percent"],
            "minimum_main_meter_trust": r["minimum_main_meter_trust"],
            "final_main_meter_trust": r["final_main_meter_trust"],
            "final_trust_state": str(month_rows["trust_state"].iloc[-1]),
            "trust_state_record_counts": {k: int(v) for k, v in states.items()},
            "fault_detected_records": int(month_rows["fault_detected"].sum()),
            "fault_detected_percent": round(100 * float(month_rows["fault_detected"].mean()), 2),
        })

    # ---- sensor evidence from the sealed/open monthly rollup of simulated sensors
    sensor_summary = sensor_rollup.get_period_summary(db, company_id, period)
    sensor_block: dict[str, Any] = {"available": sensor_summary is not None}
    if sensor_summary:
        base = sensor_rollup.get_period_summary(db, company_id, periods.from_month_number(1))
        base_co2 = base["avg_co2_ppm"] if base else sensor_summary["avg_co2_ppm"]
        sensor_block.update({k: sensor_summary[k] for k in (
            "status", "summary_hash", "sensor_count", "reading_count", "expected_count",
            "completeness_percent", "anomaly_percent", "flagged_sensor_count",
            "mean_sensor_trust", "avg_co2_ppm", "min_co2_ppm", "max_co2_ppm")})
        sensor_block["co2_vs_jan_baseline_percent"] = round(100 * (sensor_summary["avg_co2_ppm"] / base_co2 - 1), 2)
        sensor_block["sensors"] = [{
            k: s[k] for k in ("sensor_id", "zone", "completeness_percent", "avg_co2_ppm",
                              "anomaly_percent", "stuck_count", "drift_percent_per_30d",
                              "trust_score", "health", "failure_reasons")
        } for s in sensor_summary["sensors"]]

    # ---- calibration + maintenance evidence for this exact period
    cal = read_company_dataset(company_id, "calibration_events.csv")
    cal_items = []
    for _, c in cal.iterrows():
        vf, vu = date.fromisoformat(str(c["valid_from"])[:10]), date.fromisoformat(str(c["valid_until"])[:10])
        cal_items.append({
            "source": _suffix(c["source_id"]), "status": c["calibration_status"],
            "valid_from": str(vf), "valid_until": str(vu),
            "covers_full_period": bool(c["calibration_status"] == "VALID" and vf <= p_start and vu >= p_end),
        })
    main_cal = next((c for c in cal_items if c["source"] == "MTR-MAIN-001"), None)
    maint = read_company_dataset(company_id, "maintenance_events.csv")
    maint["d"] = pd.to_datetime(maint["event_timestamp"], utc=True).dt.date
    in_period = maint[(maint["d"] >= p_start) & (maint["d"] <= p_end)]
    maint_items = [{"source": _suffix(m["source_id"]), "event_type": m["event_type"],
                    "date": str(m["d"]), "result": m["result"]} for _, m in in_period.iterrows()]

    check = checklist_service.checklist(db, company_id, claim_id)
    system_cal_ok = bool(main_cal and main_cal["covers_full_period"])
    open_requests = db.scalar(select(func.count()).select_from(InfoRequest).where(
        InfoRequest.claim_id == claim_id, InfoRequest.status == "OPEN")) or 0

    documents_block = {
        "calibration_certificates": cal_items,
        "main_meter_calibration_valid_for_period": system_cal_ok or check["calibration_verified"],
        "calibration_source": "SYSTEM_RECORD" if system_cal_ok else "VERIFIED_UPLOAD" if check["calibration_verified"] else "NONE",
        "valid_certificates_covering_period": sum(c["covers_full_period"] for c in cal_items),
        "maintenance_events_in_period": maint_items,
        "repair_event_in_period": any("REPAIR" in m["event_type"] for m in maint_items),
        "checklist": [{k: s[k] for k in ("slot", "required", "status", "count")} for s in check["slots"]],
        "missing_required_documents": check["missing_required"],
        "uploaded_documents_total": check["documents_total"],
        "open_information_requests": int(open_requests),
    }
    return {
        "company_id": company_id, "claim": claim_block, "declared": declared_block, "credits": credit_block,
        "trust": trust_block, "sensors": sensor_block, "documents": documents_block,
        "data_notice": "All data is synthetic simulation for demonstration purposes.",
    }
