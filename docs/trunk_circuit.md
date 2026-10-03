**551 Switchboard Simulator**

**Trunk Interface Circuit Design**

*Rev 5.40 — 8 Trunks, Constant-Current Loop Feed, MCP23017 I/O over 6P6C I²C and MQTT, RJ45 Trunk Lines, D-Sub25 Female Audio to the Ferrofish A32 at 48kHz, External Ring Generator*

# **1. Overview**

Each trunk interface circuit presents itself to the 551 switchboard as a Central Office trunk. The trunk board is the central office: it supplies the DC loop current the switchboard supervises, it applies ring voltage toward the switchboard on command, and it detects switchboard seizure of the trunk. Eight identical trunk circuits share one PCB.

This is the mirror image of the station board, and the inversion matters at almost every point in the design. On a station board the switchboard owns the battery and the station answers; here the trunk board owns the battery and the switchboard answers. Consequently the trunk pairs are referenced to trunk-board ground by definition, there is no off-hook relay, and there is exactly one supervisory input per trunk — loop current — rather than the station board's ring-detect input.

Ring travels one way only on a trunk. The board originates it; nothing signals inward. The operator can apply ring to a trunk by mistake and the circuit has to survive that, but it is a fault condition to be tolerated and reported, not a signalling event to be decoded, and no ring detector is fitted — see §5. Because ring is outbound and deliberate, the relay that applies it also lifts the audio transformer clear of the line, so T2 sees ring only in the accidental case and never in normal operation — see §8.1.

Control is by a single MCP23017 GPIO expander on the shared I²C bus, mastered by the same Olimex ESP32-POE-ISO that serves the station boards, exactly as specified in station circuit Rev 3.19 §9. Audio is fully balanced through a 600Ω:600Ω transformer to the Ferrofish A32 on channels 25–32, on a pair of D-Sub25 connectors that mate with the converter directly. Ring voltage is generated on a separate board and arrives as a two-wire high-voltage bus; nothing about its generation is specified here.

## **1.1 Relationship to the Station Board**

The station design (Rev 3.19) already anticipates this board in four places, and this document holds to all four:

- Audio channels 25–32 on the fourth A32 D-Sub25 pair (station §6). The three station boards take pairs 1–3; all four pairs are in use, see §9.

- Pilot comb slots 25–32, bins 704–760, 8250.00–8906.25Hz (station §8.3).

- I²C address 0x23 on the shared daisy chain (station §9.2) — one expander, exactly as assumed.

- MQTT topics under sbgame/trunk/<1-8>/ (station §9.9).

Only two amendments to the station document are needed, and both are flagged where they arise: the TVS part number differs (§6), and the trunk MQTT topics cannot share the station topic shape because a trunk has no hook to set (§11.3). The address allocation and channel budget stand unchanged.

## **1.2 Summary of Changes from Rev 4.4**

- Four trunks raised to eight. One board, one D-Sub pair, one relay per trunk. Trunk lines move to RJ45 (§8.5) and the I²C bus to a 6P6C modular connector (§10.4); audio stays on D-Sub25.

- The Wien bridge oscillator, its LM2596 13V supply, the TIP31C/TIP32C power stage and the T1 step-up transformer are all deleted. Ring voltage now arrives on a two-wire bus from a separate generator board — see §7.1.

- The LM393 comparator seizure detector, its zener clamp, threshold divider and hysteresis network are deleted and replaced by an HCPL3700M optocoupler on the loop sense resistor, matching the detection approach used on the station board — see §4.

- Raspberry Pi GPIO replaced by one MCP23017 expander on the ESP32 I²C bus. Logic rail is 3.3V throughout — see §10.

- The resistive loop feed (R1, 330Ω) is replaced by a constant-current source. This is the most consequential change in the revision and the reasoning is in §3.1: the Rev 4.4 feed resistor dissipates roughly 10W if ring is ever applied to the trunk from the switchboard side, which Rev 4.4 did not check.

- Rev 4.4's instruction to mask the seizure signal in software during ring is withdrawn. It is no longer needed: the current source and the debounce timing together separate a genuine seizure from an accidental ring without a second detector and without suppressing anything — see §4.3 and §5.

- The DPDT relay still disconnects T2 during ring, as in Rev 4.4, but now does so as a side effect of switching the ring return rather than needing a pole of its own. T2 sits between the board-side ends of the two NC contacts, so throwing either pole lifts it — see §8.1. Both functions come from pole 2 at no cost.

- L1 (47mH crosstalk isolation inductor, one per trunk) is deleted in favour of bulk decoupling on the 24V feed rail — see §12.4.

- TVS changed from P6KE120CA to P6KE150CA. The station board part would conduct on the peaks of our own ring — see §6.

- A 24V→5V switching module is added for the relay coils, with a 3.3V LDO below it, matching station §10.3. The system now runs on one common 24V battery feeding the switchboard, both board types and all loops, which makes the Mean Well LRS-35-24 undersized by 2–3× — the LRS-150-24 is specified instead. See §12.1.

- Focusrite Scarlett 18i20 references removed. Audio is the Ferrofish A32 at 48kHz, and the two-tone identification scheme is replaced by the pilot comb — see §8 and §9.

- Rev 5.1 corrected: 0x27 is allocated to this board's optional U2 rather than left unallocated, which is what station §9.2 already assumed. The BOM and §10.2 disagreed with each other in Rev 5.0 — see §10.2.

- Rev 5.1 corrected: cross-references to the generator document now point at Rev 14, and the generator's SD line is GPIO14. The I²C master pins are GPIO13 (SDA) and GPIO16 (SCL) — GPIO17 clocks the Ethernet PHY and was never available.

- Rev 5.1 corrected: the converter is referred to as the Ferrofish A32 throughout, matching station §6. Rev 5.0 called it the A32 Pro in some places and the A32 in others.

- Rev 5.1: station capacity stated consistently. Three station boards and 24 stations is the design capacity; two boards and 16 stations is the present build, which is why channels 17–24 and comb slots 17–24 are free — see §9.

- Rev 5.2: cross-references follow the generator to Rev 16 and the station document to Rev 3.7. The generator's gate-drive logic moves to 5V on a 74HCT02 with the shutdown line buffered, correcting an IR2104 threshold figure; nothing on the trunk board changes, and the ring bus it delivers is unaffected.

- Rev 5.3: fuse and fuse holder part numbers specified. F2 uses an open PC-mount block like the rest — the ring bus is exposed at J6, at the relay contacts and along the T2 primaries regardless, so a shrouded holder would protect one point on a board that is hazardous by design and is treated as such in §7.

- Rev 5.3: this board carries two of the system's five fuses and is the only one with a fuse on the ring bus.

- Rev 5.4: Q2 relay driver changed from 2N3904 to 2N2222A, matching station Rev 3.8. Confirm the TO-92 pinout against the orderable part before layout — see §10.1.

- Rev 5.5: D6 changed from SS34 to 1N5822. 1N5822, 3A / 40V, DO-201AD axial. The SS34 named through earlier revisions is an SMA/DO-214AC surface-mount part with no through-hole version. 3A is oversized against a 250-500mA fuse and deliberately so: a slow-blow fuse carries well above its rating for some time before it opens. Forward drop is unchanged at roughly 0.3-0.4V. Its drop sits ahead of the current sources, so it is the 0.7V D1 term in §3.2 that carries the compliance budget, not this one.

- Rev 5.6: TVS2 specified as the Littelfuse SP721APP — an 8-PDIP rail-clamp array with six inputs, V+ to +3.3V on pin 8 and V− to GND on pin 4, 3pF per line rather than the 1pF earlier revisions assumed. Through-hole, matching the rest of the board. Sacrificial after a mis-plug, which is the intended behaviour — see §8.6.

- Rev 5.7: the generator's 12V regulator is corrected to the Traco TSR 1-24120 in §12.1's load table. Traco carries the output voltage in the trailing digits, so the TSR 1-2412 named previously is a 1.2V part. Nothing on this board changes. The TSR 2-2450 specified here is 5.0V and is correct.

- Rev 5.8: hardware /RESET added on 6P6C positions 1 and 6, reaching pin 18 of U1 from the generator board. Adds a 10kΩ pull-up and a third TVS2 input, and requires six-conductor cords. Never assert it while ring is applied — see §10.4.

- Rev 5.9: J1 and J2 changed from the Amphenol ICC DBM25S500MN, which DigiKey does not stock, to the NorComp 182-025-213R531 — same gender, orientation, termination and gold contacts, with board locks. Six needed across the system; 16-week factory lead time despite deep distributor stock, so order together.

- Rev 5.10: cross-references follow the station document to Rev 3.13, which specifies the CTS 206-3ST for its address DIP switch. Nothing on this board changes — the trunk address remains hard-strapped with three 0Ω links and there is no switch here.

- Rev 5.11: J1 and J2 changed to the NorComp 182-025-213R561 — the same connector with integral 4-40 female screwlocks on the mating side rather than a plain threaded shell. The separate screwlock line item is deleted across the system; footprint, backset and every electrical attribute are unchanged.

- Rev 5.12 corrected: U4 is the MCP1826S-3302E/AB in TO-220-3, not SOT-223 — surface mount had no place on an otherwise through-hole board. The AMS1117-3.3 alternative is dropped, being SOT-223 only.

- Rev 5.13: RV1 deleted, matching station Rev 3.16. Eight footprints removed from this board; nothing else in the audio path changes.

- Rev 5.14: the 5V bulk capacitor is specified at 25V rather than 10V, matching station Rev 3.17. Derating only; capacitance unchanged.

- Rev 5.15: bin 768 (9000.00Hz) allocated to the operator tone — generator Rev 21 §15. Nothing on this board changes, but the T2 sweep target moves to 9000Hz, and these transformers already sit at the top of the comb.

- Rev 5.16: rail capacitors reviewed against the datasheets. Local input and output decoupling added at the LDO, which had none of its own. The 24V audio-band bulk is unchanged at one 1000µF; the station board gains the same part at Rev 3.19 for a reason specific to its resistive loop feed — see §12.6.

- Rev 5.17: J6 is the same 2-pin screw terminal as J5 rather than a separately specified 250V part. One connector type on the board, one footprint, one line in the BOM — and the creepage and separation rules for the ring bus zone are unchanged. Generator Rev 24 §10.10 makes the same change to its J2.

- Rev 5.18 corrects Rev 5.17. The terminal blocks actually on hand are the OSTTE020104 at 3.50mm and 125V — the merge assumed 5.08mm and 300V, and that assumption was doing the work. J6 reverts to a separate part, the OSTTC020162 at 5.00mm and 300V. J5 keeps the OSTTE020104, which is entirely adequate at 24V.

- Rev 5.19: D6 moves from series to a shunt clamp across +24V BRD and GND, blowing F1 on a reversed supply instead of blocking. Recovers the 0.4V of forward drop that the §3.3 compliance budget had silently omitted — see §12.5. Same change on the station and generator boards.

- Rev 5.20: schematic reference designators assigned for the five functionally named resistors — R_set, R_bias, R_LOOP, R_DET and R_pd become R11 to R15. No circuit change; this only reconciles the document's naming with what KiCad requires — see §13.

- Rev 5.21: D-Sub ground pins specified. Floating at this board with a 0Ω link footprint to board GND, unstuffed — one end grounded, the A32's. The document previously gave the pinout and said nothing about the grounds, leaving the decision to be made silently at layout — see §8.4.

- Rev 5.22: T2 specified as the Triad TY-311P on measured evidence — −5.5dB passband, flat at 9kHz, better than the SP-70 it was compared against and about $310 cheaper across 24. The datasheet band of 300Hz–3.5kHz understates the part badly — see §8.3.

- Rev 5.23: C14 deleted, all eight of them. A 100µF electrolytic at each current source, specified when L1 came out and never justified since — a current source rejects supply variation by construction, so local bulk buys nothing at either end. Removes eight parts from a strip about to be arrayed eight times, and 800µF of power-on inrush from a rail fused at 500mA — see §12.4.

- Rev 5.24: the generator's ring output becomes two separately terminated branches, and this board is fed from one of them rather than sharing a terminal with the switchboard. Generator J2 feeds this board's J6; the switchboard is fed from a new J6 on the generator, through a fuse of its own. Nothing on this board changes — the feed still arrives as a floating two-wire bus at J6, and every figure in §7 stands — but the ring bus is now a star from the generator rather than two conductors under one screw on a block specified for one. The practical difference is diagnostic: a fault on the switchboard cable can be isolated without unwiring this board's feed. Generator Rev 28 §7.6 and §10.10.

- Rev 5.24 corrects Rev 5.3. That entry said this board carries two of the system's five fuses and is the only one with a fuse on the ring bus. Both halves have stopped being true. Generator Rev 28 adds an F2 of its own on the switchboard ring branch, so the system now carries six fuses and two of them sit on the ring bus. This board still carries two, and is still the only board with a fuse on a ring bus input — the generator's fuses its output. The BOM's fuse block count moves from five to six.

- Rev 5.24: F2's margin is stated rather than left to a review note. §7.6's estimate of 20mA per trunk puts eight trunks ringing simultaneously at about 178mA, which is 71% of a 250mA rating — sitting on the 75% continuous derating a fast-acting fuse is normally held to, with only the ring cadence duty cycle left as margin. The value stands pending measurement, but it is not the comfortable choice the bare number suggests, and 500mA is the fallback — see §12.5.

- Rev 5.25: R_RST, C15, C16 and C17 added to the §13 table. Each was already required by a section of this document — the 10kΩ /RESET pull-up by §10.4 since Rev 5.8, the LDO input and output capacitors by §12.6 since Rev 5.16 — and none of them had a designator or a BOM line. A part named in prose is not a part: it does not reach the parts list, the purchase count or the schematic. The project BOM's 10kΩ count has been corrected from 34 to 42 across both board types on the same basis. Found by drawing the station schematic, which has the identical omission and fixed it at station Rev 3.25.

- Rev 5.25: the §13 entry for J3 is corrected. It said positions 2–5 wired, 1 and 6 unused, and that the jack accepts 6P4C or 6P6C plugs. Rev 5.8 put /RESET and its return on positions 1 and 6 and §10.4 has said so since; all six positions are wired and the cords must be six-conductor. A 6P4C cord leaves a working bus with no hardware reset, which is a degraded mode rather than a failure, but it is not what the table described.

- Rev 5.25: the T2 screen connection is removed from §8.2. The TY-311P specified at Rev 5.22 is a four-pin part with a primary and a secondary and nothing else, and the symbol drawn for it — switchboard:XFMR_TY-311P, against the matching footprint of the same name — has four pins. There was never a terminal to land a screen on. Station Rev 3.25 corrects the same line in its §7.3 and §12.

- Rev 5.25: the D-Sub ground link from §8.4 gets a designator, JP4, and a row in §13. The address straps become JP1–JP3 for the same reason. §8.4 specified an unstuffed 0Ω link and §10.2 three more, and an unnamed footprint is one nobody can refer to in a build note or find in a netlist.

- Rev 5.25: §12.5 and §12.6 are restored to numerical order. §12.6 was inserted between §12.4 and §12.5 at Rev 5.16 and has sat out of sequence since. Numbering and cross-references are unchanged; only the order on the page moves.

- Rev 5.26: C_C gets a reference designator, C1, and §13’s preamble is corrected from five illegal names to six. Rev 5.20 assigned R11 to R15 to the five functionally named resistors and did not notice that the same problem applies to the one functionally named capacitor — C_C is no more a valid KiCad reference than R_set is, and annotation would have renumbered it to whatever came next. C1 is free: C2, C5 and C8 to C17 are taken, and C14 is retired rather than available. It also puts the compensation capacitor next to C2 on the same strip. Found by drawing the trunk schematic guide, the same way Rev 5.25 found R_RST and the JP links.

- Rev 5.26: L1’s position is stated, in §12.4 and in §13. The row has named the part, its value and its purpose since Rev 4.4 and has never said what it connects to. Each L1 sits in series with the 24V feed to its own strip, so +24V_BRD and the strip feed are two nets with the link between them; drawn as a single net the footprint has nowhere to land. This is the same defect Rev 5.25 corrected for the D-Sub ground link and the address straps — a footprint nothing can refer to — except that here the part had a designator all along and what was missing was the connection. A designator without a net is as unbuildable as a net without a designator.

- Rev 5.27: C18 added, 100nF across TVS2 pins 8 and 4 at the device. TVS2 has been specified since Rev 5.6 with no bypass. The SP721 does not shunt to ground; it conducts the transient from the IN pin into V+, so V+ has to source that current locally or it lifts during the event — degrading the clamp and injecting the transient into the +3.3V rail that U1 and the master sit on. The layout deliberately puts TVS2 at J3, the opposite edge from U1 and the LDO, so C6 and C8 are the length of the board away and cannot serve. Same addition on the station and generator boards at their own revisions. C18 rather than the free C3 or C4: those gaps are historical and a new number says plainly that this is new, where reusing a gap invites the question of whether something was deleted.

