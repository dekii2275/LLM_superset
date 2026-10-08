# Contributing

Use Python 3.12 and Node.js 22.21 (see `.nvmrc`). Install backend development
dependencies with `python -m pip install -r backend/requirements-dev.txt` in a
virtual environment, and frontend dependencies with `npm ci` in `frontend/`.
Copy the environment templates and supply local credentials as described in
[README.md](README.md).

## Check a change

From the repository root, with the Python virtual environment active:

```powershell
python scripts/check_repository.py
python -m ruff check .
python -m ruff format --check .
$env:PYTHONPATH = "backend"
$env:DATABASE_URL = "postgresql+psycopg://test:test@127.0.0.1:5432/ai_bi"
$env:GEMINI_API_KEY = "ci-placeholder-key"
$env:REDIS_URL = "redis://127.0.0.1:6379/15"
$env:JWT_SECRET_KEY = "test-only-jwt-key-with-at-least-32-characters"
python -m unittest discover -s backend/tests -v

Set-Location frontend
npm.cmd run format:check
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
```

The unit tests use mocks for application data and external services. Their test
URLs and keys override local settings. The Superset setup scripts and
`scripts/demo_preflight.py` need a running stack and are separate integration
checks. Stop `next dev` before building in the same directory.

To apply formatting, run `python -m ruff check . --fix` followed by
`python -m ruff format .` at the root, and `npm.cmd run format` in `frontend/`.
Use `npm` instead of `npm.cmd` on Linux/macOS. Keep UTF-8 and LF line endings;
the repository includes `.editorconfig` and `.gitattributes`.

Submit a focused pull request describing the changed behavior and the checks
you ran. Keep `.env` files, credentials, generated caches, database backups and
raw datasets out of commits. Keep `package-lock.json` updated when changing npm
dependencies.
