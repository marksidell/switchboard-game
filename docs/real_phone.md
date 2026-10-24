# 551 Switchboard Simulator — A Real Telephone on the Board (Proposal)

Rev 3 — 2026-10-24. Adopted, option B (Mark, 2026-10-23). The parts of it that are
design go into `station_circuit.md`, `audio.md`, `pilot-map.md`, `control.md`, `mqtt.md`
and `game_control.md` (§6 below), and this document becomes the record of how the
decision was reached.

## Changes in Rev 3

- §3: the phone's line moved to switchboard jack 18, room 203 (Mark, 2026-10-24). Jack 10
  is uncabled.

## Changes in Rev 2

- Adopted, option B, on board 3 strip 8 (Mark, 2026-10-23). The monitor already runs on
  the Digiface 33/34.
- §3: the phone's line is on switchboard jack 10, room 405.
- §5: the bench measurements are in. The phone pulls the line to 7.9 V at most, under
  the 8.5 V the §3.1 values need, and the 4.4 kΩ load neither lights the lamp nor sags
  the line much (23.5 V). The §3.1 values stand.

## Changes in Rev 1

—  First version, from the discussion between Mark and Claude Code on 2026-10-17.

## 1. What it is for

A second person, not the operator, picks up a real telephone wired to the switchboard,
calls the operator and asks for any of the 22 stations. The operator answers and puts the
call through as she would any other. The caller then hears that room's guest, who answers
in character.

The guest behaves like "Hello, this is Lenny": a set of pre-rendered, vague,
in-character replies, played one at a time whenever the caller pauses. **Mark's decision:
the guest cycles through the replies as Lenny does** and never ends the call; the caller
hangs up when they choose.

## 2. Why the existing station circuit cannot do it

An on-hook station's relay lifts Rx03 (330 Ω) and Tx01 off the line (station §5.1, §7.2),
so that channel hears no pilots, and the game cannot detect a phone on it. The ring
detector cannot see the hook either: Cx03 blocks DC (station §3.5). The phone needs a hook
detector of its own, and a way for the game to put the line into the pilot comb once the
phone is off-hook.

## 3. Hardware: board 3 strip 8

The phone uses board 3 strip 8's line pair. The pair already runs from the switchboard to
the game box and is unused on the line side: the strip carries the audience monitor
(J7B101 pins 7/8; station §7.9.8). The phone is wired across it at the game box.
It is cabled to switchboard jack 18, room 203 (Mark, 2026-10-24; jack 10, room 405, from
2026-10-23): bundle 2,
white-brown, `hardware/station-wiring.csv`.

### 3.1 Hook detector

Fit the strip's unstuffed ring-detector footprint as a DC hook detector:

| Part | Station fit | Here |
|---|---|---|
| Ux01 | HCPL3700M | HCPL3700M |
| Rx06, Rx07 | 10 kΩ | 2.2 kΩ each, 2 W (Vishay PR02; fits the DIN0309, 12.7 mm footprint), mounted a few mm off the board |
| Cx03 | 1 µF, 250 V | 0 Ω link |
| Dx01 | TVS | TVS, as fitted on every station |

The HCPL3700's input has a diode bridge, so line polarity does not matter (Mark).
Bridging tip and ring, it senses the line's **voltage**: it conducts with the phone on-hook
(about 24 V) and releases when the phone is off-hook and pulls the line down. The firmware
inverts the sense. The output reaches a board-3 expander input that is otherwise unused.

Sizing, from the device's guaranteed limits (station §3.5: turn-on 1.96–3.11 mA, turn-off
1.00–1.62 mA, about 4.2–5.5 V across the input):

- On-hook, 24 V: (24 − 5.5) / 4.4 kΩ ≈ 4.2 mA, more than the 3.11 mA worst-case turn-on.
- Off-hook: below 1.0 mA, and so released, as long as the line is under about 8.5 V
  ((8.5 − 4.2) / 4.4 kΩ). Measured at most 7.9 V (§5): 0.84 mA, released.
- On-hook with the detector's own load: 23.5 V measured (§5), (23.5 − 5.5) / 4.4 kΩ =
  4.1 mA, on.
- Ringing: **the operator may ring the phone, and nothing can stop her (Mark).** At
  90 V rms, about 1.6 W in total, 0.8 W in each resistor, 40% of a PR02's rating.
- Being DC-coupled, the detector also sees ringing. Its output pulses at 40 Hz while the
  phone is rung, so "being rung" can be told apart from "on-hook" with no extra parts.

