from bs4 import BeautifulSoup, Comment
from typing import List
import re
import json
from mistralai.client import MistralClient
from mistralai import Mistral
import json
import time
from openai import OpenAI
def extract_minified_body_html(html: str, max_length: int = 10000) -> str:
    try:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style"]):
            tag.decompose()
        body = soup.body
        if body is None:
            return ""
        cleaned_html = body.decode_contents()
        cleaned_html = re.sub(r"\s+", " ", cleaned_html)
        return cleaned_html
    except Exception as e:
        print(f"[HTML Parse Error]: {e}")
        return ""
def create_chunks_html_for_prompts(html:str,chunk_size=10000,chunk_overlap=1000)->List:
    chunks=[]
    for i in range(0,len(html),chunk_size):
        start=i-chunk_overlap if i>0 else i
        chunk=html[start:start+chunk_size]
        chunks.append(chunk)
    return chunks
def make_chunk_prompt(chunk: str, source_url: str) -> str:
    return f"""
You are analyzing part of an HTML page to detect job listings.
dont assume any content, analyze content on the provided html chunk.
Page URL: {source_url}

This is a **chunk** of the `<body>` tag of the HTML. Your task is to determine if this chunk contains part of a job **listing page**.
Please analyze the HTML content of the chunk below and answer the following:

1. Is this a **job listing page**?
-> A job listing page will have list of job titles if it does mark "is_job_listing" as True and individual job listing page 
has details only of one job so do not confuse it with job listing page
2. Does it contain **pagination** (e.g., Next button or numbered links)?
3. If yes, provide:
   - The href or button text that links to the next page.
4. If no, provide:
   - The links (href and visible text) of individual job postings listed on this page.

Return JSON like this:
{{
  "is_job_listing": true,
  "has_pagination": true,
  "next_page_element": {{
    "text": "...",
    "href": "..."
  }},
  "individual_job_links": [
    {{"text": "...", "href": "..."}}
  ]
}}

HTML Chunk:
```html
{chunk}
"""
def merge_llm_chunk_responses(responses: list[dict]) -> dict:
    final = {
        "is_job_listing": False,
        "has_pagination": False,
        "next_page_element": None,
        "individual_job_links": []
    }

    for resp in responses:
        if resp.get("is_job_listing"):
            final["is_job_listing"] = True
            final["individual_job_links"].extend(resp.get("individual_job_links", []))

            if resp.get("has_pagination") and not final["next_page_element"]:
                final["has_pagination"] = True
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
    # print('final json',final)
    return final


def analyze_full_html_with_mistral(html: str, url: str) -> dict:
    cleaned_body = extract_minified_body_html(html)
    chunks = create_chunks_html_for_prompts(cleaned_body)

    responses = []
    for chunk in chunks:
        prompt = make_chunk_prompt(chunk, url)
        # Call mistral API here with the prompt
        result = detect_job_listings(prompt)  # <- plug in your API client
        # print(result)
        try:
            responses.append(result)
        except Exception as e:
            print(f"Error parsing response: {e}")
        time.sleep(2.3)
    return merge_llm_chunk_responses(responses)
def detect_job_listings(user_prompt):

    api_key = "guEDJaE2YX3qKA2OkrnTxfAamFFj29wX"

    api_key_deepseek='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'


    openai_client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key= api_key_deepseek,
    )

    chat_response = openai_client.chat.completions.create(
        model="openai/gpt-4",
        extra_body={
            "models": ["anthropic/claude-3.5-sonnet", "gryphe/mythomax-l2-13b"],
        },
        messages=[
            {
                "role": "system",
                "content": """"You are an expert HTML analyzer specialized in job websites.,
                You are given raw HTML of a webpage and asked to classify it and extract meaningful links."""
            },

            {
                "role": "user",
                "content": user_prompt
            }
        ]
    )

    # print(completion.choices[0].message.content)

#     client = Mistral(api_key=api_key)
#     model = "mistral-large-latest"
#     chat_response = client.chat.complete(
#         model=model,
#         messages=[
#             {
#                 "role": "system",
#                 "content": """"You are an expert HTML analyzer specialized in job websites.
# You are given raw HTML of a webpage and asked to classify it and extract meaningful links."""
#             },
#             {
#                 "role": "user",
#                 "content":user_prompt
#             }
#         ],
#         response_format={
#             "type": "json_object",
#         }
#     )

    try:
        raw_output = chat_response.choices[0].message.content
        print(raw_output)
        parsed_json = json.loads(raw_output)
        return parsed_json
    except Exception as e:
        print(f"[LLM Parsing Error] {e}")
        return None
