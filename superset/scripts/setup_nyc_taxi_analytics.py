"""Create an idempotent, production-reusable NYC Taxi analytics dashboard.

Run from the repository root after Superset and PostgreSQL are available:

    python superset/scripts/setup_nyc_taxi_analytics.py
    python superset/scripts/setup_nyc_taxi_analytics.py --style-only

The script reads Superset credentials from the process environment or
`.env.local` / `.env.prod`. It creates a SQL-backed dataset that joins taxi
trips to the TLC zone lookup, then upserts its charts and dashboard.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from setup_nyc_taxi_demo import (
    DEFAULT_BASE_URL,
    ROOT,
    SupersetClient,
    SupersetError,
    canonical_title,
    ensure_dashboard_embedding,
    find_database,
    get_server_version,
    load_dotenv,
)


DATABASE_NAME = "NYC Taxi PostgreSQL"
DATASET_NAME = "nyc_taxi_analysis"
DASHBOARD_TITLE = "NYC Taxi Trips Analysis"
DASHBOARD_SLUG = "nyc-taxi-trips-analysis"
ROW_LIMIT = 1000
BACKGROUND_IMAGE = ROOT / "superset" / "assets" / "superset-dashboard-background.png"


def dashboard_background_css() -> str:
    image = base64.b64encode(BACKGROUND_IMAGE.read_bytes()).decode("ascii")
    return f"""\
.dashboard-content {{
  background-color: #eef8f3 !important;
  background-image: linear-gradient(rgba(239, 249, 244, 0.58), rgba(239, 249, 244, 0.58)), url("data:image/png;base64,{image}") !important;
  background-size: cover !important;
  background-position: center center !important;
  background-repeat: no-repeat !important;
  background-attachment: fixed !important;
}}
.dashboard-content .dashboard-component {{
  background: transparent !important;
}}
.dashboard-content .dashboard-component-chart-holder {{
  background: rgba(255, 255, 255, 0.75) !important;
  -webkit-backdrop-filter: blur(8px) !important;
  backdrop-filter: blur(8px) !important;
  border: 1px solid rgba(173, 199, 189, 0.8) !important;
  border-radius: 12px !important;
  box-shadow: 0 8px 24px rgba(29, 54, 46, 0.14) !important;
}}
.dashboard-content .dashboard-component-chart-holder .dashboard-chart,
.dashboard-content .dashboard-component-chart-holder .chart-container,
.dashboard-content .dashboard-component-chart-holder .slice_container,
.dashboard-content .dashboard-component-chart-holder canvas {{
  background: transparent !important;
  background-color: transparent !important;
}}
.dashboard-content .dashboard-component-tabs {{
  background: transparent !important;
}}
"""

VIRTUAL_DATASET_SQL = """SELECT
    trips.*,
    pickup.borough AS pickup_borough,
    pickup.zone AS pickup_zone,
    dropoff.borough AS dropoff_borough,
    dropoff.zone AS dropoff_zone,
    CASE trips.vendor_id
        WHEN 1 THEN 'Creative Mobile Technologies'
        WHEN 2 THEN 'VeriFone Inc'
        ELSE 'Vendor ' || COALESCE(trips.vendor_id::text, 'Unknown')
    END AS vendor_name,
    CASE trips.payment_type
        WHEN 1 THEN 'Credit Card'
        WHEN 2 THEN 'Cash'
        WHEN 3 THEN 'No Charge'
        WHEN 4 THEN 'Dispute'
        WHEN 5 THEN 'Unknown'
        WHEN 6 THEN 'Voided Trip'
        ELSE 'Other'
    END AS payment_type_name,
    TRIM(TO_CHAR(trips.tpep_pickup_datetime, 'FMDay')) AS day_of_week,
    CASE
        WHEN EXTRACT(HOUR FROM trips.tpep_pickup_datetime) BETWEEN 5 AND 6
            THEN 'Early Morning'
        WHEN EXTRACT(HOUR FROM trips.tpep_pickup_datetime) BETWEEN 7 AND 11
            THEN 'Morning'
        WHEN EXTRACT(HOUR FROM trips.tpep_pickup_datetime) BETWEEN 12 AND 16
            THEN 'Afternoon'
        WHEN EXTRACT(HOUR FROM trips.tpep_pickup_datetime) BETWEEN 17 AND 20
            THEN 'Evening'
        ELSE 'Night'
    END AS time_of_day
FROM raw.yellow_taxi_trips AS trips
LEFT JOIN raw.taxi_zone_lookup AS pickup
    ON trips.pu_location_id = pickup.location_id
