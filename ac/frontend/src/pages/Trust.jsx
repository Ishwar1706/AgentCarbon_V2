import React, { useState } from "react";
import { api } from "../api/client.js";
import { useAuth } from "../state/AuthContext.jsx";
import { Badge, Card, Empty, ErrorBox, Loading, Table, fmt, useAsync } from "../components/UI.jsx";
import { Lines, COLORS } from "../components/Charts.jsx";

export default function Trust() {
  const { companyId } = useAuth();
  const [month, setMonth] = useState(3);
  const p = { company_id: companyId };
  const sum = useAsync(() => api.get("/trust/monthly-summary", p), [companyId]);
  const tl = useAsync(() => api.get("/trust/timeline", { ...p, month_number: month }), [companyId, month]);
  if (!companyId) return <Empty text="No company selected." />;
  if (sum.loading) return <Loading text="Running the dynamic trust engine…" />;
  if (sum.error) return <ErrorBox message={sum.error} />;
  const rows = (tl.data || []).map((r) => ({ ...r, t: r.timestamp.slice(5, 16).replace("T", " ") }));
  return (
    <>
      <div className="page-title"><h1>Meter trust &amp; fraud detection</h1>
        <p>Four electricity meters are fused. The main meter loses weight when it disagrees with the supporting meters, so manipulated readings stop influencing the verified total.</p></div>
      <Card title="Monthly trust summary">
        <Table rows={sum.data.map((r) => ({ ...r, id: r.month_number }))} onRow={(r) => setMonth(r.month_number)} selected={(r) => r.month_number === month} columns={[
          { key: "month_label", label: "Month" }, { key: "month_scenario", label: "Scenario", render: (r) => <Badge value={r.month_scenario} /> },
          { key: "static_mae_kwh", label: "Static MAE kWh", num: true, render: (r) => fmt(r.static_mae_kwh, 3) },
          { key: "dynamic_mae_kwh", label: "Dynamic MAE kWh", num: true, render: (r) => fmt(r.dynamic_mae_kwh, 3) },
          { key: "mae_reduction_percent", label: "Error reduction %", num: true, render: (r) => fmt(r.mae_reduction_percent, 1) },
          { key: "minimum_main_meter_trust", label: "Min trust", num: true, render: (r) => fmt(r.minimum_main_meter_trust, 3) },
          { key: "final_main_meter_trust", label: "Final trust", num: true, render: (r) => fmt(r.final_main_meter_trust, 3) },
          { key: "detected_records", label: "Fault records", num: true },
        ]} />
      </Card>
      <div className="grid g2">
        <Card title={`Energy readings — Month ${month}`} subtitle="Real usage vs main meter vs fused estimates (kWh per 15 min)">
          {tl.loading ? <Loading /> : <Lines data={rows} xKey="t" lines={[
            { key: "Usage_kWh", name: "Real usage", color: "#1f2c38" }, { key: "main_incomer_meter_kwh", name: "Main meter" },
            { key: "static_fused_kwh", name: "Static fusion", color: COLORS[2] }, { key: "dynamic_fused_kwh", name: "Dynamic fusion", color: COLORS[0] }]} />}
        </Card>
        <Card title={`Main meter trust — Month ${month}`}>
          {tl.loading ? <Loading /> : <Lines data={rows} xKey="t" yDomain={[0, 1]} lines={[{ key: "main_meter_trust", name: "Trust score", color: COLORS[1] }]} />}
        </Card>
      </div>
    </>
  );
}
