# Ring Generator Board — KiCad Schematic Drawing Guide

> **Follows `ring_generator.md` Rev 72 for designators, 2026-10-05.** Every reference in this guide's tables, netlists and prose is the board's as built (`kicad/control`), the names `ring_generator.md` uses from Rev 72. The board was drawn with a different assignment from the one this guide planned; §1's table maps the guide's planned references and the document's former names to the board. The wiring this guide describes is still its pre-build plan where the board differs — the 74HCT04 gate assignment, J1's four pins, the SP721 pins — and `ring_generator.md` §5.1, §10 and §11 are the authority for what was built. §4 is a record and keeps the names it was written with.

Derived from ring generator Rev 32 §10 and §11, and the KiCad library plan.
Structure: **one flat sheet**. No hierarchy, no instances.

---

## 1. Sheet structure

The trunk and station boards are eight identical circuits around a common root, so they
want a hierarchical sheet drawn once and instanced. This board is the opposite: every
part on it is unique. There is one H-bridge, one transformer, one controller. A
hierarchical sheet with a single instance buys nothing and costs a level of indirection
when you are tracing a gate drive loop.

Draw it flat, but not as one undifferentiated page. Lay it out in the six blocks of §3
below, in reading order, and put a box and a title around each. The blocks are the same
divisions Rev 32 §13 uses for layout zones, so schematic and PCB tell the same story and a note
written against one is findable from the other.

The one division worth respecting absolutely is the ring output. `RING_HI`,
`RING_HI_SB` and `RING_LO` belong in their own corner of the sheet with the transformer
secondary, F2, J7 and J8, and nothing else routed through that space.

### Designators

The board was annotated by KiCad, not to the plan this guide set out, and every part keeps the board's reference (`ring_generator.md` Rev 68 and Rev 72). Former document names and this guide's planned references, for reading older notes:

