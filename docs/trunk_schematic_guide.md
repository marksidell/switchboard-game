# Trunk Board — KiCad Schematic Drawing Guide

Derived from trunk circuit Rev 5.25 and the KiCad library plan; C19, the /RESET filter, added at trunk Rev 5.40; R_LOOP and R_DET values from trunk Rev 5.41. **Follows trunk Rev 5.42: every reference below is the designator as annotated on the rev 2 board** — strip parts as Rxnn, x = trunk number + 1, root parts from 101 — with the former document name alongside in each table. §6 is a record of an earlier check and keeps the names it was written in. Checked part by part
against Rev 5.25 §13 — the earlier version of this guide was written against Rev 5.16 and
its header was never moved, so the change entries from 5.17 to 5.25 had never been read
back into it. Result of that check is at the end of §5.
Structure: one root sheet carrying everything common, plus **8 instances of a single
hierarchical sheet** `trunk.kicad_sch`.

---

## 1. Sheet structure

```
trunks.kicad_sch          (root)
 ├── trunk1  → trunk.kicad_sch
 ├── trunk2  → trunk.kicad_sch
 ├── ...
 └── trunk8  → trunk.kicad_sch
```

Draw the hierarchical sheet **once**. In KiCad 9, add the other seven by placing a new
sheet and selecting the same file — KiCad creates additional instances rather than
copies, so an edit to one propagates to all eight.

### Annotation and designators

Use **Tools → Annotate → Sheet by sheet**, with "First free after sheet number × 100".
As annotated on the rev 2 board, the root sheet is 1xx and trunk *n* is (*n*+1)xx: trunk 1
gets R201, R202…, trunk 8 gets R901…. This guide writes strip parts as **Rxnn** — Rx06
is R206 on trunk 1 through R906 on trunk 8 — and root parts by their own number.

Until trunk Rev 5.41 the documents named parts functionally (`R_set`, `R_LOOP`, `R_DET`,
`R_pd`, `R_RST`, `C_C`) or with numbers of their own (`R1`, `R2`, `R4`–`R8`) that
collided with KiCad's, and this guide assigned interim numbers (R11–R15, C1) that
annotation then replaced. Trunk Rev 5.42 retires all of that: the trunk document and this
guide now use the annotated designators, and the tables below keep each part's former name
in a column of its own. A `Function` field on each symbol carrying the role is still worth
having for anyone reading the schematic itself.

### What eight instances of one sheet actually do

Each instance gets its own set of reference designators, stored as per-instance data in
the schematic file. Eight sheets give eight distinct sets of parts in the netlist and
eight sets of footprints in the PCB.

**Values, footprints and custom fields are shared**, because they belong to the symbol
rather than the instance. Edit 22R to 24R in one trunk and all eight change. That is what
you want here — the eight trunks are identical by design — but it also means trunk 3
cannot differ from the others without being given its own sheet file.

**Annotation fills sequentially** in the order KiCad walks the sheet, so the suffix a part gets is whatever annotation gave it. On the rev 2 board that is what this guide now records: R204 on the PCB is Rx04 on trunk 1, the base bias resistor formerly called `R_bias`.

Build the root sheet with **two** instances first, annotate, and look at what you get.
Ten minutes, and it tells you how your KiCad 9 build behaves rather than how this guide
says it should.

---

## 2. Hierarchical sheet pins

Eight pins per sheet. Power and the ring bus are **not** in this list — both use global
symbols.

| Pin name | Type | Goes to (root) |
|---|---|---|
| `TIP` | passive | J7A101/J7B101, one pair per trunk |
| `RING` | passive | J7A101/J7B101, same pair |
| `A32_IN_H` | output | J104, hot of channel 24+n |
| `A32_IN_C` | output | J104, cold of channel 24+n |
| `A32_OUT_H` | input | J105, hot of channel 24+n |
| `A32_OUT_C` | input | J105, cold of channel 24+n |
| `SEIZE` | output | U101 Port A bit n |
| `RING_EN` | input | U101 Port B bit n |

### Pin names versus net names

The eight pin names above are **identical on all eight sheet symbols**. A sheet pin is not
independently named — it is the parent-side face of the hierarchical label inside the
child sheet, and KiCad matches them by name. Rename one and it stops connecting.

The numbering lives on the **nets**, not the pins. Each sheet pin has a wire attached, and
that wire carries a local label:

```
trunk1  TIP pin ──── TIP_1 ────► J7A101 pin 1
trunk2  TIP pin ──── TIP_2 ────► J7A101 pin 3
```

Use `<signal>_<n>` throughout, matching the `SEIZE_1`…`SEIZE_8` already coming off U101:

| Sheet pin (all 8 sheets) | Root-sheet nets |
|---|---|
| `TIP` | `TIP_1` … `TIP_8` |
| `RING` | `RING_1` … `RING_8` |
| `A32_IN_H` | `A32_IN_H_1` … `_8` |
| `A32_IN_C` | `A32_IN_C_1` … `_8` |
| `A32_OUT_H` | `A32_OUT_H_1` … `_8` |
| `A32_OUT_C` | `A32_OUT_C_1` … `_8` |
| `SEIZE` | `SEIZE_1` … `SEIZE_8` |
| `RING_EN` | `RING_EN_1` … `RING_EN_8` |

Verbose, but every net name says both what it is and which trunk it belongs to, and they
sort sensibly in the netlist and in the PCB's net list panel.

**Power nets** — place `PWR_FLAG`-backed global symbols on the root sheet only:
`+24V_BRD`, `+5V`, `+3V3`, `GND`. Inside the trunk sheet just drop the matching power
symbols; they connect implicitly.

**Ring bus** — `RING_HI` and `RING_LO` are **global labels**, not hierarchical pins. All
eight sheets share them, so this keeps sixteen wires off the root sheet. Place the global
label at Kx01 pole 1 NO and pole 2 NO inside the trunk sheet, and once each at F101 and J102
on the root sheet.

Because the ring bus is the hazardous net and a global label makes it less visible than a
drawn wire, compensate on the sheet rather than in the netlist: give both labels a
distinct colour or a hatched box, and put a text note at F101 on the root sheet naming the
eight destinations. The isolation rules in trunk §14 apply to the copper regardless of how the
schematic expresses the connection.

---

## 3. The trunk strip — five blocks

