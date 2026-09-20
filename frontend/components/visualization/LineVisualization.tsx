"use client";

import { useState } from "react";
import type { ChartDatum } from "@/lib/types";

type LineVisualizationProps = {
  data: ChartDatum[];
  unit: string;
};

const WIDTH = 480;
const HEIGHT = 238;
const LEFT = 34;
const RIGHT = 14;
const TOP = 16;
const BOTTOM = 34;

export function LineVisualization({ data, unit }: LineVisualizationProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const max = Math.ceil(Math.max(...data.map((datum) => datum.value), 1) * 10) / 10;
  const chartWidth = WIDTH - LEFT - RIGHT;
  const chartHeight = HEIGHT - TOP - BOTTOM;
  const points = data.map((datum, index) => ({
    ...datum,
    x: LEFT + (index / Math.max(data.length - 1, 1)) * chartWidth,
    y: TOP + (1 - datum.value / max) * chartHeight,
  }));
  const linePoints = points.map((point) => `${point.x},${point.y}`).join(" ");
  const active = activeIndex === null ? null : points[activeIndex];

  return (
    <div className="line-chart" aria-label="Monthly revenue line chart">
      <div className="line-chart-unit">Revenue · {unit}</div>
      <svg className="line-chart-svg" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Monthly revenue from January to December">
        {[0, 0.5, 1].map((portion) => {
          const y = TOP + chartHeight * portion;
          const value = max * (1 - portion);
          return (
            <g key={portion}>
              <line className="chart-gridline" x1={LEFT} x2={WIDTH - RIGHT} y1={y} y2={y} />
              <text className="chart-axis-value" x={LEFT - 7} y={y + 4} textAnchor="end">{value.toFixed(1)}</text>
            </g>
          );
        })}
        <polyline className="line-chart-stroke" points={linePoints} />
        {points.map((point, index) => (
          <g key={point.label}>
            <circle
              className={`line-chart-point ${activeIndex === index ? "is-active" : ""}`}
              cx={point.x}
              cy={point.y}
              r={activeIndex === index ? 5 : 3.5}
              tabIndex={0}
              aria-label={`${point.label}: ${point.value.toFixed(2)} ${unit}`}
              onMouseEnter={() => setActiveIndex(index)}
              onMouseLeave={() => setActiveIndex(null)}
              onFocus={() => setActiveIndex(index)}
              onBlur={() => setActiveIndex(null)}
            />
            {index % 2 === 0 && (
              <text className="chart-axis-label" x={point.x} y={HEIGHT - 8} textAnchor="middle">{point.label}</text>
            )}
          </g>
        ))}
      </svg>
      {active && (
        <div className="line-chart-tooltip" style={{ left: `${(active.x / WIDTH) * 100}%`, top: `${(active.y / HEIGHT) * 100}%` }} role="status">
          <strong>{active.label}</strong><span>{active.value.toFixed(2)} {unit}</span>
        </div>
      )}
    </div>
  );
}
