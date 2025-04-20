import csv
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# === CONFIGURATION ===
BASE_URL = "https://jobs.lifepointhealth.net"
START_PATH = "/search-jobs?acm=ALL&alrpm=ALL&ascf=[%7B%22key%22:%22is_manager%22,%22value%22:%22Wythe+County+Community+Hospital%22%7D]"
FULL_URL = urljoin(BASE_URL, START_PATH)
OUTPUT_FILENAME = "total_jobs.csv"
HEADLESS_MODE = True  # Set to False to open browser

# === SCRAPER ===
all_jobs = []
page_count = 1

with sync_playwright() as p:
    browser = p.chromium.launch(headless=HEADLESS_MODE)
    page = browser.new_page()
    page.goto(FULL_URL)

    while True:
        print(f"Scraping Page {page_count}...")

        # Wait for the main job container
        page.wait_for_selector('#search-results-list', timeout=10000)
        soup = BeautifulSoup(page.content(), 'html.parser')
        container = soup.select_one('#search-results-list')

        job_links = container.select('a[data-job-id]') if container else []

        for job in job_links:
            title = job.get_text(strip=True)
            href = job.get('href')
            if href:
                full_url = urljoin(BASE_URL, href)
                all_jobs.append({"Title": title, "URL": full_url})

        # Handle pagination
        next_btn = page.query_selector('a.next')
        if not next_btn or "disabled" in next_btn.get_attribute("class"):
            break

        next_btn.click()
        page.wait_for_timeout(2000)

        page_count += 1

    browser.close()

# === SAVE TO CSV ===
with open(OUTPUT_FILENAME, mode="w", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(file, fieldnames=["Title", "URL"])
    writer.writeheader()
    writer.writerows(all_jobs)

print(f"\n Done. Collected {len(all_jobs)} job listings.")
print(f" Saved to CSV: {OUTPUT_FILENAME}")