If the phone does not pull the line below about 8.5 V, the fallback is a bidirectional
TVS of about 12 V in series, to raise the threshold. It needs smaller resistors, and
ringing then dissipates more in them.

### 3.2 Knowing the operator is on the call

Two options were weighed.

**A. Inference from timing.** The phone goes off-hook. Then the operator rings station
*n* when no scripted call expects it, and the game treats that as a free call to *n*.
This corrects itself: if nobody is there, Lenny's listen hears silence, nudges and gives
up. But it is weak while a game is running, so free calls would only work with no game
running or in a "phone" mode.

**B. Strip 8 as a line interface — Mark's choice.** Fit the strip's relay, Cx01 and Tx01,
but **not Rx03**, so the line's DC stays the phone's and the bridging hook detector keeps
working. While the phone is off-hook the game closes the relay. Slot 24's pilot is then on
the phone's line, and op, peer, the monitor and listen all work on it as on any station.

## 4. Audio consequence: the monitor moves to the Digiface

Option B takes A32 channel 24 back from the audience monitor. The monitor returns to the
Digiface's own analog output, channels 33/34: a command-line change, `--monitor-ch 33,34`
(audio.md §14), with no code change.

The jack is a 6.3 mm TRS, unbalanced stereo: 33 on the tip, 34 on the ring, sleeve to
ground. Full scale is +9.5 dBu, fixed; there is no TotalMix under Linux. The −3 dBFS
limiter holds the output to about +6.5 dBu. This is the cost that moved the monitor off
the Digiface at station Rev 3.40, and Mark accepts it.

The amplifier takes balanced line level today, from A32 output 24. To feed it:

- A 1/4″ TS to XLR male cable: tip to pin 2, sleeve to pins 1 and 3. About $10; try it
  first.
- If it hums: an ART DTI, a passive 1:1 line-level isolator.
- **Not** a TRS–TRS cable into a balanced input: tip and ring carry the same signal, and
  the input subtracts one from the other, which cancels the monitor.
- **Not** a DI box: its mic-level output is 30–40 dB below what the amplifier is set for.

The level falls by the difference between channel 24's A32 reference level and +9.5 dBu.
Take that up with `monitor/set` (to +20 dB), or with the amplifier's input gain.

## 5. Bench measurements needed

Phone on the strip 8 pair at the game box:

1. Line voltage, on-hook.
2. Line voltage, off-hook, not yet answered.
3. Line voltage, off-hook, with the answer cord in.
4. Line voltage, off-hook, patched to a station.
5. Does a 4.4 kΩ resistor across the pair light the line lamp, or pull in the line relay?
   The detector draws about 4.2 mA all the time the phone is on-hook.

Measured 2026-10-23 (Mark), phone on the strip 8 pair, board unchanged:

| # | Condition | Tip–ring |
|---|---|---|
| 1 | On-hook | 24 V |
| 2 | Off-hook, not answered | 5.5 V |
| 3 | Off-hook, answer cord in | 7.9 V |
| 3a | Off-hook, answer cord in, operator keyed in | 7.0 V |
| 4 | Off-hook, patched to a station | 7.9 V |
| 5 | On-hook, 4.4 kΩ across the pair | 23.5 V; lamp dark |

The worst off-hook case, 7.9 V, is 0.6 V under the 8.5 V limit: 0.84 mA against the
1.00 mA worst-case turn-off. The §3.1 values stand. (2 × 2.4 kΩ would split the margin
more evenly, 3.75 mA on and 0.77 mA off, but 2.2 kΩ meets both worst cases.)

## 6. If adopted

**Hardware and the circuit plan:**

- `station_circuit.md`: strip 8 becomes a phone line interface (relay, Cx01, Tx01; no
  Rx03), with the hook detector of §3.1.
- `pilot-map.md` and `audio.md`: slot 24 becomes a circuit again. The monitor defaults
  to 33/34.

**Control and wire:**

- `control.md`: the hook input; masking it during ringing; the relay under game
  command.
- `mqtt.md`: a hook topic, e.g. `sbgame/phone/hook`, and the relay command.

**Game and content:**

- `game_control.md`: a free-call mode outside the deal, which is not scored and keeps
  the called room busy for dealing. Each room's guest comes from the game's `occupants`.
- `script.yml`: a new `freecall:` section. Per guest: a greeting that names them, about
  10–14 vague replies cycled without end, and a "who is this?" — about 15 × 22 ≈ 330 clips,
  rendered as every other line is. The guest nudges after about 8 s of silence.
