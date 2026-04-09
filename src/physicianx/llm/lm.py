from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from physicianx.config.pipeline import PipelineConfig
from physicianx.models import JobDetails, JobListingSchema
from physicianx.llm.session import LMSession
from physicianx.llm.usage import Usage
from physicianx.llm.validators.pydantic_validator import SchemaValidator

TSchema = TypeVar("TSchema", bound=BaseModel)


def ensure_pipeline_llm_config(config: PipelineConfig) -> None:
    """Raise if environment is missing required LLM settings for pipeline runs."""

    if not config.resolved_llm_api_key():
        raise ValueError("LLM API key is missing. Set LLM_API_KEY (or legacy API_KEY_GEMINI).")
    if not config.llm_model_listing.strip() or not config.llm_model_job_detail.strip():
        raise ValueError("LLM model ids are missing. Set LLM_MODEL_LISTING and LLM_MODEL_JOB_DETAIL.")


def is_rate_limit_error(exc: BaseException) -> bool:
    s = str(exc).lower()
    return "429" in s or "resource exhausted" in s or ("rate" in s and "limit" in s)


def parse_extra_headers_json(raw: str) -> dict[str, str] | None:
    if not raw.strip():
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("LLM_EXTRA_HEADERS_JSON must be a JSON object.")
    return {str(k): str(v) for k, v in parsed.items()}


class LM(ABC, Generic[TSchema]):
    """Task-specific LM: prompts, validator, `call_model` (single LiteLLM call); subclasses implement `invoke` with retries."""

    def __init__(self, config: PipelineConfig) -> None:
        self._config = config

    def establish_session_id(self) -> str:
        return uuid.uuid4().hex

    def llm_temperature(self) -> float:
        return 0.1

    def llm_top_p(self) -> float:
        return 0.3

    async def call_model(self, session: LMSession) -> tuple[str, Usage]:
        """One LiteLLM completion from the current session messages; no retries."""

        try:
            from litellm import acompletion
        except ImportError as e:
            raise ImportError("LiteLLM requires the 'litellm' package.") from e

        api_key = self._config.resolved_llm_api_key()
        if not api_key:
            raise ValueError("LLM API key is missing. Set LLM_API_KEY (or legacy API_KEY_GEMINI).")

        base = self._config.llm_api_base.strip() or None
        extra = parse_extra_headers_json(self._config.llm_extra_headers_json)
        response = await acompletion(
            model=self.model_id(),
            api_key=api_key,
            api_base=base,
            extra_headers=extra,
            response_format={"type": "json_object"},
            temperature=self.llm_temperature(),
            top_p=self.llm_top_p(),
            messages=session.messages_for_completion(),
        )
        text = response.choices[0].message.content or "{}"
        usage_raw = getattr(response, "usage", None)
        usage = Usage(
            input_tokens=getattr(usage_raw, "prompt_tokens", None) if usage_raw else None,
            output_tokens=getattr(usage_raw, "completion_tokens", None) if usage_raw else None,
            total_tokens=getattr(usage_raw, "total_tokens", None) if usage_raw else None,
        )
        return text, usage

    @abstractmethod
    def model_id(self) -> str: ...

    @abstractmethod
    def response_model(self) -> type[BaseModel]: ...

    @abstractmethod
    def output_validator(self) -> SchemaValidator:
        """Validator for LLM JSON output; must match `response_model` semantics."""

    @abstractmethod
    async def invoke(self, **ctx: Any) -> TSchema | None: ...

    @abstractmethod
    def system_prompt(self, **ctx: Any) -> str: ...

    @abstractmethod
    def user_prompt(self, **ctx: Any) -> str: ...

    def repair_user_prompt(self, *, errors: str, attempt: int, **ctx: Any) -> str:
        _ = ctx
        return (
            f"The previous JSON was invalid or did not match the schema (attempt {attempt + 1}).\n"
            f"Errors:\n{errors}\n"
            "Reply with a single corrected JSON object only."
        )

    def with_token_usage(self, model: BaseModel, usage: Usage) -> BaseModel:
        total = usage.total_tokens
        if isinstance(model, JobListingSchema):
            return model.model_copy(update={"total_token_count": total or 0})
        if isinstance(model, JobDetails):
            return model.model_copy(update={"total_token_count": total})
        return model
