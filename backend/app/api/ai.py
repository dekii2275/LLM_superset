import logging

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.schemas.ai import (
    AIChatRequest,
    AIChatResponse,
    AIIntent,
    ActionExecutionRequest,
    ActionExecutionResponse,
    EditDashboardOperation,
)
from app.services.ai_bi_service import AIBIService
from app.services.gemini_service import GeminiService
from app.services.mcp_service import MCPToolError, MCPUnavailableError, SupersetMCPService
from app.services.query_service import QueryService, SQLValidationError
from app.services.superset_write_service import SupersetWriteService
from app.services.visualization_service import VisualizationService

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])
logger = logging.getLogger(__name__)


def mcp_service() -> SupersetMCPService:
    return SupersetMCPService(
        settings.superset_mcp_internal_url,
        # Task 3 deliberately exposes metadata only. Future write phases need
        # an explicit, separately reviewed route rather than an environment
        # toggle which could accidentally enable mutations here.
        allow_write=False,
    )


@router.get("/health")
async def ai_health() -> dict[str, str | bool]:
    try:
        tools = await mcp_service().list_tools()
        mcp_status = "connected" if tools else "connected (no tools returned)"
    except MCPUnavailableError:
        mcp_status = "unavailable"
    return {
        "status": "ok" if mcp_status.startswith("connected") else "degraded",
        "gemini_configured": bool(settings.gemini_api_key),
        "mcp": mcp_status,
    }


@router.post("/chat", response_model=AIChatResponse)
async def ai_chat(request: AIChatRequest) -> AIChatResponse:
    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="Gemini API is not configured")
    service = AIBIService(
        mcp_service(),
        GeminiService(
            settings.gemini_api_key,
            settings.gemini_model,
            answer_max_rows=settings.ai_answer_max_rows,
        ),
        QueryService(
            default_limit=settings.default_query_limit,
            max_limit=settings.max_query_limit,
            timeout_seconds=settings.ai_query_timeout_seconds,
        ),
        asset_resolver=SupersetWriteService(
            settings.superset_url,
            settings.superset_public_url,
            settings.superset_admin_username,
            settings.superset_admin_password,
            settings.superset_taxi_dataset_id,
            settings.frontend_origins,
        ),
    )
    try:
        return await service.chat(request.message, request.context)
    except MCPUnavailableError as error:
        raise HTTPException(status_code=503, detail="Superset MCP is unavailable") from error
    except MCPToolError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        # Do not return provider internals or credentials to callers.
        provider_status = getattr(error, "code", None)
        logger.error(
            "Gemini orchestration failed: error_type=%s status=%s",
            type(error).__name__,
            provider_status,
        )
        if provider_status == 429:
            raise HTTPException(status_code=429, detail="Gemini rate limit reached; retry later") from error
        if provider_status in {500, 503, 504}:
            raise HTTPException(status_code=503, detail="Gemini is temporarily unavailable; retry later") from error
        raise HTTPException(
            status_code=502,
            detail="Gemini request failed; verify GEMINI_MODEL and API access",
        ) from error


