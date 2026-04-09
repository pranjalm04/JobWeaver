from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

from pydantic import BaseModel, ValidationError

from physicianx.models import JobDetails
from physicianx.llm.lm import LM, is_rate_limit_error
from physicianx.llm.session import LMSession
from physicianx.llm.validators.exceptions import OutputValidationError
from physicianx.llm.validators.job_details_output_validator import JobDetailsOutputValidator
from physicianx.llm.validators.pydantic_validator import SchemaValidator


class JobDetailsLM(LM[JobDetails]):
    """Structured job-detail extraction per page (fresh session per `invoke`). Prompts live here, not in pipeline stages."""

    _details_output_validator = JobDetailsOutputValidator()

    def model_id(self) -> str:
        return self._config.llm_model_job_detail

    def response_model(self) -> type[BaseModel]:
        return JobDetails

    def output_validator(self) -> SchemaValidator:
        return self._details_output_validator

    def system_prompt(self, **ctx: Any) -> str:
        _ = ctx
        return (
            "You are a strict job-detail page extractor. "
            "Output ONLY valid JSON that matches the provided schema. "
            "Never add commentary, explanations, or markdown."
        )

    def user_prompt(self, **ctx: Any) -> str:
        markdown = str(ctx["markdown"])
        return f"""
    You are an expert information extractor specializing in job details pages. Your task is to analyze the provided text, which is a markdown representation of an HTML job details page, and extract specific attributes about the single job listing presented on this page.

    You MUST output ONLY a valid JSON object that strictly conforms to the following schema:

    ```json
    {{
      "jobtitle": "string",
      "location": "string",
      "required_skills": "string",
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

    async def invoke(self, *, markdown: str) -> JobDetails | None:
        ctx: dict[str, Any] = {"markdown": markdown}
        session = LMSession(session_id=self.establish_session_id())
        session.add_system(self.system_prompt(**ctx))
        session.add_user(self.user_prompt(**ctx))
        validator = self.output_validator()
        max_retries = self._config.llm_max_retries
        base_ms = self._config.llm_retry_base_ms

        for attempt in range(max_retries + 1):
            transport_attempt = 0
            text: str | None = None
            usage = None
            while True:
                try:
                    text, usage = await self.call_model(session)
                except Exception as e:
                    if transport_attempt < max_retries and is_rate_limit_error(e):
                        transport_attempt += 1
                        delay = (base_ms / 1000.0) * (2**transport_attempt) + random.uniform(0, 0.25)
                        logging.warning("[llm] retry after rate limit (%s): %.2fs", e, delay)
                        await asyncio.sleep(delay)
                        continue
                    logging.info("[llm] transport error: %s", e)
                    return None
                break

            assert text is not None and usage is not None

            try:
                payload: dict[str, Any] = json.loads(text)
            except json.JSONDecodeError as e:
                session.add_assistant(text)
                session.add_user(self.repair_user_prompt(errors=f"Invalid JSON: {e}", attempt=attempt))
                continue

            try:
                validated = validator.validate(payload)
            except (ValidationError, OutputValidationError) as e:
                session.add_assistant(text)
                session.add_user(self.repair_user_prompt(errors=str(e), attempt=attempt, **ctx))
                continue

            out = self.with_token_usage(validated, usage)
            return out if isinstance(out, JobDetails) else None

        return None


from physicianx.llm.validators.registry import register_model

register_model(JobDetails, JobDetailsLM._details_output_validator)
