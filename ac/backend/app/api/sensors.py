"""Sensors, raw readings, monthly rollups, CSV export and authenticated ingestion."""
from __future__ import annotations

import csv
import hashlib
import io
import secrets
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.sensor import Sensor, SensorReading
from app.services import sensor_rollup
from app.services.company_access import ALL_VIEWERS, Ctx, company_context
from app.services import periods
from app.services.sensor_sim import flag_single
from collections import deque

router = APIRouter(tags=["sensors"])
viewer = company_context(*ALL_VIEWERS)


def _own_sensor(db: Session, ctx: Ctx, sensor_id: str) -> Sensor:
    sensor = db.scalar(select(Sensor).where(Sensor.sensor_id == sensor_id, Sensor.company_id == ctx.company_id))
    if sensor is None:
        raise HTTPException(404, "Sensor not found for this company.")
    return sensor


def _row(r: SensorReading) -> dict:
    return {"sensor_id": r.sensor_id, "timestamp": r.timestamp.isoformat(), "sequence_number": r.sequence_number,
            "period": r.period, "co2_ppm": r.co2_ppm, "temperature_c": r.temperature_c,
            "humidity_percent": r.humidity_percent, "device_status": r.device_status,
            "scenario": r.scenario, "validation_status": r.validation_status}


@router.get("/sensors")
def list_sensors(ctx: Ctx = Depends(viewer), db: Session = Depends(get_db)):
    months = sensor_rollup.period_list(db, ctx.company_id)
    latest_summary = sensor_rollup.get_period_summary(db, ctx.company_id, months[-1]) if months else None
    health = {s["sensor_id"]: s for s in (latest_summary or {}).get("sensors", [])}
    out = []
    for s in db.scalars(select(Sensor).where(Sensor.company_id == ctx.company_id).order_by(Sensor.sensor_id)):
        last = db.scalar(select(SensorReading).where(SensorReading.sensor_id == s.sensor_id)
                         .order_by(SensorReading.sequence_number.desc()).limit(1))
        total = db.scalar(select(func.count(SensorReading.id)).where(SensorReading.sensor_id == s.sensor_id))
        h = health.get(s.sensor_id, {})
        out.append({
            "sensor_id": s.sensor_id, "zone": s.zone, "location": s.location, "sensor_type": s.sensor_type,
            "device_status": s.device_status, "calibration_status": s.calibration_status,
            "trust_score": h.get("trust_score", s.current_trust), "health": h.get("health", "UNKNOWN"),
            "failure_confidence": h.get("failure_confidence"), "failure_reasons": h.get("failure_reasons", []),
            "total_readings": total, "latest": _row(last) if last else None,
            "health_period": months[-1] if months else None,
            "health_label": periods.label(months[-1]) if months else None,
        })
    return out


@router.get("/sensors/latest")
def latest_readings(limit: int = Query(default=30, ge=1, le=200), ctx: Ctx = Depends(viewer), db: Session = Depends(get_db)):
    rows = db.scalars(select(SensorReading).join(Sensor, Sensor.sensor_id == SensorReading.sensor_id)
                      .where(Sensor.company_id == ctx.company_id)
                      .order_by(SensorReading.timestamp.desc(), SensorReading.id.desc()).limit(limit)).all()
    return [_row(r) for r in rows]


@router.get("/sensors/monthly-rollup")
def monthly_rollup(ctx: Ctx = Depends(viewer), db: Session = Depends(get_db)):
    return sensor_rollup.list_period_summaries(db, ctx.company_id, with_sensors=True)


@router.get("/sensors/series")
def series(period: str = Query(...), points: int = Query(default=240, ge=20, le=800),
           ctx: Ctx = Depends(viewer), db: Session = Depends(get_db)):
    periods.valid(period)
    frame = sensor_rollup.load_period_frame(db, ctx.company_id, period)
    if frame.empty:
        return {"period": period, "timestamps": [], "series": {}}
    frame["bucket"] = pd.qcut(frame["timestamp"].rank(method="first"), q=min(points, len(frame)), labels=False, duplicates="drop")
    stamps = frame.groupby("bucket")["timestamp"].first().dt.strftime("%Y-%m-%d %H:%M").tolist()
    pivot = frame.groupby(["bucket", "sensor_id"])["co2_ppm"].mean().round(1).unstack()
    return {"period": period, "timestamps": stamps,
            "series": {c: [None if pd.isna(v) else float(v) for v in pivot[c]] for c in pivot.columns}}