- Rev 5.27: what is deliberately not fitted. The same datasheet note asks for bypass on both V+ and V− and for a series resistor in the supply feed. V− is pin 4 and goes straight to GND, so bypassing it is a zero-length connection with nothing to add. The series resistor belongs to the automotive load-dump and reverse-battery case the note is written for; nothing here sees a reverse battery, and series resistance in the V+ feed would raise the clamp’s dynamic impedance. Recorded so a later reader comparing the board against the datasheet sees two decisions rather than two omissions.

- Rev 5.27: the SP721 pinout is confirmed against the Littelfuse datasheet, revision GD 07/10/24 — IN on 1–3 and 5–7, V− on 4, V+ on 8. Rev 5.6 recorded V+ on pin 8 and V− on pin 4 and was right. No change; noted so the check is on the record.
- Rev 5.28: four-layer stack-up, top / In1 GND / In2 power / bottom, matching the generator board's layer order with In2 carrying +24V_BRD, +5V and +3.3V as a split pour instead of a second ground. Three rails cross all eight strips — 24V to each L1, 5V to each relay coil, 3.3V to each OC1 and its pull-up — and putting them on an inner layer leaves both outer layers to the strip signals and the ring spine. Both inner layers are kept back 3mm from the high-voltage edge by a rule area, not because 141V across the laminate is a hazard (it is not; 3mm is a surface creepage figure) but so the silkscreen boundary is true on every layer and the pour presents no capacitance to a 20Hz net carrying 40kHz residue. Details in trunk_schematic_guide §7.5.
- Rev 5.28: the GND plane supersedes two §14 layout notes. "Star the eight R_LOOP ground returns to a single point" (§12.4, §14) existed because a shared return trace has shared impedance; a plane has less impedance than any star, so the returns go straight to the plane and the star is not drawn. "A ground pour between" the converter and the transformer strip is what a plane does everywhere. Both notes are rewritten rather than deleted so the reasoning survives. The generator board went to four layers earlier and this document was not swept for the consequence at the time.
- Rev 5.28: §14's "star-ground the T2 shields" is deleted. The TY-311P has no screen — Rev 5.25 removed the screen connection from §8.2 and §13, and this line in §14 was missed. A layout note for a terminal that does not exist.
- Rev 5.29: L1 deleted outright — no footprint. Rev 4.x removed the 47mH inductor and kept eight unstuffed 0Ω link positions "in case bench measurement wants it back"; Rev 5.26 gave them a place in the netlist. Two things were wrong with that insurance. First, the footprint was an axial 0207 resistor site, which no 47mH part will ever fit, so the position did not preserve the option it existed for. Second, §12.4's own arithmetic puts crosstalk through the rail below −90dB with the inductor contributing 295Ω at 1kHz against a current source that presents ~600kΩ — the part was shown to do nothing before it was kept as a fallback. If the bench ever does show trunk-to-trunk crosstalk above the floor, the path is the rail or the ground, and the remedy is at C13 or in the return routing, not eight inductors. Consequences: the strip feed node `V_FEED` merges into +24V_BRD; §12.4, §13, §14 and §16 updated; schematic guide §3.3 and §7 updated. Eight footprints off a strip arrayed eight times.
- Rev 5.30: the MQTT topic prefix is sbgame/, not sw/, following station Rev 3.29 — changed in §1.1 and §11.3. Station §1.8 records the reasoning: sw/ was two letters that could mean several things on a shared broker, sbgame/ names the exhibit and is still one segment for wildcard subscriptions. Nothing below the prefix changes. §11.3 also gains the sbgame/trunk/<1-8>/op topic that station Rev 3.28 added to §9.10 and this document did not carry — "on" | "off", host → broker, retained, published by the host from bin 768 on each trunk's own receive channel (station §8.7) — so the two documents list the same trunk topics again. Nothing on this board changes.
- Rev 5.31: §11.3’s topic table gets the header row and key that station Rev 3.30 adds to station §9.10 — publisher → consumer and payload columns named, "host" defined as the Linux box, "host → broker" replaced by "host → any", and the circuit id format stated as station/<n> or trunk/<n>. Station §1.9 has the reasoning. The table is also now a Markdown table rather than fixed-width lines separated by blank lines, which rendered as prose. No change to any topic or payload.
- Rev 5.32: formatting only. The block diagram, every circuit and calculation listing and the §11.2 state machine — twenty-four blocks — are now fenced code blocks. They had been fixed-width text with a blank line between every row, an artefact of the docx extraction, which renders as run-together prose with the alignment lost. Same sweep as station Rev 3.31 and generator Rev 55. No word of the content changes.
- Rev 5.33: §11.4 follows station Rev 3.32. The host → ESP32 heartbeat is now sbgame/ctl/host_heartbeat (renamed again to game_heartbeat at Rev 5.34), and a reverse heartbeat sbgame/ctl/esp_heartbeat is added, published from the ESP32 main loop after the I²C poll. On this board the case it covers is a wedged main loop with a ring relay energised, which the 30-second firmware timeout cannot clear if the wedge is upstream of it; the host cannot clear it either, but it can now tell. The station §9.11 cross-reference in this section was wrong — the failure paths are in station §9.12 — and is corrected.
- Rev 5.34: §11.3 and §11.4 follow station Rev 3.33. The host’s two programs are named in the topic table — the C++ audio program publishes peer and op, the Python game program publishes ring/set and the heartbeat, which is renamed sbgame/ctl/game_heartbeat. "The host" had been used for both, and station §8.7’s Python listing invited reading the detector as part of the game program. Nothing on this board changes.
- Rev 5.35: §11 moves to control.md and mqtt.md, following station Rev 3.34. The polling and debounce rules, the state machine, the topic table and the failure handling are now specified once, in the controller’s own document and the MQTT document, with §11’s four headings kept here as pointers. The cadence constants leave §7.5 and the concurrent-ring cap leaves §7.6 for control.md §8.3 and §8.4; what stays in §7.5 and §7.6 is what this board requires of them. No change to any behaviour.
- Rev 5.37: follows station Rev 3.35 — three station boards built, operator tap on station 24. §1.1, §9, §10.2, §10.4 and the relay row in §13 no longer describe a two-board build with the third as capacity. 0x22 is a fitted board. No change on this board.
- Rev 5.38: cross-reference only. `esp32.md` is `control.md` and `ring/esp32.ino` is `control/control.ino` as of 2026-09-19 (control.md Rev 9); every reference in this document follows, the Rev 5.35 and Rev 5.36 entries included. No change on this board.
- Rev 5.39: follows station Rev 3.40 — stations 1–22, the operator tap on station board 3 strip 7 (A32 channel 23) and the audience monitor on strip 8's A32 output, channel 24, in place of the Digiface's own output. §3.3.1, §7.4, §9, §12.1, §12.1.1, §12.5 and the relay row in §13 follow the count. Trunk channels 25–32 and comb slots 25–32 are unchanged. No change on this board.
- Rev 5.40: C19 added, 100nF from U1 pin 18 (/RESET) to GND at the pin (§10.4, §13), the same part as station Rev 3.43 and for the same finding. On the bench, 2026-10-03, this board's expander came back at its power-on configuration — IODIR FF, IPOL 00, so every trunk read seized until the firmware's configuration check (control.md §6.4) restored it — when a ring relay switched, on trunks 1, 2, 7 and 8 and intermittently. Raising the 24V current limit from 0.1A to 1A changed nothing; 100nF across pin 18 and ground on both boards stopped it, with no reset in twelve board tests. R_RST and C19 make 1ms against control.md §6.2's 2ms pulse and 5ms settle; no firmware change. The present board carries C19 as a bodge; the next revision gives it a footprint. Schematic: the root sheet as annotated runs C101–C109, so C19 takes C110.

- Rev 5.36: the §11.1 pointer follows control.md Rev 2, which adds dial pulse detection on the seizure input. The 25ms release rule it quoted is gone — a dial pulse is a 25–100ms release — and the ring discriminator is now the break-to-break interval. No hardware change: the current source and the HCPL3700M already pass a dial pulse as a clean loop-current interruption (§3.2.2, §4). One measurement is added to the control.md open items rather than to §16 here, since it is a firmware threshold check: pulse timing on SEIZE_n through the real cord circuit and dial.

# **2. Functional Block Diagram (One Trunk)**

```text
                          +24V BRD
                             |
                     [ constant-current source ]   Q3/Q4, R_set, R_bias
                             |  28mA
                            R1 (100R)
                             |
                            D1 (1N4007)
                             |
          RING_HI o---------|-------- RLY1 pole 1 NO
                             +-------- RLY1 pole 1 NC ---- node A
                                                             |
  SWITCHBOARD TRUNK JACK                                     |
                                                    C2 (0.47uF, 250V)
    TIP  o----+----- RLY1 pole 1 common ---------------------+
              |                                              |
          TVS1 (P6KE150CA)                            T2 primary (+)
              |                                              |
    RING o----+----- RLY1 pole 2 common               T2 primary (-)
                            |                                |
                     RLY1 pole 2 NC ---- node B -------------+
                            |               |
                     RLY1 pole 2 NO      R_LOOP (150R) ---- GND
                            |               |
          RING_LO o-------+            R_DET (470R)
                                            |
                                       OC1 HCPL3700M (DC input)

  OC1 output ------> U1 Port A bit n   SEIZE_n     (loop current)
  U1 Port B bit n -> R4 -> Q2 -> RLY1 coil        RING_EN_n

  T2 secondary: fully floating 600R winding
    Hot  ---- R5 (1k) ---- A32 ANALOG IN (+)     [channel 24+n]
    Cold ---- R6 (1k) ---- A32 ANALOG IN (-)
    A32 ANALOG OUT (+) ---- R7 (1k) ---- T2 sec hot
    A32 ANALOG OUT (-) ---- R8 (1k) ---- T2 sec cold
```

Only TVS1 sits permanently across tip and ring at the jack. Everything else on the trunk — the DC feed, the sense resistor and the audio transformer — is behind a relay contact, and both relay poles break when ring is applied. Node A and node B are the board-side ends of the two NC contacts; T2 spans them, which is what lifts it clear of the line during ring — see §8.1.

# **3. DC Loop Feed — Constant Current Source**

## **3.1 Why Not a Series Resistor**

Rev 4.4 fed each trunk from +24V through a 330Ω 1W resistor, and analysed the ring case only as far as the 10Ω sense shunt. The feed resistor itself was never checked, and it is the part that fails.

If the operator applies ring to a trunk — which is a mistake rather than a signalling event, but a mistake that will happen on a manual board — 90V RMS appears across the trunk pair on top of our 24V feed. D1 blocks the opposing half-cycle, but on the aiding half-cycle the loop EMF is 24 + 127 = 151V peak and the current is limited only by the series resistance:

```text
  R_line = 100R:   I_pk = 285mA   I_rms = 142mA   P(R1) = 6.7W
  R_line = 0R:     I_pk = 343mA   I_rms = 172mA   P(R1) = 9.7W
```

A 1W part does not survive that, and neither does a 5W part if the key is held. Raising the resistor rating is not a fix either, because the same current also has to pass through the sense element, and the sense element has to develop enough voltage at 28mA to trip a detector while surviving ten times that during ring. Those two requirements pull in opposite directions and there is no resistor value that satisfies both.

A constant-current feed removes the conflict outright. The feed current is the same whether the trunk is idle, seized, or being rung into by mistake, so every downstream part is sized for one condition. This is also what a real line card does, and it brings two benefits beyond the thermal one: loop current no longer varies with the switchboard cord circuit resistance, and the sense threshold therefore has an unambiguous on/off rather than a range to straddle. It is also what makes the accidental-ring case survivable without any additional protection components at all — see §5.

## **3.2 Circuit**

```text
  +24V BRD ----+---------------------------- Q3 emitter (2N3906)
               |
               +-- R_set (22R, 0.5W) --+---- Q4 emitter (MJE350)
                                       |
                                       +---- Q3 base

  Q3 collector ------------------------------ Q4 base
  Q4 base ---- R_bias (10k) ---------------- GND
  Q4 base ---- C_C (1nF) ------------------- Q4 emitter     [compensation, 3.2.2]

  Q4 collector ---- R1 (100R, 1W) ---- D1 (1N4007) ---- RLY1 pole 1 NC ---- TIP
```

Q4 passes the loop current; Q3 monitors the drop across R_set and steals Q4's base drive when that drop reaches its own V_BE. Loop current is therefore V_BE(Q3) / R_set, independent of everything downstream, up to the compliance limit in §3.3.

D1 blocks reverse current during the opposing half-cycle of an accidental ring, when TIP swings to roughly −103V with respect to ground. It stands off about 127V in that condition; a 1N4007 is far beyond what is needed but costs nothing. Without it, Q4 would see its collector-emitter junction reverse-biased by the same 127V.

## **3.2.1 How It Regulates**

This is a standard topology, not a novelty. It is the same two-transistor arrangement used as the short-circuit limiter in a classic series-pass linear regulator — the current-limit transistor around the pass device — repurposed so that the limit is the operating point rather than a fault threshold. It goes by several names in the literature: two-transistor current source, current limiter, or V_BE-referenced current source. It is worth being explicit about the loop because the whole trunk design now leans on its two properties: a hard current ceiling, and a very high output impedance.

The regulating loop has one sensing element and one correcting element:

- R_set carries the whole output current, so the voltage across it is a direct measure of that current. That voltage is also, by construction, Q3's base-emitter voltage — Q3's emitter is on the rail and its base is on the far side of R_set.

- R_bias pulls Q4's base toward ground and is what turns Q4 on in the first place. It supplies 2.27mA, against the 0.28mA of base current Q4 actually needs at 28mA of collector current.

- Q3's collector sources current into Q4's base node, pulling it back up toward the rail. Since Q4 is PNP, raising its base voltage reduces its V_BE and turns it off. Q3 therefore opposes R_bias, and the surplus 1.99mA of R_bias current is exactly what Q3 has to sink to hold the balance.

The sequence at power-on: R_bias turns Q4 hard on, current climbs, the drop across R_set climbs with it, and at roughly 0.62V Q3 begins to conduct and steals base drive from Q4. The loop settles where the output current produces exactly enough drop across R_set to keep Q3 conducting just hard enough. That point is I = V_BE(Q3) / R_set, independent of what is downstream, which is the whole purpose.

Nothing about that depends on Q4's gain, on the supply voltage, or on the load — all of those are inside the feedback loop. What it does depend on is V_BE(Q3), which is why the current has the −0.3%/°C tempco and the ±10% part-to-part spread noted in §3.3, and why R_set is specified at 1%: it is the only element setting the value that the loop cannot correct for.

The loop gain is what makes the regulation tight, and it is high because Q3 is a transconductance amplifier working into a moderately high impedance:

```text
  Q3 operating point   Ic3 = 1.99 mA        gm3 = 76 mA/V
  Q4 base node         R_bias || [rpi4 + (b+1)Rset]  = 1.9 kohm
  dI -> dVbe3 -> dIc3 -> dVb4 -> dI
  loop gain T ~ 138
```

A 1% change in output current moves the R_set voltage by about 6mV, which Q3 turns into roughly 0.46mA of collector current, which moves Q4's base by nearly a volt. The loop is stiff.

That gain also multiplies the output impedance, which is the property §12.4 relies on when it claims the feed looks like an open circuit to audio:

```text
  Q4 alone, Early VA = 100V:   ro = 3.5 kohm
  with feedback:               ro x (1 + T) ~ 500 kohm
  Q4 Ccb ~ 30pF at 8.9 kHz:    Xc ~ 600 kohm
  combined at the top of the pilot comb:  ~270 kohm
```

Against a 600Ω line that is a ratio of roughly 450:1 even at the worst frequency in the band, and better than 800:1 through the voice band where the Early-effect term dominates and Ccb has not yet come in. The Early voltage is an estimate and the figure should be confirmed rather than trusted — see §16 — but there is a great deal of margin in it.

## **3.2.2 Compensation and Transient Behaviour**

This is a feedback loop with gain, so it can oscillate, and a telephone line is a reactive load with cord circuit inductance measured in henries. C_C, 1nF from Q4's base to its emitter, is the dominant-pole compensation and was missing from earlier drafts of this document. Fit the footprint and expect to tune it: 100pF to 10nF covers the useful range, and the correct value depends on the actual cord circuit, which has not been measured.

C_C also sets the recovery time when a seizure suddenly presents a load. Before the switchboard closes the loop, Q4 has no load, saturates, and sits with its full 2.27mA of base drive available, so at the instant of seizure the loop has to catch a transistor that is already fully on. An earlier draft of this section put that inrush at 227mA, from beta × I_bias. That is wrong: it is what Q4 would deliver into a zero-impedance load, but the series resistance is in the path from the first instant, and a saturated Q4 can only pass what that resistance allows.

```text
  I = (24 - Vce(sat) - Vd) / (R_set + R1 + R_LOOP)  with Q4 saturated

      R1 = 100R:   85 mA   ->  12.8 V on R_LOOP  ->  24 mA into OC1
      R1 =   0R:  134 mA   ->  20.1 V on R_LOOP  ->  40 mA into OC1

  duration with C_C = 1nF: ~2 us
```

So the real figure is 85mA, three times the steady current rather than eight, and 24mA into an optocoupler input rated 50mA average and 140mA surge. The detector is in no difficulty. The spike is worth knowing about only so that nobody finds it on a scope and assumes something is wrong, and it is far too brief for the 100ms seize debounce in §11.1 to register.

