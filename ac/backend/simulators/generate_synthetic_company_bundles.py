from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_DIR = PROJECT_ROOT / "datasets" / "generated"
DEFAULT_OUTPUT_DIR = DEFAULT_SOURCE_DIR / "company_bundles"

DATASET_FILES = (
    "real_industrial_foundation.csv",
    "plant_meter_readings.csv",
    "shop_energy_readings.csv",
    "production_records.csv",
    "fuel_consumption.csv",
    "historical_scd40_readings.csv",
    "calibration_events.csv",
    "maintenance_events.csv",
    "trust_lifecycle_events.csv",
    "emission_factors.csv",
    "daily_carbon_emissions.csv",
    "monthly_carbon_claims.csv",
)

COMPANIES = (
    {
        "company_id": "sim-northstar-mobility",
        "claim_bias_percent": {}, "calibration_overrides": {},
        "legal_name": "Northstar Mobility Works",
        "city": "Hamilton",
        "state": "Ontario",
        "energy_scale": 0.86,
        "co2_offset_ppm": -18.0,
    },
    {
        "company_id": "sim-ironwood-automotive",
        "claim_bias_percent": {2: 9.0, 3: -4.0}, "calibration_overrides": {},
        "legal_name": "Ironwood Automotive Group",
        "city": "Windsor",
        "state": "Ontario",
        "energy_scale": 1.12,
        "co2_offset_ppm": 24.0,
    },
    {
        "company_id": "sim-crestline-motors",
        "claim_bias_percent": {1: -6.5, 4: 12.0}, "calibration_overrides": {"MTR-MAIN-001": "2026-04-15"},
        "legal_name": "Crestline Motor Manufacturing",
        "city": "Detroit",
        "state": "Michigan",
        "energy_scale": 0.94,
        "co2_offset_ppm": 8.0,
    },
    {
        "company_id": "sim-redwood-vehicle-systems",
        "claim_bias_percent": {2: -17.0, 5: 8.5}, "calibration_overrides": {"SCD40-PAINT-001": "2026-03-15"},
        "legal_name": "Redwood Vehicle Systems",
        "city": "Toledo",
        "state": "Ohio",
        "energy_scale": 1.21,
        "co2_offset_ppm": -9.0,
    },
    {
        "company_id": "sim-summit-auto-works",
        "claim_bias_percent": {1: 2.5, 3: 9.0, 5: -2.0}, "calibration_overrides": {},
        "legal_name": "Summit Auto Works",
        "city": "Kitchener",
        "state": "Ontario",
        "energy_scale": 1.04,
        "co2_offset_ppm": 15.0,
    },
)


def _scaled_columns(filename: str, columns: list[str]) -> list[str]:
    if filename in {"plant_meter_readings.csv", "shop_energy_readings.csv"}:
        return [
            column
            for column in columns
            if column == "Usage_kWh" or column.endswith("_kwh")
        ]
    if filename in {
        "real_industrial_foundation.csv",
        "production_records.csv",
    }:
        selected = [
            column
            for column in columns
            if column.endswith("_kwh") or column == "Usage_kWh"
        ]
        if filename == "production_records.csv":
            selected.extend(
                column
                for column in (
                    "planned_vehicles",
                    "vehicles_produced",
                    "accepted_units",
                    "rejected_units",
                )
                if column in columns
            )
        return selected
    if filename == "fuel_consumption.csv":
        return [
            column
            for column in ("natural_gas_scm", "diesel_litres")
            if column in columns
        ]
    if filename in {"daily_carbon_emissions.csv", "monthly_carbon_claims.csv"}:
        return [
            column
            for column in columns
            if (
                column.endswith("_kwh")
                or column.endswith("_scm")
                or column.endswith("_litres")
                or (
                    "kgco2" in column.lower()
                    and "intensity" not in column.lower()
                )
            )
        ] + [
            column
            for column in ("vehicles_produced", "accepted_units")
            if column in columns
        ]
    return []


def _scale_values(frame: pd.DataFrame, columns: list[str], factor: float) -> None:
    for column in columns:
        if column in frame.columns:
            scaled = pd.to_numeric(frame[column]) * factor
            if column in {
                "planned_vehicles",
                "vehicles_produced",
                "accepted_units",
                "rejected_units",
            }:
                frame[column] = scaled.round().astype("int64")
            else:
                frame[column] = scaled.round(6)



def _apply_claim_bias(frame: pd.DataFrame, filename: str, bias: dict) -> None:
    """Make each company's claims differ: scale claimed values for chosen months."""
    if not bias or filename not in {"monthly_carbon_claims.csv", "daily_carbon_emissions.csv"}:
        return
    claimed_cols = [
        c for c in frame.columns
        if c.startswith("claimed_") and (c.endswith("_kwh") or "kgco2" in c.lower())
    ]
    for month, pct in bias.items():
        mask = frame["month_number"] == month
        for column in claimed_cols:
            frame.loc[mask, column] = (frame.loc[mask, column] * (1 + pct / 100.0)).round(6)
    verified = "verified_total_kgco2e"
    if filename == "monthly_carbon_claims.csv":
        diff = (frame[verified] - frame["claimed_total_kgco2e"]).round(6)
        frame["claim_discrepancy_kgco2e"] = diff
        frame["claim_discrepancy_percent"] = (diff.abs() / frame[verified] * 100).round(6)
        def rec(row):
            if row["claim_discrepancy_percent"] <= 1.0:
                return "APPROVAL_AFTER_PROBATION_REVIEW" if row["repair_events"] > 0 else "RECOMMEND_APPROVAL"
            return "MANUAL_REVIEW"
        frame["verification_recommendation"] = frame.apply(rec, axis=1)
    else:
        diff = (frame[verified] - frame["claimed_total_kgco2e"]).round(6)
        frame["emission_discrepancy_kgco2e"] = diff
        frame["emission_discrepancy_percent"] = (diff.abs() / frame[verified] * 100).round(6)


