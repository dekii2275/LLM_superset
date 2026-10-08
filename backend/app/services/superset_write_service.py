"""Narrow, server-controlled Superset REST write path for Task 4 charts."""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from app.schemas.ai import (
    ChartPlan,
    CreateChartResult,
    CreateDashboardResult,
    DashboardPlan,
    EditChartOperation,
    EditChartPlan,
    EditDashboardOperation,
    EditDashboardPlan,
    UpdateChartResult,
    UpdateDashboardResult,
    VisualizationSpec,
)
from app.services.query_service import QueryService, _tokens
from app.services.superset import SupersetClient, SupersetEmbedError

logger = logging.getLogger(__name__)


class SupersetWriteService:
    """Server-controlled Superset REST writes for confirmed chart/dashboard actions."""

    def __init__(
        self,
        base_url: str,
        public_url: str,
        username: str | None,
        password: str | None,
        dataset_id: int,
        frontend_origins: str = "",
    ) -> None:
        self.base_url = base_url
        self.public_url = public_url.rstrip("/")
        self.username = username
        self.password = password
        self.dataset_id = dataset_id
        self.frontend_origins = [
            origin.strip() for origin in frontend_origins.split(",") if origin.strip()
        ]

    async def create_chart(
        self, chart_plan: ChartPlan, sql: str, visualization: VisualizationSpec
    ) -> CreateChartResult:
        if not self.username or not self.password:
            return CreateChartResult(
                success=False,
                message="Không thể xác thực với Superset.",
                error="Superset credentials are not configured.",
            )
        try:
            client = SupersetClient(self.base_url, self.username, self.password)
            client.login()
            self._verify_dataset(client)
            return self._create_chart_with_client(client, chart_plan, sql, visualization)
        except SupersetEmbedError:
            logger.exception("superset_chart_create_failed")
            return CreateChartResult(
                success=False,
                message="Không thể tạo biểu đồ trong Superset.",
                error="Superset API request failed.",
            )
        except ValueError as error:
            return CreateChartResult(success=False, message=str(error), error=str(error))

    async def create_dashboard(
        self,
        dashboard_plan: DashboardPlan,
        prepared_charts: list[tuple[ChartPlan, str, VisualizationSpec]],
    ) -> CreateDashboardResult:
        """Create 2–8 verified charts and one dashboard using Executive Layout Hierarchy."""
        if not 2 <= len(prepared_charts) <= 8:
            return CreateDashboardResult(
                success=False,
                message="Dashboard yêu cầu từ 2 đến 8 biểu đồ hợp lệ.",
                error="Invalid prepared chart count.",
            )
        try:
            client = self._read_client()
            target_ds_id = dashboard_plan.dataset_id or (
                dashboard_plan.charts[0].dataset_id if dashboard_plan.charts else self.dataset_id
            )
            self._verify_dataset(client, target_ds_id)
            details: list[dict[str, Any]] = []
            ids: list[int] = []
            for chart_plan, sql, visualization in prepared_charts:
                if not chart_plan.dataset_id:
                    chart_plan.dataset_id = target_ds_id
                created = self._create_chart_with_client(client, chart_plan, sql, visualization)
                if not created.success or created.chart_id is None:
                    raise ValueError(created.error or created.message)
                ids.append(created.chart_id)
                details.append(
                    client.request("GET", f"/api/v1/chart/{created.chart_id}").get("result", {})
                )
            title = self._unique_dashboard_title(client, dashboard_plan.title)
            layout = self.build_dashboard_layout(title, details)
            metadata = {
                "positions": layout,
                "timed_refresh_immune_slices": [],
                "expanded_slices": {},
                "refresh_frequency": 0,
                "default_filters": "{}",
                "color_scheme": None,
                "label_colors": {},
                # Programmatically generated cross-filter metadata kept the
                # Natural Earth dashboard on Superset's loading spinner. Keep
                # it disabled until this metadata can be validated by Superset.
                "cross_filters_enabled": False,
                "chart_configuration": {},
                "filter_scopes": {},
            }
            created = client.request(
                "POST",
                "/api/v1/dashboard/",
                {
                    "dashboard_title": title,
                    "slug": self._slug(title),
                    "published": True,
                    "position_json": json.dumps(layout),
                    "json_metadata": json.dumps(metadata),
                },
            )
            dashboard_id = self._created_dashboard_id(client, created, title)
            for chart in details:
                self._set_chart_dashboard_relation(client, chart, dashboard_id, attach=True)
            dashboard = client.request("GET", f"/api/v1/dashboard/{dashboard_id}").get("result", {})
            embedded = client.request(
                "POST",
                f"/api/v1/dashboard/{dashboard_id}/embedded",
                {"allowed_domains": self.frontend_origins},
            ).get("result", {})
            return CreateDashboardResult(
                success=True,
                dashboard_id=dashboard_id,
                dashboard_uuid=str(embedded.get("uuid")) if embedded.get("uuid") else None,
                dashboard_name=title,
                chart_ids=ids,
                url=f"{self.public_url}/superset/dashboard/{dashboard.get('slug') or self._slug(title)}/",
                message="Dashboard created successfully.",
            )
        except (SupersetEmbedError, KeyError, ValueError) as error:
            logger.exception("superset_dashboard_create_failed")
            return CreateDashboardResult(
                success=False, message="Không thể tạo dashboard trong Superset.", error=str(error)
            )

    async def resolve_chart(self, chart_id: int | None, chart_name: str | None) -> dict[str, Any]:
        return self._resolve_chart(self._read_client(), chart_id, chart_name)

    async def resolve_dashboard(
        self, dashboard_id: int | None, dashboard_name: str | None
    ) -> dict[str, Any]:
        return self._resolve_dashboard(self._read_client(), dashboard_id, dashboard_name)

    async def edit_chart(self, plan: EditChartPlan) -> UpdateChartResult:
        try:
            client = self._read_client()
            chart = self._resolve_chart(client, plan.chart_id, plan.chart_name)
            self._verify_chart_dataset(chart)
            target_dataset_id = int(chart.get("datasource_id") or self.dataset_id)
            dataset_meta = None
            try:
                dataset_meta = client.get_dataset(target_dataset_id)
            except Exception:
                pass
            form_data, query_context = (
                self._json_object(chart.get("params")),
                self._json_object(chart.get("query_context")),
            )
            title = str(chart.get("slice_name") or "Chart")
            chart_type = self._semantic_chart_type(
                str(chart.get("viz_type") or form_data.get("viz_type") or "")
            )
            dimension = self._chart_dimension(form_data, query_context)
            metric = self._chart_metric(form_data, query_context)
            if plan.operation == EditChartOperation.RENAME_CHART:
                if not plan.new_title:
                    raise ValueError("A new chart title is required.")
                title = plan.new_title.strip()
            elif plan.operation == EditChartOperation.CHANGE_CHART_TYPE:
                if plan.new_chart_type not in {"bar", "line", "pie"}:
                    raise ValueError(
                        "Loại biểu đồ này chưa được hỗ trợ trong bản demo. Chỉ hỗ trợ bar, line hoặc pie."
                    )
                chart_type = plan.new_chart_type
            elif plan.operation == EditChartOperation.CHANGE_METRIC:
                if not plan.new_metric:
                    raise ValueError("A new chart metric is required.")
                metric = self._dataset_metric(
                    plan.new_metric, dataset_meta=dataset_meta, dataset_id=target_dataset_id
                )
            elif plan.operation == EditChartOperation.CHANGE_DIMENSION:
                if not plan.new_dimension:
                    raise ValueError("A new chart dimension is required.")
                dimension = self._dataset_dimension(
                    plan.new_dimension, dataset_meta=dataset_meta, dataset_id=target_dataset_id
                )
            else:
                raise ValueError("Unsupported chart edit operation.")
            updated_form, updated_query, viz_type = self._edited_chart_config(
                form_data,
                query_context,
                chart_type,
                dimension,
                metric,
                dataset_id=target_dataset_id,
            )
            client.request(
                "PUT",
                f"/api/v1/chart/{chart['id']}",
                self._chart_update_payload(chart, title, viz_type, updated_form, updated_query),
            )
            return UpdateChartResult(
                success=True,
                chart_id=int(chart["id"]),
                chart_name=title,
                url=f"{self.public_url}/explore/?slice_id={chart['id']}",
                message="Chart updated successfully.",
            )
        except (SupersetEmbedError, KeyError, ValueError) as error:
            logger.exception("superset_chart_update_failed")
            return UpdateChartResult(
                success=False,
                message="Không thể cập nhật biểu đồ trong Superset.",
                error=str(error),
            )

    async def edit_dashboard(
        self,
        plan: EditDashboardPlan,
        prepared_new_chart: tuple[ChartPlan, str, VisualizationSpec] | None = None,
    ) -> UpdateDashboardResult:
        try:
            client = self._read_client()
            dashboard = self._resolve_dashboard(client, plan.dashboard_id, plan.dashboard_name)
            dashboard_id, title = (
                int(dashboard["id"]),
                str(dashboard.get("dashboard_title") or "Dashboard"),
            )
            charts = self._dashboard_charts(client, dashboard_id)
            if plan.operation == EditDashboardOperation.RENAME_DASHBOARD:
                if not plan.new_title:
                    raise ValueError("A new dashboard title is required.")
                title = plan.new_title.strip()
            elif plan.operation == EditDashboardOperation.ADD_CHART:
                if prepared_new_chart:
                    chart_plan, sql, visualization = prepared_new_chart
                    created = self._create_chart_with_client(client, chart_plan, sql, visualization)
                    if not created.success or created.chart_id is None:
                        raise ValueError(created.error or created.message)
                    selected = client.request("GET", f"/api/v1/chart/{created.chart_id}").get(
                        "result", {}
                    )
                else:
                    selected = self._resolve_chart(client, plan.chart_id, plan.chart_name)
                if any(int(item["id"]) == int(selected["id"]) for item in charts):
                    raise ValueError("Chart is already attached to this dashboard.")
                self._set_chart_dashboard_relation(client, selected, dashboard_id, attach=True)
                charts.append(selected)
            elif plan.operation == EditDashboardOperation.REMOVE_CHART:
                selected = self._resolve_chart(client, plan.chart_id, plan.chart_name)
                if not any(int(item["id"]) == int(selected["id"]) for item in charts):
                    raise ValueError("Chart is not attached to this dashboard.")
                self._set_chart_dashboard_relation(client, selected, dashboard_id, attach=False)
                charts = [item for item in charts if int(item["id"]) != int(selected["id"])]
            else:
                raise ValueError("Unsupported dashboard edit operation.")
            self._update_dashboard_layout(client, dashboard, title, charts)
            refreshed = client.request("GET", f"/api/v1/dashboard/{dashboard_id}").get("result", {})
            return UpdateDashboardResult(
                success=True,
                dashboard_id=dashboard_id,
                dashboard_name=title,
                chart_ids=[int(item["id"]) for item in charts],
                url=f"{self.public_url}/superset/dashboard/{refreshed.get('slug') or dashboard.get('slug') or self._slug(title)}/",
                message="Dashboard updated successfully.",
            )
        except (SupersetEmbedError, KeyError, ValueError) as error:
            logger.exception("superset_dashboard_update_failed")
            return UpdateDashboardResult(
                success=False,
                message="Không thể cập nhật dashboard trong Superset.",
                error=str(error),
            )

    def _create_chart_with_client(
        self,
        client: SupersetClient,
        chart_plan: ChartPlan,
        sql: str,
        visualization: VisualizationSpec,
    ) -> CreateChartResult:
        target_dataset_id = chart_plan.dataset_id or self.dataset_id
        self._verify_dataset(client, target_dataset_id)
        title = self._unique_title(client, chart_plan.title)
        case_axis = self._simple_case_count_axis(sql, chart_plan, visualization)
        if case_axis:
            source_meta = client.get_dataset(target_dataset_id)
            metric_names = {
                str(item.get("metric_name")).casefold()
                for item in source_meta.get("metrics", [])
                if isinstance(item, dict)
            }
            schema = str(source_meta.get("schema") or "")
            table = str(source_meta.get("table_name") or "")
            if (
                "count" in metric_names
                and not source_meta.get("sql")
                and re.fullmatch(r"[A-Za-z_]\w*", schema)
                and re.fullmatch(r"[A-Za-z_]\w*", table)
            ):
                self._verified_preview_sql(client, target_dataset_id, sql)
                virtual_dataset_id = self._create_case_group_dataset(
                    client,
                    target_dataset_id,
                    schema,
                    table,
                    case_axis,
                    visualization.x_axis,
                )
                saved_plan = chart_plan.model_copy(
                    update={"dataset_id": virtual_dataset_id, "metric": "count"}
                )
                saved_visualization = visualization.model_copy(update={"y_axis": "count"})
                try:
                    payload = self.build_superset_chart_payload(
                        title,
                        saved_plan,
                        saved_visualization,
                        client=client,
                    )
                    form = json.loads(payload["params"])
                    form.update({"metrics": ["count"], "show_legend": False, "zoomable": False})
                    context = json.loads(payload["query_context"])
                    context["queries"][0].update(
                        {
                            "metrics": ["count"],
                            "orderby": [["count", False]],
                        }
                    )
                    payload["params"] = json.dumps(form, ensure_ascii=False, sort_keys=True)
                    payload["query_context"] = json.dumps(
                        context, ensure_ascii=False, sort_keys=True
                    )
                    created = client.request("POST", "/api/v1/chart/", payload)
                except Exception:
                    try:
                        client.request("DELETE", f"/api/v1/dataset/{virtual_dataset_id}")
                    except Exception:
                        logger.warning(
                            "case_group_dataset_cleanup_failed dataset_id=%s", virtual_dataset_id
                        )
                    raise
                chart_id = self._created_chart_id(client, created, title)
                return CreateChartResult(
                    success=True,
                    chart_id=chart_id,
                    chart_name=title,
                    url=f"{self.public_url}/explore/?slice_id={chart_id}",
                    message="Chart created successfully.",
                )

        virtual_dataset_id = self._create_preview_dataset(client, target_dataset_id, title, sql)
        saved_plan = chart_plan.model_copy(update={"dataset_id": virtual_dataset_id})
        try:
            payload = self.build_superset_chart_payload(
                title, saved_plan, visualization, client=client, preview_dataset=True
            )
            created = client.request("POST", "/api/v1/chart/", payload)
        except Exception:
            try:
                client.request("DELETE", f"/api/v1/dataset/{virtual_dataset_id}")
            except Exception:
                logger.warning("preview_dataset_cleanup_failed dataset_id=%s", virtual_dataset_id)
            raise
        chart_id = self._created_chart_id(client, created, title)
        logger.info(
            "superset_chart_created chart_id=%s title=%r viz_type=%s dataset_id=%s",
            chart_id,
            title,
            payload["viz_type"],
            target_dataset_id,
        )
        return CreateChartResult(
            success=True,
            chart_id=chart_id,
            chart_name=title,
            url=f"{self.public_url}/explore/?slice_id={chart_id}",
            message="Chart created successfully.",
        )

    def _create_preview_dataset(
        self, client: SupersetClient, source_id: int, title: str, sql: str
    ) -> int:
        """Keep the verified preview transformation as a live Superset source."""
        source, safe_sql = self._verified_preview_sql(client, source_id, sql)
        database = source.get("database") or {}
        database_id = database.get("id") if isinstance(database, dict) else database
        dataset_name = f"ai_chart_{source_id}_{uuid.uuid4().hex[:12]}"
        created = client.request(
            "POST",
            "/api/v1/dataset/",
            {
                "database": int(database_id),
                "schema": source.get("schema"),
                "table_name": dataset_name,
                "sql": safe_sql,
            },
        )
        dataset_id = created.get("id")
        if not dataset_id:
            raise ValueError("Superset không trả về ID cho nguồn dữ liệu của biểu đồ.")
        logger.info(
            "chart_preview_dataset_created dataset_id=%s source_id=%s title=%r",
            dataset_id,
            source_id,
            title,
        )
        return int(dataset_id)

    @staticmethod
    def _simple_case_count_axis(
        sql: str, chart_plan: ChartPlan, visualization: VisualizationSpec
    ) -> str | None:
        """Preserve a simple count-by-CASE on the physical dataset and its filters."""
        if chart_plan.chart_type != "bar" or not visualization.x_axis or not visualization.y_axis:
            return None
        if any(
            token.value in {"where", "having", "join", "with", "union", "intersect", "except"}
            for token in _tokens(sql)
        ):
            return None
        match = re.match(
            r"\s*SELECT\s+(CASE\b.*?\bEND)\s+AS\s+([A-Za-z_]\w*)\s*,\s*"
            r"COUNT\s*\(\s*\*\s*\)\s+AS\s+([A-Za-z_]\w*)\s+FROM\s+",
            sql,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match or "group" not in [token.value for token in _tokens(sql)]:
            return None
        if (
            match.group(2).casefold() != visualization.x_axis.casefold()
            or match.group(3).casefold() != visualization.y_axis.casefold()
        ):
            return None
        return match.group(1)

    def _create_case_group_dataset(
        self,
        client: SupersetClient,
        source_id: int,
        schema: str,
        table: str,
        expression: str,
        axis: str,
    ) -> int:
        """Expose a CASE category as a normal column without limiting source rows."""
        source = client.get_dataset(source_id)
        database = source.get("database") or {}
        database_id = database.get("id") if isinstance(database, dict) else database
        if not database_id or not re.fullmatch(r"[A-Za-z_]\w*", axis):
            raise ValueError("Invalid source for population-group chart.")
        dataset_sql = f"SELECT *, {expression} AS {axis} FROM {schema}.{table}"
        if QueryService().referenced_tables(dataset_sql) != {(schema, table)}:
            raise ValueError("The chart category uses a table outside the selected dataset.")
        created = client.request(
            "POST",
            "/api/v1/dataset/",
            {
                "database": int(database_id),
                "schema": schema,
                "table_name": f"ai_chart_{source_id}_{uuid.uuid4().hex[:12]}",
                "sql": dataset_sql,
            },
        )
        dataset_id = created.get("id")
        if not dataset_id:
            raise ValueError("Superset did not return a dataset ID for the chart.")
        return int(dataset_id)

    @staticmethod
    def _verified_preview_sql(
        client: SupersetClient, source_id: int, sql: str
    ) -> tuple[dict[str, Any], str]:
        source = client.get_dataset(source_id)
        database = source.get("database") or {}
        database_id = database.get("id") if isinstance(database, dict) else database
        if not database_id or not source.get("table_name"):
            raise ValueError("Không thể đọc nguồn dữ liệu của biểu đồ.")

        query_service = QueryService()
        try:
            safe_sql = query_service.prepare_sql(sql)
            allowed = (
                query_service.referenced_tables(source["sql"])
                if source.get("sql")
                else {(str(source.get("schema") or ""), str(source["table_name"]))}
            )
            actual = query_service.referenced_tables(safe_sql)
        except Exception as error:
            raise ValueError("Không thể xác minh nguồn dữ liệu của truy vấn preview.") from error
        if source_id in (1, 2):
            allowed.add(("raw", "taxi_zone_lookup"))
        if not actual or not actual.issubset(allowed):
            raise ValueError("Truy vấn preview dùng bảng ngoài bộ dữ liệu đang chọn.")
        return source, safe_sql

    def build_superset_chart_payload(
        self,
        title: str,
        chart_plan: ChartPlan,
        visualization: VisualizationSpec,
        client: SupersetClient | None = None,
        preview_dataset: bool = False,
    ) -> dict[str, Any]:
        target_dataset_id = chart_plan.dataset_id or self.dataset_id
        dataset_meta = None
        if client:
            try:
                dataset_meta = client.get_dataset(target_dataset_id)
            except Exception:
                pass
        chart_type = chart_plan.chart_type
        measure = (
            visualization.value_axis if chart_type == "heatmap" else visualization.y_axis
        ) or chart_plan.metric
        if preview_dataset:
            columns = {
                str(item.get("column_name"))
                for item in (dataset_meta or {}).get("columns", [])
                if isinstance(item, dict)
            }
            dimension = visualization.x_axis or chart_plan.dimension
            if (chart_type not in {"kpi", "table", "map"} and dimension not in columns) or (
                chart_type != "table"
                and measure
                and measure not in columns
                and not (chart_type == "map" and measure == "count")
            ):
                raise ValueError("Cột của preview không có trong nguồn dữ liệu Superset.")
            metric = (
                "count"
                if chart_type == "map" and measure == "count"
                else {
                    "expressionType": "SIMPLE",
                    "column": {"column_name": measure},
                    "aggregate": "SUM",
                    "label": f"SUM({measure})",
                }
                if measure
                else "count"
            )
        else:
            dimension = self._dataset_dimension(
                visualization.x_axis or chart_plan.dimension,
                dataset_meta=dataset_meta,
                dataset_id=target_dataset_id,
            )
            metric = self._dataset_metric(
                measure,
                dataset_meta=dataset_meta,
                dataset_id=target_dataset_id,
            )
        row_limit = chart_plan.limit or 100
        source = f"{target_dataset_id}__table"
        if chart_type == "heatmap":
            second_dimension = (
                (visualization.y_axis or chart_plan.secondary_dimension)
                if preview_dataset
                else self._dataset_dimension(
                    visualization.y_axis or chart_plan.secondary_dimension,
                    dataset_meta=dataset_meta,
                    dataset_id=target_dataset_id,
                )
            )
            if (
                not second_dimension
                or second_dimension == dimension
                or (preview_dataset and second_dimension not in columns)
            ):
                raise ValueError("Biểu đồ nhiệt cần hai chiều dữ liệu khác nhau.")
            viz_type = "heatmap_v2"
            form_data = {
                "datasource": source,
                "viz_type": viz_type,
                "x_axis": dimension,
                "groupby": second_dimension,
                "metric": metric,
                "row_limit": min(row_limit, 500),
                "normalize_across": "heatmap",
                "show_legend": True,
                "show_values": True,
                "legend_type": "continuous",
            }
            query = self._query_context_query(
                dimension, metric, min(row_limit, 500), time_series=False
            )
            query["columns"] = [dimension, second_dimension]
        elif chart_type == "pie":
            viz_type = "pie"
            form_data: dict[str, Any] = {
                "datasource": source,
                "viz_type": viz_type,
                "groupby": [dimension],
                "metric": metric,
                "color_scheme": "supersetColors",
                "show_labels": True,
                "show_legend": True,
                "legend_orientation": "bottom",
                "label_type": "key_percent",
                "sort_by_metric": True,
                "row_limit": min(row_limit, 100),
                "donut": True,
                "inner_radius": 45,
                "labels_outside": True,
                "rich_tooltip": True,
            }
            query = self._query_context_query(dimension, metric, row_limit, time_series=False)
        elif chart_type in {"line", "area"}:
            viz_type = "echarts_timeseries_line"
            time_dimension = (
                "tpep_pickup_datetime"
                if dimension in {"source_month", "tpep_pickup_datetime"}
                else dimension
            )
            form_data = {
                "datasource": source,
                "viz_type": viz_type,
                "metrics": [metric],
                "x_axis": time_dimension,
                "granularity_sqla": time_dimension,
                "time_grain_sqla": "P1D",
                "time_range": "No filter",
                "row_limit": row_limit,
                "show_legend": False,
                "area": chart_type == "area",
                "opacity": 0.25 if chart_type == "area" else 0.0,
                "zoomable": True,
                "rich_tooltip": True,
            }
            query = self._query_context_query(time_dimension, metric, row_limit, time_series=True)
        elif chart_type == "kpi":
            viz_type = "big_number_total"
            form_data = {
                "datasource": source,
                "viz_type": viz_type,
                "metric": metric,
                "subheader": title,
                "row_limit": 1,
                "y_axis_format": ",.2s",
                "header_font_size": 0.35,
                "subheader_font_size": 0.15,
            }
            query = {
                "columns": [],
                "metrics": [metric],
                "granularity": None,
                "time_range": "No filter",
                "row_limit": 1,
                "extras": {"where": "", "having": "", "time_grain_sqla": None},
                "is_timeseries": False,
                "order_desc": True,
            }
        elif chart_type == "table":
            viz_type = "table"
            if preview_dataset:
                output_columns = [
                    str(item["column_name"])
                    for item in (dataset_meta or {}).get("columns", [])
                    if isinstance(item, dict) and item.get("column_name")
                ]
                form_data = {
                    "datasource": source,
                    "viz_type": viz_type,
                    "query_mode": "raw",
                    "all_columns": output_columns,
                    "row_limit": row_limit,
                    "include_search": True,
                    "page_length": 10,
                }
                query = {
                    "columns": output_columns,
                    "metrics": [],
                    "row_limit": row_limit,
                    "time_range": "No filter",
                    "is_timeseries": False,
                    "extras": {"where": "", "having": "", "time_grain_sqla": None},
                }
            else:
                form_data = {
                    "datasource": source,
                    "viz_type": viz_type,
                    "groupby": [dimension] if dimension else [],
                    "metrics": [metric],
                    "row_limit": row_limit,
                    "include_search": True,
                    "page_length": 10,
                    "order_desc": True,
                    "table_timestamp_format": "smart_date",
                }
                query = self._query_context_query(dimension, metric, row_limit, time_series=False)
        elif chart_type == "scatter":
            viz_type = "echarts_timeseries_scatter"
            form_data = {
                "datasource": source,
                "viz_type": viz_type,
                "metrics": [metric],
                "x_axis": dimension,
                "row_limit": row_limit,
            }
            query = self._query_context_query(dimension, metric, row_limit, time_series=False)
        elif chart_type == "map":
            cols = [
                str(c.get("column_name") or "")
                for c in (dataset_meta or {}).get("columns", [])
                if isinstance(c, dict) and c.get("column_name")
            ]
            has_lat = any(c.casefold() in {"latitude", "lat"} for c in cols)
            has_lon = any(c.casefold() in {"longitude", "lon", "lng"} for c in cols)
            lat_col = next((c for c in cols if c.casefold() in {"latitude", "lat"}), "latitude")
            lon_col = next(
                (c for c in cols if c.casefold() in {"longitude", "lon", "lng"}), "longitude"
            )
            has_country_iso = any(
                c.casefold() in {"country_iso_a2", "country_code", "iso_a2", "country_iso"}
                for c in cols
            )
            iso_col = next(
                (
                    c
                    for c in cols
                    if c.casefold() in {"country_iso_a2", "country_code", "iso_a2", "country_iso"}
                ),
                "country_iso_a2",
            )

            dim_lower = (dimension or "").casefold()
            prefer_country = any(term in dim_lower for term in ("country", "quoc_gia", "iso"))

            if chart_plan.map_style == "grid":
                if not has_lat or not has_lon:
                    raise ValueError("deck.gl Grid requires latitude and longitude columns.")
                viz_type = "deck_grid"
                form_data = {
                    "datasource": source,
                    "viz_type": viz_type,
                    "spatial": {"type": "latlong", "lonCol": lon_col, "latCol": lat_col},
                    "size": "count",
                    "grid_size": 120,
                    "extruded": True,
                    "autozoom": False,
                    "mapbox_style": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                    "row_limit": min(row_limit if chart_plan.limit else 500, 500),
                    "viewport": {
                        "longitude": 0,
                        "latitude": 20,
                        "zoom": 1.5,
                        "pitch": 45,
                        "bearing": 0,
                    },
                    "groupby": [],
                }
                query = {
                    "columns": [lon_col, lat_col],
                    "metrics": ["count"],
                    "row_limit": min(row_limit if chart_plan.limit else 500, 500),
                }
            elif prefer_country and has_country_iso:
                viz_type = "world_map"
                form_data = {
                    "datasource": source,
                    "viz_type": viz_type,
                    "entity": iso_col,
                    "country_fieldtype": "cca2",
                    "metric": metric,
                    "max_bubble_size": "25",
                    "row_limit": min(row_limit, 1000),
                }
                query = {
                    "columns": [iso_col],
                    "metrics": [metric],
                    "row_limit": min(row_limit, 1000),
                }
            elif has_lat and has_lon:
                viz_type = "deck_scatter"
                form_data = {
                    "datasource": source,
                    "viz_type": viz_type,
                    "spatial": {"type": "latlong", "lonCol": lon_col, "latCol": lat_col},
                    "point_radius_fixed": {"type": "fix", "value": 2000},
                    "point_size": metric,
                    "row_limit": min(row_limit, 2000),
                    "viewport": {
                        "longitude": 0,
                        "latitude": 20,
                        "zoom": 1.5,
                        "pitch": 0,
                        "bearing": 0,
                    },
                }
                query = {
                    "columns": [lon_col, lat_col],
                    "metrics": [metric],
                    "row_limit": min(row_limit, 2000),
                }
            elif has_country_iso:
                viz_type = "world_map"
                form_data = {
                    "datasource": source,
                    "viz_type": viz_type,
                    "entity": iso_col,
                    "country_fieldtype": "cca2",
                    "metric": metric,
                    "max_bubble_size": "25",
                    "row_limit": min(row_limit, 1000),
                }
                query = {
                    "columns": [iso_col],
                    "metrics": [metric],
                    "row_limit": min(row_limit, 1000),
                }
            else:
                viz_type = "echarts_timeseries_bar"
                form_data = {
                    "datasource": source,
                    "viz_type": viz_type,
                    "metrics": [metric],
                    "x_axis": dimension,
                    "groupby": [],
                    "columns": [],
                    "x_axis_sort_series_type": "name",
                    "x_axis_sort_series_ascending": True,
                    "row_limit": row_limit,
                    "order_desc": True,
                    "color_scheme": "echartsColors",
                    "zoomable": True,
                    "rich_tooltip": True,
                    "show_value": True,
                    "y_axis_format": ",.2s",
                }
                query = self._query_context_query(
                    dimension, metric, row_limit, time_series=False, echarts_axis=True
                )
        else:
            viz_type = "echarts_timeseries_bar"
            form_data = {
                "datasource": source,
                "viz_type": viz_type,
                "metrics": [metric],
                "x_axis": dimension,
                "groupby": [],
                "columns": [],
                "x_axis_sort_series_type": "name",
                "x_axis_sort_series_ascending": True,
                "row_limit": row_limit,
                "order_desc": True,
                "color_scheme": "echartsColors",
                "zoomable": True,
                "rich_tooltip": True,
                "show_value": True,
                "y_axis_format": ",.2s",
            }
            query = self._query_context_query(
                dimension, metric, row_limit, time_series=False, echarts_axis=True
            )

        query_context = {
            "datasource": {"id": target_dataset_id, "type": "table"},
            "queries": [query],
            "result_format": "json",
            "result_type": "full",
        }
        return {
            "slice_name": title,
            "datasource_id": target_dataset_id,
            "datasource_type": "table",
            "viz_type": viz_type,
            "description": f"Created by AI BI Assistant: {chart_plan.question}",
            "params": json.dumps(form_data, ensure_ascii=False, sort_keys=True),
            "query_context": json.dumps(query_context, ensure_ascii=False, sort_keys=True),
        }

    def _verify_dataset(self, client: SupersetClient, dataset_id: int | None = None) -> None:
        target_id = dataset_id or self.dataset_id
        result = client.request("GET", f"/api/v1/dataset/{target_id}").get("result", {})
        if not result or not result.get("id"):
            raise ValueError(f"Configured Superset dataset {target_id} is unavailable.")

    def _read_client(self) -> SupersetClient:
        if not self.username or not self.password:
            raise ValueError("Superset credentials are not configured.")
        client = SupersetClient(self.base_url, self.username, self.password)
        client.login()
        return client

    @staticmethod
    def _json_object(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if not value:
            return {}
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise ValueError("Saved Superset configuration is invalid.")
        return parsed

    def _resolve_chart(
        self, client: SupersetClient, chart_id: int | None, chart_name: str | None
    ) -> dict[str, Any]:
        if chart_id:
            chart = client.request("GET", f"/api/v1/chart/{chart_id}").get("result", {})
            if not chart or int(chart.get("id", 0)) != chart_id:
                raise ValueError(f"Không tìm thấy biểu đồ ID {chart_id}.")
            return chart
        return self._resolve_named_asset(
            client, "/api/v1/chart/?q=(page:0,page_size:100)", chart_name, "slice_name", "biểu đồ"
        )

    def _resolve_dashboard(
        self, client: SupersetClient, dashboard_id: int | None, dashboard_name: str | None
    ) -> dict[str, Any]:
        if dashboard_id:
            dashboard = client.request("GET", f"/api/v1/dashboard/{dashboard_id}").get("result", {})
            if not dashboard or int(dashboard.get("id", 0)) != dashboard_id:
                raise ValueError(f"Không tìm thấy dashboard ID {dashboard_id}.")
            return dashboard
        return self._resolve_named_asset(
            client,
            "/api/v1/dashboard/?q=(page:0,page_size:100)",
            dashboard_name,
            "dashboard_title",
            "dashboard",
        )

    @staticmethod
    def _resolve_named_asset(
        client: SupersetClient, url: str, name: str | None, field: str, label: str
    ) -> dict[str, Any]:
        if not name:
            raise ValueError(f"Hãy chọn {label} cần cập nhật.")
        assets = client.request("GET", url).get("result", [])
        wanted = name.strip().casefold()
        exact = [asset for asset in assets if str(asset.get(field, "")).casefold() == wanted]
        if len(exact) == 1:
            return client.request("GET", f"{url.split('?')[0].rstrip('/')}/{exact[0]['id']}").get(
                "result", exact[0]
            )
        close = [asset for asset in assets if wanted in str(asset.get(field, "")).casefold()]
        if len(close) == 1:
            return client.request("GET", f"{url.split('?')[0].rstrip('/')}/{close[0]['id']}").get(
                "result", close[0]
            )
        if len(close) > 1 or len(exact) > 1:
            raise ValueError(f"Tên {label} '{name}' chưa đủ rõ; hãy chọn đúng tên.")
        raise ValueError(f"Không tìm thấy {label} '{name}'.")

    def _verify_chart_dataset(self, chart: dict[str, Any]) -> None:
        datasource_id = int(chart.get("datasource_id") or 0)
        if datasource_id <= 0 or chart.get("datasource_type") != "table":
            raise ValueError("Chart does not use a valid Superset table dataset.")

    @staticmethod
    def _semantic_chart_type(viz_type: str) -> str:
        if viz_type == "pie":
            return "pie"
        if viz_type == "echarts_timeseries_line":
            return "line"
        if viz_type == "echarts_timeseries_bar":
            return "bar"
        if viz_type in {"big_number_total", "big_number"}:
            return "kpi"
        if viz_type == "table":
            return "table"
        if viz_type == "echarts_timeseries_scatter":
            return "scatter"
        if viz_type in {"world_map", "deck_scatter", "deck_grid"}:
            return "map"
        raise ValueError("This saved chart type is not supported by the demo editor.")

    @staticmethod
    def _chart_dimension(form: dict[str, Any], query_context: dict[str, Any]) -> str:
        value = (form.get("groupby") or [None])[0] or form.get("x_axis")
        if value:
            return str(value)
        queries = query_context.get("queries") or [{}]
        return str((queries[0].get("columns") or ["pu_location_id"])[0] or "pu_location_id")

    @staticmethod
    def _chart_metric(form: dict[str, Any], query_context: dict[str, Any]) -> str:
        value = form.get("metric") or (form.get("metrics") or [None])[0]
        if value:
            return str(value)
        queries = query_context.get("queries") or [{}]
        return str((queries[0].get("metrics") or ["count"])[0] or "count")

    def _edited_chart_config(
        self,
        form: dict[str, Any],
        query_context: dict[str, Any],
        chart_type: str,
        dimension: str,
        metric: Any,
        dataset_id: int | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], str]:
        target_ds_id = dataset_id or self.dataset_id
        updated = dict(form)
        updated["datasource"] = f"{target_ds_id}__table"
        row_limit = int(updated.get("row_limit") or 100)
        if chart_type == "pie":
            viz_type = "pie"
            updated.update(
                {
                    "viz_type": viz_type,
                    "groupby": [dimension],
                    "metric": metric,
                    "row_limit": min(row_limit, 100),
                }
            )
            updated.pop("metrics", None)
            updated.pop("x_axis", None)
            query = self._query_context_query(dimension, metric, row_limit, time_series=False)
        elif chart_type in {"line", "area"}:
            viz_type = "echarts_timeseries_line"
            time_dimension = (
                "tpep_pickup_datetime"
                if (dimension == "source_month" and target_ds_id in (1, 2))
                else dimension
            )
            updated.update(
                {
                    "viz_type": viz_type,
                    "metrics": [metric],
                    "x_axis": time_dimension,
                    "granularity_sqla": time_dimension,
                    "row_limit": row_limit,
                    "area": chart_type == "area",
                }
            )
            updated.pop("groupby", None)
            updated.pop("metric", None)
            query = self._query_context_query(time_dimension, metric, row_limit, time_series=True)
        elif chart_type == "kpi":
            viz_type = "big_number_total"
            updated.update({"viz_type": viz_type, "metric": metric, "row_limit": 1})
            updated.pop("groupby", None)
            updated.pop("metrics", None)
            updated.pop("x_axis", None)
            query = {
                "columns": [],
                "metrics": [metric],
                "granularity": None,
                "time_range": "No filter",
                "row_limit": 1,
                "extras": {"where": "", "having": "", "time_grain_sqla": None},
                "is_timeseries": False,
                "order_desc": True,
            }
        elif chart_type == "table":
            viz_type = "table"
            updated.update(
                {
                    "viz_type": viz_type,
                    "groupby": [dimension] if dimension else [],
                    "metrics": [metric],
                    "row_limit": row_limit,
                    "include_search": True,
                    "page_length": 25,
                }
            )
            updated.pop("x_axis", None)
            query = self._query_context_query(dimension, metric, row_limit, time_series=False)
        elif chart_type == "scatter":
            viz_type = "echarts_timeseries_scatter"
            updated.update(
                {
                    "viz_type": viz_type,
                    "metrics": [metric],
                    "x_axis": dimension,
                    "row_limit": row_limit,
                }
            )
            updated.pop("groupby", None)
            updated.pop("metric", None)
            query = self._query_context_query(dimension, metric, row_limit, time_series=False)
        else:
            viz_type = "echarts_timeseries_bar"
            updated.update(
                {
                    "viz_type": viz_type,
                    "metrics": [metric],
                    "x_axis": dimension,
                    "groupby": [],
                    "columns": [],
                    "row_limit": row_limit,
                }
            )
            updated.pop("metric", None)
            query = self._query_context_query(
                dimension, metric, row_limit, time_series=False, echarts_axis=True
            )
        updated_context = dict(query_context)
        updated_context.update(
            {
                "datasource": {"id": target_ds_id, "type": "table"},
                "queries": [query],
                "result_format": updated_context.get("result_format", "json"),
                "result_type": updated_context.get("result_type", "full"),
            }
        )
        return updated, updated_context, viz_type

    @staticmethod
    def _dashboard_ids(chart: dict[str, Any]) -> list[int]:
        values = chart.get("dashboards") or []
        return [int(value["id"] if isinstance(value, dict) else value) for value in values]

    def _chart_update_payload(
        self,
        chart: dict[str, Any],
        title: str,
        viz_type: str,
        form: dict[str, Any],
        query_context: dict[str, Any],
    ) -> dict[str, Any]:
        datasource_id = int(chart.get("datasource_id") or self.dataset_id)
        return {
            "slice_name": title,
            "datasource_id": datasource_id,
            "datasource_type": "table",
            "viz_type": viz_type,
            "description": chart.get("description") or "",
            "dashboards": self._dashboard_ids(chart),
            "params": json.dumps(form, ensure_ascii=False, sort_keys=True),
            "query_context": json.dumps(query_context, ensure_ascii=False, sort_keys=True),
        }

    def _set_chart_dashboard_relation(
        self, client: SupersetClient, chart: dict[str, Any], dashboard_id: int, *, attach: bool
    ) -> None:
        ids = set(self._dashboard_ids(chart))
        if attach:
            ids.add(dashboard_id)
        else:
            ids.discard(dashboard_id)
        form, context = (
            self._json_object(chart.get("params")),
            self._json_object(chart.get("query_context")),
        )
        client.request(
            "PUT",
            f"/api/v1/chart/{chart['id']}",
            {
                "slice_name": chart["slice_name"],
                "datasource_id": chart["datasource_id"],
                "datasource_type": chart["datasource_type"],
                "viz_type": chart["viz_type"],
                "description": chart.get("description") or "",
                "dashboards": sorted(ids),
                "params": json.dumps(form, ensure_ascii=False, sort_keys=True),
                "query_context": json.dumps(context, ensure_ascii=False, sort_keys=True),
            },
        )

    @staticmethod
    def _dashboard_charts(client: SupersetClient, dashboard_id: int) -> list[dict[str, Any]]:
        return client.request("GET", f"/api/v1/dashboard/{dashboard_id}/charts").get("result", [])

    def _update_dashboard_layout(
        self,
        client: SupersetClient,
        dashboard: dict[str, Any],
        title: str,
        charts: list[dict[str, Any]],
    ) -> None:
        layout = self._preserve_dashboard_layout(dashboard, title, charts)
        metadata = self._json_object(dashboard.get("json_metadata"))
        metadata["positions"] = layout
        client.request(
            "PUT",
            f"/api/v1/dashboard/{dashboard['id']}",
            {
                "dashboard_title": title,
                "slug": dashboard.get("slug") or self._slug(title),
                "published": bool(dashboard.get("published", True)),
                "position_json": json.dumps(layout, ensure_ascii=False),
                "json_metadata": json.dumps(metadata, ensure_ascii=False),
            },
        )

    def _preserve_dashboard_layout(
        self, dashboard: dict[str, Any], title: str, charts: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Keep the native layout and append newly attached charts at its end."""
        try:
            layout = self._json_object(dashboard.get("position_json"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return self.build_dashboard_layout(title, charts)

        grid_id = next(
            (
                key
                for key, node in layout.items()
                if isinstance(node, dict) and node.get("type") == "GRID"
            ),
            None,
        )
        if grid_id is None or not isinstance(layout.get(grid_id, {}).get("children"), list):
            return self.build_dashboard_layout(title, charts)

        for node in layout.values():
            if isinstance(node, dict) and node.get("type") == "HEADER":
                node.setdefault("meta", {})["text"] = title

        chart_by_id = {int(chart["id"]): chart for chart in charts}
        removed_node_ids = [
            key
            for key, node in layout.items()
            if isinstance(node, dict)
            and node.get("type") == "CHART"
            and self._chart_id_from_position(node) not in chart_by_id
        ]
        self._remove_layout_nodes(layout, removed_node_ids)

        positioned_chart_ids = self._layout_chart_ids(layout)
        for chart in charts:
            chart_id = int(chart["id"])
            if chart_id not in positioned_chart_ids:
                self._append_chart_at_end(layout, grid_id, chart)

        return layout

    @staticmethod
    def _chart_id_from_position(node: dict[str, Any]) -> int | None:
        try:
            return int((node.get("meta") or {}).get("chartId"))
        except (TypeError, ValueError):
            return None

    def _layout_chart_ids(self, layout: dict[str, Any]) -> set[int]:
        return {
            chart_id
            for node in layout.values()
            if isinstance(node, dict) and node.get("type") == "CHART"
            for chart_id in [self._chart_id_from_position(node)]
            if chart_id is not None
        }

    @staticmethod
    def _remove_layout_nodes(layout: dict[str, Any], node_ids: list[str]) -> None:
        if not node_ids:
            return
        removed = set(node_ids)
        for node in layout.values():
            if isinstance(node, dict) and isinstance(node.get("children"), list):
                node["children"] = [child for child in node["children"] if child not in removed]
        for node_id in node_ids:
            layout.pop(node_id, None)

        empty_rows = [
            key
            for key, node in layout.items()
            if isinstance(node, dict) and node.get("type") == "ROW" and not node.get("children")
        ]
        if empty_rows:
            SupersetWriteService._remove_layout_nodes(layout, empty_rows)

    @staticmethod
    def _next_position_id(layout: dict[str, Any], base: str) -> str:
        if base not in layout:
            return base
        suffix = 2
        while f"{base}-{suffix}" in layout:
            suffix += 1
        return f"{base}-{suffix}"

    def _append_chart_at_end(
        self, layout: dict[str, Any], grid_id: str, chart: dict[str, Any]
    ) -> None:
        chart_id = int(chart["id"])
        row_id = self._next_position_id(layout, f"ROW-AI-{chart_id}")
        chart_key = self._next_position_id(layout, f"CHART-{chart_id}")
        layout[chart_key] = {
            "id": chart_key,
            "type": "CHART",
            "children": [],
            "parents": ["ROOT_ID", grid_id, row_id],
            "meta": {
                "chartId": chart_id,
                "sliceName": chart["slice_name"],
                "uuid": chart.get("uuid"),
                "width": 12,
                "height": 50,
            },
        }
        layout[row_id] = {
            "id": row_id,
            "type": "ROW",
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
            "children": [chart_key],
            "parents": ["ROOT_ID", grid_id],
        }
        layout[grid_id]["children"].append(row_id)

    def _unique_title(self, client: SupersetClient, requested: str) -> str:
        existing = {
            str(chart.get("slice_name", "")).casefold()
            for chart in client.request("GET", "/api/v1/chart/?q=(page:0,page_size:100)").get(
                "result", []
            )
        }
        title = requested.strip()
        if title.casefold() not in existing:
            return title
        suffix = 2
        while f"{title} ({suffix})".casefold() in existing:
            suffix += 1
        return f"{title} ({suffix})"

    def _created_chart_id(self, client: SupersetClient, created: dict[str, Any], title: str) -> int:
        direct_id = created.get("id") or created.get("result", {}).get("id")
        if direct_id is not None:
            return int(direct_id)
        for chart in client.request("GET", "/api/v1/chart/?q=(page:0,page_size:100)").get(
            "result", []
        ):
            if chart.get("slice_name") == title:
                return int(chart["id"])
        raise ValueError("Superset created the chart but did not return its ID.")

    def _unique_dashboard_title(self, client: SupersetClient, requested: str) -> str:
        existing = {
            str(dashboard.get("dashboard_title", "")).casefold()
            for dashboard in client.request(
                "GET", "/api/v1/dashboard/?q=(page:0,page_size:100)"
            ).get("result", [])
        }
        title = requested.strip()
        if title.casefold() not in existing:
            return title
        suffix = 2
        while f"{title} ({suffix})".casefold() in existing:
            suffix += 1
        return f"{title} ({suffix})"

    @staticmethod
    def _created_dashboard_id(client: SupersetClient, created: dict[str, Any], title: str) -> int:
        direct_id = created.get("id") or created.get("result", {}).get("id")
        if direct_id is not None:
            return int(direct_id)
        for dashboard in client.request("GET", "/api/v1/dashboard/?q=(page:0,page_size:100)").get(
            "result", []
        ):
            if dashboard.get("dashboard_title") == title:
                return int(dashboard["id"])
        raise ValueError("Superset created the dashboard but did not return its ID.")

    @staticmethod
    def _slug(title: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")
        return slug[:120] or "ai-bi-dashboard"

    @staticmethod
    def _chart_viz_type(chart: dict[str, Any]) -> str:
        viz = chart.get("viz_type")
        if not viz and "params" in chart:
            try:
                params = (
                    json.loads(chart["params"])
                    if isinstance(chart["params"], str)
                    else chart["params"]
                )
                viz = params.get("viz_type")
            except Exception:
                pass
        return str(viz or "").strip()

    @classmethod
    def build_dashboard_layout(cls, title: str, charts: list[dict[str, Any]]) -> dict[str, Any]:
        if not charts:
            raise ValueError("Dashboard layout requires at least one chart.")

        has_typed_charts = any(bool(cls._chart_viz_type(c)) for c in charts)
        if has_typed_charts:
            kpis = [
                c for c in charts if cls._chart_viz_type(c) in {"big_number_total", "big_number"}
            ]
            maps = [
                c
                for c in charts
                if cls._chart_viz_type(c) in {"world_map", "deck_scatter", "deck_grid"}
            ]
            trends = [c for c in charts if cls._chart_viz_type(c) in {"echarts_timeseries_line"}]
            breakdowns = [
                c for c in charts if cls._chart_viz_type(c) in {"echarts_timeseries_bar", "pie"}
            ]
            details = [
                c
                for c in charts
                if c not in kpis and c not in maps and c not in trends and c not in breakdowns
            ]

            arranged_rows: list[tuple[list[dict[str, Any]], int, int]] = []

            # Tier 1: Executive KPI Cards (compact height 26, width auto-split 3, 4, 6, 12)
            if kpis:
                chunk_size = 4
                for i in range(0, len(kpis), chunk_size):
                    chunk = kpis[i : i + chunk_size]
                    w = max(3, 12 // len(chunk))
                    arranged_rows.append((chunk, w, 26))

            # Tier 2: Spatial / Map Visualizations (height 55, width 12 if single, 6 if 2)
            if maps:
                chunk_size = 2 if len(maps) > 1 else 1
                for i in range(0, len(maps), chunk_size):
                    chunk = maps[i : i + chunk_size]
                    w = 12 if len(chunk) == 1 else 6
                    arranged_rows.append((chunk, w, 55))

            # Tier 3: Time Trends (Line / Area, height 50)
            if trends:
                chunk_size = 2 if len(trends) > 1 else 1
                for i in range(0, len(trends), chunk_size):
                    chunk = trends[i : i + chunk_size]
                    w = 12 if len(chunk) == 1 else 6
                    arranged_rows.append((chunk, w, 50))

            # Tier 4: Breakdowns (Bar / Pie, height 50)
            if breakdowns:
                chunk_size = 2
                for i in range(0, len(breakdowns), chunk_size):
                    chunk = breakdowns[i : i + chunk_size]
                    w = 12 if len(chunk) == 1 else 6
                    arranged_rows.append((chunk, w, 50))

            # Tier 5: Details (Tables / Scatter / Other, height 50)
            if details:
                chunk_size = 1 if any(cls._chart_viz_type(c) == "table" for c in details) else 2
                for i in range(0, len(details), chunk_size):
                    chunk = details[i : i + chunk_size]
                    w = 12 if len(chunk) == 1 else 6
                    arranged_rows.append((chunk, w, 50))

            if arranged_rows:
                row_ids = [f"ROW-{index + 1}" for index in range(len(arranged_rows))]
                positions: dict[str, Any] = {
                    "DASHBOARD_VERSION_KEY": "v2",
                    "ROOT_ID": {"id": "ROOT_ID", "type": "ROOT", "children": ["GRID_ID"]},
                    "GRID_ID": {
                        "id": "GRID_ID",
                        "type": "GRID",
                        "parents": ["ROOT_ID"],
                        "children": row_ids,
                    },
                    "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": title}},
                }
                for row_id, (row_charts, width, height) in zip(row_ids, arranged_rows):
                    chart_keys: list[str] = []
                    for chart in row_charts:
                        chart_key = f"CHART-{chart['id']}"
                        chart_keys.append(chart_key)
                        positions[chart_key] = {
                            "id": chart_key,
                            "type": "CHART",
                            "children": [],
                            "parents": ["ROOT_ID", "GRID_ID", row_id],
                            "meta": {
                                "chartId": int(chart["id"]),
                                "sliceName": chart["slice_name"],
                                "uuid": chart.get("uuid"),
                                "width": width,
                                "height": height,
                            },
                        }
                    positions[row_id] = {
                        "id": row_id,
                        "type": "ROW",
                        "meta": {"background": "BACKGROUND_TRANSPARENT"},
                        "children": chart_keys,
                        "parents": ["ROOT_ID", "GRID_ID"],
                    }
                return positions

        # Default fallback: 2 charts per row
        rows = [charts[index : index + 2] for index in range(0, len(charts), 2)]
        row_ids = [f"ROW-{index + 1}" for index in range(len(rows))]
        positions = {
            "DASHBOARD_VERSION_KEY": "v2",
            "ROOT_ID": {"id": "ROOT_ID", "type": "ROOT", "children": ["GRID_ID"]},
            "GRID_ID": {
                "id": "GRID_ID",
                "type": "GRID",
                "parents": ["ROOT_ID"],
                "children": row_ids,
            },
            "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": title}},
        }
        for row_id, row_charts in zip(row_ids, rows):
            chart_keys = []
            width = 12 if len(row_charts) == 1 else 6
            for chart in row_charts:
                chart_key = f"CHART-{chart['id']}"
                chart_keys.append(chart_key)
                positions[chart_key] = {
                    "id": chart_key,
                    "type": "CHART",
                    "children": [],
                    "parents": ["ROOT_ID", "GRID_ID", row_id],
                    "meta": {
                        "chartId": int(chart["id"]),
                        "sliceName": chart["slice_name"],
                        "uuid": chart.get("uuid"),
                        "width": width,
                        "height": 50,
                    },
                }
            positions[row_id] = {
                "id": row_id,
                "type": "ROW",
                "meta": {"background": "BACKGROUND_TRANSPARENT"},
                "children": chart_keys,
                "parents": ["ROOT_ID", "GRID_ID"],
            }
        return positions

    def _dataset_dimension(
        self,
        value: str | None,
        dataset_meta: dict[str, Any] | None = None,
        dataset_id: int | None = None,
    ) -> str:
        target_id = dataset_id or self.dataset_id
        val_str = (value or "").strip()
        normalized = val_str.casefold()

        # For taxi dataset (ID 1, 2) backward-compatibility
        if target_id in (1, 2) or dataset_meta is None:
            if "zone" in normalized or "pickup" in normalized:
                return "pu_location_id"
            if "payment" in normalized:
                return "payment_type"
            if any(token in normalized for token in ("month", "date", "time")):
                return "source_month"
            allowed = {
                "vendor_id",
                "passenger_count",
                "ratecode_id",
                "payment_type",
                "pu_location_id",
                "do_location_id",
                "source_month",
            }
            if val_str in allowed:
                return val_str
            if target_id in (1, 2) and dataset_meta is None:
                raise ValueError(
                    "The requested chart dimension is not supported by the taxi dataset."
                )

        # For any dataset with metadata
        if dataset_meta:
            cols = [
                str(c.get("column_name") or "")
                for c in dataset_meta.get("columns", [])
                if isinstance(c, dict) and c.get("column_name")
            ]
            # 1. Exact match
            for c in cols:
                if c.casefold() == normalized:
                    return c
            # 2. Substring match
            for c in cols:
                if normalized and (normalized in c.casefold() or c.casefold() in normalized):
                    return c
            # 3. Token match (e.g. "country" in "country_iso_a2", "pop" in "population_max")
            norm_tokens = [t for t in re.split(r"[_\s]+", normalized) if t]
            for c in cols:
                c_tokens = [t for t in re.split(r"[_\s]+", c.casefold()) if t]
                if any(
                    t in c_tokens or any(t in ct or ct in t for ct in c_tokens) for t in norm_tokens
                ):
                    return c
            # 4. If val_str is strictly one of the existing columns
            if val_str and val_str in cols:
                return val_str
            # 5. Non-ID categorical column fallback
            non_id_cols = [c for c in cols if not c.casefold().endswith("id")]
            if non_id_cols:
                return non_id_cols[0]
            if cols:
                return cols[0]

        if val_str and re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", val_str):
            return val_str
        return val_str or "id"

    def _dataset_metric(
        self,
        value: Any,
        dataset_meta: dict[str, Any] | None = None,
        dataset_id: int | None = None,
    ) -> Any:
        target_id = dataset_id or self.dataset_id
        if isinstance(value, dict):
            # If value is already a SIMPLE metric dict, extract column name and aggregate
            agg = str(value.get("aggregate") or "SUM").upper()
            col = str((value.get("column") or {}).get("column_name") or "")
            val_str = f"{agg}({col})" if col else "count"
        else:
            val_str = (str(value) if value is not None else "count").strip()
        normalized = val_str.casefold()

        # Check taxi dataset compatibility when no metadata is supplied or target is taxi
        if (target_id in (1, 2) and dataset_meta is None) or (
            dataset_meta is None
            and any(val_str == m for m in ("count", "Gross Trip Amount", "Average Trip Distance"))
        ):
            if any(token in normalized for token in ("count", "trip", "number")):
                return "count"
            if any(token in normalized for token in ("revenue", "amount", "fare", "total")):
                return "Gross Trip Amount"
            if "distance" in normalized:
                return "Average Trip Distance"
            if val_str in {"count", "Gross Trip Amount", "Average Trip Distance"}:
                return val_str
            if target_id in (1, 2) and dataset_meta is None:
                raise ValueError("The requested chart metric is not supported by the taxi dataset.")

        if dataset_meta:
            metrics = [
                str(m.get("metric_name") or "")
                for m in dataset_meta.get("metrics", [])
                if isinstance(m, dict) and m.get("metric_name")
            ]
            cols = [
                str(c.get("column_name") or "")
                for c in dataset_meta.get("columns", [])
                if isinstance(c, dict) and c.get("column_name")
            ]

            # 1. Match against saved Superset dataset metrics
            for m in metrics:
                if m.casefold() == normalized:
                    return m

            # 2. General count synonyms (places, cities, records, etc.)
            count_synonyms = (
                "count",
                "record",
                "row",
                "number",
                "place",
                "places",
                "dia_diem",
                "so_luong",
                "city",
                "cities",
                "trip",
                "tong_so",
            )
            is_count_request = any(token in normalized for token in count_synonyms)

            # 3. Match taxi metrics if dataset is taxi
            if target_id in (1, 2):
                if any(token in normalized for token in ("revenue", "amount", "fare", "total")):
                    if "Gross Trip Amount" in metrics:
                        return "Gross Trip Amount"
                if "distance" in normalized:
                    if "Average Trip Distance" in metrics:
                        return "Average Trip Distance"

            # 4. Check for aggregate expressions, e.g. SUM(pop), AVG(amount), or raw column name
            agg = "SUM"
            col_target = val_str
            m_upper = val_str.upper()
            for candidate_agg in ("SUM", "AVG", "MAX", "MIN", "COUNT"):
                if m_upper.startswith(f"{candidate_agg}(") and m_upper.endswith(")"):
                    agg = candidate_agg
                    col_target = val_str[len(candidate_agg) + 1 : -1].strip()
                    break

            if agg == "COUNT":
                if "count" in [m.casefold() for m in metrics]:
                    return "count"
                for m in metrics:
                    if "count" in m.casefold():
                        return m
                return "count"

            # An output alias such as city_count describes COUNT(*), not a
            # similarly named source column such as is_megacity.
            if re.search(r"(?:^|_)count$", normalized) and normalized not in {
                c.casefold() for c in cols
            }:
                return next((m for m in metrics if m.casefold() == "count"), "count")

            matched_col = None
            # 4a. Exact column match
            for c in cols:
                if c.casefold() == col_target.casefold():
                    matched_col = c
                    break

            # 4b. Substring match
            if not matched_col and col_target:
                for c in cols:
                    if (
                        col_target.casefold() in c.casefold()
                        or c.casefold() in col_target.casefold()
                    ):
                        matched_col = c
                        break

            # 4c. Token match (e.g. "total_population" -> "population" in "population_max")
            if not matched_col and col_target:
                skip_tokens = {
                    "sum",
                    "avg",
                    "max",
                    "min",
                    "count",
                    "total",
                    "tong",
                    "amount",
                    "rate",
                }
                norm_tokens = [
                    t
                    for t in re.split(r"[_\s]+", col_target.casefold())
                    if t and t not in skip_tokens
                ]
                for c in cols:
                    c_tokens = [t for t in re.split(r"[_\s]+", c.casefold()) if t]
                    if any(
                        t in c_tokens or any(t in ct or ct in t for ct in c_tokens)
                        for t in norm_tokens
                    ):
                        matched_col = c
                        break

            if matched_col:
                return {
                    "expressionType": "SIMPLE",
                    "column": {"column_name": matched_col},
                    "aggregate": agg,
                    "label": f"{agg}({matched_col})",
                }

            # 5. If it was a count request or has count synonyms, return count
            if is_count_request:
                if "count" in [m.casefold() for m in metrics]:
                    return "count"
                for m in metrics:
                    if "count" in m.casefold():
                        return m
                return "count"

            # 6. Look for a numeric column in dataset_meta['columns']
            numeric_cols = [
                c.get("column_name")
                for c in dataset_meta.get("columns", [])
                if isinstance(c, dict)
                and any(
                    t in str(c.get("type", "")).upper()
                    for t in ("INT", "DOUBLE", "FLOAT", "NUMERIC", "REAL", "DECIMAL")
                )
                and not str(c.get("column_name", "")).casefold().endswith("id")
            ]
            if numeric_cols:
                best_col = str(numeric_cols[0])
                return {
                    "expressionType": "SIMPLE",
                    "column": {"column_name": best_col},
                    "aggregate": agg,
                    "label": f"{agg}({best_col})",
                }

            if "count" in [m.casefold() for m in metrics]:
                return "count"
            if metrics:
                return metrics[0]

        # Fallback when no dataset_meta is available
        if any(token in normalized for token in ("revenue", "amount", "fare", "total")):
            return "Gross Trip Amount"
        if "distance" in normalized:
            return "Average Trip Distance"
        if any(token in normalized for token in ("count", "trip", "number")):
            return "count"
        return val_str or "count"

    @staticmethod
    def _query_context_query(
        dimension: str,
        metric: Any,
        row_limit: int,
        *,
        time_series: bool,
        echarts_axis: bool = False,
    ) -> dict[str, Any]:
        # ECharts turns x_axis into an adhoc BASE_AXIS column when the dashboard
        # runs a query. Guest access compares that compiled column with the
        # saved query_context; a plain string is rejected as a changed payload.
        columns = (
            []
            if time_series
            else [
                {
                    "columnType": "BASE_AXIS",
                    "sqlExpression": dimension,
                    "label": dimension,
                    "expressionType": "SQL",
                    "isColumnReference": True,
                }
                if echarts_axis
                else dimension
            ]
        )
        return {
            "columns": columns,
            "metrics": [metric],
            "granularity": dimension if time_series else None,
            "time_range": "No filter",
            "row_limit": row_limit,
            "extras": {
                "where": "",
                "having": "",
                "time_grain_sqla": "P1D" if time_series else None,
            },
            "is_timeseries": time_series,
            "order_desc": True,
            "orderby": [[metric, False]],
        }
