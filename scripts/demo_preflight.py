"""Read-only readiness checks for the local NYC Taxi demo.

Uses only GET endpoints and never prints credentials or guest tokens.
Run with Python's standard library; no backend dependencies are required.
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def get(url: str, timeout: float) -> object:
    request = Request(url, headers={"Accept": "application/json,text/html"})
    with urlopen(request, timeout=timeout) as response:
        body = response.read(2_000_000)
        if response.status != 200:
            raise ValueError(f"HTTP {response.status}")
        if "json" in response.headers.get("Content-Type", ""):
            return json.loads(body)
        return body.decode("utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check live demo prerequisites without changing data"
    )
    parser.add_argument("--api", default="http://127.0.0.1:48123")
    parser.add_argument("--frontend", default="http://127.0.0.1:43117")
    parser.add_argument("--superset", default="http://127.0.0.1:59088")
    parser.add_argument("--dataset-id", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args()

    api = args.api.rstrip("/")
    frontend = args.frontend.rstrip("/")
    superset = args.superset.rstrip("/")
    failures: list[str] = []
    total = 0

    def check(label: str, url: str, validate) -> object | None:
        nonlocal total
        total += 1
        try:
            payload = get(url, args.timeout)
            detail = validate(payload)
            if detail is False:
                raise ValueError("unexpected or empty response")
            print(f"[OK]   {label}" + (f": {detail}" if isinstance(detail, str) else ""))
            return payload
        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            reason = f"HTTP {error.code}" if isinstance(error, HTTPError) else str(error)
            failures.append(label)
            print(f"[FAIL] {label}: {reason}")
            return None

    check("API", f"{api}/health", lambda x: isinstance(x, dict) and x.get("status") == "ok")
    check(
        "PostgreSQL",
        f"{api}/health/db",
        lambda x: isinstance(x, dict) and x.get("database") == "connected",
    )
    check(
        "Superset via API",
        f"{api}/health/superset",
        lambda x: isinstance(x, dict) and x.get("superset") == "connected",
    )
    check(
        "Superset directly", f"{superset}/health", lambda x: isinstance(x, str) and bool(x.strip())
    )

    check(
        "Gemini and MCP",
        f"{api}/api/v1/ai/health",
        lambda x: (
            isinstance(x, dict)
            and x.get("status") == "ok"
            and x.get("gemini_configured") is True
            and str(x.get("mcp", "")).startswith("connected")
        ),
    )
    check(
        "AI enabled",
        f"{api}/api/v1/ai/settings",
        lambda x: isinstance(x, dict) and x.get("llm_enabled") is True,
    )

    datasets = check(
        "Registered dataset",
        f"{api}/api/v1/ai/datasets",
        lambda x: (
            isinstance(x, list)
            and any(isinstance(d, dict) and d.get("id") == args.dataset_id for d in x)
        ),
    )
    dataset = (
        next((d for d in datasets if isinstance(d, dict) and d.get("id") == args.dataset_id), None)
        if isinstance(datasets, list)
        else None
    )
    dashboard_id = dataset.get("default_dashboard_id") if dataset else None
    if dashboard_id:
        check(
            "Dashboard charts",
            f"{api}/api/v1/superset/charts?{urlencode({'dashboard_id': dashboard_id})}",
            lambda x: f"{len(x)} charts" if isinstance(x, list) and x else False,
        )
        check(
            "Dashboard embed config",
            f"{api}/api/v1/superset/dashboard/{dashboard_id}/embed-config",
            lambda x: (
                isinstance(x, dict) and bool(x.get("dashboard_id")) and bool(x.get("superset_url"))
            ),
        )
        check(
            "Dashboard guest token",
            f"{api}/api/v1/superset/dashboard/{dashboard_id}/guest-token",
            lambda x: isinstance(x, dict) and bool(x.get("token")),
        )
    else:
        for label in ("Dashboard charts", "Dashboard embed config", "Dashboard guest token"):
            total += 1
            failures.append(label)
            print(f"[FAIL] {label}: dataset has no default dashboard")

    check(
        "Frontend",
        frontend + "/",
        lambda x: isinstance(x, str) and "<html" in x.lower(),
    )

    print(f"\nResult: {total - len(failures)}/{total} checks passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