@router.post("/actions/execute", response_model=ActionExecutionResponse)
async def execute_action(request: ActionExecutionRequest) -> ActionExecutionResponse:
    """Confirmation-only write boundary. `/chat` remains read-only."""
    if request.action not in {AIIntent.CREATE_CHART, AIIntent.CREATE_DASHBOARD, AIIntent.EDIT_CHART, AIIntent.EDIT_DASHBOARD}:
        raise HTTPException(status_code=400, detail="Unsupported confirmed action.")

    writer = SupersetWriteService(
        settings.superset_url,
        settings.superset_public_url,
        settings.superset_admin_username,
        settings.superset_admin_password,
        settings.superset_taxi_dataset_id,
        settings.frontend_origins,
    )

    if request.action == AIIntent.EDIT_CHART:
        if not request.edit_chart_plan:
            raise HTTPException(status_code=422, detail="An edit chart plan is required.")
        result = await writer.edit_chart(request.edit_chart_plan)
        return ActionExecutionResponse(success=result.success, action=AIIntent.EDIT_CHART, result=result if result.success else None, message=result.message, error=result.error)

    if request.action == AIIntent.EDIT_DASHBOARD:
        if not request.edit_dashboard_plan:
            raise HTTPException(status_code=422, detail="An edit dashboard plan is required.")
        plan = request.edit_dashboard_plan
        prepared_new_chart = None
        if plan.operation == EditDashboardOperation.ADD_CHART and plan.create_chart_plan:
            planner = AIBIService(
                mcp_service(),
                GeminiService(settings.gemini_api_key or "", settings.gemini_model, answer_max_rows=settings.ai_answer_max_rows),
                QueryService(default_limit=settings.default_query_limit, max_limit=settings.max_query_limit, timeout_seconds=settings.ai_query_timeout_seconds),
            )
            try:
                prepared_new_chart = await planner.prepare_chart_for_write(plan.create_chart_plan)
            except (RuntimeError, SQLValidationError) as error:
                logger.warning("dashboard_add_chart_prepare_failed dashboard_id=%s error=%s", plan.dashboard_id, error)
                return ActionExecutionResponse(success=False, action=AIIntent.EDIT_DASHBOARD, message="Không thể chuẩn bị biểu đồ mới cho dashboard.", error=str(error))
        result = await writer.edit_dashboard(plan, prepared_new_chart)
        return ActionExecutionResponse(success=result.success, action=AIIntent.EDIT_DASHBOARD, result=result if result.success else None, message=result.message, error=result.error)

    if request.action == AIIntent.CREATE_DASHBOARD:
        if not request.dashboard_plan:
            raise HTTPException(status_code=422, detail="A dashboard plan is required.")
        if not 3 <= len(request.dashboard_plan.charts) <= 4:
            raise HTTPException(status_code=400, detail="A dashboard must contain three or four charts.")
        planner = AIBIService(
            mcp_service(),
            GeminiService(
                settings.gemini_api_key or "",
                settings.gemini_model,
                answer_max_rows=settings.ai_answer_max_rows,
            ),
            QueryService(
                default_limit=settings.default_query_limit,
                max_limit=settings.max_query_limit,
                timeout_seconds=settings.ai_query_timeout_seconds,
            ),
        )
        try:
            prepared_charts = await planner.prepare_dashboard_charts(request.dashboard_plan)
        except (RuntimeError, SQLValidationError) as error:
            logger.warning("dashboard_prepare_failed title=%r error=%s", request.dashboard_plan.title, error)
            return ActionExecutionResponse(
                success=False,
                action=AIIntent.CREATE_DASHBOARD,
                message="Không thể chuẩn bị đầy đủ biểu đồ cho dashboard.",
                error=str(error),
            )
        result = await writer.create_dashboard(request.dashboard_plan, prepared_charts)
        return ActionExecutionResponse(
            success=result.success,
            action=AIIntent.CREATE_DASHBOARD,
            result=result if result.success else None,
            message=result.message,
            error=result.error,
        )

    if not request.chart_plan or not request.query or not request.visualization:
        raise HTTPException(status_code=422, detail="A chart plan, query, and visualization are required.")

    query_service = QueryService(
        default_limit=settings.default_query_limit,
        max_limit=settings.max_query_limit,
        timeout_seconds=settings.ai_query_timeout_seconds,
    )
    try:
        # Revalidate untrusted browser data. The normalized SQL is never
        # executed here; chart creation uses the server-controlled dataset map.
        safe_sql = query_service.prepare_sql(request.query.sql or "")
    except SQLValidationError as error:
        raise HTTPException(status_code=400, detail="The pending chart query is not read-only.") from error

    if request.query.error or not request.query.rows:
        raise HTTPException(status_code=400, detail="The pending chart has no usable query data.")
    validated_visualization = VisualizationService().validate(request.visualization, request.query)
    if validated_visualization.type == "none":
        raise HTTPException(status_code=400, detail="The pending chart visualization is invalid.")
    if validated_visualization.type != request.chart_plan.chart_type:
        raise HTTPException(status_code=400, detail="The chart plan and visualization type do not match.")

    result = await writer.create_chart(request.chart_plan, safe_sql, validated_visualization)
    return ActionExecutionResponse(
        success=result.success,
        action=AIIntent.CREATE_CHART,
        result=result if result.success else None,
        message=result.message,
        error=result.error,
    )
