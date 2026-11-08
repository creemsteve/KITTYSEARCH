from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

import kittysearch as core
from kittysearch_desktop import KittySearchWindow


class DesktopOverviewTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(directory.cleanup)
        patcher = patch.object(core, "data_dir", return_value=Path(directory.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        self.addCleanup(self.close)
        with patch.object(KittySearchWindow, "_start_managed_service"), patch.object(KittySearchWindow, "_refresh_health"), patch.object(KittySearchWindow, "_refresh_model_hardware"):
            self.window = KittySearchWindow(self.root)
        item = dict(url="https://example.org/page", title="Page", content="Snippet", kitty_score=80,
                    kitty_relevance=80, kitty_ai_reviewed=True, kitty_ai_generated=False,
                    kitty_reasons=["Relevant"], kitty_summary="Page knowledge.", kitty_source_id="1")
        self.data = dict(results=[item], analyzed=True, model="model.gguf", model_error=None,
                         overview={"text": "Combined findings [1].", "reviewed": 1, "total": 1,
                                   "sources": [{"id": "1", "title": "Page", "url": item["url"]}]},
                         overview_error=None)

    def close(self):
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.root.destroy()

    def overview_text(self):
        return self.window.overview_detail.get("1.0", "end")

    def test_overview_and_page_summary_are_both_visible(self):
        self.window._search_done(self.data, None)
        self.assertIn("Combined findings [1]", self.overview_text())
        self.assertIn("1 of 1 results", self.overview_text())
        self.assertIn("https://example.org/page", self.overview_text())
        self.assertTrue(self.window.overview_detail.tag_ranges("source_1"))
        self.assertEqual(self.window.result_views.select(), str(self.window.overview_tab))
        self.assertEqual(self.window.overview_detail.cget("state"), "disabled")
        self.window.result_tree.selection_set("0")
        self.window._show_result()
        self.assertEqual(self.window.result_views.select(), str(self.window.details_tab))
        detail = self.window.result_detail.get("1.0", "end")
        self.assertIn("Page overview [1]:\nPage knowledge.", detail)
        self.assertIn("Snippet", detail)
        self.assertIn("Relevant", detail)

    def test_new_search_response_clears_old_text_and_source_links(self):
        self.window._search_done(self.data, None)
        self.window._search_done(dict(self.data, overview=None, overview_error="General overview unavailable"), None)
        self.assertNotIn("Combined findings", self.overview_text())
        self.assertEqual(self.window.overview_detail.tag_ranges("source_1"), ())
        self.assertIn("General overview unavailable", self.overview_text())
        self.window._search_done(None, "Search failed")
        self.assertIn("search failed", self.overview_text())

    def test_inflight_domain_changes_hide_overview_and_excluded_sources(self):
        self.window.cfg["blocked_domains"] = ["example.org"]
        self.window._search_done(self.data, None)
        self.assertEqual(self.window.results, [])
        self.assertNotIn("Combined findings", self.overview_text())
        self.assertNotIn("https://example.org", self.overview_text())
        self.assertIn("Domain filters changed", self.overview_text())

    def test_saved_domain_filter_clears_existing_overview(self):
        self.window._search_done(self.data, None)
        self.window.searxng_blocked_domains.set("example.org")
        self.window._save_searxng_settings()
        self.assertIsNone(self.window.overview)
        self.assertIn("Domain filters changed", self.overview_text())


if __name__ == "__main__":
    unittest.main()
