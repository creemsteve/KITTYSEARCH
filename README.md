# KittySearch

KittySearch is a native desktop app and CLI for SearXNG. It can send result titles and snippets to a local Ollama model, which scores relevance and source quality and flags pages that show evidence of generative-AI authorship. Results are ranked, not silently discarded; the app has an option to hide flagged results.

This repository is distributed under the GNU Affero General Public License v3.0. See [LICENSE](LICENSE).

## Requirements

- Python 3.10+ with Tk support to run from source. The application uses only the Python standard library.
- By default, a SearXNG instance with its JSON search format enabled. The desktop app can start SearXNG automatically in Docker, or run its Python app natively on Windows without Docker or WSL.
- Optional: Ollama with a model pulled locally. The model does not need Internet access after installation.

The app does not send search result text to a hosted AI service. It sends query text and result snippets to the configured local Ollama endpoint. Search queries go to the configured SearXNG instance, which may in turn contact upstream search engines according to its configuration.

## Run

```powershell
python kittysearch.py
```

```bash
python3 kittysearch.py
```

The native window includes Search and Settings tabs. Close the window to stop KittySearch.

## Configure

On first launch the app creates `kittysearch-data/config.json` next to the source file, or next to the frozen executable. Connection settings can be edited from the **Settings** tab and are saved to this file. Example:

```json
{
  "searxng_url": "http://127.0.0.1:8080",
  "searxng_mode": "external",
  "ollama_url": "http://127.0.0.1:11434",
  "model": "qwen2.5:7b",
  "results": 20,
  "timeout": 20
}
```

Choose the Docker mode in Settings to have KittySearch run the official `searxng/searxng` container on startup and stop it when KittySearch exits. Docker downloads the image the first time. This mode uses the configured loopback SearXNG URL and writes a local SearXNG settings file beside `config.json`.

### Native Windows setup without Docker or WSL

SearXNG does not officially support native Windows. The KittySearch EXE bundles its own SearXNG source, dependencies, and embedded Python runtime, so end users do not need Python, Docker, or WSL installed for search. On a fresh EXE setup, KittySearch starts its bundled SearXNG automatically at `http://127.0.0.1:8080`. You can change this under Connection settings.

When running KittySearch from source, native setup requires 64-bit Python 3.11 or 3.12 and internet access during installation. From the KittySearch folder, run:

```powershell
.\setup-searxng-windows.ps1
```

The script downloads SearXNG source, creates an isolated virtual environment, installs its Python requirements, and creates local settings with a generated secret key. It does not install Docker, WSL, or packages into your system Python. SearXNG source and logs are stored under `kittysearch-data\searxng-windows`; its settings are stored beside KittySearch's `config.json`.

In KittySearch **Settings**, choose the native Windows mode and use `http://127.0.0.1:8080`. KittySearch starts SearXNG when it launches and stops it when KittySearch exits. To select a Python executable explicitly, pass `-Python` (for example `-Python py`). To install a specific upstream branch or ref, pass `-Ref`.

SearXNG changes frequently and native Windows operation is not covered by upstream support. If an upstream update breaks the compatibility patch, rerun the setup script after removing `kittysearch-data\searxng-windows\source` to fetch a clean source tree. The setup preserves the local settings file.

For an existing WSL setup, choose **Start SearXNG automatically (Windows WSL2, no Docker)** and keep the SearXNG URL at `http://127.0.0.1:8080`. Run `setup-searxng-wsl.ps1` to install it in Ubuntu. The upstream Linux installation guide is [here](https://docs.searxng.org/admin/installation-searxng); keep `json` enabled in `search.formats`.

Choose **Connect to an existing SearXNG** to use an instance managed separately.

You can set `KITTYSEARCH_HOME`, `KITTYSEARCH_SEARXNG_URL`, `KITTYSEARCH_OLLAMA_URL`, and `KITTYSEARCH_MODEL` instead. Environment variables take precedence over the saved values when KittySearch starts. Command-line configuration checks:

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

KittySearch runs on Windows and Linux. On Windows, use the native setup above, WSL2, Docker, or point it at an existing SearXNG instance. Native Windows SearXNG is a compatibility setup and is not an upstream supported platform. On Linux, use SearXNG's supported installation methods or Docker mode. Ollama can run locally on Windows or Linux. Keep the endpoints on loopback unless you intentionally operate trusted services on another machine.

## Build a portable Windows EXE

Run the build script on Windows with 64-bit Python 3.11 or 3.12 and internet access:

```powershell
.\build-windows.ps1
```

The build downloads SearXNG source, applies the Windows compatibility patch, installs its dependencies into an embedded Python runtime, and packages all of that into `dist\KittySearch.exe`. It also creates `dist\SearXNG-source.zip`, which must accompany the EXE to provide the corresponding SearXNG source. The EXE has no installer and no Python, Docker, or WSL prerequisite. Place it in a writable folder and run `KittySearch.exe`; it opens a native desktop window without a browser. Settings and logs are written to `kittysearch-data` alongside it.

Ollama and its model weights remain separate optional services. The native SearXNG build tracks upstream `master` by default; pass `-SearXNGBranch` to select another branch. PyInstaller builds are platform-specific: build the Windows EXE on Windows and a Linux binary on Linux.

## Notes on AI-authorship screening

Authorship cannot be reliably determined from a search snippet alone. KittySearch only applies an AI penalty when the local model identifies direct evidence in the supplied snippet/title with adequate confidence, or a narrow explicit phrase heuristic matches. It does not treat general AI usage by a publisher as proof that a particular page was generated. Review the evidence before relying on an AI flag.
