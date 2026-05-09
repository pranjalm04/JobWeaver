from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

# --- Heuristic Keywords & Patterns ---

LISTING_KEYWORDS_TITLE_H1 = [
    "career",
    "job",
    "vacancy",
    "Career Opportunities",
    "opening",
    "opportunity",
    "position",
    "listing",
    "search jobs",
    "find jobs",
    "job openings",
    "job listings",
    "job vacancies",
    "employment opportunities",
]
LISTING_KEYWORDS_GENERAL = ["filter", "sort by", "results", "found", "jobs found"]
INDIVIDUAL_JOB_KEYWORDS_STRONG = ["apply now", "submit application", "job description"]

PAGINATION_KEYWORDS = ["next", "previous", "last", "first", "page"]
PAGINATION_CLASSES = [
    "pagination",
    "pager",
    "page-numbers",
    "page-list",
    "paging",
    "pagination-container",
    "paginator",
]
PAGINATION_SYMBOLS = ["»", "«", "›", "‹", ">", "<"]

JOB_TITLE_FRAGMENTS = [
    "analyst",
    "specialist",
    "engineer",
    "manager",
    "technician",
    "coordinator",
    "junior",
    "assistant",
    "associate",
    "advocate",
    "director",
    "designer",
    "consultant",
    "surgeon",
    "nurse",
    "therapist",
    "radiology",
    "psychiatrist",
    "support worker",
    "councellor",
    "technologist",
    "scientist",
]
SEARCH_FORM_INPUT_NAMES = [
    "keyword",
    "query",
    "q",
    "search",
    "location",
    "city",
    "state",
    "zipcode",
    "postal",
    "country",
    "category",
    "department",
    "jobid",
]
SEARCH_FORM_KEYWORDS = ["search jobs", "find jobs", "filter jobs"]

LISTING_URL_PATHS = [
    "/jobs",
    "/careers",
    "/vacancies",
    "/openings",
    "/search",
    "/job-listings",
    "/positions",
    "/employment",
]


@dataclass(frozen=True)
class HeuristicResult:
    score: float
    debug_info: list

    def __iter__(self):
        yield self.score
        yield self.debug_info


@dataclass
class _Scorer:
    score: float = 0.0
    debug_info: list[str] = field(default_factory=list)


def _score_title_keywords(soup: BeautifulSoup, scorer: _Scorer) -> None:
    page_title = soup.title.string.lower() if soup.title and soup.title.string else ""
    h1_text = soup.h1.get_text(" ", strip=True).lower() if soup.h1 else ""
    h2_texts = " ".join(h2.get_text(" ", strip=True).lower() for h2 in soup.find_all("h2", limit=5))
    h3_texts = " ".join(h3.get_text(" ", strip=True).lower() for h3 in soup.find_all("h3", limit=5))
    title_h1_h2_text = f"{page_title} {h1_text} {h2_texts} {h3_texts}"

    found_title_keyword = False
    if any(keyword in title_h1_h2_text for keyword in LISTING_KEYWORDS_TITLE_H1):
        scorer.score += 1.5
        found_title_keyword = True
        scorer.debug_info.append("(+1.5) Found strong listing keyword in Title/H1/H2")

    if any(keyword in title_h1_h2_text for keyword in INDIVIDUAL_JOB_KEYWORDS_STRONG):
        scorer.score -= 1.0
        scorer.debug_info.append(
            "(-1.0) Found 'Apply Now'/'Job Description' style keyword in H1 (penalty)"
        )
    if any(keyword in title_h1_h2_text for keyword in LISTING_KEYWORDS_GENERAL):
        if not found_title_keyword:
            scorer.score += 0.5
            scorer.debug_info.append("(+0.5) Found general listing keyword in Title/H1/H2")


def _score_url_path(url: str | None, scorer: _Scorer) -> None:
    if not url:
        return
    try:
        parsed_url = urlparse(url)
    except ValueError:
        scorer.debug_info.append("[Warn] URL parsing error.")
        return
    path_lower = parsed_url.path.lower() if parsed_url.path else ""
    if any(p in path_lower for p in LISTING_URL_PATHS if p != "/"):
        scorer.score += 1.0
        scorer.debug_info.append(
            f"(+1.0) URL path ('{path_lower}') matches common listing pattern."
        )


