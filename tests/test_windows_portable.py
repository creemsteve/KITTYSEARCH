import importlib.util
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

import kittysearch as core

spec = importlib.util.spec_from_file_location("package_windows", Path(__file__).resolve().parents[1] / "package-windows.py")
packaging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packaging)


class PortableWindowsTests(unittest.TestCase):
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
            for name in ("LICENSE", "README.md", "kittysearch.py", "build-windows.ps1", "requirements-build.txt"):
                (root / name).write_text("source", encoding="utf-8")
            (root / "kittysearch-data").mkdir()
            (root / "kittysearch-data/secret.json").write_text("personal", encoding="utf-8")
            with patch.object(packaging, "ROOT", root):
                output = packaging.package("cpu", "master")
            with zipfile.ZipFile(output) as archive:
                self.assertIn("KITTYSEARCH/KITTYSEARCH.exe", archive.namelist())
                self.assertIn("KITTYSEARCH/KITTYSEARCH-source.zip", archive.namelist())
                for row in archive.read("KITTYSEARCH/SHA256SUMS.txt").decode().splitlines():
                    checksum, name = row.split("  ", 1)
                    self.assertEqual(checksum, packaging.hashlib.sha256(archive.read("KITTYSEARCH/" + name)).hexdigest())
            with zipfile.ZipFile(root / "dist/KITTYSEARCH-source.zip") as archive:
                self.assertIn("KITTYSEARCH/kittysearch.py", archive.namelist())
                self.assertFalse(any("kittysearch-data" in name for name in archive.namelist()))


if __name__ == "__main__":
    unittest.main()
