# Building KITTYSEARCH from source

This guide describes the source builds currently supported by this repository. The Windows script creates the portable executable and release ZIP used for Windows releases. Linux has a build helper for a standalone executable. macOS can be built locally with PyInstaller; this repository does not currently have a macOS release-packaging script.

## Common setup

Install Git, a supported Python interpreter, and the platform's Tk support. The desktop app itself uses the Python standard library. Packaging uses PyInstaller, and local GGUF inference uses `llama-cpp-python`.

Create a virtual environment from the project root:

```bash
python3 -m venv .venv
```

Activate it in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Or in a POSIX shell (Linux and macOS):

```bash
source .venv/bin/activate
```

The Windows release build requires **64-bit Python 3.11 or 3.12** and its own virtual environment because backend installation replaces that environment's inference runtime. Use the same dedicated-environment approach for Linux and macOS builds.

## Windows portable release

Build on Windows with 64-bit Python 3.11 or 3.12 and internet access. From the project root, create and activate the environment:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

The release default is Vulkan. Choose one backend and a separate output directory for each variant:

```powershell
.\build-windows.ps1 -Python .\.venv\Scripts\python.exe -InferenceBackend vulkan -DistDirectory dist/vulkan
.\build-windows.ps1 -Python .\.venv\Scripts\python.exe -InferenceBackend cuda -CudaVersion cu130 -DistDirectory dist/cuda
.\build-windows.ps1 -Python .\.venv\Scripts\python.exe -InferenceBackend cpu -DistDirectory dist/cpu
```

The script downloads SearXNG source, applies the Windows compatibility patch, builds the embedded SearXNG runtime, installs the selected inference backend, and packages `KITTYSEARCH.exe`. It checks the runtime in the build environment and runs a backend check in the finished executable. A failed check stops packaging. The Windows package includes the corresponding KITTYSEARCH and SearXNG sources, licenses, build metadata, instructions, and checksums; it excludes personal settings and model weights.

The resulting ZIP is labelled by backend: `KITTYSEARCH-Windows-x64-vulkan-portable.zip`, `KITTYSEARCH-Windows-x64-cuda-cu130-portable.zip`, or `KITTYSEARCH-Windows-x64-cpu-portable.zip`. CUDA builds also include NVIDIA's matching cuBLAS DLLs and license. GPU drivers are end-user prerequisites; users do not need Python, a compiler, or a GPU SDK.

Vulkan is the Windows default for compatible NVIDIA, AMD, and Intel graphics. CUDA is for compatible NVIDIA GPUs; select a wheel version supported by the target GPU architecture and driver. CUDA 13 supports compute capability 7.5 or newer, including RTX 50-series GPUs. CPU builds do not support GPU offload. Do not build multiple variants into the same output directory.

Before publishing a Windows release, follow the release checks in [AGENTS.md](AGENTS.md): run the unit suite, inspect ZIP contents and checksums, and run the extracted EXE's runtime check from a clean directory. If compatible hardware and a GGUF model are available, smoke-test actual GPU loading and generation as described there. Do not publish or replace release assets without authorization.

## Linux standalone executable

Install Python 3, Tk development support, and the native build tools required by your distribution. Create and activate a virtual environment as in [Common setup](#common-setup). The helper installs the inference runtime and PyInstaller into the active environment and creates `dist/KITTYSEARCH`:

```bash
./build-linux.sh
```

The Linux default backend is CPU. To choose another supported backend, set the environment variable for the build:

```bash
KITTYSEARCH_INFERENCE_BACKEND=vulkan ./build-linux.sh
KITTYSEARCH_INFERENCE_BACKEND=cuda KITTYSEARCH_CUDA_VERSION=cu130 ./build-linux.sh
```

The script bundles KITTYSEARCH, the selected `llama-cpp-python` runtime, and assets. It does not bundle or start SearXNG, create the Windows release ZIP/metadata/checksums, or run a runtime check against the finished executable. Configure a SearXNG service separately (local or remote) with JSON search enabled, then point KITTYSEARCH to it. Linux GPU support depends on the selected backend's compatible driver and runtime. A CPU build has no GPU offload.

Run the generated executable with:

```bash
./dist/KITTYSEARCH
```

## macOS local build

This repository does not currently provide a macOS release build or ZIP packager. To create a local PyInstaller build, install Xcode Command Line Tools, a Python installation with Tk support, and any native prerequisites required by the chosen inference wheel. Create and activate a virtual environment as in [Common setup](#common-setup), from the project root.

Install the build requirements and choose either Metal acceleration or CPU inference:

```bash
python -m pip install -r requirements-build.txt
python install-model-runtime.py --backend metal
python -m PyInstaller --noconfirm --clean --onefile --windowed --name KITTYSEARCH --collect-all llama_cpp --add-data "assets:assets" kittysearch.py
```

For a CPU-only build, replace the backend installation command with:

```bash
python install-model-runtime.py --backend cpu
```

PyInstaller output is created under `dist/` (a macOS `.app` bundle may be produced for a windowed build). This local build does not bundle SearXNG or create a signed/notarized release. Configure a SearXNG service separately with JSON search enabled. Metal requires a compatible Mac; CUDA is not supported on macOS. Keep the built app and runtime on the same Mac architecture for which they were created.

## Run from source

For development without a packaged executable, install the local model runtime only if needed, then run the app directly:

```bash
python -m pip install -r requirements-model.txt
python kittysearch.py
```

For a GPU runtime, use `install-model-runtime.py` with a supported backend (`vulkan`, `cuda`, or `metal` where supported) instead of relying on the CPU runtime. See [README.md](README.md#local-model) for backend selection, driver requirements, model setup, and SearXNG configuration.
