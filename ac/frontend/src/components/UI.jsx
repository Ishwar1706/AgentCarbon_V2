import React, { useEffect, useRef, useState } from "react";
import { AlertTriangle, CalendarX, LoaderCircle } from "lucide-react";
import { periodLabel } from "../../lib/periods.js";

export const fmt = (v, d = 2) =>
  v === null || v === undefined || Number.isNaN(Number(v)) ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: d });
export const short = (h) => (h ? `${h.slice(0, 10)}…${h.slice(-6)}` : "—");
export const when = (t) => (t ? new Date(t).toLocaleString() : "—");

export function Card({ title, subtitle, actions, children, className = "" }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          <div>
            {title && <h3>{title}</h3>}
            {subtitle && <p>{subtitle}</p>}
          </div>
          {actions && <div className="row">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}
export function Metric({ label, value, hint, tone = "teal" }) {
  return (
    <div className={`metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {hint && <small>{hint}</small>}
    </div>
  );
}
const GOOD = /APPROV|ACTIVE|TRUSTED|VERIFIED|HEALTHY|COMPLETED|PASS|SEALED|REHABILIT|VALID|ONLINE/;
const BAD = /REJECT|SUSPEND|MISSING|FAIL|CRITICAL|PENALIZ|TAMPER|AT_RISK|HIGH_RISK|ERROR/;
const WARN = /INFO_REQUESTED|NOT_STARTED|NOT_SUBMITTED|DRAFT|PROVIDED|RESPONDED|OPEN|REVIEW|WARNING|PROBATION|PENDING|OPEN|MORE_EVIDENCE|ADDITIONAL|ESCALAT|RUNNING|QUEUED|SUBMITTED|HIGH|MEDIUM|FALLBACK/;
const NICE = {
  ADDITIONAL_EVIDENCE_REQUIRED: "Manual review – evidence missing",
  RECOMMEND_APPROVAL: "Recommend approval", RECOMMEND_REJECTION: "Recommend rejection",
  APPROVAL_AFTER_PROBATION_REVIEW: "Approve after probation review", MANUAL_REVIEW: "Manual review",
  INFO_REQUESTED: "Information requested", NOT_STARTED: "Not started", PLANT_OPERATOR: "Plant operator",
  CREDIT_BUYER: "Credit buyer", COMPANY_OPERATOR: "Company operator",
};
export function Badge({ value }) {
  const raw = String(value ?? "—");
  const kind = BAD.test(raw) ? "bad" : WARN.test(raw) ? "warn" : GOOD.test(raw) ? "good" : "neutral";
  return <span className={`badge ${kind}`}>{NICE[raw] || raw.replaceAll("_", " ")}</span>;
}
export function NoData({ period, text }) {
  return (
    <div className="card nodata">
      <CalendarX size={34} />
      <h3>No data available for {periodLabel(period)}</h3>
      <p className="muted">{text || "Monthly data exists for Jan – May 2026 (plus any months produced by the live sensor simulator). Pick another month in the calendar."}</p>
    </div>
  );
}
export const Loading = ({ text = "Loading…" }) => (
  <div className="state"><LoaderCircle className="spin" size={18} /> {text}</div>
);
export const ErrorBox = ({ message }) =>
  message ? <div className="error-box"><AlertTriangle size={18} /> {message}</div> : null;
export const Empty = ({ text = "Nothing here yet." }) => <div className="state muted">{text}</div>;

/** Fetches on mount / when deps change; optional polling. While the deps differ from the
 *  last completed load, `loading` is true and `data` is null (never stale data for another company/month). */
export function useAsync(fn, deps = [], pollMs = 0) {
  const key = JSON.stringify(deps);
  const [state, setState] = useState({ data: null, error: "", loading: true, key: null });
  const fnRef = useRef(fn);
  const keyRef = useRef(key);
  fnRef.current = fn;
  keyRef.current = key;
  const load = (silent) => {
    const k = keyRef.current;
    if (!silent) setState((s) => ({ ...s, loading: true, error: "" }));
    return fnRef.current()
      .then((data) => { if (k === keyRef.current) setState({ data, error: "", loading: false, key: k }); })
      .catch((e) => { if (k === keyRef.current) setState((s) => ({ data: silent ? s.data : null, error: e.message, loading: false, key: k })); });
  };
  useEffect(() => {
    load(false);
    if (!pollMs) return;
    const t = setInterval(() => load(true), pollMs);
    return () => clearInterval(t);
    // eslint-disable-next-line
  }, [key, pollMs]);
  const stale = state.key !== key;
  return { data: stale ? null : state.data, error: stale ? "" : state.error, loading: stale || state.loading, reload: () => load(true) };
}

export function Table({ columns, rows, empty = "No rows", onRow, selected }) {
  if (!rows?.length) return <Empty text={empty} />;
  return (
    <div className="table-wrap">
      <table>
        <thead><tr>{columns.map((c) => <th key={c.key} className={c.num ? "num" : ""}>{c.label}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id ?? i} onClick={onRow ? () => onRow(r) : undefined}
                className={`${onRow ? "clickable" : ""} ${selected && selected(r) ? "selected" : ""}`}>
              {columns.map((c) => <td key={c.key} className={c.num ? "num" : ""}>{c.render ? c.render(r) : r[c.key]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Field({ label, children }) {
  return <label className="field"><span>{label}</span>{children}</label>;
}
export function Progress({ percent }) {
  return <div className="bar"><div style={{ width: `${Math.min(100, percent || 0)}%` }} /></div>;
}
