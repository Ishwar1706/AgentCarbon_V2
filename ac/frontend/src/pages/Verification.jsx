import React, { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bot, Play } from "lucide-react";
import { api } from "../api/client.js";
import { useAuth } from "../state/AuthContext.jsx";
import { Badge, Card, Empty, ErrorBox, Field, Loading, Metric, Table, fmt, short, useAsync, when } from "../components/UI.jsx";

const run0Status = (list, id) => list?.find((r) => r.run_id === id)?.status;
const DECISIONS = ["APPROVE", "REJECT", "REQUEST_MORE_EVIDENCE", "ESCALATE"];

export default function Verification() {
  const { user, companyId } = useAuth();
  const [qs, setQs] = useSearchParams();
  const p = { company_id: companyId };
  const claims = useAsync(() => api.get("/dashboard/claims", p), [companyId]);
  const sys = useAsync(() => api.get("/verifications/status"), []);
  const claimId = qs.get("claim") || claims.data?.[0]?.claim_id || "";
  const [mode, setMode] = useState("AUTO");
  const [runId, setRunId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const history = useAsync(() => (claimId ? api.get("/verifications/runs", { ...p, claim_id: claimId }) : Promise.resolve([])), [companyId, claimId]);
  useEffect(() => { setRunId(""); }, [claimId, companyId]);
  const shownRun = runId || history.data?.find((r) => r.status === "COMPLETED")?.run_id || history.data?.[0]?.run_id || "";
  const [watching, setWatching] = useState(false);
  const run = useAsync(() => (shownRun ? api.get(`/verifications/runs/${shownRun}`, p) : Promise.resolve(null)), [shownRun, companyId],
    shownRun && (watching || ["QUEUED", "RUNNING"].includes(run0Status(history.data, shownRun))) ? 1500 : 0);
  const decisions = useAsync(() => (claimId ? api.get("/auditor/decisions", { ...p, claim_id: claimId }) : Promise.resolve([])), [companyId, claimId]);
  const [dec, setDec] = useState({ decision: "APPROVE", comments: "" });
  const live = run.data && ["QUEUED", "RUNNING"].includes(run.data.status);
  useEffect(() => { if (run.data && !live) { setWatching(false); history.reload(); } }, [run.data?.status]);
  useEffect(() => { if (live) { const t = setInterval(history.reload, 2000); return () => clearInterval(t); } }, [live]);
  if (!companyId) return <Empty text="No company selected." />;
  const isAuditor = user.role === "AUDITOR";
  const canRun = ["AUDITOR", "PLANT_OPERATOR"].includes(user.role);

  const start = async () => {
    setBusy(true); setError("");
    try { const r = await api.post("/verifications/run", { claim_id: claimId, mode }, p); setRunId(r.run_id); setWatching(true); history.reload(); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  const decide = async () => {
    setError("");
    try { await api.post("/auditor/decisions", { claim_id: claimId, ...dec }, p); setDec({ ...dec, comments: "" }); decisions.reload(); claims.reload(); }
    catch (e) { setError(e.message); }
  };
  const r = run.data?.result, cons = r?.consensus;
  const llmOn = sys.data?.groq_configured;
  return (
    <>
      <div className="page-title"><h1>Agent verification</h1>
        <p>Four specialist agents analyse the evidence, debate, and a consensus agent proposes a recommendation. A deterministic safety guard can only make it stricter. The auditor decides.</p></div>
      <Card>
        <div className="row">
          <Field label="Claim"><select value={claimId} onChange={(e) => setQs({ claim: e.target.value })}>{(claims.data || []).map((c) => <option key={c.claim_id} value={c.claim_id}>{c.month_label.replace("_", " ")} — {c.claim_id.replace(/^sim-/, "")}</option>)}</select></Field>
          {canRun && (isAuditor ? (
            <Field label="Mode"><select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="AUTO">Auto ({llmOn ? "AI agents" : "rules only"})</option>
              <option value="AGENTIC" disabled={!llmOn}>AI agents (Groq gpt-oss-120b)</option>
              <option value="DETERMINISTIC">Rule engine only</option></select></Field>
          ) : <span className="small muted">Operators can run a free rule-engine pre-check.</span>)}
          {canRun && <button className="btn primary" disabled={busy || live || !claimId} onClick={start}><Play size={14} /> {live ? "Running…" : "Run verification"}</button>}
        </div>
        {!llmOn && isAuditor && <div className="notice" style={{ marginTop: 10 }}>No <b>GROQ_API_KEY</b> is configured, so the AI agents are off and the deterministic rule engine is used. Add the key to <span className="mono">.env</span> and restart to enable the full agentic debate.</div>}
        <ErrorBox message={error || history.error || run.error} />
      </Card>

      {(history.data || []).length > 0 && (
        <Card title="Runs for this claim">
          <Table rows={history.data.map((x) => ({ ...x, id: x.run_id }))} onRow={(x) => setRunId(x.run_id)} selected={(x) => x.run_id === shownRun} columns={[
            { key: "created_at", label: "Started", render: (x) => when(x.created_at) }, { key: "status", label: "Status", render: (x) => <Badge value={x.status} /> },
            { key: "execution_mode", label: "Mode", render: (x) => <Badge value={x.execution_mode} /> },
            { key: "final_recommendation", label: "Recommendation", render: (x) => x.final_recommendation ? <Badge value={x.final_recommendation} /> : "—" },
            { key: "llm_calls", label: "LLM calls", num: true }, { key: "llm_tokens", label: "Tokens", num: true, render: (x) => fmt(x.llm_tokens, 0) },
          ]} />
        </Card>
      )}

      {run.loading && !run.data && shownRun && <Loading />}
      {run.data && (live || run.data.status === "FAILED" || run.data.progress?.length > 0) && (
        <Card title="Run progress" subtitle={live ? "AI agents are working — this can take a minute or more." : undefined}>
          <div className="log">{run.data.progress.map((x, i) => <div key={i} className={x.level}>{new Date(x.time).toLocaleTimeString()}  {x.message}</div>)}</div>
          {run.data.status === "FAILED" && <ErrorBox message={run.data.error} />}
        </Card>
      )}

      {cons && (<>
        <Card title="Consensus recommendation" subtitle={`Run ${run.data.run_id} · ${r.execution_mode.replaceAll("_", " ")}${r.llm?.model ? ` · ${r.llm.model}` : ""}`}>
          <div className="grid g4" style={{ marginBottom: 12 }}>
            <Metric label="Final recommendation" value={<Badge value={cons.final_recommendation} />} tone={cons.final_recommendation === "RECOMMEND_APPROVAL" ? "teal" : "warn"} />
            <Metric label="Confidence" value={fmt(cons.confidence_score, 2)} tone="blue" />
            <Metric label="Claimed → verified" value={`${fmt(cons.claimed_emissions_kgco2e, 0)} → ${fmt(cons.verified_emissions_kgco2e, 0)}`} hint="kgCO2e" />
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
            </div>))}
        </div></Card>
        <Card title="Debate transcript" subtitle={`${r.debate_messages.length} messages`}>
          <div className="chat">{r.debate_messages.map((m) => (
            <div className="msg" key={m.sequence_number}>
              <div className="who"><b>{m.sender_agent.replaceAll("_", " ")}</b> → {m.recipient_agent.replaceAll("_", " ")} <Badge value={m.message_type} /> <span>round {m.round_number}</span></div>
              <div>{m.content}</div>
            </div>))}</div>
        </Card>
        <Card title="Integrity"><div className="small">Evidence <span className="mono">{short(r.integrity.evidence_bundle_hash)}</span> · Trust <span className="mono">{short(r.integrity.trust_snapshot_hash)}</span> · Report <span className="mono">{short(r.integrity.report_hash)}</span> · Sensor dataset seal <span className="mono">{short(r.evidence_packet.sensors.summary_hash)}</span></div>
          <details style={{ marginTop: 8 }}><summary className="small">Evidence packet the agents received</summary><pre className="json">{JSON.stringify(r.evidence_packet, null, 2)}</pre></details></Card>
      </>)}

      {isAuditor && claimId && (
        <Card title="Auditor decision" subtitle="Final authority rests with you. A completed run is required.">
          <div className="row"><Field label="Decision"><select value={dec.decision} onChange={(e) => setDec({ ...dec, decision: e.target.value })}>{DECISIONS.map((d) => <option key={d}>{d}</option>)}</select></Field></div>
          <Field label="Comments"><textarea value={dec.comments} onChange={(e) => setDec({ ...dec, comments: e.target.value })} /></Field>
          <div className="row" style={{ marginTop: 8 }}><button className="btn primary" disabled={dec.comments.trim().length < 5} onClick={decide}>Record decision</button></div>
        </Card>
      )}
      {(decisions.data || []).length > 0 && (
        <Card title="Decision history"><Table rows={decisions.data.map((d) => ({ ...d, id: d.decision_id }))} columns={[
          { key: "decided_at", label: "When", render: (d) => when(d.decided_at) }, { key: "decision", label: "Decision", render: (d) => <Badge value={d.decision} /> },
          { key: "comments", label: "Comments" }, { key: "verification_run_id", label: "Run" }]} /></Card>
      )}
    </>
  );
}
