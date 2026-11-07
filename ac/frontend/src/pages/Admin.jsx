import React, { useState } from "react";
import { api } from "../api/client.js";
import { Badge, Card, ErrorBox, Loading, Table, useAsync, when } from "../components/UI.jsx";

export default function Admin() {
  const apps = useAsync(() => api.get("/admin/applications"), []);
  const [error, setError] = useState("");
  const review = async (id, action) => {
    setError("");
    const note = window.prompt(`Optional note for ${action.toLowerCase()}:`) || "";
    try { await api.post(`/admin/applications/${id}/review`, { action, note }); apps.reload(); } catch (e) { setError(e.message); }
  };
  if (apps.loading && !apps.data) return <Loading />;
  return (
    <>
      <div className="page-title"><h1>Admin review</h1><p>Approve new companies and auditors before they can access any data.</p></div>
      <ErrorBox message={error || apps.error} />
      <Card>
        <Table rows={(apps.data || []).map((a) => ({ ...a, id: a.application_id }))} empty="No applications." columns={[
          { key: "type", label: "Type", render: (a) => <Badge value={a.type} /> }, { key: "name", label: "Name" }, { key: "applicant", label: "Applicant" },
          { key: "detail", label: "Details" }, { key: "status", label: "Status", render: (a) => <Badge value={a.status} /> }, { key: "created_at", label: "Submitted", render: (a) => when(a.created_at) },
          { key: "a", label: "", render: (a) => a.status === "PENDING" && (<div className="row">
            <button className="btn sm primary" onClick={() => review(a.application_id, "APPROVE")}>Approve</button>
            <button className="btn sm danger" onClick={() => review(a.application_id, "REJECT")}>Reject</button></div>) },
        ]} />
      </Card>
    </>
  );
}
