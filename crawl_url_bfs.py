import asyncio
from typing import Set, List, Optional, Tuple, Dict
import logging
from urllib.parse import urlparse
from crawl4ai import CrawlResult, AsyncWebCrawler, CrawlerRunConfig
from utils.normalize_url import normalize_url
import regex as re
from Heuristic_search import check_job_listing_heuristics


class BFSCrawl():
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
            include_external: bool = False
    ):
        self.start_url = start_url
        self.max_depth = max_depth
        self.include_external = include_external
        self._cancel_event = asyncio.Event()
        self._pages_crawled = 0
        self.logger = logging.getLogger(__name__)
        self.JOB_KEYWORDS = {
            'career': 1,
            'job': 1,
            'opportunit': 2,
            'position': 2,
            'vacanc': 3
        }
        self.JOB_PATTERNS = re.compile(
            r'(?i)'  # Case-insensitive
            r'(?:career|job|position|employment|opportunit)(?:s|y|ies)?/'  # Matches "career/jobs/", "opportunity/"
            r'|\b(?:job|career|opening|position|opportunity)s?\b'  # Matches words like "jobs", "career", "openings"
            r'|search_query=([^&]*?(?:job|career|opportunity)[^&]*)'  # Matches search queries containing "job" or "career"
            r'|\bjoin\b.*?\b(?:team|us)\b'  # Matches "join our team"
            r'|(?=.*\b(?:open|openings|view)\b)(?=.*\bjobs\b).*'  # Matches URLs containing "open jobs"
            r'|/jobs\?(?:[^#\s]+)?'
            r'|\b(careers? | jobs? | vacancies | openings? |employment?| opportunities | search jobs? | job listings? | positions? available | current openings? | find a job | explore roles)\b')

    async def prioritizeUrls(self, downstream_url, url_content):
        prioritized_url = None

        if re.search(self.JOB_PATTERNS, downstream_url) or (
                url_content is not None and re.search(self.JOB_PATTERNS, url_content)):
            prioritized_url = downstream_url

        return prioritized_url

    async def can_process_url(self, url: str, depth: int) -> bool:
        """
        Validates the URL and applies the filter chain.
        For the start URL (depth 0) filtering is bypassed.
        """
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Missing scheme or netloc")
            if parsed.scheme not in ("http", "https"):
                raise ValueError("Invalid scheme")
            if "." not in parsed.netloc:
                raise ValueError("Invalid domain")
        except Exception as e:
            return False

        return True

    async def link_discovery(
            self,
            result: CrawlResult,
            source_url: str,
            current_depth: int,
            visited: Set[str],
            next_level: List[Tuple[str, Optional[str], int]],
            depths: Dict[str, int],
    ) -> [float,list, bool]:
        """
        Extracts links from the crawl result, validates and scores them, and
        prepares the next level of URLs.
        Each valid URL is appended to next_level as a tuple (url, parent_url)
        and its depth is tracked.
        """
        next_depth = current_depth + 1
        if next_depth > self.max_depth:
            return [0,{}, False]
        score,debug_info = check_job_listing_heuristics(result.html,source_url)
        isJoblisting = True if score > 3.0 else False

        links = result.links.get("internal", [])

        if self.include_external:
            links += result.links.get("external", [])
        valid_links = []
        remove_duplicates = set()
        for link in links:
            url = link.get("href")
            context = link.get("text")
            base_url = normalize_url(url, source_url)
            if base_url in visited:
                continue
            if not await self.can_process_url(url, next_depth):
                continue
            else:
                valid_links.append((url, context))

        for url, ctx in valid_links:
            # attach the score to metadata if needed
            prioritizedUrl = await self.prioritizeUrls(url, ctx)
            if prioritizedUrl is not None:
                next_level.append((prioritizedUrl, source_url, next_depth))
                # depths[url] = next_depth
        return [score,debug_info,isJoblisting]

    async def _arun_batch(
            self,
            start_url: str,
            crawler: AsyncWebCrawler,
            config: CrawlerRunConfig,
            max_concurrent: int
    ) -> List[CrawlResult]:
        """
        Batch (non-streaming) mode:
        Processes one BFS level at a time, then yields all the results.
        """
        visited: Set[str] = set()
        # current_level holds tuples: (url, parent_url)
        current_level: List[Tuple[str, Optional[str], int]] = [(self.start_url, None, 0)]
        depths: Dict[str, int] = {start_url: 0}

        results: List[CrawlResult] = []
        remove_duplicates = set()
        while current_level and not self._cancel_event.is_set():
            next_level: List[Tuple[str, Optional[str], int]] = []
            urls_depth = [(url, depth) for url, _, depth in current_level]
            urls = [url for url, _ in urls_depth]
            visited.update(urls)
            # Clone the config to disable deep crawling recursion and enforce batch mode.
            batch_config = config.clone(deep_crawl_strategy=None, stream=False)

            for i in range(0, len(urls_depth), max_concurrent):
                batch = urls_depth[i:i + max_concurrent]
                print(len(batch))
                tasks = []
                for j, (url, depth) in enumerate(batch):
                    session_id = (
                        f"parallel_session_{j}"  # Different session per concurrent task
                    )
                    task = crawler.arun(url=url, config=batch_config, session_id=session_id)
                    tasks.append(task)
                print("start tasks")
                result_batch = await asyncio.gather(*tasks, return_exceptions=True)
                print("end tasks")
                for (url, depth), result in zip(batch, result_batch):
                    # depth = depths.get(url)
                    if isinstance(result, Exception):
                        print("Error parsing url {}".format(url))
                    elif result.success:
                        url = result.url
                        # print(result.html)
                        result.metadata = result.metadata or {}
                        result.metadata["depth"] = depth
                        parent_url = next((parent for (u, parent, depth) in current_level if u == url), None)
                        result.metadata["parent_url"] = parent_url
                        results.append(result)

                        score,debug_info, is_job_listing = await self.link_discovery(result, url, depth, visited, next_level,
                                                                          depths)
                        result.metadata['isJobListing'] = is_job_listing
                        result.metadata['score'] = score
                        result.metadata["debug_info"]=debug_info
                        self._pages_crawled += 1

            filtered_next_level = []
            for url, source_url, depth in next_level:
                if url not in remove_duplicates:
                    remove_duplicates.add(url)
                    filtered_next_level.append((url, source_url, depth))
                    print(url, depth)

            current_level = filtered_next_level
            print(
                "-------------------------------------------------------------------------------------------------------")
        for result in results:
            if result.metadata['score']>=2.5:
                # print(result.html)
                print(f"{result.url} {result.metadata['depth']} {result.metadata['score']} {result.metadata['debug_info']}")
        print(self._pages_crawled)

        return results
