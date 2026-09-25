# Station Board — KiCad Schematic Drawing Guide

Derived from station circuit Rev 3.25 and the KiCad library plan; R11/R12 value updated to station Rev 3.27 (22.1k → 22k 1%); tap and monitor strips updated to station Rev 3.40 (operator tap on board 3 strip 7, audience monitor output on strip 8).
Structure: one root sheet carrying everything common, plus **8 instances of a single
hierarchical sheet** `station_circuit.kicad_sch`.

Three station boards are built from this one schematic. They differ only in the SW1
address strap and which A32 D-Sub pair they land on — neither of which is a schematic
difference — and in two strips on board 3 being stuffed differently — strip 7 as the
operator tap and strip 8 as the audience monitor output — which §2 is entirely about.

`trunk_schematic_guide.md` is the companion document. Where the two boards do the same
thing this guide points at it rather than repeating it, because the two boards share most
of their part list and two copies of the same paragraph is how they drift apart.

---

## 1. Sheet structure

```
station_board.kicad_sch        (root)
 ├── STN1  → station_circuit.kicad_sch
 ├── STN2  → station_circuit.kicad_sch
 ├── ...
 └── STN8  → station_circuit.kicad_sch
```

Same mechanism as the trunk board: draw the child sheet once, add the other seven by
placing a new sheet and selecting the same file so KiCad makes instances rather than
copies. Annotate **sheet by sheet**, "first free after sheet number × 100". Trunk guide §1
has the full reasoning and it applies here unchanged.

### Designators, and why this board is worse than the trunk

The trunk board had a collision between document names and KiCad references. This board has
that plus a name KiCad will simply refuse: **`R1a` and `R1b` are not valid references.** A
KiCad reference is a letter prefix and a number, nothing else. The two 10kΩ ring-detector
resistors have no legal designator at all as the document names them.

So the same discipline as the trunk board, and for the same reason: let KiCad own the
reference, put the document name in a user field called **`Function`**, and make it visible
on the parts where the value does not tell you what the part is. `10k` appears five times on
this board in three different jobs.

The document uses R1a, R1b and R2–R13. R14 upward is free:

| Sheet | Doc name | Assign | Notes |
|---|---|---|---|
| Strip | R1a | R14 | |
| Strip | R1b | R15 | |
| Strip | R_pd | R16 | |
| Strip | — (station §3.6 OC1 V_CC series link) | R17 | new; has no designator in the doc |
| Root | — (station §9.4 /RESET pull-up) | R18 | new; has no designator in the doc |
| Root | — (station §9.2 SW1 address straps ×3) | R19, R20, R21 | new; see §5.3 — these may not exist yet |

R1 is left unused deliberately. The document's name for that part is the *pair* R1a/R1b,
and giving one half of a pair the number R1 while the other half is R14 is worse than not
adopting the name at all. R14/R15 keeps them symmetric and the `Function` field keeps them
findable.

As on the trunk board, annotation will not preserve any of this — "first free after sheet
number × 100" fills in the order KiCad walks the sheet, so R14 may land as R107. The
`Function` field is the only thing that survives, and it is what lets you see R305 on the
PCB and know it is R1b on station 21.

### C13 and C14 are retired, not free

The 0.1µF and 10µF counts in `telephone_bom.xlsx` are 12 and 10 per station board. Work
them out from the parts below and they only reconcile if three capacitors that have no
designator in station §11 are included: **C15** (10µF at U4's input), **C16** (0.1µF at
U4's input) and **C17** (0.1µF at U4's output), added by station §10.6. These are the same three
numbers, in the same three jobs, as the trunk board. That is worth more than closing a
numbering gap, so:

- **C13** stays unused. It was the 1000µF audio-band bulk added at Rev 3.19 and withdrawn
  at Rev 3.23 (station §10.7). Reusing the number makes any board or document from Rev 3.19–3.22
  ambiguous.
- **C14** stays unused. It is the trunk board's deleted local bulk. Keeping the two boards'
  capacitor numbering aligned is the point.

C15–C17 need writing back into station §11 the same way they need writing back into the
trunk document.

---

## 2. The operator tap, and how it survives being replicated

Strip 7 on board 3 is stuffed as the operator tap (station §7.9.6). Relative to a station strip it
**fits** R11 and R12, and **omits** RLY1, Q2, D5, R4, R16, C9, R3, R14, R15, C4, OC1 and C5
(station §7.9.7). Strip 8 on board 3 is the audience monitor output (station §7.9.8): it
**fits** R2 and nothing else, and the loudspeaker cable is soldered to the J2-side pads of the
unfitted R7 and R8. Two strips in twenty-four differ from the other twenty-two. Neither
difference is a schematic change.

