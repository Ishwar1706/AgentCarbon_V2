from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.access_control import utcnow


class Sensor(Base):
    __tablename__ = "sensors"
    id: Mapped[int] = mapped_column(primary_key=True)
    sensor_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.company_id"), index=True)
    sensor_type: Mapped[str] = mapped_column(String(50), default="SCD40")
    zone: Mapped[str] = mapped_column(String(50), default="GENERAL")
    location: Mapped[str] = mapped_column(String(200))
    measurement_unit: Mapped[str] = mapped_column(String(20), default="ppm")
    calibration_status: Mapped[str] = mapped_column(String(30), default="VALID")
    device_status: Mapped[str] = mapped_column(String(30), default="ONLINE")
    current_trust: Mapped[float] = mapped_column(Float, default=0.90)
    is_simulated: Mapped[int] = mapped_column(Integer, default=1)
    api_key_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SensorReading(Base):
    """One SCD40 sample. `timestamp` is the (simulated) measurement time,
    `month_number` is the 30-day reporting period it belongs to."""
    __tablename__ = "sensor_readings"
    __table_args__ = (
        UniqueConstraint("sensor_id", "sequence_number", name="uq_sensor_sequence"),
        Index("ix_reading_sensor_period", "sensor_id", "month_number"),
        Index("ix_reading_sensor_ts", "sensor_id", "timestamp"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    sensor_id: Mapped[str] = mapped_column(ForeignKey("sensors.sensor_id", ondelete="CASCADE"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sequence_number: Mapped[int] = mapped_column(Integer)
    month_number: Mapped[int] = mapped_column(Integer)
    co2_ppm: Mapped[float] = mapped_column(Float)
    temperature_c: Mapped[float] = mapped_column(Float)
    humidity_percent: Mapped[float] = mapped_column(Float)
    device_status: Mapped[str] = mapped_column(String(30), default="ONLINE")
    data_origin: Mapped[str] = mapped_column(String(50), default="SIMULATED_HARDWARE")
    scenario: Mapped[str] = mapped_column(String(30), default="NORMAL")
    validation_status: Mapped[str] = mapped_column(String(30), default="VALID")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SensorPeriodSeal(Base):
    """A closed (complete) monthly sensor dataset with a tamper-evident hash."""
    __tablename__ = "sensor_period_seals"
    __table_args__ = (UniqueConstraint("company_id", "month_number", name="uq_company_period_seal"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[str] = mapped_column(String(80), index=True)
    month_number: Mapped[int] = mapped_column(Integer)
    summary_json: Mapped[str] = mapped_column(Text)
    summary_hash: Mapped[str] = mapped_column(String(64))
    sealed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
