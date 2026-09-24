#!/usr/bin/env python3
"""Transaction-safe, streaming ingestion for NYC Yellow Taxi source files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import psycopg
from psycopg import sql

from nyc_taxi_common import (
    DATA_DIR,
    INGESTION_TABLE,
    RESERVED_TRIP_COLUMNS,
    TRIPS_TABLE,
    ZONE_TABLE,
    adapt_csv_value,
    adapt_parquet_value,
    combined_trip_schema,
    connect,
    normalize_identifier,
    parquet_files,
    read_csv_schema,
    zone_file,
)


SCHEMA = "raw"
BATCH_SIZE = 20_000
DEMO_MAX_ROWS_PER_SOURCE = int(os.getenv("DEMO_MAX_ROWS_PER_SOURCE", "10000"))


class ChangedSourceNeedsReload(RuntimeError):
    """A named source changed after a successful load and needs an explicit reload."""


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_ingestion_log(cur: psycopg.Cursor[Any]) -> None:
    cur.execute(
        sql.SQL(
            "CREATE TABLE IF NOT EXISTS {}.{} ("
            "source_file TEXT PRIMARY KEY, source_type TEXT NOT NULL, row_count BIGINT, "
            "file_size BIGINT NOT NULL, sha256 TEXT NOT NULL, loaded_at TIMESTAMPTZ NOT NULL, "
            "status TEXT NOT NULL, error TEXT)"
        ).format(sql.Identifier(SCHEMA), sql.Identifier(INGESTION_TABLE))
    )


def ensure_trips_table(cur: psycopg.Cursor[Any], schema_fields: list[dict[str, Any]]) -> None:
    definitions = [
        sql.SQL("{} {}").format(sql.Identifier(field["column"]), sql.SQL(field["postgres_type"]))
        for field in schema_fields
    ]
    definitions.extend(
        [
            sql.SQL("source_file TEXT NOT NULL"),
            sql.SQL("source_year INTEGER NOT NULL"),
            sql.SQL("source_month SMALLINT NOT NULL"),
            sql.SQL("loaded_at TIMESTAMPTZ NOT NULL"),
        ]
    )
    cur.execute(sql.SQL("CREATE TABLE IF NOT EXISTS {}.{} ({})").format(
        sql.Identifier(SCHEMA), sql.Identifier(TRIPS_TABLE), sql.SQL(", ").join(definitions)
    ))

    cur.execute(
        "SELECT column_name, data_type, udt_name FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s",
        (SCHEMA, TRIPS_TABLE),
    )
    existing = {row[0] for row in cur.fetchall()}
    for field in schema_fields:
        if field["column"] not in existing:
            cur.execute(
                sql.SQL("ALTER TABLE {}.{} ADD COLUMN {} {}").format(
                    sql.Identifier(SCHEMA), sql.Identifier(TRIPS_TABLE),
                    sql.Identifier(field["column"]), sql.SQL(field["postgres_type"]),
                )
            )
    metadata_types = {
        "source_file": "TEXT",
        "source_year": "INTEGER",
        "source_month": "SMALLINT",
        "loaded_at": "TIMESTAMPTZ",
    }
    for column, pg_type in metadata_types.items():
        if column not in existing:
            cur.execute(
                sql.SQL("ALTER TABLE {}.{} ADD COLUMN {} {}").format(
                    sql.Identifier(SCHEMA), sql.Identifier(TRIPS_TABLE), sql.Identifier(column), sql.SQL(pg_type)
                )
            )


def ensure_zone_table(cur: psycopg.Cursor[Any], columns: list[dict[str, Any]]) -> None:
    definitions = [
        sql.SQL("{} {}").format(sql.Identifier(column["column"]), sql.SQL(column["postgres_type"]))
        for column in columns
    ]
    cur.execute(sql.SQL("CREATE TABLE IF NOT EXISTS {}.{} ({})").format(
        sql.Identifier(SCHEMA), sql.Identifier(ZONE_TABLE), sql.SQL(", ").join(definitions)
    ))
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s",
        (SCHEMA, ZONE_TABLE),
    )
    existing = {row[0] for row in cur.fetchall()}
    for column in columns:
        if column["column"] not in existing:
            cur.execute(
                sql.SQL("ALTER TABLE {}.{} ADD COLUMN {} {}").format(
                    sql.Identifier(SCHEMA), sql.Identifier(ZONE_TABLE),
                    sql.Identifier(column["column"]), sql.SQL(column["postgres_type"]),
                )
            )


def prior_ingestion(path: Path) -> tuple[str, str] | None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            sql.SQL("SELECT sha256, status FROM {}.{} WHERE source_file=%s").format(
                sql.Identifier(SCHEMA), sql.Identifier(INGESTION_TABLE)
            ),
            (path.name,),
        )
        row = cur.fetchone()
        return (row[0], row[1]) if row else None


def should_skip(path: Path, file_hash: str, reload_names: set[str]) -> bool:
    old = prior_ingestion(path)
    if path.name in reload_names or old is None or old[1] != "success":
        return False
    if old[0] != file_hash:
        raise ChangedSourceNeedsReload(
            f"{path.name} differs from the successfully imported file (SHA-256 changed); "
            f"rerun with --reload {path.name} to replace only that source"
        )
    print(f"{path.name}: Already imported - skipped")
    return True


def log_failure(path: Path, source_type: str, file_hash: str, error: BaseException) -> None:
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(SCHEMA)))
            ensure_ingestion_log(cur)
            cur.execute(
                sql.SQL(
                    "INSERT INTO {}.{} (source_file, source_type, row_count, file_size, sha256, loaded_at, status, error) "
                    "VALUES (%s,%s,NULL,%s,%s,%s,'failed',%s) "
                    "ON CONFLICT (source_file) DO UPDATE SET source_type=EXCLUDED.source_type, "
                    "file_size=EXCLUDED.file_size, sha256=EXCLUDED.sha256, loaded_at=EXCLUDED.loaded_at, "
                    "status='failed', error=EXCLUDED.error"
                ).format(sql.Identifier(SCHEMA), sql.Identifier(INGESTION_TABLE)),
                (path.name, source_type, path.stat().st_size, file_hash, datetime.now(timezone.utc), str(error)[:4000]),
            )
    except Exception as log_error:
        print(f"Could not record failed ingestion for {path.name}: {log_error}", file=sys.stderr)


def log_success(cur: psycopg.Cursor[Any], path: Path, source_type: str, row_count: int, file_hash: str) -> None:
    cur.execute(
        sql.SQL(
            "INSERT INTO {}.{} (source_file, source_type, row_count, file_size, sha256, loaded_at, status, error) "
            "VALUES (%s,%s,%s,%s,%s,%s,'success',NULL) "
            "ON CONFLICT (source_file) DO UPDATE SET source_type=EXCLUDED.source_type, "
            "row_count=EXCLUDED.row_count, file_size=EXCLUDED.file_size, sha256=EXCLUDED.sha256, "
            "loaded_at=EXCLUDED.loaded_at, status='success', error=NULL"
        ).format(sql.Identifier(SCHEMA), sql.Identifier(INGESTION_TABLE)),
        (path.name, source_type, row_count, path.stat().st_size, file_hash, datetime.now(timezone.utc)),
    )


def ingest_parquet(
    path: Path,
    schema_fields: list[dict[str, Any]],
    file_hash: str,
    max_rows_per_source: int,
) -> int:
    match = re.search(r"(\d{4})-(\d{2})", path.name)
    if not match:
        raise ValueError(f"Could not derive source year/month from {path.name!r}")
    source_year, source_month = int(match.group(1)), int(match.group(2))
    parquet = pq.ParquetFile(path)
    actual_rows = parquet.metadata.num_rows
    sample_stride = (
        max(1, math.ceil(actual_rows / max_rows_per_source))
        if max_rows_per_source > 0
        else 1
    )
    source_to_normalized = {source: normalized for field in schema_fields for source in field["source_names"] for normalized in [field["column"]]}
    normalized_types = {field["column"]: field["postgres_type"] for field in schema_fields}
    source_fields = [(field.name, source_to_normalized[field.name]) for field in parquet.schema_arrow]
    copy_columns = [normalized for _, normalized in source_fields] + ["source_file", "source_year", "source_month", "loaded_at"]
    copied = 0
    seen = 0

    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(SCHEMA)))
        ensure_ingestion_log(cur)
        ensure_trips_table(cur, schema_fields)
        cur.execute(
            sql.SQL("DELETE FROM {}.{} WHERE source_file=%s").format(sql.Identifier(SCHEMA), sql.Identifier(TRIPS_TABLE)),
            (path.name,),
        )
        loaded_at = datetime.now(timezone.utc)
        copy_query = sql.SQL("COPY {}.{} ({}) FROM STDIN").format(
            sql.Identifier(SCHEMA), sql.Identifier(TRIPS_TABLE),
            sql.SQL(", ").join(map(sql.Identifier, copy_columns)),
        )
        with cur.copy(copy_query) as copy:
            for batch in parquet.iter_batches(batch_size=BATCH_SIZE):
                for row in batch.to_pylist():
                    seen += 1
                    # An evenly spaced, deterministic sample preserves the
                    # source's time distribution without retaining millions of
                    # rows for a local demo. Set 0 to import every source row.
                    if (seen - 1) % sample_stride != 0:
                        continue
                    values = [adapt_parquet_value(row.get(source), normalized_types[normalized]) for source, normalized in source_fields]
                    values.extend([path.name, source_year, source_month, loaded_at])
                    copy.write_row(values)
                    copied += 1
                print(f"  {path.name}: sampled {copied:,}/{actual_rows:,} rows", flush=True)
        cur.execute(
            sql.SQL("SELECT COUNT(*) FROM {}.{} WHERE source_file=%s").format(sql.Identifier(SCHEMA), sql.Identifier(TRIPS_TABLE)),
            (path.name,),
        )
        inserted = cur.fetchone()[0]
        if inserted != copied:
            raise RuntimeError(f"PostgreSQL has {inserted:,} rows for {path.name}; expected {copied:,}")
        log_success(cur, path, "parquet", inserted, file_hash)
    return copied


def ingest_zone_csv(path: Path, columns: list[dict[str, Any]], expected_rows: int, file_hash: str) -> int:
    source_to_normalized = {column["source_name"]: column["column"] for column in columns}
    pg_types = {column["column"]: column["postgres_type"] for column in columns}
    copied = 0
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(SCHEMA)))
        ensure_ingestion_log(cur)
        ensure_zone_table(cur, columns)
        cur.execute(sql.SQL("TRUNCATE TABLE {}.{}").format(sql.Identifier(SCHEMA), sql.Identifier(ZONE_TABLE)))
        copy_query = sql.SQL("COPY {}.{} ({}) FROM STDIN").format(
            sql.Identifier(SCHEMA), sql.Identifier(ZONE_TABLE),
            sql.SQL(", ").join(sql.Identifier(column["column"]) for column in columns),
        )
        with path.open("r", encoding="utf-8-sig", newline="") as stream, cur.copy(copy_query) as copy:
            reader = csv.DictReader(stream)
            for row in reader:
                copy.write_row([
                    adapt_csv_value(row.get(column["source_name"]), pg_types[column["column"]])
                    for column in columns
                ])
                copied += 1
        if copied != expected_rows:
            raise RuntimeError(f"CSV has {expected_rows:,} rows but streamed {copied:,}")
        cur.execute(sql.SQL("SELECT COUNT(*) FROM {}.{}").format(sql.Identifier(SCHEMA), sql.Identifier(ZONE_TABLE)))
        inserted = cur.fetchone()[0]
        if inserted != expected_rows:
            raise RuntimeError(f"PostgreSQL has {inserted:,} rows in taxi zone lookup; expected {expected_rows:,}")
        log_success(cur, path, "csv", inserted, file_hash)
    return copied


def create_exploration_indexes(schema_fields: list[dict[str, Any]]) -> list[str]:
    names = {field["column"] for field in schema_fields}
    index_columns: list[tuple[str, ...]] = []
    # The schema inspection is source-driven; only add indexes for columns that exist.
    timestamp_columns = [
        field["column"] for field in schema_fields
        if field["postgres_type"].startswith("TIMESTAMP")
        and ("pickup" in field["column"] or "dropoff" in field["column"])
    ]
    for column in timestamp_columns:
        index_columns.append((column,))
    pickup_ids = [name for name in names if ("pickup" in name or name.startswith("pu_")) and "location" in name and "id" in name]
    dropoff_ids = [name for name in names if ("dropoff" in name or name.startswith("do_")) and "location" in name and "id" in name]
    for column in sorted(pickup_ids)[:1] + sorted(dropoff_ids)[:1]:
        index_columns.append((column,))
    index_columns.append(("source_year", "source_month"))
    created = []
    with connect() as conn, conn.cursor() as cur:
        for columns in index_columns:
            index_name = "ix_yellow_taxi_" + "_".join(columns)
            cur.execute(sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {}.{} ({})").format(
                sql.Identifier(index_name), sql.Identifier(SCHEMA), sql.Identifier(TRIPS_TABLE),
                sql.SQL(", ").join(map(sql.Identifier, columns)),
            ))
            created.append(index_name)
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reload", nargs="*", metavar="SOURCE_FILE",
        help="replace specified source file(s); with no names, reload every available source",
    )
    parser.add_argument(
        "--max-rows-per-source",
        type=int,
        default=DEMO_MAX_ROWS_PER_SOURCE,
        help=(
            "maximum rows retained from each Parquet source (default: "
            f"{DEMO_MAX_ROWS_PER_SOURCE:,}; use 0 for a full import)"
        ),
    )
    args = parser.parse_args()
    try:
        trips = parquet_files()
        zone_path = zone_file()
        schema_fields, drift = combined_trip_schema(trips)
        if drift:
            print("Parquet schema drift detected; using the loss-conscious union schema:")
            for item in drift:
                print(f"  {item}")
        zone_columns, zone_rows, _ = read_csv_schema(zone_path)
        available = {path.name for path in trips} | {zone_path.name}
        if args.reload is None:
            reload_names: set[str] = set()
        elif args.reload:
            reload_names = set(args.reload)
        else:
            reload_names = set(available)
        unknown = reload_names - available
        if unknown:
            raise ValueError(f"Unknown source file(s): {', '.join(sorted(unknown))}. Available: {', '.join(sorted(available))}")

        # Bootstrap catalog objects before the first idempotency lookup.
        with connect() as conn, conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(SCHEMA)))
            ensure_ingestion_log(cur)
            ensure_trips_table(cur, schema_fields)
            ensure_zone_table(cur, zone_columns)

        failed: list[tuple[Path, str]] = []
        for path in trips:
            file_hash = checksum(path)
            try:
                if should_skip(path, file_hash, reload_names):
                    continue
                print(f"Importing {path.name} ({path.stat().st_size:,} bytes)")
                rows = ingest_parquet(path, schema_fields, file_hash, args.max_rows_per_source)
                print(f"  Imported and validated {rows:,} rows")
            except Exception as exc:
                if not isinstance(exc, ChangedSourceNeedsReload):
                    log_failure(path, "parquet", file_hash, exc)
                failed.append((path, str(exc)))
                print(f"  FAILED: {exc}", file=sys.stderr)

        zone_hash = checksum(zone_path)
        try:
            if not should_skip(zone_path, zone_hash, reload_names):
                print(f"Importing {zone_path.name} ({zone_path.stat().st_size:,} bytes)")
                rows = ingest_zone_csv(zone_path, zone_columns, zone_rows, zone_hash)
                print(f"  Imported and validated {rows:,} rows")
        except Exception as exc:
            if not isinstance(exc, ChangedSourceNeedsReload):
                log_failure(zone_path, "csv", zone_hash, exc)
            failed.append((zone_path, str(exc)))
            print(f"  FAILED: {exc}", file=sys.stderr)

        if not failed:
            indexes = create_exploration_indexes(schema_fields)
            print(f"Exploration indexes present: {', '.join(indexes) if indexes else 'none'}")
        with connect() as conn, conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT COUNT(*) FROM {}.{}").format(sql.Identifier(SCHEMA), sql.Identifier(TRIPS_TABLE)))
            total = cur.fetchone()[0]
            cur.execute(sql.SQL("SELECT source_file, COUNT(*) FROM {}.{} GROUP BY source_file ORDER BY source_file").format(sql.Identifier(SCHEMA), sql.Identifier(TRIPS_TABLE)))
            by_source = cur.fetchall()
        print("\nValidated PostgreSQL summary")
        print(f"Total trip rows: {total:,}")
        for source, count in by_source:
            print(f"  {source}: {count:,}")
        print(f"Data directory: {DATA_DIR}")
        if failed:
            print("Failed sources:")
            for path, error in failed:
                print(f"  {path.name}: {error}")
            return 1
        return 0
    except Exception as exc:
        print(f"Import could not start: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
