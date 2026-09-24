from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI BI Assistant API"
    app_env: str = "development"
    database_url: str
    frontend_url: str = "http://localhost:43117"
    frontend_origins: str = "http://localhost:43117,http://127.0.0.1:43117"
    superset_url: str = "http://superset:8088"
    superset_public_url: str = "http://localhost:58088"
    superset_mcp_internal_url: str = "http://superset-mcp:5008/mcp"
    superset_admin_username: str | None = None
    superset_admin_password: str | None = None
    superset_dashboard_slug: str = "nyc-yellow-taxi-overview"
    superset_taxi_dataset_id: int = 1
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.6-flash"
    ai_allow_superset_write: bool = False
    default_query_limit: int = 100
    max_query_limit: int = 500
    ai_query_timeout_seconds: int = 10
    ai_answer_max_rows: int = 20

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")


settings = Settings()
