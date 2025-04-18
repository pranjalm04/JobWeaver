from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
import regex as re
from crawl_url_bfs import BFSCrawl
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator


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
prune_filter = PruningContentFilter(
    # Lower → more content retained, higher → more content pruned
    threshold=0.2,
    # "fixed" or "dynamic"
    threshold_type="dynamic",
    # Ignore nodes with <5 words
    min_word_threshold=5
)

# Step 2: Insert it into a Markdown Generator
md_generator = DefaultMarkdownGenerator(content_filter=prune_filter)
run_cfg = CrawlerRunConfig(
    wait_until="domcontentloaded",
    excluded_tags=["style","script"],
    exclude_external_links=False,
    # stream=True,  # Enable streaming for arun_many()
    cache_mode=CacheMode.DISABLED,
    # semaphore_count=10,
    markdown_generator=md_generator,
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
    start_url="https://www.scripps.org"
    crawl=BFSCrawl(start_url=start_url,max_depth=2,include_external=True)
    results=await crawl._arun_batch(crawler,run_cfg,50)


    await crawler.close()
if __name__ =="__main__":
    asyncio.run(main())