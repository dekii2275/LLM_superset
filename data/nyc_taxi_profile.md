# NYC Yellow Taxi Data Profile

Generated: 2026-09-20T04:43:35+00:00

## Dataset overview

- Total trip rows: **11,458,193**
- Total trip table columns: **25** (includes ingestion metadata)
- Source trip files: **3**
- Trip source months: **2026-05, 2026-06, 2026-07**
- PostgreSQL raw tables: `raw.yellow_taxi_trips`, `raw.taxi_zone_lookup`, `raw.ingestion_log`
- Taxi zone lookup rows: **265**
- Parquet schemas identical: **no**

| Source file | Expected rows | Imported rows | Status | File size (bytes) |
|---|---:|---:|---|---:|
| yellow_tripdata_2026-05.parquet | 4,090,836 | 4,090,836 | success | 69,699,174 |
| yellow_tripdata_2026-06.parquet | 3,837,248 | 3,837,248 | success | 65,465,637 |
| yellow_tripdata_2026-07.parquet | 3,530,109 | 3,530,109 | success | 61,685,033 |
| taxi_zone_lookup.csv | 265 | 265 | success | 12,331 |

## Source schema comparison

Schema drift was detected and the loader created a union table schema. Missing source values are stored as NULL. No source field was dropped.

- **yellow_tripdata_2026-06.parquet:** missing=none; added=['request_source']; type changes=none; order changed=False.
- **yellow_tripdata_2026-07.parquet:** missing=none; added=['request_source']; type changes=none; order changed=False.

## Trip schema

Source column names are normalized to lowercase snake_case. The source name mapping is recorded below. Descriptions are included only when mapped from the supplied data dictionary.

| PostgreSQL column | PostgreSQL type | Source column name(s) | Source type | Nullable | Description |
|---|---|---|---|---|---|
| `vendor_id` | `integer` | `VendorID` | `int32` | YES | A code indicating the TPEP provider that provided the record. 1 = Creative Mobile Technologies, LLC 2 = Curb Mobility, LLC 6 = Myle Technologies Inc 7 = Helix |
| `tpep_pickup_datetime` | `timestamp without time zone` | `tpep_pickup_datetime` | `timestamp[us]` | YES | The date and time when the meter was engaged. |
| `tpep_dropoff_datetime` | `timestamp without time zone` | `tpep_dropoff_datetime` | `timestamp[us]` | YES | The date and time when the meter was disengaged. |
| `passenger_count` | `bigint` | `passenger_count` | `int64` | YES | The number of passengers in the vehicle. |
| `trip_distance` | `double precision` | `trip_distance` | `double` | YES | The elapsed trip distance in miles reported by the taximeter. |
| `ratecode_id` | `bigint` | `RatecodeID` | `int64` | YES | The final rate code in effect at the end of the trip. 1 = Standard rate 2 = JFK 3 = Newark 4 = Nassau or Westchester 5 = Negotiated fare 6 = Group ride 99 = Null/unknown |
| `store_and_fwd_flag` | `text` | `store_and_fwd_flag` | `large_string` | YES | This flag indicates whether the trip record was held in vehicle memory before sending to the vendor, aka “store and forward,” because the vehicle did not have a connection to the server. Y = store and forward trip N = not a store and forward trip |
| `pu_location_id` | `integer` | `PULocationID` | `int32` | YES | TLC Taxi Zone in which the taximeter was engaged. |
| `do_location_id` | `integer` | `DOLocationID` | `int32` | YES | TLC Taxi Zone in which the taximeter was disengaged. |
| `payment_type` | `bigint` | `payment_type` | `int64` | YES | A numeric code signifying how the passenger paid for the trip. 0 = Flex Fare trip 1 = Credit card 2 = Cash 3 = No charge 4 = Dispute 5 = Unknown 6 = Voided trip |
| `fare_amount` | `double precision` | `fare_amount` | `double` | YES | The time-and-distance fare calculated by the meter. For additional information on the following columns, see https://www.nyc.gov/site/tlc/passengers/taxi-fare.page |
| `extra` | `double precision` | `extra` | `double` | YES | Miscellaneous extras and surcharges. |
| `mta_tax` | `double precision` | `mta_tax` | `double` | YES | Tax that is automatically triggered based on the metered rate in use. |
| `tip_amount` | `double precision` | `tip_amount` | `double` | YES | Tip amount – This field is automatically populated for credit card tips. Cash tips are not included. |
| `tolls_amount` | `double precision` | `tolls_amount` | `double` | YES | Total amount of all tolls paid in trip. |
| `improvement_surcharge` | `double precision` | `improvement_surcharge` | `double` | YES | Improvement surcharge assessed trips at the flag drop. The improvement surcharge began being levied in 2015. |
| `total_amount` | `double precision` | `total_amount` | `double` | YES | The total amount charged to passengers. Does not include cash tips. |
| `congestion_surcharge` | `double precision` | `congestion_surcharge` | `double` | YES | Total amount collected in trip for NYS congestion surcharge. |
| `airport_fee` | `double precision` | `Airport_fee` | `double` | YES | For pick up only at LaGuardia and John F. Kennedy Airports. |
| `cbd_congestion_fee` | `double precision` | `cbd_congestion_fee` | `double` | YES | Per-trip charge for MTA's Congestion Relief Zone starting Jan. 5, 2025. |
| `request_source` | `text` | `request_source` | `large_string` | YES | Unknown / not mapped yet |
| `source_file` | `text` | `(ingestion metadata)` | `generated during ingestion` | NO | Unknown / not mapped yet |
| `source_year` | `integer` | `(ingestion metadata)` | `generated during ingestion` | NO | Unknown / not mapped yet |
| `source_month` | `smallint` | `(ingestion metadata)` | `generated during ingestion` | NO | Unknown / not mapped yet |
| `loaded_at` | `timestamp with time zone` | `(ingestion metadata)` | `generated during ingestion` | NO | Unknown / not mapped yet |

