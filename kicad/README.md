# KiCad

Schematics and PCB layouts for the custom boards, KiCad 9. Opened in place on Linux
and, through Syncthing, on Windows at `C:\s\sbgame\kicad`.

| Folder | Board | Specification |
|---|---|---|
| `control/` | Ring generator and controller — the board as built, carrying the ESP32-POE-ISO | `docs/ring_generator.md`, `docs/control.md` |
| `control2/` | The high-frequency-link generator alternative. Drawn, not adopted | `docs/ring_generator.md` §9.7 |
| `stations/` | Station board, 8 strips; three are built | `docs/station_circuit.md`, `docs/station_schematic_guide.md` |
| `trunks/` | Trunk board, 8 trunks; one is built | `docs/trunk_circuit.md`, `docs/trunk_schematic_guide.md` |
| `electret/` | Electret transmitter and receiver low-pass for the operator headset, in a box on the cord. Drawn, not built | none yet; `electret/README.md` |
| `power/` | Switchboard power cut: a relay in the switchboard's 24V leg, driven from the controller's GPIO15 on J1. Drawn, not built | `docs/ring_generator.md` §7.8, `docs/control.md` §5.4 |
| `lib/` | The custom symbol and footprint library, `switchboard` | `kicad_library_plan.xlsx` (in `~/s/game/`) |

Every project's `sym-lib-table` and `fp-lib-table` reach the library as
`${KIPRJMOD}/../lib/`. Keep them relative, and keep `lib/` beside the projects.

Not tracked (`.gitignore`): `*-backups/`, `gerbers/`, the fab `.zip`s, `.kicad_prl`,
ERC reports, lock, cache and autosave files. Plot the gerbers again from the
`.kicad_pcb` to get them back.

Front panels and other mechanical designs are in `../hardware/`.
