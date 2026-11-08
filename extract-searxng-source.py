"""Safely extract a SearXNG source ZIP on Windows, skipping Unix-only paths."""
from __future__ import annotations

import shutil
import stat
import sys
import zipfile
from pathlib import Path

INVALID = frozenset('<>:"\\|?*')
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def extract(archive_path: Path, destination: Path) -> tuple[int, int]:
    destination.mkdir(parents=True, exist_ok=True)
    files = skipped = 0
    try:
        with zipfile.ZipFile(archive_path) as archive:
            entries = []
            for info in archive.infolist():
                name = info.filename.replace("\\", "/").rstrip("/")
                if not name:
                    continue
                parts = tuple(name.split("/"))
                if info.is_dir() and len(parts) == 1:
                    continue
                if len(parts) < 2 or any(p in ("", ".", "..") for p in parts):
                    raise ValueError(f"Unsafe archive path: {info.filename!r}")
                entries.append((info, parts))
            roots = {parts[0] for _, parts in entries}
            if len(roots) != 1:
                raise ValueError("Expected a ZIP with one top-level directory.")
            root = next(iter(roots))
            for info, parts in entries:
                relative = parts[1:]
                if not relative:
                    continue
                if any(any(c in INVALID or ord(c) < 32 for c in p) or p.endswith((" ", ".")) or p.split(".", 1)[0].upper() in RESERVED for p in relative):
                    skipped += 1
                    continue
                if stat.S_ISLNK(info.external_attr >> 16):
                    skipped += 1
                    continue
                target = destination.joinpath(*relative)
                target.resolve().relative_to(destination.resolve())
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
                    files += 1
        missing = [p for p in ("setup.py", "requirements.txt", "searx/webapp.py", "searx/valkeydb.py") if not (destination / p).is_file()]
        if missing:
            raise ValueError("Incomplete SearXNG source archive; missing: " + ", ".join(missing))
        return files, skipped
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


if __name__ == "__main__":
    try:
        count, skipped = extract(Path(sys.argv[1]), Path(sys.argv[2]))
        print(f"Extracted {count} files; skipped {skipped} Windows-incompatible paths.")
    except (OSError, ValueError, IndexError, zipfile.BadZipFile) as error:
        print(f"SearXNG extraction failed: {error}", file=sys.stderr)
        raise SystemExit(1)