## **3.2.3 Why Not an LM317 or a Depletion FET**

Both are the obvious two-part alternatives and both were rejected for the same reason, which is worth recording so the decision is not revisited from scratch later.

| **Option** | **Why not** |
| --- | --- |
| LM317 as current source | Standard and simple — I = 1.25V / R — but it is a 40V part. Q4 stands off 136V during an accidental ring (§3.4). Also wastes 1.25V of compliance against this circuit's 0.62V. |
| Depletion MOSFET + source resistor | Two parts, and DN2540-class devices handle 400V. But V_GS(off) spreads 1.0–3.5V, so eight channels would need eight individual trims. |
| LM334 | Three-terminal and well behaved, but tops out around 10mA. Not enough for a 28mA loop feed. |
| Current regulator diode (CRD) | Simplest possible, but available currents and voltage ratings are both far below what is needed here. |
| Op-amp and pass device | Precision far beyond the requirement, and more parts than the discrete pair. |

The voltage rating is the decisive term. The pass device has to survive the full ring excursion in the accidental case, which rules out every integrated option and leaves a discrete high-voltage transistor with a discrete sense element around it. Having chosen that, the two-transistor loop costs one more small-signal transistor than a bare series resistor and gives a hard current ceiling in exchange.

## **3.2.4 What R1 Is For**

R1 is not necessary. The current source regulates perfectly well without it, and it is worth being explicit about what it buys and what it costs, because it costs the scarcest quantity in this design.

R1 does three things, and only one of them matters:

- It moves steady dissipation off Q4 and into a resistor. Real but small — 0.09W between the 100Ω and 220Ω cases.

- It halves the inrush when a seizure suddenly presents a load to a saturated Q4. Both values are benign.

- It limits the current if Q4 fails collector-to-emitter short. This is the one that earns R1 its place.

It does almost nothing for the case that actually stresses Q4. During an accidental ring the transistor is absorbing 127V of applied ring, and whether R1 drops 2.8V or 6.2V of the remainder changes peak dissipation by 2%. R1 is not thermal protection for the event that matters.

Against that it consumes compliance one-for-one, and compliance is what the design is short of, because the 551 cord circuit resistance is still unmeasured and the switchboard's own trunk supervisory relay needs adequate loop current to operate. Running out of compliance is not a graceful degradation in the way §3.3 suggests — the current falls, and it may fall below what the switchboard needs to see.

| **R1** | **Line compliance** | **Q4 at shorted jack** | **Q4 short-fault: I / R_LOOP / OC1** |
| --- | --- | --- | --- |
| 0Ω | 654Ω | 0.52W | 134mA / 2.71W / 40mA — R_LOOP destroyed, OC1 over-driven |
| 100Ω | 554Ω | 0.44W | 85mA / 1.08W / 24mA — survivable with a 2W R_LOOP |
| 220Ω | 434Ω | 0.35W | 59mA / 0.52W / 16mA — comfortable, but 120Ω less compliance |
| 330Ω | 324Ω | 0.26W | 46mA / 0.32W / 12mA — too little compliance to risk |

R1 = 100Ω is specified as the default, revised down from 220Ω. It keeps a shorted pass transistor from cascading into R_LOOP and the optocoupler, which is the only real job it has, while giving back 120Ω of compliance against the unmeasured cord circuit. R_LOOP is uprated to 2W to cover the resulting 1.08W fault case; that is the cost of the change and it is one resistor package size.

Deleting R1 entirely is the tempting simplification and should be resisted. At 0Ω a shorted Q4 puts 2.7W into a 0.5W R_LOOP and drives 40mA continuously into the optocoupler input — a single transistor failure then takes out two more parts and possibly the trunk's detection with it. The 100Ω resistor is cheap insurance against a plausible failure turning into a cascading one.

## **3.3 Component Values and Compliance**

| **Parameter** | **Value** | **Notes** |
| --- | --- | --- |
| R_set | 22Ω, 0.5W | Sets loop current |
| Loop current | 28.2mA nominal | V_BE 0.62V / 22Ω |
| Spread | 26–31mA | V_BE 0.58–0.68V across parts and temperature |
| Fixed drops at 28mA | 8.4V | R_set 0.62 + R1 2.82 + D1 0.7 + R_LOOP 4.23 |
| Compliance for line | 15.6V | Regulates up to ~554Ω of switchboard cord circuit — see §3.2.4 |
| Beyond compliance | Degrades | Behaves as a resistive feed and loop current falls. Our detector holds to 14mA (§4.2), but the switchboard's supervisory relay may not. |

*If the cord circuit measures comfortably below 400Ω, R1 can go back up to 220Ω for a cooler Q4 and a gentler fault case. If it measures above 554Ω, see §3.3.1 — and note that raising the supply rail is not among the options.*

The 2mV/°C temperature coefficient of V_BE(Q3) makes the loop current fall about 0.3% per °C. Over a realistic 25–50°C range that is 28mA down to 26mA, which no part of the design is sensitive to. Do not attempt to compensate it.

## **3.3.1 If Compliance Is Short**

An earlier draft of this document suggested raising the rail to 30V if 554Ω proved insufficient. That was written before the supply became common to the whole system and it is no longer a knob that can be turned. Three separate things block it:

- The specified LRS-150-24 adjusts over 21.6–28.8V. It cannot reach 30V at all, so this is a change of supply, not a trim.

- The switchboard runs on the same rail, and its lamps are incandescent. Filament life goes roughly as the twelfth power of voltage, so 24V to 30V is a 1.25× overdrive and cuts lamp life by about fifteen times. On vintage lamps that cannot readily be replaced, this alone settles it.

- The station boards run on the same rail too. R3 is 330Ω 2W and its short-circuit dissipation goes from 1.75W to 2.73W, past the part. Station loop current rises from 70mA to 88mA, adding about 400mA to the system budget across 22 stations and shifting every supervision margin the switchboard was designed around.

That is the real cost of the common battery decision, and it is worth stating plainly: the rail voltage stopped being a trunk board parameter the moment the switchboard was put on it. Anything that changes the rail now changes vintage equipment that was designed for 24V.

The options that remain are all local to this board:

Before listing them, one thing has to be said clearly because it rules out a whole family of apparent fixes. Compliance and the Q4-short fault current are two views of the same quantity: the total series resistance in the loop. Call everything other than R_set R_extra — currently R1 plus R_LOOP, 250Ω. Both figures fall out of it, and neither depends on where that resistance physically sits or on which part of it the detector senses across:

| **R_extra** | **Compliance at 28.2mA** | **Q4-short fault current** |
| --- | --- | --- |
| 100Ω | 704Ω | 189mA |
| 150Ω | 654Ω | 134mA |
| 250Ω (as designed) | 554Ω | 85mA |
| 300Ω | 504Ω | 72mA |

So resistance cannot be deleted to buy compliance without giving up fault limiting in exact proportion. An earlier draft of this section listed "move the sense from R_LOOP to R1" as recovering 150Ω for nothing. It does not, and the row was wrong. Deleting R_LOOP takes R_extra from 250Ω to 100Ω, which does give 704Ω of compliance — but it also takes the shorted-Q4 fault from 85mA to 189mA, putting 3.6W into R1 and 54mA into the optocoupler input, past a PC817's continuous rating. The fault-limiting argument that justified keeping R1 in §3.2.4 applies just as much to the total.

That leaves only two axes that genuinely move compliance: the loop current, and the feed voltage.

| **Option** | **Loop I** | **Compliance** | **Q4 (×8)** | **Cost** |
| --- | --- | --- | --- | --- |
| As designed | 28.2mA | 554Ω | 0.44W (3.5W) | — |
| Raise R_set to 33Ω | 18.8mA | 956Ω | 0.34W (2.7W) | One resistor, and the fault current is unchanged at 85mA. But 18.8mA may be below what the switchboard's trunk supervisory relay needs to operate — measure that first. |
| Local 48V feed for the loops only | 28.2mA | 1405Ω | 1.12W (8.9W) | An isolated 24→48V module on the trunk board. Contained — touches nothing shared, unlike the common rail — but 8.9W of board dissipation needs real heatsinking. |
| Both | 18.8mA | 2085Ω | 0.75W (6.0W) | Only if the cord circuit turns out to be extreme |

Raising R_set is the cheap one and should be tried first, subject to the supervisory relay measurement below. The 48V module is the option that actually has room in it, and it is worth noting that it does not compromise the common battery in any way that matters: the trunk board is the exchange for its own eight loops, and nothing requires those loops to sit at the same potential as the switchboard's talk battery. What it costs is heat, and 8.9W across eight TO-126 packages is the point at which the thermal design stops being incidental.

## **3.3.2 A Simplification Worth Taking Anyway**

The same reasoning suggests a change that is not a compliance fix but is a genuine tidy-up. Since only the total R_extra matters, there is no need for it to be split between a high-side R1 and a low-side R_LOOP. Merging them into a single 250Ω resistor in the ring return leg gives identical figures on every count:

```text
  compliance                554 ohm      unchanged
  Q4-short fault             85 mA       unchanged
  V_sense at 28.2mA        7.05 V        (was 4.23V across R_LOOP alone)
  R_DET = 1k -> I_opto     5.65 mA       margin 1.8x over the 3.11mA threshold
  fault: 20 mA into OC1, 1.80 W in the resistor
```

It removes one component per trunk, eight across the board, and keeps the sense node ground-referenced and at low voltage where it belongs. The cost is that the single resistor needs a 3W rating for the fault case where the split version used a 1W and a 2W part, so the choice is really one 3W package against two smaller ones — closer than it looks, since two smaller bodies also spread the heat better.

Sensing across a high-side R1 instead, which is the other way to remove a component, is the one arrangement to avoid. It works electrically — the optocoupler provides the isolation — but it moves the LED and its series resistor out of the ground-referenced logic area and into the high-voltage zone, where their common-mode potential swings with the line during ring. There is no benefit to pay for that.

*Reducing the loop current is the cheapest fix on the list and the one with the hidden dependency. The switchboard's trunk supervisory relay has a minimum operate current that nobody has measured, and if it needs 20mA or more then 18.8mA is not available regardless of what our own detector can see. Measure the relay before the resistor — it also bounds how far the current can be trimmed for any other reason.*

## **3.4 Dissipation**

Each trunk has its own current source, so the figures below are per trunk and the ×8 column is only the board aggregate for thermal planning — no single Q4 ever carries more than one trunk's 28mA. The per-trunk worst case is a dead short at that trunk's jack, which puts the whole compliance voltage across that trunk's Q4; the board worst case is all eight in that state at once:

| **Element** | **Per trunk** | **×8** | **Notes** |
| --- | --- | --- | --- |
| Q4 (MJE350) | 0.44W | 3.5W | TO-126, 300V/0.5A. Fit a heatsink — see below. |
| R1 (100Ω) | 0.08W | 0.6W | 1W part — rated for the Q4-short case, not this one |
| R_LOOP (150Ω) | 0.12W | 1.0W | 2W part — rated for the Q4-short case (§3.2.4) |
| Relay coils | 0.15W | 1.2W | On the 5V rail |
| Total loops + coils | 0.79W | ≈6.4W | Per-trunk column is one trunk block; ×8 is the board. Ventilate — see §15 |

During an accidental ring the current source holds 28mA while absorbing the extra 127V peak. Integrating over the cycle rather than estimating it: Q4 sees 3.9W at the peak of the aiding half-cycle and 1.3W averaged, which is the figure that matters thermally. A bare TO-126 in free air is around 83°C/W, so 1.3W is a 108°C rise — too much to sustain. Fit a small clip-on heatsink rather than merely leaving the footprint; at 40°C/W the rise falls to about 52°C, which the part will tolerate for as long as anyone holds a ring key. Note that R1 does not help here — it changes peak dissipation by 2% (§3.2.4).

# **4. Loop Seizure Detection**

When the switchboard seizes the trunk, DC loop current flows through R_LOOP in the ring return leg. An HCPL3700M in DC-input mode detects the resulting voltage and presents a logic level to the expander. This replaces the LM393 comparator, its threshold divider, hysteresis resistor and zener clamp from Rev 4.4 — the optocoupler supplies the threshold, the hysteresis and the isolation barrier in one part, and it is the part already stocked for the station boards.

This is the only supervisory input on the board. There is one per trunk and nothing else.

## **4.1 Circuit**

```text
  RING (jack) ---- RLY1 pole 2 NC ----+---- R_LOOP (150R, 0.5W) ---- GND
                                      |
                                 R_DET (470R)
                                      |
                                 OC1 pin 2 (DC+)
  OC1 pin 3 (DC-) ---- GND
  OC1 pins 1, 4 ---- open, no connection   (selects the DC input pair)
  OC1 pin 5 ---- GND
  OC1 pin 8 ---- +3.3V, with C5 (0.1uF) from pin 8 to pin 5, at the device
  OC1 pin 6 ---- R2 (4.7k) ---- +3.3V
  OC1 pin 6 ---- SEIZE_n ---- MCP23017 U1 Port A bit n
```

The AC and DC input pairs are alternative entry points to the same input buffer and the datasheet specifies each with the other pair open. Leaving pins 1 and 4 floating selects DC operation and bypasses the internal bridge. Note that this is the opposite pin usage from the station board ring detector, which needs the bridge for full-wave behaviour — same part number, different wiring, and worth a clear note on the schematic so the two are not confused during assembly. C5 is not optional; the datasheet requires it.

## **4.2 Sizing**

```text
  V_sense at 28mA        = 28.2mA x 150R        = 4.23V
  I_opto                 = (4.23 - 1.4) / 470   = 6.0mA
  worst-case I_TH+       = 3.11mA               -> 1.93x margin
  turn-off at I_TH- max  = 1.62mA -> V_sense 2.16V -> 14.4mA loop
```

Because the feed is a current source, the loop current is either zero or 28mA with nothing in between, so the detector never sits near its threshold and the 1.2mA of built-in hysteresis is never exercised in normal operation. The 14.4mA release point exists only to define behaviour if the current source is driven out of compliance by an unexpectedly high-resistance cord circuit; even then the detector holds up to roughly 1.2kΩ of line.

*The 1.4V figure for the HCPL3700M DC input forward drop is taken from the device's input characteristic and should be confirmed against the datasheet curve at 6mA before the board is cut. It is the one number in this section that is not either measured or set by a resistor, and R_DET is the knob if it turns out different.*

A cheaper part would work here. With the fault currents bounded by the current source there is nothing left for a threshold optocoupler to protect against, and a PC817 with R_DET at 600Ω would give the same 5mA of LED current. The HCPL3700M is specified anyway for one part number across both boards and for the guaranteed threshold limits, but with only eight fitted per board this is a smaller saving than it was and commonality probably wins.

## **4.3 Behaviour During Ring**

Two cases, and they behave differently on purpose.

When the trunk board applies ring, relay pole 2 lifts the ring conductor off R_LOOP and returns it to RING_LO instead. Ring current bypasses the sense resistor entirely, the detector reads zero throughout, and R_LOOP and OC1 see nothing. This is why ring trip is handled by cadence rather than by masking — see §7.5.

When ring is applied from the switchboard by mistake, the relay is de-energised and the ring current does flow through the DC feed path — but the current source caps it at 28mA, so the detector asserts on the aiding half-cycles and produces a 20Hz pulse train on SEIZE_n. This does not need masking, because it does not look like a seizure. The debounce in §11.1 separates the two on timing alone, and the pulse train is itself a reportable diagnostic — see §5.2.

The audio path does not disturb either case. T2 returns to node B, above R_LOOP, so the audio loop closes back through the relay to the line and does not pass through the sense resistor. R_LOOP carries loop DC only.

# **5. Accidental Ring from the Switchboard**

Ring on a trunk travels one way: the board originates it and the switchboard receives it. There is no ring-down signalling inward and no ring detector is fitted. What the design does have to do is survive the operator applying ring to a trunk by mistake, and — because it costs nothing — notice that it happened.

## **5.1 Survival**

The constant-current feed does essentially all of this work. With the loop current capped at 28mA regardless of applied voltage, an accidental ring is electrically almost indistinguishable from a normal seizure as far as every board component is concerned. Taking each part in the path:

| **Component** | **Exposure** | **Verdict** |
| --- | --- | --- |
| Q4 | Absorbs up to 137V at 28mA. ~4.1W peak, ~0.7W cycle average. | The only part under real stress. Heatsink footprint, §3.4. |
| D1 | ~127V reverse on the opposing half-cycle | 1N4007 at 1000V — no concern |
| R1, R_LOOP | 28mA, unchanged from normal | No concern. This is what the current source buys. |
| OC1 | Pulses at 20Hz at normal input current | No concern. No clamp needed. |
| C2, T2 | Only exposed here — relay is released. 90 × 600/17000 ≈ 3.2V across the primary. | No concern. C2 rated 250V and holds the rest. This is the sole case in which T2 sees ring. |
| TVS1 | 127V peak, below the 128V standoff | Stays off. Present for genuine transients. |
| RLY1 pole 1 NO | Stands off switchboard ring against a permanently live bus | See note below |

