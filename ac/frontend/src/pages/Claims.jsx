import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client.js";
import { useAuth } from "../state/AuthContext.jsx";
import { Badge, Card, Empty, ErrorBox, Loading, Table, fmt, useAsync } from "../components/UI.jsx";

export default function Claims() {
  const { user, companyId } = useAuth();
  const nav = useNavigate();
  const [msg, setMsg] = useState("");
  const claims = useAsync(() => api.get("/dashboard/claims", { company_id: companyId }), [companyId]);
  if (!companyId) return <Empty text="No company selected." />;
  if (claims.loading && !claims.data) return <Loading />;
  const submit = async (id) => {
    setMsg("");
    try { await api.post(`/claims/${id}/submit`, undefined, { company_id: companyId }); claims.reload(); }
    catch (e) { setMsg(e.message); }
  };
  const go = (id, path) => nav(`${path}?claim=${encodeURIComponent(id)}`);
  return (
    <>
      <div className="page-title"><h1>Monthly carbon claims</h1>
        <p>Each claim is checked against the company's meter trust analysis and its sealed monthly sensor dataset.</p></div>
      <ErrorBox message={claims.error || msg} />
      <Card>
        <Table rows={(claims.data || []).map((r) => ({ ...r, id: r.claim_id }))} columns={[
          { key: "month_label", label: "Month", render: (r) => r.month_label.replace("_", " ") },
          { key: "period", label: "Period", render: (r) => `${r.period_start} → ${r.period_end}` },
          { key: "claimed_total_kgco2e", label: "Claimed kg", num: true, render: (r) => fmt(r.claimed_total_kgco2e, 0) },
          { key: "verified_total_kgco2e", label: "Verified kg", num: true, render: (r) => fmt(r.verified_total_kgco2e, 0) },
          { key: "discrepancy_percent", label: "Gap %", num: true, render: (r) => fmt(r.discrepancy_percent) },
          { key: "workflow_status", label: "Status", render: (r) => <Badge value={r.workflow_status} /> },
          { key: "recommendation", label: "AI recommendation", render: (r) => r.recommendation ? <Badge value={r.recommendation} /> : <span className="muted">—</span> },
          { key: "auditor_decision", label: "Auditor", render: (r) => r.auditor_decision ? <Badge value={r.auditor_decision} /> : <span className="muted">—</span> },
          { key: "actions", label: "", render: (r) => (
            <div className="row">
              {user.role === "PLANT_OPERATOR" && ["NOT_SUBMITTED", "MORE_EVIDENCE_REQUESTED"].includes(r.workflow_status) && <button className="btn sm primary" onClick={() => submit(r.claim_id)}>Submit</button>}
              <button className="btn sm" onClick={() => go(r.claim_id, "/verify")}>{user.role === "AUDITOR" ? "Verify" : "Open"}</button>
              <button className="btn sm" onClick={() => go(r.claim_id, "/evidence")}>Evidence</button>
            </div>) },
        ]} />
      </Card>
    </>
  );
}
