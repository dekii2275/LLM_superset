import secrets
import unittest
from unittest.mock import MagicMock, patch

from pydantic import SecretStr

from app.services.auth_service import AuthService, verify_password


class AuthBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.admin_password = secrets.token_urlsafe(24)
        self.manager_password = secrets.token_urlsafe(24)
        patcher = patch.multiple(
            "app.services.auth_service.settings",
            app_admin_password=SecretStr(self.admin_password),
            app_manager_password=SecretStr(self.manager_password),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_missing_password_skips_bootstrap_without_database_access(self) -> None:
        with (
            patch("app.services.auth_service.settings.app_admin_password", None),
            patch("app.services.auth_service.engine") as engine,
        ):
            AuthService.seed_default_users()
        engine.begin.assert_not_called()

    def test_seed_uses_private_passwords_and_independent_salts(self) -> None:
        with patch("app.services.auth_service.engine") as engine:
            connection = engine.begin.return_value.__enter__.return_value
            empty_count = MagicMock()
            empty_count.scalar.return_value = 0
            users = MagicMock()
            users.fetchall.return_value = []
            connection.execute.side_effect = [empty_count, MagicMock(), users]
            AuthService.seed_default_users()
        hashes = connection.execute.call_args_list[1].args[1]
        self.assertTrue(verify_password(self.admin_password, hashes["admin_hash"]))
        for key in ("manhattan_hash", "queens_hash", "asia_hash"):
            self.assertTrue(verify_password(self.manager_password, hashes[key]))
            self.assertFalse(verify_password(self.admin_password, hashes[key]))
        self.assertEqual(len(set(hashes.values())), 4)

    def test_rotation_updates_only_named_accounts_and_hashes_passwords(self) -> None:
        with patch("app.services.auth_service.engine") as engine:
            connection = engine.begin.return_value.__enter__.return_value
            connection.execute.return_value.rowcount = 1
            self.assertEqual(AuthService.rotate_bootstrap_passwords(), 4)
        credentials = [call.args[1] for call in connection.execute.call_args_list]
        self.assertEqual(
            [row["username"] for row in credentials],
            ["admin", "user_manhattan", "user_queens", "user_asia"],
        )
        self.assertTrue(verify_password(self.admin_password, credentials[0]["password_hash"]))
        for row in credentials[1:]:
            self.assertTrue(verify_password(self.manager_password, row["password_hash"]))

    def test_rotation_without_private_passwords_never_touches_database(self) -> None:
        with (
            patch("app.services.auth_service.settings.app_manager_password", None),
            patch("app.services.auth_service.engine") as engine,
        ):
            with self.assertRaises(ValueError):
                AuthService.rotate_bootstrap_passwords()
        engine.begin.assert_not_called()
