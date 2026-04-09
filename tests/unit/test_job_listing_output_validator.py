from __future__ import annotations

import unittest

from physicianx.llm.validators.exceptions import OutputValidationError
from physicianx.llm.validators.job_listing_output_validator import JobListingOutputValidator


class TestJobListingOutputValidator(unittest.TestCase):
    def setUp(self) -> None:
        self.v = JobListingOutputValidator()

    def test_not_listing_skips_selector_checks(self) -> None:
        out = self.v.validate(
            {
                "is_job_listing": False,
                "score": 0.0,
                "has_pagination": False,
                "parent_container_selector": "",
                "individual_job_links": [],
            }
        )
        self.assertFalse(out.is_job_listing)

    def test_listing_with_links_requires_parent_and_valid_selectors(self) -> None:
        payload = {
            "is_job_listing": True,
            "score": 5.0,
            "has_pagination": False,
            "parent_container_selector": "#root",
            "individual_job_links": [
                {"href": "/a", "text": "T", "selector": "a.job"},
            ],
        }
        out = self.v.validate(payload)
        self.assertTrue(out.is_job_listing)
        self.assertEqual(len(out.individual_job_links), 1)

    def test_invalid_link_selector_raises(self) -> None:
        payload = {
            "is_job_listing": True,
            "score": 5.0,
            "has_pagination": False,
            "parent_container_selector": "#root",
            "individual_job_links": [
                {"href": "/a", "text": "T", "selector": "div["},
            ],
        }
        with self.assertRaises(OutputValidationError):
            self.v.validate(payload)

    def test_child_job_link_selector_rejects_commas(self) -> None:
        payload = {
            "is_job_listing": True,
            "score": 5.0,
            "has_pagination": False,
            "parent_container_selector": "#root",
            "individual_job_links": [
                {"href": "/a", "text": "T", "selector": "a"},
            ],
            "child_job_link_selector": "a, b",
        }
        with self.assertRaises(OutputValidationError) as ctx:
            self.v.validate(payload)
        self.assertIn("comma", str(ctx.exception).lower())

    def test_missing_parent_when_links_raises(self) -> None:
        payload = {
            "is_job_listing": True,
            "score": 5.0,
            "has_pagination": False,
            "parent_container_selector": "",
            "individual_job_links": [
                {"href": "/a", "text": "T", "selector": "a"},
            ],
        }
        with self.assertRaises(OutputValidationError):
            self.v.validate(payload)


if __name__ == "__main__":
    unittest.main()
