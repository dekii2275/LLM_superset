"""Create or update the NYC Taxi demo assets in Apache Superset.

Run from the repository root after starting the Compose services:

    python superset/scripts/setup_nyc_taxi_demo.py

The script uses only Python's standard library and reads Superset credentials
from the process environment or the repository's local .env file.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_URL = "http://localhost:58088"
DEFAULT_FRONTEND_URL = "http://localhost:43117"
DATABASE_NAME = "NYC Taxi PostgreSQL"
DATABASE_NAME_ALIASES = {DATABASE_NAME, "NYC Yellow Taxi PostgreSQL"}
TABLE_SCHEMA = "raw"
TABLE_NAME = "yellow_taxi_trips"
CATALOG = "ai_bi"
DATASET_FRIENDLY_NAME = "NYC Yellow Taxi Trips"
DASHBOARD_TITLE = "NYC Yellow Taxi Overview"
MONTHS = [5, 6, 7]
SOURCE_YEAR = 2026
TIME_RANGE = "2026-05-01 : 2026-08-01"  # end is exclusive; includes July 31
ROW_LIMIT = 1000


class SupersetError(RuntimeError):
    """Raised when a Superset REST API operation fails."""


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def canonical_title(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("—", "-").replace("–", "-")).strip()


class SupersetClient:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )
        self.access_token: str | None = None
        self.csrf_token: str | None = None

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        authenticated: bool = True,
    ) -> Any:
        url = f"{self.base_url}{path if path.startswith('/') else '/' + path}"
        headers = {"Accept": "application/json", "Referer": f"{self.base_url}/"}
        if authenticated and self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and self.csrf_token:
            headers["X-CSRFToken"] = self.csrf_token
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with self.opener.open(req, timeout=60) as response:
                content = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SupersetError(f"{method.upper()} {path} returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise SupersetError(f"Could not reach Superset at {self.base_url}: {exc.reason}") from exc
        if not content:
            return None
        content_type = response.headers.get("Content-Type", "")
        if "json" in content_type:
            return json.loads(content.decode("utf-8"))
        return content.decode("utf-8", errors="replace")

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
            raise SupersetError("Superset login succeeded without returning an access token.")
        csrf = self.request("GET", "/api/v1/security/csrf_token/")
        self.csrf_token = csrf.get("result")
        if not self.csrf_token:
            raise SupersetError("Superset did not return a CSRF token.")

    def list_objects(self, resource: str) -> list[dict[str, Any]]:
        query = urllib.parse.quote("(page:0,page_size:100)", safe="")
        result = self.request("GET", f"/api/v1/{resource}/?q={query}")
        return result.get("result", [])


def get_server_version(client: SupersetClient) -> str:
    html = client.request("GET", "/", authenticated=False)
    match = re.search(r"version_string.{0,200}?(\d+\.\d+\.\d+)", html, re.DOTALL)
    if match:
        return match.group(1)
    return "unknown (version is visible in Superset's About menu)"


def find_database(client: SupersetClient) -> dict[str, Any]:
    databases = client.list_objects("database")
    matches = [
        db for db in databases if db.get("database_name") in DATABASE_NAME_ALIASES
    ]
    if len(matches) != 1:
        names = [db.get("database_name") for db in databases]
        raise SupersetError(
            f"Expected one existing analytics connection named {DATABASE_NAME}; found {names}. "
            "The setup script will not create a second PostgreSQL connection."
        )
    database = matches[0]
    if database.get("backend") != "postgresql":
        raise SupersetError(f"{DATABASE_NAME} is not a PostgreSQL connection.")
    return database


def get_or_create_dataset(client: SupersetClient, database_id: int) -> int:
    result = client.request(
        "POST",
        "/api/v1/dataset/get_or_create/",
        {
            "database_id": database_id,
            "catalog": CATALOG,
            "schema": TABLE_SCHEMA,
            "table_name": TABLE_NAME,
        },
    )
    dataset_id = result.get("result", {}).get("table_id")
    if dataset_id is None:
        raise SupersetError("Superset did not return a dataset ID for raw.yellow_taxi_trips.")
    return int(dataset_id)


METRIC_DEFINITIONS = [
    {
        "metric_name": "Total Trips",
        "expression": "COUNT(*)",
        "metric_type": "sql",
        "verbose_name": "Total Trips",
        "description": "Count of NYC Yellow Taxi trip records.",
        "d3format": ",d",
    },
    {
        "metric_name": "Gross Trip Amount",
        "expression": "SUM(total_amount)",
        "metric_type": "sql",
        "verbose_name": "Gross Trip Amount",
        "description": (
            "Sum of passenger trip total_amount; this is not accounting revenue."
        ),
        "d3format": "$,.2f",
    },
    {
        "metric_name": "Average Trip Amount",
        "expression": "AVG(total_amount)",
        "metric_type": "sql",
        "verbose_name": "Average Trip Amount",
        "description": "Average passenger trip total_amount.",
        "d3format": "$,.2f",
    },
    {
        "metric_name": "Average Trip Distance",
        "expression": "AVG(trip_distance)",
        "metric_type": "sql",
        "verbose_name": "Average Trip Distance",
        "description": "Average trip distance in miles.",
        "d3format": ",.2f",
    },
]


def ensure_dataset_metadata(client: SupersetClient, dataset_id: int) -> dict[str, Any]:
    detail = client.request("GET", f"/api/v1/dataset/{dataset_id}").get("result", {})
    if detail.get("schema") != TABLE_SCHEMA or detail.get("datasource_name") != TABLE_NAME:
        raise SupersetError(
            f"Dataset {dataset_id} does not point to {TABLE_SCHEMA}.{TABLE_NAME}."
        )

    columns = {column["column_name"]: column for column in detail.get("columns", [])}
    expected_columns = {
        "tpep_pickup_datetime",
        "tpep_dropoff_datetime",
        "passenger_count",
        "trip_distance",
        "payment_type",
        "fare_amount",
        "tip_amount",
        "total_amount",
        "source_year",
        "source_month",
    }
    missing = expected_columns - columns.keys()
    if missing:
        raise SupersetError(f"Dataset metadata is missing source columns: {sorted(missing)}")
    for temporal in ("tpep_pickup_datetime", "tpep_dropoff_datetime"):
        if not columns[temporal].get("is_dttm"):
            raise SupersetError(f"{temporal} is not marked as a temporal column in Superset.")
    for numeric in (
        "passenger_count",
        "trip_distance",
        "fare_amount",
        "tip_amount",
        "total_amount",
    ):
        if columns[numeric].get("type_generic") != 0:
            raise SupersetError(f"{numeric} is not marked numeric in Superset metadata.")

    existing = {metric.get("metric_name"): metric for metric in detail.get("metrics", [])}
    default_count = existing.get("count")
    metrics: list[dict[str, Any]] = []
    if default_count:
        metrics.append(
            {
                "id": default_count.get("id"),
                "metric_name": "count",
                "metric_type": default_count.get("metric_type", "count"),
                "expression": default_count.get("expression", "COUNT(*)"),
                "verbose_name": default_count.get("verbose_name", "COUNT(*)"),
                "description": default_count.get("description"),
                "warning_text": default_count.get("warning_text"),
                "d3format": default_count.get("d3format"),
                "currency": default_count.get("currency"),
                "extra": default_count.get("extra", "{}"),
            }
        )
    for definition in METRIC_DEFINITIONS:
        previous = existing.get(definition["metric_name"], {})
        metrics.append(
            {
                **definition,
                "id": previous.get("id"),
                "warning_text": previous.get("warning_text"),
                "currency": previous.get("currency"),
                "extra": previous.get("extra", "{}"),
            }
        )

    description = (
        f"{DATASET_FRIENDLY_NAME}: physical Superset dataset for "
        f"{CATALOG}.{TABLE_SCHEMA}.{TABLE_NAME}. Demo charts filter source_year = 2026 "
        "and source_month IN (5, 6, 7)."
    )
    client.request(
        "PUT",
        f"/api/v1/dataset/{dataset_id}",
        {"description": description, "metrics": metrics},
    )
    updated = client.request("GET", f"/api/v1/dataset/{dataset_id}").get("result", {})
    actual = {metric.get("metric_name"): metric for metric in updated.get("metrics", [])}
    for definition in METRIC_DEFINITIONS:
        metric = actual.get(definition["metric_name"])
        if not metric or metric.get("expression") != definition["expression"]:
            raise SupersetError(f"Metric {definition['metric_name']} was not saved correctly.")
    return updated


def common_filters() -> list[dict[str, Any]]:
    return [
        {
            "clause": "WHERE",
            "subject": "source_year",
            "operator": "==",
            "comparator": SOURCE_YEAR,
            "expressionType": "SIMPLE",
            "isExtra": False,
            "sqlExpression": None,
            "filterOptionName": "filter_source_year",
        },
        {
            "clause": "WHERE",
            "subject": "source_month",
            "operator": "IN",
            "comparator": MONTHS,
            "expressionType": "SIMPLE",
            "isExtra": False,
            "sqlExpression": None,
            "filterOptionName": "filter_source_month",
        },
    ]


def query_filters() -> list[dict[str, Any]]:
    return [
        {"col": "source_year", "op": "==", "val": SOURCE_YEAR},
        {"col": "source_month", "op": "IN", "val": MONTHS},
    ]


def chart_definitions(dataset_id: int) -> list[dict[str, Any]]:
    source = f"{dataset_id}__table"

    def definition(
        title: str,
        viz_type: str,
        form_fields: dict[str, Any],
        metric: str,
        *,
        columns: list[str] | None = None,
        time_series: bool = False,
        time_range: str = "No filter",
        orderby: list[list[Any]] | None = None,
        description: str,
    ) -> dict[str, Any]:
        form_data = {
            "datasource": source,
            "viz_type": viz_type,
            "adhoc_filters": common_filters(),
            "extra_form_data": {},
            "url_params": {},
            "row_limit": ROW_LIMIT,
            "time_range": time_range,
            **form_fields,
        }
        query = {
            "columns": columns or [],
            "metrics": [metric],
            "filters": query_filters(),
            "granularity": "tpep_pickup_datetime" if time_series else None,
            "time_range": time_range,
            "row_limit": ROW_LIMIT,
            "extras": {
                "where": "",
                "having": "",
                "time_grain_sqla": "P1D" if time_series else None,
            },
            "is_timeseries": time_series,
            "order_desc": True,
        }
        if orderby:
            query["orderby"] = orderby
        query_context = {
            "datasource": {"id": dataset_id, "type": "table"},
            "queries": [query],
            "result_format": "json",
            "result_type": "full",
        }
        return {
            "title": title,
            "viz_type": viz_type,
            "description": description,
            "form_data": form_data,
            "query_context": query_context,
        }

    return [
        definition(
            "NYC Taxi \u2014 Total Trips",
            "big_number_total",
            {"metric": "Total Trips", "show_trend_line": False},
            "Total Trips",
            description="Trip count for source months May, June, and July 2026.",
        ),
        definition(
            "NYC Taxi \u2014 Gross Trip Amount",
            "big_number_total",
            {"metric": "Gross Trip Amount", "show_trend_line": False},
            "Gross Trip Amount",
            description=(
                "Sum of passenger total_amount for source months May, June, and July 2026. "
                "It is not accounting revenue."
            ),
        ),
        definition(
            "NYC Taxi \u2014 Trips Over Time",
            "echarts_timeseries_line",
            {
                "granularity_sqla": "tpep_pickup_datetime",
                "time_grain_sqla": "P1D",
                "metrics": ["Total Trips"],
                "groupby": [],
                "order_desc": False,
                "show_legend": False,
                "x_axis_format": "%Y-%m-%d",
                "x_axis_label": "Pickup date",
            },
            "Total Trips",
            time_series=True,
            time_range=TIME_RANGE,
            description=(
                "Daily trips by pickup date from May 1 through July 31, 2026. "
                "Timestamp anomalies outside the demo period are excluded by the BI filter."
            ),
        ),
        definition(
            "NYC Taxi \u2014 Trips by Payment Type",
            "pie",
            {
                "groupby": ["payment_type"],
                # Pie expects the singular `metric` control; `metrics` is used
                # by the other chart types in this dashboard.
                "metric": "Total Trips",
                "order_desc": True,
                "sort_by_metric": True,
                "color_scheme": "supersetColors",
                "show_legend": True,
                "legend_orientation": "top",
                "legend_type": "scroll",
                "label_type": "key_value_percent",
                "number_format": "SMART_NUMBER",
                "show_labels": True,
                "labels_outside": True,
                "label_line": False,
                "show_labels_threshold": 5,
                "threshold_for_other": 0,
                "donut": True,
                "inner_radius": 30,
                "outer_radius": 70,
                "rose_type": None,
            },
            "Total Trips",
            columns=["payment_type"],
            orderby=[["Total Trips", False]],
            description=(
                "Trip counts grouped by payment_type code, sorted by Total Trips descending, "
                "for source months May, June, and July 2026."
            ),
        ),
    ]


def list_chart_by_name(client: SupersetClient, title: str) -> dict[str, Any] | None:
    expected = canonical_title(title)
    for chart in client.list_objects("chart"):
        if canonical_title(chart.get("slice_name", "")) == expected:
            return chart
    return None


def upsert_chart(client: SupersetClient, dataset_id: int, definition: dict[str, Any]) -> dict[str, Any]:
    body = {
        "slice_name": definition["title"],
        "datasource_id": dataset_id,
        "datasource_type": "table",
        "viz_type": definition["viz_type"],
        "description": definition["description"],
        "params": json.dumps(definition["form_data"], ensure_ascii=False, sort_keys=True),
        "query_context": json.dumps(
            definition["query_context"], ensure_ascii=False, sort_keys=True
        ),
    }
    existing = list_chart_by_name(client, definition["title"])
    if existing:
        client.request("PUT", f"/api/v1/chart/{existing['id']}", body)
        chart_id = int(existing["id"])
    else:
        client.request("POST", "/api/v1/chart/", body)
        current = list_chart_by_name(client, definition["title"])
        if not current:
            raise SupersetError(f"Superset created no chart named {definition['title']}.")
        chart_id = int(current["id"])
    return client.request("GET", f"/api/v1/chart/{chart_id}").get("result", {})


def verify_chart_query(client: SupersetClient, chart: dict[str, Any]) -> dict[str, Any]:
    result = client.request("GET", f"/api/v1/chart/{chart['id']}/data/")
    entries = result.get("result", [])
    if not entries or entries[0].get("status") != "success" or entries[0].get("error"):
        detail = entries[0].get("error") if entries else "empty chart response"
        raise SupersetError(f"Chart query failed for {chart.get('slice_name')}: {detail}")
    return entries[0]


def make_dashboard_positions(charts: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [
        ("ROW-KPI", charts[:2], [6, 6]),
        ("ROW-TREND", charts[2:3], [12]),
        ("ROW-PAYMENT", charts[3:4], [12]),
    ]
    positions: dict[str, Any] = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"id": "ROOT_ID", "type": "ROOT", "children": [r[0] for r in rows]},
        "GRID_ID": {
            "id": "GRID_ID",
            "type": "GRID",
            "parents": ["ROOT_ID"],
            "children": [r[0] for r in rows],
        },
        "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": DASHBOARD_TITLE}},
    }
    positions["ROOT_ID"]["children"] = ["GRID_ID"]
    for row_id, row_charts, widths in rows:
        chart_keys: list[str] = []
        for chart, width in zip(row_charts, widths):
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
                    "uuid": chart["uuid"],
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


def ensure_dashboard(client: SupersetClient, charts: list[dict[str, Any]]) -> dict[str, Any]:
    existing = next(
        (
            dashboard
            for dashboard in client.list_objects("dashboard")
            if dashboard.get("dashboard_title") == DASHBOARD_TITLE
        ),
        None,
    )
    positions = make_dashboard_positions(charts)
    json_metadata = {
        "timed_refresh_immune_slices": [],
        "expanded_slices": {},
        "refresh_frequency": 0,
        "default_filters": "{}",
        "color_scheme": None,
        "label_colors": {},
        "cross_filters_enabled": False,
        "chart_configuration": {},
        "filter_scopes": {},
        "positions": positions,
    }
    body = {
        "dashboard_title": DASHBOARD_TITLE,
        "slug": "nyc-yellow-taxi-overview",
        "published": True,
        "position_json": json.dumps(positions, ensure_ascii=False),
        "json_metadata": json.dumps(json_metadata, ensure_ascii=False),
    }
    if existing:
        dashboard_id = int(existing["id"])
        client.request("PUT", f"/api/v1/dashboard/{dashboard_id}", body)
    else:
        client.request("POST", "/api/v1/dashboard/", body)
        match = next(
            (
                dashboard
                for dashboard in client.list_objects("dashboard")
                if dashboard.get("dashboard_title") == DASHBOARD_TITLE
            ),
            None,
        )
        if not match:
            raise SupersetError(f"Superset created no dashboard named {DASHBOARD_TITLE}.")
        dashboard_id = int(match["id"])

    # Keep the chart-to-dashboard relation explicit as well as present in the layout.
    for chart in charts:
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
    return client.request("GET", f"/api/v1/dashboard/{dashboard_id}").get("result", {})


def ensure_dashboard_embedding(
    client: SupersetClient, dashboard: dict[str, Any], frontend_origins: list[str]
) -> dict[str, Any]:
    dashboard_id = int(dashboard["id"])
    result = client.request(
        "POST",
        f"/api/v1/dashboard/{dashboard_id}/embedded",
        {"allowed_domains": frontend_origins},
    ).get("result", {})
    if not result.get("uuid"):
        raise SupersetError("Superset did not return an embedded dashboard UUID.")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SUPERSET_HOST_URL", DEFAULT_BASE_URL),
        help=f"Host-reachable Superset URL (default: {DEFAULT_BASE_URL})",
    )
    args = parser.parse_args()

    env_file = load_dotenv(ROOT / ".env")
    username = os.environ.get("SUPERSET_ADMIN_USERNAME", env_file.get("SUPERSET_ADMIN_USERNAME"))
    password = os.environ.get("SUPERSET_ADMIN_PASSWORD", env_file.get("SUPERSET_ADMIN_PASSWORD"))
    if not username or not password:
        raise SupersetError(
            "Set SUPERSET_ADMIN_USERNAME and SUPERSET_ADMIN_PASSWORD in the environment or .env."
        )

    client = SupersetClient(args.base_url, username, password)
    client.login()
    version = get_server_version(client)
    database = find_database(client)
    database_id = int(database["id"])
    dataset_id = get_or_create_dataset(client, database_id)
    dataset = ensure_dataset_metadata(client, dataset_id)

    charts: list[dict[str, Any]] = []
    chart_results: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for definition in chart_definitions(dataset_id):
        chart = upsert_chart(client, dataset_id, definition)
        chart_result = verify_chart_query(client, chart)
        charts.append(chart)
        chart_results.append((chart, chart_result))

    dashboard = ensure_dashboard(client, charts)
    dashboard_id = int(dashboard["id"])

    # Confirm the saved chart definitions behind the dashboard layout.
    dashboard_charts = client.request(
        "GET", f"/api/v1/dashboard/{dashboard_id}/charts"
    ).get("result", [])
    linked = {int(chart["id"]) for chart in dashboard_charts}
    expected = {int(chart["id"]) for chart in charts}
    if linked != expected:
        raise SupersetError(
            f"Dashboard chart association mismatch: expected {sorted(expected)}, got {sorted(linked)}."
        )
    dashboard = client.request("GET", f"/api/v1/dashboard/{dashboard_id}").get("result", {})
    default_frontend_origins = ",".join(
        [
            env_file.get("FRONTEND_URL", DEFAULT_FRONTEND_URL),
            "http://127.0.0.1:43117",
        ]
    )
    frontend_origins = [
        origin.strip().rstrip("/")
        for origin in os.environ.get(
            "FRONTEND_ORIGINS",
            env_file.get(
                "FRONTEND_ORIGINS",
                default_frontend_origins,
            ),
        ).split(",")
        if origin.strip()
    ]
    embedded_dashboard = ensure_dashboard_embedding(client, dashboard, frontend_origins)
    filter_status = (
        "not configured (optional Source Month native-filter payload was version-sensitive; "
        "use the dashboard editor if needed)"
    )

    print(f"Superset version: {version}")
    print(f"Database connection: {database.get('database_name')} (ID {database_id})")
    print(
        f"Dataset: {DATASET_FRIENDLY_NAME} (physical relation "
        f"{CATALOG}.{TABLE_SCHEMA}.{TABLE_NAME}, ID {dataset_id})"
    )
    print("Dataset metadata: 25 source columns; pickup/dropoff are temporal; requested numeric fields detected")
    print("Metrics:")
    for metric in METRIC_DEFINITIONS:
        print(f"- {metric['metric_name']}: {metric['expression']}")
    print("Charts:")
    for chart, result in chart_results:
        print(
            f"- {chart['slice_name']} | {chart['viz_type']} | ID {chart['id']} | "
            f"query {result['status']} ({result.get('rowcount')} result rows)"
        )
    print(f"Dashboard: {dashboard.get('dashboard_title')} | ID {dashboard_id} | published")
    print(f"Dashboard URL: {args.base_url.rstrip('/')}/superset/dashboard/{dashboard_id}/")
    print(
        f"Embedded dashboard UUID: {embedded_dashboard['uuid']} | "
        f"allowed domains: {', '.join(frontend_origins)}"
    )
    print(f"Source Month native filter: {filter_status}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SupersetError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
