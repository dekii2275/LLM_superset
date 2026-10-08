"""Check files selected by Git for accidental credentials and oversized artifacts.

This lightweight check reports paths and issue types, never matching secret values.
It is a publication guard, not a replacement for a dedicated secret scanner.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_SIZE = 100 * 1024 * 1024
SECRET_PATTERNS = {
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "Google API key": re.compile(rb"AIza[0-9A-Za-z_-]{35}"),
    "GitHub token": re.compile(
        rb"(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{80,255})"
    ),
    "AWS access key": re.compile(rb"(?:AKIA|ASIA)[A-Z0-9]{16}"),
}

CREDENTIAL_NAME = r"(?:[A-Za-z0-9_]*(?:password|passwd|secret_key|jwt_secret)[A-Za-z0-9_]*|pwd)"
CREDENTIAL_PATTERNS = (
    re.compile(
        rf"\b{CREDENTIAL_NAME}[\"']?[ \t]*(?::[ \t]*str[ \t]*)?(?:=|:)[ \t]*[\"']([^\"'\r\n]+)[\"']",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^[ \t]*{CREDENTIAL_NAME}[ \t]*[:=][ \t]*([A-Za-z0-9_!@#%^&+./=:-]+)[ \t]*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(r"\bhash_password\([ \t]*[\"']([^\"'\r\n]+)[\"']"),
    re.compile(r"\blogin\([ \t]*[\"'][^\"']+[\"'][ \t]*,[ \t]*[\"']([^\"'\r\n]+)[\"']"),
)


def credential_findings(name: str, body: bytes) -> list[tuple[int, str]]:
    """Flag credential literals outside examples/tests, without returning their values."""
    path = Path(name)
    if (
        "tests" in path.parts
        or path.name.startswith("test_")
        or ".test." in path.name
        or path.name.endswith("env.example")
        or path.suffix == ".md"
    ):
        return []
    source = body.decode("utf-8", errors="replace")
    findings = set()
    for index, pattern in enumerate(CREDENTIAL_PATTERNS):
        if (
            index == 1
            and path.suffix not in {".yml", ".yaml", ".sh"}
            and not path.name.startswith(".env")
        ):
            continue
        for match in pattern.finditer(source):
            value = match.group(1)
            if not value or value.startswith(("replace_", "your_", "${", "$", "{{")):
                continue
            findings.add((source.count("\n", 0, match.start()) + 1, "hardcoded credential"))
    return sorted(findings)


def main() -> int:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    names = sorted(set(result.stdout.decode("utf-8").split("\0")) - {""})
    issues = []
    checked = 0
    for name in names:
        path = ROOT / name
        if not path.is_file():
            continue
        checked += 1
        template = path.name.endswith("env.example")
        if (path.name == ".env" or path.name.startswith(".env.")) and not template:
            issues.append((name, "environment file selected by Git"))
        if path.suffix.lower() in {".pem", ".key", ".p12", ".pfx", ".dump", ".backup", ".parquet"}:
            issues.append((name, "private key or database/source-data artifact selected by Git"))
        if path.stat().st_size >= MAX_FILE_SIZE:
            issues.append((name, "file reaches GitHub's 100 MiB limit"))
            continue
        body = path.read_bytes()
        if b"\0" in body[:8192]:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(body):
                issues.append((name, f"possible {label}"))
        for line, reason in credential_findings(name, body):
            issues.append((f"{name}:{line}", reason))
    for name, reason in issues:
        print(f"[FAIL] {name}: {reason}")
    if issues:
        return 1
    print(f"[OK] {checked} Git-selected files checked; no blocked artifacts or recognized secrets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