@router.get("/sensors/export.csv")
def export_csv(period: str = Query(...), ctx: Ctx = Depends(viewer), db: Session = Depends(get_db)):
    def generate():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["sensor_id", "timestamp", "sequence_number", "period", "co2_ppm",
                         "temperature_c", "humidity_percent", "validation_status", "scenario"])
        yield buffer.getvalue()
        result = db.execute(select(SensorReading).join(Sensor, Sensor.sensor_id == SensorReading.sensor_id)
                            .where(Sensor.company_id == ctx.company_id, SensorReading.period == periods.valid(period))
                            .order_by(SensorReading.sensor_id, SensorReading.sequence_number).execution_options(yield_per=2000))
        for r in result.scalars():
            buffer.seek(0); buffer.truncate()
            writer.writerow([r.sensor_id, r.timestamp.isoformat(), r.sequence_number, r.period,
                             r.co2_ppm, r.temperature_c, r.humidity_percent, r.validation_status, r.scenario])
            yield buffer.getvalue()
    return StreamingResponse(generate(), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="{ctx.company_id}-{period}-sensor-readings.csv"'})


@router.get("/sensors/{sensor_id}/readings")
def sensor_readings(sensor_id: str, period: str | None = Query(default=None),
                    only_flagged: bool = False, limit: int = Query(default=50, ge=1, le=500),
                    offset: int = Query(default=0, ge=0), ctx: Ctx = Depends(viewer), db: Session = Depends(get_db)):
    _own_sensor(db, ctx, sensor_id)
    query = select(SensorReading).where(SensorReading.sensor_id == sensor_id)
    count = select(func.count(SensorReading.id)).where(SensorReading.sensor_id == sensor_id)
    if period:
        periods.valid(period)
        query, count = query.where(SensorReading.period == period), count.where(SensorReading.period == period)
    if only_flagged:
        query, count = (query.where(SensorReading.validation_status != "VALID"),
                        count.where(SensorReading.validation_status != "VALID"))
    rows = db.scalars(query.order_by(SensorReading.sequence_number.desc()).limit(limit).offset(offset)).all()
    return {"total": db.scalar(count), "limit": limit, "offset": offset, "rows": [_row(r) for r in rows]}


class NewSensor(BaseModel):
    sensor_id: str = Field(pattern=r"^[A-Za-z0-9._-]{4,60}$")
    zone: str = Field(default="GENERAL", max_length=40)
    location: str = Field(min_length=3, max_length=200)


@router.post("/sensors", status_code=201)
def register_sensor(body: NewSensor, ctx: Ctx = Depends(company_context("PLANT_OPERATOR")),
                    db: Session = Depends(get_db)):
    if db.scalar(select(Sensor).where(Sensor.sensor_id == body.sensor_id)):
        raise HTTPException(409, "Sensor id already exists.")
    key = secrets.token_urlsafe(32)
    db.add(Sensor(sensor_id=body.sensor_id, company_id=ctx.company_id, zone=body.zone.upper(),
                  location=body.location, is_simulated=0, api_key_hash=hashlib.sha256(key.encode()).hexdigest()))
    db.commit()
    return {"sensor_id": body.sensor_id, "api_key": key,
            "notice": "Store this key now. It is shown only once. Send it as the X-Sensor-Key header to POST /api/v1/sensor-readings."}


class Ingest(BaseModel):
    sensor_id: str
    timestamp: datetime
    sequence_number: int = Field(ge=1)
    co2_ppm: float = Field(ge=0, le=60000)
    temperature_c: float = Field(ge=-40, le=100)
    humidity_percent: float = Field(ge=0, le=100)


@router.post("/sensor-readings", status_code=201)
def ingest(body: Ingest, x_sensor_key: str = Header(default=""), db: Session = Depends(get_db)):
    sensor = db.scalar(select(Sensor).where(Sensor.sensor_id == body.sensor_id))
    if not sensor or not sensor.api_key_hash or not secrets.compare_digest(
            sensor.api_key_hash, hashlib.sha256(x_sensor_key.encode()).hexdigest()):
        raise HTTPException(401, "Invalid sensor id or X-Sensor-Key.")
    if db.scalar(select(SensorReading.id).where(SensorReading.sensor_id == body.sensor_id,
                                                SensorReading.sequence_number == body.sequence_number)):
        raise HTTPException(409, "Duplicate sequence number for this sensor.")
    ts = body.timestamp if body.timestamp.tzinfo else body.timestamp.replace(tzinfo=timezone.utc)
    status = flag_single(body.co2_ppm, body.temperature_c, body.humidity_percent, deque(), body.co2_ppm)
    db.add(SensorReading(sensor_id=body.sensor_id, timestamp=ts, sequence_number=body.sequence_number,
                         period=periods.of(ts), co2_ppm=body.co2_ppm, temperature_c=body.temperature_c,
                         humidity_percent=body.humidity_percent, data_origin="HARDWARE", validation_status=status))
    db.commit()
    return {"accepted": True, "validation_status": status}
