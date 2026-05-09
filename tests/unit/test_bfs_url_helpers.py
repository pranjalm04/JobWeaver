"""Unit tests for BFSCrawl URL filtering, prioritization, and dedup helpers."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from physicianx.pipeline.stages.crawl import BFSCrawl, JOB_PATTERNS


def _make_bfs() -> BFSCrawl:
    return BFSCrawl(
        start_url="https://example.com/careers",
        max_depth=2,
        crawler=MagicMock(),
        include_external=False,
    )


class TestCanProcessUrl(unittest.TestCase):
    def setUp(self) -> None:
        self.bfs = _make_bfs()

    def test_valid_http_url(self) -> None:
        self.assertTrue(
            self.bfs.can_process_url(
                "https://example.com/jobs/1",
                "https://example.com/jobs/1",
                "https://example.com/careers",
            )
        )

    def test_empty_href_rejected(self) -> None:
        self.assertFalse(self.bfs.can_process_url("", "", "https://example.com/careers"))

    def test_fragment_only_rejected(self) -> None:
        self.assertFalse(
            self.bfs.can_process_url(
                "#section",
                "https://example.com/careers#section",
                "https://example.com/careers",
            )
        )

    def test_non_http_scheme_rejected(self) -> None:
        self.assertFalse(
            self.bfs.can_process_url(
                "mailto:hr@example.com",
                "mailto:hr@example.com",
                "https://example.com/careers",
            )
        )

    def test_missing_domain_rejected(self) -> None:
        self.assertFalse(
            self.bfs.can_process_url(
                "/jobs/1",
                "/jobs/1",
                "https://example.com/careers",
            )
        )

    def test_same_page_rejected(self) -> None:
        # Same scheme + netloc + path → "same page"
        self.assertFalse(
            self.bfs.can_process_url(
                "https://example.com/careers/",
                "https://example.com/careers/",
                "https://example.com/careers",
            )
        )

    def test_invalid_netloc_no_dot_rejected(self) -> None:
        self.assertFalse(
            self.bfs.can_process_url(
                "https://localhost/jobs",
                "https://localhost/jobs",
                "https://example.com/careers",
            )
        )


class TestPrioritizeUrls(unittest.TestCase):
    def setUp(self) -> None:
        self.bfs = _make_bfs()

    def test_url_with_jobs_path_prioritized(self) -> None:
        self.assertEqual(
            self.bfs.prioritizeUrls("https://example.com/jobs/123", None),
            "https://example.com/jobs/123",
        )

    def test_url_with_careers_path_prioritized(self) -> None:
        self.assertEqual(
            self.bfs.prioritizeUrls("https://example.com/careers", None),
            "https://example.com/careers",
        )

    def test_unrelated_url_not_prioritized(self) -> None:
        self.assertIsNone(self.bfs.prioritizeUrls("https://example.com/about", None))

    def test_anchor_text_can_promote_unrelated_url(self) -> None:
        self.assertEqual(
            self.bfs.prioritizeUrls("https://example.com/page", "View Open Jobs"),
            "https://example.com/page",
        )

    def test_module_level_pattern_matches_directly(self) -> None:
        # Sanity check that JOB_PATTERNS is the regex powering the helper.
        self.assertIsNotNone(JOB_PATTERNS.search("/careers/team"))
        self.assertIsNone(JOB_PATTERNS.search("/about/leadership"))


class TestDedupeNextLevel(unittest.TestCase):
    def test_dedup_within_call_and_against_seen_set(self) -> None:
        seen: set[str] = {"https://example.com/already-seen"}
        next_level = [
            ("https://example.com/a", "src", 1),
            ("https://example.com/a", "src", 1),  # dup within batch
            ("https://example.com/b", "src", 1),
            ("https://example.com/already-seen", "src", 1),  # dup vs prior
        ]
        deduped = BFSCrawl._dedupe_next_level(next_level, seen)
        urls = [url for url, _, _ in deduped]
        self.assertEqual(urls, ["https://example.com/a", "https://example.com/b"])
        # `seen` is mutated to include newly-yielded urls
        self.assertIn("https://example.com/a", seen)
        self.assertIn("https://example.com/b", seen)

    def test_empty_input_returns_empty(self) -> None:
        self.assertEqual(BFSCrawl._dedupe_next_level([], set()), [])


if __name__ == "__main__":
    unittest.main()
