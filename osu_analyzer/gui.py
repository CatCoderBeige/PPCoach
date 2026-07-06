"""Desktop GUI (CustomTkinter) for PPCoach.

Dark, minimalist design with osu! pink as the single accent color. Results are
shown as individual cards in a scrollable area (profile header with avatar + stat
cards + tip cards) instead of a single text box.
"""

import io
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path

import customtkinter as ctk
import requests

from . import theme, updater
from .config import (APP_NAME, VERSION, ConfigError, load_settings,
                     save_settings, set_last_username)
from .osu_api import OsuApiClient, OsuApiError
from .rules_engine import Finding, generate_report

try:
    from PIL import Image, ImageDraw
except ImportError:  # Pillow is optional; without it only the avatar fallback is used
    Image = None
    ImageDraw = None

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

AVATAR_SIZE = 96
CONTENT_WRAP = 600  # text wrap for full width (e.g. error card)
TIP_WRAP = 270      # text wrap in the two-column tip cards

# Static demo profile shown as a greyed-out preview on startup (no API call,
# deliberately NO real values - only placeholders, so it's clear nothing has been
# analyzed yet).
EXAMPLE_STATS = {
    "username": "Example Player",
    "country_code": "",
    "statistics": {
        "global_rank": None,
        "country_rank": None,
        "pp": None,
        "hit_accuracy": None,
        "level": {"current": None},
        "play_time": None,
    },
}
EXAMPLE_FINDINGS = [
    Finding("Where you lose PP",
            "See exactly which skills are holding your performance back.", "accuracy"),
    Finding("How to improve",
            "Get concrete, actionable tips tailored to how you play.", "strategy"),
]


def _asset_path(filename: str) -> Path:
    """Finds asset files both in dev mode and in the built .exe
    (PyInstaller unpacks datas to sys._MEIPASS at runtime)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets" / filename


def _load_round_avatar(url: str):
    """Loads the avatar image and masks it into a circle. Returns a CTkImage or None.

    Deliberately tolerant: any error (network, missing Pillow, corrupt image)
    results in None, so the analysis never fails because of an avatar.
    """
    if not url or Image is None:
        return None
    try:
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
        img = img.resize((AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)

        mask = Image.new("L", (AVATAR_SIZE, AVATAR_SIZE), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, AVATAR_SIZE, AVATAR_SIZE), fill=255)
        img.putalpha(mask)

        return ctk.CTkImage(light_image=img, dark_image=img,
                            size=(AVATAR_SIZE, AVATAR_SIZE))
    except Exception:
        return None


def _load_flag(country_code: str):
    """Loads the country flag (flagcdn) as a small CTkImage. Tolerant -> None on error."""
    if not country_code or Image is None:
        return None
    try:
        url = f"https://flagcdn.com/w40/{country_code.lower()}.png"
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
        w, h = img.size
        target_h = 15
        target_w = max(1, round(w * target_h / h))
        img = img.resize((target_w, target_h), Image.LANCZOS)
        return ctk.CTkImage(light_image=img, dark_image=img, size=(target_w, target_h))
    except Exception:
        return None


def _set_app_user_model_id(appid: str = "CatCoderBeige.PPCoach") -> None:
    """Registers us with Windows as a standalone app (own taskbar icon, clean
    grouping). Errors are ignored (e.g. on non-Windows)."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(appid)
    except Exception:
        pass


def _ensure_desktop_shortcut() -> None:
    """Creates a desktop shortcut with the app icon on first start (only in the
    built .exe) and remembers this in the settings - so an icon the user later
    deletes is not recreated unasked."""
    if not updater.is_frozen():
        return
    try:
        settings = load_settings()
        if settings.get("desktop_shortcut_created"):
            return
        desktop = Path(os.path.expanduser("~")) / "Desktop"
        if not desktop.exists():
            return
        lnk = desktop / f"{APP_NAME}.lnk"
        exe = sys.executable
        workdir = os.path.dirname(exe)
        ps = (
            f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
            f"$s.TargetPath='{exe}';$s.IconLocation='{exe},0';"
            f"$s.WorkingDirectory='{workdir}';$s.Save()"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            creationflags=0x08000000,  # CREATE_NO_WINDOW
            check=False,
        )
        settings["desktop_shortcut_created"] = True
        save_settings(settings)
    except Exception:
        pass


