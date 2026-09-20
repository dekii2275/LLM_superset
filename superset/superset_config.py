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
