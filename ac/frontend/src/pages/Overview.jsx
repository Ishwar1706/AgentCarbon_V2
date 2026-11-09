import React from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client.js";
import { useAuth } from "../state/AuthContext.jsx";
import { Badge, Card, Empty, ErrorBox, Loading, Metric, NoData, Table, fmt, useAsync } from "../components/UI.jsx";
import { Lines, COLORS } from "../components/Charts.jsx";
import { periodLabel } from "../../lib/periods.js";

export default function Overview() {
  const { companyId, company, period, setPeriod } = useAuth();
  const p = { company_id: companyId };
  const ov = useAsync(() => api.get("/dashboard/overview", { ...p, period }), [companyId, period]);
  const cmp = useAsync(() => api.get("/dashboard/monthly-comparison", p), [companyId]);
  const shops = useAsync(() => api.get("/dashboard/shop-energy", p), [companyId]);
  const daily = useAsync(() => api.get("/dashboard/daily-emissions", { ...p, period }), [companyId, period]);
  if (!companyId) return <Empty text="No company selected." />;
  if (ov.loading && !ov.data) return <Loading />;
  if (ov.error) return <ErrorBox message={ov.error} />;
  const rows = cmp.data || [];
  const o = ov.data;
  const header = (
    <div className="page-title"><h1>{company?.legal_name}</h1>
      <p>Monthly overview for <b>{periodLabel(period)}</b>. Change the month with the calendar at the top.</p></div>
  );
  if (!o.available) return <>{header}<NoData period={period} /></>;
  const c = o.claim, s = o.sensors, cr = o.credits;
  const sevTone = c.discrepancy_percent > 15 ? "bad" : c.discrepancy_percent > 5 ? "warn" : "teal";
  return (
    <>
      {header}
      <div className="grid g4">
        <Metric label="Declared emissions" value={`${fmt(c.claimed_total_kgco2e, 0)} kg`} hint="kgCO2e from the monthly request" tone="blue" />
        <Metric label="Verified emissions" value={`${fmt(c.verified_total_kgco2e, 0)} kg`} hint="from trusted meter fusion" />
        <Metric label="Discrepancy" value={`${fmt(c.discrepancy_percent)}%`} tone={sevTone} hint={c.recommendation ? c.recommendation.replaceAll("_", " ") : "not verified yet"} />
        <Metric label="Credits expected / supported" value={`${fmt(cr.expected_credits_tco2e)} / ${fmt(cr.supported_credits_tco2e)} t`} tone={cr.overstatement_percent > 10 ? "bad" : "teal"} hint={cr.overstatement_percent > 10 ? `overstated ${fmt(cr.overstatement_percent, 0)}%` : "tCO2e"} />
        <Metric label="Request status" value={<Badge value={c.request_status} />} tone="blue" />
        <Metric label="Min. main-meter trust" value={fmt(o.trust?.minimum_main_meter_trust, 3)} tone={o.trust?.minimum_main_meter_trust < 0.6 ? "bad" : "teal"} hint="dynamic trust engine" />
        <Metric label="Sensors this month" value={s ? s.sensor_count : "—"} hint={s ? `${fmt(s.reading_count, 0)} readings · ${fmt(s.completeness_percent, 1)}% complete` : ""} tone="blue" />
        <Metric label="Flagged sensors" value={s ? s.flagged_sensor_count : "—"} tone={s?.flagged_sensor_count ? "warn" : "teal"} hint={s ? `mean trust ${fmt(s.mean_sensor_trust, 2)}` : ""} />
      </div>
      <div className="grid g2">
        <Card title="Declared vs verified emissions" subtitle="kgCO2e per month (plant-reported figures vs trusted meters)">
          <ResponsiveContainer width="100%" height={270}>
            <BarChart data={rows}><CartesianGrid stroke="#cbd5de" strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} width={60} />
              <Tooltip contentStyle={{ background: "#f3f6f9", fontSize: 12 }} /><Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="claimed_total_kgco2e" name="Plant-reported" fill="#3d6fa3" /><Bar dataKey="verified_total_kgco2e" name="Verified" fill="#2f7f79" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Sensor-fleet CO2 by month" subtitle="Average CO2 (ppm) across this company's sensors. High CO2 with a low claim is a red flag.">
          <Lines data={rows} xKey="label" lines={[{ key: "sensor_avg_co2_ppm", name: "Avg CO2 ppm" }]} />
        </Card>
      </div>
      <div className="grid g2">
        <Card title="Energy by shop" subtitle="kWh per month">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={shops.data || []}><CartesianGrid stroke="#cbd5de" strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} width={60} />
              <Tooltip contentStyle={{ background: "#f3f6f9", fontSize: 12 }} /><Legend wrapperStyle={{ fontSize: 12 }} />
              {["paint_shop_kwh", "body_shop_kwh", "press_shop_kwh", "assembly_shop_kwh", "utilities_kwh"].map((k, i) => <Bar key={k} dataKey={k} stackId="a" name={k.replace("_kwh", "").replace("_", " ")} fill={COLORS[i]} />)}
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card title={`Daily emissions — ${periodLabel(period)}`}>
          <Lines data={daily.data || []} xKey="day_in_month" lines={[{ key: "claimed_total_kgco2e", name: "Plant-reported" }, { key: "verified_total_kgco2e", name: "Verified" }]} />
        </Card>
      </div>
      <Card title="All months with data" subtitle="Click a month to open it.">
        <Table rows={rows.map((r) => ({ ...r, id: r.period }))} onRow={(r) => setPeriod(r.period)} selected={(r) => r.period === period} columns={[
          { key: "label", label: "Month" }, { key: "scenario", label: "Scenario", render: (r) => <Badge value={r.scenario} /> },
          { key: "discrepancy_percent", label: "Discrepancy %", num: true, render: (r) => fmt(r.discrepancy_percent) },
          { key: "minimum_meter_trust", label: "Min trust", num: true, render: (r) => fmt(r.minimum_meter_trust, 3) },
          { key: "sensor_count", label: "Sensors", num: true }, { key: "flagged_sensors", label: "Flagged", num: true },
          { key: "sensor_completeness_percent", label: "Sensor completeness %", num: true, render: (r) => fmt(r.sensor_completeness_percent, 1) },
        ]} />
      </Card>
    </>
  );
}