Each block carries its parts and then its nets. Draw a block start to finish before moving
on; you should not need a second window open on this document.

Every parts table carries the part's **former name** beside its designator, so text written
before trunk Rev 5.42 can still be followed.

Strip designators are written Rxnn; on the board x is the trunk number + 1. `NODE_A` and `NODE_B`
are local labels: the two nets that are line-side when the relay is released and
board-side when it is thrown (trunk §14).

---

### 3.1 Jack and relay

| Ref | Former name | Value | Symbol | Footprint |
|---|---|---|---|---|
| Dx01 | TVS1 | P6KE150CA | `Device:D_TVS` | `Diode_THT:D_DO-15_P10.16mm_Horizontal` |
| Kx01 | RLY1 | J104D2C5VDC.15S | `Relay:Relay_DPDT` | `Relay_THT:Relay_DPDT_Omron_G6A` |

```
TIP   ── Kx01 pole 1 common
RING  ── Kx01 pole 2 common
Dx01 across TIP ── RING          (the only part not behind a relay contact)

Kx01 pole 1 NC ── NODE_A
Kx01 pole 1 NO ── RING_HI      [global label]
Kx01 pole 2 NC ── NODE_B
Kx01 pole 2 NO ── RING_LO      [global label]
```

**P6KE150CA, not the station board's P6KE120CA.** The two boards use deliberately
different TVS voltages, and each is sized for its own line. Set the value field per board
and never standardise them.

The relay switches between the loop feed and the ring bus — there is no
released-and-isolated position, which is the opposite sense from the station relay. Do
not copy the station sheet's contact wiring.

---

### 3.2 Constant-current loop feed

| Ref | Former name | Value | Symbol | Footprint |
|---|---|---|---|---|
| Qx03 | Q4 | MJE350 | `Transistor_BJT:Q_PNP_ECB` — **verify, likely ECB not EBC** | `Package_TO_SOT_THT:TO-126-3_Vertical` |
| Qx01 | Q3 | 2N3906 | `Transistor_BJT:Q_PNP_EBC` | `Package_TO_SOT_THT:TO-92_Inline` |
| Rx02 | R_set | 22R 0.5W 1% | `Device:R` | `R_Axial_DIN0309_L9.0mm_D3.2mm` |
| Rx04 | R_bias | 10k | `Device:R` | `R_Axial_DIN0207_L6.3mm_D2.5mm` |
| Rx05 | R1 | 100R 1W | `Device:R` | `R_Axial_DIN0414_L11.9mm_D4.5mm` |
| Cx02 | C_C | 1nF C0G | `Device:C` | `C_Disc_D5.0mm_W2.5mm_P5.00mm` |
| Dx03 | D1 | 1N4007 | `Diode:1N4007` | `D_DO-41_SOD81_P10.16mm_Horizontal` |

```
+24V_BRD ─┬──────────────────── Qx01 emitter
         └── Rx02 ─┬─────────── Qx03 emitter
                   └─────────── Qx01 base
Qx01 collector ────────────────── Qx03 base
Qx03 base ── Rx04 ──────────────── GND
Qx03 base ── Cx02 ───────────────── Qx03 emitter
Qx03 collector ── Rx05 ── Dx03(A→K) ── NODE_A
```

Dx03 anode to Rx05, cathode to `NODE_A`.

**No L1, and no `V_FEED`.** Earlier versions of this guide placed an unstuffed 0Ω link
between `+24V_BRD` and a strip-local feed node `V_FEED`, holding a place for the 47mH
inductor deleted at trunk Rev 4.x. Trunk Rev 5.29 deletes the footprint: the site could
not take the part and the part was already shown to do nothing (trunk §12.4). Qx01's emitter
and Rx02 connect straight to the `+24V_BRD` power symbol. If a `V_FEED` label exists on the
strip sheet from an earlier pass, remove it; it would be a second net with nothing between
it and the rail.

Cx02 is the compensation capacitor, formerly `C_C`.

Cx01, the 100µF local bulk on +24V_BRD (formerly C14), was deleted from the design at trunk Rev 5.23 but is **fitted** on every strip of the rev 2 board (trunk §12.4, Rev 5.42). The board's other 24V bulk is C102 at the input.

Fit a footprint for Cx02 that accepts 100pF–10nF. Trunk §3.2.2 leaves the value open pending a
scope across Rx06 at seizure.

---

### 3.3 Loop return and seizure detect

| Ref | Former name | Value | Symbol | Footprint |
|---|---|---|---|---|
| Rx06 | R_LOOP | 220R 2W (trunk Rev 5.41; was 150R) | `Device:R` | `R_Axial_DIN0516_L15.5mm_D5.0mm` |
| Rx07 | R_DET | 150R (trunk Rev 5.41; was 470R) | `Device:R` | `R_Axial_DIN0207` |
| Ux01 | OC1 | HCPL3700M | `switchboard:HCPL-3700` | `Package_DIP:DIP-8_W7.62mm` |
| Rx12 | R2 | 4.7k | `Device:R` | `R_Axial_DIN0207` |
| Cx05 | C5 | 0.1µF | `Device:C` | `C_Disc_D5.1mm_W3.2mm_P5.00mm` |

```
NODE_B ──┬── Rx06 ── GND
         └── Rx07 ── Ux01 pin 2   (DC+)
Ux01 pin 3 ── GND                  (DC−)
Ux01 pins 1, 4 ── NO CONNECT       ← place NC flags; this selects the DC input pair
Ux01 pin 5 ── GND
Ux01 pin 8 ── +3V3,  Cx05 from pin 8 to pin 5 at the device
Ux01 pin 6 ── Rx12 ── +3V3
Ux01 pin 6 ── SEIZE
```

**Pins 1 and 4 must be explicitly open.** The AC and DC input pairs are alternative
entries to the same buffer and the datasheet specifies each with the other pair floating.
This is the opposite wiring from the station board, which drives AC on pins 1/4 with 2 and
3 open — put a text note on the sheet, because the symbol types all four as passive and
ERC will not object either way.

Each Rx06 returns to the In1 ground plane by its own via and none of the eight share a
trace (trunk §12.4, Rev 5.28 — previously a star to one point, superseded by the plane).
That is a layout decision, but it is decided here.

---

### 3.4 Relay driver

