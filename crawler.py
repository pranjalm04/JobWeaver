"""Compatibility entrypoint.

Prefer `poetry run physicianx run-pipeline` or Celery tasks for production.
"""

import asyncio

if __name__ == "__main__":
    from physicianx.pipeline.runner import run_pipeline_from_env

    asyncio.run(run_pipeline_from_env())
