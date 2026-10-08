import type {
  AIChatContext,
  AIChatResponse,
  ActionExecutionResponse,
  AlertItem,
  BusinessGlossaryItem,
  ChatSession,
  DbChatMessage,
  ChartExplanation,
  ChartPlan,
  DashboardPlan,
  DashboardOption,
  DatasetPreviewResult,
  DatasetSummary,
  EditChartPlan,
  EditDashboardPlan,
  QueryResult,
  SupersetChartExplanationResponse,
  SupersetChartItem,
  UploadDatasetResult,
  UserProfile,
  VerifiedMetricItem,
  VisualizationSpec,
} from "./types";

export function apiUrl(path: string): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "");
  return baseUrl ? `${baseUrl}${path}` : "";
}

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("ai_bi_auth_token");
}

export function setAuthToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) {
    localStorage.setItem("ai_bi_auth_token", token);
  } else {
    localStorage.removeItem("ai_bi_auth_token");
  }
}

export function authHeaders(): Record<string, string> {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

export type AISettings = { llm_enabled: boolean; tokens_used: number };

export async function getAISettings(): Promise<AISettings> {
  const response = await fetch(apiUrl("/api/v1/ai/settings"), { cache: "no-store" });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(payload?.detail ?? "Không thể tải cài đặt AI.", response.status);
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
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(payload?.detail ?? "Không thể cập nhật cài đặt AI.", response.status);
  }
  return response.json() as Promise<AISettings>;
}

export async function getDatasets(): Promise<DatasetSummary[]> {
  const response = await fetch(apiUrl("/api/v1/ai/datasets"), { cache: "no-store" });
  if (!response.ok) {
    return [];
  }
  return response.json() as Promise<DatasetSummary[]>;
}

export async function askAI(
  message: string,
  context?: AIChatContext,
  datasetId?: number | null,
  sessionId?: string | null,
): Promise<AIChatResponse> {
  const payload: Record<string, unknown> = { message };
  if (context) payload.context = context;
  if (datasetId) payload.dataset_id = datasetId;
  if (sessionId) payload.session_id = sessionId;

  const response = await fetch(apiUrl("/api/v1/ai/chat"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(
      errorPayload?.detail ?? "Dịch vụ AI không thể xử lý yêu cầu.",
      response.status,
    );
  }

  return response.json() as Promise<AIChatResponse>;
}

export async function explainChart(
  sql: string,
  visualization: VisualizationSpec,
): Promise<ChartExplanation> {
  const response = await fetch(apiUrl("/api/v1/ai/explain-chart"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sql, visualization }),
  });
  const payload = (await response.json().catch(() => null)) as
    | ChartExplanation
    | { detail?: string }
    | null;
  if (!response.ok) {
    throw new ApiError(
      payload && "detail" in payload
        ? (payload.detail ?? "Không thể giải thích biểu đồ.")
        : "Không thể giải thích biểu đồ.",
      response.status,
    );
  }
  return payload as ChartExplanation;
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
      dataset_id: chartPlan.dataset_id,
      chart_plan: chartPlan,
      query,
      visualization,
    }),
  });
  const payload = (await response.json().catch(() => null)) as
    | ActionExecutionResponse
    | { detail?: string }
    | null;
  if (!response.ok) {
    throw new ApiError(
      payload && "detail" in payload
        ? (payload.detail ?? "Không thể tạo biểu đồ.")
        : "Không thể tạo biểu đồ.",
      response.status,
    );
  }
  return payload as ActionExecutionResponse;
}

export async function executeCreateDashboard(
  plan: DashboardPlan,
): Promise<ActionExecutionResponse> {
  const response = await fetch(apiUrl("/api/v1/ai/actions/execute"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action: "CREATE_DASHBOARD",
      dataset_id: plan.dataset_id,
      dashboard_plan: plan,
    }),
  });
  const payload = (await response.json().catch(() => null)) as
    | ActionExecutionResponse
    | { detail?: string }
    | null;
  if (!response.ok) {
    throw new ApiError(
      payload && "detail" in payload
        ? (payload.detail ?? "Không thể tạo bảng điều khiển.")
        : "Không thể tạo bảng điều khiển.",
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
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action,
      [field]: plan,
      ...(query && visualization ? { query, visualization } : {}),
    }),
  });
  const payload = (await response.json().catch(() => null)) as
    | ActionExecutionResponse
    | { detail?: string }
    | null;
  if (!response.ok)
    throw new ApiError(
      payload && "detail" in payload
        ? (payload.detail ?? "Không thể áp dụng thay đổi này.")
        : "Không thể áp dụng thay đổi này.",
      response.status,
    );
  return payload as ActionExecutionResponse;
}