| Ref | Former name | Value | Symbol | Footprint |
|---|---|---|---|---|
| Qx02 | Q2 | 2N2222A | `Transistor_BJT:Q_NPN_EBC` | `Package_TO_SOT_THT:TO-92_Inline` |
| Rx01 | R4 | 1k | `Device:R` | `R_Axial_DIN0207` |
| Rx03 | R_pd | 10k | `Device:R` | `R_Axial_DIN0207` |
| Dx02 | D5 | 1N4148 | `Diode:1N4148` | `D_DO-35_SOD27_P7.62mm_Horizontal` |
| Cx03 | C9 | 10µF 50V | `Device:C_Polarized` | `CP_Radial_D5.0mm_P2.00mm` |

```
RING_EN ── Rx01 ── Qx02 base
Qx02 base ── Rx03 ── GND
Qx02 emitter ── GND
Qx02 collector ── Kx01 coil (−)
Kx01 coil (+) ── +5V
Dx02 anode ── Qx02 collector,  Dx02 cathode ── +5V
Cx03 across +5V ── GND             (local reservoir at the coil)
```

Rx03 is not optional — Port B floats between reset and configuration (trunk §7.3).

---

### 3.5 Audio

| Ref | Former name | Value | Symbol | Footprint |
|---|---|---|---|---|
| Cx04 | C2 | 0.47µF 250V film | `Device:C` | `C_Rect_L18.0mm_*_P15.00mm` |
| Tx01 | T2 | Triad TY-311P | `switchboard:XFMR_TY-311P` | `switchboard:XFMR_TY-311P` — pads 1/3/4/6 |
| Rx08, Rx09 | R5, R6 | 1k matched | `Device:R` | `R_Axial_DIN0207` |
| Rx10, Rx11 | R7, R8 | 1k matched | `Device:R` | `R_Axial_DIN0207` |

```
NODE_A ── Cx04 ── Tx01 primary (+)
NODE_B ──────── Tx01 primary (−)

Tx01 secondary hot  ── Rx08 ── A32_IN_H
Tx01 secondary cold ── Rx09 ── A32_IN_C
A32_OUT_H ── Rx10 ── Tx01 secondary hot
A32_OUT_C ── Rx11 ── Tx01 secondary cold
```

Rx08/Rx09 and Rx10/Rx11 join at the secondary — receive and transmit share the winding.

Tx01's pins are numbered **1 and 3 for the primary, 4 and 6 for the secondary**; 2 and 5 are
the absent centre taps of the TY body. The dots are on **1 and 4**. See §5.

**There is no screen.** The TY-311P is a four-pin part and the symbol drawn for it has four
pins, so the screen connection trunk §8.2 once specified was never a terminal that existed.
Removed at Rev 5.25; the station document corrected the same line. Draw nothing and leave no
fifth pad.

---

## 4. Root sheet — six blocks

Same arrangement: parts, then nets, block by block.

---

### 4.1 Power entry

| Ref | Former name | Value | Symbol | Footprint |
|---|---|---|---|---|
| J103 | J5 | OSTTE020104, 3.50mm 125V | `Connector:Screw_Terminal_01x02` | `TerminalBlock_4Ucon:TerminalBlock_4Ucon_1x02_P3.50mm_Horizontal` |
| F102 | F1 | 500mA slow-blow, 0218.500MXP | `Device:Fuse` | carried by its holder, below |
| (F102) | FH1 | Littelfuse 64900001039, 649 series | — | `Fuse:Fuseholder_Clip-5x20mm_*` — measure the 649 pitch |
| D101 | D6 | 1N5822 | `Diode:1N5822` | `D_DO-201AD_P12.70mm_Horizontal` — **shunt, not series** |
| C102 | C13 | 1000µF 50V | `Device:C_Polarized` | `CP_Radial_D16.0mm_P7.50mm` |
| C103 | C10 | 47µF 50V | `Device:C_Polarized` | `CP_Radial_D6.3mm_P2.50mm` |
| C104 | C11 | 0.1µF | `Device:C` | `C_Disc_D5.1mm` |
| U102 | U3 | TSR 2-2450 | `Converter_DCDC:TSR2-2450` | `Converter_DCDC:...TSR2-2` |
| C105 | C12 | 220µF 25V | `Device:C_Polarized` | `CP_Radial_D6.3mm_P2.50mm` |
| C106 | C15 | 10µF | `Device:C_Polarized` | `CP_Radial_D5.0mm_P2.00mm` |
| C107 | C16 | 0.1µF | `Device:C` | `C_Disc_D5.1mm` |
| U103 | U4 | MCP1826S-3302E/AB | `Regulator_Linear:MCP1826S` | `Package_TO_SOT_THT:TO-220-3_Vertical` |
| C108 | C8 | 10µF | `Device:C_Polarized` | `CP_Radial_D5.0mm_P2.00mm` |
| C109 | C17 | 0.1µF | `Device:C` | `C_Disc_D5.1mm` |
| C101 | C6 | 0.1µF | `Device:C` | `C_Disc_D5.1mm` — U101 VDD decoupling |

```
J103 pin 1 ── F102 ── +24V_BRD
J103 pin 2 ── GND
D101 cathode ── +24V_BRD,  D101 anode ── GND    [SHUNT clamp, reverse-biased]
C102 across +24V_BRD ── GND       (audio-band bulk, at the input terminal)
C103, C104 across +24V_BRD ── GND  (at U102's pins)
U102: Vin=+24V_BRD, GND=GND, Vout=+5V
C105 across +5V ── GND            (at U102's output pin)
C106, C107 across +5V ── GND       (at U103's INPUT pin, not at U102)
U103: Vin=+5V, GND=GND, Vout=+3V3
C108, C109 across +3V3 ── GND       (at U103's output pin)
C101 across +3V3 ── GND            (at U101 pin 9, VDD)
```

D101 is a shunt clamp, not a series diode. Cathode to the rail, anode to ground, carrying
nothing until the supply is connected backwards — then it conducts and blows F102. Draw F102
between J103 and the clamp; if the fuse ends up downstream the protection does nothing.
Watch the orientation in the schematic: it is the opposite of the series arrangement the
symbol invites you to draw.

Every capacitor above belongs **at the pin of the part it serves**, not gathered together
where the schematic looks tidy. That is why C106/C107 are separate from
C105 — same rail, different place. The schematic cannot express the distinction, so it has
to survive as a layout note.

