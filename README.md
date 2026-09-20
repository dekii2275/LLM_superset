# AI BI Assistant

Docker Compose skeleton for an AI BI Assistant with a Next.js frontend, FastAPI backend, PostgreSQL, Apache Superset, and Redis.

## Architecture

```text
Browser
  ├── Next.js frontend
  │     └── FastAPI backend
  │             └── PostgreSQL (ai_bi)
  └── Apache Superset
        ├── PostgreSQL (superset metadata)
        └── Redis (cache)
```

This phase creates infrastructure only. There is no LLM or NL2SQL integration, and no business schema, seed data, dataset, chart, or dashboard. Database `ai_bi` is intentionally empty so a real dataset can be imported later.

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
cp .env.example .env
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
- The frontend status cards periodically check FastAPI, PostgreSQL, and Superset.
- PostgreSQL uses `pg_isready`; Redis uses `redis-cli ping`.

Check the API from a terminal:

```bash
curl http://localhost:48123/health
curl http://localhost:48123/health/db
```

## Useful commands

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f superset
docker compose logs -f postgres
docker compose down
```

`docker compose down` removes containers and the Compose network but preserves named volumes and their database data. `docker compose down -v` also deletes persistent volumes, including PostgreSQL databases, Redis data, Superset home data, and frontend dependency caches.

PostgreSQL's initialization SQL runs only when `postgres_data` is empty. It creates the `superset` database alongside the initial `ai_bi` database. The `ai_bi` database contains no business tables or sample data.
