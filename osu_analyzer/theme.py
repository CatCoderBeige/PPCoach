"""Zentrale Design-Tokens und wiederverwendbare UI-Bausteine fuer PPCoach.

Minimalistisch & dunkel: neutrale Basis mit osu!-Pink als einziger Markenfarbe -
abgestimmt auf osu!-Gamer.
Alles CustomTkinter/Tkinter, damit die App weiterhin als eine einzelne .exe
gebaut werden kann.
"""

import tkinter as tk

import customtkinter as ctk

# --- Farb-Palette (minimalistisch & kohaerent) -----------------------------
# Prinzip: neutrale, kuehle Dunkelbasis + EINE Markenfarbe (osu!-Pink), sparsam
# eingesetzt. Kategorie-Akzente sind bewusst gedaempft und tonal aufeinander
# abgestimmt (aehnliche Saettigung & Helligkeit) - sie wirken als Familie statt
# bunt. Das haelt das Bild ruhig und modern, passend zur osu!-Identitaet.

# Neutrale Basis
BG_WINDOW = "#0F1115"       # Fensterhintergrund (kuehles Fast-Schwarz, neutral)
BG_CARD = "#171A20"         # Karten-Oberflaeche
BG_CARD_ALT = "#1D212A"     # leicht erhoehte Karte (z.B. Hero-Header)
BG_INPUT = "#1A1E25"        # Eingabefelder
BORDER = "#2A2F3A"          # dezente Linien/Raender

TEXT_PRIMARY = "#EAECEF"    # Haupttext (kuehles Fast-Weiss)
TEXT_MUTED = "#8B93A1"      # gedaempfter Text
TEXT_ON_ACCENT = "#FFFFFF"

# Markenfarbe: osu!-Pink - nur fuer primaere Aktionen & wichtige Highlights.
ACCENT = "#FF6AA6"
ACCENT_HOVER = "#FF85B6"

# Semantik
POSITIVE = "#46B37E"        # "Update verfuegbar" / Erfolg (ruhiges Gruen)
POSITIVE_HOVER = "#57C08E"
POSITIVE_TEXT = "#08130C"   # dunkler Text auf hellem Gruen-Button
DANGER = "#DB6B63"          # Fehler/Hinweis-Karten (gedaempftes Rot)

# Gedaempfte, tonal abgestimmte Kategorie-Akzente (eine Farbfamilie).
CAT_BLUE = "#6E9BD1"
CAT_TEAL = "#5FB0A6"
CAT_GREEN = "#79B58C"
CAT_AMBER = "#D3A96B"
CAT_ORANGE = "#CD8C66"
CAT_ROSE = "#D97BA4"
CAT_RED = "#D9776F"
CAT_NEUTRAL = "#8B93A1"

# Kategorie -> (Symbol, Akzentfarbe). Simplistische, monochrome Glyphen; die
# gedaempfte Farbe kodiert die Kategorie, ohne das Bild bunt zu machen. "general"
# ist der Fallback, damit wirklich jeder Tipp ein Symbol bekommt.
CATEGORY_STYLE = {
    "accuracy":    ("◎", CAT_BLUE),
    "mods":        ("↯", CAT_AMBER),
    "spread":      ("✦", CAT_ROSE),
    "consistency": ("≡", CAT_TEAL),
    "misses":      ("✕", CAT_RED),
    "playtime":    ("◷", CAT_ORANGE),
    "strategy":    ("➜", CAT_GREEN),
    "general":     ("◆", CAT_NEUTRAL),
}
DEFAULT_CATEGORY = "general"


def category_style(category: str) -> tuple[str, str]:
    """Liefert (Symbol, Farbe) fuer eine Kategorie, mit sicherem Fallback."""
    return CATEGORY_STYLE.get(category, CATEGORY_STYLE[DEFAULT_CATEGORY])

# Gradient fuer AI-Banner/Popup-Kopf: ruhiger Ein-Ton-Verlauf (Rose -> osu!-Pink),
# bleibt in der Markenfamilie statt Lila und Pink zu mischen.
GRADIENT_START = (201, 92, 142)   # #C95C8E gedaempftes Rose
GRADIENT_END = (255, 106, 166)    # #FF6AA6 osu!-Pink

