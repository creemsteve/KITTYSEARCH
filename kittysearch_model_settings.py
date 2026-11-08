"""Desktop model controls, kept independent of search and service settings."""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, ttk
import webbrowser

import kittysearch as core
import kittysearch_models as models
from kittysearch_theme import COLORS


class ModelSettingsMixin:
    def _build_settings(self) -> None:
        self._model_downloading = False
        self._model_hw = None
        self._model_runtime = None
        outer = self.settings_tab
        canvas = tk.Canvas(outer, background=COLORS["background"], highlightthickness=0)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        f = ttk.Frame(canvas, padding=(0, 0, 16, 16))
        window = canvas.create_window((0, 0), window=f, anchor="nw")
        f.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        self._model_wrapped_labels = []
        def resize(event):
            canvas.itemconfigure(window, width=event.width)
            for label in self._model_wrapped_labels:
                label.configure(wraplength=max(300, event.width - 32))
        canvas.bind("<Configure>", resize)
        def wheel(event):
            steps = max(1, abs(event.delta) // 120) if event.delta else 1
            canvas.yview_scroll(-steps if event.delta > 0 or event.num == 4 else steps, "units")
            return "break"
        def bind_wheel(widget):
            widget.bind("<MouseWheel>", wheel, add="+")
            widget.bind("<Button-4>", wheel, add="+")
            widget.bind("<Button-5>", wheel, add="+")
            for child in widget.winfo_children():
                bind_wheel(child)
        def hint(text="", parent=None):
            label = ttk.Label(parent or f, text=text, style="Hint.TLabel", wraplength=850, justify="left")
            label.pack(anchor="w", fill="x", pady=(6, 10))
            self._model_wrapped_labels.append(label)
            return label
        ttk.Label(f, text="Local AI model", style="Title.TLabel").pack(anchor="w")
        self.active_model_label = hint()
        self.model_choices = {spec["name"]: key for key, spec in models.MODEL_CATALOG.items()}
        self.model_choices["Local GGUF file…"] = "custom"
        current = self.cfg.get("model_id", models.DEFAULT_MODEL_ID)
        self.model_choice = tk.StringVar(value=next(label for label, key in self.model_choices.items() if key == current))
        self.model_picker = ttk.Combobox(f, textvariable=self.model_choice, values=list(self.model_choices), state="readonly")
        self.model_picker.pack(fill="x")
        self.model_picker.bind("<<ComboboxSelected>>", lambda _e: self._update_model_status())
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(8, 0))
        self.custom_model_path = tk.StringVar(value=self.cfg["model_path"] if current == "custom" else "")
        self.custom_model_entry = ttk.Entry(row, textvariable=self.custom_model_path)
        self.custom_model_entry.pack(side="left", fill="x", expand=True)
        self.custom_model_entry.bind("<FocusOut>", lambda _e: self._update_model_guidance())
        self.browse_model_button = ttk.Button(row, text="Browse GGUF…", command=self._browse_model)
        self.browse_model_button.pack(side="left", padx=(8, 0))
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(10, 0))
        self.download_button = ttk.Button(row, text="Download & use model", command=self._download_model, style="Primary.TButton")
        self.download_button.pack(side="left")
        self.model_page_button = ttk.Button(row, text="Model details & license", command=self._open_model_page)
        self.model_page_button.pack(side="left", padx=(8, 0))
        self.download_status = hint()
        acceleration_divider = ttk.Separator(f)
        acceleration_divider.pack(fill="x", pady=(4, 12))
        ttk.Label(f, text="Hardware acceleration", style="Section.TLabel").pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=8)
        self.acceleration_modes = {"Auto (GPU when available)": "auto", "CPU only": "cpu", "GPU offload": "gpu"}
        self.acceleration = tk.StringVar(value=next(label for label, mode in self.acceleration_modes.items() if mode == self.cfg["model_acceleration"]))
        self.acceleration_picker = ttk.Combobox(row, textvariable=self.acceleration, values=list(self.acceleration_modes), state="readonly", width=30)
        self.acceleration_picker.pack(side="left")
        self.acceleration_picker.bind("<<ComboboxSelected>>", lambda _e: self._acceleration_changed())
        fields = ttk.Frame(f)
        fields.pack(fill="x")
        self.model_fields = {}
        self.model_field_entries = {}
        for index, (key, label) in enumerate((("model_gpu_layers", "GPU layers (-1 = all)"), ("model_main_gpu", "GPU device (0 = first)"), ("model_threads", "CPU threads"), ("model_context", "Context tokens"))):
            box = ttk.Frame(fields)
            box.grid(row=0, column=index, sticky="ew", padx=(0, 12))
            fields.columnconfigure(index, weight=1)
            ttk.Label(box, text=label).pack(anchor="w")
            variable = tk.StringVar(value=str(self.cfg[key]))
            entry = ttk.Entry(box, textvariable=variable, width=14)
            entry.pack(fill="x", pady=(6, 0))
            entry.bind("<FocusOut>", lambda _e: self._update_model_guidance())
            self.model_fields[key] = variable
            self.model_field_entries[key] = entry
        hint("Auto tries GPU offload and falls back to CPU if loading fails. GPU mode requires a compatible runtime and driver. "
             "Reduce GPU layers if video memory is tight. Device numbers follow the inference runtime's order.")
        ttk.Label(f, text="Search depth", style="Section.TLabel").pack(anchor="w", pady=(8, 0))
        self.depth_choices = core.pages.DEPTH_LABELS
        self.search_depth = tk.StringVar(value=next(label for label, key in self.depth_choices.items()
                                                   if key == self.cfg.get("search_depth", "snippets")))
        self.depth_picker = ttk.Combobox(f, textvariable=self.search_depth, values=list(self.depth_choices), state="readonly")
        self.depth_picker.pack(fill="x", pady=(6, 0))
        hint("Snippets uses search previews only. Page reads up to 6,000 characters per result; Deep reads up to 24,000. "
             "Page and Deep contact result websites directly and take longer. The local model reviews text in passages; "
             "blocked, unsupported or unreadable pages use snippets. Save to apply to the next claw.")
        self.kitty_mode = tk.BooleanVar(value=self.cfg.get("kitty_mode", False))
        self.kitty_mode_toggle = ttk.Checkbutton(f, text="kitty mode :3", variable=self.kitty_mode)
        self.kitty_mode_toggle.pack(anchor="w", pady=(4, 0))
        hint("Ask the local AI to talk like a playful therian catgirl in result explanations. "
             "Save settings to apply this voice to the next claw.")
        self.save_model_button = ttk.Button(f, text="Use model & save settings", command=self._save_model_settings, style="Primary.TButton")
        self.save_model_button.pack(anchor="w")
        self.model_settings_status = hint("Changes apply to the next claw; an active claw keeps its current settings.")
        hardware_panel = ttk.Frame(f)
        hardware_panel.pack(fill="x", before=acceleration_divider, pady=(4, 8))
        row = ttk.Frame(hardware_panel)
        row.pack(fill="x")
        ttk.Label(row, text="This computer & model fit", style="Section.TLabel").pack(side="left")
        self.refresh_hardware_button = ttk.Button(row, text="Refresh hardware", command=self._refresh_model_hardware)
        self.refresh_hardware_button.pack(side="right")
        self.model_hardware_label = hint("Detecting CPU, RAM, graphics and runtime…", hardware_panel)
        self.model_guidance_label = hint(parent=hardware_panel)
        bind_wheel(f)
        self._acceleration_changed()
        self._update_model_status()
        # Scan only when this tab is first opened; search startup stays light.
        self.tabs.bind("<<NotebookTabChanged>>", self._model_tab_changed, add="+")

    def _model_tab_changed(self, _event=None):
        if self.tabs.select() == str(self.settings_tab) and self._model_hw is None and not getattr(self, "_hardware_scan_started", False):
            self._refresh_model_hardware()

    def _selected_model_id(self):
        return self.model_choices[self.model_choice.get()]

    def _model_form_settings(self):
        values = dict(self.cfg, model_id=self._selected_model_id(), model_path=self.custom_model_path.get(),
                      model_acceleration=self.acceleration_modes[self.acceleration.get()], kitty_mode=self.kitty_mode.get(),
                      search_depth=self.depth_choices[self.search_depth.get()])
        values.update({key: var.get().strip() for key, var in self.model_fields.items()})
        return models.validate_settings(core.data_dir(), values)

    def _browse_model(self):
        path = filedialog.askopenfilename(parent=self.root, title="Choose an instruct GGUF model", filetypes=[("GGUF models", "*.gguf")])
        if path:
            self.custom_model_path.set(path)
            self._update_model_status()

    def _open_model_page(self):
        spec = models.MODEL_CATALOG.get(self._selected_model_id())
        if spec:
            webbrowser.open(spec["page"])

    def _acceleration_changed(self):
        cpu = self.acceleration_modes[self.acceleration.get()] == "cpu"
        for key in ("model_gpu_layers", "model_main_gpu"):
            self.model_field_entries[key].configure(state="disabled" if cpu else "normal")
        self._update_model_guidance()

    def _update_model_status(self):
        model_id = self._selected_model_id()
        custom = model_id == "custom"
        self.custom_model_entry.configure(state="normal" if custom else "disabled")
        self.browse_model_button.configure(state="normal" if custom and not self._model_downloading else "disabled")
        self.model_page_button.configure(state="disabled" if custom else "normal")
        path = core.Path(self.custom_model_path.get()).expanduser() if custom else models.catalog_model_path(core.data_dir(), model_id)
        installed = path.is_file()
        self.download_button.configure(state="disabled" if custom or installed or self._model_downloading else "normal")
        if not self._model_downloading:
            spec = models.MODEL_CATALOG.get(model_id)
            size = f" Download: {spec['size_gb']:.2f} GB; SHA256 verified before use." if spec else " Choose an instruct model supported by llama.cpp."
            self.download_status.configure(text=("Selected model is installed." if installed else "Selected model is not installed.") + size)
        self.active_model_label.configure(text=f"Active model: {core.Path(self.cfg['model_path']).name}. Models run locally.")
        self._update_model_guidance()

    def _save_model_settings(self):
        try:
            values = models.save_settings(core.data_dir(), self._model_form_settings())
        except (ValueError, OSError) as exc:
            self.model_settings_status.configure(text=f"Settings were not saved: {exc}")
            return
        self.cfg = dict(self.cfg, **values)
        installed = core.Path(values["model_path"]).is_file()
        self.model_settings_status.configure(text="Settings saved. The next claw will load this model." if installed else "Settings saved. Download this model to enable AI review.")
        self._update_model_status()
        self._refresh_health()

    def _set_download_busy(self, busy):
        self._model_downloading = busy
        self.model_picker.configure(state="disabled" if busy else "readonly")
        self.custom_model_entry.configure(state="disabled" if busy else "normal")
        self.save_model_button.configure(state="disabled" if busy else "normal")
        self.kitty_mode_toggle.configure(state="disabled" if busy else "normal")
        self.depth_picker.configure(state="disabled" if busy else "readonly")
        self.acceleration_picker.configure(state="disabled" if busy else "readonly")
        for entry in self.model_field_entries.values():
            entry.configure(state="disabled" if busy else "normal")
        if not busy:
            self._acceleration_changed()
        self._update_model_status()

    def _download_model(self):
        if self._model_downloading:
            return
        try:
            settings = self._model_form_settings()
        except ValueError as exc:
            self.download_status.configure(text=str(exc))
            return
        model_id = settings["model_id"]
        if model_id not in models.MODEL_CATALOG:
            return
        self._set_download_busy(True)
        self.download_status.configure(text="Downloading selected model…")
        last_update = [0.0]
        def progress(received, total):
            now = core.time.monotonic()
            if now - last_update[0] < 0.2 and received != total:
                return
            last_update[0] = now
            message = f"Downloading… {received * 100 // total}%" if total else f"Downloading… {received // (1024 * 1024)} MiB"
            self._post_model(lambda: self.download_status.configure(text=message))
        def run():
            try:
                core.download_model(progress, model_id=model_id)
                self._post_model(lambda: self._model_downloaded(settings))
            except Exception as exc:
                self._post_model(lambda message=str(exc): self._model_download_failed(message))
        threading.Thread(target=run, daemon=True).start()

    def _post_model(self, callback):
        if not getattr(self, "_closing", False):
            try:
                self.root.after(0, lambda: callback() if not getattr(self, "_closing", False) else None)
            except (RuntimeError, tk.TclError):
                pass

    def _model_downloaded(self, settings):
        self._set_download_busy(False)
        try:
            values = models.save_settings(core.data_dir(), settings)
        except (OSError, ValueError) as exc:
            self.download_status.configure(text=f"Model installed, but settings were not saved: {exc}")
            return
        self.cfg = dict(self.cfg, **values)
        self._update_model_status()
        self.model_settings_status.configure(text="Download verified. Model selected for the next claw.")
        self._refresh_health()

    def _model_download_failed(self, message):
        self._set_download_busy(False)
        self.download_status.configure(text=f"Download failed: {message}")

    def _refresh_model_hardware(self):
        self._hardware_scan_started = True
        self.refresh_hardware_button.configure(state="disabled")
        def run():
            try:
                hw = models.detect_hardware(core.data_dir())
                with core._INFERENCE_LOCK, core._MODEL_LOCK:
                    runtime = models.runtime_capabilities()
                self._post_model(lambda: self._model_hardware_ready(hw, runtime))
            except Exception as exc:
                self._post_model(lambda message=str(exc): self._model_hardware_failed(message))
        threading.Thread(target=run, daemon=True).start()

    def _model_hardware_failed(self, message):
        self._hardware_scan_started = False
        self.refresh_hardware_button.configure(state="normal")
        self.model_hardware_label.configure(text=f"Hardware detection unavailable: {message}. You can retry Refresh hardware.")

    def _model_hardware_ready(self, hw, runtime):
        self._model_hw, self._model_runtime = hw, runtime
        self.refresh_hardware_button.configure(state="normal")
        self.model_hardware_label.configure(text=models.hardware_summary(hw, runtime))
        self._update_model_guidance()

    def _update_model_guidance(self):
        if not self._model_hw:
            return
        try:
            values = {key: var.get().strip() for key, var in self.model_fields.items()}
            values["model_acceleration"] = self.acceleration_modes[self.acceleration.get()]
            values = models.inference_settings(values)
            custom_bytes = None
            if self._selected_model_id() == "custom":
                path = core.Path(self.custom_model_path.get()).expanduser()
                if path.is_file():
                    custom_bytes = path.stat().st_size
            text = models.model_guidance(self._selected_model_id(), self._model_hw, self._model_runtime, values, custom_bytes)
        except (ValueError, OSError) as exc:
            text = str(exc)
        self.model_guidance_label.configure(text=text)
