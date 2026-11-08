import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import kittysearch as core
from kittysearch_desktop import KittySearchWindow


class DesktopSearxngTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        self.root.withdraw()
        self.addCleanup(self.destroy_root)
        self.directory = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.directory.cleanup)
        data_dir = patch.object(core, "data_dir", return_value=Path(self.directory.name))
        data_dir.start()
        self.addCleanup(data_dir.stop)
        with patch.object(KittySearchWindow, "_start_managed_service"):
            self.app = KittySearchWindow(self.root)
        # Execute workers inline so their outcomes can be inspected deterministically.
        worker = patch("kittysearch_desktop.threading.Thread",
                       side_effect=lambda **kwargs: SimpleNamespace(start=kwargs["target"]))
        worker.start()
        self.addCleanup(worker.stop)

    def destroy_root(self):
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.root.destroy()

    def set_external_form(self):
        self.app.searxng_mode.set("Existing instance")
        self.app.searxng_url.set("https://example.org/searx/")
        self.app.searxng_timeout.set("30")

    def test_invalid_save_preserves_active_configuration_and_file(self):
        before = self.app.cfg.copy()
        self.app.searxng_timeout.set("0")
        with patch.object(core, "stop_managed_searxng") as stop:
            self.app._save_searxng_settings()
        stop.assert_not_called()
        self.assertEqual(self.app.cfg, before)
        self.assertFalse((core.data_dir() / "desktop-searxng.json").exists())
        self.assertIn("not saved", self.app.searxng_status.cget("text"))

    def test_switch_to_external_stops_owned_service_and_persists(self):
        self.set_external_form()
        with patch.object(core, "stop_managed_searxng") as stop, patch.object(core, "http_json", return_value={}):
            self.app._save_searxng_settings()
            self.root.update()
        stop.assert_called_once()
        self.assertEqual(self.app.cfg["searxng_url"], "https://example.org/searx")
        self.assertEqual(core.automatic_config()["timeout"], 30)
        self.assertFalse(self.app._service_busy)

    def test_timeout_only_change_does_not_stop_service(self):
        self.app.searxng_timeout.set("31")
        with patch.object(core, "stop_managed_searxng") as stop, patch.object(core, "http_json", return_value={}):
            self.app._save_searxng_settings()
            self.root.update()
        stop.assert_not_called()
        self.assertEqual(self.app.cfg["timeout"], 31)

    def test_connection_test_uses_unsaved_form_without_applying_it(self):
        before = self.app.cfg.copy()
        self.set_external_form()
        with patch.object(core, "http_json", return_value={}) as request, patch.object(core, "stop_managed_searxng") as stop:
            self.app._test_searxng_connection()
            self.root.update()
        request.assert_called_once_with("https://example.org/searx/config", timeout=30)
        stop.assert_not_called()
        self.assertEqual(self.app.cfg, before)
        self.assertFalse((core.data_dir() / "desktop-searxng.json").exists())
        self.assertIn("Connected", self.app.searxng_status.cget("text"))

    def test_startup_failure_leaves_settings_editable(self):
        self.app.cfg.update(searxng_mode="docker", searxng_url="http://localhost:9090")
        calls = []
        with patch.object(core, "stop_managed_searxng", side_effect=lambda: calls.append("stop")), patch.object(core, "http_json", side_effect=OSError("offline")), patch.object(core, "start_managed_searxng", side_effect=RuntimeError("Docker unavailable")) as start:
            self.app._start_managed_service(restart=True)
            self.root.update()
        self.assertEqual(calls, ["stop"])
        start.assert_called_once_with(self.app.cfg)
        self.assertIn("Docker unavailable", self.app.searxng_status.cget("text"))
        self.assertFalse(self.app._service_busy)
        self.assertFalse(self.app.save_searxng_button.instate(["disabled"]))


    def test_search_preferences_are_saved_without_restarting_service(self):
        self.app.searxng_engines.set("chosen engine")
        self.app.searxng_categories.set("news")
        self.app.searxng_language.set("en-US")
        self.app.searxng_safesearch.set("Strict")
        self.app.searxng_allowed_domains.set("EXAMPLE.ORG")
        self.app.searxng_blocked_domains.set("ads.example.org")
        self.app.results = [{"url": "https://ads.example.org", "title": "Blocked"}, {"url": "https://example.org", "title": "Kept"}]
        with patch.object(self.app, "_start_managed_service") as start:
            self.app._save_searxng_settings()
        start.assert_called_once_with(restart=False)
        cfg = core.automatic_config()
        self.assertEqual(cfg["engines"], ["chosen engine"])
        self.assertEqual(cfg["categories"], ["news"])
        self.assertEqual(cfg["language"], "en-US")
        self.assertEqual(cfg["safesearch"], 2)
        self.assertEqual(cfg["allowed_domains"], ["example.org"])
        self.assertEqual([item["title"] for item in self.app.results], ["Kept"])

    def test_engine_picker_loads_current_server_and_applies_selection(self):
        self.set_external_form()
        config = {"categories": ["general", "news"], "engines": [
            {"name": "one", "categories": ["general"], "enabled": True},
            {"name": "two", "categories": ["news"], "enabled": False}]}
        with patch.object(core, "http_json", return_value=config) as request:
            self.app._load_searxng_engines()
            self.root.update()
        request.assert_called_once_with("https://example.org/searx/config", timeout=30)
        rows = self.app.searxng_engine_tree.get_children()
        self.assertEqual(len(rows), 2)
        self.app.searxng_engine_tree.selection_set(rows)
        self.app._use_selected_searxng_engines()
        self.assertEqual(self.app.searxng_engines.get(), "one, two")
        self.assertIn("news", self.app.searxng_category_hint.cget("text"))
        self.assertFalse((core.data_dir() / "desktop-searxng.json").exists())
        self.app.searxng_url.set("https://different.example")
        self.app._use_selected_searxng_engines()
        self.assertIn("Load engines", self.app.searxng_status.cget("text"))

    def test_failed_engine_load_leaves_form_editable(self):
        with patch.object(core, "http_json", side_effect=OSError("offline")):
            self.app._load_searxng_engines()
            self.root.update()
        self.assertIn("Could not load engines", self.app.searxng_status.cget("text"))
        self.assertFalse(self.app.load_engines_button.instate(["disabled"]))

    def test_result_from_inflight_search_respects_latest_domain_rules(self):
        self.app.cfg["blocked_domains"] = ["blocked.org"]
        data = {"results": [{"url": "https://blocked.org", "title": "Blocked"}, {"url": "https://good.org", "title": "Kept"}],
                "analyzed": False, "model": None, "model_error": None}
        for item in data["results"]:
            item.update(kitty_score=50, kitty_ai_generated=False, kitty_reasons=[])
        self.app._search_done(data, None)
        self.assertEqual([item["title"] for item in self.app.results], ["Kept"])


if __name__ == "__main__":
    unittest.main()
