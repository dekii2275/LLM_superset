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

const COLORS = [
  "#0E4A86",
  "#0072CE",
  "#D9232D",
  "#64748B",
  "#36A4E8",
  "#15803D",
  "#F59E0B",
  "#7C3AED",
];

function formatValue(value: unknown): string {
  if (typeof value === "number") {
    return new Intl.NumberFormat("vi-VN", {
      maximumFractionDigits: Number.isInteger(value) ? 0 : 2,
    }).format(value);
  }
  return String(value ?? "");
}

function tickLabel(value: unknown): string {
  const text = formatValue(value);
  return text.length > 18 ? `${text.slice(0, 17)}…` : text;
}

function formatKpiValue(value: unknown): string {
  if (typeof value === "number") {
    if (Math.abs(value) >= 1_000_000_000) {
      return `${(value / 1_000_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 2 })} tỷ`;
    }
    if (Math.abs(value) >= 1_000_000) {
      return `${(value / 1_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 2 })} tr`;
    }
    if (Math.abs(value) >= 1_000) {
      return `${(value / 1_000).toLocaleString("vi-VN", { maximumFractionDigits: 1 })}k`;
    }
    return new Intl.NumberFormat("vi-VN", {
      maximumFractionDigits: Number.isInteger(value) ? 0 : 2,
    }).format(value);
  }
  return String(value ?? "0");
}

