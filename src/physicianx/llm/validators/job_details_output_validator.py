from __future__ import annotations

from typing import Any

from physicianx.models import JobDetails
from physicianx.llm.validators.exceptions import OutputValidationError


class JobDetailsOutputValidator:
    """Schema + detail-page-specific checks beyond Pydantic field types."""

    def validate(self, data: dict[str, Any]) -> JobDetails:
        job = JobDetails.model_validate(data)
        self._validate_domain(job)
        return job

    def _validate_domain(self, job: JobDetails) -> None:
        if not job.jobtitle or not job.jobtitle.strip():
            raise OutputValidationError("jobtitle must be non-empty after trimming whitespace.")

