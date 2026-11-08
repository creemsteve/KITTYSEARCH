# KITTYSEARCH

KITTYSEARCH is a native desktop app for SearXNG. It can run a local GGUF language model directly inside the application to summarize page findings, combine them into a general overview, score relevance and source quality, and flag pages that show evidence of generative-AI authorship. Results are ranked, not silently discarded; the app has an option to hide flagged results.

This repository is distributed under the GNU Affero General Public License v3.0. See [LICENSE](LICENSE).

## Requirements

- Python 3.10+ with Tk support to run from source. Search uses only the Python standard library.
- By default, a SearXNG instance with its JSON search format enabled. The desktop app starts its local Windows instance automatically when needed.
- Optional for AI review: `llama-cpp-python` and a compatible GGUF model file. Both run locally; no model server is used.

The app does not send search result text to a hosted AI service. Query text, result snippets, and retrieved page text (when enabled) are passed to the locally loaded model in the KITTYSEARCH process. Search queries go to the configured SearXNG instance, which may in turn contact upstream search engines according to its configuration. Page and Deep search depths also contact result websites directly from your computer.

## AI-assisted development

Generative AI tools have been used to help develop KITTYSEARCH, including writing and revising code, investigating bugs, and drafting documentation. The project maintainer guides the work and is responsible for reviewing and maintaining the resulting changes. AI-assisted work can contain errors, so review the source and verify behavior before relying on it. This development use is separate from KITTYSEARCH's optional local model features described below.

## Run

```powershell
python kittysearch.py
```

```bash
python3 kittysearch.py
```

The native window includes Claw, Pawprints, Settings (local AI model), and SearXNG settings tabs. Close the window to stop KITTYSEARCH.

