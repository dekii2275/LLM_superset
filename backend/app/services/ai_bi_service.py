"""Explicit Gemini-to-MCP orchestration for the local, read-only BI demo."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from google.genai import types

from app.schemas.ai import (
    AIActionPlan,
    AIChatContext,
    AIChatResponse,
    AIIntent,
    AIToolCall,
    ChartPlan,
    DashboardPlan,
    EditChartOperation,
    EditChartPlan,
    EditDashboardOperation,
    EditDashboardPlan,
    IntentInfo,
    IntentResult,
    PendingAction,
    PendingDashboardAction,
    PendingEditChartAction,
    PendingEditDashboardAction,
    QueryResult,
    VisualizationSpec,
)
from app.services.gemini_service import GeminiService
from app.services.intent_service import IntentService
from app.services.mcp_service import MCPToolError, SupersetMCPService, jsonable
from app.services.query_service import QueryService, SQLValidationError
from app.services.visualization_service import VisualizationService

logger = logging.getLogger(__name__)

_SAFE_TOOL_NAMES = {"health_check", "get_instance_info", "search_tools", "call_tool"}
MAX_TOOL_TURNS = 16


class AIBIService:
    def __init__(
        self,
        mcp: SupersetMCPService,
        gemini: GeminiService,
        query_service: QueryService,
        visualization_service: VisualizationService | None = None,
        asset_resolver: Any | None = None,
    ) -> None:
        self.mcp = mcp
        self.gemini = gemini
        self.query_service = query_service
        self.visualization_service = visualization_service or VisualizationService()
        self.asset_resolver = asset_resolver

    async def chat(
        self, message: str, context: AIChatContext | None = None
    ) -> AIChatResponse:
        intent_result = await IntentService(self.gemini).classify(message, context)
        logger.info(
            "ai_intent=%s confidence=%s target_type=%s target_id=%s target_name=%r",
            intent_result.intent.value,
            intent_result.confidence,
            intent_result.target_type,
            intent_result.target_id,
            intent_result.target_name,
        )
        intent = IntentInfo(type=intent_result.intent, confidence=intent_result.confidence)
        if intent_result.intent == AIIntent.ASK_DATA:
            logger.info("ai_intent_route=nl2sql")
            # Preserve the established NL2SQL flow. If planning fails we use
            # the existing metadata flow rather than failing due to the router.
            try:
                plan = await self.gemini.generate_sql(message)
            except Exception:
                logger.exception("nl2sql_planning_failed_after_intent_route")
                response = await self._chat_with_mcp(message)
                response.intent = intent
                return response
            if plan.intent.lower() == "data_query" and plan.sql.strip():
                response = await self._answer_data_question(message, plan.sql)
                response.intent = intent
                return response
            response = await self._chat_with_mcp(message)
            response.intent = intent
            return response
        if intent_result.intent == AIIntent.GENERAL:
            logger.info("ai_intent_route=metadata_mcp")
            response = await self._chat_with_mcp(message)
            response.intent = intent
            return response

        if intent_result.intent == AIIntent.CREATE_CHART:
            logger.info("ai_intent_route=create_chart_preview")
            return await self._prepare_create_chart(message, context, intent)

        if intent_result.intent == AIIntent.CREATE_DASHBOARD:
            logger.info("ai_intent_route=create_dashboard_preview")
            return await self._prepare_create_dashboard(message, intent)

        if intent_result.intent == AIIntent.EDIT_CHART:
            logger.info("ai_intent_route=edit_chart_preview")
            return await self._prepare_edit_chart(message, intent_result, intent)

        if intent_result.intent == AIIntent.EDIT_DASHBOARD:
            logger.info("ai_intent_route=edit_dashboard_preview")
            return await self._prepare_edit_dashboard(message, intent_result, intent)

        logger.info("ai_intent_route=action_plan")
        action_plan = self._action_plan(intent_result, message)
        return AIChatResponse(
            answer=self._action_answer(action_plan),
            intent=intent,
            action_plan=action_plan,
        )

    async def _prepare_edit_chart(
        self, message: str, intent_result: IntentResult, intent: IntentInfo
    ) -> AIChatResponse:
        if self._unsupported_chart_type(message):
            return AIChatResponse(answer="Loại biểu đồ này chưa được hỗ trợ trong bản demo. Chỉ hỗ trợ bar, line hoặc pie.", intent=intent)
        try:
            plan = await self.gemini.generate_edit_chart_plan(message)
            plan.chart_id = intent_result.target_id or plan.chart_id
            plan.chart_name = intent_result.target_name or plan.chart_name
            plan = await self._resolve_edit_chart_target(plan)
        except (ValueError, RuntimeError) as error:
            return AIChatResponse(answer=str(error), intent=intent)
        except Exception:
            logger.exception("edit_chart_planning_failed")
            return AIChatResponse(answer="Chưa thể chuẩn bị thay đổi biểu đồ. Hãy thử mô tả rõ hơn.", intent=intent)
        return AIChatResponse(
            answer=self._edit_chart_answer(plan), intent=intent, edit_chart_plan=plan,
            pending_action=PendingEditChartAction(edit_chart_plan=plan),
        )

    async def _prepare_edit_dashboard(
        self, message: str, intent_result: IntentResult, intent: IntentInfo
    ) -> AIChatResponse:
        try:
            plan = await self.gemini.generate_edit_dashboard_plan(message)
            plan.dashboard_id = intent_result.target_id or plan.dashboard_id
            plan.dashboard_name = intent_result.target_name or plan.dashboard_name
            if plan.operation == EditDashboardOperation.ADD_CHART and not plan.chart_id and not plan.chart_name and not plan.create_chart_plan:
                plan.create_chart_plan = await self.gemini.generate_chart_plan(message)
            plan = await self._resolve_edit_dashboard_target(plan)
        except (ValueError, RuntimeError) as error:
            return AIChatResponse(answer=str(error), intent=intent)
        except Exception:
            logger.exception("edit_dashboard_planning_failed")
            return AIChatResponse(answer="Chưa thể chuẩn bị thay đổi dashboard. Hãy thử mô tả rõ hơn.", intent=intent)
        return AIChatResponse(
            answer=self._edit_dashboard_answer(plan), intent=intent, edit_dashboard_plan=plan,
            pending_action=PendingEditDashboardAction(edit_dashboard_plan=plan),
        )

    async def _resolve_edit_chart_target(self, plan: EditChartPlan) -> EditChartPlan:
        if not self.asset_resolver:
            if not plan.chart_id and not plan.chart_name:
                raise ValueError("Hãy chọn biểu đồ cần cập nhật.")
            return plan
        resolved = await self.asset_resolver.resolve_chart(plan.chart_id, plan.chart_name)
        plan.chart_id, plan.chart_name = int(resolved["id"]), str(resolved.get("slice_name") or plan.chart_name)
        return plan

    async def _resolve_edit_dashboard_target(self, plan: EditDashboardPlan) -> EditDashboardPlan:
        if not self.asset_resolver:
            if not plan.dashboard_id and not plan.dashboard_name:
                raise ValueError("Hãy chọn dashboard cần cập nhật.")
            return plan
        resolved = await self.asset_resolver.resolve_dashboard(plan.dashboard_id, plan.dashboard_name)
        plan.dashboard_id, plan.dashboard_name = int(resolved["id"]), str(resolved.get("dashboard_title") or plan.dashboard_name)
        if plan.operation in {EditDashboardOperation.ADD_CHART, EditDashboardOperation.REMOVE_CHART} and not plan.create_chart_plan:
            if not plan.chart_id and not plan.chart_name:
                raise ValueError("Hãy nêu biểu đồ cần thêm hoặc gỡ.")
            chart = await self.asset_resolver.resolve_chart(plan.chart_id, plan.chart_name)
            plan.chart_id, plan.chart_name = int(chart["id"]), str(chart.get("slice_name") or plan.chart_name)
        return plan

    @staticmethod
    def _unsupported_chart_type(message: str) -> bool:
        lowered = message.casefold()
        return any(token in lowered for token in ("scatter", "heatmap", "box plot", "histogram"))

    @staticmethod
    def _edit_chart_answer(plan: EditChartPlan) -> str:
        target = plan.chart_name or f"chart {plan.chart_id}"
        detail = {EditChartOperation.CHANGE_CHART_TYPE: f"đổi thành {plan.new_chart_type}", EditChartOperation.RENAME_CHART: f"đổi tên thành {plan.new_title}", EditChartOperation.CHANGE_METRIC: f"đổi metric thành {plan.new_metric}", EditChartOperation.CHANGE_DIMENSION: f"đổi dimension thành {plan.new_dimension}"}[plan.operation]
        return f"Tôi sẽ {detail} cho {target}. Xác nhận để cập nhật trong Superset."

    @staticmethod
    def _edit_dashboard_answer(plan: EditDashboardPlan) -> str:
        target = plan.dashboard_name or f"dashboard {plan.dashboard_id}"
        if plan.operation == EditDashboardOperation.RENAME_DASHBOARD:
            detail = f"đổi tên thành {plan.new_title}"
        elif plan.operation == EditDashboardOperation.REMOVE_CHART:
            detail = f"gỡ {plan.chart_name or 'biểu đồ'} (không xóa chart đã lưu)"
        else:
            detail = f"thêm {plan.create_chart_plan.title if plan.create_chart_plan else plan.chart_name or 'biểu đồ'}"
        return f"Tôi sẽ {detail} trong {target}. Xác nhận để cập nhật trong Superset."

    async def _prepare_create_dashboard(
        self, message: str, intent: IntentInfo
    ) -> AIChatResponse:
        try:
            dashboard_plan = await self.gemini.generate_dashboard_plan(message)
        except Exception:
            logger.exception("create_dashboard_planning_failed")
            return AIChatResponse(
                answer="Chưa thể chuẩn bị dashboard. Hãy thử mô tả mục tiêu dashboard rõ hơn.",
                intent=intent,
            )
        # DashboardPlan performs the 3–4 chart bound at validation time. Keep
        # this guard explicit for future model/schema changes and clear logs.
        if not 3 <= len(dashboard_plan.charts) <= 4:
            logger.warning("dashboard_plan_invalid_chart_count count=%s", len(dashboard_plan.charts))
            return AIChatResponse(
                answer="Dashboard demo cần từ 3 đến 4 biểu đồ hợp lệ.", intent=intent
            )
        return AIChatResponse(
            answer=(
                f"Tôi đã chuẩn bị dashboard {dashboard_plan.title} với "
                f"{len(dashboard_plan.charts)} biểu đồ. Xác nhận để tạo trong Superset."
            ),
            intent=intent,
            dashboard_plan=dashboard_plan,
            pending_action=PendingDashboardAction(dashboard_plan=dashboard_plan),
        )

    async def _prepare_create_chart(
        self, message: str, context: AIChatContext | None, intent: IntentInfo
    ) -> AIChatResponse:
        if self._is_save_visualization_request(message):
            reused = self._reuse_chart_context(context)
            if reused is None:
                return AIChatResponse(
                    answer="Không tìm thấy biểu đồ gần nhất để lưu.", intent=intent
                )
            chart_plan, query, visualization = reused
        else:
            try:
                chart_plan = await self.gemini.generate_chart_plan(message)
                sql_plan = await self.gemini.generate_sql(chart_plan.question)
            except Exception:
                logger.exception("create_chart_planning_failed")
                return AIChatResponse(
                    answer="Chưa thể chuẩn bị biểu đồ. Hãy thử mô tả dữ liệu cần hiển thị rõ hơn.",
                    intent=intent,
                )
            if sql_plan.intent.lower() != "data_query" or not sql_plan.sql.strip():
                return AIChatResponse(
                    answer="Chưa thể tạo truy vấn dữ liệu cho biểu đồ này.", intent=intent
                )
            data_response = await self._answer_data_question(chart_plan.question, sql_plan.sql)
            query = data_response.query
            if query is None or query.error:
                data_response.intent = intent
                data_response.answer = "Chưa thể lấy dữ liệu để tạo biểu đồ."
                return data_response
            if not query.rows:
                return AIChatResponse(
                    answer="Không có dữ liệu để tạo biểu đồ.", intent=intent, query=query
                )
            visualization = self._chart_visualization(chart_plan, query, data_response.visualization)
            if visualization.type == "none":
                return AIChatResponse(
                    answer="Kết quả hiện tại không phù hợp để tạo biểu đồ an toàn.",
                    intent=intent,
                    query=query,
                )

        if not query.sql or query.error or not query.rows:
            return AIChatResponse(
                answer="Không có dữ liệu hợp lệ để tạo biểu đồ.",
                intent=intent,
                query=query,
                visualization=visualization,
            )
        return AIChatResponse(
            answer=f"Tôi đã chuẩn bị biểu đồ {chart_plan.title}. Xác nhận để tạo chart trong Superset.",
            intent=intent,
            query=query,
            visualization=visualization,
            pending_action=PendingAction(
                chart_plan=chart_plan,
                query_sql=query.sql,
            ),
        )

    async def prepare_dashboard_charts(
        self, dashboard_plan: DashboardPlan
    ) -> list[tuple[ChartPlan, str, VisualizationSpec]]:
        """Prepare every planned chart with the established Task 1/2/4 flow.

        This runs before the confirmation write service is called. A failure
        stops the dashboard immediately, so it never receives a broken chart.
        """
        prepared: list[tuple[ChartPlan, str, VisualizationSpec]] = []
        for chart_plan in dashboard_plan.charts:
            prepared.append(await self.prepare_chart_for_write(chart_plan))
        return prepared

    async def prepare_chart_for_write(
        self, chart_plan: ChartPlan
    ) -> tuple[ChartPlan, str, VisualizationSpec]:
        """Shared Task 4 preparation used by dashboard add-new-chart as well."""
        try:
            sql_plan = await self.gemini.generate_sql(chart_plan.question)
        except Exception as error:
            raise RuntimeError(f"Could not generate SQL for {chart_plan.title}.") from error
        if sql_plan.intent.lower() != "data_query" or not sql_plan.sql.strip():
            raise RuntimeError(f"Could not prepare a data query for {chart_plan.title}.")
        response = await self._answer_data_question(chart_plan.question, sql_plan.sql)
        query = response.query
        if query is None or query.error:
            raise RuntimeError(f"Could not retrieve data for {chart_plan.title}.")
        if not query.rows:
            raise RuntimeError(f"No data was returned for {chart_plan.title}.")
        visualization = self._chart_visualization(chart_plan, query, response.visualization)
        if visualization.type == "none":
            raise RuntimeError(f"The result for {chart_plan.title} cannot be charted safely.")
        return chart_plan, self.query_service.prepare_sql(query.sql or ""), visualization

    @staticmethod
    def _is_save_visualization_request(message: str) -> bool:
        normalized = message.casefold()
        return "save" in normalized or "lưu" in normalized

    def _reuse_chart_context(
        self, context: AIChatContext | None
    ) -> tuple[ChartPlan, QueryResult, VisualizationSpec] | None:
        if not context or not context.last_query or not context.last_visualization:
            return None
        try:
            query = QueryResult.model_validate(context.last_query)
            visualization = VisualizationSpec.model_validate(context.last_visualization)
        except Exception:
            logger.warning("create_chart_save_context_invalid")
            return None
        if not query.sql or query.error or not query.rows or visualization.type == "none":
            return None
        if self.visualization_service.validate(visualization, query).type == "none":
            return None
        return (
            ChartPlan(
                title=visualization.title or "Saved chart",
                chart_type=visualization.type,
                question="Save the current visualization",
                metric=visualization.y_axis,
                dimension=visualization.x_axis,
                limit=query.row_count if query.row_count <= 500 else None,
            ),
            query,
            visualization,
        )

    def _chart_visualization(
        self, chart_plan: ChartPlan, query: QueryResult, existing: VisualizationSpec | None
    ) -> VisualizationSpec:
        baseline = existing or self.visualization_service.heuristic(query)
        x_axis = chart_plan.dimension if chart_plan.dimension in query.columns else baseline.x_axis
        y_axis = chart_plan.metric if chart_plan.metric in query.columns else baseline.y_axis
        candidate = VisualizationSpec(
            type=chart_plan.chart_type,
            title=chart_plan.title,
            x_axis=x_axis,
            y_axis=y_axis,
            x_label=(x_axis or "").replace("_", " ").title() or None,
            y_label=(y_axis or "").replace("_", " ").title() or None,
        )
        return self.visualization_service.validate(candidate, query)

    @staticmethod
    def _action_plan(intent: IntentResult, message: str) -> AIActionPlan:
        labels = {
            AIIntent.CREATE_CHART: "Create chart",
            AIIntent.CREATE_DASHBOARD: "Create dashboard",
            AIIntent.EDIT_CHART: "Edit chart",
            AIIntent.EDIT_DASHBOARD: "Edit dashboard",
        }
        parameters: dict[str, Any] = {"request": message.strip()}
        if intent.operation:
            parameters["operation"] = intent.operation
        lowered = message.casefold()
        if intent.intent in {AIIntent.CREATE_CHART, AIIntent.EDIT_CHART}:
            for chart_type in ("bar", "line", "pie", "area"):
                if chart_type in lowered or (chart_type == "bar" and "cột" in lowered):
                    parameters["preferred_chart_type" if intent.intent == AIIntent.CREATE_CHART else "chart_type"] = chart_type
                    parameters.setdefault("operation", "change_chart_type")
                    break
        if intent.intent == AIIntent.EDIT_DASHBOARD:
            parameters.setdefault("operation", "add_chart" if "add" in lowered or "thêm" in lowered else "edit_dashboard")
        if intent.intent == AIIntent.EDIT_CHART:
            parameters.setdefault("operation", "edit_chart")
        title = intent.target_name or labels[intent.intent]
        return AIActionPlan(
            action=intent.intent,
            title=title,
            description=intent.user_goal or message.strip(),
            target_type=intent.target_type,
            target_id=intent.target_id,
            target_name=intent.target_name,
            parameters=parameters,
            requires_confirmation=True,
        )

    @staticmethod
    def _action_answer(action_plan: AIActionPlan) -> str:
        return (
            f"Action preview ready: {action_plan.title}. "
            "No Superset changes have been made; this will be available for confirmation in a later step."
        )

    async def _answer_data_question(self, message: str, sql: str) -> AIChatResponse:
        for retry_count in range(2):
            try:
                result = await self.query_service.execute_query(sql)
            except SQLValidationError:
                logger.warning("nl2sql_validation_rejected question=%r retry=%s", message, retry_count)
                return AIChatResponse(
                    answer="Không thể thực hiện truy vấn này vì SQL không đáp ứng chính sách chỉ đọc.",
                    query=QueryResult(sql=sql, error="SQL rejected by the read-only policy"),
                )

            logger.info(
                "nl2sql question=%r sql=%s row_count=%s execution_time_ms=%s retry=%s error=%s",
                message,
                result.sql,
                result.row_count,
                result.execution_time_ms,
                retry_count,
                bool(result.error),
            )
            if not result.error:
                try:
                    answer = await self.gemini.generate_answer_from_result(message, result)
                except Exception:
                    logger.exception("nl2sql_answer_generation_failed")
                    answer = (
                        "Không tìm thấy dữ liệu phù hợp với điều kiện này."
                        if result.row_count == 0
                        else f"Truy vấn trả về {result.row_count} dòng dữ liệu."
                    )
                visualization = await self._visualization(message, result)
                return AIChatResponse(answer=answer, query=result, visualization=visualization)

            if retry_count == 0:
                try:
                    repaired = await self.gemini.repair_sql(message, sql, result.error)
                    if repaired.intent.lower() == "data_query" and repaired.sql.strip():
                        sql = repaired.sql
                        continue
                except Exception:
                    logger.exception("nl2sql_repair_generation_failed")
            if result.error == "Query timed out":
                answer = "Truy vấn mất quá nhiều thời gian. Hãy thử câu hỏi cụ thể hơn."
            else:
                answer = "Tôi chưa thể tạo truy vấn phù hợp cho câu hỏi này."
            return AIChatResponse(answer=answer, query=result)

        raise RuntimeError("NL2SQL retry loop ended unexpectedly")

    async def _visualization(self, message: str, result: QueryResult) -> VisualizationSpec:
        try:
            return await self.visualization_service.plan(message, result, self.gemini)
        except Exception:
            logger.exception("visualization_planning_failed")
            return VisualizationSpec()

    async def _chat_with_mcp(self, message: str) -> AIChatResponse:
        request_id = uuid.uuid4().hex
        available_tools = await self.mcp.list_tools()
        declarations = self._function_declarations(available_tools)
        if not declarations:
            raise MCPToolError("Superset MCP did not expose any safe discovery tools")

        tools = [types.Tool(function_declarations=declarations)]
        contents: list[Any] = [types.Content(role="user", parts=[types.Part.from_text(text=message)])]
        tool_calls: list[AIToolCall] = []

        # Explicit orchestration keeps policy enforcement in FastAPI rather
        # than granting an experimental SDK MCP bridge unrestricted access.
        # A write flow needs several grounded discovery turns (dataset, chart
        # type schema, then create) before the final MCP mutation. Keep a hard
        # cap so a malformed model response cannot loop indefinitely.
        for _ in range(MAX_TOOL_TURNS):
            response = await self.gemini.generate(contents, tools)
            function_calls = response.function_calls or []
            if not function_calls:
                answer = (response.text or "Gemini returned no answer.").strip()
                return AIChatResponse(answer=answer, tool_calls=tool_calls)

            candidate = response.candidates[0].content if response.candidates else None
            if candidate is None:
                raise RuntimeError("Gemini returned a tool call without response content")
            contents.append(candidate)
            response_parts: list[types.Part] = []
            for call in function_calls:
                started = time.monotonic()
                arguments = dict(call.args or {})
                try:
                    result = await self.mcp.call_tool(call.name, arguments)
                    summary = self._summary(result)
                    status = "success"
                    tool_response: dict[str, Any] = {"result": result}
                except MCPToolError as error:
                    summary = str(error)
                    status = "blocked" if "read-only policy" in summary else "error"
                    tool_response = {"error": summary}
                duration_ms = round((time.monotonic() - started) * 1000)
                logger.info(
                    "ai_request_id=%s model=%s mcp_tool=%s status=%s duration_ms=%s",
                    request_id,
                    self.gemini.model,
                    call.name,
                    status,
                    duration_ms,
                )
                tool_calls.append(AIToolCall(tool=call.name, status=status, summary=summary))
                response_parts.append(
                    types.Part.from_function_response(name=call.name, response=tool_response)
                )
            # Gemini 3.x Generate Content accepts function responses as user
            # content (its supported roles do not include the legacy "tool").
            contents.append(types.Content(role="user", parts=response_parts))

        return AIChatResponse(
            answer="I could not complete the request within the permitted tool-call limit.",
            tool_calls=tool_calls,
        )

    @staticmethod
    def _function_declarations(mcp_tools: list[dict[str, Any]]) -> list[types.FunctionDeclaration]:
        declarations: list[types.FunctionDeclaration] = []
        for tool in mcp_tools:
            name = str(tool.get("name", ""))
            if name not in _SAFE_TOOL_NAMES:
                continue
            schema = tool.get("inputSchema") or tool.get("input_schema") or {"type": "object"}
            declarations.append(
                types.FunctionDeclaration(
                    name=name,
                    description=str(tool.get("description", "")),
                    parameters_json_schema=jsonable(schema),
                )
            )
        return declarations

    @staticmethod
    def _summary(result: dict[str, Any]) -> str:
        text = json.dumps(result, ensure_ascii=False, default=str)
        return text[:500] + ("…" if len(text) > 500 else "")