The strip is drawn once and replicated everywhere, in both the schematic and the PCB, and the
tap parts are part of that replication. That is settled, and it is the right call for layout:
one laid-out strip copies to the other seven and the eight copies are identical footprint sets.

The thing to be clear about is why replication and correct stuffing are not in tension. A sheet
instance owns its reference designators; **values, footprints and symbol attributes — including
the do-not-populate flag — belong to the symbol and are shared across all eight**. So the tap
strip cannot be a DNP variant of the shared sheet. But DNP is a BOM and position-file attribute:
it does not remove a footprint from the board. Set it and the copper is unchanged.

So in the shared sheet:

- **R11, R12, R13 → DNP.** Correct for all 8 strips on boards 1 and 2 and 7 of the 8 on
  board 3, which is 23 strips out of 24. The footprints are placed on every strip regardless, which is what
  station §7.9.1 wants and what makes the layout replicable.
- **Everything else → fitted.** Correct for every strip except the tap and the monitor strip.
- Carry the exception in the `Function` or a `Notes` field — `TAP STRIP ONLY — station §7.9.7`
  on R11/R12/R13, and `NOT FITTED ON TAP STRIP` on RLY1, Q2, D5, R4, R16, C9, R3, R14, R15,
  C4, OC1 and C5. Fields are shared across the eight instances, which is what you want: the
  note is true of the same part on every strip.
- **Station §7.9.7 and §7.9.8 are the only authority for the stuffing of board 3's strips 7 and 8.** Say so in a text box on the sheet.
  The schematic is not going to carry it and should not pretend to.

Two consequences to accept rather than discover:

**The exported BOM will be wrong for three parts.** With R11/R12 DNP, KiCad exports zero
22kΩ where the build needs two. `telephone_bom.xlsx` says 2 and is the source of truth;
reconcile the export by hand for R11, R12 and R13, and nothing else. Station §11 counts these
as ×8 — a footprint count with a stuffing note — while the BOM counts 2, a purchasing figure.
Both are defensible and they are not the same convention; know which one you are
reading before a third reader has to work it out.

**R2 is the trap.** Station §7.9.7 and §7.9.8 keep R2 fitted on the tap and monitor strips even
though OC1 is absent, so Port A bits 6 and 7 are held high instead of floating. It is the only part of the ring detector that
stays. Anyone reading "the ring detector comes out" and pulling the whole block will remove
it, and the symptom is an intermittent ring on a station that does not exist. Put that on the
sheet next to R2, not only in station §7.9.7 and §7.9.8.

## 3. Hierarchical sheet pins

Eight pins per sheet, all power via global symbols. There is **no ring bus on this board** —
no `RING_HI`/`RING_LO`, no F2, no J6. Ring arrives from the switchboard on tip and ring like
any other line voltage, so the hazardous net is the per-strip jack net and nothing global
needs the trunk guide's colour-and-hatching treatment.

| Pin name | Type | Goes to (root) |
|---|---|---|
| `TIP` | passive | J7A/J7B, one pair per station |
| `RING` | passive | J7A/J7B, same pair |
| `A32_IN_H` | output | J1, hot of channel n |
| `A32_IN_C` | output | J1, cold of channel n |
| `A32_OUT_H` | input | J2, hot of channel n |
| `A32_OUT_C` | input | J2, cold of channel n |
| `RING_DET` | output | U1 Port A bit n |
| `OFFHOOK` | input | U1 Port B bit n |

Pin names are identical on all eight sheet symbols — a sheet pin is the parent-side face of
the child's hierarchical label and KiCad matches by name. The numbering lives on the root
sheet's nets:

| Sheet pin (all 8) | Root-sheet nets |
|---|---|
| `TIP` | `TIP_1` … `TIP_8` |
| `RING` | `RING_1` … `RING_8` |
| `A32_IN_H` | `A32_IN_H_1` … `_8` |
| `A32_IN_C` | `A32_IN_C_1` … `_8` |
| `A32_OUT_H` | `A32_OUT_H_1` … `_8` |
| `A32_OUT_C` | `A32_OUT_C_1` … `_8` |
| `RING_DET` | `RING_DET_1` … `RING_DET_8` |
| `OFFHOOK` | `OFFHOOK_1` … `OFFHOOK_8` |

`RING_n` is a line conductor and `RING_DET_n` is a logic signal, and they differ by a suffix.
A mistyped label reads perfectly plausibly. ERC will catch a pin left unconnected but not two
labels swapped between things that both exist, so check the netlist for sixteen distinct
`RING*` nets before layout rather than trusting the schematic to look right.

**Power nets** — `PWR_FLAG`-backed global symbols on the root sheet only: `+24V_BRD`, `+5V`,
`+3V3`, `GND`. Inside the strip just drop the matching power symbols.

---

