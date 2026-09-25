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
- Node.js 22+ with npm, and `uv` for the native frontend/backend workflow
- Optional: Python 3 for the Superset setup script

## Repository and data policy

Source code, configuration templates, scripts, and documentation are kept in
Git. Large or environment-specific data is deliberately ignored:

- `data/*.parquet` — raw NYC Taxi source files
- `data/exports/*.dump`, `.backup`, `.sql`, `.tar`, `.zip` — database exports
- `.env.local` and `.env.prod` — local and production credentials/settings

Keep those files in private object storage, a secure backup system, or a
separate release bundle. See [data/exports/README.md](data/exports/README.md)
for the current PostgreSQL archive format.

## Quick start

1. Clone the repository and create a local environment file.

   ```powershell
   git clone <YOUR_REPOSITORY_URL>
   Set-Location LLM_superset
   Copy-Item .env.example .env.local
   ```

2. Edit `.env.local`. At minimum, replace these placeholder values with unique
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
   docker compose --env-file .env.local up -d postgres
   ```

4. Start the Docker services. By default this starts PostgreSQL, Redis, Superset,
   and the Superset MCP server. The frontend and backend run natively below.

   ```powershell
   docker compose --env-file .env.local up -d
   docker compose --env-file .env.local ps
   ```

5. Set up the native frontend/backend environments once.

   ```powershell
   # Backend: create one virtual environment at the repository root
   $repo = (Get-Location).Path
   $env:UV_CACHE_DIR = Join-Path $repo ".uv-cache"
   $env:UV_PYTHON_INSTALL_DIR = Join-Path $repo ".uv-python"
   uv venv --python 3.12
   uv pip install --python .venv\Scripts\python.exe -r backend\requirements.txt

   # Frontend: install dependencies and save its browser URLs
   Set-Location frontend
   $env:npm_config_cache = Join-Path $repo ".npm-cache"
   Copy-Item local.env.example .env.local
   npm ci
   ```

   The backend reads the repository `.env.local` automatically. Its `DATABASE_URL`,
   `SUPERSET_URL`, and `SUPERSET_MCP_INTERNAL_URL` use host ports; Compose
   overrides them with Docker service URLs for the optional containerized app.
   The frontend reads `frontend/.env.local` automatically.

6. Each time you start the project, open two PowerShell terminals.

   **Backend terminal:**

   ```powershell
   Set-Location backend
   & ..\.venv\Scripts\Activate.ps1
   uvicorn app.main:app --host 127.0.0.1 --port 48123 --reload
   ```

   **Frontend terminal:**

   ```powershell
   Set-Location frontend
   npm run dev
   ```

   The backend terminal activates the already-created root `.venv`, then runs
   `uvicorn` from the backend directory. The backend reads the repository `.env.local`
   automatically; no environment variables need to be re-entered at startup.
   Run `uv pip install --python ..\.venv\Scripts\python.exe -r requirements.txt`
   or `npm ci` again only after changing that app's dependencies.

7. Initialize the Superset dataset and demo dashboard after Superset is
   healthy.

   ```powershell
   python superset/scripts/setup_nyc_taxi_demo.py
   ```

   To create the Power BI-style dashboard from the reference images, run the
   reusable setup script. It keeps seven shared KPI cards above the **Trips &
   Revenue** and **Trip Patterns** tabs, with Vendor Name and Day Of Week
   filters in a vertical panel at the left. Tabs appear before the charts, and
   each tab starts with the same KPI row. The second tab includes six charts for
   weekday trips, time-of-day trips, pickup/dropoff boroughs, average daily
   trips by weekday, and daily trends split into time-of-day groups. The time
   groups are Early Morning (05:00–06:59), Morning (07:00–11:59), Afternoon
   (12:00–16:59), Evening (17:00–20:59), and Night (all other hours).

   The script uses the source data's two latest years by default (or the years
   available in the dataset if fewer than two are present):

   ```powershell
   python superset/scripts/setup_nyc_taxi_analytics.py --env-file .env.local
   ```

   For another Superset instance, point the same script to it and choose that
   environment's credentials file:

   ```powershell
   python superset/scripts/setup_nyc_taxi_analytics.py --base-url https://superset.example.com --env-file .env.prod --years 2017,2018
   ```

The script is safe to re-run: it updates only its own virtual dataset,
charts, and dashboard named **NYC Taxi Trips Analysis**, then enables embedding
for the configured `FRONTEND_URL` / `FRONTEND_ORIGINS`. It also applies the
branded background from `superset/assets/superset-dashboard-background.png`.

Local URLs:

| Service | URL |
| --- | --- |
| Application | http://localhost:43117 |
| API docs | http://localhost:48123/docs |
| Superset | http://localhost:58088 |

To run the frontend and backend in Docker instead, opt in with
`docker compose --env-file .env.local --profile app-containers up -d --build`.

On Windows, enable **Start Docker Desktop when you sign in**. The infrastructure
containers use Docker's `unless-stopped` restart policy, so they start with the
Docker Engine. Avoid `docker compose --env-file .env.local down` if you want those containers to be
there on the next Docker start; `down` removes them.

## Load analytics data

Choose one method. Do this while only PostgreSQL is running for a clean first
deployment.

### Option A — restore a PostgreSQL archive (recommended)

Copy the private archive, such as `ai_bi_raw_20260924.dump`, into
`data/exports/`. It is a PostgreSQL custom archive and is already compressed.
Do not unzip it.

```powershell
docker compose --env-file .env.local cp data/exports/ai_bi_raw_20260924.dump postgres:/tmp/ai_bi_raw.dump
docker compose --env-file .env.local exec -T postgres pg_restore -U ai_bi_user -d ai_bi --no-owner --no-privileges --clean --if-exists /tmp/ai_bi_raw.dump
```

`--clean --if-exists` replaces objects in the `raw` schema; omit those flags
when restoring into an empty database. Replace `ai_bi_user` and `ai_bi` only
if you changed `POSTGRES_USER` or `APP_DB_NAME` in `.env.local`. Verify the import:

```powershell
docker compose --env-file .env.local exec -T postgres psql -U ai_bi_user -d ai_bi -c "SELECT COUNT(*) FROM raw.yellow_taxi_trips;"
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
docker compose --env-file .env.local --profile tools run --rm data-loader
```

Set `DEMO_MAX_ROWS_PER_SOURCE=0` in `.env.local` only if a full source import is
intended. The default limits each input file to 10,000 rows for the demo.

## Operations

```powershell
# Service status and logs
docker compose --env-file .env.local ps
docker compose --env-file .env.local logs -f backend
docker compose --env-file .env.local logs -f frontend
docker compose --env-file .env.local logs -f superset

