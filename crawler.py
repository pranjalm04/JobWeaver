import asyncio, csv
from typing import List, Dict
from dotenv import load_dotenv
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl_url_bfs import BFSCrawl  # ← your class
from google import genai
import os
from utils.job_listing_llm_preprocess import analyze_full_html_with_llm
MAX_SEEDS_IN_FLIGHT = 100
MAX_PAGES_GLOBAL = 250
MAX_PAGES_PER_SEED = 50
MAX_DEPTH = 2


class crawlJobs():

    def __init__(self):
        self.crawler: AsyncWebCrawler = None
        self.BROWSER_CFG = BrowserConfig(
            browser_type="chromium",
            headless=True,
            viewport={
                "width": 1920,
                "height": 1080,
            },
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/116.0.0.0 Safari/537.36",
        )
        self.RUN_CFG = CrawlerRunConfig(
            wait_until="load",
            excluded_tags=["style", "script"],
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
        self.client = genai.Client(api_key=os.getenv("API_KEY_GEMINI"))

        self.SEED_URLS = ['https://nrothandrehab.com', 'https://wythephysicianpractices.com',
                          'https://careers.uhhospitals.org']
        # semaphores
        self.seed_sem = asyncio.Semaphore(MAX_SEEDS_IN_FLIGHT)
        self.page_sem = asyncio.Semaphore(MAX_PAGES_GLOBAL)

    def patch_page_semaphore(self) -> None:
        """Wrap crawler.arun so every Playwright call grabs `page_sem`."""
        orig = self.crawler.arun
        async def safe_arun(*args, **kwargs):
            async with self.page_sem:
                return await orig(*args, **kwargs)
        self.crawler.arun = safe_arun

    async def crawl_seed(self, seed: str) -> None:
        """Run one BFSCrawl instance and handle its single‑dict result."""
        async with self.seed_sem:  # limit concurrent seeds
            bfs = BFSCrawl(seed, MAX_DEPTH, include_external=True)
            rec = await bfs._arun_batch(self.crawler, self.RUN_CFG, MAX_PAGES_PER_SEED)
            await self.handle_result(rec)

    async def handle_result(self, rec: [Dict[str, any] or None]) -> None:
        """Persist / print the first (best) result returned by your BFS."""
        if not rec:
            return
        llm_res=await analyze_full_html_with_llm(rec['html'],rec['url'],self.client)
        if llm_res is not None:
            import json
            with open('llm_outputs.json', "a", encoding="utf-8") as f:
                json.dump(llm_res, f, ensure_ascii=False)
                f.write("\n")
        print(f"{rec['job_listing_score']:4.1f}  {rec['url']}")


    async def main(self) -> None:
        async with AsyncWebCrawler(config=self.BROWSER_CFG) as crawlerbfs:
            self.crawler=crawlerbfs
            self.patch_page_semaphore()
            tasks = [asyncio.create_task(self.crawl_seed(s)) for s in self.SEED_URLS]
            # stream completions; propagates exceptions immediately
            for fut in asyncio.as_completed(tasks):
                try:
                    await fut
                except Exception as exc:
                    print("[ERR]", exc)


if __name__ == "__main__":
    load_dotenv('config.env')
    crawler=crawlJobs()
    asyncio.run(crawler.main())
