# 551 Switchboard Simulator — A Grandstream ATA on a Trunk Jack (Bench Notes)

Rev 2 — 2026-10-22. Bench notes, Mark's measurements. Nothing here is a design
decision. The ATA is a Grandstream HT80x V2; its administration guide is in
`reference/HT80x-V2-–-Administration-Guide.pdf`.

## Changes in Rev 2

— Loop current measured with a meter in series, in place of Rev 1's figure worked out
from the voltages. It is 30 mA, not 10 mA, with the cord in and with the operator
keyed alike: the ATA feeds a regulated current, not a soft 48 V source, and Rev 1's
inferences from a 4 kΩ source are withdrawn. The ATA sees the seizure as soon as the
cord goes in, not when the operator keys: Rev 1 had it otherwise because no dial tone
was heard on the loudspeaker then, and none could be, since the loudspeaker follows
the operator, who was not yet on the line.

## 1. Measured

The ATA's FXS port connected to one of the switchboard's trunk jacks, in place of the
trunk board. Mark, 2026-10-22. Tip to ring, and the loop current with a meter in
series:

| State | Tip to ring | Loop current | The ATA |
| --- | --- | --- | --- |
| No cord in the jack | −48 V | 0 mA | idle |
| Cord plugged in | −28 V | 30 mA | sees the seizure, plays dial tone |
| Cord in, operator keyed | −6 V | 30 mA | the same |

The switchboard trunk's DC resistance, measured on its own: 575 Ω.

## 2. What the numbers say

- **The feed is a regulated current, about 30 mA.** The current does not change between
  the two loaded states while the voltage falls from 28 V to 6 V, which is what an FXS
  port's current-limited feed does. The 48 V is its open-circuit voltage.
- **The loop is not 575 Ω in either state.** At 30 mA, the cord alone is
  28 V / 30 mA ≈ 930 Ω, and keying the operator brings it down to 6 V / 30 mA ≈ 200 Ω,
  her set and the cord circuit now in parallel with it. The 575 Ω was measured in some
  other condition: an ohmmeter on a loop with relays, a lamp and diodes in it does not
  read what the loop does at 30 mA.
- **The seizure is the cord, not the key**, as on a real trunk: the cord closes the
  loop. The operator then joins a line that already has dial tone.
- **30 mA is about what the switchboard sees in play.** The trunk board's own
  constant-current feed is 26–28 mA (trunk_circuit.md §3.3), so its trunk relay and
  lamp are not asked for anything new.

## 3. Open

- Where the 575 Ω was measured, and why it differs from the 930 Ω the cord presents at
  30 mA.
- The ATA's loop current setting, if it has one (administration guide, FXS port
  settings).
