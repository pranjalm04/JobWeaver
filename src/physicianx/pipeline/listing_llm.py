from __future__ import annotations

from physicianx.config.pipeline import PipelineConfig
from physicianx.llm.models import JobListingLM
from physicianx.pipeline.stages import listing_llm as _listing_llm

analyze_full_html_with_llm = _listing_llm.analyze_full_html_with_llm
JobListingSchema = _listing_llm.JobListingSchema


async def extract_job_listing_spec(
    html: str,
    url: str,
    listing_lm: JobListingLM,
    *,
    config: PipelineConfig | None = None,
):
    return await analyze_full_html_with_llm(html, url, listing_lm, config=config)
