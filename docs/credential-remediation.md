# Remediate exposed credentials

The GitGuardian summary screenshot does not identify the two findings. Open
**Detected hardcoded secrets** in its PR comment and verify each file, line and
detector type. Do not paste credential values into chat or issues.

This change removes known app passwords from runtime source and the browser
bundle. The application reads `APP_ADMIN_PASSWORD` and `APP_MANAGER_PASSWORD`
from a private environment file when creating its initial users. CI/CD generates
new random disposable credentials on each run, masks them in Actions logs, and
stores smoke-test credentials only in the ignored `.env.smoke` file.

## Existing application accounts

Changing environment settings does not update passwords already stored in the
database. Choose new, unique values for `APP_ADMIN_PASSWORD` and
`APP_MANAGER_PASSWORD` in `.env.local` or on the server in `.env.prod`. Keep these
separate from `SUPERSET_ADMIN_PASSWORD`; never use `NEXT_PUBLIC_*` variables for
credentials.

After updating the code and private settings, explicitly rotate the four seeded
app accounts (`admin`, `user_manhattan`, `user_queens`, `user_asia`). For native
Windows development:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m scripts.rotate_app_passwords --apply
```

For a running containerized installation:

```bash
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml \
  up -d --no-build backend
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml \
  exec -T backend python -m scripts.rotate_app_passwords --apply
```

The script updates only password hashes for those named users; IDs, roles, RLS
rules, datasets and chat history are preserved. Rotate `JWT_SECRET_KEY` in the
same private environment and restart the backend to invalidate already-issued
tokens. Users then sign in with the new password. Use distinct credentials per
person before extending this demo authentication to real users.

## Confirm the reported incident

If GitGuardian identifies an actual API key, database credential or Superset
administrator password, revoke or rotate it at the affected service and update
private deployment settings. The app-user rotation script does not rotate those
other services. Disposable CI credentials are not production credentials.

Push this fix and inspect the new scan. A clean new scan does not revoke an old
credential or erase its previous commits. Resolve the old GitGuardian incident
after rotation and verification. Coordinate any history cleanup with repository
collaborators; do not force-push rewritten shared history without agreement.

The local repository check now flags common hardcoded credential assignments
in runtime source and workflows, in addition to recognized provider tokens. It
does not replace GitGuardian's detectors or verification of the two reported
findings.
