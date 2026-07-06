"""Desktop-GUI (CustomTkinter) fuer PPCoach.

Lila-dominantes, dunkles Design mit osu!-Pink als Akzent. Ergebnisse werden als
einzelne Karten in einem scrollbaren Bereich dargestellt (Profil-Header mit
Avatar + Stat-Karten + Tipp-Karten) statt in einer einzelnen Text-Box.
"""

import io
import sys
import threading
import tkinter as tk
from pathlib import Path

import customtkinter as ctk
import requests

from . import theme, updater
from .config import APP_NAME, VERSION, ConfigError, get_last_username, set_last_username
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

# Statisches Demo-Profil, das beim Start gezeigt wird (kein API-Call noetig).
EXAMPLE_STATS = {
    "username": "mrekk",
    "country_code": "AU",
    "statistics": {
        "global_rank": 1,
        "country_rank": 1,
        "pp": 21500,
        "hit_accuracy": 99.06,
        "level": {"current": 105},
        "play_time": 5_400_000,  # Sekunden (~1500 h)
    },
}
EXAMPLE_FINDINGS = [
    Finding("Accuracy drops on harder maps",
            "Accuracy falls by about 1.8% as star rating increases – practice maps just "
            "above the comfort zone.", "accuracy"),
    Finding("Untapped PP potential from mods",
            "HD/HR barely show up in the top scores – farming known maps with them is "
            "comparatively easy PP.", "mods"),
    Finding("Strong consistency",
            "Almost all top scores are S or better – solid miss control across full maps.",
            "consistency"),
    Finding("Next steps for this PP level",
            "Fine-tune with targeted maps for known weaknesses and smart mod combinations.",
            "strategy"),
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


class PPCoachApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{VERSION}")
        self.geometry("800x780")
        self.minsize(680, 620)
        self.configure(fg_color=theme.BG_WINDOW)
        self._set_icon()

        self._client = OsuApiClient()
        self._update_info = None
        self._overlay = None
        self._build_layout()
        self._show_example_profile()  # beim Start ein Beispiel-Profil zeigen
        self._check_updates_async()  # still im Hintergrund, stoert nie

    def _set_icon(self):
        icon_path = _asset_path("icon.ico")
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except tk.TclError:
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
        ctk.CTkLabel(
            topbar, text="unofficial · not affiliated with osu!",
            font=theme.font(11), text_color=theme.TEXT_MUTED,
        ).pack(side="right", pady=(10, 0))

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

        # Search row - compact (usernames are short), left-aligned
        input_frame = ctk.CTkFrame(outer, fg_color="transparent")
        input_frame.pack(fill="x")

        self.username_entry = ctk.CTkEntry(
            input_frame, placeholder_text="Enter osu! username …",
            width=280, height=44, font=theme.font(14),
            corner_radius=theme.RADIUS_BUTTON,
            fg_color=theme.BG_INPUT, border_color=theme.BORDER, border_width=1,
        )
        self.username_entry.pack(side="left", padx=(0, 10))
        self.username_entry.bind("<Return>", lambda _e: self._start_analysis())
        # Prefill with the last used name, or "mrekk" as an example
        self.username_entry.insert(0, get_last_username() or "mrekk")

        self.analyze_button = ctk.CTkButton(
            input_frame, text="Analyze", command=self._start_analysis,
            height=44, width=140, font=theme.font(14, "bold"),
            corner_radius=theme.RADIUS_BUTTON,
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
            text_color=theme.TEXT_ON_ACCENT,
        )
        self.analyze_button.pack(side="left")

        # Status-Zeile
        self.status_label = ctk.CTkLabel(
            outer, text="", font=theme.font(12), text_color=theme.TEXT_MUTED,
        )
        self.status_label.pack(anchor="w", pady=(10, 6))

        # Scrollbarer Content-Bereich (Empty-State bzw. Ergebnis-Karten)
        self.content = ctk.CTkScrollableFrame(
            outer, fg_color="transparent",
        )
        self.content.pack(fill="both", expand=True)
        # Zwei gleich breite Spalten: Tipps liegen links/rechts, Header spannen beide.
        self.content.grid_columnconfigure(0, weight=1, uniform="col")
        self.content.grid_columnconfigure(1, weight=1, uniform="col")

        # Footer: Version + manueller Update-Check (Launcher-Gefuehl).
        self.footer_label = ctk.CTkLabel(
            outer, text=f"v{VERSION}  ·  check for updates", font=theme.font(11),
            text_color=theme.TEXT_MUTED, cursor="hand2",
        )
        self.footer_label.pack(anchor="e", pady=(8, 0))
        self.footer_label.bind("<Button-1>", lambda _e: self._manual_check())

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
        """Zeigt beim Start ein statisches Demo-Profil (mrekk), damit man sofort
        sieht, wie eine Analyse aussieht."""
        self._render_results("mrekk", EXAMPLE_STATS, EXAMPLE_FINDINGS,
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

        # Beispiel-Modus: deutlich sichtbarer Hinweis, dass das nur ein Demo-Profil ist.
        if example:
            note = ctk.CTkFrame(self.content, fg_color=theme.BG_CARD,
                                corner_radius=theme.RADIUS_CARD)
            note.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 12))
            note.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                note, text="EXAMPLE", font=theme.font(11, "bold"),
                text_color=theme.POSITIVE_TEXT, fg_color=theme.POSITIVE,
                corner_radius=6, padx=8, pady=2,
            ).grid(row=0, column=0, padx=(14, 10), pady=12)
            ctk.CTkLabel(
                note,
                text="This is a sample profile. Enter your own osu! username above and "
                     "click “Analyze”.",
                font=theme.font(12), text_color=theme.TEXT_MUTED, anchor="w",
                justify="left",
            ).grid(row=0, column=1, sticky="w", padx=(0, 14), pady=12)
            row += 1

        # --- Hero-Header (Avatar + Name + Rang) ---------------------------
        hero = ctk.CTkFrame(self.content, fg_color=theme.BG_CARD_ALT,
                            corner_radius=theme.RADIUS_CARD)
        hero.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 12))
        hero.grid_columnconfigure(1, weight=1)

        self._build_avatar(hero, username, avatar_image)

        info = ctk.CTkFrame(hero, fg_color="transparent")
        info.grid(row=0, column=1, sticky="w", padx=(4, 18), pady=18)
        ctk.CTkLabel(
            info, text=stats.get("username", username), font=theme.font(24, "bold"),
            text_color=theme.TEXT_PRIMARY, anchor="w",
        ).pack(anchor="w")

        country = stats.get("country_code", "")
        rankrow = ctk.CTkFrame(info, fg_color="transparent")
        rankrow.pack(anchor="w", pady=(6, 0))
        ctk.CTkLabel(
            rankrow, text=f"Global {theme.fmt_rank(statistics.get('global_rank'))}",
            font=theme.font(13, "bold"), text_color=theme.ACCENT,
        ).pack(side="left")
        if statistics.get("country_rank"):
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
        # Nur der Kern-Wert (PP) traegt die Markenfarbe als Fokuspunkt; die uebrigen
        # Werte bleiben neutral-hell -> ruhig und uebersichtlich.
        stats_data = [
            (theme.fmt_pp(statistics.get("pp")), "Performance", theme.ACCENT),
            (theme.fmt_accuracy(statistics.get("hit_accuracy")), "Accuracy",
             theme.TEXT_PRIMARY),
            (str(level.get("current", "?")), "Level", theme.TEXT_PRIMARY),
            (theme.fmt_hours(statistics.get("play_time")), "Playtime",
             theme.TEXT_PRIMARY),
        ]
        for col, (value, label, accent) in enumerate(stats_data):
            stat_row.grid_columnconfigure(col, weight=1, uniform="stat")
            card = theme.StatCard(stat_row, value=value, label=label, accent=accent)
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
            icon, accent = theme.category_style(finding.category)
            col = idx % 2
            padx = (0, 6) if col == 0 else (6, 0)
            theme.TipCard(
                self.content, title=finding.title, body=finding.text,
                accent=accent, icon=icon, wraplength=TIP_WRAP,
            ).grid(row=row + idx // 2, column=col, sticky="new", padx=padx,
                   pady=(0, 12))

    def _build_avatar(self, master, username, avatar_image):
        """Setzt links im Hero entweder das runde Avatar-Bild oder einen
        Fallback-Kreis mit der Initiale des Nutzernamens."""
        if avatar_image is not None:
            ctk.CTkLabel(master, text="", image=avatar_image).grid(
                row=0, column=0, padx=(18, 8), pady=18)
            return

        size = AVATAR_SIZE
        canvas = tk.Canvas(master, width=size, height=size, highlightthickness=0,
                           bd=0, bg=theme.BG_CARD_ALT)
        canvas.grid(row=0, column=0, padx=(18, 8), pady=18)
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
        info = self._update_info
        if info is None:
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Update available")
        dialog.geometry("460x400")
        dialog.resizable(False, False)
        dialog.configure(fg_color=theme.BG_WINDOW)
        dialog.transient(self)

        header = theme.GradientBanner(
            dialog, on_click=lambda: None,
            text=f"⬆  Update {info.version} available", height=70,
        )
        header.configure(cursor="arrow")
        header.unbind("<Button-1>")
        header.pack(fill="x")

        body = ctk.CTkFrame(dialog, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(16, 20))

        ctk.CTkLabel(
            body, text=f"You have v{VERSION} – v{info.version} is available.",
            font=theme.font(14, "bold"), text_color=theme.TEXT_PRIMARY,
        ).pack(anchor="w")

        notes_box = ctk.CTkTextbox(
            body, font=theme.font(12), fg_color=theme.BG_CARD,
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
            button_row, text="Later", command=dialog.destroy, height=40, width=110,
            corner_radius=theme.RADIUS_BUTTON, font=theme.font(13),
            fg_color=theme.BG_CARD, hover_color=theme.BG_CARD_ALT,
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

        dialog.update_idletasks()
        dialog.after(10, dialog.grab_set)

    def _update_failed(self, update_btn, later_btn, status, exc):
        update_btn.configure(state="normal")
        later_btn.configure(state="normal")
        status.configure(text=f"Update failed: {exc}")

    # -- AI-Info-Popup (In-App-Overlay, kein separates Fenster) -------------
    def _close_overlay(self):
        overlay = getattr(self, "_overlay", None)
        if overlay is not None and overlay.winfo_exists():
            overlay.destroy()
        self._overlay = None
        self.unbind("<Escape>")

    def _show_ai_teaser(self):
        self._close_overlay()

        # Scrim: dunkler Vollflaechen-Layer ueber der ganzen App -> wirkt als
        # In-App-Popup (modaler Look), oeffnet KEIN zweites Fenster.
        scrim = ctk.CTkFrame(self, fg_color="#05060A", corner_radius=0)
        scrim.place(relx=0, rely=0, relwidth=1, relheight=1)
        scrim.bind("<Button-1>", lambda _e: self._close_overlay())  # ausserhalb = zu
        self._overlay = scrim
        self.bind("<Escape>", lambda _e: self._close_overlay())

        card = ctk.CTkFrame(scrim, fg_color=theme.BG_CARD,
                            corner_radius=theme.RADIUS_CARD, width=480, height=510)
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.pack_propagate(False)

        # Gradient-Kopf in der gleichen auffaelligen AI-Werbefarbe wie der Banner
        header = theme.GradientBanner(
            card, on_click=lambda: None, text="✨  AI Coach", height=72, cta="",
            colors=(theme.AI_GRADIENT_START, theme.AI_GRADIENT_END),
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
