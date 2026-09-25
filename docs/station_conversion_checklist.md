# Station Board — Trunk-to-Station Conversion Checklist

Working document, 2026-09-11. Written against `trunk_schematic_guide.md` (§7 dated
2026-09-09, trunk Rev 5.29) and `station_schematic_guide.md` (station Rev 3.25/3.26).
Starting point: the trunk KiCad project copied to a `station` directory with a global
text rename of "trunk" → "station" already done, ERC and DRC clean.

**This file is not an authority for anything.** Every part, value, symbol, footprint and
net below is taken from the two schematic guides, and where they disagree with this file
they win. The one thing here that exists nowhere else — the netclass proposal in §6 — is
marked as such and belongs in `station_schematic_guide.md` as a new section once it is
checked. Retire this file when the station schematic and PCB match the station guide.

Each item is one of **KEEP**, **DELETE**, **MODIFY** or **ADD**. Order matters within the
strip: do the deletions first so designators are free before the additions claim them.

---

## 0. Before touching the strip

- **Sheet instance names.** The station guide's netclass patterns assume the eight sheet
  symbols are `STN1`…`STN8`. The global rename will have produced `STATION1`…`STATION8`
  (or whatever the trunk sheets were called with the word swapped). Either is fine, but
  §6 below and the station guide must use whatever the sheets are actually named. Decide
  now; check the PCB net list panel after the first Update PCB.
- **Whether channels 2–8 are already replicated in the PCB.** If they are, every strip
  edit below hits eight copies of footprints; delete the seven replicas and re-run Repeat
  Layout after the strip is finished. If only strip 1 is placed, work on it alone.
- **Do not convert the trunk's R11–R15 into station parts by editing values.** The two
  boards use the same numbers for different parts (trunk R11 is `R_set`; station R11 is a
  tap resistor). Editing a value leaves the `Function` field, the footprint and the
  layout position telling the wrong story. Delete and re-place.

---

## 1. Strip sheet — hierarchical labels

| Item | Action | Detail |
|---|---|---|
| `TIP`, `RING` | KEEP | Unchanged, passive |
| `A32_IN_H/C`, `A32_OUT_H/C` | KEEP | Unchanged |
| `SEIZE` (output) | MODIFY | Rename to `RING_DET`. Still output, still OC1 pin 6 |
| `RING_EN` (input) | MODIFY | Rename to `OFFHOOK`. Still input, still R4 |
| `RING_HI`, `RING_LO` global labels | DELETE | No ring bus on this board. Two globals at RLY1 NO contacts go |
| `NODE_A`, `NODE_B` local labels | KEEP | Same names; different meaning (line-side through closed NO contacts, isolated when released). Rewired in §2.2 |
| `V_FEED` | DELETE if present | Should already be gone at trunk Rev 5.29 |
| `+24V_BRD` power symbol | DELETE | The station strip uses no 24V. Only `+5V`, `+3V3`, `GND` remain |

---

## 2. Strip sheet — blocks

### 2.1 Jack and TVS (trunk §3.1 → station §4.1 / §4.2)

| Ref | Action | Detail |
|---|---|---|
| TVS1 | MODIFY | Value P6KE150CA → **P6KE120CA**. Symbol and footprint unchanged. Still the only part not behind a contact |
| RLY1 | KEEP, rewire | Same part, symbol, footprint. Contacts rewired — see 2.2 |

### 2.2 Relay contacts and loop (station §4.2) — replaces trunk 3.2 and 3.3

The trunk relay switched between loop feed (NC) and ring bus (NO). The station relay
connects the line to the circuit (NO) and isolates it (released). **Do not keep the
trunk contact wiring.**

