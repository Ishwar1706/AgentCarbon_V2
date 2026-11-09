import React from "react";
import { NavLink, Outlet } from "react-router-dom";
import { Activity, BadgeCheck, BarChart3, Bot, FilePenLine, Inbox, LayoutDashboard, LogOut, MessageSquareWarning, ShieldCheck, Users } from "lucide-react";
import { useAuth } from "../state/AuthContext.jsx";
import { Badge, useAsync } from "./UI.jsx";
import MonthPicker from "./MonthPicker.jsx";
import { api } from "../api/client.js";
import { ROLE_LABEL } from "../../lib/periods.js";

const NAV = {
  PLANT_OPERATOR: [
    ["/", "Overview", LayoutDashboard], ["/sensors", "Sensors & Monthly Data", Activity], ["/trust", "Meter Trust", BarChart3],
    ["/request", "Monthly Request", FilePenLine], ["/inbox", "Auditor Requests", Inbox],
  ],
  AUDITOR: [
    ["/", "Overview", LayoutDashboard], ["/sensors", "Sensors & Monthly Data", Activity], ["/trust", "Meter Trust", BarChart3],
    ["/verify", "Review & Agents", Bot], ["/inbox", "Information Requests", MessageSquareWarning], ["/audit", "Audit Registry", ShieldCheck],
  ],
  CREDIT_BUYER: [["/", "Verified Credits", BadgeCheck]],
  ADMIN: [["/", "Accounts & Approvals", Users]],
};

export default function Shell() {
  const { user, logout, companies, companyId, setCompanyId, company } = useAuth();
  const usesData = ["PLANT_OPERATOR", "AUDITOR"].includes(user.role);
  const status = useAsync(() => (user.role === "AUDITOR" ? api.get("/verifications/status") : Promise.resolve(null)), [user.role]);
  const badge = useAsync(() => (usesData && companyId ? api.get("/info-requests/summary", { company_id: companyId }) : Promise.resolve(null)), [companyId, user.role], 15000);
  const count = user.role === "PLANT_OPERATOR" ? badge.data?.open : badge.data?.responded;
  return (
    <div className="layout">
      <aside className="side">
        <div className="brand">AgentCarbon<small>Multi-agent carbon credit verification</small></div>
        <nav className="nav col" style={{ gap: 2 }}>
          {NAV[user.role].map(([to, label, Icon]) => (
            <NavLink key={to} to={to} end={to === "/"}>
              <Icon size={17} /> <span style={{ flex: 1 }}>{label}</span>
              {to === "/inbox" && count > 0 && <span className="count">{count}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="foot">All company data is a synthetic simulation.</div>
      </aside>
      <div className="main">
        <div className="top">
          {user.role === "PLANT_OPERATOR" && <strong>{company?.legal_name || user.company_name}</strong>}
          {user.role === "AUDITOR" && (
            <select value={companyId} onChange={(e) => setCompanyId(e.target.value)} aria-label="Company">
              {companies.length === 0 && <option value="">No companies available</option>}
              {companies.map((c) => <option key={c.company_id} value={c.company_id}>{c.legal_name} ({c.sensor_count} sensors)</option>)}
            </select>
          )}
          {usesData && <MonthPicker />}
          <span className="spacer" />
          {status.data && (
            <span className="small muted">AI agents: {status.data.groq_configured
              ? <Badge value={`GROQ ${status.data.model.split("/").pop()}`} /> : <Badge value="RULES ONLY (no API key)" />}</span>
          )}
          <span className="small">{user.full_name} · <span className="badge neutral">{ROLE_LABEL[user.role]}</span></span>
          <button className="btn sm" onClick={logout}><LogOut size={14} /> Sign out</button>
        </div>
        <main className="content"><Outlet /></main>
      </div>
    </div>
  );
}
