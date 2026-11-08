import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

import kittysearch as core
import kittysearch_models as models

spec = importlib.util.spec_from_file_location("package_windows", Path(__file__).resolve().parents[1] / "package-windows.py")
packaging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packaging)


class PortableWindowsTests(unittest.TestCase):
    def test_runtime_check_runs_without_loading_settings_and_records_frozen_exe(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            executable = root / "KITTYSEARCH.exe"
            executable.write_bytes(b"frozen app")
            output = root / "runtime-check.json"
            report = dict(installed=True, gpu=True, backend="vulkan", ok=True)
            arguments = [str(executable), "runtime-check", "--backend", "vulkan", "--output", str(output)]
            with patch.object(core.sys, "argv", arguments), patch.object(core.sys, "frozen", True, create=True), patch.object(core.sys, "executable", str(executable)), patch.object(models, "check_runtime", return_value=report), patch.object(core, "load_config") as config:
                self.assertEqual(core.main(), 0)
            result = json.loads(output.read_text())
            self.assertTrue(result["frozen"])
            self.assertEqual(result["executable_sha256"], packaging.sha256(executable))
            config.assert_not_called()

    def test_runtime_check_failure_returns_nonzero_and_writes_diagnostics(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "runtime-check.json"
            report = dict(installed=False, gpu=False, backend="vulkan", ok=False, detail="missing DLL")
            with patch.object(core.sys, "argv", ["KITTYSEARCH", "runtime-check", "--backend", "vulkan", "--output", str(output)]), patch.object(models, "check_runtime", return_value=report):
                self.assertEqual(core.main(), 1)
            self.assertEqual(json.loads(output.read_text())["detail"], "missing DLL")

    def test_gpu_model_smoke_test_uses_explicit_offload_and_requires_tokens(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "smoke-test.json"
            arguments = ["KITTYSEARCH", "runtime-check", "--backend", "cuda", "--model", "model.gguf", "--output", str(output)]
            for tokens in (3, 0):
                with self.subTest(tokens=tokens), patch.object(core.sys, "argv", arguments), patch.object(models, "check_runtime", return_value=dict(ok=True)), patch.object(core, "get_local_model") as load:
                    load.return_value.create_completion.return_value = {"usage": {"completion_tokens": tokens}}
                    self.assertEqual(core.main(), 0 if tokens else 1)
                    self.assertEqual(load.call_args.args[0]["model_acceleration"], "gpu")
                    models.inference_settings(load.call_args.args[0])
                    self.assertEqual(json.loads(output.read_text())["model_test"]["ok"], bool(tokens))

    def test_service_exit_is_reported_without_waiting_for_startup_timeout(self):
        process = SimpleNamespace(poll=lambda: 1, returncode=1)
        with patch.object(core, "MANAGED_PROCESS", process), patch.object(core, "stop_managed_searxng") as stop, patch.object(core, "http_json") as request:
            with self.assertRaisesRegex(RuntimeError, "exited during startup.*code 1.*service logs"):
                core.wait_for_managed_searxng(core.DEFAULTS, startup_message="Check service logs.")
        stop.assert_called_once()
        request.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows subprocess flags")
    def test_embedded_service_has_no_console_and_uses_portable_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "source/searx").mkdir(parents=True)
            (root / "source/searx/webapp.py").touch()
            (root / "python").mkdir()
            (root / "python/python.exe").touch()
            with patch.object(core, "bundled_searxng_root", return_value=root), patch.object(core, "data_dir", return_value=root / "data"), patch.object(core, "WINDOWS_MANAGED_SETTINGS", root / "data/settings.yml"), patch.object(core.subprocess, "Popen") as launch, patch.object(core, "wait_for_managed_searxng"), patch.multiple(core, MANAGED_PROCESS=None, MANAGED_SEARXNG=False, MANAGED_SEARXNG_MODE=""):
                core.start_windows_searxng(core.DEFAULTS)
                options = launch.call_args.kwargs
                self.assertEqual(options["creationflags"], core.subprocess.CREATE_NO_WINDOW)
                self.assertEqual(Path(options["env"]["TEMP"]), root / "data/searxng-cache")
                self.assertEqual(options["env"]["TMP"], options["env"]["TEMP"])

    def test_release_contains_source_and_checksums_but_no_personal_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "dist").mkdir()
            for name in ("KITTYSEARCH.exe", "SearXNG-source.zip"):
                (root / "dist" / name).write_bytes(b"build artifact")
            for name in ("LICENSE", "README.md", "AGENTS.md", "kittysearch.py", "build-windows.ps1", "requirements-build.txt"):
                (root / name).write_text("source", encoding="utf-8")
            (root / "kittysearch-data").mkdir()
            (root / "kittysearch-data/secret.json").write_text("personal", encoding="utf-8")
            report = dict(ok=True, installed=True, frozen=True, gpu=False, backend="cpu",
                          executable_sha256=packaging.sha256(root / "dist/KITTYSEARCH.exe"))
            (root / "dist/runtime-check.json").write_text(json.dumps(report), encoding="utf-8")
            with patch.object(packaging, "ROOT", root):
                output = packaging.package("cpu", "master")
            with zipfile.ZipFile(output) as archive:
                self.assertIn("KITTYSEARCH/KITTYSEARCH.exe", archive.namelist())
                self.assertIn("KITTYSEARCH/KITTYSEARCH-source.zip", archive.namelist())
                self.assertIn("CPU local inference runtime", archive.read("KITTYSEARCH/START-HERE.txt").decode())
                for row in archive.read("KITTYSEARCH/SHA256SUMS.txt").decode().splitlines():
                    checksum, name = row.split("  ", 1)
                    self.assertEqual(checksum, packaging.hashlib.sha256(archive.read("KITTYSEARCH/" + name)).hexdigest())
            with zipfile.ZipFile(root / "dist/KITTYSEARCH-source.zip") as archive:
                self.assertIn("KITTYSEARCH/kittysearch.py", archive.namelist())
                self.assertIn("KITTYSEARCH/AGENTS.md", archive.namelist())
                self.assertFalse(any("kittysearch-data" in name for name in archive.namelist()))
            with patch.object(packaging, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "must pass runtime-check"):
                    packaging.package("vulkan", "master")
                report.update(backend="vulkan", gpu=True)
                (root / "dist/runtime-check.json").write_text(json.dumps(report), encoding="utf-8")
                output = packaging.package("vulkan", "master")
                with zipfile.ZipFile(output) as archive:
                    instructions = archive.read("KITTYSEARCH/START-HERE.txt").decode()
                    self.assertIn("VULKAN local inference runtime", instructions)
                    self.assertNotIn("The CPU local inference runtime", instructions)
                    self.assertEqual(json.loads(archive.read("KITTYSEARCH/build-info.json"))["runtime_check"], report)
                (root / "dist/KITTYSEARCH.exe").write_bytes(b"changed after validation")
                with self.assertRaisesRegex(ValueError, "must pass runtime-check"):
                    packaging.package("vulkan", "master")


if __name__ == "__main__":
    unittest.main()
