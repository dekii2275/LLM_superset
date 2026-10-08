import os
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:password@localhost:5432/ai_bi")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient

from app.main import app
from app.services.chat_persistence_service import ChatMessage, ChatSession
from app.services.semantic_service import BusinessGlossaryItem, SemanticService, VerifiedMetricItem


class Phase2SemanticAndChatTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("app.services.semantic_service.engine")
    def test_semantic_service_build_context(self, mock_engine):
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        # Mock glossary rows: id, dataset_id, term, target_type, target_name, description, created_at
        glossary_row = (
            1,
            1,
            "doanh thu",
            "metric",
            "total_amount",
            "Tong tien chuyen di",
            "2026-10-05 12:00:00",
        )
        # Mock metric rows: id, dataset_id, metric_name, display_name, sql_expression, description, created_at
        metric_row = (
            1,
            1,
            "total_revenue",
            "Tổng Doanh Thu",
            "SUM(total_amount)",
            "Doanh thu thuc",
            "2026-10-05 12:00:00",
        )

        mock_conn.execute.side_effect = [
            MagicMock(fetchall=MagicMock(return_value=[glossary_row])),
            MagicMock(fetchall=MagicMock(return_value=[metric_row])),
        ]

        context = SemanticService.build_semantic_context(dataset_id=1)
        self.assertIn("Semantic Layer & Business Glossary:", context)
        self.assertIn("Tổng Doanh Thu", context)
        self.assertIn("SUM(total_amount)", context)
        self.assertIn("doanh thu", context)
        self.assertIn("total_amount", context)

    @patch("app.services.semantic_service.SemanticService.get_glossary")
    def test_get_glossary_endpoint(self, mock_get_glossary):
        mock_get_glossary.return_value = [
            BusinessGlossaryItem(
                id=1,
                dataset_id=1,
                term="doanh thu",
                target_type="metric",
                target_name="total_amount",
                description="Doanh thu",
            )
        ]
        resp = self.client.get("/api/v1/semantic/glossary?dataset_id=1")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["term"], "doanh thu")

    @patch("app.services.semantic_service.SemanticService.add_glossary_term")
    def test_add_glossary_term_endpoint(self, mock_add):
        mock_add.return_value = BusinessGlossaryItem(
            id=10,
            dataset_id=1,
            term="tip",
            target_type="column",
            target_name="tip_amount",
            description="Tien boa",
        )
        resp = self.client.post(
            "/api/v1/semantic/glossary",
            json={
                "dataset_id": 1,
                "term": "tip",
                "target_type": "column",
                "target_name": "tip_amount",
                "description": "Tien boa",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["id"], 10)

    @patch("app.services.semantic_service.SemanticService.get_verified_metrics")
    def test_get_metrics_endpoint(self, mock_get_metrics):
        mock_get_metrics.return_value = [
            VerifiedMetricItem(
                id=1,
                dataset_id=1,
                metric_name="total_revenue",
                display_name="Tổng Doanh Thu",
                sql_expression="SUM(total_amount)",
                description="Tong tien",
            )
        ]
        resp = self.client.get("/api/v1/semantic/metrics?dataset_id=1")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["metric_name"], "total_revenue")

    @patch("app.services.chat_persistence_service.ChatPersistenceService.list_sessions")
    def test_list_chat_sessions_endpoint(self, mock_list):
        mock_list.return_value = [
            ChatSession(
                id="sess_abc123",
                title="Phân tích taxi",
                dataset_id=1,
                created_at="2026-10-05 12:00:00",
                updated_at="2026-10-05 12:00:00",
            )
        ]
        resp = self.client.get("/api/v1/chat/sessions?dataset_id=1")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "sess_abc123")

    @patch("app.services.chat_persistence_service.ChatPersistenceService.get_messages")
    def test_get_chat_messages_endpoint(self, mock_get_msgs):
        mock_get_msgs.return_value = [
            ChatMessage(
                id=1,
                session_id="sess_abc123",
                sender="user",
                content="Doanh thu hom nay the nao?",
            ),
            ChatMessage(
                id=2,
                session_id="sess_abc123",
                sender="assistant",
                content="Doanh thu dat 1000 USD",
            ),
        ]
        resp = self.client.get("/api/v1/chat/sessions/sess_abc123/messages")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["sender"], "user")
        self.assertEqual(data[1]["sender"], "assistant")


if __name__ == "__main__":
    unittest.main()
