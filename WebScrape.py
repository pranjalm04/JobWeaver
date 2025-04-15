from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode, KeywordRelevanceScorer, \
    LXMLWebScrapingStrategy, FilterChain, URLPatternFilter, BM25ContentFilter,URLScorer
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy,DFSDeepCrawlStrategy ,BestFirstCrawlingStrategy, ContentRelevanceFilter
from concurrent.futures import ThreadPoolExecutor
from crawl4ai.deep_crawling.scorers import ContentTypeScorer
import regex as re
from crawl_url_bfs import BFSCrawl

import asyncio
browser_cfg = BrowserConfig(
    browser_type="chromium",
    headless=True,
    # browser_args=["--disable-gpu","--disable-dev-shm-usage", "--no-sandbox"],
    viewport={
        "width": 1920,
        "height": 1080,
    },
    user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/116.0.0.0 Safari/537.36",
)

run_cfg = CrawlerRunConfig(
    wait_until="domcontentloaded",
    excluded_tags=["style","script"],
    exclude_external_links=False,
    # stream=True,  # Enable streaming for arun_many()
    cache_mode=CacheMode.DISABLED,
    # semaphore_count=10,
    process_iframes=True,
    remove_overlay_elements=True,
    exclude_external_images=True,
    exclude_social_media_links=True,
    verbose=False,
    log_console=False
)
async def main():

    crawler: AsyncWebCrawler = AsyncWebCrawler(config=browser_cfg)
    await crawler.start()
    """inspect this site"""
    start_url="https://lutheranhospital.com"
    crawl=BFSCrawl(start_url=start_url,max_depth=4,include_external=True)
    results=await crawl._arun_batch(start_url,crawler,run_cfg,50)


    await crawler.close()
if __name__ =="__main__":
    asyncio.run(main())