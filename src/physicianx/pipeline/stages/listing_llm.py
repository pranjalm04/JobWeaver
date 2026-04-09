from __future__ import annotations

import asyncio
import logging
import time
from typing import List

from bs4 import BeautifulSoup

from physicianx.config.pipeline import PipelineConfig
from physicianx.models import JobListingSchema
from physicianx.llm.models import JobListingLM
from physicianx.listing_cache import save_listing_cache, try_load_listing_cache
from physicianx.observability import log_stage_event

__all__ = [
    "JobListingSchema",
    "analyze_full_html_with_llm",
    "merge_llm_chunk_responses",
    "extract_minified_body_html",
    "create_chunks_html_for_prompts",
    "make_chunk_prompt",
    "detect_job_listings",
]


def extract_minified_body_html(html: str, max_length: int = 10000) -> str:
    try:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "img", "iframe", "footer", "header", "svg", "noscript"]):
            tag.decompose()
        body = soup.body
        if body is None:
            return ""
        cleaned_html = body.decode_contents()
        return cleaned_html
    except Exception as e:
        logging.error(f"[HTML Parse Error]: {e}")
        return ""


def create_chunks_html_for_prompts(
    html: str,
    chunk_size: int = 100000,
    chunk_overlap: int = 1000,
    max_chunks: int = 8,
) -> List[str]:
    chunks = []
    for i in range(0, len(html), chunk_size):
        if len(chunks) >= max_chunks:
            break
        start = i - chunk_overlap if i > 0 else i
        chunk = html[start : start + chunk_size]
        chunks.append(chunk)
    return chunks


def make_chunk_prompt(chunk: str, source_url: str) -> str:
    return f"""You are an expert HTML parser and job listing extractor. Your sole purpose is to analyze the provided HTML chunk and determine if it represents a **list of multiple job openings**. If it does, extract specific attributes related *only* to those job listings and any associated pagination.

### CRITICAL: Read and understand these STRICT CRITERIA for Job Listing Page Detection:
1.  **PRIMARY SIGNAL: VISIBLE JOB TITLES.** The page **MUST** contain a visible list of text that are clearly identifiable as actual job titles for open positions. Examples of valid job titles: "Software Engineer", "Registered Nurse", "Marketing Manager", "Warehouse Associate", "Data Scientist", "Project Manager", "Accountant", "Customer Service Representative".
2.  **MULTIPLE DISTINCT LISTINGS.** The page **MUST** display a list of *multiple* different job openings. A page detailing only *one* job or general career information is NOT a job listing page.
3.  **IGNORE NON-JOB CONTENT.** **DO NOT** set `is_job_listing = true` and **DO NOT** extract links if the visible text primarily consists of:
    * News articles, blog posts, or company updates (e.g., "Life Inside...", "How [Name] Engineered...", "Summer Fest").
    * Employee spotlights or interviews.
    * General information about company culture, benefits, or departments.
    * Navigation links, filter options, department names, location lists, or job categories (e.g., "Engineering", "Marketing", "New York Jobs").
    * Links that lead to external sites not directly related to a job application (like LinkedIn profiles or general YouTube channels).
4.  **DO NOT INFER.** **DO NOT** infer job listings from URLs, link `href` attributes, image alt text, metadata, or assumptions based on surrounding text like "Careers", "Jobs", "Opportunities" if actual job titles are not clearly visible.

### Extraction Rules (Apply ONLY if ALL STRICT CRITERIA are met and `is_job_listing` is true):

1.  **`is_job_listing`**: Set to `true` only if the page clearly lists multiple actual job titles according to the criteria above. Otherwise, set to `false`.
2.  **`score`**: Provide a confidence score (0.0 to 10.0) indicating how certain you are that this chunk contains a job listing page. Higher scores for clearer, more numerous, and less ambiguous job titles. If `is_job_listing` is `false`, the score should be 0.0.
3.  **`parent_container_selector`**: Identify the CSS selector for the closest HTML element that contains *all* the individual job listing elements. Prioritize simple selectors like `div.job-list`, `ul#jobs`, `section[role='main']`. Avoid overly specific or lengthy paths. If no clear container for *all* job links is found or `is_job_listing` is `false`, return an empty string.
4.  **`individual_job_links`**: For each detected link (`<a>` tag) whose **visible text** is clearly an actual job title and which appears to link **directly to a single job detail page**:
    * `href`: Extract the value of the `href` attribute.
    * `text`: Extract the visible text of the `<a>` tag (this **MUST** be the job title).
    * `selector`: Provide a simple, relative CSS selector for *this specific link* within its immediate context. Examples: `a.job-link`, `h2 > a`, `div.title a`. Avoid dynamic IDs or very long paths. If `is_job_listing` is `false`, this list should be empty.
5.  **`child_job_link_selector`**: Generate a *single*, general CSS selector that matches *most* or *all* of the individual job listing links within the `parent_container_selector`. This selector should be as simple as possible, using maybe one tag and one class or attribute. Examples: `a.job-card`, `a[href*='/job/']`, `div.job-item a`. **This selector must be a single string, without commas, spaces, newlines, or multiple combined selectors.** It should be a concise pattern that captures the job links. If no clear pattern exists, no job links are found, or `is_job_listing` is `false`, return an empty string.
6.  **`has_pagination`**: Set to `true` if elements clearly indicating navigation to the *next* page (e.g., "Next", ">", "Load More", numbered pages beyond the first) are visible and the page is identified as a job listing page. Otherwise, set to `false`.
7.  **`next_page_element`**: If `has_pagination` is `true`, extract the following for the *next* page element:
    * `text`: The visible text (e.g., "Next", "Load More").
    * `href`: The URL from the `href` attribute (if it's a link). If it's a button, the `href` can be an empty string.
    * `selector`: A simple CSS selector for the next page element (e.g., `a.next-page`, `button#load-more`). Avoid selecting previous page buttons or all pagination numbers. If `has_pagination` is `false`, this should be empty.

### Output Format:
- You **MUST** output only a valid JSON object.
- The JSON object **MUST** strictly adhere to the `JobListingSchema` provided (implicitly, based on the field names and types described above).
- **DO NOT** include any extra text, explanations, markdown formatting (like ```json), or comments outside or inside the JSON.
- Ensure all fields are present in the output JSON.

Analyze only the HTML chunk below:

```html
{chunk}
"""


