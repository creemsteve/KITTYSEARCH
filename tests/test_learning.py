import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import kittysearch as core


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name)
        self.patch = patch.object(core, "data_dir", return_value=self.home)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def search(self, urls):
        items = [{"url": url, "title": "Example", "content": "Relevant source"} for url in urls]
        with patch.object(core, "http_json", return_value={"results": items}):
            return core.search("example", core.DEFAULTS)

    def test_first_search_does_not_create_database(self):
        self.assertFalse(self.search(["https://example.com/a"])["results"][0]["kitty_ai_generated"])
        self.assertFalse((self.home / "learning.sqlite3").exists())

    def test_page_persists_normalizes_and_preserves_queries(self):
        core.set_feedback("https://EXAMPLE.com:443/a?q=one#first", "page")
        core.set_feedback("https://example.com/a?q=one#second", "page")
        self.assertEqual(core.load_feedback()["page"], {"https://example.com/a?q=one"})
        data = self.search(["https://example.com/a?q=one#third", "https://example.com/a?q=two", "https://example.com/b"])
        flags = {item["url"]: item["kitty_user_flags"] for item in data["results"]}
        self.assertEqual(flags["https://example.com/a?q=one#third"], ["page"])
        self.assertEqual(flags["https://example.com/a?q=two"], [])
        self.assertEqual(flags["https://example.com/b"], [])

    def test_website_applies_to_all_pages_but_not_other_hosts(self):
        core.set_feedback("https://example.com/a", "website")
        data = self.search(["http://example.com/other", "https://example.com:8443/a", "https://sub.example.com/a", "https://example.com.evil.org/a"])
        flags = {item["url"]: item["kitty_user_flags"] for item in data["results"]}
        self.assertEqual(flags["http://example.com/other"], ["website"])
        self.assertEqual(flags["https://example.com:8443/a"], ["website"])
        self.assertEqual(flags["https://sub.example.com/a"], [])
        self.assertEqual(flags["https://example.com.evil.org/a"], [])

    def test_flags_rerank_once_and_undo_restores_original_review(self):
        items = self.search(["https://example.com/a", "https://other.org/b"])["results"]
        original = copy.deepcopy(items[0])
        core.set_feedback(original["url"], "page")
        core.set_feedback(original["url"], "website")
        for _ in range(3):
            core.apply_feedback(items, core.load_feedback())
        flagged = items[-1]
        self.assertEqual(flagged["url"], original["url"])
        self.assertEqual(flagged["kitty_score"], max(0, original["kitty_score"] - 30))
        self.assertEqual(flagged["kitty_user_flags"], ["page", "website"])
        core.remove_feedback("page", core.feedback_target(original["url"], "page"))
        core.apply_feedback(items, core.load_feedback())
        self.assertTrue(flagged["kitty_ai_generated"])
        self.assertEqual(flagged["kitty_user_flags"], ["website"])
        core.remove_feedback("website", "example.com")
        core.apply_feedback(items, core.load_feedback())
        for field in ("kitty_score", "kitty_reasons", "kitty_ai_generated"):
            self.assertEqual(flagged[field], original[field])

    def test_removing_user_flag_preserves_automatic_flag(self):
        item = {"url": "https://example.com/a", "kitty_score": 20,
                "kitty_ai_generated": True, "kitty_reasons": ["Explicit evidence"]}
        core.set_feedback(item["url"], "page")
        core.apply_feedback([item], core.load_feedback())
        self.assertEqual(item["kitty_score"], 20)
        core.remove_feedback("page", item["url"])
        core.apply_feedback([item], core.load_feedback())
        self.assertTrue(item["kitty_ai_generated"])
        self.assertEqual(item["kitty_reasons"], ["Explicit evidence"])

    def test_invalid_input_does_not_create_database(self):
        for url in ("", "example.com", "file:///tmp/a", "https://user:pass@example.com", "https://example.com:bad",
                    "https://bad host.com/a", "https://exa\nmple.com/a", "https://example.com\\other/a"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                core.set_feedback(url, "page")
        with self.assertRaises(ValueError):
            core.set_feedback("https://example.com", "domain")
        self.assertFalse((self.home / "learning.sqlite3").exists())

    def test_corruption_is_reported_without_overwriting_flags(self):
        path = self.home / "learning.sqlite3"
        path.write_bytes(b"not a database")
        data = self.search(["https://example.com/a"])
        self.assertIn("Could not load saved AI flags", data["feedback_error"])
        self.assertEqual(len(data["results"]), 1)
        with self.assertRaises(core.sqlite3.Error):
            core.set_feedback("https://example.com/a", "page")
        self.assertEqual(path.read_bytes(), b"not a database")


if __name__ == "__main__":
    unittest.main()