*The one combination worth thinking about is ring applied to a trunk whose relay is released. The open pole 1 NO contact then has the generator bus on one side and switchboard ring on the other, and since the generator runs continuously (§7.6) this cannot be designed away by gating it. It is bounded, though, and by less than it first appears. Both ends switch the same floating bus, so the two voltages are not merely phase-coherent — they are the same two conductors. If the switchboard applies the same leg to tip that our NO contact carries, the differential is zero; if it applies the other leg, the differential is the bus voltage itself, 141V peak. It cannot be the sum of two sources, because there is only one source. See §7.4 for the resulting standoff figure.*

No additional protection components are specified for this case. That is a deliberate result of the feed topology rather than an omission: Rev 4.4 needed a zener clamp, a series limiter and a carefully undersized shunt to survive the same event, and all three are gone because the current never gets large in the first place.

## **5.2 Reporting It**

An accidental ring produces a distinctive signature on SEIZE_n that costs nothing to recognise. Current flows only while the instantaneous loop EMF exceeds the fixed drops, which for a 127V peak ring on a 24V feed is a little over half of each cycle:

```text
  R_line = 0R:    conducts 191 deg of 360   53% duty   26.5 ms on / 23.5 ms off
  R_line = 100R:  conducts 189 deg of 360   52% duty   26.2 ms on / 23.8 ms off
  R_line = 400R:  conducts 181 deg of 360   50% duty   25.1 ms on / 24.9 ms off
```

A genuine seizure asserts continuously. An accidental ring never asserts for longer than about 27ms before dropping out. Requiring 100ms of continuous assertion before declaring a seizure therefore rejects the ring case with roughly four times margin, and the transitions that fail the test are exactly the evidence that ring is present. Firmware reports it as a fault rather than silently discarding it — an operator who has rung a trunk and is waiting for an answer that will never come is a support call otherwise, and the host is the only place that can put it on screen.

# **6. Overvoltage Protection — TVS**

A bidirectional TVS across tip and ring at each trunk jack clamps transients from the switchboard side before they reach the audio transformer or the relay contacts.

```text
  TIP  o----+---- RLY1 pole 1 common
            |
         TVS1 (P6KE150CA, bidirectional)
            |
  RING o----+---- RLY1 pole 2 common
```

The part differs deliberately from the station board, and station §4.1 will need correcting where it states the two boards use the same TVS. The station board uses a P6KE120CA, which has a 102V standoff and breaks down between 114V and 126V. On a station that is acceptable, because ring arrives only from the switchboard and mild conduction on the peaks is a protection function. On the trunk board we generate the ring ourselves, at 127V peak nominal and up to 141V peak no-load, so a 120V-class part would conduct on every cycle of every ring — loading the generator, distorting the waveform and dissipating power for no benefit.

The P6KE150CA has a 128V standoff, breaks down between 143V and 158V, and clamps at 207V. It stays out of the way of our own ring, and it also stays out of the way of an accidental 90V ring from the switchboard, which is correct: that event is already bounded by the current source and does not need clamping. What remains for the TVS is genuine transients — cord plugging, relay switching elsewhere on the frame, and whatever arrives down a long cable run.

## **6.1 Why the TVS Stays at the Jack**

TVS1 is now the only component on the trunk that is not behind a relay contact, so the obvious question is whether it should move behind them too, across the transformer primary at node A and node B. It should not, and the reasons are worth recording because the answer is the opposite of the one for T2.

- It could not clamp the largest stress in the circuit. The worst standoff anywhere on this board is across the open relay contacts — up to 165V peak (§7.4). A suppressor behind those contacts is on the wrong side of the gap it would need to protect. Only a jack-side part limits the line excursion and therefore the contact stress.

- It would be disconnected exactly when it is most needed. During the ring-on interval both poles are thrown, so a behind-the-contacts TVS is isolated from the line — and that is the interval with 127V already on the pair and the operator most likely to be plugging a cord in to answer.

- The energy that most needs absorbing originates on the switchboard side. This is the routine case, not an exotic one: every time the operator pulls a cord from a seized trunk, 28mA of loop current is broken through the cord circuit's repeat and retard coils.

```text
  L = 0.5H:   E = 0.20 mJ    unclamped peak at a 100us break =  141 V
  L = 2.0H:   E = 0.80 mJ                                    =  564 V
  L = 5.0H:   E = 1.99 mJ                                    = 1410 V

  P6KE150CA clamps at 207V; 600W for 10/1000us is roughly 0.6 J
```

The energy is three orders of magnitude inside the part's capability, so voltage rather than energy is what is being managed — but that transient appears across tip and ring at the jack, and it is generated by inductance that belongs to the switchboard, not to us. A clamp behind our contacts would sit downstream of the arc it is meant to prevent.

- Clamping degrades with series inductance. A TVS wants minimum lead length and loop area to the port it protects. Routing the clamp path through two relay contacts and the associated trace adds enough inductance to blunt it against fast transients — cord-plug arcing and static off a long cable run — which are precisely the events a slower series element like C2 does nothing about.

Behind the contacts there is also nothing left to clamp. T2's primary carries no DC because C2 blocks it, so opening the contacts produces no kick from the transformer, and the current source, R1 and D1 are not inductive. The board side of the relay stores essentially no energy.

One residual exposure is worth naming rather than protecting against. C2 is a low impedance to a fast transient — 0.34Ω at 1MHz — so a spike that the jack TVS has clamped to 207V still passes through C2 and appears across T2's primary at close to that amplitude. A 600Ω telephone transformer's primary insulation handles 207V without difficulty, and the energy behind it is sub-millijoule, so no second suppressor is specified. If a transformer is ever found failing in service rather than on the bench, a bidirectional TVS of around 200V across the primary is the fix, but do not fit one pre-emptively — it would sit across the audio path for the whole life of the board to solve a problem that has not been observed.

# **7. Ring Injection**

## **7.1 Ring Bus Interface**

Ring voltage is generated on a separate board, designed separately, and arrives at the trunk board as a two-wire bus. Nothing in this document depends on how it is generated. What the trunk board requires of it:

| **Parameter** | **Requirement** | **Notes** |
| --- | --- | --- |
| Waveform | 20Hz sine | Generator Rev 20: ESP32 LEDC PWM, 40kHz carrier, H-bridge into T1. Exactly 20.000Hz. |
| Amplitude | 90V RMS nominal | 95–100V RMS no-load per generator §14. Trunk board tolerates 85–100V RMS without change. |
| Reference | Floating pair | Confirmed: the switchboard breaks both legs too. Needs a high-impedance common-mode reference — see §7.1.1. |
| Load | (N trunks + switchboard) × I_ring | Shared source; the switchboard rings stations from the same generator — see §7.6 |
| Connector | J6, 2-pin, 250V | Physically separate from all other connectors |
| Enable | None on this board | The generator is enabled by GPIO14 (SD, via a 5V buffer) and the GPIO4 manual switch on the generator board. The trunk board has no part in it — see §7.6. |

## **7.1.1 Sharing the Generator with the Switchboard**

The same generator supplies the switchboard's own ringing, so the operator rings stations from it as well. Three consequences, none of which change the trunk board circuit but two of which change what the document previously claimed.

First, the bus is genuinely floating and stays that way. The switchboard isolates its ring supply from the line circuits with DPDT switches, breaking both legs when not ringing — which is the signature of a floating source, since a supply with one leg bonded to battery would only need single-pole keys. An earlier draft of this section predicted the opposite and it was wrong. Both ends of the system therefore treat the bus identically: two poles, both legs broken, complete isolation when idle. The original floating-pair specification stands, and pole 2's justification in §7.2 is restored in full — it keeps ring current out of the ground plane as well as lifting T2's cold end.

It also means the bus carries no load at all when nothing is ringing. Neither end presents so much as a leakage path, so the generator idles into an open circuit and its no-load output voltage — measured at 95–100V RMS, 141V peak — is what sits on the bus for most of the session. Every clearance and standoff figure on this board should be taken against that number rather than the 90V RMS nominal.

*A fully floating bus with both ends open has no defined common-mode potential, so it will drift on leakage and stray capacitance. That is not dangerous at these energies but it makes bench measurements confusing and leaves creepage stress unpredictable. Ask the generator board for a high-impedance reference — 1MΩ from each leg to ground, or a grounded centre tap if the transformer has one. That pins the common mode near zero while leaving the pair effectively floating at signal levels, and it costs two resistors.*

Second, the generator can no longer be gated on trunk ring. The operator must be able to ring a station at any moment, so the generator has to be running whenever the system is up — see §7.6.

Third, the station boards are a very light ring load and this is good news for the generator budget. A station's ring detector draws about 4mA RMS through its 20kΩ dropper (station §3.4), against the 20mA or more a real telephone ringer would take. Even with several stations being rung the switchboard side contributes little; the trunk side, loading the switchboard's own trunk circuits, remains the unknown.

## **7.2 Relay Contact Configuration**

One DPDT relay per trunk, de-energised for normal operation so that loss of power or loss of the controller cannot leave ring on a line.

```text
  NORMAL (de-energised, NC contacts):
    Pole 1 NC:  node A <---- current source, R1, D1     [DC loop feed to TIP]
    Pole 2 NC:  node B <---- R_LOOP -> GND              [loop return, sensed]
                T2 spans node A - node B                [audio in circuit]

  RINGING (energised, NO contacts):
    Pole 1 NO:  RING_HI -------------------> TIP       [ring applied]
    Pole 2 NO:  RING ----------------------> RING_LO  [ring return, bypasses R_LOOP]
                node A and node B both open             [T2 lifted clear, both ends]
```

Pole 2 does two jobs at once, which is why the transformer does not need a pole of its own. Switching the ring conductor from R_LOOP to RING_LO keeps ring current out of the sense resistor and out of the ground plane, and because T2 hangs off node B — the board side of that same contact — throwing the pole also disconnects the transformer. Pole 1 disconnects its other end. T2 therefore sits behind a double break during ring, like the station board transformer, and it costs nothing to have.

Both poles carry line voltage. Treat the entire relay except its coil pins as part of the high-voltage zone.

## **7.3 Relay Driver**

```text
  MCP23017 U1 Port B bit n ---- R4 (1k) ---- Q2 base (2N2222A)
  Q2 base ---- R_pd (10k) ---- GND                    [see note below]
  Q2 collector ---- RLY1 coil (-)
  Q2 emitter ---- GND
  RLY1 coil (+) ---- +5V
  D5 (1N4148) flyback: anode to Q2 collector, cathode to +5V
```

Base drive is (3.3 − 0.7) / 1kΩ = 2.6mA against a 29.9mA coil, a forced beta of 11.5, which saturates the 2N2222A hard. The expander sources 2.6mA comfortably against its 25mA per-pin limit, and because Q2 switches the low side of a 5V coil the 3.3V logic rail creates no level-shifting problem.

Q2 is a 2N2222A as of Rev 5.4, replacing the 2N3904, matching station Rev 3.8 §5.2. The two boards share this part deliberately. Order a TO-92 part with EBC pinout and confirm it on the datasheet for the exact orderable part, not on the generic 2N2222A number. The original 2N2222A is a TO-18 metal can and will not fit this footprint at all; TO-92 equivalents such as the onsemi PN2222A and P2N2222A are EBC, but TO-92 parts sold as 2N2222A vary between EBC, CBE and ECB by manufacturer. The footprint is committed at layout and there are 24 of these, so settle it before the boards are ordered.

*R_pd is an addition over the station board driver and it is not optional here. The MCP23017 powers up with every pin configured as an input, so Port B floats between reset and firmware configuration. On a station board a floating driver at worst closes a loop; on a trunk board it puts 90V on a line. R_pd holds Q2 off through that window and through any subsequent expander reset. The same resistor would be worth retrofitting to the station boards.*

## **7.4 Relay Selection**

CIT Relay and Switch J104D2C5VDC.15S, the same part as the station board off-hook relay. This is deliberate: station §5.5 already calls for buying all 32 in one order against a 20-week factory lead time, and 22 stations plus 8 trunks is 30 of them, 32 with the two unfitted strips on station board 3 counted as spares.

| **Parameter** | **Value** | **Against the requirement** |
| --- | --- | --- |
| Contact form | DPDT (2 Form C) | Both poles used. No spare contact. |
| Coil | 5V, 167Ω, 29.9mA, 0.15W | Same coil margin analysis as station §5.4 applies |
| Contact rating | 2A, 250VAC / 100VDC | Switches 28mA at 141V peak; open-contact standoff 165V peak — see below |
| Max switching | 500VA / 200W | Worst case 127V × 0.028A = 3.6VA |
| Contact material | AgNi, gold plated | Gold flash matters more here — trunk contacts switch tens of mA, not amps |
| Sealed | Fully | Board-washable |

The open-contact dielectric strength caveat from station §5.5 applies with more force on this board, though the figure is now firmly bounded. Because both the trunk board and the switchboard switch the same single floating bus (§7.1.1), no contact ever sees two ring sources in series:

```text
  our ring, pole 1 NC open:   node A 23.8V  vs  TIP on a bus leg +/-141V  ->  165 V pk
  idle, pole 1 NO open:       RING_HI +/-141V  vs  TIP at node A 23.8V   ->  165 V pk
  operator rings a released trunk, pole 1 NO open:
      same bus leg on tip      ->    0 V
      opposite bus leg on tip  ->  141 V pk   (the bus differential, not a sum)
```

165V peak is the worst case anywhere on the board, against an earlier working assumption of 254V. Parts in this class are normally rated 750–1000 VAC contact-to-contact, so this should be comfortable — but the distributor attribute table lists only maximum switching voltage, which is a different specification. Pull the contact-to-contact figure from the datasheet before committing.

## **7.5 Ring Cadence and Ring Trip**

The trunk board cannot detect seizure while it is ringing, because pole 2 has lifted the ring conductor off the sense resistor. Rev 4.4 had the same blind spot and papered over it by masking the seizure signal in software, which detects the answer never rather than late. Cadenced ring solves it properly and costs nothing:

The cadence itself — 2s on, 4s off, and the reasoning about answer latency — is a firmware constant and lives in control.md §8.3 as of Rev 5.35. What this board requires of it is only that the relay is released for long enough each cycle for the seizure detector to settle, which at a 100ms debounce any plausible cadence satisfies.

Releasing the relay mid-cycle interrupts up to 28mA at up to 127V, which is 3.6VA against the relay's 500VA rating. No zero-crossing logic is needed.

## **7.6 Concurrent Ring Limit and Generator Enable**

Eight trunks and the switchboard share one generator. Each ringing trunk loads it with whatever the switchboard's trunk circuit draws, and the operator can add a station ring on top at any time. Those figures are not known yet and together they decide how many trunks may ring at once.

The constraint is on the generator side. If the generator is built on the 20W tap of the OSD transformer, and the switchboard draws on the order of 20mA per trunk at 90V, then eight trunks ringing simultaneously is roughly 16VA — at the limit, with no margin for the transformer's own losses. This is worth settling early because it is cheaper to fix in firmware than in magnetics.

- Measure the ring current drawn by one trunk with the switchboard connected, at the generator's actual output voltage, and separately the current the switchboard draws when the operator rings one station. There is no standing load to subtract — both ends isolate both legs when idle — so the budget is simply the sum of whatever is ringing at that instant.

- Those two measurements now size three things rather than one: the concurrent-ring cap below, this board's F2, and the generator's F2 on the switchboard branch. The per-trunk figure sets ours, since our F2 carries every ringing trunk; the per-station figure sets the generator's, since its J6 branch carries only what the operator's ring key draws. Generator Rev 28 §7.6 sizes that one at 250mA on the same estimate this section calls unmeasured.

- Set a concurrent-ring cap in the firmware from those measurements — control.md §8.4, where the cap lives; four is the starting value there. Trunks beyond the cap queue rather than ring, with headroom for one station ring on top.

- Nothing is required of the trunk board for generator control. With the ESP32 now resident on the generator board (generator Rev 20 §3), enabling is entirely local to it — GPIO14 drives the IR2104 SD pins through a 5V buffer and GPIO4 reads a manual master-enable switch. The earlier proposal for a RING_GEN_EN line from the controller to the generator is withdrawn; there is no longer a wire to run.

What the generator enable cannot be, now that the generator is shared, is a per-call gate. Rev 5.0 originally proposed holding the bus dead unless a trunk was ringing, which would have kept 90V off eight relay contacts for most of the session. That is no longer available: the operator's ring key can be pressed at any moment and the firmware has no way to see it coming, so the generator must run whenever the system is up. Generator Rev 20 §1 states this directly: when enabled it runs continuously, and cadence for individual trunks and stations is decided elsewhere. The GPIO4 master enable is a maintenance and shutdown control, not a per-call one.

The practical consequence is that the ring bus and both relay NO contacts are live for the whole session. This is why §15 says to assume the bus is energised whenever the system is powered, and it removes the mitigation previously offered for the contact-standoff case in §5.1. It costs almost nothing in power, though: both the switchboard and the trunk board isolate both legs when not ringing, so a generator running with nothing being rung is driving an open circuit and dissipates only its own quiescent load.

# **8. Balanced Audio Interface and External Connectors**

