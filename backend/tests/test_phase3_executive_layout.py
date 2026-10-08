"""Unit tests for Phase 3: Executive Layout Hierarchy, Cross-Filtering & Extended Visualizations."""

import json
import unittest
from unittest.mock import MagicMock, patch

from app.schemas.ai import (
    ChartPlan,
    CreateChartResult,
    DashboardPlan,
    QueryResult,
    VisualizationSpec,
)
from app.services.superset_write_service import SupersetWriteService
from app.services.visualization_service import VisualizationService


class Phase3ExecutiveLayoutTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.writer = SupersetWriteService(
            base_url="http://superset-test:8088",
            public_url="http://localhost:8088",
            username="admin",
            password="admin_password",
            dataset_id=1,
        )
        self.viz_service = VisualizationService()

    def test_kpi_chart_payload(self) -> None:
        client = MagicMock()
        client.get_dataset.return_value = {
            "columns": [{"column_name": "fare_amount"}],
            "metrics": [{"metric_name": "Gross Trip Amount"}],
        }
        plan = ChartPlan(
            title="Tổng doanh thu",
            chart_type="kpi",
            question="Tổng doanh thu taxi",
            metric="fare_amount",
            limit=1,
        )
        spec = VisualizationSpec(type="kpi", y_axis="fare_amount")
        payload = self.writer.build_superset_chart_payload(
            "Tổng doanh thu", plan, spec, client=client
        )
        self.assertEqual(payload["viz_type"], "big_number_total")
        params = json.loads(payload["params"])
        self.assertEqual(params["viz_type"], "big_number_total")
        self.assertEqual(params["row_limit"], 1)
        self.assertEqual(params["subheader"], "Tổng doanh thu")
        query_context = json.loads(payload["query_context"])
        self.assertEqual(query_context["queries"][0]["row_limit"], 1)

    def test_table_chart_payload(self) -> None:
        client = MagicMock()
        client.get_dataset.return_value = {
            "columns": [{"column_name": "payment_type"}, {"column_name": "fare_amount"}],
            "metrics": [{"metric_name": "count"}],
        }
        plan = ChartPlan(
            title="Bảng chi tiết thanh toán",
            chart_type="table",
            question="Chi tiết các khoản thanh toán",
            dimension="payment_type",
            metric="count",
            limit=50,
        )
        spec = VisualizationSpec(type="table", x_axis="payment_type", y_axis="count")
        payload = self.writer.build_superset_chart_payload(
            "Bảng chi tiết thanh toán", plan, spec, client=client
        )
        self.assertEqual(payload["viz_type"], "table")
        params = json.loads(payload["params"])
        self.assertEqual(params["viz_type"], "table")
        self.assertTrue(params.get("include_search"))
        self.assertIn("payment_type", params.get("groupby", []))

    def test_area_chart_payload_enables_area_and_opacity(self) -> None:
        client = MagicMock()
        client.get_dataset.return_value = {
            "columns": [{"column_name": "tpep_pickup_datetime"}, {"column_name": "fare_amount"}],
            "metrics": [{"metric_name": "count"}],
        }
        plan = ChartPlan(
            title="Xu hướng chuyến đi theo thời gian",
            chart_type="area",
            question="Xu hướng chuyến đi taxi",
            dimension="tpep_pickup_datetime",
            metric="count",
        )
        spec = VisualizationSpec(type="area", x_axis="tpep_pickup_datetime", y_axis="count")
        payload = self.writer.build_superset_chart_payload(
            "Xu hướng chuyến đi theo thời gian", plan, spec, client=client
        )
        self.assertEqual(payload["viz_type"], "echarts_timeseries_line")
        params = json.loads(payload["params"])
        self.assertTrue(params.get("area"))
        self.assertAlmostEqual(params.get("opacity", 0), 0.25)

    def test_executive_layout_hierarchy_ordering(self) -> None:
        """Confirms that executive hierarchy ranks: KPI -> Trend -> Breakdown -> Table."""
        charts = [
            {"id": 101, "slice_name": "Chi tiết chuyến đi", "viz_type": "table", "uuid": "u1"},
            {
                "id": 102,
                "slice_name": "Phân bổ theo hình thức trả tiền",
                "viz_type": "pie",
                "uuid": "u2",
            },
            {
                "id": 103,
                "slice_name": "Tổng doanh thu",
                "viz_type": "big_number_total",
                "uuid": "u3",
            },
            {
                "id": 104,
                "slice_name": "Tổng số cuốc xe",
                "viz_type": "big_number_total",
                "uuid": "u4",
            },
            {
                "id": 105,
                "slice_name": "Xu hướng theo ngày",
                "viz_type": "echarts_timeseries_line",
                "uuid": "u5",
            },
            {
                "id": 106,
                "slice_name": "Số chuyến theo khu vực",
                "viz_type": "echarts_timeseries_bar",
                "uuid": "u6",
            },
        ]
        layout = SupersetWriteService.build_dashboard_layout("Báo cáo Điều hành NYC Taxi", charts)

        # Row 1 should be KPI Cards (charts 103 and 104)
        self.assertEqual(layout["ROW-1"]["children"], ["CHART-103", "CHART-104"])
        self.assertEqual(layout["CHART-103"]["meta"]["height"], 26)
        self.assertEqual(layout["CHART-104"]["meta"]["height"], 26)
        self.assertEqual(layout["CHART-103"]["meta"]["width"], 6)

        # Row 2 should be Time Trend (chart 105)
        self.assertEqual(layout["ROW-2"]["children"], ["CHART-105"])
        self.assertEqual(layout["CHART-105"]["meta"]["width"], 12)
        self.assertEqual(layout["CHART-105"]["meta"]["height"], 50)

        # Row 3 should be Breakdowns (charts 102 and 106)
        self.assertEqual(layout["ROW-3"]["children"], ["CHART-102", "CHART-106"])
        self.assertEqual(layout["CHART-102"]["meta"]["width"], 6)
        self.assertEqual(layout["CHART-106"]["meta"]["width"], 6)

        # Row 4 should be Table Detail (chart 101)
        self.assertEqual(layout["ROW-4"]["children"], ["CHART-101"])
        self.assertEqual(layout["CHART-101"]["meta"]["width"], 12)
        self.assertEqual(layout["CHART-101"]["meta"]["height"], 50)

    async def test_create_dashboard_omits_unsafe_cross_filtering(self) -> None:
        """Generated dashboards must render with any supported chart mix."""
        mock_client = MagicMock()

        def mock_request(method: str, url: str, payload=None):
            if "/api/v1/dataset/" in url:
                return {"result": {"id": 1, "columns": []}}
            if "/api/v1/chart/?" in url:
                return {"result": []}
            if "/api/v1/chart/" in url and method == "POST":
                mock_request.chart_count = getattr(mock_request, "chart_count", 0) + 1
                return {"id": 10 + mock_request.chart_count}
            if "/api/v1/chart/" in url and method == "GET":
                chart_id = int(url.rstrip("/").split("/")[-1])
                return {
                    "result": {
                        "id": chart_id,
                        "slice_name": f"Chart {chart_id}",
                        "datasource_id": 1,
                        "datasource_type": "table",
                        "viz_type": "echarts_timeseries_bar",
                        "uuid": f"u{chart_id}",
                    }
                }
            if "/api/v1/chart/" in url and method == "PUT":
                return {"result": {}}
            if "/api/v1/dashboard/?" in url:
                return {"result": []}
            if "/api/v1/dashboard/" in url and method == "POST" and "embedded" not in url:
                return {"id": 99}
            if "/api/v1/dashboard/" in url and "embedded" in url:
                return {"result": {"uuid": "embedded-uuid-99"}}
            if "/api/v1/dashboard/" in url and method == "GET":
                return {"result": {"id": 99, "slug": "executive-board"}}
            return {"result": {}}

        mock_client.request.side_effect = mock_request

        with (
            patch.object(self.writer, "_read_client", return_value=mock_client),
            patch.object(
                self.writer,
                "_create_chart_with_client",
                side_effect=[
                    CreateChartResult(success=True, chart_id=11, message="created"),
                    CreateChartResult(success=True, chart_id=12, message="created"),
                ],
            ),
        ):
            prepared = [
                (
                    ChartPlan(title="Chart 1", chart_type="bar", question="Q1"),
                    "SELECT 1",
                    VisualizationSpec(type="bar", x_axis="x", y_axis="y"),
                ),
                (
                    ChartPlan(title="Chart 2", chart_type="pie", question="Q2"),
                    "SELECT 2",
                    VisualizationSpec(type="pie", x_axis="x", y_axis="y"),
                ),
            ]
            plan = DashboardPlan(title="Executive Board", charts=[prepared[0][0], prepared[1][0]])
            res = await self.writer.create_dashboard(plan, prepared)

        self.assertTrue(res.success)
        self.assertEqual(res.dashboard_id, 99)

        # Inspect POST dashboard payload
        post_dashboard_call = [
            call
            for call in mock_client.request.call_args_list
            if call.args[0] == "POST" and call.args[1] == "/api/v1/dashboard/"
        ][0]
        payload = post_dashboard_call.args[2]
        meta = json.loads(payload["json_metadata"])
        self.assertFalse(meta["cross_filters_enabled"])
        self.assertEqual(meta["chart_configuration"], {})

    def test_visualization_service_validates_kpi_and_table(self) -> None:
        kpi_result = QueryResult(
            columns=["total_revenue"],
            rows=[{"total_revenue": 500_000.50}],
            row_count=1,
        )
        validated_kpi = self.viz_service.validate(
            VisualizationSpec(type="kpi", y_axis="total_revenue"), kpi_result
        )
        self.assertEqual(validated_kpi.type, "kpi")
        self.assertEqual(validated_kpi.y_axis, "total_revenue")

        table_result = QueryResult(
            columns=["vendor", "trips", "revenue"],
            rows=[{"vendor": "VeriFone", "trips": 100, "revenue": 2000}],
            row_count=1,
        )
        validated_table = self.viz_service.validate(VisualizationSpec(type="table"), table_result)
        self.assertEqual(validated_table.type, "table")


if __name__ == "__main__":
    unittest.main()
