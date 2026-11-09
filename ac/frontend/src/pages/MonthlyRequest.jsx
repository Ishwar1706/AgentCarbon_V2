import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Upload } from "lucide-react";
import { api, downloadFile } from "../api/client.js";
import { useAuth } from "../state/AuthContext.jsx";
import { Badge, Card, Empty, ErrorBox, Field, Loading, Metric, NoData, Table, fmt, useAsync, when } from "../components/UI.jsx";

const EMPTY = { expected_credits_tco2e: "", declared_electricity_kwh: "", declared_production_units: "", declared_natural_gas_scm: "", declared_diesel_litres: "", notes: "" };

function SlotRow({ slot, disabled, onUpload }) {
  const input = useRef(null);
  return (
    <div className="slot">
      <div><b>{slot.label}</b> {slot.required ? <span className="small muted">· required</span> : <span className="small muted">· optional</span>}</div>
      {slot.status === "MISSING" && !slot.required ? <span className="badge neutral">Not provided</span> : <Badge value={slot.status} />}
      <span className="small muted">{slot.count} file{slot.count === 1 ? "" : "s"}{slot.rejected ? ` · ${slot.rejected} rejected` : ""}</span>
      <span>
        <input ref={input} type="file" hidden onChange={(e) => { if (e.target.files[0]) onUpload(slot.slot, e.target.files[0]); e.target.value = ""; }} />
        <button className="btn sm" disabled={disabled} onClick={() => input.current.click()}><Upload size={13} /> Upload</button>
      </span>
    </div>
  );
}

