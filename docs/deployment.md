# Deploying AI BI Assistant

This guide deploys the repository on the Ubuntu VM using Docker Compose. The
production overlay provides a single public gateway on TCP port 55200 for
IP-only HTTP access.

## 1. Prepare the server

Install Git, Docker Engine, and the Docker Compose plugin. Clone the repository
and create an environment file that is never committed:

```bash
git clone <YOUR_REPOSITORY_URL> ai-bi-assistant
cd ai-bi-assistant
cp .env.example .env.prod
chmod 600 .env.prod
```

Generate unique values for all passwords and Superset secrets. Keep
`POSTGRES_PASSWORD` URL-safe because it is also used in `DATABASE_URL`. Set
`GEMINI_API_KEY` only on the server or in the deployment secret store.

## 2. Configure public URLs

For IP-only access through the single public gateway port:

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

The backend uses `FRONTEND_ORIGINS` for browser access and
`SUPERSET_PUBLIC_URL` when it returns Superset links. The production gateway
listens on `55200/TCP` and routes frontend, backend API, and Superset paths.
Ensure the cloud firewall permits only this project port from the Internet.
This IP-only configuration uses HTTP; use TLS and authentication before
handling sensitive data. Rebuild the frontend after changing `NEXT_PUBLIC_*`.

## 3. Restore the private data archive

Copy the PostgreSQL custom archive from secure storage to
`data/exports/ai_bi_raw_20260924.dump`. The archive is intentionally ignored
by Git.

Start only PostgreSQL and wait for it to become healthy:

```bash
docker compose --env-file .env.prod up -d postgres
docker compose --env-file .env.prod ps postgres
```

Copy and restore the archive. The command below replaces the existing `raw`
schema, so do not use it against production data that has not been backed up.

```bash
docker compose --env-file .env.prod cp data/exports/ai_bi_raw_20260924.dump postgres:/tmp/ai_bi_raw.dump
docker compose --env-file .env.prod exec -T postgres pg_restore -U ai_bi_user -d ai_bi \
  --no-owner --no-privileges --clean --if-exists /tmp/ai_bi_raw.dump
```

Replace `ai_bi_user` and `ai_bi` only if you changed `POSTGRES_USER` or
`APP_DB_NAME` in `.env.prod`.

Verify the restored trip count:

```bash
docker compose --env-file .env.prod exec -T postgres psql -U ai_bi_user -d ai_bi \
  -c "SELECT COUNT(*) FROM raw.yellow_taxi_trips;"
```

## 4. Start and initialize the application

```bash
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d --no-build
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml ps
```

After the `superset` service is healthy, create the database connection,
dataset, charts, and dashboard:

```bash
python3 superset/scripts/setup_nyc_taxi_demo.py
```

The setup script reads `.env.local` when present, otherwise `.env.prod`, and
uses the local Superset port. It is safe to rerun; it updates the named demo
assets.

## 5. Public gateway

The production Compose overlay starts the Nginx gateway on port `55200`. It
routes:

| Public host/path | Local upstream |
| --- | --- |
| `http://18.143.137.242:55200/` | Frontend container |
| `http://18.143.137.242:55200/api/` | Backend container |
| `http://18.143.137.242:55200/superset/` | Superset container |

Only the gateway port is public. Database, Redis, backend, Superset, and MCP
host ports remain private. Do not proxy the MCP endpoint.

## 6. Verify

```bash
curl --fail http://18.143.137.242:55200/health
curl --fail http://18.143.137.242:55200/superset/health
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml ps
```

Open the application at `http://18.143.137.242:55200/`, send a data question,
then open the embedded dashboard. If embedded Superset fails, confirm that
`FRONTEND_URL` matches the browser origin and `SUPERSET_PUBLIC_URL` ends in
`/superset`.

## Updating

For normal updates, merge or push to `main`; the CI/CD workflow publishes
commit-tagged images and deploys by pulling them. For a manual update, export
the desired image tag and run `docker compose --env-file .env.prod pull`
followed by `docker compose --env-file .env.prod up -d --no-build` with both
production Compose files. Back up PostgreSQL and the
`superset_home` Docker volume before changing the deployment.

Do not run `docker compose --env-file .env.prod down -v` on a deployed instance
unless you intend to delete all persisted PostgreSQL, Redis, and Superset data.
