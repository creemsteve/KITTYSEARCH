import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import kittysearch as core


class SearxngSettingsTests(unittest.TestCase):
    def settings(self, **changes):
        return dict(searxng_mode="external", searxng_url="https://example.org/searx/",
                    timeout="25", **changes)

    def test_normalizes_url_and_timeout(self):
        settings = core.validate_searxng_settings(self.settings())
        self.assertEqual(settings["searxng_url"], "https://example.org/searx")
        self.assertEqual(settings["timeout"], 25)

    def test_rejects_invalid_urls(self):
        for url in ("", "file:///search", "https://", "https://host:bad", "http://host:65536",
                    "http://host:0", "http://user:password@host", "http://host?q=x",
                    "http://host#fragment", "http://bad host", "http://[broken"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                core.validate_searxng_settings(dict(self.settings(), searxng_url=url))

    def test_timeout_bounds_and_types(self):
        for timeout in (0, 301, True, None, "1.5", "-1", [], "²"):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                core.validate_searxng_settings(dict(self.settings(), timeout=timeout))

    def test_managed_modes_require_local_http(self):
        for url in ("https://localhost:8080", "http://remote:8080", "http://localhost:8080/path"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                core.validate_searxng_settings(dict(self.settings(), searxng_mode="docker", searxng_url=url))
        cfg = core.validate_searxng_settings(dict(self.settings(), searxng_mode="docker",
                                                searxng_url="http://127.0.0.1:9090"))
        self.assertEqual(cfg["searxng_url"], "http://127.0.0.1:9090")

    def test_windows_modes_require_windows_and_default_port(self):
        for mode in ("windows", "wsl"):
            cfg = dict(self.settings(), searxng_mode=mode, searxng_url="http://localhost:8080")
            with patch.object(core.os, "name", "posix"), self.assertRaises(ValueError):
                core.validate_searxng_settings(cfg)
            with patch.object(core.os, "name", "nt"):
                self.assertEqual(core.validate_searxng_settings(cfg)["searxng_mode"], mode)
                with self.assertRaises(ValueError):
                    core.validate_searxng_settings(dict(cfg, searxng_url="http://localhost:9090"))

    def test_settings_survive_restart_without_changing_cli_or_model(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory, patch.object(core, "data_dir", return_value=Path(directory)):
            cli = Path(directory) / "config.json"
            cli.write_text('{"searxng_url": "http://cli:9000", "timeout": 99}', encoding="utf-8")
            original = cli.read_bytes()
            core.save_searxng_settings(dict(self.settings(), model_path="unwanted.gguf"))
            cfg = core.automatic_config()
            self.assertEqual(cfg["searxng_url"], "https://example.org/searx")
            self.assertEqual(cfg["timeout"], 25)
            self.assertEqual(cfg["model_path"], str(Path(directory) / "models" / core.MODEL_FILENAME))
            self.assertEqual(cli.read_bytes(), original)
            saved = json.loads((Path(directory) / "desktop-searxng.json").read_text(encoding="utf-8"))
            self.assertEqual(set(saved), {"searxng_url", "searxng_mode", "timeout", *core.searxng.SEARCH_DEFAULTS})
            with patch.dict(core.os.environ, {}, clear=True):
                self.assertEqual(core.load_config()["timeout"], 99)

    def test_invalid_file_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory, patch.object(core, "data_dir", return_value=Path(directory)):
            path = Path(directory) / "desktop-searxng.json"
            for content in ("broken", "null", "[]", '{"searxng_mode": "unknown"}'):
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    self.assertEqual(core.automatic_config()["searxng_url"], core.DEFAULTS["searxng_url"])


if __name__ == "__main__":
    unittest.main()
