from __future__ import annotations

from typing import List

from physicianx.models import JobListingSchema, ScrapedJobLink
from physicianx.pipeline.stages.job_links import scrape_jobs_to_dict


async def scrape_job_links(job_listing_spec: JobListingSchema) -> List[ScrapedJobLink]:
    return await scrape_jobs_to_dict(job_listing_spec)
