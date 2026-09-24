# AI BI Assistant

An analytics workspace for the NYC Yellow Taxi dataset. The app combines a
Next.js chat interface, FastAPI, PostgreSQL, Apache Superset, Redis, and
Gemini-assisted analysis.

## What it does

- Ask questions about the connected NYC Yellow Taxi data.
- Preview query results and charts in the chat.
- Create charts and dashboards in Superset after an explicit confirmation.
- Embed the live Superset dashboard in the application.

The application is designed around the `ai_bi` PostgreSQL database and the
`raw.yellow_taxi_trips` table. Superset metadata is stored separately in the
`superset` database.

## Requirements

- Git
- Docker Engine or Docker Desktop with Docker Compose v2
- Optional: Python 3 for the Superset setup script

## Repository and data policy

Source code, configuration templates, scripts, and documentation are kept in
Git. Large or environment-specific data is deliberately ignored:

- `data/*.parquet` — raw NYC Taxi source files
- `data/exports/*.dump`, `.backup`, `.sql`, `.tar`, `.zip` — database exports
- `.env` — credentials and deployment settings

Keep those files in private object storage, a secure backup system, or a
separate release bundle. See [data/exports/README.md](data/exports/README.md)
for the current PostgreSQL archive format.

## Quick start

1. Clone the repository and create a local environment file.

   ```powershell
   git clone <YOUR_REPOSITORY_URL>
   Set-Location LLM_superset
   Copy-Item .env.example .env
   ```

2. Edit `.env`. At minimum, replace these placeholder values with unique
   secrets:

   - `POSTGRES_PASSWORD`
   - `SUPERSET_ADMIN_PASSWORD`
   - `SUPERSET_SECRET_KEY`
   - `SUPERSET_GUEST_TOKEN_JWT_SECRET`
   - `SUPERSET_ANALYTICS_DB_PASSWORD`

   Set `GEMINI_API_KEY` to enable the AI chat. The stack still starts without
   it, but `/api/v1/ai/chat` is unavailable.

3. Start PostgreSQL, then load data by one of the methods below.

   ```powershell
   docker compose up -d postgres
   ```

4. Start the full stack.

   ```powershell
   docker compose up -d --build
   docker compose ps
   ```

5. Initialize the Superset dataset and demo dashboard after Superset is
   healthy.

   ```powershell
   python superset/scripts/setup_nyc_taxi_demo.py
   ```

Local URLs:

| Service | URL |
| --- | --- |
| Application | http://localhost:43117 |
| API docs | http://localhost:48123/docs |
| Superset | http://localhost:58088 |

## Load analytics data

Choose one method. Do this while only PostgreSQL is running for a clean first
deployment.

### Option A — restore a PostgreSQL archive (recommended)

Copy the private archive, such as `ai_bi_raw_20260924.dump`, into
`data/exports/`. It is a PostgreSQL custom archive and is already compressed.
Do not unzip it.

```powershell
docker compose cp data/exports/ai_bi_raw_20260924.dump postgres:/tmp/ai_bi_raw.dump
docker compose exec -T postgres pg_restore -U ai_bi_user -d ai_bi --no-owner --no-privileges --clean --if-exists /tmp/ai_bi_raw.dump
```

`--clean --if-exists` replaces objects in the `raw` schema; omit those flags
when restoring into an empty database. Replace `ai_bi_user` and `ai_bi` only
if you changed `POSTGRES_USER` or `APP_DB_NAME` in `.env`. Verify the import:

```powershell
docker compose exec -T postgres psql -U ai_bi_user -d ai_bi -c "SELECT COUNT(*) FROM raw.yellow_taxi_trips;"
```

### Option B — import source files

Obtain these private source files and place them under `data/`:

```text
yellow_tripdata_2026-05.parquet
yellow_tripdata_2026-06.parquet
yellow_tripdata_2026-07.parquet
taxi_zone_lookup.csv
```

Then run the loader:

```powershell
docker compose --profile tools run --rm data-loader
```

Set `DEMO_MAX_ROWS_PER_SOURCE=0` in `.env` only if a full source import is
intended. The default limits each input file to 10,000 rows for the demo.

## Operations

```powershell
# Service status and logs
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f superset

# Health checks
Invoke-WebRequest http://localhost:48123/health
Invoke-WebRequest http://localhost:48123/health/db

# Stop services but preserve database volumes
docker compose down
```

`docker compose down -v` deletes PostgreSQL, Redis, Superset, and frontend
volumes. Use it only when you intend to remove all local persisted state.

## Server deployment

The base Compose file deliberately binds all service ports to `127.0.0.1`.
For a server, use a TLS reverse proxy such as Nginx or Caddy and keep PostgreSQL,
Redis, and the Superset MCP port private. Set the public URLs in `.env` before
starting containers:

```dotenv
FRONTEND_URL=https://bi.example.com
FRONTEND_ORIGINS=https://bi.example.com
NEXT_PUBLIC_API_URL=https://bi.example.com
NEXT_PUBLIC_SUPERSET_URL=https://superset.example.com
SUPERSET_PUBLIC_URL=https://superset.example.com
```

Route `bi.example.com` to the local frontend port `43117` and its `/api/`
path to local backend port `48123`. Route `superset.example.com` to local port
`58088`. Full deployment order, proxy requirements, data restoration, and
security checks are in [docs/deployment.md](docs/deployment.md).

## Security notes

- Never commit `.env`, database dumps, raw Parquet files, or exported tokens.
- Set distinct, strong Superset and PostgreSQL secrets for every environment.
- The app has no end-user authentication yet. Do not expose it publicly until
  authentication, authorization, and row-level security are configured.
- Do not expose the MCP port (`55008`) outside localhost.

## Further documentation

- [Deployment guide](docs/deployment.md)
- [Data export and restore guide](data/exports/README.md)
- [Superset dashboard guide](docs/superset-nyc-taxi-dashboard.md)
- [Gemini and Superset MCP guide](docs/superset-mcp-gemini.md)
