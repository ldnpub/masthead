import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from extractors import choose_extractor, load_extractors
from extractors.base import ExtractError
from http_client import public_link, source_headers


MEMBER_HTML = """
<html><body>
  <p>Nav that should not be read.</p>
  <article class="member-body" data-author="Night Editor">
    <h1>The galley proof</h1>
    <h2>On the stone</h2>
    <p>The first paragraph of a fictional member article.</p>
    <p>The second paragraph stays on the desk.</p>
  </article>
</body></html>
"""


class ExtractorTests(unittest.TestCase):
    def test_registry_includes_the_example_and_the_fallback(self):
        extractors, errors = load_extractors()
        ids = [ext.id for ext in extractors]
        self.assertIn("example-member-press", ids)
        self.assertEqual(ids[-1], "readable")
        self.assertEqual(errors, [])

    def test_fictional_host_uses_the_example_extractor(self):
        ext = choose_extractor("https://members.example-press.test/galley")
        self.assertEqual(ext.id, "example-member-press")
        article = ext.extract("https://members.example-press.test/galley", MEMBER_HTML)
        self.assertEqual(article.title, "The galley proof")
        self.assertEqual(article.author, "Night Editor")
        self.assertTrue(article.blocks[0].startswith("#H# "))
        self.assertGreaterEqual(article.words, 8)

    def test_other_hosts_use_readable(self):
        ext = choose_extractor("https://example-press.test/city/story")
        self.assertEqual(ext.id, "readable")

    def test_explicit_id_and_unknown_id(self):
        ext = choose_extractor("https://example-press.test/x", "readable")
        self.assertEqual(ext.id, "readable")
        with self.assertRaises(ExtractError):
            choose_extractor("https://example-press.test/x", "not-a-real-extractor")

    def test_example_refuses_unrelated_markup(self):
        ext = choose_extractor("https://members.example-press.test/x", "example-member-press")
        with self.assertRaises(ExtractError):
            ext.extract("https://members.example-press.test/x", "<p>Nothing to read.</p>")


class LinkTests(unittest.TestCase):
    def test_public_link_strips_query_secrets(self):
        url = public_link("https://members.example-press.test/a?token=hide-me&page=2")
        self.assertEqual(url, "https://members.example-press.test/a?page=2")

    def test_source_headers_basic_and_cookie(self):
        basic = source_headers({"auth": {"scheme": "basic", "username": "ada", "password": "secret"}})
        self.assertTrue(basic["Authorization"].startswith("Basic "))
        cookie = source_headers({"auth": {"scheme": "cookie", "cookie": "session=local"}})
        self.assertEqual(cookie["Cookie"], "session=local")


if __name__ == "__main__":
    unittest.main()
