import asyncio, csv
import logging
import time
from typing import List, Dict
import random
import aiofiles
from dotenv import load_dotenv
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawler_custom import BFSCrawl
from google import genai
import os
import json
from utils.jobs_extraction_llm import extract_job_data
from extract_jobs import scrape_jobs_to_dict
from utils.job_listing_llm_preprocess import analyze_full_html_with_llm
MAX_SEEDS_IN_FLIGHT = 100
MAX_PAGES_GLOBAL = 250
MAX_PAGES_PER_SEED = 50
MAX_DEPTH = 2
import pandas as pd

class crawlJobs():

    def __init__(self):
        self.crawler = None
        self.llm_tasks=[]
        self.record_tasks=[]
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
            wait_until="networkidle",
            excluded_tags=["style"],
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
        self.SEED_URLS=['https://jobs.unchealthcare.org/search/jobs']
        # self.SEED_URLS=random.sample(pd.read_csv("extras/Error Report_Untitled Page_Table.csv")['host'].tolist(),20)
        print(self.SEED_URLS)

        # self.SEED_URLS = ['https://chacareers.org','https://wgh.org','https://northstarfamilymedicine.org','https://realhealthclinic.com','https://orthonorman.com','https://wecareeyegroup.com','https://fallcreekvision.com','https://theneurologyfoundation.org','https://summitfacial.com','https://retinacarecenter.org','https://scenicbluffs.org','https://nycgyne.com','https://legacyrehab.net','https://vista-hc.com','https://dr4health.com','https://miller-pt.com','https://fairwayeyecenter.com','https://titusvillechiropractors.com','https://activemethodpt.com','https://rehabnj.net','https://sunrisetreatmentcenter.net','https://forneyeyeassociates.com','https://thrivelincoln.com','https://alluvionhealth.org','https://pacesetter-health.com','https://drgalen.org','https://reddentherapy.com','https://qsm.org','https://newdirectionsbrooklyn.com','https://tsowoodlands.com','https://crmd.net','https://nhcoregon.org','https://svpt.net','https://orindaoptometrygroup.com','https://parkviewcardiology.com','https://rmhsccn.org','https://nasamri.com','https://ohsu.edu','https://southsidepainspecialists.com','https://potomacanesthesia.com','https://theshepherdscenter.com','https://mainechiropractichealth.com','https://hqpt.com','https://newyorkcityspine.com','https://preventivefamilycare.com','https://ptnorthwest.com','https://northshoreeye.net','https://westcountyeyes.com','https://dentalimplantsandoralsurgery.com','https://sacramentospine.com','https://westchaseorthopaedics.com','https://rmchospital.com','https://saccoeyegroup.com','https://pardeehospital.org','https://waynesborofamilyclinic.com','https://seacoastrejuvenation.com','https://orthoneuro.com','https://drmartinperez.com','https://southpalmeye.net','https://rhnmd.com','https://osteopathic.nova.edu','https://rhoadtobeauty.com','https://onesourcesportsneuro.com','https://risingsunphysicaltherapy.com','https://pamelamorrisonpt.com','https://nybra.com','https://tsengaestheticsmd.com','https://northlakept.com','https://psyassociates.com','https://honorhealth.com','https://brownchiro.com','https://nwkchiro.com','https://cancercarespecialists.org','https://lighttouchrehab.com','https://ptprofessionals.net','https://oldbridgept.com','https://blvdchiro.com','https://lenapope.org','https://theheartgroupfresno.com','https://www.capecodhealth.org','https://sausalito-optometry.com','https://pureinternalmedicine.com','https://scrmc.com','https://westpaclab.com','https://orindamedicalgroup.com','https://mepkc.com','https://pinnacledermatology.com','https://yakutathealth.org','https://positiveimpacthealthcenters.org','https://olmmed.org','https://wacocenterforoms.com','https://psychphilly.com','https://orthocentercc.com','https://premierfsm.com','https://covingtonortho.com','https://orthonc.com','https://visionsource-mandeville.com','https://thefootinstitute.com','https://oneworldomaha.org','https://mcewyo.org','https://purechiropracticandwellness.com']
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
            bfs = BFSCrawl(seed, MAX_DEPTH, self.crawler, include_external=True)
            rec = await bfs._arun_batch(self.RUN_CFG, 50)
            await self.handle_result(rec,seed)

    async def handle_result(self, rec: [Dict[str, any] or None], seed: str) -> None:

        try:
            record = f"{seed} {rec['url']} {rec['job_listing_score']}" if rec else f"{seed} NA NA"

            if rec:

                task = asyncio.create_task(self.analyze_and_save_llm(rec['html'], rec['url']))
                self.llm_tasks.append(task)

            task = asyncio.create_task(self.save_record(record))
            self.record_tasks.append(task)

            if rec:
                print(f"[CRAWL] {rec['job_listing_score']:4.1f} {rec['url']}")

        except Exception as e:
            print(f"[HANDLE RESULT ERROR] General failure for seed {seed}: {e}")
    async def analyze_and_save_llm(self, html: str, url: str):
        """Analyze HTML with LLM and save output asynchronously."""
        try:
            llm_res = await analyze_full_html_with_llm(html, url, self.client)
            jobs=await scrape_jobs_to_dict(llm_res)
            logging.info(f"jobs extracted {len(jobs)}")
            await extract_job_data(self.crawler,[j['URL'] for j in jobs],self.RUN_CFG,self.client)

            if llm_res:
                async with aiofiles.open('llm_outputs.json', mode="a", encoding="utf-8") as f:
                    await f.write(json.dumps(llm_res, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[LLM SAVE ERROR] {url}: {e}")

    async def save_record(self, record: str):
        """Save basic crawl record asynchronously."""
        try:
            async with aiofiles.open('career_listings.txt', mode="a", encoding="utf-8") as f:
                await f.write(record + "\n")
        except Exception as e:
            print(f"[RECORD SAVE ERROR]: {e}")

    async def main(self) -> None:
        async with AsyncWebCrawler(config=self.BROWSER_CFG) as crawlerbfs:

            self.crawler = crawlerbfs
            await self.crawler.awarmup()
            self.patch_page_semaphore()
            tasks = [asyncio.create_task(self.crawl_seed(s)) for s in self.SEED_URLS]

            for fut in asyncio.as_completed(tasks):
                try:
                    await fut
                except Exception as exc:
                    print("[ERR]", exc)
            if self.llm_tasks:
                results = await asyncio.gather(*self.llm_tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception):
                        print(f"[LLM TASK ERROR]: {res}")
            if self.record_tasks:
                results = await asyncio.gather(*self.record_tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception):
                        print(f"[RECORD SAVE ERROR]: {res}")

if __name__ == "__main__":
    load_dotenv('config.env')
    start=time.time()
    crawler=crawlJobs()
    asyncio.run(crawler.main())
    end=time.time()
    print(f"time_take{(end-start)/60}")
