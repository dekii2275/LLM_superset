import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.api.auth import get_current_user_optional
from app.core.config import settings
from app.schemas.ai import (
    ActionExecutionRequest,
    ActionExecutionResponse,
    AIChatContext,
    AIChatRequest,
    AIChatResponse,
    AIIntent,
    ChartExplanation,
    DatasetSummary,
    EditDashboardOperation,
    ExplainChartRequest,
)
from app.services.ai_bi_service import AIBIService
from app.services.ai_settings import get_token_usage, is_llm_enabled, set_llm_enabled
from app.services.cache_service import cache_service
from app.services.chart_explanation_service import (
    ChartExplanationService,
    ChartExplanationValidationError,
)
from app.services.future_date_service import future_date_response
from app.services.gemini_service import GeminiService
from app.services.mcp_service import MCPToolError, MCPUnavailableError, SupersetMCPService
from app.services.query_service import QueryService, SQLValidationError
from app.services.rls_service import RLSService
from app.services.schema_service import SchemaService
from app.services.superset import SupersetClient
from app.services.superset_write_service import SupersetWriteService
from app.services.visualization_service import VisualizationService

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])
logger = logging.getLogger(__name__)


def _response_metadata(response: AIChatResponse) -> dict[str, Any]:
    """Store the same chart and action state for live and cached answers."""
    metadata: dict[str, Any] = {}
    if response.query:
        metadata["query"] = response.query.model_dump(mode="json")
        if response.query.sql:
            metadata["sql"] = response.query.sql
    if response.intent:
        metadata["intent"] = response.intent.model_dump(mode="json")
    for field in ("visualization", "dashboard_plan", "action_plan", "pending_action"):
        value = getattr(response, field)
        if value:
            metadata[field] = value.model_dump(mode="json")
    if response.applied_rls_filter:
        metadata["applied_rls_filter"] = response.applied_rls_filter
    if response.cached:
        metadata["cached"] = True
        metadata["cache_type"] = response.cache_type
        metadata["cache_latency_ms"] = response.cache_latency_ms
    return metadata


def _persist_assistant_response(session_id: str | None, response: AIChatResponse) -> None:
    if not session_id:
        return
    response.session_id = session_id
    try:
        from app.services.chat_persistence_service import ChatPersistenceService

        ChatPersistenceService.add_message(
            session_id, "assistant", response.answer, metadata=_response_metadata(response) or None
        )
    except Exception:
        logger.warning("Failed to persist assistant response", exc_info=True)


class AISettingsUpdate(BaseModel):
    llm_enabled: bool


def superset_client() -> SupersetClient | None:
    if not settings.superset_admin_username or not settings.superset_admin_password:
        return None
    client = SupersetClient(
        settings.superset_url, settings.superset_admin_username, settings.superset_admin_password
    )
    try:
        client.login()
        return client
    except Exception:
        logger.warning("superset_client_login_failed_in_ai_api")
        return None


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


@router.get("/datasets", response_model=list[DatasetSummary])
def list_datasets() -> list[DatasetSummary]:
    """Fetch all available datasets from Superset."""
    client = superset_client()
    service = SchemaService(client)
    return service.list_datasets()


@router.get("/settings")
def get_ai_settings() -> dict[str, bool | int]:
    return {"llm_enabled": is_llm_enabled(), "tokens_used": get_token_usage()}


@router.put("/settings")
def update_ai_settings(request: AISettingsUpdate) -> dict[str, bool | int]:
    return {"llm_enabled": set_llm_enabled(request.llm_enabled), "tokens_used": get_token_usage()}