class PPCoachApp(ctk.CTk):
    def __init__(self):
        _set_app_user_model_id()  # appear as our own app in the taskbar
        super().__init__()
        self.title(f"{APP_NAME} v{VERSION}")
        self.geometry("800x780")
        self.minsize(680, 620)
        self.configure(fg_color=theme.BG_WINDOW)
        self._set_icon()

        updater.cleanup_old()      # remove leftovers from a previous update
        _ensure_desktop_shortcut()  # create the desktop shortcut with icon once

        self._client = OsuApiClient()
        self._update_info = None
        self._overlay = None
        self._scrim_bg = None
        self._build_layout()
        self._show_example_profile()  # show an example profile on startup
        self._check_updates_async()  # quietly in the background, never intrusive

        # Match the title bar to the app design (dark, same color as the window)
        # instead of the light system default bar. Immediately + once slightly
        # delayed, since some Windows builds only repaint after the first paint.
        self._style_titlebar()
        self.after(60, self._style_titlebar)

    def _set_icon(self):
        icon_path = _asset_path("icon.ico")
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except tk.TclError:
                pass

    def _style_titlebar(self):
        """Colors the title bar, window border and title text to match the app design.

        Uses the DWM API (Windows 11, build 22000+). On older systems or non-Windows
        it fails silently and the default bar stays.
        """
        if sys.platform != "win32":
            return
        try:
            import ctypes

            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute

            def _set(attr: int, value: int) -> None:
                val = ctypes.c_int(value)
                dwm(hwnd, attr, ctypes.byref(val), ctypes.sizeof(val))

            def _colorref(hex_color: str) -> int:
                h = hex_color.lstrip("#")
                r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
                return (b << 16) | (g << 8) | r  # COLORREF is 0x00BBGGRR

            _set(20, 1)                              # dark mode (light icons/buttons)
            _set(35, _colorref(theme.BG_WINDOW))     # title bar background
            _set(34, _colorref(theme.BORDER))        # window border
            _set(36, _colorref(theme.TEXT_PRIMARY))  # title text
        except Exception:
            pass

    # -- Layout -------------------------------------------------------------
    def _build_layout(self):
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=22, pady=20)

        # Topbar: title + subtle hint
        topbar = ctk.CTkFrame(outer, fg_color="transparent")
        topbar.pack(fill="x")
        ctk.CTkLabel(
            topbar, text=APP_NAME, font=theme.font(26, "bold"),
            text_color=theme.TEXT_PRIMARY,
        ).pack(side="left")
        ctk.CTkLabel(
            topbar, text="  osu! skill analysis", font=theme.font(13),
            text_color=theme.TEXT_MUTED,
        ).pack(side="left", pady=(10, 0))

        # Update check now at the TOP right (launcher feel): version + manual check.
        self.footer_label = ctk.CTkLabel(
            topbar, text=f"v{VERSION}  ·  check for updates", font=theme.font(11),
            text_color=theme.TEXT_MUTED, cursor="hand2",
        )
        self.footer_label.pack(side="right", pady=(10, 0))
        self.footer_label.bind("<Button-1>", lambda _e: self._manual_check())

        # Update button: only visible once a new version has been found.
        self.update_button = ctk.CTkButton(
            topbar, text="⬆  Update", command=self._open_update_dialog,
            height=30, width=110, font=theme.font(12, "bold"),
            corner_radius=theme.RADIUS_BUTTON,
            fg_color=theme.POSITIVE, hover_color=theme.POSITIVE_HOVER,
            text_color=theme.POSITIVE_TEXT,
        )

        # AI banner (promo + info popup) - deliberately loud ad color (cyan ->
        # violet) that clearly stands out from the rest.
        self.ai_banner = theme.GradientBanner(
            outer, on_click=self._show_ai_teaser,
            text="AI Coach — your personal osu! coach",
            height=76, badge="COMING SOON", cta="Discover  ›",
            colors=(theme.AI_GRADIENT_START, theme.AI_GRADIENT_END),
        )
        self.ai_banner.pack(fill="x", pady=(16, 16))

        # Search bar - centered & prominent: this is the single primary action,
        # so it sits in the middle and stands out with an accent border.
        input_frame = ctk.CTkFrame(outer, fg_color="transparent")
        input_frame.pack(fill="x")

        search_wrap = ctk.CTkFrame(input_frame, fg_color="transparent")
        search_wrap.pack()  # no fill -> horizontally centered

        self.username_entry = ctk.CTkEntry(
            search_wrap, placeholder_text="🔍   Enter your osu! username …",
            width=320, height=50, font=theme.font(15),
            corner_radius=theme.RADIUS_BUTTON,
            fg_color=theme.BG_INPUT, border_color=theme.ACCENT, border_width=2,
        )
        self.username_entry.pack(side="left", padx=(0, 10))
        self.username_entry.bind("<Return>", lambda _e: self._start_analysis())
        # Deliberately NO prefill: the field starts empty (placeholder only).

        self.analyze_button = ctk.CTkButton(
            search_wrap, text="Analyze", command=self._start_analysis,
            height=50, width=150, font=theme.font(15, "bold"),
            corner_radius=theme.RADIUS_BUTTON,
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
            text_color=theme.TEXT_ON_ACCENT,
        )
        self.analyze_button.pack(side="left")

        # Status line (centered under the search bar)
        self.status_label = ctk.CTkLabel(
            outer, text="", font=theme.font(12), text_color=theme.TEXT_MUTED,
        )
        self.status_label.pack(pady=(12, 6))

        # Scrollable content area (empty state or result cards)
        self.content = ctk.CTkScrollableFrame(
            outer, fg_color="transparent",
        )
        self.content.pack(fill="both", expand=True)
        # Two equal-width columns: tips sit left/right, headers span both.
        self.content.grid_columnconfigure(0, weight=1, uniform="col")
        self.content.grid_columnconfigure(1, weight=1, uniform="col")

        # Footer: subtle legal disclaimer (now at the bottom instead of the top).
        self.disclaimer_label = ctk.CTkLabel(
            outer, text="unofficial · not affiliated with osu!",
            font=theme.font(11), text_color=theme.TEXT_MUTED,
        )
        self.disclaimer_label.pack(anchor="e", pady=(8, 0))

    # -- Content states -----------------------------------------------------
    def _clear_content(self):
        for child in self.content.winfo_children():
            child.destroy()

    def _show_empty_state(self):
        self._clear_content()
        card = ctk.CTkFrame(self.content, fg_color=theme.BG_CARD,
                            corner_radius=theme.RADIUS_CARD)
        card.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text="🎯", font=theme.font(48),
        ).grid(row=0, column=0, pady=(30, 4))
        ctk.CTkLabel(
            card, text="Ready for your analysis", font=theme.font(20, "bold"),
            text_color=theme.TEXT_PRIMARY,
        ).grid(row=1, column=0)
        ctk.CTkLabel(
            card,
            text="Enter your osu! username above and click “Analyze”.\n"
                 "You'll get your stats plus concrete tips on where you're leaving\n"
                 "the most PP on the table – accuracy, mods, consistency and more.",
            font=theme.font(13), text_color=theme.TEXT_MUTED, justify="center",
        ).grid(row=2, column=0, pady=(6, 12), padx=20)
        ctk.CTkLabel(
            card,
            text="✨  Want even deeper, tailored analysis? "
                 "Check out the AI Coach above.",
            font=theme.font(12, "bold"), text_color=theme.ACCENT,
            justify="center",
        ).grid(row=3, column=0, pady=(0, 30), padx=20)

    def _show_example_profile(self):
        """Shows a deliberately simple, greyed-out preview on startup (placeholders
        instead of real values), so you can see the layout of an analysis - without
        it looking like real data."""
        self._render_results("Example Player", EXAMPLE_STATS, EXAMPLE_FINDINGS,
                             avatar_image=None, flag_image=None, example=True)

    def _show_error(self, message: str):
        self._clear_content()
        theme.TipCard(
            self.content, title="Something went wrong", body=message,
            accent=theme.DANGER, icon="⚠", wraplength=CONTENT_WRAP,
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(4, 0))

    def _render_results(self, username, stats, findings, avatar_image, flag_image=None,
                        example=False):
        self._clear_content()
        statistics = stats.get("statistics", {})
        row = 0

        # In example mode everything is muted: muted colors signal that these are
        # placeholders and not real values.
        primary = theme.TEXT_MUTED if example else theme.TEXT_PRIMARY
        accent = theme.TEXT_MUTED if example else theme.ACCENT

        # Example mode: clearly visible hint that this is only a preview.
        if example:
            note = ctk.CTkFrame(self.content, fg_color=theme.BG_CARD,
                                corner_radius=theme.RADIUS_CARD)
            note.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 12))
            note.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                note, text="EXAMPLE", font=theme.font(11, "bold"),
                text_color=theme.TEXT_PRIMARY, fg_color=theme.BORDER,
                corner_radius=6, padx=8, pady=2,
            ).grid(row=0, column=0, padx=(14, 10), pady=12)
            ctk.CTkLabel(
                note,
                text="Preview with placeholder values. Enter your osu! username above "
                     "to see your real analysis.",
                font=theme.font(12), text_color=theme.TEXT_MUTED, anchor="w",
                justify="left",
            ).grid(row=0, column=1, sticky="w", padx=(0, 14), pady=12)
            row += 1

        # --- Hero header (avatar + name + rank) ---------------------------
        hero = ctk.CTkFrame(self.content, fg_color=theme.BG_CARD_ALT,
                            corner_radius=theme.RADIUS_CARD)
        hero.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 12))
        hero.grid_columnconfigure(1, weight=1)

        self._build_avatar(hero, username, avatar_image, muted=example)

        info = ctk.CTkFrame(hero, fg_color="transparent")
        info.grid(row=0, column=1, sticky="w", padx=(4, 18), pady=18)
        ctk.CTkLabel(
            info, text=stats.get("username", username), font=theme.font(24, "bold"),
            text_color=primary, anchor="w",
        ).pack(anchor="w")

        country = stats.get("country_code", "")
        rankrow = ctk.CTkFrame(info, fg_color="transparent")
        rankrow.pack(anchor="w", pady=(6, 0))
        global_text = ("Global —" if example
                       else f"Global {theme.fmt_rank(statistics.get('global_rank'))}")
        ctk.CTkLabel(
            rankrow, text=global_text,
            font=theme.font(13, "bold"), text_color=accent,
        ).pack(side="left")
        if not example and statistics.get("country_rank"):
            if flag_image is not None:
                ctk.CTkLabel(rankrow, text="", image=flag_image).pack(
                    side="left", padx=(14, 5))
            else:
                # Fallback without an image: just the country code
                ctk.CTkLabel(rankrow, text="  ·  ", font=theme.font(13),
                             text_color=theme.TEXT_MUTED).pack(side="left")
            ctk.CTkLabel(
                rankrow,
                text=f"{country} {theme.fmt_rank(statistics.get('country_rank'))}",
                font=theme.font(13, "bold"), text_color=theme.TEXT_PRIMARY,
            ).pack(side="left")
        row += 1

        # --- Stat cards ----------------------------------------------------
        level = statistics.get("level", {}) or {}
        stat_row = ctk.CTkFrame(self.content, fg_color="transparent")
        stat_row.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        if example:
            # Placeholders (no real values), all muted.
            stats_data = [
                ("—", "Performance", accent),
                ("—", "Accuracy", primary),
                ("—", "Level", primary),
                ("—", "Playtime", primary),
            ]
        else:
            # Only the core value (PP) carries the brand color as a focal point;
            # the other values stay neutral-light -> calm and easy to scan.
            stats_data = [
                (theme.fmt_pp(statistics.get("pp")), "Performance", theme.ACCENT),
                (theme.fmt_accuracy(statistics.get("hit_accuracy")), "Accuracy",
                 theme.TEXT_PRIMARY),
                (str(level.get("current", "?")), "Level", theme.TEXT_PRIMARY),
                (theme.fmt_hours(statistics.get("play_time")), "Playtime",
                 theme.TEXT_PRIMARY),
            ]
        for col, (value, label, card_accent) in enumerate(stats_data):
            stat_row.grid_columnconfigure(col, weight=1, uniform="stat")
            card = theme.StatCard(stat_row, value=value, label=label, accent=card_accent)
            padx = (0, 8) if col == 0 else (8, 8) if col < 3 else (8, 0)
            card.grid(row=0, column=col, sticky="ew", padx=padx)
        row += 1

        # --- Tip cards (two columns: left/right, more compact) -------------
        ctk.CTkLabel(
            self.content, text="YOUR TIPS", font=theme.font(12, "bold"),
            text_color=theme.TEXT_MUTED, anchor="w",
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(2, 8), padx=2)
        row += 1

        for idx, finding in enumerate(findings):
            icon, cat_accent = theme.category_style(finding.category)
            if example:
                cat_accent = theme.TEXT_MUTED  # muted, since it's only a preview
            col = idx % 2
            padx = (0, 6) if col == 0 else (6, 0)
            theme.TipCard(
                self.content, title=finding.title, body=finding.text,
                accent=cat_accent, icon=icon, wraplength=TIP_WRAP,
            ).grid(row=row + idx // 2, column=col, sticky="new", padx=padx,
                   pady=(0, 12))

    def _build_avatar(self, master, username, avatar_image, muted=False):
        """Places the round avatar image on the left of the hero, or a fallback:
        normally a circle with the initial, in (greyed-out) example mode a neutral,
        muted placeholder silhouette."""
        if avatar_image is not None:
            ctk.CTkLabel(master, text="", image=avatar_image).grid(
                row=0, column=0, padx=(18, 8), pady=18)
            return

        size = AVATAR_SIZE
        canvas = tk.Canvas(master, width=size, height=size, highlightthickness=0,
                           bd=0, bg=theme.BG_CARD_ALT)
        canvas.grid(row=0, column=0, padx=(18, 8), pady=18)

        if muted:
            # Neutral placeholder (no real profile): muted silhouette.
            canvas.create_oval(2, 2, size - 2, size - 2, fill=theme.BG_CARD,
                               outline=theme.BORDER, width=2)
            canvas.create_oval(size * 0.34, size * 0.24, size * 0.66, size * 0.56,
                               fill=theme.TEXT_MUTED, outline="")
            canvas.create_arc(size * 0.20, size * 0.60, size * 0.80, size * 1.04,
                              start=0, extent=180, fill=theme.TEXT_MUTED, outline="")
            return

        canvas.create_oval(0, 0, size, size, fill=theme.ACCENT, outline="")
        initial = (username[:1] or "?").upper()
        canvas.create_text(size / 2, size / 2, text=initial,
                           font=(theme.FONT_FAMILY, 40, "bold"), fill="white")

    # -- Flow ---------------------------------------------------------------
    def _start_analysis(self):
        username = self.username_entry.get().strip()
        if not username:
            self.status_label.configure(text="Please enter a username.")
            return

        self.analyze_button.configure(state="disabled")
        self.status_label.configure(text="Loading data from the osu! API …")

        thread = threading.Thread(target=self._run_analysis, args=(username,),
                                  daemon=True)
        thread.start()

    def _run_analysis(self, username: str):
        try:
            stats = self._client.get_user_stats(username)
            scores = self._client.get_top_scores(stats["id"])
            findings = generate_report(stats, scores)
            avatar_image = _load_round_avatar(stats.get("avatar_url", ""))
            flag_image = _load_flag(stats.get("country_code", ""))
        except (OsuApiError, ConfigError) as exc:
            self.after(0, self._on_error, str(exc))
            return
        except Exception as exc:  # an unexpected error must not crash the GUI
            self.after(0, self._on_error, f"Unexpected error: {exc}")
            return

        self.after(0, self._on_success, username, stats, findings, avatar_image,
                   flag_image)

    def _on_success(self, username, stats, findings, avatar_image, flag_image):
        set_last_username(username)
        self.status_label.configure(text="Analysis complete ✓")
        self.analyze_button.configure(state="normal")
        self._render_results(username, stats, findings, avatar_image, flag_image)

    def _on_error(self, message: str):
        self.status_label.configure(text="Error")
        self.analyze_button.configure(state="normal")
        self._show_error(message)

    # -- Self-update --------------------------------------------------------
    def _check_updates_async(self, manual: bool = False):
        threading.Thread(target=self._check_updates, args=(manual,),
                         daemon=True).start()

    def _check_updates(self, manual: bool):
        try:
            info = updater.check_for_update()
        except Exception:
            # An unreachable update server must never disturb the app.
            if manual:
                self.after(0, lambda: self.footer_label.configure(
                    text=f"v{VERSION}  ·  check failed  ·  try again"))
            return

        if info:
            self.after(0, self._show_update_available, info)
        elif manual:
            self.after(0, lambda: self.footer_label.configure(
                text=f"v{VERSION}  ·  up to date ✓  ·  check again"))

    def _manual_check(self):
        self.footer_label.configure(text=f"v{VERSION}  ·  checking for updates …")
        self._check_updates_async(manual=True)

    def _show_update_available(self, info):
        self._update_info = info
        self.update_button.configure(text=f"⬆  Update {info.version}")
        self.update_button.pack(side="right", padx=(0, 10), pady=(6, 0))
        self.footer_label.configure(
            text=f"v{VERSION}  ·  version {info.version} available")

    def _open_update_dialog(self):
        """Shows the update details as an in-app box (no second window). A click on
        'Update now' downloads, installs and restarts automatically."""
        info = self._update_info
        if info is None:
            return

        card = self._open_overlay(480, 470)

        header = theme.GradientBanner(
            card, on_click=lambda: None,
            text=f"⬆  Update {info.version}", height=70, cta="",
            colors=(theme.UPDATE_GRADIENT_START, theme.UPDATE_GRADIENT_END),
            round_top=theme.RADIUS_CARD, corner_color=theme.BG_WINDOW,
        )
        header.configure(cursor="arrow")
        header.unbind("<Button-1>")
        header.pack(fill="x")

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(16, 20))

        ctk.CTkLabel(
            body, text=f"You have v{VERSION} – v{info.version} is available.",
            font=theme.font(14, "bold"), text_color=theme.TEXT_PRIMARY,
        ).pack(anchor="w")

        notes_box = ctk.CTkTextbox(
            body, font=theme.font(12), fg_color=theme.BG_CARD_ALT,
            text_color=theme.TEXT_MUTED, corner_radius=theme.RADIUS_CARD,
            wrap="word", height=150,
        )
        notes_box.pack(fill="both", expand=True, pady=(10, 12))
        notes_box.insert("1.0", info.notes or "No changelog provided.")
        notes_box.configure(state="disabled")

        progress = ctk.CTkProgressBar(body, progress_color=theme.POSITIVE)
        progress.set(0)
        status = ctk.CTkLabel(body, text="", font=theme.font(11),
                              text_color=theme.TEXT_MUTED)

        button_row = ctk.CTkFrame(body, fg_color="transparent")
        button_row.pack(fill="x", pady=(4, 0))

        later_btn = ctk.CTkButton(
            button_row, text="Later", command=self._close_overlay, height=40, width=110,
            corner_radius=theme.RADIUS_BUTTON, font=theme.font(13),
            fg_color=theme.BG_CARD_ALT, hover_color=theme.BORDER,
        )
        later_btn.pack(side="left")

        update_btn = ctk.CTkButton(
            button_row, text="Update now", height=40,
            corner_radius=theme.RADIUS_BUTTON, font=theme.font(13, "bold"),
            fg_color=theme.POSITIVE, hover_color=theme.POSITIVE_HOVER,
            text_color=theme.POSITIVE_TEXT,
        )
        update_btn.pack(side="right")

        def do_update():
            if not updater.is_frozen():
                status.pack(anchor="w", pady=(10, 0))
                status.configure(
                    text="In developer mode (python) nothing is replaced – this only "
                         "works in the built .exe.")
                return
            update_btn.configure(state="disabled")
            later_btn.configure(state="disabled")
            progress.pack(fill="x", pady=(12, 4))
            status.pack(anchor="w")
            status.configure(text="Downloading update …")
            threading.Thread(target=run_update, daemon=True).start()

        def run_update():
            try:
                path = updater.download_update(
                    info, progress_cb=lambda f: self.after(0, progress.set, f))
                self.after(0, lambda: status.configure(
                    text="Installing & restarting …"))
                updater.apply_update_and_restart(path)  # terminates the process
            except Exception as exc:
                self.after(0, self._update_failed, update_btn, later_btn, status, exc)

        update_btn.configure(command=do_update)

    def _update_failed(self, update_btn, later_btn, status, exc):
        update_btn.configure(state="normal")
        later_btn.configure(state="normal")
        status.configure(text=f"Update failed: {exc}")

    # -- In-app overlays (no separate window) -------------------------------
    def _close_overlay(self):
        overlay = getattr(self, "_overlay", None)
        if overlay is not None and overlay.winfo_exists():
            overlay.destroy()
        self._overlay = None
        self._scrim_bg = None
        self.unbind("<Escape>")

    def _make_dimmed_backdrop(self):
        """Takes a snapshot of the current window and only dims it slightly. This
        keeps the background behind the popup visible (instead of fully black).

        Returns a plain Tk PhotoImage (NOT a CTkImage) on purpose: CTkImage re-applies
        the widget/DPI scaling factor, which on scaled displays (e.g. 150%) blew the
        snapshot up so the background looked zoomed in. A Tk PhotoImage is drawn 1:1
        with the grabbed pixels, so it lines up exactly with the real window.
        Falls back tolerantly to None on any error."""
        if Image is None:
            return None
        try:
            from PIL import ImageGrab, ImageTk
        except Exception:
            return None
        try:
            self.update_idletasks()
            x, y = self.winfo_rootx(), self.winfo_rooty()
            w, h = self.winfo_width(), self.winfo_height()
            if w <= 1 or h <= 1:
                return None
            shot = ImageGrab.grab(bbox=(x, y, x + w, y + h)).convert("RGB")
            dark = Image.new("RGB", shot.size, (8, 9, 14))
            dimmed = Image.blend(shot, dark, 0.4)  # only dim a little
            return ImageTk.PhotoImage(dimmed)
        except Exception:
            return None

    def _open_overlay(self, width, height, closable=True):
        """Builds a modal in-app overlay (slightly dimmed background + centered
        card) and returns the card. Does NOT open a second window."""
        self._close_overlay()
        # Take the snapshot BEFORE the scrim so the real content is captured.
        backdrop = self._make_dimmed_backdrop()

        scrim = ctk.CTkFrame(self, fg_color=theme.BG_WINDOW, corner_radius=0)
        scrim.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._overlay = scrim
        self._scrim_bg = backdrop

        if backdrop is not None:
            # Plain tk.Label so the snapshot is drawn 1:1 (no CTk image scaling).
            bg = tk.Label(scrim, image=backdrop, bd=0, highlightthickness=0)
            bg.place(x=0, y=0)
            if closable:
                bg.bind("<Button-1>", lambda _e: self._close_overlay())

        if closable:
            scrim.bind("<Button-1>", lambda _e: self._close_overlay())  # outside = close
            self.bind("<Escape>", lambda _e: self._close_overlay())
        card = ctk.CTkFrame(scrim, fg_color=theme.BG_CARD,
                            corner_radius=theme.RADIUS_CARD, width=width, height=height)
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.pack_propagate(False)
        return card

    def _show_ai_teaser(self):
        card = self._open_overlay(480, 510)

        # Gradient header in the same loud AI ad color as the banner
        header = theme.GradientBanner(
            card, on_click=lambda: None, text="✨  AI Coach", height=72, cta="",
            colors=(theme.AI_GRADIENT_START, theme.AI_GRADIENT_END),
            round_top=theme.RADIUS_CARD, corner_color=theme.BG_WINDOW,
        )
        header.configure(cursor="arrow")
        header.unbind("<Button-1>")
        header.pack(fill="x")

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(18, 20))

        ctk.CTkLabel(
            body, text="Coming soon – your personal coach",
            font=theme.font(16, "bold"), text_color=theme.TEXT_PRIMARY,
        ).pack(anchor="w")
        ctk.CTkLabel(
            body,
            text="The next update takes the analysis to a whole new level:",
            font=theme.font(13), text_color=theme.TEXT_MUTED, justify="left",
        ).pack(anchor="w", pady=(4, 14))

        bullets = [
            ("🎯", "Tailored to you",
             "Analyzes your individual playstyle instead of generic rules."),
            ("🔍", "Much deeper",
             "Spots subtle patterns in aim, reading & timing that rules of thumb miss."),
            ("🗺", "Special map picks",
             "Hand-picked maps that train exactly your weaknesses."),
        ]
        for icon, title, text in bullets:
            self._teaser_bullet(body, icon, title, text)

        ctk.CTkButton(
            body, text="Got it", command=self._close_overlay,
            height=40, font=theme.font(13, "bold"),
            corner_radius=theme.RADIUS_BUTTON,
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
        ).pack(fill="x", pady=(16, 0))

    def _teaser_bullet(self, master, icon, title, text):
        row = ctk.CTkFrame(master, fg_color=theme.BG_CARD,
                           corner_radius=theme.RADIUS_CARD)
        row.pack(fill="x", pady=4)
        row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(row, text=icon, font=theme.font(20)).grid(
            row=0, column=0, rowspan=2, padx=(14, 10), pady=12)
        ctk.CTkLabel(
            row, text=title, font=theme.font(13, "bold"),
            text_color=theme.TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=(0, 12), pady=(11, 0))
        ctk.CTkLabel(
            row, text=text, font=theme.font(12), text_color=theme.TEXT_MUTED,
            anchor="w", justify="left", wraplength=300,
        ).grid(row=1, column=1, sticky="w", padx=(0, 12), pady=(0, 11))


def main():
    app = PPCoachApp()
    app.mainloop()


if __name__ == "__main__":
    main()
