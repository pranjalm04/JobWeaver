import csv
import asyncio
from urllib.parse import urljoin
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# ------- Config Section --------
joblisting ={"is_job_listing": True, "score": 9.5, "has_pagination": True, "parent_container_selector": "div#js-job-search-results", "next_page_element": {"text": "", "href": "https://careers.rochesterregional.org/jobs/?page=2#results", "selector": "li.page-item.next > a"}, "individual_job_links": [{"href": "/jobs/req_207572/unit-secretary-emergency-department/", "text": "Unit Secretary-Emergency Department", "selector": "h2.card-title > a"}, {"href": "/jobs/req_207278/mri-technologist/", "text": "MRI Technologist", "selector": "h2.card-title > a"}, {"href": "/jobs/req_217599/assistant-nurse-manager/", "text": "Assistant Nurse Manager.", "selector": "h2.card-title > a"}, {"href": "/jobs/req_216000/access-associate/", "text": "Access Associate", "selector": "h2.card-title > a"}, {"href": "/jobs/req_217173/access-associate/", "text": "Access Associate", "selector": "h2.card-title > a"}, {"href": "/jobs/req_217179/access-associate/", "text": "Access Associate", "selector": "h2.card-title > a"}, {"href": "/jobs/req_217260/sous-chef/", "text": "Sous Chef", "selector": "h2.card-title > a"}, {"href": "/jobs/req_208843/patient-care-tech-medical-surgical-1400/", "text": "Patient Care Tech - Medical Surgical (1400)", "selector": "h2.card-title > a"}, {"href": "/jobs/req_217388/lpn-dermatology-clifton-springs/", "text": "LPN - Dermatology - Clifton Springs", "selector": "h2.card-title > a"}, {"href": "/jobs/req_210401/telemed-technician-hc/", "text": "Telemed Technician-HC", "selector": "h2.card-title > a"}, {"href": "/jobs/req_212362/patient-care-tech-radiology/", "text": "Patient Care Tech-Radiology", "selector": "h2.card-title > a"}, {"href": "/jobs/req_216353/medical-assistant/", "text": "Medical Assistant", "selector": "h2.card-title > a"}, {"href": "/jobs/req_215467/patient-care-tech-ct/", "text": "Patient Care Tech-CT", "selector": "h2.card-title > a"}, {"href": "/jobs/req_214077/unit-clerk-potsdam-ny-full-time/", "text": "Unit Clerk - Potsdam, NY (Full Time)", "selector": "h2.card-title > a"}, {"href": "/jobs/req_216740/licensed-master-of-social-work-developmental-and-behavioral-pediatrics/", "text": "Licensed Master of Social Work - Developmental and Behavioral Pediatrics", "selector": "h2.card-title > a"}, {"href": "/jobs/req_217106/medical-assistant/", "text": "Medical Assistant", "selector": "h2.card-title > a"}, {"href": "/jobs/req_185329/registered-nurse-acute-general-medicine/", "text": "Registered Nurse - Acute General Medicine", "selector": "h2.card-title > a"}, {"href": "/jobs/req_213846/registered-nurse-acute-general-medicine/", "text": "Registered Nurse - Acute General Medicine", "selector": "h2.card-title > a"}, {"href": "/jobs/req_216821/lpn-urgent-care-wilson-per-diem/", "text": "LPN - Urgent Care - Wilson - Per Diem", "selector": "h2.card-title > a"}, {"href": "/jobs/req_217486/cna/", "text": "C.N.A.", "selector": "h2.card-title > a"}], "total_token_count": 21595, "careers_url": "https://careers.rochesterregional.org/jobs/", "child_job_link_selector": "h2.card-title > a"}

config = {
    "base_url": joblisting.get("careers_url"),
    "output_filename": "xyz.csv",
    "container_selector": joblisting.get('parent_container_selector'),
    "next_button_selector": joblisting.get('next_page_element', {}).get('selector'),
    "headless": True,
    "has_pagination": joblisting.get('has_pagination'),
    "job_links": joblisting.get('individual_job_links'),
    "child_job_link_selector": joblisting.get('child_job_link_selector')
}

# ------- Scraper Section --------
async def scrape_jobs_to_dict(**cfg):
    all_jobs = []
    page_count = 1
    base_url = cfg['base_url']
    container_selector = cfg['container_selector']
    next_button_selector = cfg['next_button_selector']
    has_pagination = cfg['has_pagination']
    output_filename = cfg['output_filename']
    job_link_selector = cfg['child_job_link_selector']
    print(next_button_selector)
    print(f"Starting scrape on: {base_url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=cfg['headless'])
        page = await browser.new_page()
        await page.goto(base_url)
        await page.wait_for_load_state('networkidle',timeout=4000)
        async def scrape_current_page():
            nonlocal all_jobs

            await page.wait_for_load_state('networkidle', timeout=4000)
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            container = soup.select_one(container_selector)
            job_links = container.select(job_link_selector)
            print(f"[Page {page_count}] Found {len(job_links)} job links.")
            for job in job_links:
                # print(job)
                title = job.get_text(strip=True)
                print(title)
                href = job.get('href')
                if href:
                    job_url = urljoin(base_url, href)
                    all_jobs.append({"Title": title, "URL": job_url})


        if has_pagination:
            while True:
                print(f"Scraping Page {page_count}...")
                await scrape_current_page()

                next_btn = page.locator(next_button_selector)
                next_btn_visible=await next_btn.is_visible()
                print(next_btn_visible)

                before_html=await page.inner_html(job_link_selector)
                print(await next_btn.get_attribute("class"))

                if not next_btn or "disabled" in (await next_btn.get_attribute("class") or "") or await next_btn.is_disabled():
                    break

                try:
                    # await next_btn.scroll_into_view_if_needed()
                    await next_btn.click(force=True)
                    await page.wait_for_timeout(1000)
                    print("Clicked Next Button.")
                    page_count += 1
                except Exception as e:
                    print(f"Error waiting for new page: {e}. Stopping.")
                    break

        else:
            await scrape_current_page()

        if len(all_jobs) == 0:
            for link in cfg['job_links']:
                job_url = urljoin(base_url, link.get('href'))
                all_jobs.append({'Title': link.get('text'), 'URL': job_url})
        await browser.close()

    # Saving
    with open(output_filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["Title", "URL"])
        writer.writeheader()
        writer.writerows(all_jobs)

    print(f"\nDone. Scraped {len(all_jobs)} job listings.")
    print(f" Saved to: {output_filename}")

async def scrape_jobs_to_csv(cfg: dict):
    await scrape_jobs_to_dict(**cfg)

if __name__ == "__main__":
    asyncio.run(scrape_jobs_to_csv(config))
