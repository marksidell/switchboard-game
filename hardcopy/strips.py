"""Designation strips for the 551: 9.75in x 7.5mm, jacks at 1in pitch.

    python3 hardcopy/strips.py script.yml hardcopy/strips.pdf

Print landscape at 100%. Needs pycairo, PyYAML and the URW C059 font."""
import sys, cairo, yaml

IN = 72.0
MM = IN / 25.4
STRIP_W, STRIP_H = 9.75 * IN, 7.5 * MM
PITCH = 1.0 * IN
MARGIN = (STRIP_W - 9 * PITCH) / 2          # 0.375in to the first jack centre
SIZE = 12.5                                  # pt; cap height ~3.4mm
MAX_W = 0.88 * PITCH                         # label may not run into its neighbour
FONT = "C059"                                # URW Century Schoolbook

script = yaml.safe_load(open(sys.argv[1]))
labels = {j["jack"]: str(j["label"]) for j in script["jacks"]}
rows = [range(21, 31), range(11, 21), range(1, 11), range(101, 111)]   # top to bottom on the board
# Trunk row: trunks 1-8 at the first eight positions; the last two positions have no jacks.
labels.update({100 + t: f"Trunk {t}" for t in range(1, 9)})

PAGE_W, PAGE_H = 11 * IN, 8.5 * IN
surf = cairo.PDFSurface(sys.argv[2], PAGE_W, PAGE_H)
cr = cairo.Context(surf)
cr.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
cr.set_font_size(SIZE)
cap = cr.text_extents("H").height

x0 = (PAGE_W - STRIP_W) / 2
gap = 0.5 * IN
y0 = (PAGE_H - 4 * STRIP_H - 3 * gap) / 2

def cut_marks(x, y, w, h, l=0.2 * IN, off=0.06 * IN):
    cr.set_line_width(0.3); cr.set_source_rgb(0, 0, 0)
    for cx in (x, x + w):
        for cy in (y, y + h):
            dx = -1 if cx == x else 1
            dy = -1 if cy == y else 1
            cr.move_to(cx + dx * off, cy); cr.rel_line_to(dx * l, 0)
            cr.move_to(cx, cy + dy * off); cr.rel_line_to(0, dy * l)
    cr.stroke()

for r, jacks in enumerate(rows):
    y = y0 + r * (STRIP_H + gap)
    # hairline outline, light grey, to cut on or just inside
    cr.set_source_rgb(0.75, 0.75, 0.75); cr.set_line_width(0.25)
    cr.rectangle(x0, y, STRIP_W, STRIP_H); cr.stroke()
    cut_marks(x0, y, STRIP_W, STRIP_H)
    if jacks is None:
        continue
    cr.set_source_rgb(0, 0, 0)
    for i, j in enumerate(jacks):
        text = labels.get(j, "")
        if not text:
            continue
        ext = cr.text_extents(text)
        lim = 0.78 * IN if i in (0, 9) else MAX_W   # end jacks sit 0.375in from the edge
        sx = min(1.0, lim / ext.x_advance)
        cx = x0 + MARGIN + i * PITCH
        half = ext.x_advance * sx / 2
        edge = 0.06 * IN                     # keep the end labels on the strip
        cx = min(max(cx, x0 + edge + half), x0 + STRIP_W - edge - half)
        base = y + STRIP_H / 2 + cap / 2
        cr.save()
        cr.translate(cx, base); cr.scale(sx, 1)
        cr.move_to(-ext.x_advance / 2, 0); cr.show_text(text)
        cr.restore()
        if sx < 1:
            print(f"jack {j} {text!r}: condensed to {sx:.0%}")

# scale check
cr.set_source_rgb(0, 0, 0); cr.set_line_width(0.5)
yb = PAGE_H - 0.45 * IN
cr.move_to(x0, yb); cr.rel_line_to(4 * IN, 0)
for k in range(5):
    cr.move_to(x0 + k * IN, yb - 4); cr.rel_line_to(0, 8)
cr.stroke()
cr.select_font_face("Nimbus Sans"); cr.set_font_size(7)
cr.move_to(x0 + 4.1 * IN, yb + 2.5)
cr.show_text("4 in — print at 100% / actual size, landscape. Strips 9.75 in x 7.5 mm, jacks 1 in apart. "
             "Rows top to bottom: 21-30, 11-20, 1-10, trunks.")
surf.finish()
