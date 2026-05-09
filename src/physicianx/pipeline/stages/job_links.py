from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.async_api import Page, async_playwright

from physicianx.config.pipeline import PipelineConfig
from physicianx.models import JobListingSchema, ScrapedJobLink
from physicianx.observability import log_stage_event
from physicianx.storage.writer import write_job_links_csv

logger = logging.getLogger(__name__)


def _append_job_if_new(all_jobs: list[ScrapedJobLink], title: str, job_url: str) -> None:
    if not any(j.url == job_url for j in all_jobs):
        all_jobs.append(ScrapedJobLink(title=title, url=job_url))


def try_extract_jobs_from_static_html(
    html: str,
    base_url: str,
    container_selector: str,
    child_job_link_selector: str,
) -> list[ScrapedJobLink] | None:
    """If the listing page is static, resolve links from already-fetched HTML."""
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


def _apply_llm_link_fallback(
    joblisting: JobListingSchema,
    base_url: str,
    all_jobs: list[ScrapedJobLink],
) -> None:
    if all_jobs or not joblisting.individual_job_links:
        return
    logger.info("Falling back to LLM-discovered job links (%d).", len(joblisting.individual_job_links))
    for link in joblisting.individual_job_links:
        job_url = urljoin(base_url, link.href)
        _append_job_if_new(all_jobs, link.text, job_url)


async def _scroll_to_bottom_until_stable(page: Page, max_scrolls: int = 200, pause_ms: int = 1000) -> None:
    previous_height = await page.evaluate("() => document.body.scrollHeight")
    for _ in range(max_scrolls):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(pause_ms)
        new_height = await page.evaluate("() => document.body.scrollHeight")
        if new_height == previous_height:
            break
        previous_height = new_height


async def _collect_links_on_page(
    page: Page,
    container_selector: str,
    job_link_selector: str,
    base_url: str,
    all_jobs: list[ScrapedJobLink],
    page_count: int,
) -> list[str]:
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
        await _scroll_to_bottom_until_stable(page)
        await page.wait_for_selector(
            f"{container_selector} {job_link_selector}",
            state="attached",
            timeout=10000,
        )
    except Exception as e:
        logger.warning(
            "[Page %d] could not stabilize page before scraping: %s. Scraping anyway.",
            page_count,
            e,
        )

    content = await page.content()
    soup = BeautifulSoup(content, "html.parser")
    if not soup.select_one(container_selector):
        logger.error("[Page %d] Job container not found: %s", page_count, container_selector)
        return []

    current_page_job_urls: list[str] = []
    for job in soup.select(job_link_selector):
        href = job.get("href")
        if not href:
            continue
        job_url = urljoin(base_url, href)
        current_page_job_urls.append(job_url)
        _append_job_if_new(all_jobs, job.get_text(strip=True), job_url)

    logger.info("[Page %d] Found %d job links.", page_count, len(current_page_job_urls))
    return current_page_job_urls


async def _click_next_or_stop(page: Page, next_button_selector: str, page_count: int) -> bool:
    """Click the next-page button. Returns False to stop pagination."""
    next_btn = page.locator(f"{next_button_selector}:visible").first
    try:
        await next_btn.scroll_into_view_if_needed()
    except Exception as e:
        logger.error("cannot scroll next button into view: %s", e)

    try:
        is_visible = await next_btn.is_visible()
        if not is_visible and await next_btn.is_disabled():
            logger.info("Next button is disabled. End of pagination.")
            return False
        if not is_visible:
            logger.info("Next button is not visible. Ending pagination.")
            return False
    except Exception as e:
        logger.info("Next button visibility check failed: %s. Ending pagination.", e)
        return False

    try:
        await next_btn.click(timeout=10000)
        await page.wait_for_load_state("domcontentloaded", timeout=30000)
        await page.wait_for_timeout(500)
        logger.info("Clicked Next. Moving to page %d.", page_count + 1)
        return True
    except Exception as e:
        logger.error("Error clicking next button: %s. Stopping pagination.", e)
        return False


