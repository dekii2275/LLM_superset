"""Detect explicit future dates in questions about observed BI data."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from app.schemas.ai import AIChatResponse

_DATE_PATTERNS = (
    re.compile(
        r"\b(?P<day>\d{1,2})\s+tháng\s+(?P<month>\d{1,2})\s+(?:năm\s+)?(?P<year>\d{4})\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?P<day>\d{1,2})[/.](?P<month>\d{1,2})[/.](?P<year>\d{4})\b"),
    re.compile(r"\b(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})\b"),
)
_CALENDAR_ONLY = ("thứ mấy", "ngày gì", "còn bao nhiêu ngày", "cách hôm nay bao nhiêu ngày")


def future_date_response(question: str, *, today: date | None = None) -> AIChatResponse | None:
    """Return a factual no-data answer for one explicit day that has not happened."""
    normalized = question.casefold()
    if any(phrase in normalized for phrase in _CALENDAR_ONLY):
        return None

    dates: set[date] = set()
    for pattern in _DATE_PATTERNS:
        for match in pattern.finditer(normalized):
            try:
                dates.add(date(int(match["year"]), int(match["month"]), int(match["day"])))
            except ValueError:
                continue
    if len(dates) != 1:
        return None

    requested_day = next(iter(dates))
    current_day = today or datetime.now(timezone(timedelta(hours=7))).date()
    if requested_day <= current_day:
        return None
    return AIChatResponse(
        answer=(
            f"Ngày {requested_day:%d/%m/%Y} vẫn ở tương lai "
            f"(hôm nay là {current_day:%d/%m/%Y}), nên chưa có dữ liệu thực tế cho ngày này."
        )
    )
