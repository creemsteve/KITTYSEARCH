#!/usr/bin/env python3
"""Install an inference backend into the Python environment running this script."""
import argparse
from pathlib import Path
import subprocess
import sys


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
    wheel = args.cuda_version if args.backend == "cuda" else args.backend
    # Isolate runtime wheel selection to its backend index. Mixing indexes can
    # silently select a newer CPU wheel instead of the requested GPU wheel.
    subprocess.run(pip + ["--force-reinstall", "--no-cache-dir", "--no-deps", "--only-binary=:all:",
                          "--index-url", "https://abetlen.github.io/llama-cpp-python/whl/" + wheel,
                          "llama-cpp-python>=0.3,<1"], check=True)
    subprocess.run(pip + ["-r", str(Path(__file__).with_name("requirements-model.txt"))], check=True)
    print("Installed " + args.backend + " inference runtime. Restart KITTYSEARCH to use it.")


if __name__ == "__main__":
    main()
