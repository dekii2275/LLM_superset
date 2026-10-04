from sqlalchemy import text

from app.db.database import engine

_table_ready = False


def _ensure_table() -> None:
    global _table_ready
    if _table_ready:
        return
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS ai_settings (
                    setting_key VARCHAR(64) PRIMARY KEY,
                    enabled BOOLEAN NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS ai_token_usage (
                    usage_key VARCHAR(32) PRIMARY KEY,
                    total_tokens BIGINT NOT NULL DEFAULT 0
                )
                """
            )
        )
    _table_ready = True


def is_llm_enabled() -> bool:
    _ensure_table()
    with engine.connect() as connection:
        enabled = connection.execute(
            text("SELECT enabled FROM ai_settings WHERE setting_key = 'llm_enabled'")
        ).scalar_one_or_none()
    return True if enabled is None else bool(enabled)


def set_llm_enabled(enabled: bool) -> bool:
    _ensure_table()
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO ai_settings (setting_key, enabled)
                VALUES ('llm_enabled', :enabled)
                ON CONFLICT (setting_key) DO UPDATE SET enabled = EXCLUDED.enabled
                """
            ),
            {"enabled": enabled},
        )
    return enabled


def get_token_usage() -> int:
    _ensure_table()
    with engine.connect() as connection:
        total = connection.execute(
            text("SELECT total_tokens FROM ai_token_usage WHERE usage_key = 'gemini'")
        ).scalar_one_or_none()
    return int(total or 0)


def record_token_usage(tokens: int) -> None:
    if tokens <= 0:
        return
    _ensure_table()
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO ai_token_usage (usage_key, total_tokens)
                VALUES ('gemini', :tokens)
                ON CONFLICT (usage_key) DO UPDATE
                SET total_tokens = ai_token_usage.total_tokens + EXCLUDED.total_tokens
                """
            ),
            {"tokens": tokens},
        )
