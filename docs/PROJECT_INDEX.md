# Switchboard Game — Project Index

Current as of 2026-10-30. When a document's revision changes, change its number here. What
changed in each revision is in that document's Revision History, not here.

**Where the documents live.** The `.md` documents are in `docs/`, under version control, and
Claude Code owns and edits them in place. `script.yml` is at the top of the repository. The
spreadsheets, `digikey_upload.csv` and the datasheets stay in the Syncthing share at `~/s/game/`.
Filenames are stable and carry no version number. Until 2026-09-25 the project also had a chat
side with rules of its own; those rules, and the status as it stood then, are in the git history
of this file.

## Specifications

| File | Rev | Covers |
|---|---|---|
| `mqtt.md` | **52** | The MQTT design: broker, clients, topic naming, every message by publisher, QoS and retention, liveness, broker configuration and access list. |
| `control.md` | **42** | The firmware specification: startup order, ring generation, I²C map, station and trunk behaviour, dial pulse timing, failsafes. |
| `audio.md` | **40** | The audio program specification: channel plan, output mixer, detector scheduling, file playback, trunk tones, speech detection, audience monitor, MQTT interface. |
| `game_control.md` | **125** | The game program, status page and Stream Deck: what a game is, call pacing, the deck of scenes, tallies, call slots, the log, the jack map. |
| `pilot-map.md` | — | Slot ↔ bin ↔ circuit assignment and the detector constants. Authoritative. |
| `audio-io.md` | — | Channel map, measured reference levels, bench tools. |

## Hardware design

| File | Rev | Covers |
|---|---|---|
| `station_circuit.md` | **3.52** | Station interface: 8 strips per board, three boards, ring detection, off-hook, audio, the operator tap, the real telephone on station 24. |
| `trunk_circuit.md` | **5.57** | Trunk interface, 8 circuits: constant-current loop feed, seizure detection, ring relay, the Grandstream ATA on trunk 8. |
| `headset.md` | **2** | Receiver low-pass for the operator's headset and station 24's 500 set: design, the measurements behind it, the response in place. |
| `ring_generator.md` | **79** | Ring generator: H-bridge, transformer, and the Olimex ESP32 that is the system's I²C master. |

The KiCad drawing guides for all three boards are in `archive/`, as records of how the schematics were drawn. The boards are built, and the guides are not kept current; the trunk guide's §7 still has the PCB netclasses and stack-up.

## Notes and proposals

| File | Rev | Covers |
|---|---|---|
| `real_phone.md` | **5** | How the decision for a real telephone on the board was reached, adopted 2026-10-23. |
| `grandstream_trunk.md` | **7** | Bench notes on a Grandstream HT80x V2 ATA on a trunk jack. The design is `trunk_circuit.md` §4.5. |
| `lenny-spec.txt` | — | Mark's spec for Lenny mode, as he wrote it. The design is `game_control.md` §8. |

## Task briefs

Written for Claude Code during the chat era and kept as a record: `tts_task.md`,
`broker_setup_task.md`, `monitor_channel_task.md`, `monitor_source_task.md`,
`ring_start_phase_task.md`. `IAM-SETUP.md` is the AWS account for the speech run.

## Outside `docs/`

| File | Covers |
|---|---|
| `script.yml` | Mark's file: the game's cast, outside lines, stations, jacks and scenes. Read by `tts/` and `engine/` through `tts/script.py`. |
| `control/control.ino` | The controller firmware, written to `control.md`. |
| `kicad/` | KiCad projects: `control` (the generator as built), `control2` (the HF-link alternative, not adopted), `stations`, `trunks`. Library tables use `${KIPRJMOD}/../lib/`, so the tree opens on Linux and on Windows. |
| `kicad/lib/` | Custom symbols (HCPL-3700, SP721, XFMR_TY-311P) and footprints. |
| `telephone_bom.xlsx` | In `~/s/game/`. **The BOM**, with Have, Need and Buying columns. Still on the two-board build as last checked, 2026-09-23; see Open items. |
| `kicad_library_plan.xlsx` | In `~/s/game/`. Symbol and footprint choices, with what is verified and what is not. |

## Open items

Carried from September, before the boards were built, and not rechecked since. Closed items
and items the built boards settled have been removed; some of what remains may be done too.

**Bench**
- TY-311P sweep in the tap configuration — lightly loaded, may show an HF peak (station §7.9.5)
- Sweep 2–3 transformers of the production lot, not one — spread at 9kHz decides whether
  one detection threshold serves all channels
- Generator §8.5: scope the switch node with C14 fitted, and confirm C14
  runs cool after an hour — it carries about 0.15A RMS of 40kHz ripple (generator §9.6)
- **Ring current, both figures** (trunk §7.6). Per-trunk with the switchboard connected, and
  the switchboard's own draw when the operator rings one station. This measurement now sizes
  three things: the concurrent-ring cap, trunk F101 (which sits at 71% of rating on the present
  estimate) and generator F2. It also decides whether generator §9.4's no-load trim stands
