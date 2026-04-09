"""
Target schema for moving off JSONL-only storage.

Use Postgres/SQLite for rows; S3/GCS (or local dir) for raw HTML keyed by content hash.
Implement with SQLAlchemy/Alembic when you add a DB dependency.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class CrawlRunRecord(BaseModel):
    """One execution of the pipeline (or one seed)."""

    id: str = Field(description="UUID run_id / correlation id")
    started_at: datetime
    finished_at: datetime | None = None
    seed_url: str
    status: str = Field(description="ok | error | partial")
    meta: dict[str, Any] = Field(default_factory=dict)


class HtmlBlobRef(BaseModel):
    """Pointer to stored raw HTML (dedup by sha256)."""

    content_sha256: str
    source_url: str
    byte_length: int
    storage_uri: str = Field(description="s3://bucket/key or file path")


class JobRecord(BaseModel):
    """Normalized job row for querying and dedup."""

    id: str = Field(description="Stable id: hash(seed_url + normalized_job_url)")
    run_id: str
    listing_url: str
    job_url: str
    title: str | None = None
    location: str | None = None
    extracted: dict[str, Any] = Field(default_factory=dict, description="JobDetails fields")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
