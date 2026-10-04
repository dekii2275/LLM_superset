import asyncio
import base64
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.schemas.ai import DashboardReport, DashboardChartInsight
from app.services.gemini_service import GeminiService
from app.services.superset import SupersetClient
from app.api import superset as superset_api


class SupersetDashboardReportTests(unittest.TestCase):
    def test_dashboard_report_scopes_ai_and_attaches_individual_chart_screenshots(self):
        charts = [
            {"id": 21, "title": "Trips by month", "rows": []},
            {"id": 22, "title": "Revenue by month", "rows": []},
        ]
        images = {
            21: b"\x89PNG\r\n\x1a\nchart-21",
            22: b"\x89PNG\r\n\x1a\nchart-22",
        }
        client = SimpleNamespace(
            dashboard_chart_data=lambda slug, active_tabs, data_mask: {
                "dashboard_title": "Taxi",
                "dashboard_id": 7,
                "active_tab_title": "Trips & Revenue",
                "active_tabs": active_tabs,
                "data_mask": data_mask,
                "applied_filters": ["Vendor Name: Yellow"],
                "charts": charts,
            },
            dashboard_chart_screenshots=lambda dashboard_id, chart_ids, active_tabs, data_mask: {
                chart_id: images[chart_id] for chart_id in chart_ids
            },
        )

        class FakeGeminiService:
            def __init__(self, *args, **kwargs):
                pass

            async def generate_dashboard_report(self, title, report_charts, *, active_tab_title, applied_filters):
                self.title = title
                self.charts = report_charts
                return DashboardReport(
                    overview="Taxi report",
                    chart_insights=[
                        DashboardChartInsight(chart_id=chart["id"], insight=chart["title"])
                        for chart in report_charts
                    ],
                )

        with (
            patch.object(superset_api, "is_llm_enabled", return_value=True),
            patch.object(superset_api.settings, "gemini_api_key", "test-key"),
            patch.object(superset_api, "get_client", return_value=client),
            patch.object(superset_api, "GeminiService", FakeGeminiService),
        ):
            result = asyncio.run(superset_api.create_dashboard_report(SimpleNamespace(
                active_tabs=["TAB-TRIPS-REVENUE"],
                data_mask={"NATIVE_FILTER-VENDOR": {"filterState": {"value": ["Yellow"]}}},
            )))

        self.assertEqual([chart["id"] for chart in result["charts"]], [21, 22])
        self.assertEqual(result["active_tab_title"], "Trips & Revenue")
        self.assertEqual(result["applied_filters"], ["Vendor Name: Yellow"])
        self.assertEqual(
            [chart["screenshot_base64"] for chart in result["charts"]],
            [base64.b64encode(images[chart_id]).decode("ascii") for chart_id in (21, 22)],
        )
        self.assertNotIn("dashboard_screenshot_base64", result)
        self.assertEqual([item["chart_id"] for item in result["analysis"]["chart_insights"]], [21, 22])

    def test_dashboard_chart_screenshots_send_current_tab_and_filter_state(self):
        client = SupersetClient("http://superset", "user", "password")
        client.access_token = "access-token"
        png = b"\x89PNG\r\n\x1a\nindividual-chart"
        calls = []

        def request(method, path, payload=None, *, authenticated=True, timeout_seconds=15):
            calls.append((method, path, payload, timeout_seconds))
            return {"result": {"chart_images": {"21": base64.b64encode(png).decode("ascii")}}}

        client.request = request
        mask = {"NATIVE_FILTER-VENDOR": {"filterState": {"value": ["Yellow"]}}}
        images = client.dashboard_chart_screenshots(
            7, [21], ["TAB-TRIPS-REVENUE"], mask
        )

        self.assertEqual(images, {21: png})
        self.assertEqual(calls, [(
            "POST",
            "/api/v1/dashboard/7/chart_screenshots/",
            {
                "chart_ids": [21],
                "activeTabs": ["TAB-TRIPS-REVENUE"],
                "dataMask": mask,
                "anchor": "",
                "urlParams": [],
            },
            180,
        )])

    def test_gemini_usage_is_recorded_from_response_metadata(self):
        service = GeminiService.__new__(GeminiService)
        response = SimpleNamespace(usage_metadata=SimpleNamespace(total_token_count=123))

        async def generate_content(**kwargs):
            return response

        service.client = SimpleNamespace(
            aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        )

        with patch("app.services.gemini_service.record_token_usage") as record_usage:
            result = asyncio.run(service._generate_content(model="test-model", contents="hello"))

        self.assertIs(result, response)
        record_usage.assert_called_once_with(123)

    def test_dashboard_chart_data_resolves_slug_and_caps_sample_rows(self):
        client = SupersetClient("http://superset", "user", "password")
        calls = []
        rows = [{"month": f"2026-{month:02d}", "trips": month} for month in range(1, 36)]
        positions = {
            "TABS_ID": {"id": "TABS_ID", "type": "TABS", "children": ["TAB-TRIPS-REVENUE", "TAB-TRIP-PATTERNS"]},
            "TAB-TRIPS-REVENUE": {"id": "TAB-TRIPS-REVENUE", "type": "TAB", "children": ["ROW-TRIPS"], "parents": ["ROOT_ID", "GRID_ID", "TABS_ID"], "meta": {"text": "Trips & Revenue"}},
            "ROW-TRIPS": {"id": "ROW-TRIPS", "type": "ROW", "children": ["CHART-21", "CHART-22"], "parents": ["ROOT_ID", "GRID_ID", "TABS_ID", "TAB-TRIPS-REVENUE"]},
            "CHART-21": {"id": "CHART-21", "type": "CHART", "children": [], "parents": ["ROOT_ID", "GRID_ID", "TABS_ID", "TAB-TRIPS-REVENUE", "ROW-TRIPS"], "meta": {"chartId": 21}},
            "CHART-22": {"id": "CHART-22", "type": "CHART", "children": [], "parents": ["ROOT_ID", "GRID_ID", "TABS_ID", "TAB-TRIPS-REVENUE", "ROW-TRIPS"], "meta": {"chartId": 22}},
            "TAB-TRIP-PATTERNS": {"id": "TAB-TRIP-PATTERNS", "type": "TAB", "children": ["CHART-23"], "parents": ["ROOT_ID", "GRID_ID", "TABS_ID"], "meta": {"text": "Trip Patterns"}},
            "CHART-23": {"id": "CHART-23", "type": "CHART", "children": [], "parents": ["ROOT_ID", "GRID_ID", "TABS_ID", "TAB-TRIP-PATTERNS"], "meta": {"chartId": 23}},
        }
        query_context = {
            "datasource": {"id": 10, "type": "table"},
            "queries": [{"columns": ["month"], "metrics": ["Total Trips"], "filters": [], "extras": {}}],
            "result_format": "json",
            "result_type": "full",
        }
        native_filter_configuration = [{
            "id": "NATIVE_FILTER-VENDOR",
            "name": "Vendor Name",
            "type": "NATIVE_FILTER",
            "filterType": "filter_select",
            "targets": [{"datasetId": 10, "column": {"name": "vendor_name"}}],
            "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
        }]
        data_mask = {
            "NATIVE_FILTER-VENDOR": {
                "extraFormData": {"filters": [{"col": "vendor_name", "op": "IN", "val": ["Yellow"]}]},
                "filterState": {"value": ["Yellow"]},
            },
        }

        def request(method, path, payload=None, *, authenticated=True):
            calls.append((method, path, payload))
            if path == "/api/v1/dashboard/?q=(page:0,page_size:100)":
                return {"result": [{"id": 7, "slug": "taxi", "dashboard_title": "Taxi"}]}
            if path == "/api/v1/dashboard/7":
                return {"result": {
                    "id": 7,
                    "position_json": json.dumps(positions),
                    "json_metadata": json.dumps({"native_filter_configuration": native_filter_configuration}),
                }}
            if path == "/api/v1/dashboard/7/charts":
                return {"result": [
                    {"id": 21, "slice_name": "Trips by month", "viz_type": "echarts_timeseries_line"},
                    {"id": 22, "slice_name": "Revenue by month", "viz_type": "echarts_timeseries_line"},
                    {"id": 23, "slice_name": "Trips by vendor", "viz_type": "echarts_timeseries_bar"},
                ]}
            if path in {"/api/v1/chart/21", "/api/v1/chart/22"}:
                chart_id = int(path.rsplit("/", 1)[-1])
                return {"result": {
                    "id": chart_id,
                    "slice_name": "Trips by month" if chart_id == 21 else "Revenue by month",
                    "viz_type": "echarts_timeseries_line",
                    "params": json.dumps({"viz_type": "echarts_timeseries_line"}),
                    "query_context": json.dumps(query_context),
                }}
            if path == "/api/v1/chart/data":
                self.assertIn(
                    {"col": "vendor_name", "op": "IN", "val": ["Yellow"], "isExtra": True},
                    payload["queries"][0]["filters"],
                )
                return {"result": [{"status": "success", "colnames": ["month", "trips"], "data": rows}]}
            raise AssertionError(f"Unexpected Superset request: {path}")

        client.request = request

        report_data = client.dashboard_chart_data("taxi", ["TAB-TRIPS-REVENUE"], data_mask)

        self.assertEqual(report_data["dashboard_title"], "Taxi")
        self.assertEqual(report_data["active_tab_title"], "Trips & Revenue")
        self.assertEqual(report_data["active_tabs"], ["TAB-TRIPS-REVENUE"])
        self.assertEqual(report_data["applied_filters"], ["Vendor Name: Yellow"])
        self.assertEqual(report_data["charts"], [{
            "id": 21,
            "title": "Trips by month",
            "viz_type": "echarts_timeseries_line",
            "columns": ["month", "trips"],
            "rows": rows[:30],
            "row_count": 35,
            "truncated": True,
            "unavailable": False,
        }, {
            "id": 22,
            "title": "Revenue by month",
            "viz_type": "echarts_timeseries_line",
            "columns": ["month", "trips"],
            "rows": rows[:30],
            "row_count": 35,
            "truncated": True,
            "unavailable": False,
        }])
        requested_charts = [path for _, path, _ in calls if path.startswith("/api/v1/chart/")]
        self.assertEqual(requested_charts, ["/api/v1/chart/21", "/api/v1/chart/data", "/api/v1/chart/22", "/api/v1/chart/data"])

    def test_report_llm_returns_structured_overview_and_per_chart_insight(self):
        expected = DashboardReport(
            overview="Số chuyến tăng trong giai đoạn được hiển thị.",
            highlights=["Tháng cuối có nhiều chuyến nhất."],
            chart_insights=[DashboardChartInsight(chart_id=21, insight="Số chuyến tăng theo tháng.")],
        )
        models = SimpleNamespace(generate_content=None)

        async def generate_content(**kwargs):
            models.prompt = kwargs["contents"]
            return SimpleNamespace(parsed=expected)

        models.generate_content = generate_content
        service = GeminiService.__new__(GeminiService)
        service.model = "test-model"
        service.client = SimpleNamespace(aio=SimpleNamespace(models=models))

        report = asyncio.run(service.generate_dashboard_report(
            "Taxi",
            [{"id": 21, "title": "Trips by month"}],
            active_tab_title="Trips & Revenue",
            applied_filters=["Vendor Name: Yellow"],
        ))

        self.assertEqual(report, expected)
        self.assertIn('"id": 21', models.prompt)
        self.assertIn("Active tab: Trips & Revenue", models.prompt)
        self.assertIn("Vendor Name: Yellow", models.prompt)


if __name__ == "__main__":
    unittest.main()
