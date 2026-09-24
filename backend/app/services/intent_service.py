"""Intent routing for AI BI requests; write intents are planned, never executed."""

from __future__ import annotations

import logging
import re

from app.schemas.ai import AIChatContext, AIIntent, IntentResult
from app.services.gemini_service import GeminiService

logger = logging.getLogger(__name__)


class IntentService:
    def __init__(self, gemini: GeminiService) -> None:
        self.gemini = gemini

    async def classify(
        self, message: str, context: AIChatContext | None = None
    ) -> IntentResult:
        """Use Gemini first, while making routing resilient to classifier failures."""
        try:
            result = await self.gemini.classify_intent(message)
        except Exception:
            logger.exception("intent_classification_failed; using heuristic fallback")
            result = self.heuristic(message)
        return self._apply_trusted_context(result, context)

    @staticmethod
    def heuristic(message: str) -> IntentResult:
        """Small conservative fallback: uncertain requests retain the legacy data path."""
        normalized = " ".join(message.casefold().split())

        # Dashboard edits are checked before dashboard creation because an
        # instruction such as "add a chart to the dashboard" includes both nouns.
        if IntentService._matches(normalized, (
            r"\b(add|rename|change|edit|remove)\b.*\bdashboard\b",
            r"\bdashboard\b.*\b(add|rename|change|edit|remove)\b",
            r"\bthêm\b.*\bdashboard\b",
            r"\b(sửa|đổi)\b.*\bdashboard\b",
        )):
            return IntentService._fallback(AIIntent.EDIT_DASHBOARD, message, "dashboard")
        if IntentService._matches(normalized, (
            r"\b(create|make|build)\b.*\bdashboard\b",
            r"\btạo\b.*\bdashboard\b",
            r"\btạo\b.*\bbảng điều khiển\b",
        )):
            return IntentService._fallback(AIIntent.CREATE_DASHBOARD, message, "dashboard")
        if IntentService._matches(normalized, (
            r"\b(change|rename|edit|update)\b.*\bchart\b",
            r"\bchart\b.*\b(to|into)\b",
            r"\b(đổi|sửa)\b.*\bbiểu đồ\b",
        )):
            return IntentService._fallback(AIIntent.EDIT_CHART, message, "chart")
        if IntentService._matches(normalized, (
            r"\b(create|make|build|save)\b.*\b(chart|visualization)\b",
            r"\btạo\b.*\bbiểu đồ\b",
            r"\blưu\b.*\bbiểu đồ\b",
        )):
            return IntentService._fallback(AIIntent.CREATE_CHART, message, "chart")
        if IntentService._matches(normalized, (
            r"\b(what|which|list)\b.*\b(datasets?|dashboards?|charts?|columns?)\b",
            r"\b(datasets?|dashboards?|charts?|columns?)\b.*\b(available|have)\b",
            r"\b(danh sách|có những|cột nào|dataset nào|dashboard nào)\b",
        )):
            return IntentService._fallback(AIIntent.GENERAL, message)
        return IntentService._fallback(AIIntent.ASK_DATA, message)

    @staticmethod
    def _fallback(intent: AIIntent, message: str, target_type: str | None = None) -> IntentResult:
        return IntentResult(
            intent=intent,
            confidence=None,
            target_type=target_type,
            user_goal=message.strip(),
            requires_confirmation=intent not in {AIIntent.ASK_DATA, AIIntent.GENERAL},
        )

    @staticmethod
    def _matches(message: str, patterns: tuple[str, ...]) -> bool:
        return any(re.search(pattern, message) for pattern in patterns)

    @staticmethod
    def _apply_trusted_context(
        result: IntentResult, context: AIChatContext | None
    ) -> IntentResult:
        # IDs must only come from the UI/backend context, never model output.
        result.target_id = None
        if result.intent == AIIntent.EDIT_DASHBOARD and context:
            result.target_type = "dashboard"
            result.target_id = context.active_dashboard_id
            if context.active_dashboard_title:
                result.target_name = context.active_dashboard_title
        elif result.intent == AIIntent.EDIT_CHART and context:
            result.target_type = "chart"
            result.target_id = context.active_chart_id
            if context.active_chart_title:
                result.target_name = context.active_chart_title
        result.requires_confirmation = result.intent not in {AIIntent.ASK_DATA, AIIntent.GENERAL}
        return result
