import json
import unittest
from unittest.mock import patch

from app.schemas.ai import ChartPlan, VisualizationSpec
from app.services.superset_write_service import SupersetWriteService

SQL = (
    "SELECT CASE WHEN population_max < 1000000 THEN 'Dưới 1 triệu' "
    "WHEN population_max < 5000000 THEN 'Từ 1-5 triệu' ELSE 'Trên 5 triệu' "
    "END AS population_group, COUNT(*) AS city_count "
    "FROM raw.natural_earth_populated_places GROUP BY 1"
)


class FakeSuperset:
    def __init__(self):
        self.writes = []

    def get_dataset(self, dataset_id):
        if dataset_id == 5:
            return {
                "id": 5,
                "database": {"id": 1},
                "schema": "raw",
                "table_name": "natural_earth_populated_places",
                "kind": "physical",
                "columns": [{"column_name": "population_max", "type": "BIGINT"}],
                "metrics": [{"metric_name": "count"}],
            }
        if dataset_id == 90:
            return {
                "id": 90,
                "columns": [
                    {"column_name": "population_group", "type": "TEXT"},
                    {"column_name": "city_count", "type": "BIGINT"},
                ],
            }
        raise AssertionError(dataset_id)

    def request(self, method, path, payload=None):
        if method == "GET" and path == "/api/v1/dataset/5":
            return {"result": {"id": 5}}
        if method == "GET" and path.startswith("/api/v1/chart/?"):
            return {"result": []}
        if method == "POST" and path == "/api/v1/dataset/":
            self.writes.append((path, payload))
            return {"id": 90}
        if method == "POST" and path == "/api/v1/chart/":
            self.writes.append((path, payload))
            return {"id": 91}
        raise AssertionError((method, path))


class SavedChartPreviewParityTests(unittest.TestCase):
    def setUp(self):
        self.writer = SupersetWriteService("http://superset", "http://public", "u", "p", 5)
        self.plan = ChartPlan(
            title="Số lượng đô thị theo nhóm quy mô dân số",
            chart_type="bar",
            question="Đếm thành phố theo nhóm dân số",
            dataset_id=5,
            dimension="population_group",
            metric="city_count",
        )
        self.spec = VisualizationSpec(
            type="bar",
            x_axis="population_group",
            y_axis="city_count",
        )

    def test_simple_count_groups_use_guest_safe_column_and_keep_dashboard_filters(self):
        client = FakeSuperset()
        with patch("app.services.superset_write_service.QueryService") as query_service:
            query_service.return_value.prepare_sql.return_value = SQL
            query_service.return_value.referenced_tables.return_value = {
                ("raw", "natural_earth_populated_places")
            }
            result = self.writer._create_chart_with_client(client, self.plan, SQL, self.spec)

        self.assertTrue(result.success)
        self.assertEqual(
            [path for path, _ in client.writes], ["/api/v1/dataset/", "/api/v1/chart/"]
        )
        dataset_payload, chart_payload = (item[1] for item in client.writes)
        self.assertIn("CASE WHEN population_max", dataset_payload["sql"])
        self.assertIn(
            "AS population_group FROM raw.natural_earth_populated_places", dataset_payload["sql"]
        )
        self.assertNotIn("LIMIT 100", dataset_payload["sql"])
        self.assertEqual(chart_payload["datasource_id"], 90)
        form = json.loads(chart_payload["params"])
        self.assertEqual(form["x_axis"], "population_group")
        self.assertEqual(form["metrics"], ["count"])
        self.assertFalse(form["show_legend"])
        self.assertFalse(form["zoomable"])
        context = json.loads(chart_payload["query_context"])
        self.assertEqual(context["datasource"]["id"], 90)
        self.assertTrue(context["queries"][0]["columns"][0]["isColumnReference"])
        self.assertEqual(context["queries"][0]["metrics"], ["count"])

    def test_filtered_preview_keeps_sql_in_virtual_dataset(self):
        client = FakeSuperset()
        filtered_sql = SQL.replace(" GROUP BY 1", " WHERE country = 'Japan' GROUP BY 1")
        with patch("app.services.superset_write_service.QueryService") as query_service:
            query_service.return_value.prepare_sql.return_value = filtered_sql
            query_service.return_value.referenced_tables.return_value = {
                ("raw", "natural_earth_populated_places")
            }
            result = self.writer._create_chart_with_client(
                client, self.plan, filtered_sql, self.spec
            )

        self.assertTrue(result.success)
        dataset_payload, chart_payload = (item[1] for item in client.writes)
        self.assertEqual(dataset_payload["sql"], filtered_sql)
        self.assertEqual(chart_payload["datasource_id"], 90)
        form = json.loads(chart_payload["params"])
        self.assertEqual(form["x_axis"], "population_group")
        self.assertEqual(form["metrics"][0]["column"]["column_name"], "city_count")

    def test_rejects_preview_query_from_another_dataset(self):
        client = FakeSuperset()
        with patch("app.services.superset_write_service.QueryService") as query_service:
            query_service.return_value.prepare_sql.return_value = SQL
            query_service.return_value.referenced_tables.return_value = {("private", "other_table")}
            with self.assertRaisesRegex(ValueError, "ngoài bộ dữ liệu"):
                self.writer._create_chart_with_client(client, self.plan, SQL, self.spec)
        self.assertEqual(client.writes, [])


if __name__ == "__main__":
    unittest.main()