## 4. The station strip — four blocks

Each block carries its parts and then its nets. Draw a block start to finish before moving
on; you should not need a second window open on this document.

Values from station Rev 3.25 §11. Every symbol and footprint below is taken from
`kicad_library_plan.xlsx`, which records them as checked against the KiCad 9.0.0 stock
libraries on 21 Aug 2026. Nothing here is a name supplied from memory. The TY-311P
footprint now exists, but its library and footprint name is written down nowhere and this
guide is not going to guess it — put it in `kicad_library_plan.xlsx` row 25 and it
propagates from there.

The **document name** column is the bridge to station §11, which names these parts
differently. `NODE_A` and `NODE_B` are local labels: the two nets that are line-side
through the closed relay contacts and isolated when it releases.

---

### 4.1 Jack, TVS and ring detector

| Ref | Doc name | Value | Symbol | Footprint |
|---|---|---|---|---|
| TVS1 | TVS1 | P6KE120CA | `Device:D_TVS` | `Diode_THT:D_DO-15_P10.16mm_Horizontal` |
| R14 | R1a | 10k 0.5W | `Device:R` | `Resistor_THT:R_Axial_DIN0309_L9.0mm_D3.2mm_P12.70mm_Horizontal` |
| R15 | R1b | 10k 0.5W | `Device:R` | same as R14 |
| C4 | C4 | 1µF 250V film | `Device:C` | `Capacitor_THT:C_Rect_L*_W*_P5.00mm` |
| OC1 | OC1 | HCPL3700M | `switchboard:HCPL-3700` | `Package_DIP:DIP-8_W7.62mm` |
| R17 | — | 0R link | `Device:R` | DIN0207 — OC1 V_CC feed, **fit** |
| C5 | C5 | 0.1µF | `Device:C` | `Capacitor_THT:C_Disc_D5.1mm_W3.2mm_P5.00mm` |
| R2 | R2 | 4.7k | `Device:R` | `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` |

Permanently across the line, ahead of the relay, because ring has to be detectable while
the station is on-hook.

```
TIP  ──┬── TVS1 ─────────────────────────────────────── RING
       └── R14 (10k) ── R15 (10k) ── C4 (1µF 250V) ──── OC1 pin 1 (AC1)
RING  ─────────────────────────────────────────────────  OC1 pin 4 (AC2)

OC1 pins 2, 3 ── NO CONNECT      ← selects the internal bridge; place NC flags
OC1 pin 7     ── NO CONNECT
OC1 pin 5     ── GND
OC1 pin 8     ── R17 (0R) ── +3V3
C5 from OC1 pin 8 to OC1 pin 5, at the device
OC1 pin 6 ── R2 (4.7k) ── +3V3
OC1 pin 6 ── RING_DET
```

**P6KE120CA, not the trunk board's P6KE150CA.** The two boards use deliberately different
TVS voltages, and each is sized for its own line. Set the value field per board and never
standardise them.

**Pins 2 and 3 must be explicitly open, and this is the opposite of the trunk board.** The
AC and DC input pairs are alternative entries to the same buffer and the datasheet
specifies each with the other pair floating. The trunk board drives DC on pins 2/3 with 1
and 4 open; this board drives AC on pins 1/4 with 2 and 3 open. The library plan's
HCPL-3700 symbol types pins 1–4 as passive, so ERC will not object either way — the
no-connect flags are the only thing on the sheet that records which mode this is. Put a
text note beside OC1 saying so.

C5 sits between pins 8 and 5, downstream of R17. It is a datasheet requirement, not
decoration, and it belongs at the device rather than wherever the sheet looks tidy.

R17 has no designator in station §11 and no line in `telephone_bom.xlsx`. It is station
§3.6's optional ≥240Ω in the V_CC feed, fitted as a 0Ω link, and station §12 already asks
for the footprint. Assigning it a number is this guide's doing — see §7.

**R2 is the trap on the tap and monitor strips.** Station §7.9.7 and §7.9.8 keep R2 fitted
even though OC1 is absent, so Port A bits 6 and 7 are held high instead of floating. It is the only part of the ring
detector that stays. Anyone reading "the ring detector comes out" and pulling the whole
block will remove it, and the symptom is an intermittent ring on a station that does not
exist. Put that on the sheet next to R2, not only in station §7.9.7 and §7.9.8.

---

### 4.2 Relay contacts and the loop

| Ref | Doc name | Value | Symbol | Footprint |
|---|---|---|---|---|
| RLY1 | RLY1 | J104D2C5VDC.15S | `Relay:Relay_DPDT` | `Relay_THT:Relay_DPDT_Omron_G6A` |
| R3 | R3 | 330R 2W | `Device:R` | `Resistor_THT:R_Axial_DIN0516_L15.5mm_D5.0mm_P20.32mm_Horizontal` |
| R11, R12 | R11, R12 | 22k 1% metal film matched | `Device:R` | DIN0207 — **DNP, tap strip only** |

