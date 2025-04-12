import heapq
import json
import urllib
from collections import deque
from urllib.parse import urlparse, urljoin, urlunparse, quote
import requests
import regex as re
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from llmIntegrations import extract_jobs_from_html
from playwright.sync_api import sync_playwright
import time
import requests


class JobCrawler:

    def __init__(self):
        self.seed_url = "https://careers.rochesterregional.org/"
        self.depth_threshold = 3
        self.driver = self.getChromedriver()
        self.pq = list()
        self.visited_relative_urls = set()
        self.visited_urls = set()
        self.result_set = set()
        self.JOB_KEYWORDS = {
            'career': 1,
            'job': 1,
            'opportunit': 2,
            'position': 2,
            'vacanc': 3
        }
        self.JOB_PATTERNS = re.compile(
            r'(?i)'  # Case-insensitive
            r'(?:career|job|position|employment|opportunit|apply)(?:s|y|ies)?/'  # Matches "career/jobs/", "opportunity/"
            r'|\b(?:job|career|opening|position)s?\b'  # Matches words like "jobs", "career", "openings"
            # r'|search_query=([^&]*?(?:job|career)[^&]*)'  # Matches search queries containing "job" or "career"
            r'|\bjoin\b.*?\b(?:team|us)\b'  # Matches "join our team"
            r'|(?=.*\b(?:open|openings|view)\b)(?=.*\bjobs\b).*'  # Matches URLs containing "open jobs"
            r'|/jobs\?(?:[^#\s]+)?'
            # Matches Indeed-style job URLs
        )
        self.url_pattern = re.compile(
            r'^(https?|ftp):\/\/'  # Protocol (http, https, ftp)
            r'([a-zA-Z0-9.-]+)'  # Domain name (subdomains included)
            r'(\.[a-zA-Z]{2,})'  # Top-level domain (e.g., .com, .org)
            r'(:\d+)?'  # Optional port (e.g., :8080)
            r'(\/[^\s]*)?$',  # Path (optional)
            re.IGNORECASE
        )

    # def is_job_listing_page(self, content):


    def getChromedriver(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver

    def getDomain(self, url):
        parsed_url = urlparse(url)
        return parsed_url.hostname  # Extracts the domain name (hostname)

    def isMatchingDomain(self, current_url, parent_url):
        domain_url = self.getDomain(current_url)
        domain_seed = self.getDomain(parent_url)
        return domain_url == domain_seed
    def extractUrlsIframes(self, iframes):
        """
        extrcat the urls from iframes which are loaded once they are in the view port
        The contents are hidden when we dont have those iframes in the view port
        """
        url_context=dict()
        try:
            for frame in iframes:
                links=frame.locator("a").all()
                for link in links:
                   url_context[link.get_attribute("href")]=link.inner_text()

            # print('url_context',url_context)
        except:
            print('error from extracturls')
        return url_context

    def getHtmlContent(self, url):
        html_content = ""
        iframes_url_context = dict()

        try:
            with sync_playwright() as p:
                def block_resources(route):
                    # Block images and stylesheets
                    if route.request.resource_type in ["image", "stylesheet"]:
                        route.abort()
                    else:
                        route.continue_()


                def handle_response(response):
                    """Intercept network responses and extract JSON."""
                    try:
                        print(response.headers.get("content-type",""))
                        if "json" in response.headers.get("content-type", ""):
                            json_data = response.json()
                            print(json_data)
                    except Exception as e:
                        print('json errors',e)

                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                    java_script_enabled=True
                )
                page = context.new_page()
                # page.route("**/*", lambda route: route.continue_())
                page.route("**/*", block_resources)

                # page.on("response",handle_response)
                page.goto(url, wait_until="networkidle")
                page.wait_for_load_state("networkidle")

                iframes = page.frames
                iframes_url_context.update(self.extractUrlsIframes(iframes))
                html_content = page.content()
                browser.close()

        except Exception as e:
            print('error from playwright',e)


        if html_content == "":
            try:
                self.driver.get(url)
                self.driver.implicitly_wait(1)
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, 'a'))
                )
                html_content = self.driver.page_source
            except Exception as e:
                print('error')
            finally:
                self.driver.quit()
        if html_content == "":
            response = requests.get(url, timeout=5)
            html_content = response.text

        return html_content, iframes_url_context

    def getUrls(self, html_content):
        links = list()
        soup = BeautifulSoup(html_content, 'html.parser')
        try:
            content_links = soup.find_all('a', href=True)
            links.extend(content_links)
        except:
            print('error parsing html content')
        return links

    def get_link_score(self, url, anchor_text):
        score = 0
        text = (url + ' ' + anchor_text).lower()
        for kw, weight in self.JOB_KEYWORDS.items():
            if kw in text:
                score += weight
        return score

    def isValidUrl(self, url):
        if url == '':
            return False
        return bool(self.url_pattern.match(url.strip()))

    def convertToAbsoluteUrl(self, base_url, href):
        if not href or href.startswith("#") or href == "/":
            return None
        parsed_href = urlparse(href)
        is_relative = not bool(parsed_href.netloc)
        absolute_url = urljoin(base_url, href) if is_relative else href
        parsed_base = urlparse(base_url)
        parsed_absolute = urlparse(absolute_url)
        if (parsed_absolute.netloc == parsed_base.netloc and
                parsed_absolute.path == parsed_base.path and
                parsed_absolute.query == parsed_base.query):
            return None
        return absolute_url

    def getRelativeUrl(self, url1, url2):
        parsed_url1 = urlparse(url1)
        parsed_url2 = urlparse(url2)
        path1 = parsed_url1.path
        path2 = parsed_url2.path
        if path1.startswith(path2):
            unique_path = path1[len(path2):]
        else:
            unique_path = path1
        if parsed_url1.query:
            unique_path += '?' + parsed_url1.query
        return unique_path

    def prioritizeUrls(self, relative_url, downstream_url, url_content):
        prioritized_url = None
        if re.search(self.JOB_PATTERNS, relative_url) or re.search(self.JOB_PATTERNS, url_content):
            prioritized_url = downstream_url
        return prioritized_url

    def getAdjacentUrls(self, html_content,iframe_url_context, url, depth):
        adjacentLinks = set()
        links = self.getUrls(html_content)
        link_context = {link['href']: link.get_text(separator=" ", strip=True) for link in links}
        link_context.update(iframe_url_context)
        # print(link_context)
        for href, ctx in link_context.items():
            new_depth = depth

            downStreamUrl = self.convertToAbsoluteUrl(url, href)
            # print(downStreamUrl)
            if downStreamUrl is None:
                continue
            if self.isValidUrl(downStreamUrl):
                relative_url = self.getRelativeUrl(downStreamUrl, url)

                prioritizedUrl = self.prioritizeUrls(relative_url, downStreamUrl, ctx)
                # print(prioritizedUrl)
                if prioritizedUrl is None:
                    continue
                url_without_query_params = self.urlWithoutQueryParams(prioritizedUrl)
                # print(downStreamUrl,relative_url)
                if url_without_query_params not in self.visited_urls and relative_url not in self.visited_relative_urls:
                    if not self.isMatchingDomain(prioritizedUrl, url):
                        new_depth = depth + 1

                    if new_depth <= self.depth_threshold:
                        adjacentLinks.add((new_depth, prioritizedUrl, relative_url))
        return adjacentLinks

    def urlWithoutQueryParams(self, url):
        url = urlparse(url)
        url_without_query = urlunparse((url.scheme, url.netloc, url.path, '', '', ''))
        return url_without_query

    def crawl(self):
        heapq.heappush(self.pq, (1, self.seed_url, ""))
        cnt = 0
        while (self.pq):
            current_url_context = heapq.heappop(self.pq)
            depth = current_url_context[0]
            current_url = current_url_context[1]
            current_relative_url = current_url_context[2]
            current_url_without_query_params = self.urlWithoutQueryParams(current_url)

            if current_url in self.visited_urls or current_relative_url in self.visited_relative_urls:
                continue
            self.visited_urls.add(current_url)
            if current_relative_url != "":
                self.visited_relative_urls.add(current_relative_url)
            print('current_url', current_url)
            cnt += 1
            html_content, iframes_urls_context = self.getHtmlContent(current_url)
            # print(html_content)
            soup = BeautifulSoup(html_content, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
            # print(extract_jobs_from_html(text,current_url))
            adjacent_urls = self.getAdjacentUrls(html_content, iframes_urls_context,current_url, depth)
            # print(adjacent_urls)
            if len(adjacent_urls) == 0:
                continue

            for depth, url, relative_url in adjacent_urls:
                heapq.heappush(self.pq, (depth, url, relative_url))
        print(cnt)

    @staticmethod
    def main():
        crawlJobs = JobCrawler()
        crawlJobs.crawl()

        # hc=crawlJobs.getHtmlContent('https://careers-ahmchealth.icims.com/jobs/search?hashed=-435591615&mobile=false&width=1534&height=500&bga=true&needsRedirect=false&jan1offset=-300&jun1offset=-240#icims_content_iframe')
        # print(hc)
        # print([link['href'] for link in crawlJobs.getUrls(crawlJobs.getHtmlContent('https://jewishboard.org/careers/'))])


if __name__ == '__main__':
    JobCrawler.main()