| Ref | Action | Detail |
|---|---|---|
| RLY1 pole 1 NC → NODE_A | DELETE wire | Pole A NC becomes NO CONNECT |
| RLY1 pole 1 NO → RING_HI | DELETE wire | Pole A NO becomes → `NODE_A` |
| RLY1 pole 2 NC → NODE_B | DELETE wire | Pole B NC becomes NO CONNECT |
| RLY1 pole 2 NO → RING_LO | DELETE wire | Pole B NO becomes → `NODE_B` |
| NC flags on both NC contacts | ADD | Four unconnected pins per strip otherwise |
| Q4 (MJE350), Q3 (2N3906) | DELETE | Current source |
| R11 `R_set` 22R 0309 | DELETE | |
| R12 `R_bias` 10k | DELETE | |
| R1 100R 1W 0414 | DELETE | |
| C1 `C_C` 1nF | DELETE | |
| D1 1N4007 | DELETE | |
| R13 `R_LOOP` 150R 2W 0516 | DELETE | Footprint is the same DIN0516 as station R3 — delete anyway; the net position and `Function` differ |
| R14 `R_DET` 470R | DELETE | |
| `Q4C`, `R1_D1`, `Q4E`, `Q4B`, `OC_IN` labels | DELETE | LOOP-class and current-source nets. `OC_IN` is re-created in 2.3 on a different net |
| R3 330R 2W | ADD | `Device:R`, `Resistor_THT:R_Axial_DIN0516_L15.5mm_D5.0mm_P20.32mm_Horizontal`. `NODE_A` ── R3 ── `NODE_B`. ~1.6W continuous — placement note |
| R11, R12 22.1k 1% | ADD | `Device:R`, DIN0207. R11: `TIP` ── `NODE_A`; R12: `RING` ── `NODE_B`. **DNP**, `Function` = "TAP STRIP ONLY — station §7.9.7". Across the NO contacts |

### 2.3 Ring detector (station §4.1) — rebuilt around the surviving OC1

| Ref | Action | Detail |
|---|---|---|
| OC1 HCPL3700M | KEEP, rewire | Same symbol and footprint. **Input mode flips**: trunk drove DC on pins 2/3 with 1/4 NC; station drives AC on pins 1/4 with 2/3 NC. Move the NC flags from 1/4 to 2/3; add NC on pin 7. Replace the text note |
| OC1 pin 2 ← R14 wire | DELETE | |
| OC1 pin 3 → GND wire | DELETE | |
| R14 (station `R1a`) 10k 0.5W | ADD | `Device:R`, `Resistor_THT:R_Axial_DIN0309_L9.0mm_D3.2mm_P12.70mm_Horizontal`. From `TIP` |
| R15 (station `R1b`) 10k 0.5W | ADD | Same footprint. R14 ── R15 ── C4 |
| C4 1µF 250V film | ADD | `Device:C`, `Capacitor_THT:C_Rect_L*_W*_P5.00mm` (body size marked *Verify* in library plan). C4 ── OC1 pin 1 |
| OC1 pin 4 ← `RING` | ADD wire | Direct |
| R17 0R link | ADD | `Device:R`, DIN0207. `+3V3` ── R17 ── OC1 pin 8. **Fit.** `Function` = "OC1 V_CC link, station §3.6" |
| C5 0.1µF | KEEP | Pin 8 to pin 5, at the device — now downstream of R17 |
| R2 4.7k | KEEP | Pin 6 to `+3V3`. Add the tap- and monitor-strip note: R2 stays fitted on board 3 strips 7 and 8 when OC1 is absent (Port A bits 6 and 7 pull-up) |
| OC1 pin 6 → `SEIZE` | MODIFY | Now → `RING_DET` |
| OC1 pin 5 → GND | KEEP | |

The trunk's OC1 pin 8 was wired straight to `+3V3`; that wire is replaced by R17.

### 2.4 Relay driver (trunk §3.4 → station §4.3)

| Ref | Action | Detail |
|---|---|---|
| Q2, R4, D5, C9 | KEEP | Unchanged |
| R15 `R_pd` 10k | MODIFY | Renumber to **R16** (station assignment; R15 is now `R1b`). Same part, same net |
| `RING_EN` ── R4 | MODIFY | Now `OFFHOOK` ── R4 |
| `Q2B`, `COIL` labels | KEEP | |
| Text note | ADD | "Nothing else in the coil path — no series LED, no limiting resistor (station §5.4)" |
| `NOT FITTED ON TAP STRIP` field | ADD | On RLY1, Q2, D5, R4, R16, C9, R3, R14, R15, C4, OC1, C5 |

### 2.5 Audio (trunk §3.5 → station §4.4)

