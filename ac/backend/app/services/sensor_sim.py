"""SCD40 sensor simulation kernels: historical months and live samples."""
from __future__ import annotations

import zlib
from collections import deque
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from app.services import periods

STEP_MINUTES = periods.STEP_MINUTES
STEPS_PER_DAY = periods.STEPS_PER_DAY
STUCK_RUN = 6


def seeded_rng(*parts: Any) -> np.random.Generator:
    return np.random.default_rng(zlib.crc32("|".join(map(str, parts)).encode()))


# ----------------------------------------------------------------- flagging
def flag_frame(frame: pd.DataFrame) -> pd.Series:
    """Vectorised validation of readings (ordered by sequence)."""
    co2, temp, hum = frame["co2_ppm"], frame["temperature_c"], frame["humidity_percent"]
    status = pd.Series("VALID", index=frame.index, dtype=object)
    same = co2.diff().eq(0)
    stuck = same.rolling(STUCK_RUN - 1, min_periods=STUCK_RUN - 1).sum().eq(STUCK_RUN - 1)
    stuck = stuck | stuck.shift(-1, fill_value=False)  # include first sample of the run
    for k in range(1, STUCK_RUN - 1):
        stuck = stuck | stuck.shift(-k, fill_value=False)
    median = co2.rolling(9, center=True, min_periods=3).median()
    spike = (co2 - median).abs() > 600
    status[co2 > 2000] = "HIGH_CO2"
    status[spike] = "SPIKE"
    status[stuck] = "STUCK_VALUE"
    status[(co2 < 380) | (co2 > 5000) | (temp < -10) | (temp > 60) | (hum < 0) | (hum > 100)] = "OUT_OF_RANGE"
    return status


def flag_single(co2: float, temp: float, hum: float, recent: deque, expected: float) -> str:
    if co2 < 380 or co2 > 5000 or temp < -10 or temp > 60 or hum < 0 or hum > 100:
        return "OUT_OF_RANGE"
    if len(recent) >= STUCK_RUN - 1 and all(v == co2 for v in recent):
        return "STUCK_VALUE"
    if abs(co2 - expected) > 600:
        return "SPIKE"
    if co2 > 2000:
        return "HIGH_CO2"
    return "VALID"


# --------------------------------------------------------------- historical
def generate_historical(profile: dict[str, Any], base: pd.DataFrame) -> pd.DataFrame:
    """Five months of 15-minute readings for one sensor, derived from the
    company's SCD40 baseline stream plus a zone factor, noise and planted faults."""
    rng = seeded_rng("hist", profile["sensor_id"])
    n = len(base)
    co2 = base["co2_ppm"].to_numpy(float) * profile["gain"] + profile["offset"] + rng.normal(0, profile["noise"], n)
    temp = base["temperature_c"].to_numpy(float) + profile["temp_offset"] + rng.normal(0, 0.25, n)
    hum = base["humidity_percent"].to_numpy(float) + profile["hum_offset"] + rng.normal(0, 0.8, n)
    scenario = np.array(["NORMAL"] * n, dtype=object)
    keep = np.ones(n, dtype=bool)
    month = base["month_number"].to_numpy(int)

    for fault in profile["faults"]:
        month_start = int(np.argmax(month == fault["month"]))
        i0 = month_start + int(fault["start_day"] * STEPS_PER_DAY)
        i1 = min(n, i0 + int(fault["hours"] * 60 / STEP_MINUTES))
        if i0 >= n or i1 <= i0:
            continue
        kind = fault["kind"]
        if kind == "STUCK":
            co2[i0:i1], temp[i0:i1], hum[i0:i1] = co2[i0], temp[i0], hum[i0]
        elif kind == "DRIFT":  # ramps up, then stays offset until the end of the month
            co2[i0:i1] += np.linspace(0, fault["magnitude"], i1 - i0)
            later = month == fault["month"] + 1
            month_end = int(np.argmax(later)) if later.any() else n
            co2[i1:month_end] += fault["magnitude"]
            scenario[i0:month_end] = "DRIFT"
        elif kind == "SPIKE":
            hit = rng.random(i1 - i0) < 0.12
            co2[i0:i1][hit] = rng.uniform(2300, fault["magnitude"] + 700, hit.sum())
        elif kind == "DROPOUT":
            keep[i0:i1] = False
        scenario[i0:i1] = kind

    co2 = np.where(co2 < 415, 415 + rng.uniform(0, 30, n), co2)  # soft floor above ambient (no flat clipping)
    co2 = np.clip(co2, 380, 5200).round(2)
    frame = pd.DataFrame({
        "timestamp": pd.to_datetime(base["timestamp"], utc=True),
        "sequence_number": base["sequence_number"].to_numpy(int),
        "month_number": month,
        "co2_ppm": co2,
        "temperature_c": temp.round(2),
        "humidity_percent": np.clip(hum, 5, 99).round(2),
        "scenario": scenario,
    })[keep].reset_index(drop=True)
    frame["period"] = frame["timestamp"].dt.strftime("%Y-%m")
    frame = frame.drop(columns=["month_number"])
    frame["validation_status"] = flag_frame(frame)
    frame["device_status"] = "ONLINE"
    frame["data_origin"] = "SIMULATED_HARDWARE"
    return frame