export async function getSupersetCharts(dashboardId?: number): Promise<SupersetChartItem[]> {
  const query = dashboardId ? `?dashboard_id=${dashboardId}` : "";
  const response = await fetch(apiUrl(`/api/v1/superset/charts${query}`), {
    cache: "no-store",
  });
  const payload = (await response.json().catch(() => null)) as
    | SupersetChartItem[]
    | { detail?: string }
    | null;
  if (!response.ok) {
    throw new ApiError(
      payload && "detail" in payload
        ? (payload.detail ?? "Không thể tải danh sách biểu đồ.")
        : "Không thể tải danh sách biểu đồ.",
      response.status,
    );
  }
  return (payload as SupersetChartItem[]) || [];
}

export async function explainSupersetChart(
  chartId: number,
): Promise<SupersetChartExplanationResponse> {
  const response = await fetch(apiUrl(`/api/v1/superset/charts/${chartId}/explain`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  const payload = (await response.json().catch(() => null)) as
    | SupersetChartExplanationResponse
    | { detail?: string }
    | null;
  if (!response.ok) {
    throw new ApiError(
      payload && "detail" in payload
        ? (payload.detail ?? "Không thể giải thích biểu đồ.")
        : "Không thể giải thích biểu đồ.",
      response.status,
    );
  }
  return payload as SupersetChartExplanationResponse;
}

export async function uploadDataset(
  file: File,
  tableName?: string,
  description?: string,
): Promise<UploadDatasetResult> {
  const formData = new FormData();
  formData.append("file", file);
  if (tableName) formData.append("table_name", tableName);
  if (description) formData.append("description", description);

  const response = await fetch(apiUrl("/api/v1/data/upload"), {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(errorPayload?.detail ?? "Không thể tải lên tệp dữ liệu.", response.status);
  }

  return response.json() as Promise<UploadDatasetResult>;
}

export async function previewDataset(datasetId: number, limit = 20): Promise<DatasetPreviewResult> {
  const response = await fetch(apiUrl(`/api/v1/data/preview/${datasetId}?limit=${limit}`), {
    cache: "no-store",
  });

  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(errorPayload?.detail ?? "Không thể xem trước dữ liệu.", response.status);
  }

  return response.json() as Promise<DatasetPreviewResult>;
}

export async function getDashboardsList(): Promise<DashboardOption[]> {
  const response = await fetch(apiUrl("/api/v1/data/dashboards"), {
    cache: "no-store",
  });

  if (!response.ok) {
    return [];
  }

  return response.json() as Promise<DashboardOption[]>;
}

export async function updateDatasetDashboardSetting(
  datasetId: number,
  dashboardId: number | null,
  isEnabled: boolean,
): Promise<{ dataset_id: number; dashboard_id: number | null; is_enabled: boolean }> {
  const response = await fetch(apiUrl(`/api/v1/data/datasets/${datasetId}/dashboard`), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dashboard_id: dashboardId, is_enabled: isEnabled }),
  });

  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(
      errorPayload?.detail ?? "Không thể cập nhật cấu hình dashboard.",
      response.status,
    );
  }

  return response.json() as Promise<{
    dataset_id: number;
    dashboard_id: number | null;
    is_enabled: boolean;
  }>;
}

export async function getGlossary(datasetId?: number): Promise<BusinessGlossaryItem[]> {
  const url = datasetId
    ? apiUrl(`/api/v1/semantic/glossary?dataset_id=${datasetId}`)
    : apiUrl("/api/v1/semantic/glossary");
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    return [];
  }
  return response.json() as Promise<BusinessGlossaryItem[]>;
}

export async function addGlossaryTerm(
  item: Omit<BusinessGlossaryItem, "id" | "created_at">,
): Promise<BusinessGlossaryItem> {
  const response = await fetch(apiUrl("/api/v1/semantic/glossary"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(item),
  });
  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(
      errorPayload?.detail ?? "Không thể thêm thuật ngữ nghiệp vụ.",
      response.status,
    );
  }
  return response.json() as Promise<BusinessGlossaryItem>;
}

export async function deleteGlossaryTerm(termId: number): Promise<{ success: boolean }> {
  const response = await fetch(apiUrl(`/api/v1/semantic/glossary/${termId}`), {
    method: "DELETE",
  });
  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(errorPayload?.detail ?? "Không thể xóa thuật ngữ.", response.status);
  }
  return response.json() as Promise<{ success: boolean }>;
}

