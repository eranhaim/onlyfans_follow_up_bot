from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://followup:followup@postgres:5432/followup"
    mongodb_url: str = "mongodb://mongo:27017/followup"
    frontend_origin: str = "http://localhost:8087"
    admin_password: str = "change-me"

    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_session_string: str | None = None

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_s3_bucket: str = "followup-videos"
    aws_region: str = "us-east-1"

    scheduler_interval_seconds: int = 300

    @field_validator("telegram_api_id", mode="before")
    @classmethod
    def empty_api_id(cls, value):
        if value in ("", None):
            return None
        return value

    @field_validator(
        "telegram_api_hash", "telegram_session_string",
        "openai_api_key", "aws_access_key_id", "aws_secret_access_key",
        mode="before",
    )
    @classmethod
    def empty_optional_str(cls, value):
        if value == "":
            return None
        return value


settings = Settings()