# Health checks
Invoke-WebRequest http://localhost:48123/health
Invoke-WebRequest http://localhost:48123/health/db

# Stop services but preserve database volumes
docker compose --env-file .env.local down
```

`docker compose --env-file .env.local down -v` deletes PostgreSQL, Redis, Superset, and frontend
volumes. Use it only when you intend to remove all local persisted state.

## Server deployment

Keep local settings in `.env.local` and production settings in `.env.prod`.
The production overlay publishes one gateway on TCP port `55200`:

```dotenv
APP_ENV=production
FRONTEND_URL=http://18.143.137.242:55200
FRONTEND_ORIGINS=http://18.143.137.242:55200
NEXT_PUBLIC_API_URL=http://18.143.137.242:55200
NEXT_PUBLIC_SUPERSET_URL=http://18.143.137.242:55200/superset
SUPERSET_PUBLIC_URL=http://18.143.137.242:55200/superset
SUPERSET_APP_ROOT=/superset
ENABLE_PROXY_FIX=true
```

The CI/CD workflow reads `.env.prod` on the VM. Full deployment steps and
security notes are in [docs/deployment.md](docs/deployment.md).

## Security notes

- Never commit `.env.local`, `.env.prod`, database dumps, raw Parquet files, or exported tokens.
- Set distinct, strong Superset and PostgreSQL secrets for every environment.
- The app has no end-user authentication yet. Do not expose it publicly until
  authentication, authorization, and row-level security are configured.
- Do not expose the MCP port (`55008`) outside localhost.

## Further documentation

- [Deployment guide](docs/deployment.md)
- [CI/CD setup](docs/ci-cd.md)
- [Data export and restore guide](data/exports/README.md)
- [Superset dashboard guide](docs/superset-nyc-taxi-dashboard.md)
- [Gemini and Superset MCP guide](docs/superset-mcp-gemini.md)
