"""Shared schema inspection and SQL helpers for NYC Yellow Taxi data."""

from __future__ import annotations

import csv
import json
import os
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import psycopg
from psycopg import sql


DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
TRIPS_TABLE = "yellow_taxi_trips"
ZONE_TABLE = "taxi_zone_lookup"
INGESTION_TABLE = "ingestion_log"
RESERVED_TRIP_COLUMNS = {"source_file", "source_year", "source_month", "loaded_at"}


def connect() -> psycopg.Connection:
    """Connect using the repository's existing DATABASE_URL without logging it."""
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        # The backend's SQLAlchemy URL includes its driver suffix; psycopg expects
        # the standard PostgreSQL URI scheme.
        dsn = dsn.replace("postgresql+psycopg://", "postgresql://", 1)
        return psycopg.connect(dsn)
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "postgres"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("APP_DB_NAME", "ai_bi"),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def quote_identifier(name: str) -> sql.Identifier:
    return sql.Identifier(name)


def normalize_identifier(name: str) -> str:
    """Convert source names to lowercase snake_case and keep a mapping in reports."""
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    if not value:
        raise ValueError(f"Column name {name!r} cannot be normalized")
    if value[0].isdigit():
        value = f"column_{value}"
    return value


def parquet_files() -> list[Path]:
    files = sorted(DATA_DIR.glob("yellow_tripdata_*.parquet"))
    if not files:
        raise FileNotFoundError(f"No yellow_tripdata_*.parquet files found in {DATA_DIR}")
    return files


def zone_file() -> Path:
    path = DATA_DIR / "taxi_zone_lookup.csv"
    if not path.is_file():
        raise FileNotFoundError(f"Expected zone lookup CSV at {path}")
    return path


def get_parquet_schema(path: Path) -> pa.Schema:
    return pq.ParquetFile(path).schema_arrow


def normalized_arrow_fields(schema: pa.Schema) -> list[tuple[str, pa.DataType, bool]]:
    fields = []
    seen: dict[str, str] = {}
    for field in schema:
        normalized = normalize_identifier(field.name)
        if normalized in seen:
            raise ValueError(
                f"Source columns {seen[normalized]!r} and {field.name!r} both normalize to {normalized!r}"
            )
        if normalized in RESERVED_TRIP_COLUMNS:
            raise ValueError(f"Source column {field.name!r} conflicts with ingestion metadata {normalized!r}")
        seen[normalized] = field.name
        fields.append((field.name, field.type, field.nullable))
    return fields


def arrow_to_postgres_type(data_type: pa.DataType) -> str:
    if pa.types.is_boolean(data_type):
        return "BOOLEAN"
    if pa.types.is_integer(data_type):
        return "SMALLINT" if data_type.bit_width <= 16 else "INTEGER" if data_type.bit_width <= 32 else "BIGINT"
    if pa.types.is_floating(data_type):
        return "REAL" if data_type.bit_width <= 32 else "DOUBLE PRECISION"
    if pa.types.is_decimal(data_type):
        return f"NUMERIC({data_type.precision},{data_type.scale})"
    if pa.types.is_timestamp(data_type):
        return "TIMESTAMP WITH TIME ZONE" if data_type.tz else "TIMESTAMP"
    if pa.types.is_date(data_type):
        return "DATE"
    if pa.types.is_time(data_type):
        return "TIME"
    if pa.types.is_binary(data_type) or pa.types.is_large_binary(data_type):
        return "BYTEA"
    if pa.types.is_list(data_type) or pa.types.is_large_list(data_type) or pa.types.is_struct(data_type) or pa.types.is_map(data_type):
        return "JSONB"
    if pa.types.is_null(data_type) or pa.types.is_string(data_type) or pa.types.is_large_string(data_type):
        return "TEXT"
    raise TypeError(f"Unsupported Parquet type {data_type}; refusing to discard or guess the source field")


def common_arrow_type(left: pa.DataType, right: pa.DataType) -> pa.DataType:
    """Choose a loss-conscious common type for schema drift across source months."""
    if left == right:
        return left
    if pa.types.is_null(left):
        return right
    if pa.types.is_null(right):
        return left
    if pa.types.is_integer(left) and pa.types.is_integer(right):
        return pa.int64()
    if (pa.types.is_integer(left) or pa.types.is_floating(left)) and (
        pa.types.is_integer(right) or pa.types.is_floating(right)
    ):
        return pa.float64()
    if pa.types.is_decimal(left) and pa.types.is_decimal(right):
        scale = max(left.scale, right.scale)
        precision = min(38, max(left.precision - left.scale, right.precision - right.scale) + scale)
        return pa.decimal128(precision, scale)
    if pa.types.is_integer(left) and pa.types.is_decimal(right):
        return right
    if pa.types.is_decimal(left) and pa.types.is_integer(right):
        return left
    if pa.types.is_timestamp(left) and pa.types.is_timestamp(right):
        if left.tz != right.tz:
            raise TypeError(f"Incompatible timestamp timezones across source files: {left} vs {right}")
        units = {"s": 0, "ms": 1, "us": 2, "ns": 3}
        return pa.timestamp(max((left.unit, right.unit), key=lambda unit: units[unit]), tz=left.tz)
    raise TypeError(f"Incompatible source types across months: {left} vs {right}")


