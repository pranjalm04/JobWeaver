import requests
from bs4 import BeautifulSoup
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
import asyncio
from utils.job_listing_llm_preprocess import extract_minified_body_html
from Heuristic_search import check_job_listing_heuristics

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


async def main():
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
        wait_until="networkidle",
        excluded_tags=["style"],
        exclude_external_links=False,
        markdown_generator=md_generator,
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
    import tiktoken
    crawler: AsyncWebCrawler = AsyncWebCrawler(config=browser_cfg)
    await crawler.start()
    """inspect this site"""
    start_url="https://jobs.unchealthcare.org/search/jobs"
    encoding = tiktoken.get_encoding("cl100k_base")
    results=await crawler.arun(url=start_url,config=run_cfg)

    try:
        if results.success:



            final_score,debug_info=check_job_listing_heuristics(results.html,url=start_url)

            print(final_score, debug_info)
            # --- Count the tokens ---

            # print(parsed_html_str)
    except Exception as e:
        print(f"[Error] BeautifulSoup Parsing Error: {e}")
        return 0.0 # Cannot parse
    common_selectors = ['div[class*="job"]', 'li[class*="job"]', 'article[class*="job"]',
                        'div[class*="result"]', 'li[class*="result"]', 'div[class*="item"]',
                        'div[class*="card"]', 'div[class*="Career"]', 'tr[class*="job"]',
                        'article[class*="career"]']
    common_selectors=[("div","job"),("li","job"),("article","job"),("div","result"),("li","result"),("div","item"),("div","card"), \
                      ("div","Career"),("tr","job"),("article","career")]           # Added table row
    potential_items = {}


    await crawler.close()
if __name__ =="__main__":
    asyncio.run(main())