## Date range

- Pickup (`tpep_pickup_datetime`): 2008-12-30 23:06:00 to 2026-08-05 20:54:00
- Dropoff (`tpep_dropoff_datetime`): 2008-12-30 23:15:45 to 2026-08-05 21:04:08

### Pickup dates outside the source month

- `yellow_tripdata_2026-05.parquet`: 14 rows have pickup timestamps outside the month in the source filename.
- `yellow_tripdata_2026-06.parquet`: 17 rows have pickup timestamps outside the month in the source filename.
- `yellow_tripdata_2026-07.parquet`: 46 rows have pickup timestamps outside the month in the source filename.

## Null analysis

| Column | Null count | Null percentage |
|---|---:|---:|
| `request_source` | 9,475,596 | 82.6971% |
| `airport_fee` | 2,938,598 | 25.6463% |
| `congestion_surcharge` | 2,938,598 | 25.6463% |
| `passenger_count` | 2,938,598 | 25.6463% |
| `ratecode_id` | 2,938,598 | 25.6463% |
| `store_and_fwd_flag` | 2,938,598 | 25.6463% |
| `cbd_congestion_fee` | 0 | 0.0000% |
| `do_location_id` | 0 | 0.0000% |
| `extra` | 0 | 0.0000% |
| `fare_amount` | 0 | 0.0000% |
| `improvement_surcharge` | 0 | 0.0000% |
| `loaded_at` | 0 | 0.0000% |
| `mta_tax` | 0 | 0.0000% |
| `payment_type` | 0 | 0.0000% |
| `pu_location_id` | 0 | 0.0000% |
| `source_file` | 0 | 0.0000% |
| `source_month` | 0 | 0.0000% |
| `source_year` | 0 | 0.0000% |
| `tip_amount` | 0 | 0.0000% |
| `tolls_amount` | 0 | 0.0000% |
| `total_amount` | 0 | 0.0000% |
| `tpep_dropoff_datetime` | 0 | 0.0000% |
| `tpep_pickup_datetime` | 0 | 0.0000% |
| `trip_distance` | 0 | 0.0000% |
| `vendor_id` | 0 | 0.0000% |

## Numeric summary

