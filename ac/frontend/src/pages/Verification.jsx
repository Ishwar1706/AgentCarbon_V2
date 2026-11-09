import React, { useEffect, useState } from "react";
import { Bot, Play, Send } from "lucide-react";
import { api, downloadFile } from "../api/client.js";
import { useAuth } from "../state/AuthContext.jsx";
import { Badge, Card, Empty, ErrorBox, Field, Loading, Metric, NoData, Table, fmt, short, useAsync, when } from "../components/UI.jsx";

const DECISIONS = ["APPROVE", "REJECT", "ESCALATE"];
const DOC_TYPES = ["ELECTRICITY_BILL", "PRODUCTION_RECORD", "FUEL_BILL", "CALIBRATION_CERTIFICATE", "MAINTENANCE_RECORD", "METER_PHOTO", "OTHER"];
const statusOf = (list, id) => list?.find((r) => r.run_id === id)?.status;

function InfoRequestForm({ period, label, p, suggested, onSent }) {
  const [items, setItems] = useState([]);
  const [title, setTitle] = useState("");
  const [message, setMessage] = useState("");
  const [custom, setCustom] = useState({ kind: "INFORMATION", doc_type: "OTHER", label: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setItems(suggested || []); setTitle(`Information needed for ${label}`); }, [period, JSON.stringify(suggested)]);
  const send = async () => {
    setBusy(true); setError("");
    try { await api.post("/info-requests", { period, title, message, items }, p); setMessage(""); onSent(); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  return (
    <Card title="Request information from the operator" subtitle="Items are suggested from the gaps the agents found. Edit, add or remove, then send — the operator gets it in their inbox.">
      <Field label="Title"><input value={title} onChange={(e) => setTitle(e.target.value)} style={{ width: "100%" }} /></Field>
      <div className="col" style={{ margin: "10px 0" }}>
        {items.length === 0 && <span className="muted small">No items yet — add one below.</span>}
        {items.map((it, i) => (
          <div className="row" key={i}><Badge value={it.kind} /><span style={{ flex: 1 }}>{it.label}</span>
            <button className="btn sm danger" onClick={() => setItems(items.filter((_, j) => j !== i))}>Remove</button></div>))}
      </div>
      <div className="row">
        <select value={custom.kind} onChange={(e) => setCustom({ ...custom, kind: e.target.value })}><option value="INFORMATION">Question</option><option value="DOCUMENT">Document</option></select>
        {custom.kind === "DOCUMENT" && <select value={custom.doc_type} onChange={(e) => setCustom({ ...custom, doc_type: e.target.value })}>{DOC_TYPES.map((t) => <option key={t}>{t}</option>)}</select>}
        <input placeholder="What do you need?" value={custom.label} onChange={(e) => setCustom({ ...custom, label: e.target.value })} style={{ flex: 1, minWidth: 220 }} />
        <button className="btn sm" disabled={custom.label.trim().length < 3} onClick={() => { setItems([...items, { ...custom, doc_type: custom.kind === "DOCUMENT" ? custom.doc_type : "" }]); setCustom({ ...custom, label: "" }); }}>Add item</button>
      </div>
      <Field label="Message (optional)"><textarea value={message} onChange={(e) => setMessage(e.target.value)} /></Field>
      <ErrorBox message={error} />
      <div className="row" style={{ marginTop: 8 }}><button className="btn primary" disabled={busy || items.length === 0 || title.trim().length < 3} onClick={send}><Send size={14} /> Send request</button></div>
    </Card>
  );
}

export default function Verification() {
  const { companyId, period, refreshCalendar } = useAuth();
  const p = { company_id: companyId };
  const detail = useAsync(() => api.get(`/requests/${period}`, p), [companyId, period]);
  const sys = useAsync(() => api.get("/verifications/status"), []);
  const [mode, setMode] = useState("AUTO");
  const [runId, setRunId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [watching, setWatching] = useState(false);
  const [dec, setDec] = useState({ decision: "APPROVE", comments: "" });
  const history = useAsync(() => api.get("/verifications/runs", { ...p, period }), [companyId, period]);
  const decisions = useAsync(() => api.get("/auditor/decisions", { ...p, period }), [companyId, period]);
  useEffect(() => { setRunId(""); setWatching(false); }, [companyId, period]);
  const shownRun = runId || history.data?.find((r) => ["QUEUED", "RUNNING"].includes(r.status))?.run_id ||
    history.data?.find((r) => r.status === "COMPLETED")?.run_id || history.data?.[0]?.run_id || "";
  const run = useAsync(() => (shownRun ? api.get(`/verifications/runs/${shownRun}`, p) : Promise.resolve(null)), [shownRun, companyId],
    shownRun && (watching || ["QUEUED", "RUNNING"].includes(statusOf(history.data, shownRun))) ? 1500 : 0);
  const live = run.data && ["QUEUED", "RUNNING"].includes(run.data.status);
  useEffect(() => { if (run.data && !live) { setWatching(false); history.reload(); } }, [run.data?.status]);
  useEffect(() => { if (live) { const t = setInterval(history.reload, 2000); return () => clearInterval(t); } }, [live]);

  if (!companyId) return <Empty text="No company selected." />;
  if (detail.loading && !detail.data) return <Loading />;
  if (detail.error) return <ErrorBox message={detail.error} />;
  const d = detail.data;
  const title = <div className="page-title"><h1>Review & agents — {d.label}</h1>
    <p>Four specialist agents analyse the operator's request and evidence, debate, and a consensus agent proposes a recommendation. A deterministic guard can only make it stricter. You decide.</p></div>;
  if (!d.available) return <>{title}<NoData period={period} /></>;

  const reqStatus = d.request?.status || "NOT_STARTED";
  const submitted = Boolean(d.request && d.request.status !== "DRAFT");
  const closedMonth = ["APPROVED", "REJECTED"].includes(reqStatus);
  const llmOn = sys.data?.groq_configured;
  const r = run.data?.result, cons = r?.consensus;
  const refresh = () => { detail.reload(); history.reload(); decisions.reload(); refreshCalendar(); };

  const start = async () => {
    setBusy(true); setError("");
    try { const x = await api.post("/verifications/run", { period, mode }, p); setRunId(x.run_id); setWatching(true); history.reload(); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  const decide = async () => {
    setError("");
    try { await api.post("/auditor/decisions", { period, ...dec }, p); setDec({ ...dec, comments: "" }); refresh(); } catch (e) { setError(e.message); }
  };
  const verifyDoc = async (id, status) => {
    const note = status === "REJECTED" ? window.prompt("Reason for rejection?") || "" : "";
    if (status === "REJECTED" && !note.trim()) return;
    try { await api.patch(`/documents/${id}/verify`, { status, note }, p); detail.reload(); } catch (e) { setError(e.message); }
  };
  const ev = d.evaluation;
  const suggested = cons?.suggested_info_items || [];

  return (
    <>
      {title}
      <Card title="Operator's monthly request" actions={[<Badge key="s" value={reqStatus} />]}>
        {!submitted ? <div className="notice">Operator has not submitted this month - the agents will use the plant&apos;s own figures.</div> : (
          <div className="grid g4">
            <Metric label="Expected credits" value={`${fmt(ev.expected_credits_tco2e)} t`} tone="blue" />
            <Metric label="Supported by data" value={`${fmt(ev.supported_credits_tco2e)} t`} />
            <Metric label="Overstatement" value={`${fmt(ev.overstatement_percent, 0)}%`} tone={ev.overstatement_percent > 10 ? "bad" : "teal"} />
            <Metric label="Declared electricity" value={`${fmt(d.request.declared_electricity_kwh, 0)} kWh`} hint={`verified ${fmt(d.plant_records.verified_electricity_kwh, 0)} kWh`} />
          </div>)}
        {d.request?.notes && <p className="small" style={{ marginTop: 8 }}>Operator notes: {d.request.notes}</p>}
        <div style={{ marginTop: 12 }}>
          <b className="small">Evidence checklist</b>
          <div className="row" style={{ marginTop: 6 }}>{d.checklist.slots.filter((s) => s.required).map((s) => <span key={s.slot} className="row">{s.label}: <Badge value={s.status} /></span>)}</div>
        </div>
        <div style={{ marginTop: 12 }}>
          <Table rows={d.documents.map((x) => ({ ...x, id: x.document_id }))} empty="No documents uploaded yet." columns={[
            { key: "document_label", label: "Document" }, { key: "original_filename", label: "File" },
            { key: "verification_status", label: "Status", render: (x) => <Badge value={x.verification_status} /> }, { key: "uploaded_at", label: "Uploaded", render: (x) => when(x.uploaded_at) },
            { key: "a", label: "", render: (x) => (<div className="row">
              <button className="btn sm" onClick={() => downloadFile(`/documents/${x.document_id}/download`, p, x.original_filename)}>Open</button>
              {x.verification_status === "PENDING" && <><button className="btn sm" onClick={() => verifyDoc(x.document_id, "VERIFIED")}>Verify</button><button className="btn sm danger" onClick={() => verifyDoc(x.document_id, "REJECTED")}>Reject</button></>}</div>) }]} />
        </div>
      </Card>

      <Card>
        <div className="row">
          <Field label="Mode"><select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="AUTO">Auto ({llmOn ? "AI agents" : "rules only"})</option>
            <option value="AGENTIC" disabled={!llmOn}>AI agents (Groq gpt-oss-120b)</option>
            <option value="DETERMINISTIC">Rule engine only</option></select></Field>
          <button className="btn primary" disabled={busy || live} onClick={start}><Play size={14} /> {live ? "Running…" : "Run verification"}</button>
        </div>
        {!llmOn && <div className="notice" style={{ marginTop: 10 }}>No <b>GROQ_API_KEY</b> is configured, so the AI agents are off and the rule engine is used. Add the key to <span className="mono">.env</span> and restart to enable the agentic debate.</div>}
        <ErrorBox message={error || history.error || run.error} />
      </Card>

      {(history.data || []).length > 0 && (
        <Card title="Runs for this month"><Table rows={history.data.map((x) => ({ ...x, id: x.run_id }))} onRow={(x) => setRunId(x.run_id)} selected={(x) => x.run_id === shownRun} columns={[
          { key: "created_at", label: "Started", render: (x) => when(x.created_at) }, { key: "status", label: "Status", render: (x) => <Badge value={x.status} /> },
          { key: "execution_mode", label: "Mode", render: (x) => <Badge value={x.execution_mode} /> },
          { key: "final_recommendation", label: "Recommendation", render: (x) => x.final_recommendation ? <Badge value={x.final_recommendation} /> : "—" },
          { key: "llm_calls", label: "LLM calls", num: true }, { key: "llm_tokens", label: "Tokens", num: true, render: (x) => fmt(x.llm_tokens, 0) }]} /></Card>)}

      {run.loading && !run.data && shownRun && <Loading />}
      {run.data && (live || run.data.status === "FAILED") && (
        <Card title="Run progress" subtitle={live ? "AI agents are working — this can take a minute or more." : undefined}>
          <div className="log">{run.data.progress.map((x, i) => <div key={i} className={x.level}>{new Date(x.time).toLocaleTimeString()}  {x.message}</div>)}</div>
          {run.data.status === "FAILED" && <ErrorBox message={run.data.error} />}
        </Card>)}

      {cons && (<>
        <Card title="Consensus recommendation" subtitle={`Run ${run.data.run_id} · ${r.execution_mode.replaceAll("_", " ")}${r.llm?.model ? ` · ${r.llm.model}` : ""}`}>
          <div className="grid g4" style={{ marginBottom: 12 }}>
            <Metric label="Final recommendation" value={<Badge value={cons.final_recommendation} />} tone={cons.final_recommendation === "RECOMMEND_APPROVAL" ? "teal" : "warn"} />
            <Metric label="Confidence" value={fmt(cons.confidence_score, 2)} tone="blue" />
            <Metric label="Declared → verified" value={`${fmt(cons.claimed_emissions_kgco2e, 0)} → ${fmt(cons.verified_emissions_kgco2e, 0)}`} hint="kgCO2e" />
            <Metric label="Rule-engine baseline" value={<Badge value={cons.deterministic_recommendation} />} hint={cons.llm_recommendation ? `AI proposed: ${cons.llm_recommendation.replaceAll("_", " ")}` : "no AI used"} />
          </div>
          <p>{cons.primary_reason}</p>
          {cons.explanation && <p className="muted" style={{ marginTop: 6 }}>{cons.explanation}</p>}
          {cons.guard_override && <div className="notice" style={{ marginTop: 10 }}>The safety guard raised the AI's recommendation because the evidence rules require a stricter outcome ({cons.guard_rules_triggered.join(", ")}).</div>}
          <div className="grid g2" style={{ marginTop: 12 }}>
            <div><b className="small">Required actions</b><ul>{cons.required_actions.map((a, i) => <li key={i}>{a}</li>)}</ul></div>
            {cons.dissenting_points?.length > 0 && <div><b className="small">Dissenting points</b><ul>{cons.dissenting_points.map((a, i) => <li key={i}>{a}</li>)}</ul></div>}
          </div>
        </Card>
        <Card title="Agent assessments"><div className="grid g2">
          {r.agent_assessments.map((a) => (
            <div className="agent" key={a.agent_name}>
              <div className="row"><Bot size={16} /><h4>{a.agent_name.replaceAll("_", " ")}</h4><Badge value={a.status} /><Badge value={a.risk_level} /><span className="small muted">conf {fmt(a.confidence_score, 2)}</span></div>
              <p className="small">{a.summary}</p>
              {a.findings.map((f, i) => <div className="finding" key={i}><b>{f.title}</b> — {f.description}</div>)}
              <div className="small muted">Action: {a.recommended_action}</div>
            </div>))}</div></Card>
        <Card title="Debate transcript" subtitle={`${r.debate_messages.length} messages`}>
          <div className="chat">{r.debate_messages.map((m) => (
            <div className="msg" key={m.sequence_number}>
              <div className="who"><b>{m.sender_agent.replaceAll("_", " ")}</b> → {m.recipient_agent.replaceAll("_", " ")} <Badge value={m.message_type} /> <span>round {m.round_number}</span></div>
              <div>{m.content}</div></div>))}</div></Card>
        <Card title="Integrity"><div className="small">Evidence <span className="mono">{short(r.integrity.evidence_bundle_hash)}</span> · Trust <span className="mono">{short(r.integrity.trust_snapshot_hash)}</span> · Report <span className="mono">{short(r.integrity.report_hash)}</span> · Sensor dataset seal <span className="mono">{short(r.evidence_packet.sensors.summary_hash)}</span></div>
          <details style={{ marginTop: 8 }}><summary className="small">Evidence packet the agents received</summary><pre className="json">{JSON.stringify(r.evidence_packet, null, 2)}</pre></details></Card>
      </>)}

      {submitted && !closedMonth && <InfoRequestForm period={period} label={d.label} p={p} suggested={suggested} onSent={refresh} />}
      {d.info_requests.length > 0 && <Card title="Information requests for this month"><Table rows={d.info_requests.map((x) => ({ ...x, id: x.request_id }))} columns={[
        { key: "created_at", label: "Sent", render: (x) => when(x.created_at) }, { key: "title", label: "Title" }, { key: "status", label: "Status", render: (x) => <Badge value={x.status} /> },
        { key: "items", label: "Items", render: (x) => `${x.items.filter((i) => i.fulfilled).length}/${x.items.length} provided` }]} /></Card>}

      {submitted && (
        <Card title="Your decision" subtitle="Final authority rests with you. A completed run is required.">
          <div className="row"><Field label="Decision"><select value={dec.decision} onChange={(e) => setDec({ ...dec, decision: e.target.value })}>{DECISIONS.map((x) => <option key={x}>{x}</option>)}</select></Field></div>
          <Field label="Comments"><textarea value={dec.comments} onChange={(e) => setDec({ ...dec, comments: e.target.value })} /></Field>
          <div className="row" style={{ marginTop: 8 }}><button className="btn primary" disabled={dec.comments.trim().length < 5} onClick={decide}>Record decision</button></div>
        </Card>)}
      {(decisions.data || []).length > 0 && <Card title="Decision history"><Table rows={decisions.data.map((x) => ({ ...x, id: x.decision_id }))} columns={[
        { key: "decided_at", label: "When", render: (x) => when(x.decided_at) }, { key: "decision", label: "Decision", render: (x) => <Badge value={x.decision} /> },
        { key: "comments", label: "Comments" }, { key: "verification_run_id", label: "Run" }]} /></Card>}
    </>
  );
}
