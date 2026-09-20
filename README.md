# AI BI Assistant

Docker Compose skeleton for an AI BI Assistant with a Next.js frontend, FastAPI backend, PostgreSQL, Apache Superset, and Redis.

## Frontend Demo

The frontend is a dark analytics workspace with a mock chat and visualization flow. It runs without an LLM or a real analytics query engine, so you can explore the product UI while the backend integrations are developed.

Try these questions in the chat:

- `Tổng doanh thu năm 2026?` — a big number card.
- `Xu hướng doanh thu theo tháng?` — a line chart.
- `Top 5 sản phẩm doanh thu cao nhất?` — a bar chart.
- `Doanh thu theo thành phố?` — a city comparison chart.

For a filter refinement, ask for the top five products and then send `Chỉ xem ở Hà Nội.` Remove the `City = Hà Nội` chip to clear that filter. Open **View SQL** to inspect or copy the example query; the displayed SQL is mock content and is not executed. Recent analyses in the sidebar are also sample conversations and reset when the page is reloaded.

The API badge checks FastAPI `GET /health`. Superset is labeled **Demo** until a real integration is connected. Save chart, dashboard, and Superset actions are intentionally disabled in this frontend demo. The charts still use mock frontend values; NYC Yellow Taxi source data is loaded separately into the PostgreSQL `raw` schema for exploration.

## Architecture

```text
Browser
  ├── Next.js frontend
  │     └── FastAPI backend
  │             └── PostgreSQL (ai_bi)
  └── Apache Superset
        ├── PostgreSQL (Superset metadata)
        └── Redis (cache)
```

There is no LLM or NL2SQL integration and no Superset dataset or dashboard yet. The `ai_bi` database contains raw NYC Yellow Taxi trip and zone lookup tables for data exploration.

## Requirements

- Docker Desktop or Docker Engine
- Docker Compose v2 (`docker compose`)

## Setup

Copy `.env.example` to `.env`, then replace the PostgreSQL password, Superset admin password, and Superset secret key with unique values. Use the same PostgreSQL password in `POSTGRES_PASSWORD` and `DATABASE_URL`.

In PowerShell, use `Copy-Item .env.example .env` for the copy step.

Generate a Superset secret key with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Then build and start the services:

```bash
docker compose build
docker compose up -d
docker compose ps
```

The Superset administrator is created from `SUPERSET_ADMIN_USERNAME`, `SUPERSET_ADMIN_PASSWORD`, and `SUPERSET_ADMIN_EMAIL` in `.env`. The initialization service skips creating the account if that username already exists. Changing the password in `.env` later does not reset the existing account password.

## Service URLs

| Service | URL |
| --- | --- |
| Frontend | <http://localhost:43117> |
| FastAPI | <http://localhost:48123> |
| FastAPI Swagger | <http://localhost:48123/docs> |
| Superset | <http://localhost:58088> |
| PostgreSQL | `localhost:55439` |
| Redis | `localhost:56379` |

Database clients inside Compose use service DNS and container ports. For example, FastAPI uses `postgres:5432`; Superset uses `postgres:5432` for metadata and `redis:6379` for cache. The host port mappings are for access from the host machine.

## Health checks

- `GET /health` returns `{"status":"ok"}`.
- `GET /health/db` runs `SELECT 1` and returns the PostgreSQL connection status.
- `GET /health/superset` checks Superset's health endpoint.
- The frontend periodically checks only the FastAPI `GET /health` endpoint; its Superset badge is a demo status.
- PostgreSQL uses `pg_isready`; Redis uses `redis-cli ping`.

Check the API from a terminal:

```bash
curl http://localhost:48123/health
curl http://localhost:48123/health/db
```

## Useful commands

```bash
docker compose ps
docker compose logs -f frontend
docker compose logs -f backend
docker compose logs -f superset
docker compose logs -f postgres
docker compose down
```

`docker compose down` removes containers and the Compose network but preserves named volumes and their database data. `docker compose down -v` also deletes persistent volumes, including PostgreSQL databases, Redis data, Superset home data, and frontend dependency caches.

PostgreSQL's initialization SQL runs only when `postgres_data` is empty. It creates the `superset` database alongside the initial `ai_bi` database. The `ai_bi` database contains no business tables or sample data.

## NYC Yellow Taxi Data Ingestion

The one-off `data-loader` Compose service reads the source files from `data/` and writes raw data to the `ai_bi` PostgreSQL database. It uses the existing `DATABASE_URL`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` settings from `.env`; inside Compose, PostgreSQL is reached as `postgres:5432`. Existing host port mappings are unchanged.

Expected source files:

```text
data/yellow_tripdata_2026-05.parquet
data/yellow_tripdata_2026-06.parquet
data/yellow_tripdata_2026-07.parquet
data/taxi_zone_lookup.csv
```

Inspect source file sizes, row counts, actual schemas, schema drift, first five rows, and the supplied trip dictionary:

```bash
docker compose run --rm data-loader /app/scripts/inspect_nyc_taxi_data.py
```

Import all available Yellow Taxi Parquet files and the zone lookup. Parquet rows are streamed in batches; each source is imported in its own transaction, and the loader validates its row count before recording success:

```bash
docker compose run --rm data-loader
```

Successful, unchanged sources are skipped on later runs. Reload only one source file (its existing rows are replaced transactionally):

```bash
docker compose run --rm data-loader /app/scripts/import_nyc_taxi.py --reload yellow_tripdata_2026-05.parquet
```

Use `--reload` without a filename to reload every available source. After a successful import, profile the database and write `data/nyc_taxi_profile.md`:

```bash
docker compose run --rm data-loader /app/scripts/profile_nyc_taxi.py
```

The raw tables are `raw.yellow_taxi_trips`, `raw.taxi_zone_lookup`, and `raw.ingestion_log`. The trip table keeps source fields (normalized to snake_case with source-name mappings in the report) and adds `source_file`, `source_year`, `source_month`, and `loaded_at`. No synthetic trip primary key or business transformation is applied.

Example PostgreSQL checks from a SQL client:

```sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'raw'
ORDER BY table_name;

SELECT COUNT(*) FROM raw.yellow_taxi_trips;

SELECT source_file, COUNT(*) AS rows
FROM raw.yellow_taxi_trips
GROUP BY source_file
ORDER BY source_file;

SELECT * FROM raw.yellow_taxi_trips LIMIT 10;
SELECT * FROM raw.taxi_zone_lookup LIMIT 10;
SELECT * FROM raw.ingestion_log ORDER BY source_file;
```

The generated profile includes the discovered PostgreSQL schema, per-column null and numeric summaries, date ranges and month anomalies, categorical frequencies, zone lookup statistics, pickup/dropoff location ID compatibility, quality-check counts, and sample rows. Profiling reports anomalies without deleting or cleaning records.
