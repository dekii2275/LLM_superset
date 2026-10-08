# Publish the source to GitHub

## Prepare the files

Run the checks in [CONTRIBUTING.md](../CONTRIBUTING.md), then review the files Git
will upload from the repository root:

```powershell
python scripts/check_repository.py
git status --short
git diff --check
git diff --stat
```

`.gitignore` excludes local environment files, dependency folders, build caches,
private keys, raw Parquet data, source ZIP downloads and database exports. The
small public Natural Earth CSV remains included with its
[source attribution](../data/natural_earth_populated_places_source.txt).
`.gitignore` does not remove files already committed: if credentials were ever
committed, rotate them and clean the Git history before publishing. The included
checker recognizes common token formats; review environment-specific settings
and use GitHub secret scanning as well.

## Upload

Create an empty GitHub repository, choose its visibility, then commit and push:

```powershell
git add .
git diff --cached --stat
git commit -m "chore: standardize repository for GitHub"
git remote -v
```

If `origin` already points to the intended repository, keep it. Otherwise set
the destination with one of these commands:

```powershell
# New remote
git remote add origin https://github.com/<owner>/<repository>.git

# Existing remote that needs a new destination
git remote set-url origin https://github.com/<owner>/<repository>.git
```

Push your current branch without rewriting existing remote history:

```powershell
git push -u origin HEAD
```

Open a pull request into `main` if your current branch is a development branch.
CI runs on pushes to `main` and pull requests targeting `main`; it can also be
started manually from Actions. It checks repository artifacts, Python lint and
formatting, backend tests, frontend formatting/types/tests/build, and Compose
templates.

## Optional container publishing and deployment

Uploading source only runs CI. Set `PUBLISH_ENABLED=true` in GitHub repository
variables to publish images after successful pushes to `main`. Set
`DEPLOY_ENABLED=true` only when the server and deployment secrets are ready.
Configure `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_SUPERSET_URL` for your server
before publishing images; their fallback values target a local demonstration.

Images use the lowercase repository owner by default. To use another owner, set
`GHCR_NAMESPACE` in repository variables and ensure the workflow has permission
to publish there. Set the same namespace in the server's `.env.prod`. See
[CI/CD setup](ci-cd.md) and [deployment](deployment.md).
