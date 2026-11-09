import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Upload } from "lucide-react";
import { api } from "../api/client.js";
import { useAuth } from "../state/AuthContext.jsx";
import { Badge, Card, Empty, ErrorBox, Loading, when, useAsync } from "../components/UI.jsx";

function OperatorCard({ req, p, onChange }) {
  const [answers, setAnswers] = useState({});
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const files = useRef({});
  const open = req.status === "OPEN";
  useEffect(() => { if (open && !req.operator_seen) api.post(`/info-requests/${req.request_id}/seen`, undefined, p).catch(() => {}); }, [req.request_id]);

  const upload = async (item, file) => {
    setBusy(true); setError("");
    try {
      const form = new FormData();
      form.append("period", req.period); form.append("document_type", item.doc_type); form.append("data_label", "USER_UPLOADED");
      form.append("info_request_id", req.request_id); form.append("file", file);
      await api.upload("/documents/upload", form, p); onChange();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  const reply = async () => {
    setBusy(true); setError("");
    try { await api.post(`/info-requests/${req.request_id}/reply`, { answers, note: note || null }, p); onChange(); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="irq">
      <div className="row"><b>{req.title}</b><Badge value={req.status} /><span className="small muted">{req.label} · from {req.created_by} · {when(req.created_at)}</span></div>
      {req.message && <p>{req.message}</p>}
      {req.items.map((it) => (
        <div className="item" key={it.item_id}>
          <div className="row"><span className={it.fulfilled ? "fulfilled" : "pending"}>{it.fulfilled ? "✓ Provided" : "• Needed"}</span><span>{it.label}</span></div>
          {open && it.kind === "DOCUMENT" && !it.fulfilled && (
            <div><input type="file" hidden ref={(el) => (files.current[it.item_id] = el)} onChange={(e) => { if (e.target.files[0]) upload(it, e.target.files[0]); e.target.value = ""; }} />
              <button className="btn sm" disabled={busy} onClick={() => files.current[it.item_id].click()}><Upload size={13} /> Upload {it.doc_type.replaceAll("_", " ").toLowerCase()}</button></div>)}
          {open && it.kind === "INFORMATION" && <textarea placeholder="Your answer" value={answers[it.item_id] ?? it.answer} onChange={(e) => setAnswers({ ...answers, [it.item_id]: e.target.value })} />}
          {!open && it.kind === "INFORMATION" && it.answer && <div className="small muted">Answer: {it.answer}</div>}
        </div>))}
      {open && (<>
        <textarea placeholder="Optional note to the auditor" value={note} onChange={(e) => setNote(e.target.value)} />
        <ErrorBox message={error} />
        <div className="row"><button className="btn primary" disabled={busy} onClick={reply}>Send reply</button><Link className="small" to="/request">Open this month's request</Link></div>
      </>)}
      {req.response_note && <div className="small muted">Your note: {req.response_note}</div>}
      {req.close_note && <div className="small muted">Auditor: {req.close_note}</div>}
    </div>
  );
}

function AuditorCard({ req, p, onChange, setPeriod }) {
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const close = async () => {
    try { await api.post(`/info-requests/${req.request_id}/close`, { note: note || null }, p); onChange(); } catch (e) { setError(e.message); }
  };
  return (
    <div className="irq">
      <div className="row"><b>{req.title}</b><Badge value={req.status} /><span className="small muted">{req.label} · {when(req.created_at)}</span></div>
      {req.items.map((it) => (
        <div className="item" key={it.item_id}>
          <div className="row"><span className={it.fulfilled ? "fulfilled" : "pending"}>{it.fulfilled ? "✓ Provided" : "• Waiting"}</span><span>{it.label}</span></div>
          {it.kind === "INFORMATION" && it.answer && <div className="small">Operator: {it.answer}</div>}
        </div>))}
      {req.response_note && <div className="small">Operator note: {req.response_note}</div>}
      <ErrorBox message={error} />
      <div className="row">
        <Link className="btn sm" to="/verify" onClick={() => setPeriod(req.period)}>Open review</Link>
        {req.status !== "CLOSED" && <><input placeholder="Closing note (optional)" value={note} onChange={(e) => setNote(e.target.value)} style={{ minWidth: 200 }} /><button className="btn sm" onClick={close}>Close request</button></>}
      </div>
    </div>
  );
}

export default function InfoRequests() {
  const { user, companyId, setPeriod } = useAuth();
  const p = { company_id: companyId };
  const list = useAsync(() => api.get("/info-requests", p), [companyId], 10000);
  if (!companyId) return <Empty text="No company selected." />;
  if (list.loading && !list.data) return <Loading />;
  const operator = user.role === "PLANT_OPERATOR";
  const rows = list.data || [];
  const open = rows.filter((r) => r.status !== "CLOSED");
  const closed = rows.filter((r) => r.status === "CLOSED");
  return (
    <>
      <div className="page-title"><h1>{operator ? "Requests from your auditor" : "Information requests sent to operators"}</h1>
        <p>{operator ? "When evidence is missing, your auditor asks for it here. Upload the documents or answer the questions, then send your reply."
          : "Requests you sent for missing documents or information, and the operator's replies."}</p></div>
      <ErrorBox message={list.error} />
      {rows.length === 0 && <Card><Empty text={operator ? "No requests from the auditor. You are all caught up." : "No requests have been sent for this company yet."} /></Card>}
      {open.length > 0 && <Card title={operator ? `Needs your attention (${open.filter((r) => r.status === "OPEN").length})` : "Open & answered"}>
        <div className="col">{open.map((r) => operator ? <OperatorCard key={r.request_id} req={r} p={p} onChange={list.reload} /> : <AuditorCard key={r.request_id} req={r} p={p} onChange={list.reload} setPeriod={setPeriod} />)}</div></Card>}
      {closed.length > 0 && <Card title="Closed"><div className="col">{closed.map((r) => operator ? <OperatorCard key={r.request_id} req={r} p={p} onChange={list.reload} /> : <AuditorCard key={r.request_id} req={r} p={p} onChange={list.reload} setPeriod={setPeriod} />)}</div></Card>}
    </>
  );
}