---

### 4.2 Ring bus

| Ref | Former name | Value | Symbol | Footprint |
|---|---|---|---|---|
| J102 | J6 | OSTTC020162, 5.00mm 300V | `Connector:Screw_Terminal_01x02` | **5.00mm**, not J103's 3.50mm — try the same 4Ucon series |
| F101 | F2 | 250mA fast 250V, 0217.250MXP | `Device:Fuse` | carried by its holder, below |
| (F101) | FH2 | Littelfuse 64900001039, 649 series | — | `Fuse:Fuseholder_Clip-5x20mm_*` — same holder as F102's |

```
J102 pin 1 ── F101 ── RING_HI   [global label → all 8 sheets]
J102 pin 2 ────────  RING_LO  [global label → all 8 sheets]
```

J102 is **not** the same terminal as J103. J103 is the OSTTE020104 (3.50mm, 125V), fine at 24V;
J102 is the OSTTC020162 (5.00mm, 300V) because 100V RMS ring is 141V peak, above the
OSTTE's rating entirely. Two different footprints — 3.50mm and 5.00mm pad spacing — and
the parts are different colours, black and blue, which distinguishes them on the finished
board.

`RING_HI` and `RING_LO` are **global labels**, not hierarchical pins. All eight strips
share them, which keeps sixteen wires off the root sheet. Place the global label at Kx01
pole 1 NO and pole 2 NO inside the strip (§3.1), and once each at F101 and J102 here.

Because the ring bus is the hazardous net and a global label makes it less visible than a
drawn wire, compensate on the sheet rather than in the netlist: give both labels a
distinct colour or a hatched box, and put a text note at F101 naming the eight destinations.

F101's 250mA is not the comfortable number it looks. Trunk §7.6's estimate of 20mA per
trunk puts eight ringing at once at about 178mA — 71% of rating, sitting on the 75%
continuous derating a fast-acting fuse is normally held to, with only the ring cadence
duty cycle left as margin. The value stands pending measurement and 500mA is the fallback
(trunk Rev 5.24, §12.5). Footprint and holder are the same either way, so this does not
block layout.

Keep this whole net in its own zone with 3mm creepage, physically separate from the
low-voltage connectors. The isolation rules in trunk §14 apply to the copper regardless of how
the schematic expresses the connection.

---

### 4.3 I²C and expanders

| Ref | Former name | Value | Symbol | Footprint |
|---|---|---|---|---|
| U101 | U1 | MCP23017-E/SP, 0x23 | `Interface_Expansion:MCP23017_SP` | `Package_DIP:DIP-28_W7.62mm` |
| TVS101 | TVS2 | SP721APP | `switchboard:SP721` | `Package_DIP:DIP-8_W7.62mm` |
| C18 | C18 | 0.1µF | `Device:C` | `C_Disc_D5.1mm` — new at Rev 5.27; **not on the rev 2 board** (TODO.md) |
| J101 | J3 | 6P6C | `Connector_Generic:Conn_01x06` | `Connector_RJ:RJ12_*` |
| R101 | R_RST | 10k | `Device:R` | `R_Axial_DIN0207` — /RESET pull-up, **do fit** |
| C110 | C19 | 0.1µF | `Device:C` | `C_Disc_D5.1mm` — /RESET filter, new at Rev 5.40 |

```
J101 pin 2 ── SCL ── TVS101 IN ── U101 pin 12 (SCL)
J101 pin 4 ── SDA ── TVS101 IN ── U101 pin 13 (SDA)
J101 pin 1 ── /RESET ── TVS101 IN ── U101 pin 18
J101 pins 3, 5, 6 ── GND
TVS101 pin 8 ── +3V3,  TVS101 pin 4 ── GND
C18 from TVS101 pin 8 to pin 4, at the device
R101 (10k) from /RESET ── +3V3            ← fit on this board
C110 (C19, 100nF) U101 pin 18 ── GND, at the pin

U101 pin 9  (VDD)   ── +3V3, C101 at the pin
U101 pin 10 (VSS)   ── GND
U101 pin 12 (SCL)   ── SCL         U101 pin 13 (SDA) ── SDA
U101 pin 18 (RESET) ── /RESET
U101 pin 15 (A0) ── +3V3    U101 pin 16 (A1) ── +3V3
U101 pin 17 (A2) ── GND                                  → 0x23, hardwired
U101 pin 19 (INTB), pin 20 (INTA) ── NO CONNECT flags
```

**All six J101 positions are wired and the cords must be six-conductor.** /RESET and its
return sit on positions 1 and 6, which is what trunk Rev 5.25 corrected the §13 entry to
say after seventeen revisions of it describing positions 1 and 6 as unused. A 6P4C cord
seats happily and leaves a working bus with no hardware reset — a degraded mode with no
symptom until you need the reset. Silkscreen it.

**SP721 pinout verified against the datasheet** — Littelfuse SP721 series, revision GD
07/10/24: IN on 1–3 and 5–7, V− on 4, V+ on 8. Any three of the six inputs will do for
SDA, SCL and /RESET; the generator board uses 1, 2 and 3 in that order.

C18 is new at Rev 5.27 and belongs at TVS101's own pins. The SP721 conducts the transient
from the IN pin into V+ rather than shunting it to ground, so V+ must source that current
locally. TVS101 sits at J101 by design, the opposite edge from U101 and the LDO, which puts C101
and C108 the length of the board away.

C19 is new at Rev 5.40 and goes the other way: at U101 pin 18, not at the jack. It filters what /RESET has picked up along the cord and the board, so it belongs at the pin it protects.

`/RESET` and its 10k pull-up were added at Rev 5.8. The pull-up goes on **every** expander
board — the opposite of the DO-NOT-FIT rule for the I²C pull-ups, and for a reason
(trunk §10.4).

The address is hardwired in copper on the rev 2 board: there are no strap links, and moving it means cutting tracks (trunk §10.2, Rev 5.42). There are no I²C pull-up footprints and no second expander; the bus pull-ups are on the generator board.

The no-connect flags matter: this board polls rather than using interrupt-on-change
(trunk §10.4), so ERC should be told the pins are deliberately unused rather than left to
report them.

---

### 4.4 Expander to trunk sheets

No parts. Sixteen labelled stubs.

