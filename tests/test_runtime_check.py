import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import kittysearch_models as models

spec = importlib.util.spec_from_file_location("install_model_runtime", Path(__file__).resolve().parents[1] / "install-model-runtime.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class RuntimeCheckTests(unittest.TestCase):
    def test_gpu_build_rejects_cpu_runtime(self):
        with patch.object(models, "runtime_capabilities", return_value=dict(installed=False, gpu=False, detail="missing DLL")):
            report = models.check_runtime("vulkan")
        self.assertFalse(report["ok"])
        self.assertEqual(report["detail"], "missing DLL")

    def test_windows_checks_backend_dlls_and_capabilities(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "lib").mkdir()
            runtime = SimpleNamespace(__file__=str(root / "__init__.py"))
            for name in ("llama.dll", "ggml.dll", "ggml-base.dll", "ggml-cpu.dll"):
                (root / "lib" / name).touch()
            with patch.object(models.sys, "platform", "win32"), patch.object(models.importlib, "import_module", return_value=runtime), patch.object(models, "runtime_capabilities", return_value=dict(installed=True, gpu=True, detail="GPU")):
                report = models.check_runtime("vulkan")
                self.assertFalse(report["ok"])
                self.assertEqual(report["missing_libraries"], ["ggml-vulkan.dll"])
                (root / "lib/ggml-vulkan.dll").touch()
                self.assertTrue(models.check_runtime("vulkan")["ok"])
                self.assertFalse(models.check_runtime("cuda")["ok"])
                self.assertFalse(models.check_runtime("cpu")["ok"])
                for name in ("ggml-cuda.dll", "cublas64_13.dll", "cublasLt64_13.dll"):
                    (root / "lib" / name).touch()
                self.assertFalse(models.check_runtime("cuda")["ok"])
                (root / "lib/NVIDIA-cuBLAS-LICENSE.txt").touch()
                self.assertTrue(models.check_runtime("cuda")["ok"])
            with patch.object(models.importlib, "import_module", return_value=runtime), patch.object(models, "runtime_capabilities", return_value=dict(installed=True, gpu=False, detail="CPU")):
                self.assertFalse(models.check_runtime("vulkan")["ok"])
                self.assertTrue(models.check_runtime("cpu")["ok"])

    def test_cuda_runtime_stages_both_cublas_dlls_and_license(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "source").mkdir()
            (root / "lib").mkdir()
            files = [Path(name) for name in ("cublas64_13.dll", "cublasLt64_13.dll", "License.txt")]
            for entry in files:
                (root / "source" / entry).write_bytes(b"redistributable")
            distribution = SimpleNamespace(files=files, locate_file=lambda entry: root / "source" / entry)
            with patch.object(installer.importlib.metadata, "distribution", return_value=distribution), patch.object(installer, "runtime_library_root", return_value=root / "lib"):
                installer.stage_cuda_libraries("nvidia-cublas>=13.0,<13.1")
                self.assertEqual(sorted(p.name for p in (root / "lib").iterdir()),
                                 ["NVIDIA-cuBLAS-LICENSE.txt", "cublas64_13.dll", "cublasLt64_13.dll"])
                distribution.files = files[:1]
                with self.assertRaisesRegex(RuntimeError, "both runtime DLLs and its license"):
                    installer.stage_cuda_libraries("nvidia-cublas>=13.0,<13.1")

    def test_cublas_package_matches_cuda_major_and_minor(self):
        self.assertEqual(installer.cuda_cublas_requirement("cu118"), "nvidia-cublas-cu11>=11.11,<12")
        self.assertEqual(installer.cuda_cublas_requirement("cu124"), "nvidia-cublas-cu12>=12.4,<12.5")
        self.assertEqual(installer.cuda_cublas_requirement("cu130"), "nvidia-cublas>=13.0,<13.1")


if __name__ == "__main__":
    unittest.main()
