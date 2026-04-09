import unittest

from physicianx.url import normalize_url, url_diff


class TestDomainUrl(unittest.TestCase):
    def test_normalize_url(self):
        out = normalize_url("/jobs?utm_source=a&ref=x&q=1#foo", "https://example.com")
        self.assertEqual(out, "https://example.com/jobs?q=1")

    def test_url_diff(self):
        self.assertEqual(
            url_diff("https://example.com/careers", "https://example.com/careers/jobs/dev"),
            "jobs/dev",
        )


if __name__ == "__main__":
    unittest.main()

