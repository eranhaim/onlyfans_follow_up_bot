from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://followup:followup@postgres:5432/followup"
    frontend_origin: str = "http://localhost:8087"
    admin_password: str = "change-me"

    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_session_string: str | None = None

    scheduler_interval_seconds: int = 300

    @field_validator("telegram_api_id", mode="before")
    @classmethod
    def empty_api_id(cls, value):
        if value in ("", None):
            return None
        return value

    @field_validator("telegram_api_hash", "telegram_session_string", mode="before")
    @classmethod
    def empty_optional_str(cls, value):
        if value == "":
            return None
        return value


settings = Settings()
