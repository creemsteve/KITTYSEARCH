# KittySearch

KittySearch is a local web interface and CLI for SearXNG. It can send result titles and snippets to a local Ollama model, which scores relevance and source quality and flags pages that show evidence of generative-AI authorship. Results are ranked, not silently discarded; the UI has an option to hide flagged results.

This repository is distributed under the GNU Affero General Public License v3.0. See [LICENSE](LICENSE).

## Requirements

- Python 3.10+ to run from source. The application uses only the Python standard library.
- A SearXNG instance with its JSON search format enabled.
- Optional: Ollama with a model pulled locally. The model does not need Internet access after installation.

The app does not send search result text to a hosted AI service. It sends query text and result snippets to the configured local Ollama endpoint. Search queries go to the configured SearXNG instance, which may in turn contact upstream search engines according to its configuration.

## Run

```powershell
python kittysearch.py serve --open
```

```bash
python3 kittysearch.py serve --open
```

Open `http://127.0.0.1:8787`. Press Ctrl+C to stop.

The interface includes Telnet and serial-terminal tabs. Telnet connects to a host and TCP port (default 23). The serial tab lists detected COM ports on Windows and common `/dev` serial devices on Linux. Auto-detect probes common baud rates and scores incoming text; the device must already be transmitting readable output. A silent device cannot reveal its baud rate. Probing opens the port repeatedly and can reset boards wired to reset on DTR. Serial uses 8 data bits, no parity, and 1 stop bit.

Telnet is unencrypted. Use it only on trusted networks; prefer SSH for remote administrative access.

## Configure

On first launch the app creates `kittysearch-data/config.json` next to the source file, or next to the frozen executable. Example:

```json
{
  "searxng_url": "http://127.0.0.1:8080",
  "ollama_url": "http://127.0.0.1:11434",
  "model": "qwen2.5:7b",
  "results": 20,
  "timeout": 20
}
```

You can set `KITTYSEARCH_HOME`, `KITTYSEARCH_SEARXNG_URL`, `KITTYSEARCH_OLLAMA_URL`, and `KITTYSEARCH_MODEL` instead. Command-line configuration checks:

```bash
python kittysearch.py doctor
python kittysearch.py search "how do heat pumps work" --limit 10
python kittysearch.py search "clinical guideline query" --json
```

SearXNG's `search.formats` setting must include `html` and `json`; some default setups disable JSON. Point KittySearch at the SearXNG base URL (not `/search`). SearXNG documents its [HTTP Search API](https://docs.searxng.org/dev/search_api) and [container setup](https://docs.searxng.org/admin/installation-docker). For example, in a SearXNG settings file:

```yaml
search:
  formats:
    - html
    - json
```

For Ollama, install it for [Windows](https://ollama.com/download/windows) or [Linux](https://ollama.com/download/linux), then pull and configure a local model:

```bash
ollama pull qwen2.5:7b
```

Set `"model": "qwen2.5:7b"` in `kittysearch-data/config.json`. Ollama serves its local API at `http://127.0.0.1:11434`. Model quality and speed vary by hardware. If Ollama is not configured or available, KittySearch still sorts results with a lightweight lexical/domain heuristic and clearly reports that AI review did not run.

## SearXNG and cross-platform setup

KittySearch itself runs on Windows and Linux. Run SearXNG separately using its supported deployment method (commonly a Linux host or container) and point KittySearch at its address. Ollama can run locally on Windows or Linux. Keep the endpoints on loopback unless you intentionally operate trusted services on another machine.

## Build a portable Windows EXE

Install PyInstaller on Windows, then run:

```powershell
python -m pip install -r requirements-build.txt
.
build-windows.ps1
```

The output is `dist\KittySearch.exe`, a PyInstaller one-file executable with the Python runtime and KittySearch application bundled. Place it in a writable folder and run `KittySearch.exe serve --open`; its settings are written to `kittysearch-data` alongside it. The EXE has no installer and no Python prerequisite.

The EXE encapsulates KittySearch, including the Telnet and serial terminal clients, not SearXNG or Ollama/model weights. Those are independent services and are kept separately so the same app can run on both operating systems. PyInstaller builds are platform-specific: build the Windows EXE on Windows and a Linux binary on Linux.

## Notes on AI-authorship screening

Authorship cannot be reliably determined from a search snippet alone. KittySearch only applies an AI penalty when the local model identifies direct evidence in the supplied snippet/title with adequate confidence, or a narrow explicit phrase heuristic matches. It does not treat general AI usage by a publisher as proof that a particular page was generated. Review the evidence before relying on an AI flag.
