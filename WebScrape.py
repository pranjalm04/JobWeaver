from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
import regex as re
from crawl_url_bfs import BFSCrawl

from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from utils.job_listing_llm_preprocess import analyze_full_html_with_llm
from dotenv import load_dotenv
import asyncio
from Pagination import extract_job_data
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
    threshold=0.1,
    threshold_type="dynamic",
    min_word_threshold=5
)

# Step 2: Insert it into a Markdown Generator
md_generator = DefaultMarkdownGenerator(content_filter=prune_filter)
run_cfg = CrawlerRunConfig(
    wait_until="load",
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
    load_dotenv('config.env')
    crawler: AsyncWebCrawler = AsyncWebCrawler(config=browser_cfg)
    await crawler.start()
    """inspect this site"""
    start_url="https://careers.uhhospitals.org"
    crawl: BFSCrawl=BFSCrawl(start_url=start_url,max_depth=2,include_external=True)
    results=await crawl._arun_batch(crawler,run_cfg,50)


    print(f"results {results['url']} {results['job_listing_score']} {results['debug_info']}")
    print("#############################################################")
    # job_listing_details=analyze_full_html_with_llm(results["html"],results["url"])
    # print(job_listing_details)
    url="https://jobs.lifepointhealth.net/search-jobs?acm=ALL&alrpm=ALL&ascf=[%7B%22key%22:%22is_manager%22,%22value%22:%22Wythe+County+Community+Hospital%22%7D]"
    await crawler.close()

if __name__ =="__main__":
    asyncio.run(main())
    # job_listing_structured_details = {'is_job_listing': True, 'score': 7, 'has_pagination': True, 'next_page_element': {'text': 'Next', 'href': '/search-jobs&p=2', 'selector': 'a.next'}, 'individual_job_links': [{'href': '/job/wytheville/coord-nursing/40921/80058528176', 'text': 'Coord-Nursing', 'selector': 'a[data-job-id]'}, {'href': '/job/wytheville/dir-human-resources/40921/80050633264', 'text': 'Dir-Human Resources', 'selector': 'a[data-job-id]'}, {'href': '/job/wytheville/registrar/40921/80050633248', 'text': 'Registrar', 'selector': 'a[data-job-id]'}, {'href': '/job/wytheville/hr-specialist/40921/79766919056', 'text': 'HR Specialist', 'selector': 'a[data-job-id]'}, {'href': '/job/wytheville/maintenance-mechanic/40921/71470795504', 'text': 'Maintenance Mechanic', 'selector': 'a[data-job-id]'}, {'href': '/job/wytheville/rn-womens-svcs/40921/78743038112', 'text': 'RN-Womens Svcs', 'selector': 'a[data-job-id]'}, {'href': '/job/wytheville/nurse-tech/40921/67946461200', 'text': 'Nurse Tech', 'selector': 'a[data-job-id]'}, {'href': '/job/wytheville/er-monitor-tech/40921/77941840512', 'text': 'ER/Monitor Tech', 'selector': 'a[data-job-id]'}, {'href': '/job/wytheville/radiology-tech-prn/40921/74080251520', 'text': 'Radiology Tech PRN', 'selector': 'a[data-job-id]'}, {'href': '/job/wytheville/medical-asst-prn/40921/76957525888', 'text': 'Medical Asst PRN', 'selector': 'a[data-job-id]'}, {'href': '/job/wytheville/multi-modality-tech/40921/73624767136', 'text': 'Multi-Modality Tech', 'selector': 'a[data-job-id]'}, {'href': '/job/wytheville/ultrasound-tech-prn/40921/73624766752', 'text': 'Ultrasound Tech PRN', 'selector': 'a[data-job-id]'}, {'href': '/job/wytheville/coord-accounting/40921/78705600080', 'text': 'Coord-Accounting', 'selector': 'a[data-job-id]'}, {'href': '/job/wytheville/medical-asst-prn/40921/76957521488', 'text': 'Medical Asst PRN', 'selector': 'a[data-job-id]'}, {'href': '/job/wytheville/lpn-prn/40921/67196649632', 'text': 'LPN PRN', 'selector': 'a[data-job-id]'}, {'href': '/job/las-cruces/sonographer-diagnostic-imaging-center/40921/80259791472', 'text': 'Sonographer Diagnostic Imaging Center', 'selector': 'a[data-job-id]'}, {'href': '/job/las-cruces/mammographer-diagnostic-imaging-center/40921/80259791184', 'text': 'Mammographer Diagnostic Imaging Center', 'selector': 'a[data-job-id]'}, {'href': '/job/danville/front-office-representative-chc/40921/80259790384', 'text': 'Front Office Representative - CHC', 'selector': 'a[data-job-id]'}], 'total_token_count': 24708}

    # extract_job_data(job_listing_structured_details)