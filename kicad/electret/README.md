# electret — operator headset transmitter and receiver filter

An electret capsule in place of the carbon transmitter in the operator's headset. The
capsule alone goes in the mouthpiece, on the cord's transmitter pair (J2); this board
goes in a box on the cord and connects to the switchboard's transmitter feed (J1),
either polarity. It presents itself to the feed as a carbon element does: a DC drop of
a few volts, with speech as a varying EMF.

The feed (Mark's drawing, 2026-10-09): 24 V battery through a 140 Ω retard coil to the
transmitter; the transmitter's AC is coupled through 3 µF into the 2.3 Ω primary of the
induction coil. With R1 = 10 Ω the board takes ≈ 133 mA at ≈ 5.4 V, ≈ 0.7 W: Q1 (TIP120)
0.35 W, R1 0.18 W, the bridge (DF04M) 0.2 W. R1 sets the source impedance and so the sidetone balance;
10–22 Ω, chosen by ear.

## Headset cord

| Pair | Circuit | Plug |
|---|---|---|
| red/green | transmitter (the capsule): J2 | tip |
| black/white | receiver: J4 | sleeve |

Recorded by Mark, 2026-10-12.

## Capsule

Same Sky CMC-97452-L100 (Mark, 2026-10-19), replacing the Soberton EM-6027N: wire leads,
where the EM-6027N's solder pads are hard to wire. 9.7 mm, which a traditional operator's
headset takes. From distributor listings — Same Sky's datasheet not yet checked, and some
sellers list a near-identical CMC-9745-L100:

| | CMC-97452-L100 | EM-6027N |
|---|---|---|
| Directivity | unidirectional | noise-cancelling |
| Sensitivity | −37 dB ±3 dB | −42 dB ±3 dB |
| Supply | 1.5–9 V, 400 µA, 2.2 kΩ | 2 V std, 10 V max, 500 µA max, 2.2 kΩ |
| Response | 100 Hz–12 kHz | 200 Hz–10 kHz |

No circuit change: through R6 at 400 µA, MIC sits near 2.4 V. About 5 dB hotter than the
EM-6027N; if the tap level is high, R11 4k7 takes off 6.4 dB. Front toward the mouth,
rear port left open — directivity depends on it. The lead with continuity to the can is
−, to J2 pin 2.

## Breadboard, on the switchboard — 2026-10-19

EM-6027N, R1 10 Ω, Mark's meter: 1.25 V across R1 (125 mA), 5.26 V across J1, COLL
2.3 V, BASE 1.3 V, V1 3.56 V, V2 3.3 V, 2.9 V across the capsule (≈ 0.2 mA). A capsule
wired backwards reads about 0.56 V there — one diode drop.

AD3 on OUT and across J1, R11 2k2: a normal count is 268 mV RMS on OUT and clips at
both rails (0.04 / 3.4 V; 0.68 % of samples), loud 2.7 %. J1 = −0.43 × OUT (R2/R12
predicts −0.47). Idle: 120 Hz 1.3 mV on OUT (the switchboard battery's ripple), 0.56 mV
in 300–3400 Hz; the 9 kHz operator tone 0.34 mV across J1.

**R11 2k2 → 4k7, R2 560 → 1k2.** R11 for headroom on OUT. R2 because the line level is
set by OUT's swing times R2/R12, and OUT was already at its rails: R2 1k2 doubles the gain
to the line (+6.6 dB) and raises COLL to ≈ 3.5 V, so Q1 has room to swing down and V1,
and with it OUT's swing, rises (V1 measured 4.5 V).

On station 22's channel, operator on the talk key, counting one to ten; 300–3400 Hz,
100 ms frames, dBFS. The speech detector's bound is −70:

| | Normal: median / p90 | Frames > −70 | Loud: median / p90 | Idle |
|---|---|---|---|---|
| Electret, R2 560, R11 4k7 | −69.3 / −61.7 | 22 of 41 | −58.2 / −46.9 | −93.2 |
| Electret, R2 1k2, R11 4k7 | −62.8 / −52.1 | 39 of 56 | −59.9 / −44.8 | −89.6 |
| Carbon, same day | −69.8 / −61.0 | 24 of 47 | −69.1 / −43.2 | −94.6 |

The electret is about 7 dB above the carbon at a normal voice and about 2 dB better above
its noise; the carbon catches up only on loud peaks. The capsule was in the open, not
mounted in the headset — repeat with the built board, the CMC-97452-L100 and the capsule
in the mouthpiece. With the operator on an off-hook station the tap channel (23) reads
about 16 dB lower than with the station on-hook.

## Receiver low-pass

A passive filter on the receiver pair, J3 (from the switchboard) to J4 (to the
receiver), for the case where the pilots (6.0–8.9 kHz) or the operator tone (9 kHz)
are audible in the headset. Elliptic, series element first, so its input impedance in
the pilot band stays at or above the receiver's and it does not load the cord while the
operator is bridged. Notches at 8.06 kHz (L1 C9) and 6.10 kHz (L2 C11).

Designed against three AD3 impedance sweeps in `measurements/` (2026-10-12, 100 mV,
1 kΩ reference): the receiver in free air and on the ear (78.5 Ω DC), and the operator
circuit seen from the receiver conductors with the receiver lifted, the carbon headset
plugged in and the key bridged to a line held off-hook by a 500 set.
`receiver_filter.py` computes the response of the values on the sheet:

| | |
|---|---|
| 300 Hz–3 kHz | within ±1 dB |
| 3.4 kHz | −2.0 dB |
| 6.0–9.14 kHz | ≥ 39.4 dB down |
| source ×0.5 or ×1.5 | ≥ 38.3 dB, passband within 1.7 dB |
| L ±10 %, C ±5 %, 2000 trials | ≥ 30.2 dB in 99 %, worst 27.5 dB |

Inductors are modelled as L plus DCR, without core loss, so real notches are shallower.
At 2.5–3.4 kHz the filter's input impedance is 0.35–0.47 of the receiver's, which may
move the sidetone balance at the top of the band. Bench checks once built: the response
across the receiver with the AD3 network analyzer, sidetone by ear, the outgoing level
on the tap channel, and `optone` and `op` detection with the operator bridged.

No specification in `docs/` yet. R11 is selected on the bench to match the carbon
element's level on the tap channel. Untested.