| Column | Min | Max | Average |
|---|---:|---:|---:|
| `vendor_id` | 1 | 7 | 1.8950529110480160 |
| `passenger_count` | 0 | 9 | 1.2550013234197165 |
| `trip_distance` | 0.0 | 318129.1 | 5.220112484578029 |
| `ratecode_id` | 1 | 99 | 3.3514413537263215 |
| `pu_location_id` | 1 | 265 | 161.8598538181369436 |
| `do_location_id` | 1 | 265 | 161.5197561255950218 |
| `payment_type` | 0 | 5 | 0.86076670204455449476 |
| `fare_amount` | -1683.7 | 7045.0 | 21.36104982261705 |
| `extra` | -7.5 | 244.35 | 1.1432396757499237 |
| `mta_tax` | -0.5 | 11.5 | 0.4894803491266031 |
| `tip_amount` | -81.97 | 333.33 | 2.923507853287365 |
| `tolls_amount` | -129.48 | 1210.79 | 0.5469387616339252 |
| `improvement_surcharge` | -1.0 | 2.5 | 0.9782900410210956 |
| `total_amount` | -1815.18 | 7053.5 | 30.35904815971681 |
| `congestion_surcharge` | -2.5 | 2.75 | 2.2556162763605547 |
| `airport_fee` | -2.0 | 27.0 | 0.17585108212303519 |
| `cbd_congestion_fee` | -0.75 | 0.75 | 0.5369173830463495 |
| `source_year` | 2026 | 2026 | 2026.0000000000000000 |
| `source_month` | 5 | 7 | 5.9510632261125293 |

## Categorical analysis

Distinct counts and top-value frequencies exclude NULL values.

### `vendor_id`

- Distinct values: 4

| Value | Frequency |
|---|---:|
| 2 | 9,276,780 |
| 1 | 2,014,294 |
| 7 | 143,314 |
| 6 | 23,805 |

### `payment_type`

- Distinct values: 6

| Value | Frequency |
|---|---:|
| 1 | 7,342,917 |
| 0 | 2,938,598 |
| 2 | 1,076,359 |
| 4 | 66,235 |
| 3 | 34,082 |
| 5 | 2 |

### `ratecode_id`

- Distinct values: 7

| Value | Frequency |
|---|---:|
| 1 | 7,881,389 |
| 2 | 274,121 |
| 99 | 195,743 |
| 5 | 106,665 |
| 3 | 35,304 |
| 4 | 26,370 |
| 6 | 3 |

### `store_and_fwd_flag`

- Distinct values: 2

| Value | Frequency |
|---|---:|
| N | 8,503,361 |
| Y | 16,234 |


## Taxi zone lookup

- Rows: 265
- Columns (4): `location_id`, `borough`, `zone`, `service_zone`
- Distinct boroughs: 8
- Distinct zones: 262

| Borough | Rows |
|---|---:|
| Manhattan | 69 |
| Queens | 69 |
| Brooklyn | 61 |
| Bronx | 43 |
| Staten Island | 20 |
| EWR | 1 |
| N/A | 1 |
| Unknown | 1 |

Ten sample rows returned by `SELECT * FROM raw.taxi_zone_lookup LIMIT 10`:

```json
[
  {
    "location_id": 1,
    "borough": "EWR",
    "zone": "Newark Airport",
    "service_zone": "EWR"
  },
  {
    "location_id": 2,
    "borough": "Queens",
    "zone": "Jamaica Bay",
    "service_zone": "Boro Zone"
  },
  {
    "location_id": 3,
    "borough": "Bronx",
    "zone": "Allerton/Pelham Gardens",
    "service_zone": "Boro Zone"
  },
  {
    "location_id": 4,
    "borough": "Manhattan",
    "zone": "Alphabet City",
    "service_zone": "Yellow Zone"
  },
  {
    "location_id": 5,
    "borough": "Staten Island",
    "zone": "Arden Heights",
    "service_zone": "Boro Zone"
  },
  {
    "location_id": 6,
    "borough": "Staten Island",
    "zone": "Arrochar/Fort Wadsworth",
    "service_zone": "Boro Zone"
  },
  {
    "location_id": 7,
    "borough": "Queens",
    "zone": "Astoria",
    "service_zone": "Boro Zone"
  },
  {
    "location_id": 8,
    "borough": "Queens",
    "zone": "Astoria Park",
    "service_zone": "Boro Zone"
  },
  {
    "location_id": 9,
    "borough": "Queens",
    "zone": "Auburndale",
    "service_zone": "Boro Zone"
  },
  {
    "location_id": 10,
    "borough": "Queens",
    "zone": "Baisley Park",
    "service_zone": "Boro Zone"
  }
]
```

