import os
import sys
import unittest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:password@localhost:5432/ai_bi")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.schemas.ai import QueryResult, VisualizationSpec
from app.services.visualization_service import VisualizationService


class BrokenPlanner:
    async def generate_visualization(self, question: str, result: QueryResult) -> VisualizationSpec:
        raise RuntimeError("Gemini unavailable")


class VisualizationServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.service = VisualizationService()
        self.monthly = QueryResult(
            columns=["month", "trip_count"],
            rows=[
                {"month": "2026-05", "trip_count": 4_090_836},
                {"month": "2026-06", "trip_count": 3_837_248},
                {"month": "2026-07", "trip_count": 3_530_109},
            ],
            row_count=3,
        )

    def test_accepts_valid_time_series_spec(self) -> None:
        spec = self.service.validate(
            VisualizationSpec(type="line", x_axis="month", y_axis="trip_count"), self.monthly
        )
        self.assertEqual(spec.type, "line")

    def test_invalid_axes_fall_back_to_none(self) -> None:
        invalid_x = self.service.validate(
            VisualizationSpec(type="line", x_axis="fake_column", y_axis="trip_count"), self.monthly
        )
        invalid_y = self.service.validate(
            VisualizationSpec(type="line", x_axis="month", y_axis="fake_metric"), self.monthly
        )
        self.assertEqual(invalid_x.type, "none")
        self.assertEqual(invalid_y.type, "none")

    def test_single_scalar_is_not_charted(self) -> None:
        scalar = QueryResult(
            columns=["total_trips"], rows=[{"total_trips": 11_458_193}], row_count=1
        )
        self.assertEqual(self.service.heuristic(scalar).type, "none")

    async def test_gemini_failure_uses_heuristic(self) -> None:
        spec = await self.service.plan("Trips by month", self.monthly, BrokenPlanner())
        self.assertEqual(spec.type, "line")
        self.assertEqual(spec.x_axis, "month")
        self.assertEqual(spec.y_axis, "trip_count")


if __name__ == "__main__":
    unittest.main()