Audio is coupled bidirectionally through a 600Ω:600Ω isolation transformer whose secondary is left fully floating, producing a balanced signal on the equipment side. The primary sits between the board-side ends of the two relay NC contacts, so it is in circuit whenever the relay is released — which is every state except the ring-on interval — and lifted clear of the line whenever ring is applied.

## **8.1 Primary Circuit**

```text
  TIP  ---- RLY1 pole 1 NC ---- node A ---- C2 (0.47uF, 250V) ---- T2 primary (+)
  RING ---- RLY1 pole 2 NC ---- node B ----------------------------- T2 primary (-)

  node B ---- R_LOOP (150R) ---- GND        [DC return and sense; audio does not
                                             pass through it - see below]
```

Placing T2 behind the contacts rather than across the jack is the right way round and it is free. Ring that the board applies deliberately — which is every incoming trunk call, repeatedly, for the life of the installation — never reaches the transformer or C2 at all. The only remaining exposure is an accidental ring from the switchboard with the relay released, and C2 covers that: its reactance at 20Hz is about 17kΩ, so the voltage across the 600Ω primary is 90 × 600/17000 ≈ 3.2V. The 250V rating on C2 is required for that case, since C2 holds the rest of the ring voltage across itself.

R_LOOP does not load the audio, which is what makes this placement free rather than a compromise. The audio loop runs TIP → pole 1 → node A → C2 → T2 → node B → pole 2 → RING and closes back through the switchboard; R_LOOP is a stub from node B to ground carrying loop DC. The only route from node A to ground is through the current source, which is close to an open circuit at audio frequencies — the same property that makes the crosstalk figure in §12.4 work.

At 0.47µF the −3dB point against the 600Ω primary is about 565Hz, which is inside the voice band and produces some low-end rolloff. If that matters on trunks, increase C2 to 2.2µF for −3dB at 120Hz, keeping the 250V rating. The trade is smaller than it was before this change, because C2 now sees ring only in the accidental case — but in that case a larger C2 puts proportionally more across the primary, about 15V rather than 3.2V, so do not increase it without checking the transformer can take that.

## **8.1.1 Switching Transient**

One artifact comes with the move and it is worth writing down rather than discovering on a scope. C2 sits at a different DC potential in the two relay states, so each transition pushes a brief current through the primary:

```text
  seized:   node A 16.5V   node B 4.2V    C2 holds 12.2V
  ringing:  node A 23.8V   node B 0.0V    C2 holds 23.8V

  step on each transition = 11.6V  ->  19mA peak into the 600R primary,
  decaying with tau = 282us
```

Node A rises during ring because the current source is left open-circuited by pole 1 and saturates toward the rail; node B falls to ground because R_LOOP no longer carries loop current. The result is a click on that trunk's audio channel at each relay operate and release — twice per ring cadence period, so roughly once every three seconds while a trunk is ringing.

This is harmless in the voice path, because nobody is connected to a trunk that is being rung. It can briefly disturb the pilot FFT on that channel, so have the host suppress pilot detection on a trunk while its ring topic reads on, plus one FFT block either side. The host already knows the ring state and the transient is two orders of magnitude shorter than the 85ms block. Do not try to fix it in hardware: a bleed resistor at node A large enough to hold the node down would be small enough to unbalance the audio.

## **8.1.2 Carrier Residue and the Pilot Comb**

Generator Rev 20 synthesises the ring waveform with a 40kHz PWM carrier through an H-bridge and T1. That carrier is not on the trunk board's problem list during normal ringing, because the relay has lifted T2 clear of the line. It is on the list during an accidental ring, when the relay is released and T2 is connected — and the numbers put it somewhere awkward.

```text
  C2 at 20 kHz-decade extremes:   17 kohm at 20 Hz   ->   8.5 ohm at 40 kHz
  T1 leakage 14.6mH at 40 kHz:    3.7 kohm referred to primary
                                  127 kohm referred to secondary
  divider onto the T2 branch:     about -46 dB

  40 kHz sampled at 48 kHz folds to 8.0 kHz
  trunk pilot comb occupies       8.250 - 8.906 kHz
```

C2 provides no protection at all here. Its whole purpose is to be a high impedance at 20Hz, which makes it 8.5Ω at 40kHz — effectively a short into T2's 600Ω primary. What does the filtering is T1's leakage inductance, which the generator design measured at 14.6mH and which presents about 127kΩ referred to the secondary, giving roughly 46dB of attenuation before the residue reaches the transformer at all.

That is probably enough, and the Ferrofish's own decimation filter should reject whatever survives long before it can fold. But 40kHz against a 48kHz sample rate lands at 8kHz, which is the doorstep of the trunk pilot comb, and a spurious tone at 8kHz is the single worst place in the spectrum for this system to acquire one. The margin is almost certainly there; the consequence of it not being there is a trunk that mis-identifies itself.

This is a measurement, not a design change. Apply ring to a trunk from the switchboard with the relay released, capture that trunk's A32 input, and look at the 8kHz region. If anything shows, the fix is on the generator board — an output filter across the secondary — not here, because nothing on the trunk board can distinguish it from signal once it has arrived. Suppressing pilot detection during ring, which §8.1.1 already asks for on transient grounds, does not help in this case: the relay is released, so the board does not know ring is present until the seizure detector reports the 20Hz pattern.

## **8.2 Receive and Transmit**

```text
  T2 secondary hot  ---- R5 (1k) ---- A32 ANALOG IN (+)
  T2 secondary cold ---- R6 (1k) ---- A32 ANALOG IN (-)

  A32 ANALOG OUT (+) ---- R7 (1k) ---- T2 secondary hot
  A32 ANALOG OUT (-) ---- R8 (1k) ---- T2 secondary cold
```

There is no third connection at the transformer. Revisions through Rev 5.24 showed a T2 screen or shield earthed to chassis; the TY-311P is a four-pin part and has no such terminal, so the line described something that could not be built. The secondary is unreferenced at this board by design, and §8.4 covers what happens to the D-Sub ground pins, which is the real grounding decision on the equipment side. RV1 is deleted as of Rev 5.13, matching station Rev 3.16 §7.4. The transmit signal is voice audio summed with the trunk's pilot tone in software before the DAC. The A32's switchable reference levels and recallable digital trim cover what the pot was for, and a dual-gang trimmer in a through-hole package is not a catalogue part — the full reasoning is in the station document. Eight footprints come off this board.

## **8.3 Transformer Selection**

Same requirement as the station board — usable response to about 9kHz, which ordinary 600Ω:600Ω telephone and line-matching transformers reach comfortably. Specialty wideband parts are not needed.

One difference is worth attention at measurement time. The trunk pilots occupy 8250.00–8906.25Hz, the top eight slots of the comb, so the trunk transformers work at the highest frequencies in the system and will show the most insertion loss. Add the operator tone at 9000.00Hz (bin 768, generator §15) and 9000Hz becomes the frequency to sweep against, not 8906.25Hz — a trunk circuit carries it whenever the operator is patched to that trunk. Standard telephone transformers begin rolling off above roughly 4kHz, so expect a few dB more here than on station 1. Sweep one part from 300Hz to 10kHz and record the loss at each of the eight trunk pilot frequencies specifically, then pre-emphasise per-trunk injection level in software to equalise received magnitudes. The ratiometric threshold in station §8.4 tolerates unequal levels, so this is refinement rather than necessity — but the trunks are where it will matter first if it matters anywhere.

Measured, 2026-08-24, Analog Discovery 3 network analyser, 10Hz to 100kHz. Triad TY-311P: passband loss about −5.5dB, flat from roughly 400Hz to 10kHz, no rolloff whatever at 9kHz, and still only −8dB at 100kHz. Low end −8.5dB at 10Hz. Driven at 200mV.

Triad SP-70, swept 2026-08-20: passband loss about −7dB, likewise flat through the comb and past the operator tone. Low end −18dB at 10Hz. Driven at 2V.

The two low-frequency figures are not comparable — 2V against 200mV is a 20dB difference in drive, and a small core at 10 to 20Hz is exactly where level starts to matter. Some or all of the SP-70's steeper low end is likely the drive level rather than the part. The passband figures are comparable and the 1.5dB difference between them tracks the winding resistances: 38/53Ω for the TY-311P against 72/92Ω for the SP-70.

The TY-311P is specified. It has lower insertion loss, it is flat where the comb and the operator tone live, and at roughly $5.67 against $20.49 it saves about $310 across the 24 needed. Its datasheet band of 300Hz to 3.5kHz understates it considerably — that specification describes a telephone application, not the limit of the part.

The low-frequency difference is close to irrelevant in circuit. C2 at 0.47µF puts a 565Hz corner ahead of the primary and contributes about 29dB of attenuation on its own at 20Hz, dominating either transformer. The one case where it becomes interesting is §9.4's option of raising C2 to 2.2µF if trunk audio sounds thin: that moves the corner to 120Hz and lets more 20Hz ring leakage into the audio path, and the SP-70 would have been rejecting more of it. Those two decisions are linked, and if C2 is ever raised the low end is worth re-measuring rather than assumed.

One sample has been swept. Sweep two or three of the production quantity before committing all 24 to boards. What matters is not the absolute loss but the spread between units at 9kHz: if they track within a dB, one detection threshold serves every channel; if they do not, that is a per-channel calibration problem in the detector rather than an analog one, and it is much cheaper to learn on the bench than after assembly.

Incidental, but worth carrying to layout: the two sweeps showed opposite phase in the passband, around 0° for one and 180° for the other, because one was connected dot-to-dot and the other reversed. Not a fault in either part. Make the footprint's dot convention explicit on the silkscreen and wire all 24 the same way — a single reversed transformer inverts one circuit's audio and nothing else, which is the kind of fault that survives a long time before anyone notices.

## **8.4 Audio Connectors — J1, J2**

Audio terminates in two D-Sub25 connectors in TASCAM analog pinout, mating with the A32 through a standard male-to-male analog loom with no breakout: J1 carries the board's eight outputs to the A32 analog input connector for channels 25–32, and J2 carries the A32's eight analog outputs back to the board. Trunk n is channel n on the connector and A32 channel 24+n. Both are female sockets — see §13.1, which corrects an earlier error in this document.

| **Board channel** | **1** | **2** | **3** | **4** | **5** | **6** | **7** | **8** |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Hot (+) | 24 | 10 | 21 | 7 | 18 | 4 | 15 | 1 |
| Cold (−) | 12 | 23 | 9 | 20 | 6 | 17 | 3 | 14 |
| Ground | 25 | 11 | 22 | 8 | 19 | 5 | 16 | 2 |

Pin 13 is not connected. The TASCAM analog and AES/EBU digital pinouts differ and breakout cables are not interchangeable; the A32 analog connectors need the analog variant. Confirm the pinout against the converter manual before making up looms — it is standard TASCAM on the analog ports, but it costs nothing to check and a mis-made 25-way loom is tedious to trace.

The eight ground pins on each connector are left floating at this board, on the assumption that they are commoned at the A32. T2 is the isolation barrier and nothing in the secondary circuit needs board ground: R5 to R8 run between the winding and the converter's pins, and board GND appears nowhere in that loop. The converter's own output stage, driving through R7 and R8, DC-references the secondary from its end.

Grounding them at both ends closes a loop that encircles the rack: board GND to the PSU, PSU to mains earth, earth to the A32 chassis, chassis to the cable ground pins, and back to the board. Eight audio channels sharing that loop is the classic way to acquire mains hum and its harmonics. Grounding at one end only is the standard answer, and the A32 is the end that should have it.

There is a real argument the other way, which is why the decision gets a footprint rather than a piece of copper. T2 has interwinding capacitance and its primary sits on a line that carries 90V RMS ring. Common-mode current through that capacitance has to return somewhere, and with the secondary unreferenced at the board it returns down the snake to the converter's input. The A32's common-mode rejection should absorb it. Ring transients are fast, and the word doing the work in that sentence is "should".

So: tie the eight ground pins of each D-Sub together at the board into a single node, and take one 0Ω link footprint from that node to board GND. Leave it unstuffed. If the system hums, it stays out. If ring events produce clicks or thumps in the captured audio, fit it and listen again. A 100Ω resistor in parallel with 10nF is the middle position — it gives transients and RF a path to ground while presenting an open circuit to 50/60Hz loop current — and the same footprint takes it.

Silkscreen the link position and what fitting it means. An unstuffed 0Ω whose purpose is undocumented gets fitted by whoever populates the next board, on the reasonable assumption that a missing part is an oversight.

This keeps the station and trunk boards on the same audio connector, as station §6 specifies, and removes the second cabling scheme that an RJ45 audio interface would have introduced.

## **8.5 Trunk Line Connectors — J7A, J7B**

The eight trunk pairs leave on two shielded RJ45 jacks, four trunks per connector, one twisted pair per trunk. RJ45 is used for nothing else on this board, and should be used for nothing else anywhere in the system: the connector type itself now signals hazardous voltage — see §8.6.

| **Pin** | **T568B colour** | **J7A** | **J7B** |
| --- | --- | --- | --- |
| 1 | white/orange | Trunk 1 TIP | Trunk 5 TIP |
| 2 | orange | Trunk 1 RING | Trunk 5 RING |
| 3 | white/green | Trunk 2 TIP | Trunk 6 TIP |
| 6 | green | Trunk 2 RING | Trunk 6 RING |
| 5 | white/blue | Trunk 3 TIP | Trunk 7 TIP |
| 4 | blue | Trunk 3 RING | Trunk 7 RING |
| 7 | white/brown | Trunk 4 TIP | Trunk 8 TIP |
| 8 | brown | Trunk 4 RING | Trunk 8 RING |

One trunk per twisted pair, striped conductor to tip. Putting each trunk on its own pair is what keeps ring voltage on one trunk from appearing differentially on another, and it is why the pairs must not be split across trunks for wiring convenience.

Crosstalk is not a concern at these frequencies, and it is worth having the numbers so the question does not get reopened. The worst case is the connector body itself, where roughly 2pF couples adjacent pins with no twisting to help:

```text
  ring, 141V pk at 20 Hz  ->  21 uV into an adjacent pair  =  -93 dB re 1V
  40 kHz carrier residue  ->  -46 dB at the secondary, -70 dB across the
                              connector  =  -116 dB total
  audio at 10 kHz         ->  -82 dB pair to pair
```

*Cable voltage rating is a real constraint here and an easy one to get wrong. Cat5e patch cords are frequently marked 30V or 72V, which is fine for Ethernet and PoE and is not fine for 141V peak ring. Specify 300V-rated cable (CM or CMR) for the trunk line runs and check the jacket print rather than assuming. The audio and I²C runs have no such requirement.*

## **8.6 Connector Classes**

Three signal classes, three connector types, one per class:

| **Connector** | **Type** | **Carries** |
| --- | --- | --- |
| J1, J2 | D-Sub25 female | Balanced audio, line level. Female sockets, mating a male-to-male loom — see §13.1. |
| J3 | 6P6C modular | I²C, 3.3V logic |
| J7A, J7B | RJ45 | Trunk tip/ring, 141V peak |
| J5, J6 | Screw terminal / 2-pin | 24V supply and the ring bus |

An earlier revision put audio, I²C and trunk lines all on RJ45, which made a mis-plug the most likely way the finished system would be destroyed — a trunk line into the I²C jack puts 141V onto SDA and SCL, shared with every station board and the master. Distinct connector types remove that failure mode at the design stage rather than managing it with labels, and no cable can now be crossed between classes and still seat.

One residual case survives and is worth naming, because it is the one people are surprised by: a 6P6C plug physically fits an RJ45 jack. It is narrower, so it lands on the middle six positions and leaves the outer two unmade. An I²C cord can therefore be pushed into J7A or J7B, where it would find trunk tip and ring conductors. The reverse is impossible — an RJ45 plug will not enter a 6P6C jack — so the hazard is one-directional and only needs one control.

- Keep the TVS array on SDA and SCL — a Littelfuse SP721APP, the same part on all three board types. It fully covers the case where the trunks involved are idle, because the current source caps each at 28mA, which a 3.3V array absorbs without difficulty. If one of those trunks happens to be ringing, 141V arrives with no current limit and the array fails short — which pulls the bus down and halts the system, rather than passing 141V to three expanders and the master. A failure that stops the game is a far better outcome than one that destroys the control system, and the array costs about 3pF against a bus with a large timing margin (§10.4). Fit C18, 100nF, across TVS2 pins 8 and 4 at the device. The SP721 does not shunt to ground — it conducts the transient from the IN pin into V+ — so V+ has to be able to source that current locally, or it lifts during the event and the clamp degrades exactly when it is working. TVS2 belongs at J3, which is the far end of the board from U1 and the LDO, so C6 and C8 are no help. Only the V+ side needs it: V− is pin 4 and goes straight to GND. The series resistor the datasheet also mentions is not fitted — that note covers automotive load-dump and reverse-battery conditions, and series resistance in the V+ feed would raise the clamp’s dynamic impedance, which is the opposite of what is wanted here.

- Colour-code cables and jacks consistently across every board — the trunk lines in one colour, the I²C cords in another. This is now a convenience rather than the primary control, which is the right place for it to be.

- Group J6, J7A and J7B at the high-voltage edge of the board with J1, J2 and J3 at the opposite edge, and mark the boundary on the silkscreen.

