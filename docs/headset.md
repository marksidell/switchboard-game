**551 Switchboard Simulator**

**Receiver Low-Pass Filter**

*Rev 1. The changes in each revision are in §8.*

# 1. Overview

The pilot comb (6000–8906.25Hz, `pilot-map.md`) and the 9kHz operator tone are on every line the switchboard connects, and so they reach every receiver on it. This filter keeps them out of two receivers: the operator's headset and the real telephone on station 24 (`real_phone.md`). It is a passive low-pass on the receiver pair, between the circuit that drives the receiver and the receiver itself, so the line, the pilots on it and their detection are untouched.

One design serves both. It is drawn in `kicad/electret`, J3 (from the circuit) to J4 (to the receiver), on the same board as the headset's electret transmitter. `kicad/electret/receiver_filter.py` computes its response from the measurements in `kicad/electret/measurements/`.

| Where | Fitted | Measured |
|---|---|---|
| Station 24's 500 set, jack 18 | Yes, transmitter half unstuffed (§5) | 2026-11-03, in place (§6) |
| The operator's headset, in the box on the cord | Not yet | Not yet (§7) |

# 2. Design

Elliptic, series element first:

```
    J3 ──[L1 ∥ C9]──┬──[L2 ∥ C11]──┬── J4
                   C10            C12
    ───────────────┴──────────────┴───
```

| Ref | Value | Part |
|---|---|---|
| L1 | 10mH | Bourns RLB1314-103KL |
| C9 | 39nF | film, 5% |
| C10 | 180nF | film, 5% |
| L2 | 6.8mH | Bourns RLB1314-682KL |
| C11 | 100nF | film, 5% |
| C12 | 220nF | film, 5% |

L1 with C9 notches 8.06kHz, and L2 with C11 6.10kHz.

Series element first, so that in the pilot band the filter's input impedance stays at or above the receiver's (at least 1.04 times it from 5.8 to 9.5kHz). A filter with a shunt capacitor first would load the cord in the pilot band while the operator is bridged across a call, and take pilot level from the line the detector reads.

The cost is at the top of the passband: at 2.5–3.4kHz the input impedance is 0.35–0.47 times the receiver's, which may move the telephone's sidetone balance there.

The inductors are radial drum cores, unshielded and not polarized. Two placed close together couple a little, and the way round they are fitted then nudges the notches.

The model takes each inductor as L plus the datasheet's maximum DC resistance (L1 12Ω, L2 9.4Ω) and leaves out core loss, so real notches are shallower than computed.

# 3. Measurements Designed Against

All taken with the AD3's impedance adapter at 100mV against a 1kΩ reference, and kept in `kicad/electret/measurements/`.

**The headset, 2026-10-12.** The receiver in free air (`receiver_free.txt`) and on the ear (`receiver_on_ear.txt`), 78.5Ω DC. In free air, |Z| was 87Ω at 100Hz, peaked at 248Ω at 1.0kHz, had a second resonance at 2.3kHz, and rose to 434Ω at 3.47kHz, 584Ω at 6.04kHz and 704Ω at 8.7kHz. Above 3kHz it rises as f^0.51, lossy iron with Q about 1. The source (`source_500set.txt`) is the operator circuit seen from the receiver conductors: receiver lifted, carbon headset plugged in, key bridged to a line held off-hook by a 500 set.

**Station 24's 500 set, 2026-10-26.** Short-compensated with `500set_short_nocap.txt`. The load (`500set_receiver_on_ear.txt`) is the receiver leads off the network with the handset on the ear. The source (`500set_source.txt`) is the network's receiver terminals with the phone off-hook on jack 18 and `sbaudio` stopped.

# 4. Computed Response

Loss relative to the receiver connected without the filter, from `receiver_filter.py`.

| | Headset | 500 set |
|---|---|---|
| 300Hz–3kHz | within 1dB | within 1.5dB to 3.4kHz; −1.3 to −1.5dB below 1kHz |
| 3.4kHz | −2.0dB | (in the line above) |
| 6.0–9.14kHz | at least 39.4dB down | at least 40.4dB down |
| Source impedance scaled | ×0.5 or ×1.5: at least 38.3dB, passband within 1.7dB | ×0.5 to ×3: at least 37.7dB |
| L ±10%, C ±5%, 2000 trials | at least 30.2dB in 99%, worst 27.5dB | at least 30.2dB in 99% |

The 500 set's loss below 1kHz is the inductors' 21Ω in series with a receiver of about 100Ω there. Changing only C10 and C12 does not remove it.

# 5. In the 500 Set

