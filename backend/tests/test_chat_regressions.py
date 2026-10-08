"""Regressions for future-day answers and chart history after reload."""

import asyncio
import json
import os
import sys
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:password@localhost:5432/ai_bi")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.api.ai import ai_chat
from app.schemas.ai import (
    AIChatRequest,
    AIChatResponse,
    AIIntent,
    IntentInfo,
    QueryResult,
    VisualizationSpec,
)
from app.services.chat_persistence_service import ChatPersistenceService
from app.services.future_date_service import future_date_response
from app.services.query_service import QueryService


class FutureDateTests(unittest.TestCase):
    def test_vietnamese_future_day_is_not_reported_as_zero(self):
        response = future_date_response(
            "Số lượng chuyến đi ngày 20 tháng 10 năm 2026 là bao nhiêu?",
            today=date(2026, 10, 6),
        )
        self.assertIn("20/10/2026", response.answer)
        self.assertIn("tương lai", response.answer)
        self.assertIn("chưa có dữ liệu", response.answer)
        self.assertIsNone(response.query)

    def test_other_date_formats_and_past_day(self):
        today = date(2026, 10, 6)
        self.assertIsNotNone(future_date_response("Chuyến đi 20/10/2026?", today=today))
        self.assertIsNotNone(future_date_response("Chuyến đi 2026-10-20?", today=today))
        self.assertIsNone(future_date_response("Chuyến đi 05/10/2026?", today=today))
        self.assertIsNone(future_date_response("Ngày 20/10/2026 là thứ mấy?", today=today))

    def test_future_guard_runs_before_semantic_cache(self):
        with (
            patch("app.api.ai.is_llm_enabled", return_value=True),
            patch("app.api.ai.settings.gemini_api_key", "test-key"),
            patch("app.api.ai.RLSService.get_filter_for_user", return_value=None),
            patch("app.api.ai.cache_service.get") as cache_get,
            patch(
                "app.services.chat_persistence_service.ChatPersistenceService.add_message"
            ) as add_message,
        ):
            response = asyncio.run(
                ai_chat(
                    AIChatRequest(
                        message="Số lượng chuyến đi ngày 20 tháng 10 năm 2026 là bao nhiêu?",
                        session_id="sess_future",
                    ),
                    authorization=None,
                )
            )
        self.assertIn("tương lai", response.answer)
        cache_get.assert_not_called()
        self.assertEqual(add_message.call_count, 2)
        self.assertEqual(add_message.call_args_list[1].args[1], "assistant")


class ChartHistoryTests(unittest.TestCase):
    def test_cached_chart_persists_visualization_and_rows(self):
        cached = AIChatResponse(
            answer="Doanh thu theo tháng",
            intent=IntentInfo(type=AIIntent.ASK_DATA),
            query=QueryResult(
                sql="SELECT month, revenue FROM trips",
                columns=["month", "revenue"],
                rows=[
                    {"month": "2026-09", "revenue": 120.5},
                    {"month": "2026-10", "revenue": 90.0},
                ],
                row_count=2,
            ),
            visualization=VisualizationSpec(
                type="line", title="Doanh thu theo tháng", x_axis="month", y_axis="revenue"
            ),
        )
        with (
            patch("app.api.ai.is_llm_enabled", return_value=True),
            patch("app.api.ai.settings.gemini_api_key", "test-key"),
            patch("app.api.ai.RLSService.get_filter_for_user", return_value=None),
            patch(
                "app.api.ai.cache_service.get",
                return_value={
                    "response": cached.model_dump(mode="json"),
                    "cache_type": "exact",
                    "latency_ms": 2.0,
                },
            ),
            patch(
                "app.services.chat_persistence_service.ChatPersistenceService.add_message"
            ) as add_message,
        ):
            response = asyncio.run(
                ai_chat(
                    AIChatRequest(message="Doanh thu theo từng tháng?", session_id="sess_chart"),
                    authorization=None,
                )
            )
        self.assertTrue(response.cached)
        metadata = add_message.call_args_list[1].kwargs["metadata"]
        self.assertEqual(metadata["visualization"]["type"], "line")
        self.assertEqual(len(metadata["query"]["rows"]), 2)

    def test_legacy_cached_chart_is_recovered_from_saved_rows(self):
        metadata = {
            "cached": True,
            "query": {
                "sql": "SELECT zone, trips FROM trips",
                "columns": ["zone", "trips"],
                "rows": [{"zone": "A", "trips": 12}, {"zone": "B", "trips": 8}],
                "row_count": 2,
            },
        }
        restored = ChatPersistenceService._restore_legacy_cached_chart(metadata, "Top khu vực")
        self.assertEqual(restored["visualization"]["type"], "bar")
        self.assertEqual(restored["visualization"]["y_axis"], "trips")

    def test_legacy_cached_kpi_is_recovered(self):
        metadata = {
            "cached": True,
            "query": {
                "sql": "SELECT COUNT(*) AS total_trips FROM trips",
                "columns": ["total_trips"],
                "rows": [{"total_trips": 30000}],
                "row_count": 1,
            },
        }
        restored = ChatPersistenceService._restore_legacy_cached_chart(metadata, "Số chuyến")
        self.assertEqual(restored["visualization"]["type"], "kpi")
        self.assertEqual(restored["visualization"]["y_axis"], "total_trips")

    def test_metadata_serializer_accepts_decimal_and_date(self):
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = (7, "2026-10-06 12:00:00")
        transaction = MagicMock()
        transaction.__enter__.return_value = connection
        with (
            patch.object(ChatPersistenceService, "get_session", return_value=MagicMock()),
            patch("app.services.chat_persistence_service.engine.begin", return_value=transaction),
        ):
            ChatPersistenceService.add_message(
                "sess_chart",
                "assistant",
                "Biểu đồ",
                metadata={
                    "query": {"rows": [{"month": date(2026, 9, 1), "revenue": Decimal("120.50")}]}
                },
            )
        stored = json.loads(connection.execute.call_args_list[0].args[1]["metadata_json"])
        self.assertEqual(stored["query"]["rows"][0]["month"], "2026-09-01")
        self.assertEqual(stored["query"]["rows"][0]["revenue"], 120.5)

    def test_database_result_is_chart_friendly(self):
        connection = MagicMock()
        database_result = MagicMock()
        database_result.keys.return_value = ["month", "revenue"]
        row = MagicMock()
        row._mapping = {"month": date(2026, 9, 1), "revenue": Decimal("120.50")}
        database_result.__iter__.return_value = iter([row])
        connection.execute.side_effect = [MagicMock(), MagicMock(), database_result]
        engine = MagicMock()
        engine.connect.return_value.__enter__.return_value = connection

        result = QueryService(engine=engine)._execute_sync("SELECT month, revenue FROM trips")
        self.assertEqual(result.rows, [{"month": "2026-09-01", "revenue": 120.5}])


if __name__ == "__main__":
    unittest.main()
