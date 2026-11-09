"""Live sensor simulator. Runs inside the API process (no external script needed).

Each tick advances the company's *simulated clock* by 15 minutes and writes one
reading per sensor. When a calendar month is complete it is sealed into a monthly
dataset that later verification cycles consume.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import timedelta
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.sensor import Sensor, SensorReading
from app.models.workflows import Company
from app.services import periods, sensor_rollup
from app.services.company_data import COMPANY_PROFILES, read_company_dataset
from app.services.sensor_profiles import sensor_profiles
from app.services.sensor_sim import STEP_MINUTES, LiveBaseline, SensorLiveState, live_reading

log = logging.getLogger("agentcarbon.live")
FAULT_KINDS = {"STUCK", "DRIFT", "SPIKE", "DROPOUT"}


class CompanySim:
    def __init__(self, company_id: str):
        self.company_id = company_id
        self.running = False
        self.interval = 2.0
        self.next_due = 0.0
        self.next_ts = periods.start("2026-01")
        self.states: dict[str, SensorLiveState] = {}
        self.baseline: LiveBaseline | None = None
        self.emitted = 0
        self.started_at: float | None = None
        self.lock = threading.RLock()

    # -- state is rebuilt from the database so restarts continue seamlessly
    def load(self, db: Session) -> None:
        company = db.get(Company, self.company_id)
        sensors = db.scalars(select(Sensor).where(Sensor.company_id == self.company_id)
                             .order_by(Sensor.sensor_id)).all()
        legal = company.legal_name if company else self.company_id
        known = {p["sensor_id"]: p for p in (
            sensor_profiles(self.company_id, legal) if self.company_id in COMPANY_PROFILES else [])}
        last_ts = db.scalar(select(func.max(SensorReading.timestamp)).join(
            Sensor, Sensor.sensor_id == SensorReading.sensor_id).where(Sensor.company_id == self.company_id))
        if last_ts is not None:
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=periods.start("2026-01").tzinfo)
            self.next_ts = last_ts + timedelta(minutes=STEP_MINUTES)
        base_df = read_company_dataset(self.company_id, "historical_scd40_readings.csv") \
            if self.company_id in COMPANY_PROFILES else None
        if base_df is not None:
            self.baseline = LiveBaseline(base_df)
        new_states = {}
        for sensor in sensors:
            max_seq = db.scalar(select(func.max(SensorReading.sequence_number))
                                .where(SensorReading.sensor_id == sensor.sensor_id)) or 0
            profile = known.get(sensor.sensor_id) or {
                "sensor_id": sensor.sensor_id, "zone": sensor.zone, "location": sensor.location,
                "gain": 1.0, "offset": 0.0, "temp_offset": 0.0, "hum_offset": 0.0,
                "noise": 11.0, "faults": []}
            old = self.states.get(sensor.sensor_id)
            state = SensorLiveState(profile, max_seq + 1)
            if old:
                state.fault, state.last, state.recent = old.fault, old.last, old.recent
            new_states[sensor.sensor_id] = state
        self.states = new_states

    def current_period(self) -> str:
        return periods.of(self.next_ts)

    def steps_done_in_period(self) -> int:
        return int((self.next_ts - periods.start(self.current_period())).total_seconds() // (STEP_MINUTES * 60))


class LiveEngine:
    def __init__(self) -> None:
        self.sims: dict[str, CompanySim] = {}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._guard = threading.Lock()

    def sim(self, db: Session, company_id: str) -> CompanySim:
        with self._guard:
            sim = self.sims.get(company_id)
            if sim is None:
                sim = self.sims[company_id] = CompanySim(company_id)
        with sim.lock:
            sim.load(db)
        return sim

    # ---------------------------------------------------------- control
    def start(self, db: Session, company_id: str, interval: float) -> CompanySim:
        sim = self.sim(db, company_id)
        with sim.lock:
            sim.interval = max(0.5, min(60.0, interval))
            sim.running = True
            sim.started_at = time.time()
            sim.next_due = time.monotonic()
        self.ensure_thread()
        return sim

    def stop(self, company_id: str) -> None:
        sim = self.sims.get(company_id)
        if sim:
            sim.running = False

    def ensure_thread(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="live-sensor-sim", daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()
        for sim in self.sims.values():
            sim.running = False

    def _loop(self) -> None:
        while not self._stop.is_set():
            now = time.monotonic()
            for sim in list(self.sims.values()):
                if sim.running and now >= sim.next_due:
                    sim.next_due = now + sim.interval
                    try:
                        with SessionLocal() as db:
                            self.advance(db, sim.company_id, 1)
                    except Exception:  # keep the engine alive
                        log.exception("live tick failed for %s", sim.company_id)
            self._stop.wait(0.25)

    # ------------------------------------------------------------ steps
    def advance(self, db: Session, company_id: str, steps: int) -> dict[str, Any]:
        sim = self.sim(db, company_id) if company_id not in self.sims or not self.sims[company_id].states else self.sims[company_id]
        written, sealed = 0, []
        with sim.lock:
            if sim.baseline is None:
                raise ValueError("This company has no baseline sensor profile to simulate from.")
            rows: list[dict] = []
            for _ in range(steps):
                ts = sim.next_ts
                for state in sim.states.values():
                    reading = live_reading(state, ts, sim.baseline)
                    if reading:
                        rows.append(reading)
                sim.next_ts = ts + timedelta(minutes=STEP_MINUTES)
                crossed = periods.of(sim.next_ts) != periods.of(ts)
                if crossed or len(rows) >= 4000:
                    written += self._flush(db, rows)
                    rows = []
                if crossed:
                    seal = sensor_rollup.seal_period(db, company_id, periods.of(ts))
                    if seal:
                        sealed.append(periods.of(ts))
            written += self._flush(db, rows)
            sim.emitted += written
        sensor_rollup.refresh_open_trust(db, company_id)
        return {"readings_written": written, "sealed_periods": sealed,
                "simulated_time": sim.next_ts.isoformat(), "current_period": sim.current_period()}

    @staticmethod
    def _flush(db: Session, rows: list[dict]) -> int:
        if not rows:
            return 0
        db.execute(insert(SensorReading), rows)
        db.commit()
        return len(rows)

    def complete_month(self, db: Session, company_id: str) -> dict[str, Any]:
        sim = self.sim(db, company_id)
        remaining = periods.steps(sim.current_period()) - sim.steps_done_in_period()
        return self.advance(db, company_id, max(1, remaining))

    # ----------------------------------------------------------- faults
    def inject_fault(self, db: Session, company_id: str, sensor_id: str, kind: str,
                     hours: float, magnitude: float) -> None:
        if kind not in FAULT_KINDS:
            raise ValueError(f"Unknown fault kind: {kind}")
        sim = self.sim(db, company_id)
        state = sim.states.get(sensor_id)
        if state is None:
            raise ValueError("Sensor not found for this company.")
        steps = max(1, int(hours * 60 / STEP_MINUTES))
        state.fault = {"kind": kind, "remaining": steps, "total": steps,
                       "magnitude": magnitude or (300.0 if kind == "DRIFT" else 2600.0), "acc": 0.0}

    def clear_fault(self, db: Session, company_id: str, sensor_id: str) -> None:
        state = self.sim(db, company_id).states.get(sensor_id)
        if state:
            state.fault = None

    def status(self, db: Session, company_id: str) -> dict[str, Any]:
        sim = self.sim(db, company_id)
        done = sim.steps_done_in_period()
        return {
            "company_id": company_id, "running": sim.running, "interval_seconds": sim.interval,
            "simulated_time": sim.next_ts.isoformat(), "current_period": sim.current_period(),
            "current_label": periods.label(sim.current_period()),
            "steps_done_in_period": done, "steps_per_period": periods.steps(sim.current_period()),
            "period_progress_percent": round(100 * done / periods.steps(sim.current_period()), 1),
            "readings_emitted_this_session": sim.emitted,
            "sensor_count": len(sim.states),
            "active_faults": {sid: s.fault["kind"] for sid, s in sim.states.items() if s.fault},
        }


engine = LiveEngine()
