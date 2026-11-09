import React, { useState } from "react";
import { api, downloadFile, openFile } from "../api/client.js";
import { Badge, Card, ErrorBox, Loading, Metric, Table, fmt, short, useAsync, when } from "../components/UI.jsx";

export default function Credits() {
  const sum = useAsync(() => api.get("/credits/summary"), []);
  const list = useAsync(() => api.get("/credits"), []);
  const [company, setCompany] = useState("");
  const [checks, setChecks] = useState({});
  if (list.loading && !list.data) return <Loading />;
  const rows = (list.data || []).filter((r) => !company || r.company_id === company);
  const companies = [...new Map((list.data || []).map((r) => [r.company_id, r.company_name])).entries()];
  const s = sum.data;
  return (
    <>
      <div className="page-title"><h1>Verified carbon credits</h1>
        <p>Only credits that an independent auditor <b>approved</b> and registered in the tamper-evident ledger are listed. Each lot shows how many credits the data supports, and can be re-verified and downloaded as a report.</p></div>
      <ErrorBox message={list.error || sum.error} />
      {s && <div className="grid g4">
        <Metric label="Credit lots" value={s.credit_lots} tone="blue" />
        <Metric label="Total approved credits" value={`${fmt(s.total_credits_tco2e)} t`} hint="tCO2e" />
        <Metric label="Companies" value={s.companies} />
        <Metric label="Registry integrity" value={<Badge value={s.registry_valid ? "VERIFIED" : "TAMPER_DETECTED"} />} hint={`${s.registry_blocks} blocks`} tone={s.registry_valid ? "teal" : "bad"} />
      </div>}
      <Card title="Available credit lots" actions={[
        <select key="c" value={company} onChange={(e) => setCompany(e.target.value)}><option value="">All companies</option>{companies.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select>]}>
        <Table rows={rows.map((r) => ({ ...r, id: r.claim_id }))} empty="No approved credits have been registered yet." columns={[
          { key: "company_name", label: "Company" }, { key: "label", label: "Month" },
          { key: "approved_credits_tco2e", label: "Approved tCO₂e", num: true, render: (r) => <b>{fmt(r.approved_credits_tco2e)}</b> },
          { key: "expected_credits_tco2e", label: "Operator expected", num: true, render: (r) => fmt(r.expected_credits_tco2e) },
          { key: "supported_credits_tco2e", label: "Data supports", num: true, render: (r) => fmt(r.supported_credits_tco2e) },
          { key: "auditor", label: "Auditor" }, { key: "confidence_score", label: "AI confidence", num: true, render: (r) => fmt(r.confidence_score, 2) },
          { key: "block_number", label: "Block", num: true }, { key: "record_hash", label: "Record hash", render: (r) => <span className="mono">{short(r.record_hash)}</span> },
          { key: "registered_at", label: "Registered", render: (r) => when(r.registered_at) },
          { key: "a", label: "", render: (r) => (<div className="row">
            {checks[r.claim_id] ? <Badge value={checks[r.claim_id].status} /> : <button className="btn sm" onClick={async () => setChecks({ ...checks, [r.claim_id]: await api.get(`/credits/${r.claim_id}/verify`) })}>Verify</button>}
            <button className="btn sm" onClick={() => openFile(`/credits/${r.claim_id}/report`, { format: "html" })}>Report</button>
            <button className="btn sm" onClick={() => downloadFile(`/credits/${r.claim_id}/report`, { format: "json" }, `${r.claim_id}.json`)}>JSON</button></div>) },
        ]} />
      </Card>
    </>
  );
}
