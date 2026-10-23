# hardware

Mechanical design files other than the circuit boards (those are in `kicad/`).
Front panels are Front Panel Designer files (Schaeffer / Front Panel Express).

- `panel1.fpd` — connectors for the cabling to the switchboard.
- `panel2.fpd` — connectors for everything else: the Stream Deck, the audience monitor,
  the travel router and the Next Scene pushbutton.
- `station-wiring.csv` — the station lines from the station boards' RJ45s to the
  switchboard: one 25-pair colour group to each RJ45, the slate pair unused.
- `switchboard-wiring.md` — the ring and power feeds into the switchboard: which game
  cable wire goes to which switchboard wire, and why the ring pair crosses colours.
- `switchboard-wiring-notes-2026-10-16.jpg` — Mark's handwritten table that
  `switchboard-wiring.md` was written from.
- `trunk8-ata-mod-2026-10-23-*.jpg` — the trunk board's trunk 8 as modified for the
  Grandstream ATA (`docs/trunk_circuit.md` §4.5, Rev 5.55): `board` the top half, the
  pair from the glued-on RJ45 down to strip 8; `jack` the RJ45 at the board's edge;
  `strip8` close up, the 330 Ω with the back-to-back 220 µF pair, U901's jumpers, the
  tip lead at D903's cathode pad and K901's two jumpers.
  `whole` the finished board, the pair glued down at the corner by T901.
- `rj45-punchdown-cat6.jpg` — the blue Cat 6 RJ45 keystone's punch-down terminals
  seen from above, jack opening at the top, with the colour on each pin. X is the
  group colour (white, red, black, yellow, violet). Go by the pin numbers, not the
  jack's T568A/B colour labels.