@router.post("/chat", response_model=AIChatResponse)
async def ai_chat(
    request: AIChatRequest, authorization: str | None = Header(None)
) -> AIChatResponse:
    if not is_llm_enabled():
        raise HTTPException(
            status_code=503, detail="AI đã tắt trong Settings. Hãy bật lại để tiếp tục chat."
        )
    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="Gemini API is not configured")

    current_user = get_current_user_optional(authorization)
    target_dataset_id = request.dataset_id or settings.superset_taxi_dataset_id
    rls_info = RLSService.get_filter_for_user(current_user, target_dataset_id)
    rls_filter = rls_info["filter_clause"] if rls_info else None

    session_id = request.session_id or (request.context.session_id if request.context else None)
    if session_id:
        if request.context is None:
            request.context = AIChatContext(session_id=session_id)
        elif not request.context.session_id:
            request.context.session_id = session_id
        try:
            from app.services.chat_persistence_service import ChatPersistenceService

            ChatPersistenceService.add_message(session_id, "user", request.message)
        except Exception as e:
            logger.warning("Failed to persist user message: %s", e)

    # A future-day aggregate can yield a misleading SQL zero or a stale cache hit.
    future_response = future_date_response(request.message)
    if future_response:
        _persist_assistant_response(session_id, future_response)
        return future_response

    # 1. Semantic Cache Lookup (Tier 1: Exact, Tier 2: Semantic Similarity)
    cached_entry = (
        None
        if request.context and request.context.pending_dashboard_plan
        else cache_service.get(request.message, target_dataset_id, rls_filter=rls_filter)
    )
    if cached_entry and cached_entry.get("response"):
        resp_data = cached_entry["response"]
        cached_resp = AIChatResponse(**resp_data)
        # Older cache entries may contain action drafts or metadata answers.
        # Only a successful data answer can be replayed without its chat context.
        if (
            cached_resp.intent
            and cached_resp.intent.type == AIIntent.ASK_DATA
            and cached_resp.query
            and not cached_resp.query.error
        ):
            cached_resp.cached = True
            cached_resp.cache_type = cached_entry.get("cache_type", "exact")
            cached_resp.cache_latency_ms = cached_entry.get("latency_ms", 5.0)
            if rls_info:
                cached_resp.applied_rls_filter = rls_info.get("description")
            _persist_assistant_response(session_id, cached_resp)
            return cached_resp

    client = superset_client()
    schema_service = SchemaService(client)
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
        schema_service=schema_service,
    )

    try:
        response = await service.chat(
            request.message, request.context, dataset_id=request.dataset_id, user=current_user
        )

        # Store in Semantic Cache if it was a successful data query
        if (
            response.intent
            and response.intent.type == AIIntent.ASK_DATA
            and response.query
            and not response.query.error
            and response.answer
        ):
            cache_service.set(
                request.message, target_dataset_id, rls_filter, response.model_dump(mode="json")
            )

        _persist_assistant_response(session_id, response)
        return response
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
            raise HTTPException(
                status_code=429, detail="Gemini rate limit reached; retry later"
            ) from error
        if provider_status in {500, 503, 504}:
            raise HTTPException(
                status_code=503, detail="Gemini is temporarily unavailable; retry later"
            ) from error
        raise HTTPException(
            status_code=502,
            detail="Gemini request failed; verify GEMINI_MODEL and API access",
        ) from error


@router.post("/explain-chart", response_model=ChartExplanation)
async def explain_chart(request: ExplainChartRequest) -> ChartExplanation:
    """Re-run a chart's SQL under the read-only policy and explain its result."""
    query_service = QueryService(
        default_limit=settings.default_query_limit,
        max_limit=settings.max_query_limit,
        timeout_seconds=settings.ai_query_timeout_seconds,
    )
    try:
        result = await query_service.execute_query(request.sql)
    except SQLValidationError as error:
        raise HTTPException(
            status_code=400, detail="SQL của biểu đồ không hợp lệ hoặc không được phép."
        ) from error

    if result.error:
        logger.warning("chart_explanation_query_failed error_type=%s", type(result.error).__name__)
        raise HTTPException(status_code=422, detail="Không thể chạy lại truy vấn của biểu đồ.")

    try:
        service = ChartExplanationService()
        base_explanation = service.analyze(result, request.visualization)
        gemini = (
            GeminiService(settings.gemini_api_key, settings.gemini_model)
            if settings.gemini_api_key
            else None
        )
        if gemini:
            return await service.explain_with_gemini(
                base_explanation=base_explanation,
                chart_title=request.visualization.title or "Biểu đồ",
                viz_type=request.visualization.type,
                sample_rows=result.rows[:10],
                gemini=gemini,
            )
        return base_explanation
    except ChartExplanationValidationError as error:
        raise HTTPException(
            status_code=422, detail="Thông tin biểu đồ không khớp với kết quả truy vấn."
        ) from error


def _prepared_chart_from_preview(chart_plan, query, visualization):
    """Revalidate a reviewed browser preview before writing a new chart."""
    if not query or not visualization:
        raise RuntimeError("A chart preview is required.")
    if query.error or not query.rows:
        raise RuntimeError("The chart preview has no usable query data.")
    query_service = QueryService(
        default_limit=settings.default_query_limit,
        max_limit=settings.max_query_limit,
        timeout_seconds=settings.ai_query_timeout_seconds,
    )
    safe_sql = query_service.prepare_sql(query.sql or "")
    validated_visualization = VisualizationService().validate(visualization, query)
    if validated_visualization.type == "none":
        raise RuntimeError("The chart preview visualization is invalid.")
    if validated_visualization.type != chart_plan.chart_type:
        raise RuntimeError("The chart preview type does not match the requested chart.")
    return chart_plan, safe_sql, validated_visualization


