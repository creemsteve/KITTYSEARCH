"""Assemble a portable Windows release without including personal application data."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import zipfile


ROOT = Path(__file__).resolve().parent
PORTABLE_README = """KITTYSEARCH for Windows x64

Extract the entire KITTYSEARCH folder to a writable location, then double-click
KITTYSEARCH.exe. No installer, Python, Docker, or WSL is required.

The native desktop app starts its embedded SearXNG service automatically.
Search requires an internet connection. The CPU local inference runtime is
included. Download a model in Settings, or choose an existing GGUF model there.
Model weights are not included in this archive.

Settings, downloaded models, learning flags, and service logs are kept in
kittysearch-data beside the executable. Move that folder with the executable
to keep your settings and downloaded models. Close the app before moving it.
Closing KITTYSEARCH stops the SearXNG instance that it started.

KITTYSEARCH is licensed under GNU AGPL v3. See LICENSE, README.md, and the
included KITTYSEARCH-source.zip and SearXNG-source.zip for corresponding source.
Bundled dependencies retain their own licenses inside the executable/runtime.
SHA256SUMS.txt contains checksums of the release files.
"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package(backend: str, searxng_ref: str) -> Path:
    dist = ROOT / "dist"
    executable = dist / "KITTYSEARCH.exe"
    searxng_source = dist / "SearXNG-source.zip"
    for required in (executable, searxng_source):
        if not required.is_file():
            raise FileNotFoundError(f"Build the Windows executable first: {required}")

    # Explicit source roots keep local settings, flags, downloaded weights,
    # environments, credentials, and build output out of public releases.
    sources = [p for p in ROOT.iterdir() if p.is_file() and (
        p.suffix in (".py", ".ps1", ".sh") or p.name in ("README.md", "LICENSE")
        or (p.name.startswith("requirements-") and p.suffix == ".txt"))]
    for directory in (ROOT / "assets", ROOT / "tests"):
        sources.extend(p for p in directory.rglob("*")
                       if p.is_file() and "__pycache__" not in p.parts)
    app_source = dist / "KITTYSEARCH-source.zip"
    with zipfile.ZipFile(app_source, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(sources):
            archive.write(path, "KITTYSEARCH/" + path.relative_to(ROOT).as_posix())

    info = {
        "application": "KITTYSEARCH", "platform": "windows-x64",
        "python": platform.python_version(), "inference_backend": backend,
        "pyinstaller": importlib.metadata.version("pyinstaller"),
        "llama_cpp_python": importlib.metadata.version("llama-cpp-python"),
        "searxng_ref": searxng_ref, "searxng_source_sha256": sha256(searxng_source),
        "executable_sha256": sha256(executable), "model_weights_included": False,
    }
    (dist / "build-info.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    (dist / "START-HERE.txt").write_text(PORTABLE_README, encoding="utf-8")
    files = [executable, searxng_source, app_source, ROOT / "LICENSE", ROOT / "README.md",
             dist / "build-info.json", dist / "START-HERE.txt"]
    checksums = dist / "SHA256SUMS.txt"
    checksums.write_text("".join(f"{sha256(p)}  {p.name}\n" for p in files), encoding="utf-8")
    output = dist / "KITTYSEARCH-Windows-x64-portable.zip"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files + [checksums]:
            archive.write(path, "KITTYSEARCH/" + path.name)
    output.with_suffix(".zip.sha256").write_text(f"{sha256(output)}  {output.name}\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("cpu", "cuda", "vulkan"), default="cpu")
    parser.add_argument("--searxng-ref", default="master")
    arguments = parser.parse_args()
    print(package(arguments.backend, arguments.searxng_ref))
