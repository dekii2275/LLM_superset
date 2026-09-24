export type MessageRole = "user" | "assistant";

export type ToolCall = {
  tool: string;
  status: "success" | "error" | "blocked";
  summary?: string | null;
};

export type VisualizationType = "none" | "bar" | "line" | "pie" | "area";

export type AIIntent =
  | "ASK_DATA"
  | "CREATE_CHART"
  | "CREATE_DASHBOARD"
  | "EDIT_CHART"
  | "EDIT_DASHBOARD"
  | "GENERAL";

export type AIChatContext = {
  active_dashboard_id?: number | null;
  active_dashboard_title?: string | null;
  active_chart_id?: number | null;
  active_chart_title?: string | null;
  last_query?: QueryResult | null;
  last_visualization?: VisualizationSpec | null;
};

export type IntentInfo = {
  type: AIIntent;
  confidence?: number | null;
};

export type AIActionPlan = {
  action: AIIntent;
  title: string;
  description: string;
  target_type?: string | null;
  target_id?: number | null;
  target_name?: string | null;
  parameters?: Record<string, unknown>;
  requires_confirmation: boolean;
};

export type ChartPlan = {
  title: string;
  chart_type: "bar" | "line" | "pie" | "area";
  question: string;
  metric?: string | null;
  dimension?: string | null;
  limit?: number | null;
  sort?: string | null;
};

export type DashboardPlan = {
  title: string;
  description?: string | null;
  charts: ChartPlan[];
};

export type PendingCreateChartAction = {
  action: "CREATE_CHART";
  chart_plan: ChartPlan;
  requires_confirmation: boolean;
  query_sql?: string | null;
};

export type PendingCreateDashboardAction = {
  action: "CREATE_DASHBOARD";
  dashboard_plan: DashboardPlan;
  requires_confirmation: boolean;
};

export type EditChartOperation = "CHANGE_CHART_TYPE" | "RENAME_CHART" | "CHANGE_METRIC" | "CHANGE_DIMENSION";
export type EditDashboardOperation = "ADD_CHART" | "REMOVE_CHART" | "RENAME_DASHBOARD";

export type EditChartPlan = {
  chart_id?: number | null;
  chart_name?: string | null;
  operation: EditChartOperation;
  new_title?: string | null;
  new_chart_type?: "bar" | "line" | "pie" | null;
  new_metric?: string | null;
  new_dimension?: string | null;
};

export type EditDashboardPlan = {
  dashboard_id?: number | null;
  dashboard_name?: string | null;
  operation: EditDashboardOperation;
  chart_id?: number | null;
  chart_name?: string | null;
  new_title?: string | null;
  create_chart_plan?: ChartPlan | null;
};

export type PendingEditChartAction = { action: "EDIT_CHART"; edit_chart_plan: EditChartPlan; requires_confirmation: boolean };
export type PendingEditDashboardAction = { action: "EDIT_DASHBOARD"; edit_dashboard_plan: EditDashboardPlan; requires_confirmation: boolean };

export type CreateChartResult = {
  success: boolean;
  chart_id?: number | null;
  chart_name?: string | null;
  url?: string | null;
  message: string;
  error?: string | null;
};

export type CreateDashboardResult = {
  success: boolean;
  dashboard_id?: number | null;
  dashboard_uuid?: string | null;
  dashboard_name?: string | null;
  chart_ids: number[];
  url?: string | null;
  message: string;
  error?: string | null;
};

export type ActionExecutionResponse = {
  success: boolean;
  action: AIIntent;
  result?: CreateChartResult | CreateDashboardResult | null;
  message: string;
  error?: string | null;
};

export type VisualizationSpec = {
  type: VisualizationType;
  title?: string | null;
  x_axis?: string | null;
  y_axis?: string | null;
  x_label?: string | null;
  y_label?: string | null;
};

export type QueryResult = {
  sql?: string | null;
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  execution_time_ms?: number | null;
  error?: string | null;
};

export type ChatMessage = {
  id: string;
  role: MessageRole;
  content: string;
  createdAt: string;
  toolCalls?: ToolCall[];
  intent?: IntentInfo | null;
  actionPlan?: AIActionPlan | null;
  dashboardPlan?: DashboardPlan | null;
  pendingAction?: PendingCreateChartAction | PendingCreateDashboardAction | PendingEditChartAction | PendingEditDashboardAction | null;
  query?: QueryResult | null;
  visualization?: VisualizationSpec | null;
};

export type AIChatResponse = {
  answer: string;
  tool_calls: ToolCall[];
  intent?: IntentInfo | null;
  action_plan?: AIActionPlan | null;
  dashboard_plan?: DashboardPlan | null;
  edit_chart_plan?: EditChartPlan | null;
  edit_dashboard_plan?: EditDashboardPlan | null;
  pending_action?: PendingCreateChartAction | PendingCreateDashboardAction | PendingEditChartAction | PendingEditDashboardAction | null;
  query?: QueryResult | null;
  visualization?: VisualizationSpec | null;
};