export default function MonthlyRequest() {
  const { companyId, period, refreshCalendar } = useAuth();
  const p = { company_id: companyId };
  const detail = useAsync(() => api.get(`/requests/${period}`, p), [companyId, period]);
  const [f, setF] = useState(EMPTY);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const d = detail.data;

  useEffect(() => {
    if (!d?.available) return;
    const src = d.request ? d.request : { expected_credits_tco2e: d.prefill.expected_credits_tco2e, declared_electricity_kwh: d.prefill.electricity_kwh,
      declared_production_units: d.prefill.production_units, declared_natural_gas_scm: d.prefill.natural_gas_scm, declared_diesel_litres: d.prefill.diesel_litres, notes: "" };
    setF({ expected_credits_tco2e: src.expected_credits_tco2e, declared_electricity_kwh: Math.round(src.declared_electricity_kwh * 100) / 100,
      declared_production_units: src.declared_production_units, declared_natural_gas_scm: Math.round(src.declared_natural_gas_scm * 100) / 100,
      declared_diesel_litres: Math.round(src.declared_diesel_litres * 100) / 100, notes: src.notes || "" });
    setMsg(""); setError("");
  }, [d?.claim_id, d?.request?.updated_at, d?.prefill?.expected_credits_tco2e]);

  if (!companyId) return <Empty text="No company selected." />;
  if (detail.loading && !d) return <Loading />;
  if (detail.error) return <ErrorBox message={detail.error} />;
  const title = <div className="page-title"><h1>Monthly request — {d.label}</h1>
    <p>Declare this month's figures and the carbon credits you expect to earn, attach your bills, then submit for audit.</p></div>;
  if (!d.available) return <>{title}<NoData period={period} text="You can only file a monthly request for months that have plant data (Jan – May 2026 in this demo)." /></>;

  const num = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const body = () => ({ expected_credits_tco2e: +f.expected_credits_tco2e, declared_electricity_kwh: +f.declared_electricity_kwh,
    declared_production_units: parseInt(f.declared_production_units, 10), declared_natural_gas_scm: +f.declared_natural_gas_scm,
    declared_diesel_litres: +f.declared_diesel_litres, notes: f.notes || null });
  const act = async (fn, ok) => {
    setBusy(true); setError(""); setMsg("");
    try { await fn(); setMsg(ok); detail.reload(); refreshCalendar(); } catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  const save = () => act(() => api.put(`/requests/${period}`, body(), p), "Saved.");
  const submit = () => act(async () => { await api.put(`/requests/${period}`, body(), p); await api.post(`/requests/${period}/submit`, undefined, p); }, "Submitted to the auditor.");
  const upload = (slot, file) => act(async () => {
    const form = new FormData();
    form.append("period", period); form.append("document_type", slot); form.append("data_label", "USER_UPLOADED"); form.append("file", file);
    await api.upload("/documents/upload", form, p);
  }, `${file.name} uploaded.`);
  const resetToPlant = () => setF({ ...f, expected_credits_tco2e: d.prefill.expected_credits_tco2e, declared_electricity_kwh: Math.round(d.prefill.electricity_kwh * 100) / 100,
    declared_production_units: d.prefill.production_units, declared_natural_gas_scm: Math.round(d.prefill.natural_gas_scm * 100) / 100, declared_diesel_litres: Math.round(d.prefill.diesel_litres * 100) / 100 });
  const status = d.request?.status || "NOT_STARTED";
  const ev = d.evaluation;
  const openInfo = d.info_requests.filter((i) => i.status === "OPEN");
  const complete = Object.values(f).slice(0, 5).every((v) => v !== "" && !Number.isNaN(+v));

  return (
    <>
      {title}
      <div className="row"><Badge value={status} />{d.request?.submitted_at && <span className="small muted">submitted {when(d.request.submitted_at)}</span>}</div>
      {openInfo.length > 0 && <div className="notice"><b>Your auditor needs more information.</b> {openInfo.length} open request{openInfo.length > 1 ? "s" : ""} — <Link to="/inbox">open the Auditor Requests inbox</Link>.</div>}
      {d.decision && <Card title={`Auditor decision: ${d.decision.decision}`} subtitle={when(d.decision.decided_at)}><p>{d.decision.comments}</p></Card>}
      <ErrorBox message={error} />
      {msg && <div className="notice">{msg}</div>}
      <div className="grid g2">
        <Card title="1 · Declared figures & expected credits" subtitle={d.editable ? "Prefilled from your plant's own systems — edit if your bills differ." : `Locked: this request is ${status}.`}
              actions={d.editable ? [<button key="r" className="btn sm" onClick={resetToPlant}>Use plant figures</button>] : null}>
          <div className="form-grid">
            <Field label="Expected credits to earn (tCO₂e)"><input className="input-num" type="number" step="0.01" min="0" value={f.expected_credits_tco2e} onChange={num("expected_credits_tco2e")} disabled={!d.editable} /></Field>
            <Field label="Electricity consumed (kWh)"><input className="input-num" type="number" step="0.01" min="0" value={f.declared_electricity_kwh} onChange={num("declared_electricity_kwh")} disabled={!d.editable} /></Field>
            <Field label="Vehicles produced (units)"><input className="input-num" type="number" step="1" min="0" value={f.declared_production_units} onChange={num("declared_production_units")} disabled={!d.editable} /></Field>
            <Field label="Natural gas (SCM)"><input className="input-num" type="number" step="0.01" min="0" value={f.declared_natural_gas_scm} onChange={num("declared_natural_gas_scm")} disabled={!d.editable} /></Field>
            <Field label="Diesel (litres)"><input className="input-num" type="number" step="0.01" min="0" value={f.declared_diesel_litres} onChange={num("declared_diesel_litres")} disabled={!d.editable} /></Field>
          </div>
          <Field label="Notes for the auditor (optional)"><textarea value={f.notes} onChange={num("notes")} disabled={!d.editable} /></Field>
          {d.editable && (
            <div className="row" style={{ marginTop: 10 }}>
              <button className="btn" disabled={busy || !complete} onClick={save}>Save draft</button>
              <button className="btn primary" disabled={busy || !complete} onClick={submit}>{status === "INFO_REQUESTED" ? "Resubmit" : "Submit for verification"}</button>
            </div>)}
        </Card>
        <Card title="Credit check" subtitle="How the system sees your expected credits (based on verified meter data)">
          <div className="grid g4" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <Metric label="You expect" value={`${fmt(ev.expected_credits_tco2e)} t`} tone="blue" />
            <Metric label="Supported by data" value={`${fmt(ev.supported_credits_tco2e)} t`} />
            <Metric label="Approvable" value={`${fmt(ev.approvable_credits_tco2e)} t`} />
            <Metric label="Overstatement" value={`${fmt(ev.overstatement_percent, 0)}%`} tone={ev.overstatement_percent > 10 ? "bad" : "teal"} />
          </div>
          <p className="small muted" style={{ marginTop: 10 }}>Baseline {fmt(ev.baseline_intensity_kgco2e_per_vehicle)} kgCO₂e per vehicle. Credits = (baseline × verified production − verified emissions) ÷ 1000. Verified electricity this month: {fmt(d.plant_records.verified_electricity_kwh, 0)} kWh. (Refreshes after you save.)</p>
        </Card>
      </div>
      <Card title="2 · Evidence checklist" subtitle="Upload your electricity bill, production record and fuel bill. Missing items will make the AI agents flag the month for manual review and your auditor will ask for them.">
        {d.checklist.slots.map((s) => <SlotRow key={s.slot} slot={s} disabled={busy || ["APPROVED", "REJECTED"].includes(status)} onUpload={upload} />)}
        {d.checklist.missing_required.length > 0 && <div className="notice" style={{ marginTop: 10 }}>Still missing: {d.checklist.slots.filter((s) => s.required && s.status === "MISSING").map((s) => s.label).join(", ")}.</div>}
      </Card>
      <Card title="Uploaded documents">
        <Table rows={d.documents.map((x) => ({ ...x, id: x.document_id }))} empty="No documents uploaded for this month yet." columns={[
          { key: "document_label", label: "Type" }, { key: "original_filename", label: "File" },
          { key: "size_bytes", label: "Size KB", num: true, render: (x) => fmt(x.size_bytes / 1024, 1) },
          { key: "verification_status", label: "Status", render: (x) => <Badge value={x.verification_status} /> },
          { key: "auditor_note", label: "Auditor note", render: (x) => x.auditor_note || "—" },
          { key: "uploaded_at", label: "Uploaded", render: (x) => when(x.uploaded_at) },
          { key: "a", label: "", render: (x) => <button className="btn sm" onClick={() => downloadFile(`/documents/${x.document_id}/download`, p, x.original_filename)}>Download</button> },
        ]} />
      </Card>
    </>
  );
}