export function DynamicChart({ spec, rows, eyebrow }: DynamicChartProps) {
  if (spec.type === "none" || !rows || rows.length === 0) {
    return null;
  }

  // 1. KPI Card Rendering
  if (spec.type === "kpi") {
    const rawVal =
      spec.y_axis && rows[0][spec.y_axis] !== undefined
        ? rows[0][spec.y_axis]
        : Object.values(rows[0])[0];
    const formattedVal = formatKpiValue(rawVal);
    const metricTitle = spec.title || spec.y_label || spec.y_axis || "Chỉ số điều hành";

    return (
      <section
        className="my-3 border border-slate-200 bg-white p-4 shadow-xs"
        style={{ borderRadius: "2px" }}
        aria-label={metricTitle}
      >
        {eyebrow && (
          <p className="text-[10px] font-bold tracking-wider text-emerald-700 uppercase mb-1">
            {eyebrow}
          </p>
        )}
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h4 className="text-xs font-semibold text-slate-600 truncate">{metricTitle}</h4>
            <div className="mt-1.5 text-3xl font-extrabold tracking-tight text-slate-900 font-mono">
              {formattedVal}
            </div>
            {typeof rawVal === "number" && (
              <p className="mt-1 text-[11px] text-slate-400 font-mono">
                Số liệu gốc: {new Intl.NumberFormat("vi-VN").format(rawVal)}
              </p>
            )}
          </div>
          <div
            className="flex h-10 w-10 shrink-0 items-center justify-center border border-sky-200 bg-sky-50 text-sky-700 font-mono font-bold text-xs"
            style={{ borderRadius: "2px" }}
          >
            KPI
          </div>
        </div>
      </section>
    );
  }

  // 2. Table Mini View Rendering
  if (spec.type === "table") {
    const columns = Object.keys(rows[0] || {});
    return (
      <section
        className="my-3 border border-slate-200 bg-white p-3 shadow-xs"
        style={{ borderRadius: "2px" }}
        aria-label={spec.title ?? "Bảng tổng hợp"}
      >
        {eyebrow && (
          <p className="text-[10px] font-bold tracking-wider text-emerald-700 uppercase mb-1">
            {eyebrow}
          </p>
        )}
        {spec.title && <h4 className="text-xs font-semibold text-slate-700 mb-2">{spec.title}</h4>}
        <div className="overflow-x-auto max-h-[280px] border border-slate-100">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-slate-50 text-slate-700 font-semibold sticky top-0 border-b border-slate-200">
              <tr>
                {columns.map((col) => (
                  <th
                    key={col}
                    className="px-3 py-1.5 border-r last:border-r-0 border-slate-200 whitespace-nowrap text-[11px]"
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {rows.slice(0, 30).map((row, idx) => (
                <tr key={idx} className="hover:bg-slate-50/80">
                  {columns.map((col) => (
                    <td
                      key={col}
                      className="px-3 py-1.5 border-r last:border-r-0 border-slate-100 whitespace-nowrap font-mono text-[11px]"
                    >
                      {formatValue(row[col])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length > 30 && (
          <p className="text-[10px] text-slate-400 mt-1.5 text-right font-mono">
            Hiển thị 30 / {rows.length} dòng
          </p>
        )}
      </section>
    );
  }

  // 3. Map Preview Rendering
  if (spec.type === "map") {
    const columns = Object.keys(rows[0] || {});
    const latCol = columns.find((k) => ["latitude", "lat"].includes(k.toLowerCase())) || "latitude";
    const lonCol =
      columns.find((k) => ["longitude", "lon", "lng"].includes(k.toLowerCase())) || "longitude";
    const nameCol =
      columns.find((k) =>
        ["name", "country", "admin1", "city", "country_iso_a2"].includes(k.toLowerCase()),
      ) || columns[0];
    const metricCol =
      spec.y_axis ||
      columns.find(
        (k) =>
          typeof rows[0][k] === "number" &&
          !["latitude", "lat", "longitude", "lon", "lng"].includes(k.toLowerCase()),
      );

    return (
      <section
        className="my-3 border border-sky-200 bg-sky-50/40 p-3 shadow-xs"
        style={{ borderRadius: "2px" }}
        aria-label={spec.title ?? "Bản đồ phân bố địa lý"}
      >
        <div className="flex items-center justify-between mb-2">
          <div>
            {eyebrow && (
              <p className="text-[10px] font-bold tracking-wider text-sky-800 uppercase mb-0.5">
                {eyebrow}
              </p>
            )}
            <h4 className="text-xs font-semibold text-slate-800">
              {spec.title || "Biểu đồ Địa lý / Bản đồ (Map)"}
            </h4>
          </div>
          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold bg-sky-100 text-sky-700 border border-sky-300">
            🗺 BẢN ĐỒ ({rows.length} điểm)
          </span>
        </div>
        <div className="overflow-x-auto max-h-[220px] border border-sky-100 bg-white">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-slate-50 text-slate-700 font-semibold sticky top-0 border-b border-slate-200">
              <tr>
                <th className="px-3 py-1.5 text-[11px]">Địa danh / Đối tượng</th>
                <th className="px-3 py-1.5 text-[11px]">Tọa độ / Vị trí</th>
                {metricCol && (
                  <th className="px-3 py-1.5 text-[11px] text-right">Chỉ số ({metricCol})</th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {rows.slice(0, 15).map((row, idx) => (
                <tr key={idx} className="hover:bg-sky-50/50">
                  <td className="px-3 py-1.5 font-medium text-[11px]">
                    {String(row[nameCol] ?? "")}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-[11px] text-slate-500">
                    {row[latCol] !== undefined && row[lonCol] !== undefined
                      ? `${row[latCol]}, ${row[lonCol]}`
                      : String(row[spec.x_axis || ""] ?? "-")}
                  </td>
                  {metricCol && (
                    <td className="px-3 py-1.5 font-mono text-[11px] text-right text-sky-700 font-bold">
                      {formatValue(row[metricCol])}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="text-[10px] text-slate-500 mt-1.5 flex items-center justify-between">
          <span>
            {spec.map_style === "grid"
              ? "Xem trước dữ liệu tọa độ; bản đồ deck.gl Grid 3D hiển thị trong Superset sau khi xác nhận tạo chart."
              : "Bản đồ tương tác trực quan hóa không gian sẵn sàng để tạo trên Superset."}
          </span>
          {rows.length > 15 && <span>Hiển thị 15 / {rows.length} điểm</span>}
        </div>
      </section>
    );
  }

  if (spec.type === "heatmap") {
    if (!spec.x_axis || !spec.y_axis || !spec.value_axis) return null;
    const xAxis = spec.x_axis;
    const yAxis = spec.y_axis;
    const valueAxis = spec.value_axis;
    const xValues = [...new Set(rows.map((row) => String(row[xAxis] ?? "")))].slice(0, 24);
    const yValues = [...new Set(rows.map((row) => String(row[yAxis] ?? "")))].slice(0, 16);
    const values = new Map(
      rows.map((row) => [
        JSON.stringify([String(row[xAxis] ?? ""), String(row[yAxis] ?? "")]),
        Number(row[valueAxis]) || 0,
      ]),
    );
    const maximum = Math.max(1, ...values.values());
    return (
      <section
        className="my-3 overflow-x-auto border border-slate-200 bg-white p-3 shadow-xs"
        aria-label={spec.title ?? "Biểu đồ nhiệt"}
      >
        {eyebrow && (
          <p className="mb-1 text-[10px] font-bold uppercase text-emerald-700">{eyebrow}</p>
        )}
        <h4 className="mb-2 text-xs font-semibold text-slate-700">
          {spec.title ?? "Biểu đồ nhiệt"}
        </h4>
        <table className="border-collapse text-[11px]">
          <thead>
            <tr>
              <th className="min-w-24 border border-slate-200 p-1 text-left">
                {yAxis} / {xAxis}
              </th>
              {xValues.map((x) => (
                <th key={x} className="min-w-16 border border-slate-200 p-1 text-center">
                  {x}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {yValues.map((y) => (
              <tr key={y}>
                <th className="border border-slate-200 p-1 text-left">{y}</th>
                {xValues.map((x) => {
                  const value = values.get(JSON.stringify([x, y]));
                  const intensity = value === undefined ? 0 : value / maximum;
                  return (
                    <td
                      key={`${x}-${y}`}
                      className="border border-slate-200 p-1 text-center font-mono"
                      style={{
                        backgroundColor:
                          value === undefined
                            ? "#f8fafc"
                            : `rgba(2, 132, 199, ${0.12 + intensity * 0.8})`,
                        color: intensity > 0.65 ? "white" : "#0f172a",
                      }}
                    >
                      {value === undefined ? "–" : formatValue(value)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    );
  }

  if (!spec.x_axis || !spec.y_axis || rows.length < 2) {
    return null;
  }

  const commonAxes = (
    <>
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
          borderRadius: 2,
          background: "#FFFFFF",
          color: "#0F172A",
          fontSize: 11,
        }}
      />
    </>
  );

  return (
    <section className="dynamic-chart" aria-label={spec.title ?? "Trực quan hóa truy vấn"}>
      {eyebrow && <p className="dynamic-chart-eyebrow">{eyebrow}</p>}
      {spec.title && <h4>{spec.title}</h4>}
      <div className="dynamic-chart-canvas">
        <ResponsiveContainer width="100%" height={290}>
          {spec.type === "bar" ? (
            <BarChart data={rows} margin={{ top: 12, right: 10, left: -12, bottom: 0 }}>
              {commonAxes}
              <Bar
                dataKey={spec.y_axis}
                fill="#0284C7"
                radius={[5, 5, 0, 0]}
                maxBarSize={48}
                animationDuration={800}
              />
            </BarChart>
          ) : spec.type === "line" ? (
            <LineChart data={rows} margin={{ top: 12, right: 10, left: -12, bottom: 0 }}>
              {commonAxes}
              <Line
                type="monotone"
                dataKey={spec.y_axis}
                stroke="#0284C7"
                strokeWidth={2.5}
                dot={{ r: 3, fill: "#0284C7" }}
                activeDot={{ r: 6, fill: "#0369A1" }}
                animationDuration={800}
              />
            </LineChart>
          ) : spec.type === "area" ? (
            <AreaChart data={rows} margin={{ top: 12, right: 10, left: -12, bottom: 0 }}>
              <defs>
                <linearGradient id="query-area" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#0284C7" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#0284C7" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              {commonAxes}
              <Area
                type="monotone"
                dataKey={spec.y_axis}
                stroke="#0284C7"
                fill="url(#query-area)"
                strokeWidth={2.2}
                animationDuration={800}
              />
            </AreaChart>
          ) : (
            <PieChart>
              <Tooltip
                formatter={(value) => formatValue(value)}
                contentStyle={{
                  border: "1px solid #E2E8F0",
                  borderRadius: 8,
                  background: "#FFFFFF",
                  boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.1)",
                  color: "#0F172A",
                  fontSize: 12,
                  padding: "8px 12px",
                }}
              />
              <Legend wrapperStyle={{ fontSize: 11, color: "#475569", paddingTop: 8 }} />
              <Pie
                data={rows}
                dataKey={spec.y_axis}
                nameKey={spec.x_axis}
                cx="50%"
                cy="46%"
                innerRadius={50}
                outerRadius={88}
                paddingAngle={3}
                animationDuration={800}
              >
                {rows.map((_, index) => (
                  <Cell
                    key={index}
                    fill={COLORS[index % COLORS.length]}
                    stroke="#FFFFFF"
                    strokeWidth={2}
                  />
                ))}
              </Pie>
            </PieChart>
          )}
        </ResponsiveContainer>
      </div>
    </section>
  );
}