| Former document name | Planned here | Board |
|---|---|---|
| `U_ESP32` | U1 | U6 |
| `IC1` | U2 | U4 |
| `IC2` | U3 | U5 |
| `U4` | U4 | U1 |
| `U_12V` | U5 | U3 |
| `TVS2` | U6 | U2 |
| `D1` | D1 | D1 |
| `D_BOOT1` | D2 | D2 |
| `D_BOOT2` | D3 | D3 |
| `R_SDA` | R1 | R2 |
| `R_SCL` | R2 | R1 |
| `R_SD_PD` | R3 | R4 |
| `R_PWMA_PU` | R4 | R3 |
| `R_PWMB_PU` | R5 | R5 |
| `R_G1`, `R_G2`, `R_G3`, `R_G4` | R6, R7, R8, R9 | R6, R8, R7, R9 (the guide numbered them in its Q order; the board's R7 drives Q2, low left) |
| `R_SNB` | R10 | R10 |
| `R_SD_PD2` | R11 | — (not fitted) |
| `C_BULK1` | C1 | C2 |
| `C_BULK2` | C2 | C3 |
| `C_12V_IN1` | C3 | C4 |
| `C_12V_IN2` | C4 | C5 |
| `C_12V_OUT` | C5 | C7 |
| `C_12V_BULK` | C6 | C6 |
| `C_U4` | C7 | C1 |
| `C_VCC1` | C8 | C8 |
| `C_VCC2` | C9 | C11 |
| `C_BOOT1` | C10 | C9 |
| `C_BOOT2` | C11 | C10 |
| `C_SNB` | C12 | C12 |
| `C_TVS2` | C13 | C15 |
| `R_MON1` | R14 | R12 |
| `R_MON2` | R15 | R11 |
| `C_MON` | C14 | C13 |
| `R_GS3` | R12 | R13 (now R_GS2; bodged) |
| `R_GS4` | R13 | R14 (bodged) |
| `C_OUT` | — | C14 |
| `Q2`, `Q3` | Q2 high right, Q3 low left | Q3 high right, Q2 low left |
| `J1`, `J2`, `J3`, `J4`, `J6`, `J7`, `J8`, `J9`, `J10` | same | J2, J7, J5, not on the board, J8, J9, J6, J1, J3 |

Net names follow the MOSFETs: the guide's `Q2_GATE` is the board's `Q3_GATE` and the reverse. `PS1`, `T1`, `FH1` and `FH2` are not schematic parts.

---

## 2. Nets, labels and power

No hierarchical sheet pins on this board — there is no child sheet. Everything is either
a drawn wire, a local label, or a global power symbol.

**Power symbols**, `PWR_FLAG`-backed, placed once each:

| Net | Where the flag goes |
|---|---|
| `+24V_IN` | J2 pin 1, upstream of F1 |
| `+24V_SW` | F1 pin 2 — the whole board's switched rail |
| `+12V_VCC` | U3 Vout |
| `+5V` | Olimex EXT1 pin 1 |
| `+3V3` | Olimex 3.3V pin |
| `GND` | system ground |

**Local labels** for everything else. The signal names in Rev 32 §11 are already good net
names and there is no reason to invent others: `IN1`, `IN2`, `SD`, `SD_N`, `SW_L`,
`SW_R`, `VB_L`, `VB_R`, `HO_L`, `HO_R`, `LO_L`, `LO_R`, `Q1_GATE`…`Q4_GATE`, `SNUB_MID`,
`GPIO4`, `GPIO14`, `GPIO32`, `GPIO33`, `SDA`, `SCL`, `/RESET`.

**The ring nets** — `RING_HI`, `RING_HI_SB`, `RING_LO` — are three separate nets and the
distinction is the fuse again. `RING_HI` runs from J6 to J7 and to F2 pin 1; `RING_HI_SB` is only the short piece from F2 pin 2 to J8. Merge them and the
switchboard branch is unfused.

Give all three a distinct colour or a hatched box on the sheet, the same treatment the
trunk guide gives its ring bus. The trunk board's reason was that a global label hides a
connection; here the reason is that these are ordinary drawn wires carrying 141V peak on
a sheet where everything else is 24V or less, and nothing about the drawing says so.

---

## 3. The six blocks

Each block below carries its own parts and its own nets, in that order. Draw a block
start to finish before moving on. The blocks match Rev 32 §13's layout zones, so a note written
against one is findable from the other.

Every parts table carries the board reference and, beside it, the name the document used
before Rev 72 (for connectors, MOSFETs and ICs, the numbering before Rev 68), so older notes
stay readable without paging back to §1.

**Symbol and footprint names come from `kicad_library_plan.xlsx`**, which records them as
checked against the KiCad 9.0.0 stock libraries on 21 Aug 2026. That file is the authority;
if it and this guide disagree, it wins. Rows still marked *verify* there are body-dimension
questions rather than name questions.

---

### 3.1 Power entry and the 24V rail

| Ref | Former name | Value | Symbol | Footprint |
|---|---|---|---|---|
| J2 | `J1` | OSTTE020104, 3.50mm **125V** | `Connector:Screw_Terminal_01x02` | `TerminalBlock_4Ucon:...1x02_P3.50mm_Horizontal` |
| F1 | `F1` | 500mA slow-blow, 0218.500MXP | `Device:Fuse` | `Fuse:Fuseholder_Clip-5x20mm_*` |
| FH1 | `FH1` | 649-series block | — | holder; part of F1's footprint, not a separate symbol |
| D1 | `D1` | 1N5822 | `Diode:1N5822` | `D_DO-201AD_P12.70mm_Horizontal` |
| C2 | `C_BULK1` | 100µF 50V | `Device:C_Polarized` | `CP_Radial_D8.0mm_P3.50mm` |
| C3 | `C_BULK2` | 100nF | `Device:C` | `C_Disc_D5.1mm_W3.2mm_P5.00mm` |

```
J2 pin1 ── +24V_IN ── F1 pin1
F1 pin2 ── +24V_SW
D1 cathode ── +24V_SW,  D1 anode ── GND     [SHUNT clamp, reverse-biased]
J2 pin2 ── GND

C2, C3 across +24V_SW ── GND                (at Q1/Q3 drains, not at J2)
+24V_SW ── Q1 drain, Q3 drain               (drawn in 3.5)
```

`+24V_IN` and `+24V_SW` are two nets, not one, and the fuse is what separates them. If
you draw them as a single rail the fuse has nothing to protect and the D1 clamp has
nothing to blow. This is the most consequential net split on the board.

D1 is a shunt clamp, not a series diode. Cathode to the rail, anode to ground, carrying
nothing until the supply is connected backwards — then it conducts and blows F1. **F1
must be upstream.** J2, then F1, then the clamp, then the board. If the fuse ends up
downstream of the clamp it carries only the board's own load current, never sees the
fault, and the 1N5822 conducts 6.5A until it dies.

Same orientation trap as the trunk board's D101, and it catches people the same way,
because the diode symbol invites a series drawing.

**PS1 is not a schematic part.** Rev 32 §10.1 lists the Mean Well LRS-150-24 because it is
the board's supply, but it is a chassis part shared by the whole system and it arrives
here through J2. Draw a power flag on `+24V_IN`, not a PSU symbol.

---

### 3.2 +12V regulator

| Ref | Former name | Value | Symbol | Footprint |
|---|---|---|---|---|
| U3 | `U_12V` | Traco TSR 1-24120 | `Converter_DCDC:TSR1-24120` | `Converter_DCDC:Converter_DCDC_TRACO_TSR-1_THT` |
| C4 | `C_12V_IN1` | 47µF 50V | `Device:C_Polarized` | `CP_Radial_D6.3mm_P2.50mm` |
| C5 | `C_12V_IN2` | 100nF | `Device:C` | `C_Disc_D5.1mm` |
| C7 | `C_12V_OUT` | 100nF | `Device:C` | `C_Disc_D5.1mm` |
| C6 | `C_12V_BULK` | 10µF 50V | `Device:C_Polarized` | `CP_Radial_D5.0mm_P2.00mm` |

```
U3 Vin ── +24V_SW,  U3 GND ── GND,  U3 Vout ── +12V_VCC
C4, C5 across +24V_SW ── GND      (input side, at U3's input pin)
C7, C6 across +12V_VCC ── GND     (output side, at U3's output pin)

+12V_VCC ── U4 pin4 (VCC), U5 pin4 (VCC)     (drawn in 3.5)
+12V_VCC ── D2 anode, D3 anode               (drawn in 3.5)
```

C4 and C5 sit on `+24V_SW`, not on `+12V_VCC`. They are the regulator's **input**
capacitors and they belong to this block even though their net comes from 3.1 — that is
why they are here and not there.

C7 and C6 are both at the output and do different jobs: C7 decouples, C6 stores. The
IR2104s draw gate charge in pulses at 40kHz and 100nF holds nothing between them.

`TSR1-24120` — no underscore after TSR, and in `Converter_DCDC` rather than
`Regulator_Switching`. The symbol carries its own footprint. **Pinout verified against the
Traco datasheet of 2 July 2026**: 1 +Vin, 2 GND, 3 +Vout, SIP-3 on 2 × 2.54mm.

Two things from that datasheet reach layout rather than the schematic. **Route no traces
under the converter** — it asks for this explicitly, and this board also carries the I²C
bus and the ring output. And maximum output capacitance is 470µF, against the 10.1µF this
rail carries, so C7 and C6 are nowhere near the limit.

---

### 3.3 Controller and I²C

| Ref | Former name | Value | Symbol | Footprint |
|---|---|---|---|---|
| U6 | `U_ESP32` | Olimex ESP32-POE-ISO | **make** — no stock symbol; see §5 | none — socketed on two 1x10 pin sockets |
| R2 | `R_SDA` | 2.2k | `Device:R` | `R_Axial_DIN0207` |
| R1 | `R_SCL` | 2.2k | `Device:R` | `R_Axial_DIN0207` |
| U2 | `TVS2` | SP721APP | `switchboard:SP721` | `Package_DIP:DIP-8_W7.62mm` |
| C15 | `C_TVS2` | 100nF | `Device:C` | `C_Disc_D5.1mm` |
| J5 | `J3` | 6P6C | `Connector_Generic:Conn_01x06` | `Connector_RJ:RJ12_*` |
| J4 (not on the board) | `J4` | 4-pin header | `Connector_Generic:Conn_01x04` | `PinHeader_1x04_P2.54mm_Vertical` — **footprint only, DNP** |
| J1 | `J9` | 3-pin header | `Connector_Generic:Conn_01x03` *verify* | `PinHeader_1x03_P2.54mm_Vertical` *verify* — **fit** |

```
U6 3.3V pin ── +3V3
U6 EXT1 pin1 ── +5V
U6 GND ── GND

U6 GPIO13 ── SDA ── R2 ── +3V3,  U2 IN, J5 pin4
U6 GPIO16 ── SCL ── R1 ── +3V3,  U2 IN, J5 pin2
U6 GPIO5  ── /RESET ──           U2 IN, J5 pin1
J5 pins 3, 5, 6 ── GND
U2 pin8 (V+) ── +3V3,  U2 pin4 (V−) ── GND
C15 from U2 pin8 to U2 pin4, at the device
U2 three remaining inputs ── NO CONNECT flags

U6 GPIO4  ── GPIO4 ── J1 pin1    (master enable, active LOW, internal pull-up)
GND       ────────── J1 pin2
U6 GPIO15 ── GPIO15 ── J1 pin3   (waveform sync — see doc §12.5)
J4 (not on the board) pins ── second I²C, FOOTPRINT ONLY
```

`switchboard:SP721` is the one custom symbol here that already exists and is already used
on the station and trunk boards. **Pinout verified against the datasheet** — Littelfuse
SP721 series, revision GD 07/10/24: IN on 1–3 and 5–7, V− on 4, V+ on 8.

C15 is new at Rev 34 and belongs at U2's own pins, not with the other decoupling. The
SP721 does not shunt to ground — it conducts the transient from the IN pin into V+ — so
V+ has to source that current locally or it lifts while the clamp is working. This board
has no other +3.3V decoupling at all, since the rail arrives from the Olimex header.

`GPIO4` lands on J1 pin 1 as of Rev 43 — a 2.54mm shunt across pins 1 and 2 pulls it low
and the generator runs. Before Rev 43 the net went nowhere in the document and this guide
asked for a text note explaining what grounded it; the header existed on the schematic and
in neither place.

**GND is in the middle of J1 on purpose.** The enable shunt is fitted once; the scope
probe on pin 3 is used constantly and wants the shortest ground return the header allows.
A shunt put wrongly across pins 2 and 3 grounds a push-pull output, which it survives.

`GPIO15` is a strapping pin — firmware leaves it as an input until `setup()` runs. Nothing
on the sheet enforces that, so it wants a text note beside J1.

U2's spare inputs get explicit no-connect flags. It is a six-input rail clamp with three
in use, and ERC should be told the other three are deliberate.

**The Olimex pin numbers are the one thing on this board that costs a respin.** Rev 32
§3.1 says so and it is worth repeating as a text note on the sheet: verify GPIO4, GPIO5,
GPIO13, GPIO14, GPIO16, GPIO32, GPIO33, the 3.3V pin and EXT1 pin 1 against the Olimex
schematic for the board revision physically in hand. GPIO17 must stay free — the LAN8710A
has no crystal and takes its 50MHz clock from that pin.

---

### 3.4 Level translation and SD buffer

| Ref | Former name | Value | Symbol | Footprint |
|---|---|---|---|---|
| U1 | `U4` | 74HCT04 | `74xx:74HCT04` | `Package_DIP:DIP-14_W7.62mm` |
| C1 | `C_U4` | 100nF | `Device:C` | `C_Disc_D5.1mm` |
| R4 | `R_SD_PD` | 10k | `Device:R` | `R_Axial_DIN0207` |
| R3 | `R_PWMA_PD` | 10k | `Device:R` | `R_Axial_DIN0207` |
| R5 | `R_PWMB_PD` | 10k | `Device:R` | `R_Axial_DIN0207` |
| R_SD_PD2 (not fitted) | `R_SD_PD2` | 10k | `Device:R` | `R_Axial_DIN0207` |

```
74HCT04 pinout, verified against TI SCLS042F §4:
                1A 1, 1Y 2, 2A 3, 2Y 4, 3A 5, 3Y 6, GND 7,
                4Y 8, 4A 9, 5Y 10, 5A 11, 6Y 12, 6A 13, VCC 14.

U6 GPIO32 ── GPIO32 ── U1 pin1              (Gate 1 in)
GPIO32 ── R3 ── GND                         (pull-down, low through boot)
U1 pin2  ── PWMA_MID ── U1 pin3             (Gate 1 out → Gate 2 in)
U1 pin4  ── IN1 ── U4 pin2 (IN)             (Gate 2 out)

U6 GPIO33 ── GPIO33 ── U1 pin5              (Gate 3 in)
GPIO33 ── R5 ── GND                         (pull-down)
U1 pin6  ── PWMB_MID ── U1 pin9             (Gate 3 out → Gate 4 in)
U1 pin8  ── IN2 ── U5 pin2 (IN)             (Gate 4 out)

U6 GPIO14 ── GPIO14 ── U1 pin11             (Gate 5 in)
GPIO14 ── R4 ── GND                         (pull-down)
U1 pin10 ── SD_N ── U1 pin13                (Gate 5 out → Gate 6 in)
U1 pin12 ── SD ── U4 pin3, U5 pin3          (LOW = shutdown)
SD ── R_SD_PD2 (not fitted) ── GND                            (holds shutdown with U1 unpowered)

U1 pin14 ── +5V,  U1 pin7 ── GND
C1 from pin14 to pin7, at the device
```

**Pinout verified against the datasheet** — TI SCLS065G, §4, DIP-14 top view:

```
1Y  1 ┃ 14  VCC        Gate 1: out 1, in 2 3
1A  2 ┃ 13  4Y         Gate 2: out 4, in 5 6
1B  3 ┃ 12  4B         Gate 3: in 8 9, out 10
2Y  4 ┃ 11  4A         Gate 4: in 11 12, out 13
2A  5 ┃ 10  3Y
2B  6 ┃  9  3B
GND 7 ┃  8  3A
```

Note the asymmetry, because it is the thing that invites a wrong assumption: the upper
half runs Y-A-B and the lower half runs A-B-Y, so outputs are on 1, 4, 10 and 13. That is
the exact complement of the 7400, and reasoning from one to the other gets it backwards.
Rev 33 §11 is correct on all four gates.

**Every path is two inverters, so every path is non-inverting.** IN1 follows GPIO32, IN2
follows GPIO33, SD follows GPIO14. `PWMA_MID` and `PWMB_MID` are the nets between the two
gates of each PWM path — they exist for the same reason `SD_N` does, and the second gate's
input must not share a net with its own output.

**The PWM pins are active HIGH as of Rev 44**, so duty is written directly and 0 is the
park value. That is LEDC's power-on state, so the peripheral comes up parked. Under the
74HCT02 the opposite was true and 0 duty was a DC short across the primary. Draw the tie explicitly at the pins rather than relying on the
symbol; KiCad's multi-unit `74xx` symbols put each gate on its own unit and a floating
second input is easy to leave behind.

R3 and R5 are **pull-downs to GND** as of Rev 44 — they were pull-ups to +3.3V while the
drive was active low. Not optional either way: GPIO32 and GPIO33 have no internal pull at
reset, so without them both inverter inputs float through the bootloader window, and a
floating HCT input near threshold drives its gate either way.

**SD low is shutdown; SD high is enabled.** R4 holds GPIO14 low from power-on, and gates 3
and 4 are a non-inverting pair, so SD follows GPIO14 down and the bridge stays off. The
second gate is what makes that true — a single inverting gate would turn R4's pull-down
into an *enable* at power-on. R_SD_PD2 (not fitted), new at Rev 37, pulls the SD net itself down, covering
the case R4 cannot: PoE absent with the 24V bus live, where +12V is up and both drivers
are alive while U1 has no supply.

The gate is **level translation**, and that is the whole job. Shoot-through within a
leg is handled inside the IR2104, which derives HO and LO from one IN pin with 520ns
typical deadtime. The interlock that used to be here forbade a harmless state and put the
dangerous one where an unprogrammed GPIO lands; Rev 40 removed it and Rev 44 replaced the
NOR with an inverter. Do not re-add it.

The reason the gate is here at all is the threshold: the ESP32's guaranteed VOH is
0.8 × VDD = 2.64V against the IR2104's 3.0V VIH minimum, so direct drive is outside
specification by 0.36V. The IRS2104 would solve that electrically and is surface-mount
only.

`74xx:74HCT02` exists — place that, not `74HC02`. The two are pin-identical and a symbol
cannot tell them apart, but the whole of §5 turns on which is fitted: an HC part has a
3.5V input threshold against a 3.3V drive, and works on the bench while failing in the
rack.

---

### 3.5 Gate drive and H-bridge

| Ref | Former name | Value | Symbol | Footprint |
|---|---|---|---|---|
| U4 | `IC1` | IR2104PBF, left | `Driver_FET:IR2104` | `Package_DIP:DIP-8_W7.62mm` — **assign it by hand** |
| U5 | `IC2` | IR2104PBF, right | same | same |
| C8 | `C_VCC1` | 100nF | `Device:C` | `C_Disc_D5.1mm` |
| C11 | `C_VCC2` | 100nF | `Device:C` | `C_Disc_D5.1mm` |
| D2 | `D_BOOT1` | UF4007 | `Device:D`, value set to UF4007 | `Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal` |
| D3 | `D_BOOT2` | UF4007 | same | same |
| C9 | `C_BOOT1` | 100nF | `Device:C` | `C_Disc_D5.1mm` |
| C10 | `C_BOOT2` | 100nF | `Device:C` | `C_Disc_D5.1mm` |
| Q1 | `Q1` | IRLZ44NPBF, high left | `Transistor_FET:IRLZ44N` | `Package_TO_SOT_THT:TO-220-3_Vertical` |
| Q3 | `Q2` | IRLZ44NPBF, high right | same | same |
| Q2 | `Q3` | IRLZ44NPBF, low left | same | same |
| Q4 | `Q4` | IRLZ44NPBF, low right | same | same |
| R6 | `R_G1` | 10Ω, Q1 gate | `Device:R` | `R_Axial_DIN0207` |
| R8 | `R_G2` | 10Ω, Q3 gate | `Device:R` | `R_Axial_DIN0207` |
| R7 | `R_G3` | 10Ω, Q2 gate | `Device:R` | `R_Axial_DIN0207` |
| R9 | `R_G4` | 10Ω, Q4 gate | `Device:R` | `R_Axial_DIN0207` |
| R13 | `R_GS3` | 10k, Q2 gate to GND | `Device:R` | `R_Axial_DIN0207` |
| R14 | `R_GS4` | 10k, Q4 gate to GND | `Device:R` | `R_Axial_DIN0207` |

```
IR2104 pinout: 1 VCC, 2 IN, 3 /SD, 4 COM, 5 LO, 6 VS, 7 HO, 8 VB.

U4 pin1 ── +12V_VCC,  U4 pin4 ── GND,  C8 across those two at the device
U5 pin1 ── +12V_VCC,  U5 pin4 ── GND,  C11 across those two at the device

Bootstrap, left leg:
  VB_L  = D2 cathode, C9 upper plate, U4 pin8
  D2 anode ── +12V_VCC

Bootstrap, right leg:
  VB_R  = D3 cathode, C10 upper plate, U5 pin8
  D3 anode ── +12V_VCC

*** SW_L and SW_R are FOUR-WAY NODES. All four must land, or the high side is dead. ***

  SW_L  = Q1 source,  Q2 drain,  U4 pin6 (VS),  C9 lower plate
  SW_R  = Q3 source,  Q4 drain,  U5 pin6 (VS),  C10 lower plate

  (SW_L also carries R10 pin1 and J9 pin1 — see 3.6)

Gate drive:
  U4 pin7 (HO) ── HO_L ── R6 ── Q1_GATE ── Q1 gate
  U5 pin7 (HO) ── HO_R ── R8 ── Q3_GATE ── Q3 gate
  U4 pin5 (LO) ── LO_L ── R7 ── Q2_GATE ── Q2 gate
  U5 pin5 (LO) ── LO_R ── R9 ── Q4_GATE ── Q4 gate

  Q2_GATE ── R13 ── GND            (gate-to-source, low side only)
  Q4_GATE ── R14 ── GND

Rail:
  Q1 drain ── +24V_SW      Q2 source ── GND
  Q3 drain ── +24V_SW      Q4 source ── GND
```

The pinout above is the datasheet order and it is not what this guide said before. Rev 32
§8.2 and its netlist had 1 VB, 2 HO, 3 VS, 4 VCC, 5 LO, 6 COM, 7 IN, 8 SD — seven of eight
pins wrong — and this guide copied it. Corrected in the document at Rev 33. **Check it
against the datasheet yourself before you wire this block**; do not take it from here.

**VS is a wire you have to run, and forgetting it costs an evening.** Pin 6 is not connected
to anything by implication — the driver reaches the bridge only through HO, LO and VS, and
VS is the one that carries no signal, so it is the one that gets dropped. Nothing about
the schematic looks wrong afterwards.

VS is the driver's reference for its entire high side. HO drives relative to VS, and the bootstrap capacitor
sits between VB and VS. The bootstrap charges when Q2 pulls SW_L to ground — nothing else
in the design pulls that node down — so if pin 6 is not on SW_L, the driver's idea of zero
floats independently of the actual switching node.

What a missing VS looks like on the bench, because the symptoms point elsewhere:

- **VB−VS reads 2–4V** instead of 11V, ramping *linearly* at a few microamps rather than
  charging fast. Linear means leakage, not a diode conducting.
- **The diode measures fine** — anode at 12V, cathode 0.2V below it, referenced to ground.
- **SW_L measures 0V** at the physical junction, referenced to ground.
- All three are true simultaneously and appear to contradict each other. They don't: the
  capacitor's lower plate is on the driver's floating VS pin, which is not the node you
  are probing.
- HO produces nothing usable, which looks like a dead driver.

**Each gate resistor sits between two different nets** — driver side and gate side, eight
nets for four resistors. Rev 32 §11 names them that way; up to Rev 31 both pins of each
resistor were listed on one net, which drawn literally shorts it out.

Keep each gate loop — driver pin, resistor, gate, source, back to COM — drawn as a closed
compact shape on the sheet. It has to be compact on the PCB, and drawing it that way is
what reminds you.

**Pinout verified against the datasheet** — PD-94831, lead assignments box on the package
outline page: 1 GATE, 2 DRAIN, 3 SOURCE, 4 DRAIN, G-D-S from the front.

**R13 and R14 are not optional and there is no high-side pair.** A floating MOSFET gate does
not stay off: Crss couples about a ninth of any drain step onto the gate, so applying 24V
deposits roughly 2V against a 1.0V threshold minimum. Found on the bench at Rev 46 with the
drivers unfitted — the board shorted the rail to ground. Low side only, because every DC path
from +24V to ground runs through Q2 or Q4; high-side equivalents would drain the bootstrap
capacitor and buy nothing. See doc §8.4.

`Driver_FET:IR2104` **ships with no default footprint**. Assign `DIP-8_W7.62mm` yourself or
both drivers reach the netlist unassigned. **Pinout verified against IR PD60046-S**, lead
assignments for the 8-lead PDIP — the order given at the head of this block.

If you heatsink the MOSFETs to the board or a bracket rather than using clip-ons, the
library plan calls for `TO-220-3_Horizontal_TabDown` instead.

Lead 4 is the tab and it is the drain. `TO-220-3_Vertical` has three pads and no tab pad,
which is right here because these take clip-on heatsinks and the tab is not soldered. If
that ever changes you need a four-pad variant, and the drain then lands on two pads.

---

### 3.6 Snubber, drive monitor, transformer terminals and ring output

| Ref | Former name | Value | Symbol | Footprint |
|---|---|---|---|---|
| R12 | `R_MON1` | 4.7k 1/4W | `Device:R` | `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` |
| R11 | `R_MON2` | 4.7k 1/4W | `Device:R` | same as R12 |
| C13 | `C_MON` | 100nF 50V X7R | `Device:C` | same as C15 (the decoupling disc) |
| J3 | `J10` | 3-pin header | same as J1 | same as J1 — **fit** |
| R10 | `R_SNB` | 100Ω **1W** | `Device:R` | `Resistor_THT:R_Axial_DIN0414_L11.9mm_D4.5mm_P15.24mm_Horizontal` |
| C12 | `C_SNB` | 10nF 250V film | `Device:C` | `Capacitor_THT:C_Rect_L7.0mm_W*_P5.00mm` — Kemet R82, 5mm pitch; W still *verify* |
| J9 | `J7` | OSTTE020104, 3.50mm **125V** | `Connector:Screw_Terminal_01x02` | same as J2 |
| J6 | `J8` | OSTTC020162, 5.00mm **300V** | `Connector:Screw_Terminal_01x02` | **5.00mm, not 5.08mm** — see §5 |
| J7 | `J2` | OSTTC020162, 5.00mm 300V | same as J6 | same as J6 |
| J8 | `J6` | OSTTC020162, 5.00mm 300V | same as J6 | same as J6 |
| F2 | `F2` | 250mA fast, 0217.250MXP | `Device:Fuse` | `Fuse:Fuseholder_Clip-5x20mm_*` |
| FH2 | `FH2` | 649-series block | — | holder; part of F2's footprint |

```
SW_L ── R10 ── SNUB_MID ── C12 ── SW_R       (series RC across the primary)

SW_L ── R12 ── MON_A ── C13 ── MON_B ── R11 ── SW_R   (balanced 170Hz low-pass, doc §8.7)
MON_A ── J3 pin1
GND   ── J3 pin2
MON_B ── J3 pin3

SW_L ── J9 pin1                              (out to T1 primary, off-board)
SW_R ── J9 pin2

J6 pin1 ── RING_HI                           (in from T1 20W tap, off-board)
J6 pin2 ── RING_LO

RING_HI ── J7 pin1
RING_HI ── F2 pin1
F2 pin2 ── RING_HI_SB ── J8 pin1
RING_LO ── J7 pin2, J8 pin2
```

R10 is 1W as of Rev 38, not the 1/4W earlier revisions specified. Snubber dissipation is
C·V²·f = 230mW, which is 92% of a quarter-watt part. It is the same MFR-100 the trunk board
buys for its R1 (Rx05), so nothing new is ordered — but the footprint is DIN0414, not DIN0207, and it
is a noticeably larger body to place.

C12 is film, not ceramic. An X7R loses capacitance under DC bias and handles repetitive
pulse current poorly.

C13 is the opposite call, on purpose: it is the same X7R disc as the decoupling parts. The
monitor is a viewing filter whose response at 20Hz is within 1% of unity across any
capacitance the part could drift to, and the pulse-current argument does not apply to a
node fed through 9.4k. Do not "correct" it to film. R12 and R11 are the only parts that
take the switching node away from the MOSFET zone; keep them at the SW_L/SW_R end and let
the filtered nodes make the run to J3. GND in the middle of J3 for the same reason as J1.

**T1 is not a schematic part.** It is mounted off the board and wired to J9 and J6, so it
has no symbol and no footprint and wants neither. The only terminals the board knows about
are the four wires that reach J9 and J6. As of Rev 48 T1 is an Antek AS-0522 toroid used in
reverse — the OSD saturated at 20Hz, doc §9.5 — so the text note on the sheet names: the two
22V windings in series to J9 (drive), the two 115V windings in series to J6 (ring output),
static shield to GND or unconnected. Output peak is 113V rather than 141V; J6 stays the blue
300V block.

The J7 branch is not fused on this board; the trunk board fuses its own ring input at its
J102. F2 protects the switchboard branch only. Both ends of F2 sit at ring potential, so it
belongs inside the hazardous zone, not outside it because it is a fuse.

One leg only. The secondary is floating and `RING_LO` is not bonded to GND anywhere, so
opening `RING_HI` breaks the circuit but does not make the cable dead: with F2 open,
`RING_LO` stays connected to the secondary through J8. A blown F2 is not an isolation
method. Put that on the sheet as text, next to the fuse.

Five terminal blocks of two different parts: J2 and J9 are 3.50mm black at 125V, J7, J8
and J6 are 5.00mm blue at 300V. Different footprints, different pitches, different
colours. Do not let a single generic 2-pin terminal symbol with one footprint serve all
five — set the footprint per instance and check it after annotation, because this is
the case where a global edit propagates where you did not want it.

---

## 4. What this guide found

Four things in Rev 31 that drawing the schematic surfaced. All four are fixed in Rev 32 and
this guide is written against the corrected document; they are kept here because the next
board's guide should be written expecting to find the same kinds of thing.

**`C_12V_BULK` had no entry in the document's §10.2.** It was in the Rev 31 §11 netlist, in the Rev 23
change entry that added it, in Rev 32 §7.7's prose, and counted on BOM row 44 — everywhere except the
component list, which is where anyone drawing from §10 alone would look. Same pattern as
R17 on the station board and R_RST on the trunk board, found at the same stage.

**J1's value cell said 300V.** The part is the 125V OSTTE020104, as J2's note two rows down
and BOM row 57 both stated. The value column is what gets copied onto a symbol.

**T1 had no mounting decision**, and therefore no symbol, no footprint, and no terminals.
Settled at Rev 32: off-board, wired to J7 and J8. The BOM had no line for those terminals
because until Rev 32 nothing said they were needed.

**The gate resistor nets shorted the resistors.** Each read `IC1 pin2 (HO), R_G1 pin1 /
R_G1 pin2, Q1 gate` — both pins on one net. Unlikely to reach copper, since a gate resistor
is drawn in series without thinking, but the netlist section exists to be checked against a finished
schematic and a netlist that shorts four parts cannot do that job.

## 5. Before you start drawing

- **Check every pinout against its datasheet, not against the document.** Rev 32's IR2104
  pin list was wrong on seven of eight pins and every revision since §8.2 was written had
  copied it forward. Drawn against a correct KiCad symbol it would have put +12V on COM,
  ground on VS, the bootstrap cap on HO and the gate drive on VB, on both drivers — a board
  that destroys itself at power-on with no bench symptom beforehand. All five pinouts this
  board depends on are now checked against manufacturer drawings: IR2104 (PD60046-S),
  IRLZ44N (PD-94831), 74HCT02 (TI SCLS065G), SP721 (Littelfuse rev GD 07/10/24) and
  TSR 1-24120 (Traco, 2 July 2026). Only the IR2104 was ever wrong.
- **The Olimex needs a symbol drawn, and no footprint.** The library plan has it as
  off-board and socketed: the module plugs into two `Connector_Generic:Conn_01x10` sockets
  on `PinSocket_1x10_P2.54mm`, so the sockets carry the land pattern and the module itself
  needs none. Draw the symbol with pins named by GPIO number rather than header position —
  the header numbering is what makes this part easy to wire wrong. Confirm the row length
  against the board in hand; the library plan marks that *verify*.
- **Verify every GPIO against the Olimex schematic for the revision in hand.** Rev 32 §3.1 calls
  this the one assumption in the document whose failure costs a respin rather than a
  firmware edit, and it is correct to. GPIO17 must stay free.
- **`74HC02` is not `74HCT02`.** If the library only has HC, use it and override the value
  field. A symbol cannot express the difference, and the whole of §5 depends on it.
- **`Driver_FET:IR2104`, `Transistor_FET:IRLZ44N`, `Diode:UF4007` and a TSR 1-series
  symbol are all unverified.** I have not opened the chooser and cannot confirm any of
  them exist under those names. Check each before placing; where one is missing, a generic
  symbol with the value field set is fine, but the footprint and pad order then have to be
  confirmed against the datasheet rather than inherited from the symbol.
- **All four MOSFET tabs are live, and at three different potentials.** The TO-220 tab is
  the drain — datasheet lead 4, confirmed: Q1 and Q3 tabs sit at +24V, Q2's tab at `SW_L` and Q4's at `SW_R`, both
  switching the full rail at 40kHz. They cannot share an unisolated heatsink and they
  cannot touch each other. Same class of constraint as the eight MJE350 heatsinks on the
  trunk board, and worth the same silkscreen warning.
- **J9 and J6 are the transformer, and the swap is not symmetric.** These are wire-clamp
  blocks: the 3.50mm and 5.00mm pitches distinguish the parts on the board but key nothing,
  and any wire fits any block. Secondary leads onto J9 puts 141V peak on `SW_L` and `SW_R`
  against a 55V IRLZ44N rating and destroys four MOSFETs and both drivers. The reverse is
  harmless. Silkscreen T1-PRI and T1-SEC, and put them at opposite edges.
- **J7, J8 and J6 are 5.00mm, not 5.08mm.** The OSTTC020162 footprint pitch is on the index's
  blocking-layout list for exactly this reason. KiCad's terminal block footprints are
  mostly 5.08mm and the two will fit each other badly enough to be annoying and well
  enough to be missed.
- **Check the snubber capacitor's body.** C12 is specified in Rev 32 §10.8 as 10nF 100V
  ceramic and in BOM row 43 as the KEMET R82 film part at 250V, with a note saying film
  and not ceramic. The BOM is the quantity authority; take the footprint from the R82
  body, which is a boxed radial and not a disc.
- **The board has no audio and no D-Sub.** Unlike the station and trunk boards there is
  no A32 connection here, no TY-311P, and nothing on the 24V rail in the audio band. If
  you find yourself reaching for the audio blocks out of habit, the operator tone injector
  that used to live here was deleted at Rev 27 and moved to a station strip.
