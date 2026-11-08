"""Local model choices, saved inference settings, and conservative hardware estimates."""
from __future__ import annotations

import ctypes
import importlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
from typing import Any


DEFAULT_MODEL_ID = "granite-4.2-3b"
MODEL_CATALOG = {
    DEFAULT_MODEL_ID: {
        "name": "IBM Granite 4.2 3B · Q4_K_M", "size_gb": 2.24,
        "filename": "granite-4.2-3b-Q4_K_M.gguf",
        "url": "https://huggingface.co/ibm-granite/granite-4.2-3b-GGUF/resolve/c40945d/granite-4.2-3b-Q4_K_M.gguf",
        "sha256": "e0406663965846ae22a403456eb826ccce5f450840491f71952f18a7cb78e7d5",
        "page": "https://huggingface.co/ibm-granite/granite-4.2-3b-GGUF",
        "memory_gib": 4.5,
        "tradeoff": "3B model: a balance of review detail and speed; slower than the 1.5B option.",
    },
    "qwen2.5-1.5b": {
        "name": "Qwen 2.5 1.5B Instruct · Q4_K_M", "size_gb": 1.12,
        "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/dd26da440ef0330c47919d1ecae0966d24022222/qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "sha256": "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e",
        "page": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF",
        "memory_gib": 2.5,
        "tradeoff": "Smallest and likely fastest choice; may miss nuance or produce less consistent reviews.",
    },
    "llama3.2-3b": {
        "name": "Llama 3.2 3B Instruct · Q4_K_M", "size_gb": 2.02,
        "filename": "Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "url": "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/c1f82a567baf4622ef1be9094a208511846e60df/Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "sha256": "6c1a2b41161032677be168d354123594c0e6e67d2b9227c84f296ad037c728ff",
        "page": "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF",
        "memory_gib": 4.0,
        "tradeoff": "Alternative 3B instruct model; more capacity than 1.5B, with higher memory use and slower CPU review.",
    },
}
SETTING_KEYS = ("model_id", "model_path", "model_context", "model_threads",
                "model_gpu_layers", "model_acceleration", "model_main_gpu", "kitty_mode")


def catalog_model_path(home: Path, model_id: str) -> Path:
    if model_id not in MODEL_CATALOG:
        raise ValueError("Choose a model from the catalog.")
    return home / "models" / MODEL_CATALOG[model_id]["filename"]


def inference_settings(cfg: dict[str, Any]) -> dict[str, Any]:
    values = {"model_acceleration": cfg.get("model_acceleration", "auto")}
    if values["model_acceleration"] not in ("auto", "cpu", "gpu"):
        raise ValueError("Acceleration must be Auto, CPU or GPU.")
    for key, default, low, high, label in (
        ("model_context", 8192, 2048, 131072, "Context tokens"),
        ("model_threads", max(1, (os.cpu_count() or 2) - 1), 1, 1024, "CPU threads"),
        ("model_gpu_layers", -1, -1, 999, "GPU layers"),
        ("model_main_gpu", 0, 0, 63, "GPU device"),
    ):
        raw = cfg.get(key, default)
        if isinstance(raw, bool) or not re.fullmatch(r"-?[0-9]+", str(raw)):
            raise ValueError(f"{label} must be a whole number.")
        values[key] = int(raw)
        if not low <= values[key] <= high:
            raise ValueError(f"{label} must be between {low} and {high}.")
    if values["model_acceleration"] == "gpu" and values["model_gpu_layers"] == 0:
        raise ValueError("GPU mode needs at least one GPU layer, or -1 for all layers.")
    return values


def validate_settings(home: Path, cfg: dict[str, Any], *, require_file: bool = True) -> dict[str, Any]:
    values = inference_settings(cfg)
    kitty_mode = cfg.get("kitty_mode", False)
    if not isinstance(kitty_mode, bool):
        raise ValueError("kitty mode :3 must be enabled or disabled.")
    values["kitty_mode"] = kitty_mode
    model_id = cfg.get("model_id", DEFAULT_MODEL_ID)
    if model_id in MODEL_CATALOG:
        path = catalog_model_path(home, model_id)
    elif model_id == "custom":
        path = Path(str(cfg.get("model_path", ""))).expanduser()
        if path.suffix.lower() != ".gguf" or (require_file and not path.is_file()):
            raise ValueError("Choose an existing local GGUF file.")
        path = path.resolve()
    else:
        raise ValueError("Choose a catalog model or a local GGUF file.")
    return dict(values, model_id=model_id, model_path=str(path))


