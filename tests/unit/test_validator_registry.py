from __future__ import annotations

import unittest

from pydantic import BaseModel

import physicianx.llm.models  # noqa: F401 -- registers default schema validators
from physicianx.models import JobDetails, JobListingSchema
from physicianx.llm.validators import (
    JobDetailsOutputValidator,
    JobListingOutputValidator,
    PydanticValidator,
    register_model,
    validator_for,
)


class TestValidatorRegistry(unittest.TestCase):
    def test_validator_for_listing_and_details(self) -> None:
        v1 = validator_for(JobListingSchema)
        self.assertIsInstance(v1, JobListingOutputValidator)
        out = v1.validate({"is_job_listing": False, "score": 0.0, "has_pagination": False, "parent_container_selector": ""})
        self.assertIsInstance(out, JobListingSchema)

        v2 = validator_for(JobDetails)
        self.assertIsInstance(v2, JobDetailsOutputValidator)
        out2 = v2.validate(
            {
                "jobtitle": "t",
                "location": "",
                "required_skills": "",
                "compensation": "",
                "salary": None,
                "benefits": "",
            }
        )
        self.assertIsInstance(out2, JobDetails)

    def test_unknown_model_raises(self) -> None:
        class NeverRegistered(BaseModel):
            x: int

        with self.assertRaises(KeyError):
            validator_for(NeverRegistered)

    def test_register_model_allows_lookup(self) -> None:
        class RegModel(BaseModel):
            y: str

        register_model(RegModel, PydanticValidator(RegModel))
        v = validator_for(RegModel)
        self.assertEqual(v.validate({"y": "a"}).y, "a")


if __name__ == "__main__":
    unittest.main()
