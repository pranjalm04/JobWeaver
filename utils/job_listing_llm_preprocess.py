from bs4 import BeautifulSoup, Comment
from typing import List, Optional
import re
import json
import time
from pydantic import BaseModel, Field
from google import genai
from google.genai import types


class NextPageElement(BaseModel):
    text: str = Field(..., description="Text of the next page button")
    href: str = Field(..., description="Href URL of the next page link")
    selector: str = Field(..., description="CSS selector of the element which points to next page")


class JobLink(BaseModel):
    href: str = Field(..., description="Href of the individual job listing")
    text: str = Field(..., description="Text shown for the job link")
    selector:str = Field(...,description="Css selector for job link. Prefer format like a.job-link, h2 > a, a[href^='/jobs/'], h2.job-title a, div.listing a.stretched-link.")


class JobListingSchema(BaseModel):
    is_job_listing: bool = Field(..., description="True if chunk looks like a job listing page")
    score: float = Field(..., description="The confidence score for detecting job listing page in range of 0-10")
    has_pagination: bool = Field(..., description="True if pagination is detected")
    parent_container_selector:str= Field(...,description="CSS selector of the closest element that encloses *all* these job links having valid job titles")
    next_page_element: Optional[NextPageElement] = Field(default=None, description="info of the element which point to next page if paginated")
    individual_job_links: List[JobLink] = Field(default_factory=list, description="List of job detail page links")
    child_job_link_selector: str = Field(default=None,description="CSS selector that matches all individual job links inside the parent container.")

def extract_minified_body_html(html: str, max_length: int = 10000) -> str:
    try:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "img", "iframe", "footer","header","svg","noscript"]):
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


def create_chunks_html_for_prompts(html: str, chunk_size=100000, chunk_overlap=1000) -> List:
    chunks = []
    for i in range(0, len(html), chunk_size):
        start = i - chunk_overlap if i > 0 else i
        chunk = html[start:start + chunk_size]
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
5.  **`child_job_link_selector`**: Generate a *single*, general CSS selector that matches *most* or *all* the individual job listing links within the `parent_container_selector`. This selector should be as simple as possible, using maybe one tag and one class or attribute. Examples: `a.job-card`, `a[href*='/job/']`, `div.job-item a`. **This selector must be a single string, without commas, spaces, newlines, or multiple combined selectors.** It should be a concise pattern that captures the job links. If no clear pattern exists, no job links are found, or `is_job_listing` is `false`, return an empty string.
6.  **`has_pagination`**: Set to `true` if elements clearly indicating navigation to the *next* page (e.g., "Next", ">", "Load More", numbered pages beyond the first) are visible and the page is identified as a job listing page. Otherwise, set to `false`.
7.  **`next_page_element`**: If `has_pagination` is `true`, extract the following for the *next* page element:
    * `text`: The visible text (e.g., "Next", "Load More").
    * `href`: The URL from the `href` attribute (if it's a link). If it's a button, the `href` can be an empty string.
    * `selector`: A simple CSS selector for the next page element (e.g., `a.next-page`, `button#load-more`). Avoid selecting previous page buttons or all pagination numbers. If `has_pagination` is `false`, this should be `null`.

### Output Format:
- You **MUST** output only a valid JSON object.
- The JSON object **MUST** strictly adhere to the `JobListingSchema` provided (implicitly, based on the field names and types described above).
- **DO NOT** include any extra text, explanations, markdown formatting (like ```json), or comments outside or inside the JSON.
- Ensure all fields are present in the output JSON.

Analyze only the HTML chunk below:

```html
{chunk}
"""
def merge_llm_chunk_responses(responses: list[dict],careers_url:str) -> dict:
    final = {
        "is_job_listing": False,
        "score": 0,
        "has_pagination": False,
        "parent_container_selector": '',
        "next_page_element": None,
        "individual_job_links": [],
        "total_token_count": 0,
        "careers_url":'',
        'child_job_link_selector':None
    }

    for resp in responses:
        if resp.get("is_job_listing"):
            final["is_job_listing"] = True
            final["individual_job_links"].extend(resp.get("individual_job_links", []))
            final["score"] = max(final["score"], resp.get("score", 0))
            final["total_token_count"] += resp.get("total_token_count", 0)
            final["child_job_link_selector"]=resp.get("child_job_link_selector")
            if resp.get("has_pagination") and not final["next_page_element"]:
                final["has_pagination"] = True

                final["next_page_element"] = resp.get("next_page_element")
            if final['child_job_link_selector'] == '':
                final['child_job_link_selector']=resp.get("child_job_link_selector")
            if final['parent_container_selector']=='':
                final['parent_container_selector']=resp.get("parent_container_selector")
    # Deduplicate job links
    seen = set()
    deduped_links = []
    for link in final["individual_job_links"]:
        key = link["href"]
        if key not in seen:
            deduped_links.append(link)
            seen.add(key)
    final["individual_job_links"] = deduped_links
    final["careers_url"]=careers_url
    return final


async def analyze_full_html_with_llm(html: str, url: str,client:genai.Client) -> dict:
    cleaned_body = extract_minified_body_html(html)
    chunks = create_chunks_html_for_prompts(cleaned_body)
    responses = []
    for chunk in chunks:
        prompt = make_chunk_prompt(chunk, url)
        result = await detect_job_listings(prompt,client)
        try:
            responses.append(result)
        except Exception as e:
            print(f"Error parsing response: {e}")
        time.sleep(1)

    return merge_llm_chunk_responses(responses,url)


async def detect_job_listings(user_prompt,client : genai.Client):
    generation_cfg = {
        "temperature": 0.1,
        "top_p": 0.3,
        "stop_sequences": ["```"],
        "max_output_tokens": 512,
        "candidate_count": 1,
    }
    SYSTEM_INST = (
        "You are a strict HTML job‑listing extractor. "
        "Output ONLY valid JSON that matches the provided schema. "
        "Never add commentary, explanations, or markdown."
    )
    config=types.GenerateContentConfig(
        system_instruction=SYSTEM_INST,
        temperature=0.1,
        top_p=0.3,
        # max_output_token=512,
        candidate_count=1,
        response_mime_type='application/json',
        response_schema= JobListingSchema
    )

    try:

        response = await client.aio.models.generate_content(
            model='gemini-2.0-flash',
            contents=user_prompt,
            config=config
        )
        raw_response = response.text
        print(raw_response)
        parsed_json = json.loads(raw_response)
        parsed_json["total_token_count"] = response.usage_metadata.total_token_count
        return parsed_json
    except Exception as e:
        print(f"[LLM Parsing Error] {e}")
        return None
