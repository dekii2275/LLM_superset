"""Deterministic, query-grounded chart statistics and explanation text."""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from numbers import Number
from typing import Any

from app.schemas.ai import ChartExplanation, QueryResult, VisualizationSpec

logger = logging.getLogger(__name__)


class ChartExplanationValidationError(ValueError):
    """Raised when the supplied visualization cannot be matched to query data."""


class ChartExplanationService:
    """Calculate displayed-chart statistics without sending raw rows to Gemini."""

    def analyze(
        self, result: QueryResult, visualization: VisualizationSpec
    ) -> ChartExplanation:
        if visualization.type not in {"bar", "line", "pie", "area"}:
            raise ChartExplanationValidationError("Unsupported chart type")
        x_axis, y_axis = visualization.x_axis, visualization.y_axis
        if not x_axis or not y_axis or x_axis not in result.columns or y_axis not in result.columns:
            raise ChartExplanationValidationError("Chart axes do not match the query result")

        rows = result.rows
        points: list[tuple[Any, Decimal]] = []
        omitted_rows = 0
        for row in rows:
            value = _as_decimal(row.get(y_axis))
            category = row.get(x_axis)
            if category is None or value is None:
                omitted_rows += 1
                continue
            points.append((category, value))

        chart_title = visualization.title or f"{_label(y_axis)} theo {_label(x_axis)}"
        x_label = visualization.x_label or _label(x_axis)
        y_label = visualization.y_label or _label(y_axis)
        scope_note = self._scope_note(len(rows), len(points), omitted_rows)

        if not rows:
            explanation = ChartExplanation(
                summary=f"Truy vấn trả về 0 dòng cho biểu đồ {chart_title}.",
                highlights=[],
                note=scope_note,
            )
            return explanation

        if not points:
            explanation = ChartExplanation(
                summary=f"Không đủ giá trị số hợp lệ để phân tích {y_label} theo {x_label}.",
                highlights=[],
                note=scope_note,
            )
            return explanation

        if len(points) == 1:
            category, value = points[0]
            explanation = ChartExplanation(
                summary=f"Chỉ có một điểm dữ liệu hợp lệ; chưa đủ điểm để so sánh nhóm hoặc xác định xu hướng.",
                highlights=[f"Điểm hợp lệ duy nhất: {_label_value(category)} — {y_label} {_format_number(value)}."],
                note=scope_note,
            )
            return explanation

        if visualization.type in {"bar", "pie"}:
            highlights = self._categorical_highlights(points, y_label, visualization.type)
            summary = f"Biểu đồ {chart_title} thể hiện {y_label} theo {x_label} trên {len(points)} điểm dữ liệu hợp lệ."
        else:
            highlights, trend = self._series_highlights(points, y_label)
            summary = f"Biểu đồ {chart_title} có {len(points)} mốc theo thứ tự truy vấn; xu hướng nhìn chung {trend}."

        return ChartExplanation(summary=summary, highlights=highlights, note=scope_note)

    async def explain_with_gemini(
        self,
        base_explanation: ChartExplanation,
        chart_title: str,
        viz_type: str,
        sample_rows: list[dict[str, Any]],
        gemini: Any | None = None,
    ) -> ChartExplanation:
        """Enhance deterministic statistics with Gemini executive insights when available."""
        if not gemini or not hasattr(gemini, "generate_chart_explanation"):
            return base_explanation
        try:
            return await gemini.generate_chart_explanation(
                chart_title=chart_title,
                viz_type=viz_type,
                computed_summary=base_explanation.summary,
                computed_highlights=base_explanation.highlights,
                computed_note=base_explanation.note,
                sample_data=sample_rows,
            )
        except Exception as error:
            logger.warning("gemini_chart_explanation_fallback error=%s", error)
            return base_explanation

    @staticmethod
    def _scope_note(row_count: int, usable_count: int, omitted_rows: int) -> str:
        if row_count == 0:
            return (
                "Truy vấn trả về 0 dòng. Chưa có dữ liệu để rút ra kết luận; "
                "kết quả truy vấn có thể bị giới hạn hoặc chỉ gồm một phần dữ liệu."
            )
        note = f"Đã phân tích {usable_count} điểm hợp lệ trong {row_count} dòng kết quả truy vấn."
        if omitted_rows:
            note += f" Bỏ qua {omitted_rows} dòng thiếu nhóm hoặc giá trị số."
        note += (
            " Nhận xét chỉ áp dụng cho các dòng truy vấn trả về (có thể là top N hoặc phạm vi giới hạn), "
            "không đại diện mặc định cho toàn bộ dữ liệu và không xác định nguyên nhân."
        )
        return note

    def _categorical_highlights(
        self,
        points: list[tuple[Any, Decimal]],
        y_label: str,
        chart_type: str,
    ) -> list[str]:
        maximum = max(points, key=lambda point: point[1])
        minimum = min(points, key=lambda point: point[1])
        spread = maximum[1] - minimum[1]
        highlights = [
            f"Cao nhất: {_label_value(maximum[0])} — {y_label} {_format_number(maximum[1])}.",
            f"Thấp nhất: {_label_value(minimum[0])} — {y_label} {_format_number(minimum[1])}.",
            f"Chênh lệch giữa hai mức: {_format_number(spread)}.",
        ]

        total = sum((value for _, value in points), Decimal(0))
        all_non_negative = all(value >= 0 for _, value in points)
        if chart_type == "pie" and total > 0 and all_non_negative:
            share = maximum[1] * Decimal(100) / total
            share_text = _format_percent(share)
            total_text = _format_number(total)
            highlights.append(
                f"Nhóm {_label_value(maximum[0])} chiếm {share_text}% tổng {total_text} của các nhóm được truy vấn."
            )

        return highlights

    def _series_highlights(
        self, points: list[tuple[Any, Decimal]], y_label: str
    ) -> tuple[list[str], str]:
        first, last = points[0], points[-1]
        change = last[1] - first[1]
        trend = _linear_trend([value for _, value in points])
        highlights = [
            f"Cao nhất: {_label_value(max(points, key=lambda point: point[1])[0])} — "
            f"{y_label} {_format_number(max(value for _, value in points))}.",
            f"Thấp nhất: {_label_value(min(points, key=lambda point: point[1])[0])} — "
            f"{y_label} {_format_number(min(value for _, value in points))}.",
        ]
        if len(points) >= 2:
            direction = "tăng" if change > 0 else "giảm" if change < 0 else "không đổi"
            detail = f"{direction} {_format_number(abs(change))}"
            if first[1] > 0:
                detail += f" ({_format_percent(abs(change) * Decimal(100) / first[1])}%)"
            highlights.append(
                f"Từ {_label_value(first[0])} ({_format_number(first[1])}) đến "
                f"{_label_value(last[0])} ({_format_number(last[1])}), {detail} so với giá trị đầu chuỗi."
            )
        if len(points) >= 3:
            changes = [
                (abs(right[1] - left[1]), left, right)
                for left, right in zip(points, points[1:])
            ]
            largest_change, left, right = max(changes, key=lambda item: item[0])
            direction = "tăng" if right[1] > left[1] else "giảm" if right[1] < left[1] else "không đổi"
            highlights.append(
                f"Biến động liền kề lớn nhất: {direction} {_format_number(largest_change)} "
                f"từ {_label_value(left[0])} đến {_label_value(right[0])}."
            )

        return highlights, trend


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool) or not isinstance(value, (Number, Decimal)):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _linear_trend(values: list[Decimal]) -> str:
    if len(values) < 3:
        return "chưa đủ điểm để xác định"

    count = Decimal(len(values))
    mean_x = Decimal(len(values) - 1) / Decimal(2)
    mean_y = sum(values, Decimal(0)) / count
    denominator = sum((Decimal(index) - mean_x) ** 2 for index in range(len(values)))
    slope = sum(
        (Decimal(index) - mean_x) * (value - mean_y)
        for index, value in enumerate(values)
    ) / denominator
    value_range = max(values) - min(values)
    tolerance = max(value_range, Decimal(1)) * Decimal("0.000000001")
    if slope > tolerance:
        return "tăng"
    if slope < -tolerance:
        return "giảm"
    return "dao động nhưng chưa có hướng rõ"


def _format_number(value: Decimal) -> str:
    formatted = f"{value:,.6f}".rstrip("0").rstrip(".")
    return formatted.replace(",", "\0").replace(".", ",").replace("\0", ".")


def _format_percent(value: Decimal) -> str:
    rounded = value.quantize(Decimal("0.1"))
    return _format_number(rounded)


def _label(column: str) -> str:
    return column.replace("_", " ").strip().title()


def _label_value(value: Any) -> str:
    if hasattr(value, "isoformat"):
        value = value.isoformat()
    if isinstance(value, (int, float)) and value > 100000000000:
        try:
            from datetime import datetime
            return datetime.fromtimestamp(value / 1000.0).strftime("%Y-%m-%d")
        except Exception:
            pass
    return str(value)[:160]
