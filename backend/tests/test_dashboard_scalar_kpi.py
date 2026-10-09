"""Regression coverage for scalar KPIs in confirmed dashboard creation."""

import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/ai_bi")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.schemas.ai import (
    ChartPlan,
    DashboardPlan,
    QueryResult,
    SQLGenerationResult,
    VisualizationSpec,
)
from app.services.ai_bi_service import AIBIService
from app.services.query_service import QueryService
from app.services.superset_write_service import SupersetWriteService


class DashboardScalarKPITests(unittest.IsolatedAsyncioTestCase):
    def service(self, results):
        gemini = MagicMock()
        gemini.generate_sql = AsyncMock(
            side_effect=[SQLGenerationResult(intent="data_query", sql=r.sql) for r in results]
        )
        gemini.generate_answer_from_result = AsyncMock(return_value="Query completed.")
        # Scalar queries may receive no visualization from the model.
        gemini.generate_visualization = AsyncMock(return_value=VisualizationSpec())
        query_service = QueryService()
        query_service.execute_query = AsyncMock(side_effect=results)
        return AIBIService(object(), gemini, query_service)

    async def test_scalar_kpi_resolves_sql_expression_to_result_alias(self):
        for metric in (None, "COUNT(*)", "trip_count"):
            with self.subTest(metric=metric):
                result = QueryResult(
                    sql="SELECT COUNT(*) AS trip_count FROM raw.yellow_taxi_trips",
                    columns=["trip_count"],
                    rows=[{"trip_count": 30000}],
                    row_count=1,
                )
                plan = ChartPlan(
                    title="Total Trips", chart_type="kpi", question="Count trips", metric=metric
                )
                _, _, spec = await self.service([result]).prepare_chart_for_write(plan)
                self.assertEqual(spec.type, "kpi")
                self.assertEqual(spec.y_axis, "trip_count")

    async def test_scalar_kpi_survives_visualization_provider_failure(self):
        result = QueryResult(
            sql="SELECT SUM(total_amount) AS revenue FROM raw.yellow_taxi_trips",
            columns=["revenue"],
            rows=[{"revenue": 0}],
            row_count=1,
        )
        service = self.service([result])
        service.gemini.generate_visualization.side_effect = RuntimeError("Provider unavailable")
        _, spec = await service.prepare_chart_preview(
            ChartPlan(
                title="Revenue", chart_type="kpi", question="Revenue", metric="SUM(total_amount)"
            )
        )
        self.assertEqual(spec.y_axis, "revenue")

    async def test_invalid_or_ambiguous_scalar_still_rejected(self):
        for columns, rows in (
            (["value"], [{"value": None}]),
            (["value"], [{"value": True}]),
            (["value"], [{"value": "30000"}]),
            (["a", "b"], [{"a": 1, "b": 2}]),
        ):
            with self.subTest(rows=rows):
                result = QueryResult(sql="SELECT 1", columns=columns, rows=rows, row_count=1)
                with self.assertRaisesRegex(RuntimeError, "cannot be charted safely"):
                    await self.service([result]).prepare_chart_preview(
                        ChartPlan(
                            title="Invalid KPI",
                            chart_type="kpi",
                            question="Count",
                            metric="COUNT(*)",
                        )
                    )

    async def test_grouped_result_cannot_be_silently_reduced_to_first_row_kpi(self):
        result = QueryResult(
            sql="SELECT vendor_id, COUNT(*) AS trip_count FROM raw.yellow_taxi_trips GROUP BY vendor_id",
            columns=["vendor_id", "trip_count"],
            rows=[{"vendor_id": 1, "trip_count": 12}, {"vendor_id": 2, "trip_count": 8}],
            row_count=2,
        )
        with self.assertRaisesRegex(RuntimeError, "cannot be charted safely"):
            await self.service([result]).prepare_chart_preview(
                ChartPlan(
                    title="Trips", chart_type="kpi", question="Count trips", metric="trip_count"
                )
            )

    async def test_explicit_kpi_metric_selects_correct_column_among_multiple_aggregates(self):
        result = QueryResult(
            sql="SELECT COUNT(*) AS trip_count, SUM(total_amount) AS revenue FROM raw.yellow_taxi_trips",
            columns=["trip_count", "revenue"],
            rows=[{"trip_count": 30000, "revenue": 900000}],
            row_count=1,
        )
        _, spec = await self.service([result]).prepare_chart_preview(
            ChartPlan(title="Revenue", chart_type="kpi", question="Revenue", metric="revenue")
        )
        self.assertEqual(spec.y_axis, "revenue")

    async def test_demo_dashboard_prepares_all_five_payloads_without_model_visualization(self):
        definitions = [
            ("kpi", "COUNT(*)", None, None, ["trip_count"], [{"trip_count": 30000}]),
            ("kpi", "SUM(total_amount)", None, None, ["revenue"], [{"revenue": 900000}]),
            (
                "area",
                "revenue",
                "day",
                None,
                ["day", "revenue"],
                [{"day": "2026-07-01", "revenue": 10}, {"day": "2026-07-02", "revenue": 20}],
            ),
            (
                "heatmap",
                "trip_count",
                "vendor_id",
                "payment_type",
                ["vendor_id", "payment_type", "trip_count"],
                [
                    {"vendor_id": 1, "payment_type": 1, "trip_count": 12},
                    {"vendor_id": 2, "payment_type": 2, "trip_count": 8},
                ],
            ),
            (
                "table",
                "revenue",
                "day",
                None,
                ["day", "trip_count", "revenue"],
                [
                    {"day": "2026-07-02", "trip_count": 2, "revenue": 20},
                    {"day": "2026-07-01", "trip_count": 1, "revenue": 10},
                ],
            ),
        ]
        charts, results = [], []
        for index, (kind, metric, dimension, secondary, columns, rows) in enumerate(definitions):
            charts.append(
                ChartPlan(
                    title=f"Chart {index}",
                    chart_type=kind,
                    question=kind,
                    metric=metric,
                    dimension=dimension,
                    secondary_dimension=secondary,
                )
            )
            results.append(
                QueryResult(sql="SELECT 1", columns=columns, rows=rows, row_count=len(rows))
            )
        prepared = await self.service(results).prepare_dashboard_charts(
            DashboardPlan(title="Demo", dataset_id=1, charts=charts)
        )
        self.assertEqual(len(prepared), 5)
        writer = SupersetWriteService("http://superset", "http://public", "u", "p", 1)
        expected = [
            "big_number_total",
            "big_number_total",
            "echarts_timeseries_line",
            "heatmap_v2",
            "table",
        ]
        for (plan, _, spec), result, viz_type in zip(prepared, results, expected):
            client = MagicMock()
            client.get_dataset.return_value = {
                "columns": [{"column_name": c} for c in result.columns]
            }
            payload = writer.build_superset_chart_payload(
                plan.title, plan, spec, client, preview_dataset=True
            )
            self.assertEqual(payload["viz_type"], viz_type)
            if plan.chart_type == "kpi":
                metric_column = json.loads(payload["params"])["metric"]["column"]["column_name"]
                self.assertEqual(metric_column, result.columns[0])
