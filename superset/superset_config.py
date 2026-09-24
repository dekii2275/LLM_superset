import os

from sqlalchemy.engine import URL

secret_key = os.environ["SUPERSET_SECRET_KEY"].strip()
placeholder_secrets = {
    "replace_with_a_unique_random_secret_at_least_32_characters",
    "change_this_to_a_long_random_secret",
}
if len(secret_key) < 32 or secret_key in placeholder_secrets:
    raise RuntimeError(
        "SUPERSET_SECRET_KEY must be a unique random value with at least 32 characters."
    )

SECRET_KEY = secret_key

application_root = os.environ.get("SUPERSET_APP_ROOT", "").strip().rstrip("/")
if application_root:
    APPLICATION_ROOT = application_root
ENABLE_PROXY_FIX = os.environ.get("ENABLE_PROXY_FIX", "false").lower() == "true"

# Enable the official embedded-dashboard flow.  The separate guest-token key
# should be supplied in production; the fallback keeps existing local installs
# working until that value is added to the environment file.
FEATURE_FLAGS = {"EMBEDDED_SUPERSET": True}
GUEST_TOKEN_JWT_SECRET = os.environ.get("SUPERSET_GUEST_TOKEN_JWT_SECRET", secret_key)
GUEST_TOKEN_JWT_EXP_SECONDS = 300
# Gamma is the read-only built-in role appropriate for this local dashboard
# demo. Replace it with a least-privilege EmbeddedViewer role in production.
GUEST_ROLE_NAME = "Gamma"

# Local-development MCP only. Do not expose this listener publicly or keep
# authentication disabled in production; use a JWT/OAuth MCP configuration.
MCP_AUTH_ENABLED = False
MCP_DEV_USERNAME = os.getenv("MCP_DEV_USERNAME", "admin")
MCP_SERVICE_HOST = "0.0.0.0"
MCP_SERVICE_PORT = 5008
# Superset defaults to SAMEORIGIN, which prevents the official embedded SDK
# from rendering a dashboard in this frontend on a different local port.
# Keep Superset's standard CSP and security headers, but allow the local
# Next.js frontend to host its embedded dashboard. Flask-Talisman would
# otherwise add X-Frame-Options: SAMEORIGIN; disabling only that legacy header
# lets the explicit CSP `frame-ancestors` allow-list control embedding.
from superset.config import TALISMAN_CONFIG as DEFAULT_TALISMAN_CONFIG

frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:43117").rstrip("/")

TALISMAN_CONFIG = {
    **DEFAULT_TALISMAN_CONFIG,
    "frame_options": None,
    "content_security_policy": {
        **DEFAULT_TALISMAN_CONFIG["content_security_policy"],
        "frame-ancestors": [frontend_url],
    },
}

SQLALCHEMY_DATABASE_URI = URL.create(
    "postgresql+psycopg2",
    username=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
    host="postgres",
    port=5432,
    database=os.environ.get("SUPERSET_DB_NAME", "superset"),
).render_as_string(hide_password=False)
SQLALCHEMY_TRACK_MODIFICATIONS = False

redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")

CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_REDIS_URL": redis_url,
    "CACHE_DEFAULT_TIMEOUT": 300,
}

FILTER_STATE_CACHE_CONFIG = {
    **CACHE_CONFIG,
    "CACHE_KEY_PREFIX": "superset_filter_state:",
}

EXPLORE_FORM_DATA_CACHE_CONFIG = {
    **CACHE_CONFIG,
    "CACHE_KEY_PREFIX": "superset_explore_form:",
}

DATA_CACHE_CONFIG = {
    **CACHE_CONFIG,
    "CACHE_KEY_PREFIX": "superset_data:",
}
