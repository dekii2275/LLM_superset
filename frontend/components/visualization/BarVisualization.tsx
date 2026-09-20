import type { ChartDatum } from "@/lib/types";

type BarVisualizationProps = {
  data: ChartDatum[];
  unit: string;
};

export function BarVisualization({ data, unit }: BarVisualizationProps) {
  const max = Math.max(...data.map((datum) => datum.value), 1);

  return (
    <div className="bar-chart" role="list" aria-label="Revenue comparison chart">
      {data.map((datum, index) => (
        <div className="bar-chart-row" role="listitem" key={datum.label} title={`${datum.label}: ${datum.value.toFixed(2)} ${unit}`}>
          <div className="bar-row-heading">
            <span className="bar-label"><i className={`bar-rank rank-${index + 1}`} />{datum.label}</span>
            <strong>{datum.value.toFixed(2)}B</strong>
          </div>
          <div className="bar-track" tabIndex={0} aria-label={`${datum.label}, ${datum.value.toFixed(2)} ${unit}`}>
            <span className={`bar-fill bar-fill-${index + 1}`} style={{ width: `${Math.max((datum.value / max) * 100, 4)}%` }} />
          </div>
        </div>
      ))}
      <div className="chart-axis-caption">Revenue · {unit}</div>
    </div>
  );
}