## Location ID compatibility

- Pickup: `pu_location_id` has 261 distinct non-null IDs; 0 unmatched (0.0000%).
- Dropoff: `do_location_id` has 262 distinct non-null IDs; 0 unmatched (0.0000%).

## Basic data-quality checks

These are counts only. Raw records were not cleaned or deleted.

| Check | Rows |
|---|---:|
| trip_distance < 0 | 0 |
| trip_distance = 0 | 369,459 |
| fare_amount < 0 | 42,079 |
| total_amount < 0 | 43,888 |
| passenger_count < 0 | 0 |
| dropoff_time < pickup_time | 2 |
| pickup_time = dropoff_time | 144,184 |

## Trip sample

Ten sample records, ordered by source file and pickup time. All 25 table columns are included.

```json
[
  {
    "vendor_id": 2,
    "tpep_pickup_datetime": "2008-12-31 23:05:53",
    "tpep_dropoff_datetime": "2009-01-01 18:07:17",
    "passenger_count": 1,
    "trip_distance": 2.28,
    "ratecode_id": 1,
    "store_and_fwd_flag": "N",
    "pu_location_id": 264,
    "do_location_id": 264,
    "payment_type": 1,
    "fare_amount": 17.7,
    "extra": 0.0,
    "mta_tax": 0.5,
    "tip_amount": 4.49,
    "tolls_amount": 0.0,
    "improvement_surcharge": 1.0,
    "total_amount": 26.94,
    "congestion_surcharge": 2.5,
    "airport_fee": 0.0,
    "cbd_congestion_fee": 0.75,
    "request_source": null,
    "source_file": "yellow_tripdata_2026-05.parquet",
    "source_year": 2026,
    "source_month": 5,
    "loaded_at": "2026-09-20 04:18:33.555313+00:00"
  },
  {
    "vendor_id": 2,
    "tpep_pickup_datetime": "2009-01-01 15:33:07",
    "tpep_dropoff_datetime": "2009-01-01 17:08:07",
    "passenger_count": 1,
    "trip_distance": 13.01,
    "ratecode_id": 1,
    "store_and_fwd_flag": "N",
    "pu_location_id": 138,
    "do_location_id": 90,
    "payment_type": 1,
    "fare_amount": 79.3,
    "extra": 0.0,
    "mta_tax": 0.5,
    "tip_amount": 12.0,
    "tolls_amount": 14.92,
    "improvement_surcharge": 1.0,
    "total_amount": 110.97,
    "congestion_surcharge": 2.5,
    "airport_fee": 0.0,
    "cbd_congestion_fee": 0.75,
    "request_source": null,
    "source_file": "yellow_tripdata_2026-05.parquet",
    "source_year": 2026,
    "source_month": 5,
    "loaded_at": "2026-09-20 04:18:33.555313+00:00"
  },
  {
    "vendor_id": 2,
    "tpep_pickup_datetime": "2026-04-30 23:47:18",
    "tpep_dropoff_datetime": "2026-04-30 23:53:05",
    "passenger_count": 5,
    "trip_distance": 1.24,
    "ratecode_id": 1,
    "store_and_fwd_flag": "N",
    "pu_location_id": 50,
    "do_location_id": 246,
    "payment_type": 1,
    "fare_amount": 7.9,
    "extra": 1.0,
    "mta_tax": 0.5,
    "tip_amount": 4.1,
    "tolls_amount": 0.0,
    "improvement_surcharge": 1.0,
    "total_amount": 17.75,
    "congestion_surcharge": 2.5,
    "airport_fee": 0.0,
    "cbd_congestion_fee": 0.75,
    "request_source": null,
    "source_file": "yellow_tripdata_2026-05.parquet",
    "source_year": 2026,
    "source_month": 5,
    "loaded_at": "2026-09-20 04:18:33.555313+00:00"
  },
  {
    "vendor_id": 2,
    "tpep_pickup_datetime": "2026-04-30 23:49:52",
    "tpep_dropoff_datetime": "2026-05-01 00:04:47",
    "passenger_count": 1,
    "trip_distance": 1.53,
    "ratecode_id": 1,
    "store_and_fwd_flag": "N",
    "pu_location_id": 68,
    "do_location_id": 234,
    "payment_type": 2,
    "fare_amount": 13.5,
    "extra": 1.0,
    "mta_tax": 0.5,
    "tip_amount": 0.0,
    "tolls_amount": 0.0,
    "improvement_surcharge": 1.0,
    "total_amount": 19.25,
    "congestion_surcharge": 2.5,
    "airport_fee": 0.0,
    "cbd_congestion_fee": 0.75,
    "request_source": null,
    "source_file": "yellow_tripdata_2026-05.parquet",
    "source_year": 2026,
    "source_month": 5,
    "loaded_at": "2026-09-20 04:18:33.555313+00:00"
  },
  {
    "vendor_id": 2,
    "tpep_pickup_datetime": "2026-04-30 23:50:39",
    "tpep_dropoff_datetime": "2026-04-30 23:57:37",
    "passenger_count": 1,
    "trip_distance": 1.04,
    "ratecode_id": 1,
    "store_and_fwd_flag": "N",
    "pu_location_id": 263,
    "do_location_id": 236,
    "payment_type": 1,
    "fare_amount": 8.6,
    "extra": 1.0,
    "mta_tax": 0.5,
    "tip_amount": 2.72,
    "tolls_amount": 0.0,
    "improvement_surcharge": 1.0,
    "total_amount": 16.32,
    "congestion_surcharge": 2.5,
    "airport_fee": 0.0,
    "cbd_congestion_fee": 0.0,
    "request_source": null,
    "source_file": "yellow_tripdata_2026-05.parquet",
    "source_year": 2026,
    "source_month": 5,
    "loaded_at": "2026-09-20 04:18:33.555313+00:00"
  },
  {
    "vendor_id": 2,
    "tpep_pickup_datetime": "2026-04-30 23:51:13",
    "tpep_dropoff_datetime": "2026-05-01 00:28:20",
    "passenger_count": 5,
    "trip_distance": 9.58,
    "ratecode_id": 1,
    "store_and_fwd_flag": "N",
    "pu_location_id": 88,
    "do_location_id": 41,
    "payment_type": 1,
    "fare_amount": 47.8,
    "extra": 1.0,
    "mta_tax": 0.5,
    "tip_amount": 0.0,
    "tolls_amount": 0.0,
    "improvement_surcharge": 1.0,
    "total_amount": 53.55,
    "congestion_surcharge": 2.5,
    "airport_fee": 0.0,
    "cbd_congestion_fee": 0.75,
    "request_source": null,
    "source_file": "yellow_tripdata_2026-05.parquet",
    "source_year": 2026,
    "source_month": 5,
    "loaded_at": "2026-09-20 04:18:33.555313+00:00"
  },
  {
    "vendor_id": 2,
    "tpep_pickup_datetime": "2026-04-30 23:51:53",
    "tpep_dropoff_datetime": "2026-04-30 23:58:30",
    "passenger_count": 1,
    "trip_distance": 1.06,
    "ratecode_id": 1,
    "store_and_fwd_flag": "N",
    "pu_location_id": 170,
    "do_location_id": 137,
    "payment_type": 1,
    "fare_amount": 8.6,
    "extra": 1.0,
    "mta_tax": 0.5,
    "tip_amount": 0.05,
    "tolls_amount": 0.0,
    "improvement_surcharge": 1.0,
    "total_amount": 14.4,
    "congestion_surcharge": 2.5,
    "airport_fee": 0.0,
    "cbd_congestion_fee": 0.75,
    "request_source": null,
    "source_file": "yellow_tripdata_2026-05.parquet",
    "source_year": 2026,
    "source_month": 5,
    "loaded_at": "2026-09-20 04:18:33.555313+00:00"
  },
  {
    "vendor_id": 2,
    "tpep_pickup_datetime": "2026-04-30 23:53:41",
    "tpep_dropoff_datetime": "2026-05-01 00:14:20",
    "passenger_count": 2,
    "trip_distance": 8.76,
    "ratecode_id": 1,
    "store_and_fwd_flag": "N",
    "pu_location_id": 138,
    "do_location_id": 161,
    "payment_type": 1,
    "fare_amount": 35.9,
    "extra": 6.0,
    "mta_tax": 0.5,
    "tip_amount": 11.22,
    "tolls_amount": 7.46,
    "improvement_surcharge": 1.0,
    "total_amount": 67.33,
    "congestion_surcharge": 2.5,
    "airport_fee": 2.0,
    "cbd_congestion_fee": 0.75,
    "request_source": null,
    "source_file": "yellow_tripdata_2026-05.parquet",
    "source_year": 2026,
    "source_month": 5,
    "loaded_at": "2026-09-20 04:18:33.555313+00:00"
  },
  {
    "vendor_id": 2,
    "tpep_pickup_datetime": "2026-04-30 23:54:52",
    "tpep_dropoff_datetime": "2026-05-01 00:11:11",
    "passenger_count": 5,
    "trip_distance": 2.93,
    "ratecode_id": 1,
    "store_and_fwd_flag": "N",
    "pu_location_id": 239,
    "do_location_id": 166,
    "payment_type": 1,
    "fare_amount": 18.4,
    "extra": 1.0,
    "mta_tax": 0.5,
    "tip_amount": 4.68,
    "tolls_amount": 0.0,
    "improvement_surcharge": 1.0,
    "total_amount": 28.08,
    "congestion_surcharge": 2.5,
    "airport_fee": 0.0,
    "cbd_congestion_fee": 0.0,
    "request_source": null,
    "source_file": "yellow_tripdata_2026-05.parquet",
    "source_year": 2026,
    "source_month": 5,
    "loaded_at": "2026-09-20 04:18:33.555313+00:00"
  },
  {
    "vendor_id": 2,
    "tpep_pickup_datetime": "2026-04-30 23:54:59",
    "tpep_dropoff_datetime": "2026-05-01 00:12:16",
    "passenger_count": 1,
    "trip_distance": 2.27,
    "ratecode_id": 1,
    "store_and_fwd_flag": "N",
    "pu_location_id": 114,
    "do_location_id": 87,
    "payment_type": 2,
    "fare_amount": 13.5,
    "extra": 1.0,
    "mta_tax": 0.5,
    "tip_amount": 0.0,
    "tolls_amount": 0.0,
    "improvement_surcharge": 1.0,
    "total_amount": 19.25,
    "congestion_surcharge": 2.5,
    "airport_fee": 0.0,
    "cbd_congestion_fee": 0.75,
    "request_source": null,
    "source_file": "yellow_tripdata_2026-05.parquet",
    "source_year": 2026,
    "source_month": 5,
    "loaded_at": "2026-09-20 04:18:33.555313+00:00"
  }
]
```

## Ingestion audit

| Source file | Type | Rows in log | Status | Loaded at (UTC) | Error |
|---|---|---:|---|---|---|
| `taxi_zone_lookup.csv` | csv | 265 | success | 2026-09-20 04:25:41.857808+00:00 |  |
| `yellow_tripdata_2026-05.parquet` | parquet | 4090836 | success | 2026-09-20 04:20:56.291086+00:00 |  |
| `yellow_tripdata_2026-06.parquet` | parquet | 3837248 | success | 2026-09-20 04:23:25.307645+00:00 |  |
| `yellow_tripdata_2026-07.parquet` | parquet | 3530109 | success | 2026-09-20 04:25:41.722168+00:00 |  |

## Notes

- No foreign keys, fact/dimension models, analytics views, or data cleaning were applied.
- Monetary source fields retain their source floating-point type when stored as Arrow float values. Decimal source fields use PostgreSQL `NUMERIC`.