Keyed RJ45 jacks are no longer necessary and can be dropped. They were specified when several RJ45 connectors on this board carried different things; now RJ45 means trunk line and nothing else, anywhere in the system, and keying would not prevent the 6P6C case anyway.

# **9. Pilot Tone Assignments**

Trunks share the pilot comb with the stations and are identified by exactly the same mechanism — a station patched to a trunk must be able to name it as readily as it would name another station. The scheme, the FFT parameters, the ratiometric threshold and the detection code are all specified in station §8 and are not repeated here.

| **Trunk** | **Slot** | **FFT bin** | **Frequency** | **A32 channel** |
| --- | --- | --- | --- | --- |
| 1 | 25 | 704 | 8250.00 Hz | 25 |
| 2 | 26 | 712 | 8343.75 Hz | 26 |
| 3 | 27 | 720 | 8437.50 Hz | 27 |
| 4 | 28 | 728 | 8531.25 Hz | 28 |
| 5 | 29 | 736 | 8625.00 Hz | 29 |
| 6 | 30 | 744 | 8718.75 Hz | 30 |
| 7 | 31 | 752 | 8812.50 Hz | 31 |
| 8 | 32 | 760 | 8906.25 Hz | 32 |

All three station boards are built (station Rev 3.35), so slots 1–22 are stations, slots 23 and 24 are left allocated to the operator tap and audience monitor strips and unused (station Rev 3.40), and the trunks are at 25–32 on pair 4. Through Rev 5.36 this section described slots 17–24 as free pending the third board and warned against renumbering the trunks into them; the warning is moot now but the reason — reflashing pilot assignments on working hardware to solve a cosmetic problem — still applies to any future renumbering.

Pilot injection is continuous except during the ring-on interval, when the relay lifts T2 off the line and the trunk's pilot is absent from the pair for 2 seconds in every 6. This costs nothing in practice — a trunk that is being rung is by definition not yet patched to anything, and the pilot returns within one FFT block of the relay releasing. It does mean pilot detection on that channel should be suppressed while the trunk is ringing, which §8.1.1 asks for anyway on transient grounds.

# **10. Digital Control — MCP23017**

## **10.1 Expander Allocation**

Eight trunks need two signals each — seizure in, ring enable out — which is exactly sixteen pins and therefore exactly one expander. The trunk board fits the same single-expander pattern as a station board, and for the same reason: one input and one output per circuit.

| **Device** | **Pins** | **Function** |
| --- | --- | --- |
| U1 (0x23) | Port A 0–7 | SEIZE_1..8 — from OC1. External pull-ups fitted (R2), so leave GPPU off. Set IPOL to invert the active-low sense. |
| U1 (0x23) | Port B 0–7 | RING_EN_1..8 — outputs, drive high to energise the ring relay |
| U2 | — | Not fitted. 0x27 is reserved for it, matching station §9.2. Leave the footprint, the address strap and the decoupling for per-trunk status LEDs if they are ever wanted — see §10.2. |

U1 is exactly full, with the same consequence station §9.1 notes: any additional per-trunk signal requires U2 to be stuffed, which consumes a second I²C address. Two candidates might arise later — a ring bus current monitor to confirm the generator is live, and per-trunk status LEDs — and both would fit comfortably on U2 if it is ever wanted. Leave the footprint.

## **10.2 Addressing**

0x23, matching generator Rev 20 §2.2 and station §9.2. Nothing about the address plan changes.

| **Address** | **Board** | **Function** |
| --- | --- | --- |
| 0x20 – 0x21 | Station boards 1–2 | Mandatory expander, one per board |
| 0x22 | Station board 3 | Mandatory expander |
| 0x23 | Trunk board | U1 — seizure sense and ring enable |
| 0x24 – 0x26 | Station boards 1–3 | Optional LED expanders |
| 0x27 | Trunk board | U2 — optional, unstuffed. Reserved on the same basis as the station boards' 0x24–0x26. |

Generator Rev 20 §2.2 and station Rev 3.15 §9.2 both treat the trunk board address as fixed, in contrast to the DIP-strapped station boards, and that is the right call — there is only one trunk board and nothing to distinguish. Hard-strap A0 and A1 high and A2 low. Fit the straps as 0Ω link footprints rather than solid copper so the address can be moved without cutting the board; the links cost nothing and a wrong address is otherwise a scalpel job.

*The startup scan is driven from the configured station board count (control.md §4.2). With three station boards built the list is 0x20, 0x21, 0x22 and 0x23. Generator Rev 13 hard-coded 0x20–0x23 when only two station boards existed, which logged a phantom missing device at 0x22 on every boot; the configured count is what keeps that from recurring if a board is ever pulled.*

## **10.3 Power-On and Reset State**

The MCP23017 comes out of reset with IODIR = 0xFF, every pin an input. Port B therefore floats until firmware configures it, and on this board a floating Port B bit means an undriven ring relay coil. R_pd (§7.3) defines the state through that window. Tie the RESET pin high through 10kΩ rather than leaving it floating, and bring it to a header so the ESP32 can assert a hardware reset if the bus ever needs recovering — a wedged expander holding a ring relay closed is the one failure on this board that a firmware watchdog alone cannot clear.

## **10.4 I²C Bus — J3, RJ11**

The I²C master is the Olimex ESP32-POE-ISO on the ring generator board (generator Rev 20 §3). It reaches the bus on GPIO13 (SDA) and GPIO16 (SCL); the GPIO16/GPIO17 pair named in earlier revisions was wrong, because GPIO17 clocks the Ethernet PHY — generator Rev 14 §3.1. The bus daisy-chains from there through the station boards and terminates here. The generator board carries one connector, each station board two, and the trunk board — last in the chain — one. All three station boards are built and in the chain ahead of this board.

The bus uses a 6P6C modular connector, distinct from the RJ45 used for trunk lines and the D-Sub25 used for audio. Three signal classes, three connector types, and no way to cross them with a cable that seats properly.

```text
  ring generator ---[RJ11]--- station 1 ---[RJ11]--- station 2 ---[RJ11]---[station 3]---[RJ11]--- TRUNK
   (master, 1x)              (2x, thru)          (2x, thru)      (capacity)       (1x, end)

   J3, 6P6C, ~600mm total bus length
```

| **Position** | **Signal** | **Pair** | **Connection on this board** |
| --- | --- | --- | --- |
| 1 | — | 3 (1–6) | /RESET — expander hardware reset from the generator board, paired with GND at position 6 |
| 2 | SCL | 2 (2–5) | U1 pin 12 |
| 3 | GND | 1 (3–4) | Board ground — SDA return |
| 4 | SDA | 1 (3–4) | U1 pin 13 |
| 5 | GND | 2 (2–5) | Board ground — SCL return |
| 6 | — | 3 (1–6) | /RESET return — paired with /RESET at position 1 |

Each signal has its return on its own concentric pair — SCL with the ground at position 5, SDA with the ground at position 3, /RESET with the ground at position 6 — which is the same pair discipline the RJ45 arrangement used. Positions 1 and 6 are unused, so a standard four-conductor cord occupying positions 2 to 5 fits exactly.

Within that constraint the ordering still matters, and it is worth setting down why the grounds are interleaved rather than grouped. Putting SCL and SDA on adjacent conductors would couple the clock edge straight into the data line:

```text
  glitch on SDA from an SCL edge  =  Cc / (Cc + Cn) x 3.3V

    SCL and SDA adjacent      Cc ~ 25 pF   ->  0.66 V
    a ground conductor between Cc ~  5 pF   ->  0.16 V

  MCP23017 at 3.3V: VIH = 2.64 V
```

A 0.66V dip takes SDA to exactly VIH, and a false edge on SDA while SCL is high is read as a START or STOP condition — not a corrupted byte but a corrupted transaction, and on this board a corrupted transaction can energise a ring relay. Interleaving the grounds puts a grounded conductor between clock and data and drops the coupling by around 12dB for free. Prefer round twisted six-conductor cable over flat satin cord for the same reason, though the pinout works with either.

*Use straight-through cords, and verify rather than assume. Standard voice line cords are wired reversed end to end — position 2 lands on 5, 3 on 4 — which with this pinout shorts both SCL and SDA to ground. That is a harmless failure: the pull-ups source about 1.5mA into ground, nothing is damaged, and the bus is simply dead, which the generator's startup scan reports immediately as every device missing. But reversed cords are the commonly stocked kind, so crimp the cords for this system deliberately and label them.*

*Generator Rev 20 §4.2 and station Rev 3.15 §9.4 now carry this same pinout. The three documents agree and no further change is outstanding; the RJ45 I²C arrangement of the earlier revisions is gone from all of them.*

*Fit no pull-ups on this board. Generator Rev 20 §4.4 places the single 2.2kΩ pair on the generator board and states that station and trunk boards must not fit their own. R9 and R10 stay in the BOM as unstuffed footprints only, and should be marked DO NOT FIT on the silkscreen rather than merely left empty — a bare footprint invites someone to populate it.*

There is no INT line, which is correct because this board polls rather than using interrupt-on-change (station §9.5). The reason is sharper here than on a station board: during an accidental ring the seizure input produces a 20Hz pulse train, so one trunk being rung into would generate 40 interrupts per second for something that is not even a state change. Polling Port A of three expanders at 200Hz — four with the third station board fitted — costs roughly 6% of a 100kHz bus and gives the debounce in §11.1 the sample density it needs.

The single expander here adds about 10pF. With 2.2kΩ pull-ups and roughly 50pF of total bus capacitance the rise time is about 94ns against the 1µs I²C budget, so at 600mm no bus buffer is needed and the P82B96 footprint recommended in earlier revisions of this document can be dropped.

Positions 1 and 6 of the 6P6C carry /RESET and its return, from GPIO5 on the generator board to pin 18 of U1. Generator §4.7 owns the design and station §9.4 covers what it means for a board that consumes it; two points are specific to this board.

Fit a 10kΩ pull-up to +3.3V on /RESET here as on the station boards, and note that this is the opposite of the DO NOT FIT rule for the I²C pull-ups. The reasoning is in station §9.4: a static line driven by a CMOS output does not care about three pull-ups in parallel, and an unplugged board must not leave pin 18 floating. /RESET also takes a third input of TVS2.

The consequence to weigh is sharper here than on a station board. A reset returns the expander to IODIR = 0xFF, which releases every ring relay — R_pd (§7.3) is what holds the drivers off through the window, and that argument is unchanged. But releasing a ring relay mid-cadence opens the contacts at an arbitrary point in the 20Hz waveform rather than at a cadence boundary, which is the click §9.5 quantifies and the switching discipline §7.6 exists to avoid. Never assert /RESET while ring is applied. At startup, and on a detected bus fault with ring already inhibited, it is exactly the right tool.

Filter /RESET at U1: C19, 100nF from pin 18 to GND, as close to the pin as the layout allows (Rev 5.40). The line runs the length of the bus cord and every board with only 10kΩ pull-ups holding it up, and the MCP23017 resets on a pulse of about a microsecond. Before C19 a ring relay switching on this board reset the expander intermittently — every trunk then reads seized, since IPOL is cleared — and with it fitted not once. With R_RST it is a 1ms time constant, inside control.md §6.2's 2ms pulse and 5ms settle.

# **11. Firmware Behaviour**

Moved to control.md at Rev 5.35. The four subsections are kept as headings so that cross-references land; each points at where its content now lives.

## **11.1 Polling and Debounce**

control.md §6.3, §8.1 and §8.2. Port A polled at 200Hz; seized after 100ms continuous assertion; a release of 25–100ms inside a seizure is a dial pulse and is counted, a release of 250ms or more is the trunk releasing; accidental ring is recognised by successive breaks 60ms or less apart. The dial pulse timing that sets those windows is tabled in control.md §8.2. Nothing on this board changes for dialling — the seizure detector of §4 sees a dial pulse as loop current stopping, which it already reports.

## **11.2 Trunk State Machine**

control.md §8.2. IDLE, RINGING, SEIZED, RING_ON_TRUNK, with RING_ON_TRUNK a report rather than a mode.

## **11.3 MQTT Topics**

mqtt.md §4 to §6. The trunk topics are not the station topics with a different noun — a trunk is commanded to ring and reports seizure, a station is commanded off-hook and reports ring — and mqtt.md §4 says so. This board’s own messages are seize, ring (echoed relay state) and fault from the ESP32; peer and op from the audio program; ring/set from the game program.

## **11.4 Failure Handling**

mqtt.md §8 for the protocol and control.md §10 for the actions. The three guards that matter on this board — relays released on broker loss and on two missed game heartbeats, and the 30s hard ring timeout that nothing on the host can override — are all there. The reason they matter more here than on a station board is unchanged: a relay left closed on a station holds a loop; a relay left closed on a trunk puts 90V on a switchboard line.

# **12. Power**

## **12.1 Supply — One Common Battery**

A single 24V supply feeds everything: the trunk loops, the trunk and station board rails, and the switchboard itself. This is the right decision and it is what a real exchange does — common battery is the defining feature of the architecture the 551 was built for. It also disposes of the labelling hazard that station §10.1 was written around, since there are no longer two 24V supplies to confuse.

It changes the sizing question completely, though, and the LRS-35-24 is not adequate. The reason is not the trunk board — it is that the station loop current is now drawn from this supply. Station §5.2 puts each off-hook station at 60–70mA through R3, and the switchboard is what feeds that, so the station loops dominate everything else on the board side. The system as built (station Rev 3.40) is 22 stations on three boards plus 8 trunks, 30 loops; the 24-circuit column below is the earlier two-board build and is kept because the supply choice was argued from both:

| **Load** | **24 circuits** | **32 circuits** | **Notes** |
| --- | --- | --- | --- |
| Station loops | 1120mA | 1680mA | 70mA each, all off-hook. 16 or 24 stations. Station §5.2. |
| 8 trunk loops | 226mA | 226mA | 28mA each, fed by the trunk board. Unchanged. |
| Station board rails | 142mA | 213mA | 71mA per board into its DC-DC module |
| Trunk board rails | 65mA | 65mA | Relay coils and logic, excluding the loop feeds above |
| Subtotal, known | 1553mA | 2184mA | 37.3W / 52.4W |
| Switchboard lamps, relays | UNKNOWN | UNKNOWN | Estimate 500–1500mA. Must be measured — see below. |
| Ring generator input | UNKNOWN | UNKNOWN | H-bridge into T1 plus a TSR 1-24120 for the gate drivers. Scales with concurrent ring load; near quiescent when nothing is ringing. The ESP32 is PoE-powered and draws nothing from this rail. |
| Realistic total | 2.4–4.1A | 3.0–4.7A | 56–97W / 72–112W |

Specify the Mean Well LRS-150-24: 24V at 6.5A (156W), 89% efficient, output adjustable over 21.6–28.8V, 159 × 97 × 30mm. Dropping from 32 circuits to 24 saves 631mA, which is real but does not change the answer, because the two unmeasured terms dominate the uncertainty either way:

| **Supply** | **24 circuits** | **32 circuits** | **Verdict** |
| --- | --- | --- | --- |
| LRS-35-24 (1.5A) | 157–270% | 199–312% | Undersized by 2–3× |
| LRS-100-24 (4.5A) | 52–90% | 66–104% | Adequate at 24 circuits only if the switchboard is modest; fails at 32 |
| LRS-150-24 (6.5A) | 36–62% | 46–72% | Correct. Covers both build stages. |

The LRS-100-24 is tempting at 24 circuits and should still be declined. At the top of the estimate it runs 90% loaded, which is no place to be for an enclosed convection-cooled supply in a warm rack — the LRS series derates above 50°C — and it has no room at all for a third station board. Since the system is explicitly built out in stages (station §1), buying the 150 now avoids buying a supply twice for the sake of a few dollars.

*Two differences from the LRS-35 worth catching at build time. The LRS-150 has an AC input select switch for 115V or 230V rather than the LRS-35's universal input — set it before first power-on, because getting it wrong destroys the supply. And the adjustment range is wide: set the output to 24.0V at the terminals under load rather than accepting the factory setting, since the relay coil margin in station §5.4 is calculated against the 5V rail at its lower limit and everything upstream feeds into it.*

Incandescent switchboard lamps are the other reason to oversize. Cold filament resistance is roughly a tenth of hot, so a bank of lamps lighting at once draws a large brief inrush, and the LRS series current-limits into hiccup mode rather than riding it out. A supply sized close to the steady-state figure can fail to start the system rather than merely sagging under it.

Measure the switchboard's draw before ordering — idle, with a typical number of lamps lit, and with every lamp lit. It is the largest guess in the table and the one that decides whether the margin above is real.

*One consequence of putting the ring generator on the common battery: its input current is modulated at 20Hz by the ring waveform, and it steps by several hundred milliamps each time the cadence turns on and off. That modulation appears across the supply's output impedance and therefore on every station and trunk loop. It is unlikely to matter — 20Hz is below the voice band and below the pilot comb, and a 0.5V dip on 24V moves a 70mA loop by about 2%, nowhere near a supervision threshold — but it is the one load on the system that is neither steady nor small. Give the generator its own pair from the PSU terminals in the star, and put generous bulk capacitance at its input rather than relying on the shared rail.*

