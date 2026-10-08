import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Any

from sqlalchemy import text

from app.core.config import settings
from app.db.database import engine

logger = logging.getLogger(__name__)


def hash_password(password: str, salt: str | None = None) -> str:
    """Hash password using salted SHA-256."""
    if not salt:
        salt = secrets.token_hex(8)
    h = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return f"sha256${salt}${h}"


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify plain password against hashed password."""
    try:
        if not password_hash or "$" not in password_hash:
            return False
        parts = password_hash.split("$")
        if len(parts) != 3 or parts[0] != "sha256":
            return False
        salt = parts[1]
        expected_hash = parts[2]
        actual_hash = hashlib.sha256(f"{salt}:{plain_password}".encode("utf-8")).hexdigest()
        return hmac.compare_digest(actual_hash, expected_hash)
    except Exception:
        return False


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = 4 - (len(data) % 4)
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data.encode("utf-8"))


def create_jwt_token(payload: dict[str, Any], expires_in_seconds: int = 86400 * 7) -> str:
    """Creates a JWT token using HS256."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload_copy = dict(payload)
    now = int(time.time())
    payload_copy.setdefault("iat", now)
    payload_copy.setdefault("exp", now + expires_in_seconds)

    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload_copy, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")

    secret = settings.jwt_secret_key.encode("utf-8")
    sig = hmac.new(secret, signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(sig)

    return f"{header_b64}.{payload_b64}.{sig_b64}"


def decode_jwt_token(token: str) -> dict[str, Any] | None:
    """Decodes and validates a JWT token using HS256."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        secret = settings.jwt_secret_key.encode("utf-8")
        expected_sig = hmac.new(secret, signing_input, hashlib.sha256).digest()
        actual_sig = _b64url_decode(sig_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
        exp = payload.get("exp")
        if exp and int(time.time()) > exp:
            return None
        return payload
    except Exception as e:
        logger.warning(f"Invalid JWT token: {e}")
        return None


class AuthService:
    """Authentication and User management service."""

    @staticmethod
    def seed_default_users() -> None:
        """Seed default enterprise demo users and RLS rules."""
        try:
            with engine.begin() as conn:
                count = conn.execute(text("SELECT COUNT(*) FROM public.users;")).scalar() or 0
                if count == 0:
                    admin_hash = hash_password("admin123")
                    manhattan_hash = hash_password("pass123")
                    queens_hash = hash_password("pass123")
                    asia_hash = hash_password("pass123")

                    conn.execute(
                        text("""
                            INSERT INTO public.users (username, password_hash, display_name, role, is_active)
                            VALUES
                                ('admin', :admin_hash, 'Quản trị viên Hệ thống (Toàn quyền)', 'admin', true),
                                ('user_manhattan', :manhattan_hash, 'Quản lý Khu vực Manhattan (RLS Taxi)', 'manager', true),
                                ('user_queens', :queens_hash, 'Quản lý Khu vực Queens (RLS Taxi)', 'manager', true),
                                ('user_asia', :asia_hash, 'Quản lý Vùng Châu Á (RLS Đô thị)', 'manager', true);
                        """),
                        {
                            "admin_hash": admin_hash,
                            "manhattan_hash": manhattan_hash,
                            "queens_hash": queens_hash,
                            "asia_hash": asia_hash,
                        },
                    )

                    # Get user IDs
                    users_rows = conn.execute(
                        text("SELECT id, username FROM public.users;")
                    ).fetchall()
                    user_map = {row.username: row.id for row in users_rows}

                    # Seed RLS rules
                    # user_manhattan: RLS on datasets 1 and 2 (NYC Taxi) -> pickup_borough = 'Manhattan'
                    if "user_manhattan" in user_map:
                        u_id = user_map["user_manhattan"]
                        manhattan_clause = "pickup_borough = 'Manhattan'"
                        conn.execute(
                            text("""
                                INSERT INTO public.user_dataset_rls (user_id, dataset_id, filter_clause, description)
                                VALUES
                                    (:uid, 1, :filter, 'Chỉ xem dữ liệu đón tại Manhattan'),
                                    (:uid, 2, :filter, 'Chỉ xem dữ liệu đón tại Manhattan');
                            """),
                            {"uid": u_id, "filter": manhattan_clause},
                        )

                    # user_queens: RLS on datasets 1 and 2 -> pickup_borough = 'Queens'
                    if "user_queens" in user_map:
                        u_id = user_map["user_queens"]
                        queens_clause = "pickup_borough = 'Queens'"
                        conn.execute(
                            text("""
                                INSERT INTO public.user_dataset_rls (user_id, dataset_id, filter_clause, description)
                                VALUES
                                    (:uid, 1, :filter, 'Chỉ xem dữ liệu đón tại Queens'),
                                    (:uid, 2, :filter, 'Chỉ xem dữ liệu đón tại Queens');
                            """),
                            {"uid": u_id, "filter": queens_clause},
                        )

                    # user_asia: RLS on dataset 5 (Populated places) -> country IN Asian countries
                    if "user_asia" in user_map:
                        u_id = user_map["user_asia"]
                        asia_filter = "country IN ('Vietnam', 'Japan', 'China', 'India', 'Thailand', 'South Korea', 'Indonesia', 'Philippines', 'Singapore', 'Malaysia')"
                        conn.execute(
                            text("""
                                INSERT INTO public.user_dataset_rls (user_id, dataset_id, filter_clause, description)
                                VALUES
                                    (:uid, 5, :filter, 'Chỉ xem các đô thị thuộc các quốc gia Châu Á');
                            """),
                            {"uid": u_id, "filter": asia_filter},
                        )
        except Exception as e:
            logger.exception("seed_default_users_failed: %s", e)

    @staticmethod
    def authenticate(username: str, password: str) -> dict[str, Any] | None:
        """Validate credentials and return user info with token."""
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text(
                        "SELECT id, username, password_hash, display_name, role, is_active FROM public.users WHERE username = :u;"
                    ),
                    {"u": username.strip()},
                ).fetchone()

                if not row:
                    return None

                user_id, uname, p_hash, display_name, role, is_active = row
                if not is_active or not verify_password(password, p_hash):
                    return None

                # Get RLS rules for user
                rls_rows = conn.execute(
                    text(
                        "SELECT dataset_id, filter_clause, description FROM public.user_dataset_rls WHERE user_id = :uid;"
                    ),
                    {"uid": user_id},
                ).fetchall()

                rls_rules = [
                    {
                        "dataset_id": r.dataset_id,
                        "filter_clause": r.filter_clause,
                        "description": r.description,
                    }
                    for r in rls_rows
                ]

                token = create_jwt_token(
                    {
                        "sub": user_id,
                        "username": uname,
                        "role": role,
                        "display_name": display_name,
                    }
                )

                return {
                    "id": user_id,
                    "username": uname,
                    "display_name": display_name,
                    "role": role,
                    "token": token,
                    "rls_rules": rls_rules,
                }
        except Exception as e:
            logger.exception("authenticate_failed: %s", e)
            return None

    @staticmethod
    def get_user_by_id(user_id: int) -> dict[str, Any] | None:
        """Get user details and RLS rules by ID."""
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text(
                        "SELECT id, username, display_name, role, is_active FROM public.users WHERE id = :uid;"
                    ),
                    {"uid": user_id},
                ).fetchone()
                if not row:
                    return None

                u_id, uname, display_name, role, is_active = row
                rls_rows = conn.execute(
                    text(
                        "SELECT dataset_id, filter_clause, description FROM public.user_dataset_rls WHERE user_id = :uid;"
                    ),
                    {"uid": user_id},
                ).fetchall()

                return {
                    "id": u_id,
                    "username": uname,
                    "display_name": display_name,
                    "role": role,
                    "is_active": is_active,
                    "rls_rules": [
                        {
                            "dataset_id": r.dataset_id,
                            "filter_clause": r.filter_clause,
                            "description": r.description,
                        }
                        for r in rls_rows
                    ],
                }
        except Exception as e:
            logger.exception("get_user_by_id_failed: %s", e)
            return None

    @staticmethod
    def list_users() -> list[dict[str, Any]]:
        """List all users for quick switching."""
        try:
            with engine.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT id, username, display_name, role, is_active FROM public.users ORDER BY id ASC;"
                    )
                ).fetchall()

                result = []
                for row in rows:
                    rls_rows = conn.execute(
                        text(
                            "SELECT dataset_id, filter_clause, description FROM public.user_dataset_rls WHERE user_id = :uid;"
                        ),
                        {"uid": row.id},
                    ).fetchall()
                    result.append(
                        {
                            "id": row.id,
                            "username": row.username,
                            "display_name": row.display_name,
                            "role": row.role,
                            "is_active": row.is_active,
                            "rls_rules": [
                                {
                                    "dataset_id": r.dataset_id,
                                    "filter_clause": r.filter_clause,
                                    "description": r.description,
                                }
                                for r in rls_rows
                            ],
                        }
                    )
                return result
        except Exception as e:
            logger.exception("list_users_failed: %s", e)
            return []
