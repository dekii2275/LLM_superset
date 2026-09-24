import unittest
from unittest.mock import AsyncMock, patch

from app.api.ai import execute_action
from app.schemas.ai import (
    AIChatContext,
    AIIntent,
    ActionExecutionRequest,
    EditChartOperation,
    EditChartPlan,
    EditDashboardOperation,
    EditDashboardPlan,
    IntentResult,
    UpdateChartResult,
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
