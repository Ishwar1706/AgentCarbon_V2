"""Roll raw sensor readings up into complete monthly datasets (and seal them)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.sensor import Sensor, SensorPeriodSeal, SensorReading
from app.services.sensor_sim import (
    STEPS_PER_PERIOD, STEP_MINUTES, month_of, period_end, period_start,
)

DRIFT_FLAG_PERCENT = 8.0


def _hash(data: dict) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def load_period_frame(db: Session, company_id: str, month: int) -> pd.DataFrame:
    rows = db.execute(
        select(
            SensorReading.sensor_id, SensorReading.timestamp, SensorReading.sequence_number,
            SensorReading.co2_ppm, SensorReading.temperature_c, SensorReading.humidity_percent,
            SensorReading.validation_status,
        )
        .join(Sensor, Sensor.sensor_id == SensorReading.sensor_id)
        .where(Sensor.company_id == company_id, SensorReading.month_number == month)
        .order_by(SensorReading.sensor_id, SensorReading.sequence_number)
    ).all()
    frame = pd.DataFrame(rows, columns=[
        "sensor_id", "timestamp", "sequence_number", "co2_ppm",
        "temperature_c", "humidity_percent", "validation_status",
    ])
    if not frame.empty:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame


def _drift_percent(frame: pd.DataFrame) -> dict[str, float]:
    """Sensor-specific drift: slope of the sensor/peer-median ratio over the period (% per 30 days)."""
    if frame.empty or frame["sensor_id"].nunique() < 2:
        return {}
    frame = frame.assign(day=frame["timestamp"].dt.floor("D"))
    daily = frame.groupby(["day", "sensor_id"])["co2_ppm"].mean().unstack()
    if len(daily) < 5:
        return {}
    ratio = daily.div(daily.median(axis=1), axis=0)
    out = {}
    x = np.arange(len(ratio))
    for sensor_id in ratio.columns:
        series = ratio[sensor_id].dropna()
        if len(series) < 5:
            continue
        norm = series / series.median()
        slope = np.polyfit(x[: len(norm)], norm.to_numpy(), 1)[0]
        out[sensor_id] = float(slope * 30 * 100)
    return out


def summarize_period(db: Session, company_id: str, month: int) -> dict | None:
    frame = load_period_frame(db, company_id, month)
    if frame.empty:
        return None
    sensors = db.scalars(select(Sensor).where(Sensor.company_id == company_id)
                         .order_by(Sensor.sensor_id)).all()
    last_ts = frame["timestamp"].max()
    elapsed = int((last_ts - period_start(month)) / pd.Timedelta(minutes=STEP_MINUTES)) + 1
    expected = min(STEPS_PER_PERIOD, max(1, elapsed))
    drift = _drift_percent(frame)
    rows = []
    for sensor in sensors:
        part = frame[frame["sensor_id"] == sensor.sensor_id]
        if part.empty:
            continue
        count = len(part)
        completeness = min(1.0, count / expected)
        counts = part["validation_status"].value_counts().to_dict()
        anomalies = int(count - counts.get("VALID", 0))
        stuck = int(counts.get("STUCK_VALUE", 0))
        spikes = int(counts.get("SPIKE", 0)) + int(counts.get("OUT_OF_RANGE", 0))
        seq = part["sequence_number"].to_numpy()
        longest_gap = int(np.max(np.diff(seq)) - 1) if count > 1 else 0
        drift_pct = round(drift.get(sensor.sensor_id, 0.0), 2)
        anomaly_rate = anomalies / count
        drift_flag = abs(drift_pct) >= DRIFT_FLAG_PERCENT
        trust = float(np.clip(
            0.99 - 0.6 * (1 - completeness) - 2.0 * anomaly_rate
            - (0.15 if stuck >= 6 else 0.0) - (0.25 if drift_flag else 0.0), 0.05, 0.99))
        health = "HEALTHY" if trust >= 0.85 else "WARNING" if trust >= 0.60 else "AT_RISK"
        reasons = []
        if completeness < 0.95:
            reasons.append(f"Data completeness {completeness*100:.1f}% (longest gap {longest_gap} samples).")
        if stuck >= 6:
            reasons.append(f"{stuck} samples with a stuck/frozen CO2 value.")
        if spikes:
            reasons.append(f"{spikes} spike or out-of-range samples.")
        if drift_flag:
            reasons.append(f"Sensor drifts {drift_pct:+.1f}% per 30 days relative to its peer sensors.")
        rows.append({
            "sensor_id": sensor.sensor_id, "zone": sensor.zone, "location": sensor.location,
            "reading_count": count, "expected_count": expected,
            "completeness_percent": round(completeness * 100, 2),
            "avg_co2_ppm": round(float(part["co2_ppm"].mean()), 2),
            "min_co2_ppm": round(float(part["co2_ppm"].min()), 2),
            "max_co2_ppm": round(float(part["co2_ppm"].max()), 2),
            "avg_temperature_c": round(float(part["temperature_c"].mean()), 2),
            "avg_humidity_percent": round(float(part["humidity_percent"].mean()), 2),
            "anomaly_count": anomalies, "anomaly_percent": round(anomaly_rate * 100, 2),
            "stuck_count": stuck, "spike_count": spikes, "longest_gap_samples": longest_gap,
            "drift_percent_per_30d": drift_pct, "trust_score": round(trust, 4),
            "health": health,
            "failure_confidence": round(float(np.clip((1 - trust) * 1.15, 0, 0.99)), 3),
            "failure_reasons": reasons,
        })
    total = sum(r["reading_count"] for r in rows)
    expected_total = sum(r["expected_count"] for r in rows)
    summary = {
        "company_id": company_id, "month_number": month,
        "period_start": period_start(month).isoformat(),
        "period_end": period_end(month).isoformat(),
        "sensor_count": len(rows), "reading_count": total, "expected_count": expected_total,
        "completeness_percent": round(100 * total / expected_total, 2) if expected_total else 0.0,
        "anomaly_percent": round(100 * sum(r["anomaly_count"] for r in rows) / max(total, 1), 2),
        "flagged_sensor_count": sum(r["health"] != "HEALTHY" for r in rows),
        "mean_sensor_trust": round(float(np.mean([r["trust_score"] for r in rows])), 4),
        "avg_co2_ppm": round(float(frame["co2_ppm"].mean()), 2),
        "min_co2_ppm": round(float(frame["co2_ppm"].min()), 2),
        "max_co2_ppm": round(float(frame["co2_ppm"].max()), 2),
        "avg_temperature_c": round(float(frame["temperature_c"].mean()), 2),
        "avg_humidity_percent": round(float(frame["humidity_percent"].mean()), 2),
        "last_timestamp": last_ts.isoformat(),
        "sensors": rows,
    }
    return summary


def seal_period(db: Session, company_id: str, month: int) -> SensorPeriodSeal | None:
    existing = db.scalar(select(SensorPeriodSeal).where(
        SensorPeriodSeal.company_id == company_id, SensorPeriodSeal.month_number == month))
    if existing:
        return existing
    summary = summarize_period(db, company_id, month)
    if summary is None:
        return None
    seal = SensorPeriodSeal(
        company_id=company_id, month_number=month,
        summary_json=json.dumps(summary, sort_keys=True), summary_hash=_hash(summary),
        sealed_at=datetime.now(timezone.utc),
    )
    db.add(seal)
    for row in summary["sensors"]:
        sensor = db.scalar(select(Sensor).where(Sensor.sensor_id == row["sensor_id"]))
        if sensor:
            sensor.current_trust = row["trust_score"]
    db.commit()
    return seal


def get_period_summary(db: Session, company_id: str, month: int) -> dict | None:
    seal = db.scalar(select(SensorPeriodSeal).where(
        SensorPeriodSeal.company_id == company_id, SensorPeriodSeal.month_number == month))
    if seal:
        data = json.loads(seal.summary_json)
        data.update(status="SEALED", summary_hash=seal.summary_hash, sealed_at=seal.sealed_at.isoformat())
        return data
    data = summarize_period(db, company_id, month)
    if data:
        data.update(status="OPEN", summary_hash=None, sealed_at=None)
    return data


def period_numbers(db: Session, company_id: str) -> list[int]:
    rows = db.execute(
        select(SensorReading.month_number).join(Sensor, Sensor.sensor_id == SensorReading.sensor_id)
        .where(Sensor.company_id == company_id).distinct().order_by(SensorReading.month_number)
    ).all()
    return [r[0] for r in rows]


def list_period_summaries(db: Session, company_id: str, with_sensors: bool = False) -> list[dict]:
    out = []
    for month in period_numbers(db, company_id):
        data = get_period_summary(db, company_id, month)
        if data:
            if not with_sensors:
                data = {k: v for k, v in data.items() if k != "sensors"}
            out.append(data)
    return out


def refresh_open_trust(db: Session, company_id: str) -> None:
    """Keep Sensor.current_trust in sync with the latest (open or sealed) period."""
    months = period_numbers(db, company_id)
    if not months:
        return
    data = get_period_summary(db, company_id, months[-1])
    for row in (data or {}).get("sensors", []):
        sensor = db.scalar(select(Sensor).where(Sensor.sensor_id == row["sensor_id"]))
        if sensor:
            sensor.current_trust = row["trust_score"]
    db.commit()
