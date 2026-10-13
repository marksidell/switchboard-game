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
