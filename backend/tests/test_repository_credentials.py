import importlib.util
import secrets
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_repository.py"
SPEC = importlib.util.spec_from_file_location("check_repository", MODULE_PATH)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


class RepositoryCredentialTests(unittest.TestCase):
    def test_workflow_literal_is_flagged_without_exposing_value(self) -> None:
        value = secrets.token_urlsafe(24)
        findings = checker.credential_findings(
            ".github/workflows/cd.yml", f"POSTGRES_PASSWORD={value}\n".encode()
        )
        self.assertEqual(findings, [(1, "hardcoded credential")])
        self.assertNotIn(value, repr(findings))

    def test_backend_password_literal_and_frontend_login_are_flagged(self) -> None:
        value = secrets.token_urlsafe(24)
        cases = (
            ("backend/app/services/auth.py", f'hash_password("{value}")'),
            ("frontend/context/Auth.tsx", f'login("admin", "{value}")'),
        )
        for name, source in cases:
            with self.subTest(name=name):
                self.assertEqual(
                    checker.credential_findings(name, source.encode()),
                    [(1, "hardcoded credential")],
                )

    def test_dynamic_credentials_and_type_annotations_are_not_flagged(self) -> None:
        cases = (
            ("backend/app/auth.py", "password: str\nnext_field: str = 'value'\n"),
            ("backend/app/auth.py", "admin_password = settings.app_admin_password\n"),
            (".github/workflows/cd.yml", "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}\n"),
            (".github/workflows/cd.yml", "password: ${{ secrets.GITHUB_TOKEN }}\n"),
            ("frontend/context/Auth.tsx", "login(username, password)\n"),
        )
        for name, source in cases:
            with self.subTest(name=name):
                self.assertEqual(checker.credential_findings(name, source.encode()), [])

    def test_example_and_unit_test_fixtures_are_not_runtime_credentials(self) -> None:
        source = f'password = "{secrets.token_urlsafe(24)}"'.encode()
        for name in (".env.example", "backend/tests/test_login.py"):
            self.assertEqual(checker.credential_findings(name, source), [])