| Ref | Action | Detail |
|---|---|---|
| C2 0.47µF 250V | MODIFY | Renumber to **C3**. Same part, same footprint, same net (`NODE_A` ── C3 ── T2 pin 1). Whether station §11 uses C2 for anything is not stated in the station guide; leave C2 unassigned rather than guess |
| T2, R5–R8 | KEEP | Unchanged, including dots on 1 and 4 |
| `T2P`, `T2S_H`, `T2S_C` labels | KEEP | |
| R13 2.2k | ADD | `Device:R`, DIN0207, across T2 secondary (`T2S_H` ── `T2S_C`). **DNP** pending station §7.9.5 |

Note the trunk strip's R13 (`R_LOOP`, deleted in 2.2) and the station strip's R13 (secondary
load) share a number and nothing else. This is the clearest case for deleting rather than
editing.

### 2.6 Strip designator map after conversion

| Station ref | Doc name | Came from |
|---|---|---|
| TVS1, RLY1, Q2, R2, R4, R5–R8, D5, C5, C9, OC1, T2 | same | Trunk, kept |
| C3 | C3 | Trunk C2, renumbered |
| R16 | R_pd | Trunk R15, renumbered |
| R3, R11, R12, R13, R14, R15, R17, C4 | per station guide §1 | New |
| — | — | Trunk Q3, Q4, R1, R11, R12, R13, R14, C1, D1 deleted |

---

## 3. Root sheet — blocks

### 3.1 Power entry (trunk §4.1 → station §5.1)

| Ref | Action | Detail |
|---|---|---|
| J5, FH1, D6, C10, C11, U3, C12, C15, C16, U4, C8, C17, C6, C7 | KEEP | Unchanged, including D6 as shunt and F1 upstream of it |
| F1 | MODIFY | 500mA → **250mA** slow-blow, 0218.250MXP. Same holder |
| C13 1000µF | DELETE | No audio-band bulk on this board — the loop feed is R3 in the tip-ring loop, never on `+24V_BRD`. Add the text note saying it was considered and removed |
| `/24V_IN` label | KEEP | J5 pin 1 to F1 |

### 3.2 Ring bus (trunk §4.2)

| Ref | Action | Detail |
|---|---|---|
| J6, F2, FH2 | DELETE | Whole block |
| `/RING_IN`, `RING_HI`, `RING_LO` | DELETE | Confirm no global label of either name survives anywhere — a leftover global label on one strip becomes an eight-way net with no source |
| Ring bus colour/hatching, text note at F2 | DELETE | |

### 3.3 I²C and expanders (trunk §4.3 → station §5.2 / §5.3)

| Ref | Action | Detail |
|---|---|---|
| J3 6P6C | MODIFY | Becomes **J3A**; ADD **J3B**, same symbol and footprint, wired in parallel pin-for-pin. Footprint `Connector_RJ:RJ12_Amphenol_54601-x06_Horizontal` is a candidate, not verified |
| TVS2, C18 | KEEP | At the jacks |
| R11 `R_RST` 10k | MODIFY | Renumber to **R18**. Same net |
| R9, R10 | KEEP | Still DO NOT FIT |
| U1 | MODIFY | Value/field: address 0x23 → **0x20–0x22 by SW1** |
| U2 | KEEP | Footprint only, DNP; address field → 0x24–0x26 |
| JP1, JP2, JP3 0R straps | DELETE | Replaced by SW1 + R19–R21. Delete these **before** renumbering JP4 (3.6), or the numbers collide |
| U1 A0/A1/A2 wiring to straps | DELETE | |
| SW1 CTS 206-3ST | ADD | `Switch:SW_DIP_x03`, `Button_Switch_THT:SW_DIP_SPSTx03_Slide_9.78x9.8mm_W7.62mm_P2.54mm`. Each position: U1 A-pin to GND |
| R19, R20, R21 10k | ADD | `Device:R`, DIN0207. U1 pin 15/16/17 to `+3V3` respectively. `A0`, `A1`, `A2` labels kept |
| Text note | ADD | Closed = 0; all open = 0x27 = not a station address (station §9.2). Silkscreen the sense |
| Text note at J3 | MODIFY | Six-conductor cord requirement stays; add that 3/5/6 are ground but not interchangeable at the cable (interleave) |

### 3.4 Expander to strips (trunk §4.4 → station §5.4)

