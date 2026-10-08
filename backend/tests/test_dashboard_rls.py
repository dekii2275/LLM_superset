import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api import superset as api
from app.api.auth import get_current_user_required
from app.schemas.ai import DashboardReport, DashboardReportRequest
from app.services.dashboard_access_service import DashboardAccessService
from app.services.superset import SupersetClient, SupersetEmbedError

ADMIN = {"id": 1, "username": "admin", "role": "admin", "is_active": True, "rls_rules": []}


def manager(borough="Manhattan", dataset_id=2):
    return {
        "id": 2,
        "username": "user_" + borough.lower(),
        "role": "manager",
        "is_active": True,
        "rls_rules": [{"dataset_id": dataset_id, "filter_clause": f"pickup_borough = '{borough}'"}],
    }


def client_fixture():
    client = SupersetClient("http://superset", "service-account", "unused")
    chart = {
        "id": 5,
        "datasource_id": 2,
        "slice_name": "Trips",
        "viz_type": "big_number_total",
        "dashboards": [{"id": 7}],
        "params": json.dumps({"metric": "count"}),
        "query_context": json.dumps(
            {"datasource": {"id": 2, "type": "table"}, "queries": [{"metrics": ["count"]}]}
        ),
    }
    responses = {
        "/api/v1/dashboard/7": {"result": {"id": 7, "slug": "taxi"}},
        "/api/v1/dashboard/taxi": {"result": {"id": 7, "slug": "taxi"}},
        "/api/v1/dashboard/7/charts": {"result": [chart]},
        "/api/v1/chart/5": {"result": chart},
        "/api/v1/dataset/2": {"result": {"id": 2, "columns": [{"column_name": "pickup_borough"}]}},
        "/api/v1/dashboard/7/embedded": {"result": {"uuid": "embedded-7"}},
        "/api/v1/security/guest_token/": {"token": "scoped-token"},
        "/api/v1/chart/data": {"result": [{"data": [{"count": 10}], "colnames": ["count"]}]},
    }
    client.request = MagicMock(side_effect=lambda method, path, *args, **kwargs: responses[path])
    return client, chart, responses


