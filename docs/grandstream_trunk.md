# 551 Switchboard Simulator — A Grandstream ATA on a Trunk Jack (Bench Notes)

Rev 1 — 2026-10-22. Bench notes, Mark's measurements. Nothing here is a design
decision. The ATA is a Grandstream HT80x V2; its administration guide is in
`reference/HT80x-V2-–-Administration-Guide.pdf`.

## 1. Measured

The ATA's FXS port connected to one of the switchboard's trunk jacks, in place of the
trunk board. Tip to ring, Mark, 2026-10-22:

| State | Tip to ring |
| --- | --- |
| Trunk not seized | −48 V |
| Cord plugged in; the ATA does not see it seized (no dial tone) | −28 V |
| Seized, operator connected; the ATA plays dial tone | −6 V |

"Seized", here and below, is the ATA's off-hook detection: it plays dial tone.

The switchboard trunk's DC resistance: 575 Ω.

## 2. Loop current when seized

Mark's figure: 10 mA. Ohm's law agrees, if the 575 Ω is the whole loop the ATA sees
when seized: 6 V / 575 Ω = 10.4 mA.

What the three voltages imply, not measured:

- **The ATA's feed is soft.** Its voltage falls from 48 V to 6 V at 10.4 mA, an
  effective source resistance of about (48 − 6) / 10.4 mA ≈ 4.0 kΩ. An FXS port
  usually feeds a regulated loop current of about 20–25 mA. Either the port limits the
  current lower than that, or something besides the 575 Ω is in the loop.
- **With the cord plugged in but not seized, the jack still draws current.** At −28 V
  the 575 Ω would draw 49 mA, more than the ATA can supply. So the trunk's 575 Ω is not
  across the line in that state, and a higher resistance is. If the source is about
  4.0 kΩ, the line draws about (48 − 28) / 4.0 kΩ ≈ 5 mA, through about 5.6 kΩ:
  probably the cord's supervisory path.

## 3. Open

- The loop current, measured with a meter in series, seized and plugged-not-seized,
  rather than inferred from the voltages.
- The ATA's off-hook detection threshold. It gives dial tone at about 10 mA and not at
  about 5 mA, so it lies between; how far 10 mA is above it. Its loop
  current setting, if it has one (administration guide, FXS port settings).
