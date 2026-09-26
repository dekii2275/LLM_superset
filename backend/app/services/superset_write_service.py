"""Narrow, server-controlled Superset REST write path for Task 4 charts."""

from __future__ import annotations

import json
import logging
import re
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
        self.frontend_origins = [origin.strip() for origin in frontend_origins.split(",") if origin.strip()]

    async def create_chart(
        self, chart_plan: ChartPlan, sql: str, visualization: VisualizationSpec
    ) -> CreateChartResult:
        # `sql` is accepted only after API-level read-only validation. It is
        # intentionally not sent to Superset: the saved chart uses the trusted
        # existing physical taxi dataset and our deterministic field mapping.
        del sql
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
            return self._create_chart_with_client(client, chart_plan, visualization)
        except SupersetEmbedError:
            logger.exception("superset_chart_create_failed")
            return CreateChartResult(
                success=False,
                message="Không thể tạo biểu đồ trong Superset.",
                error="Superset API request failed.",
            )
        except ValueError as error:
            return CreateChartResult(success=False, message=str(error), error=str(error))

    async def _legacy_create_dashboard_incomplete(
        self,
        dashboard_plan: DashboardPlan,
        prepared_charts: list[tuple[ChartPlan, str, VisualizationSpec]],
    ) -> CreateDashboardResult:
        """Create all charts, attach them, and apply one deterministic 2×2 layout."""
        if not self.username or not self.password:
            return CreateDashboardResult(
                success=False,
                message="Không thể xác thực với Superset.",
                error="Superset credentials are not configured.",
            )

    async def resolve_chart(self, chart_id: int | None, chart_name: str | None) -> dict[str, Any]:
        """Resolve a saved chart without accepting model-invented identifiers."""
        client = self._read_client()
        return self._resolve_chart(client, chart_id, chart_name)

    async def resolve_dashboard(
        self, dashboard_id: int | None, dashboard_name: str | None
    ) -> dict[str, Any]:
        client = self._read_client()
        return self._resolve_dashboard(client, dashboard_id, dashboard_name)

    async def edit_chart(self, plan: EditChartPlan) -> UpdateChartResult:
        if not self.username or not self.password:
            return UpdateChartResult(success=False, message="Không thể xác thực với Superset.", error="Superset credentials are not configured.")
        try:
            client = self._read_client()
            chart = self._resolve_chart(client, plan.chart_id, plan.chart_name)
            self._verify_chart_dataset(chart)
            form_data = self._json_object(chart.get("params"))
            query_context = self._json_object(chart.get("query_context"))
            title = str(chart.get("slice_name") or "Chart")
            viz_type = str(chart.get("viz_type") or form_data.get("viz_type") or "")
            chart_type = self._semantic_chart_type(viz_type)
            dimension = self._chart_dimension(form_data, query_context)
            metric = self._chart_metric(form_data, query_context)

            if plan.operation == EditChartOperation.RENAME_CHART:
                if not plan.new_title:
                    raise ValueError("A new chart title is required.")
                title = plan.new_title.strip()
            elif plan.operation == EditChartOperation.CHANGE_CHART_TYPE:
                if plan.new_chart_type not in {"bar", "line", "pie"}:
                    raise ValueError("Loại biểu đồ này chưa được hỗ trợ trong bản demo. Chỉ hỗ trợ bar, line hoặc pie.")
                chart_type = plan.new_chart_type
            elif plan.operation == EditChartOperation.CHANGE_METRIC:
                if not plan.new_metric:
                    raise ValueError("A new chart metric is required.")
                metric = self._dataset_metric(plan.new_metric)
            elif plan.operation == EditChartOperation.CHANGE_DIMENSION:
                if not plan.new_dimension:
                    raise ValueError("A new chart dimension is required.")
                dimension = self._dataset_dimension(plan.new_dimension)
            else:  # Defensive even though Pydantic enum validation already applies.
                raise ValueError("Unsupported chart edit operation.")

            updated_form, updated_query, new_viz_type = self._edited_chart_config(
                form_data, query_context, chart_type, dimension, metric
            )
            payload = self._chart_update_payload(chart, title, new_viz_type, updated_form, updated_query)
            client.request("PUT", f"/api/v1/chart/{chart['id']}", payload)
            logger.info("superset_chart_updated chart_id=%s operation=%s", chart["id"], plan.operation.value)
            return UpdateChartResult(
                success=True,
                chart_id=int(chart["id"]),
                chart_name=title,
                url=f"{self.public_url}/explore/?slice_id={chart['id']}",
                message="Chart updated successfully.",
            )
        except (SupersetEmbedError, KeyError, ValueError) as error:
            logger.exception("superset_chart_update_failed")
            return UpdateChartResult(success=False, message="Không thể cập nhật biểu đồ trong Superset.", error=str(error))

    async def edit_dashboard(
        self,
        plan: EditDashboardPlan,
        prepared_new_chart: tuple[ChartPlan, str, VisualizationSpec] | None = None,
    ) -> UpdateDashboardResult:
        if not self.username or not self.password:
            return UpdateDashboardResult(success=False, message="Không thể xác thực với Superset.", error="Superset credentials are not configured.")
        try:
            client = self._read_client()
            dashboard = self._resolve_dashboard(client, plan.dashboard_id, plan.dashboard_name)
            dashboard_id = int(dashboard["id"])
            charts = self._dashboard_charts(client, dashboard_id)
            title = str(dashboard.get("dashboard_title") or "Dashboard")

            if plan.operation == EditDashboardOperation.RENAME_DASHBOARD:
                if not plan.new_title:
                    raise ValueError("A new dashboard title is required.")
                title = plan.new_title.strip()
            elif plan.operation == EditDashboardOperation.ADD_CHART:
                if prepared_new_chart:
                    chart_plan, sql, visualization = prepared_new_chart
                    del sql
                    created = self._create_chart_with_client(client, chart_plan, visualization)
                    if not created.success or created.chart_id is None:
                        raise ValueError(created.error or created.message)
                    selected = client.request("GET", f"/api/v1/chart/{created.chart_id}").get("result", {})
                else:
                    selected = self._resolve_chart(client, plan.chart_id, plan.chart_name)
                if any(int(chart["id"]) == int(selected["id"]) for chart in charts):
                    raise ValueError("Chart is already attached to this dashboard.")
                self._set_chart_dashboard_relation(client, selected, dashboard_id, attach=True)
                charts.append(selected)
            elif plan.operation == EditDashboardOperation.REMOVE_CHART:
                selected = self._resolve_chart(client, plan.chart_id, plan.chart_name)
                if not any(int(chart["id"]) == int(selected["id"]) for chart in charts):
                    raise ValueError("Chart is not attached to this dashboard.")
                self._set_chart_dashboard_relation(client, selected, dashboard_id, attach=False)
                charts = [chart for chart in charts if int(chart["id"]) != int(selected["id"])]
            else:
                raise ValueError("Unsupported dashboard edit operation.")

            self._update_dashboard_layout(client, dashboard, title, charts)
            refreshed = client.request("GET", f"/api/v1/dashboard/{dashboard_id}").get("result", {})
            slug = refreshed.get("slug") or dashboard.get("slug") or self._slug(title)
            return UpdateDashboardResult(
                success=True,
                dashboard_id=dashboard_id,
                dashboard_name=title,
                chart_ids=[int(chart["id"]) for chart in charts],
                url=f"{self.public_url}/superset/dashboard/{slug}/",
                message="Dashboard updated successfully.",
            )
        except (SupersetEmbedError, KeyError, ValueError) as error:
            logger.exception("superset_dashboard_update_failed")
            return UpdateDashboardResult(success=False, message="Không thể cập nhật dashboard trong Superset.", error=str(error))
        if not 3 <= len(prepared_charts) <= 4:
            return CreateDashboardResult(
                success=False,
                message="Dashboard demo requires three or four charts.",
                error="Invalid prepared chart count.",
            )
        created_ids: list[int] = []
        try:
            client = SupersetClient(self.base_url, self.username, self.password)
            client.login()
            self._verify_dataset(client)
            chart_details: list[dict[str, Any]] = []
            for chart_plan, sql, visualization in prepared_charts:
                del sql  # SQL was validated/executed before this confirmed write phase.
                chart = self._create_chart_with_client(client, chart_plan, visualization)
                if not chart.success or chart.chart_id is None:
                    return CreateDashboardResult(
                        success=False,
                        chart_ids=created_ids,
                        message="Unable to create all dashboard charts.",
                        error=chart.error or chart.message,
                    )
                created_ids.append(chart.chart_id)
                chart_details.append(
                    client.request("GET", f"/api/v1/chart/{chart.chart_id}").get("result", {})
                )

            title = self._unique_dashboard_title(client, dashboard_plan.title)
            layout = self.build_dashboard_layout(title, chart_details)
            metadata = {
                "timed_refresh_immune_slices": [],
                "expanded_slices": {},
                "refresh_frequency": 0,
                "default_filters": "{}",
                "color_scheme": None,
                "label_colors": {},
                "cross_filters_enabled": False,
                "chart_configuration": {},
                "filter_scopes": {},
                "positions": layout,
            }
            payload = {
                "dashboard_title": title,
                "slug": self._slug(title),
                "published": True,
                "position_json": json.dumps(layout, ensure_ascii=False),
                "json_metadata": json.dumps(metadata, ensure_ascii=False),
            }
            created = client.request("POST", "/api/v1/dashboard/", payload)
            dashboard_id = self._created_dashboard_id(client, created, title)

            # Superset 6.1 expects this explicit relation in addition to the
            # layout tree, otherwise charts may not appear on the dashboard.
            for chart in chart_details:
                client.request(
                    "PUT",
                    f"/api/v1/chart/{chart['id']}",
                    {
                        "dashboards": [dashboard_id],
                        "slice_name": chart["slice_name"],
                        "datasource_id": chart["datasource_id"],
                        "datasource_type": chart["datasource_type"],
                        "viz_type": chart["viz_type"],
                        "params": chart["params"],
                        "query_context": chart.get("query_context"),
                    },
                )
            dashboard = client.request("GET", f"/api/v1/dashboard/{dashboard_id}").get("result", {})
            embedded = client.request(
                "POST",
                f"/api/v1/dashboard/{dashboard_id}/embedded",
                {"allowed_domains": self.frontend_origins},
            ).get("result", {})
            dashboard_uuid = embedded.get("uuid")
            logger.info(
                "superset_dashboard_created dashboard_id=%s dashboard_uuid=%s title=%r chart_ids=%s",
                dashboard_id,
                dashboard_uuid,
                title,
                created_ids,
            )
            slug = dashboard.get("slug") or self._slug(title)
            return CreateDashboardResult(
                success=True,
                dashboard_id=dashboard_id,
                dashboard_uuid=str(dashboard_uuid) if dashboard_uuid else None,
                dashboard_name=title,
                chart_ids=created_ids,
                url=f"{self.public_url}/superset/dashboard/{slug}/",
                message="Dashboard created successfully.",
            )
        except SupersetEmbedError:
            logger.exception("superset_dashboard_create_failed chart_ids=%s", created_ids)
            return CreateDashboardResult(
                success=False,
                chart_ids=created_ids,
                message="Không thể tạo dashboard trong Superset.",
                error="Superset API request failed.",
            )
        except (KeyError, ValueError) as error:
            logger.exception("superset_dashboard_payload_failed chart_ids=%s", created_ids)
            return CreateDashboardResult(
                success=False,
                chart_ids=created_ids,
                message="Không thể tạo dashboard trong Superset.",
                error=str(error),
            )

    async def create_dashboard(
        self,
        dashboard_plan: DashboardPlan,
        prepared_charts: list[tuple[ChartPlan, str, VisualizationSpec]],
    ) -> CreateDashboardResult:
        """Create 3–4 verified charts and one dashboard using a trusted layout."""
        if not 3 <= len(prepared_charts) <= 4:
            return CreateDashboardResult(success=False, message="Dashboard demo requires three or four charts.", error="Invalid prepared chart count.")
        try:
            client = self._read_client()
            self._verify_dataset(client)
            details: list[dict[str, Any]] = []
            ids: list[int] = []
            for chart_plan, sql, visualization in prepared_charts:
                del sql
                created = self._create_chart_with_client(client, chart_plan, visualization)
                if not created.success or created.chart_id is None:
                    raise ValueError(created.error or created.message)
                ids.append(created.chart_id)
                details.append(client.request("GET", f"/api/v1/chart/{created.chart_id}").get("result", {}))
            title = self._unique_dashboard_title(client, dashboard_plan.title)
            layout = self.build_dashboard_layout(title, details)
            metadata = {"positions": layout, "timed_refresh_immune_slices": [], "expanded_slices": {}, "refresh_frequency": 0, "default_filters": "{}", "color_scheme": None, "label_colors": {}, "cross_filters_enabled": False, "chart_configuration": {}, "filter_scopes": {}}
            created = client.request("POST", "/api/v1/dashboard/", {"dashboard_title": title, "slug": self._slug(title), "published": True, "position_json": json.dumps(layout), "json_metadata": json.dumps(metadata)})
            dashboard_id = self._created_dashboard_id(client, created, title)
            for chart in details:
                self._set_chart_dashboard_relation(client, chart, dashboard_id, attach=True)
            dashboard = client.request("GET", f"/api/v1/dashboard/{dashboard_id}").get("result", {})
            embedded = client.request("POST", f"/api/v1/dashboard/{dashboard_id}/embedded", {"allowed_domains": self.frontend_origins}).get("result", {})
            return CreateDashboardResult(success=True, dashboard_id=dashboard_id, dashboard_uuid=str(embedded.get("uuid")) if embedded.get("uuid") else None, dashboard_name=title, chart_ids=ids, url=f"{self.public_url}/superset/dashboard/{dashboard.get('slug') or self._slug(title)}/", message="Dashboard created successfully.")
        except (SupersetEmbedError, KeyError, ValueError) as error:
            logger.exception("superset_dashboard_create_failed")
            return CreateDashboardResult(success=False, message="Không thể tạo dashboard trong Superset.", error=str(error))

    async def resolve_chart(self, chart_id: int | None, chart_name: str | None) -> dict[str, Any]:
        return self._resolve_chart(self._read_client(), chart_id, chart_name)

    async def resolve_dashboard(self, dashboard_id: int | None, dashboard_name: str | None) -> dict[str, Any]:
        return self._resolve_dashboard(self._read_client(), dashboard_id, dashboard_name)

    async def edit_chart(self, plan: EditChartPlan) -> UpdateChartResult:
        try:
            client = self._read_client()
            chart = self._resolve_chart(client, plan.chart_id, plan.chart_name)
            self._verify_chart_dataset(chart)
            form_data, query_context = self._json_object(chart.get("params")), self._json_object(chart.get("query_context"))
            title = str(chart.get("slice_name") or "Chart")
            chart_type = self._semantic_chart_type(str(chart.get("viz_type") or form_data.get("viz_type") or ""))
            dimension, metric = self._chart_dimension(form_data, query_context), self._chart_metric(form_data, query_context)
            if plan.operation == EditChartOperation.RENAME_CHART:
                if not plan.new_title: raise ValueError("A new chart title is required.")
                title = plan.new_title.strip()
            elif plan.operation == EditChartOperation.CHANGE_CHART_TYPE:
                if plan.new_chart_type not in {"bar", "line", "pie"}: raise ValueError("Loại biểu đồ này chưa được hỗ trợ trong bản demo. Chỉ hỗ trợ bar, line hoặc pie.")
                chart_type = plan.new_chart_type
            elif plan.operation == EditChartOperation.CHANGE_METRIC:
                if not plan.new_metric: raise ValueError("A new chart metric is required.")
                metric = self._dataset_metric(plan.new_metric)
            elif plan.operation == EditChartOperation.CHANGE_DIMENSION:
                if not plan.new_dimension: raise ValueError("A new chart dimension is required.")
                dimension = self._dataset_dimension(plan.new_dimension)
            else: raise ValueError("Unsupported chart edit operation.")
            updated_form, updated_query, viz_type = self._edited_chart_config(form_data, query_context, chart_type, dimension, metric)
            client.request("PUT", f"/api/v1/chart/{chart['id']}", self._chart_update_payload(chart, title, viz_type, updated_form, updated_query))
            return UpdateChartResult(success=True, chart_id=int(chart["id"]), chart_name=title, url=f"{self.public_url}/explore/?slice_id={chart['id']}", message="Chart updated successfully.")
        except (SupersetEmbedError, KeyError, ValueError) as error:
            logger.exception("superset_chart_update_failed")
            return UpdateChartResult(success=False, message="Không thể cập nhật biểu đồ trong Superset.", error=str(error))

    async def edit_dashboard(self, plan: EditDashboardPlan, prepared_new_chart: tuple[ChartPlan, str, VisualizationSpec] | None = None) -> UpdateDashboardResult:
        try:
            client = self._read_client()
            dashboard = self._resolve_dashboard(client, plan.dashboard_id, plan.dashboard_name)
            dashboard_id, title = int(dashboard["id"]), str(dashboard.get("dashboard_title") or "Dashboard")
            charts = self._dashboard_charts(client, dashboard_id)
            if plan.operation == EditDashboardOperation.RENAME_DASHBOARD:
                if not plan.new_title: raise ValueError("A new dashboard title is required.")
                title = plan.new_title.strip()
            elif plan.operation == EditDashboardOperation.ADD_CHART:
                if prepared_new_chart:
                    chart_plan, sql, visualization = prepared_new_chart
                    del sql
                    created = self._create_chart_with_client(client, chart_plan, visualization)
                    if not created.success or created.chart_id is None: raise ValueError(created.error or created.message)
                    selected = client.request("GET", f"/api/v1/chart/{created.chart_id}").get("result", {})
                else:
                    selected = self._resolve_chart(client, plan.chart_id, plan.chart_name)
                if any(int(item["id"]) == int(selected["id"]) for item in charts): raise ValueError("Chart is already attached to this dashboard.")
                self._set_chart_dashboard_relation(client, selected, dashboard_id, attach=True)
                charts.append(selected)
            elif plan.operation == EditDashboardOperation.REMOVE_CHART:
                selected = self._resolve_chart(client, plan.chart_id, plan.chart_name)
                if not any(int(item["id"]) == int(selected["id"]) for item in charts): raise ValueError("Chart is not attached to this dashboard.")
                self._set_chart_dashboard_relation(client, selected, dashboard_id, attach=False)
                charts = [item for item in charts if int(item["id"]) != int(selected["id"])]
            else: raise ValueError("Unsupported dashboard edit operation.")
            self._update_dashboard_layout(client, dashboard, title, charts)
            refreshed = client.request("GET", f"/api/v1/dashboard/{dashboard_id}").get("result", {})
            return UpdateDashboardResult(success=True, dashboard_id=dashboard_id, dashboard_name=title, chart_ids=[int(item["id"]) for item in charts], url=f"{self.public_url}/superset/dashboard/{refreshed.get('slug') or dashboard.get('slug') or self._slug(title)}/", message="Dashboard updated successfully.")
        except (SupersetEmbedError, KeyError, ValueError) as error:
            logger.exception("superset_dashboard_update_failed")
            return UpdateDashboardResult(success=False, message="Không thể cập nhật dashboard trong Superset.", error=str(error))

    def _create_chart_with_client(
        self, client: SupersetClient, chart_plan: ChartPlan, visualization: VisualizationSpec
    ) -> CreateChartResult:
        title = self._unique_title(client, chart_plan.title)
        payload = self.build_superset_chart_payload(title, chart_plan, visualization)
        created = client.request("POST", "/api/v1/chart/", payload)
        chart_id = self._created_chart_id(client, created, title)
        logger.info(
            "superset_chart_created chart_id=%s title=%r viz_type=%s dataset_id=%s",
            chart_id, title, payload["viz_type"], self.dataset_id,
        )
        return CreateChartResult(
            success=True, chart_id=chart_id, chart_name=title,
            url=f"{self.public_url}/explore/?slice_id={chart_id}",
            message="Chart created successfully.",
        )

    def build_superset_chart_payload(
        self, title: str, chart_plan: ChartPlan, visualization: VisualizationSpec
    ) -> dict[str, Any]:
        dimension = self._dataset_dimension(visualization.x_axis or chart_plan.dimension)
        metric = self._dataset_metric(visualization.y_axis or chart_plan.metric)
        row_limit = chart_plan.limit or 100
        source = f"{self.dataset_id}__table"
        chart_type = chart_plan.chart_type

        if chart_type == "pie":
            viz_type = "pie"
            form_data: dict[str, Any] = {
                "datasource": source,
                "viz_type": viz_type,
                "groupby": [dimension],
                "metric": metric,
                "color_scheme": "supersetColors",
                "show_labels": True,
                "show_legend": True,
                "label_type": "key_value_percent",
                "sort_by_metric": True,
                "row_limit": min(row_limit, 100),
                "donut": False,
            }
            query = self._query_context_query(dimension, metric, row_limit, time_series=False)
        elif chart_type in {"line", "area"}:
            # Superset 6.1's verified ECharts line chart is used for area as
            # well; it is safer than guessing an unsupported area viz_type.
            viz_type = "echarts_timeseries_line"
            time_dimension = "tpep_pickup_datetime" if dimension in {"source_month", "tpep_pickup_datetime"} else dimension
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
            }
            query = self._query_context_query(time_dimension, metric, row_limit, time_series=True)
        else:
            viz_type = "echarts_timeseries_bar"
            form_data = {
                "datasource": source,
                "viz_type": viz_type,
                "metrics": [metric],
                "x_axis": dimension,
                "x_axis_sort_series_type": "name",
                "x_axis_sort_series_ascending": True,
                "row_limit": row_limit,
                "order_desc": True,
            }
            query = self._query_context_query(dimension, metric, row_limit, time_series=False)

        query_context = {
            "datasource": {"id": self.dataset_id, "type": "table"},
            "queries": [query],
            "result_format": "json",
            "result_type": "full",
        }
        return {
            "slice_name": title,
            "datasource_id": self.dataset_id,
            "datasource_type": "table",
            "viz_type": viz_type,
            "description": f"Created by AI BI Assistant: {chart_plan.question}",
            "params": json.dumps(form_data, ensure_ascii=False, sort_keys=True),
            "query_context": json.dumps(query_context, ensure_ascii=False, sort_keys=True),
        }

    def _verify_dataset(self, client: SupersetClient) -> None:
        result = client.request("GET", f"/api/v1/dataset/{self.dataset_id}").get("result", {})
        if result.get("schema") != "raw" or result.get("datasource_name") != "yellow_taxi_trips":
            raise ValueError("Configured Superset taxi dataset is unavailable.")

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

    def _resolve_chart(self, client: SupersetClient, chart_id: int | None, chart_name: str | None) -> dict[str, Any]:
        if chart_id:
            chart = client.request("GET", f"/api/v1/chart/{chart_id}").get("result", {})
            if not chart or int(chart.get("id", 0)) != chart_id:
                raise ValueError(f"Không tìm thấy biểu đồ ID {chart_id}.")
            return chart
        return self._resolve_named_asset(client, "/api/v1/chart/?q=(page:0,page_size:100)", chart_name, "slice_name", "biểu đồ")

    def _resolve_dashboard(self, client: SupersetClient, dashboard_id: int | None, dashboard_name: str | None) -> dict[str, Any]:
        if dashboard_id:
            dashboard = client.request("GET", f"/api/v1/dashboard/{dashboard_id}").get("result", {})
            if not dashboard or int(dashboard.get("id", 0)) != dashboard_id:
                raise ValueError(f"Không tìm thấy dashboard ID {dashboard_id}.")
            return dashboard
        return self._resolve_named_asset(client, "/api/v1/dashboard/?q=(page:0,page_size:100)", dashboard_name, "dashboard_title", "dashboard")

    @staticmethod
    def _resolve_named_asset(client: SupersetClient, url: str, name: str | None, field: str, label: str) -> dict[str, Any]:
        if not name:
            raise ValueError(f"Hãy chọn {label} cần cập nhật.")
        assets = client.request("GET", url).get("result", [])
        wanted = name.strip().casefold()
        exact = [asset for asset in assets if str(asset.get(field, "")).casefold() == wanted]
        if len(exact) == 1:
            return client.request("GET", f"{url.split('?')[0].rstrip('/')}/{exact[0]['id']}").get("result", exact[0])
        close = [asset for asset in assets if wanted in str(asset.get(field, "")).casefold()]
        if len(close) == 1:
            return client.request("GET", f"{url.split('?')[0].rstrip('/')}/{close[0]['id']}").get("result", close[0])
        if len(close) > 1 or len(exact) > 1:
            raise ValueError(f"Tên {label} '{name}' chưa đủ rõ; hãy chọn đúng tên.")
        raise ValueError(f"Không tìm thấy {label} '{name}'.")

    def _verify_chart_dataset(self, chart: dict[str, Any]) -> None:
        if int(chart.get("datasource_id") or 0) != self.dataset_id or chart.get("datasource_type") != "table":
            raise ValueError("Chart does not use the configured taxi dataset.")

    @staticmethod
    def _semantic_chart_type(viz_type: str) -> str:
        if viz_type == "pie": return "pie"
        if viz_type == "echarts_timeseries_line": return "line"
        if viz_type == "echarts_timeseries_bar": return "bar"
        raise ValueError("This saved chart type is not supported by the demo editor.")

    @staticmethod
    def _chart_dimension(form: dict[str, Any], query_context: dict[str, Any]) -> str:
        value = (form.get("groupby") or [None])[0] or form.get("x_axis")
        if value: return str(value)
        queries = query_context.get("queries") or [{}]
        return str((queries[0].get("columns") or ["pu_location_id"])[0] or "pu_location_id")

    @staticmethod
    def _chart_metric(form: dict[str, Any], query_context: dict[str, Any]) -> str:
        value = form.get("metric") or (form.get("metrics") or [None])[0]
        if value: return str(value)
        queries = query_context.get("queries") or [{}]
        return str((queries[0].get("metrics") or ["count"])[0] or "count")

    def _edited_chart_config(self, form: dict[str, Any], query_context: dict[str, Any], chart_type: str, dimension: str, metric: str) -> tuple[dict[str, Any], dict[str, Any], str]:
        updated = dict(form)
        updated["datasource"] = f"{self.dataset_id}__table"
        row_limit = int(updated.get("row_limit") or 100)
        if chart_type == "pie":
            viz_type = "pie"; updated.update({"viz_type": viz_type, "groupby": [dimension], "metric": metric, "row_limit": min(row_limit, 100)})
            updated.pop("metrics", None); updated.pop("x_axis", None)
            query = self._query_context_query(dimension, metric, row_limit, time_series=False)
        elif chart_type == "line":
            viz_type = "echarts_timeseries_line"; time_dimension = "tpep_pickup_datetime" if dimension == "source_month" else dimension
            updated.update({"viz_type": viz_type, "metrics": [metric], "x_axis": time_dimension, "granularity_sqla": time_dimension, "row_limit": row_limit})
            updated.pop("groupby", None); updated.pop("metric", None)
            query = self._query_context_query(time_dimension, metric, row_limit, time_series=True)
        else:
            viz_type = "echarts_timeseries_bar"; updated.update({"viz_type": viz_type, "metrics": [metric], "x_axis": dimension, "row_limit": row_limit})
            updated.pop("groupby", None); updated.pop("metric", None)
            query = self._query_context_query(dimension, metric, row_limit, time_series=False)
        updated_context = dict(query_context)
        updated_context.update({"datasource": {"id": self.dataset_id, "type": "table"}, "queries": [query], "result_format": updated_context.get("result_format", "json"), "result_type": updated_context.get("result_type", "full")})
        return updated, updated_context, viz_type

    @staticmethod
    def _dashboard_ids(chart: dict[str, Any]) -> list[int]:
        values = chart.get("dashboards") or []
        return [int(value["id"] if isinstance(value, dict) else value) for value in values]

    def _chart_update_payload(self, chart: dict[str, Any], title: str, viz_type: str, form: dict[str, Any], query_context: dict[str, Any]) -> dict[str, Any]:
        return {"slice_name": title, "datasource_id": self.dataset_id, "datasource_type": "table", "viz_type": viz_type, "description": chart.get("description") or "", "dashboards": self._dashboard_ids(chart), "params": json.dumps(form, ensure_ascii=False, sort_keys=True), "query_context": json.dumps(query_context, ensure_ascii=False, sort_keys=True)}

    def _set_chart_dashboard_relation(self, client: SupersetClient, chart: dict[str, Any], dashboard_id: int, *, attach: bool) -> None:
        ids = set(self._dashboard_ids(chart))
        if attach: ids.add(dashboard_id)
        else: ids.discard(dashboard_id)
        form, context = self._json_object(chart.get("params")), self._json_object(chart.get("query_context"))
        client.request("PUT", f"/api/v1/chart/{chart['id']}", {"slice_name": chart["slice_name"], "datasource_id": chart["datasource_id"], "datasource_type": chart["datasource_type"], "viz_type": chart["viz_type"], "description": chart.get("description") or "", "dashboards": sorted(ids), "params": json.dumps(form, ensure_ascii=False, sort_keys=True), "query_context": json.dumps(context, ensure_ascii=False, sort_keys=True)})

    @staticmethod
    def _dashboard_charts(client: SupersetClient, dashboard_id: int) -> list[dict[str, Any]]:
        return client.request("GET", f"/api/v1/dashboard/{dashboard_id}/charts").get("result", [])

    def _update_dashboard_layout(self, client: SupersetClient, dashboard: dict[str, Any], title: str, charts: list[dict[str, Any]]) -> None:
        layout = self._preserve_dashboard_layout(dashboard, title, charts)
        metadata = self._json_object(dashboard.get("json_metadata")); metadata["positions"] = layout
        client.request("PUT", f"/api/v1/dashboard/{dashboard['id']}", {"dashboard_title": title, "slug": dashboard.get("slug") or self._slug(title), "published": bool(dashboard.get("published", True)), "position_json": json.dumps(layout, ensure_ascii=False), "json_metadata": json.dumps(metadata, ensure_ascii=False)})

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

    def _append_chart_at_end(self, layout: dict[str, Any], grid_id: str, chart: dict[str, Any]) -> None:
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
            for chart in client.request("GET", "/api/v1/chart/?q=(page:0,page_size:100)").get("result", [])
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
        for chart in client.request("GET", "/api/v1/chart/?q=(page:0,page_size:100)").get("result", []):
            if chart.get("slice_name") == title:
                return int(chart["id"])
        raise ValueError("Superset created the chart but did not return its ID.")

    def _unique_dashboard_title(self, client: SupersetClient, requested: str) -> str:
        existing = {
            str(dashboard.get("dashboard_title", "")).casefold()
            for dashboard in client.request("GET", "/api/v1/dashboard/?q=(page:0,page_size:100)").get("result", [])
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
        for dashboard in client.request("GET", "/api/v1/dashboard/?q=(page:0,page_size:100)").get("result", []):
            if dashboard.get("dashboard_title") == title:
                return int(dashboard["id"])
        raise ValueError("Superset created the dashboard but did not return its ID.")

    @staticmethod
    def _slug(title: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")
        return slug[:120] or "ai-bi-dashboard"

    @staticmethod
    def build_dashboard_layout(title: str, charts: list[dict[str, Any]]) -> dict[str, Any]:
        if not charts:
            raise ValueError("Dashboard layout requires at least one chart.")
        # Keep adding two-chart rows as needed.  Superset's native dashboard
        # layout is not limited to six charts, so imposing an artificial cap
        # here made an otherwise-valid add-chart request fail after the chart
        # had already been created.
        rows = [charts[index:index + 2] for index in range(0, len(charts), 2)]
        row_ids = [f"ROW-{index + 1}" for index in range(len(rows))]
        positions: dict[str, Any] = {
            "DASHBOARD_VERSION_KEY": "v2",
            "ROOT_ID": {"id": "ROOT_ID", "type": "ROOT", "children": ["GRID_ID"]},
            "GRID_ID": {"id": "GRID_ID", "type": "GRID", "parents": ["ROOT_ID"], "children": row_ids},
            "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": title}},
        }
        for row_id, row_charts in zip(row_ids, rows):
            chart_keys: list[str] = []
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

    @staticmethod
    def _dataset_dimension(value: str | None) -> str:
        normalized = (value or "").casefold()
        if "zone" in normalized or "pickup" in normalized:
            return "pu_location_id"
        if "payment" in normalized:
            return "payment_type"
        if any(token in normalized for token in ("month", "date", "time")):
            return "source_month"
        allowed = {"vendor_id", "passenger_count", "ratecode_id", "payment_type", "pu_location_id", "do_location_id", "source_month"}
        if value in allowed:
            return value
        raise ValueError("The requested chart dimension is not supported by the taxi dataset.")

    @staticmethod
    def _dataset_metric(value: str | None) -> str:
        normalized = (value or "").casefold()
        if any(token in normalized for token in ("count", "trip", "number")):
            return "count"
        if any(token in normalized for token in ("revenue", "amount", "fare", "total")):
            return "Gross Trip Amount"
        if "distance" in normalized:
            return "Average Trip Distance"
        raise ValueError("The requested chart metric is not supported by the taxi dataset.")

    @staticmethod
    def _query_context_query(
        dimension: str, metric: str, row_limit: int, *, time_series: bool
    ) -> dict[str, Any]:
        return {
            "columns": [] if time_series else [dimension],
            "metrics": [metric],
            "granularity": dimension if time_series else None,
            "time_range": "No filter",
            "row_limit": row_limit,
            "extras": {"where": "", "having": "", "time_grain_sqla": "P1D" if time_series else None},
            "is_timeseries": time_series,
            "order_desc": True,
            "orderby": [[metric, False]],
        }