def load_settings(home: Path, defaults: dict[str, Any]) -> dict[str, Any]:
    try:
        saved = json.loads((home / "desktop-model.json").read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            return validate_settings(home, dict(defaults, **{k: v for k, v in saved.items() if k in SETTING_KEYS}), require_file=False)
    except (OSError, ValueError, TypeError):
        pass
    return validate_settings(home, defaults, require_file=False)


def save_settings(home: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    values = validate_settings(home, cfg)
    home.mkdir(parents=True, exist_ok=True)
    path = home / "desktop-model.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(values, indent=2), encoding="utf-8")
    temporary.replace(path)
    return values


def gpu_offload_supported(runtime: Any) -> bool:
    # Initialize devices before asking, especially for dynamically loaded backends.
    initialize = getattr(runtime, "llama_backend_init", None)
    if initialize:
        initialize()
    check = getattr(runtime, "llama_supports_gpu_offload", None)
    return bool(check and check())


def runtime_capabilities() -> dict[str, Any]:
    try:
        runtime = importlib.import_module("llama_cpp")
        gpu = gpu_offload_supported(runtime)
        info = runtime.llama_print_system_info()
        if isinstance(info, bytes):
            info = info.decode("utf-8", errors="replace")
        return {"installed": True, "gpu": gpu, "detail": str(info)}
    except Exception as exc:
        return {"installed": False, "gpu": False, "detail": str(exc)}


def _run(command: list[str]) -> str:
    return subprocess.check_output(command, text=True, timeout=8, stderr=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).strip()


def detect_hardware(home: Path) -> dict[str, Any]:
    """Best effort local detection; missing specs stay unknown, never zero."""
    result: dict[str, Any] = {"cpu": platform.processor() or platform.machine(), "threads": os.cpu_count(),
                              "ram_gib": None, "available_gib": None, "gpus": [], "disk_gib": None}
    gib = 1024 ** 3
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                result["cpu"] = str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong) for name in ("total", "available", "page_total", "page_available", "virtual_total", "virtual_available", "extended")]
        try:
            memory = MemoryStatus()
            memory.length = ctypes.sizeof(memory)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
                result.update(ram_gib=memory.total / gib, available_gib=memory.available / gib)
        except (OSError, AttributeError):
            pass
        try:
            # AdapterRAM from Win32_VideoController truncates VRAM above 4 GiB.
            # Use it only for adapter names; NVIDIA's utility supplies real VRAM.
            names = json.loads(_run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                                    "ConvertTo-Json -Compress -InputObject @(Get-CimInstance Win32_VideoController -ErrorAction Stop | Select-Object -ExpandProperty Name)"]))
            result["gpus"] = [{"name": name, "vram_gib": None} for name in names]
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    elif sys.platform.startswith("linux"):
        try:
            memory = dict(re.findall(r"^(MemTotal|MemAvailable):\s+(\d+)", Path("/proc/meminfo").read_text(), re.M))
            result.update(ram_gib=int(memory["MemTotal"]) * 1024 / gib,
                          available_gib=int(memory["MemAvailable"]) * 1024 / gib)
            cpu = re.search(r"^model name\s*:\s*(.+)", Path("/proc/cpuinfo").read_text(), re.M)
            if cpu:
                result["cpu"] = cpu[1]
            for vendor in Path("/sys/class/drm").glob("card[0-9]*/device/vendor"):
                device = vendor.parent
                vendor_id = vendor.read_text().strip()
                name = {"0x1002": "AMD", "0x8086": "Intel", "0x10de": "NVIDIA"}.get(vendor_id, vendor_id)
                vram = device / "mem_info_vram_total"
                result["gpus"].append({"name": name + " graphics", "vram_gib": int(vram.read_text()) / gib if vram.exists() else None})
        except (OSError, ValueError, KeyError):
            pass
    elif sys.platform == "darwin":
        try:
            result["ram_gib"] = int(_run(["sysctl", "-n", "hw.memsize"])) / gib
            result["gpus"] = [{"name": "Apple graphics (shared system memory)", "vram_gib": None}]
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    try:
        rows = _run(["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"])
        nvidia = []
        for row in rows.splitlines():
            name, total, free = row.rsplit(",", 2)
            nvidia.append({"name": name.strip(), "vram_gib": float(total) / 1024, "free_gib": float(free) / 1024})
        if nvidia:
            result["gpus"] = [gpu for gpu in result["gpus"] if "nvidia" not in gpu["name"].lower()] + nvidia
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    try:
        parent = home
        while not parent.exists() and parent != parent.parent:
            parent = parent.parent
        result["disk_gib"] = shutil.disk_usage(parent).free / gib
    except OSError:
        pass
    return result


