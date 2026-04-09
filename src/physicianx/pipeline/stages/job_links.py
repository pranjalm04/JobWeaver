from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from physicianx.models import JobListingSchema, ScrapedJobLink
from physicianx.observability import log_stage_event
from physicianx.storage.writer import write_job_links_csv

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def _append_job_if_new(all_jobs: list[ScrapedJobLink], title: str, job_url: str) -> None:
    if not any(j.url == job_url for j in all_jobs):
        all_jobs.append(ScrapedJobLink(title=title, url=job_url))


def try_extract_jobs_from_static_html(
    html: str,
    base_url: str,
    container_selector: str,
    child_job_link_selector: str,
) -> list[ScrapedJobLink] | None:
    """
    If the listing page is static (no pagination clicks), resolve links from HTML
    already fetched by crawl4ai and avoid launching Playwright.
    """
    if not html.strip() or not container_selector.strip() or not child_job_link_selector.strip():
        return None
    try:
        soup = BeautifulSoup(html, "html.parser")
        container = soup.select_one(container_selector)
        if not container:
            return None
        job_elements = container.select(child_job_link_selector)
        if not job_elements:
            return None
        out: list[ScrapedJobLink] = []
        for job in job_elements:
            href = job.get("href")
            if not href:
                continue
            job_url = urljoin(base_url, href)
            title = job.get_text(strip=True)
            _append_job_if_new(out, title, job_url)
        return out if out else None
    except Exception:
        return None


