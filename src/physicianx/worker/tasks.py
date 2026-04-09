from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import traceback
from typing import Any

from crawl4ai import AsyncWebCrawler

from physicianx.config import PipelineConfig
from physicianx.storage.writer import append_jsonl
from physicianx.pipeline.runner import PipelineRunner
from physicianx.pipeline.stages.job_details_llm import extract_job_data
from physicianx.pipeline.stages.job_links import scrape_jobs_to_dict
from physicianx.pipeline.stages.listing_llm import JobListingSchema, analyze_full_html_with_llm
from physicianx.worker.celery_app import celery_app


def _build_runner_with_seed(seed_url: str | None = None) -> PipelineRunner:
    cfg = PipelineConfig.from_env()
    if seed_url:
        cfg = cfg.model_copy(update={"seed_urls": seed_url})
    return PipelineRunner(cfg)


def _err(message: str, **extra: Any) -> dict[str, Any]:
    return {"status": "error", "error": message, **extra}


@celery_app.task(
    name="physicianx.crawl_seed",
    bind=True,
    autoretry_for=(ConnectionError, OSError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def crawl_seed(self, seed_url: str) -> dict[str, Any]:
    try:
        runner = _build_runner_with_seed(seed_url)
        asyncio.run(runner.main())
        return {"status": "ok", "seed_url": seed_url, "run_id": runner.run_id}
    except Exception as e:
        logging.exception("crawl_seed failed")
        return _err(str(e), seed_url=seed_url, traceback=traceback.format_exc())


@celery_app.task(
    name="physicianx.run_pipeline",
    bind=True,
    autoretry_for=(ConnectionError, OSError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)
def run_pipeline(self) -> dict[str, Any]:
    try:
        runner = _build_runner_with_seed()
        asyncio.run(runner.main())
        return {"status": "ok", "seeds": runner.config.seeds, "run_id": runner.run_id}
    except Exception as e:
        logging.exception("run_pipeline failed")
        return _err(str(e), traceback=traceback.format_exc())


@celery_app.task(
    name="physicianx.analyze_listing",
    bind=True,
    autoretry_for=(ConnectionError, OSError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=4,
)
def analyze_listing(self, html: str, url: str) -> dict[str, Any]:
    cfg = PipelineConfig.from_env()
    runner = _build_runner_with_seed()

    async def _run() -> str:
        listing_spec = await analyze_full_html_with_llm(
            html,
            url,
            runner.listing_lm,
            config=cfg,
            run_id=runner.run_id,
        )
        output_path = os.path.join(
            cfg.output_dir,
            f"listing_{hashlib.md5(url.encode('utf-8')).hexdigest()}.jsonl",
        )
        await append_jsonl(output_path, listing_spec.model_dump())
        return output_path

    try:
        output_path = asyncio.run(_run())
        return {"status": "ok", "url": url, "output_path": output_path, "run_id": runner.run_id}
    except Exception as e:
        logging.exception("analyze_listing failed")
        return _err(str(e), url=url, traceback=traceback.format_exc())


@celery_app.task(name="physicianx.scrape_job_links")
def scrape_job_links(listing_payload: dict[str, Any]) -> dict[str, Any]:
    try:
        listing_spec = JobListingSchema.model_validate(listing_payload)
        links = asyncio.run(scrape_jobs_to_dict(listing_spec))
        return {
            "status": "ok",
            "count": len(links),
            "links": [link.model_dump() for link in links],
        }
    except Exception as e:
        logging.exception("scrape_job_links failed")
        return _err(str(e), traceback=traceback.format_exc())


@celery_app.task(name="physicianx.extract_job_details")
def extract_job_details(job_urls: list[str]) -> dict[str, Any]:
    runner = _build_runner_with_seed()
    rid = runner.run_id

    async def _run() -> int:
        async with AsyncWebCrawler(config=runner.BROWSER_CFG) as crawler:
            await crawler.awarmup()
            details = await extract_job_data(
                crawler,
                job_urls,
                runner.RUN_CFG,
                runner.job_details_lm,
                run_id=rid,
            )
            return len(details)

    try:
        count = asyncio.run(_run())
        return {"status": "ok", "count": count, "run_id": rid}
    except Exception as e:
        logging.exception("extract_job_details failed")
        return _err(str(e), traceback=traceback.format_exc())