```
TIP  ── RLY1 pole A NO ── NODE_A
RING ── RLY1 pole B NO ── NODE_B
RLY1 pole A NC, pole B NC ── NO CONNECT

NODE_A ── R3 (330R 2W) ── NODE_B

R11 (22k) from TIP  to NODE_A     [DNP — bridges pole A NO]
R12 (22k) from RING to NODE_B     [DNP — bridges pole B NO]
```

Both poles are normally open and both close together: on-hook is the released state and
the whole station circuit is lifted clear of the line. That is the opposite sense from the
trunk relay, which switches between the loop feed and the ring bus and has no
released-and-isolated position. Do not copy the trunk sheet's contact wiring.

The NC contacts are genuinely unused. Flag them, or ERC will report four unconnected pins
per strip and you will learn to ignore ERC on this board.

R11/R12 sit directly across the NO contacts. A strip with both R11/R12 **and** RLY1 fitted
leaves 22kΩ permanently bridging the contacts and puts C3 and T2 partly on the line with
the station on-hook (station §12). That is invisible once the board is racked, so it wants
the note on the schematic as well as the silkscreen.

R3 runs about 1.6W continuously in a 2W part, eight per board — a placement constraint.
See §6.

---

### 4.3 Relay driver

| Ref | Doc name | Value | Symbol | Footprint |
|---|---|---|---|---|
| Q2 | Q2 | 2N2222A | `Transistor_BJT:Q_NPN_EBC` | `Package_TO_SOT_THT:TO-92_Inline` |
| R4 | R4 | 1k | `Device:R` | DIN0207 |
| R16 | R_pd | 10k | `Device:R` | DIN0207 |
| D5 | D5 | 1N4148 | `Diode:1N4148` | `Diode_THT:D_DO-35_SOD27_P7.62mm_Horizontal` |
| C9 | C9 | 10µF 50V | `Device:C_Polarized` | `Capacitor_THT:CP_Radial_D5.0mm_P2.00mm` |

```
OFFHOOK ── R4 (1k) ── Q2 base
Q2 base ── R16 (10k) ── GND
Q2 emitter ── GND
Q2 collector ── RLY1 coil (−)
RLY1 coil (+) ── +5V
D5 anode ── Q2 collector,  D5 cathode ── +5V
C9 (10µF) across +5V ── GND, at the coil
```

R16 is not optional — Port B floats from power-on until firmware configures the expander,
and again after any /RESET, and a floating base is not reliably off (station §5.2).

**Nothing else goes in the coil path.** Station §5.4 leaves 5% pull-in margin at 85°C
against a 5V rail at its lower limit, so no current-limiting resistor and no series
indicator LED. If a per-station lamp is ever wanted it gets its own driver. Worth a text
note on the sheet, because a series LED is the kind of thing someone adds later without
reading station §5.4.

---

### 4.4 Audio

| Ref | Doc name | Value | Symbol | Footprint |
|---|---|---|---|---|
| C3 | C3 | 0.47µF 250V film | `Device:C` | `Capacitor_THT:C_Rect_L18.0mm_W*_P15.00mm_FKS3_FKP3` |
| T2 | T2 | Triad TY-311P | `switchboard:XFMR_TY-311P` | `switchboard:XFMR_TY-311P` — pads 1/3/4/6 |
| R5, R6 | R5, R6 | 1k matched | `Device:R` | DIN0207 |
| R7, R8 | R7, R8 | 1k matched | `Device:R` | DIN0207 |
| R13 | R13 | 2.2k | `Device:R` | DIN0207 — **DNP** until station §7.9.5 says otherwise |

```
NODE_A ── C3 (0.47µF 250V) ── T2 primary (+)
NODE_B ───────────────────── T2 primary (−)

T2 secondary hot  ── R5 ── A32_IN_H
T2 secondary cold ── R6 ── A32_IN_C
A32_OUT_H ── R7 ── T2 secondary hot
A32_OUT_C ── R8 ── T2 secondary cold

R13 (2.2k) across T2 secondary      [DNP]
```

R5/R6 and R7/R8 join at the secondary — receive and transmit share the winding.

There is no screen. T2 is a custom symbol and a custom footprint, both
`switchboard:XFMR_TY-311P`, and the part has four pins — so the T2 screen that station
station §7.3 earthed to chassis and station §12 starred to a single point was never a terminal that
existed. Both sections are corrected at Rev 3.25. Draw nothing here and leave no fifth
pad. §5.6's unstuffed D-Sub ground link is the one deliberate connection between the
equipment side and board ground.

