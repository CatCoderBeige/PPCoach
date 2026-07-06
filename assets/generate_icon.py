"""Generates a placeholder logo/icon for PPCoach.

One-off helper script, not part of the product. Re-run with `python
assets/generate_icon.py` if needed, or simply replace the generated files with
your own logo (same filename/same size is enough).
"""

from PIL import Image, ImageDraw

GRADIENT_START = (155, 89, 255)
GRADIENT_END = (255, 105, 180)
SIZE = 256


def lerp_color(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def build_base_image() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    for y in range(SIZE):
        t = y / (SIZE - 1)
        color = lerp_color(GRADIENT_START, GRADIENT_END, t)
        draw.line([(0, y), (SIZE, y)], fill=color)

    mask = Image.new("L", (SIZE, SIZE), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([(0, 0), (SIZE - 1, SIZE - 1)], radius=56, fill=255)

    rounded = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    rounded.paste(img, (0, 0), mask)

    draw = ImageDraw.Draw(rounded)
    cx, cy = SIZE / 2, SIZE / 2

    # Stylized upward-pointing arrow/trend as an "improvement" symbol
    points = [
        (cx - 62, cy + 46),
        (cx - 18, cy + 4),
        (cx + 10, cy + 30),
        (cx + 62, cy - 46),
    ]
    draw.line(points, fill="white", width=14, joint="curve")
    arrow_tip = points[-1]
    draw.polygon(
        [
            (arrow_tip[0], arrow_tip[1]),
            (arrow_tip[0] - 30, arrow_tip[1] + 6),
            (arrow_tip[0] - 4, arrow_tip[1] + 30),
        ],
        fill="white",
    )
    for px, py in points[:-1]:
        draw.ellipse([px - 8, py - 8, px + 8, py + 8], fill="white")
    draw.ellipse([arrow_tip[0] - 8, arrow_tip[1] - 8, arrow_tip[0] + 8, arrow_tip[1] + 8], fill="white")

    return rounded


if __name__ == "__main__":
    base = build_base_image()
    base.save("assets/logo.png")
    base.save(
        "assets/icon.ico",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("Generated: assets/logo.png, assets/icon.ico")
