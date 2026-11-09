import React, { useEffect, useRef, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { api } from "../api/client.js";
import { useAuth } from "../state/AuthContext.jsx";
import { MONTHS, periodLabel } from "../../lib/periods.js";

export default function MonthPicker() {
  const { period, setPeriod, companyId } = useAuth();
  const [open, setOpen] = useState(false);
  const [year, setYear] = useState(+period.slice(0, 4));
  const [months, setMonths] = useState([]);
  const box = useRef(null);

  useEffect(() => {
    if (!open || !companyId) return;
    api.get("/calendar", { company_id: companyId, year }).then((d) => setMonths(d.months)).catch(() => setMonths([]));
  }, [open, year, companyId]);
  useEffect(() => {
    const close = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const pick = (p) => { setPeriod(p); setOpen(false); };
  return (
    <div className="cal-wrap" ref={box}>
      <button className="btn" onClick={() => { setYear(+period.slice(0, 4)); setOpen(!open); }}>
        <CalendarDays size={16} /> {periodLabel(period)}
      </button>
      {open && (
        <div className="cal-pop">
          <div className="cal-head">
            <button className="btn sm" onClick={() => setYear(year - 1)} aria-label="Previous year"><ChevronLeft size={14} /></button>
            <strong>{year}</strong>
            <button className="btn sm" onClick={() => setYear(year + 1)} aria-label="Next year"><ChevronRight size={14} /></button>
          </div>
          <div className="cal-grid">
            {MONTHS.map((name, i) => {
              const p = `${year}-${String(i + 1).padStart(2, "0")}`;
              const info = months.find((m) => m.period === p);
              const cls = info?.claim_data ? "has" : info?.sensor_data ? "sensor" : "none";
              return (
                <button key={p} className={`cal-month ${cls} ${p === period ? "on" : ""}`} onClick={() => pick(p)}
                        title={info?.claim_data ? "Claim, meter and sensor data" : info?.sensor_data ? "Sensor data only" : "No data available"}>
                  {name}
                  {info?.open_info_requests > 0 && <span className="pip">{info.open_info_requests}</span>}
                </button>
              );
            })}
          </div>
          <div className="cal-legend small muted">
            <span><i className="dot has" /> full data</span><span><i className="dot sensor" /> sensors only</span><span><i className="dot none" /> no data</span>
          </div>
        </div>
      )}
    </div>
  );
}
