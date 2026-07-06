"""Zentrale Design-Tokens und wiederverwendbare UI-Bausteine fuer PPCoach.

Lila-dominant, dunkel, mit osu!-Pink als Akzent - abgestimmt auf osu!-Gamer.
Alles CustomTkinter/Tkinter, damit die App weiterhin als eine einzelne .exe
gebaut werden kann.
"""

import tkinter as tk

import customtkinter as ctk

# --- Farb-Palette ----------------------------------------------------------
BG_WINDOW = "#0E0B14"       # Fensterhintergrund (fast schwarz, leicht violett)
BG_CARD = "#1B1626"         # Karten-Oberflaeche
BG_CARD_ALT = "#221B33"     # etwas hellere Karte (z.B. Hero-Header)
BG_INPUT = "#241D33"        # Eingabefelder

ACCENT_PURPLE = "#9B59FF"   # Leit-Akzent Lila
ACCENT_PURPLE_HOVER = "#AA72FF"
OSU_PINK = "#FF66AB"        # osu!-Pink als Highlight
OSU_PINK_HOVER = "#FF7FB8"

TEXT_PRIMARY = "#F3EEFF"    # Haupttext
TEXT_MUTED = "#A99FC0"      # gedaempfter Text
TEXT_ON_ACCENT = "#FFFFFF"

DANGER = "#FF5C6C"          # Fehler/Hinweis-Karten

# Erweiterte Akzentpalette, damit nicht alles nur lila/pink ist. Bewusst kraeftige,
# aber auf dunklem Grund gut lesbare Farben.
COLOR_BLUE = "#4EA1FF"
COLOR_CYAN = "#22D3EE"
COLOR_GREEN = "#3DDC84"
COLOR_GOLD = "#FFC24B"
COLOR_ORANGE = "#FF9F43"
COLOR_RED = DANGER

# Kategorie -> (Symbol, Akzentfarbe). Simplistische, monochrome Glyphen; die Farbe
# uebernimmt die Unterscheidung. "general" ist der Fallback fuer alle unbekannten
# Faelle, damit wirklich jeder Tipp ein Symbol bekommt.
CATEGORY_STYLE = {
    "accuracy":    ("◎", COLOR_BLUE),
    "mods":        ("↯", COLOR_GOLD),
    "spread":      ("✦", ACCENT_PURPLE),
    "consistency": ("≡", COLOR_CYAN),
    "misses":      ("✕", COLOR_RED),
    "playtime":    ("◷", COLOR_ORANGE),
    "strategy":    ("➜", COLOR_GREEN),
    "general":     ("◆", OSU_PINK),
}
DEFAULT_CATEGORY = "general"


def category_style(category: str) -> tuple[str, str]:
    """Liefert (Symbol, Farbe) fuer eine Kategorie, mit sicherem Fallback."""
    return CATEGORY_STYLE.get(category, CATEGORY_STYLE[DEFAULT_CATEGORY])

# Gradient-Endpunkte (Lila -> Pink) fuer den AI-Banner und Popup-Kopf
GRADIENT_START = (155, 89, 255)   # #9B59FF
GRADIENT_END = (255, 102, 171)    # #FF66AB

# Ecken-Radien
RADIUS_CARD = 16
RADIUS_BUTTON = 12

FONT_FAMILY = "Segoe UI"


def font(size: int, weight: str = "normal") -> ctk.CTkFont:
    """Kurzhelfer fuer konsistente Schriftarten."""
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)


