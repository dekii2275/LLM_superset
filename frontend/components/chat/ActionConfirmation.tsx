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

function chartTypeLabel(chartType: string): string {
  const labels: Record<string, string> = { bar: "cột", line: "đường", pie: "tròn", area: "miền" };
  return labels[chartType] ?? chartType;
}

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
      setError(requestError instanceof ApiError || requestError instanceof Error ? requestError.message : "Không thể tạo biểu đồ.");
      setState("error");
    }
  };

  if (state === "success") {
    return (
      <section className="action-confirmation is-success" aria-label="Kết quả tạo biểu đồ">
        <strong>✓ Đã tạo biểu đồ trong Superset</strong>
        <span>{action.chart_plan.title}{chartId ? ` · Mã biểu đồ: ${chartId}` : ""}</span>
        {chartUrl && <a href={chartUrl} target="_blank" rel="noreferrer">Mở trong Superset</a>}
      </section>
    );
  }

  if (state === "cancelled") {
    return <p className="action-cancelled">Đã hủy tạo biểu đồ. Không có thay đổi nào trong Superset.</p>;
  }

  return (
    <section className="action-confirmation" aria-label="Xác nhận tạo biểu đồ">
      <strong>Tạo biểu đồ này trong Superset?</strong>
      <span>Biểu đồ {chartTypeLabel(action.chart_plan.chart_type)} · {action.chart_plan.title}</span>
      {state === "error" && <p role="alert">{error}</p>}
      <div className="action-confirmation-buttons">
        <button type="button" onClick={() => setState("cancelled")} disabled={state === "executing"}>Hủy</button>
        <button type="button" className="create-chart-button" onClick={createChart} disabled={state === "executing"}>
          {state === "executing" ? "Đang tạo…" : "Tạo trong Superset"}
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
  const detail = plan.operation === "CHANGE_CHART_TYPE" ? `Đổi loại biểu đồ thành ${plan.new_chart_type}` : plan.operation === "RENAME_CHART" ? `Đổi tên thành ${plan.new_title}` : plan.operation === "CHANGE_METRIC" ? `Đổi chỉ số thành ${plan.new_metric}` : `Đổi chiều dữ liệu thành ${plan.new_dimension}`;
  const apply = async () => { if (state !== "idle") return; setState("executing"); try { const response = await executeEditChart(plan); if (!response.success) throw new Error(response.error ?? response.message); setState("success"); onUpdated?.(); } catch (e) { setError(e instanceof Error ? e.message : "Không thể cập nhật biểu đồ."); setState("error"); } };
  if (state === "success") return <section className="action-confirmation is-success"><strong>✓ Đã cập nhật biểu đồ</strong><span>{plan.chart_name}</span></section>;
  if (state === "cancelled") return <p className="action-cancelled">Đã hủy cập nhật biểu đồ. Không có thay đổi nào trong Superset.</p>;
  return <section className="action-confirmation" aria-label="Xác nhận cập nhật biểu đồ"><strong>Thay đổi biểu đồ?</strong><span>{plan.chart_name}</span><small>{detail}</small>{state === "error" && <p role="alert">{error}</p>}<div className="action-confirmation-buttons"><button type="button" onClick={() => setState("cancelled")} disabled={state === "executing"}>Hủy</button><button type="button" className="create-chart-button" onClick={apply} disabled={state === "executing"}>{state === "executing" ? "Đang cập nhật…" : "Áp dụng thay đổi"}</button></div></section>;
}

type EditDashboardConfirmationProps = {
  action: PendingEditDashboardAction;
  query?: QueryResult | null;
  visualization?: VisualizationSpec | null;
  onUpdated?: (result: CreateDashboardResult) => void;
};
export function EditDashboardConfirmation({ action, query, visualization, onUpdated }: EditDashboardConfirmationProps) {
  const [state, setState] = useState<"idle" | "executing" | "success" | "cancelled" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const plan = action.edit_dashboard_plan;
  const detail = plan.operation === "RENAME_DASHBOARD" ? `Đổi tên thành ${plan.new_title}` : plan.operation === "REMOVE_CHART" ? `Gỡ ${plan.chart_name}; biểu đồ đã lưu sẽ không bị xóa.` : `Thêm ${plan.create_chart_plan?.title ?? plan.chart_name}`;
  const apply = async () => { if (state !== "idle") return; setState("executing"); try { const response = await executeEditDashboard(plan, query ?? undefined, visualization ?? undefined); const dashboard = response.result; if (!response.success || !dashboard || !("dashboard_id" in dashboard) || !dashboard.dashboard_id) throw new Error(response.error ?? response.message); setState("success"); onUpdated?.(dashboard); } catch (e) { setError(e instanceof Error ? e.message : "Không thể cập nhật bảng điều khiển."); setState("error"); } };
  if (state === "success") return <section className="action-confirmation is-success"><strong>✓ Đã cập nhật bảng điều khiển</strong><span>{plan.dashboard_name}</span></section>;
  if (state === "cancelled") return <p className="action-cancelled">Đã hủy cập nhật bảng điều khiển. Không có thay đổi nào trong Superset.</p>;
  return <section className="action-confirmation dashboard-confirmation" aria-label="Xác nhận cập nhật bảng điều khiển"><strong>Cập nhật bảng điều khiển?</strong><span>{plan.dashboard_name}</span><small>{detail}</small>{state === "error" && <p role="alert">{error}</p>}<div className="action-confirmation-buttons"><button type="button" onClick={() => setState("cancelled")} disabled={state === "executing"}>Hủy</button><button type="button" className="create-chart-button" onClick={apply} disabled={state === "executing"}>{state === "executing" ? "Đang cập nhật…" : plan.operation === "REMOVE_CHART" ? "Gỡ" : "Áp dụng thay đổi"}</button></div></section>;
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
      setError(requestError instanceof ApiError || requestError instanceof Error ? requestError.message : "Không thể tạo bảng điều khiển.");
      setState("error");
    }
  };

  if (state === "success" && result) {
    return (
      <section className="action-confirmation is-success" aria-label="Kết quả tạo bảng điều khiển">
        <strong>✓ Đã tạo bảng điều khiển trong Superset</strong>
        <span>{result.dashboard_name} · Đã tạo {result.chart_ids.length} biểu đồ</span>
        {result.url && <a href={result.url} target="_blank" rel="noreferrer">Mở trong Superset</a>}
      </section>
    );
  }
  if (state === "cancelled") {
    return <p className="action-cancelled">Đã hủy tạo bảng điều khiển. Không có thay đổi nào trong Superset.</p>;
  }
  return (
    <section className="action-confirmation dashboard-confirmation" aria-label="Xác nhận tạo bảng điều khiển">
      <strong>Tạo bảng điều khiển trong Superset?</strong>
      <span>{action.dashboard_plan.title}</span>
      <ul className="dashboard-plan-list">
        {action.dashboard_plan.charts.map((chart) => (
          <li key={`${chart.title}-${chart.question}`}><b>{chart.title}</b><small>Biểu đồ {chartTypeLabel(chart.chart_type)}</small></li>
        ))}
      </ul>
      {state === "error" && <p role="alert">{error}</p>}
      <div className="action-confirmation-buttons">
        <button type="button" onClick={() => setState("cancelled")} disabled={state === "executing"}>Hủy</button>
        <button type="button" className="create-chart-button" onClick={createDashboard} disabled={state === "executing"}>
          {state === "executing" ? "Đang tạo bảng điều khiển…" : "Tạo bảng điều khiển"}
        </button>
      </div>
    </section>
  );
}
