#!/usr/bin/env python3
"""KittySearch: a native SearXNG desktop app with optional local LLM review."""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

APP_NAME = "KittySearch"
VERSION = "0.1.0"
DEFAULTS = {
    "searxng_url": "http://127.0.0.1:8080",
    "searxng_mode": "external",
    "ollama_url": "http://127.0.0.1:11434",
    "model": "",
    "results": 20,
    "timeout": 20,
}


def data_dir() -> Path:
    override = os.environ.get("KITTYSEARCH_HOME")
    if override:
        return Path(override).expanduser()
    if getattr(sys, "frozen", False):
        # Keep the executable portable: settings are stored alongside it.
        return Path(sys.executable).resolve().parent / "kittysearch-data"
    return Path(__file__).resolve().parent / "kittysearch-data"


def load_config() -> dict[str, Any]:
    cfg = DEFAULTS.copy()
    p = data_dir() / "config.json"
    first_run = not p.exists()
    try:
        saved = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            cfg.update({k: v for k, v in saved.items() if k in cfg})
    except (OSError, ValueError):
        pass
    if first_run:
        if getattr(sys, "frozen", False) and os.name == "nt":
            cfg["searxng_mode"] = "windows"
        try:
            save_config(cfg)
        except OSError:
            pass
    cfg["searxng_url"] = os.environ.get("KITTYSEARCH_SEARXNG_URL", cfg["searxng_url"]).rstrip("/")
    cfg["ollama_url"] = os.environ.get("KITTYSEARCH_OLLAMA_URL", cfg["ollama_url"]).rstrip("/")
    cfg["model"] = os.environ.get("KITTYSEARCH_MODEL", cfg["model"])
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    p = data_dir() / "config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


MANAGED_CONTAINER = "kittysearch-searxng"
MANAGED_SETTINGS = data_dir() / "docker-searxng-settings.yml"
WINDOWS_MANAGED_SETTINGS = data_dir() / "searxng-settings.yml"
WINDOWS_SEARXNG_ROOT = data_dir() / "searxng-windows"
def bundled_searxng_root() -> Path | None:
    if getattr(sys, "frozen", False):
        root = Path(getattr(sys, "_MEIPASS", "")) / "searxng-runtime"
        if root.is_dir():
            return root
    return None

MANAGED_SEARXNG = False
MANAGED_SEARXNG_MODE = ""
MANAGED_PROCESS: subprocess.Popen[str] | None = None
WSL_DISTRO = os.environ.get("KITTYSEARCH_WSL_DISTRO", "Ubuntu")


def wait_for_managed_searxng(cfg: dict[str, Any], *, startup_message: str) -> None:
    deadline = time.time() + 75
    while time.time() < deadline:
        try:
            http_json(cfg["searxng_url"].rstrip("/") + "/config", timeout=2)
            return
        except Exception:
            time.sleep(.75)
    stop_managed_searxng()
    raise RuntimeError(startup_message)


def start_managed_searxng(cfg: dict[str, Any]) -> None:
    global MANAGED_SEARXNG
    parsed = urllib.parse.urlparse(cfg["searxng_url"])
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.path not in ("", "/"):
        raise ValueError("Automatic SearXNG mode requires a loopback HTTP URL such as http://127.0.0.1:8080, without a path.")
    port = parsed.port or 80
    if port < 1 or port > 65535:
        raise ValueError("SearXNG URL has an invalid port.")
    MANAGED_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    if not MANAGED_SETTINGS.exists():
        key = secrets.token_urlsafe(48)
        MANAGED_SETTINGS.write_text(
            "use_default_settings: true\nserver:\n  secret_key: '" + key + "'\n"
            "search:\n  formats:\n    - html\n    - json\n", encoding="utf-8")
    mount = str(MANAGED_SETTINGS.resolve()).replace("\\", "/")
    try:
        subprocess.run(["docker", "run", "--detach", "--rm", "--name", MANAGED_CONTAINER,
                        "--publish", f"127.0.0.1:{port}:8080", "--env", "SEARXNG_BASE_URL=" + cfg["searxng_url"].rstrip("/") + "/",
                        "--volume", f"{mount}:/etc/searxng/settings.yml:ro", "searxng/searxng:latest"],
                       check=True, capture_output=True, text=True, timeout=300)
    except FileNotFoundError as e:
        raise RuntimeError("Docker was not found. Install and start Docker Desktop or Docker Engine, or select existing SearXNG mode.") from e
    except subprocess.CalledProcessError as e:
        message = (e.stderr or e.stdout or str(e)).strip()
        raise RuntimeError("Could not start managed SearXNG: " + message) from e
    MANAGED_SEARXNG = True
    global MANAGED_SEARXNG_MODE
    MANAGED_SEARXNG_MODE = "docker"
    wait_for_managed_searxng(cfg, startup_message="SearXNG container started but did not become ready within 75 seconds.")


