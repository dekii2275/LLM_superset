import json
import unittest
from unittest.mock import AsyncMock, Mock

from app.schemas.ai import AIChatResponse, AIIntent, IntentInfo, QueryResult, VisualizationSpec
from app.services.ai_bi_service import AIBIService
from app.services.superset_write_service import SupersetWriteService

GRID_REQUEST = (
    "Tạo biểu đồ bản đồ 3D loại deck.gl Grid với tiêu đề “Mật độ đô thị trên thế giới”. "
    "Dùng longitude và latitude. Cho xem trước biểu đồ trước khi lưu."
)


class GridChartTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_grid_request_is_not_mistaken_for_save_existing(self):
        schema = Mock()
        schema.get_dataset.return_value = {
            "schema": "raw",
            "table_name": "natural_earth_populated_places",
            "columns": [
                {"column_name": name}
                for name in ("longitude", "latitude", "population_max", "name", "country")
            ],
        }
        gemini = Mock()
        gemini.generate_chart_plan = AsyncMock(
            side_effect=AssertionError("grid path should be deterministic")
        )
        service = AIBIService(Mock(), gemini, Mock(), schema_service=schema)
        self.assertFalse(service._is_save_visualization_request(GRID_REQUEST))
        self.assertTrue(service._is_save_visualization_request("Lưu biểu đồ vừa vẽ"))
        rows = [{"longitude": 1.0, "latitude": 2.0, "population_max": 1000}]
        query = QueryResult(
            sql="SELECT longitude, latitude, population_max FROM raw.natural_earth_populated_places LIMIT 500",
            columns=list(rows[0]),
            rows=rows,
            row_count=1,
        )
        service._answer_data_question = AsyncMock(
            return_value=AIChatResponse(
                answer="Preview", query=query, visualization=VisualizationSpec(type="map")
            )
        )

        response = await service._prepare_create_chart(
            GRID_REQUEST,
            None,
            IntentInfo(type=AIIntent.CREATE_CHART),
            dataset_id=5,
        )

        self.assertIsNotNone(response.pending_action)
        self.assertEqual(response.pending_action.chart_plan.map_style, "grid")
        self.assertEqual(response.visualization.map_style, "grid")
        self.assertEqual(response.pending_action.chart_plan.title, "Mật độ đô thị trên thế giới")
        self.assertIn("LIMIT 500", service._answer_data_question.await_args.args[1])
        gemini.generate_chart_plan.assert_not_awaited()

    async def test_grid_payload_uses_spatial_columns_and_count_weights(self):
        writer = SupersetWriteService("http://superset", "http://public", "u", "p", 5)
        plan, _ = AIBIService(
            Mock(),
            Mock(),
            Mock(),
            schema_service=Mock(
                get_dataset=Mock(
                    return_value={
                        "schema": "raw",
                        "table_name": "natural_earth_populated_places",
                        "columns": [{"column_name": name} for name in ("longitude", "latitude")],
                    }
                )
            ),
        )._deck_grid_plan(GRID_REQUEST, 5)
        client = Mock()
        client.get_dataset.return_value = {
            "columns": [
                {"column_name": name} for name in ("longitude", "latitude", "population_max")
            ],
            "metrics": [{"metric_name": "count"}],
        }
        payload = writer.build_superset_chart_payload(
            plan.title,
            plan,
            VisualizationSpec(type="map"),
            client=client,
            preview_dataset=True,
        )
        form = json.loads(payload["params"])
        context = json.loads(payload["query_context"])
        self.assertEqual(payload["viz_type"], "deck_grid")
        self.assertEqual(
            form["spatial"], {"type": "latlong", "lonCol": "longitude", "latCol": "latitude"}
        )
        self.assertEqual(form["size"], "count")
        self.assertTrue(form["extruded"])
        self.assertEqual(context["queries"][0]["metrics"], ["count"])


if __name__ == "__main__":
    unittest.main()
