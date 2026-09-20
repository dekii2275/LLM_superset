#!/usr/bin/env python3
"""Profile imported NYC Yellow Taxi raw tables and write a Markdown report."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import psycopg
from pypdf import PdfReader
from psycopg import sql
from psycopg.rows import dict_row

from nyc_taxi_common import (
    DATA_DIR,
    INGESTION_TABLE,
    TRIPS_TABLE,
    ZONE_TABLE,
    combined_trip_schema,
    connect,
    display_value,
    normalize_identifier,
    parquet_files,
    zone_file,
)


SCHEMA = "raw"
NUMERIC_TYPES = {"smallint", "integer", "bigint", "numeric", "real", "double precision"}


def md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def column_info(cur: psycopg.Cursor[Any], table: str) -> list[dict[str, Any]]:
    cur.execute(
        "SELECT column_name, data_type, is_nullable, ordinal_position "
        "FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
        (SCHEMA, table),
    )
    return [dict(row) for row in cur.fetchall()]


def table_exists(cur: psycopg.Cursor[Any], table: str) -> bool:
    cur.execute("SELECT to_regclass(%s) AS relation", (f"{SCHEMA}.{table}",))
    return cur.fetchone()["relation"] is not None


def dictionary_descriptions(path: Path, source_fields: list[dict[str, Any]]) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        print(f"Could not extract the supplied data dictionary: {type(exc).__name__}: {exc}")
        return {}

    # The source PDF presents fields as a table. Keep descriptions strictly tied to
    # text adjacent to an exact source field name; otherwise report them unmapped.
    descriptions: dict[str, str] = {}
    lines = [" ".join(line.split()) for page in pages for line in page.splitlines() if line.strip()]
    all_names = [name for field in source_fields for name in field["source_names"]]
    for field in source_fields:
        names = field["source_names"]
        for name in names:
            for index, line in enumerate(lines):
                if not re.match(rf"^{re.escape(name)}(?:\s+|$)", line, flags=re.IGNORECASE):
                    continue
                tail = line[len(name):].strip(" :\t-–")
                description_parts = [tail] if tail else []
                for next_line in lines[index + 1:]:
                    is_next_field = any(
                        other.casefold() != name.casefold()
                        and re.match(rf"^{re.escape(other)}(?:\s+|$)", next_line, flags=re.IGNORECASE)
                        for other in all_names
                    )
                    if is_next_field:
                        break
                    description_parts.append(next_line)
                candidate = " ".join(description_parts).strip(" :\t-–")
                if candidate and len(candidate) > 6:
                    descriptions[field["column"]] = candidate[:500]
                break
            if field["column"] in descriptions:
                break
    return descriptions


def find_column(columns: list[str], predicate) -> str | None:
    return next((column for column in columns if predicate(column)), None)


def aggregate_one(cur: psycopg.Cursor[Any], expression: sql.Composable, table: str = TRIPS_TABLE) -> dict[str, Any]:
    cur.execute(sql.SQL("SELECT {} FROM {}.{}").format(expression, sql.Identifier(SCHEMA), sql.Identifier(table)))
    return dict(cur.fetchone())


def count_matching(cur: psycopg.Cursor[Any], predicate: sql.Composable) -> int:
    cur.execute(sql.SQL("SELECT COUNT(*) AS count FROM {}.{} WHERE {}").format(
        sql.Identifier(SCHEMA), sql.Identifier(TRIPS_TABLE), predicate
    ))
    return cur.fetchone()["count"]


def categorical_profile(cur: psycopg.Cursor[Any], column: str) -> dict[str, Any]:
    ident = sql.Identifier(column)
    cur.execute(sql.SQL("SELECT COUNT(DISTINCT {}) AS count FROM {}.{}").format(
        ident, sql.Identifier(SCHEMA), sql.Identifier(TRIPS_TABLE)
    ))
    distinct_count = cur.fetchone()["count"]
    cur.execute(sql.SQL(
        "SELECT {} AS value, COUNT(*) AS frequency FROM {}.{} WHERE {} IS NOT NULL "
        "GROUP BY {} ORDER BY frequency DESC, {}::text LIMIT 10"
    ).format(ident, sql.Identifier(SCHEMA), sql.Identifier(TRIPS_TABLE), ident, ident, ident))
    top = [{"value": display_value(row["value"]), "frequency": row["frequency"]} for row in cur.fetchall()]
    return {"distinct_count": distinct_count, "top": top}


def zone_match_report(cur: psycopg.Cursor[Any], trip_columns: list[str], zone_columns: list[str]) -> list[str]:
    pickup = find_column(trip_columns, lambda name: ("pickup" in name or name.startswith("pu_")) and "location" in name and "id" in name)
    dropoff = find_column(trip_columns, lambda name: ("dropoff" in name or name.startswith("do_")) and "location" in name and "id" in name)
    zone_id = find_column(zone_columns, lambda name: name in {"location_id", "locationid"} or ("location" in name and "id" in name))
    lines = []
    if not zone_id:
        return ["Zone key column was not identified; compatibility checks were not run."]
    for label, column in (("Pickup", pickup), ("Dropoff", dropoff)):
        if not column:
            lines.append(f"{label}: matching location ID column was not present.")
            continue
        cur.execute(sql.SQL(
            "SELECT COUNT(DISTINCT trip.{trip_column}) AS distinct_count, "
            "COUNT(DISTINCT trip.{trip_column}) FILTER (WHERE NOT EXISTS ("
            "SELECT 1 FROM {schema}.{zone_table} zone WHERE zone.{zone_id}::text = trip.{trip_column}::text)) "
            "AS unmatched_count "
            "FROM {schema}.{trips_table} trip"
        ).format(
            trip_column=sql.Identifier(column), schema=sql.Identifier(SCHEMA),
            zone_table=sql.Identifier(ZONE_TABLE), zone_id=sql.Identifier(zone_id),
            trips_table=sql.Identifier(TRIPS_TABLE),
        ))
        result = cur.fetchone()
        distinct_count, unmatched_count = result["distinct_count"], result["unmatched_count"]
        percentage = 100.0 * unmatched_count / distinct_count if distinct_count else 0.0
        lines.append(
            f"{label}: `{column}` has {distinct_count:,} distinct non-null IDs; "
            f"{unmatched_count:,} unmatched ({percentage:.4f}%)."
        )
    return lines


def build_report() -> tuple[str, dict[str, Any]]:
    files = parquet_files()
    schema_fields, drift = combined_trip_schema(files)
    source_type_map = {field["column"]: str(field["arrow_type"]) for field in schema_fields}
    descriptions = dictionary_descriptions(DATA_DIR / "data_dictionary_trip_records_yellow.pdf", schema_fields)
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        required = [TRIPS_TABLE, ZONE_TABLE, INGESTION_TABLE]
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema=%s ORDER BY table_name",
            (SCHEMA,),
        )
        raw_tables = [row["table_name"] for row in cur.fetchall()]
        missing = [table for table in required if table not in raw_tables]
        if missing:
            raise RuntimeError(f"Required raw tables are missing: {', '.join(missing)}. Run the importer first.")

        trip_columns = column_info(cur, TRIPS_TABLE)
        zone_columns = column_info(cur, ZONE_TABLE)
        col_names = [column["column_name"] for column in trip_columns]
        zone_names = [column["column_name"] for column in zone_columns]
        cur.execute(sql.SQL("SELECT COUNT(*) AS total FROM {}.{}").format(sql.Identifier(SCHEMA), sql.Identifier(TRIPS_TABLE)))
        total_rows = cur.fetchone()["total"]
        cur.execute(sql.SQL(
            "SELECT source_file, COUNT(*) AS row_count, MIN(source_year) AS source_year, "
            "MIN(source_month) AS source_month FROM {}.{} GROUP BY source_file ORDER BY source_file"
        ).format(sql.Identifier(SCHEMA), sql.Identifier(TRIPS_TABLE)))
        counts_by_source = cur.fetchall()
        cur.execute(sql.SQL(
            "SELECT source_file, source_type, row_count, file_size, sha256, loaded_at, status, error "
            "FROM {}.{} ORDER BY source_file"
        ).format(sql.Identifier(SCHEMA), sql.Identifier(INGESTION_TABLE)))
        ingestion_log = cur.fetchall()
        log_by_file = {row["source_file"]: row for row in ingestion_log}

        null_expressions = [
            sql.SQL("COUNT(*) FILTER (WHERE {} IS NULL) AS {}").format(
                sql.Identifier(column), sql.Identifier(column)
            ) for column in col_names
        ]
        cur.execute(sql.SQL("SELECT {} FROM {}.{}").format(
            sql.SQL(", ").join(null_expressions), sql.Identifier(SCHEMA), sql.Identifier(TRIPS_TABLE)
        ))
        null_counts = dict(cur.fetchone())

        numeric_columns = [column for column in trip_columns if column["data_type"] in NUMERIC_TYPES]
        numeric_summary = {}
        for column in numeric_columns:
            name = column["column_name"]
            cur.execute(sql.SQL("SELECT MIN({c}) AS min, MAX({c}) AS max, AVG({c}) AS avg FROM {s}.{t}").format(
                c=sql.Identifier(name), s=sql.Identifier(SCHEMA), t=sql.Identifier(TRIPS_TABLE)
            ))
            numeric_summary[name] = dict(cur.fetchone())

        cat_names = []
        for candidate in ("vendor_id", "payment_type", "ratecode_id", "store_and_fwd_flag"):
            if candidate in col_names:
                cat_names.append(candidate)
        # Include equivalent source names after safe normalization.
        for column in trip_columns:
            name = column["column_name"]
            if name not in cat_names and any(marker in name for marker in ("vendor", "payment", "ratecode", "store_and_fwd", "flag")):
                cat_names.append(name)
        categorical = {name: categorical_profile(cur, name) for name in cat_names}

        pickup_time = find_column(col_names, lambda name: "pickup" in name and "datetime" in name) or find_column(
            col_names, lambda name: "pickup" in name and "timestamp" in next((column["data_type"] for column in trip_columns if column["column_name"] == name), "")
        )
        dropoff_time = find_column(col_names, lambda name: "dropoff" in name and "datetime" in name) or find_column(
            col_names, lambda name: "dropoff" in name and "timestamp" in next((column["data_type"] for column in trip_columns if column["column_name"] == name), "")
        )
        date_range = {}
        if pickup_time:
            cur.execute(sql.SQL("SELECT MIN({}) AS min, MAX({}) AS max FROM {}.{}").format(
                sql.Identifier(pickup_time), sql.Identifier(pickup_time), sql.Identifier(SCHEMA), sql.Identifier(TRIPS_TABLE)
            ))
            date_range["pickup"] = cur.fetchone()
        if dropoff_time:
            cur.execute(sql.SQL("SELECT MIN({}) AS min, MAX({}) AS max FROM {}.{}").format(
                sql.Identifier(dropoff_time), sql.Identifier(dropoff_time), sql.Identifier(SCHEMA), sql.Identifier(TRIPS_TABLE)
            ))
            date_range["dropoff"] = cur.fetchone()

        date_anomalies = []
        if pickup_time and "source_year" in col_names and "source_month" in col_names:
            cur.execute(sql.SQL(
                "SELECT source_file, COUNT(*) AS rows_outside_source_month "
                "FROM {s}.{t} WHERE {pickup} IS NOT NULL AND "
                "(EXTRACT(YEAR FROM {pickup})::int <> source_year OR EXTRACT(MONTH FROM {pickup})::int <> source_month) "
                "GROUP BY source_file ORDER BY source_file"
            ).format(s=sql.Identifier(SCHEMA), t=sql.Identifier(TRIPS_TABLE), pickup=sql.Identifier(pickup_time)))
            date_anomalies = cur.fetchall()

        quality_checks: list[tuple[str, sql.Composable]] = []
        for column, label, expression in (
            ("trip_distance", "trip_distance < 0", lambda c: sql.SQL("{} < 0").format(c)),
            ("trip_distance", "trip_distance = 0", lambda c: sql.SQL("{} = 0").format(c)),
            ("fare_amount", "fare_amount < 0", lambda c: sql.SQL("{} < 0").format(c)),
            ("total_amount", "total_amount < 0", lambda c: sql.SQL("{} < 0").format(c)),
            ("passenger_count", "passenger_count < 0", lambda c: sql.SQL("{} < 0").format(c)),
        ):
            if column in col_names:
                quality_checks.append((label, expression(sql.Identifier(column))))
        if pickup_time and dropoff_time:
            quality_checks.extend([
                ("dropoff_time < pickup_time", sql.SQL("{} < {}").format(sql.Identifier(dropoff_time), sql.Identifier(pickup_time))),
                ("pickup_time = dropoff_time", sql.SQL("{} = {}").format(sql.Identifier(dropoff_time), sql.Identifier(pickup_time))),
            ])
        quality_counts = {label: count_matching(cur, expression) for label, expression in quality_checks}

        zone_summary: dict[str, Any] = {"row_count": None, "borough_count": None, "zone_count": None, "borough_distribution": [], "sample": []}
        cur.execute(sql.SQL("SELECT COUNT(*) AS count FROM {}.{}").format(sql.Identifier(SCHEMA), sql.Identifier(ZONE_TABLE)))
        zone_summary["row_count"] = cur.fetchone()["count"]
        borough_col = find_column(zone_names, lambda name: name == "borough")
        zone_col = find_column(zone_names, lambda name: name == "zone")
        if borough_col:
            cur.execute(sql.SQL("SELECT {} AS borough, COUNT(*) AS row_count FROM {}.{} GROUP BY {} ORDER BY row_count DESC, {} NULLS LAST").format(
                sql.Identifier(borough_col), sql.Identifier(SCHEMA), sql.Identifier(ZONE_TABLE),
                sql.Identifier(borough_col), sql.Identifier(borough_col),
            ))
            borough_rows = cur.fetchall()
            zone_summary["borough_count"] = len(borough_rows)
            zone_summary["borough_distribution"] = [{"borough": row["borough"], "rows": row["row_count"]} for row in borough_rows]
        if zone_col:
            cur.execute(sql.SQL("SELECT COUNT(DISTINCT {}) AS count FROM {}.{}").format(
                sql.Identifier(zone_col), sql.Identifier(SCHEMA), sql.Identifier(ZONE_TABLE)
            ))
            zone_summary["zone_count"] = cur.fetchone()["count"]
        cur.execute(sql.SQL("SELECT * FROM {}.{} LIMIT 10").format(sql.Identifier(SCHEMA), sql.Identifier(ZONE_TABLE)))
        zone_summary["sample"] = [dict(row) for row in cur.fetchall()]
        compatibility = zone_match_report(cur, col_names, zone_names)

        sample_output_columns = col_names
        sample_order = [sql.Identifier("source_file")]
        if pickup_time:
            sample_order.append(sql.Identifier(pickup_time))
        cur.execute(sql.SQL("SELECT * FROM {}.{} ORDER BY {} LIMIT 10").format(
            sql.Identifier(SCHEMA), sql.Identifier(TRIPS_TABLE), sql.SQL(", ").join(sample_order),
        ))
        sample_rows = [dict(row) for row in cur.fetchall()]

    available_files = {path.name: path for path in files}
    source_file_report = []
    source_months = [
        match.group(1) if (match := re.search(r"(\d{4}-\d{2})", path.name)) else path.stem
        for path in files
    ]
    count_map = {row["source_file"]: row["row_count"] for row in counts_by_source}
    for path in files:
        metadata = pq.ParquetFile(path).metadata
        log = log_by_file.get(path.name)
        source_file_report.append({
            "name": path.name,
            "file_size": path.stat().st_size,
            "expected_rows": metadata.num_rows,
            "imported_rows": count_map.get(path.name, 0),
            "status": log["status"] if log else "not logged",
            "sha256_matches_log": bool(log and log["sha256"]),
        })
    zones_path = zone_file()
    zone_log = log_by_file.get(zones_path.name)
    report_lines = [
        "# NYC Yellow Taxi Data Profile",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
        "## Dataset overview",
        "",
        f"- Total trip rows: **{total_rows:,}**",
        f"- Total trip table columns: **{len(trip_columns)}** (includes ingestion metadata)",
        f"- Source trip files: **{len(files)}**",
        f"- Trip source months: **{', '.join(source_months)}**",
        "- PostgreSQL raw tables: `raw.yellow_taxi_trips`, `raw.taxi_zone_lookup`, `raw.ingestion_log`",
        f"- Taxi zone lookup rows: **{zone_summary['row_count']:,}**",
        f"- Parquet schemas identical: **{'yes' if not drift else 'no'}**",
        "",
        "| Source file | Expected rows | Imported rows | Status | File size (bytes) |",
        "|---|---:|---:|---|---:|",
    ]
    for item in source_file_report:
        report_lines.append(f"| {md(item['name'])} | {item['expected_rows']:,} | {item['imported_rows']:,} | {md(item['status'])} | {item['file_size']:,} |")
    report_lines.extend([
        f"| {md(zones_path.name)} | {zone_summary['row_count']:,} | {zone_summary['row_count']:,} | {md(zone_log['status'] if zone_log else 'not logged')} | {zones_path.stat().st_size:,} |",
        "",
        "## Source schema comparison",
        "",
    ])
    if drift:
        report_lines.append("Schema drift was detected and the loader created a union table schema. Missing source values are stored as NULL. No source field was dropped.")
        report_lines.append("")
        for item in drift:
            report_lines.append(f"- **{md(item['file'])}:** missing={item['missing_columns'] or 'none'}; added={item['added_columns'] or 'none'}; type changes={item['type_changes'] or 'none'}; order changed={item['column_order_changed']}.")
    else:
        report_lines.append("All Parquet files have the same column names, order, and Arrow types.")
    report_lines.extend([
        "",
        "## Trip schema",
        "",
        "Source column names are normalized to lowercase snake_case. The source name mapping is recorded below. Descriptions are included only when mapped from the supplied data dictionary.",
        "",
        "| PostgreSQL column | PostgreSQL type | Source column name(s) | Source type | Nullable | Description |",
        "|---|---|---|---|---|---|",
    ])
    source_to_normalized = {field["column"]: field for field in schema_fields}
    for column in trip_columns:
        name = column["column_name"]
        source = source_to_normalized.get(name)
        source_names = ", ".join(source["source_names"]) if source else "(ingestion metadata)"
        source_type = source_type_map.get(name, "generated during ingestion")
        description = descriptions.get(name, "Unknown / not mapped yet")
        report_lines.append(f"| `{md(name)}` | `{md(column['data_type'])}` | `{md(source_names)}` | `{md(source_type)}` | {column['is_nullable']} | {md(description)} |")

    report_lines.extend([
        "",
        "## Date range",
        "",
    ])
    if pickup_time:
        report_lines.append(f"- Pickup (`{pickup_time}`): {display_value(date_range['pickup']['min'])} to {display_value(date_range['pickup']['max'])}")
    else:
        report_lines.append("- Pickup datetime: no timestamp column with a pickup name was identified.")
    if dropoff_time:
        report_lines.append(f"- Dropoff (`{dropoff_time}`): {display_value(date_range['dropoff']['min'])} to {display_value(date_range['dropoff']['max'])}")
    else:
        report_lines.append("- Dropoff datetime: no timestamp column with a dropoff name was identified.")
    report_lines.extend([
        "",
        "### Pickup dates outside the source month",
        "",
    ])
    if date_anomalies:
        report_lines.extend([f"- `{row['source_file']}`: {row['rows_outside_source_month']:,} rows have pickup timestamps outside the month in the source filename." for row in date_anomalies])
    else:
        report_lines.append("No rows were found outside their source month, or no suitable pickup timestamp was available.")

    report_lines.extend([
        "",
        "## Null analysis",
        "",
        "| Column | Null count | Null percentage |",
        "|---|---:|---:|",
    ])
    for name, count in sorted(null_counts.items(), key=lambda item: (-item[1], item[0])):
        percentage = 100.0 * count / total_rows if total_rows else 0.0
        report_lines.append(f"| `{md(name)}` | {count:,} | {percentage:.4f}% |")

    report_lines.extend([
        "",
        "## Numeric summary",
        "",
        "| Column | Min | Max | Average |",
        "|---|---:|---:|---:|",
    ])
    for name, stats in numeric_summary.items():
        report_lines.append(f"| `{md(name)}` | {md(display_value(stats['min']))} | {md(display_value(stats['max']))} | {md(display_value(stats['avg']))} |")

    report_lines.extend(["", "## Categorical analysis", "", "Distinct counts and top-value frequencies exclude NULL values.", ""])
    if categorical:
        for name, profile in categorical.items():
            report_lines.extend([f"### `{md(name)}`", "", f"- Distinct values: {profile['distinct_count']:,}", "", "| Value | Frequency |", "|---|---:|"])
            report_lines.extend([f"| {md(item['value'])} | {item['frequency']:,} |" for item in profile["top"]])
            report_lines.append("")
    else:
        report_lines.append("No matching vendor, payment, rate-code, or store-and-forward columns were present.")

    report_lines.extend([
        "",
        "## Taxi zone lookup",
        "",
        f"- Rows: {zone_summary['row_count']:,}",
        f"- Columns ({len(zone_columns)}): {', '.join(f'`{md(name)}`' for name in zone_names)}",
        f"- Distinct boroughs: {zone_summary['borough_count'] if zone_summary['borough_count'] is not None else 'not available'}",
        f"- Distinct zones: {zone_summary['zone_count'] if zone_summary['zone_count'] is not None else 'not available'}",
    ])
    if zone_summary["borough_distribution"]:
        report_lines.extend(["", "| Borough | Rows |", "|---|---:|"])
        report_lines.extend([f"| {md(row['borough'])} | {row['rows']:,} |" for row in zone_summary["borough_distribution"]])
    report_lines.extend(["", "Ten sample rows returned by `SELECT * FROM raw.taxi_zone_lookup LIMIT 10`:", ""])
    if zone_summary["sample"]:
        report_lines.append("```json")
        report_lines.append(json.dumps(zone_summary["sample"], ensure_ascii=False, indent=2, default=str))
        report_lines.append("```")
    report_lines.extend(["", "## Location ID compatibility", ""])
    report_lines.extend([f"- {line}" for line in compatibility])

    report_lines.extend([
        "",
        "## Basic data-quality checks",
        "",
        "These are counts only. Raw records were not cleaned or deleted.",
        "",
        "| Check | Rows |",
        "|---|---:|",
    ])
    if quality_counts:
        report_lines.extend([f"| {md(label)} | {count:,} |" for label, count in quality_counts.items()])
    else:
        report_lines.append("No requested quality-check fields were present.")
    report_lines.extend(["", "## Trip sample", "", f"Ten sample records, ordered by source file and pickup time. All {len(sample_output_columns)} table columns are included.", "", "```json"])
    report_lines.append(json.dumps(sample_rows, ensure_ascii=False, indent=2, default=str))
    report_lines.extend(["```", "", "## Ingestion audit", "", "| Source file | Type | Rows in log | Status | Loaded at (UTC) | Error |", "|---|---|---:|---|---|---|"])
    for row in ingestion_log:
        report_lines.append(f"| `{md(row['source_file'])}` | {md(row['source_type'])} | {md(row['row_count'])} | {md(row['status'])} | {md(display_value(row['loaded_at']))} | {md(row['error'] or '')} |")
    report_lines.extend(["", "## Notes", "", "- No foreign keys, fact/dimension models, analytics views, or data cleaning were applied.", "- Monetary source fields retain their source floating-point type when stored as Arrow float values. Decimal source fields use PostgreSQL `NUMERIC`.", ""])

    summary = {
        "total_rows": total_rows,
        "trip_columns": len(trip_columns),
        "raw_tables": raw_tables,
        "source_files": source_file_report,
        "zone_rows": zone_summary["row_count"],
        "trip_sample": sample_rows,
        "zone_sample": zone_summary["sample"],
        "date_range": date_range,
        "drift": drift,
        "quality_counts": quality_counts,
    }
    return "\n".join(report_lines), summary


def main() -> int:
    try:
        report, summary = build_report()
        output = DATA_DIR / "nyc_taxi_profile.md"
        output.write_text(report, encoding="utf-8")
        print(f"Profile report written to {output}")
        print(f"Total trips: {summary['total_rows']:,}; trip columns: {summary['trip_columns']}; zone rows: {summary['zone_rows']:,}")
        print(f"Tables in raw: {', '.join(summary['raw_tables'])}")
        print("\nDataset                  Rows        Status")
        print("------------------------------------------------")
        for item in summary["source_files"]:
            print(f"{item['name']:<25} {item['imported_rows']:>10,}  {item['status']}")
        print(f"{'Taxi Zone Lookup':<25} {summary['zone_rows']:>10,}  Imported")
        print("------------------------------------------------")
        print(f"{'Total Trips':<25} {summary['total_rows']:>10,}")
        print("\nDate range:")
        for kind, values in summary["date_range"].items():
            print(f"  {kind}: {display_value(values['min'])} to {display_value(values['max'])}")
        if summary["drift"]:
            print(f"Schema drift reports: {len(summary['drift'])}")
        print("\nTrip sample (10 PostgreSQL rows; selected fields):")
        sample_fields = [
            "source_file", "vendor_id", "tpep_pickup_datetime", "tpep_dropoff_datetime",
            "passenger_count", "trip_distance", "fare_amount", "total_amount",
        ]
        trip_sample = [{key: row.get(key) for key in sample_fields if key in row} for row in summary["trip_sample"]]
        print(json.dumps(trip_sample, ensure_ascii=False, indent=2, default=str))
        print("\nTaxi zone sample (10 PostgreSQL rows):")
        print(json.dumps(summary["zone_sample"], ensure_ascii=False, indent=2, default=str))
        return 0
    except Exception as exc:
        print(f"Profiling failed: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