- Audio commissioning order is `audio.md` §15: clock lock between Digiface and A32 first,
  then channel wiring by test tone, then every level and threshold — including the period
  tones' modulation depth, set by ear (`audio.md` §8.2), and the monitor channel's reference and
  trim against the loudspeaker amplifier's input sensitivity (§15 step 7), then the tap trim and
  a listen for the balance between caller and called party on a circuit source (audio.md §16)

**Decisions deferred**
- Station §11 counts the tap parts ×8 as footprints; the BOM counts them 2 as purchases.
  Both are defensible, neither is wrong, and they are not the same convention
- TSR 2-2450 maximum output capacitance. Still open — the TSR 1 limit is 470µF against
  10µF on the generator, but that is a different part and a different datasheet — affects the 220µF, and the failure mode is a
  board that will not start with no diagnostic symptom
- **BOM to the build.** `telephone_bom.xlsx` was on the two-board build when last checked, 2026-09-23, and the board has changed since (trunk 8, station 24). Check Have/Need before relying on any line
- Rack packaging
- Powerpole contact gauge for the switchboard 24V run — set by run length and lamp inrush,
  not by the 1A average. Pick the wire first
- Protection for that run. As drawn it is unfused and the LRS-150-24 will source 6.5A into a
  damaged cable. Wants a fuse at the PSU end; not yet sized
- Calls arriving before the operator has connected the current one — deferred by Mark
  (`game_control.md` §5.5); and the rest of that document's §14

## Things that have bitten before

- **Two files for one purpose.** The BOM diverged twice. One file, one owner.
- **A cross-reference is a place a correction can hide.** Generator Rev 29 fixed three
  descriptions of the D1 shunt clamp by finding every mention of the designator. Rev 30 found a
  fourth in §7.7, which described the rail as diode-dropped without naming D1 — the consequence
  of the old topology, not the part. Grep the effect as well as the designator.
- **Renaming a thing is not re-examining it.** Generator Rev 31 established that the 74HCT02
  could not prevent shoot-through, and corrected the heading, the safety notes and the BOM
  description accordingly. It left the cross-coupled gate topology in place for nine more
  revisions, until someone asked whether the interlock was needed at all. Removed at Rev 40.
  When a justification turns out to be wrong, check whether the circuit it justified is still
  wanted.
- **A protection everyone names may not be the protection doing the work.** The generator's
  74HCT02 was called a shoot-through interlock from Rev 5 to Rev 30, in four places including the
  document title and the safety notes. Shoot-through is prevented inside the IR2104, which derives
  both gate drives from one input pin. What the 74HCT02 actually does is translate 3.3V logic to
  the 5V the IR2104 input threshold needs. Remove it and the drivers stop seeing valid logic
  levels; that is also why HCT was specified over HC. Corrected at Rev 31. Ask what fails if a
  part is removed, not what it is named after.
- **A claim about a default is not a component.** Generator §5.3 asserted for twenty-five
  revisions that GPIO32 and GPIO33 default high on boot. They have no internal pull at reset, so
  the 74HCT02 interlock inputs floated through the bootloader window and the safe state rested on
  SD alone. Fixed at Rev 30 with R_PWMA_PU and R_PWMB_PU. A pin state that the design depends on
  needs a part holding it, not a sentence asserting it.
- **Section numbers collide when sections are inserted.** Generator §7 carried two §7.5 headings,
  one of them out of order, until Rev 30. Renumbering the later ones would have broken live
  cross-references, so the misplaced section moved to the end instead.
- **A guide split into a parts list and a net list needs two windows open.** All three
  schematic guides were written that way and all three were rebuilt in blocks, each block
  carrying its own parts table and its own nets, with the document name beside every reference.
  Found by drawing from one, not by reviewing it.
- **A designator without a net is as unbuildable as a net without a designator.** Trunk L1
  had a designator, a value, a quantity and a reason from Rev 4.4 to Rev 5.25, and no statement
  of what it connects to. Rev 5.25 caught the mirror-image case — unnamed footprints — and this
  one survived it. Fixed at trunk Rev 5.26.
- **The schematic can run ahead of the document too.** A 2-pin GPIO4 enable header existed in
  KiCad and in neither the generator document nor the BOM. Every other divergence found here has
  been the document leading and the parts list trailing; this one ran the other way, and nothing
  caught it because nothing in the document contradicted it. Absorbed as J9 at Rev 43.
- **A floating gate is not an off gate.** The generator had no MOSFET gate-to-source resistors
  through 45 revisions. Crss couples roughly a ninth of any drain step onto a floating gate, so
  applying 24V turns the low side partly on and leaves it there. Found on the bench, not in
  review, and only harmless because the supply was current-limited. Fixed at Rev 46 with two
  resistors — low side only, since every path from rail to ground runs through one.
