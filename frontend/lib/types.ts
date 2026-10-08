export type MessageRole = "user" | "assistant";

export type ToolCall = {
  tool: string;
  status: "success" | "error" | "blocked";
  summary?: string | null;
};

export type VisualizationType =
  | "none"
  | "bar"
  | "line"
  | "pie"
  | "area"
  | "kpi"
  | "table"
  | "scatter"
  | "map"
  | "heatmap";

export type AIIntent =
  | "ASK_DATA"
  | "CREATE_CHART"
  | "CREATE_DASHBOARD"
  | "EDIT_CHART"
  | "EDIT_DASHBOARD"
  | "GENERAL";

export type DatasetSummary = {
  id: number;
  table_name: string;
  name: string;
  schema_name?: string | null;
  description?: string | null;
  column_count: number;
  metric_count: number;
  columns: string[];
  metrics: string[];
  default_dashboard_id?: number | null;
  default_dashboard_title?: string | null;
};

export type AIChatContext = {
  active_dashboard_id?: number | null;
  active_dashboard_title?: string | null;
  active_chart_id?: number | null;
  active_chart_title?: string | null;
  dataset_id?: number | null;
  session_id?: string | null;
  conversation_history?: Array<{ role: string; content: string }> | null;
  last_query?: QueryResult | null;
  last_visualization?: VisualizationSpec | null;
  pending_dashboard_plan?: DashboardPlan | null;
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
  chart_type: "bar" | "line" | "pie" | "area" | "kpi" | "table" | "scatter" | "map" | "heatmap";
  map_style?: "grid" | "scatter" | null;
  question: string;
  metric?: string | null;
  dimension?: string | null;
  secondary_dimension?: string | null;
  limit?: number | null;
  sort?: string | null;
  dataset_id?: number | null;
};

export type DashboardPlan = {
  title: string;
  description?: string | null;
  charts: ChartPlan[];
  dataset_id?: number | null;
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

export type EditChartOperation =
  | "CHANGE_CHART_TYPE"
  | "RENAME_CHART"
  | "CHANGE_METRIC"
  | "CHANGE_DIMENSION";
export type EditDashboardOperation = "ADD_CHART" | "REMOVE_CHART" | "RENAME_DASHBOARD";

export type EditChartPlan = {
  chart_id?: number | null;
  chart_name?: string | null;
  operation: EditChartOperation;
  new_title?: string | null;
  new_chart_type?: "bar" | "line" | "pie" | "area" | "kpi" | "table" | "scatter" | "map" | null;
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

export type PendingEditChartAction = {
  action: "EDIT_CHART";
  edit_chart_plan: EditChartPlan;
  requires_confirmation: boolean;
};
export type PendingEditDashboardAction = {
  action: "EDIT_DASHBOARD";
  edit_dashboard_plan: EditDashboardPlan;
  requires_confirmation: boolean;
};

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
  map_style?: "grid" | "scatter" | null;
  title?: string | null;
  x_axis?: string | null;
  y_axis?: string | null;
  value_axis?: string | null;
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

export type ChartExplanation = {
  summary: string;
  highlights: string[];
  note: string;
};

export type RlsRuleItem = {
  dataset_id: number;
  filter_clause: string;
  description?: string | null;
};

export type UserProfile = {
  id: number;
  username: string;
  display_name: string;
  role: string;
  is_active?: boolean;
  rls_rules: RlsRuleItem[];
};

export type AlertItem = {
  id: number;
  dataset_id?: number | null;
  alert_type: string;
  severity: "info" | "warning" | "critical";
  title: string;
  message: string;
  metric_name?: string | null;
  change_percent?: number | null;
  suggested_query?: string | null;
  is_read: boolean;
  created_at?: string | null;
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
  pendingAction?:
    | PendingCreateChartAction
    | PendingCreateDashboardAction
    | PendingEditChartAction
    | PendingEditDashboardAction
    | null;
  query?: QueryResult | null;
  visualization?: VisualizationSpec | null;
  cached?: boolean;
  cache_type?: string | null;
  cache_latency_ms?: number | null;
  applied_rls_filter?: string | null;
};

export type AIChatResponse = {
  answer: string;
  tool_calls: ToolCall[];
  intent?: IntentInfo | null;
  action_plan?: AIActionPlan | null;
  dashboard_plan?: DashboardPlan | null;
  edit_chart_plan?: EditChartPlan | null;
  edit_dashboard_plan?: EditDashboardPlan | null;
  pending_action?:
    | PendingCreateChartAction
    | PendingCreateDashboardAction
    | PendingEditChartAction
    | PendingEditDashboardAction
    | null;
  query?: QueryResult | null;
  visualization?: VisualizationSpec | null;
  session_id?: string | null;
  cached?: boolean;
  cache_type?: string | null;
  cache_latency_ms?: number | null;
  applied_rls_filter?: string | null;
};

export type SupersetChartItem = {
  id: number;
  slice_name: string;
  viz_type: "bar" | "line" | "pie" | "area" | "kpi" | string;
  raw_viz_type?: string;
  description?: string;
};

export type SupersetChartExplanationResponse = {
  chart_id: number;
  chart_name: string;
  viz_type: string;
  sql?: string | null;
  explanation: ChartExplanation;
};

export type DatasetColumnMeta = {
  name: string;
  type: string;
  sample?: string[];
};

export type UploadDatasetResult = {
  dataset_id?: number | null;
  table_name: string;
  row_count: number;
  column_count: number;
  columns: DatasetColumnMeta[];
  sample_rows: Record<string, unknown>[];
  description?: string;
};

export type DatasetPreviewResult = {
  table_name: string;
  total_rows: number;
  column_count: number;
  columns: { name: string; type: string }[];
  rows: Record<string, unknown>[];
};

export type DashboardOption = {
  id: number;
  title: string;
  slug: string;
};

export type BusinessGlossaryItem = {
  id?: number;
  dataset_id: number;
  term: string;
  target_type: "column" | "metric" | "filter" | string;
  target_name: string;
  description?: string | null;
  created_at?: string | null;
};

export type VerifiedMetricItem = {
  id?: number;
  dataset_id: number;
  metric_name: string;
  display_name: string;
  sql_expression: string;
  description?: string | null;
  created_at?: string | null;
};

export type ChatSession = {
  id: string;
  title: string;
  dataset_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type DbChatMessage = {
  id?: number;
  session_id: string;
  sender: "user" | "assistant";
  content: string;
  metadata?: Record<string, unknown> | null;
  created_at?: string | null;
};
