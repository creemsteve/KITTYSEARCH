# KITTYSEARCH

KITTYSEARCH is a native desktop app and CLI for SearXNG. It can run a local GGUF language model directly inside the application to score relevance and source quality and flag pages that show evidence of generative-AI authorship. Results are ranked, not silently discarded; the app has an option to hide flagged results.

This repository is distributed under the GNU Affero General Public License v3.0. See [LICENSE](LICENSE).

## Requirements

- Python 3.10+ with Tk support to run from source. Search uses only the Python standard library.
- By default, a SearXNG instance with its JSON search format enabled. The desktop app starts its local Windows instance automatically when needed.
- Optional for AI review: `llama-cpp-python` and a compatible GGUF model file. Both run locally; no model server is used.

The app does not send search result text to a hosted AI service. Query text and result snippets are passed to the locally loaded model in the KITTYSEARCH process. Search queries go to the configured SearXNG instance, which may in turn contact upstream search engines according to its configuration.

## AI-assisted development

Generative AI tools have been used to help develop KITTYSEARCH, including writing and revising code, investigating bugs, and drafting documentation. The project maintainer guides the work and is responsible for reviewing and maintaining the resulting changes. AI-assisted work can contain errors, so review the source and verify behavior before relying on it. This development use is separate from KITTYSEARCH's optional local model features described below.

## Run

```powershell
python kittysearch.py
```

```bash
python3 kittysearch.py
```

The native window includes Search, Learning, Settings (local AI model), and SearXNG settings tabs. Close the window to stop KITTYSEARCH.

