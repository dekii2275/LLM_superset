"""Dynamic schema extraction and prompt builder for Superset datasets."""

from __future__ import annotations

import logging
from typing import Any

from app.schemas.ai import DatasetSummary
from app.services.superset import SupersetClient

logger = logging.getLogger(__name__)

NYC_TAXI_FALLBACK_SCHEMA = """Available PostgreSQL analytics schema:

raw.yellow_taxi_trips
- vendor_id, tpep_pickup_datetime, tpep_dropoff_datetime, passenger_count
- trip_distance, ratecode_id, store_and_fwd_flag, pu_location_id, do_location_id
- payment_type, fare_amount, extra, mta_tax, tip_amount, tolls_amount
- improvement_surcharge, total_amount, congestion_surcharge, airport_fee
- cbd_congestion_fee, request_source, source_file, source_year, source_month, loaded_at

raw.taxi_zone_lookup
- location_id, borough, zone, service_zone

Join pickup zones with trip.pu_location_id = zone.location_id and dropoff zones
with trip.do_location_id = zone.location_id. The pickup timestamp is
tpep_pickup_datetime. payment_type is numeric (1 credit card, 2 cash, 3 no
charge, 4 dispute, 5 unknown, 0 flex fare)."""


class DatasetSchemaUnavailableError(RuntimeError):
    """The selected dataset cannot be safely queried without its metadata."""


