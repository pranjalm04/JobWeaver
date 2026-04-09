from __future__ import annotations

from typing import Self

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Celery broker + shared paths (aligned with pipeline env where possible)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key_gemini: str = ""
    celery_broker_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("CELERY_BROKER_URL"),
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/1",
        validation_alias=AliasChoices("CELERY_RESULT_BACKEND"),
    )
    output_dir: str = Field(default="outputs")
    job_details_path: str = Field(default="", validation_alias=AliasChoices("JOB_DETAILS_PATH"))

    @model_validator(mode="after")
    def _default_job_details_path(self) -> Self:
        if not self.job_details_path.strip():
            self.job_details_path = f"{self.output_dir.rstrip('/')}/job_details.jsonl"
        return self


def get_settings() -> Settings:
    return Settings()
