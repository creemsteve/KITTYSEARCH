"""Native Tk desktop interface for KittySearch."""
from __future__ import annotations

import threading
import tkinter as tk
import urllib.parse
import webbrowser
from tkinter import messagebox, ttk
from typing import Any

import kittysearch as core


class KittySearchWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = core.load_config()
        self.results: list[dict[str, Any]] = []
        self.root.title(f"{core.APP_NAME} {core.VERSION}")
        self.root.geometry("1040x760")
        self.root.minsize(760, 560)
        self._style()
        self._build()
        self._start_managed_service()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(150, self._refresh_health)

    def _style(self) -> None:
        style = ttk.Style(self.root)
        for theme in ("vista", "xpnative", "clam"):
            try:
                style.theme_use(theme)
                break
            except tk.TclError:
                continue
        style.configure("Title.TLabel", font=("Segoe UI", 21, "bold"))
        style.configure("Hint.TLabel", foreground="#5c6670")
        style.configure("Treeview", rowheight=27)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def _build(self) -> None:
        shell = ttk.Frame(self.root, padding=(18, 14))
        shell.pack(fill="both", expand=True)
        header = ttk.Frame(shell)
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text="KittySearch", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="Local search", style="Hint.TLabel").pack(side="left", padx=14, pady=(9, 0))
        self.tabs = ttk.Notebook(shell)
        self.tabs.pack(fill="both", expand=True)
        self.search_tab = ttk.Frame(self.tabs, padding=14)
        self.settings_tab = ttk.Frame(self.tabs, padding=14)
        self.tabs.add(self.search_tab, text="Search")
        self.tabs.add(self.settings_tab, text="Settings")
        self._build_search()
        self._build_settings()
        self.footer = ttk.Label(shell, text=f"Data and settings: {core.data_dir()}", style="Hint.TLabel", anchor="w")
        self.footer.pack(fill="x", pady=(10, 0))

    def _build_search(self) -> None:
        f = self.search_tab
        ttk.Label(f, text="Search with receipts.", style="Title.TLabel").pack(anchor="w")
        ttk.Label(f, text="SearXNG results reviewed by your local AI model.", style="Hint.TLabel").pack(anchor="w", pady=(2, 12))
        row = ttk.Frame(f)
        row.pack(fill="x")
        self.query = tk.StringVar()
        self.query_entry = ttk.Entry(row, textvariable=self.query)
        self.query_entry.pack(side="left", fill="x", expand=True, ipady=5)
        self.query_entry.bind("<Return>", lambda _e: self._search())
        self.search_button = ttk.Button(row, text="Search", command=self._search)
        self.search_button.pack(side="left", padx=(8, 0))
        controls = ttk.Frame(f)
        controls.pack(fill="x", pady=9)
        self.hide_ai = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls, text="Hide likely AI-generated results", variable=self.hide_ai, command=self._render_results).pack(side="left")
        self.health = ttk.Label(controls, text="Checking local services…", style="Hint.TLabel")
        self.health.pack(side="right")
        self.search_status = ttk.Label(f, text="", style="Hint.TLabel", anchor="w")
        self.search_status.pack(fill="x", pady=(0, 6))
        body = ttk.Panedwindow(f, orient="vertical")
        body.pack(fill="both", expand=True)
        listing = ttk.Frame(body)
        cols = ("score", "relevance", "title", "source")
        self.result_tree = ttk.Treeview(listing, columns=cols, show="headings", selectmode="browse")
        for col, title, width in (("score", "Quality", 76), ("relevance", "Relevance", 84), ("title", "Result", 450), ("source", "Source", 240)):
            self.result_tree.heading(col, text=title)
            self.result_tree.column(col, width=width, minwidth=55, stretch=col in ("title", "source"))
        yscroll = ttk.Scrollbar(listing, orient="vertical", command=self.result_tree.yview)
        self.result_tree.configure(yscrollcommand=yscroll.set)
        self.result_tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        self.result_tree.bind("<<TreeviewSelect>>", self._show_result)
        details = ttk.Frame(body)
        self.result_detail = tk.Text(details, height=8, wrap="word", state="disabled", font=("Segoe UI", 10))
        self.result_detail.pack(fill="both", expand=True)
        actions = ttk.Frame(details)
        actions.pack(fill="x", pady=(5, 0))
        self.open_result_button = ttk.Button(actions, text="Open selected source", command=self._open_result, state="disabled")
        self.open_result_button.pack(side="left")
        body.add(listing, weight=3)
        body.add(details, weight=1)
        ttk.Label(f, text="AI flags are estimates, not proof of authorship.", style="Hint.TLabel").pack(anchor="w", pady=(7, 0))

    def _build_settings(self) -> None:
        f = self.settings_tab
        ttk.Label(f, text="Connection settings", style="Title.TLabel").pack(anchor="w", pady=(0, 12))
        self.mode = tk.StringVar(value=self.cfg.get("searxng_mode", "external"))
        self.searx_url = tk.StringVar(value=self.cfg["searxng_url"])
        self.ollama_url = tk.StringVar(value=self.cfg["ollama_url"])
        self.model = tk.StringVar(value=self.cfg.get("model", ""))
        self.result_count = tk.StringVar(value=str(self.cfg.get("results", 20)))
        self.timeout = tk.StringVar(value=str(self.cfg.get("timeout", 20)))
        fields = (("SearXNG mode", self.mode, ("external", "windows", "wsl", "docker")),
                  ("SearXNG URL", self.searx_url, None), ("Ollama URL", self.ollama_url, None),
                  ("Ollama model (optional)", self.model, None), ("Results (1–50)", self.result_count, None),
                  ("Timeout in seconds (1–120)", self.timeout, None))
        for label, var, values in fields:
            ttk.Label(f, text=label).pack(anchor="w", pady=(7, 3))
            if values:
                ttk.Combobox(f, textvariable=var, values=values, state="readonly", width=38).pack(anchor="w", fill="x")
            else:
                ttk.Entry(f, textvariable=var, width=42).pack(anchor="w", fill="x")
        ttk.Button(f, text="Save settings", command=self._save_settings).pack(anchor="w", pady=14)
        self.settings_status = ttk.Label(f, text="", style="Hint.TLabel", wraplength=700)
        self.settings_status.pack(anchor="w")
        ttk.Label(f, text="SearXNG automatic modes: Windows (bundled or locally installed), WSL2, or Docker.", style="Hint.TLabel", wraplength=700).pack(anchor="w", pady=(12, 0))

    def _start_managed_service(self) -> None:
        mode = self.cfg.get("searxng_mode", "external")
        if mode == "external":
            return
        def run() -> None:
            try:
                {"windows": core.start_windows_searxng, "wsl": core.start_wsl_searxng, "docker": core.start_managed_searxng}[mode](self.cfg)
                self.root.after(0, lambda: self._set_health("SearXNG started."))
            except Exception as exc:
                self.root.after(0, lambda message=str(exc): self._set_health(f"SearXNG startup failed: {message}"))
        threading.Thread(target=run, daemon=True).start()

    def _save_settings(self) -> None:
        try:
            cfg = self.cfg.copy()
            cfg.update({"searxng_mode": self.mode.get(), "searxng_url": self.searx_url.get().strip().rstrip("/"),
                        "ollama_url": self.ollama_url.get().strip().rstrip("/"), "model": self.model.get().strip(),
                        "results": int(self.result_count.get()), "timeout": int(self.timeout.get())})
            for key in ("searxng_url", "ollama_url"):
                from urllib.parse import urlparse
                parsed = urlparse(cfg[key])
                if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError(f"Enter a valid {key.replace('_', ' ')} using http:// or https://.")
            if not 1 <= cfg["results"] <= 50:
                raise ValueError("Results must be between 1 and 50.")
            if not 1 <= cfg["timeout"] <= 120:
                raise ValueError("Timeout must be between 1 and 120.")
            if core.MANAGED_SEARXNG:
                core.stop_managed_searxng()
            mode = cfg["searxng_mode"]
            if mode != "external":
                {"windows": core.start_windows_searxng, "wsl": core.start_wsl_searxng, "docker": core.start_managed_searxng}[mode](cfg)
            core.save_config(cfg)
            self.cfg = cfg
            self.settings_status.configure(text="Settings saved. Managed SearXNG is running." if mode != "external" else "Settings saved.")
            self._refresh_health()
        except Exception as exc:
            messagebox.showerror("Settings not saved", str(exc), parent=self.root)

    def _search(self) -> None:
        query = self.query.get().strip()
        if not query:
            self.search_status.configure(text="Enter a search query.")
            return
        self.search_button.configure(state="disabled")
        self.search_status.configure(text="Searching and reviewing sources locally…")
        def run() -> None:
            try:
                result = core.search(query, self.cfg)
                self.root.after(0, lambda: self._search_done(result, None))
            except Exception as exc:
                self.root.after(0, lambda message=str(exc): self._search_done(None, message))
        threading.Thread(target=run, daemon=True).start()

    def _search_done(self, data: dict[str, Any] | None, error: str | None) -> None:
        self.search_button.configure(state="normal")
        if error:
            self.search_status.configure(text=error)
            return
        self.results = data["results"]
        model_note = f"Reviewed by {data['model']}" if data["analyzed"] else "Lexical ranking only"
        self.search_status.configure(text=f"{len(self.results)} results · {model_note}" + (f" · local model unavailable: {data['model_error']}" if data["model_error"] else ""))
        self._render_results()

    def _render_results(self) -> None:
        self.result_tree.delete(*self.result_tree.get_children())
        self.visible_results: dict[str, dict[str, Any]] = {}
        for index, item in enumerate(self.results):
            if self.hide_ai.get() and item.get("kitty_ai_generated"):
                continue
            iid = str(index)
            self.visible_results[iid] = item
            host = urllib.parse.urlparse(item.get("url", "")).hostname or ""
            flag = " · Likely generated" if item.get("kitty_ai_generated") else ""
            self.result_tree.insert("", "end", iid=iid, values=(f"{item.get('kitty_score', 0)}/100", f"{item.get('kitty_relevance', 0)}/100", (item.get("title") or item.get("url", "")) + flag, host))

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

    def _open_result(self) -> None:
        selected = self.result_tree.selection()
        if selected:
            webbrowser.open(self.visible_results[selected[0]].get("url", ""))

    def _refresh_health(self) -> None:
        def run() -> None:
            searx = ollama = False
            try: core.http_json(self.cfg["searxng_url"] + "/config", timeout=2); searx = True
            except Exception: pass
            try: core.http_json(self.cfg["ollama_url"] + "/api/tags", timeout=2); ollama = True
            except Exception: pass
            self.root.after(0, lambda: self._set_health(f"SearXNG {'ready' if searx else 'unavailable'} · Ollama {'ready' if ollama else 'unavailable'}"))
        threading.Thread(target=run, daemon=True).start()

    def _set_health(self, text: str) -> None:
        self.health.configure(text=text)

    def _close(self) -> None:
        try:
            core.stop_managed_searxng()
        except Exception as exc:
            messagebox.showwarning("SearXNG shutdown", str(exc), parent=self.root)
        self.root.destroy()


def run_desktop() -> None:
    root = tk.Tk()
    KittySearchWindow(root)
    root.mainloop()