@router.post("/actions/execute", response_model=ActionExecutionResponse)
async def execute_action(request: ActionExecutionRequest) -> ActionExecutionResponse:
    if request.action not in {
        AIIntent.CREATE_CHART,
        AIIntent.CREATE_DASHBOARD,
        AIIntent.EDIT_CHART,
        AIIntent.EDIT_DASHBOARD,
    }:
        raise HTTPException(status_code=400, detail="Unsupported confirmed action.")

    target_dataset_id = None
    if request.chart_plan and request.chart_plan.dataset_id:
        target_dataset_id = request.chart_plan.dataset_id
    elif request.dashboard_plan and request.dashboard_plan.dataset_id:
        target_dataset_id = request.dashboard_plan.dataset_id
    elif request.dataset_id:
        target_dataset_id = request.dataset_id
    elif (
        request.edit_dashboard_plan
        and request.edit_dashboard_plan.create_chart_plan
        and request.edit_dashboard_plan.create_chart_plan.dataset_id
    ):
        target_dataset_id = request.edit_dashboard_plan.create_chart_plan.dataset_id
    else:
        target_dataset_id = settings.superset_taxi_dataset_id

    writer = SupersetWriteService(
        settings.superset_url,
        settings.superset_public_url,
        settings.superset_admin_username,
        settings.superset_admin_password,
        target_dataset_id,
        settings.frontend_origins,
    )

    if request.action == AIIntent.EDIT_CHART:
        if not request.edit_chart_plan:
            raise HTTPException(status_code=422, detail="An edit chart plan is required.")
        result = await writer.edit_chart(request.edit_chart_plan)
        return ActionExecutionResponse(
            success=result.success,
            action=AIIntent.EDIT_CHART,
            result=result if result.success else None,
            message=result.message,
            error=result.error,
        )

    if request.action == AIIntent.EDIT_DASHBOARD:
        if not request.edit_dashboard_plan:
            raise HTTPException(status_code=422, detail="An edit dashboard plan is required.")
        plan = request.edit_dashboard_plan
        prepared_new_chart = None
        if plan.operation == EditDashboardOperation.ADD_CHART and plan.create_chart_plan:
            try:
                prepared_new_chart = _prepared_chart_from_preview(
                    plan.create_chart_plan,
                    request.query,
                    request.visualization,
                )
            except (RuntimeError, SQLValidationError) as error:
                logger.warning(
                    "dashboard_add_chart_prepare_failed dashboard_id=%s error=%s",
                    plan.dashboard_id,
                    error,
                )
                return ActionExecutionResponse(
                    success=False,
                    action=AIIntent.EDIT_DASHBOARD,
                    message="Không thể chuẩn bị biểu đồ mới cho dashboard.",
                    error=str(error),
                )
        result = await writer.edit_dashboard(plan, prepared_new_chart)
        return ActionExecutionResponse(
            success=result.success,
            action=AIIntent.EDIT_DASHBOARD,
            result=result if result.success else None,
            message=result.message,
            error=result.error,
        )

    if request.action == AIIntent.CREATE_DASHBOARD:
        if not is_llm_enabled():
            raise HTTPException(
                status_code=503, detail="AI đã tắt trong Settings. Hãy bật lại để tạo dashboard."
            )
        if not request.dashboard_plan:
            raise HTTPException(status_code=422, detail="A dashboard plan is required.")
        if not 2 <= len(request.dashboard_plan.charts) <= 8:
            raise HTTPException(
                status_code=400, detail="Bảng điều khiển yêu cầu từ 2 đến 8 biểu đồ hợp lệ."
            )
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
            schema_service=SchemaService(superset_client()),
        )
        try:
            prepared_charts = await planner.prepare_dashboard_charts(request.dashboard_plan)
        except (RuntimeError, SQLValidationError) as error:
            logger.warning(
                "dashboard_prepare_failed title=%r error=%s", request.dashboard_plan.title, error
            )
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
        raise HTTPException(
            status_code=422, detail="A chart plan, query, and visualization are required."
        )

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
        raise HTTPException(
            status_code=400, detail="The pending chart query is not read-only."
        ) from error

    if request.query.error or not request.query.rows:
        raise HTTPException(status_code=400, detail="The pending chart has no usable query data.")
    validated_visualization = VisualizationService().validate(request.visualization, request.query)
    if validated_visualization.type == "none":
        raise HTTPException(status_code=400, detail="The pending chart visualization is invalid.")
    if validated_visualization.type != request.chart_plan.chart_type:
        raise HTTPException(
            status_code=400, detail="The chart plan and visualization type do not match."
        )

    result = await writer.create_chart(request.chart_plan, safe_sql, validated_visualization)
    return ActionExecutionResponse(
        success=result.success,
        action=AIIntent.CREATE_CHART,
        result=result if result.success else None,
        message=result.message,
        error=result.error,
    )


@router.post("/cache/clear")
def clear_cache() -> dict[str, str]:
    """Clears all query caches in Redis and memory."""
    cache_service.clear()
    return {"status": "success", "message": "Đã xóa toàn bộ Semantic Cache thành công."}