async def _paginate_and_collect(
    page: Page,
    container_selector: str,
    job_link_selector: str,
    next_button_selector: str,
    base_url: str,
    all_jobs: list[ScrapedJobLink],
) -> None:
    page_count = 1
    previous_page_job_urls: list[str] = []
    while True:
        logger.info("Scraping page %d...", page_count)
        current = await _collect_links_on_page(
            page, container_selector, job_link_selector, base_url, all_jobs, page_count
        )

        if set(current) == set(previous_page_job_urls) and page_count > 1:
            logger.info("Page contents unchanged after click. End of pagination.")
            break
        if not current and page_count > 1:
            logger.info("No links on current page. End of pagination.")
            break

        previous_page_job_urls = current
        if not await _click_next_or_stop(page, next_button_selector, page_count):
            break
        page_count += 1


async def _scrape_with_playwright(
    joblisting: JobListingSchema,
    output_filename: str,
    run_id: str | None,
) -> list[ScrapedJobLink]:
    base_url = joblisting.careers_url
    container_selector = joblisting.parent_container_selector
    job_link_selector = joblisting.child_job_link_selector or ""
    next_button_selector = (
        joblisting.next_page_element.selector if joblisting.next_page_element else None
    )
    has_pagination = joblisting.has_pagination

    all_jobs: list[ScrapedJobLink] = []
    pw_t0 = time.perf_counter()
    error_repr: str | None = None

    logger.info("Starting Playwright scrape: %s (next=%s)", base_url, next_button_selector)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            try:
                await page.goto(base_url, wait_until="networkidle", timeout=60000)
                try:
                    await _scroll_to_bottom_until_stable(page)
                except Exception as e:
                    logger.error("error while scrolling to the bottom: %s", e)
                await page.wait_for_selector(container_selector, state="attached", timeout=50000)
            except Exception as e:
                logger.error("Failed to navigate or find container on initial page: %s", e)
                error_repr = str(e)
            else:
                if has_pagination and next_button_selector:
                    await _paginate_and_collect(
                        page,
                        container_selector,
                        job_link_selector,
                        next_button_selector,
                        base_url,
                        all_jobs,
                    )
                else:
                    logger.info("No pagination — scraping initial page only.")
                    await _collect_links_on_page(
                        page, container_selector, job_link_selector, base_url, all_jobs, 1
                    )
        finally:
            await browser.close()

    _apply_llm_link_fallback(joblisting, base_url, all_jobs)
    await asyncio.to_thread(write_job_links_csv, output_filename, all_jobs)
    logger.info("Done. Scraped %d job links → %s", len(all_jobs), output_filename)

    if run_id:
        extra: dict = {"mode": "playwright", "count": len(all_jobs)}
        if error_repr:
            extra["error"] = error_repr
        log_stage_event(
            run_id=run_id,
            stage="job_links_scrape",
            duration_ms=(time.perf_counter() - pw_t0) * 1000,
            url=base_url,
            extra=extra,
        )
    return all_jobs


async def scrape_jobs_to_dict(
    joblisting: JobListingSchema,
    *,
    config: PipelineConfig,
    source_html: str | None = None,
    run_id: str | None = None,
) -> list[ScrapedJobLink]:
    base_url = joblisting.careers_url
    output_filename = os.path.join(
        config.output_dir,
        f"job_links_{hashlib.md5(base_url.encode('utf-8')).hexdigest()}.csv",
    )

    container_selector = joblisting.parent_container_selector
    child_sel = joblisting.child_job_link_selector or ""

    if (
        source_html
        and not joblisting.has_pagination
        and container_selector
        and child_sel
    ):
        t0 = time.perf_counter()
        static_jobs = try_extract_jobs_from_static_html(
            source_html, base_url, container_selector, child_sel
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
            logger.info(
                "Resolved %d job links from static HTML (skipped Playwright).", len(static_jobs)
            )
            return static_jobs

    return await _scrape_with_playwright(joblisting, output_filename, run_id)
