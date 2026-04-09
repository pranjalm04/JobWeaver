"""Optional on-disk cache for listing LLM results (keyed by SHA-256 of raw HTML)."""

from __future__ import annotations

import hashlib
import json
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from physicianx.models import JobListingSchema


def html_fingerprint(html: str) -> str:
    return hashlib.sha256(html.encode("utf-8", errors="replace")).hexdigest()


def cache_path(cache_dir: str, html: str) -> str:
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{html_fingerprint(html)}.json")


def try_load_listing_cache(cache_dir: str, html: str) -> JobListingSchema | None:
    if not cache_dir.strip():
        return None
    path = cache_path(cache_dir, html)
    if not os.path.isfile(path):
        return None
    try:
        from physicianx.models import JobListingSchema

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return JobListingSchema.model_validate(data)
    except OSError:
        return None


def save_listing_cache(cache_dir: str, html: str, spec: JobListingSchema) -> None:
    if not cache_dir.strip():
        return
    path = cache_path(cache_dir, html)
    with open(path, "w", encoding="utf-8") as f:
        f.write(spec.model_dump_json(indent=2))