The four pins are **numbered 1 and 3 for the primary and 4 and 6 for the secondary** — 2
and 5 are the absent centre taps of the TY body. Drawing the symbol rather than using the
stock generic is what makes that safe: KiCad matches pin number to pad number with no
remapping, and a 1-2-3-4 symbol against 1/3/4/6 pads would have landed symbol pin 3 on pad
3, the far end of the primary.

The two film capacitor footprints and the DIN0309 pair are marked *Verify* in the library
plan — the pitch is settled but the body size is not, and C4 at 1µF/250V is a tall box.
Confirm both against the datasheets before layout; there are sixteen of each in the
system.

---

## 5. Root sheet — six blocks

Same arrangement: parts, then nets, block by block.

No J6, no F2, no OSTTC020162 anywhere on this board. Those are ring-bus parts and the ring
bus does not reach here.

---

### 5.1 Power entry

| Ref | Doc name | Value | Symbol | Footprint |
|---|---|---|---|---|
| J5 | J5 | OSTTE020104, 3.50mm 125V | `Connector:Screw_Terminal_01x02` | `TerminalBlock_4Ucon:TerminalBlock_4Ucon_1x02_P3.50mm_Horizontal` |
| F1 | F1 | 250mA slow-blow, 0218.250MXP | `Device:Fuse` | carried by FH1 |
| FH1 | FH1 | Littelfuse 64900001039 | — | `Fuse:Fuseholder_Clip-5x20mm_*` — measure the 649 pitch |
| D6 | D6 | 1N5822 | `Diode:1N5822` | `Diode_THT:D_DO-201AD_P12.70mm_Horizontal` — **shunt, not series** |
| C10 | C10 | 47µF 50V | `Device:C_Polarized` | `Capacitor_THT:CP_Radial_D6.3mm_P2.50mm` |
| C11 | C11 | 0.1µF | `Device:C` | `C_Disc_D5.1mm_W3.2mm_P5.00mm` |
| U3 | U3 | TSR 2-2450 | `Converter_DCDC:TSR2-2450` | `Converter_DCDC:Converter_DCDC_TRACO_TSR2-24xxN_TSR2-24xxxN_THT` |
| C12 | C12 | 220µF 25V | `Device:C_Polarized` | `Capacitor_THT:CP_Radial_D6.3mm_P2.50mm` |
| C15 | — | 10µF | `Device:C_Polarized` | `Capacitor_THT:CP_Radial_D5.0mm_P2.00mm` |
| C16 | — | 0.1µF | `Device:C` | `C_Disc_D5.1mm_W3.2mm_P5.00mm` |
| U4 | U4 | MCP1826S-3302E/AB | `Regulator_Linear:MCP1826S` | `Package_TO_SOT_THT:TO-220-3_Vertical` |
| C8 | C8 | 10µF | `Device:C_Polarized` | `Capacitor_THT:CP_Radial_D5.0mm_P2.00mm` |
| C17 | — | 0.1µF | `Device:C` | `C_Disc_D5.1mm_W3.2mm_P5.00mm` |
| C6 | C6 | 0.1µF | `Device:C` | `Capacitor_THT:C_Disc_D5.1mm_W3.2mm_P5.00mm` |
| C7 | C7 | 0.1µF | `Device:C` | same — U2's decoupling, **footprint only, DNP** |

```
J5 pin 1 ── F1 ── +24V_BRD
J5 pin 2 ── GND
D6 cathode ── +24V_BRD,  D6 anode ── GND     [SHUNT clamp, reverse-biased]

C10, C11 across +24V_BRD ── GND    (at U3's pins)
U3: Vin=+24V_BRD, GND=GND, Vout=+5V
C12 across +5V ── GND              (at U3's output pin)
C15, C16 across +5V ── GND         (at U4's INPUT pin, not at U3)
U4: Vin=+5V, GND=GND, Vout=+3V3
C8, C17 across +3V3 ── GND         (at U4's output pin)
C6 across +3V3 ── GND              (at U1 pin 9, VDD)
C7 across +3V3 ── GND              (at U2 pin 9 — FOOTPRINT ONLY)
```

D6 is a shunt clamp: cathode to the rail, anode to ground, carrying nothing until the
supply is connected backwards, then conducting hard and blowing F1. **F1 must be between
J5 and the clamp.** Downstream, it protects nothing. The symbol invites you to draw a
series diode; don't.

Every capacitor above belongs at the pin of the part it serves. C15/C16 being separate
from C12 is what station §10.6 is about — same rail, different place — and the
schematic cannot express the distinction, so it has to survive as a layout note.

