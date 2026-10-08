# AI BI Assistant

An analytics workspace for the NYC Yellow Taxi dataset. The app combines a
Next.js chat interface, FastAPI, PostgreSQL, Apache Superset, Redis, and
Gemini-assisted analysis.

## What it does

- Ask questions about the connected NYC Yellow Taxi data.
- Preview query results and charts in the chat.
- Create charts and dashboards in Superset after an explicit confirmation.
- Embed the live Superset dashboard in the application.
- Upload CSV/Parquet datasets and select the dataset used for analysis.
- Manage business glossary terms, verified metrics, and saved chat sessions.
- Export dashboard reports and view demo user/RLS and anomaly-alert flows.

The application is designed around the `ai_bi` PostgreSQL database and the
`raw.yellow_taxi_trips` table. Superset metadata is stored separately in the
`superset` database.

## Project structure

| Directory | Purpose |
| --- | --- |
| `backend/` | FastAPI routes, analytics services, and unit tests |
| `frontend/` | Next.js application and report-generation test |
| `database/` | PostgreSQL initialization and data import/profile tools |
| `superset/` | Superset image, configuration, and dashboard setup scripts |
| `deploy/` | Production Nginx gateway configuration |
| `scripts/` | Repository checks and live demo preflight |
| `data/` | Small public references; private inputs/exports are ignored |
| `docs/` | Deployment, integration, and feature documentation |

## Requirements

- Git
- Docker Engine or Docker Desktop with Docker Compose v2
- Node.js 22.21 with npm (see `.nvmrc`)
- Python 3.12 for the backend and setup scripts

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
   - `JWT_SECRET_KEY` (at least 32 characters; also required by Compose)
   - `APP_ADMIN_PASSWORD` and `APP_MANAGER_PASSWORD` (private app login bootstrap values)

   Keep the password in `DATABASE_URL` consistent with `POSTGRES_PASSWORD`.
   Generate signing keys with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

   Set `GEMINI_API_KEY` to enable the AI chat. The stack still starts without
   it, but `/api/v1/ai/chat` is unavailable.

3. Start PostgreSQL, then load data by one of the methods below.

   ```powershell
   docker compose --env-file .env.local up -d postgres
   ```

4. Start the Docker services. By default this starts PostgreSQL, Redis, Superset,
   its screenshot worker, and the Superset MCP server. The frontend and backend run natively below.

   ```powershell
   docker compose --env-file .env.local up -d
   docker compose --env-file .env.local ps
   ```

5. Set up the native frontend/backend environments once.

   ```powershell
   # Backend: create one virtual environment at the repository root
   py -3.12 -m venv .venv
   .venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt

   # Frontend: install dependencies and save its browser URLs
   Set-Location frontend
   Copy-Item local.env.example .env.local
   npm.cmd ci
   ```

   The backend reads the repository `.env.local` automatically. Its `DATABASE_URL`,
   `SUPERSET_URL`, and `SUPERSET_MCP_INTERNAL_URL` use host ports; Compose
   overrides them with Docker service URLs for the optional containerized app.
   The frontend reads `frontend/.env.local` automatically.

6. Each time you start the project, open two PowerShell terminals.

   **Backend terminal:**

   ```powershell
   Set-Location backend
   ..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 48123 --reload
   ```

   **Frontend terminal:**

   ```powershell
   Set-Location frontend
   npm.cmd run dev
   ```

   The backend uses the already-created root `.venv` and runs
   `uvicorn` from the backend directory. The backend reads the repository `.env.local`
   automatically; no environment variables need to be re-entered at startup.
   Reinstall Python dependencies or run `npm.cmd ci` after changing that app's
   dependency files. On Linux/macOS, use `python3.12 -m venv .venv`,
   `.venv/bin/python`, and `npm` instead of the Windows commands.

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
| Superset | http://localhost:59088 |

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

Before a live walkthrough, run `python scripts/demo_preflight.py` and follow
the [demo and acceptance checklist](docs/demo-acceptance.md). The preflight
checks the running services, selected dataset, dashboard embed setup, and
frontend route without changing application data.

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
FRONTEND_URL=http://<server-ip>:55200
FRONTEND_ORIGINS=http://<server-ip>:55200
NEXT_PUBLIC_API_URL=http://<server-ip>:55200
NEXT_PUBLIC_SUPERSET_URL=http://<server-ip>:55200/superset
SUPERSET_PUBLIC_URL=http://<server-ip>:55200/superset
SUPERSET_APP_ROOT=/superset
ENABLE_PROXY_FIX=true
```

Set `GHCR_NAMESPACE` in `.env.prod` to the lowercase owner of the published
container images, and supply a unique `JWT_SECRET_KEY` of at least 32 characters.
Image publishing requires `PUBLISH_ENABLED=true` in GitHub repository variables;
server deployment additionally requires `DEPLOY_ENABLED=true`.
The CI/CD workflow reads `.env.prod` on the VM. Full deployment steps and
security notes are in [docs/deployment.md](docs/deployment.md).

## Security notes

- Never commit `.env.local`, `.env.prod`, database dumps, raw Parquet files, or exported tokens.
- Set distinct, strong Superset and PostgreSQL secrets for every environment.
- Authentication and RLS currently demonstrate local user flows. Startup seeds
  app accounts only when `APP_ADMIN_PASSWORD` and `APP_MANAGER_PASSWORD` are set
  in the private environment file. Login and account switching require password
  entry; passwords are never embedded in the browser bundle. Some API routes permit anonymous
  access. Replace this demo authentication and audit endpoint authorization
  before using private data or making the service publicly accessible.
- Production requires an explicit `JWT_SECRET_KEY`; development without a key
  generates a process-local key, so tokens expire across process restarts.
- Do not expose the MCP port (`55008`) outside localhost.
- For an existing installation with old demo passwords, follow the
  [credential remediation guide](docs/credential-remediation.md). Updating
  bootstrap settings alone does not rotate accounts already stored in PostgreSQL.

## Further documentation

- [GitHub publishing guide](docs/github-publishing.md)
- [Development and checks](CONTRIBUTING.md)
- [Deployment guide](docs/deployment.md)
- [CI/CD setup](docs/ci-cd.md)
- [Data export and restore guide](data/exports/README.md)
- [Superset dashboard guide](docs/superset-nyc-taxi-dashboard.md)
- [Gemini and Superset MCP guide](docs/superset-mcp-gemini.md)
