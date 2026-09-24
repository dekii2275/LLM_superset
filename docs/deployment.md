# Deploying AI BI Assistant

This guide deploys the repository after cloning it onto a server. It assumes
Docker Compose v2, a DNS name, and a TLS reverse proxy are available.

## 1. Prepare the server

Install Git, Docker Engine, and the Docker Compose plugin. Clone the repository
and create an environment file that is never committed:

```bash
git clone <YOUR_REPOSITORY_URL> ai-bi-assistant
cd ai-bi-assistant
cp .env.example .env
chmod 600 .env
```

Generate unique values for all passwords and Superset secrets. Keep
`POSTGRES_PASSWORD` URL-safe because it is also used in `DATABASE_URL`. Set
`GEMINI_API_KEY` only on the server or in the deployment secret store.

## 2. Configure public URLs

Example with separate application and Superset hostnames:

```dotenv
FRONTEND_URL=https://bi.example.com
FRONTEND_ORIGINS=https://bi.example.com
NEXT_PUBLIC_API_URL=https://bi.example.com
NEXT_PUBLIC_SUPERSET_URL=https://superset.example.com
SUPERSET_PUBLIC_URL=https://superset.example.com
```

The backend uses `FRONTEND_ORIGINS` for browser access and
`SUPERSET_PUBLIC_URL` when it returns Superset links. Rebuild the frontend
after changing `NEXT_PUBLIC_*` variables.

## 3. Restore the private data archive

Copy the PostgreSQL custom archive from secure storage to
`data/exports/ai_bi_raw_20260924.dump`. The archive is intentionally ignored
by Git.

Start only PostgreSQL and wait for it to become healthy:

```bash
docker compose up -d postgres
docker compose ps postgres
```

Copy and restore the archive. The command below replaces the existing `raw`
schema, so do not use it against production data that has not been backed up.

```bash
docker compose cp data/exports/ai_bi_raw_20260924.dump postgres:/tmp/ai_bi_raw.dump
docker compose exec -T postgres pg_restore -U ai_bi_user -d ai_bi \
  --no-owner --no-privileges --clean --if-exists /tmp/ai_bi_raw.dump
```

Replace `ai_bi_user` and `ai_bi` only if you changed `POSTGRES_USER` or
`APP_DB_NAME` in `.env`.

Verify the restored trip count:

```bash
docker compose exec -T postgres psql -U ai_bi_user -d ai_bi \
  -c "SELECT COUNT(*) FROM raw.yellow_taxi_trips;"
```

## 4. Start and initialize the application

```bash
docker compose up -d --build
docker compose ps
```

After the `superset` service is healthy, create the database connection,
dataset, charts, and dashboard:

```bash
python3 superset/scripts/setup_nyc_taxi_demo.py
```

The setup script uses the repository `.env` and the local Superset port. It is
safe to rerun; it updates the named demo assets.

## 5. Put a TLS reverse proxy in front

The Compose file intentionally exposes application ports only to localhost.
Configure a reverse proxy to send traffic as follows:

| Public host/path | Local upstream |
| --- | --- |
| `https://bi.example.com/` | `http://127.0.0.1:43117` |
| `https://bi.example.com/api/` | `http://127.0.0.1:48123/api/` |
| `https://superset.example.com/` | `http://127.0.0.1:58088` |

Forward the usual `Host`, `X-Forwarded-For`, and `X-Forwarded-Proto` headers.
Enable HTTPS before sharing the service. Do not proxy port `55008`: it is the
development MCP endpoint and must remain private.

## 6. Verify

```bash
curl --fail https://bi.example.com/api/health
curl --fail https://superset.example.com/health
docker compose ps
```

Open the application, send a data question, then open the embedded dashboard.
If embedded Superset fails, first confirm that `FRONTEND_URL` exactly matches
the browser origin and that `SUPERSET_PUBLIC_URL` is the public Superset URL.

## Updating

Before updating, back up PostgreSQL and the `superset_home` Docker volume.
Then pull, rebuild, and restart:

```bash
git pull --ff-only
docker compose up -d --build
docker compose ps
```

Do not run `docker compose down -v` on a deployed instance unless you intend
to delete all persisted PostgreSQL, Redis, and Superset data.
