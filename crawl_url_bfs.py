import asyncio
from typing import Set, List, Optional, Tuple, Dict
import logging
from urllib.parse import urlparse
from crawl4ai import CrawlResult, AsyncWebCrawler, CrawlerRunConfig
from utils.normalize_url import normalize_url,url_diff
import regex as re
# from cosine_similarity import calculate_cosine_similarity_score
from Heuristic_search import check_job_listing_heuristics
from utils.job_listing_llm_preprocess import analyze_full_html_with_llm
import os

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
            r'(?i)'  # case-insensitive
            r'('
            r'(?:career|job|position|employment|opportunit)(?:s|y|ies)?'  # matches "career", "careers", "opportunity"
            r'|search_query=[^&]*?(?:job|career|opportunity)[^&]*'  # search queries
            r'|join.*?(team|us)'  # "join our team"
            r'|(?:open|opening|view).*?jobs'  # "open jobs"
            r'|/jobs\?(?:[^#\s]+)?'  # "/jobs?..."  # catch specific domain with careers
            r'|(?:jobs?|careers?|vacancies|openings?|employment)'
            r')',
            re.IGNORECASE
        )

    def prioritizeUrls(self, downstream_url, url_content):
        prioritized_url = None

        if re.search(self.JOB_PATTERNS, downstream_url) or (
                url_content is not None and re.search(self.JOB_PATTERNS, url_content)):
            prioritized_url = downstream_url

        return prioritized_url

    def can_process_url(self, url:str,base_url: str, source_url : str) -> bool:
        """
        Validates the URL and applies the filter chain.
        For the start URL (depth 0) filtering is bypassed.
        """
        url=url.strip()
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
                    parsed_source.scheme == parsed.scheme and
                    parsed_source.netloc == parsed.netloc and
                    parsed_source.path.rstrip("/") == parsed.path.rstrip("/")
            ):
                raise ValueError("Same page")
        except Exception as e:
            return False

        return True

    async def link_discovery(
            self,
            result: CrawlResult,
            source_url: str,
            current_depth: int,
            visited: Set[str],
            next_level: List[Tuple[str, Optional[str], int]]
    ) -> [float, list, bool]:
        """
        Extracts links from the crawl result, validates and scores them, and
        prepares the next level of URLs.
        Each valid URL is appended to next_level as a tuple (url, parent_url)
        and its depth is tracked.
        """
        score, debug_info = check_job_listing_heuristics(result.html, source_url)
        is_job_listing = True if score > 3 else False
        job_listing_metadata=None
        # if is_job_listing:
        #     try:
        #         job_listing_metadata = analyze_full_html_with_llm(result.html, source_url)
        #         print(source_url, job_listing_metadata)
        #     except Exception as e:
        #         print("error while getting response from llm", e)
        next_depth = current_depth + 1
        if next_depth <= self.max_depth:
            # print(result.html)
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
                if not self.can_process_url(url,base_url, source_url):
                    continue
                else:
                    valid_links.append((url, context))

            for url, ctx in valid_links:
                # attach the score to metadata if needed
                if len(next_level) > int(os.getenv("MAX_URLS_ON_LEVEL")):
                    break
                prioritized_url = self.prioritizeUrls(url, ctx)
                if prioritized_url is not None:
                    next_level.append((prioritized_url, source_url, next_depth))
        return [score, debug_info, is_job_listing,job_listing_metadata]

    async def _arun_batch(
            self,
            crawler: AsyncWebCrawler,
            config: CrawlerRunConfig,
            max_concurrent: int
    ) -> [dict[str,any] or None]:
        """
        Batch (non-streaming) mode:
        Processes one BFS level at a time, then yields all the results.
        """
        visited: Set[str] = set()
        current_level: List[Tuple[str, Optional[str], int]] = [(self.start_url, None, 0)]
        results: List[dict[str,any]] = []
        depth_bfs=0
        remove_duplicates = set()
        while current_level and not self._cancel_event.is_set():

            next_level: List[Tuple[str, Optional[str], int]] = []
            urls_depth = [(url, depth) for url, _, depth in current_level]
            urls = [url for url, _ in urls_depth]
            visited.update(urls)
            print("level==============", depth_bfs)
            # Clone the config to disable deep crawling recursion and enforce batch mode.
            batch_config = config.clone(deep_crawl_strategy=None, stream=False)
            for i in range(0, len(urls_depth), max_concurrent):
                batch = urls_depth[i:i + max_concurrent]
                tasks = []
                for j, (url, depth) in enumerate(batch):
                    session_id = (
                        f"parallel_session_{j}"  # Different session per concurrent task
                    )
                    task = crawler.arun(url=url, config=batch_config, session_id=session_id)
                    tasks.append(task)
                print(f"starting {len(tasks)} tasks............")
                result_batch = await asyncio.gather(*tasks, return_exceptions=True)
                print("end tasks")
                discovery_tasks = []
                for (url, depth), result in zip(batch, result_batch):
                    if isinstance(result, Exception):
                        print("Error parsing url {}".format(url))
                    elif result.success:
                        url = result.url
                        parent_url = next((parent for (u, parent, depth) in current_level if u == url), None)
                        task = self.link_discovery(result, url, depth, visited, next_level)
                        discovery_tasks.append((result, task))
                results_with_discovery = await asyncio.gather(*[t[1] for t in discovery_tasks], return_exceptions=True)
                for (result, discovery), (score, debug_info, is_job_listing,job_listing_metadata) in zip(discovery_tasks,
                                                                                    results_with_discovery):
                    if isinstance((score, debug_info, is_job_listing), Exception):
                        continue
                    result_metadata={
                        "html":result.html,
                        "url": result.url,
                        "depth":depth_bfs,
                        "debug_info": debug_info,
                        "is_job_listing": is_job_listing,
                        "job_listing_score": score,
                        "job_listing_metadata":job_listing_metadata
                    }
                    result.html=None
                    result.links=None
                    results.append(result_metadata)

            filtered_next_level = []
            for url, source_url, depth in next_level:
                if url not in remove_duplicates:
                    remove_duplicates.add(url)
                    filtered_next_level.append((url, source_url, depth))

            current_level = filtered_next_level
            print(f"----------------FINISHED CRAWLING URLS AT LEVEL {depth_bfs}--------------------------------")
            depth_bfs+=1

        results=sorted(results,key=lambda x:(-x['job_listing_score'],len(x["url"])))
        # for i,result in enumerate(results):
        #     if i<5:
        #         print(result["url"],result["job_listing_score"],result["debug_info"])
        return results[0] if results else None
