"""The operator's two 5 x 7 in directory cards: the guest list and outside numbers.

    python3 hardcopy/cards.py script.yml hardcopy/cards.pdf

Both cards on one US Letter page, landscape; print at 100%. Needs pycairo, PyYAML
and libfontconfig. The typeface is Special Elite (hardcopy/fonts, Apache 2.0),
drawn from real typewritten text; each character is struck with a little wobble
and uneven ink, fixed by a seed so the cards come out the same every time.
"""
import csv, ctypes, math, os, random, sys
import cairo, yaml

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_FILE = os.path.join(HERE, "fonts", "SpecialElite-Regular.ttf")
FONT = "Special Elite"
EXCHANGES = os.path.join(HERE, "seattle-exchanges.csv")
DATE = "September 29"

# How each outside number is typed. Keyed by the outside: id.
OUTSIDE = {
    "operator":     "Operator (Long Distance)",
    "pharmacy":     "Ballard Pharmacy",
    "canlis":       "Canlis",
    "florist":      "Harbor Florist",
    "paramount":    "Paramount Theatre",
    "placepigalle": "Place Pigalle",
    "rays":         "Ray's Boathouse",
    "police":       "Police",
    "times":        "Seattle Times",
    "taxi":         "Shilshole Cab",
    "pizza":        "Sunny Hill Pizza",
    "swedish":      "Swedish Hospital",
    "v16company":   "V16 Co. of America",
    "ferries":      "Wash. State Ferries",
    "westernunion": "Western Union",
}

IN = 72.0
CARD_W, CARD_H = 5 * IN, 7 * IN
PAGE_W, PAGE_H = 11 * IN, 8.5 * IN
SIZE = 11.5
MARGIN = 0.45 * IN
LEAD = 1.6 * SIZE                      # a line and a half, near enough
INK = (0.13, 0.12, 0.14)


def register_font():
    fc = ctypes.CDLL("libfontconfig.so.1")
    fc.FcConfigAppFontAddFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    if not fc.FcConfigAppFontAddFile(None, FONT_FILE.encode()):
        sys.exit(f"cannot load {FONT_FILE}")


def guests(script):
    """(name, room label) for every jack with a guest:, by surname."""
    def surname(name):
        words = name.split()
        return words[-2] if words[-1] == "Family" else words[-1]
    rows = [(j["guest"], str(j["label"])) for j in script["jacks"] if j.get("guest")]
    return sorted(rows, key=lambda r: (surname(r[0]), r[0]))


