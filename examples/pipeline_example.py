"""Minimal local run: configure `.env` (API_KEY_GEMINI, SEED_URLS), then:

    PYTHONPATH=src python examples/pipeline_example.py
"""

from __future__ import annotations

import asyncio

from physicianx.pipeline.runner import run_pipeline_from_env


if __name__ == "__main__":
    asyncio.run(run_pipeline_from_env())
