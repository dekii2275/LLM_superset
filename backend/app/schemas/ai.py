from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AIIntent(str, Enum):
    ASK_DATA = "ASK_DATA"
    CREATE_CHART = "CREATE_CHART"
    CREATE_DASHBOARD = "CREATE_DASHBOARD"
    EDIT_CHART = "EDIT_CHART"
    EDIT_DASHBOARD = "EDIT_DASHBOARD"
    GENERAL = "GENERAL"


class AIChatContext(BaseModel):
    """Optional, trusted UI context for a future saved-asset workflow."""

    active_dashboard_id: int | None = None
    active_dashboard_title: str | None = None
    active_chart_id: int | None = None
    active_chart_title: str | None = None
    # The browser may provide the most recent temporary result when the user
    # asks to save it. The server validates its SQL and visualization again.
    last_query: dict[str, Any] | None = None
    last_visualization: dict[str, Any] | None = None


class AIChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)
    context: AIChatContext | None = None


class IntentResult(BaseModel):
    intent: AIIntent
    confidence: float | None = Field(default=None, ge=0, le=1)
    target_type: str | None = None
    target_name: str | None = None
    target_id: int | None = None
    operation: str | None = None
    user_goal: str
    requires_confirmation: bool = False


class IntentInfo(BaseModel):
    type: AIIntent
    confidence: float | None = None


class AIActionPlan(BaseModel):
    action: AIIntent
    title: str
    description: str
    target_type: str | None = None
    target_id: int | None = None
    target_name: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = True


class AIToolCall(BaseModel):
    tool: str
    status: Literal["success", "error", "blocked"]
    summary: str | None = None


class SQLGenerationResult(BaseModel):
    """The bounded, user-visible plan returned by Gemini for a data question."""

    intent: str
    sql: str = ""
    reasoning_summary: str | None = None
    answer_type: str = "table"


class QueryResult(BaseModel):
    sql: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    execution_time_ms: int | None = None
    error: str | None = None


class VisualizationSpec(BaseModel):
    type: Literal["none", "bar", "line", "pie", "area"] = "none"
    title: str | None = None
    x_axis: str | None = None
    y_axis: str | None = None
    x_label: str | None = None
    y_label: str | None = None


class ChartPlan(BaseModel):
    """A semantic chart request; deliberately independent from Superset form_data."""

    title: str = Field(min_length=1, max_length=200)
    chart_type: Literal["bar", "line", "pie", "area"]
    question: str = Field(min_length=1, max_length=4_000)
    metric: str | None = None
    dimension: str | None = None
    limit: int | None = Field(default=None, ge=1, le=500)
    sort: str | None = None


class DashboardPlan(BaseModel):
    """A compact semantic dashboard plan; layout remains backend-owned."""

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1_000)
    charts: list[ChartPlan] = Field(min_length=3, max_length=4)


class EditChartOperation(str, Enum):
    CHANGE_CHART_TYPE = "CHANGE_CHART_TYPE"
    RENAME_CHART = "RENAME_CHART"
    CHANGE_METRIC = "CHANGE_METRIC"
    CHANGE_DIMENSION = "CHANGE_DIMENSION"


class EditDashboardOperation(str, Enum):
    ADD_CHART = "ADD_CHART"
    REMOVE_CHART = "REMOVE_CHART"
    RENAME_DASHBOARD = "RENAME_DASHBOARD"


class EditChartPlan(BaseModel):
    """A deliberately small, semantic saved-chart change request."""

    chart_id: int | None = Field(default=None, ge=1)
    chart_name: str | None = Field(default=None, min_length=1, max_length=200)
    operation: EditChartOperation
    new_title: str | None = Field(default=None, min_length=1, max_length=200)
    new_chart_type: Literal["bar", "line", "pie"] | None = None
    new_metric: str | None = Field(default=None, min_length=1, max_length=200)
    new_dimension: str | None = Field(default=None, min_length=1, max_length=200)


class EditDashboardPlan(BaseModel):
    """A bounded dashboard change; layout and REST payloads stay server-owned."""

    dashboard_id: int | None = Field(default=None, ge=1)
    dashboard_name: str | None = Field(default=None, min_length=1, max_length=200)
    operation: EditDashboardOperation
    chart_id: int | None = Field(default=None, ge=1)
    chart_name: str | None = Field(default=None, min_length=1, max_length=200)
    new_title: str | None = Field(default=None, min_length=1, max_length=200)
    create_chart_plan: ChartPlan | None = None


class PendingAction(BaseModel):
    action: Literal["CREATE_CHART"] = "CREATE_CHART"
    chart_plan: ChartPlan
    requires_confirmation: bool = True
    query_sql: str | None = None


class PendingDashboardAction(BaseModel):
    action: Literal["CREATE_DASHBOARD"] = "CREATE_DASHBOARD"
    dashboard_plan: DashboardPlan
    requires_confirmation: bool = True


class PendingEditChartAction(BaseModel):
    action: Literal["EDIT_CHART"] = "EDIT_CHART"
    edit_chart_plan: EditChartPlan
    requires_confirmation: bool = True


class PendingEditDashboardAction(BaseModel):
    action: Literal["EDIT_DASHBOARD"] = "EDIT_DASHBOARD"
    edit_dashboard_plan: EditDashboardPlan
    requires_confirmation: bool = True


class CreateChartResult(BaseModel):
    success: bool
    chart_id: int | None = None
    chart_name: str | None = None
    url: str | None = None
    message: str
    error: str | None = None


class CreateDashboardResult(BaseModel):
    success: bool
    dashboard_id: int | None = None
    dashboard_uuid: str | None = None
    dashboard_name: str | None = None
    chart_ids: list[int] = Field(default_factory=list)
    url: str | None = None
    message: str
    error: str | None = None


class UpdateChartResult(CreateChartResult):
    """The response shape is intentionally compatible with saved chart cards."""


class UpdateDashboardResult(CreateDashboardResult):
    """The response shape is intentionally compatible with embedded dashboards."""


class ActionExecutionRequest(BaseModel):
    action: AIIntent
    chart_plan: ChartPlan | None = None
    dashboard_plan: DashboardPlan | None = None
    query: QueryResult | None = None
    visualization: VisualizationSpec | None = None
    edit_chart_plan: EditChartPlan | None = None
    edit_dashboard_plan: EditDashboardPlan | None = None


class ActionExecutionResponse(BaseModel):
    success: bool
    action: AIIntent
    result: CreateChartResult | CreateDashboardResult | UpdateChartResult | UpdateDashboardResult | None = None
    message: str
    error: str | None = None


class AIChatResponse(BaseModel):
    answer: str
    tool_calls: list[AIToolCall] = Field(default_factory=list)
    intent: IntentInfo | None = None
    action_plan: AIActionPlan | None = None
    dashboard_plan: DashboardPlan | None = None
    edit_chart_plan: EditChartPlan | None = None
    edit_dashboard_plan: EditDashboardPlan | None = None
    pending_action: PendingAction | PendingDashboardAction | PendingEditChartAction | PendingEditDashboardAction | None = None
    query: QueryResult | None = None
    visualization: VisualizationSpec | None = None
