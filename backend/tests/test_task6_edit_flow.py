import unittest
from unittest.mock import AsyncMock, patch

from app.api.ai import execute_action
from app.schemas.ai import (
    AIChatContext,
    AIIntent,
    ActionExecutionRequest,
    ChartPlan,
    EditChartOperation,
    EditChartPlan,
    EditDashboardOperation,
    EditDashboardPlan,
    IntentResult,
    QueryResult,
    SQLGenerationResult,
    UpdateChartResult,
    VisualizationSpec,
)
from app.services.ai_bi_service import AIBIService
from app.services.superset_write_service import SupersetWriteService


class EditGemini:
    async def classify_intent(self, message):
        return IntentResult(intent=AIIntent.EDIT_CHART, user_goal=message)

    async def generate_edit_chart_plan(self, message):
        return EditChartPlan(operation=EditChartOperation.CHANGE_CHART_TYPE, new_chart_type="bar")


class EditPreviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_edit_chart_preview_uses_trusted_context_and_never_writes(self):
        service = AIBIService(object(), EditGemini(), object())
        response = await service.chat(
            "Change this chart to bar", AIChatContext(active_chart_id=12, active_chart_title="Monthly Trip Volume")
        )
        self.assertEqual(response.pending_action.action, "EDIT_CHART")
        self.assertEqual(response.pending_action.edit_chart_plan.chart_id, 12)
        self.assertEqual(response.pending_action.edit_chart_plan.new_chart_type, "bar")

    async def test_unsupported_chart_type_is_a_safe_preview_error(self):
        service = AIBIService(object(), EditGemini(), object())
        response = await service.chat("Change this chart to a scatter plot", AIChatContext(active_chart_id=12))
        self.assertIsNone(response.pending_action)
        self.assertIn("bar", response.answer)

    async def test_add_new_dashboard_chart_returns_chart_preview_before_confirmation(self):
        class DashboardGemini:
            async def classify_intent(self, message):
                return IntentResult(intent=AIIntent.EDIT_DASHBOARD, user_goal=message)

            async def generate_edit_dashboard_plan(self, message):
                return EditDashboardPlan(
                    operation=EditDashboardOperation.ADD_CHART,
                    dashboard_name="NYC Yellow Taxi Overview",
                    create_chart_plan=ChartPlan(
                        title="Top Pickup Zones",
                        chart_type="bar",
                        question="Top pickup zones by trip count",
                        dimension="zone",
                        metric="trip_count",
                    ),
                )

            async def generate_sql(self, question):
                return SQLGenerationResult(
                    intent="data_query",
                    sql="SELECT 'A' AS zone, 12 AS trip_count UNION ALL SELECT 'B', 8",
                )

            async def generate_answer_from_result(self, question, result):
                return "Preview data ready."

            async def generate_visualization(self, question, result):
                return VisualizationSpec(type="bar", x_axis="zone", y_axis="trip_count")

        class PreviewQueryService:
            async def execute_query(self, sql):
                return QueryResult(
                    sql=sql,
                    columns=["zone", "trip_count"],
                    rows=[{"zone": "A", "trip_count": 12}, {"zone": "B", "trip_count": 8}],
                    row_count=2,
                )

            def prepare_sql(self, sql):
                return sql

        response = await AIBIService(object(), DashboardGemini(), PreviewQueryService()).chat(
            "Add top pickup zones to the dashboard"
        )
        self.assertEqual(response.pending_action.action, "EDIT_DASHBOARD")
        self.assertEqual(response.query.rows[0]["zone"], "A")
        self.assertEqual(response.visualization.title, "Top Pickup Zones")


class EditExecutionBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_execute_edit_chart_calls_semantic_writer_only(self):
        plan = EditChartPlan(chart_id=12, operation=EditChartOperation.RENAME_CHART, new_title="Monthly Taxi Demand")
        result = UpdateChartResult(success=True, chart_id=12, chart_name="Monthly Taxi Demand", message="Chart updated successfully.")
        request = ActionExecutionRequest(action=AIIntent.EDIT_CHART, edit_chart_plan=plan)
        with patch("app.api.ai.SupersetWriteService") as writer:
            writer.return_value.edit_chart = AsyncMock(return_value=result)
            response = await execute_action(request)
        self.assertTrue(response.success)
        self.assertEqual(response.result.chart_name, "Monthly Taxi Demand")


class DashboardLayoutTests(unittest.TestCase):
    def test_layout_supports_five_charts_as_three_rows(self):
        charts = [{"id": index, "slice_name": f"Chart {index}", "uuid": str(index)} for index in range(1, 6)]
        layout = SupersetWriteService.build_dashboard_layout("Demo", charts)
        self.assertEqual(layout["GRID_ID"]["children"], ["ROW-1", "ROW-2", "ROW-3"])
        self.assertEqual(layout["ROW-3"]["children"], ["CHART-5"])

    def test_layout_supports_more_than_six_charts(self):
        charts = [{"id": index, "slice_name": f"Chart {index}", "uuid": str(index)} for index in range(1, 10)]
        layout = SupersetWriteService.build_dashboard_layout("Demo", charts)
        self.assertEqual(layout["GRID_ID"]["children"], ["ROW-1", "ROW-2", "ROW-3", "ROW-4", "ROW-5"])
        self.assertEqual(layout["ROW-4"]["children"], ["CHART-7", "CHART-8"])
        self.assertEqual(layout["ROW-5"]["children"], ["CHART-9"])
