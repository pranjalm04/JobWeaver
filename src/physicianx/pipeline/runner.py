from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid

from crawl4ai import AsyncWebCrawler

from physicianx.config import PipelineConfig
from physicianx.llm import ensure_pipeline_llm_config
from physicianx.llm.models import JobDetailsLM, JobListingLM
from physicianx.observability import StageTimer, log_stage_event
from physicianx.storage.writer import append_jsonl, append_text_line
from physicianx.web.crawl4ai import build_browser_config, build_run_config
from physicianx.pipeline.stages.crawl import BFSCrawl
from physicianx.pipeline.stages.job_details_llm import extract_job_data
from physicianx.pipeline.stages.job_links import scrape_jobs_to_dict
from physicianx.pipeline.stages.listing_llm import analyze_full_html_with_llm


class PipelineRunner:
    def __init__(self, config: PipelineConfig, run_id: str | None = None):
        self.config = config
        self.run_id = run_id or uuid.uuid4().hex

        self.crawler = None

        self.page_sem = asyncio.Semaphore(self.config.max_pages_global)
        self.seed_sem = asyncio.Semaphore(self.config.max_seeds_in_flight)

        self.BROWSER_CFG = build_browser_config()
        self.RUN_CFG = build_run_config()
        ensure_pipeline_llm_config(self.config)
        self.listing_lm = JobListingLM(self.config)
        self.job_details_lm = JobDetailsLM(self.config)

        self.llm_outputs_path = os.path.join(self.config.output_dir, "llm_outputs.jsonl")
        self.career_listings_path = os.path.join(self.config.output_dir, "career_listings.txt")

    def patch_page_semaphore(self) -> None:
        """Limit concurrent crawl4ai browser work to match `max_pages_global`."""

        orig_arun = self.crawler.arun

        async def safe_arun(*args, **kwargs):
            async with self.page_sem:
                return await orig_arun(*args, **kwargs)

        self.crawler.arun = safe_arun

        if hasattr(self.crawler, "arun_many"):
            orig_many = self.crawler.arun_many

            async def safe_arun_many(*args, **kwargs):
                async with self.page_sem:
                    return await orig_many(*args, **kwargs)

            self.crawler.arun_many = safe_arun_many

    async def save_record(self, record_line: str) -> None:
        os.makedirs(self.config.output_dir, exist_ok=True)
        await append_text_line(self.career_listings_path, record_line)

    async def analyze_and_save_llm(self, html: str, url: str) -> None:
        try:
            with StageTimer(
                run_id=self.run_id,
                stage="post_crawl_analyze",
                url=url,
                extra={"phase": "full"},
            ):
                llm_res = await analyze_full_html_with_llm(
                    html,
                    url,
                    self.listing_lm,
                    config=self.config,
                    run_id=self.run_id,
                )
                jobs = await scrape_jobs_to_dict(
                    llm_res,
                    source_html=html,
                    run_id=self.run_id,
                )

                await extract_job_data(
                    self.crawler,
                    [j.url for j in jobs],
                    self.RUN_CFG,
                    self.job_details_lm,
                    run_id=self.run_id,
                )

                if llm_res is not None:
                    await append_jsonl(self.llm_outputs_path, llm_res.model_dump())
        except Exception as e:
            logging.error(f"[LLM SAVE ERROR] {url}: {e}")

    async def crawl_seed(self, seed: str) -> dict | None:
        """BFS crawl for one seed; does not run post-crawl LLM (avoids sharing the crawler)."""
        with StageTimer(run_id=self.run_id, stage="bfs_crawl", seed=seed):
            async with self.seed_sem:
                bfs = BFSCrawl(
                    seed,
                    int(self.config.max_depth),
                    self.crawler,
                    include_external=True,
                    max_pages_per_host=self.config.max_pages_per_host,
                )
                rec = await bfs._arun_batch(self.RUN_CFG, self.config.max_pages_per_seed)
        record_line = f"{seed} {rec['url']} {rec['job_listing_score']}" if rec else f"{seed} NA NA"
        await self.save_record(record_line)
        return rec

    async def main(self) -> None:
        os.makedirs(self.config.output_dir, exist_ok=True)
        log_stage_event(
            run_id=self.run_id,
            stage="pipeline_start",
            duration_ms=0.0,
            extra={"seeds": len(self.config.seeds)},
        )

        browser = AsyncWebCrawler(config=self.BROWSER_CFG)
        async with browser as crawlerbfs:
            self.crawler = crawlerbfs
            await self.crawler.awarmup()
            self.patch_page_semaphore()

            crawl_tasks = [asyncio.create_task(self.crawl_seed(seed)) for seed in self.config.seeds]
            outcomes = await asyncio.gather(*crawl_tasks, return_exceptions=True)

            for out in outcomes:
                if isinstance(out, Exception):
                    logging.error(f"[CRAWL] {out}")
                    continue
                rec = out
                if rec:
                    await self.analyze_and_save_llm(rec["html"], rec["url"])

        log_stage_event(run_id=self.run_id, stage="pipeline_end", duration_ms=0.0)


async def run_pipeline_from_env() -> None:
    config = PipelineConfig.from_env()
    runner = PipelineRunner(config)
    start = time.time()
    await runner.main()
    end = time.time()
    print(f"time_take {(end - start) / 60:.2f} min")
