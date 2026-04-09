from __future__ import annotations

import unittest

from physicianx.llm.validators.exceptions import OutputValidationError
from physicianx.llm.validators.job_details_output_validator import JobDetailsOutputValidator


class TestJobDetailsOutputValidator(unittest.TestCase):
    def setUp(self) -> None:
        self.v = JobDetailsOutputValidator()

    def test_valid_passes(self) -> None:
        out = self.v.validate(
            {
                "jobtitle": "Engineer",
                "location": "",
                "required_skills": "",
                "compensation": "",
                "salary": None,
                "benefits": "",
            }
        )
        self.assertEqual(out.jobtitle, "Engineer")

    def test_empty_jobtitle_raises(self) -> None:
        with self.assertRaises(OutputValidationError):
            self.v.validate(
                {
                    "jobtitle": "   ",
                    "location": "",
                    "required_skills": "",
                    "compensation": "",
                    "salary": None,
                    "benefits": "",
                }
            )


if __name__ == "__main__":
    unittest.main()
