import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import kittysearch as core


class Response(io.BytesIO):
    headers = {"Content-Length": "10"}


class DownloadTests(unittest.TestCase):
    def test_download_is_verified_and_installed(self):
        content = b"GGUF model"
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory, patch.object(core, "data_dir", return_value=Path(directory)), patch.object(core, "MODEL_SHA256", hashlib.sha256(content).hexdigest()), patch.object(core.urllib.request, "urlopen", return_value=Response(content)):
            progress = []
            target = core.download_model(lambda received, total: progress.append((received, total)))
            self.assertEqual(target.read_bytes(), content)
            self.assertEqual(progress[-1], (len(content), len(content)))
            self.assertFalse(target.with_suffix(target.suffix + ".part").exists())
            self.assertEqual(core.automatic_config()["model_path"], str(target))

    def test_bad_download_does_not_replace_existing_model(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory, patch.object(core, "data_dir", return_value=Path(directory)), patch.object(core.urllib.request, "urlopen", return_value=Response(b"bad")):
            target = Path(directory) / "models" / core.MODEL_FILENAME
            target.parent.mkdir()
            target.write_bytes(b"existing")
            with self.assertRaisesRegex(ValueError, "verification"):
                core.download_model()
            self.assertEqual(target.read_bytes(), b"existing")
            self.assertFalse(target.with_suffix(target.suffix + ".part").exists())


if __name__ == "__main__":
    unittest.main()

