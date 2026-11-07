from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SIMULATOR_DIR = PROJECT_ROOT / "backend" / "simulators"
SOURCE_FILE = PROJECT_ROOT / "datasets" / "source" / "Steel_industry_data.csv"
GENERATED_DIR = PROJECT_ROOT / "datasets" / "generated"
MANIFEST_FILE = GENERATED_DIR / "dataset_manifest.json"

GENERATOR_SCRIPTS = [
    "five_month_dataset_generator.py",
    "virtual_meter_generator.py",
    "shop_energy_generator.py",
    "daily_operations_generator.py",
    "historical_scd40_generator.py",
    "evidence_event_generator.py",
    "carbon_claim_generator.py",
]

DATASET_METADATA = {
    "real_industrial_foundation.csv": {
        "data_origin": "PUBLIC_REAL_DATA",
        "description": "Cleaned and remapped five-month industrial energy foundation.",
        "expected_rows": 14_400,
    },
    "plant_meter_readings.csv": {
        "data_origin": "CONTROLLED_SIMULATION",
        "description": "Four synchronized plant-level electricity meter streams and attack labels.",
        "expected_rows": 14_400,
    },
    "shop_energy_readings.csv": {
        "data_origin": "CONTROLLED_SIMULATION",
        "description": "Shop-wise allocation reconciled to real plant electricity usage.",
        "expected_rows": 14_400,
    },
    "production_records.csv": {
        "data_origin": "CONTROLLED_SIMULATION",
        "description": "Daily production records derived from the real energy pattern.",
        "expected_rows": 150,
    },
    "fuel_consumption.csv": {
        "data_origin": "CONTROLLED_SIMULATION",
        "description": "Daily natural-gas and diesel activity data.",
        "expected_rows": 150,
    },
    "historical_scd40_readings.csv": {
        "data_origin": "SIMULATED_HARDWARE",
        "description": "Historical SCD40-compatible CO2, temperature, and humidity stream.",
        "expected_rows": 14_400,
    },
    "calibration_events.csv": {
        "data_origin": "SYNTHETIC_DOCUMENT",
        "description": "Calibration evidence for meters and the SCD40 prototype sensor.",
        "expected_rows": 5,
    },
    "maintenance_events.csv": {
        "data_origin": "SYNTHETIC_DOCUMENT",
        "description": "Investigation, repair, and sensor-inspection work-order events.",
        "expected_rows": 3,
    },
    "trust_lifecycle_events.csv": {
        "data_origin": "SYSTEM_DERIVED",
        "description": "Persistent main-meter trust-state transitions.",
        "expected_rows": 6,
    },
    "emission_factors.csv": {
        "data_origin": "CONFIGURATION_REGISTRY",
        "description": "Versioned electricity, natural-gas, and diesel emission factors.",
        "expected_rows": 3,
    },
    "daily_carbon_emissions.csv": {
        "data_origin": "SYSTEM_DERIVED",
        "description": "Daily Scope 1, claimed Scope 2, and verified Scope 2 calculations.",
        "expected_rows": 150,
    },
    "monthly_carbon_claims.csv": {
        "data_origin": "SYSTEM_DERIVED",
        "description": "Five monthly synchronized claims and verification recommendations.",
        "expected_rows": 5,
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_prerequisites() -> None:
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(
            "The original steel-industry CSV is missing. "
            f"Expected: {SOURCE_FILE}"
        )

    missing_scripts = [
        script_name
        for script_name in GENERATOR_SCRIPTS
        if not (SIMULATOR_DIR / script_name).exists()
    ]
    if missing_scripts:
        raise FileNotFoundError(
            "Generator scripts are missing: " + ", ".join(missing_scripts)
        )


def run_generators() -> None:
    print("=" * 72)
    print("AGENTCARBON MASTER DATASET GENERATOR")
    print("=" * 72)

    for position, script_name in enumerate(GENERATOR_SCRIPTS, start=1):
        script_path = SIMULATOR_DIR / script_name
        print()
        print(f"[{position}/{len(GENERATOR_SCRIPTS)}] Running {script_name}")
        print("-" * 72)

        completed = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=PROJECT_ROOT,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"Generator failed: {script_name} "
                f"with exit code {completed.returncode}."
            )


def inspect_csv(path: Path, expected_rows: int) -> dict:
    dataframe = pd.read_csv(path)
    row_count = int(len(dataframe))
    column_count = int(len(dataframe.columns))
    missing_values = int(dataframe.isna().sum().sum())

    if row_count != expected_rows:
        raise ValueError(
            f"{path.name} contains {row_count} rows; "
            f"expected {expected_rows}."
        )
    if missing_values != 0:
        raise ValueError(
            f"{path.name} contains {missing_values} missing values."
        )

    return {
        "filename": path.name,
        "record_count": row_count,
        "column_count": column_count,
        "missing_value_count": missing_values,
        "file_size_bytes": int(path.stat().st_size),
        "sha256": sha256_file(path),
    }


def create_manifest() -> dict:
    dataset_entries = []

    for filename, metadata in DATASET_METADATA.items():
        dataset_path = GENERATED_DIR / filename
        if not dataset_path.exists():
            raise FileNotFoundError(
                f"Expected generated dataset is missing: {dataset_path}"
            )

        entry = inspect_csv(
            dataset_path,
            expected_rows=int(metadata["expected_rows"]),
        )
        entry["data_origin"] = metadata["data_origin"]
        entry["description"] = metadata["description"]
        dataset_entries.append(entry)

    manifest = {
        "manifest_version": "1.0.0",
        "project": "AgentCarbon",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_dataset": {
            "filename": SOURCE_FILE.name,
            "repository_status": "NOT_COMMITTED",
            "sha256": sha256_file(SOURCE_FILE),
        },
        "generation_order": GENERATOR_SCRIPTS,
        "dataset_count": len(dataset_entries),
        "datasets": dataset_entries,
    }

    MANIFEST_FILE.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return manifest


def display_summary(manifest: dict) -> None:
    print()
    print("=" * 72)
    print("FINAL DATASET PACKAGE SUMMARY")
    print("=" * 72)
    print("Dataset files:", manifest["dataset_count"])

    for entry in manifest["datasets"]:
        print(
            f"{entry['filename']}: "
            f"rows={entry['record_count']}, "
            f"columns={entry['column_count']}, "
            f"origin={entry['data_origin']}, "
            f"sha256={entry['sha256'][:12]}..."
        )

    print()
    print("Manifest created:")
    print(MANIFEST_FILE)


def main() -> None:
    verify_prerequisites()
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    run_generators()
    manifest = create_manifest()
    display_summary(manifest)

    print()
    print("=" * 72)
    print("AGENTCARBON DATASET PIPELINE COMPLETED SUCCESSFULLY")
    print("=" * 72)


if __name__ == "__main__":
    main()
