"""Carbon Gray 100 styling and process-local bundled IBM Plex fonts."""
from __future__ import annotations

import ctypes
import ctypes.util
import os
from pathlib import Path
import sys
import tkinter as tk
from tkinter import font, ttk


COLORS = {
    "background": "#161616", "layer": "#262626", "field": "#393939",
    "hover": "#474747", "border": "#525252", "text": "#f4f4f4",
    "secondary": "#c6c6c6", "disabled": "#8d8d8d", "blue": "#0f62fe",
    "blue_hover": "#0353e9", "blue_pressed": "#002d9c", "link": "#78a9ff",
    "selection": "#0043ce", "focus": "#ffffff",
}
FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
_fonts_loaded = False


def load_fonts() -> None:
    """Register fonts before Tk initializes; never install fonts system-wide.

    PyInstaller places this module and assets together in its extraction folder.
    Windows registration lasts for this process; Fontconfig is also process-local.
    """
    global _fonts_loaded
    if _fonts_loaded:
        return
    paths = [FONT_DIR / f"IBMPlexSans-{weight}.ttf"
             for weight in ("Regular", "SemiBold", "Italic")]
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"Bundled IBM Plex font missing: {path}")
    if sys.platform == "win32":
        add_font = ctypes.WinDLL("gdi32").AddFontResourceExW
        add_font.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
        add_font.restype = ctypes.c_int
        for path in paths:
            if not add_font(str(path), 0x10, None):  # FR_PRIVATE
                raise RuntimeError(f"Could not load IBM Plex font: {path}")
    elif sys.platform.startswith("linux"):
        fc = ctypes.CDLL(ctypes.util.find_library("fontconfig") or "libfontconfig.so.1")
        fc.FcConfigGetCurrent.restype = ctypes.c_void_p
        fc.FcConfigAppFontAddFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        fc.FcConfigAppFontAddFile.restype = ctypes.c_int
        config = fc.FcConfigGetCurrent()
        for path in paths:
            if not fc.FcConfigAppFontAddFile(config, os.fsencode(path)):
                raise RuntimeError(f"Could not load IBM Plex font: {path}")
    _fonts_loaded = True


