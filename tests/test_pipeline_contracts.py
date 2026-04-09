import unittest

from physicianx.url import normalize_url, url_diff

try:
    from physicianx.models import JobListingSchema
    from physicianx.pipeline.stages.heuristics import HeuristicResult, check_job_listing_heuristics
    from physicianx.pipeline.stages.listing_llm import merge_llm_chunk_responses

    _HAS_BS4 = True
except ModuleNotFoundError:
    _HAS_BS4 = False


class TestUrlUtils(unittest.TestCase):
    def test_normalize_url_strips_tracking_and_fragment(self):
        href = "/jobs?utm_source=abc&utm_medium=test&foo=bar#section"
        base = "https://example.com/careers/"
        normalized = normalize_url(href, base)
        self.assertEqual(normalized, "https://example.com/jobs?foo=bar")

    def test_url_diff_returns_relative_path(self):
        parent_url = "https://example.com/careers"
        child_url = "https://example.com/careers/jobs/software"
        self.assertEqual(url_diff(parent_url, child_url), "jobs/software")


class TestHeuristics(unittest.TestCase):
    @unittest.skipUnless(_HAS_BS4, "bs4 not installed")
    def test_check_job_listing_heuristics_returns_typed_result(self):
        html = """
        <html>
          <head><title>Jobs</title></head>
          <body>
            <h1>Careers</h1>
            <nav class="pagination">Next</nav>
            <a href="/jobs/1">Software Engineer</a>
            <a href="/jobs/2">Nurse</a>
          </body>
        </html>
        """.strip()

        result = check_job_listing_heuristics(html, url="https://example.com/jobs")
        self.assertIsInstance(result, HeuristicResult)
        self.assertGreater(result.score, 3.0)
        self.assertIsInstance(result.debug_info, list)

        score, debug_info = check_job_listing_heuristics(html, url="https://example.com/jobs")
        self.assertIsInstance(score, float)
        self.assertIsInstance(debug_info, list)


class TestListingMerge(unittest.TestCase):
    @unittest.skipUnless(_HAS_BS4, "bs4 not installed")
    def test_merge_llm_chunk_responses_dedupes_by_href_and_validates_schema(self):
        responses = [
            JobListingSchema.model_validate(
                {
                    "is_job_listing": True,
                    "score": 5.0,
                    "has_pagination": True,
                    "parent_container_selector": "div.jobs",
                    "next_page_element": {"text": "Next", "href": "/page2", "selector": "a.next"},
                    "individual_job_links": [
                        {"href": "/job/1", "text": "Role1", "selector": "a.role"},
                    ],
                    "child_job_link_selector": "a.role",
                    "total_token_count": 10,
                }
            ),
            JobListingSchema.model_validate(
                {
                    "is_job_listing": True,
                    "score": 7.0,
                    "has_pagination": False,
                    "parent_container_selector": "",
                    "next_page_element": None,
                    "individual_job_links": [
                        {"href": "/job/1", "text": "Role1 duplicate", "selector": "a.role"},
                    ],
                    "child_job_link_selector": "",
                    "total_token_count": 20,
                }
            ),
        ]

        spec = merge_llm_chunk_responses(responses, careers_url="https://example.com")
        self.assertTrue(spec.is_job_listing)
        self.assertEqual(spec.score, 7.0)
        self.assertTrue(spec.has_pagination)
        self.assertEqual(spec.total_token_count, 30)
        self.assertEqual(len(spec.individual_job_links), 1)
        self.assertEqual(spec.individual_job_links[0].href, "/job/1")


if __name__ == "__main__":
    unittest.main()