def exchanges():
    """"782" -> "SU2": the exchange's two capital letters and its digit, as a
    phone book of 1958 prints them."""
    out = {}
    with open(EXCHANGES, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name, digit = row["Exchange"].split()
            out[row["Numeric"]] = "".join(c for c in name if c.isupper()) + digit
    return out


def outside(script):
    ex = exchanges()
    rows = []
    for oid, o in script["outside"].items():
        if oid not in OUTSIDE:
            print(f"warning: outside {oid} has no entry in OUTSIDE")
            continue
        number = str(o["number"])
        if number != "0":
            prefix, _, line = number.partition("-")
            if prefix not in ex:
                sys.exit(f"outside {oid}: {number} is not a Seattle exchange")
            number = f"{ex[prefix]}-{line}"
        rows.append((OUTSIDE[oid], number))
    op = [r for r in rows if r[1] == "0"]
    return op + sorted(r for r in rows if r[1] != "0")


class Typewriter:
    """Monospaced strikes on a card, with the faults of a used machine."""

    def __init__(self, cr, seed):
        self.cr = cr
        self.rng = random.Random(seed)
        cr.select_font_face(FONT)
        cr.set_font_size(SIZE)
        self.pitch = cr.text_extents("M").x_advance
        # a worn machine: some typebars sit a little high or low, every time
        bars = random.Random(1951)
        self.bar = {c: (bars.gauss(0, 0.18), bars.gauss(0, 0.25))
                    for c in map(chr, range(33, 127))}

    def cols(self, width):
        return int(width // self.pitch)

    def type(self, x, y, text):
        cr, rng = self.cr, self.rng
        # the carriage wanders a hair along the line
        drift = rng.gauss(0, 0.2)
        for i, c in enumerate(text):
            if c == " ":
                continue
            bx, by = self.bar.get(c, (0, 0))
            dx = bx + rng.gauss(0, 0.12)
            dy = by + drift + rng.gauss(0, 0.15)
            ink = min(1.0, max(0.55, rng.gauss(0.86, 0.09)))
            rot = math.radians(rng.gauss(0, 0.5))
            cw = cr.text_extents(c).x_advance
            cr.save()
            cr.translate(x + i * self.pitch + (self.pitch - cw) / 2 + dx, y + dy)
            cr.rotate(rot)
            cr.set_source_rgba(*INK, ink)
            cr.move_to(0, 0); cr.show_text(c)
            if rng.random() < 0.08:          # a key that bounced: a faint second strike
                cr.set_source_rgba(*INK, 0.25)
                cr.move_to(rng.uniform(-0.4, 0.4), rng.uniform(-0.3, 0.3)); cr.show_text(c)
            cr.restore()

    def centred(self, x, y, width, text):
        n = self.cols(width)
        self.type(x + (n - len(text)) // 2 * self.pitch, y, text)

    def leader(self, x, y, width, left, right):
        n = self.cols(width)
        dots = n - len(left) - len(right) - 2
        if dots < 3:
            sys.exit(f"too long for the card: {left!r} {right!r}")
        self.type(x, y, f"{left} {'.' * dots} {right}")


def card(cr, tw, x, y, title, rows):
    w = CARD_W - 2 * MARGIN
    cx = x + MARGIN
    ty = y + MARGIN + SIZE
    for t in title:
        tw.centred(cx, ty, w, t)
        ty += LEAD
    rule = max(len(t) for t in title)
    tw.centred(cx, ty - LEAD + 3, w, "_" * rule)     # underscored, as a typist would
    ty += LEAD
    for left, right in rows:
        tw.leader(cx, ty, w, left, right)
        ty += LEAD
    if ty - LEAD > y + CARD_H - MARGIN:
        sys.exit(f"{title[0]}: {len(rows)} lines do not fit the card")


def cut_marks(cr, x, y, w, h, l=0.2 * IN, off=0.06 * IN):
    cr.set_line_width(0.3); cr.set_source_rgb(0, 0, 0)
    for cx in (x, x + w):
        for cy in (y, y + h):
            dx = -1 if cx == x else 1
            dy = -1 if cy == y else 1
            cr.move_to(cx + dx * off, cy); cr.rel_line_to(dx * l, 0)
            cr.move_to(cx, cy + dy * off); cr.rel_line_to(0, dy * l)
    cr.stroke()


def main():
    script = yaml.safe_load(open(sys.argv[1]))
    register_font()
    surf = cairo.PDFSurface(sys.argv[2], PAGE_W, PAGE_H)
    cr = cairo.Context(surf)
    tw = Typewriter(cr, seed=929)
    hotel = script["setting"]["hotel"]

    gap = 0.5 * IN
    x0 = (PAGE_W - 2 * CARD_W - gap) / 2
    y0 = (PAGE_H - CARD_H) / 2
    for i in range(2):
        x = x0 + i * (CARD_W + gap)
        cr.set_source_rgb(0.8, 0.8, 0.8); cr.set_line_width(0.25)
        cr.rectangle(x, y0, CARD_W, CARD_H); cr.stroke()
        cut_marks(cr, x, y0, CARD_W, CARD_H)

    card(cr, tw, x0, y0, [f"{hotel.upper()} GUEST LIST", DATE],
         guests(script))
    card(cr, tw, x0 + CARD_W + gap, y0, ["OUTSIDE NUMBERS"], outside(script))

    cr.select_font_face("Nimbus Sans"); cr.set_font_size(7); cr.set_source_rgb(0, 0, 0)
    cr.move_to(x0, PAGE_H - 0.3 * IN)
    cr.show_text("Print at 100% / actual size, landscape. Cards 5 x 7 in.")
    surf.finish()


if __name__ == "__main__":
    main()
