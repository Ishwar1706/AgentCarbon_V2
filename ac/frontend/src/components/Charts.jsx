import React from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export const COLORS = ["#2f7f79", "#3d6fa3", "#b9772c", "#8a5a9e", "#a8403a", "#4d8f3d", "#6b7f93", "#c2578a"];

export function Lines({ data, xKey, lines, height = 280, yDomain, unit }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="#cbd5de" strokeDasharray="3 3" />
        <XAxis dataKey={xKey} tick={{ fontSize: 11 }} minTickGap={40} />
        <YAxis tick={{ fontSize: 11 }} domain={yDomain || ["auto", "auto"]} unit={unit} width={52} />
        <Tooltip contentStyle={{ background: "#f3f6f9", border: "1px solid #cbd5de", fontSize: 12 }} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {lines.map((l, i) => (
          <Line key={l.key} type="monotone" dataKey={l.key} name={l.name || l.key} dot={false} connectNulls
                stroke={l.color || COLORS[i % COLORS.length]} strokeWidth={1.8} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
