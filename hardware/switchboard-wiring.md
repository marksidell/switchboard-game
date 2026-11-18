# Switchboard wiring — ring and power

How the game hardware's ring and power feeds join the 551's own wiring. Mark, 2026-10-16.
The station lines are in `station-wiring.csv`.
Mark's handwritten table, the source of these, is
`switchboard-wiring-notes-2026-10-16.jpg`: ring above the line, power below, with power
by internal terminal (1–4, 45–48) rather than by 66 block position.

## Ring

The switchboard's ring supply comes in on a red/white pair. When the switchboard
rings a station:

| Switchboard ring wire | Goes to the line's |
| --- | --- |
| white | tip |
| red | ring |

On the game hardware the ring generator's output enters the trunk board on J102
(`trunk_schematic_guide.md`). The cable at J102 is red/black:

| J102 pin | Signal | Cable wire | When the trunk board rings a station, goes to the line's |
| --- | --- | --- | --- |
| 1 | RING_HI | red | tip |
| 2 | RING_LO | black | ring |

At the switchboard, ring arrives on the four-conductor game cable (below), green and
white, joined to the switchboard's ring pair:

| Game cable | Signal | Switchboard ring wire | Both carry |
| --- | --- | --- | --- |
| green | RING_HI | white | tip side |
| white | RING_LO | red | ring side |

**Do not swap these.** The colours look like they should go white to white, but the
game's white has to go to the switchboard's red. The pairing puts the two supplies on
the line in the same polarity. If the
operator rings a trunk while the trunk board is also ringing it, the opposite pairing
shorts one ring supply into the other.

## Power

Inside the switchboard:

| Supply | Internal terminals | 66 block 46–50 |
| --- | --- | --- |
| GND | 1–4 | ring |
| BAT, +24V | 45–48 | tip |

When the switchboard feeds loop power to a station, BAT reaches the line's tip through
one retard coil and GND reaches its ring through a separate retard coil.

## The game cable

Inside the game hardware, ring (J102's red/black cable) and power each run to an
Anderson Powerpole connector of their own on the back panel (`panel-back.fpd`). From the
panel, one four-conductor cable carries both to the switchboard:

| Wire | Signal | At the switchboard |
| --- | --- | --- |
| red | +24V | 66 block 46–50 tip |
| black | GND | 66 block 46–50 ring |
| green | RING_HI | ring wire white |
| white | RING_LO | ring wire red |
