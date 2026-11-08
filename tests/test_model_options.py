import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import kittysearch as core
import kittysearch_models as models


class ModelSettingsTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(directory.cleanup)
        self.home = Path(directory.name)
        home = patch.object(core, "data_dir", return_value=self.home)
        home.start()
        self.addCleanup(home.stop)

    def test_saved_choices_survive_restart_independent_of_cli_and_service(self):
        (self.home / "config.json").write_text('{"model_path":"cli.gguf"}')
        values = dict(core.automatic_config(), model_id="qwen2.5-1.5b", model_acceleration="gpu", model_gpu_layers=12, model_main_gpu=1)
        models.save_settings(self.home, values)
        cfg = core.automatic_config()
        self.assertEqual(cfg["model_gpu_layers"], 12)
        self.assertEqual(cfg["model_main_gpu"], 1)
        self.assertEqual(cfg["model_acceleration"], "gpu")
        self.assertEqual(Path(cfg["model_path"]), models.catalog_model_path(self.home, "qwen2.5-1.5b"))
        self.assertEqual(core.load_config()["model_path"], "cli.gguf")
        self.assertFalse((self.home / "desktop-searxng.json").exists())

    def test_custom_file_remains_selected_when_temporarily_unavailable(self):
        path = self.home / "custom.gguf"
        path.write_bytes(b"GGUF")
        values = dict(core.automatic_config(), model_id="custom", model_path=str(path))
        models.save_settings(self.home, values)
        path.unlink()
        self.assertEqual(core.automatic_config()["model_path"], str(path))
        with self.assertRaisesRegex(ValueError, "existing local GGUF"):
            models.save_settings(self.home, values)

    def test_kitty_mode_defaults_off_and_saved_choice_survives_restart(self):
        cfg = core.automatic_config()
        self.assertFalse(cfg["kitty_mode"])
        models.save_settings(self.home, dict(cfg, kitty_mode=True))
        self.assertTrue(core.automatic_config()["kitty_mode"])
        models.save_settings(self.home, dict(cfg, kitty_mode=False))
        self.assertFalse(core.automatic_config()["kitty_mode"])
        saved = json.loads((self.home / "desktop-model.json").read_text())
        del saved["kitty_mode"]
        (self.home / "desktop-model.json").write_text(json.dumps(saved))
        self.assertFalse(core.automatic_config()["kitty_mode"])

    def test_invalid_values_do_not_replace_saved_settings(self):
        cfg = core.automatic_config()
        models.save_settings(self.home, cfg)
        before = (self.home / "desktop-model.json").read_bytes()
        for changes in ({"model_context": 0}, {"model_threads": True}, {"model_threads": "1.5"},
                        {"model_gpu_layers": -2}, {"model_main_gpu": -1}, {"model_id": "../escape"},
                        {"kitty_mode": "false"}, {"kitty_mode": 1},
                        {"model_acceleration": "gpu", "model_gpu_layers": 0}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                models.save_settings(self.home, dict(cfg, **changes))
        self.assertEqual((self.home / "desktop-model.json").read_bytes(), before)

    def test_malformed_settings_recover_to_defaults(self):
        path = self.home / "desktop-model.json"
        for value in ("oops", "null", "[]", '{"model_context": "bad"}'):
            path.write_text(value)
            self.assertEqual(core.automatic_config()["model_id"], models.DEFAULT_MODEL_ID)

    def test_catalog_paths_relocate_with_portable_data(self):
        models.save_settings(self.home, dict(core.DEFAULTS, model_id="qwen2.5-1.5b"))
        other = self.home / "moved"
        other.mkdir()
        (other / "desktop-model.json").write_bytes((self.home / "desktop-model.json").read_bytes())
        loaded = models.load_settings(other, core.DEFAULTS)
        self.assertEqual(Path(loaded["model_path"]).parent, other / "models")

    def test_alternative_download_verifies_selected_model(self):
        content = b"GGUF alternative"
        model_id = "qwen2.5-1.5b"
        spec = dict(models.MODEL_CATALOG[model_id], sha256=hashlib.sha256(content).hexdigest())
        response = io.BytesIO(content)
        response.headers = {"Content-Length": str(len(content))}
        with patch.dict(models.MODEL_CATALOG, {model_id: spec}), patch.object(core.urllib.request, "urlopen", return_value=response) as request:
            target = core.download_model(model_id=model_id)
        self.assertEqual(target.read_bytes(), content)
        self.assertEqual(target.name, spec["filename"])
        self.assertEqual(request.call_args.args[0].full_url, spec["url"])
        self.assertFalse((target.parent / core.MODEL_FILENAME).exists())

    def test_interrupted_download_preserves_installed_model_and_cleans_partial(self):
        model_id = "llama3.2-3b"
        target = models.catalog_model_path(self.home, model_id)
        target.parent.mkdir()
        target.write_bytes(b"installed")
        response = io.BytesIO(b"partial")
        response.headers = {}
        def interrupted(*_args):
            raise OSError("connection lost")
        with patch.object(core.urllib.request, "urlopen", return_value=response), self.assertRaises(OSError):
            core.download_model(interrupted, model_id=model_id)
        self.assertEqual(target.read_bytes(), b"installed")
        self.assertFalse(target.with_suffix(".gguf.part").exists())


class RuntimeOptionsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "model.gguf"
        self.path.write_bytes(b"GGUF")
        self.cfg = dict(core.DEFAULTS, model_path=str(self.path))
        self.runtime = SimpleNamespace(Llama=Mock(side_effect=lambda **_kw: Mock()), LLAMA_SPLIT_MODE_NONE=0,
                                       llama_backend_init=Mock(), llama_supports_gpu_offload=Mock(return_value=True))
        self.patches = [patch.object(core.importlib, "import_module", return_value=self.runtime),
                        patch.object(core, "_MODEL_INSTANCE", None), patch.object(core, "_MODEL_KEY", None),
                        patch.object(core, "_MODEL_STATUS", "")]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_cpu_skips_gpu_and_reuses_model(self):
        cfg = dict(self.cfg, model_acceleration="cpu")
        model = core.get_local_model(cfg)
        self.assertIs(core.get_local_model(cfg), model)
        self.assertEqual(self.runtime.Llama.call_args.kwargs["n_gpu_layers"], 0)
        self.runtime.llama_supports_gpu_offload.assert_not_called()

    def test_explicit_gpu_uses_requested_layers_device_and_context(self):
        core.get_local_model(dict(self.cfg, model_acceleration="gpu", model_gpu_layers=15,
                                  model_main_gpu=1, model_context=4096, model_threads=3))
        args = self.runtime.Llama.call_args.kwargs
        self.assertEqual((args["n_gpu_layers"], args["main_gpu"], args["n_ctx"], args["n_threads"]), (15, 1, 4096, 3))
        self.assertEqual(args["split_mode"], 0)

    def test_auto_cpu_when_offload_unavailable_and_gpu_mode_reports_error(self):
        self.runtime.llama_supports_gpu_offload.return_value = False
        core.get_local_model(self.cfg)
        self.assertEqual(self.runtime.Llama.call_args.kwargs["n_gpu_layers"], 0)
        self.assertIn("unavailable", core._MODEL_STATUS)
        with self.assertRaisesRegex(RuntimeError, "GPU offload is unavailable"):
            core.get_local_model(dict(self.cfg, model_acceleration="gpu"))

    def test_portable_gpu_error_explains_that_host_pip_cannot_update_exe(self):
        self.runtime.llama_supports_gpu_offload.return_value = False
        with patch.object(core.sys, "frozen", True, create=True):
            with self.assertRaisesRegex(RuntimeError, "Vulkan or CUDA portable build.*Installing Python packages does not change"):
                core.get_local_model(dict(self.cfg, model_acceleration="gpu"))

    def test_auto_gpu_failure_retries_cpu_once_and_reports_fallback(self):
        self.runtime.Llama.side_effect = [RuntimeError("out of VRAM"), Mock()]
        core.get_local_model(self.cfg)
        self.assertEqual([c.kwargs["n_gpu_layers"] for c in self.runtime.Llama.call_args_list], [-1, 0])
        self.assertIn("CPU fallback", core._MODEL_STATUS)

    def test_explicit_gpu_failure_does_not_silently_use_cpu(self):
        self.runtime.Llama.side_effect = RuntimeError("out of VRAM")
        with self.assertRaisesRegex(RuntimeError, "fewer GPU layers"):
            core.get_local_model(dict(self.cfg, model_acceleration="gpu"))
        self.assertEqual(self.runtime.Llama.call_count, 1)

    def test_switch_releases_old_model_before_new_allocation(self):
        old = core.get_local_model(self.cfg)
        def load(**_options):
            old.close.assert_called_once()
            return Mock()
        self.runtime.Llama.side_effect = load
        core.get_local_model(dict(self.cfg, model_context=4096))

    def test_failed_switch_does_not_reuse_closed_model(self):
        old = core.get_local_model(self.cfg)
        self.runtime.Llama.side_effect = RuntimeError("load failed")
        with self.assertRaises(RuntimeError):
            core.get_local_model(dict(self.cfg, model_context=4096, model_acceleration="cpu"))
        old.close.assert_called_once()
        self.assertIsNone(core._MODEL_INSTANCE)
        self.assertIsNone(core._MODEL_KEY)


class HardwareGuidanceTests(unittest.TestCase):
    def setUp(self):
        self.hw = dict(cpu="Example CPU", threads=8, ram_gib=16, available_gib=10,
                       disk_gib=50, gpus=[])
        self.runtime = dict(installed=True, gpu=False)

    def guide(self, **changes):
        return models.model_guidance("granite-4.2-3b", self.hw, self.runtime, dict(core.DEFAULTS, **changes))

    def test_low_available_memory_warns_even_on_large_ram_machine(self):
        self.hw.update(ram_gib=64, available_gib=2)
        self.assertIn("Tight available RAM", self.guide())

    def test_gpu_guidance_requires_runtime_support_and_enabled_offload(self):
        self.hw["gpus"] = [dict(name="GPU", vram_gib=12, free_gib=10)]
        self.assertNotIn("fit on a GPU", self.guide())
        self.runtime["gpu"] = True
        self.assertIn("fit on a GPU", self.guide())
        self.assertNotIn("fit on a GPU", self.guide(model_acceleration="cpu"))
        self.assertNotIn("fit on a GPU", self.guide(model_gpu_layers=0))

    def test_larger_context_can_change_fit_estimate(self):
        self.assertIn("Likely to fit in RAM", self.guide())
        self.assertIn("Tight available RAM", self.guide(model_context=65536))

    def test_unknown_specs_do_not_claim_gpu_fit(self):
        self.hw.update(ram_gib=None, available_gib=None, gpus=[dict(name="Shared GPU", vram_gib=None)])
        self.runtime["gpu"] = True
        text = self.guide()
        self.assertIn("RAM availability unknown", text)
        self.assertIn("insufficient or unknown", text)
        self.assertNotIn("fit on a GPU", text)

    def test_low_disk_and_missing_runtime_are_explained(self):
        self.hw["disk_gib"] = 0.1
        self.runtime["installed"] = False
        text = self.guide()
        self.assertIn("Install the inference runtime", text)
        self.assertIn("Not enough free disk", text)

    def test_unknown_custom_model_quality_is_not_invented(self):
        text = models.model_guidance("custom", self.hw, self.runtime, core.DEFAULTS, custom_bytes=5 * 1024 ** 3)
        self.assertIn("quality are unknown", text)
        self.assertIn("rough memory estimate", text)


if __name__ == "__main__":
    unittest.main()