def _apply_calibration_overrides(frame: pd.DataFrame, overrides: dict) -> None:
    for source_suffix, valid_until in overrides.items():
        mask = frame["source_id"].astype(str).str.endswith(source_suffix)
        frame.loc[mask, "valid_until"] = valid_until

def _make_company_dataset(
    frame: pd.DataFrame,
    filename: str,
    company: dict[str, Any],
) -> pd.DataFrame:
    result = frame.copy()
    _scale_values(
        result,
        _scaled_columns(filename, list(result.columns)),
        float(company["energy_scale"]),
    )

    if filename == "historical_scd40_readings.csv":
        result["co2_ppm"] = (
            pd.to_numeric(result["co2_ppm"])
            + float(company["co2_offset_ppm"])
        ).clip(lower=400, upper=2000).round(2)
        result["sensor_id"] = f"SCD40-{company['company_id']}"
        result["location"] = f"{company['legal_name']} Assembly Plant"

    for column in ("source_id", "sensor_id"):
        if (
            column in result.columns
            and filename != "historical_scd40_readings.csv"
        ):
            result[column] = result[column].map(
                lambda value: f"{company['company_id']}-{value}"
            )

    for column in ("claim_id", "verification_cycle_id", "event_id"):
        if column in result.columns:
            result[column] = result[column].map(
                lambda value: f"{company['company_id']}-{value}"
            )

    _apply_claim_bias(result, filename, company.get("claim_bias_percent", {}))
    if filename == "calibration_events.csv":
        _apply_calibration_overrides(result, company.get("calibration_overrides", {}))

    if filename != "emission_factors.csv":
        for column in ("data_origin", "shop_data_origin"):
            if column in result.columns:
                result[column] = "SYNTHETIC_COMPANY_SIMULATION"

    return result


def generate_company_bundles(
    source_dir: Path,
    output_dir: Path,
) -> list[dict[str, Any]]:
    if not (source_dir / "monthly_carbon_claims.csv").is_file():
        raise FileNotFoundError(
            "The base five-month dataset package is incomplete; missing: "
            "monthly_carbon_claims.csv"
        )
    missing = [name for name in DATASET_FILES if not (source_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(
            "The base five-month dataset package is incomplete; missing: "
            + ", ".join(missing)
        )

    base_frames = {
        filename: pd.read_csv(source_dir / filename)
        for filename in DATASET_FILES
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = []

    for company in COMPANIES:
        company_dir = output_dir / company["company_id"]
        company_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "company": {
                key: value
                for key, value in company.items()
                if key not in {"energy_scale", "co2_offset_ppm", "claim_bias_percent", "calibration_overrides"}
            },
            "industry": "Automobile manufacturing",
            "data_origin": "SYNTHETIC_SIMULATION",
            "reference": "AgentCarbon five-month demonstration dataset",
            "notice": (
                "Fictional company and simulated measurements. "
                "Not actual company disclosures or operational records."
            ),
            "months": sorted(
                int(value)
                for value in base_frames["monthly_carbon_claims.csv"][
                    "month_number"
                ].unique()
            ),
            "datasets": {},
        }

        for filename, base_frame in base_frames.items():
            transformed = _make_company_dataset(base_frame, filename, company)
            destination = company_dir / filename
            transformed.to_csv(destination, index=False)
            manifest["datasets"][filename] = {
                "rows": len(transformed),
                "columns": list(transformed.columns),
                "path": filename,
            }

        manifest_path = company_dir / "company_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        generated.append(
            {
                "company_id": company["company_id"],
                "legal_name": company["legal_name"],
                "directory": company_dir.name,
                "dataset_count": len(DATASET_FILES),
                "months": manifest["months"],
            }
        )

    (output_dir / "manifest.json").write_text(
        json.dumps(
            {
                "data_origin": "SYNTHETIC_SIMULATION",
                "company_count": len(generated),
                "companies": generated,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    archive_path = output_dir.with_suffix(".zip")
    with ZipFile(
        archive_path,
        "w",
        compression=ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:
        archive.write(output_dir / "manifest.json", "manifest.json")
        for company in COMPANIES:
            company_dir = output_dir / company["company_id"]
            archive.write(
                company_dir / "company_manifest.json",
                f"{company_dir.name}/company_manifest.json",
            )
            for filename in DATASET_FILES:
                archive.write(
                    company_dir / filename,
                    f"{company_dir.name}/{filename}",
                )
    return generated


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate five explicitly synthetic automobile-company data "
            "bundles from the existing five-month AgentCarbon demonstration."
        )
    )
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    companies = generate_company_bundles(args.source_dir, args.output_dir)
    print(
        f"Generated {len(companies)} synthetic company bundles "
        f"under {args.output_dir}"
    )
    for company in companies:
        print(
            f"- {company['legal_name']}: {company['dataset_count']} datasets, "
            f"months {company['months']}"
        )
    print("All generated records are simulations, not real company data.")


if __name__ == "__main__":
    main()
