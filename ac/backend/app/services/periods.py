"""Calendar-month helpers. A *period* is a string like "2026-03" (March 2026)."""
from __future__ import annotations

import calendar
import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

STEP_MINUTES = 15
STEPS_PER_DAY = 96
DATASET_YEAR = 2026
DATASET_PERIODS = [f"{DATASET_YEAR}-{m:02d}" for m in range(1, 6)]  # Jan-May 2026 have full datasets
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_PERIOD = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_CLAIM = re.compile(r"-CLAIM-(\d{4})-(\d{2})$")


def valid(period: str) -> str:
    if not period or not _PERIOD.match(period):
        raise HTTPException(400, "period must look like 2026-03 (YYYY-MM).")
    return period


def parts(period: str) -> tuple[int, int]:
    m = _PERIOD.match(period)
    return int(m.group(1)), int(m.group(2))


def label(period: str) -> str:
    year, month = parts(period)
    return f"{MONTH_NAMES[month - 1]} {year}"


def month_number(period: str) -> int | None:
    """1..5 for the dataset months (Jan-May 2026), otherwise None."""
    return DATASET_PERIODS.index(period) + 1 if period in DATASET_PERIODS else None


def from_month_number(n: int) -> str:
    return DATASET_PERIODS[n - 1]


def days(period: str) -> int:
    year, month = parts(period)
    return calendar.monthrange(year, month)[1]


def steps(period: str) -> int:
    return days(period) * STEPS_PER_DAY


def start(period: str) -> datetime:
    year, month = parts(period)
    return datetime(year, month, 1, tzinfo=timezone.utc)


def end(period: str) -> datetime:
    """Last 15-minute slot of the month."""
    return start(period) + timedelta(days=days(period)) - timedelta(minutes=STEP_MINUTES)


def of(ts: datetime) -> str:
    return f"{ts.year}-{ts.month:02d}"


def next_period(period: str) -> str:
    year, month = parts(period)
    return f"{year + (month == 12)}-{1 if month == 12 else month + 1:02d}"


def claim_id(company_id: str, period: str) -> str:
    year, month = parts(period)
    return f"{company_id}-CLAIM-{year}-{month:02d}"


def period_from_claim(claim: str) -> str | None:
    m = _CLAIM.search(claim or "")
    return f"{m.group(1)}-{m.group(2)}" if m else None
