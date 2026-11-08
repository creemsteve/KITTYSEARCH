"""Remove rebuildable files before collecting the portable Windows runtime."""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys


LINKER_SUFFIXES = frozenset({".lib", ".a", ".exp", ".pdb"})


def remove_files(root: Path, candidates) -> tuple[int, int]:
    """Remove only regular files contained in the requested runtime directory."""
    root = root.resolve()
    count = size = 0
    for path in candidates:
        if path.is_symlink() or not path.is_file():
            continue
        path.resolve().relative_to(root)
        length = path.stat().st_size
        path.unlink()
        count += 1
        size += length
    return count, size


def prune_bytecode(root: Path) -> tuple[int, int]:
    candidates = []
    for path in root.rglob("*.pyc"):
        try:
            source = Path(importlib.util.source_from_cache(str(path)))
        except ValueError:
            source = path.with_suffix(".py")
        # Keep sourceless modules and the embedded standard-library ZIP intact.
        if source.is_file():
            candidates.append(path)
    return remove_files(root, candidates)


def prune_linker_files(root: Path) -> tuple[int, int]:
    # DLLs, Python modules, metadata and redistribution licenses remain bundled.
    return remove_files(root, [p for p in root.iterdir() if p.suffix.lower() in LINKER_SUFFIXES])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    project = Path(__file__).resolve().parent
    bundle = args.bundle.resolve()
    if bundle != project / "build" / "searxng-runtime":
        parser.error("Only this project's build/searxng-runtime can be optimized.")
    if not all((bundle / name).is_dir() for name in ("python", "source", "site-packages")):
        parser.error("The embedded SearXNG runtime must be prepared first.")
    if sys.prefix == sys.base_prefix:
        parser.error("Use the dedicated build virtual environment.")
    spec = importlib.util.find_spec("llama_cpp")
    if spec is None or not spec.origin:
        parser.error("Install the inference backend before optimizing it.")
    libraries = Path(spec.origin).resolve().parent / "lib"
    libraries.relative_to(Path(sys.prefix).resolve())
    bytecode = prune_bytecode(bundle)
    linker = prune_linker_files(libraries)
    print(f"Removed {bytecode[0] + linker[0]} rebuildable runtime files "
          f"({bytecode[1] + linker[1]:,} bytes); native runtime libraries and licenses retained.")


if __name__ == "__main__":
    main()
