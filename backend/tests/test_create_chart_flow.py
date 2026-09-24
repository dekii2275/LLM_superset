import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:password@localhost:5432/ai_bi")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import HTTPException

from app.api.ai import execute_action
from app.schemas.ai import (
    AIIntent,
    ActionExecutionRequest,
    ChartPlan,
    CreateChartResult,
    CreateDashboardResult,
    DashboardPlan,
    IntentResult,
    QueryResult,
    SQLGenerationResult,
    VisualizationSpec,
)
from app.services.ai_bi_service import AIBIService
from app.services.superset_write_service import SupersetWriteService


class CreateChartGemini:
    async def classify_intent(self, message: str) -> IntentResult:
        return IntentResult(intent=AIIntent.CREATE_CHART, user_goal=message)

    async def generate_chart_plan(self, message: str) -> ChartPlan:
        return ChartPlan(
            title="Top 10 Pickup Zones",
            chart_type="bar",
            question="Top 10 pickup zones by trip count",
            metric="trip_count",
            dimension="zone",
            limit=10,
        )

    async def generate_sql(self, question: str) -> SQLGenerationResult:
        return SQLGenerationResult(
            intent="data_query",
            sql="SELECT pu_location_id AS zone, COUNT(*) AS trip_count FROM raw.yellow_taxi_trips GROUP BY 1 ORDER BY 2 DESC LIMIT 10",
        )

    async def generate_answer_from_result(self, question: str, result: QueryResult) -> str:
        return "Prepared chart data."

    async def generate_visualization(self, question: str, result: QueryResult) -> VisualizationSpec:
        return VisualizationSpec(type="bar", x_axis="zone", y_axis="trip_count")


class FailingChartGemini(CreateChartGemini):
    async def repair_sql(self, question: str, sql: str, database_error: str) -> SQLGenerationResult:
        return SQLGenerationResult(intent="data_query", sql=sql)


class DashboardGemini(CreateChartGemini):
    async def classify_intent(self, message: str) -> IntentResult:
        return IntentResult(intent=AIIntent.CREATE_DASHBOARD, user_goal=message)

    async def generate_dashboard_plan(self, message: str) -> DashboardPlan:
        return DashboardPlan(
            title="NYC Taxi Overview",
            description="Taxi activity overview.",
            charts=[
                ChartPlan(title="Trips by Month", chart_type="line", question="Trips by month", metric="trip_count", dimension="month"),
                ChartPlan(title="Revenue by Month", chart_type="line", question="Revenue by month", metric="total_revenue", dimension="month"),
                ChartPlan(title="Top Pickup Zones", chart_type="bar", question="Top pickup zones", metric="trip_count", dimension="zone", limit=10),
                ChartPlan(title="Payment Types", chart_type="pie", question="Payment type distribution", metric="trip_count", dimension="payment_type"),
            ],
        )


class QuerySuccess:
    async def execute_query(self, sql: str) -> QueryResult:
        return QueryResult(
            sql=sql,
            columns=["zone", "trip_count"],
            rows=[{"zone": "A", "trip_count": 12}, {"zone": "B", "trip_count": 8}],
            row_count=2,
            execution_time_ms=3,
        )


class QueryFailure:
    async def execute_query(self, sql: str) -> QueryResult:
        return QueryResult(sql=sql, error="Invalid query")


class CreateChartPreviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_chart_returns_query_preview_and_pending_action(self) -> None:
        service = AIBIService(object(), CreateChartGemini(), QuerySuccess())
        response = await service.chat("Create a bar chart for top pickup zones")
        self.assertEqual(response.intent.type, AIIntent.CREATE_CHART)
        self.assertIsNotNone(response.query)
        self.assertEqual(response.visualization.type, "bar")
        self.assertIsNotNone(response.pending_action)
        self.assertEqual(response.pending_action.chart_plan.title, "Top 10 Pickup Zones")

    async def test_query_failure_never_returns_pending_action(self) -> None:
        service = AIBIService(object(), FailingChartGemini(), QueryFailure())
        response = await service.chat("Create a bar chart for top pickup zones")
        self.assertIsNotNone(response.query)
        self.assertIsNotNone(response.query.error)
        self.assertIsNone(response.pending_action)

    async def test_dashboard_preview_returns_plan_without_query_or_write(self) -> None:
        service = AIBIService(object(), DashboardGemini(), QuerySuccess())
        response = await service.chat("Create an NYC Taxi dashboard")
        self.assertEqual(response.intent.type, AIIntent.CREATE_DASHBOARD)
        self.assertEqual(len(response.dashboard_plan.charts), 4)
        self.assertEqual(response.pending_action.action, "CREATE_DASHBOARD")
        self.assertIsNone(response.query)


class SupersetPayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.writer = SupersetWriteService("http://superset", "http://public", "u", "p", 1)

    def test_payload_uses_verified_bar_mapping(self) -> None:
        payload = self.writer.build_superset_chart_payload(
            "Top Pickup Zones",
            ChartPlan(title="Top Pickup Zones", chart_type="bar", question="Top zones", limit=10),
            VisualizationSpec(type="bar", x_axis="zone", y_axis="trip_count"),
        )
        self.assertEqual(payload["datasource_id"], 1)
        self.assertEqual(payload["viz_type"], "echarts_timeseries_bar")
        self.assertIn("pu_location_id", payload["params"])
        self.assertIn('"count"', payload["params"])

    def test_dashboard_layout_uses_all_chart_ids(self) -> None:
        layout = self.writer.build_dashboard_layout(
            "NYC Taxi Overview",
            [{"id": index, "slice_name": f"Chart {index}", "uuid": f"uuid-{index}"} for index in range(1, 5)],
        )
        self.assertEqual(layout["ROW-1"]["children"], ["CHART-1", "CHART-2"])
        self.assertEqual(layout["ROW-2"]["children"], ["CHART-3", "CHART-4"])


class ExecuteBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def request(self, sql: str, action: AIIntent = AIIntent.CREATE_CHART) -> ActionExecutionRequest:
        return ActionExecutionRequest(
            action=action,
            chart_plan=ChartPlan(title="Top Pickup Zones", chart_type="bar", question="Top zones"),
            query=QueryResult(
                sql=sql,
                columns=["zone", "trip_count"],
                rows=[{"zone": "A", "trip_count": 12}, {"zone": "B", "trip_count": 8}],
                row_count=2,
            ),
            visualization=VisualizationSpec(type="bar", x_axis="zone", y_axis="trip_count"),
        )

    async def test_execute_valid_create_chart_uses_write_service(self) -> None:
        result = CreateChartResult(success=True, chart_id=42, chart_name="Top Pickup Zones", message="Chart created successfully.")
        with patch("app.api.ai.SupersetWriteService") as writer:
            writer.return_value.create_chart = AsyncMock(return_value=result)
            response = await execute_action(self.request("SELECT 1 AS zone, 2 AS trip_count"))
        self.assertTrue(response.success)
        self.assertEqual(response.result.chart_id, 42)

    async def test_execute_rejects_unsupported_action_and_unsafe_sql(self) -> None:
        with self.assertRaises(HTTPException) as unsupported:
            await execute_action(self.request("SELECT 1 AS zone, 2 AS trip_count", AIIntent.EDIT_DASHBOARD))
        # EDIT_DASHBOARD is now supported, but still needs a semantic plan.
        self.assertEqual(unsupported.exception.status_code, 422)
        with self.assertRaises(HTTPException) as unsafe:
            await execute_action(self.request("DROP TABLE raw.yellow_taxi_trips"))
        self.assertEqual(unsafe.exception.status_code, 400)

    async def test_execute_dashboard_uses_prepared_charts_and_writer(self) -> None:
        plan = DashboardGemini().generate_dashboard_plan("dashboard")
        plan = await plan
        result = CreateDashboardResult(
            success=True, dashboard_id=7, dashboard_uuid="uuid-7", dashboard_name=plan.title,
            chart_ids=[12, 13, 14, 15], message="Dashboard created successfully.",
        )
        request = ActionExecutionRequest(action=AIIntent.CREATE_DASHBOARD, dashboard_plan=plan)
        with patch("app.api.ai.AIBIService.prepare_dashboard_charts", new=AsyncMock(return_value=[])), patch("app.api.ai.SupersetWriteService") as writer:
            writer.return_value.create_dashboard = AsyncMock(return_value=result)
            response = await execute_action(request)
        self.assertTrue(response.success)
        self.assertEqual(response.result.dashboard_id, 7)

    async def test_dashboard_chart_prepare_failure_stops_before_dashboard_write(self) -> None:
        plan = await DashboardGemini().generate_dashboard_plan("dashboard")
        request = ActionExecutionRequest(action=AIIntent.CREATE_DASHBOARD, dashboard_plan=plan)
        with patch("app.api.ai.AIBIService.prepare_dashboard_charts", new=AsyncMock(side_effect=RuntimeError("Chart 2 failed"))), patch("app.api.ai.SupersetWriteService") as writer:
            response = await execute_action(request)
        self.assertFalse(response.success)
        self.assertIsNone(response.result)
        writer.return_value.create_dashboard.assert_not_called()


if __name__ == "__main__":
    unittest.main()