# --------------------------------------------------------------------- live
class LiveBaseline:
    """Hour-of-day CO2/temperature/humidity profile learned from a company's baseline month."""

    def __init__(self, base: pd.DataFrame):
        month1 = base[base["month_number"] == 1].copy()
        hours = pd.to_datetime(month1["timestamp"]).dt.hour
        g = month1.groupby(hours)
        self.co2 = g["co2_ppm"].mean().reindex(range(24)).ffill().bfill().to_numpy()
        self.temp = g["temperature_c"].mean().reindex(range(24)).ffill().bfill().to_numpy()
        self.hum = g["humidity_percent"].mean().reindex(range(24)).ffill().bfill().to_numpy()


class SensorLiveState:
    def __init__(self, profile: dict[str, Any], next_seq: int):
        self.profile = profile
        self.next_seq = next_seq
        self.recent: deque = deque(maxlen=STUCK_RUN - 1)
        self.fault: dict[str, Any] | None = None  # {kind, remaining, magnitude, acc}
        self.last: tuple[float, float, float] | None = None
        self.rng = seeded_rng("live", profile["sensor_id"], next_seq)


def live_reading(state: SensorLiveState, ts: datetime, baseline: LiveBaseline) -> dict[str, Any] | None:
    """Return one reading dict, or None when the device drops out this step."""
    p, rng = state.profile, state.rng
    hour = ts.hour
    expected = baseline.co2[hour] * p["gain"] + p["offset"]
    co2 = expected + rng.normal(0, p["noise"])
    temp = baseline.temp[hour] + p["temp_offset"] + rng.normal(0, 0.25)
    hum = baseline.hum[hour] + p["hum_offset"] + rng.normal(0, 0.8)
    scenario = "NORMAL"
    fault = state.fault
    if fault:
        kind = fault["kind"]
        scenario = kind
        fault["remaining"] -= 1
        if fault["remaining"] <= 0:
            state.fault = None
        if kind in ("DROPOUT", "OFFLINE"):
            return None
        if kind == "STUCK" and state.last:
            co2, temp, hum = state.last
        elif kind == "DRIFT":
            fault["acc"] = fault.get("acc", 0.0) + fault["magnitude"] / max(1, fault["total"])
            co2 += fault["acc"]
        elif kind == "SPIKE" and rng.random() < 0.15:
            co2 = rng.uniform(2300, fault["magnitude"] + 700)
    if co2 < 415:
        co2 = 415 + rng.uniform(0, 30)
    co2, temp, hum = round(float(np.clip(co2, 380, 5200)), 2), round(float(temp), 2), round(float(np.clip(hum, 5, 99)), 2)
    status = flag_single(co2, temp, hum, state.recent, expected)
    state.recent.append(co2)
    state.last = (co2, temp, hum)
    seq = state.next_seq
    state.next_seq += 1
    return {
        "sensor_id": p["sensor_id"], "timestamp": ts, "sequence_number": seq,
        "period": periods.of(ts), "co2_ppm": co2, "temperature_c": temp,
        "humidity_percent": hum, "device_status": "ONLINE",
        "data_origin": "SIMULATED_HARDWARE", "scenario": scenario,
        "validation_status": status,
    }
