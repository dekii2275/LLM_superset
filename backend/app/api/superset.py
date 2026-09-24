from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.services.superset import SupersetClient, SupersetEmbedError


router = APIRouter(prefix="/api/v1/superset", tags=["superset"])


def get_client() -> SupersetClient:
    if not settings.superset_admin_username or not settings.superset_admin_password:
        raise HTTPException(status_code=503, detail="Superset embed credentials are not configured.")
    client = SupersetClient(
        settings.superset_url,
        settings.superset_admin_username,
        settings.superset_admin_password,
    )
    try:
        client.login()
    except SupersetEmbedError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return client


@router.get("/embed-config")
def embed_config() -> dict[str, str]:
    client = get_client()
    try:
        dashboard_id = client.embedded_dashboard_id(settings.superset_dashboard_slug)
    except SupersetEmbedError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {
        "dashboard_id": dashboard_id,
        "superset_url": settings.superset_public_url.rstrip("/"),
    }


@router.get("/guest-token")
def guest_token() -> dict[str, str]:
    client = get_client()
    try:
        dashboard_id = client.embedded_dashboard_id(settings.superset_dashboard_slug)
        token = client.create_guest_token(dashboard_id)
    except SupersetEmbedError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {"token": token}


@router.get("/dashboard/{dashboard_id}/embed-config")
def dashboard_embed_config(dashboard_id: int) -> dict[str, str]:
    client = get_client()
    try:
        embedded_id = client.embedded_dashboard_id(str(dashboard_id))
    except SupersetEmbedError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {"dashboard_id": embedded_id, "superset_url": settings.superset_public_url.rstrip("/")}


@router.get("/dashboard/{dashboard_id}/guest-token")
def dashboard_guest_token(dashboard_id: int) -> dict[str, str]:
    client = get_client()
    try:
        embedded_id = client.embedded_dashboard_id(str(dashboard_id))
        token = client.create_guest_token(embedded_id)
    except SupersetEmbedError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {"token": token}
