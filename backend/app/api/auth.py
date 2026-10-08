from typing import Any

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from app.services.auth_service import AuthService, decode_jwt_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class RlsRuleItem(BaseModel):
    dataset_id: int
    filter_clause: str
    description: str | None = None


class UserProfile(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool = True
    rls_rules: list[RlsRuleItem] = []


class LoginResponse(BaseModel):
    token: str
    user: UserProfile


def get_current_user_optional(authorization: str | None = Header(None)) -> dict[str, Any] | None:
    """Dependency to extract authenticated user from Bearer token if provided."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_jwt_token(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    user = AuthService.get_user_by_id(user_id)
    return user


def get_current_user_required(authorization: str | None = Header(None)) -> dict[str, Any]:
    """Dependency that enforces a valid Bearer token."""
    user = get_current_user_optional(authorization)
    if not user or not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Thông tin xác thực không hợp lệ hoặc phiên đăng nhập đã hết hạn.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest) -> LoginResponse:
    """Simple username/password login endpoint."""
    user_data = AuthService.authenticate(req.username, req.password)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tên đăng nhập hoặc mật khẩu không chính xác.",
        )
    return LoginResponse(
        token=user_data["token"],
        user=UserProfile(
            id=user_data["id"],
            username=user_data["username"],
            display_name=user_data["display_name"],
            role=user_data["role"],
            rls_rules=[RlsRuleItem(**r) for r in user_data.get("rls_rules", [])],
        ),
    )


@router.get("/me", response_model=UserProfile)
def get_me(authorization: str | None = Header(None)) -> UserProfile:
    """Get profile of current logged-in user."""
    user = get_current_user_required(authorization)
    return UserProfile(
        id=user["id"],
        username=user["username"],
        display_name=user["display_name"],
        role=user["role"],
        is_active=user["is_active"],
        rls_rules=[RlsRuleItem(**r) for r in user.get("rls_rules", [])],
    )


@router.get("/users", response_model=list[UserProfile])
def get_demo_users() -> list[UserProfile]:
    """List available demo users for UI quick switcher."""
    users = AuthService.list_users()
    return [
        UserProfile(
            id=u["id"],
            username=u["username"],
            display_name=u["display_name"],
            role=u["role"],
            is_active=u["is_active"],
            rls_rules=[RlsRuleItem(**r) for r in u.get("rls_rules", [])],
        )
        for u in users
    ]
