import React, { useState } from "react";
import { api, downloadFile, openFile } from "../api/client.js";
import { useAuth } from "../state/AuthContext.jsx";
import { Badge, Card, Empty, ErrorBox, Table, short, useAsync, when } from "../components/UI.jsx";

export default function Audit() {
  const { user, companyId } = useAuth();
  const p = { company_id: companyId };
  const records = useAsync(() => api.get("/audit/records", p), [companyId]);
  const claims = useAsync(() => api.get("/dashboard/claims", p), [companyId]);
  const chain = useAsync(() => api.get("/audit/chain/verify"), [records.data?.length]);
  const [checks, setChecks] = useState({});
  const [error, setError] = useState("");
  if (!companyId) return <Empty text="No company selected." />;
  const registered = new Set((records.data || []).map((r) => r.claim_id));
  const ready = (claims.data || []).filter((c) => c.auditor_decision && !registered.has(c.claim_id));
  const reportable = (claims.data || []).filter((c) => c.latest_run_id);
  const act = async (fn) => { setError(""); try { await fn(); records.reload(); } catch (e) { setError(e.message); } };
  return (
    <>
      <div className="page-title"><h1>Audit registry</h1>
        <p>Each finalised claim is written to an append-only, hash-chained ledger. Any change to a stored report, evidence hash or earlier block is detected. (A local tamper-evident registry — not a public blockchain.)</p></div>
      <ErrorBox message={error || records.error} />
      <div className="grid g2">
        <Card title="Chain integrity">
          {chain.data ? <div className="row"><Badge value={chain.data.valid ? "VERIFIED" : "TAMPER_DETECTED"} /> <span>{chain.data.block_count} blocks in the registry</span></div> : "…"}
        </Card>
        {user.role === "AUDITOR" && (
          <Card title="Ready to register" subtitle="Claims with a completed run and an auditor decision.">
            {ready.length === 0 ? <span className="muted">None waiting.</span> : ready.map((c) => (
              <div className="row" key={c.claim_id} style={{ marginBottom: 6 }}>
                <span>{c.month_label.replace("_", " ")}</span><Badge value={c.auditor_decision} />
                <button className="btn sm primary" onClick={() => act(() => api.post(`/audit/register/${c.claim_id}`, undefined, p))}>Register</button>
              </div>))}
          </Card>
        )}
      </div>
      <Card title="Registry records">
        <Table rows={(records.data || []).map((r) => ({ ...r, id: r.claim_id }))} empty="No claims registered yet." columns={[
          { key: "block_number", label: "Block", num: true }, { key: "claim_id", label: "Claim", render: (r) => r.claim_id.replace(/^sim-/, "") },
          { key: "recommendation", label: "AI recommendation", render: (r) => <Badge value={r.recommendation} /> }, { key: "auditor_decision", label: "Auditor", render: (r) => <Badge value={r.auditor_decision} /> },
          { key: "record_hash", label: "Record hash", render: (r) => <span className="mono">{short(r.record_hash)}</span> },
          { key: "registered_at", label: "Registered", render: (r) => when(r.registered_at) },
          { key: "v", label: "Verification", render: (r) => checks[r.claim_id] ? <Badge value={checks[r.claim_id].status} /> : <button className="btn sm" onClick={async () => setChecks({ ...checks, [r.claim_id]: await api.get(`/audit/records/${r.claim_id}/verify`, p) })}>Verify</button> },
        ]} />
      </Card>
      <Card title="Reports" subtitle="Generated from the latest completed run and auditor decision.">
        <Table rows={reportable.map((c) => ({ ...c, id: c.claim_id }))} empty="Run a verification to produce a report." columns={[
          { key: "month_label", label: "Month", render: (c) => c.month_label.replace("_", " ") }, { key: "recommendation", label: "Recommendation", render: (c) => <Badge value={c.recommendation} /> },
          { key: "a", label: "", render: (c) => (<div className="row">
            <button className="btn sm" onClick={() => openFile(`/reports/${c.claim_id}`, { ...p, format: "html" })}>Open HTML</button>
            <button className="btn sm" onClick={() => downloadFile(`/reports/${c.claim_id}`, { ...p, format: "json" }, `${c.claim_id}.json`)}>Download JSON</button></div>) }]} />
      </Card>
    </>
  );
}
