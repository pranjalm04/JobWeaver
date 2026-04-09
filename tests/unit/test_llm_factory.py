from __future__ import annotations

import unittest

from physicianx.config.pipeline import PipelineConfig
from physicianx.models import JobListingSchema
from physicianx.llm.lm import ensure_pipeline_llm_config
from physicianx.llm.models import JobListingLM
from physicianx.llm.validators import JobListingOutputValidator


class TestPipelineConfigLlm(unittest.TestCase):
    def test_resolved_llm_api_key_prefers_llm_api_key(self) -> None:
        c = PipelineConfig(
            llm_provider="gemini",
            llm_api_key="primary",
            api_key_gemini="legacy",
        )
        self.assertEqual(c.resolved_llm_api_key(), "primary")

    def test_resolved_llm_api_key_falls_back_to_api_key_gemini_for_gemini(self) -> None:
        c = PipelineConfig(
            llm_provider="gemini",
            llm_api_key="",
            api_key_gemini="legacy-only",
        )
        self.assertEqual(c.resolved_llm_api_key(), "legacy-only")

    def test_ensure_pipeline_llm_config_ok(self) -> None:
        c = PipelineConfig(
            llm_api_key="test-key-for-factory",
            llm_model_listing="openai/gpt-4o-mini",
            llm_model_job_detail="openai/gpt-4o-mini",
        )
        ensure_pipeline_llm_config(c)

    def test_ensure_pipeline_llm_config_raises_without_key(self) -> None:
        c = PipelineConfig(
            llm_provider="openai",
            llm_api_key="",
            api_key_gemini="",
            llm_model_listing="openai/gpt-4o-mini",
            llm_model_job_detail="openai/gpt-4o-mini",
        )
        with self.assertRaises(ValueError):
            ensure_pipeline_llm_config(c)

    def test_ensure_pipeline_llm_config_raises_without_models(self) -> None:
        c = PipelineConfig(
            llm_provider="openrouter",
            llm_api_key="sk-test",
            llm_model_listing="",
            llm_model_job_detail="",
        )
        with self.assertRaises(ValueError):
            ensure_pipeline_llm_config(c)

    def test_job_listing_lm_builds_with_config(self) -> None:
        c = PipelineConfig(
            llm_api_key="k",
            llm_model_listing="openai/gpt-4o-mini",
            llm_model_job_detail="openai/gpt-4o-mini",
        )
        lm = JobListingLM(c)
        self.assertEqual(lm.model_id(), "openai/gpt-4o-mini")
        v = lm.output_validator()
        self.assertIsInstance(v, JobListingOutputValidator)
        self.assertIs(v, JobListingLM._listing_output_validator)
        self.assertIsInstance(
            v.validate(
                {
                    "is_job_listing": False,
                    "score": 0.0,
                    "has_pagination": False,
                    "parent_container_selector": "",
                }
            ),
            JobListingSchema,
        )


if __name__ == "__main__":
    unittest.main()
