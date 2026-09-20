from urllib.error import URLError
from urllib.request import urlopen

from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.database import engine

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/db")
def database_health() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Database unavailable") from error

    return {"status": "ok", "database": "connected"}


@router.get("/superset")
def superset_health() -> dict[str, str]:
    try:
        with urlopen(f"{settings.superset_url.rstrip('/')}/health", timeout=3) as response:
            if response.status != 200:
                raise HTTPException(status_code=503, detail="Superset unavailable")
    except (OSError, URLError) as error:
        raise HTTPException(status_code=503, detail="Superset unavailable") from error

    return {"status": "ok", "superset": "connected"}
