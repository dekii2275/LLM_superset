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

echo "Granting all_datasource_access to Gamma role for embedded guest tokens..."
python -c "
from superset.app import create_app
app = create_app()
with app.app_context():
    from superset import security_manager
    gamma = security_manager.find_role('Gamma')
    pvm = security_manager.find_permission_view_menu('all_datasource_access', 'all_datasource_access')
    if gamma and pvm and pvm not in gamma.permissions:
        security_manager.add_permission_role(gamma, pvm)
        print('Granted all_datasource_access to Gamma role.')
"

echo "Superset initialization complete."
