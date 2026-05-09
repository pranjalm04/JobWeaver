"""Unit tests for the pure helpers in pipeline.stages.job_links."""

from __future__ import annotations

import unittest

from jobweaver.models import JobLink, JobListingSchema, ScrapedJobLink
from jobweaver.pipeline.stages.job_links import (
    _append_job_if_new,
    _apply_llm_link_fallback,
    try_extract_jobs_from_static_html,
)


def _spec(**overrides) -> JobListingSchema:
    base = dict(
        is_job_listing=True,
        score=5.0,
        has_pagination=False,
        parent_container_selector="",
        next_page_element=None,
        individual_job_links=[],
        child_job_link_selector=None,
        total_token_count=0,
        careers_url="https://example.com/careers",
    )
    base.update(overrides)
    return JobListingSchema.model_validate(base)


class TestAppendJobIfNew(unittest.TestCase):
    def test_appends_first_occurrence(self) -> None:
        jobs: list[ScrapedJobLink] = []
        _append_job_if_new(jobs, "Engineer", "https://example.com/jobs/1")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].url, "https://example.com/jobs/1")

    def test_skips_duplicate_url(self) -> None:
        jobs: list[ScrapedJobLink] = []
        _append_job_if_new(jobs, "Engineer", "https://example.com/jobs/1")
        _append_job_if_new(jobs, "Engineer (copy)", "https://example.com/jobs/1")
        self.assertEqual(len(jobs), 1)


class TestTryExtractJobsFromStaticHtml(unittest.TestCase):
    def test_extracts_links_inside_container(self) -> None:
        html = (
            "<html><body><div class='jobs'>"
            "<a href='/jobs/1' class='job'>Software Engineer</a>"
            "<a href='/jobs/2' class='job'>Data Scientist</a>"
            "</div></body></html>"
        )
        jobs = try_extract_jobs_from_static_html(
            html, "https://example.com", "div.jobs", "a.job"
        )
        assert jobs is not None
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0].url, "https://example.com/jobs/1")
        self.assertEqual(jobs[0].title, "Software Engineer")

    def test_returns_none_when_container_missing(self) -> None:
        html = "<html><body><div class='other'><a href='/x'>X</a></div></body></html>"
        self.assertIsNone(
            try_extract_jobs_from_static_html(html, "https://example.com", "div.jobs", "a")
        )

    def test_returns_none_when_no_child_matches(self) -> None:
        html = "<html><body><div class='jobs'></div></body></html>"
        self.assertIsNone(
            try_extract_jobs_from_static_html(html, "https://example.com", "div.jobs", "a.job")
        )

    def test_returns_none_for_blank_inputs(self) -> None:
        self.assertIsNone(try_extract_jobs_from_static_html("", "https://example.com", "div", "a"))
        self.assertIsNone(
            try_extract_jobs_from_static_html("<html/>", "https://example.com", "  ", "a")
        )
        self.assertIsNone(
            try_extract_jobs_from_static_html("<html/>", "https://example.com", "div", "")
        )

    def test_skips_anchors_without_href(self) -> None:
        html = (
            "<div class='jobs'>"
            "<a class='job'>No href</a>"
            "<a class='job' href='/jobs/1'>Engineer</a>"
            "</div>"
        )
        jobs = try_extract_jobs_from_static_html(
            html, "https://example.com", "div.jobs", "a.job"
        )
        assert jobs is not None
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].url, "https://example.com/jobs/1")

    def test_dedupes_repeated_urls(self) -> None:
        html = (
            "<div class='jobs'>"
            "<a class='job' href='/jobs/1'>A</a>"
            "<a class='job' href='/jobs/1'>A again</a>"
            "</div>"
        )
        jobs = try_extract_jobs_from_static_html(
            html, "https://example.com", "div.jobs", "a.job"
        )
        assert jobs is not None
        self.assertEqual(len(jobs), 1)


class TestApplyLlmLinkFallback(unittest.TestCase):
    def test_populates_when_jobs_empty_and_links_present(self) -> None:
        spec = _spec(
            individual_job_links=[
                JobLink(href="/jobs/1", text="Engineer", selector="a.j"),
                JobLink(href="/jobs/2", text="Nurse", selector="a.j"),
            ]
        )
        jobs: list[ScrapedJobLink] = []
        _apply_llm_link_fallback(spec, "https://example.com", jobs)
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0].url, "https://example.com/jobs/1")

    def test_noop_when_jobs_already_populated(self) -> None:
        spec = _spec(
            individual_job_links=[JobLink(href="/jobs/1", text="x", selector="a")]
        )
        jobs = [ScrapedJobLink(title="existing", url="https://example.com/keep")]
        _apply_llm_link_fallback(spec, "https://example.com", jobs)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].url, "https://example.com/keep")

    def test_noop_when_no_links_to_fall_back_to(self) -> None:
        spec = _spec(individual_job_links=[])
        jobs: list[ScrapedJobLink] = []
        _apply_llm_link_fallback(spec, "https://example.com", jobs)
        self.assertEqual(jobs, [])


if __name__ == "__main__":
    unittest.main()
