from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from typing import Any, List, Optional, Set, Tuple

import regex as re
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CrawlResult, MemoryAdaptiveDispatcher
from urllib.parse import urlparse

from physicianx.url import normalize_url
from physicianx.web.host_limiter import HostLimiter
from physicianx.pipeline.stages.heuristics import check_job_listing_heuristics


class BFSCrawl:
    """
    Breadth-First Search deep crawling strategy.

    Core functions:
      - arun: Main entry point; splits execution into batch or stream modes.
      - link_discovery: Extracts, filters, and (if needed) scores the outgoing URLs.
      - can_process_url: Validates URL format and applies the filter chain.
    """

    def __init__(
        self,
        start_url: str,
        max_depth: int,
        crawler: AsyncWebCrawler,
        include_external: bool = False,
    ):
        self.crawler = crawler
        self.start_url = start_url
        self.max_depth = max_depth
        self.include_external = include_external
        self._cancel_event = asyncio.Event()
        self._pages_crawled = 0
        self.session_id = f"session_crawl_{start_url}"
        self.logger = logging.getLogger(__name__)
        self.JOB_KEYWORDS = {
            "career": 1,
            "job": 1,
            "opportunit": 2,
            "position": 2,
            "vacanc": 3,
        }
        self.JOB_PATTERNS = re.compile(
            r"(?i)"
            r"("
            r"(?:career|job|position|employment|search|apply|opportunit)(?:s|y|ies)?"
            r"|search_query=[^&]*?(?:job|career|opportunity)[^&]*"
            r"|join.*?(team|us)"
            r"|(?:open|opening|view).*?jobs"
            r"|/jobs\?(?:[^#\s]+)?"
            r"|(?:jobs?|careers?|vacancies|openings?|employment)"
            r")",
            re.IGNORECASE,
        )

    def prioritizeUrls(self, downstream_url: str, url_content: str | None) -> str | None:
        prioritized_url = None

        if re.search(self.JOB_PATTERNS, downstream_url) or (
            url_content is not None and re.search(self.JOB_PATTERNS, url_content)
        ):
            prioritized_url = downstream_url

        return prioritized_url

    def can_process_url(self, url: str, base_url: str, source_url: str) -> bool:
        url = url.strip()
        try:
            parsed = urlparse(base_url)
            parsed_source = urlparse(source_url)
            if not url:
                raise ValueError("Not a valid href")
            if url.startswith("#"):
                raise ValueError("Points to same page")

            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Missing scheme or netloc")
            if parsed.scheme not in ("http", "https"):
                raise ValueError("Invalid scheme")
            if "." not in parsed.netloc:
                raise ValueError("Invalid domain")
            if (
                parsed_source.scheme == parsed.scheme
                and parsed_source.netloc == parsed.netloc
                and parsed_source.path.rstrip("/") == parsed.path.rstrip("/")
            ):
                raise ValueError("Same page")
        except Exception:
            return False

        return True

    async def link_discovery(
        self,
        result: CrawlResult,
        source_url: str,
        current_depth: int,
        visited: Set[str],
        next_level: List[Tuple[str, Optional[str], int]],
    ) -> list:
        score, debug_info = check_job_listing_heuristics(result.html, source_url)
        is_job_listing = True if score > 3 else False
        job_listing_metadata = None
        next_depth = current_depth + 1
        if next_depth <= self.max_depth:
            links = result.links.get("internal", [])

            if self.include_external:
                links += result.links.get("external", [])
            valid_links = []
            for link in links:
                url = link.get("href")
                context = link.get("text")
                base_url = normalize_url(url, source_url)
                if base_url in visited:
                    continue
                if not self.can_process_url(url, base_url, source_url):
                    continue
                else:
                    valid_links.append((url, context))
            for url, ctx in valid_links:
                if len(next_level) > int(os.getenv("MAX_URLS_ON_LEVEL", "10000")):
                    break
                prioritized_url = self.prioritizeUrls(url, ctx)
                if prioritized_url is not None:
                    next_level.append((prioritized_url, source_url, next_depth))
        return [score, debug_info, is_job_listing, job_listing_metadata]

    async def _arun_batch(
        self,
        config: CrawlerRunConfig,
        max_concurrent: int,
    ) -> dict[str, Any] | None:
        visited: Set[str] = set()
        current_level: List[Tuple[str, Optional[str], int]] = [(self.start_url, None, 0)]
        results: List[dict[str, Any]] = []
        depth_bfs = 0
        remove_duplicates: Set[str] = set()
        seed_url_hash = str(hashlib.md5(self.start_url.encode("utf-8")).hexdigest())

        while current_level and not self._cancel_event.is_set():
            next_level: List[Tuple[str, Optional[str], int]] = []
            urls_depth = [(url, depth) for url, _, depth in current_level]
            visited.update([url for url, _ in urls_depth])
            print("level==============", depth_bfs, current_level)

            self.session_id = seed_url_hash + str(depth_bfs)
            batch_config = config.clone(
                deep_crawl_strategy=None,
                stream=False,
                session_ids=self.session_id,
            )
            for i in range(0, len(urls_depth), max_concurrent):
                batch = urls_depth[i : i + max_concurrent]
                dispatcher = MemoryAdaptiveDispatcher(
                    memory_threshold_percent=90.0,
                    check_interval=5.0,
                    max_session_permit=20,
                    monitor=None,
                )
                urls_list = [b[0] for b in batch]
                for u in urls_list:
                    await self._host_limiter.acquire(u)
                try:
                    result_batch = await self.crawler.arun_many(
                        urls=urls_list,
                        config=batch_config,
                        dispatcher=dispatcher,
                    )
                finally:
                    for u in urls_list:
                        self._host_limiter.release(u)

                discovery_tasks = []
                for (url, depth), result in zip(batch, result_batch):
                    if isinstance(result, Exception):
                        print("Error parsing url {}".format(url))
                    elif result.success:
                        url = result.url
                        print("success", url)
                        task = asyncio.create_task(
                            self.link_discovery(result, url, depth, visited, next_level)
                        )
                        discovery_tasks.append((result, task))
                results_with_discovery = await asyncio.gather(
                    *[t[1] for t in discovery_tasks], return_exceptions=True
                )
                for (result, discovery), unpacked in zip(discovery_tasks, results_with_discovery):
                    if isinstance(unpacked, Exception):
                        continue
                    score, debug_info, is_job_listing, job_listing_metadata = unpacked
                    result_metadata = {
                        "html": result.html,
                        "cleaned_html": result.cleaned_html,
                        "url": result.url,
                        "depth": depth_bfs,
                        "debug_info": debug_info,
                        "is_job_listing": is_job_listing,
                        "job_listing_score": score,
                        "job_listing_metadata": job_listing_metadata,
                    }
                    result.html = None
                    result.links = None
                    results.append(result_metadata)

            filtered_next_level = []
            for url, source_url, depth in next_level:
                if url not in remove_duplicates:
                    remove_duplicates.add(url)
                    filtered_next_level.append((url, source_url, depth))
            await self.clean_up_sessions(self.session_id)
            current_level = filtered_next_level
            print(f"----------------FINISHED CRAWLING URLS AT LEVEL {depth_bfs}--------------------------------")
            depth_bfs += 1

        results_sorted_by_highest_score = sorted(
            results, key=lambda x: (-x["job_listing_score"], len(x["url"]))
        )

        for r in results_sorted_by_highest_score:
            print(f"{r['url']}, {r['job_listing_score']},{r['debug_info']}")
        del results
        job_listing_info = results_sorted_by_highest_score[0] if results_sorted_by_highest_score else None
        del results_sorted_by_highest_score
        if job_listing_info and job_listing_info["is_job_listing"]:
            return job_listing_info
        else:
            return None

    async def clean_up_sessions(self, *sessions: str) -> None:
        for session in sessions:
            await self.crawler.crawler_strategy.kill_session(session)
