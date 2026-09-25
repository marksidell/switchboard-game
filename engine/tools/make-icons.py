#!/usr/bin/env python3
"""Draw the status page's app icons.

A jackfield: one cord patched between two jacks, one jack calling. The colours
are the page's own, from web/style.css, so the icon on the Home Screen and the
board inside it agree - change a colour there and change it here.

    python3 engine/tools/make-icons.py          # rewrite engine/web/icons/
    python3 engine/tools/make-icons.py --out /tmp/try

Needs Pillow. The icons are committed, so this is only run when the drawing
changes; nothing in the build calls it. After running it, bump the page's
build id the usual way (`make -C host sbgame-web`) or a browser that has the
old icon cached will keep showing it.
"""

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw

# ---- the page's palette (web/style.css :root) -----------------------------
BG        = (22, 24, 28)        # --bg
JACK      = (43, 48, 56)        # --idle
RING      = (153, 160, 173)     # --dim
CONNECTED = (47, 133, 90)       # --connected
CALLING   = (183, 121, 31)      # --calling

# ---- the drawing, in fractions of the canvas ------------------------------
# Fractions rather than pixels so one description serves every size. The
# figures are the 512px drawing divided by 512.
COLS, ROWS   = 4, 3
JACK_R       = 38 / 512         # outer radius, ring included
RING_W       = 6 / 512
CORD_W       = 12 / 512
PITCH_X      = 128 / 512        # centre to centre
PITCH_Y      = 142 / 512
CORD_SAG     = 0.08             # how far the cord bows below the straight line,
                                # as a fraction of its own length

# Which jacks are doing what, as (column, row) from the top left.
PATCHED = ((1, 0), (2, 1))      # the two ends of the cord
CALLS   = ((0, 2),)             # ringing, unanswered

# A maskable icon is cropped to a circle or a squircle by the platform, and
# only the middle 80% is guaranteed to survive. Shrink the drawing into that
# so the corner jacks are not sliced off.
MASKABLE_SCALE = 0.72

SS = 4                          # supersampling, for edges the 1x draw cannot give


def draw(size, scale=1.0):
    """The jackfield, on a `size` square, the drawing scaled about the centre."""
    s = size * SS
    img = Image.new("RGB", (s, s), BG)
    d = ImageDraw.Draw(img)

    r       = JACK_R * s * scale
    ring_w  = max(1, round(RING_W * s * scale))
    cord_w  = max(1, round(CORD_W * s * scale))
    pitch_x = PITCH_X * s * scale
    pitch_y = PITCH_Y * s * scale

    # Centre the grid on the canvas. The grid's extent is the distance between
    # the outermost centres, so the jacks' own radius sits outside it.
    x0 = s / 2 - pitch_x * (COLS - 1) / 2
    y0 = s / 2 - pitch_y * (ROWS - 1) / 2

    def centre(col, row):
        return x0 + col * pitch_x, y0 + row * pitch_y

    # The cord first, so the two jacks it lands on are drawn over its ends and
    # it appears to go into them rather than to stop on top of them.
    (ax, ay), (bx, by) = (centre(*PATCHED[0]), centre(*PATCHED[1]))
    length = math.hypot(bx - ax, by - ay)
    # A quadratic Bezier, its control point pushed straight down: a cord hangs
    # under its own weight, and a straight line between two jacks reads as a
    # wire diagram rather than as a switchboard.
    cx, cy = (ax + bx) / 2, (ay + by) / 2 + CORD_SAG * length * 2
    pts = []
    for i in range(65):
        t = i / 64
        u = 1 - t
        pts.append((u * u * ax + 2 * u * t * cx + t * t * bx,
                    u * u * ay + 2 * u * t * cy + t * t * by))
    d.line(pts, fill=CONNECTED, width=cord_w, joint="curve")

    for row in range(ROWS):
        for col in range(COLS):
            fill = JACK
            if (col, row) in PATCHED: fill = CONNECTED
            if (col, row) in CALLS:   fill = CALLING
            x, y = centre(col, row)
            d.ellipse((x - r, y - r, x + r, y + r), fill=fill,
                      outline=RING, width=ring_w)

    return img.resize((size, size), Image.LANCZOS)


def main():
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=here.parent / "web" / "icons",
                    help="directory to write into (default: engine/web/icons)")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    # The three the manifest names, and the one iOS reads instead of it. Each is
    # drawn at its own size rather than downscaled from 512: at 180px a 6px ring
    # becomes 2px, and it is better to draw 2px than to resample into it.
    out = {
        "icon-192.png":          draw(192),
        "icon-512.png":          draw(512),
        "maskable-512.png":      draw(512, MASKABLE_SCALE),
        "apple-touch-icon.png":  draw(180),
    }
    for name, img in out.items():
        img.save(args.out / name, optimize=True)
        print(f"{args.out / name}  {img.size[0]}x{img.size[1]}")


if __name__ == "__main__":
    main()
