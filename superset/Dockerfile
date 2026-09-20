FROM apache/superset:6.1.0

USER root

# Add the PostgreSQL driver for the metadata store and Redis' Python client for
# the configured cache backend.
RUN uv pip install --python /app/.venv/bin/python \
    "psycopg2-binary>=2.9.9,<3" \
    "redis==5.2.1"

COPY --chown=superset:superset superset_config.py /app/superset_config.py
COPY init-superset.sh /app/init-superset.sh
RUN chmod 0555 /app/init-superset.sh

ENV SUPERSET_CONFIG_PATH=/app/superset_config.py

USER superset
