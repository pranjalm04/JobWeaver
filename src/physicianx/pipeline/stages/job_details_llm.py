from __future__ import annotations

import asyncio
import logging
import os
import time

from crawl4ai import (
    AsyncWebCrawler,
    DefaultMarkdownGenerator,
    MemoryAdaptiveDispatcher,
    PruningContentFilter,
)

from physicianx.models import JobDetails
from physicianx.llm.models import JobDetailsLM
from physicianx.observability import log_stage_event
from physicianx.storage.writer import append_jsonl_records

prune_filter = PruningContentFilter(
    threshold=0.2,
    threshold_type="dynamic",
    min_word_threshold=5,
)
md_generator = DefaultMarkdownGenerator(content_filter=prune_filter)

_JOB_DETAILS_WRITE_LOCK = asyncio.Lock()


async def detect_job_schema(markdown: str, job_details_lm: JobDetailsLM) -> JobDetails | None:
    try:
        return await job_details_lm.invoke(markdown=markdown)
    except Exception as e:
        logging.error("[LLM Parsing Error] %s", e)
        return None


async def extract_job_data(
    crawler: AsyncWebCrawler,
    urls: list[str],
    config,
    job_details_lm: JobDetailsLM,
    *,
    run_id: str | None = None,
) -> list[JobDetails]:
    t0 = time.perf_counter()
    urls = urls[:10]
    all_job_details: list[JobDetails] = []
    for i in range(0, len(urls), 20):
        batch = urls[i : i + 20]

        dispatcher = MemoryAdaptiveDispatcher(
            memory_threshold_percent=90.0,
            check_interval=1.0,
            max_session_permit=10,
            monitor=None,
        )
        batch_config = config.clone(deep_crawl_strategy=None, stream=False, markdown_generator=md_generator)
        result_batch = await crawler.arun_many(
            urls=batch,
            config=batch_config,
            dispatcher=dispatcher,
        )
        job_details_tasks = []
        for result in result_batch:
            if isinstance(result, Exception):
                logging.info("Error parsing url {}")
            elif result.success:
                task = asyncio.create_task(
                    detect_job_schema(
                        result.markdown.fit_markdown,
                        job_details_lm,
                    )
                )
                job_details_tasks.append(task)

        job_detail_result = await asyncio.gather(*job_details_tasks, return_exceptions=True)
        await save_jobs(job_detail_result)

        for jd in job_detail_result:
            if isinstance(jd, JobDetails):
                all_job_details.append(jd)

    total_tokens = sum(
        (jd.total_token_count or 0) for jd in all_job_details if isinstance(jd, JobDetails)
    )
    if run_id:
        log_stage_event(
            run_id=run_id,
            stage="job_details_llm",
            duration_ms=(time.perf_counter() - t0) * 1000,
            tokens=int(total_tokens) if total_tokens else None,
            extra={"job_rows": len(all_job_details)},
        )

    return all_job_details


async def save_jobs(job_detail_result: list) -> None:
    job_details_path = os.getenv("JOB_DETAILS_PATH", "job_details.json")
    records = []
    for jd in job_detail_result:
        if isinstance(jd, JobDetails):
            records.append(jd.model_dump())
        elif jd is None:
            continue
        elif isinstance(jd, Exception):
            logging.info("result unavilable")

    if records:
        async with _JOB_DETAILS_WRITE_LOCK:
            await append_jsonl_records(job_details_path, records)
