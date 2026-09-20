#!/usr/bin/env python3
"""Inspect the actual NYC taxi source files without loading them into memory wholesale."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq
from pypdf import PdfReader

from nyc_taxi_common import DATA_DIR, combined_trip_schema, parquet_files, read_csv_schema, zone_file


def main() -> None:
    files = parquet_files()
    union, drift = combined_trip_schema(files)
    print("NYC Yellow Taxi source inspection")
    print(f"Data directory: {DATA_DIR}")
    print(f"Parquet schemas identical: {'yes' if not drift else 'no'}")
    if drift:
        print("Schema drift:")
        print(json.dumps(drift, indent=2))
    for path in files:
        parquet = pq.ParquetFile(path)
        print(f"\n## {path.name}")
        print(f"File size: {path.stat().st_size:,} bytes")
        print(f"Rows: {parquet.metadata.num_rows:,}")
        print(f"Columns: {len(parquet.schema_arrow)}")
        for field in parquet.schema_arrow:
            print(f"- {field.name}: {field.type} (nullable={field.nullable})")
        print("First 5 rows:")
        batch = next(parquet.iter_batches(batch_size=5), None)
        print(json.dumps(batch.to_pylist() if batch is not None else [], indent=2, ensure_ascii=False, default=str))

    csv_path = zone_file()
    zone_columns, zone_rows, zone_sample = read_csv_schema(csv_path)
    print(f"\n## {csv_path.name}")
    print(f"File size: {csv_path.stat().st_size:,} bytes")
    print(f"Rows: {zone_rows:,}")
    print(f"Columns: {len(zone_columns)}")
    for column in zone_columns:
        print(f"- {column['source_name']}: {column['postgres_type']}")
    print("First 5 rows:")
    print(json.dumps(zone_sample, indent=2, ensure_ascii=False))

    dictionary_path = DATA_DIR / "data_dictionary_trip_records_yellow.pdf"
    if dictionary_path.is_file():
        try:
            reader = PdfReader(str(dictionary_path))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n".join(pages)
            print(f"\nData dictionary: {dictionary_path.name} ({len(reader.pages)} pages; {len(text):,} extracted characters)")
            print("Dictionary text preview:")
            print(text[:5000])
        except Exception as exc:
            print(f"Data dictionary extraction unavailable: {type(exc).__name__}: {exc}")

    print("\nUnion schema used by the loader:")
    for column in union:
        print(f"- {column['column']} <- {', '.join(column['source_names'])}: {column['arrow_type']} => {column['postgres_type']}")


if __name__ == "__main__":
    main()
