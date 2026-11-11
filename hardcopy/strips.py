"""Designation strips for the 551: 9.75in x 7.5mm, jacks at 1in pitch.

    python3 hardcopy/strips.py script.yml hardcopy/strips.pdf

Print landscape at 100%; on the Brother MFC-9330CDW, at 105% (hardcopy/README.md).
Needs pycairo, ruamel.yaml (for the script loader, tts/script.py) and the URW
C059 font."""
from __future__ import annotations

import sys
from pathlib import Path

import cairo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tts.script import ScriptError, load  # noqa: E402

IN = 72.0
MM = IN / 25.4
STRIP_W, STRIP_H = 9.75 * IN, 7.5 * MM
PITCH = 1.0 * IN
MARGIN = (STRIP_W - 9 * PITCH) / 2          # 0.375in to the first jack centre
SIZE = 12.5                                  # pt; cap height ~3.4mm
MAX_W = 0.88 * PITCH                         # label may not run into its neighbour
FONT = "C059"                                # URW Century Schoolbook
PAGE_W, PAGE_H = 11 * IN, 8.5 * IN
# Top to bottom on the board; trunks are 101-108 here. The trunk row's last
# two positions have no jacks.
ROWS = [range(21, 31), range(11, 21), range(1, 11), range(101, 111)]
# Hard against the left and top, not centred: a printer that fits the page to
# its printable area can then be scaled back up to 100% without the right-hand
# end running off the paper.
X0 = 0.3 * IN
GAP = 0.5 * IN
Y0 = 0.6 * IN


def cut_marks(cr: cairo.Context, x: float, y: float, w: float, h: float,
              l: float = 0.2 * IN, off: float = 0.06 * IN) -> None:
    # Marks above and below each corner only, for the strip's ends: none
    # out past the ends, which would keep the sheet 0.37in from the paper's edge.
    cr.set_line_width(0.3); cr.set_source_rgb(0, 0, 0)
    for cx in (x, x + w):
        for cy in (y, y + h):
            dy = -1 if cy == y else 1
            cr.move_to(cx, cy + dy * off); cr.rel_line_to(0, dy * l)
    cr.stroke()


def strip(cr: cairo.Context, y: float, jacks: range, labels: dict[int, str], cap: float) -> None:
    # hairline outline, light grey, to cut on or just inside
    cr.set_source_rgb(0.75, 0.75, 0.75); cr.set_line_width(0.25)
    cr.rectangle(X0, y, STRIP_W, STRIP_H); cr.stroke()
    cut_marks(cr, X0, y, STRIP_W, STRIP_H)
    cr.set_source_rgb(0, 0, 0)

    # One size per strip: the largest, up to SIZE, at which every label fits.
    def lim(i: int) -> float:
        return 0.78 * IN if i in (0, 9) else MAX_W   # end jacks sit 0.375in from the edge
    cr.set_font_size(SIZE)
    k = min([1.0] + [lim(i) / cr.text_extents(labels[j]).x_advance
                     for i, j in enumerate(jacks) if labels.get(j)])
    cr.set_font_size(SIZE * k)
    if k < 1:
        print(f"jacks {jacks.start}-{jacks.stop - 1}: {SIZE * k:.2f} pt")
    for i, j in enumerate(jacks):
        text = labels.get(j, "")
        if not text:
            continue
        ext = cr.text_extents(text)
        cx = X0 + MARGIN + i * PITCH
        half = ext.x_advance / 2
        edge = 0.06 * IN                     # keep the end labels on the strip
        cx = min(max(cx, X0 + edge + half), X0 + STRIP_W - edge - half)
        base = y + STRIP_H / 2 + cap * k / 2
        cr.move_to(cx - half, base); cr.show_text(text)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: strips.py SCRIPT.yml OUT.pdf", file=sys.stderr)
        return 2
    try:
        script = load(args[0])
    except ScriptError as e:
        print(f"{e.path}: {len(e.failures)} problem(s)", file=sys.stderr)
        for f in e.failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    labels = {j["jack"]: j["label"] for j in script.jacks}
    labels.update({100 + t: f"Trunk {t}" for t in range(1, 9)})

    surf = cairo.PDFSurface(args[1], PAGE_W, PAGE_H)
    cr = cairo.Context(surf)
    cr.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(SIZE)
    cap = cr.text_extents("H").height
    for r, jacks in enumerate(ROWS):
        strip(cr, Y0 + r * (STRIP_H + GAP), jacks, labels, cap)

    # scale check
    cr.set_source_rgb(0, 0, 0); cr.set_line_width(0.5)
    yb = Y0 + 4 * STRIP_H + 3 * GAP + 0.6 * IN     # under the strips
    cr.move_to(X0, yb); cr.rel_line_to(4 * IN, 0)
    for k in range(5):
        cr.move_to(X0 + k * IN, yb - 4); cr.rel_line_to(0, 8)
    cr.stroke()
    cr.select_font_face("Nimbus Sans"); cr.set_font_size(7)
    cr.move_to(X0 + 4.1 * IN, yb - 1)
    cr.show_text("4 in — print at 100% / actual size, landscape. Strips 9.75 in x 7.5 mm, jacks 1 in apart.")
    cr.move_to(X0 + 4.1 * IN, yb + 7)
    cr.show_text("Rows top to bottom: 21-30, 11-20, 1-10, trunks. On the Brother MFC-9330CDW, print at 105%.")
    surf.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
