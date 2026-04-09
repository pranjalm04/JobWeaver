from __future__ import annotations

from pathlib import Path
from typing import Self

from pydantic import AliasChoices, Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _pipeline_config_env_files() -> tuple[str, str]:
    """Load repo-root `.env` first so `python examples/foo.py` still sees keys from project root."""

    repo_root = Path(__file__).resolve().parents[3]
    return (str(repo_root / ".env"), ".env")


class PipelineConfig(BaseSettings):
    """Pipeline parameters loaded from environment (and optional `.env`)."""

    model_config = SettingsConfigDict(
        env_file=_pipeline_config_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
        validate_assignment=True,
        populate_by_name=True,
    )

    api_key_gemini: str = Field(default="", validation_alias=AliasChoices("API_KEY_GEMINI"))
    llm_provider: str = Field(default="", validation_alias=AliasChoices("LLM_PROVIDER"))
    llm_api_key: str = Field(default="", validation_alias=AliasChoices("LLM_API_KEY"))
    llm_model_listing: str = Field(
        default="openai/gpt-4o-mini",
        validation_alias=AliasChoices("LLM_MODEL_LISTING"),
    )
    llm_model_job_detail: str = Field(
        default="openai/gpt-4o-mini",
        validation_alias=AliasChoices("LLM_MODEL_JOB_DETAIL"),
    )
    llm_api_base: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_API_BASE"),
    )
    llm_extra_headers_json: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_EXTRA_HEADERS_JSON"),
    )
    seed_urls: str = Field(default="", validation_alias=AliasChoices("SEED_URLS"))
    max_depth: int = Field(default=2, ge=0, le=100)
    max_seeds_in_flight: int = Field(default=2, ge=1, le=500)
    max_pages_global: int = Field(default=10, ge=1, le=500)
    max_pages_per_seed: int = Field(default=50, ge=1, le=10000)
    max_pages_per_host: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Concurrent fetch budget per hostname inside BFS batches.",
        validation_alias=AliasChoices("MAX_PAGES_PER_HOST"),
    )
    output_dir: str = Field(default="outputs")

    listing_max_chunks: int = Field(
        default=8,
        ge=1,
        le=100,
        validation_alias=AliasChoices("LISTING_MAX_CHUNKS"),
    )
    listing_chunk_sleep_ms: int = Field(
        default=200,
        ge=0,
        le=120_000,
        validation_alias=AliasChoices("LISTING_CHUNK_SLEEP_MS"),
    )
    listing_max_total_tokens: int = Field(
        default=500_000,
        ge=1,
        description="Stop listing LLM after cumulative prompt+output tokens exceed this (best-effort).",
        validation_alias=AliasChoices("LISTING_MAX_TOTAL_TOKENS"),
    )
    listing_cache_dir: str = Field(
        default="",
        validation_alias=AliasChoices("LISTING_CACHE_DIR"),
        description="If set, cache JobListingSchema JSON under this directory keyed by HTML hash.",
    )
    llm_max_retries: int = Field(default=4, ge=0, le=20, validation_alias=AliasChoices("LLM_MAX_RETRIES"))
    llm_retry_base_ms: int = Field(
        default=500,
        ge=50,
        le=60_000,
        validation_alias=AliasChoices("LLM_RETRY_BASE_MS"),
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def seeds(self) -> list[str]:
        if not self.seed_urls.strip():
            return []
        return [s.strip() for s in self.seed_urls.split(",") if s.strip()]

    @classmethod
    def from_env(cls) -> Self:
        return cls()

    @field_validator(
        "api_key_gemini",
        "llm_api_key",
        "llm_provider",
        "llm_api_base",
        "llm_extra_headers_json",
        mode="before",
    )
    @classmethod
    def _strip_api_key(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    def resolved_llm_api_key(self) -> str:
        """Prefer `LLM_API_KEY`; if empty, fall back to legacy `API_KEY_GEMINI`."""

        k = self.llm_api_key.strip()
        if k:
            return k
        return self.api_key_gemini.strip()
