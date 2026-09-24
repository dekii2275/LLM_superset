import os
import sys
import unittest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:password@localhost:5432/ai_bi")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.schemas.ai import AIChatContext, AIIntent, IntentResult
from app.services.intent_service import IntentService


class IntentHeuristicTests(unittest.TestCase):
    def assert_intent(self, message: str, expected: AIIntent) -> None:
        self.assertEqual(IntentService.heuristic(message).intent, expected)

    def test_ask_data(self) -> None:
        for message in (
            "How many taxi trips are there?",
            "Show taxi trips by month as a line chart.",
            "Top 10 pickup zones?",
        ):
            with self.subTest(message=message):
                self.assert_intent(message, AIIntent.ASK_DATA)

    def test_create_chart(self) -> None:
        for message in (
            "Create a bar chart for taxi trips by month.",
            "Save this visualization as a chart.",
            "Tạo biểu đồ doanh thu theo tháng.",
        ):
            with self.subTest(message=message):
                self.assert_intent(message, AIIntent.CREATE_CHART)

    def test_create_dashboard(self) -> None:
        self.assert_intent("Create an NYC Taxi dashboard.", AIIntent.CREATE_DASHBOARD)
        self.assert_intent("Tạo dashboard tổng quan taxi.", AIIntent.CREATE_DASHBOARD)

    def test_edit_chart(self) -> None:
        self.assert_intent("Change Trips by Month to a bar chart.", AIIntent.EDIT_CHART)
        self.assert_intent("Đổi biểu đồ Trips by Month thành biểu đồ cột.", AIIntent.EDIT_CHART)

    def test_edit_dashboard(self) -> None:
        self.assert_intent("Add this chart to the NYC Taxi dashboard.", AIIntent.EDIT_DASHBOARD)
        self.assert_intent("Thêm biểu đồ payment type vào dashboard taxi.", AIIntent.EDIT_DASHBOARD)

    def test_general(self) -> None:
        for message in (
            "What datasets are available?",
            "What dashboards do I have?",
            "What columns are available?",
        ):
            with self.subTest(message=message):
                self.assert_intent(message, AIIntent.GENERAL)

    def test_only_context_can_supply_target_id(self) -> None:
        result = IntentResult(
            intent=AIIntent.EDIT_DASHBOARD,
            target_id=999,
            user_goal="Edit the dashboard",
        )
        resolved = IntentService._apply_trusted_context(
            result,
            AIChatContext(active_dashboard_id=12, active_dashboard_title="NYC Taxi Overview"),
        )
        self.assertEqual(resolved.target_id, 12)
        self.assertEqual(resolved.target_name, "NYC Taxi Overview")


if __name__ == "__main__":
    unittest.main()