## **12.1.1 What This Changes for the Station Boards**

Station §10.1 draws a hard distinction between the loop supply and the board supply and says the two must never be tied together. With one common battery they are tied, at the PSU terminals, by design. That section needs revisiting, and the revision is narrower than it first looks.

The hazard station §10.1 was actually guarding against is deriving board power from tip and ring, which would put a standing load on the loop and read as a supervision fault. That remains prohibited and nothing here changes it. What the section additionally recommended — an isolated DC-DC module so board ground and battery ground do not become common — can be relaxed to the non-isolated Traco or Murata part already specified, on one condition: the 24V distribution must be a true star from the PSU terminals, with a separate pair to the switchboard and a separate pair to each interface board.

The reason isolation was wanted was to keep the boards' logic ground off a conductor carrying loop current. Star wiring achieves the same thing directly. Daisy-chaining does not: 1.5A of station loop current at 22 stations returning through a shared conductor would put tens of millivolts of drop between one board's ground and another's, and that offset lands on the I²C bus reference shared by every expander. This was a minor concern at 300mA and is a real one at an amp.

## **12.2 Rail Budget**

| **Rail** | **Load** | **Notes** |
| --- | --- | --- |
| +24V BRD | ≈ 290mA | 225mA of loop feed (8 × 28mA) plus 64mA into the DC-DC |
| +5V | ≈ 278mA | Relay coils 8 × 29.9mA = 239mA all-on, plus 39mA of LDO input |
| +3.3V | ≈ 39mA | 8 × HCPL3700M at 4mA, one MCP23017, output pull-ups ~6mA |
| Board total | ≈ 6.9W | Of which ≈ 5.1W is dissipated on the board in the loop feeds |

Size for the all-on case. Eight trunks seized simultaneously is not a pathological condition on a switchboard — it is a busy Saturday — and a rail that sags under it presents as intermittent loop-current faults that are very hard to diagnose from the software side.

The trunk board is a small fraction of the system load — about 290mA of the 2.4–4.1A total in §12.1, and it does not change with the station count. It is not what sizes the supply; the station loops and the switchboard are.

## **12.3 Converter Selection**

Traco TSR 2-2450 or Murata OKI-78SR-5/1.5-W36-C, SIP-3 in the 7805 footprint, as on the station boards. Both are 36V-rated, which is the specification that matters — prefer them over 28V-maximum modules such as the Recom R-78E5.0, since a 24V rack supply sits within a few volts of 28V before tolerance and load dump are accounted for.

Derive 3.3V with an LDO from the 5V rail rather than a second switcher. The load is 39mA at a 1.7V drop, so dissipation is 66mW and almost any small LDO will do. The part is the MCP1826S-3302E/AB in TO-220-3, through-hole; station §10.3 explains why not SOT-223.

Keep total output capacitance on the 5V rail inside the module's rating. The 220µF bulk is specified at 25V as of Rev 5.14, matching station §10.4 — 10V on a 5V rail is only 2:1 derating. 10µF local to each relay coil plus a single 220µF bulk at the converter output is about 300µF, which is inside the modules above — but check it against the datasheet of whichever is actually chosen. Exceeding it holds the output down during soft-start until the module current-limits and retries, and the symptom is a board that fails to start intermittently with nothing obviously wrong.

## **12.4 Audio-Band Rail Impedance — Replacing L1**

Rev 4.4 fitted a 47mH series inductor per trunk to stop audio from one trunk coupling into another through the shared 24V supply, on the model of the 551's own retard coils on cord circuit feeds. The intent was right but the part does not do the work, and the arithmetic shows why.

At 1kHz a well-bypassed 24V rail presents on the order of 10mΩ. Audio on one trunk's tip reaches that rail through the current source and R1, which together are a very high impedance — the current source in particular is essentially an open circuit to signal, which a resistive feed was not. Crosstalk to the rail is therefore below −90dB before any inductor is considered, and 47mH contributes only 5.9Ω at 20Hz and 295Ω at 1kHz against that. Eight bulky inductors buy nothing.

What actually matters is that the rail is genuinely low-impedance across the audio band, and that the eight sense-resistor returns do not share ground impedance:

- 1000µF electrolytic plus 100nF film at the board 24V input. Nothing local to each trunk.

C14, a 100µF electrolytic at each current source, is deleted as of Rev 5.23. It was specified alongside the 1000µF when L1 came out, and it was never asked what it was for. The answer is very little. A current source rejects supply variation by construction — that is its defining property — so the usual reason for local bulk, holding a rail stiff for a load that disturbs it, applies at neither end: this load does not disturb the rail and does not care if the rail is disturbed. There is no fast transient on 24V either. The relay coils are on the 5V rail and the ring contacts switch the ring bus; the only 24V event is a 28mA step at loop closure, on a switchhook timescale.

Nor is it needed for the crosstalk argument above, which turns on the current source presenting roughly 600kΩ to signal and puts the figure below −90dB before any bypassing is considered. C14 was belt-and-braces on a problem already solved by the topology.

Deleting it has a benefit beyond the eight parts. Eight 100µF plus the 1000µF and the 47µF is about 1.85mF of capacitance for the LRS-150-24 to charge through F1 at power-on — roughly 0.3A²s of I²t against a 500mA slow-blow, which is uncomfortably close for something that happens every time the rack is switched on. Removing 800µF takes most of that away. A local ceramic was considered as a middle course and rejected for the same reason as the electrolytic: a decoupling capacitor with nothing to decouple is a part fitted out of habit.

The station board never had the equivalent and does not need one. Its per-station capacitors are the 10µF relay-coil reservoirs on the 5V rail, which serve a real inductive load, and its single 1000µF at the 24V input earns its place because a 330Ω resistive feed does put audio-band current into the shared rail. Station §10.4 records a related correction — 100µF per relay coil reduced to 10µF because a switching module has a maximum output capacitance. Distributed bulk specified once and never re-examined is a recurring theme in this design and worth watching for.

- The eight R_LOOP ground returns must not share trace impedance. Audio does not pass through R_LOOP (§8.1), so this is a second-order path — but it is the one that remains after the rail is bypassed. Through Rev 5.27 this was written as "star the returns to a single point"; as of Rev 5.28 the board has a solid In1 ground plane, whose impedance is below any star's, and each R_LOOP returns to the plane by its own via. The requirement is unchanged, the star is not drawn.

- No L1 footprint. Through Rev 5.28 eight unstuffed 0Ω link positions were kept in series with each strip's 24V feed "in case bench measurement wants the inductor back." Deleted at Rev 5.29: the site was a 0207 axial, which cannot take a 47mH part, and the arithmetic above already shows the inductor doing nothing against a current source's output impedance. If crosstalk is measured above the floor, look at C13 and the ground returns; an inductor in the feed is not the fix and the footprint was not a way to fit one. Each strip's feed now connects directly to +24V_BRD.

## **12.5 Input Protection**

- F1, 500mA slow-blow on the 24V board input. The board draws about 290mA. Per-board fusing matters more than it did: the common supply can deliver 6.5A into a fault, where the LRS-35-24 would have current-limited at 1.5A and taken the whole system down instead.

- F2, 250mA fast-acting 250V on the ring bus input at J6. Review the value once the ring current per trunk is measured (§7.6). §7.6's estimate of 20mA per trunk puts eight trunks ringing at about 178mA, or 71% of the rating — on the 75% continuous derating limit for a fast-acting part, with the cadence duty cycle as the only remaining margin. If the measured per-trunk current exceeds the estimate, F2 goes to 500mA. The generator now carries a second ring bus fuse of its own on the switchboard branch (generator Rev 28 §7.6); this one still protects only what arrives here.

- D6, 1N5822 Schottky for reverse polarity on the 24V input. A screw terminal on a 24V bus will eventually be connected backwards. Fit D6 as a shunt clamp, not in series. Cathode to +24V BRD, anode to GND, reverse-biased and carrying nothing in normal operation. If the supply is connected backwards the diode conducts hard and blows F1; the board sits at about −0.5V until it opens, which everything on it survives. F1 must be upstream of D6 for this to work — J5, then F1, then the D6 clamp, then the board.

The fuse does open, and it is worth showing rather than assuming. The LRS-150-24 sources 6.5A before its own limiting acts, so a 500mA slow-blow sees roughly ten times its rating and opens in a few milliseconds. The 1N5822 is rated 80A non-repetitive for 8.3ms, an I²t of roughly 26A²s against the 0.25A²s of 5A for 10ms — two orders of magnitude of margin. If the diode does fail, it fails short, which is a dead short across a reversed supply and opens the fuse anyway. Both outcomes end the same way.

The reason to prefer the clamp over a series diode is compliance, and on this board it is not a small point. A series Schottky drops about 0.4V at the 250mA this board draws, and that 0.4V comes off the top of the loop feed — the one quantity §3.3 has already had to fight for. The clamp costs nothing in normal operation because it carries nothing.

It also makes the §3.3 budget honest. That table lists four fixed drops — R_set, R1, D1 and R_LOOP — and does not include D6, so the 15.6V of compliance and the 554Ω of cord circuit were computed from a full 24V at Q3's emitter. With a series D6 that was optimistic by roughly 0.4V and the real figures were nearer 15.2V and 540Ω. With the clamp, the numbers as printed are correct. This change does not add compliance so much as stop the document overstating it.

- 47µF at 50V plus 100nF at the DC-DC input pins, close to the pins, in addition to the 1000µF audio-band bulk above. The input loop of a buck converter is the noisiest current path on the board.

- Distribute the 24V bus as a star from the PSU terminals — a separate pair to the switchboard and a separate pair to each interface board. This is now a requirement rather than good practice: it is what replaces the isolated DC-DC that station §10.1 asked for, and the current it is keeping out of the logic grounds is 1.5A of station loop current. See §12.1.1.

## **12.6 Rail Capacitors — Review Findings**

Reviewed against the module and regulator datasheets. The 24V audio-band bulk in §12.4 stands as specified; two smaller things do not.

The 47µF at the DC-DC input is required rather than advisory. Traco's TSR 2 datasheet calls for an input capacitor of 22µF/50V above 20VDC input, to prevent damage at power-on, and again where the input is switched electromechanically — both apply here. 47µF clears it and the 100nF handles what the electrolytic cannot.

Confirm the module's maximum capacitive load before committing the 220µF at the 5V output. Exceeding it causes a start-up failure rather than a visible instability, so the symptom is a board that will not come up and gives no clue why.

The omission is at the LDO, and it is the same on both board types: the 3.3V rail has bulk at U4's output but nothing at its input pin. The 220µF sits at the converter output with trace inductance in between. Fit 10µF plus 100nF at U4's input, and add a 100nF ceramic at its output alongside the existing 10µF — an aluminium electrolytic alone has poor impedance exactly where the regulator's loop needs it. One more 10µF and two more 100nF, both already on the board in quantity.

The 1000µF stays at one on this board. Station Rev 3.19 §10.7 adds the same part there for a reason that does not apply here — a 330Ω resistive feed puts audio-band current into the shared rail, where this board's current sources present roughly 600kΩ and keep it out. That asymmetry is worth understanding rather than standardising away: the two boards need the same capacitor for opposite reasons, and only one of them needs it badly.

# **13. Bill of Materials**

Per trunk, ×8 on the board, unless marked otherwise. The Designator column carries this document's functional names. Six of them — R_set, R_bias, R_LOOP, R_DET, R_pd and C_C — are not valid KiCad reference designators. The schematic assigns R11 to R15 to the five resistors respectively, continuing past the R1–R10 already used here, and C1 to C_C, which is free: C2, C5 and C8 to C17 are taken and C14 is retired. R_RST on the root sheet takes R11 on that sheet. Keep the functional name in a Function field on each symbol so the schematic, the PCB and this document remain reconcilable after annotation renumbers everything.