class SchemaService:
    def __init__(self, superset_client: SupersetClient | None = None) -> None:
        self.superset = superset_client
        self._cache: dict[int, dict[str, Any]] = {}
        self._dash_mapping_cache: dict[int, tuple[int, str]] | None = None

    def _get_dataset_dashboard_mapping(self) -> dict[int, tuple[int, str]]:
        """Maps dataset_id -> (dashboard_id, dashboard_title) based on chart placement & title matching."""
        if self._dash_mapping_cache is not None:
            return self._dash_mapping_cache
        if not self.superset:
            return {1: (1, "NYC Yellow Taxi Overview"), 2: (2, "NYC Taxi Trips Analysis")}
        try:
            dashboards = self.superset.request("GET", "/api/v1/dashboard/?q=(page_size:100)").get(
                "result", []
            )
            charts = self.superset.request("GET", "/api/v1/chart/?q=(page_size:100)").get(
                "result", []
            )
            chart_ds = {
                ch.get("id"): ch.get("datasource_id")
                for ch in charts
                if isinstance(ch, dict) and ch.get("id")
            }

            dash_dataset_counts: dict[int, dict[int, int]] = {}
            dash_info: dict[int, str] = {}
            for d in dashboards:
                d_id = d.get("id")
                if not d_id:
                    continue
                dash_info[d_id] = d.get("dashboard_title") or f"Dashboard {d_id}"
                dash_dataset_counts[d_id] = {}
                d_charts = self.superset.request("GET", f"/api/v1/dashboard/{d_id}/charts").get(
                    "result", []
                )
                for ch in d_charts:
                    ds_id = ch.get("datasource_id") or chart_ds.get(ch.get("id"))
                    if ds_id:
                        dash_dataset_counts[d_id][ds_id] = (
                            dash_dataset_counts[d_id].get(ds_id, 0) + 1
                        )

            mapping: dict[int, tuple[int, str]] = {}
            datasets = self.superset.list_datasets()
            for ds in datasets:
                ds_id = ds.get("id")
                if not ds_id:
                    continue
                ds_name = (ds.get("table_name") or "").lower()
                best_dash_id = None
                best_score = -1
                for d_id, counts in dash_dataset_counts.items():
                    count = counts.get(ds_id, 0)
                    if count == 0:
                        continue
                    total_in_dash = sum(counts.values()) or 1
                    ratio = count / total_in_dash
                    score = count * 10 + ratio * 20
                    title = (dash_info.get(d_id) or "").lower()
                    if any(part in title for part in ds_name.split("_") if len(part) > 3):
                        score += 15
                    if score > best_score:
                        best_score = score
                        best_dash_id = d_id
                if best_dash_id:
                    mapping[ds_id] = (best_dash_id, dash_info[best_dash_id])

            # Apply user overrides from public.dataset_dashboard_settings
            try:
                from sqlalchemy import text

                from app.db.database import engine

                with engine.connect() as conn:
                    settings_rows = conn.execute(
                        text(
                            "SELECT dataset_id, dashboard_id, is_enabled FROM public.dataset_dashboard_settings"
                        )
                    ).fetchall()
                    for r in settings_rows:
                        did, dash_override, is_enabled = r[0], r[1], bool(r[2])
                        if not is_enabled:
                            mapping.pop(did, None)
                        elif dash_override:
                            # Verify that dashboard contains at least one chart from this dataset, or is legacy taxi
                            has_charts = (
                                dash_dataset_counts.get(dash_override, {}).get(did, 0) > 0
                            ) or (did in (1, 2) and dash_override in (1, 2))
                            if has_charts:
                                dash_title = (
                                    dash_info.get(dash_override) or f"Dashboard {dash_override}"
                                )
                                mapping[did] = (dash_override, dash_title)
                            else:
                                logger.info(
                                    "Ignoring misassigned dashboard override %s for dataset %s because dashboard contains no charts from this dataset",
                                    dash_override,
                                    did,
                                )
            except Exception:
                pass

            self._dash_mapping_cache = mapping
            return mapping
        except Exception as e:
            logger.warning(f"Error mapping datasets to dashboards: {e}")
            return {1: (1, "NYC Yellow Taxi Overview"), 2: (2, "NYC Taxi Trips Analysis")}

    def invalidate_cache(self) -> None:
        """Clear cached metadata to reflect newly created datasets and updated settings."""
        self._cache.clear()
        self._dash_mapping_cache = None

    def list_datasets(self) -> list[DatasetSummary]:
        """Fetch all datasets from Superset and map to DatasetSummary models."""
        if not self.superset:
            return [
                DatasetSummary(
                    id=1,
                    table_name="yellow_taxi_trips",
                    name="NYC Yellow Taxi Trips",
                    schema_name="raw",
                    description="Physical dataset of NYC taxi trips in raw schema",
                    column_count=25,
                    metric_count=4,
                    columns=["vendor_id", "tpep_pickup_datetime", "trip_distance", "total_amount"],
                    metrics=["Total Trips", "Gross Trip Amount"],
                    default_dashboard_id=1,
                    default_dashboard_title="NYC Yellow Taxi Overview",
                )
            ]

        try:
            raw_datasets = self.superset.list_datasets()
            dash_mapping = self._get_dataset_dashboard_mapping()
            summaries: list[DatasetSummary] = []
            for ds in raw_datasets:
                ds_id = ds.get("id")
                if not ds_id:
                    continue
                table_name = str(ds.get("table_name") or f"dataset_{ds_id}")
                ds_name = str(ds.get("name") or ds.get("table_name") or f"Dataset {ds_id}")
                schema_name = ds.get("schema")
                description = ds.get("description")

                # Fetch full details to get columns and metrics
                detail = self.get_dataset(int(ds_id)) or ds
                columns = [
                    col.get("column_name")
                    for col in detail.get("columns", [])
                    if isinstance(col, dict) and col.get("column_name")
                ]
                metrics = [
                    m.get("metric_name")
                    for m in detail.get("metrics", [])
                    if isinstance(m, dict) and m.get("metric_name")
                ]

                dash_id, dash_title = dash_mapping.get(int(ds_id), (None, None))

                summaries.append(
                    DatasetSummary(
                        id=int(ds_id),
                        table_name=table_name,
                        name=ds_name,
                        schema_name=schema_name,
                        description=description,
                        column_count=len(columns),
                        metric_count=len(metrics),
                        columns=columns[:20],
                        metrics=metrics[:10],
                        default_dashboard_id=dash_id,
                        default_dashboard_title=dash_title,
                    )
                )
            return summaries
        except Exception:
            logger.exception("list_datasets_from_superset_failed")
            return []

    def get_dataset(self, dataset_id: int) -> dict[str, Any] | None:
        """Fetch full dataset metadata from Superset, cached in memory."""
        if dataset_id in self._cache:
            return self._cache[dataset_id]

        if not self.superset:
            return None

        try:
            res = self.superset.get_dataset(dataset_id)
            ds_result = res.get("result") if isinstance(res, dict) and "result" in res else res
            if isinstance(ds_result, dict) and ds_result:
                self._cache[dataset_id] = ds_result
                return ds_result
        except Exception:
            logger.exception("get_dataset_failed dataset_id=%s", dataset_id)
        return None

    def build_schema_prompt(self, dataset_id: int | None = None) -> str:
        """Generate a concise schema context for LLM prompt generation."""
        target_id = dataset_id if dataset_id is not None else 1
        semantic_ctx = ""
        try:
            from app.services.semantic_service import SemanticService

            semantic_ctx = SemanticService.build_semantic_context(target_id)
        except Exception as e:
            logger.debug(f"Failed to load semantic context: {e}")

        # Fallback to NYC Taxi schema if no dataset or dataset 1 requested and unavailable
        if dataset_id is None or dataset_id == 1:
            # Check if dataset 1 metadata is accessible
            ds = self.get_dataset(1) if self.superset else None
            if not ds:
                if semantic_ctx:
                    return f"{NYC_TAXI_FALLBACK_SCHEMA}\n\n---\n{semantic_ctx}"
                return NYC_TAXI_FALLBACK_SCHEMA
            # For dataset 1, include taxi zone join hints for richer Text-to-SQL
            schema_str = self._format_dataset_schema(
                ds,
                extra_notes=(
                    "Join pickup zones with trip.pu_location_id = zone.location_id and dropoff zones "
                    "with trip.do_location_id = zone.location_id on raw.taxi_zone_lookup."
                ),
            )
            if semantic_ctx:
                return f"{schema_str}\n\n---\n{semantic_ctx}"
            return schema_str

        ds = self.get_dataset(dataset_id)
        if not ds:
            logger.warning("dataset_schema_unavailable dataset_id=%s", dataset_id)
            raise DatasetSchemaUnavailableError(f"Dataset {dataset_id} metadata is unavailable")

        schema_str = self._format_dataset_schema(ds)
        if semantic_ctx:
            return f"{schema_str}\n\n---\n{semantic_ctx}"
        return schema_str

    @staticmethod
    def _format_dataset_schema(ds: dict[str, Any], extra_notes: str = "") -> str:
        table_name = ds.get("table_name") or "analytics_table"
        schema_name = ds.get("schema")
        full_table = f"{schema_name}.{table_name}" if schema_name else table_name
        description = ds.get("description") or ""

        columns = ds.get("columns", [])
        metrics = ds.get("metrics", [])

        col_lines = []
        for col in columns:
            if not isinstance(col, dict):
                continue
            c_name = col.get("column_name")
            if not c_name:
                continue
            c_type = col.get("type") or "TEXT"
            c_desc = col.get("description") or ""
            is_dttm = col.get("is_dttm", False)
            type_info = f"{c_type}, temporal" if is_dttm else c_type
            if c_desc:
                col_lines.append(f"- {c_name} ({type_info}): {c_desc}")
            else:
                col_lines.append(f"- {c_name} ({type_info})")

        metric_lines = []
        for m in metrics:
            if not isinstance(m, dict):
                continue
            m_name = m.get("metric_name")
            if not m_name:
                continue
            m_expr = m.get("expression") or ""
            m_label = m.get("verbose_name") or ""
            if m_label and m_expr:
                metric_lines.append(f"- {m_name}: `{m_expr}` ({m_label})")
            elif m_expr:
                metric_lines.append(f"- {m_name}: `{m_expr}`")
            else:
                metric_lines.append(f"- {m_name}")

        is_virtual = ds.get("kind") == "virtual"
        virtual_sql = (ds.get("sql") or "").strip()

        parts = []
        if is_virtual and virtual_sql:
            parts.append(
                f"Available analytics dataset: `{table_name}` (Virtual Dataset in Superset)"
            )
            parts.append(
                f"IMPORTANT: This is a virtual dataset. You MUST query it as a Common Table Expression (CTE) or subquery:\n"
                f"WITH {table_name} AS (\n{virtual_sql}\n)"
            )
        else:
            parts.append(f"Available analytics dataset: `{full_table}`")

        if description:
            parts.append(f"Description: {description}")
        parts.append("\nColumns:")
        parts.append("\n".join(col_lines) if col_lines else "- (No columns discovered)")

        if metric_lines:
            parts.append("\nPredefined Superset Metrics:")
            parts.append("\n".join(metric_lines))

        if extra_notes:
            parts.append(f"\nNotes:\n{extra_notes}")

        return "\n".join(parts)
