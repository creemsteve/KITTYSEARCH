from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

import kittysearch as core
import kittysearch_models as models
from kittysearch_desktop import KittySearchWindow


class DesktopModelTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(directory.cleanup)
        self.home = Path(directory.name)
        home_patch = patch.object(core, "data_dir", return_value=self.home)
        home_patch.start()
        self.addCleanup(home_patch.stop)
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        self.root.withdraw()
        self.addCleanup(self.close)
        self.patches = [patch.object(KittySearchWindow, method) for method in
                        ("_start_managed_service", "_refresh_health", "_refresh_model_hardware")]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.app = KittySearchWindow(self.root)

    def close(self):
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.root.destroy()

    def choose(self, model_id):
        self.app.model_choice.set(next(label for label, key in self.app.model_choices.items() if key == model_id))
        self.app._update_model_status()

    def test_select_installed_alternative_and_persist_acceleration(self):
        path = models.catalog_model_path(self.home, "qwen2.5-1.5b")
        path.parent.mkdir()
        path.write_bytes(b"GGUF")
        self.choose("qwen2.5-1.5b")
        self.app.acceleration.set("CPU only")
        self.app._acceleration_changed()
        self.app.save_model_button.invoke()
        self.assertEqual(self.app.cfg["model_path"], str(path))
        self.assertEqual(core.automatic_config()["model_acceleration"], "cpu")
        self.assertTrue(self.app.download_button.instate(["disabled"]))
        self.assertIn(path.name, self.app.active_model_label.cget("text"))

    def test_custom_file_uses_browse_path_and_disables_catalog_download(self):
        path = self.home / "chosen.gguf"
        path.write_bytes(b"GGUF")
        self.choose("custom")
        with patch("kittysearch_model_settings.filedialog.askopenfilename", return_value=str(path)):
            self.app.browse_model_button.invoke()
        self.app.save_model_button.invoke()
        self.assertEqual(self.app.cfg["model_path"], str(path))
        self.assertEqual(self.app.cfg["model_id"], "custom")
        self.assertTrue(self.app.download_button.instate(["disabled"]))

    def test_kitty_mode_toggle_applies_only_after_saving(self):
        self.assertEqual(self.app.kitty_mode_toggle.cget("text"), "kitty mode :3")
        self.assertFalse(self.app.kitty_mode.get())
        self.app.kitty_mode_toggle.invoke()
        self.assertFalse(self.app.cfg["kitty_mode"])
        self.app.save_model_button.invoke()
        self.assertTrue(self.app.cfg["kitty_mode"])
        self.assertTrue(core.automatic_config()["kitty_mode"])
        self.app.kitty_mode_toggle.invoke()
        self.app.save_model_button.invoke()
        self.assertFalse(self.app.cfg["kitty_mode"])
        self.assertFalse(core.automatic_config()["kitty_mode"])

    def test_invalid_form_preserves_active_model_and_saved_file(self):
        self.app._save_model_settings()
        before = (self.home / "desktop-model.json").read_bytes()
        active = self.app.cfg.copy()
        self.choose("llama3.2-3b")
        self.app.model_fields["model_context"].set("bad")
        self.app.save_model_button.invoke()
        self.assertEqual(self.app.cfg, active)
        self.assertEqual((self.home / "desktop-model.json").read_bytes(), before)
        self.assertIn("not saved", self.app.model_settings_status.cget("text"))

    def test_depth_selection_applies_after_save_and_survives_restart(self):
        self.app.search_depth.set("Deep (24,000 characters)")
        self.assertEqual(self.app.cfg["search_depth"], "snippets")
        self.app.save_model_button.invoke()
        self.assertEqual(self.app.cfg["search_depth"], "deep")
        self.assertEqual(core.automatic_config()["search_depth"], "deep")
        self.app._set_download_busy(True)
        self.assertTrue(self.app.depth_picker.instate(["disabled"]))
        self.app._set_download_busy(False)
        self.assertTrue(self.app.depth_picker.instate(["readonly"]))

    def test_result_details_report_page_coverage_truncation_and_failure(self):
        item = dict(url="https://example.org", title="Source", content="Preview", kitty_score=70,
                    kitty_relevance=80, kitty_ai_reviewed=True, kitty_ai_generated=False, kitty_reasons=["Usable content"],
                    kitty_page_text="Page text", kitty_page_reviewed_chars=5, kitty_page_truncated=True,
                    kitty_page_url="https://example.org/final")
        data = dict(results=[item], analyzed=True, model="fake.gguf", model_error=None,
                    search_depth="deep", pages_retrieved=1, page_errors=0)
        self.app._search_done(data, None)
        self.app.result_tree.selection_set("0")
        self.app._show_result()
        detail = self.app.result_detail.get("1.0", "end")
        self.assertIn("5 of 9 retrieved characters reviewed", detail)
        self.assertIn("partial view", detail)
        self.assertIn("https://example.org/final", detail)
        self.assertIn("1 pages retrieved", self.app.search_status.cget("text"))
        item.update(kitty_page_text="", kitty_page_error="Timed out")
        self.app._show_result()
        self.assertIn("snippet review only: Timed out", self.app.result_detail.get("1.0", "end"))

    def test_busy_download_locks_choice_and_failure_restores_controls(self):
        self.app._set_download_busy(True)
        self.assertTrue(self.app.model_picker.instate(["disabled"]))
        self.assertTrue(self.app.save_model_button.instate(["disabled"]))
        self.assertTrue(self.app.kitty_mode_toggle.instate(["disabled"]))
        self.assertTrue(self.app.model_field_entries["model_context"].instate(["disabled"]))
        self.app._model_download_failed("network interrupted")
        self.assertFalse(self.app.model_picker.instate(["disabled"]))
        self.assertFalse(self.app.save_model_button.instate(["disabled"]))
        self.assertFalse(self.app.kitty_mode_toggle.instate(["disabled"]))
        self.assertIn("network interrupted", self.app.download_status.cget("text"))

    def test_hardware_guidance_changes_for_smaller_model(self):
        hw = dict(cpu="Example CPU", threads=4, ram_gib=8, available_gib=4, gpus=[], disk_gib=50)
        self.app._model_hardware_ready(hw, dict(installed=True, gpu=False))
        self.assertIn("Tight available RAM", self.app.model_guidance_label.cget("text"))
        self.choose("qwen2.5-1.5b")
        self.assertIn("Likely to fit in RAM", self.app.model_guidance_label.cget("text"))
        self.assertIn("Smallest and likely fastest", self.app.model_guidance_label.cget("text"))

    def test_successful_download_activates_captured_settings(self):
        settings = dict(self.app.cfg, model_id="llama3.2-3b", model_acceleration="cpu")
        settings = models.validate_settings(self.home, settings)
        target = Path(settings["model_path"])
        target.parent.mkdir()
        target.write_bytes(b"GGUF")
        self.choose("llama3.2-3b")
        self.app._set_download_busy(True)
        self.app._model_downloaded(settings)
        self.assertEqual(self.app.cfg["model_id"], "llama3.2-3b")
        self.assertEqual(core.automatic_config()["model_acceleration"], "cpu")
        self.assertIn("Download verified", self.app.model_settings_status.cget("text"))


if __name__ == "__main__":
    unittest.main()