def _score_pagination(soup: BeautifulSoup, scorer: _Scorer) -> None:
    pagination_elements = soup.find_all(
        ["nav", "div", "ul", "li"],
        class_=lambda x: x and any(pc.lower() in x.lower() for pc in PAGINATION_CLASSES),
        limit=5,
    )
    if pagination_elements:
        scorer.score += 1.5
        scorer.debug_info.append(
            f"(+1.5) Found pagination element with specific class ({[e.get('class') for e in pagination_elements]})"
        )
        return

    pagination_score = 0.0
    links = soup.find_all("a", href=True, limit=500)
    weak_pagination_containers = soup.find_all(
        ["div", "ul"],
        class_=lambda x: x and any(kw in x.lower() for kw in ["page", "paging", "pager"]),
        limit=5,
    )
    potential_pagers: list[Tag] = []
    for container in weak_pagination_containers:
        potential_pagers.extend(container.find_all("a", href=True, limit=50))

    links_to_check = list(set(links + potential_pagers))

    page_numbers_count = 0
    next_prev_sym_found = False
    next_prev_kw_found = False
    for link in links_to_check:
        link_text = link.get_text(strip=True).lower()
        link_sym = link.get_text(strip=True)
        if not link_text and not link_sym:
            continue
        if any(kw in link_text for kw in PAGINATION_KEYWORDS):
            next_prev_kw_found = True
        if any(sym in link_sym for sym in PAGINATION_SYMBOLS):
            next_prev_sym_found = True
        if re.fullmatch(r"\d{1,3}", link_text):
            page_numbers_count += 1

    if next_prev_kw_found or next_prev_sym_found:
        pagination_score += 1.0
        scorer.debug_info.append("(+1.0) Found Next/Prev keywords or symbols in links.")
    if page_numbers_count >= 3:
        pagination_score += 0.5
        scorer.debug_info.append(f"(+0.5) Found multiple ({page_numbers_count}) page number links.")

    scorer.score += min(pagination_score, 1.2)


def _score_search_form(soup: BeautifulSoup, scorer: _Scorer) -> None:
    forms = soup.find_all("form", limit=10)
    for form in forms:
        form_text = form.get_text(" ", strip=True).lower()
        if any(keyword in form_text for keyword in SEARCH_FORM_KEYWORDS):
            scorer.score += 1.0
            scorer.debug_info.append("(+1.0) Found form with job search keywords.")
            return

        inputs = form.find_all(["input", "select"], limit=20)
        for input_tag in inputs:
            attrs_text = (
                f"{input_tag.get('name', '')} {input_tag.get('id', '')} "
                f"{input_tag.get('placeholder', '')} {input_tag.get('aria-label', '')}"
            ).lower()
            if any(name in attrs_text for name in SEARCH_FORM_INPUT_NAMES):
                scorer.score += 0.8
                scorer.debug_info.append(
                    "(+0.8) Found form with relevant input names (keyword, location etc.)."
                )
                return


def _score_job_link_fragments(soup: BeautifulSoup, scorer: _Scorer) -> None:
    job_link_count = 0
    for link in soup.find_all("a", href=True, limit=500):
        link_text = link.get_text(strip=True)
        href = link.get("href", "")
        if not (
            1 < len(link_text.split()) < 100
            and not href.startswith(("http", "#", "javascript:", "mailto:"))
            and len(href) > 1
        ):
            continue
        link_text_lower = link_text.lower()
        if any(frag in link_text_lower or frag in href.lower() for frag in JOB_TITLE_FRAGMENTS):
            job_link_count += 1

    if job_link_count >= 2:
        link_score = 4.0 * min(job_link_count / 5.0, 1)
        scorer.score += link_score
        scorer.debug_info.append(
            f"(+{link_score:.1f}) Fallback: Found {job_link_count} links containing job title fragments."
        )


def check_job_listing_heuristics(html_content: str, url: str | None = None) -> HeuristicResult:
    try:
        soup = BeautifulSoup(html_content, "html.parser")
    except Exception as e:
        logger.warning("BeautifulSoup parsing error: %s", e)
        return HeuristicResult(score=0.0, debug_info=[])

    scorer = _Scorer()
    _score_title_keywords(soup, scorer)
    _score_url_path(url, scorer)
    _score_pagination(soup, scorer)
    _score_search_form(soup, scorer)
    _score_job_link_fragments(soup, scorer)

    return HeuristicResult(score=round(scorer.score, 2), debug_info=scorer.debug_info)
