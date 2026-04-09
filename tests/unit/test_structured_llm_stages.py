from __future__ import annotations

import asyncio
import unittest

from physicianx.models import JobDetails, JobListingSchema
from physicianx.pipeline.stages.job_details_llm import detect_job_schema
from physicianx.pipeline.stages.listing_llm import detect_job_listings


class FakeJobListingLM:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def invoke(self, *, user_prompt: str) -> JobListingSchema | None:
        self.calls.append(user_prompt)
        return JobListingSchema(
            is_job_listing=False,
            score=0.0,
            has_pagination=False,
            parent_container_selector="",
            next_page_element=None,
            individual_job_links=[],
            child_job_link_selector=None,
            total_token_count=42,
            careers_url="",
        )


class FakeJobDetailsLM:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def invoke(self, *, markdown: str) -> JobDetails | None:
        self.calls.append(markdown)
        return JobDetails(
            jobtitle="T",
            location="",
            required_skills="",
            compensation="",
            salary=None,
            benefits="",
            total_token_count=10,
        )


class TestFakeLlmStages(unittest.TestCase):
    def test_detect_job_listings_uses_listing_lm_invoke(self) -> None:
        fake = FakeJobListingLM()

        async def _run() -> None:
            out = await detect_job_listings("u", fake)
            self.assertIsNotNone(out)
            assert out is not None
            self.assertEqual(out.total_token_count, 42)
            self.assertEqual(len(fake.calls), 1)
            self.assertEqual(fake.calls[0], "u")

        asyncio.run(_run())

    def test_detect_job_schema_uses_details_lm_invoke(self) -> None:
        fake = FakeJobDetailsLM()

        async def _run() -> None:
            jd = await detect_job_schema("md-body", fake)
            self.assertIsNotNone(jd)
            assert jd is not None
            self.assertEqual(jd.jobtitle, "T")
            self.assertEqual(len(fake.calls), 1)
            self.assertEqual(fake.calls[0], "md-body")

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
