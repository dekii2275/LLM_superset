"use client";

import { useState } from "react";
import { ApiError, executeCreateChart, executeCreateDashboard, executeEditChart, executeEditDashboard } from "@/lib/api";
import type {
  CreateDashboardResult,
  PendingCreateChartAction,
  PendingCreateDashboardAction,
  PendingEditChartAction,
  PendingEditDashboardAction,
  QueryResult,
  VisualizationSpec,
} from "@/lib/types";

type ActionConfirmationProps = {
  action: PendingCreateChartAction;
  query: QueryResult;
  visualization: VisualizationSpec;
};

export function ActionConfirmation({ action, query, visualization }: ActionConfirmationProps) {
  const [state, setState] = useState<"idle" | "executing" | "success" | "cancelled" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [chartUrl, setChartUrl] = useState<string | null>(null);
  const [chartId, setChartId] = useState<number | null>(null);

  const createChart = async () => {
    if (state !== "idle") return;
    setState("executing");
    setError(null);
    try {
      const response = await executeCreateChart(action.chart_plan, query, visualization);
      if (!response.success || !response.result || !("chart_id" in response.result) || !response.result.chart_id) {
        throw new Error(response.error ?? response.message);
      }
      setChartId(response.result.chart_id);
      setChartUrl(response.result.url ?? null);
      setState("success");
    } catch (requestError) {
      setError(requestError instanceof ApiError || requestError instanceof Error ? requestError.message : "Could not create the chart.");
      setState("error");
    }
  };

  if (state === "success") {
    return (
      <section className="action-confirmation is-success" aria-label="Chart creation result">
        <strong>✓ Chart created in Superset</strong>
        <span>{action.chart_plan.title}{chartId ? ` · Chart ID: ${chartId}` : ""}</span>
        {chartUrl && <a href={chartUrl} target="_blank" rel="noreferrer">Open in Superset</a>}
      </section>
    );
  }

  if (state === "cancelled") {
    return <p className="action-cancelled">Chart creation cancelled. No Superset changes were made.</p>;
  }

  return (
    <section className="action-confirmation" aria-label="Chart creation confirmation">
      <strong>Create this chart in Superset?</strong>
      <span>{action.chart_plan.chart_type} chart · {action.chart_plan.title}</span>
      {state === "error" && <p role="alert">{error}</p>}
      <div className="action-confirmation-buttons">
        <button type="button" onClick={() => setState("cancelled")} disabled={state === "executing"}>Cancel</button>
        <button type="button" className="create-chart-button" onClick={createChart} disabled={state === "executing"}>
          {state === "executing" ? "Creating…" : "Create in Superset"}
        </button>
      </div>
    </section>
  );
}

type EditChartConfirmationProps = { action: PendingEditChartAction; onUpdated?: () => void };
export function EditChartConfirmation({ action, onUpdated }: EditChartConfirmationProps) {
  const [state, setState] = useState<"idle" | "executing" | "success" | "cancelled" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const plan = action.edit_chart_plan;
  const detail = plan.operation === "CHANGE_CHART_TYPE" ? `Change chart type to ${plan.new_chart_type}` : plan.operation === "RENAME_CHART" ? `Rename to ${plan.new_title}` : plan.operation === "CHANGE_METRIC" ? `Change metric to ${plan.new_metric}` : `Change dimension to ${plan.new_dimension}`;
  const apply = async () => { if (state !== "idle") return; setState("executing"); try { const response = await executeEditChart(plan); if (!response.success) throw new Error(response.error ?? response.message); setState("success"); onUpdated?.(); } catch (e) { setError(e instanceof Error ? e.message : "Could not update the chart."); setState("error"); } };
  if (state === "success") return <section className="action-confirmation is-success"><strong>✓ Chart updated</strong><span>{plan.chart_name}</span></section>;
  if (state === "cancelled") return <p className="action-cancelled">Chart update cancelled. No Superset changes were made.</p>;
  return <section className="action-confirmation" aria-label="Chart update confirmation"><strong>Change chart?</strong><span>{plan.chart_name}</span><small>{detail}</small>{state === "error" && <p role="alert">{error}</p>}<div className="action-confirmation-buttons"><button type="button" onClick={() => setState("cancelled")} disabled={state === "executing"}>Cancel</button><button type="button" className="create-chart-button" onClick={apply} disabled={state === "executing"}>{state === "executing" ? "Updating…" : "Apply Change"}</button></div></section>;
}

