"""Apply the small Windows compatibility fix required by native SearXNG."""
from __future__ import annotations

import re
import sys
from pathlib import Path


def patch(source: Path) -> None:
    target = source / "searx" / "valkeydb.py"
    text = target.read_text(encoding="utf-8")
    text = re.sub(
        r"(?m)^import pwd\s*$",
        "try:\n    import pwd\nexcept ImportError:\n    pwd = None",
        text,
    )
    pattern = re.compile(
        r"(?s)\s*_pw = pwd\.getpwuid\(os\.getuid\(\)\)\s*"
        r"logger\.exception\(\"\[%s \(%s\)\] can't connect valkey DB \.\.\.\", "
        r"_pw\.pw_name, _pw\.pw_uid\)"
    )
    replacement = '''

        if pwd is not None:
            _pw = pwd.getpwuid(os.getuid())
            user_name, user_id = _pw.pw_name, _pw.pw_uid
        else:
            user_name, user_id = os.environ.get("USERNAME", "unknown"), os.getpid()
        logger.exception("[%s (%s)] can't connect valkey DB ...", user_name, user_id)'''
    text, count = pattern.subn(replacement, text)
    if count == 0 and "if pwd is not None:" not in text:
        raise RuntimeError("Could not find the expected Unix-only Valkey diagnostic in SearXNG source.")
    if re.search(r"(?m)^import pwd\s*$", text):
        raise RuntimeError("Windows patch failed: bare Unix-only pwd import remains.")
    target.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    try:
        patch(Path(sys.argv[1]))
        print("Applied native Windows compatibility patch to SearXNG.")
    except (OSError, IndexError, RuntimeError) as error:
        print(f"SearXNG Windows patch failed: {error}", file=sys.stderr)
        raise SystemExit(1)