```
U101 GPA0..GPA7 (pins 21-28) ── SEIZE_1..8    ── trunk1..8 SEIZE pin
U101 GPB0..GPB7 (pins 1-8)   ── RING_EN_1..8  ── trunk1..8 RING_EN pin
```

Use **plain local labels**, not global and not hierarchical — everything here is on one
sheet, and sixteen labelled stubs read better than sixteen wires crossing the page. Put
the label on the wire off the U101 pin and the same name on the wire into the sheet symbol's
pin.

---

### 4.5 Trunk lines — J7A101, J7B101

| Ref | Former name | Value | Symbol | Footprint |
|---|---|---|---|---|
| J7A101, J7B101 | J7A, J7B | RJ45 shielded | `Connector_Generic_Shielded:Conn_01x08_Shielded` | `Connector_RJ:RJ45_Amphenol_RJHSE5380` |

Four trunks per jack, one twisted pair each, T568B.

| RJ45 pin | Pair colour | J7A101 | J7B101 |
|---|---|---|---|
| 1 | white/orange | Trunk 1 TIP | Trunk 5 TIP |
| 2 | orange | Trunk 1 RING | Trunk 5 RING |
| 3 | white/green | Trunk 2 TIP | Trunk 6 TIP |
| 6 | green | Trunk 2 RING | Trunk 6 RING |
| 5 | white/blue | Trunk 3 TIP | Trunk 7 TIP |
| 4 | blue | Trunk 3 RING | Trunk 7 RING |
| 7 | white/brown | Trunk 4 TIP | Trunk 8 TIP |
| 8 | brown | Trunk 4 RING | Trunk 8 RING |

Note pins 3/6 and 5/4 — the T568B pair order is not sequential.

Each `TIP_n` and `RING_n` net runs from the sheet pin of the matching strip to the jack
pin above.

---

### 4.6 Audio — J104, J105 (TASCAM analog)

| Ref | Former name | Value | Symbol | Footprint |
|---|---|---|---|---|
| J104, J105 | J1, J2 | DB25 female | `Connector:DB25_Female` | `Connector_Dsub:DSUB-25_Female_Horizontal_P2.77x2.84mm_EdgePinOffset*` — see §5 |
| R102, R103 | JP4 | 0R | `Device:R` | `R_Axial_DIN0207` — D-Sub gnd to board GND, one per DB25 (R102 J104, R103 J105), **fitted** on the rev 2 board |

J104 = 8 board outputs to A32 inputs. J105 = 8 A32 outputs to board inputs.
Same pin pattern on both connectors. Board channel n = trunk n = A32 channel 24+n.

| Board ch | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| Hot (+) | 24 | 10 | 21 | 7 | 18 | 4 | 15 | 1 |
| Cold (−) | 12 | 23 | 9 | 20 | 6 | 17 | 3 | 14 |
| Ground | 25 | 11 | 22 | 8 | 19 | 5 | 16 | 2 |

Pin 13 not connected.

**The eight ground pins float at this board.** Common them into a single node per
connector — or one node for both — and take a link from there to board GND. The design asked for one link, unstuffed; the rev 2 board has two, R102 and R103, fitted with 0R (trunk §8.4, Rev 5.42).
Tx01 isolates and nothing in the secondary needs board ground; grounding both ends would
close a hum loop through the PSU, mains earth and the A32 chassis. The link exists so the
decision can be revisited on the bench if ring transients come through Tx01's interwinding
capacitance. See trunk Rev 5.21 §8.4.

Silkscreen what fitting R102 and R103 means, or someone will populate it thinking a missing part is
an oversight.

---

## 5. Before you start drawing

- **Transistor symbols carry the pinout in the suffix**, and they live in `Transistor_BJT`
  rather than `Device`. KiCad ships no 2N2222 or 2N3906 symbol, because from its point of
  view nothing distinguishes those parts but the pad order. Qx02 is `Q_NPN_EBC` and Qx01
  should be `Q_PNP_EBC` — pad 1 = E, 2 = B, 3 = C.
- **Qx03 is probably not EBC.** The MJE340/MJE350 in TO-126 is commonly **E-C-B**, so it
  likely wants `Q_PNP_ECB` rather than the suffix Qx02 and Qx01 use. Verify from the datasheet
  before drawing; there are eight of them.
- **Check all three against the physical parts** before committing footprints. TO-92
  devices sold as 2N2222A come in EBC, CBE and ECB depending on manufacturer, and a diode
  test with a meter settles it in five minutes. This is the one class of error on this
  board that costs a respin.
- **Tx01's symbol and footprint are both drawn and both custom**, `switchboard:XFMR_TY-311P` in
  `switchboard.kicad_sym` and `switchboard.pretty` respectively. The pads are numbered 1 and 3
  (primary) and 4 and 6 (secondary), which is the TY body's own numbering with the centre-tap
  positions 2 and 5 absent — and it is why the symbol is custom rather than the stock generic.
  KiCad matches pin number to pad number with no remapping, so a 1-2-3-4 symbol would land pin 3
  on pad 3, the far end of the primary: a wrong connection rather than an open one. The symbol's
  pins are numbered 1/3/4/6 and match, so nothing is outstanding here.
- `switchboard:Triad_SP-70` is now used by nothing. T3, the generator's operator tone injector,
  was deleted at station Rev 3.24 / generator Rev 27 when the tone became an A32 output stream on
  the station tap strip. Keep the file; the three SP-70s on hand are spares.
- **The dots are on pins 1 and 4** — the primary start and the secondary start. Mark it on the
  silkscreen and wire all 24 the same way; a single reversed transformer inverts one circuit's
  audio and nothing else, which is a fault that survives a long time before anyone notices.
- **Relay footprint is the Omron G6A pattern deliberately** — the CIT part is not in the
  KiCad libraries and the G6A is the nearest standard DPDT. Verify the pin pattern and
  body against the J104D2C5VDC.15S datasheet before layout.

---

## 6. The Rev 5.16 → 5.25 check

The previous version of this guide was written against trunk Rev 5.16 and its header was
never moved, so nine revisions of change entries had never been read back into it. Every
entry from 5.17 to 5.25 has now been checked against the guide, and every §13 row against
the parts tables above.

