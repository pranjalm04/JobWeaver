import os

import requests
from bs4 import BeautifulSoup, Comment
from typing import List, Optional
import re
import json
import time
from pydantic import BaseModel, Field
from google import genai


class NextPageElement(BaseModel):
    text: str = Field(..., description="Text of the next page button")
    href: str = Field(..., description="Href URL of the next page link")
    selector: str = Field(..., description="CSS selector for the next page element")


class JobLink(BaseModel):
    href: str = Field(..., description="Href of the individual job listing")
    text: str = Field(..., description="Text shown for the job link")
    selector:str = Field(...,description="css selector for the job element.Just the selector and class or id not the value of id for e.g if its a[data-job-id='80000'] then a[data-job-id]")


class JobListingSchema(BaseModel):
    is_job_listing: bool = Field(..., description="True if chunk looks like a job listing page")
    score: float = Field(..., description="The confidence score for detecting job listing page in range of 0-10")
    has_pagination: bool = Field(..., description="True if pagination is detected")
    pagination_parent_container_selector:str= Field(...,description="css selector of the container containing all the individual job links")
    next_page_element: Optional[NextPageElement] = Field(None, description="Next page element info if paginated")
    individual_job_links: List[JobLink] = Field(default_factory=list, description="List of job detail page links")


def extract_minified_body_html(html: str, max_length: int = 10000) -> str:
    try:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "img", "iframe", "footer"]):
            tag.decompose()
        body = soup.body
        if body is None:
            return ""
        cleaned_html = body.decode_contents()
        # cleaned_html = re.sub(r"\s+", " ", cleaned_html)
        return cleaned_html
    except Exception as e:
        print(f"[HTML Parse Error]: {e}")
        return ""


def create_chunks_html_for_prompts(html: str, chunk_size=30000, chunk_overlap=1000) -> List:
    chunks = []
    for i in range(0, len(html), chunk_size):
        start = i - chunk_overlap if i > 0 else i
        chunk = html[start:start + chunk_size]
        chunks.append(chunk)
    return chunks


def make_chunk_prompt(chunk: str, source_url: str) -> str:
    return f"""
You are analyzing a chunk of HTML from a webpage. Your task is to determine if this chunk is part of a **job listing page**.

### Your Goal:
Detect pages that contain a **list of job titles** — nothing else qualifies as a job listing page.

### STRICT CRITERIA:
- Only identify a page as `is_job_listing = true` if the **visible text** includes **actual job titles** like:
  "Software Engineer", "Registered Nurse", "Marketing Manager", "Warehouse Associate", etc.
- **Do NOT use the `href` or surrounding tags** to infer job titles. Analyze only the visible **text** of the page.
- Do not mistake menu items, filter options, roles in dropdowns, or department names for job titles.

### JOB LINK EXTRACTION:
- If valid job titles are detected:
  - Extract their associated `<a>` tag `href` and text.
  - Add them to the `individual_job_links` list.
- If no valid job titles are found, the `individual_job_links` array should be empty.

### PAGINATION:
- If pagination elements are clearly visible (e.g., "Next", "Load more", numbered buttons for pages), set `has_pagination = true`.
- If no such element is visible, set `has_pagination = false`.
- If pagination is detected, extract the pagination element’s text, href, and CSS selector.

### DO NOT:
- Do not infer job listings from URL, metadata, or assumptions.
- Do not guess based on sections labeled “Departments”, “Job Areas”, “Career Tracks”, or “Locations”.
- Do not include any extra text or explanation — only return a valid JSON object matching the predefined schema.

### TASK OUTPUT (schema handled separately):
Return a structured JSON with:
- is_job_listing: boolean
- has_pagination: boolean
- next_page_element: object or null
- individual_job_links: list of text ,href"

Analyze only the chunk below:

```html
{chunk}
```"""


def merge_llm_chunk_responses(responses: list[dict]) -> dict:
    final = {
        "is_job_listing": False,
        "score": 0,
        "has_pagination": False,
        "pagination_parent_container_selector":'',
        "next_page_element": None,
        "individual_job_links": [],
        "total_token_count":0
    }

    for resp in responses:
        if resp.get("is_job_listing"):
            final["is_job_listing"] = True
            final["individual_job_links"].extend(resp.get("individual_job_links", []))
            final["score"] = max(final["score"], resp.get("score", 0))
            final["total_token_count"]+=resp.get("total_token_count",0)


            if resp.get("has_pagination") and not final["next_page_element"]:
                final["has_pagination"] = True
                final["pagination_parent_container_selector"]=resp.get("pagination_parent_container_selector")
                final["next_page_element"] = resp.get("next_page_element")

    # Deduplicate job links
    seen = set()
    deduped_links = []
    for link in final["individual_job_links"]:
        key = link["href"]
        if key not in seen:
            deduped_links.append(link)
            seen.add(key)
    final["individual_job_links"] = deduped_links
    return final


def analyze_full_html_with_llm(html: str, url: str) -> dict:
    cleaned_body = extract_minified_body_html(html)
    chunks = create_chunks_html_for_prompts(cleaned_body)
    responses = []
    for chunk in chunks:
        prompt = make_chunk_prompt(chunk, url)
        result = detect_job_listings(prompt)
        try:
            responses.append(result)
        except Exception as e:
            print(f"Error parsing response: {e}")
        time.sleep(1)

    return merge_llm_chunk_responses(responses)


def detect_job_listings(user_prompt):
    try:
        client = genai.Client(api_key=os.getenv("API_KEY_GEMINI"))
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=user_prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': JobListingSchema,
            },
        )
        raw_response = response.text
        parsed_json = json.loads(raw_response)
        parsed_json["total_token_count"]=response.usage_metadata.total_token_count
        return parsed_json
    except Exception as e:
        print(f"[LLM Parsing Error] {e}")
        return None
