import requests
from bs4 import BeautifulSoup
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode, KeywordRelevanceScorer, \
    LXMLWebScrapingStrategy, FilterChain, URLPatternFilter, BM25ContentFilter,URLScorer
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy,DFSDeepCrawlStrategy ,BestFirstCrawlingStrategy, ContentRelevanceFilter
from concurrent.futures import ThreadPoolExecutor
from crawl4ai.deep_crawling.scorers import ContentTypeScorer
import regex as re
from collections import Counter
from crawl_url_bfs import BFSCrawl
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
        wait_until="load",
        excluded_tags=["style", "script"],
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
    start_url="https://recruiting.ultipro.com/MEA1004MEVM/JobBoard/d561e1d3-aa5e-4c1b-bcf5-5319c6abdcac/OpportunityDetail?opportunityId=778ce4d3-1690-46cb-8aac-834b03160cfe"
    encoding = tiktoken.get_encoding("cl100k_base")
    results=await crawler.arun(url=start_url,config=run_cfg)

    try:
        if results.success:


            # print(extract_minified_body_html(results.html))
            markdown=results.markdown.raw_markdown
            # print(markdown)
            # print(results.markdown.fit_markdown)
            # soup = BeautifulSoup(results.html, 'html.parser')
            # parsed_html_str = soup.body
            print("$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")
            token_ids = encoding.encode(markdown)
            print("total token count", len(token_ids))
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
    for selector in common_selectors:
        try:
            career_elements = soup.find_all(selector[0], class_=re.compile(r'{}'.format(selector[1]), re.IGNORECASE))
            # items = soup.select(selector, limit=50)  # Use CSS selectors
            # print(career_elements)

            potential_items.extend(career_elements)

        except Exception:
            pass  # Ignore invalid selectors
    unique_items=[]
    for item in potential_items:
        unique_items.append(f"""<{item.name}{' '.join(f'{attr}="{value}"' for attr, value in item.attrs.items())}>...</{item.name}>""")
    # unique_items = list({item:  for item in potential_items})
    counts = Counter(unique_items)

    # for ui,val in counts.items():
        # print("unique_items",ui,val)
    # final_score,debug_info=check_job_listing_heuristics(results.html,start_url)
    # print(final_score,"  ",debug_info)

    await crawler.close()
if __name__ =="__main__":
    asyncio.run(main())