The GUI uses [IBM Carbon's Gray 100 dark theme](https://carbondesignsystem.com/building-blocks/foundations/themes/overview) and bundled IBM Plex Sans Regular, SemiBold, and Italic fonts. Source runs and portable Windows/Linux builds load the fonts privately for the application; no font installation or runtime download is required. Font files and their SIL Open Font License are included in `assets/fonts` (see its provenance README).

## Automatic setup

The desktop app defaults to a local SearXNG at `http://127.0.0.1:8080`; on Windows it starts the bundled or locally installed instance if needed. On Linux, run a SearXNG instance at that address with JSON enabled, or select Docker in **SearXNG settings**.

Open **SearXNG settings** to set the base URL, startup mode, and request timeout (1–300 seconds). **Test connection** checks the URL currently entered without saving or starting a server. **Save SearXNG settings** applies changes and saves them in `kittysearch-data/desktop-searxng.json`. Changing the URL or mode stops any instance started by KITTYSEARCH before applying the new connection. Existing instances are never stopped by KITTYSEARCH. Native Windows and WSL2 modes use port 8080; Docker supports other loopback HTTP ports. Existing instance mode supports HTTP or HTTPS servers, including a base path. WSL2 requires `setup-searxng-wsl.ps1`; Docker requires a running Docker installation.

The SearXNG settings tab also includes:

- **Search options:** language (`all`, `auto`, or a code such as `en-US`), SafeSearch (Off, Moderate, Strict), and comma-separated categories. SafeSearch depends on engine support, and server rules may override preferences.
- **Engines:** click **Load engines** to discover the current server's engine names, categories, and defaults. Hold Ctrl to select multiple engines, then click **Use selected** and save. You can also enter names separated by commas. Blank uses server defaults. With an explicit engine list, only chosen engines supporting your categories are requested. Unknown engines or categories stop the search instead of silently using defaults. This uses SearXNG's [search request handling](https://github.com/searxng/searxng/blob/master/searx/webadapter.py); engine choices apply to KITTYSEARCH searches and do not change the server's global configuration.
- **Sites:** comma-separated allowed and blocked domains. Blank allowed domains permits all sites; blocked domains always win. A domain includes its subdomains, with internationalized names supported. Enter hostnames such as `example.org`, without URL schemes, paths, ports, or wildcards.

Domain rules filter results locally before applying the result limit and running AI review. Saved rules also filter currently displayed results; run a new search to restore results after loosening a rule. They do **not** prevent SearXNG from contacting sites or fetching resources. Enforce network access policies in the server or firewall. Use the settings controls instead of `!engine`, `!!` redirect, or `:language` query shortcuts, which KITTYSEARCH rejects so they cannot override saved choices. Settings files from the earlier connection-only interface are loaded with general search, all languages, Moderate SafeSearch, server-default engines, and no domain filters.

Local model and acceleration choices are saved separately in `kittysearch-data/desktop-model.json`. The desktop app does not import the CLI configuration or settings saved by older versions.

For Windows source installations, run `./setup-searxng-windows.ps1` first. The portable Windows build includes SearXNG. SearXNG does not officially support native Windows.

The command line retains its independent `kittysearch-data/config.json` and supports `KITTYSEARCH_HOME`, `KITTYSEARCH_SEARXNG_URL`, and `KITTYSEARCH_MODEL_PATH`. Commands include:

```bash
python kittysearch.py doctor
python kittysearch.py search "how do heat pumps work" --limit 10
```

SearXNG's `search.formats` setting must include `html` and `json`; some default setups disable JSON. Point KITTYSEARCH at the SearXNG base URL (not `/search`). SearXNG documents its [HTTP Search API](https://docs.searxng.org/dev/search_api) and [container setup](https://docs.searxng.org/admin/installation-docker). For example, in a SearXNG settings file:

```yaml
search:
  formats:
    - html
    - json
```

### Local model

Open **Settings** to choose a model, then click **Download & use model**. Available downloads are [IBM Granite 4.2 3B Q4_K_M](https://huggingface.co/ibm-granite/granite-4.2-3b-GGUF) (2.24 GB), [Qwen 2.5 1.5B Instruct Q4_K_M](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF) (1.12 GB), and [Llama 3.2 3B Instruct Q4_K_M](https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF) (2.02 GB). **Model details & license** opens the selected model's source. Each download uses a pinned revision and SHA256 verification before installation in `kittysearch-data/models`; failed downloads leave installed files intact. You can also choose **Local GGUF file…** and browse to another compatible instruct model.

Use **Use model & save settings** to switch between installed models and save inference options. Changes apply to the next search. The old model is unloaded before loading its replacement. Before a download, or if inference fails, search uses lexical ranking and reports the problem.

Enable **kitty mode :3** in **Settings**, then click **Use model & save settings** to ask the local LLM to talk like a playful therian catgirl in its result explanations. It is off by default and saved with your model settings. The directive applies to the next search and keeps the required review format and evidence-based scoring instructions.

**Hardware acceleration** offers **Auto**, **CPU only**, and **GPU offload**, with GPU layer count (`-1` = all, `0` = CPU), GPU device index, CPU thread count, and context size. Auto uses offload when the installed runtime supports it and retries on CPU if GPU loading fails. Explicit GPU mode reports an error instead of silently using CPU. Search status reports the runtime choice or fallback.

**This computer & model fit** detects CPU threads, total/available RAM, graphics, VRAM when available, free disk space, and runtime GPU support. Selecting a model shows estimated memory needs, likely CPU/GPU fit, low-memory warnings, and speed/quality tradeoffs. Context size changes the memory estimate. These are conservative heuristics, not measured tokens/second or model-quality benchmarks. Missing VRAM information is shown as unknown; shared graphics memory is not assumed to be dedicated VRAM. **Refresh hardware** updates the snapshot as other apps consume memory.

When running from source, install the inference runtime in the same Python environment with `python -m pip install -r requirements-model.txt`. The packaged builds include the runtime. The model evaluates snippets, not full pages; check its scores and reasons against the sources.

For GPU acceleration, install a matching runtime and restart KITTYSEARCH (a CPU-only runtime cannot enable GPU offload through a setting):

```powershell
python install-model-runtime.py --backend vulkan
# NVIDIA alternative; choose a CUDA wheel compatible with your GPU/driver:
python install-model-runtime.py --backend cuda --cuda-version cu130
```

The installer selects prebuilt wheels from the [llama-cpp-python backend indexes](https://llama-cpp-python.readthedocs.io/en/latest/) and fails if no matching wheel exists for your Python/platform. Vulkan supports compatible NVIDIA, AMD and Intel graphics; CUDA requires compatible NVIDIA hardware and drivers. On macOS, `--backend metal` is available. `--backend cpu` restores the CPU runtime. Source builds of additional backends can follow the upstream instructions.

Portable builds default to CPU for compatibility. To include a GPU runtime on Windows, run `./build-windows.ps1 -InferenceBackend vulkan` or `./build-windows.ps1 -InferenceBackend cuda -CudaVersion cu130`. On Linux, run `KITTYSEARCH_INFERENCE_BACKEND=vulkan ./build-linux.sh`; CUDA builds also accept `KITTYSEARCH_CUDA_VERSION=cu130`. Build in a dedicated Python environment because backend selection replaces its inference runtime.

## Build a portable Windows EXE

Run the build script on Windows with 64-bit Python 3.11 or 3.12 and internet access:

```powershell
.\build-windows.ps1
```

The build downloads SearXNG source, applies the Windows compatibility patch, installs its dependencies into an embedded Python runtime, and packages all of that into `dist\KITTYSEARCH.exe`. The complete release is `dist\KITTYSEARCH-Windows-x64-portable.zip`: it includes the EXE, licenses, corresponding KITTYSEARCH and SearXNG source archives, instructions, build metadata, and SHA256 checksums. Personal settings, learning flags, and downloaded models are excluded from release archives.

Extract the ZIP to a writable folder and run `KITTYSEARCH.exe`; it opens a native desktop window without a browser. The EXE has no installer and no Python, Docker, or WSL prerequisite. Settings, downloaded models, and logs are written to `kittysearch-data` alongside it. Close KITTYSEARCH before moving it, and move that data folder with the EXE to preserve your setup. Keep the corresponding source archives with any redistributed executable. The build script works from any current directory; use `-Python .\.venv\Scripts\python.exe` to build with the project's virtual environment.

The portable EXE includes the local inference runtime; model weights are downloaded separately using the button in Settings. The native SearXNG build tracks upstream `master` by default; pass `-SearXNGBranch` to select another branch. PyInstaller builds are platform-specific: build the Windows EXE on Windows and a Linux binary on Linux.

## Notes on AI-authorship screening

Authorship cannot be reliably determined from a search snippet alone. Automatic screening applies an AI penalty only when a narrow explicit phrase heuristic matches the supplied snippet/title. A model claim alone does not establish authorship. It does not treat general AI usage by a publisher as proof that a particular page was generated. Review the evidence before relying on an AI flag. Your saved flags also affect ranking as described below.

## Learning from your flags

Select a search result and choose **Flag page as AI** or **Flag website as AI**. KITTYSEARCH remembers your choice, labels matching results **Flagged by you**, lowers their ranking, and includes them in **Hide likely AI-generated results**. Changes apply immediately and on future searches, even without a downloaded model. Repeated flags do not accumulate penalties.

The **Learning** tab lists all saved flags, lets you flag a URL directly, and lets you remove flags even when their results are hidden. You can also use **Unflag page** or **Unflag website** on a selected result. Removing a flag restores the original review and ranking; automatic AI evidence can still flag the result.

Page flags match the URL path and query, ignoring fragments, host capitalization, and default ports. Website flags match the exact hostname across HTTP/HTTPS and ports; they do not include other subdomains (`www.example.com` and `example.com` are separate). A website flag covers every page on that host, so use a page flag for a single article.

Flags are personal preferences stored in `kittysearch-data/learning.sqlite3` (or `KITTYSEARCH_HOME`), shared by desktop and CLI searches. They are never uploaded and do not retrain the local language model.