LEFT JOIN raw.taxi_zone_lookup AS dropoff
    ON trips.do_location_id = dropoff.location_id"""

METRICS = [
    {
        "metric_name": "Total Trips",
        "expression": "COUNT(*)",
        "metric_type": "sql",
        "verbose_name": "Total No Of Trips",
        "description": "Number of trip records.",
        "d3format": ",d",
    },
    {
        "metric_name": "Average Trip Distance",
        "expression": "AVG(trip_distance)",
        "metric_type": "sql",
        "verbose_name": "Avg Distance Per Trip",
        "description": "Average trip distance in miles.",
        "d3format": ",.2f",
    },
    {
        "metric_name": "Total Passengers",
        "expression": "SUM(passenger_count)",
        "metric_type": "sql",
        "verbose_name": "Total No Of Passengers",
        "description": "Sum of passenger_count across trip records.",
        "d3format": ",d",
    },
    {
        "metric_name": "Average Trips Per Day",
        "expression": "COUNT(*)::numeric / NULLIF(COUNT(DISTINCT tpep_pickup_datetime::date), 0)",
        "metric_type": "sql",
        "verbose_name": "Avg Trips Per Day",
        "description": "Trip records divided by distinct pickup dates in the selected data.",
        "d3format": ",.0f",
    },
    {
        "metric_name": "Total Trip Zones",
        "expression": "(SELECT COUNT(DISTINCT location_id) FROM raw.taxi_zone_lookup)",
        "metric_type": "sql",
        "verbose_name": "Total No of Trip Zones",
        "description": "Number of zones in the NYC TLC taxi-zone lookup table.",
        "d3format": ",d",
    },
    {
        "metric_name": "Average Fare Per Trip",
        "expression": "AVG(fare_amount)",
        "metric_type": "sql",
        "verbose_name": "Avg Fare Per Trips",
        "description": "Average fare_amount in USD per trip.",
        "d3format": "$,.2f",
    },
    {
        "metric_name": "Total Revenue",
        "expression": "SUM(total_amount)",
        "metric_type": "sql",
        "verbose_name": "Total Revenue",
        "description": "Sum of trip total_amount in USD, including recorded fees and taxes.",
        "d3format": "$,.2s",
    },
]


def ensure_dataset(client: SupersetClient, database_id: int) -> dict[str, Any]:
    datasets = client.list_objects("dataset")
    match = next(
        (
            dataset
            for dataset in datasets
            if dataset.get("table_name") == DATASET_NAME
            or dataset.get("datasource_name") == DATASET_NAME
        ),
        None,
    )
    body = {
        "database": database_id,
        "schema": "raw",
        "table_name": DATASET_NAME,
        "sql": VIRTUAL_DATASET_SQL,
    }
    if match:
        dataset_id = int(match["id"])
        database_ref = match.get("database")
        existing_database_id = (
            database_ref.get("id") if isinstance(database_ref, dict) else match.get("database_id")
        )
        if existing_database_id is not None and int(existing_database_id) != database_id:
            raise SupersetError(
                f"Dataset {DATASET_NAME} already exists on a different database connection."
            )
        client.request(
            "PUT",
            f"/api/v1/dataset/{dataset_id}",
            {key: body[key] for key in ("schema", "table_name", "sql")},
        )
        client.request("PUT", f"/api/v1/dataset/{dataset_id}/refresh")
    else:
        created_response = client.request("POST", "/api/v1/dataset/", body)
        result = created_response.get("result", {})
        dataset_id = int(
            created_response.get("id") or result.get("id") or result.get("table_id") or 0
        )
        if not dataset_id:
            current = client.list_objects("dataset")
            result = next(
                (
                    item
                    for item in current
                    if item.get("table_name") == DATASET_NAME
                    or item.get("datasource_name") == DATASET_NAME
                ),
                {},
            )
            dataset_id = int(result.get("id") or 0)
        if not dataset_id:
            raise SupersetError(f"Superset did not return the {DATASET_NAME} dataset ID.")

    detail = client.request("GET", f"/api/v1/dataset/{dataset_id}").get("result", {})
    database_ref = detail.get("database")
    detail_database_id = (
        database_ref.get("id") if isinstance(database_ref, dict) else detail.get("database_id")
    )
    if detail_database_id is not None and int(detail_database_id) != database_id:
        raise SupersetError(f"Dataset {DATASET_NAME} resolved to the wrong database.")
    columns = {column.get("column_name"): column for column in detail.get("columns", [])}
    required = {
        "vendor_id",
        "vendor_name",
        "payment_type_name",
        "day_of_week",
        "time_of_day",
        "passenger_count",
        "trip_distance",
        "fare_amount",
        "total_amount",
        "tpep_pickup_datetime",
        "source_year",
        "pickup_borough",
        "pickup_zone",
    }
    missing = required - columns.keys()
    if missing:
        raise SupersetError(
            f"Dataset {DATASET_NAME} is missing columns {sorted(missing)}. "
            "Check raw.yellow_taxi_trips and raw.taxi_zone_lookup."
        )

    old_metrics = {metric.get("metric_name"): metric for metric in detail.get("metrics", [])}
    metrics: list[dict[str, Any]] = []
    default_count = old_metrics.get("count")
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
    for metric in METRICS:
        previous = old_metrics.get(metric["metric_name"], {})
        metrics.append(
            {
                **metric,
                **({"id": previous["id"]} if previous.get("id") is not None else {}),
                "warning_text": previous.get("warning_text"),
                "currency": previous.get("currency"),
                "extra": previous.get("extra", "{}"),
            }
        )
    client.request(
        "PUT",
        f"/api/v1/dataset/{dataset_id}",
        {
            "description": (
                "NYC taxi trip analysis dataset. Joins raw.yellow_taxi_trips to "
                "raw.taxi_zone_lookup for pickup/dropoff borough and zone labels."
            ),
            "main_dttm_col": "tpep_pickup_datetime",
            "metrics": metrics,
        },
    )
    return client.request("GET", f"/api/v1/dataset/{dataset_id}").get("result", {})


def available_years(
    client: SupersetClient, database_id: int, requested_years: list[int] | None = None
) -> list[int]:
    if requested_years:
        year_list = ", ".join(str(year) for year in sorted(set(requested_years)))
        sql = (
            "SELECT DISTINCT source_year FROM raw.yellow_taxi_trips "
            f"WHERE source_year IN ({year_list}) ORDER BY source_year DESC LIMIT 10"
        )
    else:
        sql = (
            "SELECT DISTINCT source_year FROM raw.yellow_taxi_trips "
            "WHERE source_year IS NOT NULL ORDER BY source_year DESC LIMIT 2"
        )
    response = client.request(
        "POST",
        "/api/v1/sqllab/execute/",
        {
            "client_id": uuid.uuid4().hex[:11],
            "database_id": database_id,
            "sql": sql,
            "runAsync": False,
            "queryLimit": 10,
            "expand_data": True,
        },
    )
    result = response.get("result", response)
    rows = result.get("data", [])
    available = {
        int(row["source_year"]) for row in rows if row.get("source_year") is not None
    }
    if not available:
        raise SupersetError(
            "Could not read source_year values from raw.yellow_taxi_trips; "
            "the dashboard was not created."
        )
    if requested_years:
        missing = sorted(set(requested_years) - available)
        if missing:
            raise SupersetError(f"Requested source years are not present in the dataset: {missing}.")
        return sorted(set(requested_years))
    return sorted(available)[-2:]


def metric_definition(
    title: str,
    viz_type: str,
    dataset_id: int,
    metric: str,
    *,
    groupby: list[str] | None = None,
    x_axis: str | None = None,
    year: int | None = None,
    years: list[int] | None = None,
    exclude_values: dict[str, list[str]] | None = None,
    limit: int = ROW_LIMIT,
    options: dict[str, Any] | None = None,
    time_series: bool = False,
) -> dict[str, Any]:
    source = f"{dataset_id}__table"
    filters = []
    adhoc_filters = []
    if year is not None:
        filters.append({"col": "source_year", "op": "==", "val": year})
        adhoc_filters.append(
            {
                "clause": "WHERE",
                "subject": "source_year",
                "operator": "==",
                "comparator": year,
                "expressionType": "SIMPLE",
                "isExtra": False,
                "sqlExpression": None,
                "filterOptionName": f"filter_source_year_{year}",
            }
        )
    elif years:
        filters.append({"col": "source_year", "op": "IN", "val": years})
        adhoc_filters.append(
            {
                "clause": "WHERE",
                "subject": "source_year",
                "operator": "IN",
                "comparator": years,
                "expressionType": "SIMPLE",
                "isExtra": False,
                "sqlExpression": None,
                "filterOptionName": "filter_latest_source_years",
            }
        )
    for column, values in (exclude_values or {}).items():
        filters.append({"col": column, "op": "NOT IN", "val": values})
        adhoc_filters.append(
            {
                "clause": "WHERE",
                "subject": column,
                "operator": "NOT IN",
                "comparator": values,
                "expressionType": "SIMPLE",
                "isExtra": False,
                "sqlExpression": None,
                "filterOptionName": f"exclude_{column}",
            }
        )
    query = {
        "columns": (
            [{
                "columnType": "BASE_AXIS",
                "sqlExpression": x_axis,
                "label": x_axis,
                "expressionType": "SQL",
            }]
            if x_axis
            else groupby or []
        ),
        "metrics": [metric],
        "filters": filters,
        "granularity": "tpep_pickup_datetime" if time_series else None,
        "time_range": "No filter",
        "row_limit": limit,
        "extras": {
            "where": "",
            "having": "",
            "time_grain_sqla": "P1D" if time_series else None,
        },
        "is_timeseries": time_series,
        "order_desc": True,
    }
    if (groupby or x_axis) and not time_series:
        query["orderby"] = [[metric, False]]
    if time_series:
        query["orderby"] = [[metric, False]]
    form_data = {
        "datasource": source,
        "viz_type": viz_type,
        "adhoc_filters": adhoc_filters,
        "extra_form_data": {},
        "url_params": {},
        "row_limit": limit,
        "time_range": "No filter",
        **(options or {}),
    }
    return {
        "title": title,
        "viz_type": viz_type,
        "description": options.get("description", title) if options else title,
        "form_data": form_data,
        "query_context": {
            "datasource": {"id": dataset_id, "type": "table"},
            "queries": [query],
            "result_format": "json",
            "result_type": "full",
        },
    }


def chart_definitions(dataset_id: int, years: list[int]) -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    kpis = [
        ("Total No Of Trips", "Total Trips", ",d"),
        ("Avg Distance Per Trip", "Average Trip Distance", ",.2f"),
        ("Total No Of Passengers", "Total Passengers", ",d"),
        ("Avg Trips Per Day", "Average Trips Per Day", ",.0f"),
        ("Total No of Trip Zones", "Total Trip Zones", ",d"),
        ("Avg Fare Per Trips", "Average Fare Per Trip", "$,.2f"),
        ("Total Revenue", "Total Revenue", "$,.2s"),
    ]
    for title, metric, number_format in kpis:
        options = {
            "metric": metric,
            "show_trend_line": False,
            "y_axis_format": number_format,
        }
        definitions.append(
            metric_definition(
                title,
                "big_number_total",
                dataset_id,
                metric,
                years=years,
                options=options,
            )
        )
        definitions.append(
            metric_definition(
                f"{title} (Trip Patterns)",
                "big_number_total",
                dataset_id,
                metric,
                years=years,
                options=options,
            )
        )

    for year in years:
        definitions.append(
            metric_definition(
                f"Taxi Trips Trend in {year}",
                "echarts_timeseries_line",
                dataset_id,
                "Total Trips",
                year=year,
                time_series=True,
                options={
                    "granularity_sqla": "tpep_pickup_datetime",
                    "time_grain_sqla": "P1D",
                    "metrics": ["Total Trips"],
                    "groupby": [],
                    "order_desc": False,
                    "show_legend": False,
                    "x_axis_format": "%d %b",
                    "x_axis_label": "Pickup date",
                    "y_axis_format": ",.0f",
                    "color_scheme": "supersetColors",
                },
            )
        )
        definitions.append(
            metric_definition(
                f"Taxi Revenue Trend in {year}",
                "echarts_timeseries_line",
                dataset_id,
                "Total Revenue",
                year=year,
                time_series=True,
                options={
                    "granularity_sqla": "tpep_pickup_datetime",
                    "time_grain_sqla": "P1D",
                    "metrics": ["Total Revenue"],
                    "groupby": [],
                    "order_desc": False,
                    "show_legend": False,
                    "x_axis_format": "%d %b",
                    "x_axis_label": "Pickup date",
                    "y_axis_format": "$,.0s",
                    "color_scheme": "supersetColors",
                },
            )
        )

    definitions.extend(
        [
            metric_definition(
                "Total Trips by Vendor",
                "pie",
                dataset_id,
                "Total Trips",
                groupby=["vendor_name"],
                years=years,
                options={
                    "groupby": ["vendor_name"],
                    "metric": "Total Trips",
                    "show_legend": True,
                    "legend_orientation": "bottom",
                    "label_type": "key_value",
                    "number_format": ",d",
                    "show_labels": True,
                    "donut": True,
                    "inner_radius": 35,
                    "color_scheme": "supersetColors",
                },
            ),
            metric_definition(
                "Total Trips by Payment Type",
                "pie",
                dataset_id,
                "Total Trips",
                groupby=["payment_type_name"],
                years=years,
                options={
                    "groupby": ["payment_type_name"],
                    "metric": "Total Trips",
                    "show_legend": True,
                    "legend_orientation": "bottom",
                    "label_type": "key_value",
                    "number_format": ",d",
                    "show_labels": True,
                    "donut": True,
                    "inner_radius": 35,
                    "color_scheme": "supersetColors",
                },
            ),
            metric_definition(
                "Total Trips by Borough",
                "echarts_timeseries_bar",
                dataset_id,
                "Total Trips",
                x_axis="pickup_borough",
                years=years,
                exclude_values={"pickup_borough": ["Unknown", "N/A"]},
                options={
                    "x_axis": "pickup_borough",
                    "groupby": [],
                    "metrics": ["Total Trips"],
                    "orientation": "horizontal",
                    "order_desc": True,
                    "show_legend": False,
                    "show_value": True,
                    "color_scheme": "supersetColors",
                },
            ),
            metric_definition(
                "Top 6 Trip Zones",
                "echarts_timeseries_bar",
                dataset_id,
                "Total Trips",
                x_axis="pickup_zone",
                years=years,
                limit=6,
                options={
                    "x_axis": "pickup_zone",
                    "groupby": [],
                    "metrics": ["Total Trips"],
                    "orientation": "horizontal",
                    "order_desc": True,
                    "show_legend": False,
                    "show_value": True,
                    "color_scheme": "supersetColors",
                },
            ),
            metric_definition(
                "Trips by Day Of The Week",
                "echarts_timeseries_bar",
                dataset_id,
                "Total Trips",
                x_axis="day_of_week",
                years=years,
                options={
                    "x_axis": "day_of_week",
                    "groupby": [],
                    "metrics": ["Total Trips"],
                    "orientation": "horizontal",
                    "order_desc": True,
                    "show_legend": False,
                    "show_value": True,
                    "color_scheme": "supersetColors",
                },
            ),
            metric_definition(
                "Trips by Time Of The Day",
                "echarts_timeseries_bar",
                dataset_id,
                "Total Trips",
                x_axis="time_of_day",
                years=years,
                options={
                    "x_axis": "time_of_day",
                    "groupby": [],
                    "metrics": ["Total Trips"],
                    "orientation": "vertical",
                    "order_desc": True,
                    "show_legend": False,
                    "show_value": True,
                    "color_scheme": "supersetColors",
                },
            ),
            metric_definition(
                "Most Popular Pickup Borough",
                "echarts_timeseries_bar",
                dataset_id,
                "Total Trips",
                x_axis="pickup_borough",
                years=years,
                exclude_values={"pickup_borough": ["Unknown", "N/A"]},
                limit=5,
                options={
                    "x_axis": "pickup_borough",
                    "groupby": [],
                    "metrics": ["Total Trips"],
                    "orientation": "horizontal",
                    "order_desc": True,
                    "show_legend": False,
                    "show_value": True,
                    "color_scheme": "supersetColors",
                },
            ),
            metric_definition(
                "Most Popular Dropoff Borough",
                "echarts_timeseries_bar",
                dataset_id,
                "Total Trips",
                x_axis="dropoff_borough",
                years=years,
                exclude_values={"dropoff_borough": ["Unknown", "N/A"]},
                limit=5,
                options={
                    "x_axis": "dropoff_borough",
                    "groupby": [],
                    "metrics": ["Total Trips"],
                    "orientation": "horizontal",
                    "order_desc": True,
                    "show_legend": False,
                    "show_value": True,
                    "color_scheme": "supersetColors",
                },
            ),
            metric_definition(
                "Average Number Of Trips By Day",
                "echarts_timeseries_line",
                dataset_id,
                "Average Trips Per Day",
                x_axis="day_of_week",
                years=years,
                options={
                    "x_axis": "day_of_week",
                    "groupby": [],
                    "metrics": ["Average Trips Per Day"],
                    "order_desc": True,
                    "show_legend": False,
                    "show_value": True,
                    "markerSize": 5,
                    "y_axis_format": ",.0f",
                    "color_scheme": "supersetColors",
                },
            ),
            metric_definition(
                "Busiest Days Of The Week & Time Of The Day",
                "echarts_timeseries_line",
                dataset_id,
                "Total Trips",
                groupby=["time_of_day"],
                years=years,
                time_series=True,
                options={
                    "granularity_sqla": "tpep_pickup_datetime",
                    "time_grain_sqla": "P1D",
                    "metrics": ["Total Trips"],
                    "groupby": ["time_of_day"],
                    "order_desc": False,
                    "show_legend": True,
                    "x_axis_format": "%d %b",
                    "x_axis_label": "Pickup date",
                    "y_axis_format": ",.0f",
                    "color_scheme": "supersetColors",
                },
            ),
        ]
    )
    return definitions


def find_chart(client: SupersetClient, title: str, dataset_id: int) -> dict[str, Any] | None:
    expected = canonical_title(title)
    return next(
        (
            chart
            for chart in client.list_objects("chart")
            if canonical_title(chart.get("slice_name", "")) == expected
            and int(chart.get("datasource_id") or -1) == dataset_id
        ),
        None,
    )


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
    existing = find_chart(client, definition["title"], dataset_id)
    if existing:
        chart_id = int(existing["id"])
        client.request("PUT", f"/api/v1/chart/{chart_id}", body)
    else:
        client.request("POST", "/api/v1/chart/", body)
        created = find_chart(client, definition["title"], dataset_id)
        if not created:
            raise SupersetError(f"Superset created no chart named {definition['title']}.")
        chart_id = int(created["id"])
    chart = client.request("GET", f"/api/v1/chart/{chart_id}").get("result", {})
    return chart


def dashboard_positions(charts: list[dict[str, Any]], years: list[int]) -> dict[str, Any]:
    by_title = {chart["slice_name"]: chart for chart in charts}
    kpi_titles = [
        "Total No Of Trips",
        "Avg Distance Per Trip",
        "Total No Of Passengers",
        "Avg Trips Per Day",
        "Total No of Trip Zones",
        "Avg Fare Per Trips",
        "Total Revenue",
    ]

    positions: dict[str, Any] = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"id": "ROOT_ID", "type": "ROOT", "children": ["GRID_ID"]},
        "GRID_ID": {"id": "GRID_ID", "type": "GRID", "parents": ["ROOT_ID"], "children": []},
        "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": DASHBOARD_TITLE}},
    }

    def add_row(
        container_id: str,
        parent_path: list[str],
        row_id: str,
        row_charts: list[tuple[str, int]],
        height: int,
    ) -> None:
        widths = [width for _, width in row_charts]
        # Use all 12 Superset grid columns. The embedded dashboard does not show a
        # persistent filter sidebar, so reserving a column here only leaves an
        # unused strip on the right and makes the last chart harder to read.
        if sum(widths) > 12:
            raise ValueError(f"Row {row_id} exceeds the 12-column dashboard grid.")
        chart_ids = []
        for (title, _), width in zip(row_charts, widths):
            chart = by_title[title]
            chart_key = f"CHART-{chart['id']}"
            chart_ids.append(chart_key)
            positions[chart_key] = {
                "id": chart_key,
                "type": "CHART",
                "children": [],
                "parents": [*parent_path, row_id],
                "meta": {
                    "chartId": int(chart["id"]),
                    "sliceName": chart["slice_name"],
                    "uuid": chart["uuid"],
                    "width": width,
                    "height": height,
                },
            }
            if chart["slice_name"].endswith(" (Trip Patterns)"):
                suffix = " (Trip Patterns)"
                positions[chart_key]["meta"]["sliceNameOverride"] = chart[
                    "slice_name"
                ][: -len(suffix)]
        positions[container_id]["children"].append(row_id)
        positions[row_id] = {
            "id": row_id,
            "type": "ROW",
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
            "children": chart_ids,
            "parents": parent_path,
        }

    positions["GRID_ID"]["children"].append("TABS_ID")
    positions["TABS_ID"] = {
        "id": "TABS_ID",
        "type": "TABS",
        "children": ["TAB-TRIPS-REVENUE", "TAB-TRIP-PATTERNS"],
        "parents": ["ROOT_ID", "GRID_ID"],
        "meta": {},
    }
    tab_definitions: list[tuple[str, str, list[tuple[str, list[tuple[str, int]], int]]]] = []

    trips_rows: list[tuple[str, list[tuple[str, int]], int]] = [
        ("ROW-KPI-1", [(name, 3) for name in kpi_titles[:4]], 18),
        ("ROW-KPI-2", [(name, 4) for name in kpi_titles[4:]], 18),
    ]
    if len(years) == 2:
        trips_rows.append(
            (
                "ROW-TREND-TRIPS",
                [
                    (f"Taxi Trips Trend in {years[0]}", 6),
                    (f"Taxi Trips Trend in {years[1]}", 6),
                ],
                50,
            )
        )
        trips_rows.append(
            (
                "ROW-TREND-REVENUE",
                [
                    (f"Taxi Revenue Trend in {years[0]}", 6),
                    (f"Taxi Revenue Trend in {years[1]}", 6),
                ],
                50,
            )
        )
    else:
        year = years[0]
        trips_rows.append(
            (
                f"ROW-TREND-{year}",
                [
                    (f"Taxi Trips Trend in {year}", 6),
                    (f"Taxi Revenue Trend in {year}", 6),
                ],
                50,
            )
        )
    trips_rows.append(
        (
            "ROW-PATTERNS",
            [
                ("Total Trips by Vendor", 3),
                ("Total Trips by Payment Type", 3),
                ("Total Trips by Borough", 3),
                ("Top 6 Trip Zones", 3),
            ],
            50,
        )
    )

    pattern_kpi_titles = [f"{name} (Trip Patterns)" for name in kpi_titles]
    patterns_rows = [
        (
            "ROW-KPI-PATTERNS-1",
            [(name, 3) for name in pattern_kpi_titles[:4]],
            18,
        ),
        (
            "ROW-KPI-PATTERNS-2",
            [(name, 4) for name in pattern_kpi_titles[4:]],
            18,
        ),
        (
            "ROW-TRIP-PATTERNS-1",
            [
                ("Trips by Day Of The Week", 3),
                ("Trips by Time Of The Day", 3),
                ("Most Popular Pickup Borough", 3),
                ("Most Popular Dropoff Borough", 3),
            ],
            42,
        ),
        (
            "ROW-TRIP-PATTERNS-2",
            [
                ("Average Number Of Trips By Day", 5),
                ("Busiest Days Of The Week & Time Of The Day", 7),
            ],
            48,
        ),
    ]
    tab_definitions.extend(
        [
            ("TAB-TRIPS-REVENUE", "Trips & Revenue", trips_rows),
            ("TAB-TRIP-PATTERNS", "Trip Patterns", patterns_rows),
        ]
    )
    for tab_id, title, rows in tab_definitions:
        positions[tab_id] = {
            "id": tab_id,
            "type": "TAB",
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", "TABS_ID"],
            "meta": {"text": title},
        }
        tab_path = ["ROOT_ID", "GRID_ID", "TABS_ID", tab_id]
        for row_id, row_charts, height in rows:
            add_row(tab_id, tab_path, row_id, row_charts, height)
    return positions


def native_filters(dataset_id: int, charts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chart_ids = [int(chart["id"]) for chart in charts]
    filters = []
    for filter_id, name, column in [
        ("VENDOR", "Vendor Name", "vendor_name"),
        ("DAY-OF-WEEK", "Day Of Week", "day_of_week"),
    ]:
        filters.append(
            {
                "id": f"NATIVE_FILTER-{filter_id}",
                "controlValues": {
                    "enableEmptyFilter": True,
                    "defaultToFirstItem": False,
                    "creatable": False,
                    "multiSelect": True,
                    "searchAllOptions": False,
                    "inverseSelection": False,
                },
                "name": name,
                "filterType": "filter_select",
                "targets": [{"datasetId": dataset_id, "column": {"name": column}}],
                "defaultDataMask": {
                    "extraFormData": {},
                    "filterState": {},
                    "ownState": {},
                },
                "cascadeParentIds": [],
                "scope": {"excluded": [], "rootPath": ["ROOT_ID"]},
                "chartsInScope": chart_ids,
                "tabsInScope": [],
                "type": "NATIVE_FILTER",
                "description": "",
            }
        )
    return filters


def upsert_dashboard(
    client: SupersetClient,
    dataset_id: int,
    charts: list[dict[str, Any]],
    years: list[int],
) -> dict[str, Any]:
    existing = next(
        (
            dashboard
            for dashboard in client.list_objects("dashboard")
            if dashboard.get("dashboard_title") == DASHBOARD_TITLE
        ),
        None,
    )
    dashboard_id = int(existing["id"]) if existing else None
    positions = dashboard_positions(charts, years)
    json_metadata = {
        "timed_refresh_immune_slices": [],
        "expanded_slices": {},
        "refresh_frequency": 0,
        "default_filters": "{}",
        "color_scheme": None,
        "label_colors": {"Total Trips": "#E3C300", "Total Revenue": "#50B432"},
        "cross_filters_enabled": False,
        "chart_configuration": {},
        "filter_scopes": {},
        "native_filter_configuration": native_filters(dataset_id, charts),
        "positions": positions,
        "filter_bar_orientation": "VERTICAL",
    }
    body = {
        "dashboard_title": DASHBOARD_TITLE,
        "slug": DASHBOARD_SLUG,
        "published": True,
        "css": dashboard_background_css(),
        "position_json": json.dumps(positions, ensure_ascii=False),
        "json_metadata": json.dumps(json_metadata, ensure_ascii=False),
    }
    if dashboard_id:
        client.request("PUT", f"/api/v1/dashboard/{dashboard_id}", body)
    else:
        client.request("POST", "/api/v1/dashboard/", body)
        created = next(
            (
                dashboard
                for dashboard in client.list_objects("dashboard")
                if dashboard.get("dashboard_title") == DASHBOARD_TITLE
            ),
            None,
        )
        if not created:
            raise SupersetError(f"Superset created no dashboard named {DASHBOARD_TITLE}.")
        dashboard_id = int(created["id"])

    for chart in charts:
        client.request(
            "PUT",
            f"/api/v1/chart/{chart['id']}",
            {
                "dashboards": [dashboard_id],
                "slice_name": chart["slice_name"],
                "datasource_id": dataset_id,
                "datasource_type": "table",
                "viz_type": chart["viz_type"],
                "description": chart.get("description"),
                "params": chart.get("params"),
                "query_context": chart.get("query_context"),
            },
        )
    return client.request("GET", f"/api/v1/dashboard/{dashboard_id}").get("result", {})


def update_dashboard_css(client: SupersetClient) -> int:
    dashboard = next(
        (
            item
            for item in client.list_objects("dashboard")
            if item.get("dashboard_title") == DASHBOARD_TITLE
        ),
        None,
    )
    if not dashboard:
        raise SupersetError(f"Dashboard {DASHBOARD_TITLE!r} was not found.")

    dashboard_id = int(dashboard["id"])
    client.request(
        "PUT",
        f"/api/v1/dashboard/{dashboard_id}",
        {"css": dashboard_background_css()},
    )
    return dashboard_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SUPERSET_HOST_URL", DEFAULT_BASE_URL),
        help=f"Superset URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--env-file",
        help="Credential file (for example .env.local or .env.prod).",
    )
    parser.add_argument(
        "--years",
        help="Optional comma-separated source years (for example 2017,2018). "
        "By default, use the two latest years available.",
    )
    parser.add_argument(
        "--style-only",
        action="store_true",
        help="Update only this dashboard's CSS, leaving charts and layout untouched.",
    )
    args = parser.parse_args()

    env_path = Path(args.env_file) if args.env_file else ROOT / ".env.local"
    if not env_path.is_absolute():
        env_path = ROOT / env_path
    if not args.env_file and not env_path.is_file():
        env_path = ROOT / ".env.prod"
    env_file = load_dotenv(env_path)
    username = os.environ.get("SUPERSET_ADMIN_USERNAME", env_file.get("SUPERSET_ADMIN_USERNAME"))
    password = os.environ.get("SUPERSET_ADMIN_PASSWORD", env_file.get("SUPERSET_ADMIN_PASSWORD"))
    if not username or not password:
        raise SupersetError(
            "Set SUPERSET_ADMIN_USERNAME and SUPERSET_ADMIN_PASSWORD in the environment, "
            ".env.local, or .env.prod."
        )

    client = SupersetClient(args.base_url, username, password)
    client.login()
    if args.style_only:
        dashboard_id = update_dashboard_css(client)
        print(
            f"Updated CSS for {DASHBOARD_TITLE} (ID {dashboard_id}); "
            "charts and layout were untouched."
        )
        return 0

    version = get_server_version(client)
    database = find_database(client)
    database_id = int(database["id"])
    dataset = ensure_dataset(client, database_id)
    dataset_id = int(dataset["id"])
    requested_years = None
    if args.years:
        try:
            requested_years = [int(year.strip()) for year in args.years.split(",") if year.strip()]
        except ValueError as exc:
            raise SupersetError("--years must be a comma-separated list of integer years.") from exc
        if not requested_years:
            raise SupersetError("--years must include at least one year.")
        if len(set(requested_years)) > 2:
            raise SupersetError("--years accepts one or two years.")
    years = available_years(client, database_id, requested_years)

    charts = []
    for definition in chart_definitions(dataset_id, years):
        print(f"Upserting chart: {definition['title']}", flush=True)
        charts.append(upsert_chart(client, dataset_id, definition))
    dashboard = upsert_dashboard(client, dataset_id, charts, years)
    dashboard_id = int(dashboard["id"])

    linked = {
        int(chart["id"])
        for chart in client.request(
            "GET", f"/api/v1/dashboard/{dashboard_id}/charts"
        ).get("result", [])
    }
    expected = {int(chart["id"]) for chart in charts}
    if linked != expected:
        raise SupersetError(
            f"Dashboard chart association mismatch: expected {sorted(expected)}, got {sorted(linked)}."
        )

    default_frontend_origins = ",".join(
        [env_file.get("FRONTEND_URL", "http://localhost:43117"), "http://127.0.0.1:43117"]
    )
    frontend_origins = [
        origin.strip().rstrip("/")
        for origin in os.environ.get(
            "FRONTEND_ORIGINS",
            env_file.get("FRONTEND_ORIGINS", default_frontend_origins),
        ).split(",")
        if origin.strip()
    ]
    embedded = ensure_dashboard_embedding(client, dashboard, frontend_origins)

    print(f"Superset version: {version}")
    print(f"Database connection: {database.get('database_name')} (ID {database_id})")
    print(f"Virtual dataset: raw.{DATASET_NAME} (ID {dataset_id})")
    print(f"Trend years: {', '.join(map(str, years))}")
    print(f"Charts: {len(charts)}")
    for chart in charts:
        print(f"- {chart['slice_name']} | {chart['viz_type']} | ID {chart['id']}")
    print(f"Dashboard: {DASHBOARD_TITLE} | ID {dashboard_id} | published")
    print(f"Dashboard URL: {args.base_url.rstrip('/')}/superset/dashboard/{DASHBOARD_SLUG}/")
    print(f"Embedded dashboard UUID: {embedded['uuid']}")
    print("Native filters: Vendor Name, Day Of Week")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SupersetError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