**There is no C13 and no audio-band bulk on the 24V rail, and none is wanted.** Station
Station §10.7 withdrew it: R3 sits in the tip-ring loop behind the relay contacts and is never
connected to +24V_BRD, so this board's 24V rail carries nothing but the converters. The
trunk board's C13 does have a real job, which is why the absence here looks like an
omission. Put a text note on the sheet saying it was considered and removed, or it comes
back.

C15, C16 and C17 have no designators in the document — they are station §10.6's LDO
capacitors. C16 and C17 are already inside the BOM's count of 12 per board and C15 inside
its 10, so the parts are bought; only the numbering was missing. See §7.

---

### 5.2 I²C, /RESET and the expanders

| Ref | Doc name | Value | Symbol | Footprint |
|---|---|---|---|---|
| J3A, J3B | J3A, J3B | Amphenol 87180-066LF, 6P6C | `Connector_Generic:Conn_01x06` | `Connector_RJ:RJ12_Amphenol_54601-x06_Horizontal` — candidate |
| TVS2 | TVS2 | SP721APP | `switchboard:SP721` | `Package_DIP:DIP-8_W7.62mm` |
| C18 | C18 | 0.1µF | `Device:C` | `C_Disc_D5.1mm_W3.2mm_P5.00mm` — new at Rev 3.26 |
| R18 | — | 10k | `Device:R` | DIN0207 — /RESET pull-up, **do fit** |
| R9, R10 | R9, R10 | 2.2k | `Device:R` | DIN0207 — **DO NOT FIT** |
| U1 | U1 | MCP23017-E/SP, 0x20–0x22 by SW1 | `Interface_Expansion:MCP23017_SP` | `Package_DIP:DIP-28_W7.62mm` |
| U2 | U2 | MCP23017-E/SP, 0x24–0x26 | same | same — **footprint only, DNP** |

J3A and J3B are the same node — two jacks wired in parallel, in and out interchangeable.

```
J3A/J3B pin 1 ── /RESET ── TVS2 IN ── U1 pin 18, U2 pin 18
J3A/J3B pin 2 ── SCL    ── TVS2 IN ── U1 pin 12, U2 pin 12
J3A/J3B pin 4 ── SDA    ── TVS2 IN ── U1 pin 13, U2 pin 13
J3A/J3B pins 3, 5, 6 ── GND

TVS2 pin 8 ── +3V3,  TVS2 pin 4 ── GND
C18 from TVS2 pin 8 to pin 4, at the device
R18 (10k) from /RESET ── +3V3            ← fit on this board
R9, R10 footprints SDA/SCL → +3V3        ← DO NOT FIT

U1 pin 9  (VDD)  ── +3V3, C6 at the pin
U1 pin 10 (VSS)  ── GND
U1 pin 19 (INTB), pin 20 (INTA) ── NO CONNECT flags
```

**SP721 pinout verified against the datasheet** — Littelfuse SP721 series, revision GD
07/10/24: IN on 1–3 and 5–7, V− on 4, V+ on 8. Any three of the six inputs serve for SDA,
SCL and /RESET; the generator board uses 1, 2 and 3 in that order.

C18 is new at Rev 3.26 and belongs at TVS2's own pins, not with the rail decoupling. The
SP721 conducts the transient from the IN pin into V+ rather than shunting it to ground, so
V+ must source that current locally. Placing TVS2 at the jack — which is right — puts C6
and C8 the length of the board away.

Three of TVS2's six inputs are used and three are spare. Place it **at J3A/J3B**, not near
the expanders — it is protecting the whole bus from something arriving at the jack, so it
has to be the first thing that energy meets (station §12).

The /RESET pull-up goes on every expander board, which is deliberately the opposite of the
DO-NOT-FIT rule for the bus pull-ups. Three 10kΩ in parallel is 3.3kΩ on a statically
driven CMOS line and nothing notices; what it buys is that a board unplugged from the
chain still holds its own expander out of reset (station §9.4).

The no-connect flags on INTA/INTB matter: this system polls (station §9.6), and ERC should
be told the pins are deliberately unused rather than left to report them every time.

Positions 3, 5 and 6 are all board ground but they are **not interchangeable at the
cable**. The interleave is what puts a ground conductor between SCL and SDA and buys about
12dB against coupled glitches (station §9.4). The schematic cannot express that; the note
belongs on the sheet beside the connector, and the pin numbering has to be exactly as
above.

---

### 5.3 Address strap

| Ref | Doc name | Value | Symbol | Footprint |
|---|---|---|---|---|
| SW1 | SW1 | CTS 206-3ST | `Switch:SW_DIP_x03` | `Button_Switch_THT:SW_DIP_SPSTx03_Slide_9.78x9.8mm_W7.62mm_P2.54mm` |
| R19–R21 | — | 10k | `Device:R` | DIN0207 |

Board 1 is 0x20 (A2:A0 = 000), board 2 is 0x21, board 3 is 0x22, set by SW1 rather than
links so the three boards stay interchangeable (station §9.2).

