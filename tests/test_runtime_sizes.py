import importlib.util
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location(
    "optimize_windows_runtime", Path(__file__).resolve().parents[1] / "optimize-windows-runtime.py")
optimizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(optimizer)


class RuntimeSizeTests(unittest.TestCase):
    def test_bytecode_with_source_is_removed_but_sourceless_modules_are_kept(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "module.py"
            source.write_text("value = 42\n", encoding="utf-8")
            cached = Path(importlib.util.cache_from_source(str(source)))
            cached.parent.mkdir()
            cached.write_bytes(b"rebuildable bytecode")
            legacy = root / "module.pyc"
            legacy.write_bytes(cached.read_bytes())
            sourceless = root / "standalone.pyc"
            sourceless.write_bytes(cached.read_bytes())
            orphan = root / "__pycache__/orphan.cpython-311.pyc"
            orphan.write_bytes(cached.read_bytes())
            stdlib = root / "python311.zip"
            stdlib.write_bytes(b"embedded bytecode")
            expected = cached.stat().st_size + legacy.stat().st_size
            self.assertEqual(optimizer.prune_bytecode(root), (2, expected))
            self.assertFalse(cached.exists())
            self.assertFalse(legacy.exists())
            self.assertTrue(sourceless.exists())
            self.assertTrue(orphan.exists())
            self.assertEqual(stdlib.read_bytes(), b"embedded bytecode")
            namespace = {}
            exec(source.read_text(), namespace)
            self.assertEqual(namespace["value"], 42)
            self.assertEqual(optimizer.prune_bytecode(root), (0, 0))

    def test_linker_cleanup_keeps_backend_dlls_and_licenses(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            keep = ("llama.dll", "ggml-vulkan.dll", "ggml-cuda.dll", "cublas64_13.dll",
                    "cublasLt64_13.dll", "NVIDIA-cuBLAS-LICENSE.txt", "LICENSE", "module.py")
            remove = ("llama.lib", "llama.a", "llama.exp", "llama.PDB")
            for name in keep + remove:
                (root / name).write_bytes(b"content")
            self.assertEqual(optimizer.prune_linker_files(root), (len(remove), 7 * len(remove)))
            self.assertEqual({p.name for p in root.iterdir()}, set(keep))

    def test_cleanup_refuses_files_outside_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            runtime = root / "runtime"
            runtime.mkdir()
            outside = root / "outside.lib"
            outside.write_bytes(b"keep")
            with self.assertRaises(ValueError):
                optimizer.remove_files(runtime, [outside])
            self.assertEqual(outside.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
