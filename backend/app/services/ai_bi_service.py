"""Explicit Gemini-to-MCP orchestration for the local, read-only BI demo."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any

from google.genai import types
from pydantic import ValidationError

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
    SQLGenerationResult,
    VisualizationSpec,
)
from app.services.gemini_service import GeminiService
from app.services.intent_service import IntentService
from app.services.mcp_service import MCPToolError, SupersetMCPService, jsonable
from app.services.query_service import QueryService, SQLValidationError
from app.services.schema_service import DatasetSchemaUnavailableError, SchemaService
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
        schema_service: SchemaService | None = None,
    ) -> None:
        self.mcp = mcp
        self.gemini = gemini
        self.query_service = query_service
        self.visualization_service = visualization_service or VisualizationService()
        self.asset_resolver = asset_resolver
        self.schema_service = schema_service

    async def chat(
        self,
        message: str,
        context: AIChatContext | None = None,
        dataset_id: int | None = None,
        user: dict[str, Any] | None = None,
    ) -> AIChatResponse:
        from app.services.rls_service import RLSService

        active_dataset_id = dataset_id or 1
        rls_info = RLSService.get_filter_for_user(user, active_dataset_id)
        rls_filter = rls_info["filter_clause"] if rls_info else None

        try:
            schema_context = (
                self.schema_service.build_schema_prompt(dataset_id) if self.schema_service else None
            )
        except DatasetSchemaUnavailableError:
            return AIChatResponse(
                answer="Không thể đọc cấu trúc của bộ dữ liệu đang chọn. Hãy kiểm tra kết nối Superset rồi thử lại."
            )
        if rls_info:
            rls_prompt = RLSService.get_rls_prompt_context(user, active_dataset_id)
            if rls_prompt:
                schema_context = (schema_context or "") + "\n" + rls_prompt

        if context and context.pending_dashboard_plan and self._is_dashboard_refinement(message):
            return await self._refine_pending_dashboard(
                message, context.pending_dashboard_plan, dataset_id, schema_context
            )

        intent_result = await IntentService(self.gemini).classify(message, context)
        logger.info(
            "ai_intent=%s confidence=%s target_type=%s target_id=%s target_name=%r dataset_id=%s rls_active=%s",
            intent_result.intent.value,
            intent_result.confidence,
            intent_result.target_type,
            intent_result.target_id,
            intent_result.target_name,
            dataset_id,
            bool(rls_info),
        )
        intent = IntentInfo(type=intent_result.intent, confidence=intent_result.confidence)

        last_sql: str | None = None
        if context and context.last_query:
            if isinstance(context.last_query, dict):
                last_sql = context.last_query.get("sql")
            elif isinstance(context.last_query, str):
                last_sql = context.last_query

        conversation_history: list[dict[str, str]] | None = None
        if context and context.conversation_history:
            conversation_history = context.conversation_history
        elif context and context.session_id:
            try:
                from app.services.chat_persistence_service import ChatPersistenceService

                conversation_history = ChatPersistenceService.get_recent_history(context.session_id)
            except Exception:
                pass

        if intent_result.intent == AIIntent.ASK_DATA:
            logger.info("ai_intent_route=nl2sql")
            # Preserve the established NL2SQL flow. If planning fails we use
            # the existing metadata flow rather than failing due to the router.
            try:
                try:
                    plan = await self.gemini.generate_sql(
                        message,
                        schema_context=schema_context,
                        last_sql=last_sql,
                        conversation_history=conversation_history,
                    )
                except TypeError:
                    plan = await self.gemini.generate_sql(message, schema_context=schema_context)
            except Exception:
                logger.exception("nl2sql_planning_failed_after_intent_route")
                response = await self._chat_with_mcp(message)
                response.intent = intent
                return response
            if plan.intent.lower() == "data_query" and plan.sql.strip():
                effective_sql = plan.sql
                if rls_filter:
                    effective_sql = RLSService.rewrite_sql(effective_sql, rls_filter)
                response = await self._answer_data_question(
                    message, effective_sql, schema_context=schema_context, rls_info=rls_info
                )
                response.intent = intent
                if rls_info:
                    response.applied_rls_filter = rls_info.get("description")
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
            return await self._prepare_create_chart(
                message, context, intent, dataset_id=dataset_id, schema_context=schema_context
            )

        if intent_result.intent == AIIntent.CREATE_DASHBOARD:
            logger.info("ai_intent_route=create_dashboard_preview")
            return await self._prepare_create_dashboard(
                message, intent, dataset_id=dataset_id, schema_context=schema_context
            )

        if intent_result.intent == AIIntent.EDIT_CHART:
            logger.info("ai_intent_route=edit_chart_preview")
            return await self._prepare_edit_chart(message, intent_result, intent)

        if intent_result.intent == AIIntent.EDIT_DASHBOARD:
            logger.info("ai_intent_route=edit_dashboard_preview")
            return await self._prepare_edit_dashboard(
                message, intent_result, intent, dataset_id=dataset_id, schema_context=schema_context
            )

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
            return AIChatResponse(
                answer="Loại biểu đồ này chưa được hỗ trợ trong bản demo. Chỉ hỗ trợ bar, line hoặc pie.",
                intent=intent,
            )
        try:
            plan = await self.gemini.generate_edit_chart_plan(message)
            plan.chart_id = intent_result.target_id or plan.chart_id
            plan.chart_name = intent_result.target_name or plan.chart_name
            plan = await self._resolve_edit_chart_target(plan)
        except (ValueError, RuntimeError) as error:
            return AIChatResponse(answer=str(error), intent=intent)
        except Exception:
            logger.exception("edit_chart_planning_failed")
            return AIChatResponse(
                answer="Chưa thể chuẩn bị thay đổi biểu đồ. Hãy thử mô tả rõ hơn.", intent=intent
            )
        return AIChatResponse(
            answer=self._edit_chart_answer(plan),
            intent=intent,
            edit_chart_plan=plan,
            pending_action=PendingEditChartAction(edit_chart_plan=plan),
        )

    async def _prepare_edit_dashboard(
        self,
        message: str,
        intent_result: IntentResult,
        intent: IntentInfo,
        dataset_id: int | None = None,
        schema_context: str | None = None,
    ) -> AIChatResponse:
        try:
            try:
                plan = await self.gemini.generate_edit_dashboard_plan(
                    message, schema_context=schema_context
                )
            except TypeError:
                plan = await self.gemini.generate_edit_dashboard_plan(message)
            plan.dashboard_id = intent_result.target_id or plan.dashboard_id
            plan.dashboard_name = intent_result.target_name or plan.dashboard_name
            if (
                plan.operation == EditDashboardOperation.ADD_CHART
                and not plan.chart_id
                and not plan.chart_name
                and not plan.create_chart_plan
            ):
                try:
                    plan.create_chart_plan = await self.gemini.generate_chart_plan(
                        message, schema_context=schema_context
                    )
                except TypeError:
                    plan.create_chart_plan = await self.gemini.generate_chart_plan(message)
            if plan.create_chart_plan and dataset_id is not None:
                plan.create_chart_plan.dataset_id = dataset_id
            plan = await self._resolve_edit_dashboard_target(plan)
        except (ValueError, RuntimeError) as error:
            return AIChatResponse(answer=str(error), intent=intent)
        except Exception:
            logger.exception("edit_dashboard_planning_failed")
            return AIChatResponse(
                answer="Chưa thể chuẩn bị thay đổi dashboard. Hãy thử mô tả rõ hơn.", intent=intent
            )
        query: QueryResult | None = None
        visualization: VisualizationSpec | None = None
        # A new dashboard chart is not yet visible in Superset. Run only its
        # read-only query now, so confirmation is based on the actual chart.
        if plan.operation == EditDashboardOperation.ADD_CHART and plan.create_chart_plan:
            try:
                query, visualization = await self.prepare_chart_preview(
                    plan.create_chart_plan, schema_context=schema_context
                )
            except (RuntimeError, SQLValidationError) as error:
                logger.warning(
                    "dashboard_add_chart_preview_failed dashboard_id=%s chart=%r error=%s",
                    plan.dashboard_id,
                    plan.create_chart_plan.title,
                    error,
                )
                return AIChatResponse(
                    answer=f"Chưa thể tạo preview cho biểu đồ {plan.create_chart_plan.title}. {error}",
                    intent=intent,
                )
        return AIChatResponse(
            answer=self._edit_dashboard_answer(plan),
            intent=intent,
            edit_dashboard_plan=plan,
            pending_action=PendingEditDashboardAction(edit_dashboard_plan=plan),
            query=query,
            visualization=visualization,
        )

    async def _resolve_edit_chart_target(self, plan: EditChartPlan) -> EditChartPlan:
        if not self.asset_resolver:
            if not plan.chart_id and not plan.chart_name:
                raise ValueError("Hãy chọn biểu đồ cần cập nhật.")
            return plan
        resolved = await self.asset_resolver.resolve_chart(plan.chart_id, plan.chart_name)
        plan.chart_id, plan.chart_name = (
            int(resolved["id"]),
            str(resolved.get("slice_name") or plan.chart_name),
        )
        return plan

    async def _resolve_edit_dashboard_target(self, plan: EditDashboardPlan) -> EditDashboardPlan:
        if not self.asset_resolver:
            if not plan.dashboard_id and not plan.dashboard_name:
                raise ValueError("Hãy chọn dashboard cần cập nhật.")
            return plan
        resolved = await self.asset_resolver.resolve_dashboard(
            plan.dashboard_id, plan.dashboard_name
        )
        plan.dashboard_id, plan.dashboard_name = (
            int(resolved["id"]),
            str(resolved.get("dashboard_title") or plan.dashboard_name),
        )
        if (
            plan.operation
            in {EditDashboardOperation.ADD_CHART, EditDashboardOperation.REMOVE_CHART}
            and not plan.create_chart_plan
        ):
            if not plan.chart_id and not plan.chart_name:
                raise ValueError("Hãy nêu biểu đồ cần thêm hoặc gỡ.")
            chart = await self.asset_resolver.resolve_chart(plan.chart_id, plan.chart_name)
            plan.chart_id, plan.chart_name = (
                int(chart["id"]),
                str(chart.get("slice_name") or plan.chart_name),
            )
        return plan

    @staticmethod
    def _unsupported_chart_type(message: str) -> bool:
        lowered = message.casefold()
        return any(token in lowered for token in ("scatter", "heatmap", "box plot", "histogram"))

    @staticmethod
    def _edit_chart_answer(plan: EditChartPlan) -> str:
        target = plan.chart_name or f"chart {plan.chart_id}"
        detail = {
            EditChartOperation.CHANGE_CHART_TYPE: f"đổi thành {plan.new_chart_type}",
            EditChartOperation.RENAME_CHART: f"đổi tên thành {plan.new_title}",
            EditChartOperation.CHANGE_METRIC: f"đổi metric thành {plan.new_metric}",
            EditChartOperation.CHANGE_DIMENSION: f"đổi dimension thành {plan.new_dimension}",
        }[plan.operation]
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

    @staticmethod
    def _requests_heatmap(message: str) -> bool:
        lowered = message.casefold()
        return any(term in lowered for term in ("heatmap", "biểu đồ nhiệt", "bieu do nhiet"))

    @classmethod
    def _is_dashboard_refinement(cls, message: str) -> bool:
        lowered = message.casefold()
        return cls._requests_heatmap(message) and any(
            term in lowered
            for term in ("thêm", "phải có", "cần có", "bổ sung", "thiếu", "add", "include")
        )

    async def _plan_heatmap_chart(
        self, message: str, dataset_id: int | None, schema_context: str | None
    ) -> ChartPlan:
        dataset = (
            self.schema_service.get_dataset(dataset_id)
            if self.schema_service and dataset_id
            else None
        )
        columns = {
            str(column.get("column_name"))
            for column in (dataset or {}).get("columns", [])
            if isinstance(column, dict) and column.get("column_name")
        }
        if {"country", "is_megacity"}.issubset(columns):
            return ChartPlan(
                title="Số Thành Phố Theo Quốc Gia Và Siêu Đô Thị",
                chart_type="heatmap",
                question=(
                    "Đếm số thành phố theo country và is_megacity. Trả về country, "
                    "is_megacity và COUNT(*) AS city_count, sắp xếp theo city_count "
                    "giảm dần, giới hạn 30 nhóm."
                ),
                metric="city_count",
                dimension="country",
                secondary_dimension="is_megacity",
                limit=30,
                dataset_id=dataset_id,
            )
        instruction = (
            f"Tạo biểu đồ nhiệt (heatmap) cho dashboard từ yêu cầu: {message}. "
            "Chọn hai cột phân loại khác nhau từ schema làm dimension và "
            "secondary_dimension, cùng một metric tổng hợp số. "
            "Đặt chart_type=heatmap và viết question nêu rõ cả hai chiều."
        )
        try:
            chart = await self.gemini.generate_chart_plan(
                instruction, schema_context=schema_context
            )
        except TypeError:
            chart = await self.gemini.generate_chart_plan(instruction)
        chart.chart_type = "heatmap"
        chart.dataset_id = dataset_id
        if (
            not chart.dimension
            or not chart.secondary_dimension
            or chart.dimension == chart.secondary_dimension
        ):
            raise ValueError("Biểu đồ nhiệt cần hai chiều dữ liệu khác nhau trong dataset.")
        return chart

    async def _refine_pending_dashboard(
        self,
        message: str,
        pending_plan: dict[str, Any],
        dataset_id: int | None,
        schema_context: str | None,
    ) -> AIChatResponse:
        intent = IntentInfo(type=AIIntent.CREATE_DASHBOARD)
        try:
            plan = DashboardPlan.model_validate(pending_plan)
        except Exception:
            return AIChatResponse(
                answer="Bản nháp dashboard không hợp lệ. Hãy yêu cầu tạo lại dashboard.",
                intent=intent,
            )
        if dataset_id and plan.dataset_id and dataset_id != plan.dataset_id:
            return AIChatResponse(
                answer="Bản nháp dashboard thuộc bộ dữ liệu khác. Hãy chọn đúng dataset.",
                intent=intent,
            )
        if any(chart.chart_type == "heatmap" for chart in plan.charts):
            return AIChatResponse(
                answer=f"Bản nháp dashboard {plan.title} đã có biểu đồ nhiệt.",
                intent=intent,
                dashboard_plan=plan,
                pending_action=PendingDashboardAction(dashboard_plan=plan),
            )
        if len(plan.charts) >= 8:
            return AIChatResponse(
                answer="Dashboard đã có 8 biểu đồ; hãy chọn một biểu đồ cần thay thế.",
                intent=intent,
            )
        try:
            chart = await self._plan_heatmap_chart(
                message, dataset_id or plan.dataset_id, schema_context
            )
        except Exception:
            logger.exception("dashboard_heatmap_planning_failed")
            return AIChatResponse(
                answer="Chưa thể lập biểu đồ nhiệt từ các cột dữ liệu hiện có.", intent=intent
            )
        plan.charts.append(chart)
        return AIChatResponse(
            answer=(
                f"Tôi đã bổ sung biểu đồ nhiệt vào bản nháp {plan.title}. "
                f"Dashboard hiện có {len(plan.charts)} biểu đồ. Xác nhận bản nháp mới để tạo trong Superset."
            ),
            intent=intent,
            dashboard_plan=plan,
            pending_action=PendingDashboardAction(dashboard_plan=plan),
        )

    async def _prepare_create_dashboard(
        self,
        message: str,
        intent: IntentInfo,
        dataset_id: int | None = None,
        schema_context: str | None = None,
    ) -> AIChatResponse:
        try:
            try:
                dashboard_plan = await self.gemini.generate_dashboard_plan(
                    message, schema_context=schema_context
                )
            except TypeError:
                dashboard_plan = await self.gemini.generate_dashboard_plan(message)
            dashboard_plan.dataset_id = dataset_id
            for chart in dashboard_plan.charts:
                chart.dataset_id = dataset_id
            if self._requests_heatmap(message):
                heatmap = next(
                    (chart for chart in dashboard_plan.charts if chart.chart_type == "heatmap"),
                    None,
                )
                if (
                    heatmap is None
                    or not heatmap.dimension
                    or not heatmap.secondary_dimension
                    or not heatmap.metric
                ):
                    replacement = await self._plan_heatmap_chart(
                        message, dataset_id, schema_context
                    )
                    if heatmap is not None:
                        dashboard_plan.charts[dashboard_plan.charts.index(heatmap)] = replacement
                    else:
                        if len(dashboard_plan.charts) >= 8:
                            dashboard_plan.charts.pop()
                        dashboard_plan.charts.append(replacement)
        except Exception:
            logger.exception("create_dashboard_planning_failed")
            return AIChatResponse(
                answer="Chưa thể chuẩn bị dashboard. Hãy thử mô tả mục tiêu dashboard rõ hơn.",
                intent=intent,
            )
        if not 2 <= len(dashboard_plan.charts) <= 8:
            logger.warning(
                "dashboard_plan_invalid_chart_count count=%s", len(dashboard_plan.charts)
            )
            return AIChatResponse(
                answer="Bảng điều khiển yêu cầu từ 2 đến 8 biểu đồ hợp lệ.", intent=intent
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
        self,
        message: str,
        context: AIChatContext | None,
        intent: IntentInfo,
        dataset_id: int | None = None,
        schema_context: str | None = None,
    ) -> AIChatResponse:
        if self._is_save_visualization_request(message):
            reused = self._reuse_chart_context(context)
            if reused is None:
                return AIChatResponse(
                    answer="Không tìm thấy biểu đồ gần nhất để lưu.", intent=intent
                )
            chart_plan, query, visualization = reused
            chart_plan.dataset_id = dataset_id
        else:
            try:
                if self._is_deck_grid_request(message):
                    chart_plan, grid_sql = self._deck_grid_plan(message, dataset_id)
                    sql_plan = SQLGenerationResult(intent="data_query", sql=grid_sql)
                else:
                    try:
                        chart_plan = await self.gemini.generate_chart_plan(
                            message, schema_context=schema_context
                        )
                    except TypeError:
                        chart_plan = await self.gemini.generate_chart_plan(message)
                    chart_plan.dataset_id = dataset_id
                    sql_plan = await self._generate_chart_sql(chart_plan, schema_context)
            except ValueError as error:
                return AIChatResponse(answer=str(error), intent=intent)
            except Exception:
                logger.exception("create_chart_planning_failed")
                return AIChatResponse(
                    answer="Chưa thể chuẩn bị biểu đồ. Hãy thử mô tả dữ liệu cần hiển thị rõ hơn.",
                    intent=intent,
                )
            if not sql_plan.sql.strip():
                return AIChatResponse(
                    answer="Chưa thể tạo truy vấn dữ liệu cho biểu đồ này.", intent=intent
                )
            data_response = await self._answer_data_question(
                chart_plan.question, sql_plan.sql, schema_context=schema_context
            )
            query = data_response.query
            if query is None or query.error:
                data_response.intent = intent
                data_response.answer = "Chưa thể lấy dữ liệu để tạo biểu đồ."
                return data_response
            if not query.rows:
                return AIChatResponse(
                    answer="Không có dữ liệu để tạo biểu đồ.", intent=intent, query=query
                )
            visualization = self._chart_visualization(
                chart_plan, query, data_response.visualization
            )
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
        target_dataset_id = dashboard_plan.dataset_id or (
            dashboard_plan.charts[0].dataset_id if dashboard_plan.charts else None
        )
        schema_context = (
            self.schema_service.build_schema_prompt(target_dataset_id)
            if (self.schema_service and target_dataset_id)
            else None
        )
        prepared: list[tuple[ChartPlan, str, VisualizationSpec]] = []
        for chart_plan in dashboard_plan.charts:
            if not chart_plan.dataset_id and target_dataset_id:
                chart_plan.dataset_id = target_dataset_id
            prepared.append(
                await self.prepare_chart_for_write(chart_plan, schema_context=schema_context)
            )
        return prepared

    async def prepare_chart_for_write(
        self, chart_plan: ChartPlan, schema_context: str | None = None
    ) -> tuple[ChartPlan, str, VisualizationSpec]:
        """Return normalized SQL/configuration for the write boundary."""
        if not schema_context and chart_plan.dataset_id and self.schema_service:
            schema_context = self.schema_service.build_schema_prompt(chart_plan.dataset_id)
        query, visualization = await self.prepare_chart_preview(
            chart_plan, schema_context=schema_context
        )
        return chart_plan, self.query_service.prepare_sql(query.sql or ""), visualization

    async def prepare_chart_preview(
        self, chart_plan: ChartPlan, schema_context: str | None = None
    ) -> tuple[QueryResult, VisualizationSpec]:
        """Run the read-only half of chart creation for a user-visible preview."""
        if not schema_context and chart_plan.dataset_id and self.schema_service:
            schema_context = self.schema_service.build_schema_prompt(chart_plan.dataset_id)
        try:
            sql_plan = await self._generate_chart_sql(chart_plan, schema_context)
        except Exception as error:
            raise RuntimeError(f"Could not generate SQL for {chart_plan.title}.") from error
        if not sql_plan.sql.strip():
            raise RuntimeError(f"Could not prepare a data query for {chart_plan.title}.")
        response = await self._answer_data_question(
            chart_plan.question,
            sql_plan.sql,
            schema_context=schema_context,
            include_analysis=False,
        )
        query = response.query
        if query is None or query.error:
            raise RuntimeError(f"Could not retrieve data for {chart_plan.title}.")
        if not query.rows:
            raise RuntimeError(f"No data was returned for {chart_plan.title}.")
        visualization = self._chart_visualization(chart_plan, query, response.visualization)
        if visualization.type == "none":
            raise RuntimeError(f"The result for {chart_plan.title} cannot be charted safely.")
        return query, visualization

    async def _generate_chart_sql(self, chart_plan: ChartPlan, schema_context: str | None):
        """Chart plans already imply a data query; retry one empty model result."""
        for attempt in range(2):
            question = (
                f"Return database rows for the confirmed {chart_plan.chart_type} chart "
                f"'{chart_plan.title}'. Analytics question: {chart_plan.question}\n"
                f"Requested metric: {chart_plan.metric or 'infer from the analytics question'}. "
                f"Primary dimension: {chart_plan.dimension or 'none'}. "
                f"Secondary dimension: {chart_plan.secondary_dimension or 'none'}.\n"
                "Use real columns from the supplied schema and return a nonempty SELECT query. "
                "Aggregate timestamps to the time grain requested in the question."
            )
            try:
                plan = await self.gemini.generate_sql(
                    question, schema_context=schema_context, force_data_query=True
                )
            except TypeError:
                try:
                    plan = await self.gemini.generate_sql(question, schema_context=schema_context)
                except TypeError:
                    plan = await self.gemini.generate_sql(question)
            except ValidationError:
                logger.warning(
                    "chart_sql_invalid_response chart=%r attempt=%s", chart_plan.title, attempt + 1
                )
                if attempt == 0:
                    continue
                raise
            if plan.sql.strip():
                if plan.intent.casefold() != "data_query":
                    logger.warning(
                        "chart_sql_intent_mismatch chart=%r intent=%r",
                        chart_plan.title,
                        plan.intent,
                    )
                return plan
            logger.warning(
                "chart_sql_empty chart=%r attempt=%s intent=%r",
                chart_plan.title,
                attempt + 1,
                plan.intent,
            )
        return plan

    @staticmethod
    def _is_save_visualization_request(message: str) -> bool:
        normalized = message.casefold()
        if re.search(r"\b(?:trước khi|before)\s+(?:\w+\s+){0,3}(?:lưu|save)\b", normalized):
            return False
        return bool(
            re.search(
                r"^\s*(?:(?:hãy|vui lòng|cho tôi|giúp tôi|tôi muốn|please)\s+)?(?:lưu|save)\b",
                normalized,
            )
        )

    @staticmethod
    def _is_deck_grid_request(message: str) -> bool:
        normalized = message.casefold()
        return bool(re.search(r"deck\s*\.?\s*gl\s*(?:-|\s)*grid|(?:lưới|grid)\s*3d", normalized))

    def _deck_grid_plan(self, message: str, dataset_id: int | None) -> tuple[ChartPlan, str]:
        if not dataset_id or not self.schema_service:
            raise ValueError(
                "Hãy chọn dataset có cột latitude và longitude trước khi tạo bản đồ lưới 3D."
            )
        dataset = self.schema_service.get_dataset(dataset_id)
        if not dataset:
            raise ValueError("Không đọc được dataset đã chọn để tạo bản đồ lưới 3D.")
        columns = {
            str(item.get("column_name") or "").casefold(): str(item.get("column_name"))
            for item in dataset.get("columns", [])
            if isinstance(item, dict)
        }
        lat = next((columns[key] for key in ("latitude", "lat") if key in columns), None)
        lon = next((columns[key] for key in ("longitude", "lon", "lng") if key in columns), None)
        if not lat or not lon:
            raise ValueError(
                "Dataset đã chọn cần có cả cột latitude và longitude để vẽ deck.gl Grid."
            )
        chosen = [lon, lat] + [
            columns[key] for key in ("name", "country", "population_max") if key in columns
        ]
        schema = str(dataset.get("schema") or "")
        table = str(dataset.get("table_name") or "")
        if not all(re.fullmatch(r"[A-Za-z_]\w*", value) for value in [*chosen, schema, table]):
            raise ValueError("Tên cột hoặc bảng địa lý không hợp lệ.")
        source_sql = dataset.get("sql")
        source = f"({source_sql}) AS grid_source" if source_sql else f"{schema}.{table}"
        grid_sql = f"SELECT {', '.join(chosen)} FROM {source} LIMIT 500"
        match = re.search(r"(?:tiêu đề|title)\s*[“\"']([^”\"']+)", message, flags=re.IGNORECASE)
        title = match.group(1).strip() if match else "Bản đồ lưới 3D"
        plan = ChartPlan(
            title=title,
            chart_type="map",
            map_style="grid",
            question=message,
            metric="count",
            dimension=lon,
            dataset_id=dataset_id,
        )
        return plan, grid_sql

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
                metric=visualization.value_axis
                if visualization.type == "heatmap"
                else visualization.y_axis,
                dimension=visualization.x_axis,
                secondary_dimension=visualization.y_axis
                if visualization.type == "heatmap"
                else None,
                limit=query.row_count if query.row_count <= 500 else None,
            ),
            query,
            visualization,
        )

    def _chart_visualization(
        self, chart_plan: ChartPlan, query: QueryResult, existing: VisualizationSpec | None
    ) -> VisualizationSpec:
        if chart_plan.chart_type == "kpi":
            # A scalar aggregate is a valid KPI even if Gemini returns no chart
            # or names the metric as COUNT(*) rather than its SQL result alias.
            if query.row_count != 1 or len(query.rows) != 1:
                return VisualizationSpec()
            numeric_columns = [
                column
                for column in query.columns
                if self.visualization_service._is_numeric_column(query, column)
            ]
            y_axis = (
                chart_plan.metric
                if chart_plan.metric in numeric_columns
                else existing.y_axis
                if existing and existing.type == "kpi" and existing.y_axis in numeric_columns
                else numeric_columns[0]
                if len(numeric_columns) == 1
                else None
            )
            return self.visualization_service.validate(
                VisualizationSpec(
                    type="kpi",
                    title=chart_plan.title,
                    y_axis=y_axis,
                    y_label=(y_axis or "").replace("_", " ").title() or None,
                ),
                query,
            )
        if chart_plan.chart_type == "heatmap":
            numeric_columns = [
                column
                for column in query.columns
                if self.visualization_service._is_numeric_column(query, column)
            ]
            value_axis = (
                chart_plan.metric
                if chart_plan.metric in numeric_columns
                else (numeric_columns[-1] if numeric_columns else None)
            )
            categories = [column for column in query.columns if column != value_axis]
            x_axis = (
                chart_plan.dimension
                if chart_plan.dimension in categories
                else (categories[0] if categories else None)
            )
            y_axis = (
                chart_plan.secondary_dimension
                if chart_plan.secondary_dimension in categories
                else next((column for column in categories if column != x_axis), None)
            )
            return self.visualization_service.validate(
                VisualizationSpec(
                    type="heatmap",
                    title=chart_plan.title,
                    x_axis=x_axis,
                    y_axis=y_axis,
                    value_axis=value_axis,
                ),
                query,
            )
        baseline = existing or self.visualization_service.heuristic(query)
        x_axis = chart_plan.dimension if chart_plan.dimension in query.columns else baseline.x_axis
        y_axis = chart_plan.metric if chart_plan.metric in query.columns else baseline.y_axis
        candidate = VisualizationSpec(
            type=chart_plan.chart_type,
            map_style=chart_plan.map_style if chart_plan.chart_type == "map" else None,
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
                    parameters[
                        "preferred_chart_type"
                        if intent.intent == AIIntent.CREATE_CHART
                        else "chart_type"
                    ] = chart_type
                    parameters.setdefault("operation", "change_chart_type")
                    break
        if intent.intent == AIIntent.EDIT_DASHBOARD:
            parameters.setdefault(
                "operation",
                "add_chart" if "add" in lowered or "thêm" in lowered else "edit_dashboard",
            )
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

    async def _answer_data_question(
        self,
        message: str,
        sql: str,
        schema_context: str | None = None,
        rls_info: dict[str, Any] | None = None,
        *,
        include_analysis: bool = True,
    ) -> AIChatResponse:
        applied_desc = rls_info.get("description") if rls_info else None
        for retry_count in range(2):
            try:
                result = await self.query_service.execute_query(sql)
            except SQLValidationError:
                logger.warning(
                    "nl2sql_validation_rejected question=%r retry=%s", message, retry_count
                )
                return AIChatResponse(
                    answer="Không thể thực hiện truy vấn này vì SQL không đáp ứng chính sách chỉ đọc.",
                    query=QueryResult(sql=sql, error="SQL rejected by the read-only policy"),
                    applied_rls_filter=applied_desc,
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
                if not include_analysis:
                    # Confirmed chart plans already specify their visualization.
                    # Keep SQL validation/repair, without two extra LLM calls per chart.
                    return AIChatResponse(
                        answer="",
                        query=result,
                        visualization=self.visualization_service.heuristic(result),
                        applied_rls_filter=applied_desc,
                    )
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
                return AIChatResponse(
                    answer=answer,
                    query=result,
                    visualization=visualization,
                    applied_rls_filter=applied_desc,
                )

            if retry_count == 0:
                try:
                    try:
                        repaired = await self.gemini.repair_sql(
                            message, sql, result.error, schema_context=schema_context
                        )
                    except TypeError:
                        repaired = await self.gemini.repair_sql(message, sql, result.error)
                    if repaired.intent.lower() == "data_query" and repaired.sql.strip():
                        from app.services.rls_service import RLSService

                        sql = repaired.sql
                        if rls_info and rls_info.get("filter_clause"):
                            sql = RLSService.rewrite_sql(sql, rls_info["filter_clause"])
                        continue
                except Exception:
                    logger.exception("nl2sql_repair_generation_failed")
            if result.error == "Query timed out":
                answer = "Truy vấn mất quá nhiều thời gian. Hãy thử câu hỏi cụ thể hơn."
            else:
                answer = "Tôi chưa thể tạo truy vấn phù hợp cho câu hỏi này."
            return AIChatResponse(answer=answer, query=result, applied_rls_filter=applied_desc)

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
        contents: list[Any] = [
            types.Content(role="user", parts=[types.Part.from_text(text=message)])
        ]
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
