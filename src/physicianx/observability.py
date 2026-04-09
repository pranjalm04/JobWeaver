"""Structured pipeline telemetry (JSON log lines for grep/metrics pipelines)."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

_log = logging.getLogger("physicianx.pipeline")


def log_stage_event(
    *,
    run_id: str,
    stage: str,
    duration_ms: float,
    seed: str | None = None,
    url: str | None = None,
    tokens: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "run_id": run_id,
        "stage": stage,
        "duration_ms": round(duration_ms, 2),
    }
    if seed is not None:
        payload["seed"] = seed
    if url is not None:
        payload["url"] = url
    if tokens is not None:
        payload["tokens"] = tokens
    if extra:
        payload.update(extra)
    _log.info(json.dumps(payload, ensure_ascii=False))


class StageTimer:
    """Context manager: records wall time and logs on exit."""

    def __init__(
        self,
        *,
        run_id: str,
        stage: str,
        seed: str | None = None,
        url: str | None = None,
        log_tokens: int | None = None,
        extra: dict[str, Any] | None = None,
    ):
        self.run_id = run_id
        self.stage = stage
        self.seed = seed
        self.url = url
        self.log_tokens = log_tokens
        self.extra = extra or {}
        self._t0: float = 0.0

    def __enter__(self) -> StageTimer:
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *args: object) -> None:
        duration_ms = (time.perf_counter() - self._t0) * 1000
        log_stage_event(
            run_id=self.run_id,
            stage=self.stage,
            duration_ms=duration_ms,
            seed=self.seed,
            url=self.url,
            tokens=self.log_tokens,
            extra=self.extra,
        )
