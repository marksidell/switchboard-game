"""The headset's electret transmitter circuit, drawn with schemdraw.

    python3 hardware/electret_transmitter.py hardware/electret_transmitter.svg

Writes SVG, or PNG for a name ending .png. Needs schemdraw."""
from __future__ import annotations

import sys

import schemdraw
import schemdraw.elements as elm

Point = tuple[float, float]


def draw() -> schemdraw.Drawing:
    schemdraw.config(fontsize=10, unit=2.5, lw=1.2)
    YA, YG = 10.0, 0.0
    d = schemdraw.Drawing(show=False)

    def wire(p: Point, q: Point) -> None:
        d.add(elm.Line().at(p).to(q))

    def dot(p: Point) -> None:
        d.add(elm.Dot().at(p))

    def gnd(p: Point) -> None:
        d.add(elm.Ground().at(p))

    def txt(p: Point, s: str, **kw: object) -> None:
        kw.setdefault('fontsize', 10)
        d.add(elm.Label().at(p).label(s, **kw))

    # ---------------- input, bridge ----------------
    br = d.add(elm.Ic(pins=[elm.IcPin(name='~', side='left', slot='2/2', anchorname='ac1'),
                            elm.IcPin(name='~', side='left', slot='1/2', anchorname='ac2'),
                            elm.IcPin(name='+', side='right', slot='2/2', anchorname='p'),
                            elm.IcPin(name='−', side='right', slot='1/2', anchorname='n')],
                      size=(2.2, 3), pinspacing=1.5, edgepadW=0.6,
                      label='BR1\n2× BAT54S')
               .at((0, 4.0)).anchor('ac2'))
    d.add(elm.Line().at(br.ac1).left(1.0))
    d.add(elm.Dot(open=True).label('Tx a', 'left'))
    d.add(elm.Line().at(br.ac2).left(1.0))
    d.add(elm.Dot(open=True).label('Tx b', 'left'))
    txt((-0.5, 8.0), 'transmitter feed\nfrom switchboard\n(either polarity)', fontsize=9)

    xr = br.p[0] + 0.8
    wire(br.p, (xr, br.p[1]))
    wire((xr, br.p[1]), (xr, YA))
    wire(br.n, (xr, br.n[1]))
    wire((xr, br.n[1]), (xr, YG))

    xq, xm = xr + 6.0, xr + 8.2
    wire((xr, YA), (13.0, YA))
    wire((xr, YG), (xm, YG))
    txt((xr - 0.35, YA + 0.1), 'A')
    txt((xr - 0.35, YG - 0.1), 'G')

    # D5, C1 across the bridge output
    x = xr + 1.8
    dot((x, YA)); dot((x, YG))
    d.add(elm.Zener().at((x, YG)).to((x, YA)).label('D5\n6V2', loc='bottom'))
    x = xr + 3.6
    dot((x, YA)); dot((x, YG))
    d.add(elm.Capacitor().at((x, YA)).to((x, YG)).label('C1\n10n', loc='bottom'))

    # ---------------- Vbe multiplier ----------------
    dot((xq, YA))
    r4 = d.add(elm.Resistor().at((xq, YA)).down(2.5).label('R4\n47Ω\n1206', loc='bottom'))
    yC = r4.end[1]
    q2 = d.add(elm.BjtNpn(circle=True).theta(180).flip().anchor('collector').at((xq, yC))
               )
    txt((xq - 1.3, yC - 0.7), 'Q2\nBC337-40', fontsize=10)
    wire(q2.emitter, (xq, YG))
    dot((xq, YG))
    dot((xq, yC))
    txt((xq - 0.4, yC + 0.1), 'C')
    wire((xq, yC), (xm, yC))
    r2 = d.add(elm.Resistor().at((xm, yC)).down(2.3).label('R2\n2k2', loc='bottom'))
    yB = r2.end[1]
    xb = xq + 1.3
    wire(q2.base, (xb, q2.base[1]))
    wire((xb, q2.base[1]), (xb, yB))
    wire((xb, yB), (xm, yB))
    dot((xm, yB))
    txt((xm - 0.4, yB + 0.1), 'B')
    d.add(elm.Resistor().at((xm, yB)).to((xm, YG)).label('R3\n1k0', loc='bottom'))
    dot((xm, YG))

    # ---------------- supply filter ----------------
    r5 = d.add(elm.Resistor().at((13.0, YA)).right(2.5).label('R5 330Ω'))
    xV1 = r5.end[0]
    dot((xV1, YA))
    txt((xV1, YA + 0.7), 'V1 ≈ 3.6 V')
    c3 = d.add(elm.Capacitor(polar=True).at((xV1, YA)).down(2.2).label('C3\n100µ', loc='bottom'))
    gnd(c3.end)
    wire((xV1, YA), (xV1 + 1.0, YA))
    r6 = d.add(elm.Resistor().right(2.5).label('R6 1k'))
    xV2 = r6.end[0]
    dot((xV2, YA))
    txt((xV2, YA + 0.7), 'V2')
    c4 = d.add(elm.Capacitor(polar=True).at((xV2, YA)).down(2.2).label('C4\n47µ', loc='bottom'))
    gnd(c4.end)
    xRL = xV2 + 2.0
    wire((xV2, YA), (xRL, YA))
    rl = d.add(elm.Resistor().at((xRL, YA)).down(2.5).label('RL\n2k2', loc='bottom'))
    yM = rl.end[1]
    dot((xRL, yM))

    # ---------------- preamp ----------------
    yO = 3.0
    op = d.add(elm.Opamp(leads=True).left().anchor('out').at((xm + 5.5, yO)))
    txt((op.center[0], op.center[1]), 'U1\nMCP6001\n(on V1)', fontsize=9)

    # Rin, C7 from output to base node B
    rin = d.add(elm.Resistor().at((xm, yB)).right(2.2).label('Rin 4k7'))
    c7 = d.add(elm.Capacitor(polar=True).right(2.0).reverse().label('C7 10µ'))
    wire(c7.end, (op.out[0], yB))
    wire((op.out[0], yB), op.out)

    # + input from capsule node via C5
    c5 = d.add(elm.Capacitor().at((xRL, yM)).down(2.0).label('C5 1µ', loc='bottom'))
    wire(c5.end, (xRL, op.in2[1]))
    wire((xRL, op.in2[1]), op.in2)
    dot((xRL, op.in2[1]))
    r7 = d.add(elm.Resistor().at((xRL, op.in2[1])).right(2.5).label('R7 100k'))
    xVR = r7.end[0]
    dot((xVR, op.in2[1]))
    txt((xVR + 0.1, op.in2[1] + 0.45), 'VREF', fontsize=9, halign='left')
    r9 = d.add(elm.Resistor().at((xVR, op.in2[1])).down(2.2).label('R9\n100k', loc='bottom'))
    gnd(r9.end)
    xc6 = xVR + 1.8
    wire((xVR, op.in2[1]), (xc6, op.in2[1]))
    c6 = d.add(elm.Capacitor(polar=True).at((xc6, op.in2[1])).down(2.2).label('C6\n10µ', loc='bottom'))
    gnd(c6.end)
    dot((xc6, op.in2[1]))
    xr8 = xc6 + 1.8
    wire((xc6, op.in2[1]), (xr8, op.in2[1]))
    d.add(elm.Resistor().at((xr8, op.in2[1])).up(1.5).label('R8\n100k', loc='bottom'))
    d.add(elm.Vdd().label('V1'))

    # − input: Rg + Cg to ground; Rf || Cf to output, below the op amp
    xI, yI = op.in1
    xn = xI + 0.8
    wire(op.in1, (xn, yI))
    rg = d.add(elm.Resistor().at((xn, yI)).down(2.0).label('Rg 2k2 *', loc='bottom'))
    cg = d.add(elm.Capacitor().down(1.5).label('Cg 470n', loc='bottom'))
    gnd(cg.end)
    dot((xI, yI))
    xo = op.out[0] - 0.6
    yfb = yI - 1.0
    yfc = yfb - 1.6
    wire((xI, yI), (xI, yfb))
    dot((xI, yfb))
    d.add(elm.Resistor().at((xI, yfb)).to((xo, yfb)).label('Rf 100k', loc='top'))
    wire((xI, yfb), (xI, yfc))
    d.add(elm.Capacitor().at((xI, yfc)).to((xo, yfc)).label('Cf 470p', loc='bottom'))
    wire((xo, yfc), (xo, yfb))
    dot((xo, yfb))
    wire((xo, yfb), (xo, yO))
    wire((xo, yO), op.out)
    dot(op.out)

    # ---------------- cord and capsule ----------------
    xJ = xr8 + 2.3
    wire((xRL, yM), (xJ, yM))
    d.add(elm.Dot(open=True).at((xJ, yM)))
    xmic = xJ + 2.5
    wire((xJ, yM), (xmic, yM))
    mic = d.add(elm.Mic().at((xmic, yM)).left().anchor('in1'))
    txt((xmic + 2.4, yM - 0.3), 'MIC\nEM-6027N\nnoise-cancelling', fontsize=10)
    ymr = yM - 1.6
    wire(mic.in2, (mic.in2[0], ymr))
    wire((mic.in2[0], ymr), (xJ, ymr))
    d.add(elm.Dot(open=True).at((xJ, ymr)))
    wire((xJ, ymr), (xJ - 0.8, ymr))
    gnd((xJ - 0.8, ymr))
    d.add(elm.Line(ls='--', color='gray').at((xJ, YA + 1.6)).to((xJ, ymr - 1.6)))
    txt((xJ - 1.2, YA + 1.9), 'board', fontsize=9, color='gray')
    txt((xJ + 1.4, YA + 1.9), 'headset', fontsize=9, color='gray')
    txt((xJ + 1.3, yM + 0.9), 'transmitter pair\nin headset cord', fontsize=8)

    txt((xr, -3.6), '* Rg selected on the bench, 1k5–4k7 (U1 gain 22–68), to match the carbon element\'s level on the tap channel.\n'
        'Q2 holds C–G at ≈ 2.1–2.4 V; R4 gives the element ≈ 50 Ω source impedance, like carbon.', fontsize=9, halign='left')

    return d


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: electret_transmitter.py OUT.svg|OUT.png", file=sys.stderr)
        return 2
    d = draw()
    if args[0].endswith('.png'):
        d.save(args[0], dpi=110)
    else:
        d.save(args[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
