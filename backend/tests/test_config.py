"""Verify environment loading and production JWT signing-key requirements."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from app.core.config import LOCAL_ENV_FILE, Settings


class SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def make_settings(self, **overrides) -> Settings:
        return Settings(
            _env_file=None,
            database_url="postgresql+psycopg://test:test@localhost/test",
            **overrides,
        )

    def test_local_env_path_does_not_depend_on_working_directory(self) -> None:
        self.assertTrue(LOCAL_ENV_FILE.is_absolute())
        self.assertEqual(LOCAL_ENV_FILE, Path(__file__).resolve().parents[2] / ".env.local")

    def test_development_generates_independent_keys(self) -> None:
        first = self.make_settings()
        second = self.make_settings()
        self.assertGreaterEqual(len(first.jwt_secret_key), 32)
        self.assertNotEqual(first.jwt_secret_key, second.jwt_secret_key)

    def test_production_rejects_missing_or_example_keys(self) -> None:
        with self.assertRaises(ValidationError):
            self.make_settings(app_env="production")
        for secret in (
            "short",
            "replace_with_a_unique_random_jwt_secret_at_least_32_characters",
            "ai-bi-jwt-secret-key-enterprise-phase4",
        ):
            with self.subTest(secret=secret), self.assertRaises(ValidationError):
                self.make_settings(app_env="production", jwt_secret_key=secret)

    def test_production_accepts_environment_key(self) -> None:
        secret = "test-only-persistent-jwt-secret-at-least-32-characters"
        with patch.dict(os.environ, {"JWT_SECRET_KEY": secret}):
            settings = self.make_settings(app_env="production")
        self.assertEqual(settings.jwt_secret_key, secret)


if __name__ == "__main__":
    unittest.main()
