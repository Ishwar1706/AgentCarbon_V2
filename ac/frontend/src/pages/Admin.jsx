import React, { useState } from "react";
import { api } from "../api/client.js";
import { Badge, Card, ErrorBox, Field, Loading, Metric, Table, useAsync, when } from "../components/UI.jsx";

const TABS = [["pending", "Pending approvals"], ["history", "Reviewed applications"], ["accounts", "Accounts"]];

export default function Admin() {
  const [tab, setTab] = useState("pending");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const apps = useAsync(() => api.get("/admin/applications"), []);
  const summary = useAsync(() => api.get("/admin/summary"), []);
  const accounts = useAsync(() => api.get("/admin/accounts", { role, status, q }), [role, status, q]);
  const refresh = () => { apps.reload(); accounts.reload(); summary.reload(); };

  const review = async (a, action) => {
    setError(""); setNotice("");
    const note = window.prompt(`Optional note for ${action.toLowerCase()}ing ${a.name}:`) ?? null;
    if (note === null) return;
    try { await api.post(`/admin/applications/${a.application_id}/review`, { action, note }); refresh(); } catch (e) { setError(e.message); }
  };
  const setAccount = async (u, st) => {
    setError(""); setNotice("");
    try { await api.post(`/admin/accounts/${u.id}/status`, { status: st }); refresh(); } catch (e) { setError(e.message); }
  };
  const reset = async (u) => {
    setError(""); setNotice("");
    if (!window.confirm(`Reset the password for ${u.email}?`)) return;
    try { const r = await api.post(`/admin/accounts/${u.id}/reset-password`); setNotice(`Temporary password for ${r.email}: ${r.temporary_password} — share it once; the user should change it.`); }
    catch (e) { setError(e.message); }
  };
  if (apps.loading && !apps.data) return <Loading />;
  const all = apps.data || [];
  const pending = all.filter((a) => a.status === "PENDING");
  const sm = summary.data;
  const appCols = (actions) => [
    { key: "type", label: "Type", render: (a) => <Badge value={a.type} /> }, { key: "name", label: "Organisation" },
    { key: "applicant", label: "Applicant", render: (a) => <span>{a.applicant_name}<br /><span className="small muted">{a.applicant}</span></span> },
    { key: "detail", label: "Details", render: (a) => <span className="small">{a.detail}</span> },
    { key: "status", label: "Status", render: (a) => <Badge value={a.status} /> }, { key: "created_at", label: "Submitted", render: (a) => when(a.created_at) },
    ...(actions ? [{ key: "a", label: "", render: (a) => (<div className="row"><button className="btn sm primary" onClick={() => review(a, "APPROVE")}>Approve</button><button className="btn sm danger" onClick={() => review(a, "REJECT")}>Reject</button></div>) }] : [{ key: "note", label: "Note", render: (a) => a.note || "—" }]),
  ];
  return (
    <>
      <div className="page-title"><h1>Accounts & approvals</h1>
        <p>Verify company operators, auditors and credit buyers before they can sign in, and maintain their accounts. Administrators cannot see company or credit data.</p></div>
      <div className="grid g4">
        <Metric label="Waiting for approval" value={sm?.pending_applications ?? "—"} tone={sm?.pending_applications ? "warn" : "teal"} />
        {Object.entries(sm?.accounts_by_role || {}).map(([r, n]) => <Metric key={r} label={`${r.replaceAll("_", " ").toLowerCase()} accounts`} value={n} tone="blue" />)}
      </div>
      <ErrorBox message={error || apps.error} />
      {notice && <div className="notice">{notice}</div>}
      <div className="tabs">{TABS.map(([k, l]) => <button key={k} className={`tab ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}>{l}{k === "pending" && pending.length ? ` (${pending.length})` : ""}</button>)}</div>
      {tab === "pending" && <Card><Table rows={pending.map((a) => ({ ...a, id: a.application_id }))} empty="No registrations are waiting." columns={appCols(true)} /></Card>}
      {tab === "history" && <Card><Table rows={all.filter((a) => a.status !== "PENDING").map((a) => ({ ...a, id: a.application_id }))} empty="Nothing reviewed yet." columns={appCols(false)} /></Card>}
      {tab === "accounts" && (
        <Card title="All accounts" actions={[
          <input key="q" placeholder="Search name or email" value={q} onChange={(e) => setQ(e.target.value)} />,
          <select key="r" value={role} onChange={(e) => setRole(e.target.value)}><option value="">All roles</option><option value="PLANT_OPERATOR">Operators</option><option value="AUDITOR">Auditors</option><option value="CREDIT_BUYER">Credit buyers</option><option value="ADMIN">Admins</option></select>,
          <select key="s" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All statuses</option><option>ACTIVE</option><option>SUSPENDED</option><option>PENDING</option><option>REJECTED</option></select>]}>
          <Table rows={(accounts.data || []).map((u) => ({ ...u, id: u.id }))} empty="No accounts match." columns={[
            { key: "full_name", label: "Name" }, { key: "email", label: "Email" }, { key: "role", label: "Role", render: (u) => <Badge value={u.role} /> },
            { key: "organization", label: "Organisation", render: (u) => u.organization || "—" }, { key: "account_status", label: "Status", render: (u) => <Badge value={u.account_status} /> },
            { key: "created_at", label: "Created", render: (u) => when(u.created_at) },
            { key: "a", label: "", render: (u) => (<div className="row">
              {u.account_status === "ACTIVE" && u.role !== "ADMIN" && <button className="btn sm danger" onClick={() => setAccount(u, "SUSPENDED")}>Deactivate</button>}
              {u.account_status === "SUSPENDED" && <button className="btn sm" onClick={() => setAccount(u, "ACTIVE")}>Activate</button>}
              <button className="btn sm" onClick={() => reset(u)}>Reset password</button></div>) },
          ]} />
        </Card>)}
    </>
  );
}