type EditDashboardConfirmationProps = { action: PendingEditDashboardAction; onUpdated?: (result: CreateDashboardResult) => void };
export function EditDashboardConfirmation({ action, onUpdated }: EditDashboardConfirmationProps) {
  const [state, setState] = useState<"idle" | "executing" | "success" | "cancelled" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const plan = action.edit_dashboard_plan;
  const detail = plan.operation === "RENAME_DASHBOARD" ? `Rename to ${plan.new_title}` : plan.operation === "REMOVE_CHART" ? `Remove ${plan.chart_name}; the saved chart will not be deleted.` : `Add ${plan.create_chart_plan?.title ?? plan.chart_name}`;
  const apply = async () => { if (state !== "idle") return; setState("executing"); try { const response = await executeEditDashboard(plan); const dashboard = response.result; if (!response.success || !dashboard || !("dashboard_id" in dashboard) || !dashboard.dashboard_id) throw new Error(response.error ?? response.message); setState("success"); onUpdated?.(dashboard); } catch (e) { setError(e instanceof Error ? e.message : "Could not update the dashboard."); setState("error"); } };
  if (state === "success") return <section className="action-confirmation is-success"><strong>✓ Dashboard updated</strong><span>{plan.dashboard_name}</span></section>;
  if (state === "cancelled") return <p className="action-cancelled">Dashboard update cancelled. No Superset changes were made.</p>;
  return <section className="action-confirmation dashboard-confirmation" aria-label="Dashboard update confirmation"><strong>Update dashboard?</strong><span>{plan.dashboard_name}</span><small>{detail}</small>{state === "error" && <p role="alert">{error}</p>}<div className="action-confirmation-buttons"><button type="button" onClick={() => setState("cancelled")} disabled={state === "executing"}>Cancel</button><button type="button" className="create-chart-button" onClick={apply} disabled={state === "executing"}>{state === "executing" ? "Updating…" : plan.operation === "REMOVE_CHART" ? "Remove" : "Apply Change"}</button></div></section>;
}

type DashboardConfirmationProps = {
  action: PendingCreateDashboardAction;
  onDashboardCreated?: (result: CreateDashboardResult) => void;
};

export function DashboardConfirmation({ action, onDashboardCreated }: DashboardConfirmationProps) {
  const [state, setState] = useState<"idle" | "executing" | "success" | "cancelled" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CreateDashboardResult | null>(null);

  const createDashboard = async () => {
    if (state !== "idle") return;
    setState("executing");
    setError(null);
    try {
      const response = await executeCreateDashboard(action.dashboard_plan);
      const dashboard = response.result;
      if (!response.success || !dashboard || !("dashboard_id" in dashboard) || !dashboard.dashboard_id) {
        throw new Error(response.error ?? response.message);
      }
      setResult(dashboard);
      setState("success");
      onDashboardCreated?.(dashboard);
    } catch (requestError) {
      setError(requestError instanceof ApiError || requestError instanceof Error ? requestError.message : "Could not create the dashboard.");
      setState("error");
    }
  };

  if (state === "success" && result) {
    return (
      <section className="action-confirmation is-success" aria-label="Dashboard creation result">
        <strong>✓ Dashboard created in Superset</strong>
        <span>{result.dashboard_name} · {result.chart_ids.length} charts created</span>
        {result.url && <a href={result.url} target="_blank" rel="noreferrer">Open in Superset</a>}
      </section>
    );
  }
  if (state === "cancelled") {
    return <p className="action-cancelled">Dashboard creation cancelled. No Superset changes were made.</p>;
  }
  return (
    <section className="action-confirmation dashboard-confirmation" aria-label="Dashboard creation confirmation">
      <strong>Create dashboard in Superset?</strong>
      <span>{action.dashboard_plan.title}</span>
      <ul className="dashboard-plan-list">
        {action.dashboard_plan.charts.map((chart) => (
          <li key={`${chart.title}-${chart.question}`}><b>{chart.title}</b><small>{chart.chart_type} chart</small></li>
        ))}
      </ul>
      {state === "error" && <p role="alert">{error}</p>}
      <div className="action-confirmation-buttons">
        <button type="button" onClick={() => setState("cancelled")} disabled={state === "executing"}>Cancel</button>
        <button type="button" className="create-chart-button" onClick={createDashboard} disabled={state === "executing"}>
          {state === "executing" ? "Creating dashboard…" : "Create Dashboard"}
        </button>
      </div>
    </section>
  );
}