def hex_between(start: tuple[int, int, int], end: tuple[int, int, int], t: float) -> str:
    """Interpoliert linear zwischen zwei RGB-Farben und liefert einen Hex-String."""
    r = round(start[0] + (end[0] - start[0]) * t)
    g = round(start[1] + (end[1] - start[1]) * t)
    b = round(start[2] + (end[2] - start[2]) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _lighten(rgb: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    """Hellt eine RGB-Farbe in Richtung Weiss auf (0.0 = unveraendert)."""
    return tuple(round(c + (255 - c) * amount) for c in rgb)  # type: ignore[return-value]


# --- Formatierungs-Helfer --------------------------------------------------
def fmt_int(value) -> str:
    """1234567 -> '1.234.567' (Punkt als Tausendertrenner, dt. Stil)."""
    try:
        return f"{int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "?"


def fmt_rank(value) -> str:
    return f"#{fmt_int(value)}" if value else "#?"


def fmt_pp(value) -> str:
    try:
        return f"{float(value):,.0f}".replace(",", ".") + "pp"
    except (TypeError, ValueError):
        return "?pp"


def fmt_accuracy(value) -> str:
    try:
        return f"{float(value):.2f}".replace(".", ",") + "%"
    except (TypeError, ValueError):
        return "?"


def fmt_hours(seconds) -> str:
    try:
        return f"{int(seconds) // 3600} h"
    except (TypeError, ValueError):
        return "?"


# --- Widgets ---------------------------------------------------------------
class GradientBanner(tk.Canvas):
    """Horizontaler Lila->Pink Gradient-Button, der das AI-Feature bewirbt.

    Rein visuell/Marketing - beim Klick wird der uebergebene Callback aufgerufen
    (in der App: ein Info-Popup). Hover hellt den Verlauf leicht auf.
    """

    def __init__(self, master, on_click, text="✨  AI Coach  –  bald verfügbar",
                 height=64, **kwargs):
        super().__init__(master, height=height, highlightthickness=0, bd=0,
                         bg=BG_WINDOW, **kwargs)
        self._on_click = on_click
        self._text = text
        self._hover = False
        self.configure(cursor="hand2")
        self.bind("<Configure>", self._draw)
        self.bind("<Button-1>", lambda _e: self._on_click())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _event=None):
        self._hover = True
        self._draw()

    def _on_leave(self, _event=None):
        self._hover = False
        self._draw()

    def _draw(self, _event=None):
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        if width <= 1:
            return

        boost = 0.12 if self._hover else 0.0
        start = _lighten(GRADIENT_START, boost)
        end = _lighten(GRADIENT_END, boost)

        steps = max(width // 2, 60)
        for i in range(steps):
            t = i / (steps - 1)
            color = hex_between(start, end, t)
            x0 = width * i / steps
            x1 = width * (i + 1) / steps
            self.create_rectangle(x0, 0, x1 + 1, height, fill=color, outline=color)

        # kleiner "NEU/Premium"-Charakter durch zweizeiligen Text
        self.create_text(
            22, height / 2,
            text=self._text,
            font=(FONT_FAMILY, 16, "bold"),
            fill="white",
            anchor="w",
        )
        self.create_text(
            width - 22, height / 2,
            text="ℹ  Mehr erfahren  ›",
            font=(FONT_FAMILY, 12, "bold"),
            fill="white",
            anchor="e",
        )


class StatCard(ctk.CTkFrame):
    """Kleine Kachel: grosser Wert oben, kleines Label darunter."""

    def __init__(self, master, value: str, label: str, accent: str = ACCENT_PURPLE,
                 **kwargs):
        super().__init__(master, fg_color=BG_CARD, corner_radius=RADIUS_CARD, **kwargs)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text=value, font=font(22, "bold"), text_color=accent,
        ).grid(row=0, column=0, padx=14, pady=(14, 0), sticky="w")

        ctk.CTkLabel(
            self, text=label.upper(), font=font(11, "bold"), text_color=TEXT_MUTED,
        ).grid(row=1, column=0, padx=14, pady=(2, 14), sticky="w")


class TipCard(ctk.CTkFrame):
    """Tipp-Karte: farbiges Kategorie-Symbol links, Titel + umbrochener Body rechts."""

    def __init__(self, master, title: str, body: str, accent: str = ACCENT_PURPLE,
                 icon: str = "◆", wraplength: int = 280, **kwargs):
        super().__init__(master, fg_color=BG_CARD, corner_radius=RADIUS_CARD, **kwargs)
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self, text=icon, font=font(26, "bold"), text_color=accent, width=30,
        ).grid(row=0, column=0, rowspan=2, padx=(16, 12), pady=(16, 0), sticky="n")

        ctk.CTkLabel(
            self, text=title, font=font(14, "bold"), text_color=TEXT_PRIMARY,
            justify="left", anchor="w", wraplength=wraplength,
        ).grid(row=0, column=1, padx=(0, 16), pady=(15, 2), sticky="w")

        ctk.CTkLabel(
            self, text=body, font=font(12), text_color=TEXT_MUTED,
            justify="left", anchor="w", wraplength=wraplength,
        ).grid(row=1, column=1, padx=(0, 16), pady=(0, 15), sticky="w")
