from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Any, List, Optional, Set, Tuple

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CrawlResult, MemoryAdaptiveDispatcher
from urllib.parse import urlparse

from jobweaver.url import normalize_url
from jobweaver.web.host_limiter import HostLimiter
from jobweaver.pipeline.stages.heuristics import check_job_listing_heuristics


JOB_PATTERNS = re.compile(
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


class BFSCrawl:
    """Breadth-First Search crawl with job-listing URL prioritization and per-page heuristic scoring."""

    def __init__(
        self,
        start_url: str,
        max_depth: int,
        crawler: AsyncWebCrawler,
        include_external: bool = False,
        max_pages_per_host: int = 5,
        max_urls_per_level: int = 10000,
    ):
        self.crawler = crawler
        self.start_url = start_url
        self.max_depth = max_depth
        self.include_external = include_external
        self.max_urls_per_level = max_urls_per_level
        self._cancel_event = asyncio.Event()
        self.session_id = f"session_crawl_{start_url}"
        self.logger = logging.getLogger(__name__)
        self._host_limiter = HostLimiter(max_pages_per_host)

    def prioritizeUrls(self, downstream_url: str, url_content: str | None) -> str | None:
        if JOB_PATTERNS.search(downstream_url) or (
            url_content is not None and JOB_PATTERNS.search(url_content)
        ):
            return downstream_url
        return None

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

    def link_discovery(
        self,
        result: CrawlResult,
        source_url: str,
        current_depth: int,
        visited: Set[str],
        next_level: List[Tuple[str, Optional[str], int]],
    ) -> list:
        score, debug_info = check_job_listing_heuristics(result.html, source_url)
        is_job_listing = score > 3
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
                valid_links.append((url, context))
            for url, ctx in valid_links:
                if len(next_level) > self.max_urls_per_level:
                    break
                prioritized = self.prioritizeUrls(url, ctx)
                if prioritized is not None:
                    next_level.append((prioritized, source_url, next_depth))
        return [score, debug_info, is_job_listing, None]

    async def _fetch_batch(
        self, urls_list: list[str], batch_config: CrawlerRunConfig
    ) -> list:
        dispatcher = MemoryAdaptiveDispatcher(
            memory_threshold_percent=90.0,
            check_interval=5.0,
            max_session_permit=20,
            monitor=None,
        )
        for u in urls_list:
            await self._host_limiter.acquire(u)
        try:
            return await self.crawler.arun_many(
                urls=urls_list, config=batch_config, dispatcher=dispatcher
            )
        finally:
            for u in urls_list:
                self._host_limiter.release(u)

    async def _score_batch(
        self,
        batch: list[Tuple[str, int]],
        fetched: list,
        depth_bfs: int,
        visited: Set[str],
        next_level: List[Tuple[str, Optional[str], int]],
    ) -> list[dict[str, Any]]:
        scored: list[dict[str, Any]] = []
        for (url, depth), result in zip(batch, fetched):
            if isinstance(result, Exception):
                self.logger.warning("Error parsing url %s: %s", url, result)
                continue
            if not result.success:
                continue
            self.logger.debug("crawled %s", result.url)
            try:
                score, debug_info, is_job_listing, job_listing_metadata = self.link_discovery(
                    result, result.url, depth, visited, next_level
                )
            except Exception as exc:
                self.logger.warning("link_discovery failed for %s: %s", result.url, exc)
                continue
            scored.append(
                {
                    "html": result.html,
                    "cleaned_html": result.cleaned_html,
                    "url": result.url,
                    "depth": depth_bfs,
                    "debug_info": debug_info,
                    "is_job_listing": is_job_listing,
                    "job_listing_score": score,
                    "job_listing_metadata": job_listing_metadata,
                }
            )
            result.html = None
            result.links = None
        return scored

    @staticmethod
    def _dedupe_next_level(
        next_level: List[Tuple[str, Optional[str], int]],
        seen: Set[str],
    ) -> List[Tuple[str, Optional[str], int]]:
        deduped: List[Tuple[str, Optional[str], int]] = []
        for url, source_url, depth in next_level:
            if url in seen:
                continue
            seen.add(url)
            deduped.append((url, source_url, depth))
        return deduped

    async def _arun_batch(
        self,
        config: CrawlerRunConfig,
        max_concurrent: int,
    ) -> dict[str, Any] | None:
        visited: Set[str] = set()
        current_level: List[Tuple[str, Optional[str], int]] = [(self.start_url, None, 0)]
        results: List[dict[str, Any]] = []
        depth_bfs = 0
        seen_in_next_level: Set[str] = set()
        seed_url_hash = hashlib.md5(self.start_url.encode("utf-8")).hexdigest()

        while current_level and not self._cancel_event.is_set():
            next_level: List[Tuple[str, Optional[str], int]] = []
            urls_depth = [(url, depth) for url, _, depth in current_level]
            visited.update(url for url, _ in urls_depth)
            self.logger.info("BFS level %s: %d urls", depth_bfs, len(current_level))

            self.session_id = seed_url_hash + str(depth_bfs)
            batch_config = config.clone(
                deep_crawl_strategy=None, stream=False, session_ids=self.session_id
            )

            for i in range(0, len(urls_depth), max_concurrent):
                batch = urls_depth[i : i + max_concurrent]
                fetched = await self._fetch_batch([u for u, _ in batch], batch_config)
                results.extend(
                    await self._score_batch(batch, fetched, depth_bfs, visited, next_level)
                )

            current_level = self._dedupe_next_level(next_level, seen_in_next_level)
            await self.clean_up_sessions(self.session_id)
            self.logger.info("finished BFS level %s", depth_bfs)
            depth_bfs += 1

        ranked = sorted(results, key=lambda x: (-x["job_listing_score"], len(x["url"])))
        for r in ranked:
            self.logger.debug(
                "scored %s score=%s debug=%s", r["url"], r["job_listing_score"], r["debug_info"]
            )
        top = ranked[0] if ranked else None
        return top if top and top["is_job_listing"] else None

    async def clean_up_sessions(self, *sessions: str) -> None:
        for session in sessions:
            await self.crawler.crawler_strategy.kill_session(session)
