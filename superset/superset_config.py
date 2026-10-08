import os

from sqlalchemy.engine import URL
from superset.config import TALISMAN_CONFIG as DEFAULT_TALISMAN_CONFIG

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
FEATURE_FLAGS = {
    "EMBEDDED_SUPERSET": True,
    "THUMBNAILS": True,
    "ENABLE_DASHBOARD_SCREENSHOT_ENDPOINTS": True,
    "PLAYWRIGHT_REPORTS_AND_THUMBNAILS": True,
}
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
frontend_origins = [
    origin.strip().rstrip("/")
    for origin in os.environ.get(
        "SUPERSET_EMBEDDED_ALLOWED_ORIGINS",
        "http://localhost:43117,http://127.0.0.1:43117",
    ).split(",")
    if origin.strip()
]

TALISMAN_CONFIG = {
    **DEFAULT_TALISMAN_CONFIG,
    "frame_options": None,
    "content_security_policy": {
        **DEFAULT_TALISMAN_CONFIG["content_security_policy"],
        "frame-ancestors": frontend_origins,
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


def _register_dashboard_chart_screenshot_api(_app):
    import base64

    from flask import g, request
    from flask_appbuilder import permission_name
    from flask_appbuilder.api import expose, protect, safe
    from superset import security_manager
    from superset.commands.dashboard.permalink.create import CreateDashboardPermalinkCommand
    from superset.dashboards.api import DashboardRestApi, with_dashboard
    from superset.utils.screenshots import DashboardScreenshot
    from superset.utils.urls import get_url_path
    from superset.utils.webdriver import (
        app as superset_app,
    )
    from superset.utils.webdriver import (
        machine_auth_provider_factory,
        sync_playwright,
    )

    @expose("/<id_or_slug>/chart_screenshots/", methods=("POST",))
    @protect()
    @safe
    @permission_name("read")
    @with_dashboard
    def chart_screenshots(self, dashboard):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return self.response_400(message="A JSON object is required.")

        chart_ids = payload.get("chart_ids")
        active_tabs = payload.get("activeTabs", [])
        data_mask = payload.get("dataMask", {})
        if (
            not isinstance(chart_ids, list)
            or not chart_ids
            or len(chart_ids) > 50
            or any(type(chart_id) is not int for chart_id in chart_ids)
            or len(set(chart_ids)) != len(chart_ids)
            or not isinstance(active_tabs, list)
            or any(not isinstance(tab, str) for tab in active_tabs)
            or not isinstance(data_mask, dict)
        ):
            return self.response_400(message="Invalid chart screenshot request.")

        dashboard_chart_ids = {chart.id for chart in dashboard.slices}
        if any(chart_id not in dashboard_chart_ids for chart_id in chart_ids):
            return self.response_400(message="A chart does not belong to this dashboard.")

        guest_token = payload.get("guest_token")
        if guest_token is not None:
            try:
                if not isinstance(guest_token, str) or not guest_token:
                    raise ValueError("Invalid guest token")
                claims = security_manager.parse_jwt_guest_token(guest_token)
                if claims.get("type") != "guest" or not isinstance(claims.get("rls_rules"), list):
                    raise ValueError("Invalid guest token claims")
                allowed_ids = {str(dashboard.id)} | {str(item.uuid) for item in dashboard.embedded}
                if not any(
                    resource.get("type") == "dashboard" and str(resource.get("id")) in allowed_ids
                    for resource in claims.get("resources", [])
                ):
                    raise ValueError("Guest token does not grant this dashboard")
            except Exception:
                return self.response_400(message="Invalid guest token for chart screenshots.")

        dashboard_state = {
            "dataMask": data_mask,
            "activeTabs": active_tabs,
            "anchor": payload.get("anchor", ""),
            "urlParams": payload.get("urlParams", []),
        }
        permalink_key = CreateDashboardPermalinkCommand(
            dashboard_id=str(dashboard.id),
            state=dashboard_state,
        ).run()
        dashboard_url = get_url_path("Superset.dashboard_permalink", key=permalink_key)

        screenshot = DashboardScreenshot(dashboard_url, dashboard.digest)
        driver = screenshot.driver()
        window_height, window_width = driver._window[1], driver._window[0]
        pixel_density = superset_app.config["WEBDRIVER_WINDOW"].get("pixel_density", 1)
        chart_images = {}
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=superset_app.config["WEBDRIVER_OPTION_ARGS"])
            try:
                context = browser.new_context(
                    bypass_csp=True,
                    viewport={"height": window_height, "width": window_width},
                    device_scale_factor=pixel_density,
                )
                context.set_default_timeout(
                    superset_app.config["SCREENSHOT_PLAYWRIGHT_DEFAULT_TIMEOUT"]
                )
                if guest_token:
                    # No service-account cookie: every page/chart request is evaluated
                    # by Superset under the caller's signed guest RLS policy.
                    context.set_extra_http_headers(
                        {
                            superset_app.config["GUEST_TOKEN_HEADER_NAME"]: guest_token,
                        }
                    )
                else:
                    machine_auth_provider_factory.instance.authenticate_browser_context(
                        context, g.user
                    )
                page = context.new_page()
                page.goto(
                    dashboard_url,
                    wait_until=superset_app.config["SCREENSHOT_PLAYWRIGHT_WAIT_EVENT"],
                )
                page.wait_for_timeout(superset_app.config["SCREENSHOT_SELENIUM_HEADSTART"] * 1000)

                for chart_id in chart_ids:
                    chart = page.locator(f'.chart-slice[data-test-chart-id="{chart_id}"]')
                    chart.wait_for(state="visible")
                    container = chart.locator(".chart-container").first
                    container.wait_for(state="visible")
                    chart.evaluate(
                        "element => { element.style.backgroundColor = '#fff'; "
                        "element.style.backgroundImage = 'none'; element.style.opacity = '1'; }"
                    )
                    container.evaluate(
                        "element => { element.style.backgroundColor = '#fff'; "
                        "element.style.backgroundImage = 'none'; element.style.opacity = '1'; }"
                    )
                    for loading in container.locator(".loading").all():
                        loading.wait_for(state="detached")
                    page.wait_for_timeout(
                        superset_app.config["SCREENSHOT_SELENIUM_ANIMATION_WAIT"] * 1000
                    )
                    chart_images[str(chart_id)] = base64.b64encode(
                        container.screenshot(type="png")
                    ).decode("ascii")
            finally:
                browser.close()

        return self.response(
            200,
            result={
                "chart_images": chart_images,
                "guest_rls_applied": bool(guest_token),
            },
        )

    DashboardRestApi.chart_screenshots = chart_screenshots
    DashboardRestApi.include_route_methods = set(DashboardRestApi.include_route_methods) | {
        "chart_screenshots"
    }
    DashboardRestApi.method_permission_name = {
        **DashboardRestApi.method_permission_name,
        "chart_screenshots": "read",
    }


FLASK_APP_MUTATOR = _register_dashboard_chart_screenshot_api

redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")


class CeleryConfig:
    broker_url = redis_url
    result_backend = redis_url
    imports = ("superset.sql_lab", "superset.tasks.thumbnails")
    worker_prefetch_multiplier = 1
    task_acks_late = True


CELERY_CONFIG = CeleryConfig
THUMBNAIL_CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_REDIS_URL": redis_url,
    "CACHE_DEFAULT_TIMEOUT": 604800,
    "CACHE_KEY_PREFIX": "superset_thumb__",
}
WEBDRIVER_BASEURL = f"http://superset:8088{application_root}/"

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
