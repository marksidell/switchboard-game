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
- `rj45-punchdown-cat6.jpg` — the blue Cat 6 RJ45 keystone's punch-down terminals
  seen from above, jack opening at the top, with the colour on each pin. X is the
  group colour (white, red, black, yellow, violet). Go by the pin numbers, not the
  jack's T568A/B colour labels.