export async function getVerifiedMetrics(datasetId?: number): Promise<VerifiedMetricItem[]> {
  const url = datasetId
    ? apiUrl(`/api/v1/semantic/metrics?dataset_id=${datasetId}`)
    : apiUrl("/api/v1/semantic/metrics");
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    return [];
  }
  return response.json() as Promise<VerifiedMetricItem[]>;
}

export async function addVerifiedMetric(
  item: Omit<VerifiedMetricItem, "id" | "created_at">,
): Promise<VerifiedMetricItem> {
  const response = await fetch(apiUrl("/api/v1/semantic/metrics"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(item),
  });
  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(errorPayload?.detail ?? "Không thể thêm chỉ số chuẩn.", response.status);
  }
  return response.json() as Promise<VerifiedMetricItem>;
}

export async function deleteVerifiedMetric(metricId: number): Promise<{ success: boolean }> {
  const response = await fetch(apiUrl(`/api/v1/semantic/metrics/${metricId}`), {
    method: "DELETE",
  });
  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(errorPayload?.detail ?? "Không thể xóa chỉ số.", response.status);
  }
  return response.json() as Promise<{ success: boolean }>;
}

export async function getChatSessions(datasetId?: number): Promise<ChatSession[]> {
  const url = datasetId
    ? apiUrl(`/api/v1/chat/sessions?dataset_id=${datasetId}`)
    : apiUrl("/api/v1/chat/sessions");
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    return [];
  }
  return response.json() as Promise<ChatSession[]>;
}

export async function createChatSession(
  title: string,
  datasetId?: number | null,
): Promise<ChatSession> {
  const response = await fetch(apiUrl("/api/v1/chat/sessions"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, dataset_id: datasetId }),
  });
  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(errorPayload?.detail ?? "Không thể tạo phiên chat.", response.status);
  }
  return response.json() as Promise<ChatSession>;
}

export async function deleteChatSession(sessionId: string): Promise<{ success: boolean }> {
  const response = await fetch(apiUrl(`/api/v1/chat/sessions/${sessionId}`), {
    method: "DELETE",
  });
  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(errorPayload?.detail ?? "Không thể xóa phiên hội thoại.", response.status);
  }
  return response.json() as Promise<{ success: boolean }>;
}

export async function getChatSessionMessages(sessionId: string): Promise<DbChatMessage[]> {
  const response = await fetch(apiUrl(`/api/v1/chat/sessions/${sessionId}/messages`), {
    cache: "no-store",
  });
  if (!response.ok) {
    return [];
  }
  return response.json() as Promise<DbChatMessage[]>;
}

// ==========================================
// Phase 4: Enterprise Auth, Alerts & Caching
// ==========================================

export async function loginApi(
  username: string,
  password: string,
): Promise<{ token: string; user: UserProfile }> {
  const response = await fetch(apiUrl("/api/v1/auth/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(errorPayload?.detail ?? "Đăng nhập thất bại.", response.status);
  }
  return response.json() as Promise<{ token: string; user: UserProfile }>;
}

export async function getMeApi(): Promise<UserProfile> {
  const response = await fetch(apiUrl("/api/v1/auth/me"), {
    headers: { ...authHeaders() },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new ApiError("Phiên đăng nhập hết hạn.", response.status);
  }
  return response.json() as Promise<UserProfile>;
}

export async function getDemoUsersApi(): Promise<UserProfile[]> {
  const response = await fetch(apiUrl("/api/v1/auth/users"), { cache: "no-store" });
  if (!response.ok) return [];
  return response.json() as Promise<UserProfile[]>;
}

export async function getAlertsApi(): Promise<{ alerts: AlertItem[]; unread_count: number }> {
  const response = await fetch(apiUrl("/api/v1/alerts"), { cache: "no-store" });
  if (!response.ok) return { alerts: [], unread_count: 0 };
  return response.json() as Promise<{ alerts: AlertItem[]; unread_count: number }>;
}

export async function markAlertReadApi(alertId: number): Promise<void> {
  await fetch(apiUrl(`/api/v1/alerts/${alertId}/read`), { method: "POST" });
}

export async function markAllAlertsReadApi(): Promise<void> {
  await fetch(apiUrl("/api/v1/alerts/read-all"), { method: "POST" });
}

export async function scanAnomaliesApi(datasetId: number = 1): Promise<void> {
  await fetch(apiUrl(`/api/v1/alerts/scan?dataset_id=${datasetId}`), { method: "POST" });
}

export async function clearSemanticCacheApi(): Promise<void> {
  await fetch(apiUrl("/api/v1/ai/cache/clear"), { method: "POST" });
}
