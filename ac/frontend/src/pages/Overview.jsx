import React, { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client.js";
import { useAuth } from "../state/AuthContext.jsx";
import { Badge, Card, Empty, ErrorBox, Loading, Metric, Table, fmt, useAsync } from "../components/UI.jsx";
import { Lines, COLORS } from "../components/Charts.jsx";

export default function Overview() {
  const { companyId, company } = useAuth();
  const [month, setMonth] = useState(1);
  const p = { company_id: companyId };
  const ov = useAsync(() => api.get("/dashboard/overview", { ...p, month_number: month }), [companyId, month]);
  const cmp = useAsync(() => api.get("/dashboard/monthly-comparison", p), [companyId]);
  const shops = useAsync(() => api.get("/dashboard/shop-energy", p), [companyId]);
  const daily = useAsync(() => api.get("/dashboard/daily-emissions", { ...p, month_number: month }), [companyId, month]);
  if (!companyId) return <Empty text="No company selected." />;
  if (ov.loading && !ov.data) return <Loading />;
  if (ov.error) return <ErrorBox message={ov.error} />;
  const o = ov.data, c = o.claim, s = o.sensors;
  const rows = cmp.data || [];
  const sevTone = c.discrepancy_percent > 15 ? "bad" : c.discrepancy_percent > 5 ? "warn" : "teal";
  return (
    <>
      <div className="page-title">
        <h1>{company?.legal_name}</h1>
        <p>Five months of claims, each backed by the company's own sensor fleet and meter-trust analysis.</p>
      </div>
      <div className="tabs">
        {rows.map((r) => <button key={r.month_number} className={`tab ${month === r.month_number ? "on" : ""}`} onClick={() => setMonth(r.month_number)}>{r.month_label.replace("_", " ")}</button>)}
      </div>
      <div className="grid g4">
        <Metric label="Claimed emissions" value={`${fmt(c.claimed_total_kgco2e, 0)} kg`} hint="kgCO2e as filed" tone="blue" />
        <Metric label="Verified emissions" value={`${fmt(c.verified_total_kgco2e, 0)} kg`} hint="from trusted meter fusion" />
        <Metric label="Discrepancy" value={`${fmt(c.discrepancy_percent)}%`} tone={sevTone} hint={c.recommendation ? c.recommendation.replaceAll("_", " ") : "not verified yet"} />
        <Metric label="Min. main-meter trust" value={fmt(o.trust?.minimum_main_meter_trust, 3)} tone={o.trust?.minimum_main_meter_trust < 0.6 ? "bad" : "teal"} hint="dynamic trust engine" />
        <Metric label="Sensors in this month" value={s ? `${s.sensor_count}` : "—"} hint={s ? `${fmt(s.reading_count, 0)} readings · ${fmt(s.completeness_percent, 1)}% complete` : ""} tone="blue" />
        <Metric label="Flagged sensors" value={s ? s.flagged_sensor_count : "—"} tone={s?.flagged_sensor_count ? "warn" : "teal"} hint={s ? `mean trust ${fmt(s.mean_sensor_trust, 2)}` : ""} />
      </div>
      <div className="grid g2">
        <Card title="Claimed vs verified emissions" subtitle="kgCO2e per month">
          <ResponsiveContainer width="100%" height={270}>
            <BarChart data={rows}><CartesianGrid stroke="#cbd5de" strokeDasharray="3 3" />
              <XAxis dataKey="month_label" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} width={60} />
              <Tooltip contentStyle={{ background: "#f3f6f9", fontSize: 12 }} /><Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="claimed_total_kgco2e" name="Claimed" fill="#3d6fa3" /><Bar dataKey="verified_total_kgco2e" name="Verified" fill="#2f7f79" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Sensor-fleet CO2 by month" subtitle="Average CO2 (ppm) across this company's sensors. A high-CO2 month with a low claim is a red flag.">
          <Lines data={rows} xKey="month_label" lines={[{ key: "sensor_avg_co2_ppm", name: "Avg CO2 ppm" }]} />
        </Card>
      </div>
      <div className="grid g2">
        <Card title="Energy by shop" subtitle="kWh per month">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={shops.data || []}><CartesianGrid stroke="#cbd5de" strokeDasharray="3 3" />
              <XAxis dataKey="month_number" tickFormatter={(m) => `M${m}`} tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} width={60} />
              <Tooltip contentStyle={{ background: "#f3f6f9", fontSize: 12 }} /><Legend wrapperStyle={{ fontSize: 12 }} />
              {["paint_shop_kwh", "body_shop_kwh", "press_shop_kwh", "assembly_shop_kwh", "utilities_kwh"].map((k, i) => <Bar key={k} dataKey={k} stackId="a" name={k.replace("_kwh", "").replace("_", " ")} fill={COLORS[i]} />)}
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card title={`Daily emissions — Month ${month}`}>
          <Lines data={daily.data || []} xKey="day_in_month" lines={[{ key: "claimed_total_kgco2e", name: "Claimed" }, { key: "verified_total_kgco2e", name: "Verified" }]} />
        </Card>
      </div>
      <Card title="Claim status">
        <Table rows={rows.map((r) => ({ ...r, id: r.month_number }))} columns={[
          { key: "month_label", label: "Month" }, { key: "scenario", label: "Scenario", render: (r) => <Badge value={r.scenario} /> },
          { key: "discrepancy_percent", label: "Discrepancy %", num: true, render: (r) => fmt(r.discrepancy_percent) },
          { key: "minimum_meter_trust", label: "Min trust", num: true, render: (r) => fmt(r.minimum_meter_trust, 3) },
          { key: "sensor_count", label: "Sensors", num: true }, { key: "flagged_sensors", label: "Flagged", num: true },
          { key: "sensor_completeness_percent", label: "Sensor completeness %", num: true, render: (r) => fmt(r.sensor_completeness_percent, 1) },
        ]} />
      </Card>
    </>
  );
}