# Bewusst abweichende, laute "Werbe"-Farbe fuer den AI-Coach-Banner: eine
# Cyan->Violett-Kombi, die sich klar vom pink/neutralen Rest abhebt. Ad-Charakter -
# soll auffallen und absichtlich NICHT ganz zum Rest passen.
AI_GRADIENT_START = (34, 211, 238)   # #22D3EE Cyan
AI_GRADIENT_END = (124, 92, 255)     # #7C5CFF Violett

# Ruhiger Gruen->Cyan-Verlauf fuer den Kopf der Update-Box (Signal: "los/verfuegbar").
UPDATE_GRADIENT_START = (70, 179, 126)   # #46B37E Gruen
UPDATE_GRADIENT_END = (34, 211, 238)     # #22D3EE Cyan

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


# --- Formatting helpers ----------------------------------------------------
def fmt_int(value) -> str:
    """1234567 -> '1,234,567' (comma thousands separator, English style)."""
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "?"


def fmt_rank(value) -> str:
    return f"#{fmt_int(value)}" if value else "#?"


def fmt_pp(value) -> str:
    try:
        return f"{float(value):,.0f}" + "pp"
    except (TypeError, ValueError):
        return "?pp"


def fmt_accuracy(value) -> str:
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "?"


def fmt_hours(seconds) -> str:
    try:
        return f"{int(seconds) // 3600} h"
    except (TypeError, ValueError):
        return "?"


# --- Widgets ---------------------------------------------------------------
class GradientBanner(tk.Canvas):
    """Horizontaler Gradient-Button, der das AI-Feature bewirbt.

    Rein visuell/Marketing - beim Klick wird der uebergebene Callback aufgerufen
    (in der App: ein Info-Popup). Hover hellt den Verlauf leicht auf. Farben und
    ein optionaler "Badge" (z.B. NEU) sind konfigurierbar, damit der AI-Banner
    eine bewusst auffaellige Werbefarbe tragen kann.
    """

    def __init__(self, master, on_click, text="✨  AI Coach  –  coming soon",
                 height=64, colors=None, badge=None, cta="ℹ  Learn more  ›",
                 **kwargs):
        super().__init__(master, height=height, highlightthickness=0, bd=0,
                         bg=BG_WINDOW, **kwargs)
        self._on_click = on_click
        self._text = text
        self._badge = badge
        self._cta = cta
        self._start, self._end = colors if colors else (GRADIENT_START, GRADIENT_END)
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
        start = _lighten(self._start, boost)
        end = _lighten(self._end, boost)

        steps = max(width // 2, 60)
        for i in range(steps):
            t = i / (steps - 1)
            color = hex_between(start, end, t)
            x0 = width * i / steps
            x1 = width * (i + 1) / steps
            self.create_rectangle(x0, 0, x1 + 1, height, fill=color, outline=color)

        text_x = 22
        if self._badge:
            # kleines weisses "NEU"-Pill mit farbigem Text -> Werbe-Charakter
            badge_font = (FONT_FAMILY, 11, "bold")
            probe = self.create_text(0, -50, text=self._badge, font=badge_font,
                                     anchor="nw")
            bx = self.bbox(probe)
            self.delete(probe)
            tw = (bx[2] - bx[0]) if bx else 30
            th = (bx[3] - bx[1]) if bx else 14
            pad = 9
            y0 = height / 2 - th / 2 - 4
            y1 = height / 2 + th / 2 + 4
            self.create_rectangle(22, y0, 22 + tw + 2 * pad, y1, fill="white",
                                  outline="")
            self.create_text(22 + pad, height / 2 + 1, text=self._badge,
                             font=badge_font, fill=hex_between(start, end, 0.0),
                             anchor="w")
            text_x = 22 + tw + 2 * pad + 14

        self.create_text(
            text_x, height / 2,
            text=self._text,
            font=(FONT_FAMILY, 16, "bold"),
            fill="white",
            anchor="w",
        )
        if self._cta:
            self.create_text(
                width - 22, height / 2,
                text=self._cta,
                font=(FONT_FAMILY, 12, "bold"),
                fill="white",
                anchor="e",
            )


class StatCard(ctk.CTkFrame):
    """Kleine Kachel: grosser Wert oben, kleines Label darunter."""

    def __init__(self, master, value: str, label: str, accent: str = ACCENT,
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

    def __init__(self, master, title: str, body: str, accent: str = ACCENT,
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