| Item | Action | Detail |
|---|---|---|
| `SEIZE_1`…`SEIZE_8` | MODIFY | → `RING_DET_1`…`RING_DET_8`, U1 GPA0–7 |
| `RING_EN_1`…`RING_EN_8` | MODIFY | → `OFFHOOK_1`…`OFFHOOK_8`, U1 GPB0–7 |
| Sheet symbol pin names | MODIFY | Follow the child (§1); the sheet symbols pick up the rename when the child's hierarchical labels change — check each of the eight symbols shows `RING_DET` and `OFFHOOK`, not stale pins |

After this there are sixteen nets whose names begin `RING`: `/RING_1`…`/RING_8` (line)
and `/RING_DET_1`…`/RING_DET_8` (logic). Check the netlist for exactly sixteen before
layout.

### 3.5 Lines J7A, J7B (trunk §4.5 → station §5.5)

| Item | Action | Detail |
|---|---|---|
| J7A, J7B, pinout, `TIP_n`/`RING_n` nets | KEEP | Identical |
| Text note | ADD | Board 3 J7B strip-7 pair is the operator talking path; strip-8 pair unused (monitor strip) |

### 3.6 Audio J1, J2 (trunk §4.6 → station §5.6)

| Item | Action | Detail |
|---|---|---|
| J1, J2, pin mapping | KEEP | Identical |
| JP4 0R link | MODIFY | Renumber to **JP1** (after 3.3 has freed the number). Still DNP, still `DSUB_GND` to GND |
| Channel note | MODIFY | Trunk: A32 channel = 24 + n. Station: A32 channel = (board − 1) × 8 + n. Update the sheet text and the J1/J2 fields |

### 3.7 Root designator map after conversion

| Station ref | Came from |
|---|---|
| J5, FH1, D6, C10–C12, C15–C18, U3, U4, C6–C8, TVS2, R9, R10, U1, U2, J7A/B, J1, J2 | Trunk, kept |
| J3A | Trunk J3 |
| R18 | Trunk R11 (`R_RST`) |
| JP1 | Trunk JP4 |
| J3B, SW1, R19–R21 | New |
| — | Trunk J6, F2, FH2, C13, JP1–JP3 deleted |

---

## 4. Text and fields to sweep

- Title block: board name, revision reference (station Rev 3.26).
- `Function` fields on every kept part: unchanged. On renumbered parts (C3, R16, R18, JP1):
  unchanged. On new parts: per station guide.
- Tap- and monitor-strip notes: R2 trap, R11/R12/R13 tap-only, the "station §7.9.7 and
  §7.9.8 are the only authority" text box.
- The OC1 input-mode note is the most important text edit on the sheet; the symbol types all
  four input pins passive and nothing but the note and the NC flags records which mode the
  board is in.

---

## 5. PCB

### 5.1 Strip footprints

Update PCB from schematic with "delete footprints with no symbol" on. Expect, per strip
laid out:

- Removed: Q3, Q4, trunk R1, R11, R12, R13, R14, C1, D1 — nine footprints, the whole
  current-source end of the strip.
- Added: R3 (0516), R11, R12, R13, R17 (0207), R14, R15 (0309), C4 (tall 5.00mm-pitch
  film) — eight footprints.
- Kept in place: RLY1, TVS1, T2, C3, R5–R8, Q2, R4, R16, D5, C9, OC1, C5, R2.

Keep the kept parts where they are; the relay/TVS end and the driver/OC1 end of the strip
are unchanged in kind. The freed current-source area is where the ring detector and R3 go.
R3 wants standoff and distance from C9 and the other electrolytics.

### 5.2 Root

- Remove J6/F2/FH2 and the ring spine. The 32 root lanes for audio and the 16 line nets
  stay as they are; the 16 control lanes are renamed, not moved.
- The address strap area (three 0207) becomes SW1 plus three 0207.
- One more 6P6C on the I²C edge. Two D-Subs and two RJ45s already share the other edge;
  where J3B fits is a placement question.

### 5.3 Stack-up (trunk guide §7.5)

Four layers unchanged. On In2 the strips no longer need a `+24V_BRD` band: nothing on the
station strip uses 24V. The In2 comb becomes `+5V` (relay end) and `+3V3` (OC1 end); 24V
exists only around J5/D6/C10/C11/U3. Redraw the split lines before placing strips.