def start_wsl_searxng(cfg: dict[str, Any]) -> None:
    global MANAGED_SEARXNG, MANAGED_SEARXNG_MODE
    parsed = urllib.parse.urlparse(cfg["searxng_url"])
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.path not in ("", "/"):
        raise ValueError("WSL mode requires a loopback HTTP URL such as http://127.0.0.1:8080, without a path.")
    if os.name != "nt":
        raise RuntimeError("WSL mode is available only on Windows.")
    try:
        subprocess.run(["wsl.exe", "-d", WSL_DISTRO, "--", "bash", "-lc", "$HOME/.local/bin/kittysearch-searxng start"],
                       check=True, capture_output=True, text=True, timeout=300)
    except FileNotFoundError as e:
        raise RuntimeError(f"Windows Subsystem for Linux was not found. Install WSL2 and {WSL_DISTRO}, then run setup-searxng-wsl.ps1.") from e
    except subprocess.CalledProcessError as e:
        message = (e.stderr or e.stdout or str(e)).strip()
        raise RuntimeError("Could not start SearXNG in WSL. Run setup-searxng-wsl.ps1 first. " + message) from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("Starting SearXNG in WSL timed out.") from e
    MANAGED_SEARXNG = True
    MANAGED_SEARXNG_MODE = "wsl"
    wait_for_managed_searxng(cfg, startup_message=f"SearXNG in WSL did not become ready within 75 seconds. Check its WSL log with `wsl -d {WSL_DISTRO} -- cat ~/searxng/kittysearch-searxng.log`.")


