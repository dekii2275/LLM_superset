import asyncio
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:password@localhost:5432/ai_bi")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.api.ai import ai_chat
from app.schemas.ai import (
    AIChatContext,
    AIChatRequest,
    AIIntent,
    ChartPlan,
    DashboardPlan,
    IntentResult,
    QueryResult,
)
from app.services.ai_bi_service import AIBIService
from app.services.superset_write_service import SupersetWriteService


def six_chart_plan() -> DashboardPlan:
    return DashboardPlan(
        title="Tổng Quan Dân Số",
        dataset_id=5,
        charts=[
            ChartPlan(
                title=f"Biểu đồ {index}",
                chart_type="bar",
                question=f"Số thành phố theo country {index}",
                dimension="country",
                metric="count",
                dataset_id=5,
            )
            for index in range(6)
        ],
    )


class FakeNaturalSchema:
    def build_schema_prompt(self, dataset_id):
        return "natural_cities(country, is_megacity, population_max)"

    def get_dataset(self, dataset_id):
        return {
            "columns": [
                {"column_name": name} for name in ("country", "is_megacity", "population_max")
            ]
        }


class FakeGemini:
    def __init__(self):
        self.classify_calls = 0

    async def classify_intent(self, message):
        self.classify_calls += 1
        return IntentResult(intent=AIIntent.CREATE_DASHBOARD, user_goal=message)

    async def generate_dashboard_plan(self, message, schema_context=None):
        return six_chart_plan()


class DashboardHeatmapTests(unittest.TestCase):
    def setUp(self):
        self.gemini = FakeGemini()
        self.service = AIBIService(
            object(), self.gemini, object(), schema_service=FakeNaturalSchema()
        )

    def test_initial_request_keeps_six_charts_and_adds_heatmap(self):
        response = asyncio.run(
            self.service.chat(
                "Tạo dashboard natural có tối thiểu 6 biểu đồ và biểu đồ nhiệt", dataset_id=5
            )
        )
        self.assertEqual(len(response.dashboard_plan.charts), 7)
        heatmap = response.dashboard_plan.charts[-1]
        self.assertEqual(heatmap.chart_type, "heatmap")
        self.assertEqual(
            (heatmap.dimension, heatmap.secondary_dimension), ("country", "is_megacity")
        )
        self.assertEqual(response.pending_action.dashboard_plan.charts[-1], heatmap)

    def test_short_followup_refines_pending_plan_without_metadata_router(self):
        response = asyncio.run(
            self.service.chat(
                "Phải có biểu đồ nhiệt nữa",
                AIChatContext(pending_dashboard_plan=six_chart_plan().model_dump(mode="json")),
                dataset_id=5,
            )
        )
        self.assertEqual(self.gemini.classify_calls, 0)
        self.assertEqual(response.intent.type, AIIntent.CREATE_DASHBOARD)
        self.assertEqual(len(response.dashboard_plan.charts), 7)
        self.assertEqual(response.dashboard_plan.charts[-1].chart_type, "heatmap")

    def test_pending_plan_followup_bypasses_semantic_cache(self):
        request = AIChatRequest(
            message="Phải có biểu đồ nhiệt nữa",
            dataset_id=5,
            context=AIChatContext(pending_dashboard_plan=six_chart_plan().model_dump(mode="json")),
        )
        with (
            patch("app.api.ai.is_llm_enabled", return_value=True),
            patch("app.api.ai.settings.gemini_api_key", "test-key"),
            patch("app.api.ai.RLSService.get_filter_for_user", return_value=None),
            patch("app.api.ai.superset_client", return_value=None),
            patch("app.api.ai.AIBIService", return_value=self.service),
            patch("app.api.ai.cache_service.get") as cache_get,
        ):
            response = asyncio.run(ai_chat(request, authorization=None))
        cache_get.assert_not_called()
        self.assertEqual(len(response.dashboard_plan.charts), 7)

    def test_old_cached_dashboard_draft_is_not_replayed(self):
        request = AIChatRequest(
            message="Tạo dashboard natural có tối thiểu 6 biểu đồ và biểu đồ nhiệt", dataset_id=5
        )
        old_cached = {
            "response": {
                "answer": "Bản nháp cũ không có biểu đồ nhiệt",
                "intent": {"type": "CREATE_DASHBOARD"},
                "dashboard_plan": six_chart_plan().model_dump(mode="json"),
            }
        }
        with (
            patch("app.api.ai.is_llm_enabled", return_value=True),
            patch("app.api.ai.settings.gemini_api_key", "test-key"),
            patch("app.api.ai.RLSService.get_filter_for_user", return_value=None),
            patch("app.api.ai.superset_client", return_value=None),
            patch("app.api.ai.AIBIService", return_value=self.service),
            patch("app.api.ai.cache_service.get", return_value=old_cached),
        ):
            response = asyncio.run(ai_chat(request, authorization=None))
        self.assertEqual(len(response.dashboard_plan.charts), 7)
        self.assertFalse(response.cached)

    def test_heatmap_preview_and_saved_superset_payload_use_two_dimensions(self):
        plan = ChartPlan(
            title="Thành phố theo quốc gia và siêu đô thị",
            chart_type="heatmap",
            question="Đếm số thành phố theo country và is_megacity",
            dimension="country",
            secondary_dimension="is_megacity",
            metric="city_count",
            dataset_id=5,
        )
        query = QueryResult(
            sql="SELECT country, is_megacity, COUNT(*) AS city_count FROM natural_cities GROUP BY 1, 2",
            columns=["country", "is_megacity", "city_count"],
            rows=[
                {"country": "Japan", "is_megacity": 1, "city_count": 3},
                {"country": "France", "is_megacity": 0, "city_count": 8},
            ],
            row_count=2,
        )
        spec = self.service._chart_visualization(plan, query, None)
        self.assertEqual(
            (spec.type, spec.x_axis, spec.y_axis, spec.value_axis),
            ("heatmap", "country", "is_megacity", "city_count"),
        )

        client = MagicMock()
        client.get_dataset.return_value = {
            "columns": [
                {"column_name": name} for name in ("country", "is_megacity", "population_max")
            ],
            "metrics": [{"metric_name": "count"}],
        }
        writer = SupersetWriteService("http://superset", "http://public", "u", "p", 5)
        payload = writer.build_superset_chart_payload(plan.title, plan, spec, client=client)
        form = json.loads(payload["params"])
        saved_query = json.loads(payload["query_context"])["queries"][0]
        self.assertEqual(payload["viz_type"], "heatmap_v2")
        self.assertEqual((form["x_axis"], form["groupby"]), ("country", "is_megacity"))
        self.assertEqual(saved_query["columns"], ["country", "is_megacity"])
        self.assertEqual(form["metric"], "count")


if __name__ == "__main__":
    unittest.main()
