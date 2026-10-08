"""Rotate seeded application accounts from private environment passwords.

Run from backend/: python -m scripts.rotate_app_passwords --apply
Existing user IDs, roles, RLS rules and application data are preserved.
"""

import argparse

from app.services.auth_service import AuthService


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Apply password rotation to existing seeded users"
    )
    args = parser.parse_args()
    if not args.apply:
        parser.error("Specify --apply after configuring new private bootstrap passwords")
    updated = AuthService.rotate_bootstrap_passwords()
    print(
        f"Rotated passwords for {updated} seeded application users. No credential values displayed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
