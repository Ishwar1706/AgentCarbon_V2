"""Access to the per-company synthetic CSV bundles (claims, meters, events)."""
from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd

from simulators.generate_synthetic_company_bundles import (
    COMPANIES,
    DATASET_FILES,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SOURCE_DIR,
    generate_company_bundles,
)

BUNDLES_DIR = DEFAULT_OUTPUT_DIR
COMPANY_PROFILES = {c["company_id"]: c for c in COMPANIES}
COMPANY_IDS = set(COMPANY_PROFILES)


def ensure_company_bundles() -> None:
    incomplete = not (BUNDLES_DIR / "manifest.json").is_file() or any(
        not (BUNDLES_DIR / cid / name).is_file()
        for cid in COMPANY_IDS
        for name in DATASET_FILES
    )
    if incomplete:
        generate_company_bundles(DEFAULT_SOURCE_DIR, BUNDLES_DIR)
        _read.cache_clear()


def has_company_bundle(company_id: str) -> bool:
    return company_id in COMPANY_IDS and all(
        (BUNDLES_DIR / company_id / name).is_file() for name in DATASET_FILES
    )


@lru_cache(maxsize=80)
def _read(company_id: str, filename: str) -> pd.DataFrame:
    if company_id not in COMPANY_IDS:
        raise ValueError(f"Company has no dataset bundle: {company_id}")
    if filename not in DATASET_FILES:
        raise ValueError(f"Unsupported dataset: {filename}")
    return pd.read_csv(BUNDLES_DIR / company_id / filename)


def read_company_dataset(company_id: str, filename: str) -> pd.DataFrame:
    return _read(company_id, filename).copy()


def records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def company_claims(company_id: str) -> pd.DataFrame:
    return read_company_dataset(company_id, "monthly_carbon_claims.csv").sort_values(
        "month_number"
    )


def get_claim(company_id: str, claim_id: str) -> dict | None:
    frame = company_claims(company_id)
    match = frame[frame["claim_id"] == claim_id]
    return records(match)[0] if not match.empty else None
