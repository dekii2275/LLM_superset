"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { VisualizationSpec } from "@/lib/types";

type DynamicChartProps = {
  spec: VisualizationSpec;
  rows: Record<string, unknown>[];
  eyebrow?: string;
};

const COLORS = ["#0E4A86", "#0072CE", "#D9232D", "#64748B", "#36A4E8", "#15803D", "#F59E0B", "#7C3AED"];

function formatValue(value: unknown): string {
  if (typeof value === "number") {
    return new Intl.NumberFormat("en-US", {
      maximumFractionDigits: Number.isInteger(value) ? 0 : 2,
    }).format(value);
  }
  return String(value ?? "");
}

function tickLabel(value: unknown): string {
  const text = formatValue(value);
  return text.length > 18 ? `${text.slice(0, 17)}…` : text;
}

export function DynamicChart({ spec, rows, eyebrow }: DynamicChartProps) {
  if (
    spec.type === "none" ||
    !spec.x_axis ||
    !spec.y_axis ||
    rows.length < 2
  ) {
    return null;
  }

  const commonAxes = <>
    <CartesianGrid stroke="rgba(15, 23, 42, 0.1)" vertical={false} />
    <XAxis
      dataKey={spec.x_axis}
      tickFormatter={tickLabel}
      stroke="#CBD5E1"
      tick={{ fill: "#64748B", fontSize: 10 }}
      axisLine={false}
      tickLine={false}
      interval={0}
      angle={rows.length > 6 ? -24 : 0}
      textAnchor={rows.length > 6 ? "end" : "middle"}
      height={rows.length > 6 ? 64 : 32}
    />
    <YAxis
      tickFormatter={tickLabel}
      stroke="#CBD5E1"
      tick={{ fill: "#64748B", fontSize: 10 }}
      axisLine={false}
      tickLine={false}
      width={66}
    />
    <Tooltip
      formatter={(value) => formatValue(value)}
      labelFormatter={(label) => tickLabel(label)}
      contentStyle={{
        border: "1px solid rgba(15, 23, 42, 0.18)",
        borderRadius: 8,
        background: "#FFFFFF",
        color: "#0F172A",
        fontSize: 11,
      }}
    />
  </>;

  return (
    <section className="dynamic-chart" aria-label={spec.title ?? "Query visualization"}>
      {eyebrow && <p className="dynamic-chart-eyebrow">{eyebrow}</p>}
      {spec.title && <h4>{spec.title}</h4>}
      <div className="dynamic-chart-canvas">
        <ResponsiveContainer width="100%" height={290}>
          {spec.type === "bar" ? (
            <BarChart data={rows} margin={{ top: 12, right: 10, left: -12, bottom: 0 }}>
              {commonAxes}
              <Bar dataKey={spec.y_axis} fill="#0E4A86" radius={[5, 5, 0, 0]} maxBarSize={48} />
            </BarChart>
          ) : spec.type === "line" ? (
            <LineChart data={rows} margin={{ top: 12, right: 10, left: -12, bottom: 0 }}>
              {commonAxes}
              <Line type="monotone" dataKey={spec.y_axis} stroke="#0072CE" strokeWidth={2.5} dot={{ r: 3 }} activeDot={{ r: 5 }} />
            </LineChart>
          ) : spec.type === "area" ? (
            <AreaChart data={rows} margin={{ top: 12, right: 10, left: -12, bottom: 0 }}>
              <defs>
                <linearGradient id="query-area" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#0072CE" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#0072CE" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              {commonAxes}
              <Area type="monotone" dataKey={spec.y_axis} stroke="#0072CE" fill="url(#query-area)" strokeWidth={2.2} />
            </AreaChart>
          ) : (
            <PieChart>
              <Tooltip
                formatter={(value) => formatValue(value)}
                contentStyle={{ border: "1px solid rgba(15, 23, 42, 0.18)", borderRadius: 8, background: "#FFFFFF", color: "#0F172A", fontSize: 11 }}
              />
              <Legend wrapperStyle={{ fontSize: 10, color: "#475569" }} />
              <Pie data={rows} dataKey={spec.y_axis} nameKey={spec.x_axis} cx="50%" cy="45%" outerRadius={86} paddingAngle={2}>
                {rows.map((_, index) => <Cell key={index} fill={COLORS[index % COLORS.length]} />)}
              </Pie>
            </PieChart>
          )}
        </ResponsiveContainer>
      </div>
    </section>
  );
}
