# lib — the `switchboard` library

Parts not in KiCad's stock libraries, shared by every project here.

- `switchboard.kicad_sym` — symbols: HCPL-3700, SP721, XFMR_TY-311P, NME2412SC,
  Olimex_ESP32-POE-ISO, B66208B1110T001, RLB1314-222KL.
- `switchboard.pretty/` — footprints, one `.kicad_mod` each.

A downloaded symbol is imported into `switchboard.kicad_sym` and its file deleted;
nothing else here is loaded.

Symbol and footprint choices, and which are verified, are in `kicad_library_plan.xlsx`
(in `~/s/game/`).
