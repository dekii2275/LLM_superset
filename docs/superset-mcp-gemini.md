# Superset MCP and Gemini (local development)

## Architecture

```text
Next.js
  ↓
FastAPI
  ↓
Gemini API
  ↓
FastAPI MCP client
  ↓
Superset MCP
  ↓
Superset metadata and analytics database
  ↓
PostgreSQL
```

Gemini never connects directly to PostgreSQL and does not receive PostgreSQL
credentials. It selects a function from the small MCP discovery surface; FastAPI
validates and executes that MCP call on the Docker network. Superset remains the
authority for its datasets, charts, dashboards, and permissions.

## Local-only MCP configuration

`superset-mcp` is a separate process from the Superset web server, but uses the
same Superset image, `superset_config.py`, metadata database, and
`superset_home` volume. Its internal address is
`http://superset-mcp:5008/mcp`; the host-only mapping is
`http://localhost:55008/mcp`.

For this development phase, `MCP_AUTH_ENABLED=False` and
`MCP_DEV_USERNAME` selects the existing Superset administrator. **Do not expose
port 55008 outside the local machine or use this setting in production.** A
production deployment needs authenticated MCP access (for example JWT/OAuth),
network controls, and least-privilege Superset roles.

## Run and verify MCP before Gemini

```bash
docker compose --env-file .env.local up -d --build superset-mcp backend
docker compose --env-file .env.local ps
docker compose --env-file .env.local logs -f superset-mcp
```

The MCP protocol requires initialization before tool calls. The included Python
client performs the handshake and prints discovered tool names plus health,
instance information, and dataset/dashboard searches:

```bash
docker compose --env-file .env.local exec backend python scripts/test_superset_mcp.py
```

A protocol-level host test can be performed with a client that first sends an
`initialize` request. A bare `tools/list` JSON-RPC request may be rejected by
Streamable HTTP servers that require the MCP session handshake.

Superset tool-search is enabled by default. In that mode, `tools/list` normally
contains `health_check`, `get_instance_info`, `search_tools`, and `call_tool`.
Search for a dataset/dashboard first, then use `call_tool` with the discovered
read-only tool. The smoke script prints the returned search metadata so that the
NYC Yellow Taxi dataset and overview dashboard can be verified without assuming
their internal IDs.

## AI endpoints

Set `GEMINI_API_KEY` and an available `GEMINI_MODEL` in `.env.local`, then rebuild the
backend after the dependency change. The default is `gemini-3.6-flash`, matching
the current Gemini API recommendation returned for new keys; override it if your
project has access to a different supported model. The API starts without a key;
only chat is disabled until it is configured.

```bash
curl http://localhost:48123/api/v1/ai/health
curl -X POST http://localhost:48123/api/v1/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Superset hiện có những dataset nào?"}'
```

`/api/v1/ai/chat` explicitly orchestrates Gemini function calls rather than
letting the cloud service access the local MCP URL. It exposes only Superset's
discovery proxy tools (`health_check`, `get_instance_info`, `search_tools`, and
`call_tool`) and rejects name patterns for SQL or write-capable tools while
`AI_ALLOW_SUPERSET_WRITE=false`. Tool names, outcomes, and durations are logged;
keys, database passwords, and full sensitive payloads are not logged.

## Troubleshooting and gates

Do not proceed to Gemini validation until all MCP checks pass:

- `superset-mcp` is healthy and `/mcp` is reachable.
- The Python client initializes and lists tools.
- The search output includes the NYC Yellow Taxi dataset and dashboard.
- A discovered read-only dataset-details tool returns its columns/metrics.

If a dependency error mentions `fastmcp`, rebuild `superset-mcp`: the Superset
image installs the compatible range declared by Superset 6.1 (`>=3.1,<4`).
If `/api/v1/ai/health` says `mcp: unavailable`, check `superset-mcp` logs and
verify the backend is using the internal URL, not `localhost:55008`.