SW1 cannot do this alone. It is three SPST switches, and the MCP23017's address pins have
no internal pull-up or pull-down — they have to be biased externally, or they are
undefined in one of the switch's two positions. Station Rev 3.25 adds the bias:

```
U1 pin 15 (A0) ── R19 (10k) ── +3V3,   SW1 position 1 ── GND
U1 pin 16 (A1) ── R20 (10k) ── +3V3,   SW1 position 2 ── GND
U1 pin 17 (A2) ── R21 (10k) ── +3V3,   SW1 position 3 ── GND
```

Pull-up with the switch closing to ground, so a **closed switch reads 0**. Board 1 is all
three closed, board 2 has A0 open, board 3 has A1 open, and A2 is closed on every station
board.

All three open reads 0x27 — not a station address, and the one trunk §10.2 reserves for
the trunk board's optional U2, which is not fitted. A board that comes back from the bench
with its switch untouched therefore drops off the master's startup scan as a missing
device rather than colliding silently with a working board. That is the argument for this
polarity over the other one.

Silkscreen 0x20 / 0x21 / 0x22 against the positions **and the sense**. ON means 0 here,
which is the opposite of what a switch marked ON suggests, and this is the only setting on
the board that invites being changed by someone who does not know why it is set the way it
is.

---

### 5.4 Expander to station sheets

No parts. Sixteen labelled stubs.

```
U1 GPA0..GPA7 (pins 21-28) ── RING_DET_1..8  ── STN1..8 RING_DET pin
U1 GPB0..GPB7 (pins 1-8)   ── OFFHOOK_1..8   ── STN1..8 OFFHOOK pin
```

Plain local labels — everything is on one sheet, and sixteen labelled stubs read better
than sixteen wires crossing the page. Put the label on the wire off the U1 pin and the
same name on the wire into the sheet symbol's pin.

U2's Port A is STATUS_LED_1..8 if it is ever stuffed. Leave its GPIO pins unrouted; the
footprint, straps and C7 are what have to exist now.

---

### 5.5 Station lines — J7A, J7B

| Ref | Doc name | Value | Symbol | Footprint |
|---|---|---|---|---|
| J7A, J7B | J7A, J7B | Amphenol RJHSE5380, RJ45 shielded | `Connector_Generic_Shielded:Conn_01x08_Shielded` | `Connector_RJ:RJ45_Amphenol_RJHSE5380` |

Four stations per jack, one twisted pair each, T568B. Identical to the trunk board's
arrangement.

| RJ45 pin | Pair colour | J7A | J7B |
|---|---|---|---|
| 1 | white/orange | Station 1 TIP | Station 5 TIP |
| 2 | orange | Station 1 RING | Station 5 RING |
| 3 | white/green | Station 2 TIP | Station 6 TIP |
| 6 | green | Station 2 RING | Station 6 RING |
| 5 | white/blue | Station 3 TIP | Station 7 TIP |
| 4 | blue | Station 3 RING | Station 7 RING |
| 7 | white/brown | Station 4 TIP | Station 8 TIP |
| 8 | brown | Station 4 RING | Station 8 RING |

Pins 3/6 and 5/4 — the T568B pair order is not sequential. Striped conductor to tip.

On board 3, J7B's strip-7 pair (pins 5 and 4) is the operator's talking path rather than a
station line (station §7.9.4), and its strip-8 pair (pins 7 and 8) is unused: the monitor
strip has no line side. Electrically the tap pair is the same landing; it is worth a note on
the sheet only because somebody tracing either pair will otherwise look for a telephone that
does not exist.

Terminate the jack shields to chassis at the board end only.

---

### 5.6 Audio — J1, J2 (TASCAM analog)

| Ref | Doc name | Value | Symbol | Footprint |
|---|---|---|---|---|
| J1, J2 | J1, J2 | NorComp 182-025-213R561, DB25 female | `Connector:DB25_Female` | `Connector_Dsub:DSUB-25_..._EdgePinOffset*` — see §6 |
| JP1 | JP1 | 0R link | `Device:R` | DIN0207 — D-Sub ground to board GND, **DNP** |

J1 = 8 board outputs to A32 inputs. J2 = 8 A32 outputs to board inputs. Same pin pattern
on both. Board channel n = station n on that board; A32 channel = (board − 1) × 8 + n.

| Board ch | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| Hot (+) | 24 | 10 | 21 | 7 | 18 | 4 | 15 | 1 |
| Cold (−) | 12 | 23 | 9 | 20 | 6 | 17 | 3 | 14 |
| Ground | 25 | 11 | 22 | 8 | 19 | 5 | 16 | 2 |

Pin 13 not connected.

