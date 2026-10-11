# electret — operator headset transmitter

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

No specification in `docs/` yet. R11 is selected on the bench to match the carbon
element's level on the tap channel. Untested.
