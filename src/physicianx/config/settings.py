from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Celery broker URLs. Pipeline-level paths/options live on PipelineConfig."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    celery_broker_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("CELERY_BROKER_URL"),
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/1",
        validation_alias=AliasChoices("CELERY_RESULT_BACKEND"),
    )


def get_settings() -> Settings:
    return Settings()
