from __future__ import annotations

from functools import lru_cache

import pandas as pd

from app.services.company_data import read_company_dataset
from app.services.trust_engine import DynamicTrustEngine


@lru_cache(maxsize=8)
def get_company_trust_analysis(company_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Dynamic trust analysis of the company's four electricity meters (cached, read-only)."""
    readings = read_company_dataset(company_id, "plant_meter_readings.csv")
    analysis = DynamicTrustEngine().analyze(readings)
    return analysis, DynamicTrustEngine.summarize(analysis)
