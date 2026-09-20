import type { AnalysisResponse } from "@/lib/types";
import { ActiveFilters } from "@/components/filters/ActiveFilters";
import { Icon } from "@/components/ui/Icon";
import { BarVisualization } from "./BarVisualization";
import { BigNumberChart } from "./BigNumberChart";
import { LineVisualization } from "./LineVisualization";
import { VisualizationEmptyState } from "./VisualizationEmptyState";

type VisualizationPanelProps = {
  analysis: AnalysisResponse | null;
  onRemoveFilter: (field: string) => void;
};

function ChartTypeLabel({ type }: { type: "big_number" | "line" | "bar" }) {
  const labels = { big_number: "BIG NUMBER", line: "LINE CHART", bar: "BAR CHART" };
  return <span className="chart-type-label"><Icon name="chart" size={13} /> {labels[type]}</span>;
}

export function VisualizationPanel({ analysis, onRemoveFilter }: VisualizationPanelProps) {
  const visualization = analysis?.visualization;

  return (
    <aside className="visualization-panel" aria-label="Visualization and filters">
      <div className="visualization-header">
        <div>
          <p className="panel-eyebrow">VISUALIZATION</p>
          <h2>{visualization?.title ?? "Analysis preview"}</h2>
          <p className="visualization-subtitle">{visualization ? "Based on current analysis" : "Your charts will appear here"}</p>
        </div>
        <button className="icon-button panel-menu-button" type="button" aria-label="Visualization options" title="Visualization options">
          <span aria-hidden="true">•••</span>
        </button>
      </div>

      <ActiveFilters filters={analysis?.filters ?? []} onRemove={onRemoveFilter} />

      <div className="chart-card">
        <div className="chart-card-toolbar">
          {visualization ? <ChartTypeLabel type={visualization.type} /> : <span className="chart-type-label muted">PREVIEW</span>}
          <span className="mock-data-label"><span className="status-dot demo" /> MOCK DATA</span>
        </div>
        {!visualization ? (
          <VisualizationEmptyState />
        ) : visualization.type === "big_number" ? (
          <BigNumberChart value={visualization.formattedValue} />
        ) : visualization.type === "line" ? (
          <LineVisualization data={visualization.data} unit={visualization.unit} />
        ) : (
          <BarVisualization data={visualization.data} unit={visualization.unit} />
        )}
      </div>

      {analysis?.query && (
        <div className="query-summary">
          <div className="query-summary-title"><Icon name="code" size={15} />
            <span>Query summary</span><span className="query-ok"><i /> Success</span>
          </div>
          <div className="query-summary-values">
            <span><strong>{analysis.query.executionTimeMs} ms</strong> execution</span>
            <span><strong>{analysis.query.rowCount}</strong> rows</span>
          </div>
        </div>
      )}

      <div className="viz-actions">
        <button type="button" disabled title="Available after Superset integration">Save chart</button>
        <button type="button" disabled title="Available after Superset integration">Add to dashboard</button>
        <button className="open-superset-button" type="button" disabled title="Available after Superset integration">
          <Icon name="arrow-up-right" size={14} /> Open in Superset
        </button>
      </div>
      <p className="viz-integration-note">Chart actions become available after Superset integration.</p>
    </aside>
  );
}
