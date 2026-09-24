import { useEffect, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { EmbeddedDashboard } from "@/components/superset/EmbeddedDashboard";

type VisualizationPanelProps = {
  dashboardId?: number;
  dashboardTitle?: string;
  refreshToken?: number;
};

export function VisualizationPanel({ dashboardId, dashboardTitle, refreshToken = 0 }: VisualizationPanelProps) {
  const [showSuperset, setShowSuperset] = useState(false);

  useEffect(() => {
    if (dashboardId) setShowSuperset(true);
  }, [dashboardId]);

  return (
    <aside className="visualization-panel" aria-label="Live Superset dashboard">
      <div className="visualization-header">
        <div>
          <p className="panel-eyebrow">LIVE VISUALIZATION</p>
          <h2>{dashboardTitle ?? "NYC Yellow Taxi Overview"}</h2>
          <p className="visualization-subtitle">Live data from the connected PostgreSQL dataset</p>
        </div>
        <button className="icon-button panel-menu-button" type="button" aria-label="Visualization options" title="Visualization options">
          <span aria-hidden="true">•••</span>
        </button>
      </div>

      <div className="viz-actions">
        <button type="button" disabled title="Available after Superset integration">Save chart</button>
        <button type="button" disabled title="Available after Superset integration">Add to dashboard</button>
        <button className="open-superset-button" type="button" onClick={() => setShowSuperset(true)}>
          <Icon name="arrow-up-right" size={14} /> Open live dashboard
        </button>
      </div>
      <p className="viz-integration-note">Open the embedded dashboard to explore live PostgreSQL data with a short-lived guest token.</p>
      {showSuperset && <EmbeddedDashboard key={`${dashboardId ?? "default"}-${refreshToken}`} dashboardId={dashboardId} title={dashboardTitle} onClose={() => setShowSuperset(false)} />}
    </aside>
  );
}
