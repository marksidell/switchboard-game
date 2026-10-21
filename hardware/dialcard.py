"""Print-ready rotary dial number cards, 1.5" (38.1 mm) diameter.
Style: Bell System stamped card — exchange name with two large caps,
rest in small caps; number below in stamped gothic digits."""
import random
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm, inch
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

EXCHANGE = "WAVERLY"          # first two letters large
NUMBER = "7-2004"

pdfmetrics.registerFont(TTFont("Goth", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("GothR", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"))
pdfmetrics.registerFont(TTFont("Cond", "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf"))

D = 1.5 * inch
R = D / 2
INK = (0.12, 0.11, 0.10)      # slightly warm black, like old stamp ink

def solid_text(c, x, y, text, font, size, spacing=0.0):
    """Clean black type for the exchange name."""
    widths = [pdfmetrics.stringWidth(ch, font, size) for ch in text]
    cx = x - (sum(widths) + spacing * (len(text) - 1)) / 2
    c.setFillColorRGB(0.05, 0.05, 0.05)
    c.setFont(font, size)
    for ch, w in zip(text, widths):
        c.drawString(cx, y, ch)
        cx += w + spacing

def stamped_text(c, x, y, text, font, size, seed, spacing=0.0, bg=(1, 1, 1)):
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

def card(c, cx, cy, seed, tint=None, guides=True):
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

def sheet(path):
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

if __name__ == "__main__":
    sheet("/home/claude/dial-card-WAverly-7-2004.pdf")
