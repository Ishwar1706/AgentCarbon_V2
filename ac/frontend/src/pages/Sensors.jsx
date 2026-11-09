import React, { useEffect, useState } from "react";
import { Download, Pause, Play, Zap } from "lucide-react";
import { api, downloadFile } from "../api/client.js";
import { useAuth } from "../state/AuthContext.jsx";
import { Badge, Card, Empty, ErrorBox, Field, Loading, Metric, NoData, Progress, Table, fmt, short, useAsync } from "../components/UI.jsx";
import { periodLabel } from "../../lib/periods.js";
import { Lines } from "../components/Charts.jsx";

const FAULTS = ["STUCK", "DRIFT", "SPIKE", "DROPOUT"];

function Simulator({ companyId, sensors, canControl, onChange }) {
  const { refreshCalendar } = useAuth();
  const [interval, setIntervalS] = useState(2);
  const [fault, setFault] = useState({ sensor_id: "", kind: "STUCK", hours: 24 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const p = { company_id: companyId };
  const st = useAsync(() => api.get("/simulation/status", p), [companyId], 2500);
  useEffect(() => { if (st.data?.running) onChange(); }, [st.data?.readings_emitted_this_session]);
  const act = async (fn) => {
    setBusy(true); setError(""); setNote("");
    try { const r = await fn(); if (r?.readings_written !== undefined) setNote(`${r.readings_written} readings written${r.sealed_periods?.length ? ` · ${r.sealed_periods.map(periodLabel).join(", ")} sealed` : ""}`); st.reload(); onChange(); refreshCalendar(); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  const s = st.data;
  if (!s) return <Card title="Live sensor simulator"><Loading /></Card>;
  return (
    <Card title="Live sensor simulator" subtitle="Every tick advances the plant's simulated clock by 15 minutes and writes one reading per sensor. A finished calendar month is sealed into the monthly dataset used for verification.">
      <div className="grid g4" style={{ marginBottom: 12 }}>
        <Metric label="Status" value={s.running ? "RUNNING" : "STOPPED"} tone={s.running ? "teal" : "warn"} hint={`${s.sensor_count} sensors`} />
        <Metric label="Simulated time" value={s.simulated_time.slice(0, 16).replace("T", " ")} tone="blue" hint={`${s.current_label} (live month)`} />
        <Metric label="Readings this session" value={fmt(s.readings_emitted_this_session, 0)} />
        <Metric label="Active faults" value={Object.keys(s.active_faults).length} tone={Object.keys(s.active_faults).length ? "warn" : "teal"} hint={Object.entries(s.active_faults).map(([k, v]) => `${k.slice(-6)}:${v}`).join(" ")} />
      </div>
      <div className="small muted" style={{ marginBottom: 4 }}>{s.current_label} progress: {fmt(s.period_progress_percent, 1)}% ({s.steps_done_in_period}/{s.steps_per_period} samples per sensor)</div>
      <Progress percent={s.period_progress_percent} />
      {canControl ? (
        <div className="col" style={{ marginTop: 14 }}>
          <div className="row">
            <Field label="Tick every (s)"><input type="number" min="0.5" max="60" step="0.5" value={interval} onChange={(e) => setIntervalS(+e.target.value)} style={{ width: 90 }} /></Field>
            {s.running
              ? <button className="btn" disabled={busy} onClick={() => act(() => api.post("/simulation/stop", undefined, p))}><Pause size={14} /> Stop</button>
              : <button className="btn primary" disabled={busy} onClick={() => act(() => api.post("/simulation/start", { interval_seconds: interval }, p))}><Play size={14} /> Start live feed</button>}
            <button className="btn" disabled={busy} onClick={() => act(() => api.post("/simulation/advance", { steps: 96 }, p))}><Zap size={14} /> +1 day</button>
            <button className="btn" disabled={busy} onClick={() => act(() => api.post("/simulation/advance", { steps: 672 }, p))}><Zap size={14} /> +7 days</button>
            <button className="btn primary" disabled={busy} onClick={() => act(() => api.post("/simulation/complete-month", undefined, p))}>Complete &amp; seal {s.current_label}</button>
          </div>
          <div className="row">
            <Field label="Inject fault into"><select value={fault.sensor_id} onChange={(e) => setFault({ ...fault, sensor_id: e.target.value })}><option value="">choose sensor…</option>{sensors.map((x) => <option key={x.sensor_id}>{x.sensor_id}</option>)}</select></Field>
            <Field label="Kind"><select value={fault.kind} onChange={(e) => setFault({ ...fault, kind: e.target.value })}>{FAULTS.map((k) => <option key={k}>{k}</option>)}</select></Field>
            <Field label="Hours"><input type="number" min="1" value={fault.hours} onChange={(e) => setFault({ ...fault, hours: +e.target.value })} style={{ width: 80 }} /></Field>
            <button className="btn" disabled={busy || !fault.sensor_id} onClick={() => act(() => api.post("/simulation/fault", fault, p))}>Inject</button>
            {fault.sensor_id && s.active_faults[fault.sensor_id] && <button className="btn" onClick={() => act(() => api.del(`/simulation/fault/${fault.sensor_id}`, p))}>Clear fault</button>}
          </div>
        </div>
      ) : <div className="notice" style={{ marginTop: 12 }}>Only the company's plant operator can control the simulator. You are viewing its live output.</div>}
      {note && <div className="notice" style={{ marginTop: 10 }}>{note}</div>}
      <ErrorBox message={error} />
    </Card>
  );
}

export default function Sensors() {
  const { user, companyId, period, setPeriod } = useAuth();
  const p = { company_id: companyId };
  const [sensorId, setSensorId] = useState("");
  const [page, setPage] = useState(0);
  const [flagged, setFlagged] = useState(false);
  const sensors = useAsync(() => api.get("/sensors", p), [companyId]);
  const roll = useAsync(() => api.get("/sensors/monthly-rollup", p), [companyId]);
  const latest = useAsync(() => api.get("/sensors/latest", { ...p, limit: 12 }), [companyId], 3000);
  const m = (roll.data || []).some((x) => x.period === period) ? period : null;
  const series = useAsync(() => (m ? api.get("/sensors/series", { ...p, period: m, points: 220 }) : Promise.resolve(null)), [companyId, m, roll.data?.length]);
  const sid = sensorId || sensors.data?.[0]?.sensor_id;
  const readings = useAsync(() => (sid && m ? api.get(`/sensors/${sid}/readings`, { ...p, period: m, limit: 20, offset: page * 20, only_flagged: flagged }) : Promise.resolve(null)), [companyId, sid, m, page, flagged]);
  useEffect(() => setPage(0), [sid, m, flagged]);
  if (!companyId) return <Empty text="No company selected." />;
  if (sensors.loading && !sensors.data) return <Loading />;
  const refresh = () => { sensors.reload(); roll.reload(); series.reload(); readings.reload(); };
  const periods = roll.data || [];
  const cur = periods.find((x) => x.period === m);
  const chart = (series.data?.timestamps || []).map((t, i) => ({ t: t.slice(5, 16), ...Object.fromEntries(Object.entries(series.data.series).map(([k, v]) => [k.replace("SCD40-", ""), v[i]])) }));
  const lineKeys = Object.keys(series.data?.series || {}).map((k) => ({ key: k.replace("SCD40-", "") }));
  const canControl = user.role === "PLANT_OPERATOR";
  return (
    <>
      <div className="page-title"><h1>Sensors &amp; monthly data</h1>
        <p>Each company runs its own simulated SCD40 fleet. Raw 15-minute readings roll up into complete, hash-sealed monthly datasets that feed the verification agents.</p></div>
      <div className="grid g4">
        <Metric label="Sensors" value={sensors.data?.length ?? "—"} hint="in this company's fleet" tone="blue" />
        <Metric label="Total readings" value={fmt((sensors.data || []).reduce((a, s) => a + s.total_readings, 0), 0)} />
        <Metric label="Sealed months" value={periods.filter((x) => x.status === "SEALED").length} hint={`${periods.filter((x) => x.status === "OPEN").length} open`} />
        <Metric label="Sensors needing attention" value={(sensors.data || []).filter((s) => s.health !== "HEALTHY").length} tone="warn" hint={`as of ${sensors.data?.[0]?.health_label ?? "—"}`} />
      </div>
      <Simulator companyId={companyId} sensors={sensors.data || []} canControl={canControl} onChange={refresh} />
      <Card title="Monthly rollups" subtitle="Click a month (or use the calendar) to inspect its sensors, chart and raw readings.">
        <Table rows={periods.map((x) => ({ ...x, id: x.period }))} onRow={(r) => setPeriod(r.period)} selected={(r) => r.period === period} columns={[
          { key: "label", label: "Month" },
          { key: "status", label: "Dataset", render: (r) => <Badge value={r.status} /> },
          { key: "sensor_count", label: "Sensors", num: true },
          { key: "reading_count", label: "Readings", num: true, render: (r) => fmt(r.reading_count, 0) },
          { key: "completeness_percent", label: "Complete %", num: true, render: (r) => fmt(r.completeness_percent, 1) },
          { key: "anomaly_percent", label: "Anomalies %", num: true, render: (r) => fmt(r.anomaly_percent) },
          { key: "flagged_sensor_count", label: "Flagged", num: true },
          { key: "mean_sensor_trust", label: "Mean trust", num: true, render: (r) => fmt(r.mean_sensor_trust, 2) },
          { key: "avg_co2_ppm", label: "Avg CO₂ ppm", num: true, render: (r) => fmt(r.avg_co2_ppm, 0) },
          { key: "summary_hash", label: "Seal hash", render: (r) => <span className="mono">{short(r.summary_hash)}</span> },
        ]} />
      </Card>
      {!m ? <NoData period={period} text="No sensor readings exist for this month." /> : (<>
        <Card title={`${periodLabel(m)} — CO₂ by sensor`} subtitle="Average CO₂ (ppm) per time bucket, one line per sensor">
          {series.loading ? <Loading /> : <Lines data={chart} xKey="t" lines={lineKeys} height={300} />}
        </Card>
        <Card title={`${periodLabel(m)} — sensor health`}>
          <Table rows={(cur?.sensors || []).map((s) => ({ ...s, id: s.sensor_id }))} onRow={(r) => setSensorId(r.sensor_id)} selected={(r) => r.sensor_id === sid} columns={[
            { key: "sensor_id", label: "Sensor" }, { key: "zone", label: "Zone" },
            { key: "reading_count", label: "Readings", num: true, render: (r) => `${fmt(r.reading_count, 0)} / ${fmt(r.expected_count, 0)}` },
            { key: "completeness_percent", label: "Complete %", num: true, render: (r) => fmt(r.completeness_percent, 1) },
            { key: "avg_co2_ppm", label: "Avg CO₂", num: true, render: (r) => fmt(r.avg_co2_ppm, 0) },
            { key: "anomaly_count", label: "Anomalies", num: true }, { key: "drift_percent_per_30d", label: "Drift %/30d", num: true, render: (r) => fmt(r.drift_percent_per_30d, 1) },
            { key: "trust_score", label: "Trust", num: true, render: (r) => fmt(r.trust_score, 2) }, { key: "health", label: "Health", render: (r) => <Badge value={r.health} /> },
            { key: "failure_reasons", label: "Why", render: (r) => <span className="small muted">{r.failure_reasons.join(" ") || "—"}</span> },
          ]} />
        </Card>
        <Card title={`Raw readings — ${sid || ""}`} subtitle={`${periodLabel(m)}, newest first`} actions={[
          <label key="f" className="row small"><input type="checkbox" checked={flagged} onChange={(e) => setFlagged(e.target.checked)} /> only flagged</label>,
          <select key="s" value={sid} onChange={(e) => setSensorId(e.target.value)}>{(sensors.data || []).map((s) => <option key={s.sensor_id}>{s.sensor_id}</option>)}</select>,
          <button key="d" className="btn sm" onClick={() => downloadFile("/sensors/export.csv", { ...p, period: m }, `${m}-sensor-readings.csv`)}><Download size={13} /> Export month CSV</button>,
        ]}>
          {readings.data && (<>
            <Table rows={readings.data.rows.map((r) => ({ ...r, id: r.sequence_number }))} columns={[
              { key: "timestamp", label: "Time", render: (r) => r.timestamp.slice(0, 16).replace("T", " ") }, { key: "sequence_number", label: "Seq", num: true },
              { key: "co2_ppm", label: "CO₂ ppm", num: true }, { key: "temperature_c", label: "Temp °C", num: true }, { key: "humidity_percent", label: "Humidity %", num: true },
              { key: "scenario", label: "Scenario", render: (r) => <Badge value={r.scenario} /> }, { key: "validation_status", label: "Validation", render: (r) => <Badge value={r.validation_status} /> },
            ]} />
            <div className="row" style={{ marginTop: 8 }}>
              <button className="btn sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
              <span className="small muted">{readings.data.total ? `${page * 20 + 1}–${Math.min((page + 1) * 20, readings.data.total)} of ${fmt(readings.data.total, 0)}` : "0 rows"}</span>
              <button className="btn sm" disabled={(page + 1) * 20 >= readings.data.total} onClick={() => setPage(page + 1)}>Next</button>
            </div>
          </>)}
        </Card>
      </>)}
      <Card title="Live ticker" subtitle="Latest readings across all sensors (refreshes every 3 s)">
        <Table rows={(latest.data || []).map((r, i) => ({ ...r, id: i }))} columns={[
          { key: "timestamp", label: "Sim. time", render: (r) => r.timestamp.slice(0, 16).replace("T", " ") }, { key: "sensor_id", label: "Sensor" },
          { key: "co2_ppm", label: "CO₂ ppm", num: true }, { key: "temperature_c", label: "Temp °C", num: true }, { key: "humidity_percent", label: "Hum %", num: true },
          { key: "validation_status", label: "Validation", render: (r) => <Badge value={r.validation_status} /> },
        ]} />
      </Card>
    </>
  );
}
