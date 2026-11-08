"""Native Tk desktop interface for KITTYSEARCH."""
from __future__ import annotations

import threading
import tkinter as tk
import urllib.parse
import webbrowser
from tkinter import messagebox, ttk
from typing import Any

import kittysearch as core
from kittysearch_theme import COLORS, apply_theme, load_fonts
from kittysearch_model_settings import ModelSettingsMixin


class KittySearchWindow(ModelSettingsMixin):
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = core.automatic_config()
        self._service_lock = threading.Lock()
        self._service_busy = False
        self._closing = False
        self.results: list[dict[str, Any]] = []
        self.root.title(f"{core.APP_NAME} {core.VERSION}")
        self.root.geometry("1120x820")
        self.root.minsize(820, 640)
        self._style()
        self._build()
        self._start_managed_service()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(150, self._refresh_health)

    def _style(self) -> None:
        apply_theme(self.root)

    def _build(self) -> None:
        shell = ttk.Frame(self.root, padding=(24, 16))
        shell.pack(fill="both", expand=True)
        header = ttk.Frame(shell)
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text="KITTYSEARCH", style="Brand.TLabel").pack(side="left")
        ttk.Label(header, text="Local clawing", style="Hint.TLabel").pack(side="left", padx=24)
        ttk.Separator(shell).pack(fill="x", pady=(0, 16))
        self.footer = ttk.Label(shell, text=f"Data and settings: {core.data_dir()}", style="Hint.TLabel", anchor="w")
        self.footer.pack(side="bottom", fill="x", pady=(10, 0))
        self.tabs = ttk.Notebook(shell)
        self.tabs.pack(fill="both", expand=True)
        self.search_tab = ttk.Frame(self.tabs, padding=(16, 24))
        self.settings_tab = ttk.Frame(self.tabs, padding=(16, 24))
        self.searxng_tab = ttk.Frame(self.tabs, padding=16)
        self.learning_tab = ttk.Frame(self.tabs, padding=(16, 24))
        self.tabs.add(self.search_tab, text="Claw")
        self.tabs.add(self.learning_tab, text="Pawprints")
        self.tabs.add(self.settings_tab, text="Settings")
        self.tabs.add(self.searxng_tab, text="SearXNG settings")
        self._build_search()
        self._build_learning()
        self._build_settings()
        self._build_searxng_settings()

    def _build_search(self) -> None:
        f = self.search_tab
        ttk.Label(f, text="Claw up some answers.", style="Title.TLabel").pack(anchor="w")
        ttk.Label(f, text="Sniff out pages with SearXNG, then let your local AI model review them.", style="Hint.TLabel").pack(anchor="w", pady=(2, 12))
        row = ttk.Frame(f)
        row.pack(fill="x")
        self.query = tk.StringVar()
        self.query_entry = ttk.Entry(row, textvariable=self.query)
        self.query_entry.pack(side="left", fill="x", expand=True)
        self.query_entry.bind("<Return>", lambda _e: self._search())
        self.search_button = ttk.Button(row, text="Claw!", command=self._search, style="Primary.TButton", width=12)
        self.search_button.pack(side="left")
        controls = ttk.Frame(f)
        controls.pack(fill="x", pady=9)
        self.hide_ai = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls, text="Hide likely AI-generated results", variable=self.hide_ai, command=self._render_results).pack(side="left")
        self.health = ttk.Label(controls, text="Checking local services…", style="Hint.TLabel")
        self.health.pack(side="right")
        self.search_status = ttk.Label(f, text="", style="Hint.TLabel", anchor="w")
        self.search_status.pack(fill="x", pady=(0, 6))
        ttk.Label(f, text="AI flags are estimates, not proof of authorship.", style="Hint.TLabel").pack(side="bottom", anchor="w", pady=(7, 0))
        body = ttk.Panedwindow(f, orient="vertical")
        body.pack(fill="both", expand=True)
        listing = ttk.Frame(body)
        cols = ("score", "relevance", "title", "source")
        self.result_tree = ttk.Treeview(listing, columns=cols, show="headings", selectmode="browse", height=4)
        self.result_tree.tag_configure("alternate", background=COLORS["background"])
        for col, title, width in (("score", "Quality", 90), ("relevance", "Relevance", 110), ("title", "Result", 450), ("source", "Source", 220)):
            self.result_tree.heading(col, text=title)
            self.result_tree.heading(col, anchor="w")
            self.result_tree.column(col, width=width, minwidth=55, stretch=col in ("title", "source"))
        yscroll = ttk.Scrollbar(listing, orient="vertical", command=self.result_tree.yview)
        self.result_tree.configure(yscrollcommand=yscroll.set)
        self.result_tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        self.result_tree.bind("<<TreeviewSelect>>", self._show_result)
        details = ttk.Frame(body)
        ttk.Label(details, text="Catch details", style="Section.TLabel").pack(anchor="w", pady=(8, 8))
        self.result_detail = tk.Text(details, height=5, wrap="word", state="disabled",
                                     font=("IBM Plex Sans", 10), background=COLORS["layer"],
                                     foreground=COLORS["text"], insertbackground=COLORS["text"],
                                     selectbackground=COLORS["selection"], selectforeground=COLORS["text"],
                                     relief="flat", borderwidth=0, padx=16, pady=12,
                                     highlightthickness=1, highlightbackground=COLORS["border"],
                                     highlightcolor=COLORS["focus"])
        self.result_detail.pack(fill="both", expand=True)
        actions = ttk.Frame(details)
        actions.pack(fill="x", pady=(5, 0))
        self.open_result_button = ttk.Button(actions, text="Open selected page", command=self._open_result, state="disabled")
        self.open_result_button.pack(side="left")
        self.page_flag_button = ttk.Button(actions, text="Flag page as AI", command=lambda: self._flag_result("page"), state="disabled")
        self.page_flag_button.pack(side="left", padx=(8, 0))
        self.website_flag_button = ttk.Button(actions, text="Flag website as AI", command=lambda: self._flag_result("website"), state="disabled")
        self.website_flag_button.pack(side="left", padx=(8, 0))
        body.add(listing, weight=3)
        body.add(details, weight=1)

    def _build_learning(self) -> None:
        f = self.learning_tab
        ttk.Label(f, text="Your saved pawprints", style="Title.TLabel").pack(anchor="w")
        ttk.Label(f, text="Saved flags lower page rankings and follow the Hide AI option on every new claw. "
                  "They stay on this device; the model is not retrained. Website flags cover the exact host, "
                  "across all pages, but not other subdomains.", style="Hint.TLabel", wraplength=700).pack(anchor="w", pady=(8, 16))
        ttk.Label(f, text="Flag a page or website by URL", style="Section.TLabel").pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(8, 12))
        self.feedback_url = tk.StringVar()
        ttk.Entry(row, textvariable=self.feedback_url).pack(side="left", fill="x", expand=True)
        self.feedback_scope = tk.StringVar(value="page")
        ttk.Combobox(row, textvariable=self.feedback_scope, values=("page", "website"), state="readonly", width=10).pack(side="left", padx=8)
        ttk.Button(row, text="Flag as AI-generated", command=self._add_feedback).pack(side="left")
        self.learning_status = ttk.Label(f, text="", style="Hint.TLabel", wraplength=700)
        self.learning_status.pack(anchor="w", pady=(0, 8))
        listing = ttk.Frame(f)
        listing.pack(fill="both", expand=True)
        self.feedback_tree = ttk.Treeview(listing, columns=("scope", "target"), show="headings", selectmode="browse")
        self.feedback_tree.heading("scope", text="Scope", anchor="w")
        self.feedback_tree.heading("target", text="Flagged page or website", anchor="w")
        self.feedback_tree.column("scope", width=100, stretch=False)
        self.feedback_tree.column("target", width=550)
        scroll = ttk.Scrollbar(listing, orient="vertical", command=self.feedback_tree.yview)
        self.feedback_tree.configure(yscrollcommand=scroll.set)
        self.feedback_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        actions = ttk.Frame(f)
        actions.pack(fill="x", pady=(10, 0))
        self.remove_flag_button = ttk.Button(actions, text="Remove selected flag", state="disabled", command=self._remove_feedback)
        self.remove_flag_button.pack(side="left")
        self.feedback_tree.bind("<<TreeviewSelect>>", lambda _e: self.remove_flag_button.configure(state="normal" if self.feedback_tree.selection() else "disabled"))
        ttk.Button(actions, text="Refresh", command=self._refresh_learning).pack(side="left", padx=8)
        self._refresh_learning()

    def _refresh_learning(self) -> bool:
        try:
            flags = core.load_feedback()
        except (OSError, core.sqlite3.Error) as exc:
            self.learning_status.configure(text=f"Could not load saved flags: {exc}")
            return False
        self.feedback_tree.delete(*self.feedback_tree.get_children())
        self.remove_flag_button.configure(state="disabled")
        for scope in ("page", "website"):
            for target in sorted(flags[scope]):
                self.feedback_tree.insert("", "end", values=(scope, target))
        count = sum(len(entries) for entries in flags.values())
        self.learning_status.configure(text=f"{count} saved AI flag{'s' if count != 1 else ''} · Changes apply immediately and on future claws.")
        core.apply_feedback(self.results, flags)
        self._render_results()
        return True

    def _add_feedback(self) -> None:
        try:
            core.set_feedback(self.feedback_url.get(), self.feedback_scope.get())
        except (ValueError, OSError, core.sqlite3.Error) as exc:
            messagebox.showerror("Could not save flag", str(exc), parent=self.root)
            return
        self.feedback_url.set("")
        self._refresh_learning()

    def _remove_feedback(self) -> None:
        selection = self.feedback_tree.selection()
        if not selection:
            return
        scope, target = self.feedback_tree.item(selection[0], "values")
        try:
            core.remove_feedback(scope, target)
        except (OSError, core.sqlite3.Error) as exc:
            messagebox.showerror("Could not remove flag", str(exc), parent=self.root)
            return
        self._refresh_learning()

    def _flag_result(self, scope: str) -> None:
        selection = self.result_tree.selection()
        if not selection:
            return
        item = self.visible_results[selection[0]]
        try:
            target = core.feedback_target(item.get("url", ""), scope)
            if scope in item.get("kitty_user_flags", []):
                core.remove_feedback(scope, target)
            else:
                core.set_feedback(item.get("url", ""), scope)
        except (ValueError, OSError, core.sqlite3.Error) as exc:
            messagebox.showerror("Could not update flag", str(exc), parent=self.root)
            return
        self._refresh_learning()

    def _build_searxng_settings(self) -> None:
        outer = self.searxng_tab
        ttk.Label(outer, text="SearXNG settings", style="Title.TLabel").pack(anchor="w", pady=(0, 12))
        self.searxng_status = ttk.Label(outer, text="Changes apply when you save.", style="Hint.TLabel", wraplength=700)
        self.searxng_status.pack(side="bottom", fill="x", pady=(8, 0))
        actions = ttk.Frame(outer)
        actions.pack(side="bottom", fill="x", pady=(12, 0))
        self.save_searxng_button = ttk.Button(actions, text="Save SearXNG settings", style="Primary.TButton",
                                             command=self._save_searxng_settings)
        self.save_searxng_button.pack(side="left")
        self.check_searxng_button = ttk.Button(actions, text="Test connection", command=self._test_searxng_connection)
        self.check_searxng_button.pack(side="left", padx=(8, 0))
        self.searxng_sections = ttk.Notebook(outer)
        self.searxng_sections.pack(fill="both", expand=True)
        sections = {}
        for name in ("Connection", "Claw options", "Engines", "Sites"):
            sections[name] = ttk.Frame(self.searxng_sections, padding=12)
            self.searxng_sections.add(sections[name], text=name)

        f = sections["Connection"]
        f.columnconfigure(1, weight=1)
        self.searxng_modes = {"Existing instance": "external", "Docker": "docker"}
        if core.os.name == "nt":
            self.searxng_modes.update({"Native Windows": "windows", "WSL2": "wsl"})
        self.searxng_mode = tk.StringVar(value=next(
            label for label, mode in self.searxng_modes.items() if mode == self.cfg["searxng_mode"]))
        ttk.Label(f, text="Startup mode", style="Section.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Combobox(f, textvariable=self.searxng_mode, values=list(self.searxng_modes),
                     state="readonly", width=32).grid(row=0, column=1, sticky="ew", pady=(0, 12))
        ttk.Label(f, text="Base URL", style="Section.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12))
        self.searxng_url = tk.StringVar(value=self.cfg["searxng_url"])
        ttk.Entry(f, textvariable=self.searxng_url).grid(row=1, column=1, sticky="ew", pady=(0, 12))
        ttk.Label(f, text="Timeout (seconds)", style="Section.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 12))
        self.searxng_timeout = tk.StringVar(value=str(self.cfg["timeout"]))
        ttk.Entry(f, textvariable=self.searxng_timeout, width=12).grid(row=2, column=1, sticky="w", pady=(0, 12))
        ttk.Label(f, text="Existing instance connects without starting a server. Other modes start it when needed. "
                  "Use the base URL without /search; JSON output must be enabled. Native Windows and WSL2 use "
                  "http://127.0.0.1:8080. Timeout range: 1–300 seconds.", style="Hint.TLabel", wraplength=650
                  ).grid(row=3, column=0, columnspan=2, sticky="w")

        f = sections["Claw options"]
        f.columnconfigure(1, weight=1)
        self.searxng_language = tk.StringVar(value=self.cfg.get("language", "all"))
        ttk.Label(f, text="Language", style="Section.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Combobox(f, textvariable=self.searxng_language, values=("all", "auto", "en", "en-US", "en-GB", "es", "fr", "de", "ja", "zh", "pt-BR")
                     ).grid(row=0, column=1, sticky="ew", pady=(0, 12))
        self.searxng_safe_levels = {"Off": 0, "Moderate": 1, "Strict": 2}
        self.searxng_safesearch = tk.StringVar(value=next(
            name for name, level in self.searxng_safe_levels.items() if level == self.cfg.get("safesearch", 1)))
        ttk.Label(f, text="SafeSearch", style="Section.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12))
        ttk.Combobox(f, textvariable=self.searxng_safesearch, values=list(self.searxng_safe_levels), state="readonly"
                     ).grid(row=1, column=1, sticky="ew", pady=(0, 12))
        self.searxng_categories = tk.StringVar(value=", ".join(self.cfg.get("categories", ["general"])))
        ttk.Label(f, text="Categories", style="Section.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 12))
        ttk.Entry(f, textvariable=self.searxng_categories).grid(row=2, column=1, sticky="ew", pady=(0, 8))
        self.searxng_category_hint = ttk.Label(f, text="Separate categories with commas, e.g. general, news. Load engines to see this server's categories.",
                                              style="Hint.TLabel", wraplength=650)
        self.searxng_category_hint.grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(f, text="Language accepts codes such as en-US; all means all languages. SafeSearch works with supporting engines. "
                  "Server rules can override claw preferences. Use these controls instead of !engine or :language shortcuts in your claw.",
                  style="Hint.TLabel", wraplength=650).grid(row=4, column=0, columnspan=2, sticky="w")

        f = sections["Engines"]
        self.searxng_engines = tk.StringVar(value=", ".join(self.cfg.get("engines", [])))
        ttk.Label(f, text="Selected engines (comma-separated; blank uses server defaults)", style="Section.TLabel").pack(anchor="w")
        ttk.Entry(f, textvariable=self.searxng_engines).pack(fill="x", pady=(6, 8))
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(0, 8))
        self.load_engines_button = ttk.Button(row, text="Load engines", command=self._load_searxng_engines)
        self.load_engines_button.pack(side="left")
        ttk.Button(row, text="Use selected", command=self._use_selected_searxng_engines).pack(side="left", padx=8)
        ttk.Button(row, text="Use server defaults", command=lambda: self.searxng_engines.set("")).pack(side="left")
        ttk.Label(f, text="Hold Ctrl to select several engines. Categories limit which chosen engines run.",
                  style="Hint.TLabel", wraplength=650).pack(anchor="w", pady=(0, 6))
        listing = ttk.Frame(f)
        listing.pack(fill="both", expand=True)
        self.searxng_engine_tree = ttk.Treeview(listing, columns=("name", "categories", "default"), show="headings", selectmode="extended", height=3)
        for column, title, width in (("name", "Engine", 190), ("categories", "Categories", 250), ("default", "Server default", 130)):
            self.searxng_engine_tree.heading(column, text=title, anchor="w")
            self.searxng_engine_tree.column(column, width=width, minwidth=90)
        scrollbar = ttk.Scrollbar(listing, orient="vertical", command=self.searxng_engine_tree.yview)
        self.searxng_engine_tree.configure(yscrollcommand=scrollbar.set)
        self.searxng_engine_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._engine_catalog_url = None

        f = sections["Sites"]
        ttk.Label(f, text="Allowed domains (blank allows all)", style="Section.TLabel").pack(anchor="w")
        self.searxng_allowed_domains = tk.StringVar(value=", ".join(self.cfg.get("allowed_domains", [])))
        ttk.Entry(f, textvariable=self.searxng_allowed_domains).pack(fill="x", pady=(6, 12))
        ttk.Label(f, text="Blocked domains", style="Section.TLabel").pack(anchor="w")
        self.searxng_blocked_domains = tk.StringVar(value=", ".join(self.cfg.get("blocked_domains", [])))
        ttk.Entry(f, textvariable=self.searxng_blocked_domains).pack(fill="x", pady=(6, 12))
        ttk.Label(f, text="Enter domains separated by commas, e.g. example.org, example.net. Domains include their subdomains. "
                  "Blocked domains take precedence. These lists filter results before AI review; they do not prevent SearXNG from "
                  "contacting those sites. Network access restrictions require server or firewall configuration.",
                  style="Hint.TLabel", wraplength=650).pack(anchor="w")

    def _searxng_form_settings(self) -> dict[str, Any]:
        return core.validate_searxng_settings({
            "searxng_mode": self.searxng_modes.get(self.searxng_mode.get()),
            "searxng_url": self.searxng_url.get(), "timeout": self.searxng_timeout.get().strip(),
            "engines": self.searxng_engines.get(), "categories": self.searxng_categories.get(),
            "language": self.searxng_language.get(), "safesearch": self.searxng_safe_levels.get(self.searxng_safesearch.get()),
            "allowed_domains": self.searxng_allowed_domains.get(), "blocked_domains": self.searxng_blocked_domains.get()})

    def _load_searxng_engines(self) -> None:
        try:
            settings = self._searxng_form_settings()
        except ValueError as exc:
            self.searxng_status.configure(text=str(exc))
            return
        url = settings["searxng_url"]
        self.load_engines_button.configure(state="disabled")
        self.searxng_status.configure(text="Sniffing out engines and categories…")
        def run() -> None:
            catalog, error = None, None
            try:
                catalog = core.searxng.server_options(core.http_json(url + "/config", timeout=settings["timeout"]))
            except Exception as exc:
                error = str(exc)
            self.root.after(0, lambda: self._searxng_engines_loaded(url, catalog, error))
        threading.Thread(target=run, daemon=True).start()

    def _searxng_engines_loaded(self, url: str, catalog: dict[str, Any] | None, error: str | None) -> None:
        if self._closing:
            return
        self.load_engines_button.configure(state="normal")
        if url != self.searxng_url.get().strip().rstrip("/"):
            self.searxng_status.configure(text="Server URL changed. Load engines again for the new server.")
            return
        if error:
            self.searxng_status.configure(text=f"Could not load engines: {error}")
            return
        self._engine_catalog_url = url
        self.searxng_engine_tree.delete(*self.searxng_engine_tree.get_children())
        selected = core.searxng.names(self.searxng_engines.get(), "Engines")
        for engine in sorted(catalog["engines"].values(), key=lambda item: item["name"]):
            iid = self.searxng_engine_tree.insert("", "end", values=(engine["name"], ", ".join(engine["categories"]), "On" if engine["enabled"] else "Off"))
            if engine["name"] in selected:
                self.searxng_engine_tree.selection_add(iid)
        self.searxng_category_hint.configure(text="Available categories: " + ", ".join(catalog["categories"]))
        self.searxng_status.configure(text=f"Found {len(catalog['engines'])} engines. Select engines and click Use selected, then save.")

    def _use_selected_searxng_engines(self) -> None:
        if self._engine_catalog_url != self.searxng_url.get().strip().rstrip("/"):
            self.searxng_status.configure(text="Load engines for the current server first.")
            return
        selected = self.searxng_engine_tree.selection()
        if not selected:
            self.searxng_status.configure(text="Select at least one engine, or choose Use server defaults.")
            return
        self.searxng_engines.set(", ".join(self.searxng_engine_tree.item(iid, "values")[0] for iid in selected))
        self.searxng_status.configure(text="Engine selection updated. Save to apply.")

    def _save_searxng_settings(self) -> None:
        if self._service_busy:
            return
        try:
            settings = core.save_searxng_settings(self._searxng_form_settings())
        except (ValueError, OSError) as exc:
            self.searxng_status.configure(text=f"Settings were not saved: {exc}")
            return
        restart = any(settings[key] != self.cfg[key] for key in ("searxng_mode", "searxng_url"))
        self.cfg = dict(self.cfg, **settings)
        self.searxng_url.set(settings["searxng_url"])
        self.searxng_timeout.set(str(settings["timeout"]))
        self.searxng_engines.set(", ".join(settings["engines"]))
        self.searxng_categories.set(", ".join(settings["categories"]))
        self.searxng_language.set(settings["language"])
        self.searxng_allowed_domains.set(", ".join(settings["allowed_domains"]))
        self.searxng_blocked_domains.set(", ".join(settings["blocked_domains"]))
        self.results = core.searxng.filter_results(self.results, settings)
        self._render_results()
        self.searxng_status.configure(text="Settings saved. Applying connection…")
        self._start_managed_service(restart=restart)

    def _test_searxng_connection(self) -> None:
        try:
            settings = self._searxng_form_settings()
        except ValueError as exc:
            self.searxng_status.configure(text=str(exc))
            return
        self.check_searxng_button.configure(state="disabled")
        self.searxng_status.configure(text="Testing connection…")
        def run() -> None:
            try:
                core.http_json(settings["searxng_url"] + "/config", timeout=settings["timeout"])
                message = f"Connected to {settings['searxng_url']}."
            except Exception as exc:
                message = f"Connection failed: {exc}"
            self.root.after(0, lambda: self._connection_test_done(message))
        threading.Thread(target=run, daemon=True).start()

    def _connection_test_done(self, message: str) -> None:
        if not self._closing:
            self.check_searxng_button.configure(state="normal")
            self.searxng_status.configure(text=message)

    def _start_managed_service(self, *, restart: bool = False) -> None:
        cfg = self.cfg.copy()
        mode = cfg.get("searxng_mode", "external")
        self._service_busy = True
        self.save_searxng_button.configure(state="disabled")
        def run() -> None:
            error = None
            try:
                with self._service_lock:
                    if self._closing:
                        return
                    if restart:
                        core.stop_managed_searxng()
                    if mode != "external":
                        try:
                            core.http_json(cfg["searxng_url"] + "/config", timeout=2)
                        except Exception:
                            {"windows": core.start_windows_searxng, "wsl": core.start_wsl_searxng,
                             "docker": core.start_managed_searxng}[mode](cfg)
            except Exception as exc:
                error = str(exc)
            self.root.after(0, lambda: self._service_done(error))
        threading.Thread(target=run, daemon=True).start()

    def _service_done(self, error: str | None) -> None:
        self._service_busy = False
        if self._closing:
            return
        self.save_searxng_button.configure(state="normal")
        if error:
            self.searxng_status.configure(text=f"SearXNG startup failed: {error}")
            self._set_health(f"SearXNG startup failed: {error}")
        else:
            self.searxng_status.configure(text="SearXNG settings applied.")
            self._refresh_health()

    def _search(self) -> None:
        query = self.query.get().strip()
        if not query:
            self.search_status.configure(text="Enter a topic to sniff out.")
            return
        self.search_button.configure(state="disabled")
        self.search_status.configure(text="Clawing and reviewing sources locally…")
        cfg = self.cfg.copy()
        def run() -> None:
            try:
                result = core.search(query, cfg)
                self.root.after(0, lambda: self._search_done(result, None))
            except Exception as exc:
                self.root.after(0, lambda message=str(exc): self._search_done(None, message))
        threading.Thread(target=run, daemon=True).start()

    def _search_done(self, data: dict[str, Any] | None, error: str | None) -> None:
        self.search_button.configure(state="normal")
        if error:
            self.search_status.configure(text=error)
            return
        self.results = core.searxng.filter_results(data["results"], core.searxng.normalize_options(self.cfg))
        model_note = f"Reviewed by {data['model']}" if data["analyzed"] else "Lexical ranking only"
        if data.get("model_runtime"):
            model_note += f" · {data['model_runtime']}"
        if data.get("domain_filtered"):
            model_note += f" · {data['domain_filtered']} excluded by domain filters"
        self.search_status.configure(text=f"{len(self.results)} catches · {model_note}" + (f" · {data['model_error']}" if data["model_error"] else ""))
        # Reload on completion to include flags changed while inference was running.
        if not self._refresh_learning():
            self.search_status.configure(text="Claw complete, but saved AI flags could not be loaded. See Pawprints.")
            self._render_results()

    def _render_results(self) -> None:
        selection = self.result_tree.selection()
        previous = getattr(self, "visible_results", {}).get(selection[0]) if selection else None
        self.result_tree.delete(*self.result_tree.get_children())
        self.visible_results: dict[str, dict[str, Any]] = {}
        self.open_result_button.configure(state="disabled")
        self.page_flag_button.configure(state="disabled")
        self.website_flag_button.configure(state="disabled")
        self.result_detail.configure(state="normal")
        self.result_detail.delete("1.0", "end")
        self.result_detail.configure(state="disabled")
        for index, item in enumerate(self.results):
            if self.hide_ai.get() and item.get("kitty_ai_generated"):
                continue
            iid = str(index)
            self.visible_results[iid] = item
            host = urllib.parse.urlparse(item.get("url", "")).hostname or ""
            flag = " · Flagged by you" if item.get("kitty_user_flags") else " · Likely generated" if item.get("kitty_ai_generated") else ""
            self.result_tree.insert("", "end", iid=iid, tags=("alternate",) if len(self.visible_results) % 2 == 0 else (), values=(f"{item.get('kitty_score', 0)}/100", f"{item.get('kitty_relevance', 0)}/100", (item.get("title") or item.get("url", "")) + flag, host))
            if item is previous:
                self.result_tree.selection_set(iid)
                self.result_tree.see(iid)
        self._show_result()

    def _show_result(self, _event: Any = None) -> None:
        selection = self.result_tree.selection()
        if not selection:
            return
        item = self.visible_results.get(selection[0], {})
        lines = [item.get("title", ""), item.get("url", ""), "", item.get("content", "No snippet supplied."), "", f"Quality {item.get('kitty_score', 0)}/100 · Relevance {item.get('kitty_relevance', 0)}/100", ""]
        lines.extend("• " + reason for reason in item.get("kitty_reasons", []))
        if item.get("kitty_ai_reviewed"):
            lines.append(f"Local model confidence: {item.get('kitty_ai_confidence', 0)}%")
        self.result_detail.configure(state="normal")
        self.result_detail.delete("1.0", "end")
        self.result_detail.insert("1.0", "\n".join(lines))
        self.result_detail.configure(state="disabled")
        self.open_result_button.configure(state="normal")
        try:
            core.feedback_target(item.get("url", ""), "page")
            state = "normal"
        except ValueError:
            state = "disabled"
        self.page_flag_button.configure(state=state, text="Unflag page" if "page" in item.get("kitty_user_flags", []) else "Flag page as AI")
        self.website_flag_button.configure(state=state, text="Unflag website" if "website" in item.get("kitty_user_flags", []) else "Flag website as AI")

    def _open_result(self) -> None:
        selected = self.result_tree.selection()
        if selected:
            webbrowser.open(self.visible_results[selected[0]].get("url", ""))

    def _refresh_health(self) -> None:
        cfg = self.cfg.copy()
        def run() -> None:
            searx = model = False
            try: core.http_json(cfg["searxng_url"] + "/config", timeout=2); searx = True
            except Exception: pass
            path = str(cfg.get("model_path", "")).strip()
            model = bool(path and core.Path(path).expanduser().is_file())
            note = "model configured" if model else "lexical ranking"
            self.root.after(0, lambda: self._set_health(f"SearXNG {'ready' if searx else 'unavailable'} · {note}")
                            if cfg == self.cfg and not self._closing else None)
        threading.Thread(target=run, daemon=True).start()

    def _set_health(self, text: str) -> None:
        self.health.configure(text=text)

    def _close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._set_health("Stopping SearXNG…")
        self.save_searxng_button.configure(state="disabled")
        self.search_button.configure(state="disabled")
        def run() -> None:
            error = None
            try:
                with self._service_lock:
                    core.stop_managed_searxng()
            except Exception as exc:
                error = str(exc)
            self.root.after(0, lambda: self._finish_close(error))
        threading.Thread(target=run, daemon=True).start()

    def _finish_close(self, error: str | None) -> None:
        if error:
            messagebox.showwarning("SearXNG shutdown", error, parent=self.root)
        self.root.destroy()


def run_desktop() -> None:
    load_fonts()
    root = tk.Tk()
    KittySearchWindow(root)
    root.mainloop()
