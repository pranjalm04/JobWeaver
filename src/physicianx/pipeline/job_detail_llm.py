from __future__ import annotations

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig

from physicianx.models import JobDetails
from physicianx.llm.models import JobDetailsLM
from physicianx.pipeline.stages.job_details_llm import extract_job_data


async def extract_job_details(
    crawler: AsyncWebCrawler,
    job_detail_urls: list[str],
    run_cfg: CrawlerRunConfig,
    job_details_lm: JobDetailsLM,
) -> list[JobDetails]:
    return await extract_job_data(crawler, job_detail_urls, run_cfg, job_details_lm)
