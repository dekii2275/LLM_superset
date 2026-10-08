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
    for name, reason in issues:
        print(f"[FAIL] {name}: {reason}")
    if issues:
        return 1
    print(f"[OK] {checked} Git-selected files checked; no blocked artifacts or recognized secrets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
