"""Print-ready rotary dial number cards, 1.5" (38.1 mm) diameter.
Style: Bell System stamped card — exchange name with two large caps,
rest in small caps; number below in stamped gothic digits.

    python3 hardcopy/dialcard.py hardcopy/dial-card-WAverly-7-2004.pdf

Needs reportlab, and Liberation Sans and DejaVu Sans Condensed, found through
fontconfig (fc-match) where they are not at the Debian paths."""
from __future__ import annotations

import os
import random
import subprocess
import sys

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm, inch
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

EXCHANGE = "WAVERLY"          # first two letters large
NUMBER = "7-2004"

# name: (Debian's path, the fontconfig pattern to look for elsewhere)
FONTS = {
    "Goth": ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", "Liberation Sans:bold"),
    "GothR": ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "Liberation Sans:regular"),
    "Cond": ("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf", "DejaVu Sans:condensed"),
}

D = 1.5 * inch
R = D / 2
INK = (0.12, 0.11, 0.10)      # slightly warm black, like old stamp ink

def font_file(path: str, pattern: str) -> str:
    """`path` if it exists, else the file fontconfig matches to `pattern`."""
    if os.path.exists(path):
        return path
    try:
        found = subprocess.run(["fc-match", "-f", "%{file}", pattern],
                               capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        found = ""
    if not found or not found.lower().endswith(".ttf"):
        sys.exit(f"no TrueType font for {pattern!r}: install Liberation Sans and DejaVu Sans")
    return found


def register_fonts() -> None:
    for name, (path, pattern) in FONTS.items():
        pdfmetrics.registerFont(TTFont(name, font_file(path, pattern)))


def solid_text(c: canvas.Canvas, x: float, y: float, text: str, font: str, size: float,
               spacing: float = 0.0) -> None:
    """Clean black type for the exchange name."""
    widths = [pdfmetrics.stringWidth(ch, font, size) for ch in text]
    cx = x - (sum(widths) + spacing * (len(text) - 1)) / 2
    c.setFillColorRGB(0.05, 0.05, 0.05)
    c.setFont(font, size)
    for ch, w in zip(text, widths):
        c.drawString(cx, y, ch)
        cx += w + spacing

def stamped_text(c: canvas.Canvas, x: float, y: float, text: str, font: str, size: float,
                 seed: int, spacing: float = 0.0,
                 bg: tuple[float, float, float] = (1, 1, 1)) -> None:
    """Draw text char by char with a tiny jitter so it reads as hand-stamped."""
    rnd = random.Random(seed)
    widths = [pdfmetrics.stringWidth(ch, font, size) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    cx = x - total / 2
    for ch, w in zip(text, widths):
        c.saveState()
        dx = rnd.uniform(-0.15, 0.15)
        dy = rnd.uniform(-0.3, 0.3)
        rot = rnd.uniform(-1.5, 1.5)
        c.translate(cx + w / 2 + dx, y + dy)
        c.rotate(rot)
        c.setFont(font, size)
        # grey stamp ink (no transparency - some viewers render alpha badly)
        base = rnd.uniform(0.33, 0.42)
        c.setFillColorRGB(base, base, base + 0.02)
        c.drawCentredString(0, 0, ch)
        # clip to the glyph so mottling stays inside the ink
        t = c.beginText(-w / 2, 0)
        t.setFont(font, size)
        t.setTextRenderMode(7)
        t.textOut(ch)
        c.drawText(t)
        c.setFont(font, size)
        for _ in range(int(size * 6)):
            px = rnd.uniform(-w / 2, w / 2)
            py = rnd.uniform(-size * 0.05, size * 0.75)
            g = rnd.uniform(0.50, 0.62)
            c.setFillColorRGB(g, g, g)
            c.circle(px, py, rnd.uniform(0.08, 0.25), stroke=0, fill=1)
        c.setFillColorRGB(*bg)
        for _ in range(int(size * 8)):
            px = rnd.uniform(-w / 2, w / 2)
            py = rnd.uniform(-size * 0.05, size * 0.75)
            c.circle(px, py, rnd.uniform(0.06, 0.2), stroke=0, fill=1)
        c.restoreState()
        cx += w + spacing

def card(c: canvas.Canvas, cx: float, cy: float, seed: int,
         tint: tuple[float, float, float] | None = None, guides: bool = True) -> None:
    c.saveState()
    c.translate(cx, cy)
    if tint:
        c.setFillColorRGB(*tint)
        c.setStrokeColorRGB(*tint)
        c.circle(0, 0, R, stroke=0, fill=1)
    if guides:
        # faint cut circle + crop ticks (outside the punch) for lining up
        c.setStrokeColorRGB(0.72, 0.72, 0.72)
        c.setLineWidth(0.25)
        c.circle(0, 0, R, stroke=1, fill=0)
        for ax, ay in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            c.line(ax * (R + 1 * mm), ay * (R + 1 * mm), ax * (R + 3.5 * mm), ay * (R + 3.5 * mm))

    # --- exchange name: "WA" big, "VERLY" small caps, baseline aligned ---
    big, small = EXCHANGE[:2], EXCHANGE[2:]
    bsize, ssize = 16.5, 8.4
    sp_b, sp_s = 0.3, 0.45
    wb = sum(pdfmetrics.stringWidth(ch, "GothR", bsize) for ch in big) + sp_b
    ws = sum(pdfmetrics.stringWidth(ch, "Goth", ssize) for ch in small) + sp_s * (len(small) - 1)
    gap = 0.6
    total = wb + gap + ws
    x0 = -total / 2
    y_ex = 2.8 * mm
    solid_text(c, x0 + wb / 2, y_ex, big, "GothR", bsize, sp_b)
    solid_text(c, x0 + wb + gap + ws / 2, y_ex, small, "Goth", ssize, sp_s)

    # --- number ---
    stamped_text(c, 0, -6.4 * mm, NUMBER, "Cond", 13.5, seed + 3, spacing=1.1, bg=tint or (1, 1, 1))
    c.restoreState()

def sheet(path: str) -> None:
    c = canvas.Canvas(path, pagesize=letter)
    W, H = letter
    c.setTitle(f"Dial card {EXCHANGE} {NUMBER}")
    c.setFont("GothR", 8)
    c.setFillColorRGB(0.45, 0.45, 0.45)
    c.drawString(0.75 * inch, H - 0.6 * inch,
                 f"Dial number cards  {EXCHANGE[:2]}{EXCHANGE[2:].lower()} {NUMBER}  "
                 f"- print at 100% / actual size, no scaling. Circle = 1.5 in punch.")
    c.setStrokeColorRGB(0.6, 0.6, 0.6); c.setLineWidth(0.3)
    # 1-inch scale check
    c.line(0.75 * inch, H - 0.8 * inch, 1.75 * inch, H - 0.8 * inch)
    c.line(0.75 * inch, H - 0.75 * inch, 0.75 * inch, H - 0.85 * inch)
    c.line(1.75 * inch, H - 0.75 * inch, 1.75 * inch, H - 0.85 * inch)
    c.drawString(1.85 * inch, H - 0.83 * inch, "1 inch")

    cols, rows = 4, 4
    pitch = 1.85 * inch
    x_start = (W - (cols - 1) * pitch) / 2
    y_start = H - 1.6 * inch - R
    cream = (0.93, 0.87, 0.70)
    n = 0
    for r in range(rows):
        for col in range(cols):
            tint = cream if r >= 2 else None
            card(c, x_start + col * pitch, y_start - r * pitch, seed=n * 7 + 3, tint=tint)
            n += 1
    c.setFillColorRGB(0.45, 0.45, 0.45); c.setFont("GothR", 8)
    c.drawString(0.75 * inch, y_start - 3 * pitch - R - 0.35 * inch,
                 "Rows 1-2: plain, for cream or white card stock.   Rows 3-4: aged tint printed, for white stock.")
    c.save()

def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: dialcard.py OUT.pdf", file=sys.stderr)
        return 2
    register_fonts()
    sheet(args[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
