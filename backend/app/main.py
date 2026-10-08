from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ai import router as ai_router
from app.api.alerts import router as alerts_router
from app.api.auth import router as auth_router
from app.api.chat_sessions import router as chat_sessions_router
from app.api.data import router as data_router
from app.api.health import router as health_router
from app.api.semantic import router as semantic_router
from app.api.superset import router as superset_router
from app.core.config import settings
from app.services.anomaly_service import AnomalyService
from app.services.data_service import init_data_tables

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip() for origin in settings.frontend_origins.split(",") if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event() -> None:
    """Initialize metadata tables, seed users and initial alerts."""
    init_data_tables()
    AnomalyService.seed_initial_alerts_if_empty()


@app.get("/")
def root() -> dict[str, str]:
    return {"name": settings.app_name, "status": "running"}


app.include_router(health_router)
app.include_router(superset_router)
app.include_router(ai_router)
app.include_router(data_router)
app.include_router(semantic_router)
app.include_router(chat_sessions_router)
app.include_router(auth_router)
app.include_router(alerts_router)
