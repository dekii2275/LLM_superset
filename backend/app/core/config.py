import secrets
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_ENV_FILE = Path(__file__).resolve().parents[3] / ".env.local"


class Settings(BaseSettings):
    app_name: str = "AI BI Assistant API"
    app_env: str = "development"
    database_url: str
    frontend_url: str = "http://localhost:43117"
    frontend_origins: str = "http://localhost:43117,http://127.0.0.1:43117"
    superset_url: str = "http://superset:8088"
    superset_public_url: str = "http://localhost:59088"
    superset_mcp_internal_url: str = "http://superset-mcp:5008/mcp"
    superset_admin_username: str | None = None
    superset_admin_password: str | None = None
    superset_dashboard_slug: str = "nyc-taxi-trips-analysis"
    superset_taxi_dataset_id: int = 1
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.6-flash"
    ai_allow_superset_write: bool = False
    default_query_limit: int = 100
    max_query_limit: int = 500
    ai_query_timeout_seconds: int = 10
    ai_answer_max_rows: int = 20
    redis_url: str = "redis://redis:6379/0"
    # A process-local key keeps development usable without a shared signing secret.
    # Production requires an explicit, persistent key from the environment.
    jwt_secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    jwt_algorithm: str = "HS256"

    model_config = SettingsConfigDict(case_sensitive=False, env_file=LOCAL_ENV_FILE, extra="ignore")

    @model_validator(mode="after")
    def validate_production_secret(self) -> "Settings":
        if self.app_env.lower() == "production":
            if (
                "jwt_secret_key" not in self.model_fields_set
                or len(self.jwt_secret_key) < 32
                or self.jwt_secret_key.startswith("replace_")
                or self.jwt_secret_key == "ai-bi-jwt-secret-key-enterprise-phase4"
            ):
                raise ValueError("Set JWT_SECRET_KEY to a unique secret of at least 32 characters")
        return self


settings = Settings()
