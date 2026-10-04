import json
from io import BytesIO
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.services.superset import SupersetClient


class SupersetReportContextTests(unittest.TestCase):
    def test_empty_active_tab_keeps_dashboard_level_charts_visible_below_tabs(self):
        client = SupersetClient("http://superset", "user", "password")
        positions = {
            "TABS_ID": {"id": "TABS_ID", "type": "TABS", "children": ["TAB-EMPTY"]},
            "TAB-EMPTY": {
                "id": "TAB-EMPTY",
                "type": "TAB",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "TABS_ID"],
                "meta": {"text": "lok"},
            },
            "ROW-GLOBAL": {
                "id": "ROW-GLOBAL",
                "type": "ROW",
                "children": ["CHART-50"],
                "parents": ["ROOT_ID", "GRID_ID"],
            },
            "CHART-50": {
                "id": "CHART-50",
                "type": "CHART",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW-GLOBAL"],
                "meta": {"chartId": 50},
            },
        }
        query_context = {
            "datasource": {"id": 10, "type": "table"},
            "queries": [{"columns": ["month"], "metrics": ["Total Trips"], "filters": [], "extras": {}}],
            "result_format": "json",
            "result_type": "full",
        }

        def request(method, path, payload=None, *, authenticated=True):
            if path == "/api/v1/dashboard/?q=(page:0,page_size:100)":
                return {"result": [{"id": 7, "slug": "taxi", "dashboard_title": "Taxi"}]}
            if path == "/api/v1/dashboard/7":
                return {"result": {
                    "id": 7,
                    "position_json": json.dumps(positions),
                    "json_metadata": json.dumps({"native_filter_configuration": []}),
                }}
            if path == "/api/v1/dashboard/7/charts":
                return {"result": [{"id": 50, "slice_name": "NYC Taxi — Total Trips", "viz_type": "big_number"}]}
            if path == "/api/v1/chart/50":
                return {"result": {
                    "id": 50,
                    "slice_name": "NYC Taxi — Total Trips",
                    "viz_type": "big_number",
                    "datasource_id": 10,
                    "params": json.dumps({"viz_type": "big_number"}),
                    "query_context": json.dumps(query_context),
                }}
            if path == "/api/v1/chart/data":
                return {"result": [{"status": "success", "colnames": ["trips"], "data": [{"trips": 30000}]}]}
            raise AssertionError(f"Unexpected Superset request: {path}")

        client.request = request

        report_data = client.dashboard_chart_data("taxi", ["TAB-EMPTY"], {})

        self.assertEqual(report_data["active_tab_title"], "lok")
        self.assertEqual([chart["id"] for chart in report_data["charts"]], [50])

    def test_report_data_uses_only_the_active_tab_and_current_filter(self):
        client = SupersetClient("http://superset", "user", "password")
        rows = [{"month": f"2026-{month:02d}", "trips": month} for month in range(1, 36)]
        positions = {
            "TAB-TRIPS-REVENUE": {"id": "TAB-TRIPS-REVENUE", "type": "TAB", "children": ["ROW-TRIPS"], "parents": ["ROOT_ID", "GRID_ID", "TABS_ID"], "meta": {"text": "Trips & Revenue"}},
            "ROW-TRIPS": {"id": "ROW-TRIPS", "type": "ROW", "children": ["CHART-21", "CHART-22"], "parents": ["ROOT_ID", "GRID_ID", "TABS_ID", "TAB-TRIPS-REVENUE"]},
            "CHART-21": {"id": "CHART-21", "type": "CHART", "children": [], "parents": ["ROOT_ID", "GRID_ID", "TABS_ID", "TAB-TRIPS-REVENUE", "ROW-TRIPS"], "meta": {"chartId": 21}},
            "CHART-22": {"id": "CHART-22", "type": "CHART", "children": [], "parents": ["ROOT_ID", "GRID_ID", "TABS_ID", "TAB-TRIPS-REVENUE", "ROW-TRIPS"], "meta": {"chartId": 22}},
            "TAB-TRIP-PATTERNS": {"id": "TAB-TRIP-PATTERNS", "type": "TAB", "children": ["CHART-23"], "parents": ["ROOT_ID", "GRID_ID", "TABS_ID"], "meta": {"text": "Trip Patterns"}},
            "CHART-23": {"id": "CHART-23", "type": "CHART", "children": [], "parents": ["ROOT_ID", "GRID_ID", "TABS_ID", "TAB-TRIP-PATTERNS"], "meta": {"chartId": 23}},
        }
        filters = [{
            "id": "NATIVE_FILTER-VENDOR",
            "name": "Vendor Name",
            "type": "NATIVE_FILTER",
            "filterType": "filter_select",
            "targets": [{"datasetId": 10, "column": {"name": "vendor_name"}}],
            "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
            "controlValues": {"inverseSelection": False},
        }]
        data_mask = {
            "NATIVE_FILTER-VENDOR": {
                "extraFormData": {"filters": [{"col": "vendor_name", "op": "IN", "val": ["Yellow"]}]},
                "filterState": {"value": ["Yellow"]},
            },
        }
        query_context = {
            "datasource": {"id": 10, "type": "table"},
            "queries": [{"columns": ["month"], "metrics": ["Total Trips"], "filters": [], "extras": {}}],
            "result_format": "json",
            "result_type": "full",
        }
        calls = []

        def request(method, path, payload=None, *, authenticated=True):
            calls.append((method, path, payload))
            if path == "/api/v1/dashboard/?q=(page:0,page_size:100)":
                return {"result": [{"id": 7, "slug": "taxi", "dashboard_title": "Taxi"}]}
            if path == "/api/v1/dashboard/7":
                return {"result": {
                    "id": 7,
                    "position_json": json.dumps(positions),
                    "json_metadata": json.dumps({"native_filter_configuration": filters}),
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
                    "datasource_id": 10,
                    "params": json.dumps({"viz_type": "echarts_timeseries_line"}),
                    "query_context": json.dumps(query_context),
                }}
            if path == "/api/v1/chart/data":
                self.assertEqual(payload["form_data"]["viz_type"], "echarts_timeseries_line")
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
        self.assertEqual([chart["id"] for chart in report_data["charts"]], [21, 22])
        self.assertTrue(all(chart["rows"] == rows[:30] for chart in report_data["charts"]))
        queried_charts = [path for _, path, _ in calls if path.startswith("/api/v1/chart/") and path != "/api/v1/chart/data"]
        self.assertEqual(queried_charts, ["/api/v1/chart/21", "/api/v1/chart/22"])



if __name__ == "__main__":
    unittest.main()
