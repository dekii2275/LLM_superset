#!/bin/sh
set -eu

: "${SUPERSET_ADMIN_USERNAME:?SUPERSET_ADMIN_USERNAME is required}"
: "${SUPERSET_ADMIN_PASSWORD:?SUPERSET_ADMIN_PASSWORD is required}"
: "${SUPERSET_ADMIN_EMAIL:?SUPERSET_ADMIN_EMAIL is required}"

echo "Applying Superset metadata migrations..."
superset db upgrade

if superset fab list-users | grep -Fq -- "username:$SUPERSET_ADMIN_USERNAME"; then
  echo "Superset administrator '$SUPERSET_ADMIN_USERNAME' already exists."
else
  echo "Creating Superset administrator '$SUPERSET_ADMIN_USERNAME'..."
  superset fab create-admin \
    --username "$SUPERSET_ADMIN_USERNAME" \
    --firstname AI \
    --lastname Admin \
    --email "$SUPERSET_ADMIN_EMAIL" \
    --password "$SUPERSET_ADMIN_PASSWORD"
fi

echo "Initializing Superset roles and permissions..."
superset init
echo "Superset initialization complete."
