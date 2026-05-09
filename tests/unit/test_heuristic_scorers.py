"""Unit tests for the named scoring helpers in pipeline.stages.heuristics."""

from __future__ import annotations

import unittest

from bs4 import BeautifulSoup

from jobweaver.pipeline.stages.heuristics import (
    _Scorer,
    _score_job_link_fragments,
    _score_pagination,
    _score_search_form,
    _score_title_keywords,
    _score_url_path,
    check_job_listing_heuristics,
)


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


class TestScoreTitleKeywords(unittest.TestCase):
    def test_strong_listing_keyword_in_title_adds_one_point_five(self) -> None:
        scorer = _Scorer()
        _score_title_keywords(_soup("<title>Job Openings</title>"), scorer)
        self.assertEqual(scorer.score, 1.5)

    def test_apply_now_in_h1_subtracts_one(self) -> None:
        scorer = _Scorer()
        _score_title_keywords(_soup("<h1>Apply Now for our team</h1>"), scorer)
        self.assertEqual(scorer.score, -1.0)

    def test_general_keyword_only_when_strong_absent(self) -> None:
        scorer = _Scorer()
        _score_title_keywords(_soup("<h1>Filter results</h1>"), scorer)
        self.assertEqual(scorer.score, 0.5)

    def test_general_keyword_skipped_if_strong_present(self) -> None:
        scorer = _Scorer()
        _score_title_keywords(
            _soup("<title>Career Opportunities</title><h1>Filter results</h1>"), scorer
        )
        # +1.5 (strong) only; +0.5 general is skipped because strong was found
        self.assertEqual(scorer.score, 1.5)

    def test_no_match_no_change(self) -> None:
        scorer = _Scorer()
        _score_title_keywords(_soup("<title>About us</title>"), scorer)
        self.assertEqual(scorer.score, 0.0)


class TestScoreUrlPath(unittest.TestCase):
    def test_listing_path_adds_one(self) -> None:
        scorer = _Scorer()
        _score_url_path("https://example.com/careers/openings", scorer)
        self.assertEqual(scorer.score, 1.0)

    def test_unrelated_path_no_score(self) -> None:
        scorer = _Scorer()
        _score_url_path("https://example.com/about", scorer)
        self.assertEqual(scorer.score, 0.0)

    def test_none_url_no_score(self) -> None:
        scorer = _Scorer()
        _score_url_path(None, scorer)
        self.assertEqual(scorer.score, 0.0)


class TestScorePagination(unittest.TestCase):
    def test_pagination_class_adds_one_point_five(self) -> None:
        scorer = _Scorer()
        _score_pagination(_soup('<nav class="pagination"><a>1</a></nav>'), scorer)
        self.assertEqual(scorer.score, 1.5)

    def test_next_keyword_in_link_adds_one(self) -> None:
        scorer = _Scorer()
        _score_pagination(_soup('<a href="/p2">Next</a>'), scorer)
        self.assertEqual(scorer.score, 1.0)

    def test_three_or_more_page_numbers_adds_half(self) -> None:
        scorer = _Scorer()
        _score_pagination(
            _soup('<a href="/1">1</a><a href="/2">2</a><a href="/3">3</a>'),
            scorer,
        )
        # 0.5 for page numbers; no next/prev keyword
        self.assertEqual(scorer.score, 0.5)

    def test_pagination_score_capped_at_one_point_two(self) -> None:
        scorer = _Scorer()
        _score_pagination(
            _soup(
                '<a href="/p2">Next</a>'
                '<a href="/1">1</a><a href="/2">2</a><a href="/3">3</a><a href="/4">4</a>'
            ),
            scorer,
        )
        # Without specific class: 1.0 + 0.5 = 1.5 → capped to 1.2
        self.assertEqual(scorer.score, 1.2)


class TestScoreSearchForm(unittest.TestCase):
    def test_form_with_keywords_adds_one(self) -> None:
        scorer = _Scorer()
        _score_search_form(_soup("<form>Search jobs here</form>"), scorer)
        self.assertEqual(scorer.score, 1.0)

    def test_form_with_relevant_input_adds_zero_point_eight(self) -> None:
        scorer = _Scorer()
        _score_search_form(_soup('<form><input name="keyword"/></form>'), scorer)
        self.assertEqual(scorer.score, 0.8)

    def test_unrelated_form_no_score(self) -> None:
        scorer = _Scorer()
        _score_search_form(_soup('<form><input name="email"/></form>'), scorer)
        self.assertEqual(scorer.score, 0.0)


class TestScoreJobLinkFragments(unittest.TestCase):
    def test_two_or_more_job_title_fragments_score_proportional(self) -> None:
        scorer = _Scorer()
        _score_job_link_fragments(
            _soup(
                '<a href="/r/1">Senior Software Engineer</a>'
                '<a href="/r/2">Registered Nurse</a>'
            ),
            scorer,
        )
        # 4.0 * min(2/5, 1) = 1.6
        self.assertAlmostEqual(scorer.score, 1.6, places=2)

    def test_single_match_below_threshold(self) -> None:
        scorer = _Scorer()
        _score_job_link_fragments(_soup('<a href="/r/1">Software Engineer</a>'), scorer)
        self.assertEqual(scorer.score, 0.0)

    def test_absolute_urls_excluded(self) -> None:
        scorer = _Scorer()
        _score_job_link_fragments(
            _soup(
                '<a href="https://other.com/x">Software Engineer</a>'
                '<a href="https://other.com/y">Registered Nurse</a>'
            ),
            scorer,
        )
        self.assertEqual(scorer.score, 0.0)

    def test_five_or_more_caps_at_four(self) -> None:
        scorer = _Scorer()
        _score_job_link_fragments(
            _soup(
                '<a href="/1">Software Engineer</a>'
                '<a href="/2">Registered Nurse</a>'
                '<a href="/3">Project Manager</a>'
                '<a href="/4">Data Scientist</a>'
                '<a href="/5">Senior Designer</a>'
                '<a href="/6">Junior Analyst</a>'
            ),
            scorer,
        )
        self.assertEqual(scorer.score, 4.0)


class TestCheckJobListingHeuristicsIntegration(unittest.TestCase):
    def test_known_listing_html_scores_above_three(self) -> None:
        html = (
            "<html><head><title>Job Openings</title></head><body>"
            "<h1>Career Opportunities</h1>"
            "<nav class='pagination'><a>Next</a><a>1</a><a>2</a><a>3</a></nav>"
            "<a href='/jobs/eng'>Software Engineer</a>"
            "<a href='/jobs/nurse'>Registered Nurse</a>"
            "</body></html>"
        )
        result = check_job_listing_heuristics(html, url="https://example.com/jobs")
        self.assertGreater(result.score, 3.0)
        # Expect scoring contributions from title/url/pagination/link-fragments
        self.assertGreaterEqual(len(result.debug_info), 4)

    def test_unrelated_html_scores_zero(self) -> None:
        result = check_job_listing_heuristics(
            "<html><body><p>About us</p></body></html>",
            url="https://example.com/about",
        )
        self.assertEqual(result.score, 0.0)

    def test_unparseable_html_returns_zero(self) -> None:
        # BeautifulSoup is forgiving; pass a non-string to force the except branch.
        result = check_job_listing_heuristics(None, url="https://example.com/jobs")  # type: ignore[arg-type]
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.debug_info, [])


if __name__ == "__main__":
    unittest.main()