| **Designator** | **Value / Part** | **Description / Notes** |
| --- | --- | --- |
| TVS1 ×8 | P6KE150CA | Bidirectional TVS, 128V standoff. NOT the station board part — see §6. |
| Q4 ×8 | MJE350 (PNP, TO-126) | Current source pass transistor, 300V/0.5A. Fit a clip-on heatsink, ~40°C/W — see §3.4. |
| Q3 ×8 | 2N3906 | Current source sense transistor |
| R_set ×8 | 22Ω, 0.5W, 1% | Sets loop current to 28mA. 1% matters — this is the reference. |
| R_bias ×8 | 10kΩ, 0.25W | Q4 base bias; sets Q3 operating current at ~2mA |
| C_C ×8 | 1nF ceramic | Current source loop compensation, Q4 base to emitter. Fit a footprint accepting 100pF–10nF — see §3.2.2. Takes C1 on the strip sheet; assigned at Rev 5.26, having been missed when Rev 5.20 assigned numbers to the five functionally named resistors. |
| R1 ×8 | 100Ω, 1W | Fault limiting, not thermal relief — see §3.2.4. 1W is for the Q4-short case. Revised down from 220Ω to recover compliance. |
| D1 ×8 | 1N4007 | Blocks reverse current during an accidental ring |
| R_LOOP ×8 | 150Ω, 2W | Loop current sense. 2W covers a shorted Q4 (1.08W) — see §3.2.4. |
| R_DET ×8 | 470Ω, 0.25W | Sets OC1 input current |
| OC1 ×8 | HCPL3700M (onsemi) | Seizure detect, DC input mode — pins 2/3 driven, pins 1/4 OPEN. 8-pin PDIP. Note this is the opposite wiring from the station board ring detector. |
| R2 ×8 | 4.7kΩ, 0.25W | OC1 output pull-up to 3.3V |
| C5 ×8 | 0.1µF ceramic | OC1 V_CC bypass, pins 8–5, at the device. Required. |
| RLY1 ×8 | CIT J104D2C5VDC.15S | DPDT ring relay, 5V/167Ω/29.9mA coil, sealed THT. Same part as the station off-hook relay — order the whole system quantity at once against the 20-week lead time: 8 here plus 22 on the station boards (the tap and monitor strips fit none). |
| Q2 ×8 | 2N2222A (TO-92, EBC) | Relay driver |
| R4 ×8 | 1kΩ, 0.25W | Q2 base resistor |
| R_pd ×8 | 10kΩ, 0.25W | Q2 base pulldown. Not optional — see §7.3. |
| R_RST | 10kΩ, 0.25W | /RESET pull-up to +3.3V at U1 pin 18, one per board. Fitted here and on every station board — deliberately the opposite of the DO NOT FIT rule for R9/R10, and for the reason in §10.4. Required by the text since Rev 5.8; given a designator and a BOM line at Rev 5.25. Takes R11 on the root sheet of the schematic. |
| C19 | 0.1µF ceramic, 50V | /RESET filter, U1 pin 18 to GND, at the pin. One per board. With R_RST a 1ms time constant, so a spike coupled into the bus cord cannot reset the expander, while a deliberate reset — 2ms low, 5ms settle (control.md §6.2) — still works. Added at Rev 5.40 — see §10.4. Takes C110 on the root sheet of the schematic. |
| D5 ×8 | 1N4148 | Relay coil flyback diode |
| C9 ×8 | 10µF electrolytic | Local 5V reservoir at each relay coil |
| C2 ×8 | 0.47µF, 250V film | T2 primary DC block. 250V is for the accidental-ring case only — see §8.1. |
| T2 ×8 | Triad TY-311P, 600Ω:600Ω | Audio isolation transformer, usable to ~9kHz. Wired node A to node B, behind both relay NC contacts. Trunks sit at the top of the comb — see §8.3. |
| R5, R6 ×8 | 1kΩ, 0.25W matched | Receive balanced series resistors |
| R7, R8 ×8 | 1kΩ, 0.25W matched | Transmit balanced series resistors |
| U1 | MCP23017-E/SP | I²C GPIO expander, 28-pin PDIP. V_DD = 3.3V. Address 0x23. |
| U2 | MCP23017-E/SP | Optional second expander, address 0x27 — reserved, matching station §9.2. Fit the footprint and the address strap, leave unstuffed — see §10.1. |
| C6, C7 | 0.1µF ceramic | Expander decoupling, one per device at the V_DD pin |
| C8 | 10µF electrolytic | 3.3V rail bulk |
| C15 | 10µF electrolytic | LDO input bulk, at U4’s own input pin rather than at the converter output — the distance between the two is trace inductance the regulator has to work through. §12.6, and a BOM line only since Rev 5.25. |
| C16 | 0.1µF ceramic | LDO input decoupling, at U4’s input pin alongside C15 — §12.6. |
| C17 | 0.1µF ceramic | LDO output ceramic, in parallel with C8 at U4’s output pin. An aluminium electrolytic alone has poor impedance exactly where the regulator’s loop needs it, and the MCP1826 is specified with a ceramic on the output — §12.6. |
| U3 | Traco TSR 2-2450 | 24V→5V switching module, SIP-3. Murata OKI-78SR-5/1.5-W36-C equivalent. 36V input rating required. |
| U4 | MCP1826S-3302E/AB | 3.3V LDO from the 5V rail, TO-220-3 through hole, 1A. 39mA, 66mW. DigiKey MCP1826S-3302E/AB-ND. NOT the SOT-223 suffix (E/DB). |
| C10 | 47µF, 50V electrolytic | 24V input bulk at the U3 pins |
| C11 | 0.1µF ceramic, 50V | 24V input decoupling at the U3 pins |
| C12 | 220µF, 25V electrolytic | 5V output bulk at U3. Total output capacitance must stay inside the module rating. |
| C13 | 1000µF, 50V electrolytic | 24V audio-band bulk at the board input — see §12.4. The only 24V bulk on the board as of Rev 5.23. |
| C14 ×8 — DELETED at Rev 5.23 | 100µF, 50V electrolytic | 24V local bulk at each trunk current source |
| D6 | 1N5822 | Reverse-polarity protection on the 24V input. SHUNT clamp: cathode to +24V BRD, anode to GND — not in series. Blows F1 on a reversed supply and costs no forward drop — see §12.5. |
| F1 | 500mA slow-blow, 5x20mm — Littelfuse 0218.500MXP | 24V board input fuse. 250V, 5x20mm glass cartridge, socketed. Same part as the generator board. |
| F2 | 250mA fast, 250V, 5x20mm — Littelfuse 0217.250MXP | Ring bus fuse at J6. Fast-acting, not time-lag — the value follows the concurrent-ring cap in §7. Confirm the 250mA part number against the 217 series listing; the 500mA sibling is 0217.500MXP. |
| FH1, FH2 | 5x20mm PC-mount fuse block, ×2 | Littelfuse 64900001039, 649 series PC-mount block, 5x20mm, 6.3A / 250VAC, solder lug. One for F1, one for F2. Same holder on all three board types. |
| J1, J2 | DB25 FEMALE, R/A, 4-40 | Analog I/O to the A32, TASCAM analog pinout. J1 = 8 board outputs to A32 inputs; J2 = 8 A32 outputs to board inputs. Gender is female — see §13.1. |
| J3 | 6P6C modular jack, R/A | I²C bus in. One only — the trunk board is last in the chain. ALL SIX POSITIONS WIRED: SCL, SDA and two grounds on 2–5, /RESET and its return on 1 and 6 — pinout in §10.4. Cords must be six-conductor; a 6P4C cord seats and leaves a working bus with no hardware reset. Corrected at Rev 5.25, having described the pre-Rev-5.8 wiring. Part number in §13.1. |
| TVS2 | Littelfuse SP721APP, 3pF SCR/diode rail-clamp array | ESD and mis-plug protection on SDA and SCL. 8-PDIP through-hole, 6 inputs, 3pF per line. Rail clamp, not a fixed-breakdown TVS: V+ (pin 8) to +3.3V, V- (pin 4) to GND, SDA and SCL to two of the six inputs, four spare. Sacrificial after a mis-plug — keep spares and consider a socket, since it is a DIP anyway. See §8.6. |
| C18 | 0.1µF ceramic, 50V | Bypass across TVS2, pin 8 (V+) to pin 4 (V−), at the device. The SP721 clamps by conducting the transient from its IN pin into V+, so V+ must source that current locally or it lifts while the clamp is working. TVS2 sits at J3, away from U1 and the LDO, so C6 and C8 are too far to serve. Root sheet, not per trunk. Added at Rev 5.27 — see §10.5 |
| J5 | 2-pin screw terminal | Board supply in: +24V BRD, GND |
| J6 | 2-pin screw terminal, 5.00mm, 300V | Ring bus in: RING_HI, RING_LO. On Shore OSTTC020162 (DigiKey ED2600-ND), 5.00mm pitch, 300V, 15A, 14-22 AWG, side entry, blue. NOT the same part as J5/J1: those are the OSTTE020104, 3.50mm pitch and 125V, which is inadequate here — 100V RMS ring is 141V peak, above that block's rating entirely. 300V gives 2.1x margin, in line with the 250V film capacitors and 300V cable elsewhere in this zone. The two are different colours, blue against black, so the ring bus terminal is visually distinct from the 24V input on the same board. Own zone, 3mm creepage, physically separate from the low-voltage connectors. |
| J7A, J7B | RJ45 jack, shielded, R/A | Trunk tip/ring to the switchboard, four trunks per connector. Pinout in §8.5. The only RJ45 on the board — the connector type signals hazardous voltage. Shield to chassis at this end only. Part number in §13.1. |
| JP1–JP3 | 0Ω links ×3 | MCP23017 address strap: A0, A1 to +3.3V and A2 to GND, giving 0x23. Link footprints rather than solid copper — see §10.2. Designators assigned at Rev 5.25; the row carried none before, which left three footprints nothing could refer to. |
| JP4 | 0Ω link | D-Sub ground pins to board GND — FOOTPRINT ONLY, DO NOT FIT. The sixteen connector ground pins common to one node and reach board GND only through this link, which stays out so the shields are grounded at the A32 end alone. 100Ω in parallel with 10nF is the middle position and takes the same footprint. Silkscreen what fitting it means — see §8.4. Designator assigned at Rev 5.25. |
| R9, R10 | 2.2kΩ, 0.25W | I²C pull-ups — DO NOT FIT. The single pull-up pair lives on the ring generator board. |
| Cable — trunk lines | Cat5e, 300V (CM/CMR) | Voltage rating is not optional at 141V peak. Check the jacket print — patch cords are often marked 30V or 72V. |
| Cable — I²C | 4- or 6-conductor modular, STRAIGHT-THROUGH | Not a standard voice line cord — those are reversed and short the bus to ground. See §10.4. |
| PSU | Mean Well LRS-150-24 | 24V, 6.5A, 156W enclosed. Chassis mount, off-board, common to the whole system including the switchboard. Sized for 24 circuits with headroom for 32 — see §12.1. Replaces the LRS-35-24, undersized by 2–3×. Check the 115/230V input switch before first power-on. |

## **13.1 Connector Part Numbers**

All three are through-hole, right-angle, board-edge parts. Prices and stock are as checked and will drift; the part numbers and the selection reasoning are the durable content.

| **Ref** | **Part** | **DigiKey** | **Notes** |
| --- | --- | --- | --- |
| J7A, J7B | Amphenol ICC RJHSE5380 | 664-RJHSE5380-ND | 8P8C, right angle, shielded with EMI finger, no LEDs, no magnetics, gold 50µin, board lock, −55 to +85°C. About $1.72 each, deep stock. Qty 2. |
| J3 | Amphenol ICC 87180-066LF | — | 6P6C, right angle, unshielded, through hole. About $1.88. Qty 1. Würth 615006138421 (~$0.58) or Assmann A-2004-1-4-N-R (~$0.72) are equivalent for this purpose; at one per board the price is irrelevant, so pick on footprint and availability. |
| J1, J2 | NorComp 182-025-213R561 | — | Qty 2. 25-position receptacle, female sockets, right-angle through hole, solder, gold contacts, nickel-plated steel shell, board lock, integral 4-40 female screwlocks on the mating side, 5A per contact, PA9T dielectric, −55°C to +105°C. DigiKey 182-125FE-ND. Replaces the Amphenol ICC DBM25S500MN, which DigiKey does not stock. Screwlocks are part of the connector — no separate hardware line. The 182-025-213R531 is the same part with a plain threaded shell and needs two SFSO4401NR screwlocks each, which saves nothing once counted. Backset is 0.318 in (8.08mm) either way — confirm against the board edge before committing the footprint, particularly with two of these alongside the RJ45 jacks. 16-week manufacturer lead time despite stock, so order all six at once. |

*The DB25 gender needs settling before ordering, and earlier revisions of this document had it wrong. They specified male. The convention across TASCAM-pinout gear — including the A32 — is a female socket on the equipment and a male plug on the loom, so a board-to-A32 run is a male-to-male analog snake, which is a stock item. That means the trunk board should present female, not male. Confirm against the A32 before ordering, but do not assume male just because the board is the **"**source**"** end.*

J1 and J2 need 4-40 female screwlocks on the board side so the loom's jackscrews have something to bite. On most D-Sub bodies those are a separate line item; the connector specified in §13 has them integral to the mating-side flange, so there is nothing extra to order. If that part is ever substituted, check the flange feature.

*Two procurement points. The RJHSE5380 carries a 14-week manufacturer lead time against deep distributor stock — the same pattern as the relays and the PSU, so buy spares in the first order rather than discovering it later. And the DigiKey attribute table for the RJHSE5380 lists no voltage rating at all, which matters because J7A and J7B carry 141V peak. Pull the dielectric withstanding voltage from the Amphenol datasheet (rjhsex380.pdf) and confirm it before committing. Modular jacks in this class are normally rated far above this — POTS ring has run through 8P8C for decades — but it should be a checked number rather than an assumed one.*

# **14. PCB Layout Notes**

- Three high-voltage zones, not one. J7A and J7B and their trunk wiring carry 141V peak ring from either direction; the ring bus from J6 carries it whenever the generator is enabled; and the relay contact ends bridge the two. Mark all three on silkscreen and maintain 3mm creepage from every one of them to logic.

- Divide the board into a high-voltage edge carrying J6, J7A and J7B, and a low-voltage edge carrying J1, J2 and J3, with the boundary printed on the silkscreen — see §8.6.

- The ring bus is the new hazard on this board and it is the one Rev 4.4 did not have. It runs from J6 to all eight relays in parallel, so it crosses the whole board. Route it as a single spine along the high-voltage edge with the relays hanging off it — not as a star, which would triple the length of HV copper.

- Route the isolation barrier as a continuous slot under each HCPL3700M body rather than relying on surface clearance.

- Group each trunk's current source, relay, driver and transformer into a strip and array it eight times. Get one trunk block right first. Confirm the J104D package dimensions before committing — 2 Form C is an eight-pin footprint.

- Node A and node B are the only two nets that are line-side when the relay is released and board-side when it is thrown. Keep both short and keep them inside the relay footprint's shadow rather than running them across the strip — they carry the audio and they sit between two high-voltage zones.

- Q4 dissipates 0.44W steady and 1.3W averaged during an accidental ring. Give each one a clip-on heatsink and the clearance to use it, and do not bury the eight of them in the middle of the board where the heat has nowhere to go.

- Four layers: top / In1 GND / In2 power / bottom, the generator board's layer order with In2 carrying the three low-voltage rails as a split pour. Both inner layers stop 3mm short of the high-voltage edge — rule area on In1 and In2, drawn by hand, because KiCad's clearance constraint is same-layer only and the netclass rule will not keep a plane from running under the ring spine. Stack-up, split lines and rule areas are in trunk_schematic_guide §7.5.

- Each R_LOOP returns to the In1 ground plane by its own via; none of the eight share a trace on the way. Through Rev 5.27 this was a star to a single point — see §12.4 for why the plane supersedes it. Place the LDO's own input bulk at U4's input pin rather than relying on the converter output bulk — see §12.6.

- Place the DC-DC converter, its input capacitors and its output capacitor in one tight corner well away from the transformer strip and both D-Subs. Its switching node is the only radiator on an otherwise passive board; the In1 plane is the pour between it and everything else, and it should be unbroken there.

- Put J3 at the low-voltage edge with J1 and J2, as far from J6, J7A and J7B as the board allows, and on the same edge as the corresponding connectors on the station boards so the chain runs cleanly down the rack. The bus carries 90V at 20Hz with 40kHz PWM residue on it, SDA and SCL have no error detection, and a corrupted expander write here energises a ring relay.

- Leave footprints unstuffed for: U2, the expander V_CC series resistor, and the I²C pull-ups R9/R10. L1 is gone as of Rev 5.29, not unstuffed — §12.4. Drop the P82B96 buffer footprint — §10.4 shows the bus has ample margin at this length. Board space is cheap now; a respin is not.

# **15. Safety Notes**

- This board originates ring voltage. That is the single most important difference from the station boards. 90V RMS at 20Hz (127V peak, up to 141V peak no-load) is present on J6, on the ring bus spine and on both relay NO contacts, and because the generator is shared with the switchboard it runs continuously rather than only while a trunk is ringing (§7.6). Assume the bus is live whenever the system is powered. The only things that stop it are the GPIO4 master enable switch and the GPIO14 shutdown line, both on the ring generator board — nothing on the trunk board can make the bus safe. No operator action is required to put voltage on it.

- J7A and J7B carry 141V peak. RJ45 is used for nothing else on this board or elsewhere in the system, so the connector type itself is the warning — keep it that way. Use 300V-rated cable; many Cat5e patch cords are rated 30V or 72V and are not suitable. Note that a 6P6C I²C plug will physically enter an RJ45 jack (§8.6).

- All components in the ring path must be rated 250V minimum. Maintain 3mm creepage. Note that the audio transformer is not in the ring path in normal operation — both relay poles break it clear — but C2 must still carry a 250V rating for the accidental case.

- The trunk pairs are referenced to board ground through R_LOOP, so tip and ring are not floating with respect to the board as they are on a station. The isolation barrier to the equipment side is T2 and the optocoupler; confirm each transformer's isolation before the D-Sub cables are connected.

- One common 24V battery now feeds the switchboard, both board types and all loops, so board ground and switchboard battery negative are the same node. Deriving board power from tip and ring is still prohibited (station §10.1), and the 24V distribution must be a star from the PSU terminals — see §12.1.1.

- Relay contacts stand off up to 165V peak when open (§7.4). Verify contact-to-contact dielectric strength from the datasheet rather than the distributor attribute table. Note that the relevant ring figure throughout is the generator's 141V peak no-load output, not the 127V peak of the 90V RMS nominal, because the bus idles unloaded.

- The board dissipates roughly 7W with all trunks seized, most of it in the eight current sources, and each Q4 reaches 1.3W if ring is applied to its trunk. Ventilate the enclosure. The relay coil margin in station §5.4 degrades with temperature and this board runs warmer than a station board.

- Verify the HCPL3700M pull-ups are connected to 3.3V and not 5V before powering with the ESP32 connected. The ESP32 GPIO pins are not 5V tolerant.

- Do not connect trunk circuits to a live PSTN telephone line. Designed for 551 switchboard connection only.

# **16. Open Items for Bench Verification**

Everything below is a number this design assumes rather than knows. Each has a fallback identified in the section referenced.

| **Item** | **Why it matters** | **Section** |
| --- | --- | --- |
| 551 trunk cord circuit DC resistance | Compliance is 554Ω with R1 at 100Ω. Decides whether §3.3.1 is needed at all. | §3.2.4 |
| Switchboard trunk supervisory relay operate current | Bounds how far loop current can be reduced; gates the cheapest compliance fix | §3.3.1 |
| HCPL3700M DC input forward drop at 6mA | Sets R_DET. The one unmeasured number in the seizure detector. | §4.2 |
| Current source loop stability into the real line | Sets C_C. Step the load and look for ringing; cord circuit inductance is unmeasured. | §3.2.2 |
| Current source output impedance across 300Hz–9kHz | Underpins the crosstalk claim; Early voltage is an estimate | §3.2.1 |
| Switchboard 24V draw — idle, typical, all lamps lit | The largest unmeasured term in the system budget; decides the PSU | §12.1 |
| Ring current drawn by one trunk | Sets the concurrent-ring cap and the F2 fuse value | §7.6 |
| Ring bus common-mode drift with both ends open | Confirms whether the 1MΩ reference pair is needed at the generator | §7.1.1 |
| 40kHz carrier residue at the A32 input during ring | Folds to 8kHz, on the doorstep of the trunk pilot comb | §8.1.2 |
| Ring crosstalk into an adjacent trunk pair in the same cable | Predicted −93dB; a quick confirmation with one trunk ringing and a tone on its neighbour | §8.5 |
| RJ45 jack dielectric withstanding voltage | Not in the distributor attributes; J7A/J7B carry 141V peak | §13.1 |
| A32 D-Sub gender | Decides whether the board takes female sockets and a male-to-male loom | §13.1 |
| Which bus leg the switchboard puts on tip | Decides whether the open NO contact sees 0V or 141V during an accidental ring | §7.4 |
| Generator output under 1, 4 and 8 trunk load | Confirms 85–100V RMS is held; the 20W tap may be the binding limit | §7.1 |
| SEIZE pulse pattern under applied ring | Confirms the 27ms / 100ms discrimination margin on real hardware | §5.2 |
| C2 switching transient at the relay | Predicted 19mA peak, 282µs. Confirm it does not upset pilot detection. | §8.1.1 |
| Cord-pull transient at the jack | Scope tip-ring as a cord is pulled from a seized trunk; confirms TVS1 clamping and cord circuit inductance | §6.1 |
| T2 insertion loss at 8250–8906Hz | Trunks sit at the top of the comb and will show the most loss | §8.3 |
| Relay open-contact dielectric strength | 165V peak across open contacts; attribute table does not give this | §7.4 |
| Trunk-to-trunk audio crosstalk | Expected below −90dB. If measured above the floor, the shared path is the rail (C13) or the ground returns — no inductor footprint exists to stuff, by decision at Rev 5.29 | §12.4 |
| 5V rail under 8 coils energised | Relay pull-in margin is calculated against the rail's lower limit | §12.2 |

Two of these gate the layout rather than the bring-up. The cord circuit resistance decides R1 and therefore whether Q4 needs a real heatsink, and the ring current per trunk decides the ring bus copper width and the fuse. Measure both before the board is cut; the rest can wait for a populated board.
