import unittest
from unittest.mock import patch

from app.schemas.ai import (
    AIIntent,
    ChartPlan,
    EditDashboardOperation,
    EditDashboardPlan,
    IntentResult,
    QueryResult,
    SQLGenerationResult,
    VisualizationSpec,
)
from app.services.ai_bi_service import AIBIService
from app.services.schema_service import DatasetSchemaUnavailableError, SchemaService

SCHEMA = "Available analytics dataset: `public.natural_earth_populated_places`\nColumns: country, is_megacity"
SQL = (
    "SELECT country, is_megacity, COUNT(*) AS city_count "
    "FROM public.natural_earth_populated_places GROUP BY country, is_megacity"
)


class NaturalEarthSchema:
    def build_schema_prompt(self, dataset_id):
        assert dataset_id == 5
        return SCHEMA


class HeatmapGemini:
    def __init__(self, empty_first=False):
        self.empty_first = empty_first
        self.plan_schema = None
        self.sql_calls = []

    async def classify_intent(self, message):
        return IntentResult(intent=AIIntent.EDIT_DASHBOARD, user_goal=message)

    async def generate_edit_dashboard_plan(self, message, schema_context=None):
        self.plan_schema = schema_context
        return EditDashboardPlan(
            operation=EditDashboardOperation.ADD_CHART,
            dashboard_name="World Cities",
            create_chart_plan=ChartPlan(
                title="Cities by country and megacity status",
                chart_type="heatmap",
                question="Count cities by country and is_megacity",
                dimension="country",
                secondary_dimension="is_megacity",
                metric="city_count",
            ),
        )

    async def generate_sql(self, question, schema_context=None, force_data_query=False):
        self.sql_calls.append((question, schema_context, force_data_query))
        if self.empty_first and len(self.sql_calls) == 1:
            return SQLGenerationResult(intent="metadata_question", sql="")
        # A valid SQL query remains usable even if the model mislabels its intent.
        return SQLGenerationResult(intent="metadata_question", sql=SQL)

    async def generate_answer_from_result(self, question, result):
        return "Preview ready"

    async def generate_visualization(self, question, result):
        return VisualizationSpec(
            type="heatmap", x_axis="country", y_axis="is_megacity", value_axis="city_count"
        )


class HeatmapQuery:
    async def execute_query(self, sql):
        return QueryResult(
            sql=sql,
            columns=["country", "is_megacity", "city_count"],
            rows=[
                {"country": "France", "is_megacity": False, "city_count": 2},
                {"country": "Japan", "is_megacity": True, "city_count": 3},
            ],
            row_count=2,
        )


class ChartPreviewDatasetTests(unittest.IsolatedAsyncioTestCase):
    async def test_dashboard_add_chart_uses_selected_dataset_for_plan_and_preview(self):
        gemini = HeatmapGemini()
        service = AIBIService(object(), gemini, HeatmapQuery(), schema_service=NaturalEarthSchema())

        response = await service.chat("Add a heatmap to this dashboard", dataset_id=5)

        self.assertEqual(gemini.plan_schema, SCHEMA)
        self.assertEqual(len(gemini.sql_calls), 1)
        question, schema, forced = gemini.sql_calls[0]
        self.assertIn("Count cities by country and is_megacity", question)
        self.assertIn("heatmap", question)
        self.assertEqual(schema, SCHEMA)
        self.assertTrue(forced)
        self.assertEqual(
            response.pending_action.edit_dashboard_plan.create_chart_plan.dataset_id, 5
        )
        self.assertEqual(response.visualization.type, "heatmap")
        self.assertEqual(response.query.sql, SQL)

    async def test_empty_chart_sql_is_retried_with_explicit_data_request(self):
        gemini = HeatmapGemini(empty_first=True)
        service = AIBIService(object(), gemini, HeatmapQuery(), schema_service=NaturalEarthSchema())

        response = await service.chat("Add a heatmap to this dashboard", dataset_id=5)

        self.assertIsNotNone(response.pending_action)
        self.assertEqual(len(gemini.sql_calls), 2)
        self.assertIn("Return database rows", gemini.sql_calls[1][0])
        self.assertTrue(all(call[1] == SCHEMA and call[2] for call in gemini.sql_calls))

    async def test_missing_selected_dataset_never_falls_back_to_taxi(self):
        with patch(
            "app.services.semantic_service.SemanticService.build_semantic_context", return_value=""
        ):
            with self.assertRaises(DatasetSchemaUnavailableError):
                SchemaService(None).build_schema_prompt(5)

        class UnavailableSchema:
            def build_schema_prompt(self, dataset_id):
                raise DatasetSchemaUnavailableError("temporarily unavailable")

        response = await AIBIService(
            object(), HeatmapGemini(), HeatmapQuery(), schema_service=UnavailableSchema()
        ).chat("Add a heatmap", dataset_id=5)
        self.assertIsNone(response.pending_action)
        self.assertIn("Superset", response.answer)


if __name__ == "__main__":
    unittest.main()
