#!/usr/bin/env python3
"""Draw Masthead feed covers and the share icon. Flat print, no gradients."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "public" / "fonts"
OUT = ROOT / "public" / "covers"
PWA = ROOT / "public" / "pwa"

SERIF = FONT_DIR / "6NUh8FyLNQOQZAnv9bYEvDiIdE9Ea92uemAk_WBq8U_9v0c2Wa0K7iN7hzFUPJH58nib1603gg7S2nfgRYIcUByjDg.ttf"
SERIF_ITAL = FONT_DIR / "6NVf8FyLNQOQZAnv9ZwNjucMHVn85Ni7emAe9lKqZTnbB-gzTK0K1ChJdt9vIVYX9G37lvd9sPEKsxx664UJf1h5Tf7W.ttf"
GROTESK = FONT_DIR / "7cHqv4kjgoGqM7E3t-4c4A.ttf"
GROTESK_MED = FONT_DIR / "7cHqv4kjgoGqM7E3_-gc4A.ttf"
MONO = FONT_DIR / "-F6qfjptAgt5VM-kVkqdyU8n3twJ8lc.ttf"

COVERS = [
    {
        "file": "articles.png",
        "bg": "#f4efe4",
        "ink": "#1c140f",
        "rule": "#d63c2e",
        "muted": "#6b5e52",
        "kicker": "CITY DESK",
        "word": "Articles",
        "deck": "The pages you follow, read in full.",
        "folio": "№ 01",
        "lamp": True,
    },
    {
        "file": "x.png",
        "bg": "#1c140f",
        "ink": "#f4efe4",
        "rule": "#d63c2e",
        "muted": "#c9bbaa",
        "kicker": "OVERNIGHT",
        "word": "The Wire",
        "deck": "Posts and threads, spoken once.",
        "folio": "№ 02",
        "lamp": True,
    },
    {
        "file": "videos.png",
        "bg": "#2a2118",
        "ink": "#f6efe2",
        "rule": "#c9862a",
        "muted": "#d9c4a4",
        "kicker": "PICTURE DESK",
        "word": "Screen",
        "deck": "A moving picture, reduced to sound.",
        "folio": "№ 03",
        "lamp": False,
    },
    {
        "file": "learn.png",
        "bg": "#e5efe4",
        "ink": "#14241b",
        "rule": "#1f6a45",
        "muted": "#3e5c4a",
        "kicker": "NIGHT SCHOOL",
        "word": "Lessons",
        "deck": "A course you can hear.",
        "folio": "№ 04",
        "lamp": False,
    },
    {
        "file": "readings.png",
        "bg": "#e7eef3",
        "ink": "#14202b",
        "rule": "#1e3a5f",
        "muted": "#3d5164",
        "kicker": "CLIPPINGS",
        "word": "Readings",
        "deck": "Loose pages, off the glass.",
        "folio": "№ 05",
        "lamp": False,
    },
]


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size=size)


def fit(draw: ImageDraw.ImageDraw, text: str, face: Path, start: int, max_w: int, floor: int = 80) -> ImageFont.FreeTypeFont:
    size = start
    while size > floor:
        f = font(face, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 4
    return font(face, floor)


def draw_mark(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, ink: str, paper: str, lamp: str):
    draw.rectangle([x, y, x + size, y + size], fill=ink)
    inset = max(3, size // 16)
    draw.rectangle([x + inset, y + inset, x + size - inset, y + size - inset], outline=paper, width=max(1, size // 40))
    # Block M built from a polygon, scaled from the 80px logo.
    s = size / 80
    def p(px, py):
        return (x + px * s, y + py * s)
    draw.polygon(
        [p(18, 58), p(18, 22), p(24.2, 22), p(40, 44.5), p(55.8, 22), p(62, 22), p(62, 58),
         p(56.4, 58), p(56.4, 33.2), p(40.2, 54.6), p(24, 33.2), p(24, 58)],
        fill=paper,
    )
    r = max(3, int(4 * s))
    cx, cy = p(62, 16)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=lamp)


def render_cover(spec: dict) -> Image.Image:
    img = Image.new("RGB", (1400, 1400), spec["bg"])
    draw = ImageDraw.Draw(img)
    ink, rule, muted = spec["ink"], spec["rule"], spec["muted"]
    draw.rectangle([36, 36, 1363, 1363], outline=ink, width=3)
    draw.rectangle([48, 48, 1351, 1351], outline=ink, width=1)
    draw_mark(draw, 96, 96, 132, ink if spec["bg"] != "#1c140f" else "#f4efe4", spec["bg"] if spec["bg"] != "#1c140f" else "#1c140f", "#d63c2e")
    # When the field is already ink, the mark should be paper with an ink M.
    if spec["bg"] in ("#1c140f", "#2a2118"):
        draw.rectangle([96, 96, 228, 228], fill="#f4efe4")
        draw_mark(draw, 96, 96, 132, "#1c140f", "#f4efe4", "#d63c2e")

    kicker = font(MONO, 28)
    draw.text((260, 118), "MASTHEAD", font=kicker, fill=ink)
    draw.text((260, 158), spec["kicker"], font=kicker, fill=muted)
    if spec["lamp"]:
        draw.ellipse([1188, 124, 1228, 164], fill="#d63c2e")
        draw.text((1248, 132), "ON AIR", font=font(GROTESK_MED, 26), fill=ink)

    word = fit(draw, spec["word"], SERIF, 210, 1160)
    draw.text((96, 430), spec["word"], font=word, fill=ink)
    bbox = draw.textbbox((96, 430), spec["word"], font=word)
    rule_y = bbox[3] + 28
    draw.rectangle([96, rule_y, 96 + 220, rule_y + 14], fill=rule)
    deck = font(SERIF_ITAL, 42)
    draw.text((96, rule_y + 48), spec["deck"], font=deck, fill=muted)
    draw.line([(96, 1248), (1304, 1248)], fill=ink, width=2)
    draw.text((96, 1272), spec["folio"], font=font(MONO, 28), fill=ink)
    draw.text((980, 1272), "PERSONAL PRESS", font=font(MONO, 28), fill=muted)
    return img


def render_icon(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), "#1c140f")
    draw = ImageDraw.Draw(img)
    pad = int(size * 0.08)
    draw_mark(draw, pad, pad, size - pad * 2, "#1c140f", "#f4efe4", "#d63c2e")
    # draw_mark fills its own square; the canvas is already ink, so just center the mark.
    return img


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    PWA.mkdir(parents=True, exist_ok=True)
    for spec in COVERS:
        img = render_cover(spec)
        dest = OUT / spec["file"]
        img.save(dest, "PNG", optimize=True)
        print(dest, dest.stat().st_size)
    for size, name in ((192, "icon-192.png"), (512, "icon-512.png")):
        icon = Image.new("RGB", (size, size), "#1c140f")
        draw = ImageDraw.Draw(icon)
        margin = int(size * 0.12)
        draw_mark(draw, margin, margin, size - margin * 2, "#1c140f", "#f4efe4", "#d63c2e")
        dest = PWA / name
        icon.save(dest, "PNG", optimize=True)
        print(dest, dest.stat().st_size)


if __name__ == "__main__":
    main()
