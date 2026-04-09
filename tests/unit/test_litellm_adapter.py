from __future__ import annotations

import asyncio
import sys
import types
import unittest

from physicianx.config.pipeline import PipelineConfig
from physicianx.llm.lm import parse_extra_headers_json
from physicianx.llm.models import JobListingLM
from physicianx.llm.session import LMSession


class _Resp:
    def __init__(self, text: str, usage=None):
        self.choices = [types.SimpleNamespace(message=types.SimpleNamespace(content=text))]
        self.usage = usage


class TestLMCallModel(unittest.TestCase):
    def setUp(self) -> None:
        self._orig = sys.modules.get("litellm")

    def tearDown(self) -> None:
        if self._orig is None:
            sys.modules.pop("litellm", None)
        else:
            sys.modules["litellm"] = self._orig

    def _install_fake_litellm(self, coro):
        sys.modules["litellm"] = types.SimpleNamespace(acompletion=coro)

    def test_call_model_maps_usage(self) -> None:
        captured: list[dict] = []

        async def fake_completion(**kwargs):
            captured.append(kwargs)
            return _Resp(
                '{"is_job_listing": false, "score": 0.0, "has_pagination": false, "parent_container_selector": ""}',
                usage=types.SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18),
            )

        self._install_fake_litellm(fake_completion)
        c = PipelineConfig(
            llm_api_key="k",
            llm_model_listing="openai/gpt-4o-mini",
            llm_model_job_detail="openai/gpt-4o-mini",
        )
        lm = JobListingLM(c)
        session = LMSession(session_id="s")
        session.add_system("sys")
        session.add_user("user")

        async def run():
            text, usage = await lm.call_model(session)
            self.assertIn("is_job_listing", text)
            self.assertEqual(usage.input_tokens, 11)
            self.assertEqual(usage.output_tokens, 7)
            self.assertEqual(usage.total_tokens, 18)
            self.assertEqual(captured[0]["model"], "openai/gpt-4o-mini")
            self.assertEqual(len(captured[0]["messages"]), 2)

        asyncio.run(run())

    def test_call_model_handles_missing_usage(self) -> None:
        async def fake_completion(**kwargs):
            _ = kwargs
            return _Resp(
                '{"is_job_listing": false, "score": 0.0, "has_pagination": false, "parent_container_selector": ""}',
                usage=None,
            )

        self._install_fake_litellm(fake_completion)
        c = PipelineConfig(
            llm_api_key="k",
            llm_model_listing="m",
            llm_model_job_detail="m",
        )
        lm = JobListingLM(c)
        session = LMSession(session_id="s")
        session.add_system("a")
        session.add_user("b")

        async def run():
            _, usage = await lm.call_model(session)
            self.assertIsNone(usage.input_tokens)
            self.assertIsNone(usage.output_tokens)
            self.assertIsNone(usage.total_tokens)

        asyncio.run(run())

    def test_parse_extra_headers_invalid_array_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_extra_headers_json('["x"]')


if __name__ == "__main__":
    unittest.main()
