from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

from pydantic import BaseModel, ValidationError

from physicianx.models import JobListingSchema
from physicianx.llm.lm import LM, is_rate_limit_error
from physicianx.llm.session import LMSession
from physicianx.llm.validators.exceptions import OutputValidationError
from physicianx.llm.validators.job_listing_output_validator import JobListingOutputValidator
from physicianx.llm.validators.pydantic_validator import SchemaValidator


class JobListingLM(LM[JobListingSchema]):
    """Structured listing extraction per HTML chunk (fresh session per `invoke`)."""

    _listing_output_validator = JobListingOutputValidator()

    def model_id(self) -> str:
        return self._config.llm_model_listing

    def response_model(self) -> type[BaseModel]:
        return JobListingSchema

    def output_validator(self) -> SchemaValidator:
        return self._listing_output_validator

    def system_prompt(self, **ctx: Any) -> str:
        _ = ctx
        return (
            "You are a strict HTML job‑listing extractor. "
            "Output ONLY valid JSON that matches the provided schema. "
            "Never add commentary, explanations, or markdown."
        )

    def user_prompt(self, **ctx: Any) -> str:
        return str(ctx["user_prompt"])

    async def invoke(self, *, user_prompt: str) -> JobListingSchema | None:
        ctx: dict[str, Any] = {"user_prompt": user_prompt}
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
            return out if isinstance(out, JobListingSchema) else None

        return None


from physicianx.llm.validators.registry import register_model

register_model(JobListingSchema, JobListingLM._listing_output_validator)
