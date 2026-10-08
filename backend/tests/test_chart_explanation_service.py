import os
import sys
import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:password@localhost:5432/ai_bi")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import HTTPException

from app.api.ai import explain_chart
from app.schemas.ai import (
    ChartExplanation,
    ExplainChartRequest,
    QueryResult,
    VisualizationSpec,
)
from app.services.chart_explanation_service import (
    ChartExplanationService,
    ChartExplanationValidationError,
)
from app.services.query_service import SQLValidationError


class ChartExplanationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ChartExplanationService()

    def test_bar_chart_reports_extremes_difference_and_scope(self) -> None:
        result = QueryResult(
            columns=["zone", "trips"],
            rows=[{"zone": "A", "trips": 12}, {"zone": "B", "trips": 5}],
        )
        explanation = self.service.analyze(
            result,
            VisualizationSpec(type="bar", title="Trips by Zone", x_axis="zone", y_axis="trips"),
        )
        self.assertIn("A", explanation.highlights[0])
        self.assertIn("12", explanation.highlights[0])
        self.assertIn("5", explanation.highlights[1])
        self.assertIn("7", explanation.highlights[2])
        self.assertIn("2 điểm hợp lệ trong 2 dòng", explanation.note)
        self.assertIn("không xác định nguyên nhân", explanation.note)

    def test_pie_share_uses_only_positive_displayed_values(self) -> None:
        result = QueryResult(
            columns=["payment", "total"],
            rows=[
                {"payment": "card", "total": Decimal("3")},
                {"payment": "cash", "total": Decimal("1")},
            ],
        )
        explanation = self.service.analyze(
            result,
            VisualizationSpec(type="pie", x_axis="payment", y_axis="total"),
        )
        self.assertTrue(
            any(
                "75%" in item and "các nhóm được truy vấn" in item
                for item in explanation.highlights
            )
        )

    def test_line_chart_reports_end_change_but_does_not_claim_trend_with_two_points(self) -> None:
        result = QueryResult(
            columns=["month", "trips"],
            rows=[{"month": "2026-01", "trips": 100}, {"month": "2026-02", "trips": 120}],
        )
        explanation = self.service.analyze(
            result,
            VisualizationSpec(type="line", x_axis="month", y_axis="trips"),
        )
        self.assertIn("chưa đủ điểm để xác định", explanation.summary)
        self.assertTrue(any("20 (20%)" in item for item in explanation.highlights))

    def test_area_chart_reports_direction_and_largest_adjacent_change(self) -> None:
        result = QueryResult(
            columns=["month", "trips"],
            rows=[
                {"month": "Jan", "trips": 10},
                {"month": "Feb", "trips": 16},
                {"month": "Mar", "trips": 8},
            ],
        )
        explanation = self.service.analyze(
            result,
            VisualizationSpec(type="area", x_axis="month", y_axis="trips"),
        )
        self.assertIn("giảm", explanation.summary)
        self.assertTrue(
            any("Biến động liền kề lớn nhất: giảm 8" in item for item in explanation.highlights)
        )

    def test_missing_and_non_numeric_values_are_excluded_and_reported(self) -> None:
        result = QueryResult(
            columns=["zone", "trips"],
            rows=[
                {"zone": "A", "trips": 9},
                {"zone": "B", "trips": None},
                {"zone": None, "trips": 2},
            ],
        )
        explanation = self.service.analyze(
            result,
            VisualizationSpec(type="bar", x_axis="zone", y_axis="trips"),
        )
        self.assertIn("1 điểm hợp lệ trong 3 dòng", explanation.note)
        self.assertIn("Bỏ qua 2 dòng", explanation.note)

    def test_single_valid_point_does_not_claim_a_comparison_or_trend(self) -> None:
        result = QueryResult(
            columns=["month", "trips"],
            rows=[{"month": "Jan", "trips": 9}, {"month": "Feb", "trips": None}],
        )
        explanation = self.service.analyze(
            result,
            VisualizationSpec(type="line", x_axis="month", y_axis="trips"),
        )
        self.assertIn("một điểm dữ liệu hợp lệ", explanation.summary)
        self.assertEqual(len(explanation.highlights), 1)

    def test_empty_results_return_limited_explanation(self) -> None:
        result = QueryResult(columns=["month", "trips"], rows=[])
        explanation = self.service.analyze(
            result,
            VisualizationSpec(type="line", x_axis="month", y_axis="trips"),
        )
        self.assertEqual(explanation.highlights, [])
        self.assertIn("0 dòng", explanation.summary)

    def test_axes_must_exist_in_reexecuted_result(self) -> None:
        result = QueryResult(columns=["month", "trips"], rows=[])
        with self.assertRaises(ChartExplanationValidationError):
            self.service.analyze(
                result, VisualizationSpec(type="bar", x_axis="zone", y_axis="trips")
            )


class ExplainChartEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_endpoint_reexecutes_sql_and_returns_computed_explanation(self) -> None:
        result = QueryResult(
            sql="SELECT zone, trips FROM result LIMIT 10",
            columns=["zone", "trips"],
            rows=[{"zone": "A", "trips": 12}, {"zone": "B", "trips": 5}],
        )
        with (
            patch("app.api.ai.QueryService") as query_service_type,
            patch("app.api.ai.settings.gemini_api_key", ""),
        ):
            query_service_type.return_value.execute_query = AsyncMock(return_value=result)
            response = await explain_chart(
                ExplainChartRequest(
                    sql="SELECT zone, trips FROM result",
                    visualization=VisualizationSpec(type="bar", x_axis="zone", y_axis="trips"),
                )
            )
        query_service_type.return_value.execute_query.assert_awaited_once_with(
            "SELECT zone, trips FROM result"
        )
        self.assertIn("7", response.highlights[2])

    async def test_endpoint_rejects_sql_blocked_by_read_only_policy(self) -> None:
        with patch("app.api.ai.QueryService") as query_service_type:
            query_service_type.return_value.execute_query = AsyncMock(
                side_effect=SQLValidationError("blocked")
            )
            with self.assertRaises(HTTPException) as error:
                await explain_chart(
                    ExplainChartRequest(
                        sql="DELETE FROM trips",
                        visualization=VisualizationSpec(type="bar", x_axis="zone", y_axis="trips"),
                    )
                )
        self.assertEqual(error.exception.status_code, 400)


