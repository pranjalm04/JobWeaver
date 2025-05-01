import asyncio

import aiofiles
from bs4 import BeautifulSoup, Comment
from typing import List, Optional
import re
import json
import time
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from crawl4ai import AsyncWebCrawler, MemoryAdaptiveDispatcher, PruningContentFilter, DefaultMarkdownGenerator

job_details_task=[]
prune_filter = PruningContentFilter(
    # Lower → more content retained, higher → more content pruned
    threshold=0.2,
    # "fixed" or "dynamic"
    threshold_type="dynamic",
    # Ignore nodes with <5 words
    min_word_threshold=5
)
md_generator = DefaultMarkdownGenerator(content_filter=prune_filter)
class JobDetailsSchema(BaseModel):
    jobtitle: str = Field(..., description="The job title mentioned on the job details page")
    location: str = Field(..., description="location of the job position")
    required_skills: str = Field(..., description="skills required for the job")
    compensation:str= Field(...,description="compensation provided by the job")
    salary: str= Field(default=None, description="salary range for the job position")
    benefits:str = Field(description="benefits provided by the job")


def job_prompt(markdown:str):
    return  f"""
    You are an expert information extractor specializing in job details pages. Your task is to analyze the provided text, which is a markdown representation of an HTML job details page, and extract specific attributes about the single job listing presented on this page.

    You MUST output ONLY a valid JSON object that strictly conforms to the following schema:

    ```json
    {{
      "jobtitle": "string",
      "location": "string",
      "required_skills": "boolean",
      "compensation": "string",
      "salary": "string or null",
      "benefits": "string"
    }}
    ```

    ### Extraction Instructions:

    1.  **`jobtitle`**:
        * Identify the main title of the job posting.
        * Look for prominent text, often found at the top of the page, within heading tags (`#`, `##`, etc., corresponding to `<h1>`, `<h2>` in HTML) or elements with class names like "job-title", "title", "position-title".
        * Extract the full, exact job title text.

    2.  **`location`**:
        * Find the location(s) where the job is based.
        * Look for text near keywords like "Location:", "Work Location:", "Office:", "Remote", "Hybrid", or specific city, state, or country names.
        * This information might be in paragraphs, list items, or spans, often near the job title or in a dedicated section.
        * Extract the location text as accurately as possible (e.g., "New York, NY", "Remote", "London, UK - Hybrid").

    3.  **`required_skills`**:
        * **Extract the full text** from the section(s) explicitly listing required skills, qualifications, or minimum requirements for the job.
        * Look for sections with headings like "Requirements", "Qualifications", "Required Skills", "Minimum Experience", "Must Have", "Skills".
        * Extract the content of these sections as a single string. If multiple such sections exist, concatenate their content.
        * If no such explicit section is found, return an empty string "".
        
    4.  **`compensation`**:
        * Find information related to the overall compensation package.
        * Look for sections or text discussing pay, salary, wages, compensation, or total rewards.
        * This might include details about hourly rates, salary ranges, bonuses, or a general statement about competitive pay.
        * Extract the *text* describing the compensation details. If no specific compensation details are found, provide a general statement if available (e.g., "Competitive compensation"). If no information is present, return an empty string.

    5.  **`salary`**:
        * Within the compensation information, specifically look for a stated salary range or a fixed salary figure.
        * Extract the salary range or figure as a string (e.g., "$60,000 - $80,000", "£30/hour", "Negotiable").
        * If a specific salary range or figure is not explicitly mentioned, even if compensation is discussed, set this field to `null`.

    6.  **`benefits`**:
        * Find information detailing the benefits offered with the job.
        * Look for sections with headings like "Benefits", "Perks", "What We Offer", "Employee Benefits".
        * This typically includes health insurance, dental, vision, paid time off (PTO), vacation, sick leave, retirement plans (401k, pension), life insurance, etc.
        * Extract the *text* describing the benefits. If no specific benefits are listed, return an empty string.

    ### Constraints:

    * Analyze ONLY the provided markdown text.
    * Extract ONLY the information requested for each field.
    * Output ONLY the JSON object. Do not include any introductory text, explanations, or markdown code block formatting (like ```json).
    * Ensure the JSON is valid and matches the specified schema exactly.

    Analyze the following markdown text (converted from HTML):

    ```
    {markdown}
    ```
    """

async def detect_job_schema(user_prompt,client : genai.Client):

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
        response_schema= JobDetailsSchema
    )

    try:
        response = await client.aio.models.generate_content(
            model='gemini-2.0-flash',
            contents=user_prompt,
            config=config
        )
        raw_response = response.text
        parsed_json = json.loads(raw_response)
        parsed_json["total_token_count"] = response.usage_metadata.total_token_count
        return parsed_json
    except Exception as e:
        print(f"[LLM Parsing Error] {e}")
        return None
async def extract_job_data(crawler:AsyncWebCrawler,urls,config,genaiclient:genai.Client):
    urls=urls[:10]
    print(urls)
    for i in range(0, len(urls), 20):
        batch = urls[i:i + 20]

        dispatcher = MemoryAdaptiveDispatcher(
            memory_threshold_percent=90.0,
            check_interval=1.0,
            max_session_permit=10,
            monitor=None
        )
        batch_config = config.clone(deep_crawl_strategy=None, stream=False, markdown_generator=md_generator)
        result_batch = await crawler.arun_many(
            urls=batch,
            config=batch_config,
            dispatcher=dispatcher
        )
        for result in result_batch:
            if isinstance(result, Exception):
                print("Error parsing url {}")
            elif result.success:
                task=asyncio.create_task(detect_job_schema(job_prompt(result.markdown.fit_markdown),genaiclient))
                job_details_task.append(task)
        await save_jobs()


async def save_jobs():
    job_detail_result=await asyncio.gather(*job_details_task,return_exceptions=True)
    async with aiofiles.open('job_details.json', mode="a", encoding="utf-8") as f:
        for jd in job_detail_result:
            print(jd)
            if isinstance(jd,Exception):
                print("result unavilable")
            else:
                try:
                    await f.write(json.dumps(jd, ensure_ascii=False) + "\n")
                except Exception as e:
                    print(f"[job details save error] {jd}: {e}")


