import { Icon } from "@/components/ui/Icon";

export function VisualizationEmptyState() {
  return (
    <div className="visualization-empty">
      <div className="empty-chart-icon">
        <Icon name="chart" size={24} />
        <span /><span /><span />
      </div>
      <h3>No visualization yet</h3>
      <p>Ask a question and the generated visualization will appear here.</p>
      <div className="empty-chart-caption"><span /> MOCK CHART CANVAS</div>
    </div>
  );
}
