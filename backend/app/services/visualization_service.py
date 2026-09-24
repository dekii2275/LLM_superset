"""Safe semantic visualization planning for returned NL2SQL result sets."""

from __future__ import annotations

from numbers import Number
from typing import Protocol

from app.schemas.ai import QueryResult, VisualizationSpec


class VisualizationPlanner(Protocol):
    async def generate_visualization(
        self, question: str, result: QueryResult
    ) -> VisualizationSpec: ...


_TIME_TOKENS = ("date", "time", "month", "week", "day", "year", "hour")
_CATEGORY_TOKENS = ("type", "zone", "borough", "payment", "vendor", "category")
_MEASURE_TOKENS = ("count", "trip", "total", "amount", "revenue", "fare", "distance", "average", "avg")


class VisualizationService:
    """Uses Gemini when available, with deterministic semantic fallback."""

    async def plan(
        self, question: str, result: QueryResult, planner: VisualizationPlanner
    ) -> VisualizationSpec:
        fallback = self.heuristic(result)
        if fallback.type == "none":
            return fallback
        try:
            candidate = await planner.generate_visualization(question, result)
        except Exception:
            # A visualization failure must never hide a successful answer/data set.
            return fallback
        return self.validate(candidate, result)

    def validate(self, spec: VisualizationSpec, result: QueryResult) -> VisualizationSpec:
        if spec.type == "none":
            return VisualizationSpec()
        if result.error or result.row_count < 2 or not result.rows:
            return VisualizationSpec()
        if not spec.x_axis or not spec.y_axis:
            return VisualizationSpec()
        if spec.x_axis not in result.columns or spec.y_axis not in result.columns:
            return VisualizationSpec()
        if not self._is_numeric_column(result, spec.y_axis):
            return VisualizationSpec()
        if spec.type == "pie" and result.row_count > 8:
            return VisualizationSpec()
        return spec

    def heuristic(self, result: QueryResult) -> VisualizationSpec:
        if result.error or result.row_count < 2 or not result.rows:
            return VisualizationSpec()

        numeric_columns = [
            column for column in result.columns if self._is_numeric_column(result, column)
        ]
        if not numeric_columns:
            return VisualizationSpec()
        y_axis = next(
            (column for column in numeric_columns if self._matches(column, _MEASURE_TOKENS)),
            numeric_columns[-1],
        )
        candidate_x = [column for column in result.columns if column != y_axis]
        time_columns = [column for column in candidate_x if self._matches(column, _TIME_TOKENS)]
        x_axis = next((column for column in time_columns if "month" in column.lower()), None)
        x_axis = x_axis or next((column for column in time_columns if "date" in column.lower()), None)
        x_axis = x_axis or (time_columns[0] if time_columns else None)
        if x_axis:
            chart_type = "line"
        else:
            x_axis = next(
                (column for column in candidate_x if not self._is_numeric_column(result, column)),
                None,
            )
            x_axis = x_axis or next(
                (column for column in candidate_x if self._matches(column, _CATEGORY_TOKENS)),
                None,
            )
            if not x_axis:
                return VisualizationSpec()
            chart_type = "pie" if result.row_count <= 8 and self._matches(x_axis, _CATEGORY_TOKENS) else "bar"

        return VisualizationSpec(
            type=chart_type,
            title=f"{self._label(y_axis)} by {self._label(x_axis)}",
            x_axis=x_axis,
            y_axis=y_axis,
            x_label=self._label(x_axis),
            y_label=self._label(y_axis),
        )

    @staticmethod
    def _is_numeric_column(result: QueryResult, column: str) -> bool:
        values = [row.get(column) for row in result.rows if row.get(column) is not None]
        return bool(values) and all(isinstance(value, Number) and not isinstance(value, bool) for value in values)

    @staticmethod
    def _matches(column: str, tokens: tuple[str, ...]) -> bool:
        lower_column = column.lower()
        return any(token in lower_column for token in tokens)

    @staticmethod
    def _label(column: str) -> str:
        return column.replace("_", " ").strip().title()
