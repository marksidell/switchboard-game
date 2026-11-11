#!/usr/bin/env python3
"""Receiver low-pass: response of the design on the sheet, against the measurements.

    from switchboard ──[L1 ∥ C9]──┬──[L2 ∥ C11]──┬── to receiver
                                  C10            C12
    ──────────────────────────────┴──────────────┴──

Load is the receiver on the ear (measurements/receiver_on_ear.txt); source is the
operator circuit seen from the receiver conductors (measurements/source_500set.txt).
Inductors are modelled as L plus the datasheet maximum DCR; core loss is not
modelled, so real notches are shallower than shown.  Loss is relative to the
receiver connected without the filter.  Needs numpy.
"""
from __future__ import annotations

import os

import numpy as np

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'measurements')
PARTS = dict(L1=10e-3, R1=12.0, C9=39e-9, C10=180e-9, L2=6.8e-3, R2=9.4, C11=100e-9, C12=220e-9)


Params = dict[str, float]


def load(name: str, cols: tuple[int, int, int]) -> tuple[np.ndarray, np.ndarray]:
    """A measurement file's frequency column and complex impedance."""
    rows = [l.split('\t') for l in open(os.path.join(HERE, name), encoding='latin1') if l[:1].isdigit()]
    a = np.array([[float(r[i]) for i in cols] for r in rows])
    return a[:, 0], a[:, 1] + 1j * a[:, 2]


f = np.geomspace(300, 20000, 1500)
w = 2 * np.pi * f


def interp(fx: np.ndarray, z: np.ndarray) -> np.ndarray:
    lf = np.log(f); lx = np.log(fx)
    return np.interp(lf, lx, z.real) + 1j * np.interp(lf, lx, z.imag)


def ser(z: np.ndarray) -> np.ndarray:
    return np.array([[np.ones_like(z), z], [np.zeros_like(z), np.ones_like(z)]])


def shu(y: np.ndarray) -> np.ndarray:
    return np.array([[np.ones_like(y), np.zeros_like(y)], [y, np.ones_like(y)]])


def mul(*ms: np.ndarray) -> np.ndarray:
    out = ms[0]
    for m in ms[1:]:
        out = np.einsum('ijf,jkf->ikf', out, m)
    return out


def tank(L: float, R: float, C: float) -> np.ndarray:
    zl = 1j * w * L + R
    zc = 1 / (1j * w * C)
    return zl * zc / (zl + zc)


def response(p: Params, zs: np.ndarray, Zr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Loss in dB against the bare receiver, and the filter's input impedance."""
    M = mul(ser(tank(p['L1'], p['R1'], p['C9'])), shu(1j * w * p['C10']),
            ser(tank(p['L2'], p['R2'], p['C11'])), shu(1j * w * p['C12']))
    A, B, C, D = M[0, 0], M[0, 1], M[1, 0], M[1, 1]
    vf = Zr / (A * Zr + B + zs * (C * Zr + D)); v0 = Zr / (zs + Zr)
    return 20 * np.log10(abs(vf / v0)), (A * Zr + B) / (C * Zr + D)


PB = (f >= 300) & (f <= 3000); SB = (f >= 6000) & (f <= 9140); LOAD = (f >= 5800) & (f <= 9500)
E34 = np.argmin(abs(f - 3400))


def summary(il: np.ndarray, zin: np.ndarray, Zr: np.ndarray) -> tuple[float, ...]:
    return (abs(il[PB]).max(), il[E34], (-il[SB]).min(), (abs(zin[LOAD]) / abs(Zr[LOAD])).min())


def main() -> int:
    Zr = interp(*load('receiver_on_ear.txt', (0, 3, 4)))
    Zs = interp(*load('source_500set.txt', (0, 3, 4)))
    p = PARTS
    print('notches %.0f Hz (L1 C9), %.0f Hz (L2 C11)' % (1 / (2 * np.pi * np.sqrt(p['L1'] * p['C9'])),
                                                        1 / (2 * np.pi * np.sqrt(p['L2'] * p['C11']))))
    il, zin = response(p, Zs, Zr)
    print('    f     loss dB   |Zin|   |Zrx|')
    for fx in (300, 500, 1000, 2000, 3000, 3400, 4000, 5000, 6000, 7000, 8000, 8906, 9000, 12000, 20000):
        i = np.argmin(abs(f - fx))
        print(f'{fx:6d} {il[i]:9.1f} {abs(zin[i]):7.0f} {abs(Zr[i]):7.0f}')
    print('300 Hz-3 kHz worst %.2f dB; 3.4 kHz %.1f dB; min loss 6.0-9.14 kHz %.1f dB; min Zin/Zrx 5.8-9.5 kHz %.2f' % summary(il, zin, Zr))
    for k in (0.5, 1.5):
        print('source x%.1f: %.2f dB, %.1f dB, %.1f dB, %.2f' % ((k,) + summary(*response(p, Zs * k, Zr), Zr)))
    rng = np.random.default_rng(0); W = []
    for _ in range(2000):
        q = dict(p)
        for k in ('L1', 'L2'): q[k] *= 1 + rng.uniform(-.10, .10)
        for k in ('C9', 'C10', 'C11', 'C12'): q[k] *= 1 + rng.uniform(-.05, .05)
        W.append(summary(*response(q, Zs, Zr), Zr))
    W = np.array(W)
    print('L ±10%%, C ±5%%, 2000 trials: passband worst %.2f dB; 3.4 kHz worst %.1f dB; '
          'min loss 1st percentile %.1f dB, worst %.1f dB' % (W[:, 0].max(), W[:, 1].min(), np.percentile(W[:, 2], 1), W[:, 2].min()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
