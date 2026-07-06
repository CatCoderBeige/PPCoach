"""Desktop-GUI (CustomTkinter) fuer PPCoach.

Lila-dominantes, dunkles Design mit osu!-Pink als Akzent. Ergebnisse werden als
einzelne Karten in einem scrollbaren Bereich dargestellt (Profil-Header mit
Avatar + Stat-Karten + Tipp-Karten) statt in einer einzelnen Text-Box.
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
except ImportError:  # Pillow ist optional; ohne wird nur der Avatar-Fallback genutzt
    Image = None
    ImageDraw = None

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

AVATAR_SIZE = 96
CONTENT_WRAP = 600  # Textumbruch fuer volle Breite (z.B. Fehler-Karte)
TIP_WRAP = 270      # Textumbruch in den zweispaltigen Tipp-Karten

# Statisches Demo-Profil, das beim Start als greyed-out Vorschau gezeigt wird
# (kein API-Call, bewusst KEINE echten Werte - nur Platzhalter, damit klar ist,
# dass hier noch nichts analysiert wurde).
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
    """Findet Asset-Dateien sowohl im Dev-Modus als auch in der gebauten .exe
    (PyInstaller entpackt Datas nach sys._MEIPASS zur Laufzeit)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets" / filename


def _load_round_avatar(url: str):
    """Laedt das Avatar-Bild und maskiert es rund. Liefert ein CTkImage oder None.

    Bewusst tolerant: jeder Fehler (Netzwerk, fehlendes Pillow, kaputtes Bild)
    fuehrt zu None, damit die Analyse nie an einem Avatar scheitert.
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
    """Laedt die Laenderflagge (flagcdn) als kleines CTkImage. Tolerant -> None bei Fehler."""
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
    """Meldet uns bei Windows als eigenstaendige App an (eigenes Taskleisten-Icon,
    saubere Gruppierung). Fehler werden ignoriert (z.B. auf Nicht-Windows)."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(appid)
    except Exception:
        pass