**The sixteen ground pins float at this board.** Common them into a single node — one per
connector or one for both — and take a single 0Ω link footprint, **JP1**, from there to
board GND, **unstuffed**. T2 isolates and nothing in the secondary needs board ground;
grounding both ends closes a hum loop through the PSU, mains earth and the A32 chassis.
The link exists so the decision can be revisited on the bench if ring events produce
clicks through T2's interwinding capacitance (station §7.6). The middle position — 100Ω in
parallel with 10nF — takes the same footprint.

Silkscreen what fitting JP1 means, or someone populates it on the reasonable assumption
that a missing part is an oversight.

Both connectors are **female**. Earlier revisions of both documents said male. The loom is
a stock male-to-male analog snake.

---

## 6. Before you start drawing

Most of these are shared with the trunk board and are cheaper to settle once.

- **T2 is settled and needs nothing before layout.** Symbol pins 1/3/4/6 match the pads, and the
  dots are on **1 and 4** — pin 1 the primary start, pin 4 the secondary start. Wire all 24 the
  same way and mark it on the silkscreen: a single reversed transformer inverts one circuit's
  audio and nothing else, which survives a long time before anyone notices. The pin numbering is
  why the part is custom rather than stock — KiCad matches pin number to pad number with no
  remapping, so a 1-2-3-4 symbol would have put pin 3 on pad 3, the far end of the primary.
- **Q2's pinout against the physical part.** `Transistor_BJT:Q_NPN_EBC` is confirmed to exist,
  but TO-92 parts sold as 2N2222A come in EBC, CBE and ECB by manufacturer. A diode test
  settles it in five minutes and there are 24 on the station boards. This is the one class of
  error on this board that costs a respin.
- **The relay footprint is the Omron G6A pattern deliberately** — the CIT part is not in the
  KiCad libraries. Verify the J104D2C5VDC.15S pin pattern and body against it. Eight per
  board, so the error multiplies.
- **The D-Sub backset is 8.08mm and matches no stock KiCad variant** (4.94, 7.70, 9.40,
  14.56). Take the DigiKey EDA model for 182-125FE-ND rather than the nearest pattern. Two of
  these sit on the same edge as two RJ45 jacks.
- **The 6P6C footprint is a candidate, not a match** — `RJ12_Amphenol_54601-x06_Horizontal`
  against an 87180-066LF, pending the part arriving. There are **two per station board**, so a
  wrong footprint costs twice here rather than once.
- **R3 runs about 1.6W continuously** in a 2W part, eight per board. That is a placement
  constraint, not a library one: stand them off the board and keep C9 and the electrolytics
  away from them.
- **The HCPL3700M isolation slot** (station §12 asks for a continuous routed slot under each body)
  is a board feature, not a footprint feature. Decide now whether it lives in the footprint or
  as edge-cuts on the board, because eight of them per board is not something to add by hand
  afterwards.
- **Confirm SW1's body length** against the 206-3ST drawing, and settle §5.3 first.

---

## 7. What this guide changed elsewhere

Everything on the original version of this list has been carried into the documents. Recorded
here so the trail from schematic back to document stays visible.

**Done in `station_circuit.md` at Rev 3.25:**
- §9.2 — SW1's address bias. The only item on the list that was a design fault rather than
  bookkeeping: three SPST switches and no resistors left A0–A2 undefined. R19–R21 added.
- §3.6, §11 — R17, the OC1 V_CC series link. Asked for since Rev 3.0 with no designator.
- §9.4, §11 — R18, the /RESET pull-up. Required since Rev 3.11 with no designator.
- §10.6, §11 — C15, C16, C17, the LDO capacitors. Already inside the purchased quantities.
- §7.3, §12 — the T2 screen. Corrected; the part has no such terminal.
- §11 — R1a/R1b annotated as R14/R15, since the document names are not legal references.
- §7.9.1, §12 — why the tap has to be replicated in the schematic as well as the PCB.

**Done in `telephone_bom.xlsx`:**
- 10kΩ 0.25W recounted, 34 → 42: three uncounted /RESET pull-ups, six new address-bias
  resistors, and one fewer on the generator now the tone injector's RC pole is gone.
- A line for the OC1 V_CC link at qty 0, matching the L1 row's treatment of a footprint-only part.

**Closed since the first version of this guide:**
- T2's symbol, footprint, pin numbering and dot convention are all settled. See §6.
- BOM row 23's generator column held one TY-311P left over from the operator tone injector, which
  was to have been built on the ring generator board. That went at station Rev 3.24 / generator
  Rev 27. Corrected to zero; the total is 24, which is 8 trunk and 16 station.
- BOM row 23's closing sentence still says the three SP-70s serve T3. Row 73 records T3 as
  deleted. Row 73 is right.