def start_windows_searxng(cfg: dict[str, Any]) -> None:
    """Start a locally installed, patched SearXNG Python app on Windows."""
    global MANAGED_SEARXNG, MANAGED_SEARXNG_MODE, MANAGED_PROCESS
    parsed = urllib.parse.urlparse(cfg["searxng_url"])
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.path not in ("", "/"):
        raise ValueError("Windows SearXNG mode requires a loopback HTTP URL such as http://127.0.0.1:8080, without a path.")
    if os.name != "nt":
        raise RuntimeError("Native Windows SearXNG mode is available only on Windows.")
    bundle = bundled_searxng_root()
    runtime_root = bundle if bundle is not None else WINDOWS_SEARXNG_ROOT
    source = runtime_root / "source"
    python = (runtime_root / "python" / "python.exe" if bundle is not None
              else runtime_root / ".venv" / "Scripts" / "python.exe")
    settings = WINDOWS_MANAGED_SETTINGS
    entry = source / "searx" / "webapp.py"
    if not python.is_file() or not entry.is_file():
        if bundle is not None:
            raise RuntimeError("The bundled SearXNG runtime is incomplete. Rebuild KittySearch.exe.")
        raise RuntimeError("Native SearXNG is not installed. Run setup-searxng-windows.ps1 from the KittySearch folder first.")
    settings.parent.mkdir(parents=True, exist_ok=True)
    if not settings.exists():
        key = secrets.token_urlsafe(48)
        settings.write_text(
            "use_default_settings: true\nserver:\n  secret_key: '" + key + "'\n"
            "  bind_address: 127.0.0.1\n  port: " + str(parsed.port or 8080) + "\n  limiter: false\n"
            "search:\n  formats:\n    - html\n    - json\n", encoding="utf-8")
    env = os.environ.copy()
    env["SEARXNG_SETTINGS_PATH"] = str(settings.resolve())
    env["PYTHONUTF8"] = "1"
    log_path = data_dir() / "searxng-windows.log"
    error_path = data_dir() / "searxng-windows.err.log"
    stdout = log_path.open("a", encoding="utf-8")
    stderr = error_path.open("a", encoding="utf-8")
    try:
        MANAGED_PROCESS = subprocess.Popen([str(python), "-m", "searx.webapp"], cwd=str(source), env=env,
                                           stdout=stdout, stderr=stderr,
                                           creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    finally:
        stdout.close()
        stderr.close()
    MANAGED_SEARXNG = True
    MANAGED_SEARXNG_MODE = "windows"
    wait_for_managed_searxng(cfg, startup_message=f"Native SearXNG did not become ready within 75 seconds. Check {log_path} and {error_path}.")


def stop_managed_searxng() -> None:
    global MANAGED_SEARXNG, MANAGED_SEARXNG_MODE, MANAGED_PROCESS
    if MANAGED_SEARXNG:
        if MANAGED_SEARXNG_MODE == "windows" and MANAGED_PROCESS is not None:
            if MANAGED_PROCESS.poll() is None:
                MANAGED_PROCESS.terminate()
                try:
                    MANAGED_PROCESS.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    MANAGED_PROCESS.kill()
                    MANAGED_PROCESS.wait(timeout=5)
            MANAGED_PROCESS = None
        elif MANAGED_SEARXNG_MODE == "wsl":
            subprocess.run(["wsl.exe", "-d", WSL_DISTRO, "--", "bash", "-lc", "$HOME/.local/bin/kittysearch-searxng stop"],
                           capture_output=True, text=True, timeout=30)
        elif MANAGED_SEARXNG_MODE == "docker":
            subprocess.run(["docker", "stop", "--time", "10", MANAGED_CONTAINER],
                           capture_output=True, text=True, timeout=20)
        MANAGED_SEARXNG = False
        MANAGED_SEARXNG_MODE = ""


def http_json(url: str, *, method: str = "GET", payload: Any = None, timeout: int = 20) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers={"Accept": "application/json", "Content-Type": "application/json", "User-Agent": f"{APP_NAME}/{VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read(6_000_000)
    return json.loads(raw.decode("utf-8", errors="replace"))


def lexical_score(query: str, item: dict[str, Any]) -> tuple[int, list[str], bool]:
    title = str(item.get("title", ""))
    content = str(item.get("content", ""))
    url = str(item.get("url", ""))
    text = f"{title} {content}".lower()
    tokens = [x for x in re.findall(r"[\w-]{3,}", query.lower()) if x not in {"the", "and", "for", "with", "from", "how", "what", "why"}]
    score = 45
    matched = sum(1 for token in tokens if token in text)
    score += min(35, matched * 9)
    reasons = [f"Matches {matched}/{len(tokens)} query terms"] if tokens else ["General source review"]
    host = urllib.parse.urlparse(url).hostname or ""
    if host.endswith((".gov", ".gov.uk", ".edu", ".ac.uk")):
        score += 12
        reasons.append("Government or academic domain")
    if re.search(r"(?i)\b(source|references|methodology|documentation|official data|study|doi)\b", title + " " + content):
        score += 5
        reasons.append("Mentions sources, methods, or documentation")
    ai_pattern = re.compile(r"(?i)\b(ai[- ]generated|generated by ai|written by (?:chatgpt|an? ai)|chatgpt generated|midjourney|stable diffusion|prompt[- ]generated)\b")
    flagged = bool(ai_pattern.search(title + " " + content))
    if flagged:
        score -= 25
        reasons.append("Snippet explicitly indicates generative-AI authorship")
    return max(0, min(100, score)), reasons, flagged


def analyze_with_ollama(query: str, items: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    model = str(cfg.get("model", "")).strip()
    if not model:
        return {}
    compact = [{"id": str(i), "title": str(x.get("title", ""))[:300], "url": str(x.get("url", ""))[:500], "snippet": str(x.get("content", ""))[:700]} for i, x in enumerate(items)]
    prompt = (
        "Review search-result snippets for the user's query. Judge source relevance, credibility, and whether the page appears to be primarily AI-generated. "
        "Do not infer AI authorship from polished writing or from a site merely using AI; require explicit evidence in the supplied title/snippet. "
        "Do not reward a domain alone. Return ONLY JSON as {\"results\":[{\"id\":\"0\",\"relevance\":0,\"quality\":0,\"ai_generated\":false,\"confidence\":0,\"reason\":\"short evidence-based reason\"}]}. Scores are integers 0-100. "
        "Use ai_generated=true only with explicit evidence; otherwise false and confidence 0. Query: " + query + "\nResults: " + json.dumps(compact, ensure_ascii=False)
    )
    answer = http_json(cfg["ollama_url"] + "/api/chat", method="POST", timeout=int(cfg.get("timeout", 20)) * 3,
                       payload={"model": model, "stream": False, "format": "json", "messages": [{"role": "user", "content": prompt}], "options": {"temperature": 0}})
    content = answer.get("message", {}).get("content", "")
    try:
        parsed = json.loads(content)
        arr = parsed.get("results", []) if isinstance(parsed, dict) else parsed
        return {str(x.get("id")): x for x in arr if isinstance(x, dict) and "id" in x}
    except (ValueError, TypeError):
        return {}


def search(query: str, cfg: dict[str, Any], limit: int | None = None) -> dict[str, Any]:
    q = query.strip()
    if not q:
        raise ValueError("Enter a search query.")
    n = max(1, min(int(limit or cfg.get("results", 20)), 50))
    params = urllib.parse.urlencode({"q": q, "format": "json", "categories": "general", "language": "all", "safesearch": 1})
    try:
        result = http_json(cfg["searxng_url"] + "/search?" + params, timeout=int(cfg.get("timeout", 20)))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise RuntimeError("SearXNG rejected JSON output. Enable `json` in its `search.formats` setting.") from e
        raise RuntimeError(f"SearXNG returned HTTP {e.code}. Check the configured URL and server logs.") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f"Could not reach SearXNG at {cfg['searxng_url']}: {e}") from e
    items = result.get("results", [])[:n]
    if not isinstance(items, list):
        items = []
    model_error = None
    try:
        ai = analyze_with_ollama(q, items, cfg)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, KeyError) as e:
        ai = {}
        model_error = str(e)
    enriched = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        base, reasons, heuristic_ai = lexical_score(q, item)
        review = ai.get(str(i), {})
        relevance = _int_score(review.get("relevance"), base)
        quality = _int_score(review.get("quality"), base)
        explicit_ai = bool(review.get("ai_generated", False))
        confidence = _int_score(review.get("confidence"), 0)
        flagged_ai = explicit_ai and confidence >= 60 or heuristic_ai
        # Quality/relevance dominate; evidence-backed AI suspicion is a penalty,
        # never a silent deletion.
        score = round(relevance * .50 + quality * .50)
        if flagged_ai:
            score = max(0, score - (round(confidence * .35) if explicit_ai else 20))
        reason = str(review.get("reason", "")).strip()
        if reason:
            reasons = [reason]
        if flagged_ai:
            reasons.append("Likely generative-AI content; inspect the evidence")
        item.update({"kitty_score": max(0, min(100, score)), "kitty_relevance": relevance,
                     "kitty_quality": quality, "kitty_ai_generated": flagged_ai,
                     "kitty_ai_confidence": confidence, "kitty_reasons": reasons,
                     "kitty_ai_reviewed": bool(review)})
        enriched.append(item)
    enriched.sort(key=lambda x: (x["kitty_score"], x.get("score", 0)), reverse=True)
    return {"query": q, "results": enriched, "analyzed": bool(ai), "model": cfg.get("model") or None,
            "model_error": model_error, "searxng_url": cfg["searxng_url"], "timestamp": int(time.time())}


def _int_score(value: Any, default: int) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return default


def main() -> int:
    parser = argparse.ArgumentParser(prog="kittysearch", description="Native desktop search with local AI source review")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("desktop", help="start the native desktop application")
    psearch = sub.add_parser("search", help="search from the command line")
    psearch.add_argument("query", nargs="+")
    psearch.add_argument("--limit", type=int)
    psearch.add_argument("--json", action="store_true", help="print JSON output")
    sub.add_parser("doctor", help="check local SearXNG and Ollama connections")
    args = parser.parse_args()
    if args.command in (None, "desktop"):
        from kittysearch_desktop import run_desktop
        run_desktop()
        return 0
    cfg = load_config()
    if args.command == "doctor":
        print(f"Config: {data_dir() / 'config.json'}")
        for label, url, path in (("SearXNG", cfg["searxng_url"], "/config"), ("Ollama", cfg["ollama_url"], "/api/tags")):
            try:
                http_json(url + path, timeout=4)
                print(f"{label}: reachable at {url}")
            except Exception as e:
                print(f"{label}: unavailable at {url} ({e})")
        print(f"Model: {cfg['model'] or 'not configured'}")
        return 0
    if args.command == "search":
        try:
            data = search(" ".join(args.query), cfg, args.limit)
        except Exception as e:
            print(f"Search error: {e}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(f"{len(data['results'])} results for: {data['query']}" + (f" (reviewed by {data['model']})" if data["analyzed"] else " (lexical ranking; configure a local model for AI review)"))
            for i, x in enumerate(data["results"], 1):
                flag = " [LIKELY AI-GENERATED]" if x["kitty_ai_generated"] else ""
                print(f"\n{i}. [{x['kitty_score']}/100]{flag} {x.get('title', '')}\n   {x.get('url', '')}\n   {x.get('content', '')}")
                for reason in x["kitty_reasons"]:
                    print(f"   • {reason}")
            if data["model_error"]:
                print(f"\nLocal model unavailable: {data['model_error']}", file=sys.stderr)
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
