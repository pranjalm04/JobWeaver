from __future__ import annotations

from typing import Any

from physicianx.models import JobListingSchema
from physicianx.llm.validators.css_selectors import assert_css_selector_syntax
from physicianx.llm.validators.exceptions import OutputValidationError


class JobListingOutputValidator:
    """Schema + listing-specific checks (parsable CSS selectors, child selector shape)."""

    def validate(self, data: dict[str, Any]) -> JobListingSchema:
        spec = JobListingSchema.model_validate(data)
        self._validate_domain(spec)
        return spec

    def _validate_domain(self, spec: JobListingSchema) -> None:
        if not spec.is_job_listing:
            return

        if spec.individual_job_links:
            if not spec.parent_container_selector.strip():
                raise OutputValidationError(
                    "parent_container_selector must be set when is_job_listing is true and "
                    "individual_job_links is non-empty."
                )
            assert_css_selector_syntax(
                spec.parent_container_selector,
                field="parent_container_selector",
            )

        elif spec.parent_container_selector.strip():
            assert_css_selector_syntax(
                spec.parent_container_selector,
                field="parent_container_selector",
            )

        if spec.child_job_link_selector:
            raw = spec.child_job_link_selector.strip()
            if raw:
                if "," in raw:
                    raise OutputValidationError(
                        "child_job_link_selector must be a single selector without commas; "
                        f"got {raw!r}"
                    )
                assert_css_selector_syntax(raw, field="child_job_link_selector")

        for i, link in enumerate(spec.individual_job_links):
            assert_css_selector_syntax(
                link.selector,
                field=f"individual_job_links[{i}].selector",
            )

        if spec.has_pagination and spec.next_page_element is not None:
            np = spec.next_page_element
            assert_css_selector_syntax(np.selector, field="next_page_element.selector")