- **A multi-way node written as pin pairs loses a connection.** The generator guide gave the
  bootstrap as `U2 pin8 ── VB_L, U2 pin6 ── SW_L` — two of the four things that land on SW_L,
  on one line among many that look the same. VS was left unwired on the breadboard and cost an
  evening, because a missing VS produces no error: the diode measures right, the switching node
  measures right, and the bootstrap reads 3V while appearing to contradict both. Nodes with
  three or more members are now written as nodes, not as pairs. Worth checking the trunk and
  station guides for the same shape.
- **A part named in prose is not a part.** R17, R18 and C15–C17 on the station board, and
  R_RST, C15–C17 and the two link groups on the trunk board, were each required by a section of
  their document, repeated in the layout notes, and absent from the BOM table and from every count
  that fed off it. Found at station Rev 3.25 and trunk Rev 5.25 by drawing the schematics. If a
  section says fit something, it needs a designator in the same revision that says it.
- **A corrected design leaves stale text behind.** The trunk §13 entry for J3 described
  positions 1 and 6 as unused and 6P4C cords as acceptable, seventeen revisions after Rev 5.8 put
  /RESET on those positions. §10.4 was right the whole time. When a change touches a connector,
  grep the BOM table for it.
- **A switch is not a strap.** SW1 was specified at Rev 3.5 to set the MCP23017 address and
  carried unchanged to Rev 3.24. The address pins have no internal bias, so three SPST switches
  left them undefined in one position. Corrected at Rev 3.25 with R19–R21.
- **KiCad library names from memory are unreliable.** Verify in the chooser — and read
  `kicad_library_plan.xlsx` first, which is where the answers already are. Three schematic
  guides were written carrying *verify* flags on symbols that file had already resolved
  (`74xx:74HCT02`, `Driver_FET:IR2104`, `Converter_DCDC:TSR1-24120`), and the generator guide
  raised T1's mounting as an open question when row 26 had recorded it as off-board and wired
  all along. Citing a file is not reading it.
- **A frequency rating describes the rated winding at rated load.** The OSD's "20Hz–20kHz ±1dB
  at 20W" is the 70V side into 245Ω. Driven from the 4Ω winding at nearly twice its rated voltage
  it saturated at about 4V RMS at 20Hz, and the design sat at 15.3V for 47 revisions. Nobody
  computed the magnetizing current the 14.6mH in §9.3 implied either — 8A RMS through a 500mA
  fuse. When a winding is used other than as rated, do the flux arithmetic (V × f_rated / f) and
  the magnetizing current (V / 2πfL) before anything else. Found at first power-up with T1.
- **Change entries appended by paragraph index land wherever the index points.** Generator Rev 40
  to Rev 47 change entries — eight revisions of history — were inserted into the middle of §12.2
  and each later revision appended to the same wrong place. Moved to §1.2 at Rev 48 (§16 since Rev 77). Anchor on the
  heading text, not on a paragraph number.
- **A pinout copied forward is never checked again.** Generator §8.2 gave the IR2104 as
  1 VB, 2 HO, 3 VS, 4 VCC, 5 LO, 6 COM, 7 IN, 8 SD. The datasheet is 1 VCC, 2 IN, 3 /SD,
  4 COM, 5 LO, 6 VS, 7 HO, 8 VB — seven of eight wrong, LO right by coincidence. It survived
  from the section's first draft to Rev 32, through the netlist, the schematic guide and
  every review, because each revision checked against the previous one. Drawn against a
  correct symbol it would have destroyed both drivers and four MOSFETs at power-on. Check
  pinouts against datasheets; a document is not evidence of its own pin numbers.
- **The station board is the telephone; the trunk board is the central office.** The
  switchboard feeds station loops; our trunk board feeds the switchboard. Getting this
  backwards produced two wrong revisions.
- **Distributed bulk capacitors specified once and never re-examined.** C14 and the
  station 1000µF both deleted on inspection. The 220µF and the 10µF reservoirs have been
  looked at and kept.
- **One connector type, one meaning.** RJ45 is a telephone line, 6P6C is the I²C bus, D-Sub25
  is audio, blue OSTTC is ring, black OSTTE is 24V in. The mis-plug reasoning in generator
  §4.1 only holds while that stays true, and it is what ruled out carrying 24V and ring to the
  switchboard on an RJ45 — the Olimex's PoE jack is on that same board, and unlike the 6P6C
  case the hazard would have run both ways.
- **Two conductors under one screw.** Generator J2 fed both the trunk board and the
  switchboard from Rev 24 to Rev 27, on a block specified for one conductor per position, and
  neither branch could be isolated without unwiring the other.
- **An index line is not a file.** The index recorded at station Rev 3.37 that the BOM's relay
  count was 23 station relays and that the R11/R12 note named station 24. The BOM file itself was
  still on the two-board build — station column "x2", 16 relays, board 1 strip 8 — and was found
  so on 2026-09-23; either the revised file was never uploaded or the revision was never made.
  Open the file before recording what it says.
