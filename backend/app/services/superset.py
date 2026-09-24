"""Server-side Superset guest-token integration for the local demo."""

from __future__ import annotations

import http.cookiejar
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPCookieProcessor, Request, build_opener


class SupersetEmbedError(RuntimeError):
    """Raised when Superset cannot prepare an embedded dashboard."""


class SupersetClient:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.access_token: str | None = None
        self.csrf_token: str | None = None

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json", "Referer": f"{self.base_url}/"}
        if authenticated and self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and self.csrf_token:
            headers["X-CSRFToken"] = self.csrf_token

        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")

        request = Request(
            f"{self.base_url}{path if path.startswith('/') else '/' + path}",
            data=data,
            headers=headers,
            method=method.upper(),
        )
        try:
            with self.opener.open(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise SupersetEmbedError(
                f"Superset returned HTTP {error.code} while preparing the embedded dashboard."
            ) from error
        except (OSError, URLError) as error:
            raise SupersetEmbedError("Superset is unavailable.") from error

    def login(self) -> None:
        result = self.request(
            "POST",
            "/api/v1/security/login",
            {
                "username": self.username,
                "password": self.password,
                "provider": "db",
                "refresh": True,
            },
            authenticated=False,
        )
        self.access_token = result.get("access_token")
        if not self.access_token:
            raise SupersetEmbedError("Superset login did not return an access token.")
        self.csrf_token = self.request("GET", "/api/v1/security/csrf_token/").get("result")
        if not self.csrf_token:
            raise SupersetEmbedError("Superset did not return a CSRF token.")

    def embedded_dashboard_id(self, dashboard_slug: str) -> str:
        path = f"/api/v1/dashboard/{quote(dashboard_slug, safe='')}/embedded"
        result = self.request("GET", path).get("result", {})
        dashboard_id = result.get("uuid")
        if not dashboard_id:
            raise SupersetEmbedError(
                "The Superset dashboard has not been enabled for embedding. "
                "Run the dashboard setup script after restarting Superset."
            )
        return str(dashboard_id)

    def create_guest_token(self, dashboard_id: str) -> str:
        result = self.request(
            "POST",
            "/api/v1/security/guest_token/",
            {
                "user": {"username": "ai-bi-frontend-demo"},
                "resources": [{"type": "dashboard", "id": dashboard_id}],
                "rls": [],
            },
        )
        token = result.get("token")
        if not token:
            raise SupersetEmbedError("Superset did not return a guest token.")
        return str(token)