The GUI uses [IBM Carbon's Gray 100 dark theme](https://carbondesignsystem.com/building-blocks/foundations/themes/overview) and bundled IBM Plex Sans Regular, SemiBold, and Italic fonts. Source runs and portable Windows/Linux builds load the fonts privately for the application; no font installation or runtime download is required. Font files and their SIL Open Font License are included in `assets/fonts` (see its provenance README).

## Automatic setup

The desktop app defaults to a local SearXNG at `http://127.0.0.1:8080`; on Windows it starts the bundled or locally installed instance if needed. On Linux, run a SearXNG instance at that address with JSON enabled, or select Docker in **SearXNG settings**.

Open **SearXNG settings** to set the base URL, startup mode, and request timeout (1–300 seconds). **Test connection** checks the URL currently entered without saving or starting a server. **Save SearXNG settings** applies changes and saves them in `kittysearch-data/desktop-searxng.json`. Changing the URL or mode stops any instance started by KITTYSEARCH before applying the new connection. Existing instances are never stopped by KITTYSEARCH. Native Windows and WSL2 modes use port 8080; Docker supports other loopback HTTP ports. Existing instance mode supports HTTP or HTTPS servers, including a base path. WSL2 requires `setup-searxng-wsl.ps1`; Docker requires a running Docker installation.

The SearXNG settings tab also includes:

- **Search options:** language (`all`, `auto`, or a code such as `en-US`), SafeSearch (Off, Moderate, Strict), and comma-separated categories. SafeSearch depends on engine support, and server rules may override preferences.
- **Engines:** click **Load engines** to discover the current server's engine names, categories, and defaults. Hold Ctrl to select multiple engines, then click **Use selected** and save. You can also enter names separated by commas. Blank uses server defaults. With an explicit engine list, only chosen engines supporting your categories are requested. Unknown engines or categories stop the search instead of silently using defaults. This uses SearXNG's [search request handling](https://github.com/searxng/searxng/blob/master/searx/webadapter.py); engine choices apply to KITTYSEARCH searches and do not change the server's global configuration.
- **Sites:** comma-separated allowed and blocked domains. Blank allowed domains permits all sites; blocked domains always win. A domain includes its subdomains, with internationalized names supported. Enter hostnames such as `example.org`, without URL schemes, paths, ports, or wildcards.

Domain rules filter results locally before applying the result limit and running AI review. Saved rules also filter currently displayed results; run a new search to restore results after loosening a rule. They do **not** prevent SearXNG from contacting sites or fetching resources. Enforce network access policies in the server or firewall. Use the settings controls instead of `!engine`, `!!` redirect, or `:language` query shortcuts, which KITTYSEARCH rejects so they cannot override saved choices. Settings files from the earlier connection-only interface are loaded with general search, all languages, Moderate SafeSearch, server-default engines, and no domain filters.

Local model and acceleration choices are saved separately in `kittysearch-data/desktop-model.json`. The desktop app does not import settings saved by older versions.

For Windows source installations, run `./setup-searxng-windows.ps1` first. The portable Windows build includes SearXNG. SearXNG does not officially support native Windows.

SearXNG's `search.formats` setting must include `html` and `json`; some default setups disable JSON. Point KITTYSEARCH at the SearXNG base URL (not `/search`). SearXNG documents its [HTTP Search API](https://docs.searxng.org/dev/search_api) and [container setup](https://docs.searxng.org/admin/installation-docker). For example, in a SearXNG settings file:

```yaml
search:
  formats:
    - html
    - json
```

### Local model

Open **Settings** to choose a model, then click **Download & use model**. Available models include [IBM Granite 4.2 3B Q4_K_M](https://huggingface.co/ibm-granite/granite-4.2-3b-GGUF) (2.24 GB), [IBM Granite 4.2 8B Q4_K_M](https://huggingface.co/ibm-granite/granite-4.2-8b-GGUF) (5.35 GB), and [IBM Granite 4.2 30B Q4_K_M](https://huggingface.co/gguf/granite-4.2-30b-GGUF) (18.03 GB); the larger Granite models need considerably more memory and can be slow on CPU. Smaller alternatives are [Qwen 2.5 1.5B Instruct Q4_K_M](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF) (1.12 GB) and [Llama 3.2 3B Instruct Q4_K_M](https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF) (2.02 GB). New 4B options are [Qwen3 4B Q4_K_M](https://huggingface.co/Qwen/Qwen3-4B-GGUF) (2.50 GB) and [Google Gemma 3 4B Instruct Q4_K_M](https://huggingface.co/unsloth/gemma-3-4b-it-GGUF) (2.49 GB). The 4B models use more memory than the 3B choices and can be slower on CPU; Gemma's terms apply to its use. **Model details & license** opens the selected model's source. Each download uses a pinned revision and SHA256 verification before installation in `kittysearch-data/models`; failed downloads leave installed files intact. You can also choose **Local GGUF file…** and browse to another compatible instruct model.

Use **Use model & save settings** to switch between installed models and save inference options. Changes apply to the next search. The old model is unloaded before loading its replacement. Before a download, or if inference fails, search uses lexical ranking and reports the problem.

**Search depth** in **Settings** controls how much content the local LLM examines per result. Choose **Snippets** (the default, using up to 250 characters of each search preview), **Page** (up to 6,000 extracted characters per page), or **Deep** (up to 24,000). Save with **Use model & save settings**. Page and Deep retrieve each result after domain filtering and the result limit, once the model is available. They extract HTML or plain text, remove common navigation, scripts and hidden markup, and review the text in passages that fit the model context. Ranking and explanations use the strongest reviewed passage for usable information relevant to your query. Higher depth takes longer and uses more local inference.

Retrieval uses up to four concurrent requests, a timeout of at most 20 seconds per request, and a 2 MB response limit. Redirects respect domain filters; local/private network destinations are skipped. PDFs and other unsupported types, failed requests, and pages without readable text fall back to snippets. JavaScript is not executed and no browser login cookies are used. **Catch details** shows the retrieval error or the retrieved URL, character coverage, truncation, and a text preview. Incomplete model reviews are reported. Depth limits cover extracted text from the start of the response, so even Deep may not read the whole page. Page text is held in memory for the current results; it is not saved as a page cache.

Each model-reviewed result also has a **Page overview** in **Catch details**, describing the knowledge or findings relevant to your query. For Page and Deep, it summarizes the strongest reviewed passage. The **General overview** tab below the result list combines these findings into a concise answer with numbered citations and clickable source links. Selecting a result opens **Catch details**; switch back to **General overview** to see the combined findings. It uses only the reviewed snippets or passages and is instructed to preserve uncertainty, disagreements, and gaps. Long result sets are combined in batches that fit the model context. The coverage note reports how many results contributed; unreviewed results do not supply findings. Hiding AI-flagged results does not regenerate the overview, which may still include those sources. Domain filters that remove results clear the overview until the next search. Failed synthesis leaves per-page reviews and ranking available. Check generated claims against the linked sources.

The local LLM is instructed to favor relevant academic articles and trusted sources, including peer-reviewed research, systematic reviews, government agencies, universities, expert institutions, and official documentation. It assesses credibility from the supplied content, distinguishes preprints from peer-reviewed research, and does not treat a domain or publisher alone as proof of quality. This guides review of retrieved results; it does not restrict search to academic sources.

Enable **kitty mode :3** in **Settings**, then click **Use model & save settings** to ask the local LLM to talk like a playful therian catgirl in its result explanations, page summaries, and general overview. It is off by default and saved with your model settings. The directive applies to the next search and keeps the required review format and evidence-based scoring instructions.

**Hardware acceleration** offers **Auto**, **CPU only**, and **GPU offload**, with GPU layer count (`-1` = all, `0` = CPU), GPU device index, CPU thread count, and context size. Auto uses offload when the installed runtime supports it and retries on CPU if GPU loading fails. Explicit GPU mode reports an error instead of silently using CPU. Search status reports the runtime choice or fallback.

**This computer & model fit** detects CPU threads, total/available RAM, graphics, VRAM when available, free disk space, and runtime GPU support. Selecting a model shows estimated memory needs, likely CPU/GPU fit, low-memory warnings, and speed/quality tradeoffs. Context size changes the memory estimate. These are conservative heuristics, not measured tokens/second or model-quality benchmarks. Missing VRAM information is shown as unknown; shared graphics memory is not assumed to be dedicated VRAM. **Refresh hardware** updates the snapshot as other apps consume memory.

When running from source, install the inference runtime in the same Python environment with `python -m pip install -r requirements-model.txt`. The packaged builds include the runtime. The model evaluates snippets or retrieved page passages according to Search depth; check its scores and reasons against the sources.

When running from source, install a matching GPU runtime and restart KITTYSEARCH (a CPU-only runtime cannot enable GPU offload through a setting):

```powershell
python install-model-runtime.py --backend vulkan
# NVIDIA alternative; choose a CUDA wheel compatible with your GPU/driver:
python install-model-runtime.py --backend cuda --cuda-version cu130
```

The installer selects prebuilt wheels from the [llama-cpp-python backend indexes](https://llama-cpp-python.readthedocs.io/en/latest/) and fails if no matching wheel exists for your Python/platform. Vulkan supports compatible NVIDIA, AMD and Intel graphics; CUDA requires compatible NVIDIA hardware and drivers. On macOS, `--backend metal` is available. `--backend cpu` restores the CPU runtime. Source builds of additional backends can follow the upstream instructions.

Windows portable builds include Vulkan GPU support by default, for compatible NVIDIA, AMD, and Intel graphics. Keep the graphics driver up to date; Python and the Vulkan SDK are not required. Auto can retry model loading on CPU, but the Vulkan runtime still requires a Vulkan-capable graphics driver to load. For computers without that driver, build with `./build-windows.ps1 -InferenceBackend cpu`. NVIDIA-specific builds can use `./build-windows.ps1 -InferenceBackend cuda -CudaVersion cu130 -DistDirectory dist/cuda`. CUDA wheels must support the target GPU architecture and driver; CUDA 13 supports compute capability 7.5 or newer, including RTX 50-series GPUs. CUDA 12 wheels cover older supported GPUs but may not support newer architectures. Build in a dedicated Python environment because backend selection replaces its inference runtime. Use separate output directories when building multiple variants.

Earlier portable releases included only the CPU runtime. If one reports **GPU offload is unavailable**, select **Auto** or **CPU only** in Settings and save, or replace the EXE with a GPU-enabled portable build. Keep `kittysearch-data` to preserve settings and models. Installing `llama-cpp-python` on the host does not change the embedded runtime. `START-HERE.txt` and `build-info.json` identify the backend included in a release.

On Windows, the CUDA installer also stages NVIDIA's matching cuBLAS runtime DLLs and license alongside the inference library, so the portable CUDA build includes those dependencies. A compatible NVIDIA driver is still required; the full CUDA Toolkit is not.

Linux standalone builds default to CPU. For Vulkan, run `KITTYSEARCH_INFERENCE_BACKEND=vulkan ./build-linux.sh`; CUDA builds also accept `KITTYSEARCH_CUDA_VERSION=cu130`. These builds do not create the Windows release ZIP. See [BUILDING.md](BUILDING.md) for Linux and macOS commands and current packaging limits.

## Build a portable Windows EXE

For complete source-build instructions covering Windows, Linux, and macOS, see [BUILDING.md](BUILDING.md). Only the Windows build currently creates the portable release package.

Run the build script on Windows with 64-bit Python 3.11 or 3.12 and internet access. Build in a dedicated virtual environment because selecting a backend replaces its inference runtime:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
.\build-windows.ps1 -Python .\.venv\Scripts\python.exe -InferenceBackend vulkan -DistDirectory dist/vulkan
```

The build downloads SearXNG source, applies the Windows compatibility patch, installs its dependencies into an embedded Python runtime, and packages all of that into `dist\KITTYSEARCH.exe`. It verifies the selected inference backend both after installation and inside the finished EXE; a missing or incorrect backend stops packaging. The runtime check and bundled native library names are recorded in `build-info.json`. Release ZIPs identify their backend, such as `KITTYSEARCH-Windows-x64-vulkan-portable.zip`, `KITTYSEARCH-Windows-x64-cuda-cu130-portable.zip`, or `KITTYSEARCH-Windows-x64-cpu-portable.zip`. Each includes the EXE, licenses, corresponding KITTYSEARCH and SearXNG source archives, instructions, build metadata, and SHA256 checksums. Personal settings, learning flags, and downloaded models are excluded from release archives.

Windows builds omit rebuildable bytecode caches and build-only inference linker/debug files, retain runtime DLLs and licenses, and use maximum Deflate compression for release ZIPs. See [BUILDING.md](BUILDING.md) for the size optimizations and build details.

Extract the ZIP to a writable folder and run `KITTYSEARCH.exe`; it opens a native desktop window without a browser. The EXE has no installer and no Python, Docker, or WSL prerequisite. Settings, downloaded models, and logs are written to `kittysearch-data` alongside it. Close KITTYSEARCH before moving it, and move that data folder with the EXE to preserve your setup. Keep the corresponding source archives with any redistributed executable. The build script works from any current directory; use `-Python .\.venv\Scripts\python.exe` to build with the project's virtual environment.

The portable EXE includes the local inference runtime; model weights are downloaded separately using the button in Settings. The native SearXNG build tracks upstream `master` by default; pass `-SearXNGBranch` to select another branch. PyInstaller builds are platform-specific: build the Windows EXE on Windows and a Linux binary on Linux.

Agent build and release requirements are maintained in [AGENTS.md](AGENTS.md). To check an extracted release without opening the GUI, run `KITTYSEARCH.exe runtime-check --backend vulkan --output runtime-check.json` (use `cuda` or `cpu` for those variants). Add `--model "C:\path\to\model.gguf"` to test actual model loading and a short generation. The JSON report records success or failure; GPU tests use explicit offload without CPU fallback.

## Notes on AI-authorship screening

Authorship cannot be reliably determined from a search snippet alone. Automatic screening applies an AI penalty only when a narrow explicit phrase heuristic matches the supplied snippet/title. A model claim alone does not establish authorship. It does not treat general AI usage by a publisher as proof that a particular page was generated. Review the evidence before relying on an AI flag. Your saved flags also affect ranking as described below.

## Learning from your flags

Select a search result and choose **Flag page as AI** or **Flag website as AI**. KITTYSEARCH remembers your choice, labels matching results **Flagged by you**, lowers their ranking, and includes them in **Hide likely AI-generated results**. Changes apply immediately and on future searches, even without a downloaded model. Repeated flags do not accumulate penalties.

The **Learning** tab lists all saved flags, lets you flag a URL directly, and lets you remove flags even when their results are hidden. You can also use **Unflag page** or **Unflag website** on a selected result. Removing a flag restores the original review and ranking; automatic AI evidence can still flag the result.

Page flags match the URL path and query, ignoring fragments, host capitalization, and default ports. Website flags match the exact hostname across HTTP/HTTPS and ports; they do not include other subdomains (`www.example.com` and `example.com` are separate). A website flag covers every page on that host, so use a page flag for a single article.

Flags are personal preferences stored in `kittysearch-data/learning.sqlite3`. They are never uploaded and do not retrain the local language model.