class SupersetDashboardChartsTests(unittest.IsolatedAsyncioTestCase):
    def test_list_dashboard_charts_returns_mapped_charts(self) -> None:
        from unittest.mock import MagicMock

        from app.api.superset import list_dashboard_charts

        mock_client = MagicMock()
        mock_client.request.side_effect = lambda method, path: {
            "/api/v1/dashboard/nyc-taxi-trips-analysis": {"result": {"id": 2}},
            "/api/v1/dashboard/2/charts": {
                "result": [
                    {
                        "id": 23,
                        "datasource_id": 2,
                        "slice_name": "Total Trips by Vendor",
                        "viz_type": "pie",
                        "description": "Vendor pie",
                    },
                    {
                        "id": 5,
                        "datasource_id": 2,
                        "slice_name": "Total No Of Trips",
                        "viz_type": "big_number_total",
                        "description": "KPI",
                    },
                ]
            },
        }.get(path, {"result": {}})

        with patch("app.api.superset.get_client", return_value=mock_client):
            charts = list_dashboard_charts({"role": "admin", "username": "admin"})

        self.assertEqual(len(charts), 2)
        self.assertEqual(charts[0]["id"], 23)
        self.assertEqual(charts[0]["viz_type"], "pie")
        self.assertEqual(charts[1]["id"], 5)
        self.assertEqual(charts[1]["viz_type"], "kpi")

    async def test_explain_superset_chart_kpi(self) -> None:
        from unittest.mock import MagicMock

        from app.api.superset import explain_superset_chart

        mock_client = MagicMock()
        mock_client.request.side_effect = lambda method, path: {
            "/api/v1/chart/5": {
                "result": {"id": 5, "slice_name": "Total Trips", "viz_type": "big_number_total"}
            },
            "/api/v1/chart/5/data/": {
                "result": [
                    {
                        "colnames": ["Total Trips"],
                        "data": [{"Total Trips": 30000}],
                        "query": "SELECT 30000",
                    }
                ]
            },
        }.get(path, {"result": {}})

        with (
            patch("app.api.superset.get_client", return_value=mock_client),
            patch("app.api.superset.settings.gemini_api_key", ""),
        ):
            res = await explain_superset_chart(5, {"role": "admin", "username": "admin"})

        self.assertEqual(res["chart_id"], 5)
        self.assertEqual(res["viz_type"], "kpi")
        self.assertIn("30.000", res["explanation"]["summary"])
        self.assertEqual(res["sql"], "SELECT 30000")

    async def test_explain_superset_chart_categorical(self) -> None:
        from unittest.mock import MagicMock

        from app.api.superset import explain_superset_chart

        mock_client = MagicMock()
        mock_client.request.side_effect = lambda method, path: {
            "/api/v1/chart/23": {
                "result": {
                    "id": 23,
                    "slice_name": "Vendor Share",
                    "viz_type": "pie",
                    "params": '{"groupby": ["vendor_name"], "metric": "count"}',
                }
            },
            "/api/v1/chart/23/data/": {
                "result": [
                    {
                        "colnames": ["vendor_name", "count"],
                        "data": [
                            {"vendor_name": "CMT", "count": 100},
                            {"vendor_name": "VTS", "count": 20},
                        ],
                        "query": "SELECT vendor_name, count FROM t",
                    }
                ]
            },
        }.get(path, {"result": {}})

        with (
            patch("app.api.superset.get_client", return_value=mock_client),
            patch("app.api.superset.settings.gemini_api_key", ""),
        ):
            res = await explain_superset_chart(23, {"role": "admin", "username": "admin"})

        self.assertEqual(res["chart_id"], 23)
        self.assertEqual(res["viz_type"], "pie")
        self.assertIn("CMT", res["explanation"]["highlights"][0])
        self.assertIn("100", res["explanation"]["highlights"][0])

    async def test_explain_superset_chart_gemini_enhanced(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.api.superset import explain_superset_chart

        mock_client = MagicMock()
        mock_client.request.side_effect = lambda method, path: {
            "/api/v1/chart/23": {
                "result": {
                    "id": 23,
                    "slice_name": "Vendor Share",
                    "viz_type": "pie",
                    "params": '{"groupby": ["vendor_name"], "metric": "count"}',
                }
            },
            "/api/v1/chart/23/data/": {
                "result": [
                    {
                        "colnames": ["vendor_name", "count"],
                        "data": [
                            {"vendor_name": "CMT", "count": 100},
                            {"vendor_name": "VTS", "count": 20},
                        ],
                        "query": "SELECT vendor_name, count FROM t",
                    }
                ]
            },
        }.get(path, {"result": {}})

        mock_gemini = MagicMock()
        mock_gemini.generate_chart_explanation = AsyncMock(
            return_value=ChartExplanation(
                summary="Gemini nhận định: CMT chiếm lĩnh thị phần áp đảo.",
                highlights=["CMT dẫn đầu với 100 chuyến.", "VTS chiếm phần nhỏ còn lại."],
                note="Dữ liệu chính xác từ Superset.",
            )
        )

        with (
            patch("app.api.superset.get_client", return_value=mock_client),
            patch("app.api.superset.settings.gemini_api_key", "mock-key"),
            patch("app.api.superset.GeminiService", return_value=mock_gemini),
        ):
            res = await explain_superset_chart(23, {"role": "admin", "username": "admin"})

        self.assertEqual(res["chart_id"], 23)
        self.assertIn("Gemini nhận định", res["explanation"]["summary"])
        self.assertIn("áp đảo", res["explanation"]["summary"])


if __name__ == "__main__":
    unittest.main()