async def scrape_jobs_to_dict(
    joblisting: JobListingSchema,
    *,
    source_html: str | None = None,
    run_id: str | None = None,
) -> list[ScrapedJobLink]:
    base_url = joblisting.careers_url
    output_dir = os.getenv("OUTPUT_DIR", "outputs")
    output_filename = os.path.join(
        output_dir,
        f"job_links_{hashlib.md5(base_url.encode('utf-8')).hexdigest()}.csv",
    )

    container_selector = joblisting.parent_container_selector
    child_sel = joblisting.child_job_link_selector or ""

    # Static path: single page, no pagination — use HTML we already have.
    if (
        source_html
        and not joblisting.has_pagination
        and container_selector
        and child_sel
    ):
        t0 = time.perf_counter()
        static_jobs = try_extract_jobs_from_static_html(
            source_html,
            base_url,
            container_selector,
            child_sel,
        )
        if static_jobs:
            await asyncio.to_thread(write_job_links_csv, output_filename, static_jobs)
            if run_id:
                log_stage_event(
                    run_id=run_id,
                    stage="job_links_scrape",
                    duration_ms=(time.perf_counter() - t0) * 1000,
                    url=base_url,
                    extra={"mode": "static_html", "count": len(static_jobs)},
                )
            logging.info(
                "Resolved %s job links from static HTML (skipped Playwright).",
                len(static_jobs),
            )
            return static_jobs

    cfg = {
        "base_url": base_url,
        "output_filename": output_filename,
        "container_selector": container_selector,
        "next_button_selector": joblisting.next_page_element.selector
        if joblisting.next_page_element is not None
        else None,
        "headless": True,
        "has_pagination": joblisting.has_pagination,
        "job_links": joblisting.individual_job_links,
        "child_job_link_selector": joblisting.child_job_link_selector,
    }
    all_jobs: list[ScrapedJobLink] = []
    page_count = 1
    base_url = cfg["base_url"]
    container_selector = cfg["container_selector"]
    next_button_selector = cfg["next_button_selector"]
    has_pagination = cfg["has_pagination"]
    output_filename = cfg["output_filename"]
    job_link_selector = cfg["child_job_link_selector"] or ""

    logging.info(f"Starting scrape on: {base_url}")
    logging.info(f"Next button selector: {next_button_selector}")

    pw_t0 = time.perf_counter()

    async def scroll_to_bottom_until_stable(page, max_scrolls=200, pause_ms=1000):
        previous_height = await page.evaluate("() => document.body.scrollHeight")
        for _ in range(max_scrolls):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(pause_ms)
            new_height = await page.evaluate("() => document.body.scrollHeight")
            if new_height == previous_height:
                break
            previous_height = new_height

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            await page.goto(base_url, wait_until="networkidle", timeout=60000)
            try:
                await scroll_to_bottom_until_stable(page)
            except Exception as e:
                logging.error(f"error while scrolling to the bottom {e}")

            await page.wait_for_selector(container_selector, state="attached", timeout=50000)

        except Exception as e:
            logging.error(f"Failed to navigate or find container on initial page: {e}")
            await browser.close()
            if len(all_jobs) == 0 and cfg.get("job_links"):
                logging.info("Scraping failed, using initial job links from LLM output.")
                for link in cfg["job_links"]:
                    job_url = urljoin(base_url, link.href)
                    _append_job_if_new(all_jobs, link.text, job_url)

            await asyncio.to_thread(write_job_links_csv, output_filename, all_jobs)
            logging.info(f"\nDone. Scraped {len(all_jobs)} job listings.")
            logging.info(f" Saved to: {output_filename}")
            if run_id:
                log_stage_event(
                    run_id=run_id,
                    stage="job_links_scrape",
                    duration_ms=(time.perf_counter() - pw_t0) * 1000,
                    url=base_url,
                    extra={"mode": "playwright", "count": len(all_jobs), "error": str(e)},
                )
            return all_jobs

        async def get_job_urls_on_page():
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
                await scroll_to_bottom_until_stable(page)
                await page.wait_for_selector(
                    f"{container_selector} {job_link_selector}",
                    state="attached",
                    timeout=10000,
                )

            except Exception as e:
                logging.warning(
                    f"[Page {page_count}] Could not find job links or network idle before scraping: {e}. Attempting to scrape anyway."
                )

            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")
            container = soup.select_one(container_selector)

            if not container:
                logging.error(
                    f"[Page {page_count}] Job container not found with selector: {container_selector}"
                )
                return []

            job_elements = soup.select(job_link_selector)
            current_page_job_urls = []
            for job in job_elements:
                href = job.get("href")
                if href:
                    job_url = urljoin(base_url, href)
                    current_page_job_urls.append(job_url)
                    title = job.get_text(strip=True)
                    _append_job_if_new(all_jobs, title, job_url)

            logging.info(f"[Page {page_count}] Found {len(current_page_job_urls)} job links on this page.")
            return current_page_job_urls

        if has_pagination and next_button_selector:
            previous_page_job_urls = []

            while True:
                logging.info(f"Scraping Page {page_count}...")
                current_page_job_urls = await get_job_urls_on_page()

                if set(current_page_job_urls) == set(previous_page_job_urls) and page_count > 1:
                    logging.info(
                        "Job listings did not change after clicking next. Assuming end of pagination."
                    )
                    break

                if not current_page_job_urls and page_count > 1:
                    logging.info("No job listings found on the current page. Assuming end of pagination.")
                    break

                previous_page_job_urls = current_page_job_urls

                next_btn_locator = page.locator(next_button_selector).first
                next_btn_locator = page.locator(f"{next_button_selector}:visible").first
                print(next_btn_locator)
                try:
                    await next_btn_locator.scroll_into_view_if_needed()
                except Exception as e:
                    logging.error("cannot scroll into the view", e)
                count = await page.locator(next_button_selector).count()
                print("Matches:", count)

                is_next_btn_visible = False
                try:
                    is_next_btn_visible = await next_btn_locator.is_visible()
                    logging.info(f"Next button visible check: {is_next_btn_visible}")
                    if not is_next_btn_visible and await next_btn_locator.is_disabled():
                        logging.info("Next button is visible but disabled. Assuming end of pagination.")
                        break

                except Exception as e:
                    logging.info(
                        f"Next button not found or visibility check failed: {e}. Assuming end of pagination."
                    )
                    is_next_btn_visible = False

                if not is_next_btn_visible:
                    logging.info("Next button is not visible. Ending pagination loop.")
                    break

                try:
                    await next_btn_locator.click(timeout=10000)
                    await page.wait_for_load_state("domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(500)

                    logging.info(f"Clicked Next Button. Moving to Page {page_count + 1}.")
                    page_count += 1

                except Exception as e:
                    logging.error(
                        f"Error clicking next button or waiting for page load: {e}. Stopping pagination."
                    )
                    break

        else:
            logging.info(
                "Pagination not detected or next button selector missing. Scraping only the initial page."
            )
            await get_job_urls_on_page()

        await browser.close()

    if len(all_jobs) == 0 and cfg.get("job_links"):
        logging.info("No jobs scraped during pagination, using initial job links from LLM output as fallback.")
        for link in cfg["job_links"]:
            job_url = urljoin(base_url, link.href)
            _append_job_if_new(all_jobs, link.text, job_url)

    await asyncio.to_thread(write_job_links_csv, output_filename, all_jobs)

    logging.info(f"\nDone. Scraped {len(all_jobs)} job listings.")
    logging.info(f" Saved to: {output_filename}")
    if run_id:
        log_stage_event(
            run_id=run_id,
            stage="job_links_scrape",
            duration_ms=(time.perf_counter() - pw_t0) * 1000,
            url=base_url,
            extra={"mode": "playwright", "count": len(all_jobs)},
        )
    return all_jobs
