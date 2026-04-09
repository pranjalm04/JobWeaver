from __future__ import annotations


class OutputValidationError(Exception):
    """LLM output passed Pydantic schema but failed domain-specific checks (e.g. selector syntax)."""