def apply_theme(root: tk.Tk) -> None:
    c = COLORS
    families = font.families(root)
    semibold = next((name for name in ("IBM Plex Sans SmBld", "IBM Plex Sans SemiBold")
                     if name in families), "IBM Plex Sans")
    root.configure(background=c["background"])
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont",
                 "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont"):
        font.nametofont(name, root=root).configure(family="IBM Plex Sans", size=10)
    style = ttk.Style(root)
    # Native Windows themes ignore background colors on several controls.
    style.theme_use("clam")
    style.configure(".", background=c["background"], foreground=c["text"],
                    font="TkDefaultFont", bordercolor=c["border"],
                    lightcolor=c["border"], darkcolor=c["border"],
                    troughcolor=c["background"], focuscolor=c["focus"])
    style.configure("TFrame", background=c["background"])
    style.configure("TLabel", background=c["background"])
    style.configure("Title.TLabel", font=("IBM Plex Sans", 22))
    style.configure("Brand.TLabel", font=(semibold, 14))
    style.configure("Section.TLabel", font=(semibold, 10))
    style.configure("Hint.TLabel", foreground=c["secondary"])
    style.configure("TSeparator", background=c["field"])
    style.configure("TNotebook", borderwidth=0, tabmargins=0,
                    bordercolor=c["background"], lightcolor=c["background"], darkcolor=c["background"])
    style.configure("TNotebook.Tab", padding=(24, 12), background=c["layer"],
                    foreground=c["secondary"], borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", c["field"]), ("active", c["hover"])],
              padding=[("selected", (24, 12))],
              foreground=[("selected", c["text"])],
              lightcolor=[("selected", c["link"])], darkcolor=[("selected", c["link"])])
    style.configure("TButton", background=c["field"], foreground=c["text"],
                    padding=(16, 11), borderwidth=1, relief="flat", anchor="w")
    style.map("TButton", background=[("disabled", c["layer"]), ("pressed", c["border"]),
                                     ("active", c["hover"])],
              foreground=[("disabled", c["disabled"])],
              bordercolor=[("focus", c["focus"])])
    style.configure("Primary.TButton", background=c["blue"], bordercolor=c["blue"],
                    lightcolor=c["blue"], darkcolor=c["blue"])
    style.map("Primary.TButton", background=[("disabled", c["field"]),
              ("pressed", c["blue_pressed"]), ("active", c["blue_hover"])],
              bordercolor=[("focus", c["focus"]), ("disabled", c["field"]),
                           ("!disabled", c["blue"])])
    style.configure("TEntry", fieldbackground=c["field"], foreground=c["text"],
                    insertcolor=c["text"], padding=(12, 10), borderwidth=1,
                    selectbackground=c["selection"], selectforeground=c["text"])
    style.map("TEntry", bordercolor=[("focus", c["focus"])],
              lightcolor=[("focus", c["focus"])], darkcolor=[("focus", c["focus"])],
              fieldbackground=[("disabled", c["layer"])])
    style.configure("TCombobox", fieldbackground=c["field"], background=c["field"],
                    foreground=c["text"], arrowcolor=c["text"], padding=(12, 10),
                    selectbackground=c["selection"], selectforeground=c["text"])
    style.map("TCombobox", fieldbackground=[("readonly", c["field"]), ("disabled", c["layer"])],
              foreground=[("disabled", c["disabled"]), ("readonly", c["text"])],
              bordercolor=[("focus", c["focus"])])
    root.option_add("*TCombobox*Listbox.background", c["field"])
    root.option_add("*TCombobox*Listbox.foreground", c["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", c["selection"])
    root.option_add("*TCombobox*Listbox.selectForeground", c["text"])
    style.configure("TCheckbutton", padding=(0, 6), indicatorbackground=c["background"],
                    indicatorforeground=c["background"], indicatormargin=(0, 0, 8, 0))
    style.map("TCheckbutton", background=[("active", c["background"])],
              foreground=[("disabled", c["disabled"])],
              indicatorbackground=[("selected", c["text"]), ("active", c["field"])])
    style.configure("Treeview", background=c["layer"], fieldbackground=c["layer"],
                    foreground=c["text"], rowheight=40, borderwidth=0,
                    bordercolor=c["layer"], lightcolor=c["layer"], darkcolor=c["layer"])
    style.map("Treeview", background=[("selected", c["selection"])],
              foreground=[("selected", c["text"])])
    style.configure("Treeview.Heading", background=c["field"], foreground=c["text"],
                    font=(semibold, 10), padding=(12, 10), relief="flat")
    style.map("Treeview.Heading", background=[("active", c["hover"])])
    style.configure("TScrollbar", background=c["border"], arrowcolor=c["secondary"],
                    borderwidth=0, arrowsize=14, troughcolor=c["layer"])
    style.map("TScrollbar", background=[("active", c["disabled"]), ("pressed", c["secondary"])])
    style.configure("TPanedwindow", background=c["background"])
    style.configure("Sash", sashthickness=8, gripcount=0)
    if sys.platform == "win32":
        # Match the native title bar on Windows 10/11 (older systems ignore this).
        root.update_idletasks()
        try:
            user32 = ctypes.WinDLL("user32")
            user32.GetParent.argtypes = [ctypes.c_void_p]
            user32.GetParent.restype = ctypes.c_void_p
            hwnd = user32.GetParent(root.winfo_id())
            dwm = ctypes.WinDLL("dwmapi").DwmSetWindowAttribute
            dwm.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
            enabled = ctypes.c_int(1)
            dwm(hwnd, 20, ctypes.byref(enabled), ctypes.sizeof(enabled))
        except (OSError, AttributeError):
            pass
