# CI/CD setup

`ci.yml` checks repository artifacts, Python lint/formatting, backend tests,
frontend formatting/types/tests/build, and Compose templates on pull requests
to `main` and pushes to `main`. It also supports manual runs. After a successful
CI run from a push to `main`, `cd.yml` publishes commit-tagged images to GHCR
when `PUBLISH_ENABLED=true`. It deploys them to the Ubuntu server over SSH
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
FRONTEND_URL=http://<server-ip>:55200
FRONTEND_ORIGINS=http://<server-ip>:55200
SUPERSET_PUBLIC_URL=http://<server-ip>:55200/superset
SUPERSET_APP_ROOT=/superset
ENABLE_PROXY_FIX=true
NEXT_PUBLIC_API_URL=http://<server-ip>:55200
NEXT_PUBLIC_SUPERSET_URL=http://<server-ip>:55200/superset
GHCR_NAMESPACE=<lowercase-github-owner>
JWT_SECRET_KEY=<unique-random-value-of-at-least-32-characters>
```

The frontend URLs are baked into the GHCR image during its build. The CD
workflow defaults them to localhost for a local demonstration. Set the GitHub
variables to your actual server URLs before publishing. Port `55200/TCP` is the only public port for
this project: the gateway routes `/` to the frontend, `/api/` to the backend,
and `/superset/` to Superset. The database, Redis, and MCP ports stay private.
If you change the IP, update the GitHub repository variables
`NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_SUPERSET_URL`, then push a new commit.

This IP-only endpoint uses plain HTTP and the app has demo authentication with
known demo passwords and some anonymous APIs. Replace the demo login, audit
authorization, and configure TLS before exposing private data.

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
printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u <github-user> --password-stdin
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
server deployment stays disabled. Set `PUBLISH_ENABLED=true` to enable image
publishing; both publishing and deployment are disabled on a new repository.

Set `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_SUPERSET_URL` to the public server
URLs. Images default to the lowercase repository owner; override
`GHCR_NAMESPACE` only when publishing to another authorized owner, and set the
same value in the server's `.env.prod`.

Verify the server host-key fingerprint from a trusted connection before saving
the host-key line as `DEPLOY_KNOWN_HOSTS`. This lets the workflow keep SSH host
verification enabled.

## Deploy and access

With publishing enabled, merge or push a commit to `main`. After CI passes, CD builds and pushes these
commit-tagged images to GHCR:

- `ghcr.io/<namespace>/llm-superset-backend`
- `ghcr.io/<namespace>/llm-superset-frontend`
- `ghcr.io/<namespace>/llm-superset-superset`

When deployment is enabled, GitHub Actions connects over SSH, updates the Compose files, runs
`docker compose pull`, and restarts the services with `--no-build`. The VM does
not build the application images.

Open `http://<server-ip>:55200/`. For this project, only TCP port 55200 is
public; the gateway routes application paths to their internal containers.
The app uses demo authentication and this IP endpoint uses plain HTTP, so treat
it as a demo until authentication, authorization, and TLS are hardened.
