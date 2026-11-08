import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import kittysearch as core
from kittysearch_desktop import KittySearchWindow


class DesktopLearningTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        home = patch.object(core, "data_dir", return_value=Path(self.directory.name))
        home.start()
        self.addCleanup(home.stop)
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        with patch.object(KittySearchWindow, "_start_managed_service"), patch.object(KittySearchWindow, "_refresh_health"):
            self.window = KittySearchWindow(self.root)
        self.items = [{"url": "https://example.com/a", "title": "Example", "content": "Source"},
                      {"url": "https://example.com/b", "title": "Another example", "content": "Source"}]
        with patch.object(core, "http_json", return_value={"results": self.items}):
            self.data = core.search("example", core.DEFAULTS)
        self.window._search_done(self.data, None)
        self.root.update_idletasks()

    def select_first_result(self):
        self.window.result_tree.selection_set(self.window.result_tree.get_children()[0])
        self.window._show_result()

    def test_flag_hide_and_remove_hidden_website(self):
        window = self.window
        self.select_first_result()
        window.website_flag_button.invoke()
        self.assertEqual(core.load_feedback()["website"], {"example.com"})
        self.assertTrue(all(item["kitty_ai_generated"] for item in window.results))
        self.assertIn("Flagged by you", window.result_tree.item("0", "values")[2])
        window.hide_ai.set(True)
        window._render_results()
        self.assertEqual(window.result_tree.get_children(), ())
        self.assertTrue(window.open_result_button.instate(["disabled"]))
        self.assertTrue(window.website_flag_button.instate(["disabled"]))
        self.assertEqual(window.result_detail.get("1.0", "end").strip(), "")
        window.feedback_tree.selection_set(window.feedback_tree.get_children()[0])
        window._remove_feedback()
        self.assertEqual(core.load_feedback()["website"], set())
        self.assertEqual(len(window.result_tree.get_children()), 2)
        self.assertTrue(all(not item["kitty_ai_generated"] for item in window.results))

    def test_direct_url_flag_and_unflag_selected_page(self):
        window = self.window
        window.feedback_url.set("https://example.com/a#fragment")
        window.feedback_scope.set("page")
        window._add_feedback()
        self.assertEqual(core.load_feedback()["page"], {"https://example.com/a"})
        item_id = next(iid for iid, item in window.visible_results.items() if item["url"].endswith("/a"))
        window.result_tree.selection_set(item_id)
        window._show_result()
        self.assertEqual(window.page_flag_button.cget("text"), "Unflag page")
        window.page_flag_button.invoke()
        self.assertEqual(core.load_feedback()["page"], set())
        self.assertEqual(window.feedback_tree.get_children(), ())

    def test_search_completion_uses_flags_added_during_search(self):
        core.set_feedback("https://example.com/a", "page")
        self.window._search_done(self.data, None)
        flagged = next(item for item in self.window.results if item["url"].endswith("/a"))
        self.assertEqual(flagged["kitty_user_flags"], ["page"])


if __name__ == "__main__":
    unittest.main()
