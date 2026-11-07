import React, { useState } from "react";
import { Card, ErrorBox, Field, useAsync } from "../components/UI.jsx";
import { api } from "../api/client.js";
import { useAuth } from "../state/AuthContext.jsx";

export default function Login() {
  const { login } = useAuth();
  const demo = useAsync(() => api.get("/auth/demo-accounts"), []);
  const [mode, setMode] = useState("signin");
  const [f, setF] = useState({ email: "", password: "", full_name: "", legal_name: "", state: "", city: "", organization: "", credentials: "" });
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const run = async (fn) => {
    setBusy(true); setError(""); setInfo("");
    try { await fn(); } catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  const submit = (e) => {
    e.preventDefault();
    run(async () => {
      if (mode === "signin") return login(f.email, f.password);
      const path = mode === "company" ? "/auth/register/company" : "/auth/register/auditor";
      const body = mode === "company"
        ? { email: f.email, password: f.password, full_name: f.full_name, legal_name: f.legal_name, state: f.state, city: f.city }
        : { email: f.email, password: f.password, full_name: f.full_name, organization: f.organization, credentials: f.credentials };
      const r = await api.post(path, body);
      setInfo(r.message); setMode("signin");
    });
  };
  const d = demo.data;
  return (
    <div className="login-wrap">
      <div className="login">
        <Card title="AgentCarbon" subtitle="Sensor-backed, multi-agent verification of monthly carbon claims">
          <form className="col" onSubmit={submit}>
            <div className="tabs">
              {[["signin", "Sign in"], ["company", "Register company"], ["auditor", "Register auditor"]].map(([k, l]) => (
                <button type="button" key={k} className={`tab ${mode === k ? "on" : ""}`} onClick={() => setMode(k)}>{l}</button>
              ))}
            </div>
            {mode !== "signin" && <Field label="Full name"><input value={f.full_name} onChange={set("full_name")} required /></Field>}
            <Field label="Email"><input type="email" value={f.email} onChange={set("email")} required /></Field>
            <Field label="Password"><input type="password" value={f.password} onChange={set("password")} required minLength={mode === "signin" ? 1 : 10} /></Field>
            {mode === "company" && (<>
              <Field label="Company legal name"><input value={f.legal_name} onChange={set("legal_name")} required /></Field>
              <div className="row"><Field label="State"><input value={f.state} onChange={set("state")} required /></Field>
              <Field label="City"><input value={f.city} onChange={set("city")} required /></Field></div>
            </>)}
            {mode === "auditor" && (<>
              <Field label="Organization"><input value={f.organization} onChange={set("organization")} required /></Field>
              <Field label="Credentials"><textarea value={f.credentials} onChange={set("credentials")} required /></Field>
            </>)}
            <ErrorBox message={error} />
            {info && <div className="notice">{info}</div>}
            <button className="btn primary" disabled={busy}>{busy ? "Please wait…" : mode === "signin" ? "Sign in" : "Submit registration"}</button>
          </form>
        </Card>
        {d?.demo_mode && (
          <Card title="Demo accounts" subtitle={`One click fills the form · password: ${d.password}`}>
            <div className="col" style={{ gap: 6 }}>
              {d.accounts.map((a) => (
                <button key={a.email} className="btn sm demo-btn" type="button"
                        onClick={() => { setMode("signin"); setF({ ...f, email: a.email, password: d.password }); }}>
                  <span>{a.label}</span><span className="muted small">{a.role.replace("_", " ")}</span>
                </button>
              ))}
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
