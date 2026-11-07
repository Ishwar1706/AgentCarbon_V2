import React, { useEffect, useRef, useState } from "react";
import { AlertTriangle, LoaderCircle } from "lucide-react";

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
const GOOD = /APPROV|TRUSTED|VERIFIED|HEALTHY|COMPLETED|PASS|SEALED|REHABILIT|VALID|ONLINE/;
const BAD = /REJECT|FAIL|CRITICAL|PENALIZ|TAMPER|AT_RISK|HIGH_RISK|ERROR/;
const WARN = /REVIEW|WARNING|PROBATION|PENDING|OPEN|MORE_EVIDENCE|ADDITIONAL|ESCALAT|RUNNING|QUEUED|SUBMITTED|HIGH|MEDIUM|FALLBACK/;
export function Badge({ value }) {
  const v = String(value ?? "—");
  const kind = BAD.test(v) ? "bad" : WARN.test(v) ? "warn" : GOOD.test(v) ? "good" : "neutral";
  return <span className={`badge ${kind}`}>{v.replaceAll("_", " ")}</span>;
}
export const Loading = ({ text = "Loading…" }) => (
  <div className="state"><LoaderCircle className="spin" size={18} /> {text}</div>
);
export const ErrorBox = ({ message }) =>
  message ? <div className="error-box"><AlertTriangle size={18} /> {message}</div> : null;
export const Empty = ({ text = "Nothing here yet." }) => <div className="state muted">{text}</div>;

/** Fetches on mount / when deps change; optional polling. */
export function useAsync(fn, deps = [], pollMs = 0) {
  const [state, setState] = useState({ data: null, error: "", loading: true });
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const load = (silent) => {
    if (!silent) setState((s) => ({ ...s, loading: true, error: "" }));
    return fnRef.current()
      .then((data) => setState({ data, error: "", loading: false }))
      .catch((e) => setState((s) => ({ data: silent ? s.data : null, error: e.message, loading: false })));
  };
  useEffect(() => {
    load(false);
    if (!pollMs) return;
    const t = setInterval(() => load(true), pollMs);
    return () => clearInterval(t);
    // eslint-disable-next-line
  }, [...deps, pollMs]);
  return { ...state, reload: () => load(true) };
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
