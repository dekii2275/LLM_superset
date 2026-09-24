# CI/CD setup

`ci.yml` runs the backend tests and builds the frontend on pull requests to
`main`. After a successful CI run from a push to `main`, `cd.yml` publishes
commit-tagged images to GHCR. It deploys them to the Ubuntu server over SSH
when the repository variable `DEPLOY_ENABLED` is set to `true`.

CD identifies backend, frontend, and Superset images by their Git directory tree;
the frontend tag also includes its public build URLs. It builds only images whose
content tag does not exist in GHCR, using a separate `:buildcache` per service.
Unchanged images are reused and also tagged with the release commit and `latest`.
The frontend runtime contains the Next.js standalone output, static assets, and
public assets rather than the complete build environment.
The VM pulls those images and restarts Compose without building app
images there. CD copies only Compose/runtime support files; it does not copy the
application source. Keep `.env.local`, `.env.prod`, and database exports off GitHub.

Before SSH deployment, CD starts the exact published images in a disposable
Compose stack on the GitHub runner. It checks HTTP 200 through the gateway at
`/`, `/health`, `/health/db`, `/health/superset`, and `/superset/health`.
PostgreSQL and Redis use their native readiness checks; MCP is not exposed
through the gateway. If a check fails, the workflow stops before connecting to
the VM. The production deployment then waits for its own services to become
healthy as a second check.

SSH sends keepalive requests every 30 seconds. Each pull attempt is limited to
five minutes, with up to three attempts; application startup is limited to eight
minutes. CD recreates the gateway after application startup to refresh Nginx's
upstream addresses, then checks the same five HTTP endpoints on the VM.
Services whose content tag and Compose configuration are unchanged retain their
running containers. Superset initialization may run again as a Compose dependency.

After a successful deployment, `~/ai-bi-assistant/.images.prod` records the
selected service tags. Preserve that mapping for manual operations:

```bash
docker compose --env-file .env.prod --env-file .images.prod \
  -f docker-compose.yml -f docker-compose.prod.yml up -d --no-build --wait
```

To refresh a base image or dependency, update the corresponding Dockerfile or
dependency lock/version so the service content tag changes.

## Prepare the server

Install Docker Engine and the Compose plugin (Compose v2.24.4 or newer), ensure
the `ubuntu` user can run Docker, then create the deployment directories:

```bash
mkdir -p ~/ai-bi-assistant
```

Create the server environment file `.env.prod` from `.env.example`, set unique production
secrets, and configure the public IP URLs:

```dotenv
FRONTEND_URL=http://18.143.137.242:55200
FRONTEND_ORIGINS=http://18.143.137.242:55200
SUPERSET_PUBLIC_URL=http://18.143.137.242:55200/superset
SUPERSET_APP_ROOT=/superset
ENABLE_PROXY_FIX=true
NEXT_PUBLIC_API_URL=http://18.143.137.242:55200
NEXT_PUBLIC_SUPERSET_URL=http://18.143.137.242:55200/superset
```

The frontend URLs are baked into the GHCR image during its build. The CD
workflow defaults them to this IP. Port `55200/TCP` is the only public port for
this project: the gateway routes `/` to the frontend, `/api/` to the backend,
and `/superset/` to Superset. The database, Redis, and MCP ports stay private.
If you change the IP, update the GitHub repository variables
`NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_SUPERSET_URL`, then push a new commit.

This IP-only endpoint uses plain HTTP and the app currently has no end-user
authentication. Treat it as a demo endpoint; do not send passwords or sensitive
data over it.

Copy `.env.prod` with the supplied SSH key and restrict its permissions:

```powershell
scp -i "<path-to-your-pem>" .env.prod ubuntu@<server-ip>:~/ai-bi-assistant/.env.prod
ssh -i "<path-to-your-pem>" ubuntu@<server-ip> "chmod 600 ~/ai-bi-assistant/.env.prod"
```

Restore the private PostgreSQL dump separately after the first deployment. It
is not part of the image deployment.

The images are private. Create a GitHub personal access token (classic) with
`read:packages` permission and log the VM into GHCR once:

```bash
read -rsp "GHCR read token: " GHCR_TOKEN
printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u dekii2275 --password-stdin
unset GHCR_TOKEN
chmod 600 ~/.docker/config.json
```

The token is kept in the VM user's Docker config so future deploys can pull the
private images. Keep that file private to the `ubuntu` user.

## Configure GitHub

In the repository, open **Settings → Secrets and variables → Actions** and add
these repository secrets:

| Secret | Value |
| --- | --- |
| `DEPLOY_HOST` | Server IP address |
| `DEPLOY_USER` | `ubuntu` |
| `DEPLOY_SSH_KEY` | Contents of the local PEM file; never commit or send it in chat |
| `DEPLOY_KNOWN_HOSTS` | Verified SSH host-key line for this server |

Add the repository variable `DEPLOY_ENABLED` with value `true` only after the
server has Docker Compose, GHCR read access, and its `.env.prod` file. Until then,
CI and image publishing still run but server deployment stays disabled.

Verify the server host-key fingerprint from a trusted connection before saving
the host-key line as `DEPLOY_KNOWN_HOSTS`. This lets the workflow keep SSH host
verification enabled.

## Deploy and access

Merge or push a commit to `main`. After CI passes, CD builds and pushes these
commit-tagged images to GHCR:

- `ghcr.io/dekii2275/llm-superset-backend`
- `ghcr.io/dekii2275/llm-superset-frontend`
- `ghcr.io/dekii2275/llm-superset-superset`

Then GitHub Actions connects over SSH, updates the Compose files, runs
`docker compose pull`, and restarts the services with `--no-build`. The VM does
not build the application images.

Open `http://18.143.137.242:55200/`. For this project, only TCP port 55200 is
public; the gateway routes application paths to their internal containers.
The app does not have end-user authentication and this IP endpoint uses plain
HTTP, so treat it as a demo and do not send credentials or sensitive data.
