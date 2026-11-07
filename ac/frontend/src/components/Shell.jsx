import React from "react";
import { NavLink, Outlet } from "react-router-dom";
import { Activity, BarChart3, Bot, FileCheck2, FileText, LayoutDashboard, LogOut, ShieldCheck, Users } from "lucide-react";
import { useAuth } from "../state/AuthContext.jsx";
import { Badge, ErrorBox, useAsync } from "./UI.jsx";
import { api } from "../api/client.js";

const NAV = [
  ["/", "Overview", LayoutDashboard, ["PLANT_OPERATOR", "AUDITOR", "REGULATOR_VIEWER"]],
  ["/sensors", "Sensors & Monthly Data", Activity, ["PLANT_OPERATOR", "AUDITOR", "REGULATOR_VIEWER", "ADMIN"]],
  ["/trust", "Meter Trust", BarChart3, ["PLANT_OPERATOR", "AUDITOR", "REGULATOR_VIEWER", "ADMIN"]],
  ["/claims", "Claims", FileText, ["PLANT_OPERATOR", "AUDITOR", "REGULATOR_VIEWER", "ADMIN"]],
  ["/verify", "Agent Verification", Bot, ["PLANT_OPERATOR", "AUDITOR", "REGULATOR_VIEWER"]],
  ["/evidence", "Evidence", FileCheck2, ["PLANT_OPERATOR", "AUDITOR", "REGULATOR_VIEWER", "ADMIN"]],
  ["/audit", "Audit Registry", ShieldCheck, ["PLANT_OPERATOR", "AUDITOR", "REGULATOR_VIEWER", "ADMIN"]],
  ["/admin", "Admin Review", Users, ["ADMIN"]],
];

export default function Shell() {
  const { user, logout, companies, companyId, setCompanyId, company } = useAuth();
  const status = useAsync(() => api.get("/verifications/status"), []);
  const isOperator = user.role === "PLANT_OPERATOR";
  return (
    <div className="layout">
      <aside className="side">
        <div className="brand">AgentCarbon<small>Multi-agent carbon claim verification</small></div>
        <nav className="nav col" style={{ gap: 2 }}>
          {NAV.filter((n) => n[3].includes(user.role)).map(([to, label, Icon]) => (
            <NavLink key={to} to={to} end={to === "/"}><Icon size={17} /> {label}</NavLink>
          ))}
        </nav>
        <div className="foot">All company data is a synthetic simulation.</div>
      </aside>
      <div className="main">
        <div className="top">
          {isOperator ? (
            <strong>{company?.legal_name || user.company_name || "Company pending verification"}</strong>
          ) : (
            <select value={companyId} onChange={(e) => setCompanyId(e.target.value)} aria-label="Company">
              {companies.length === 0 && <option value="">No companies available</option>}
              {companies.map((c) => (
                <option key={c.company_id} value={c.company_id}>{c.legal_name} ({c.sensor_count} sensors)</option>
              ))}
            </select>
          )}
          <span className="spacer" />
          {status.data && (
            <span className="small muted">
              AI agents: {status.data.groq_configured ? <Badge value={`GROQ ${status.data.model.split("/").pop()}`} /> : <Badge value="RULES ONLY (no API key)" />}
            </span>
          )}
          <span className="small">{user.full_name} · <Badge value={user.role} /></span>
          <button className="btn sm" onClick={logout}><LogOut size={14} /> Sign out</button>
        </div>
        <main className="content">
          {user.role === "AUDITOR" && user.auditor_verified === false && (
            <ErrorBox message="Your auditor account is awaiting administrator verification." />
          )}
          <Outlet />
        </main>
      </div>
    </div>
  );
}
