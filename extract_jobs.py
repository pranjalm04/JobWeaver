import csv
import asyncio
from urllib.parse import urljoin
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import logging
import hashlib # Import hashlib for content hashing
# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# ------- Scraper Section --------
async def scrape_jobs_to_dict(joblisting):

    cfg = {
        "base_url": joblisting.get("careers_url"),
        "output_filename": "xyz.csv",
        "container_selector": joblisting.get('parent_container_selector'),
        "next_button_selector": joblisting.get('next_page_element', {}).get('selector'),
        "headless": True,  # Set to False for debugging to see the browser
        "has_pagination": joblisting.get('has_pagination'),
        "job_links": joblisting.get('individual_job_links'),  # Fallback if no jobs scraped
        "child_job_link_selector": joblisting.get('child_job_link_selector')
    }
    all_jobs = []
    page_count = 1
    base_url = cfg['base_url']
    container_selector = cfg['container_selector']
    next_button_selector = cfg['next_button_selector']
    has_pagination = cfg['has_pagination']
    output_filename = cfg['output_filename']
    job_link_selector = cfg['child_job_link_selector']

    logging.info(f"Starting scrape on: {base_url}")
    logging.info(f"Next button selector: {next_button_selector}")

    async def scroll_to_bottom_until_stable(page, max_scrolls=20, pause_ms=1000):
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
            await page.goto(base_url, wait_until='networkidle', timeout=60000) # Increased timeout
            # await asyncio.sleep(1)
            # Wait for the main job container to be visible
            try:
                await scroll_to_bottom_until_stable(page)
            except Exception as e:
                logging.error(f"error while scrolling to the bottom {e}")

            await page.wait_for_selector(container_selector, state='attached', timeout=50000)

        except Exception as e:
            logging.error(f"Failed to navigate or find container on initial page: {e}")
            await browser.close()
            # Fallback to initial job links if scraping fails
            if len(all_jobs) == 0 and cfg.get('job_links'):
                 logging.info("Scraping failed, using initial job links from LLM output.")
                 for link in cfg['job_links']:
                    job_url = urljoin(base_url, link.get('href'))
                    all_jobs.append({'Title': link.get('text'), 'URL': job_url})

            # Saving (even if empty or fallback)
            with open(output_filename, mode="w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=["Title", "URL"])
                writer.writeheader()
                writer.writerows(all_jobs)
            logging.info(f"\nDone. Scraped {len(all_jobs)} job listings.")
            logging.info(f" Saved to: {output_filename}")
            return all_jobs



        async def get_job_urls_on_page():
            """Scrapes job URLs from the current page."""
            try:
                 await page.wait_for_load_state('networkidle', timeout=10000)
                 # Wait for job links to be present inside the container
                 await page.wait_for_selector(f"{container_selector} {job_link_selector}", state='attached', timeout=10000)
                 # Wait for network activity to settle after dynamic loading

            except Exception as e:
                 logging.warning(f"[Page {page_count}] Could not find job links or network idle before scraping: {e}. Attempting to scrape anyway.")

            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            container = soup.select_one(container_selector)

            if not container:
                logging.error(f"[Page {page_count}] Job container not found with selector: {container_selector}")
                return [] # Return empty list if container is missing

            job_elements = soup.select(job_link_selector)
            current_page_job_urls = []
            for job in job_elements:
                href = job.get('href')
                if href:
                    job_url = urljoin(base_url, href)
                    current_page_job_urls.append(job_url)
                    # Also add to all_jobs if not a duplicate
                    title = job.get_text(strip=True)
                    if not any(item['URL'] == job_url for item in all_jobs):
                         all_jobs.append({"Title": title, "URL": job_url})

            logging.info(f"[Page {page_count}] Found {len(current_page_job_urls)} job links on this page.")
            return current_page_job_urls


        if has_pagination and next_button_selector:
            previous_page_job_urls = []

            while True:
                logging.info(f"Scraping Page {page_count}...")
                current_page_job_urls = await get_job_urls_on_page()

                # --- Pagination End Check ---
                # Check if the current page has the same job URLs as the previous page.
                # This indicates that clicking 'next' did not load new content.
                if set(current_page_job_urls) == set(previous_page_job_urls) and page_count > 1:
                    logging.info("Job listings did not change after clicking next. Assuming end of pagination.")
                    break

                # If no jobs found on the current page (and not the very first page), assume end
                if not current_page_job_urls and page_count > 1:
                     logging.info("No job listings found on the current page. Assuming end of pagination.")
                     break

                previous_page_job_urls = current_page_job_urls # Store URLs for next iteration

                # --- Attempt to Click Next ---
                next_btn_locator = page.locator(next_button_selector).first
                is_next_btn_visible = False
                try:
                     is_next_btn_visible = await next_btn_locator.is_visible(timeout=5000)
                     logging.info(f"Next button visible check: {is_next_btn_visible}")
                     # Also check for disabled state if visible
                     if is_next_btn_visible and await next_btn_locator.is_disabled():
                          logging.info("Next button is visible but disabled. Assuming end of pagination.")
                          break # Break if visible but disabled

                except Exception as e:
                     # If is_visible check times out or fails, assume button is not there
                     logging.info(f"Next button not found or visibility check failed: {e}. Assuming end of pagination.")
                     is_next_btn_visible = False # Ensure flag is False on error


                if not is_next_btn_visible:
                    logging.info("Next button is not visible. Ending pagination loop.")
                    break # Break the loop if the next button is not visible


                try:
                    # Scroll into view before clicking if needed (optional)
                    # await next_btn_locator.scroll_into_view_if_needed()
                    await next_btn_locator.click(timeout=10000) # Added timeout for click
                    # Wait for the page to load after the click.
                    await page.wait_for_load_state('domcontentloaded', timeout=30000)
                    # Add a small fixed delay as a fallback
                    await page.wait_for_timeout(500)

                    logging.info(f"Clicked Next Button. Moving to Page {page_count + 1}.")
                    page_count += 1

                except Exception as e:
                    logging.error(f"Error clicking next button or waiting for page load: {e}. Stopping pagination.")
                    break # Break loop on error during click or wait

        else:
            # If no pagination detected or selector is missing, just scrape the first page
            logging.info("Pagination not detected or next button selector missing. Scraping only the initial page.")
            await get_job_urls_on_page() # Use the new function to scrape the single page


        await browser.close()

    # Saving
    # Ensure fallback is only used if no jobs were scraped during the process
    if len(all_jobs) == 0 and cfg.get('job_links'):
         logging.info("No jobs scraped during pagination, using initial job links from LLM output as fallback.")
         for link in cfg['job_links']:
            job_url = urljoin(base_url, link.get('href'))
            all_jobs.append({'Title': link.get('text'), 'URL': job_url})


    with open(output_filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["Title", "URL"])
        writer.writeheader()
        writer.writerows(all_jobs)

    logging.info(f"\nDone. Scraped {len(all_jobs)} job listings.")
    logging.info(f" Saved to: {output_filename}")
    return all_jobs

# Entry point
# if __name__ == "__main__":
#     asyncio.run(scrape_jobs_to_dict(**config))
