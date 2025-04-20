import csv
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def scrape_jobs_to_csv(base_url: str, start_path: str, container_selector: str, job_selector: str, next_button_selector: str, output_filename: str, headless: bool = True):
    all_jobs = []
    page_count = 1
    full_url = urljoin(base_url, start_path)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(full_url)
        while True:
            print(f"Scraping Page {page_count}...")
            page.wait_for_selector(container_selector, timeout=10000)
            soup = BeautifulSoup(page.content(), 'html.parser')
            container = soup.select_one(container_selector)
            job_links = container.select(job_selector) if container else []
            for job in job_links:
                title = job.get_text(strip=True)
                href = job.get('href')
                if href:
                    job_url = urljoin(base_url, href)
                    all_jobs.append({"Title": title, "URL": job_url})
            next_btn = page.query_selector(next_button_selector)
            if not next_btn or "disabled" in next_btn.get_attribute("class"):
                break
            next_btn.click()
            page.wait_for_timeout(2000)
            page_count += 1
        browser.close()
    with open(output_filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["Title", "URL"])
        writer.writeheader()
        writer.writerows(all_jobs)
    print(f"\n Done. Collected {len(all_jobs)} job listings.")
    print(f" Saved to: {output_filename}")


if __name__ == "__main__":
    scrape_jobs_to_csv(
        base_url="https://jobs.lifepointhealth.net",
        start_path="/search-jobs?acm=ALL&alrpm=ALL&ascf=[%7B%22key%22:%22is_manager%22,%22value%22:%22Wythe+County+Community+Hospital%22%7D]",
        container_selector="#search-results-list",
        job_selector="a[data-job-id]",
        next_button_selector="a.next",
        output_filename="total_jobs.csv",
        headless=True
    )
