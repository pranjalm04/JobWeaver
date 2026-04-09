"""Job listing / detail Pydantic models and backward-compatible aliases."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class NextPageElement(BaseModel):
    text: str = Field(..., description="Text of the next page button")
    href: str = Field(..., description="Href URL of the next page link")
    selector: str = Field(
        ...,
        description="CSS selector of the element which points to next page",
    )


class JobLink(BaseModel):
    href: str = Field(..., description="Href of the individual job listing")
    text: str = Field(..., description="Text shown for the job link")
    selector: str = Field(
        ...,
        description="Css selector for job link",
    )


class JobListingSchema(BaseModel):
    is_job_listing: bool = Field(
        ..., description="True if chunk looks like a job listing page"
    )
    score: float = Field(
        ...,
        description="The confidence score for detecting job listing page in range of 0-10",
    )
    has_pagination: bool = Field(..., description="True if pagination is detected")
    parent_container_selector: str = Field(
        ...,
        description="CSS selector of the closest element that encloses *all* these job links",
    )
    next_page_element: Optional[NextPageElement] = Field(
        default=None,
        description="info of the element which point to next page if paginated",
    )
    individual_job_links: List[JobLink] = Field(
        default_factory=list,
        description="List of job detail page links",
    )
    child_job_link_selector: Optional[str] = Field(
        default=None,
        description="CSS selector that matches all individual job links inside the parent container.",
    )
    total_token_count: int = Field(default=0, description="LLM token usage for the extraction")
    careers_url: str = Field(
        default="",
        description="Base careers/job board URL used for scraping",
    )


JobListingSpec = JobListingSchema


class ScrapedJobLink(BaseModel):
    title: str = Field(default="", description="Best-effort job title")
    url: str = Field(..., description="Resolved job detail page URL")


class JobDetails(BaseModel):
    jobtitle: str = Field(..., description="The job title mentioned on the job details page")
    location: str = Field(..., description="location of the job position")
    required_skills: str = Field(..., description="skills required for the job")
    compensation: str = Field(..., description="compensation provided by the job")
    salary: Optional[str] = Field(default=None, description="salary range for the job position")
    benefits: str = Field(..., description="benefits provided by the job")
    total_token_count: Optional[int] = Field(
        default=None,
        description="LLM token usage for extraction",
    )


JobDetailsSchema = JobDetails

__all__ = [
    "JobDetails",
    "JobDetailsSchema",
    "JobLink",
    "JobListingSchema",
    "JobListingSpec",
    "NextPageElement",
    "ScrapedJobLink",
]