def hardware_summary(hw: dict[str, Any], runtime: dict[str, Any]) -> str:
    def memory(value):
        return f"{value:.1f} GiB" if value is not None else "unknown"
    gpus = "; ".join(gpu["name"] + (f" ({gpu['vram_gib']:.1f} GiB VRAM)" if gpu.get("vram_gib") else " (VRAM unknown/shared)") for gpu in hw["gpus"])
    status = "GPU offload supported" if runtime["gpu"] else "CPU runtime; GPU offload unavailable"
    if not runtime["installed"]:
        status = "Inference runtime unavailable; install requirements-model.txt"
    return (f"{hw['cpu']} · {hw['threads'] or 'unknown'} logical CPU threads\n"
            f"RAM: {memory(hw['ram_gib'])} total / {memory(hw['available_gib'])} available · Disk free: {memory(hw['disk_gib'])}\n"
            f"Graphics: {gpus or 'not detected (GPU/VRAM unknown)'}\n{status}")


def model_guidance(model_id: str, hw: dict[str, Any], runtime: dict[str, Any], cfg: dict[str, Any], custom_bytes: int | None = None) -> str:
    spec = MODEL_CATALOG.get(model_id)
    if spec:
        # Allow context/KV growth; estimates deliberately leave room for buffers.
        context = int(cfg.get("model_context", 8192))
        required = spec["memory_gib"] + max(0, context - 8192) / 8192 * 1.5
        size_gib = spec["size_gb"] * 1e9 / 1024 ** 3
        tradeoff = spec["tradeoff"]
    elif custom_bytes:
        size_gib = custom_bytes / 1024 ** 3
        required = size_gib * 1.3 + 2 + max(0, int(cfg.get("model_context", 8192)) - 8192) / 8192 * 1.5
        tradeoff = "Custom model: architecture, context support, speed and review quality are unknown. File size gives only a rough memory estimate."
    else:
        return "Choose a GGUF file to estimate memory use. Custom model compatibility and review quality need testing."
    available = hw.get("available_gib")
    total = hw.get("ram_gib")
    gpu_memory = max((gpu.get("free_gib", gpu.get("vram_gib")) or 0 for gpu in hw["gpus"]), default=0)
    mode = cfg.get("model_acceleration", "auto")
    layers = int(cfg.get("model_gpu_layers", -1))
    gpu_enabled = mode != "cpu" and layers != 0 and runtime["gpu"]
    if gpu_enabled and gpu_memory >= required + 0.5:
        fit = "Likely to fit on a GPU with full offload; likely faster than CPU review."
        if layers > 0:
            fit = "GPU memory appears sufficient, but partial offload is selected; speed depends on layer count."
        fit += " Device selection and other GPU workloads can change this."
    elif available is not None and available < required + 1:
        fit = "Tight available RAM: may swap, run slowly or fail to load. Close other apps or try a smaller model."
    elif total is not None and total < required + 2:
        fit = "Limited system RAM: a smaller model is recommended to leave room for search and the OS."
    elif available is None:
        fit = "RAM availability unknown; fit cannot be confirmed."
    else:
        fit = "Likely to fit in RAM. CPU review is likely usable" + (" but slow on this CPU." if (hw.get("threads") or 0) < 4 else "; smaller models generally respond sooner.")
    if mode == "gpu" and not runtime["gpu"]:
        fit = "GPU mode cannot run with the current runtime. Install a GPU build or select Auto/CPU. " + fit
    elif gpu_enabled and gpu_memory < required + 0.5:
        fit += " GPU memory is insufficient or unknown; try partial layers. Auto can fall back to CPU if GPU loading fails."
    if not runtime["installed"]:
        fit = "Install the inference runtime before AI review can run. " + fit
    disk = hw.get("disk_gib")
    if disk is not None and disk < size_gib + 0.25:
        fit += " Not enough free disk space for a new download."
    return (f"{fit}\nEstimated model memory at this context: about {required:.1f} GiB, plus OS/search headroom. "
            f"{tradeoff}\nEstimates, not benchmarks: CPU generation, memory bandwidth, shared graphics memory, context and runtime affect speed. Review quality is not hardware-dependent and has not been benchmarked here.")