class DashboardRLSTests(unittest.TestCase):
    def test_admin_guest_token_is_unrestricted_and_uses_admin_identity(self):
        client, _, _ = client_fixture()
        DashboardAccessService(client, ADMIN).guest_token(7)
        payload = client.request.call_args.args[2]
        self.assertEqual(payload["user"], {"username": "admin"})
        self.assertEqual(payload["rls"], [])

    def test_manager_guest_tokens_differ_by_borough(self):
        for borough in ("Manhattan", "Queens"):
            client, _, _ = client_fixture()
            DashboardAccessService(client, manager(borough)).guest_token(7)
            payload = client.request.call_args.args[2]
            self.assertEqual(payload["user"]["username"], "user_" + borough.lower())
            self.assertEqual(
                payload["rls"], [{"dataset": 2, "clause": f"(pickup_borough = '{borough}')"}]
            )

    def test_dataset_without_a_rule_is_denied(self):
        client, _, _ = client_fixture()
        with self.assertRaises(HTTPException) as raised:
            DashboardAccessService(client, manager(dataset_id=1)).guest_token(7)
        self.assertEqual(raised.exception.status_code, 403)
        self.assertFalse(
            any(
                call.args[1] == "/api/v1/security/guest_token/"
                for call in client.request.call_args_list
            )
        )

    def test_every_dataset_on_a_mixed_dashboard_requires_permission(self):
        client, _, responses = client_fixture()
        responses["/api/v1/dashboard/7/charts"]["result"].append({"id": 6, "datasource_id": 99})
        with self.assertRaises(HTTPException) as raised:
            DashboardAccessService(client, manager()).guest_token(7)
        self.assertEqual(raised.exception.status_code, 403)

    def test_raw_taxi_policy_uses_pickup_zone_id(self):
        client, _, responses = client_fixture()
        responses["/api/v1/dataset/1"] = {
            "result": {
                "schema": "raw",
                "table_name": "yellow_taxi_trips",
                "columns": [{"column_name": "pu_location_id"}],
            }
        }
        clause = DashboardAccessService(client, manager(dataset_id=1)).dataset_clause(1)
        self.assertIn("pu_location_id IN (SELECT location_id FROM raw.taxi_zone_lookup", clause)
        self.assertIn("borough = 'Manhattan'", clause)

    def test_incompatible_raw_dataset_is_denied(self):
        client, _, responses = client_fixture()
        responses["/api/v1/dataset/2"]["result"] = {"table_name": "sales", "columns": []}
        with self.assertRaises(HTTPException):
            DashboardAccessService(client, manager()).dataset_clause(2)

    def test_all_dashboard_endpoints_require_authentication(self):
        app = FastAPI()
        app.include_router(api.router)
        with patch.object(api, "get_client") as service, TestClient(app) as browser:
            for path in (
                "/embed-config",
                "/guest-token",
                "/dashboard/7/embed-config",
                "/dashboard/7/guest-token",
                "/charts",
            ):
                self.assertEqual(browser.get("/api/v1/superset" + path).status_code, 401)
            self.assertEqual(browser.post("/api/v1/superset/charts/5/explain").status_code, 401)
            self.assertEqual(browser.post("/api/v1/superset/report", json={}).status_code, 401)
        service.assert_not_called()

    def test_authenticated_guest_token_route_preserves_403(self):
        client, _, _ = client_fixture()
        app = FastAPI()
        app.include_router(api.router)
        app.dependency_overrides[get_current_user_required] = lambda: manager(dataset_id=99)
        with patch.object(api, "get_client", return_value=client), TestClient(app) as browser:
            for path in (
                "/dashboard/7/embed-config",
                "/dashboard/7/guest-token",
                "/charts?dashboard_id=7",
            ):
                self.assertEqual(browser.get("/api/v1/superset" + path).status_code, 403)

    def test_invalid_token_and_disabled_account_are_rejected(self):
        from app.services.auth_service import create_jwt_token

        app = FastAPI()
        app.include_router(api.router)
        with patch.object(api, "get_client") as service, TestClient(app) as browser:
            response = browser.get(
                "/api/v1/superset/guest-token", headers={"Authorization": "Bearer invalid-token"}
            )
            self.assertEqual(response.status_code, 401)
            token = create_jwt_token({"sub": 1})
            with patch(
                "app.api.auth.AuthService.get_user_by_id",
                return_value={**ADMIN, "is_active": False},
            ):
                response = browser.get(
                    "/api/v1/superset/guest-token", headers={"Authorization": "Bearer " + token}
                )
            self.assertEqual(response.status_code, 401)
        service.assert_not_called()

    def test_explanation_queries_superset_with_the_manager_guest_token(self):
        client, _, _ = client_fixture()
        with (
            patch.object(api, "get_client", return_value=client),
            patch.object(api.settings, "gemini_api_key", ""),
        ):
            result = asyncio.run(api.explain_superset_chart(5, manager()))
        self.assertEqual(result["chart_id"], 5)
        data_calls = [
            call for call in client.request.call_args_list if call.args[1] == "/api/v1/chart/data"
        ]
        self.assertEqual(data_calls[0].kwargs["guest_token"], "scoped-token")
        self.assertFalse(
            any(call.args[1].endswith("/data/") for call in client.request.call_args_list)
        )

    def test_report_uses_selected_dashboard_and_same_policy_for_data_and_images(self):
        client, _, _ = client_fixture()
        client.dashboard_chart_data = MagicMock(
            return_value={
                "dashboard_id": 7,
                "dashboard_title": "Taxi",
                "active_tabs": [],
                "active_tab_title": "",
                "data_mask": {},
                "applied_filters": [],
                "charts": [{"id": 5, "rows": [{"count": 10}]}],
            }
        )
        client.dashboard_chart_screenshots = MagicMock(return_value={5: b"png"})
        gemini = MagicMock()
        from unittest.mock import AsyncMock

        gemini.generate_dashboard_report = AsyncMock(
            return_value=DashboardReport(overview="Restricted report")
        )
        with (
            patch.object(api, "get_client", return_value=client),
            patch.object(api, "is_llm_enabled", return_value=True),
            patch.object(api.settings, "gemini_api_key", "test-key"),
            patch.object(api, "GeminiService", return_value=gemini),
        ):
            result = asyncio.run(
                api.create_dashboard_report(DashboardReportRequest(dashboard_id=7), manager())
            )
        self.assertEqual(client.dashboard_chart_data.call_args.args[0], "7")
        self.assertEqual(
            client.dashboard_chart_data.call_args.kwargs["guest_token"], "scoped-token"
        )
        self.assertEqual(
            client.dashboard_chart_screenshots.call_args.kwargs["guest_token"], "scoped-token"
        )
        self.assertIn("(pickup_borough = 'Manhattan')", result["applied_filters"])

    def test_old_superset_screenshot_endpoint_cannot_return_unrestricted_images(self):
        client, _, _ = client_fixture()
        client.request = MagicMock(return_value={"result": {"chart_images": {"5": "ignored"}}})
        with self.assertRaises(SupersetEmbedError):
            client.dashboard_chart_screenshots(7, [5], [], {}, guest_token="scoped-token")

    def test_guest_transport_does_not_send_admin_cookie_or_authorization(self):
        client = SupersetClient("http://superset", "service", "unused")
        client.access_token = "admin-access"
        client.csrf_token = "admin-csrf"
        client.opener = MagicMock()
        with patch("app.services.superset.build_opener") as fresh_opener:
            fresh_opener.return_value.open.return_value.__enter__.return_value.read.return_value = (
                b'{"result": []}'
            )
            client.request("POST", "/api/v1/chart/data", {}, guest_token="scoped-token")
        request = fresh_opener.return_value.open.call_args.args[0]
        self.assertEqual(request.get_header("X-guesttoken"), "scoped-token")
        self.assertIsNone(request.get_header("Authorization"))
        self.assertIsNone(request.get_header("X-csrftoken"))
        client.opener.open.assert_not_called()