def combined_trip_schema(paths: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return the union schema and explicit per-file drift details."""
    schemas = [(path, get_parquet_schema(path)) for path in paths]
    union: dict[str, dict[str, Any]] = {}
    drift: list[dict[str, Any]] = []
    first_fields = normalized_arrow_fields(schemas[0][1])
    first_by_normalized = {normalize_identifier(name): data_type for name, data_type, _ in first_fields}
    first_names = [normalize_identifier(name) for name, _, _ in first_fields]
    for path, schema in schemas:
        fields = normalized_arrow_fields(schema)
        current = {normalize_identifier(name): data_type for name, data_type, _ in fields}
        missing = [name for name in first_names if name not in current]
        added = [name for name in current if name not in first_by_normalized]
        type_changes = [
            {"column": name, "first_type": str(first_by_normalized[name]), "this_type": str(current[name])}
            for name in current.keys() & first_by_normalized.keys()
            if current[name] != first_by_normalized[name]
        ]
        current_common_order = [
            normalize_identifier(name) for name, _, _ in fields
            if normalize_identifier(name) in first_by_normalized
        ]
        first_common_order = [name for name in first_names if name in current]
        order_changed = current_common_order != first_common_order
        if missing or added or type_changes or order_changed:
            drift.append({"file": path.name, "missing_columns": missing, "added_columns": added, "type_changes": type_changes, "column_order_changed": order_changed})
        for original_name, data_type, nullable in fields:
            normalized = normalize_identifier(original_name)
            if normalized not in union:
                union[normalized] = {"column": normalized, "source_names": [original_name], "arrow_type": data_type, "nullable": nullable}
            else:
                item = union[normalized]
                item["arrow_type"] = common_arrow_type(item["arrow_type"], data_type)
                if original_name not in item["source_names"]:
                    item["source_names"].append(original_name)
                item["nullable"] = item["nullable"] or nullable
    ordered = sorted(union.values(), key=lambda item: first_names.index(item["column"]) if item["column"] in first_names else len(first_names) + list(union).index(item["column"]))
    for item in ordered:
        item["postgres_type"] = arrow_to_postgres_type(item["arrow_type"])
    return ordered, drift


def infer_csv_type(values: list[str]) -> str:
    nonempty = [value.strip() for value in values if value is not None and value.strip() != ""]
    if not nonempty:
        return "TEXT"
    lowered = {value.lower() for value in nonempty}
    if lowered <= {"true", "false", "t", "f", "yes", "no"}:
        return "BOOLEAN"
    try:
        for value in nonempty:
            int(value)
        return "INTEGER" if all(-(2**31) <= int(value) < 2**31 for value in nonempty) else "BIGINT"
    except ValueError:
        pass
    try:
        parsed = [Decimal(value) for value in nonempty]
        scale = max(max(0, -value.as_tuple().exponent) for value in parsed)
        precision = min(38, max(max(1, len(value.as_tuple().digits) + value.as_tuple().exponent) for value in parsed) + scale)
        return f"NUMERIC({max(precision, scale + 1)},{scale})"
    except (InvalidOperation, ValueError):
        return "TEXT"


def read_csv_schema(path: Path) -> tuple[list[dict[str, Any]], int, list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path}")
        source_names = reader.fieldnames
        seen: dict[str, str] = {}
        rows = list(reader)
    columns = []
    for source_name in source_names:
        normalized = normalize_identifier(source_name)
        if normalized in seen:
            raise ValueError(f"CSV columns {seen[normalized]!r} and {source_name!r} both normalize to {normalized!r}")
        seen[normalized] = source_name
        columns.append({
            "column": normalized,
            "source_name": source_name,
            "postgres_type": infer_csv_type([row.get(source_name, "") or "" for row in rows]),
            "nullable": True,
        })
    return columns, len(rows), rows[:5]


def adapt_parquet_value(value: Any, postgres_type: str) -> Any:
    if value is None:
        return None
    if postgres_type == "JSONB":
        return json.dumps(value, default=str)
    if postgres_type.startswith("NUMERIC") and not isinstance(value, Decimal):
        return Decimal(str(value))
    return value


def adapt_csv_value(value: str | None, postgres_type: str) -> Any:
    if value is None or value.strip() == "":
        return None
    if postgres_type == "BOOLEAN":
        return value.strip().lower() in {"true", "t", "yes"}
    if postgres_type in {"SMALLINT", "INTEGER", "BIGINT"}:
        return int(value)
    if postgres_type.startswith("NUMERIC"):
        return Decimal(value)
    return value


def display_value(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat(sep=" ") if hasattr(value, "hour") else value.isoformat()
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)