**Already correct, no change needed.** Rev 5.18's J6 (the OSTTC020162 at 5.00mm/300V,
which reverted Rev 5.17's merge of J5 and J6 once the parts on hand turned out to be
125V). Rev 5.19's shunt D6. Rev 5.20's R11–R15. Rev 5.21's JP4. Rev 5.22's TY-311P. Rev
5.23's deleted C14. Rev 5.24's ring-bus star, which changed nothing on this board. Rev
5.25's R_RST, C15, C16, C17 and the JP1–JP3 straps.

**Four things the guide was missing and now carries:** FH1 and FH2, which had a §13 row of
their own and no row here; the six-conductor cord requirement at J3, from Rev 5.25's
correction of that entry; F2's 71%-of-rating margin and the 500mA fallback, from Rev 5.24;
and the absence of a T2 screen, from Rev 5.25, which the station guide already stated and
this one did not.

**Two things the guide found that the document still needs.** Both want a Rev 5.26:

- **`C_C` has no reference designator.** Rev 5.20 assigned numbers to the five functionally
  named resistors and did not do the same for the one functionally named capacitor. `C_C`
  is not a legal KiCad reference any more than `R_set` is. **C1** is free — C2, C5 and
  C8–C17 are taken and C14 is retired — and it puts the compensation cap next to C2 on the
  same strip.
- **`L1` has a §13 row and no position in any net.** Resolved differently from how this
  note first read: rather than giving the unstuffed link a net (`V_FEED`, which this guide
  carried through 2026-09-09), trunk Rev 5.29 deletes the footprint. A 0207 site cannot
  take the 47mH part it was holding a place for, and §12.4 had already shown the part does
  nothing. The defect — a footprint nothing can refer to — is gone with the footprint.

---

## 7. PCB netclasses and assignments

Written 2026-09-08 against trunk Rev 5.27 and the generator's netclass table; §7.5 added
2026-09-09 with trunk Rev 5.28. For **Board Setup → Design Rules → Net Classes**
and the accompanying custom rules file (`trunks.kicad_dru`). Five classes. Every net on
the board is listed once below, either by name under its class or in the Default list in §7.4,
so a net that appears nowhere here is a net that was added after this was written.

**Net names as KiCad sees them.** A local label inside the strip sheet is prefixed with the
sheet path, so `NODE_A` on the second instance is `/trunk2/NODE_A` in the PCB. Root-sheet
local labels get a bare slash: `/TIP_1`. Global labels and power symbols carry no path:
`RING_HI`, `+24V_BRD`. The assignment patterns below use the `*` wildcard KiCad 9 accepts in
the netclass assignment table, so one line covers all eight instances — **verify that your
build accepts the pattern by checking the PCB net list panel after import; if `/trunk*/NODE_A`
matches nothing, the sheet symbols are not named `trunk1`…`trunk8` and the patterns need to
follow whatever names they carry.**

**Unnamed nets need names before they can be assigned.** KiCad auto-names an unlabelled net
`Net-(R101-Pad1)`, which differs per instance and cannot be pattern-matched sensibly. Four
strip nets and two root nets below carry a class other than Default and had no label in §3
and §4; the labels this section gives them need
to be placed in the schematic, or the assignments cannot be made. The Default-class unnamed
nets in §7.4 do not need labels, but are given suggested ones for the same reason a `Function`
field exists — so a net on the PCB says what it is.

### 7.1 Voltages the classes are sized for

Two figures decide every number below, both from trunk §7 and §14:

- **141V peak** — the generator's no-load ring output, present on the ring bus whenever the
  system is powered, and on the trunk pairs and node A/B whenever the switchboard rings a
  trunk by mistake. Trunk §15 says to size against this and not the 127V peak nominal.
- **3mm** — the creepage trunk §14 requires from each high-voltage zone to logic.

KiCad's `clearance` constraint is a copper-to-copper distance, not a creepage path; the 3mm
is applied as clearance because that is the check available, and the slot under each Ux01 body
(§14) is what actually delivers the creepage across the optocoupler barrier. **KiCad 9 added a
`creepage` constraint that follows board edges and slots — check whether your build has it
before relying on the clearance rule alone.**

Within a high-voltage class — RING_HI to RING_LO, TIP_n to RING_n — the two conductors
are at most 141V apart. IPC-2221 external uncoated (B2) gives 0.6mm at 101–150V, which is
the band 141V sits at the top of. That is the class clearance. It is deliberately not 3mm:
the relay contact pins sit on a 2.54mm pitch and the J102 terminal on 5.00mm, and a 3mm
class clearance would fail DRC at every relay with no way to satisfy it.

### 7.2 Netclass definitions

Columns in the order KiCad's Board Setup → Net Classes table presents them, so the row
can be typed across.

| Name | Clearance | Track Width | Via Size | Via Hole | Colour | Sized by |
|---|---|---|---|---|---|---|
| **Default** | 0.2mm | 0.25mm | 0.6mm | 0.3mm | — | Logic, audio, sense. Nothing over 24V, nothing over a few tens of mA. Same as the generator's Default |
| **POWER** | 0.25mm | 1.0mm | 1.0mm | 0.6mm | green | 290mA on +24V_BRD, 278mA of coil current on +5V (§12.2), and the D101 clamp path carrying fault current until F102 opens. Width is for the fault, not the load. Same as the generator's Power |
| **LINE** | 0.6mm | 0.6mm | 0.6mm | 0.3mm | orange | 141V peak from the switchboard side. 28mA loop current — width is for mechanical robustness, not current |
| **RING** | 0.6mm | 0.6mm | 0.6mm | 0.3mm | red | 141V peak from J102 whenever the generator is enabled. Up to 178mA with eight ringing (trunk §7.6). Track matches the generator's Ring class; clearance does not — see below |
| **LOOP** | 0.6mm | 0.6mm | 0.6mm | 0.3mm | yellow | The two nodes between Qx03 collector and Dx03. Swing to about −113V on the aiding half-cycle of an accidental ring (24V − 137V absorbed, §3.4). Same spacing as LINE, **exempt from the 3mm rule** — see §7.3 |

µVia, DP Width and DP Gap: leave at the KiCad defaults on every row. No microvias and no
differential pairs on this board.

