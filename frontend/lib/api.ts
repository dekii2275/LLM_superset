import type {
  AIChatContext,
  AIChatResponse,
  ActionExecutionResponse,
  ChartPlan,
  DashboardPlan,
  EditChartPlan,
  EditDashboardPlan,
  QueryResult,
  VisualizationSpec,
} from "./types";

export function apiUrl(path: string): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "");
  return baseUrl ? `${baseUrl}${path}` : "";
}

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
  }
}

export type AISettings = { llm_enabled: boolean };

export async function getAISettings(): Promise<AISettings> {
  const response = await fetch(apiUrl("/api/v1/ai/settings"), { cache: "no-store" });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new ApiError(payload?.detail ?? "Could not load AI settings.", response.status);
  }
  return response.json() as Promise<AISettings>;
}

export async function setAIEnabled(llmEnabled: boolean): Promise<AISettings> {
  const response = await fetch(apiUrl("/api/v1/ai/settings"), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ llm_enabled: llmEnabled }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new ApiError(payload?.detail ?? "Could not update AI settings.", response.status);
  }
  return response.json() as Promise<AISettings>;
}

export async function askAI(message: string, context?: AIChatContext): Promise<AIChatResponse> {
  const response = await fetch(apiUrl("/api/v1/ai/chat"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(context ? { message, context } : { message }),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new ApiError(payload?.detail ?? "The AI service could not process the request.", response.status);
  }

  return response.json() as Promise<AIChatResponse>;
}

export async function executeCreateChart(
  chartPlan: ChartPlan,
  query: QueryResult,
  visualization: VisualizationSpec,
): Promise<ActionExecutionResponse> {
  const response = await fetch(apiUrl("/api/v1/ai/actions/execute"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action: "CREATE_CHART",
      chart_plan: chartPlan,
      query,
      visualization,
    }),
  });
  const payload = await response.json().catch(() => null) as ActionExecutionResponse | { detail?: string } | null;
  if (!response.ok) {
    throw new ApiError(
      payload && "detail" in payload ? payload.detail ?? "Could not create the chart." : "Could not create the chart.",
      response.status,
    );
  }
  return payload as ActionExecutionResponse;
}

export async function executeCreateDashboard(plan: DashboardPlan): Promise<ActionExecutionResponse> {
  const response = await fetch(apiUrl("/api/v1/ai/actions/execute"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "CREATE_DASHBOARD", dashboard_plan: plan }),
  });
  const payload = await response.json().catch(() => null) as ActionExecutionResponse | { detail?: string } | null;
  if (!response.ok) {
    throw new ApiError(
      payload && "detail" in payload ? payload.detail ?? "Could not create the dashboard." : "Could not create the dashboard.",
      response.status,
    );
  }
  return payload as ActionExecutionResponse;
}

export async function executeEditChart(plan: EditChartPlan): Promise<ActionExecutionResponse> {
  return executeSemanticAction("EDIT_CHART", "edit_chart_plan", plan);
}

export async function executeEditDashboard(
  plan: EditDashboardPlan,
  query?: QueryResult,
  visualization?: VisualizationSpec,
): Promise<ActionExecutionResponse> {
  return executeSemanticAction("EDIT_DASHBOARD", "edit_dashboard_plan", plan, query, visualization);
}

async function executeSemanticAction(
  action: "EDIT_CHART" | "EDIT_DASHBOARD",
  field: "edit_chart_plan" | "edit_dashboard_plan",
  plan: EditChartPlan | EditDashboardPlan,
  query?: QueryResult,
  visualization?: VisualizationSpec,
): Promise<ActionExecutionResponse> {
  const response = await fetch(apiUrl("/api/v1/ai/actions/execute"), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, [field]: plan, ...(query && visualization ? { query, visualization } : {}) }),
  });
  const payload = await response.json().catch(() => null) as ActionExecutionResponse | { detail?: string } | null;
  if (!response.ok) throw new ApiError(payload && "detail" in payload ? payload.detail ?? "Could not apply this change." : "Could not apply this change.", response.status);
  return payload as ActionExecutionResponse;
}

export async function checkEndpoint(url: string): Promise<boolean> {
  if (!url) return false;

  try {
    const response = await fetch(url, { cache: "no-store" });
    return response.ok;
  } catch {
    return false;
  }
}
