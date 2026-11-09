"""Credit arithmetic shared by the operator form and the verification agents.

Credits earned in a month = (baseline emissions for the verified production - verified emissions) / 1000.
The baseline intensity is 5% above the plant's first verified month (Jan 2026), so efficiency gains
over time earn credits. All figures are tCO2e unless stated.
"""
from __future__ import annotations

from typing import Any

from app.services.company_data import company_claims, read_company_dataset

BASELINE_MARGIN = 1.05


def baseline_intensity(company_id: str) -> float:
    first = company_claims(company_id).iloc[0]
    return float(first["verified_intensity_kgco2e_per_vehicle"]) * BASELINE_MARGIN


def factors(company_id: str, claim: dict) -> dict[str, float]:
    ef = read_company_dataset(company_id, "emission_factors.csv").set_index("activity_type")["factor_value"]
    scope2 = float(claim["claimed_scope2_kgco2"]) / max(float(claim["claimed_electricity_kwh"]), 1e-9)
    return {"electricity": scope2, "gas": float(ef["NATURAL_GAS"]), "diesel": float(ef["DIESEL"])}


def dataset_values(claim: dict) -> dict[str, float]:
    """What the plant's own systems reported for the month."""
    return {
        "electricity_kwh": float(claim["claimed_electricity_kwh"]),
        "production_units": int(claim["vehicles_produced"]),
        "natural_gas_scm": float(claim["natural_gas_scm"]),
        "diesel_litres": float(claim["diesel_litres"]),
    }


def declared_emissions(company_id: str, claim: dict, declared: dict[str, Any]) -> float:
    f = factors(company_id, claim)
    return (float(declared["electricity_kwh"]) * f["electricity"]
            + float(declared["natural_gas_scm"]) * f["gas"]
            + float(declared["diesel_litres"]) * f["diesel"])


def credits_for(company_id: str, production_units: float, emissions_kg: float) -> float:
    return max(0.0, baseline_intensity(company_id) * production_units - emissions_kg) / 1000.0


def prefill(company_id: str, claim: dict) -> dict[str, Any]:
    """Suggested form values: the plant's own reported figures and the credits they imply."""
    d = dataset_values(claim)
    total = declared_emissions(company_id, claim, d)
    return {**d, "expected_credits_tco2e": round(credits_for(company_id, d["production_units"], total), 2)}


def evaluate(company_id: str, claim: dict, declared: dict[str, Any], expected_credits: float) -> dict[str, Any]:
    verified_total = float(claim["verified_total_kgco2e"])
    ds = dataset_values(claim)
    supported = credits_for(company_id, ds["production_units"], verified_total)
    if expected_credits <= supported * 1.0 + 1e-9:
        over = 0.0
    elif supported < 0.5:
        over = 999.0 if expected_credits > 0.5 else 0.0
    else:
        over = (expected_credits - supported) / supported * 100.0
    return {
        "baseline_intensity_kgco2e_per_vehicle": round(baseline_intensity(company_id), 3),
        "expected_credits_tco2e": round(float(expected_credits), 2),
        "supported_credits_tco2e": round(supported, 2),
        "overstatement_percent": round(over, 2),
        "approvable_credits_tco2e": round(min(float(expected_credits), supported), 2),
    }


def variance_percent(declared: float, reference: float) -> float:
    return abs(declared - reference) / reference * 100.0 if reference else 0.0
