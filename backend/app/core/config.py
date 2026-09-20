from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI BI Assistant API"
    app_env: str = "development"
    database_url: str
    frontend_url: str = "http://localhost:43117"
    superset_url: str = "http://superset:8088"

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")


settings = Settings()
