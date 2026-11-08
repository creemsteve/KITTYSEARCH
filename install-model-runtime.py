#!/usr/bin/env python3
"""Install an inference backend into the Python environment running this script."""
import argparse
import importlib.metadata
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys


def runtime_library_root():
    spec = importlib.util.find_spec("llama_cpp")
    return Path(spec.origin).parent / "lib" if spec and spec.origin else None


def cuda_cublas_requirement(cuda_version):
    major, minor = int(cuda_version[2:-1]), int(cuda_version[-1])
    if major == 11:
        return "nvidia-cublas-cu11>=11.11,<12"
    package = "nvidia-cublas" if major >= 13 else "nvidia-cublas-cu12"
    return f"{package}>={major}.{minor},<{major}.{minor + 1}"


def stage_cuda_libraries(requirement):
    """Place redistributable cuBLAS DLLs beside llama.dll for source and frozen use."""
    package = requirement.split(">=", 1)[0]
    distribution = importlib.metadata.distribution(package)
    destination = runtime_library_root()
    if destination is None:
        raise RuntimeError("The installed llama_cpp package could not be located.")
    copied = []
    for entry in distribution.files or ():
        name = entry.name
        if name.lower().startswith(("cublas64_", "cublaslt64_")) and name.lower().endswith(".dll"):
            shutil.copy2(distribution.locate_file(entry), destination / name)
            copied.append(name)
        elif name.lower() in ("license.txt", "license"):
            shutil.copy2(distribution.locate_file(entry), destination / "NVIDIA-cuBLAS-LICENSE.txt")
    if len(copied) != 2 or not (destination / "NVIDIA-cuBLAS-LICENSE.txt").is_file():
        raise RuntimeError("The NVIDIA cuBLAS package must provide both runtime DLLs and its license.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("cpu", "cuda", "vulkan", "metal"), default="cpu")
    parser.add_argument("--cuda-version", choices=("cu118", "cu121", "cu122", "cu123", "cu124", "cu125", "cu130", "cu132"), default="cu124")
    args = parser.parse_args()
    if args.backend == "metal" and sys.platform != "darwin":
        parser.error("Metal requires macOS. Choose CUDA or Vulkan on Windows/Linux.")
    if args.backend == "cuda" and sys.platform == "darwin":
        parser.error("CUDA is not supported on macOS. Choose Metal instead.")
    pip = [sys.executable, "-m", "pip", "install"]
    # These files are staged by KITTYSEARCH rather than owned by the llama wheel.
    # Remove them before changing backends so Vulkan/CPU builds stay clean.
    library_root = runtime_library_root()
    if library_root:
        for pattern in ("cublas*.dll", "NVIDIA-cuBLAS-LICENSE.txt"):
            for path in library_root.glob(pattern):
                path.unlink()
    wheel = args.cuda_version if args.backend == "cuda" else args.backend
    # Isolate runtime wheel selection to its backend index. Mixing indexes can
    # silently select a newer CPU wheel instead of the requested GPU wheel.
    subprocess.run(pip + ["--force-reinstall", "--no-cache-dir", "--no-deps", "--only-binary=:all:",
                          "--index-url", "https://abetlen.github.io/llama-cpp-python/whl/" + wheel,
                          "llama-cpp-python>=0.3,<1"], check=True)
    subprocess.run(pip + ["-r", str(Path(__file__).with_name("requirements-model.txt"))], check=True)
    if args.backend == "cuda" and sys.platform == "win32":
        requirement = cuda_cublas_requirement(args.cuda_version)
        subprocess.run(pip + ["--only-binary=:all:", requirement], check=True)
        stage_cuda_libraries(requirement)
    # Verify in a fresh process so a previously loaded CPU DLL cannot mask the
    # newly installed backend. GPU selection must never silently ship CPU-only.
    subprocess.run([sys.executable, "-c",
                    "import json,sys; from kittysearch_models import check_runtime; "
                    "r=check_runtime(sys.argv[1]); print(json.dumps(r, indent=2)); "
                    "sys.exit(0 if r['ok'] else 1)", args.backend],
                   cwd=Path(__file__).resolve().parent, check=True)
    print("Installed " + args.backend + " inference runtime. Restart KITTYSEARCH to use it.")


if __name__ == "__main__":
    main()