Station 24's 500 set has no dial and has room for the board inside it (Mark, 2026-10-26). J3 goes to the network's receiver terminals and J4 to the handset's receiver leads. No DC flows there. The transmitter half of the board is unstuffed.

A filter in the line instead was considered and rejected. Loop current through the inductors would lift the line about 1.6V at the hook detector (`real_phone.md` §3.1). The sweeps taken for it are kept: `500set_offhook.txt` (phone off-hook at 59mA, 24V through 2 × 150Ω, 10µF DC block), `500set_feed.txt` (the feed alone), `500set_short.txt` (the 10µF alone), and `500set_phone.txt`, the phone alone computed from them: about 500Ω at 1kHz, and 720–750Ω at +17° across 6–9kHz.

# 6. Measured in Place, 2026-11-03

## 6.1 Setup

The filter fitted in the 500 set, the phone off-hook on jack 18 (room 203) and corded to the front desk, station 1. Station 1 carries the lowest pilot, 6000Hz. The operator's key was thrown. AD3 scope 1 across the receiver, in record mode, at 50kS/s on the 5V range. The game program was stopped.

The scripts are in `kicad/electret/inplace/`. `hold.py` and `pub.py` run under `engine/.venv` (aiomqtt), the rest under `tts/.venv` (numpy, scipy). The results are in `kicad/electret/measurements/500set_inplace_response.txt`.

1. `hold.py 1 24` sets stations 1 and 24 `hook/set on` and sends the game heartbeat the controller needs (`control.md` §10). It releases both on SIGTERM. `station/1/peer` read `station/24` and `station/24/peer` read `station/1`, and `op` was on at both.
2. Pilots alone: `ad3rec.py 5 base.npy`, then `spec.py base.npy 60 6000 8156.25 9000`.
3. Response: `mksweep.py` writes 80 sines, a twelfth of an octave apart from 100Hz to 10kHz. Each is at −20dBFS peak, 0.4s on and 0.1s off; speech in the game's files is about −19dBFS rms. Start `ad3rec.py 46 sweep.npy`, then `pub.py sbgame/station/1/play/set <name>`. `response.py DIR` finds the start and takes each tone's level over 0.25s. It takes the same frequency in the silence after the sweep as the floor.

## 6.2 Response

This is the whole path: station 1's board, the switchboard, the 500 set's network, the filter, the receiver. It is not the filter's insertion loss, so §4 does not predict it directly. The low end and the rise at 2.4–3.6kHz are mostly the line and the set.

The 1kHz tone reached the receiver at −41.5dBV (8.4mV). Relative to it:

| Hz | 100 | 200 | 300 | 600 | 1k–1.9k | 2.4k–3.6k | 4.8k | 5.08k | 5.38k | 5.7k | 6.0k–7.6k | 8.06k | 8.54k | 9.05k | 9.59k |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dB | −20 | −10 | −8 | −2 | ±1 | +3 | +1.5 | −5 | −14 | −24 | −36 to −40 | −46 | −54 | −43 | −38 |

The least in the pilot band is 35.8dB, at 6.78kHz, against the 40.4dB computed. Part of the difference is the path's own +3dB around 3kHz, against which these figures are taken.

The 100–118Hz points are disturbed by 60Hz hum.

## 6.3 Pilots at the Receiver

With no program playing:

| | dBV |
|---|---|
| 6000Hz, station 1 | −96.7 |
| 8156.25Hz, station 24 | −107.4 |
| 9000Hz, the operator | −113, at the floor |
| 60Hz hum | −67 |

The 6000Hz pilot is 55dB below the 1kHz tone, about 59dB below speech, and 30dB under the hum.

As a check, the response at 6kHz less 20dB predicts −99dBV for that pilot: the pilot is generated at −40dBFS, 20dB under the tone.

Not checked by ear. An estimate: with speech at 75–85dB SPL at the ear, the 6000Hz pilot is about 15–25dB SPL before the receiver's own roll-off above 3–4kHz. That is near a young listener's threshold at 6kHz in a quiet room, and masked by any speech or room noise.

# 7. Open Items

In the headset, once built:

- The response across the receiver.
- Sidetone, by ear.
- The operator's outgoing level on the tap channel.
- `optone` and `op` detection with the operator bridged.

In the 500 set: a listening test by someone who hears above 6kHz.

# 8. Revision History

## 8.1 Changes in Rev 1

— New document, Mark's request, 2026-11-03. The filter's design and its measurements had been only in `kicad/electret/README.md` and in commit messages: the design (e6f9124, 2026-10-12) and the 500 set (a4335d5, 2026-10-26). They are collected here, with the in-place measurement of 2026-11-03 (§6).

— No code consequence.