**Relation to the generator's classes.** Default and Power are the generator's numbers
unchanged: same fab, same 24V rail, no reason for the two boards to differ. The generator's
Ring class is 0.6mm track at **1.0mm** clearance, and the trunk's is 0.6mm at **0.6mm**.
The difference is the relay. On the generator the ring nets land only on 5.00mm terminals,
the fuse holder and the transformer terminal block, so 1.0mm cost nothing. Here RING_HI
sits next to TIP on Kx01's contact pins at 2.54mm pitch; with the pads the G6A footprint
draws that gap is around 0.9–1.0mm, and a 1.0mm class clearance would fail at sixteen
contact pairs. 0.6mm is the IPC-2221 figure for the voltage (§7.1), and it is what the
relay pitch permits. If the J104D drawing shows a wider contact pitch than the G6A's,
raise it to 1.0mm to match the generator; do not lower the generator's to match this.

Track and via values are the same on all four layers (§7.5); the classes are about
clearance, not stack-up.

GND is in POWER so that any GND drawn as a track is wide. With the In1 plane (§7.5)
there should be very little of it — a pad to its via, and nothing else. The plane is not
governed by the class track width.

### 7.3 Custom DRC rule — high voltage to low voltage

The 3mm to logic cannot be a class clearance for the reason in §7.1, so it is a rule. Put
this in `trunks.kicad_dru` beside the project file; KiCad loads it automatically.

```
(version 1)

(rule "HV zone to low voltage"
  (condition "(A.NetClass == 'RING' || A.NetClass == 'LINE') && !(B.NetClass == 'RING' || B.NetClass == 'LINE' || B.NetClass == 'LOOP')")
  (constraint clearance (min 3mm)))
```

What it does: any copper in RING or LINE must be 3mm from any copper that is not in RING,
LINE or LOOP — Default, POWER, and unconnected pads, holes and copper with no net, since
those have an empty NetClass and the condition is true for them. RING to LINE is left at the
class 0.6mm, which is what the relay contacts need. KiCad evaluates the condition with the
two items in both orders, so the rule does not need writing twice — **confirm this on your
build by placing a Default-class track 2mm from RING_HI and running DRC before trusting it.**

**Why LOOP is exempt.** Qx03 is a TO-126 on a 2.28mm pitch. Its collector is the −113V node
and its base and emitter are within a volt of the 24V rail. No rule can put 3mm between them
and the part is not going to change, so the collector node and the Rx05–Dx03 node are their own
class at LINE spacing and outside the 3mm rule. The 3mm to logic for this part of the strip
is delivered by placement — Qx03, Rx05 and Dx03 at the relay end of the strip, next to node A,
with the seizure detector and the relay driver at the other end — and not by DRC. The
document's three high-voltage zones (§14) are J7A101/J7B101 and their wiring, the ring bus, and
the relay contact ends; the current source is not among them and this class is the
statement of that.

**Where the rule will fire and what to do about it:**

- **Kx01, contact pins to coil pins.** Coil (+5V, `COIL`) is Default/POWER; contacts are
  LINE and RING. Whether the J104D coil pins are 3mm from the nearest contact pin is decided
  by the part drawing, which §5 already says to check. If they are closer, the violation is
  real and the rule is right: the relay's internal dielectric strength is what carries it
  (§15, verify from the datasheet), and the DRC marker is excluded per footprint with the
  reason recorded in the exclusion comment. Do not lower the rule to make it pass.
- **Cx04.** NODE_A (LINE) on one pin, `T2P` (Default) on the other. 15mm pitch, no
  violation.
- **Dx03.** `R1_D1` (LOOP) to NODE_A (LINE). Exempt pairing, 10.16mm pitch, nothing to see.
- **Dx01.** Both pins LINE. Class clearance only.
- **Rx06, Rx07 at NODE_B.** NODE_B (LINE) to GND and to `OC_IN` (Default) — axial parts at
  7.62mm or more, no violation, and this is the barrier the Ux01 slot completes.

### 7.4 Netclass assignments

Patterns as entered in the assignment table. Where a name is new (not in §3 or §4), it is
marked, and the label needs placing in the schematic.

**POWER**

| Pattern | Net | Where |
|---|---|---|
| `+24V_BRD` | Board 24V rail | Root, F102 output |
| `/24V_IN` | J103 pin 1 to F102 — **new label** | Root |
| `+5V` | Converter output | Root |
| `+3V3` | LDO output | Root |
| `GND` | | Everywhere |

**RING**

| Pattern | Net | Where |
|---|---|---|
| `/RING_IN` | J102 pin 1 to F101 — **new label** | Root |
| `RING_HI` | Global | F101 output, all eight Kx01 pole 1 NO |
| `RING_LO` | Global | J102 pin 2, all eight Kx01 pole 2 NO |

**LINE**

| Pattern | Net | Where |
|---|---|---|
| `/TIP_*` | `/TIP_1` … `/TIP_8` | Root, J7A101/J7B101 to sheet pins |
| `/RING_*` | `/RING_1` … `/RING_8` | Root, J7A101/J7B101 to sheet pins |
| `/trunk*/NODE_A` | Relay pole 1 NC, Dx03 cathode, Cx04 | Strip ×8 |
| `/trunk*/NODE_B` | Relay pole 2 NC, Rx06, Rx07, Tx01 pin 3 | Strip ×8 |

The pattern `/RING_*` matches `/RING_1`…`/RING_8` and does not match the global
`RING_HI`/`RING_LO`, which carry no leading slash. Check both appear in the right class in
the net list panel after import; if `/RING_*` has caught the bus, the global labels were
placed as local ones somewhere.

**LOOP**

| Pattern | Net | Where |
|---|---|---|
| `/trunk*/Q4C` | Qx03 collector to Rx05 — **new label** | Strip ×8 |
| `/trunk*/R1_D1` | Rx05 to Dx03 anode — **new label** | Strip ×8 |

**Default** — everything else. Listed in full so that the class is a decision rather than a
remainder. Suggested labels in brackets for nets that have none; these are optional, unlike
the ones above.

Root sheet:

| Net | Members |
|---|---|
| `SCL`, `SDA`, `/RESET` | J101, TVS101, U101, R101 |
| `/SEIZE_1` … `/SEIZE_8` | U101 GPA0–7 to sheet pins |
| `/RING_EN_1` … `/RING_EN_8` | U101 GPB0–7 to sheet pins |
| `/A32_IN_H_1` … `_8`, `/A32_IN_C_1` … `_8` | Sheet pins to J104 |
| `/A32_OUT_H_1` … `_8`, `/A32_OUT_C_1` … `_8` | J105 to sheet pins |
| U101 pins 15, 16 to +3V3, pin 17 to GND | Address, hardwired; no labels needed |
| J104 and J105 ground pins to R102 and R103 [`DSUB_GND`] | Tied to GND through the fitted 0R parts (§4.6). ERC will report it undriven; that is correct |

