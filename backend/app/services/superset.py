"""Server-side Superset guest-token integration for the local demo."""

from __future__ import annotations

import base64
import http.cookiejar
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPCookieProcessor, Request, build_opener


class SupersetEmbedError(RuntimeError):
    """Raised when Superset cannot prepare an embedded dashboard."""


class SupersetClient:
    _PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.access_token: str | None = None
        self.csrf_token: str | None = None

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        authenticated: bool = True,
        timeout_seconds: float = 15,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json", "Referer": f"{self.base_url}/"}
        if authenticated and self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and self.csrf_token:
            headers["X-CSRFToken"] = self.csrf_token

        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")

        request = Request(
            f"{self.base_url}{path if path.startswith('/') else '/' + path}",
            data=data,
            headers=headers,
            method=method.upper(),
        )
        try:
            with self.opener.open(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise SupersetEmbedError(
                f"Superset returned HTTP {error.code} while preparing the embedded dashboard."
            ) from error
        except (OSError, URLError) as error:
            raise SupersetEmbedError("Superset is unavailable.") from error

    def login(self) -> None:
        result = self.request(
            "POST",
            "/api/v1/security/login",
            {
                "username": self.username,
                "password": self.password,
                "provider": "db",
                "refresh": True,
            },
            authenticated=False,
        )
        self.access_token = result.get("access_token")
        if not self.access_token:
            raise SupersetEmbedError("Superset login did not return an access token.")
        self.csrf_token = self.request("GET", "/api/v1/security/csrf_token/").get("result")
        if not self.csrf_token:
            raise SupersetEmbedError("Superset did not return a CSRF token.")

    def embedded_dashboard_id(self, dashboard_slug: str) -> str:
        path = f"/api/v1/dashboard/{quote(dashboard_slug, safe='')}/embedded"
        result = self.request("GET", path).get("result", {})
        dashboard_id = result.get("uuid")
        if not dashboard_id:
            raise SupersetEmbedError(
                "The Superset dashboard has not been enabled for embedding. "
                "Run the dashboard setup script after restarting Superset."
            )
        return str(dashboard_id)

    def list_datasets(self) -> list[dict[str, Any]]:
        """List all datasets accessible in Superset."""
        result = self.request("GET", "/api/v1/dataset/?q=(page:0,page_size:100)")
        return result.get("result", [])

    def get_dataset(self, dataset_id: int) -> dict[str, Any]:
        """Fetch detailed metadata for a specific Superset dataset."""
        result = self.request("GET", f"/api/v1/dataset/{dataset_id}")
        return result.get("result", {})

    @staticmethod
    def _json_object(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}

    @staticmethod
    def _chart_ids_under(position_json: dict[str, Any], root_ids: list[str]) -> set[int]:
        chart_ids: set[int] = set()
        pending = list(root_ids)
        visited: set[str] = set()
        while pending:
            item_id = pending.pop()
            if item_id in visited:
                continue
            visited.add(item_id)
            item = position_json.get(item_id)
            if not isinstance(item, dict):
                continue
            if item.get("type") == "CHART":
                chart_id = (item.get("meta") or {}).get("chartId")
                try:
                    chart_ids.add(int(chart_id))
                except (TypeError, ValueError):
                    pass
            children = item.get("children")
            if isinstance(children, list):
                pending.extend(str(child_id) for child_id in children)
        return chart_ids

    @staticmethod
    def _filter_applies_to_chart(
        filter_config: dict[str, Any], chart_id: int, chart_item: dict[str, Any]
    ) -> bool:
        scope = filter_config.get("scope") or {}
        excluded = {str(value) for value in scope.get("excluded", [])}
        if str(chart_id) in excluded:
            return False
        root_path = scope.get("rootPath") or []
        chart_parents = {str(value) for value in chart_item.get("parents", [])}
        return bool({str(value) for value in root_path} & chart_parents)

    @staticmethod
    def _active_native_filters(
        metadata: dict[str, Any], data_mask: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        active_filters = []
        safe_data_mask = {}
        for filter_config in metadata.get("native_filter_configuration", []):
            if (
                not isinstance(filter_config, dict)
                or filter_config.get("filterType") != "filter_select"
            ):
                continue
            filter_id = filter_config.get("id")
            raw_mask = data_mask.get(filter_id) if isinstance(filter_id, str) else None
            if not isinstance(raw_mask, dict):
                continue
            filter_state = raw_mask.get("filterState") or {}
            value = filter_state.get("value") if isinstance(filter_state, dict) else None
            values = value if isinstance(value, list) else [value]
            if not values or value is None or len(values) > 100:
                continue
            if any(
                item is None
                or not isinstance(item, (str, int, float, bool))
                or (isinstance(item, str) and len(item) > 256)
                for item in values
            ):
                continue

            target_columns = []
            for target in filter_config.get("targets", []):
                column = target.get("column") if isinstance(target, dict) else None
                column_name = column.get("name") if isinstance(column, dict) else column
                if isinstance(column_name, str) and column_name not in target_columns:
                    target_columns.append(column_name)
            if not target_columns:
                continue

            operation = (
                "NOT IN"
                if (filter_config.get("controlValues") or {}).get("inverseSelection")
                else "IN"
            )
            query_filters = [
                {"col": column, "op": operation, "val": values} for column in target_columns
            ]
            safe_filter_state = {"value": values}
            label = filter_state.get("label") if isinstance(filter_state, dict) else None
            if isinstance(label, str) and len(label) <= 256:
                safe_filter_state["label"] = label
            safe_data_mask[filter_id] = {
                "id": filter_id,
                "extraFormData": {"filters": query_filters},
                "filterState": safe_filter_state,
                "ownState": {},
            }
            active_filters.append(
                {
                    "id": filter_id,
                    "name": str(filter_config.get("name") or filter_id),
                    "filters": query_filters,
                    "summary": f"{filter_config.get('name') or filter_id}: {', '.join(str(item) for item in values[:10])}",
                    "config": filter_config,
                }
            )
        return active_filters, safe_data_mask

    def dashboard_chart_data(
        self,
        dashboard_slug: str,
        active_tabs: list[str] | None = None,
        data_mask: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        dashboards = self.request("GET", "/api/v1/dashboard/?q=(page:0,page_size:100)").get(
            "result", []
        )
        dashboard = next((item for item in dashboards if item.get("slug") == dashboard_slug), None)
        if not dashboard:
            raise SupersetEmbedError("The configured Superset dashboard was not found.")

        dashboard_id = dashboard.get("id")
        dashboard_detail = (
            self.request("GET", f"/api/v1/dashboard/{dashboard_id}").get("result") or {}
        )
        position_json = self._json_object(dashboard_detail.get("position_json"))
        metadata = self._json_object(dashboard_detail.get("json_metadata"))
        tabs = {
            str(item_id): item
            for item_id, item in position_json.items()
            if isinstance(item, dict) and item.get("type") == "TAB"
        }
        selected_tabs = [str(tab_id) for tab_id in (active_tabs or []) if str(tab_id) in tabs]
        if tabs and active_tabs and not selected_tabs:
            raise SupersetEmbedError("The active dashboard tab could not be matched.")
        if tabs and not selected_tabs:
            tabs_container = next(
                (
                    item
                    for item in position_json.values()
                    if isinstance(item, dict) and item.get("type") == "TABS"
                ),
                None,
            )
            defaults = (tabs_container or {}).get("children") or []
            first_tab = next((str(item_id) for item_id in defaults if str(item_id) in tabs), None)
            selected_tabs = [first_tab or next(iter(tabs))]
        selected_tab = tabs.get(selected_tabs[-1]) if selected_tabs else None
        tab_chart_ids = (
            self._chart_ids_under(position_json, [selected_tabs[-1]]) if selected_tabs else None
        )
        if tab_chart_ids is not None:
            charts_in_tabs = set().union(
                *(self._chart_ids_under(position_json, [tab_id]) for tab_id in tabs)
            )
            for item in position_json.values():
                if not isinstance(item, dict) or item.get("type") != "CHART":
                    continue
                try:
                    chart_id = int((item.get("meta") or {}).get("chartId"))
                except (TypeError, ValueError):
                    continue
                if chart_id not in charts_in_tabs:
                    tab_chart_ids.add(chart_id)
        if selected_tabs and not tab_chart_ids:
            raise SupersetEmbedError("The active dashboard tab contains no charts.")

        charts = self.request("GET", f"/api/v1/dashboard/{dashboard_id}/charts").get("result", [])
        if not charts:
            raise SupersetEmbedError("The Superset dashboard contains no charts.")

        chart_layout = {
            int((item.get("meta") or {}).get("chartId")): item
            for item in position_json.values()
            if isinstance(item, dict)
            and item.get("type") == "CHART"
            and str((item.get("meta") or {}).get("chartId", "")).isdigit()
        }
        if tab_chart_ids is not None:
            charts = [chart for chart in charts if int(chart.get("id", -1)) in tab_chart_ids]
        if not charts:
            raise SupersetEmbedError("The active dashboard tab contains no charts.")

        active_filters, safe_data_mask = self._active_native_filters(metadata, data_mask or {})
        chart_data = []
        for chart in charts:
            chart_id = chart.get("id")
            title = str(chart.get("slice_name") or f"Chart {chart_id}")
            chart_detail = self.request("GET", f"/api/v1/chart/{chart_id}").get("result") or {}
            query_context = self._json_object(chart_detail.get("query_context"))
            if not query_context:
                raise SupersetEmbedError(f"Chart {chart_id} has no saved query context.")
            chart_source_id = chart_detail.get("datasource_id") or (
                query_context.get("datasource") or {}
            ).get("id")
            chart_item = chart_layout.get(int(chart_id), {})
            query_filters = []
            for active_filter in active_filters:
                config = active_filter["config"]
                targets = config.get("targets", [])
                target_dataset_ids = {
                    str(target.get("datasetId"))
                    for target in targets
                    if isinstance(target, dict) and target.get("datasetId") is not None
                }
                if (
                    target_dataset_ids
                    and chart_source_id is not None
                    and str(chart_source_id) not in target_dataset_ids
                ):
                    continue
                if self._filter_applies_to_chart(config, int(chart_id), chart_item):
                    query_filters.extend(active_filter["filters"])

            for query in query_context.get("queries", []):
                query["filters"] = (query.get("filters") or []) + [
                    {**filter_item, "isExtra": True} for filter_item in query_filters
                ]
            payload = {
                **query_context,
                "form_data": self._json_object(chart_detail.get("params")),
            }
            results = self.request("POST", "/api/v1/chart/data", payload).get("result", [])
            result = results[0] if results else {}
            rows = result.get("data") or []
            chart_data.append(
                {
                    "id": int(chart_id),
                    "title": title,
                    "viz_type": str(chart.get("viz_type") or ""),
                    "columns": result.get("colnames") or (list(rows[0]) if rows else []),
                    "rows": rows[:30],
                    "row_count": len(rows),
                    "truncated": len(rows) > 30,
                    "unavailable": not results
                    or result.get("status") != "success"
                    or bool(result.get("error")),
                }
            )

        applied_filters = []
        for active_filter in active_filters:
            config = active_filter["config"]
            if (
                any(
                    self._filter_applies_to_chart(
                        config, int(chart["id"]), chart_layout.get(int(chart["id"]), {})
                    )
                    for chart in charts
                )
                and active_filter["summary"] not in applied_filters
            ):
                applied_filters.append(active_filter["summary"])

        return {
            "dashboard_title": str(dashboard.get("dashboard_title") or dashboard_slug),
            "dashboard_id": int(dashboard_id),
            "active_tab_title": str((selected_tab or {}).get("meta", {}).get("text") or ""),
            "active_tabs": selected_tabs,
            "data_mask": safe_data_mask,
            "applied_filters": applied_filters,
            "charts": chart_data,
        }

    def dashboard_chart_screenshots(
        self,
        dashboard_id: int,
        chart_ids: list[int],
        active_tabs: list[str],
        data_mask: dict[str, Any],
    ) -> dict[int, bytes]:
        if not chart_ids:
            return {}

        response = self.request(
            "POST",
            f"/api/v1/dashboard/{dashboard_id}/chart_screenshots/",
            {
                "chart_ids": chart_ids,
                "activeTabs": active_tabs,
                "dataMask": data_mask,
                "anchor": "",
                "urlParams": [],
            },
            timeout_seconds=180,
        )
        result = response.get("result") or response
        encoded_images = result.get("chart_images")
        if not isinstance(encoded_images, dict):
            raise SupersetEmbedError("Superset did not return chart screenshots.")

        screenshots = {}
        for chart_id in chart_ids:
            encoded = encoded_images.get(str(chart_id))
            if not isinstance(encoded, str):
                raise SupersetEmbedError(
                    f"Superset did not return a screenshot for chart {chart_id}."
                )
            try:
                image = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError) as error:
                raise SupersetEmbedError(
                    f"Superset returned an invalid screenshot for chart {chart_id}."
                ) from error
            if not image.startswith(self._PNG_SIGNATURE):
                raise SupersetEmbedError(f"Superset returned an invalid PNG for chart {chart_id}.")
            screenshots[chart_id] = image
        return screenshots

    def create_guest_token(self, dashboard_id: str) -> str:
        result = self.request(
            "POST",
            "/api/v1/security/guest_token/",
            {
                "user": {"username": "ai-bi-frontend-demo"},
                "resources": [{"type": "dashboard", "id": dashboard_id}],
                "rls": [],
            },
        )
        token = result.get("token")
        if not token:
            raise SupersetEmbedError("Superset did not return a guest token.")
        return str(token)