def _ensure_desktop_shortcut() -> None:
    """Legt beim ersten Start (nur in der gebauten .exe) eine Desktop-Verknuepfung
    mit App-Icon an und merkt sich das in den Settings - ein spaeter vom Nutzer
    geloeschtes Icon wird also nicht ungefragt neu erstellt."""
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
        _set_app_user_model_id()  # als eigene App in der Taskleiste fuehren
        super().__init__()
        self.title(f"{APP_NAME} v{VERSION}")
        self.geometry("800x780")
        self.minsize(680, 620)
        self.configure(fg_color=theme.BG_WINDOW)
        self._set_icon()

        updater.cleanup_old()      # Reste eines vorherigen Updates entfernen
        _ensure_desktop_shortcut()  # einmalig Desktop-Verknuepfung mit Icon anlegen

        self._client = OsuApiClient()
        self._update_info = None
        self._overlay = None
        self._scrim_bg = None
        self._build_layout()
        self._show_example_profile()  # beim Start ein Beispiel-Profil zeigen
        self._check_updates_async()  # still im Hintergrund, stoert nie

        # Titelleiste an das App-Design angleichen (dunkel, gleiche Farbe wie das
        # Fenster) statt der hellen System-Standardleiste. Direkt + nochmal knapp
        # verzoegert, da manche Windows-Builds erst nach dem ersten Paint neu zeichnen.
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
        """Faerbt Titelleiste, Fensterrahmen und Titeltext passend zum App-Design.

        Nutzt die DWM-API (Windows 11, Build 22000+). Auf aelteren Systemen oder
        Nicht-Windows schlaegt es still fehl und die Standardleiste bleibt.
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
                return (b << 16) | (g << 8) | r  # COLORREF ist 0x00BBGGRR

            _set(20, 1)                              # dunkler Modus (Icons/Buttons hell)
            _set(35, _colorref(theme.BG_WINDOW))     # Titelleisten-Hintergrund
            _set(34, _colorref(theme.BORDER))        # Fensterrahmen
            _set(36, _colorref(theme.TEXT_PRIMARY))  # Titeltext
        except Exception:
            pass

    # -- Aufbau -------------------------------------------------------------
    def _build_layout(self):
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=22, pady=20)

        # Topbar: Titel + dezenter Hinweis
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

        # Update-Check jetzt OBEN rechts (Launcher-Gefuehl): Version + manueller Check.
        self.footer_label = ctk.CTkLabel(
            topbar, text=f"v{VERSION}  ·  check for updates", font=theme.font(11),
            text_color=theme.TEXT_MUTED, cursor="hand2",
        )
        self.footer_label.pack(side="right", pady=(10, 0))
        self.footer_label.bind("<Button-1>", lambda _e: self._manual_check())

        # Update-Button: erst sichtbar, wenn eine neue Version gefunden wurde.
        self.update_button = ctk.CTkButton(
            topbar, text="⬆  Update", command=self._open_update_dialog,
            height=30, width=110, font=theme.font(12, "bold"),
            corner_radius=theme.RADIUS_BUTTON,
            fg_color=theme.POSITIVE, hover_color=theme.POSITIVE_HOVER,
            text_color=theme.POSITIVE_TEXT,
        )

        # AI-Banner (Werbung + Info-Popup) - bewusst auffaellige Ad-Farbe (Cyan->
        # Violett), die sich klar vom Rest abhebt.
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
        search_wrap.pack()  # kein fill -> horizontal zentriert

        self.username_entry = ctk.CTkEntry(
            search_wrap, placeholder_text="🔍   Enter your osu! username …",
            width=320, height=50, font=theme.font(15),
            corner_radius=theme.RADIUS_BUTTON,
            fg_color=theme.BG_INPUT, border_color=theme.ACCENT, border_width=2,
        )
        self.username_entry.pack(side="left", padx=(0, 10))
        self.username_entry.bind("<Return>", lambda _e: self._start_analysis())
        # Bewusst KEIN Prefill: das Feld startet leer (nur Placeholder).

        self.analyze_button = ctk.CTkButton(
            search_wrap, text="Analyze", command=self._start_analysis,
            height=50, width=150, font=theme.font(15, "bold"),
            corner_radius=theme.RADIUS_BUTTON,
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
            text_color=theme.TEXT_ON_ACCENT,
        )
        self.analyze_button.pack(side="left")

        # Status-Zeile (zentriert unter der Suchleiste)
        self.status_label = ctk.CTkLabel(
            outer, text="", font=theme.font(12), text_color=theme.TEXT_MUTED,
        )
        self.status_label.pack(pady=(12, 6))

        # Scrollbarer Content-Bereich (Empty-State bzw. Ergebnis-Karten)
        self.content = ctk.CTkScrollableFrame(
            outer, fg_color="transparent",
        )
        self.content.pack(fill="both", expand=True)
        # Zwei gleich breite Spalten: Tipps liegen links/rechts, Header spannen beide.
        self.content.grid_columnconfigure(0, weight=1, uniform="col")
        self.content.grid_columnconfigure(1, weight=1, uniform="col")

        # Footer: dezenter rechtlicher Hinweis (jetzt unten statt oben).
        self.disclaimer_label = ctk.CTkLabel(
            outer, text="unofficial · not affiliated with osu!",
            font=theme.font(11), text_color=theme.TEXT_MUTED,
        )
        self.disclaimer_label.pack(anchor="e", pady=(8, 0))

    # -- Content-Zustaende --------------------------------------------------
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
        """Zeigt beim Start eine bewusst simple, ausgegraute Vorschau (Platzhalter
        statt echter Werte), damit man den Aufbau einer Analyse sieht - ohne dass
        es wie echte Daten wirkt."""
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

        # Im Beispiel-Modus ist alles gedaempft: gedaempfte Farben signalisieren,
        # dass es sich um Platzhalter und nicht um echte Werte handelt.
        primary = theme.TEXT_MUTED if example else theme.TEXT_PRIMARY
        accent = theme.TEXT_MUTED if example else theme.ACCENT

        # Beispiel-Modus: deutlich sichtbarer Hinweis, dass das nur eine Vorschau ist.
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

        # --- Hero-Header (Avatar + Name + Rang) ---------------------------
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
                # Fallback ohne Bild: nur der Laendercode
                ctk.CTkLabel(rankrow, text="  ·  ", font=theme.font(13),
                             text_color=theme.TEXT_MUTED).pack(side="left")
            ctk.CTkLabel(
                rankrow,
                text=f"{country} {theme.fmt_rank(statistics.get('country_rank'))}",
                font=theme.font(13, "bold"), text_color=theme.TEXT_PRIMARY,
            ).pack(side="left")
        row += 1

        # --- Stat-Karten ---------------------------------------------------
        level = statistics.get("level", {}) or {}
        stat_row = ctk.CTkFrame(self.content, fg_color="transparent")
        stat_row.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        if example:
            # Platzhalter (keine echten Werte), alles gedaempft.
            stats_data = [
                ("—", "Performance", accent),
                ("—", "Accuracy", primary),
                ("—", "Level", primary),
                ("—", "Playtime", primary),
            ]
        else:
            # Nur der Kern-Wert (PP) traegt die Markenfarbe als Fokuspunkt; die
            # uebrigen Werte bleiben neutral-hell -> ruhig und uebersichtlich.
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

        # --- Tipp-Karten (zwei Spalten: links/rechts, kompakter) -----------
        ctk.CTkLabel(
            self.content, text="YOUR TIPS", font=theme.font(12, "bold"),
            text_color=theme.TEXT_MUTED, anchor="w",
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(2, 8), padx=2)
        row += 1

        for idx, finding in enumerate(findings):
            icon, cat_accent = theme.category_style(finding.category)
            if example:
                cat_accent = theme.TEXT_MUTED  # gedaempft, da nur Vorschau
            col = idx % 2
            padx = (0, 6) if col == 0 else (6, 0)
            theme.TipCard(
                self.content, title=finding.title, body=finding.text,
                accent=cat_accent, icon=icon, wraplength=TIP_WRAP,
            ).grid(row=row + idx // 2, column=col, sticky="new", padx=padx,
                   pady=(0, 12))

    def _build_avatar(self, master, username, avatar_image, muted=False):
        """Setzt links im Hero das runde Avatar-Bild, oder einen Fallback:
        im Normalfall ein Kreis mit der Initiale, im (ausgegrauten) Beispiel-Modus
        eine neutrale, gedaempfte Platzhalter-Silhouette."""
        if avatar_image is not None:
            ctk.CTkLabel(master, text="", image=avatar_image).grid(
                row=0, column=0, padx=(18, 8), pady=18)
            return

        size = AVATAR_SIZE
        canvas = tk.Canvas(master, width=size, height=size, highlightthickness=0,
                           bd=0, bg=theme.BG_CARD_ALT)
        canvas.grid(row=0, column=0, padx=(18, 8), pady=18)

        if muted:
            # Neutraler Platzhalter (kein echtes Profil): gedaempfte Silhouette.
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

    # -- Ablauf -------------------------------------------------------------
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
        except Exception as exc:  # unerwarteter Fehler soll die GUI nicht crashen
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

    # -- Selbst-Update ------------------------------------------------------
    def _check_updates_async(self, manual: bool = False):
        threading.Thread(target=self._check_updates, args=(manual,),
                         daemon=True).start()

    def _check_updates(self, manual: bool):
        try:
            info = updater.check_for_update()
        except Exception:
            # Ein nicht erreichbarer Update-Server darf die App nie stoeren.
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
        """Zeigt die Update-Details als In-App-Box (kein zweites Fenster). Ein Klick
        auf 'Update now' laedt herunter, installiert und startet automatisch neu."""
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
                updater.apply_update_and_restart(path)  # beendet den Prozess
            except Exception as exc:
                self.after(0, self._update_failed, update_btn, later_btn, status, exc)

        update_btn.configure(command=do_update)

    def _update_failed(self, update_btn, later_btn, status, exc):
        update_btn.configure(state="normal")
        later_btn.configure(state="normal")
        status.configure(text=f"Update failed: {exc}")

    # -- In-App-Overlays (kein separates Fenster) ---------------------------
    def _close_overlay(self):
        overlay = getattr(self, "_overlay", None)
        if overlay is not None and overlay.winfo_exists():
            overlay.destroy()
        self._overlay = None
        self._scrim_bg = None
        self.unbind("<Escape>")

    def _make_dimmed_backdrop(self):
        """Nimmt einen Schnappschuss des aktuellen Fensters und dunkelt ihn nur
        leicht ab. So bleibt der Hintergrund hinter dem Popup sichtbar (statt
        komplett schwarz). Faellt bei jedem Fehler tolerant auf None zurueck."""
        if Image is None:
            return None
        try:
            from PIL import ImageGrab
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
            dimmed = Image.blend(shot, dark, 0.4)  # nur ein bisschen abdunkeln
            return ctk.CTkImage(light_image=dimmed, dark_image=dimmed, size=(w, h))
        except Exception:
            return None

    def _open_overlay(self, width, height, closable=True):
        """Baut ein modales In-App-Overlay (leicht abgedunkelter Hintergrund +
        zentrierte Karte) und liefert die Karte zurueck. Oeffnet KEIN zweites
        Fenster."""
        self._close_overlay()
        # Schnappschuss VOR dem Scrim aufnehmen, damit der echte Inhalt drin ist.
        backdrop = self._make_dimmed_backdrop()

        scrim = ctk.CTkFrame(self, fg_color=theme.BG_WINDOW, corner_radius=0)
        scrim.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._overlay = scrim
        self._scrim_bg = backdrop

        if backdrop is not None:
            bg = ctk.CTkLabel(scrim, text="", image=backdrop)
            bg.place(relx=0, rely=0, relwidth=1, relheight=1)
            if closable:
                bg.bind("<Button-1>", lambda _e: self._close_overlay())

        if closable:
            scrim.bind("<Button-1>", lambda _e: self._close_overlay())  # ausserhalb = zu
            self.bind("<Escape>", lambda _e: self._close_overlay())
        card = ctk.CTkFrame(scrim, fg_color=theme.BG_CARD,
                            corner_radius=theme.RADIUS_CARD, width=width, height=height)
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.pack_propagate(False)
        return card

    def _show_ai_teaser(self):
        card = self._open_overlay(480, 510)

        # Gradient-Kopf in der gleichen auffaelligen AI-Werbefarbe wie der Banner
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