def merge_llm_chunk_responses(responses: list[JobListingSchema | None], careers_url: str) -> JobListingSchema:
    final: dict = {
        "is_job_listing": False,
        "score": 0,
        "has_pagination": False,
        "parent_container_selector": "",
        "next_page_element": None,
        "individual_job_links": [],
        "total_token_count": 0,
        "careers_url": "",
        "child_job_link_selector": None,
    }

    for resp in responses:
        if resp is not None:
            if resp.is_job_listing:
                final["is_job_listing"] = True
                final["individual_job_links"].extend(
                    link.model_dump() for link in resp.individual_job_links
                )
                final["score"] = max(final["score"], resp.score)
                final["total_token_count"] += resp.total_token_count
                final["child_job_link_selector"] = resp.child_job_link_selector
                if resp.has_pagination and not final["next_page_element"]:
                    final["has_pagination"] = True

                    final["next_page_element"] = (
                        resp.next_page_element.model_dump() if resp.next_page_element else None
                    )
                if final["child_job_link_selector"] == "":
                    final["child_job_link_selector"] = resp.child_job_link_selector
                if final["parent_container_selector"] == "":
                    final["parent_container_selector"] = resp.parent_container_selector

    seen = set()
    deduped_links = []
    for link in final["individual_job_links"]:
        key = link["href"]
        if key not in seen:
            deduped_links.append(link)
            seen.add(key)
    final["individual_job_links"] = deduped_links
    final["careers_url"] = careers_url
    return JobListingSchema.model_validate(final)


async def analyze_full_html_with_llm(
    html: str,
    url: str,
    listing_lm: JobListingLM,
    *,
    config: PipelineConfig | None = None,
    run_id: str | None = None,
) -> JobListingSchema:
    max_chunks = getattr(config, "listing_max_chunks", 8) if config else 8
    sleep_ms = getattr(config, "listing_chunk_sleep_ms", 200) if config else 200
    max_total_tokens = getattr(config, "listing_max_total_tokens", 500_000) if config else 500_000
    cache_dir = getattr(config, "listing_cache_dir", "") if config else ""

    cached = try_load_listing_cache(cache_dir, html)
    if cached is not None:
        if run_id:
            log_stage_event(
                run_id=run_id,
                stage="listing_llm",
                duration_ms=0.0,
                url=url,
                extra={"cache_hit": True, "tokens": cached.total_token_count},
            )
        return cached

    t0 = time.perf_counter()
    cleaned_body = await asyncio.to_thread(extract_minified_body_html, html)
    chunks = create_chunks_html_for_prompts(cleaned_body, max_chunks=max_chunks)
    responses: list[JobListingSchema | None] = []
    total_tokens = 0
    for chunk in chunks:
        if total_tokens >= max_total_tokens:
            logging.warning("[listing_llm] token budget exhausted; stopping chunks early")
            break
        prompt = make_chunk_prompt(chunk, url)
        result = await detect_job_listings(prompt, listing_lm)
        responses.append(result)
        if result is not None:
            total_tokens += result.total_token_count
        if sleep_ms > 0:
            await asyncio.sleep(sleep_ms / 1000.0)

    merged = merge_llm_chunk_responses(responses, url)
    save_listing_cache(cache_dir, html, merged)

    if run_id:
        log_stage_event(
            run_id=run_id,
            stage="listing_llm",
            duration_ms=(time.perf_counter() - t0) * 1000,
            url=url,
            tokens=merged.total_token_count,
            extra={"chunks": len(chunks), "cache_hit": False},
        )
    return merged


async def detect_job_listings(user_prompt: str, listing_lm: JobListingLM) -> JobListingSchema | None:
    try:
        return await listing_lm.invoke(user_prompt=user_prompt)
    except Exception as e:
        logging.info("[listing_llm] %s", e)
        return None