Strip sheet, ×8:

| Net | Members |
|---|---|
| Rx02 – Qx03 emitter – Qx01 base – Cx02 [`Q4E`] | Current source sense node |
| Qx01 collector – Qx03 base – Rx04 – Cx02 [`Q4B`] | Current source control node |
| Rx07 – Ux01 pin 2 [`OC_IN`] | Detector LED feed |
| Ux01 pin 6 → `SEIZE` | Hierarchical; Rx12 pull-up lands here |
| `RING_EN` → Rx01 | Hierarchical |
| Rx01 – Qx02 base – Rx03 [`Q2B`] | Driver base |
| Qx02 collector – Kx01 coil (−) – Dx02 anode [`COIL`] | Coil switching node. 30mA, flyback through Dx02 |
| Cx04 – Tx01 pin 1 [`T2P`] | Primary, isolated from NODE_A by Cx04 |
| Tx01 pin 4 – Rx08 – Rx10 [`T2S_H`] | Secondary hot |
| Tx01 pin 6 – Rx09 – Rx11 [`T2S_C`] | Secondary cold |
| `A32_IN_H`, `A32_IN_C`, `A32_OUT_H`, `A32_OUT_C` | Hierarchical, Rx08–Rx11 to sheet pins |

The SCL/SDA/`/RESET` group stays Default rather than getting an I²C class of its own:
nothing about their geometry differs from any other logic net, and §14's requirement that
they keep clear of the converter's switching node is a placement matter the DRC cannot
express. If it helps to see them, give them a colour in the net inspector; that does not
need a class.

The audio nets are balanced pairs at line level and audio frequency. Nothing about them
wants controlled spacing or width; they are Default. Keep each pair together by hand.

### 7.5 Stack-up and inner layers

Four layers, in the generator board's order:

| Layer | Carries |
|---|---|
| F.Cu | Strip signals, ring spine, J102/J7 wiring, and everything at the connectors |
| In1.Cu | GND plane, solid |
| In2.Cu | +24V_BRD, +5V, +3V3 as a split pour |
| B.Cu | Strip signals; the overflow from F.Cu |

The generator used both inner layers for ground. The trunk board has three rails that
cross all eight strips — 24V to each L1, 5V to each relay coil and its Cx03, 3.3V to each
Ux01 pin 8 and Rx12 — and one ground plane is plenty for a board with nothing faster than a
relay coil step. So In2 becomes the power comb and both outer layers are left to the
strips.

**Split lines on In2.** Draw the three regions before placing the first strip, not after,
because each strip has to reach all three with a single via and the split lines fix where
those vias can go. The natural arrangement, with the strips arrayed along the board:

- **+24V_BRD** as a band along the strips at the current-source end, one via per strip
  at the Qx01 emitter / Rx02 node. There is no per-strip feed net; the strip's 24V is the
  rail (trunk Rev 5.29).
- **+5V** as a band along the relay-driver end, one via per Cx03/coil.
- **+3V3** as a band along the Ux01 end, one via per Cx05/Rx12, extended to U101, TVS101/C18 and
  the LDO output.

The converter U102 and LDO U103 sit in their corner (§14) and their outputs enter the In2
regions there. Each region is fed at one point; there is no second path to check.

**Rule areas, both inner layers, at the high-voltage edge.** Draw a rule area on In1 and
In2 that covers J102, J7A101, J7B101, the ring spine, the relay contact ends and the LINE/RING
copper, with the 3mm margin, and set it to keep out copper pours. This is necessary
because the §7.3 rule will not do it: KiCad's `clearance` constraint is evaluated between
items on the same layer, and a plane on In1 under a RING track on F.Cu is not a
same-layer pair. Draw it by hand and note the reason in the rule area's name.

Electrically the keepout is not required. 141V across 0.2mm of prepreg is a stress of
roughly 0.7kV/mm against a laminate rated some tens of kV/mm; the 3mm is a surface
creepage figure and does not apply through the board. The keepout is drawn for three
other reasons: it makes the silkscreen HV boundary true on every layer rather than only
the two you can see; it removes the plane's capacitance to a 20Hz net that carries 40kHz
PWM residue (§14); and it costs nothing, because there is no logic on that edge for the
plane to serve.

**The LOOP nodes are not in the keepout.** Qx03's collector at −113V sits over the In1
plane. Same argument as above — through the laminate it is nothing — and the current
source is in the middle of the strip where the plane needs to be.

**The `physical_clearance` constraint** may evaluate across layers in your KiCad 9 build,
in which case a second rule could enforce the keepout automatically instead of a drawn
area. Not relied on here; check before using it.

**Coupling.** On a standard four-layer core the two inner layers are about 1mm apart and
In2 is close to B.Cu, not to the ground plane. Nothing on this board cares — the fastest
edge is a relay coil turning off through Dx02 — but the power pour is not a stripline over
ground and should not be described as one.

**What this retires in the trunk document.** The star of eight Rx06 returns and the
"ground pour between" the converter and the strips (§12.4, §14) were written for a
two-layer board and are superseded by the plane; trunk Rev 5.28 rewrites both and deletes
the Tx01 shield star, which referred to a terminal the TY-311P does not have.

### 7.6 What this section leaves open

- The J104D coil-to-contact pin spacing, which decides whether the Kx01 exclusion in §7.3 is
  needed. Part drawing, not this document.
- Whether the KiCad 9 `creepage` constraint is available and behaves with the Ux01 slot. If it
  is, a second rule with `(constraint creepage (min 3mm))` on the same condition is the
  honest check and the clearance rule becomes a backstop.
- The ring spine should stay on F.Cu. If it must change layers, the via passes through the
  In1/In2 keepout and needs its own 3mm ring of cleared plane on the way — the rule area
  should already provide that if it was drawn to the LINE/RING copper and not just to the
  connectors.
- The In2 split lines are placement, and placement is not done. §7.5 describes the
  arrangement that follows from the strip order in §14; if the strips end up arrayed the
  other way, the three bands rotate with them.
