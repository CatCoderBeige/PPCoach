"""Central design tokens and reusable UI building blocks for PPCoach.

Minimalist & dark: a neutral base with osu! pink as the only brand color -
tailored to osu! gamers.
All CustomTkinter/Tkinter, so the app can still be built as a single .exe.
"""

import math
import tkinter as tk

import customtkinter as ctk

# --- Color palette (minimalist & coherent) ---------------------------------
# Principle: a neutral, cool dark base + ONE brand color (osu! pink), used
# sparingly. Category accents are deliberately muted and tonally aligned (similar
# saturation & brightness) - they read as a family rather than colorful. This keeps
# the picture calm and modern, matching the osu! identity.

# Neutral base
BG_WINDOW = "#0F1115"       # window background (cool near-black, neutral)
BG_CARD = "#171A20"         # card surface
BG_CARD_ALT = "#1D212A"     # slightly raised card (e.g. hero header)
BG_INPUT = "#1A1E25"        # input fields
BORDER = "#2A2F3A"          # subtle lines/borders

TEXT_PRIMARY = "#EAECEF"    # main text (cool near-white)
TEXT_MUTED = "#8B93A1"      # muted text
TEXT_ON_ACCENT = "#FFFFFF"

# Brand color: osu! pink - only for primary actions & important highlights.
ACCENT = "#FF6AA6"
ACCENT_HOVER = "#FF85B6"

# Semantics
POSITIVE = "#46B37E"        # "update available" / success (calm green)
POSITIVE_HOVER = "#57C08E"
POSITIVE_TEXT = "#08130C"   # dark text on a light green button
DANGER = "#DB6B63"          # error/notice cards (muted red)

# Muted, tonally aligned category accents (one color family).
CAT_BLUE = "#6E9BD1"
CAT_TEAL = "#5FB0A6"
CAT_GREEN = "#79B58C"
CAT_AMBER = "#D3A96B"
CAT_ORANGE = "#CD8C66"
CAT_ROSE = "#D97BA4"
CAT_RED = "#D9776F"
CAT_NEUTRAL = "#8B93A1"

# Category -> (icon, accent color). Simplistic, monochrome glyphs; the muted color
# encodes the category without making the picture colorful. "general" is the
# fallback so every tip really gets an icon.
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
    """Returns (icon, color) for a category, with a safe fallback."""
    return CATEGORY_STYLE.get(category, CATEGORY_STYLE[DEFAULT_CATEGORY])

# Gradient for the AI banner/popup header: a calm single-tone ramp (rose ->
# osu! pink), staying within the brand family instead of mixing purple and pink.
GRADIENT_START = (201, 92, 142)   # #C95C8E muted rose
GRADIENT_END = (255, 106, 166)    # #FF6AA6 osu! pink

# Deliberately different, loud "ad" color for the AI Coach banner: a cyan->violet
# combo that clearly stands out from the pink/neutral rest. Ad character - it should
# catch the eye and intentionally NOT quite match the rest.
AI_GRADIENT_START = (34, 211, 238)   # #22D3EE cyan
AI_GRADIENT_END = (124, 92, 255)     # #7C5CFF violet

# Calm green->cyan ramp for the update box header (signal: "go/available").
UPDATE_GRADIENT_START = (70, 179, 126)   # #46B37E green
UPDATE_GRADIENT_END = (34, 211, 238)     # #22D3EE cyan

# Corner radii
RADIUS_CARD = 16
RADIUS_BUTTON = 12

FONT_FAMILY = "Segoe UI"


def font(size: int, weight: str = "normal") -> ctk.CTkFont:
    """Small helper for consistent fonts."""
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)


def hex_between(start: tuple[int, int, int], end: tuple[int, int, int], t: float) -> str:
    """Linearly interpolates between two RGB colors and returns a hex string."""
    r = round(start[0] + (end[0] - start[0]) * t)
    g = round(start[1] + (end[1] - start[1]) * t)
    b = round(start[2] + (end[2] - start[2]) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _lighten(rgb: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    """Lightens an RGB color toward white (0.0 = unchanged)."""
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
    """Horizontal gradient button that promotes the AI feature.

    Purely visual/marketing - on click the provided callback is invoked (in the app:
    an info popup). Hover lightens the gradient slightly. Colors and an optional
    "badge" (e.g. NEW) are configurable, so the AI banner can carry a deliberately
    loud ad color.
    """

    def __init__(self, master, on_click, text="✨  AI Coach  –  coming soon",
                 height=64, colors=None, badge=None, cta="ℹ  Learn more  ›",
                 round_top=0, corner_color=BG_WINDOW, **kwargs):
        super().__init__(master, height=height, highlightthickness=0, bd=0,
                         bg=corner_color, **kwargs)
        self._on_click = on_click
        self._text = text
        self._badge = badge
        self._cta = cta
        self._start, self._end = colors if colors else (GRADIENT_START, GRADIENT_END)
        # As a popup header the top corners should match the rounded card; as a
        # free-standing banner (round_top=0) it stays edge-to-edge square.
        self._round_top = round_top
        self._corner_color = corner_color
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

        if self._round_top > 0:
            self._cut_top_corners(width)

        text_x = 22
        if self._badge:
            # small white "NEW" pill with colored text -> ad character
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

    def _cut_top_corners(self, width):
        """Paints the small wedges outside the top rounding in the card color - so
        the top corners look just as rounded as the card below (a tk Canvas can't
        do rounded corners on its own)."""
        r = self._round_top
        cc = self._corner_color
        seg = 6

        left = [(0, 0), (r, 0)]
        for i in range(seg + 1):
            ang = math.radians(270 - 90 * i / seg)
            left.append((r + r * math.cos(ang), r + r * math.sin(ang)))
        self.create_polygon(left, fill=cc, outline=cc)

        right = [(width, 0), (width - r, 0)]
        for i in range(seg + 1):
            ang = math.radians(270 + 90 * i / seg)
            right.append((width - r + r * math.cos(ang), r + r * math.sin(ang)))
        self.create_polygon(right, fill=cc, outline=cc)


class StatCard(ctk.CTkFrame):
    """Small tile: large value on top, small label below."""

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
    """Tip card: colored category icon on the left, title + wrapped body on the right."""

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
