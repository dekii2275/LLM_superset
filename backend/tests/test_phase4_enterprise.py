"""Isolated unit and endpoint tests for Phase 4: Enterprise Standardization.
Covers:
1. Simple Auth (Password hashing, JWT generation/validation, Login, Me, Users list).
2. Dynamic RLS (User RLS resolution, SQL Rewriter injection into WHERE clause).
3. Semantic Cache (Normalization, Exact Match, Similarity Match, Invalidation).
4. Anomaly Alerts (Alert retrieval, unread counter, mark as read).
"""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.anomaly_service import AnomalyService
from app.services.auth_service import (
    AuthService,
    create_jwt_token,
    decode_jwt_token,
    hash_password,
    verify_password,
)
from app.services.cache_service import CacheService, compute_similarity, normalize_text
from app.services.rls_service import RLSService


class Phase4EnterpriseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    @staticmethod
    def _user(username: str = "admin") -> dict:
        manager = username != "admin"
        return {
            "id": 2 if manager else 1,
            "username": username,
            "display_name": username,
            "role": "manager" if manager else "admin",
            "is_active": True,
            "rls_rules": (
                [
                    {
                        "dataset_id": 1,
                        "filter_clause": "pickup_borough = 'Manhattan'",
                        "description": "Manhattan only",
                    }
                ]
                if manager
                else []
            ),
            "token": create_jwt_token({"sub": 2 if manager else 1}),
        }

    # =========================================================================
    # 1. Auth & Token Tests
    # =========================================================================
    def test_password_hashing_and_verification(self) -> None:
        plain = "secret_password_123"
        hashed = hash_password(plain)
        self.assertTrue(verify_password(plain, hashed))
        self.assertFalse(verify_password("wrong_password", hashed))

    def test_jwt_token_flow(self) -> None:
        payload = {"sub": 999, "username": "test_user", "role": "manager"}
        token = create_jwt_token(payload, expires_in_seconds=3600)
        decoded = decode_jwt_token(token)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded["sub"], 999)
        self.assertEqual(decoded["username"], "test_user")

        # Invalid token signature
        tampered = token[:-4] + "abcd"
        self.assertIsNone(decode_jwt_token(tampered))

    def test_login_success_and_failure(self) -> None:
        def authenticate(username: str, password: str) -> dict | None:
            if (username, password) == ("admin", "admin123"):
                return self._user()
            if (username, password) == ("user_manhattan", "pass123"):
                return self._user("user_manhattan")
            return None

        with patch.object(AuthService, "authenticate", side_effect=authenticate):
            res = self.client.post(
                "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertIn("token", data)
            self.assertEqual(data["user"]["username"], "admin")
            self.assertEqual(data["user"]["role"], "admin")

            res_m = self.client.post(
                "/api/v1/auth/login", json={"username": "user_manhattan", "password": "pass123"}
            )
            self.assertEqual(res_m.status_code, 200)
            data_m = res_m.json()
            self.assertEqual(data_m["user"]["role"], "manager")
            self.assertTrue(data_m["user"]["rls_rules"])

            bad_res = self.client.post(
                "/api/v1/auth/login", json={"username": "admin", "password": "wrongpassword"}
            )
            self.assertEqual(bad_res.status_code, 401)

    def test_get_me_endpoint(self) -> None:
        user = self._user()
        with patch.object(AuthService, "get_user_by_id", return_value=user):
            me_res = self.client.get(
                "/api/v1/auth/me", headers={"Authorization": f"Bearer {user['token']}"}
            )
            self.assertEqual(me_res.status_code, 200)
            self.assertEqual(me_res.json()["username"], "admin")

        # Unauthenticated me request
        anon_res = self.client.get("/api/v1/auth/me")
        self.assertEqual(anon_res.status_code, 401)

    def test_get_users_list(self) -> None:
        with patch.object(
            AuthService,
            "list_users",
            return_value=[self._user(), self._user("user_manhattan"), self._user("user_queens")],
        ):
            res = self.client.get("/api/v1/auth/users")
        self.assertEqual(res.status_code, 200)
        users = res.json()
        self.assertTrue(len(users) >= 3)
        usernames = [u["username"] for u in users]
        self.assertIn("admin", usernames)
        self.assertIn("user_manhattan", usernames)

    # =========================================================================
    # 2. Dynamic RLS & SQL Rewriter Tests
    # =========================================================================
    def test_rls_filter_resolution(self) -> None:
        admin_user = {"id": 1, "username": "admin", "role": "admin"}
        # Admin has no filter
        self.assertIsNone(RLSService.get_filter_for_user(admin_user, dataset_id=1))

        # user_manhattan on dataset 1
        manhattan_user = {
            "id": 2,
            "username": "user_manhattan",
            "role": "manager",
            "rls_rules": [{"dataset_id": 1, "filter_clause": "pickup_borough = 'Manhattan'"}],
        }
        filt = RLSService.get_filter_for_user(manhattan_user, dataset_id=1)
        self.assertIsNotNone(filt)
        self.assertEqual(filt["filter_clause"], "pickup_borough = 'Manhattan'")

    def test_sql_rewriter_no_where(self) -> None:
        sql = "SELECT payment_type_name, SUM(total_amount) FROM raw.nyc_taxi_analysis GROUP BY 1;"
        filter_clause = "pickup_borough = 'Manhattan'"
        rewritten = RLSService.rewrite_sql(sql, filter_clause)

        self.assertIn("WHERE (pickup_borough = 'Manhattan')", rewritten)
        self.assertIn("GROUP BY 1", rewritten)
        self.assertTrue(rewritten.endswith(";"))

    def test_sql_rewriter_with_existing_where(self) -> None:
        sql = "SELECT * FROM raw.nyc_taxi_analysis WHERE total_amount > 20 ORDER BY total_amount DESC LIMIT 10;"
        filter_clause = "pickup_borough = 'Manhattan'"
        rewritten = RLSService.rewrite_sql(sql, filter_clause)

        self.assertIn("WHERE (total_amount > 20) AND (pickup_borough = 'Manhattan')", rewritten)
        self.assertIn("ORDER BY total_amount DESC", rewritten)
        self.assertIn("LIMIT 10", rewritten)

    def test_sql_rewriter_empty_filter_leaves_sql_untouched(self) -> None:
        sql = "SELECT COUNT(*) FROM raw.nyc_taxi_analysis;"
        self.assertEqual(RLSService.rewrite_sql(sql, None), sql)
        self.assertEqual(RLSService.rewrite_sql(sql, ""), sql)

    # =========================================================================
    # 3. Semantic Cache Tests
    # =========================================================================
    def test_normalize_text(self) -> None:
        raw_q = "  Doanh thu tháng 5 là bao nhiêu??? "
        norm = normalize_text(raw_q)
        self.assertEqual(norm, "doanh thu thang 5 la bao nhieu")

    def test_similarity_metric(self) -> None:
        q1 = normalize_text("Doanh thu tháng 5 là bao nhiêu?")
        q2 = normalize_text("Cho tôi xem doanh thu tháng 5 là bao nhiêu")
        score = compute_similarity(q1, q2)
        self.assertGreater(score, 0.70)

    def test_cache_exact_and_semantic_lookup(self) -> None:
        # Use isolated in-memory stores, never the configured Redis instance.
        cache = CacheService.__new__(CacheService)
        cache.redis_client = None

        sample_resp = {
            "answer": "Doanh thu là 1,000,000 USD",
            "query": {"sql": "SELECT 1;", "row_count": 1, "columns": ["x"], "rows": [{"x": 1}]},
        }

        with (
            patch("app.services.cache_service._IN_MEMORY_CACHE", {}),
            patch("app.services.cache_service._IN_MEMORY_QUESTIONS", {}),
        ):
            self._assert_cache_isolation(cache, sample_resp)

    def _assert_cache_isolation(self, cache: CacheService, sample_resp: dict) -> None:
        cache.set(
            question="Tổng doanh thu tháng 5",
            dataset_id=1,
            rls_filter="pickup_borough = 'Manhattan'",
            response_payload=sample_resp,
        )

        # 1. Exact match lookup
        exact_hit = cache.get(
            question="tổng doanh thu tháng 5",
            dataset_id=1,
            rls_filter="pickup_borough = 'Manhattan'",
        )
        self.assertIsNotNone(exact_hit)
        self.assertTrue(exact_hit["cache_hit"])
        self.assertEqual(exact_hit["cache_type"], "exact")

        # 2. Semantic lookup with slight difference in words
        semantic_hit = cache.get(
            question="cho xem tổng doanh thu tháng 5",
            dataset_id=1,
            rls_filter="pickup_borough = 'Manhattan'",
            similarity_threshold=0.60,
        )
        self.assertIsNotNone(semantic_hit)
        self.assertTrue(semantic_hit["cache_hit"])

        # 3. Different RLS key should miss (prevents cross-user cache leakage!)
        miss = cache.get(
            question="tổng doanh thu tháng 5",
            dataset_id=1,
            rls_filter="pickup_borough = 'Queens'",
        )
        self.assertIsNone(miss)

    def test_cache_clear_endpoint(self) -> None:
        with patch("app.api.ai.cache_service.clear") as clear:
            res = self.client.post("/api/v1/ai/cache/clear")
            clear.assert_called_once()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "success")

    # =========================================================================
    # 4. Anomaly Alerts Tests
    # =========================================================================
    def test_alerts_endpoints(self) -> None:
        alert = {
            "id": 1,
            "dataset_id": 1,
            "alert_type": "anomaly",
            "severity": "warning",
            "title": "Demo alert",
            "message": "Sample",
            "is_read": False,
        }

        def mark_read(_alert_id: int) -> bool:
            alert["is_read"] = True
            return True

        with (
            patch.object(AnomalyService, "get_alerts", side_effect=lambda limit=20: [dict(alert)]),
            patch.object(AnomalyService, "mark_as_read", side_effect=mark_read),
            patch.object(AnomalyService, "mark_all_as_read", side_effect=lambda: mark_read(1)),
        ):
            res = self.client.get("/api/v1/alerts")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["unread_count"], 1)

            read_res = self.client.post("/api/v1/alerts/1/read")
            self.assertEqual(read_res.json()["status"], "success")

            all_read_res = self.client.post("/api/v1/alerts/read-all")
            self.assertEqual(all_read_res.json()["status"], "success")
            self.assertEqual(self.client.get("/api/v1/alerts").json()["unread_count"], 0)


if __name__ == "__main__":
    unittest.main()