The inner-layer keepout at the HV edge now covers J7A/J7B, their wiring, the relay
contact ends, and the ring-detector section (R14, R15, C4, OC1 pins 1/4). There is no
ring spine and no J6. The OC1 body slot is still required (station §12).

---

## 6. Netclasses — PROPOSAL, not yet in any authority

The station guide has no netclass section. What follows is the trunk guide §7 with the
station's net set applied. It needs checking and then writing into
`station_schematic_guide.md` as its own section, after which this copy is deleted.

**Classes.** Keep **Default**, **POWER** and **LINE** with the trunk values. **Delete RING
and LOOP** — no ring bus, no current source. Three classes.

**Assignments.**

| Class | Pattern | Net |
|---|---|---|
| POWER | `+24V_BRD`, `/24V_IN`, `+5V`, `+3V3`, `GND` | As trunk |
| LINE | `/TIP_*`, `/RING_*` | Root, J7 to sheet pins. `/RING_*` must not catch `/RING_DET_*` — it will, because the wildcard matches. Use `/RING_?` if the build supports single-character wildcard; otherwise list `/RING_1`…`/RING_8` explicitly. **Check the net list panel** |
| LINE | `/STN*/NODE_A`, `/STN*/NODE_B` | Strip: relay NO contacts, R3, R11/R12 far side, C3, T2 pin 3 |
| LINE | `/STN*/DET_1`, `/STN*/DET_2` — **new labels** | R14–R15 junction; R15–C4 junction. Line potential |
| LINE | `/STN*/OC_IN` — re-created | C4 to OC1 pin 1. Line potential (AC-coupled, current-limited, but full line voltage) |
| Default | everything else | As trunk §7.4 less the deleted nets; `RING_DET`/`OFFHOOK` replace `SEIZE`/`RING_EN`; `Q2B`, `COIL`, `T2P`, `T2S_H`, `T2S_C` unchanged; `A0`–`A2` now include R19–R21 and SW1; add OC1 pin 8 node between R17 and C5 [`OC_VCC`] |

Replace `STN*` with the actual sheet names (§0).

**HV rule** (`station_board.kicad_dru`):

```
(version 1)

(rule "HV zone to low voltage"
  (condition "A.NetClass == 'LINE' && B.NetClass != 'LINE'")
  (constraint clearance (min 3mm)))
```

**Where this will fire, and the new cases the trunk board did not have:**

- **RLY1 NO to NC contacts.** On the trunk both were HV (LINE and RING) and sat at class
  clearance. Here the NC pads have no net, so their NetClass is empty and the rule fires at
  every relay, 2.54mm pitch, four pads per strip. Two ways out, both with a cost:
  give the NC pins single-pin local labels (`RLY_NC_A`, `RLY_NC_B`) assigned to LINE — I am
  not certain ERC accepts a labelled single-pin net without a warning; check — or exclude per
  footprint with the reason recorded. Do not weaken the rule to `B.NetClass != ''`; that
  would also stop it catching genuinely unconnected copper near the line.
- **OC1 pins 1/4 (LINE) to pins 2/3 (no net, NC).** Same problem, 2.54mm pitch. Same two
  options. The trunk had the mirror case (pins 2/3 Default, 1/4 NC) and the rule did not fire
  because Default-to-empty is not a rule condition.
- **OC1 pins 1/4 to pins 5–8.** Across the DIP body, 7.62mm; the slot completes the creepage.
- **RLY1 contacts to coil.** Same as the trunk — decided by the J104D drawing.
- **R11/R12 (DNP).** Both pads LINE; class clearance only.
- **TVS1, R14, R15, C4.** Both pads LINE.

The 141V peak sizing argument is unchanged: the station lines carry the same ring
voltage, and on this board they carry it in normal operation rather than by mistake.

---

## 7. Done when

- ERC clean with the NC flags in place and the OC1 mode note on the sheet.
- Netlist shows 16 `RING*` nets, 8 `RING_DET_n`, 8 `OFFHOOK_n`, no `RING_HI`/`RING_LO`, no
  `SEIZE`, no `V_FEED`.
- Every strip part matches the station guide §4 tables by ref, value, symbol, footprint
  and `Function`; every root part matches §5.
- Netclass section written into `station_schematic_guide.md` and this file deleted.
