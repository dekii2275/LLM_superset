"""Chart SQL must be mandatory while ordinary metadata answers remain valid."""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/ai_bi")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pydantic import ValidationError

from app.schemas.ai import ChartPlan, ChartSQLGenerationResult, SQLGenerationResult
from app.services.ai_bi_service import AIBIService
from app.services.gemini_service import GeminiService


class ChartSQLContractTests(unittest.IsolatedAsyncioTestCase):
    def service(self, parsed):
        service = GeminiService.__new__(GeminiService)
        service.model = "test-model"
        service._generate_content = AsyncMock(return_value=SimpleNamespace(parsed=parsed))
        return service

    async def test_chart_sql_schema_requires_nonempty_sql(self):
        service = self.service({"intent": "data_query", "sql": "SELECT COUNT(*) FROM trips"})
        result = await service.generate_sql("Trips", force_data_query=True)
        self.assertEqual(result.sql, "SELECT COUNT(*) FROM trips")
        response_schema = service._generate_content.await_args.kwargs["config"].response_schema
        schema = response_schema.model_json_schema()
        self.assertIn("sql", schema["required"])
        self.assertEqual(schema["properties"]["sql"]["minLength"], 1)
        self.assertEqual(schema["properties"]["intent"]["const"], "data_query")

    async def test_chart_sql_rejects_empty_missing_or_metadata_result(self):
        for parsed in (
            {"intent": "data_query", "sql": ""},
            {"intent": "data_query"},
            {"intent": "metadata_question", "sql": ""},
            SQLGenerationResult(intent="data_query"),
        ):
            with self.subTest(parsed=parsed), self.assertRaises(ValidationError):
                await self.service(parsed).generate_sql("Revenue by day", force_data_query=True)

    async def test_metadata_question_can_still_return_empty_sql(self):
        result = await self.service({"intent": "metadata_question", "sql": ""}).generate_sql(
            "What datasets exist?"
        )
        self.assertEqual(result.intent, "metadata_question")
        self.assertEqual(result.sql, "")

    async def test_chart_planning_retries_invalid_provider_response_with_full_context(self):
        try:
            ChartSQLGenerationResult(sql="")
        except ValidationError as invalid:
            error = invalid
        gemini = SimpleNamespace(
            generate_sql=AsyncMock(
                side_effect=[
                    error,
                    SQLGenerationResult(intent="data_query", sql="SELECT day, revenue FROM trips"),
                ]
            )
        )
        service = AIBIService(object(), gemini, object())
        plan = ChartPlan(
            title="Revenue by day",
            chart_type="area",
            question="Sum revenue by day",
            metric="revenue",
            dimension="pickup_time",
        )
        result = await service._generate_chart_sql(plan, "Available schema")
        self.assertEqual(result.sql, "SELECT day, revenue FROM trips")
        self.assertEqual(gemini.generate_sql.await_count, 2)
        for call in gemini.generate_sql.await_args_list:
            self.assertIn("area", call.args[0])
            self.assertIn("pickup_time", call.args[0])
            self.assertTrue(call.kwargs["force_data_query"])
