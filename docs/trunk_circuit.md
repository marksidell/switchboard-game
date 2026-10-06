**551 Switchboard Simulator**

**Trunk Interface Circuit Design**

*Rev 5.44 — 8 Trunks, Constant-Current Loop Feed, MCP23017 I/O over 6P6C I²C and MQTT, RJ45 Trunk Lines, D-Sub25 Female Audio to the Ferrofish A32 at 48kHz, External Ring Generator*

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
- Rev 5.41: the seizure detector is resized (§4.2): R_LOOP 150Ω → 220Ω (2W) and R_DET 470Ω → 150Ω (§3.3, §3.4, §4.1, §13); R1 stays at 100Ω. Found on the bench, 2026-10-03 and 2026-10-04: trunks intermittently reported no seizure with full loop current flowing — up to 27 of 100 off-hooks on one trunk, all-or-nothing, never late — and missed dial makes (control.md Rev 23). With the Analog Discovery across R_LOOP and R_DET, a miss showed 28mA of loop current and 1.90mA into OC1, the same as a good seizure; OC1's output blipped on for about 0.25ms at the relay make and stayed off. §4.2 had modelled the HCPL3700M's DC input as an LED dropping 1.4V and flagged that figure as the one number not measured. The datasheet (onsemi HCPL3700M, 2022-03-15) gives the DC input as the buffer IC's own threshold: V_TH+ 3.35–4.05V at I_TH+ 1.96–3.11mA, V_TH− 2.01–2.86V. Measured, OC1 sat at 3.28V and 1.90mA — below every part's turn-on point and above every part's turn-off point, inside the hysteresis band, so the output stayed wherever the make transient left it. No value of R_DET alone fixes it: 28mA in 150Ω is 4.2V, barely above the 4.05V worst-case threshold with nothing in series. Loop compliance was measured through the switchboard first (§3.3.3); the heaviest configuration, a station-board station on a cord, keeps about 100Ω of spare with these values. Two alternatives were weighed and not taken: R1 to 33Ω as well (more spare, which nothing measured needs, at eight more parts and harder faults), and R1 removed (the most spare, but a shorted Q4 on a normal call then runs OC1 at 83% of its input power rating). §3.3.2's merged-resistor sizing, which had the same 1.4V error, is corrected, and two §16 items are closed. The schematic designators for the changed parts are Rx06 and Rx07 on trunk sheet x.
- Rev 5.42: the document uses the KiCad designators of the rev 2 board as annotated, in place of its own names, everywhere outside this change history, which is left as written. Strip parts are Rxnn on trunk sheet x, x = trunk number + 1 (trunk 1 is 2nn, trunk 8 is 9nn); root-sheet parts are numbered from 101. The board as built differs from the earlier text in five ways, now recorded: Cx01, the 100µF at each current source that Rev 5.23 deleted, is fitted on every strip (§12.4); U101's address is hardwired, A0 and A1 to +3.3V and A2 to GND, with no links (§10.2); the D-Sub ground link JP4 is two fitted 0R resistors, R102 and R103, one per DB25 (§8.4); C18, the TVS101 bypass, is not on the board and waits for rev 3 (TODO.md); and there are no footprints for a second expander, its decoupling or I²C pull-ups, so U2, C7, R9 and R10 are gone. C19 remains a bodge, C110 at rev 3. "Next board revision" means rev 3.
- Rev 5.43: corrections from an independent review of Rev 5.41, 2026-10-05, which confirmed the fix — every HCPL3700M turns on at the datasheet limits — and found several of its supporting figures wrong. Rx06 and Rx07 are now 1% parts: at −5% on Rx06 the turn-on margin falls from 0.52V to 0.27V (§4.2, §13). §4.2 gains the loop-current view of the same margin — a worst-case part needs 23.6mA against the 26mA design minimum, and holds down to 15.7mA — and its normal-operation figures are corrected to a 5.24–5.54V node and 3.0–4.4mA into Ux01 at 28.2mA; Rev 5.41's 3–6mA could not happen, since I_IN is at most 4.4mA at 5.0V and the input's curve is monotonic. The input clamp Rev 5.41 used, V_IHC1, applies only with pins 1 and 4 tied to pin 3; with them open, as on this board, the input is about 1kΩ in series with 1V (Broadcom AV02-3699EN) and clamps near 12.5V (V_IHC3). With that, and with Qx01's emitter-base junction clamping Rx02 in a Qx03 short, the fault figures fall: even a shorted Qx03 into a dead-shorted jack keeps every part inside its rating, and Rev 5.41's statement that it overloads Ux01 and Rx07 is withdrawn. Qx03 shorted during ring applied by mistake is recorded as the one case that destroys parts. Also corrected: the compliance cost of Rev 5.41 (45–54Ω of spare, not 25–50Ω, §3.3, §3.3.3), Rx06's dissipation (§3.4), the seizure inrush (§3.2.2), the §3.3.1 design point (320Ω), node B in §8.1.1, and the detector's hold-on figure. The detector now follows dial contact bounce, which control.md Rev 24's two-sample filter rejects (§4.2). Also corrected here: R102 and R103 are footprints left unfitted, not fitted as Rev 5.42 recorded (Mark, 2026-10-05), so the D-Sub grounds float at this board as §8.4 intends.
- Rev 5.44: Rx05 (R1) goes from 100Ω to 33Ω, 1W (Stackpole RSF1JT33R0); Rx06 220Ω 2W 1% and Rx07 150Ω 1% are unchanged from Rev 5.41 and Rev 5.43 — Mark's decision, 2026-10-05 (§3.2, §3.2.4, §3.3, §3.3.1, §3.3.3, §3.4, §4.2, §13). Measured the same day on trunk 1 (§3.3.3, tests 8 and 9): the 551's dial relay pulls in at the first dial pulse and holds until the operator switches out, and with the operator in after dialling the trunk sees about 440Ω — heavier than any configuration tested before, and the same whether or not a station is on the cord, because the operator's key takes the station out of the trunk loop until she switches out. At 440Ω the Rev 5.41 values left about 8–17Ω of spare and would lose regulation at the top of the current spread; with Rx05 at 33Ω the spare is about 75–84Ω, about 50Ω at 31mA. Rx05 + Rx06 is 253Ω, close to the Rev 5.40 total, so compliance is about 575–585Ω at 28.2mA. The cost is the double fault: a shorted Qx03 into a dead-shorted jack now puts about 450mW into Ux01, past its 230mW maximum (§4.2), where Rev 5.43 had every part within rating; no Rx05 low enough for compliance avoids that, and it is accepted as a double fault — Ux01 is a DIP and can be socketed. The single fault, a shorted Qx03 on a real loop, stays within every rating. Current-source stability was measured in the same session and closes the §16 item: dial makes overshoot for under 40µs and settle with no ringing, and Cx02 stays at 1nF (§3.3.3).

| **Former name** | **Designator** | **Former name** | **Designator** |
| --- | --- | --- | --- |
| TVS1 | Dx01 | U1 | U101 |
| Q4 | Qx03 | C6 | C101 |
| Q3 | Qx01 | C17 | C109 |
| R_set | Rx02 | C8 | C108 |
| R_bias | Rx04 | C10 | C103 |
| C_C | Cx02 | C11 | C104 |
| R1 | Rx05 | C12 | C105 |
| D1 | Dx03 | C13 | C102 |
| R_LOOP | Rx06 | C15 | C106 |
| R_DET | Rx07 | C16 | C107 |
| OC1 | Ux01 | U3 | U102 |
| R2 | Rx12 | U4 | U103 |
| C5 | Cx05 | D6 | D101 |
| RLY1 | Kx01 | F1 | F102 |
| Q2 | Qx02 | F2 | F101 |
| R4 | Rx01 | J1 | J104 |
| R_pd | Rx03 | J2 | J105 |
| D5 | Dx02 | J3 | J101 |
| C9 | Cx03 | J5 | J103 |
| C2 | Cx04 | J6 | J102 |
| T2 | Tx01 | J7A, J7B | J7A101, J7B101 |
| R5, R6 | Rx08, Rx09 | TVS2 | TVS101 |
| R7, R8 | Rx10, Rx11 | R_RST | R101 |
| C14 | Cx01 | JP4 | R102, R103 |

- Rev 5.36: the §11.1 pointer follows control.md Rev 2, which adds dial pulse detection on the seizure input. The 25ms release rule it quoted is gone — a dial pulse is a 25–100ms release — and the ring discriminator is now the break-to-break interval. No hardware change: the current source and the HCPL3700M already pass a dial pulse as a clean loop-current interruption (§3.2.2, §4). One measurement is added to the control.md open items rather than to §16 here, since it is a firmware threshold check: pulse timing on SEIZE_n through the real cord circuit and dial.

# **2. Functional Block Diagram (One Trunk)**

```text
                          +24V BRD
                             |
                     [ constant-current source ]   Qx01/Qx03, Rx02, Rx04
                             |  28mA
                            Rx05 (33R)
                             |
                            Dx03 (1N4007)
                             |
          RING_HI o---------|-------- Kx01 pole 1 NO
                             +-------- Kx01 pole 1 NC ---- node A
                                                             |
  SWITCHBOARD TRUNK JACK                                     |
                                                    Cx04 (0.47uF, 250V)
    TIP  o----+----- Kx01 pole 1 common ---------------------+
              |                                              |
          Dx01 (P6KE150CA)                            Tx01 primary (+)
              |                                              |
    RING o----+----- Kx01 pole 2 common               Tx01 primary (-)
                            |                                |
                     Kx01 pole 2 NC ---- node B -------------+
                            |               |
                     Kx01 pole 2 NO      Rx06 (220R) ------ GND
                            |               |
          RING_LO o-------+            Rx07 (150R)
                                            |
                                       Ux01 HCPL3700M (DC input)

  Ux01 output -----> U101 Port A bit n SEIZE_n     (loop current)
  U101 Port B bit n -> Rx01 -> Qx02 -> Kx01 coil  RING_EN_n

  Tx01 secondary: fully floating 600R winding
    Hot  ---- Rx08 (1k) -- A32 ANALOG IN (+)     [channel 24+n]
    Cold ---- Rx09 (1k) -- A32 ANALOG IN (-)
    A32 ANALOG OUT (+) ---- Rx10 (1k) -- Tx01 sec hot
    A32 ANALOG OUT (-) ---- Rx11 (1k) -- Tx01 sec cold
```

Only Dx01 sits permanently across tip and ring at the jack. Everything else on the trunk — the DC feed, the sense resistor and the audio transformer — is behind a relay contact, and both relay poles break when ring is applied. Node A and node B are the board-side ends of the two NC contacts; Tx01 spans them, which is what lifts it clear of the line during ring — see §8.1.

# **3. DC Loop Feed — Constant Current Source**

## **3.1 Why Not a Series Resistor**

Rev 4.4 fed each trunk from +24V through a 330Ω 1W resistor, and analysed the ring case only as far as the 10Ω sense shunt. The feed resistor itself was never checked, and it is the part that fails.

If the operator applies ring to a trunk — which is a mistake rather than a signalling event, but a mistake that will happen on a manual board — 90V RMS appears across the trunk pair on top of our 24V feed. Dx03 blocks the opposing half-cycle, but on the aiding half-cycle the loop EMF is 24 + 127 = 151V peak and the current is limited only by the series resistance:

```text
  R_line = 100R:   I_pk = 285mA   I_rms = 142mA   P(Rx05) = 6.7W
  R_line = 0R:     I_pk = 343mA   I_rms = 172mA   P(Rx05) = 9.7W
```

A 1W part does not survive that, and neither does a 5W part if the key is held. Raising the resistor rating is not a fix either, because the same current also has to pass through the sense element, and the sense element has to develop enough voltage at 28mA to trip a detector while surviving ten times that during ring. Those two requirements pull in opposite directions and there is no resistor value that satisfies both.

A constant-current feed removes the conflict outright. The feed current is the same whether the trunk is idle, seized, or being rung into by mistake, so every downstream part is sized for one condition. This is also what a real line card does, and it brings two benefits beyond the thermal one: loop current no longer varies with the switchboard cord circuit resistance, and the sense threshold therefore has an unambiguous on/off rather than a range to straddle. It is also what makes the accidental-ring case survivable without any additional protection components at all — see §5.

## **3.2 Circuit**

```text
  +24V BRD ----+---------------------------- Qx01 emitter (2N3906)
               |
               +-- Rx02 (22R, 0.5W) ---+---- Qx03 emitter (MJE350)
                                       |
                                       +---- Qx01 base

  Qx01 collector ---------------------------- Qx03 base
  Qx03 base -- Rx04 (10k) ------------------ GND
  Qx03 base -- Cx02 (1nF) ------------------ Qx03 emitter   [compensation, 3.2.2]

  Qx03 collector -- Rx05 (33R, 1W) -- Dx03 (1N4007) -- Kx01 pole 1 NC ---- TIP
```

Qx03 passes the loop current; Qx01 monitors the drop across Rx02 and steals Qx03's base drive when that drop reaches its own V_BE. Loop current is therefore V_BE(Qx01) / Rx02, independent of everything downstream, up to the compliance limit in §3.3.

Dx03 blocks reverse current during the opposing half-cycle of an accidental ring, when TIP swings to roughly −103V with respect to ground. It stands off about 127V in that condition; a 1N4007 is far beyond what is needed but costs nothing. Without it, Qx03 would see its collector-emitter junction reverse-biased by the same 127V.

## **3.2.1 How It Regulates**

This is a standard topology, not a novelty. It is the same two-transistor arrangement used as the short-circuit limiter in a classic series-pass linear regulator — the current-limit transistor around the pass device — repurposed so that the limit is the operating point rather than a fault threshold. It goes by several names in the literature: two-transistor current source, current limiter, or V_BE-referenced current source. It is worth being explicit about the loop because the whole trunk design now leans on its two properties: a hard current ceiling, and a very high output impedance.

The regulating loop has one sensing element and one correcting element:

- Rx02 carries the whole output current, so the voltage across it is a direct measure of that current. That voltage is also, by construction, Qx01's base-emitter voltage — Qx01's emitter is on the rail and its base is on the far side of Rx02.

- Rx04 pulls Qx03's base toward ground and is what turns Qx03 on in the first place. It supplies 2.27mA, against the 0.28mA of base current Qx03 actually needs at 28mA of collector current.

- Qx01's collector sources current into Qx03's base node, pulling it back up toward the rail. Since Qx03 is PNP, raising its base voltage reduces its V_BE and turns it off. Qx01 therefore opposes Rx04, and the surplus 1.99mA of Rx04 current is exactly what Qx01 has to sink to hold the balance.

The sequence at power-on: Rx04 turns Qx03 hard on, current climbs, the drop across Rx02 climbs with it, and at roughly 0.62V Qx01 begins to conduct and steals base drive from Qx03. The loop settles where the output current produces exactly enough drop across Rx02 to keep Qx01 conducting just hard enough. That point is I = V_BE(Qx01) / Rx02, independent of what is downstream, which is the whole purpose.

Nothing about that depends on Qx03's gain, on the supply voltage, or on the load — all of those are inside the feedback loop. What it does depend on is V_BE(Qx01), which is why the current has the −0.3%/°C tempco and the ±10% part-to-part spread noted in §3.3, and why Rx02 is specified at 1%: it is the only element setting the value that the loop cannot correct for.

The loop gain is what makes the regulation tight, and it is high because Qx01 is a transconductance amplifier working into a moderately high impedance:

```text
  Qx01 operating point Ic3 = 1.99 mA        gm3 = 76 mA/V
  Qx03 base node       Rx04 || [rpi4 + (b+1)Rset]    = 1.9 kohm
  dI -> dVbe3 -> dIc3 -> dVb4 -> dI
  loop gain T ~ 138
```

A 1% change in output current moves the Rx02 voltage by about 6mV, which Qx01 turns into roughly 0.46mA of collector current, which moves Qx03's base by nearly a volt. The loop is stiff.

That gain also multiplies the output impedance, which is the property §12.4 relies on when it claims the feed looks like an open circuit to audio:

```text
  Qx03 alone, Early VA = 100V: ro = 3.5 kohm
  with feedback:               ro x (1 + T) ~ 500 kohm
  Qx03 Ccb ~ 30pF at 8.9 kHz:  Xc ~ 600 kohm
  combined at the top of the pilot comb:  ~270 kohm
```

Against a 600Ω line that is a ratio of roughly 450:1 even at the worst frequency in the band, and better than 800:1 through the voice band where the Early-effect term dominates and Ccb has not yet come in. The Early voltage is an estimate and the figure should be confirmed rather than trusted — see §16 — but there is a great deal of margin in it.

## **3.2.2 Compensation and Transient Behaviour**

This is a feedback loop with gain, so it can oscillate, and a telephone line is a reactive load with cord circuit inductance measured in henries. Cx02, 1nF from Qx03's base to its emitter, is the dominant-pole compensation and was missing from earlier drafts of this document. Fit the footprint and expect to tune it: 100pF to 10nF covers the useful range, and the correct value depends on the actual cord circuit, which has not been measured.

Cx02 also sets the recovery time when a seizure suddenly presents a load. Before the switchboard closes the loop, Qx03 has no load, saturates, and sits with its full 2.27mA of base drive available, so at the instant of seizure the loop has to catch a transistor that is already fully on. An earlier draft of this section put that inrush at 227mA, from beta × I_bias. That is wrong: it is what Qx03 would deliver into a zero-impedance load, but the series resistance is in the path from the first instant, and a saturated Qx03 can only pass what that resistance allows.

```text
  I = (24 - Vce(sat) - Vd) / (Rx02 + Rx05 + Rx06)   with Qx03 saturated

      Rev 5.44, Rx05 33R,  Rx06 220R:  ~85 mA  ->  ~15 V at node B  ->  ~13-20 mA into Ux01
      Rev 5.43, Rx05 100R, Rx06 220R:  ~67 mA  ->  ~14 V at node B  ->  ~11 mA into Ux01
      Rev 5.40, Rx05 100R, Rx06 150R:   85 mA  ->  12.8 V on Rx06   ->  24 mA into Ux01
      Rev 5.40, Rx05 0R:               134 mA  ->  20.1 V on Rx06   ->  40 mA into Ux01

  duration with Cx02 = 1nF: ~2 us
```

So the real figure is about 67mA, a little over twice the steady current rather than eight, and about 11mA into an optocoupler input rated 50mA average and 140mA surge (Rev 5.43; it was 85mA and 24mA with Rev 5.40's Rx06 and Rx07). Ux01's input is about 1kΩ in series with 1V (§4.2), which is why it takes so little of the spike. The detector is in no difficulty. The spike is worth knowing about only so that nobody finds it on a scope and assumes something is wrong, and it is far too brief for the 100ms seize debounce in §11.1 to register.

## **3.2.3 Why Not an LM317 or a Depletion FET**

Both are the obvious two-part alternatives and both were rejected for the same reason, which is worth recording so the decision is not revisited from scratch later.

| **Option** | **Why not** |
| --- | --- |
| LM317 as current source | Standard and simple — I = 1.25V / R — but it is a 40V part. Qx03 stands off 136V during an accidental ring (§3.4). Also wastes 1.25V of compliance against this circuit's 0.62V. |
| Depletion MOSFET + source resistor | Two parts, and DN2540-class devices handle 400V. But V_GS(off) spreads 1.0–3.5V, so eight channels would need eight individual trims. |
| LM334 | Three-terminal and well behaved, but tops out around 10mA. Not enough for a 28mA loop feed. |
| Current regulator diode (CRD) | Simplest possible, but available currents and voltage ratings are both far below what is needed here. |
| Op-amp and pass device | Precision far beyond the requirement, and more parts than the discrete pair. |

The voltage rating is the decisive term. The pass device has to survive the full ring excursion in the accidental case, which rules out every integrated option and leaves a discrete high-voltage transistor with a discrete sense element around it. Having chosen that, the two-transistor loop costs one more small-signal transistor than a bare series resistor and gives a hard current ceiling in exchange.

## **3.2.4 What Rx05 Is For**

Rx05 is not necessary. The current source regulates perfectly well without it, and it is worth being explicit about what it buys and what it costs, because it costs the scarcest quantity in this design.

Rx05 does three things, and only one of them matters:

- It moves steady dissipation off Qx03 and into a resistor. Real but small — 0.09W between the 100Ω and 220Ω cases.

- It halves the inrush when a seizure suddenly presents a load to a saturated Qx03. Both values are benign.

- It limits the current if Qx03 fails collector-to-emitter short. This is the one that earns Rx05 its place.

It does almost nothing for the case that actually stresses Qx03. During an accidental ring the transistor is absorbing 127V of applied ring, and whether Rx05 drops 2.8V or 6.2V of the remainder changes peak dissipation by 2%. Rx05 is not thermal protection for the event that matters.

Against that it consumes compliance one-for-one, and compliance is what the design is short of, because the 551 cord circuit resistance is still unmeasured and the switchboard's own trunk supervisory relay needs adequate loop current to operate. Running out of compliance is not a graceful degradation in the way §3.3 suggests — the current falls, and it may fall below what the switchboard needs to see.

| **Rx05** | **Line compliance** | **Qx03 at shorted jack** | **Qx03 short-fault: I / Rx06 / Ux01** |
| --- | --- | --- | --- |
| 0Ω | 654Ω | 0.52W | 134mA / 2.71W / 40mA — Rx06 destroyed, Ux01 over-driven |
| 100Ω | 554Ω | 0.44W | 85mA / 1.08W / 24mA — survivable with a 2W Rx06 |
| 220Ω | 434Ω | 0.35W | 59mA / 0.52W / 16mA — comfortable, but 120Ω less compliance |
| 330Ω | 324Ω | 0.26W | 46mA / 0.32W / 12mA — too little compliance to risk |

Rx05 = 100Ω is specified as the default, revised down from 220Ω. It keeps a shorted pass transistor from cascading into Rx06 and the optocoupler, which is the only real job it has, while giving back 120Ω of compliance against the unmeasured cord circuit. Rx06 is uprated to 2W to cover the resulting 1.08W fault case; that is the cost of the change and it is one resistor package size.

Deleting Rx05 entirely is the tempting simplification and should be resisted. At 0Ω a shorted Qx03 puts 2.7W into a 0.5W Rx06 and drives 40mA continuously into the optocoupler input — a single transistor failure then takes out two more parts and possibly the trunk's detection with it. The 100Ω resistor is cheap insurance against a plausible failure turning into a cascading one.

*Rev 5.41: Rx05 stays at 100Ω. Rx06 rises to 220Ω, so Rx05 + Rx06 is 320Ω, and the fault figures in the table above improve; §4.2 has them. The compliance figures in the table are the Rev 5.40 values; §3.3 and §3.3.3 have the current ones.*

*Rev 5.44: Rx05 is 33Ω. The dial relay's load, about 440Ω with the operator in after dialling (§3.3.3), needs the compliance that 67Ω of Rx05 was costing, and Rx05 + Rx06 at 253Ω is back near the Rev 5.40 total, so the fault limiting of the paragraphs above is nearly what it was. What changes is the double fault, a shorted Qx03 into a dead-shorted jack, which now overloads Ux01 (§4.2).*

## **3.3 Component Values and Compliance**

| **Parameter** | **Value** | **Notes** |
| --- | --- | --- |
| Rx02 | 22Ω, 0.5W | Sets loop current |
| Loop current | 28.2mA nominal | V_BE 0.62V / 22Ω |
| Spread | 26–31mA | V_BE 0.58–0.68V across parts and temperature |
| Fixed drops at 28mA | 7.5–7.8V | Rx02 0.62 + Rx05 0.93 + Dx03 0.7 + node B 5.24–5.54 (Rev 5.44; 9.4–9.7V with Rx05 at 100Ω, Rev 5.43; 8.4V with Rx06 4.23 at Rev 5.40). Ux01's branch carries 3.0–4.4mA of the loop current past Rx06, so the drop is less than 28mA × 220Ω — §4.2. |
| Compliance for line | 16.2–16.5V | Regulates up to about 575–585Ω of line (Rev 5.44; 505–520Ω at Rev 5.43, 554Ω at Rev 5.40). Measured loads through the switchboard are 134–440Ω, the heaviest with the operator in and the dial relay held — §3.3.3. |
| Beyond compliance | Degrades | Behaves as a resistive feed and loop current falls. A seizure already detected holds down to 15.7mA in the worst case (13.4mA typical), but a new one is not detected below 23.6mA (§4.2); that point is reached only beyond about 670Ω of line. The switchboard's supervisory relay may give out sooner. |

*If the cord circuit measures comfortably below 400Ω, Rx05 can go back up to 220Ω for a cooler Qx03 and a gentler fault case. If it measures above about 575Ω, see §3.3.1 — and note that raising the supply rail is not among the options.*

The 2mV/°C temperature coefficient of V_BE(Qx01) makes the loop current fall about 0.3% per °C. Over a realistic 25–50°C range that is 28mA down to 26mA. Do not attempt to compensate it, but keep Qx01 away from Qx03's heatsink: this tempco, not the optocoupler, is the seizure detector's real temperature sensitivity, since the detector's guaranteed turn-on needs 23.6mA (§4.2).

## **3.3.1 If Compliance Is Short**

An earlier draft of this document suggested raising the rail to 30V if 554Ω proved insufficient. That was written before the supply became common to the whole system and it is no longer a knob that can be turned. Three separate things block it:

- The specified LRS-150-24 adjusts over 21.6–28.8V. It cannot reach 30V at all, so this is a change of supply, not a trim.

- The switchboard runs on the same rail, and its lamps are incandescent. Filament life goes roughly as the twelfth power of voltage, so 24V to 30V is a 1.25× overdrive and cuts lamp life by about fifteen times. On vintage lamps that cannot readily be replaced, this alone settles it.

- The station boards run on the same rail too. R3 is 330Ω 2W and its short-circuit dissipation goes from 1.75W to 2.73W, past the part. Station loop current rises from 70mA to 88mA, adding about 400mA to the system budget across 22 stations and shifting every supervision margin the switchboard was designed around.

That is the real cost of the common battery decision, and it is worth stating plainly: the rail voltage stopped being a trunk board parameter the moment the switchboard was put on it. Anything that changes the rail now changes vintage equipment that was designed for 24V.

The options that remain are all local to this board:

Before listing them, one thing has to be said clearly because it rules out a whole family of apparent fixes. Compliance and the Qx03-short fault current are two views of the same quantity: the total series resistance in the loop. Call everything other than Rx02 R_extra — Rx05 plus Rx06, 250Ω to Rev 5.40 and 320Ω from Rev 5.41. Both figures fall out of it, and neither depends on where that resistance physically sits or on which part of it the detector senses across:

| **R_extra** | **Compliance at 28.2mA** | **Qx03-short fault current** |
| --- | --- | --- |
| 100Ω | 704Ω | 189mA |
| 150Ω | 654Ω | 134mA |
| 250Ω (as designed to Rev 5.40) | 554Ω | 85mA |
| 300Ω | 504Ω | 72mA |
| 320Ω (Rev 5.41–5.43) | 484Ω | 68mA |
| 253Ω (as designed from Rev 5.44) | 551Ω | 85mA |

So resistance cannot be deleted to buy compliance without giving up fault limiting in exact proportion. An earlier draft of this section listed "move the sense from Rx06 to Rx05" as recovering 150Ω for nothing. It does not, and the row was wrong. Deleting Rx06 takes R_extra from 250Ω to 100Ω, which does give 704Ω of compliance — but it also takes the shorted-Qx03 fault from 85mA to 189mA, putting 3.6W into Rx05 and 54mA into the optocoupler input, past a PC817's continuous rating. The fault-limiting argument that justified keeping Rx05 in §3.2.4 applies just as much to the total.

That leaves only two axes that genuinely move compliance: the loop current, and the feed voltage.

| **Option** | **Loop I** | **Compliance** | **Qx03 (×8)** | **Cost** |
| --- | --- | --- | --- | --- |
| As designed | 28.2mA | 554Ω | 0.44W (3.5W) | — |
| Raise Rx02 to 33Ω | 18.8mA | 956Ω | 0.34W (2.7W) | One resistor, and the fault current is unchanged at 85mA. But 18.8mA may be below what the switchboard's trunk supervisory relay needs to operate — measure that first. |
| Local 48V feed for the loops only | 28.2mA | 1405Ω | 1.12W (8.9W) | An isolated 24→48V module on the trunk board. Contained — touches nothing shared, unlike the common rail — but 8.9W of board dissipation needs real heatsinking. |
| Both | 18.8mA | 2085Ω | 0.75W (6.0W) | Only if the cord circuit turns out to be extreme |

Raising Rx02 is the cheap one and should be tried first, subject to the supervisory relay measurement below. The 48V module is the option that actually has room in it, and it is worth noting that it does not compromise the common battery in any way that matters: the trunk board is the exchange for its own eight loops, and nothing requires those loops to sit at the same potential as the switchboard's talk battery. What it costs is heat, and 8.9W across eight TO-126 packages is the point at which the thermal design stops being incidental.

## **3.3.2 A Simplification Worth Taking Anyway**

The same reasoning suggests a change that is not a compliance fix but is a genuine tidy-up. Since only the total R_extra matters, there is no need for it to be split between a high-side Rx05 and a low-side Rx06. Merging them into a single 250Ω resistor in the ring return leg gives identical figures on every count:

```text
  compliance                554 ohm      unchanged
  Qx03-short fault           85 mA       unchanged
  V_sense at 28.2mA        7.05 V        (was 4.23V across Rx06 alone)
  Rx07 = 1k -> I_opto      5.65 mA       margin 1.8x over the 3.11mA threshold   [wrong - see note]
  fault: 20 mA into Ux01, 1.80 W in the resistor
```

It removes one component per trunk, eight across the board, and keeps the sense node ground-referenced and at low voltage where it belongs. The cost is that the single resistor needs a 3W rating for the fault case where the split version used a 1W and a 2W part, so the choice is really one 3W package against two smaller ones — closer than it looks, since two smaller bodies also spread the heat better.

*Rev 5.41: the Rx07 line above used the same 1.4V LED drop as Rev 5.40's §4.2 and is wrong. With the HCPL3700M's real DC threshold a merged 250Ω needs Rx07 at about 330Ω, not 1k, to turn on every part (§4.2). Rev 5.41 keeps the split and Rx05 at 100Ω.*

Sensing across a high-side Rx05 instead, which is the other way to remove a component, is the one arrangement to avoid. It works electrically — the optocoupler provides the isolation — but it moves the LED and its series resistor out of the ground-referenced logic area and into the high-voltage zone, where their common-mode potential swings with the line during ring. There is no benefit to pay for that.

*Reducing the loop current is the cheapest fix on the list and the one with the hidden dependency. The switchboard's trunk supervisory relay has a minimum operate current that nobody has measured, and if it needs 20mA or more then 18.8mA is not available regardless of what our own detector can see. Measure the relay before the resistor — it also bounds how far the current can be trimmed for any other reason.*

## **3.3.3 Measured Through the Switchboard — 2026-10-04 and 2026-10-05**

Trunk 1, as built at Rev 5.40 (Rx05 100Ω, Rx06 150Ω, Rx07 470Ω), the Analog Discovery across Rx06 (R206) and across Qx03 emitter to collector (Q203), board supply 23.99V. Loop current is Rx06's current plus Ux01's branch. The loop resistance is what the rail leaves after Rx02, Rx05, Dx03, Rx06 and Qx03, divided by that current, taking V_BE as 0.62V and Dx03 as 0.7V. Spare is Qx03's V_EC less 0.5V to keep regulating, divided by the loop current: how much more resistance the source would still drive.

| **Test** | **On the trunk** | **Loop R** | **Loop I** | **Qx03 V_EC** | **Spare** |
| --- | --- | --- | --- | --- | --- |
| 1 | Station board strip 1, wired direct (bench); R3 is 330Ω | 326Ω | 30.4mA | 5.48V | 164Ω |
| 2 | Model 500 desk set, wired direct | 175Ω | 30.1mA | 10.17V | 321Ω |
| 3 | Switchboard cord in the trunk jack — the switchboard seizes the trunk | 181Ω | 29.9mA | 10.09V | 321Ω |
| 4 | Operator connected on the talk key, no station | 134Ω | 29.7mA | 11.55V | 372Ω |
| 5 | Model 500 on the cord, carrying the trunk's loop current; operator bridged, which carries a small DC current | 179Ω | 29.5mA | 10.30V | 332Ω |
| 6 | Model 500 on the cord, operator off the circuit | 211Ω | 29.5mA | 9.36V | 300Ω |
| 7 | Station 1 on the switchboard, off-hook through the cord | 357Ω | 29.9mA | 4.83V | 145Ω |
| 8 | Operator on the trunk, no station: cord in / operator in / after dialling / operator out | 181Ω / 134Ω / **≈440Ω** / 175Ω | ≈30mA | 9.84 / 11.3 / **2.19** / 10.1V | — / — / **56Ω** / — |
| 9 | Station 1 corded to trunk 1: cord in at the trunk / station on-hook / off-hook / operator in / after dialling a 5 / operator out | 177 / 177 / 356 / 200 / **439** / 355Ω | ≈30mA | 10.1 / 10.1 / 4.76 / 9.46 / **2.36** / 4.88V | — / — / — / — / **≈60Ω** / — |

Test 1 checks the method: 326Ω calculated against R3's 330Ω. Every configuration regulates. Tests 8 and 9 (2026-10-05) found the heaviest load: the 551's dial relay pulls in at the first dial pulse and holds until the operator switches out (Mark), and while it holds the trunk sees about 440Ω. The station does not add to it — the operator's key takes the station out of the trunk loop, and the station comes back in series, at about 355Ω, the talking state, only when she switches out — so 440Ω is the worst case whether or not a station is on the cord, and the 650Ω that a station in series with the dial relay would have made does not occur.

What that leaves for each set of values, at the dial relay's 440Ω and 29.9mA:

| **Values** | **Rx05 / Rx06 / Rx07** | **Spare at 440Ω** | **At 31mA, V_BE 0.68V** |
| --- | --- | --- | --- |
| As built (Rev 5.40) | 100 / 150 / 470Ω | 56Ω (measured) | — |
| Rev 5.41–5.43 | 100 / 220 / 150Ω | about 8–17Ω | out of regulation |
| Rev 5.44 | 33 / 220 / 150Ω | about 75–84Ω | about 50Ω |

Rev 5.41's Rx06 raises node B from 4.2V to about 5.6–5.8V at these currents, which costs 45–54Ω of spare; Rev 5.44's Rx05 gives back 67Ω, so every spare in the first table is 13–22Ω larger than measured — test 7 about 160Ω, test 8's worst case about 75–84Ω.

**Stability** (Rev 5.44; §3.2.2, §16). Recorded continuously at 250kHz on Rx06 and Qx03 through a plug-in, the operator switching in, a dialled 0, the operator switching out and an unplug. Each dial make overshoots to 5.3–7.8V across Rx06 for under 40µs as Qx03 comes out of saturation, then settles within 0.1V with no ringing. The plug-in settles once the plug stops bouncing, about 4.5ms. The steady state is 25–29mV peak to peak in every configuration. The key and unplug transients, up to about 12V for a few milliseconds, are contact events, not the loop. No sign of oscillation anywhere; Cx02 stays at 1nF.

## **3.4 Dissipation**

Each trunk has its own current source, so the figures below are per trunk and the ×8 column is only the board aggregate for thermal planning — no single Qx03 ever carries more than one trunk's 28mA. The per-trunk worst case is a dead short at that trunk's jack, which puts the whole compliance voltage across that trunk's Qx03; the board worst case is all eight in that state at once:

| **Element** | **Per trunk** | **×8** | **Notes** |
| --- | --- | --- | --- |
| Qx03 (MJE350) | 0.44W | 3.5W | TO-126, 300V/0.5A. Fit a heatsink — see below. |
| Rx05 (33Ω) | 0.03W | 0.2W | 1W part — rated for the Qx03-short case, not this one (Rev 5.44; 0.08W at 100Ω) |
| Rx06 (220Ω) | up to 0.14W | 1.1W | Up to 0.17W at 31mA. 2W part — rated for the Qx03-short case (§4.2) |
| Relay coils | 0.15W | 1.2W | On the 5V rail |
| Total loops + coils | 0.79W | ≈6.4W | Per-trunk column is one trunk block; ×8 is the board. Ventilate — see §15 |

During an accidental ring the current source holds 28mA while absorbing the extra 127V peak. Integrating over the cycle rather than estimating it: Qx03 sees 3.9W at the peak of the aiding half-cycle and 1.3W averaged, which is the figure that matters thermally. A bare TO-126 in free air is around 83°C/W, so 1.3W is a 108°C rise — too much to sustain. Fit a small clip-on heatsink rather than merely leaving the footprint; at 40°C/W the rise falls to about 52°C, which the part will tolerate for as long as anyone holds a ring key. Note that Rx05 does not help here — it changes peak dissipation by 2% (§3.2.4).

# **4. Loop Seizure Detection**

When the switchboard seizes the trunk, DC loop current flows through Rx06 in the ring return leg. An HCPL3700M in DC-input mode detects the resulting voltage and presents a logic level to the expander. This replaces the LM393 comparator, its threshold divider, hysteresis resistor and zener clamp from Rev 4.4 — the optocoupler supplies the threshold, the hysteresis and the isolation barrier in one part, and it is the part already stocked for the station boards.

This is the only supervisory input on the board. There is one per trunk and nothing else.

## **4.1 Circuit**

```text
  RING (jack) ---- Kx01 pole 2 NC ----+---- Rx06 (220R, 2W) ------ GND
                                      |
                                 Rx07 (150R)
                                      |
                                 Ux01 pin 2 (DC+)
  Ux01 pin 3 (DC-) --- GND
  Ux01 pins 1, 4 --- open, no connection   (selects the DC input pair)
  Ux01 pin 5 --- GND
  Ux01 pin 8 --- +3.3V, with Cx05 (0.1uF) from pin 8 to pin 5, at the device
  Ux01 pin 6 --- Rx12 (4.7k) -- +3.3V
  Ux01 pin 6 --- SEIZE_n ---- MCP23017 U101 Port A bit n
```

The AC and DC input pairs are alternative entry points to the same input buffer and the datasheet specifies each with the other pair open. Leaving pins 1 and 4 floating selects DC operation and bypasses the internal bridge. Note that this is the opposite pin usage from the station board ring detector, which needs the bridge for full-wave behaviour — same part number, different wiring, and worth a clear note on the schematic so the two are not confused during assembly. Cx05 is not optional; the datasheet requires it.

## **4.2 Sizing**

Rev 5.41. The HCPL3700M's DC input is not an LED. It is the input of the threshold buffer, and the datasheet (onsemi HCPL3700M, 2022-03-15) specifies it directly:

| **DC input, pins 2–3** | **Min** | **Typ** | **Max** |
| --- | --- | --- | --- |
| V_TH+, turn-on voltage | 3.35V | 3.80V | 4.05V |
| I_TH+, turn-on current | 1.96mA | 2.40mA | 3.11mA |
| V_TH−, turn-off voltage | 2.01V | 2.50V | 2.86V |
| I_TH−, turn-off current | 1.00mA | 1.20mA | 1.62mA |
| I_IN at V_IN = 5.0V | 3.0mA | 3.7mA | 4.4mA |
| V_IHC3, input clamp at 15mA, pins 1 and 4 open (this board) | — | 12.5V | 13.4V |
| V_IHC1, input clamp at 10mA, pins 1 and 4 tied to pin 3 — not this board | 5.4V | 6.3V | 6.6V |
| Absolute maximum | 50mA average input current, 230mW input power | | |

With pins 1 and 4 open the DC input behaves as about 1kΩ in series with 1V (Broadcom AV02-3699EN, the original HCPL-3700 data sheet), monotonic up to the V_IHC3 clamp near 12.5V. Every part turns on once its input reaches 4.05V, and draws at most 3.11mA doing it. Rx06 is fed by the current source, so the node it sits on is a source of I × Rx06 behind Rx06 itself, and with Rx07 in series the input at worst-case turn-on is

```text
  V_in = Rx06 x (I_loop - 3.11mA) - 3.11mA x Rx07         must be >= 4.05V
```

```text
                          I_loop 26mA (low end, §3.3)   at 28.2mA
  Rev 5.40: 150R / 470R   V_in 1.97V  - never           measured 3.28V, 1.90mA
  Rev 5.41: 220R / 150R   V_in 4.57V  - 0.52V margin    node 5.24-5.54V, 3.0-4.4mA into Ux01
```

Rev 5.40 assumed a 1.4V forward drop and found 6mA and 1.93x margin. Measured on the bench, Ux01 sat at 3.28V and 1.90mA, below every part's turn-on point and above every part's turn-off point: inside the hysteresis band, where the output keeps whatever state it was in. The make transient decided it, which is why seizures and dial makes were missed all-or-nothing, at a rate that differed by part and drifted with temperature (Rev 5.41 change entry).

The same margin as a loop current: a worst-case part (V_TH+ 4.05V at I_TH+ 3.11mA) needs (4.05V + 3.11mA × 370Ω) / 220Ω = 23.6mA to turn on, a typical one 21.3mA and the best 18.5mA, against the 26mA bottom of the current source's spread. Once on, a worst-case part holds down to (2.86V + 1.62mA × 370Ω) / 220Ω = 15.7mA, typical 13.4mA, and every part turns off on a break, which takes the input to 0V. The margin is modest — 9% in current at the worst corner — which is why Rx06 and Rx07 are 1% parts (Rev 5.43): at −5% on Rx06 the 0.52V becomes 0.27V and the floor rises to 24.7mA.

The node voltage at 28.2mA depends on where Ux01's own input settles, which the datasheet bounds through I_IN at 5.0V (3.0–4.4mA): Ux01 takes 3.0–4.4mA at 4.58–5.09V, and node B sits at 5.24–5.54V (4.75–5.29V at 26mA, 5.61–5.92V at 29.9mA). That current is diverted past Rx06, which is why the compliance cost in §3.3 is less than 28mA × 70Ω. A seized trunk does not drop out, and each dial make turns the detector on cleanly.

**Dial contact bounce.** Driven this far past its threshold, the detector follows every bounce of the dial contacts longer than its tens-of-microseconds response; Cx04 hides only bounce-opens shorter than about 0.1ms. One 5ms sample caught inside a bounce would read as a short break inside a digit, or split a break, and spoil the digit. control.md Rev 24's two-sample filter rejects anything shorter than one sample interval. The switchboard's dial was measured through the real cord circuit on 2026-10-05 (control.md Rev 26): bounce only at the start of a break, re-closes of 0.96ms at most, well inside the filter. Do not filter it with a capacitor across Rx06: node B is the RING conductor.

**Faults** (Rev 5.44; Rev 5.43 had them for Rx05 at 100Ω). A shorted Qx03 is a single fault and must not take out anything else. With Qx03 shorted, Qx01's emitter-base junction sits directly across Rx02 and clamps it at about 0.85V, so Rx02 no longer limits the current; Qx01's base carries the excess. The 2N3906 has no base-current rating, so that is probably survivable rather than specified. Into the lightest load measured, 134Ω (§3.3.3), the loop rises to about 63mA and Ux01 takes 9.4mA and 99mW, inside every rating. A shorted Qx03 *and* a dead short across the jack is a double fault: about 118mA, of which Ux01 takes about 33mA and 450mW — past its 230mW absolute maximum, so Ux01 may be destroyed — while Rx07 (0.17W of 0.25W), Rx06 (1.57W of 2W) and Rx05 (0.46W of 1W) survive. Rev 5.43, with Rx05 at 100Ω, kept Ux01 to 150–170mW in that case, but no Rx05 low enough for the dial relay's 440Ω avoids it: 68Ω still gives about 270mW, and only 100Ω, at about 164mW, survives, which fails compliance (§3.3.3). It needs a failed transistor and a short across the jack together; it is accepted, and Ux01 is an 8-pin DIP that can be socketed.

One case does destroy parts: Qx03 shorted while ring is applied by mistake from the switchboard (§5). Nothing then limits the 151V peak, and Ux01 and Rx06 would be lost. It needs a failed transistor and an operator's slip together; it is recorded, not designed for.

A cheaper part would work here. With the fault currents bounded by the current source there is nothing left for a threshold optocoupler to protect against, and a PC817 with Rx07 at 600Ω would give the same 5mA of LED current. The HCPL3700M is specified anyway for one part number across both boards and for the guaranteed threshold limits, but with only eight fitted per board this is a smaller saving than it was and commonality probably wins.

## **4.3 Behaviour During Ring**

Two cases, and they behave differently on purpose.

When the trunk board applies ring, relay pole 2 lifts the ring conductor off Rx06 and returns it to RING_LO instead. Ring current bypasses the sense resistor entirely, the detector reads zero throughout, and Rx06 and Ux01 see nothing. This is why ring trip is handled by cadence rather than by masking — see §7.5.

When ring is applied from the switchboard by mistake, the relay is de-energised and the ring current does flow through the DC feed path — but the current source caps it at 28mA, so the detector asserts on the aiding half-cycles and produces a 20Hz pulse train on SEIZE_n. This does not need masking, because it does not look like a seizure. The debounce in §11.1 separates the two on timing alone, and the pulse train is itself a reportable diagnostic — see §5.2.

The audio path does not disturb either case. Tx01 returns to node B, above Rx06, so the audio loop closes back through the relay to the line and does not pass through the sense resistor. Rx06 carries loop DC only.

# **5. Accidental Ring from the Switchboard**

Ring on a trunk travels one way: the board originates it and the switchboard receives it. There is no ring-down signalling inward and no ring detector is fitted. What the design does have to do is survive the operator applying ring to a trunk by mistake, and — because it costs nothing — notice that it happened.

## **5.1 Survival**

The constant-current feed does essentially all of this work. With the loop current capped at 28mA regardless of applied voltage, an accidental ring is electrically almost indistinguishable from a normal seizure as far as every board component is concerned. Taking each part in the path:

| **Component** | **Exposure** | **Verdict** |
| --- | --- | --- |
| Qx03 | Absorbs up to 137V at 28mA. ~4.1W peak, ~0.7W cycle average. | The only part under real stress. Heatsink footprint, §3.4. |
| Dx03 | ~127V reverse on the opposing half-cycle | 1N4007 at 1000V — no concern |
| Rx05, Rx06 | 28mA, unchanged from normal | No concern. This is what the current source buys. |
| Ux01 | Pulses at 20Hz at normal input current | No concern. No clamp needed. |
| Cx04, Tx01 | Only exposed here — relay is released. 90 × 600/17000 ≈ 3.2V across the primary. | No concern. Cx04 rated 250V and holds the rest. This is the sole case in which Tx01 sees ring. |
| Dx01 | 127V peak, below the 128V standoff | Stays off. Present for genuine transients. |
| Kx01 pole 1 NO | Stands off switchboard ring against a permanently live bus | See note below |

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
  TIP  o----+---- Kx01 pole 1 common
            |
         Dx01 (P6KE150CA, bidirectional)
            |
  RING o----+---- Kx01 pole 2 common
```

The part differs deliberately from the station board, and station §4.1 will need correcting where it states the two boards use the same TVS. The station board uses a P6KE120CA, which has a 102V standoff and breaks down between 114V and 126V. On a station that is acceptable, because ring arrives only from the switchboard and mild conduction on the peaks is a protection function. On the trunk board we generate the ring ourselves, at 127V peak nominal and up to 141V peak no-load, so a 120V-class part would conduct on every cycle of every ring — loading the generator, distorting the waveform and dissipating power for no benefit.

The P6KE150CA has a 128V standoff, breaks down between 143V and 158V, and clamps at 207V. It stays out of the way of our own ring, and it also stays out of the way of an accidental 90V ring from the switchboard, which is correct: that event is already bounded by the current source and does not need clamping. What remains for the TVS is genuine transients — cord plugging, relay switching elsewhere on the frame, and whatever arrives down a long cable run.

## **6.1 Why the TVS Stays at the Jack**

Dx01 is now the only component on the trunk that is not behind a relay contact, so the obvious question is whether it should move behind them too, across the transformer primary at node A and node B. It should not, and the reasons are worth recording because the answer is the opposite of the one for Tx01.

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

- Clamping degrades with series inductance. A TVS wants minimum lead length and loop area to the port it protects. Routing the clamp path through two relay contacts and the associated trace adds enough inductance to blunt it against fast transients — cord-plug arcing and static off a long cable run — which are precisely the events a slower series element like Cx04 does nothing about.

Behind the contacts there is also nothing left to clamp. Tx01's primary carries no DC because Cx04 blocks it, so opening the contacts produces no kick from the transformer, and the current source, Rx05 and Dx03 are not inductive. The board side of the relay stores essentially no energy.

One residual exposure is worth naming rather than protecting against. Cx04 is a low impedance to a fast transient — 0.34Ω at 1MHz — so a spike that the jack TVS has clamped to 207V still passes through Cx04 and appears across Tx01's primary at close to that amplitude. A 600Ω telephone transformer's primary insulation handles 207V without difficulty, and the energy behind it is sub-millijoule, so no second suppressor is specified. If a transformer is ever found failing in service rather than on the bench, a bidirectional TVS of around 200V across the primary is the fix, but do not fit one pre-emptively — it would sit across the audio path for the whole life of the board to solve a problem that has not been observed.

# **7. Ring Injection**

## **7.1 Ring Bus Interface**

Ring voltage is generated on a separate board, designed separately, and arrives at the trunk board as a two-wire bus. Nothing in this document depends on how it is generated. What the trunk board requires of it:

| **Parameter** | **Requirement** | **Notes** |
| --- | --- | --- |
| Waveform | 20Hz sine | Generator Rev 20: ESP32 LEDC PWM, 40kHz carrier, H-bridge into T1. Exactly 20.000Hz. |
| Amplitude | 90V RMS nominal | 95–100V RMS no-load per generator §14. Trunk board tolerates 85–100V RMS without change. |
| Reference | Floating pair | Confirmed: the switchboard breaks both legs too. Needs a high-impedance common-mode reference — see §7.1.1. |
| Load | (N trunks + switchboard) × I_ring | Shared source; the switchboard rings stations from the same generator — see §7.6 |
| Connector | J102, 2-pin, 250V | Physically separate from all other connectors |
| Enable | None on this board | The generator is enabled by GPIO14 (SD, via a 5V buffer) and the GPIO4 manual switch on the generator board. The trunk board has no part in it — see §7.6. |

## **7.1.1 Sharing the Generator with the Switchboard**

The same generator supplies the switchboard's own ringing, so the operator rings stations from it as well. Three consequences, none of which change the trunk board circuit but two of which change what the document previously claimed.

First, the bus is genuinely floating and stays that way. The switchboard isolates its ring supply from the line circuits with DPDT switches, breaking both legs when not ringing — which is the signature of a floating source, since a supply with one leg bonded to battery would only need single-pole keys. An earlier draft of this section predicted the opposite and it was wrong. Both ends of the system therefore treat the bus identically: two poles, both legs broken, complete isolation when idle. The original floating-pair specification stands, and pole 2's justification in §7.2 is restored in full — it keeps ring current out of the ground plane as well as lifting Tx01's cold end.

It also means the bus carries no load at all when nothing is ringing. Neither end presents so much as a leakage path, so the generator idles into an open circuit and its no-load output voltage — measured at 95–100V RMS, 141V peak — is what sits on the bus for most of the session. Every clearance and standoff figure on this board should be taken against that number rather than the 90V RMS nominal.

*A fully floating bus with both ends open has no defined common-mode potential, so it will drift on leakage and stray capacitance. That is not dangerous at these energies but it makes bench measurements confusing and leaves creepage stress unpredictable. Ask the generator board for a high-impedance reference — 1MΩ from each leg to ground, or a grounded centre tap if the transformer has one. That pins the common mode near zero while leaving the pair effectively floating at signal levels, and it costs two resistors.*

Second, the generator can no longer be gated on trunk ring. The operator must be able to ring a station at any moment, so the generator has to be running whenever the system is up — see §7.6.

Third, the station boards are a very light ring load and this is good news for the generator budget. A station's ring detector draws about 4mA RMS through its 20kΩ dropper (station §3.4), against the 20mA or more a real telephone ringer would take. Even with several stations being rung the switchboard side contributes little; the trunk side, loading the switchboard's own trunk circuits, remains the unknown.

## **7.2 Relay Contact Configuration**

One DPDT relay per trunk, de-energised for normal operation so that loss of power or loss of the controller cannot leave ring on a line.

```text
  NORMAL (de-energised, NC contacts):
    Pole 1 NC:  node A <---- current source, Rx05, Dx03 [DC loop feed to TIP]
    Pole 2 NC:  node B <---- Rx06 -> GND                [loop return, sensed]
                Tx01 spans node A - node B              [audio in circuit]

  RINGING (energised, NO contacts):
    Pole 1 NO:  RING_HI -------------------> TIP       [ring applied]
    Pole 2 NO:  RING ----------------------> RING_LO  [ring return, bypasses Rx06]
                node A and node B both open             [Tx01 lifted clear, both ends]
```

Pole 2 does two jobs at once, which is why the transformer does not need a pole of its own. Switching the ring conductor from Rx06 to RING_LO keeps ring current out of the sense resistor and out of the ground plane, and because Tx01 hangs off node B — the board side of that same contact — throwing the pole also disconnects the transformer. Pole 1 disconnects its other end. Tx01 therefore sits behind a double break during ring, like the station board transformer, and it costs nothing to have.

Both poles carry line voltage. Treat the entire relay except its coil pins as part of the high-voltage zone.

## **7.3 Relay Driver**

```text
  MCP23017 U101 Port B bit n -- Rx01 (1k) -- Qx02 base (2N2222A)
  Qx02 base -- Rx03 (10k) ---- GND                    [see note below]
  Qx02 collector -- Kx01 coil (-)
  Qx02 emitter -- GND
  Kx01 coil (+) ---- +5V
  Dx02 (1N4148) flyback: anode to Qx02 collector, cathode to +5V
```

Base drive is (3.3 − 0.7) / 1kΩ = 2.6mA against a 29.9mA coil, a forced beta of 11.5, which saturates the 2N2222A hard. The expander sources 2.6mA comfortably against its 25mA per-pin limit, and because Qx02 switches the low side of a 5V coil the 3.3V logic rail creates no level-shifting problem.

Qx02 is a 2N2222A as of Rev 5.4, replacing the 2N3904, matching station Rev 3.8 §5.2. The two boards share this part deliberately. Order a TO-92 part with EBC pinout and confirm it on the datasheet for the exact orderable part, not on the generic 2N2222A number. The original 2N2222A is a TO-18 metal can and will not fit this footprint at all; TO-92 equivalents such as the onsemi PN2222A and P2N2222A are EBC, but TO-92 parts sold as 2N2222A vary between EBC, CBE and ECB by manufacturer. The footprint is committed at layout and there are 24 of these, so settle it before the boards are ordered.

*Rx03 is an addition over the station board driver and it is not optional here. The MCP23017 powers up with every pin configured as an input, so Port B floats between reset and firmware configuration. On a station board a floating driver at worst closes a loop; on a trunk board it puts 90V on a line. Rx03 holds Qx02 off through that window and through any subsequent expander reset. The same resistor would be worth retrofitting to the station boards.*

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

- Those two measurements now size three things rather than one: the concurrent-ring cap below, this board's F101, and the generator's @F101@ on the switchboard branch. The per-trunk figure sets ours, since our F101 carries every ringing trunk; the per-station figure sets the generator's, since its J102 branch carries only what the operator's ring key draws. Generator Rev 28 §7.6 sizes that one at 250mA on the same estimate this section calls unmeasured.

- Set a concurrent-ring cap in the firmware from those measurements — control.md §8.4, where the cap lives; four is the starting value there. Trunks beyond the cap queue rather than ring, with headroom for one station ring on top.

- Nothing is required of the trunk board for generator control. With the ESP32 now resident on the generator board (generator Rev 20 §3), enabling is entirely local to it — GPIO14 drives the IR2104 SD pins through a 5V buffer and GPIO4 reads a manual master-enable switch. The earlier proposal for a RING_GEN_EN line from the controller to the generator is withdrawn; there is no longer a wire to run.

What the generator enable cannot be, now that the generator is shared, is a per-call gate. Rev 5.0 originally proposed holding the bus dead unless a trunk was ringing, which would have kept 90V off eight relay contacts for most of the session. That is no longer available: the operator's ring key can be pressed at any moment and the firmware has no way to see it coming, so the generator must run whenever the system is up. Generator Rev 20 §1 states this directly: when enabled it runs continuously, and cadence for individual trunks and stations is decided elsewhere. The GPIO4 master enable is a maintenance and shutdown control, not a per-call one.

The practical consequence is that the ring bus and both relay NO contacts are live for the whole session. This is why §15 says to assume the bus is energised whenever the system is powered, and it removes the mitigation previously offered for the contact-standoff case in §5.1. It costs almost nothing in power, though: both the switchboard and the trunk board isolate both legs when not ringing, so a generator running with nothing being rung is driving an open circuit and dissipates only its own quiescent load.

# **8. Balanced Audio Interface and External Connectors**

Audio is coupled bidirectionally through a 600Ω:600Ω isolation transformer whose secondary is left fully floating, producing a balanced signal on the equipment side. The primary sits between the board-side ends of the two relay NC contacts, so it is in circuit whenever the relay is released — which is every state except the ring-on interval — and lifted clear of the line whenever ring is applied.

## **8.1 Primary Circuit**

```text
  TIP  ---- Kx01 pole 1 NC ---- node A ---- Cx04 (0.47uF, 250V) -- Tx01 primary (+)
  RING ---- Kx01 pole 2 NC ---- node B ----------------------------- Tx01 primary (-)

  node B ---- Rx06 (220R) ------ GND        [DC return and sense; audio does not
                                             pass through it - see below]
```

Placing Tx01 behind the contacts rather than across the jack is the right way round and it is free. Ring that the board applies deliberately — which is every incoming trunk call, repeatedly, for the life of the installation — never reaches the transformer or Cx04 at all. The only remaining exposure is an accidental ring from the switchboard with the relay released, and Cx04 covers that: its reactance at 20Hz is about 17kΩ, so the voltage across the 600Ω primary is 90 × 600/17000 ≈ 3.2V. The 250V rating on Cx04 is required for that case, since Cx04 holds the rest of the ring voltage across itself.

Rx06 does not load the audio, which is what makes this placement free rather than a compromise. The audio loop runs TIP → pole 1 → node A → Cx04 → Tx01 → node B → pole 2 → RING and closes back through the switchboard; Rx06 is a stub from node B to ground carrying loop DC. The only route from node A to ground is through the current source, which is close to an open circuit at audio frequencies — the same property that makes the crosstalk figure in §12.4 work.

At 0.47µF the −3dB point against the 600Ω primary is about 565Hz, which is inside the voice band and produces some low-end rolloff. If that matters on trunks, increase Cx04 to 2.2µF for −3dB at 120Hz, keeping the 250V rating. The trade is smaller than it was before this change, because Cx04 now sees ring only in the accidental case — but in that case a larger Cx04 puts proportionally more across the primary, about 15V rather than 3.2V, so do not increase it without checking the transformer can take that.

## **8.1.1 Switching Transient**

One artifact comes with the move and it is worth writing down rather than discovering on a scope. Cx04 sits at a different DC potential in the two relay states, so each transition pushes a brief current through the primary:

```text
  seized:   node A 16.5V   node B ~5.4V   Cx04 holds ~11V    (Rev 5.43; 4.2V and 12.2V at Rev 5.40)
  ringing:  node A 23.8V   node B 0.0V    Cx04 holds 23.8V

  step on each transition = 11.6V  ->  19mA peak into the 600R primary,
  decaying with tau = 282us
```

Node A rises during ring because the current source is left open-circuited by pole 1 and saturates toward the rail; node B falls to ground because Rx06 no longer carries loop current. The result is a click on that trunk's audio channel at each relay operate and release — twice per ring cadence period, so roughly once every three seconds while a trunk is ringing.

This is harmless in the voice path, because nobody is connected to a trunk that is being rung. It can briefly disturb the pilot FFT on that channel, so have the host suppress pilot detection on a trunk while its ring topic reads on, plus one FFT block either side. The host already knows the ring state and the transient is two orders of magnitude shorter than the 85ms block. Do not try to fix it in hardware: a bleed resistor at node A large enough to hold the node down would be small enough to unbalance the audio.

## **8.1.2 Carrier Residue and the Pilot Comb**

Generator Rev 20 synthesises the ring waveform with a 40kHz PWM carrier through an H-bridge and T1. That carrier is not on the trunk board's problem list during normal ringing, because the relay has lifted Tx01 clear of the line. It is on the list during an accidental ring, when the relay is released and Tx01 is connected — and the numbers put it somewhere awkward.

```text
  Cx04 at 20 kHz-decade extremes: 17 kohm at 20 Hz   ->   8.5 ohm at 40 kHz
  T1 leakage 14.6mH at 40 kHz:    3.7 kohm referred to primary
                                  127 kohm referred to secondary
  divider onto the Tx01 branch:   about -46 dB

  40 kHz sampled at 48 kHz folds to 8.0 kHz
  trunk pilot comb occupies       8.250 - 8.906 kHz
```

Cx04 provides no protection at all here. Its whole purpose is to be a high impedance at 20Hz, which makes it 8.5Ω at 40kHz — effectively a short into Tx01's 600Ω primary. What does the filtering is T1's leakage inductance, which the generator design measured at 14.6mH and which presents about 127kΩ referred to the secondary, giving roughly 46dB of attenuation before the residue reaches the transformer at all.

That is probably enough, and the Ferrofish's own decimation filter should reject whatever survives long before it can fold. But 40kHz against a 48kHz sample rate lands at 8kHz, which is the doorstep of the trunk pilot comb, and a spurious tone at 8kHz is the single worst place in the spectrum for this system to acquire one. The margin is almost certainly there; the consequence of it not being there is a trunk that mis-identifies itself.

This is a measurement, not a design change. Apply ring to a trunk from the switchboard with the relay released, capture that trunk's A32 input, and look at the 8kHz region. If anything shows, the fix is on the generator board — an output filter across the secondary — not here, because nothing on the trunk board can distinguish it from signal once it has arrived. Suppressing pilot detection during ring, which §8.1.1 already asks for on transient grounds, does not help in this case: the relay is released, so the board does not know ring is present until the seizure detector reports the 20Hz pattern.

## **8.2 Receive and Transmit**

```text
  Tx01 secondary hot ---- Rx08 (1k) - A32 ANALOG IN (+)
  Tx01 secondary cold -- Rx09 (1k) -- A32 ANALOG IN (-)

  A32 ANALOG OUT (+) ---- Rx10 (1k) -- Tx01 secondary hot
  A32 ANALOG OUT (-) ---- Rx11 (1k) -- Tx01 secondary cold
```

There is no third connection at the transformer. Revisions through Rev 5.24 showed a Tx01 screen or shield earthed to chassis; the TY-311P is a four-pin part and has no such terminal, so the line described something that could not be built. The secondary is unreferenced at this board by design, and §8.4 covers what happens to the D-Sub ground pins, which is the real grounding decision on the equipment side. RV1 is deleted as of Rev 5.13, matching station Rev 3.16 §7.4. The transmit signal is voice audio summed with the trunk's pilot tone in software before the DAC. The A32's switchable reference levels and recallable digital trim cover what the pot was for, and a dual-gang trimmer in a through-hole package is not a catalogue part — the full reasoning is in the station document. Eight footprints come off this board.

## **8.3 Transformer Selection**

Same requirement as the station board — usable response to about 9kHz, which ordinary 600Ω:600Ω telephone and line-matching transformers reach comfortably. Specialty wideband parts are not needed.

One difference is worth attention at measurement time. The trunk pilots occupy 8250.00–8906.25Hz, the top eight slots of the comb, so the trunk transformers work at the highest frequencies in the system and will show the most insertion loss. Add the operator tone at 9000.00Hz (bin 768, generator §15) and 9000Hz becomes the frequency to sweep against, not 8906.25Hz — a trunk circuit carries it whenever the operator is patched to that trunk. Standard telephone transformers begin rolling off above roughly 4kHz, so expect a few dB more here than on station 1. Sweep one part from 300Hz to 10kHz and record the loss at each of the eight trunk pilot frequencies specifically, then pre-emphasise per-trunk injection level in software to equalise received magnitudes. The ratiometric threshold in station §8.4 tolerates unequal levels, so this is refinement rather than necessity — but the trunks are where it will matter first if it matters anywhere.

Measured, 2026-08-24, Analog Discovery 3 network analyser, 10Hz to 100kHz. Triad TY-311P: passband loss about −5.5dB, flat from roughly 400Hz to 10kHz, no rolloff whatever at 9kHz, and still only −8dB at 100kHz. Low end −8.5dB at 10Hz. Driven at 200mV.

Triad SP-70, swept 2026-08-20: passband loss about −7dB, likewise flat through the comb and past the operator tone. Low end −18dB at 10Hz. Driven at 2V.

The two low-frequency figures are not comparable — 2V against 200mV is a 20dB difference in drive, and a small core at 10 to 20Hz is exactly where level starts to matter. Some or all of the SP-70's steeper low end is likely the drive level rather than the part. The passband figures are comparable and the 1.5dB difference between them tracks the winding resistances: 38/53Ω for the TY-311P against 72/92Ω for the SP-70.

The TY-311P is specified. It has lower insertion loss, it is flat where the comb and the operator tone live, and at roughly $5.67 against $20.49 it saves about $310 across the 24 needed. Its datasheet band of 300Hz to 3.5kHz understates it considerably — that specification describes a telephone application, not the limit of the part.

The low-frequency difference is close to irrelevant in circuit. Cx04 at 0.47µF puts a 565Hz corner ahead of the primary and contributes about 29dB of attenuation on its own at 20Hz, dominating either transformer. The one case where it becomes interesting is §9.4's option of raising Cx04 to 2.2µF if trunk audio sounds thin: that moves the corner to 120Hz and lets more 20Hz ring leakage into the audio path, and the SP-70 would have been rejecting more of it. Those two decisions are linked, and if Cx04 is ever raised the low end is worth re-measuring rather than assumed.

One sample has been swept. Sweep two or three of the production quantity before committing all 24 to boards. What matters is not the absolute loss but the spread between units at 9kHz: if they track within a dB, one detection threshold serves every channel; if they do not, that is a per-channel calibration problem in the detector rather than an analog one, and it is much cheaper to learn on the bench than after assembly.

Incidental, but worth carrying to layout: the two sweeps showed opposite phase in the passband, around 0° for one and 180° for the other, because one was connected dot-to-dot and the other reversed. Not a fault in either part. Make the footprint's dot convention explicit on the silkscreen and wire all 24 the same way — a single reversed transformer inverts one circuit's audio and nothing else, which is the kind of fault that survives a long time before anyone notices.

## **8.4 Audio Connectors — J104, J105**

Audio terminates in two D-Sub25 connectors in TASCAM analog pinout, mating with the A32 through a standard male-to-male analog loom with no breakout: J104 carries the board's eight outputs to the A32 analog input connector for channels 25–32, and J105 carries the A32's eight analog outputs back to the board. Trunk n is channel n on the connector and A32 channel 24+n. Both are female sockets — see §13.1, which corrects an earlier error in this document.

| **Board channel** | **1** | **2** | **3** | **4** | **5** | **6** | **7** | **8** |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Hot (+) | 24 | 10 | 21 | 7 | 18 | 4 | 15 | 1 |
| Cold (−) | 12 | 23 | 9 | 20 | 6 | 17 | 3 | 14 |
| Ground | 25 | 11 | 22 | 8 | 19 | 5 | 16 | 2 |

Pin 13 is not connected. The TASCAM analog and AES/EBU digital pinouts differ and breakout cables are not interchangeable; the A32 analog connectors need the analog variant. Confirm the pinout against the converter manual before making up looms — it is standard TASCAM on the analog ports, but it costs nothing to check and a mis-made 25-way loom is tedious to trace.

The eight ground pins on each connector are left floating at this board, on the assumption that they are commoned at the A32. Tx01 is the isolation barrier and nothing in the secondary circuit needs board ground: Rx08 to Rx11 run between the winding and the converter's pins, and board GND appears nowhere in that loop. The converter's own output stage, driving through Rx10 and Rx11, DC-references the secondary from its end.

Grounding them at both ends closes a loop that encircles the rack: board GND to the PSU, PSU to mains earth, earth to the A32 chassis, chassis to the cable ground pins, and back to the board. Eight audio channels sharing that loop is the classic way to acquire mains hum and its harmonics. Grounding at one end only is the standard answer, and the A32 is the end that should have it.

There is a real argument the other way, which is why the decision gets a footprint rather than a piece of copper. Tx01 has interwinding capacitance and its primary sits on a line that carries 90V RMS ring. Common-mode current through that capacitance has to return somewhere, and with the secondary unreferenced at the board it returns down the snake to the converter's input. The A32's common-mode rejection should absorb it. Ring transients are fast, and the word doing the work in that sentence is "should".

So: tie the eight ground pins of each D-Sub together at the board into a single node, and take one 0Ω link footprint from that node to board GND. Leave it unstuffed. If the system hums, it stays out. If ring events produce clicks or thumps in the captured audio, fit it and listen again. A 100Ω resistor in parallel with 10nF is the middle position — it gives transients and RF a path to ground while presenting an open circuit to 50/60Hz loop current — and the same footprint takes it.

Silkscreen the link position and what fitting it means. An unstuffed 0Ω whose purpose is undocumented gets fitted by whoever populates the next board, on the reasonable assumption that a missing part is an oversight.

*As built (rev 2 board): one link footprint per D-Sub, R102 for J104 and R103 for J105, both left unfitted (Rev 5.43; Rev 5.42 said fitted, which was wrong). The ground pins float at this board, as designed, and the cable shields are earthed at the A32 end alone. If ring events click in the captured audio, fit them, 0Ω or the 100Ω ∥ 10nF middle position.*

This keeps the station and trunk boards on the same audio connector, as station §6 specifies, and removes the second cabling scheme that an RJ45 audio interface would have introduced.

## **8.5 Trunk Line Connectors — J7A101, J7B101**

The eight trunk pairs leave on two shielded RJ45 jacks, four trunks per connector, one twisted pair per trunk. RJ45 is used for nothing else on this board, and should be used for nothing else anywhere in the system: the connector type itself now signals hazardous voltage — see §8.6.

| **Pin** | **T568B colour** | **J7A101** | **J7B101** |
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
| J104, J105 | D-Sub25 female | Balanced audio, line level. Female sockets, mating a male-to-male loom — see §13.1. |
| J101 | 6P6C modular | I²C, 3.3V logic |
| J7A101, J7B101 | RJ45 | Trunk tip/ring, 141V peak |
| J103, J102 | Screw terminal / 2-pin | 24V supply and the ring bus |

An earlier revision put audio, I²C and trunk lines all on RJ45, which made a mis-plug the most likely way the finished system would be destroyed — a trunk line into the I²C jack puts 141V onto SDA and SCL, shared with every station board and the master. Distinct connector types remove that failure mode at the design stage rather than managing it with labels, and no cable can now be crossed between classes and still seat.

One residual case survives and is worth naming, because it is the one people are surprised by: a 6P6C plug physically fits an RJ45 jack. It is narrower, so it lands on the middle six positions and leaves the outer two unmade. An I²C cord can therefore be pushed into J7A101 or J7B101, where it would find trunk tip and ring conductors. The reverse is impossible — an RJ45 plug will not enter a 6P6C jack — so the hazard is one-directional and only needs one control.

- Keep the TVS array on SDA and SCL — a Littelfuse SP721APP, the same part on all three board types. It fully covers the case where the trunks involved are idle, because the current source caps each at 28mA, which a 3.3V array absorbs without difficulty. If one of those trunks happens to be ringing, 141V arrives with no current limit and the array fails short — which pulls the bus down and halts the system, rather than passing 141V to three expanders and the master. A failure that stops the game is a far better outcome than one that destroys the control system, and the array costs about 3pF against a bus with a large timing margin (§10.4). Fit C18, 100nF, across TVS101 pins 8 and 4 at the device — not on the rev 2 board, which waits for rev 3 (Rev 5.42). The SP721 does not shunt to ground — it conducts the transient from the IN pin into V+ — so V+ has to be able to source that current locally, or it lifts during the event and the clamp degrades exactly when it is working. TVS101 belongs at J101, which is the far end of the board from U101 and the LDO, so C101 and C108 are no help. Only the V+ side needs it: V− is pin 4 and goes straight to GND. The series resistor the datasheet also mentions is not fitted — that note covers automotive load-dump and reverse-battery conditions, and series resistance in the V+ feed would raise the clamp’s dynamic impedance, which is the opposite of what is wanted here.

- Colour-code cables and jacks consistently across every board — the trunk lines in one colour, the I²C cords in another. This is now a convenience rather than the primary control, which is the right place for it to be.

- Group J102, J7A101 and J7B101 at the high-voltage edge of the board with J104, J105 and J101 at the opposite edge, and mark the boundary on the silkscreen.

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

Pilot injection is continuous except during the ring-on interval, when the relay lifts Tx01 off the line and the trunk's pilot is absent from the pair for 2 seconds in every 6. This costs nothing in practice — a trunk that is being rung is by definition not yet patched to anything, and the pilot returns within one FFT block of the relay releasing. It does mean pilot detection on that channel should be suppressed while the trunk is ringing, which §8.1.1 asks for anyway on transient grounds.

# **10. Digital Control — MCP23017**

## **10.1 Expander Allocation**

Eight trunks need two signals each — seizure in, ring enable out — which is exactly sixteen pins and therefore exactly one expander. The trunk board fits the same single-expander pattern as a station board, and for the same reason: one input and one output per circuit.

| **Device** | **Pins** | **Function** |
| --- | --- | --- |
| U101 (0x23) | Port A 0–7 | SEIZE_1..8 — from Ux01. External pull-ups fitted (Rx12), so leave GPPU off. Set IPOL to invert the active-low sense. |
| U101 (0x23) | Port B 0–7 | RING_EN_1..8 — outputs, drive high to energise the ring relay |

U101 is exactly full, with the same consequence station §9.1 notes: any additional per-trunk signal would need a second expander, which consumes a second I²C address. None is fitted or planned, and the rev 2 board has no footprint for one (Rev 5.42). Two candidates were once in mind — a ring bus current monitor to confirm the generator is live, and per-trunk status LEDs — and either would now be a board revision.

## **10.2 Addressing**

0x23, matching generator Rev 20 §2.2 and station §9.2. Nothing about the address plan changes.

| **Address** | **Board** | **Function** |
| --- | --- | --- |
| 0x20 – 0x21 | Station boards 1–2 | Mandatory expander, one per board |
| 0x22 | Station board 3 | Mandatory expander |
| 0x23 | Trunk board | U101 — seizure sense and ring enable |
| 0x24 – 0x27 | — | Unused. No board carries a second expander (Rev 5.42). |

Generator Rev 20 §2.2 and station Rev 3.15 §9.2 both treat the trunk board address as fixed, in contrast to the DIP-strapped station boards, and that is the right call — there is only one trunk board and nothing to distinguish. U101's A0 and A1 are tied to +3.3V and A2 to GND in copper, giving 0x23. Earlier revisions asked for 0Ω link footprints so the address could be moved without cutting the board; the rev 2 board is hardwired, so moving the address is a track cut (Rev 5.42).

*The startup scan is driven from the configured station board count (control.md §4.2). With three station boards built the list is 0x20, 0x21, 0x22 and 0x23. Generator Rev 13 hard-coded 0x20–0x23 when only two station boards existed, which logged a phantom missing device at 0x22 on every boot; the configured count is what keeps that from recurring if a board is ever pulled.*

## **10.3 Power-On and Reset State**

The MCP23017 comes out of reset with IODIR = 0xFF, every pin an input. Port B therefore floats until firmware configures it, and on this board a floating Port B bit means an undriven ring relay coil. Rx03 (§7.3) defines the state through that window. Tie the RESET pin high through 10kΩ rather than leaving it floating, and bring it to a header so the ESP32 can assert a hardware reset if the bus ever needs recovering — a wedged expander holding a ring relay closed is the one failure on this board that a firmware watchdog alone cannot clear.

## **10.4 I²C Bus — J101, RJ11**

The I²C master is the Olimex ESP32-POE-ISO on the ring generator board (generator Rev 20 §3). It reaches the bus on GPIO13 (SDA) and GPIO16 (SCL); the GPIO16/GPIO17 pair named in earlier revisions was wrong, because GPIO17 clocks the Ethernet PHY — generator Rev 14 §3.1. The bus daisy-chains from there through the station boards and terminates here. The generator board carries one connector, each station board two, and the trunk board — last in the chain — one. All three station boards are built and in the chain ahead of this board.

The bus uses a 6P6C modular connector, distinct from the RJ45 used for trunk lines and the D-Sub25 used for audio. Three signal classes, three connector types, and no way to cross them with a cable that seats properly.

```text
  ring generator ---[RJ11]--- station 1 ---[RJ11]--- station 2 ---[RJ11]---[station 3]---[RJ11]--- TRUNK
   (master, 1x)              (2x, thru)          (2x, thru)      (capacity)       (1x, end)

   J101, 6P6C, ~600mm total bus length
```

| **Position** | **Signal** | **Pair** | **Connection on this board** |
| --- | --- | --- | --- |
| 1 | — | 3 (1–6) | /RESET — expander hardware reset from the generator board, paired with GND at position 6 |
| 2 | SCL | 2 (2–5) | U101 pin 12 |
| 3 | GND | 1 (3–4) | Board ground — SDA return |
| 4 | SDA | 1 (3–4) | U101 pin 13 |
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

*Fit no pull-ups on this board. Generator Rev 20 §4.4 places the single 2.2kΩ pair on the generator board and states that station and trunk boards must not fit their own. The rev 2 board has no pull-up footprints at all, which settles the risk the earlier DO NOT FIT footprints carried — a bare footprint invites someone to populate it (Rev 5.42).*

There is no INT line, which is correct because this board polls rather than using interrupt-on-change (station §9.5). The reason is sharper here than on a station board: during an accidental ring the seizure input produces a 20Hz pulse train, so one trunk being rung into would generate 40 interrupts per second for something that is not even a state change. Polling Port A of three expanders at 200Hz — four with the third station board fitted — costs roughly 6% of a 100kHz bus and gives the debounce in §11.1 the sample density it needs.

The single expander here adds about 10pF. With 2.2kΩ pull-ups and roughly 50pF of total bus capacitance the rise time is about 94ns against the 1µs I²C budget, so at 600mm no bus buffer is needed and the P82B96 footprint recommended in earlier revisions of this document can be dropped.

Positions 1 and 6 of the 6P6C carry /RESET and its return, from GPIO5 on the generator board to pin 18 of U101. Generator §4.7 owns the design and station §9.4 covers what it means for a board that consumes it; two points are specific to this board.

R101, a 10kΩ pull-up to +3.3V, holds /RESET here as on the station boards; note that this is the opposite of the DO NOT FIT rule for the I²C pull-ups. The reasoning is in station §9.4: a static line driven by a CMOS output does not care about three pull-ups in parallel, and an unplugged board must not leave pin 18 floating. /RESET also takes a third input of TVS101.

The consequence to weigh is sharper here than on a station board. A reset returns the expander to IODIR = 0xFF, which releases every ring relay — Rx03 (§7.3) is what holds the drivers off through the window, and that argument is unchanged. But releasing a ring relay mid-cadence opens the contacts at an arbitrary point in the 20Hz waveform rather than at a cadence boundary, which is the click §9.5 quantifies and the switching discipline §7.6 exists to avoid. Never assert /RESET while ring is applied. At startup, and on a detected bus fault with ring already inhibited, it is exactly the right tool.

Filter /RESET at U101: C19, 100nF from pin 18 to GND, as close to the pin as the layout allows (Rev 5.40). The rev 2 board carries it as a bodge; at rev 3 it takes C110. The line runs the length of the bus cord and every board with only 10kΩ pull-ups holding it up, and the MCP23017 resets on a pulse of about a microsecond. Before C19 a ring relay switching on this board reset the expander intermittently — every trunk then reads seized, since IPOL is cleared — and with it fitted not once. With R101 it is a 1ms time constant, inside control.md §6.2's 2ms pulse and 5ms settle.

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

At 1kHz a well-bypassed 24V rail presents on the order of 10mΩ. Audio on one trunk's tip reaches that rail through the current source and Rx05, which together are a very high impedance — the current source in particular is essentially an open circuit to signal, which a resistive feed was not. Crosstalk to the rail is therefore below −90dB before any inductor is considered, and 47mH contributes only 5.9Ω at 20Hz and 295Ω at 1kHz against that. Eight bulky inductors buy nothing.

What actually matters is that the rail is genuinely low-impedance across the audio band, and that the eight sense-resistor returns do not share ground impedance:

- 1000µF electrolytic plus 100nF film at the board 24V input. Nothing local to each trunk.

Cx01, a 100µF electrolytic at each current source, was deleted from the design at Rev 5.23 — but the rev 2 board carries it, fitted on every strip (Rev 5.42). It was specified alongside the 1000µF when L1 came out, and it was never asked what it was for. The answer is very little. A current source rejects supply variation by construction — that is its defining property — so the usual reason for local bulk, holding a rail stiff for a load that disturbs it, applies at neither end: this load does not disturb the rail and does not care if the rail is disturbed. There is no fast transient on 24V either. The relay coils are on the 5V rail and the ring contacts switch the ring bus; the only 24V event is a 28mA step at loop closure, on a switchhook timescale.

Nor is it needed for the crosstalk argument above, which turns on the current source presenting roughly 600kΩ to signal and puts the figure below −90dB before any bypassing is considered. Cx01 was belt-and-braces on a problem already solved by the topology.

Deleting it has a benefit beyond the eight parts. Eight 100µF plus the 1000µF and the 47µF is about 1.85mF of capacitance for the LRS-150-24 to charge through F102 at power-on — roughly 0.3A²s of I²t against a 500mA slow-blow, which is uncomfortably close for something that happens every time the rack is switched on. Removing 800µF takes most of that away. A local ceramic was considered as a middle course and rejected for the same reason as the electrolytic: a decoupling capacitor with nothing to decouple is a part fitted out of habit.

*As built, with Cx01 fitted: the board has powered up repeatedly on the bench, including through a 0.1A supply current limit, without opening F102. The inrush concern above has not appeared; the case for leaving Cx01 off at rev 3 rests on the part count and the topology argument.*

The station board never had the equivalent and does not need one. Its per-station capacitors are the 10µF relay-coil reservoirs on the 5V rail, which serve a real inductive load, and its single 1000µF at the 24V input earns its place because a 330Ω resistive feed does put audio-band current into the shared rail. Station §10.4 records a related correction — 100µF per relay coil reduced to 10µF because a switching module has a maximum output capacitance. Distributed bulk specified once and never re-examined is a recurring theme in this design and worth watching for.

- The eight Rx06 ground returns must not share trace impedance. Audio does not pass through Rx06 (§8.1), so this is a second-order path — but it is the one that remains after the rail is bypassed. Through Rev 5.27 this was written as "star the returns to a single point"; as of Rev 5.28 the board has a solid In1 ground plane, whose impedance is below any star's, and each Rx06 returns to the plane by its own via. The requirement is unchanged, the star is not drawn.

- No L1 footprint. Through Rev 5.28 eight unstuffed 0Ω link positions were kept in series with each strip's 24V feed "in case bench measurement wants the inductor back." Deleted at Rev 5.29: the site was a 0207 axial, which cannot take a 47mH part, and the arithmetic above already shows the inductor doing nothing against a current source's output impedance. If crosstalk is measured above the floor, look at C102 and the ground returns; an inductor in the feed is not the fix and the footprint was not a way to fit one. Each strip's feed now connects directly to +24V_BRD.

## **12.5 Input Protection**

- F102, 500mA slow-blow on the 24V board input. The board draws about 290mA. Per-board fusing matters more than it did: the common supply can deliver 6.5A into a fault, where the LRS-35-24 would have current-limited at 1.5A and taken the whole system down instead.

- F101, 250mA fast-acting 250V on the ring bus input at J102. Review the value once the ring current per trunk is measured (§7.6). §7.6's estimate of 20mA per trunk puts eight trunks ringing at about 178mA, or 71% of the rating — on the 75% continuous derating limit for a fast-acting part, with the cadence duty cycle as the only remaining margin. If the measured per-trunk current exceeds the estimate, F101 goes to 500mA. The generator now carries a second ring bus fuse of its own on the switchboard branch (generator Rev 28 §7.6); this one still protects only what arrives here.

- D101, 1N5822 Schottky for reverse polarity on the 24V input. A screw terminal on a 24V bus will eventually be connected backwards. Fit D101 as a shunt clamp, not in series. Cathode to +24V BRD, anode to GND, reverse-biased and carrying nothing in normal operation. If the supply is connected backwards the diode conducts hard and blows F102; the board sits at about −0.5V until it opens, which everything on it survives. F102 must be upstream of D101 for this to work — J103, then F102, then the D101 clamp, then the board.

The fuse does open, and it is worth showing rather than assuming. The LRS-150-24 sources 6.5A before its own limiting acts, so a 500mA slow-blow sees roughly ten times its rating and opens in a few milliseconds. The 1N5822 is rated 80A non-repetitive for 8.3ms, an I²t of roughly 26A²s against the 0.25A²s of 5A for 10ms — two orders of magnitude of margin. If the diode does fail, it fails short, which is a dead short across a reversed supply and opens the fuse anyway. Both outcomes end the same way.

The reason to prefer the clamp over a series diode is compliance, and on this board it is not a small point. A series Schottky drops about 0.4V at the 250mA this board draws, and that 0.4V comes off the top of the loop feed — the one quantity §3.3 has already had to fight for. The clamp costs nothing in normal operation because it carries nothing.

It also makes the §3.3 budget honest. That table lists four fixed drops — Rx02, Rx05, Dx03 and Rx06 — and does not include D101, so the 15.6V of compliance and the 554Ω of cord circuit were computed from a full 24V at Qx01's emitter. With a series D101 that was optimistic by roughly 0.4V and the real figures were nearer 15.2V and 540Ω. With the clamp, the numbers as printed are correct. This change does not add compliance so much as stop the document overstating it.

- 47µF at 50V plus 100nF at the DC-DC input pins, close to the pins, in addition to the 1000µF audio-band bulk above. The input loop of a buck converter is the noisiest current path on the board.

- Distribute the 24V bus as a star from the PSU terminals — a separate pair to the switchboard and a separate pair to each interface board. This is now a requirement rather than good practice: it is what replaces the isolated DC-DC that station §10.1 asked for, and the current it is keeping out of the logic grounds is 1.5A of station loop current. See §12.1.1.

## **12.6 Rail Capacitors — Review Findings**

Reviewed against the module and regulator datasheets. The 24V audio-band bulk in §12.4 stands as specified; two smaller things do not.

The 47µF at the DC-DC input is required rather than advisory. Traco's TSR 2 datasheet calls for an input capacitor of 22µF/50V above 20VDC input, to prevent damage at power-on, and again where the input is switched electromechanically — both apply here. 47µF clears it and the 100nF handles what the electrolytic cannot.

Confirm the module's maximum capacitive load before committing the 220µF at the 5V output. Exceeding it causes a start-up failure rather than a visible instability, so the symptom is a board that will not come up and gives no clue why.

The omission is at the LDO, and it is the same on both board types: the 3.3V rail has bulk at U103's output but nothing at its input pin. The 220µF sits at the converter output with trace inductance in between. Fit 10µF plus 100nF at U103's input, and add a 100nF ceramic at its output alongside the existing 10µF — an aluminium electrolytic alone has poor impedance exactly where the regulator's loop needs it. One more 10µF and two more 100nF, both already on the board in quantity.

The 1000µF stays at one on this board. Station Rev 3.19 §10.7 adds the same part there for a reason that does not apply here — a 330Ω resistive feed puts audio-band current into the shared rail, where this board's current sources present roughly 600kΩ and keep it out. That asymmetry is worth understanding rather than standardising away: the two boards need the same capacitor for opposite reasons, and only one of them needs it badly.

# **13. Bill of Materials**

Per trunk, ×8 on the board, unless marked otherwise. Designators are the KiCad references on the rev 2 board as annotated (Rev 5.42). Strip parts are numbered per trunk sheet with x = trunk number + 1, so Rx06 is R206 on trunk 1 through R906 on trunk 8; root-sheet parts are numbered from 101. The notes give each part's former name in this document. C18 and C19 are not on the PCB — see their rows.

| **Designator** | **Value / Part** | **Description / Notes** |
| --- | --- | --- |
| Dx01 ×8 | P6KE150CA | Bidirectional TVS, 128V standoff. NOT the station board part — see §6. Formerly TVS1. |
| Qx03 ×8 | MJE350 (PNP, TO-126) | Current source pass transistor, 300V/0.5A. Fit a clip-on heatsink, ~40°C/W — see §3.4. Formerly Q4. |
| Qx01 ×8 | 2N3906 | Current source sense transistor. Formerly Q3. |
| Rx02 ×8 | 22Ω, 0.5W, 1% | Sets loop current to 28mA. 1% matters — this is the reference. Formerly R_set. |
| Rx04 ×8 | 10kΩ, 0.25W | Qx03 base bias; sets Qx01 operating current at ~2mA. Formerly R_bias. |
| Cx02 ×8 | 1nF ceramic | Current source loop compensation, Qx03 base to emitter. Fit a footprint accepting 100pF–10nF — see §3.2.2. Formerly C_C. |
| Rx05 ×8 | 33Ω, 1W — Stackpole RSF1JT33R0 | Fault limiting, not thermal relief — see §3.2.4. 1W is for the Qx03-short case (0.46W into a dead short). 33Ω from Rev 5.44 (was 100Ω, and 220Ω before that), for the compliance the 551's dial relay needs: about 440Ω with the operator in after dialling (§3.3.3). Formerly R1. |
| Dx03 ×8 | 1N4007 | Blocks reverse current during an accidental ring. Formerly D1. |
| Rx06 ×8 | 220Ω, 2W, 1% — Stackpole RSF2FT220R | Loop current sense. 220Ω from Rev 5.41 (was 150Ω), to drive Ux01 past its DC threshold; 1% from Rev 5.43, since −5% halves the turn-on margin — see §4.2. 2W covers a shorted Qx03, about 1.0W even into a dead short. Formerly R_LOOP. |
| Rx07 ×8 | 150Ω, 0.25W, 1% metal film — e.g. Yageo MFR-25FBF52-150R | Sets Ux01 input current, 3.0–4.4mA. 150Ω from Rev 5.41 (was 470Ω, which held Ux01 inside its hysteresis band); 1% from Rev 5.43 — see §4.2. Formerly R_DET. |
| Ux01 ×8 | HCPL3700M (onsemi) | Seizure detect, DC input mode — pins 2/3 driven, pins 1/4 OPEN. 8-pin PDIP. Note this is the opposite wiring from the station board ring detector. Formerly OC1. |
| Rx12 ×8 | 4.7kΩ, 0.25W | Ux01 output pull-up to 3.3V. Formerly R2. |
| Cx05 ×8 | 0.1µF ceramic | Ux01 V_CC bypass, pins 8–5, at the device. Required. Formerly C5. |
| Kx01 ×8 | CIT J104D2C5VDC.15S | DPDT ring relay, 5V/167Ω/29.9mA coil, sealed THT. Same part as the station off-hook relay — order the whole system quantity at once against the 20-week lead time: 8 here plus 22 on the station boards (the tap and monitor strips fit none). Formerly RLY1. |
| Qx02 ×8 | 2N2222A (TO-92, EBC) | Relay driver. Formerly Q2. |
| Rx01 ×8 | 1kΩ, 0.25W | Qx02 base resistor. Formerly R4. |
| Rx03 ×8 | 10kΩ, 0.25W | Qx02 base pulldown. Not optional — see §7.3. Formerly R_pd. |
| R101 | 10kΩ, 0.25W | /RESET pull-up to +3.3V at U101 pin 18, one per board. Fitted here and on every station board — deliberately the opposite of the rule against I²C pull-ups here, for the reason in §10.4. Required by the text since Rev 5.8; given a designator and a BOM line at Rev 5.25. Formerly R_RST. |
| C19 | 0.1µF ceramic, 50V | /RESET filter, U101 pin 18 to GND, at the pin. One per board. With R101 a 1ms time constant, so a spike coupled into the bus cord cannot reset the expander, while a deliberate reset — 2ms low, 5ms settle (control.md §6.2) — still works. Added at Rev 5.40 — see §10.4. Not on the rev 2 PCB: bodged across U101 pin 18 and GND; C110 at rev 3. |
| Dx02 ×8 | 1N4148 | Relay coil flyback diode. Formerly D5. |
| Cx03 ×8 | 10µF electrolytic | Local 5V reservoir at each relay coil. Formerly C9. |
| Cx04 ×8 | 0.47µF, 250V film | Tx01 primary DC block. 250V is for the accidental-ring case only — see §8.1. Formerly C2. |
| Tx01 ×8 | Triad TY-311P, 600Ω:600Ω | Audio isolation transformer, usable to ~9kHz. Wired node A to node B, behind both relay NC contacts. Trunks sit at the top of the comb — see §8.3. Formerly T2. |
| Rx08, Rx09 ×8 | 1kΩ, 0.25W matched | Receive balanced series resistors. Formerly R5, R6. |
| Rx10, Rx11 ×8 | 1kΩ, 0.25W matched | Transmit balanced series resistors. Formerly R7, R8. |
| U101 | MCP23017-E/SP | I²C GPIO expander, 28-pin PDIP. V_DD = 3.3V. Address 0x23. Formerly U1. |
| C101 | 0.1µF ceramic | Expander decoupling, at U101's V_DD pin. Formerly C6. |
| C108 | 10µF electrolytic | 3.3V rail bulk. Formerly C8. |
| C106 | 10µF electrolytic | LDO input bulk, at U103’s own input pin rather than at the converter output — the distance between the two is trace inductance the regulator has to work through. §12.6, and a BOM line only since Rev 5.25. Formerly C15. |
| C107 | 0.1µF ceramic | LDO input decoupling, at U103’s input pin alongside C106 — §12.6. Formerly C16. |
| C109 | 0.1µF ceramic | LDO output ceramic, in parallel with C108 at U103’s output pin. An aluminium electrolytic alone has poor impedance exactly where the regulator’s loop needs it, and the MCP1826 is specified with a ceramic on the output — §12.6. Formerly C17. |
| U102 | Traco TSR 2-2450 | 24V→5V switching module, SIP-3. Murata OKI-78SR-5/1.5-W36-C equivalent. 36V input rating required. Formerly U3. |
| U103 | MCP1826S-3302E/AB | 3.3V LDO from the 5V rail, TO-220-3 through hole, 1A. 39mA, 66mW. DigiKey MCP1826S-3302E/AB-ND. NOT the SOT-223 suffix (E/DB). Formerly U4. |
| C103 | 47µF, 50V electrolytic | 24V input bulk at the U102 pins. Formerly C10. |
| C104 | 0.1µF ceramic, 50V | 24V input decoupling at the U102 pins. Formerly C11. |
| C105 | 220µF, 25V electrolytic | 5V output bulk at U102. Total output capacitance must stay inside the module rating. Formerly C12. |
| C102 | 1000µF, 50V electrolytic | 24V audio-band bulk at the board input — see §12.4. The only 24V bulk on the board as of Rev 5.23. Formerly C13. |
| Cx01 ×8 | 100µF, 50V electrolytic | 24V local bulk at each trunk current source. Deleted from the design at Rev 5.23, fitted on the rev 2 board — §12.4. Formerly C14. |
| D101 | 1N5822 | Reverse-polarity protection on the 24V input. SHUNT clamp: cathode to +24V BRD, anode to GND — not in series. Blows F102 on a reversed supply and costs no forward drop — see §12.5. Formerly D6. |
| F102 | 500mA slow-blow, 5x20mm — Littelfuse 0218.500MXP | 24V board input fuse. 250V, 5x20mm glass cartridge, socketed. Same part as the generator board. Formerly F1. |
| F101 | 250mA fast, 250V, 5x20mm — Littelfuse 0217.250MXP | Ring bus fuse at J102. Fast-acting, not time-lag — the value follows the concurrent-ring cap in §7. Confirm the 250mA part number against the 217 series listing; the 500mA sibling is 0217.500MXP. Formerly F2. |
| (F101, F102) | 5x20mm PC-mount fuse block, ×2 | Littelfuse 64900001039, 649 series PC-mount block, 5x20mm, 6.3A / 250VAC, solder lug. One for F102, one for F101. Same holder on all three board types. Formerly F2, F1. |
| J104, J105 | DB25 FEMALE, R/A, 4-40 | Analog I/O to the A32, TASCAM analog pinout. J104 = 8 board outputs to A32 inputs; J105 = 8 A32 outputs to board inputs. Gender is female — see §13.1. Formerly J1, J2. |
| J101 | 6P6C modular jack, R/A | I²C bus in. One only — the trunk board is last in the chain. ALL SIX POSITIONS WIRED: SCL, SDA and two grounds on 2–5, /RESET and its return on 1 and 6 — pinout in §10.4. Cords must be six-conductor; a 6P4C cord seats and leaves a working bus with no hardware reset. Corrected at Rev 5.25, having described the pre-Rev-5.8 wiring. Part number in §13.1. Formerly J3. |
| TVS101 | Littelfuse SP721APP, 3pF SCR/diode rail-clamp array | ESD and mis-plug protection on SDA and SCL. 8-PDIP through-hole, 6 inputs, 3pF per line. Rail clamp, not a fixed-breakdown TVS: V+ (pin 8) to +3.3V, V- (pin 4) to GND, SDA and SCL to two of the six inputs, four spare. Sacrificial after a mis-plug — keep spares and consider a socket, since it is a DIP anyway. See §8.6. Formerly TVS2. |
| C18 | 0.1µF ceramic, 50V | Bypass across TVS101, pin 8 (V+) to pin 4 (V−), at the device. The SP721 clamps by conducting the transient from its IN pin into V+, so V+ must source that current locally or it lifts while the clamp is working. TVS101 sits at J101, away from U101 and the LDO, so C101 and C108 are too far to serve. Root sheet, not per trunk. Added at Rev 5.27 — see §10.5. Not on the rev 2 board; waits for rev 3. |
| J103 | 2-pin screw terminal | Board supply in: +24V BRD, GND. Formerly J5. |
| J102 | 2-pin screw terminal, 5.00mm, 300V | Ring bus in: RING_HI, RING_LO. On Shore OSTTC020162 (DigiKey ED2600-ND), 5.00mm pitch, 300V, 15A, 14-22 AWG, side entry, blue. NOT the same part as J103: that is the OSTTE020104, 3.50mm pitch and 125V, which is inadequate here — 100V RMS ring is 141V peak, above that block's rating entirely. 300V gives 2.1x margin, in line with the 250V film capacitors and 300V cable elsewhere in this zone. The two are different colours, blue against black, so the ring bus terminal is visually distinct from the 24V input on the same board. Own zone, 3mm creepage, physically separate from the low-voltage connectors. Formerly J6. |
| J7A101, J7B101 | RJ45 jack, shielded, R/A | Trunk tip/ring to the switchboard, four trunks per connector. Pinout in §8.5. The only RJ45 on the board — the connector type signals hazardous voltage. Shield to chassis at this end only. Part number in §13.1. Formerly J7A, J7B. |
| R102, R103 | 0Ω, 0.25W | D-Sub ground pins to board GND, one per DB25: R102 for J104, R103 for J105. **DO NOT FIT** — footprints only, unfitted on the rev 2 board, so the shields are grounded at the A32 end alone (§8.4). 100Ω in parallel with 10nF is the middle position in the same footprint, if ring events click. Formerly JP4 (one link in the design; the board has one per DB25). |
| Cable — trunk lines | Cat5e, 300V (CM/CMR) | Voltage rating is not optional at 141V peak. Check the jacket print — patch cords are often marked 30V or 72V. |
| Cable — I²C | 4- or 6-conductor modular, STRAIGHT-THROUGH | Not a standard voice line cord — those are reversed and short the bus to ground. See §10.4. |
| PSU | Mean Well LRS-150-24 | 24V, 6.5A, 156W enclosed. Chassis mount, off-board, common to the whole system including the switchboard. Sized for 24 circuits with headroom for 32 — see §12.1. Replaces the LRS-35-24, undersized by 2–3×. Check the 115/230V input switch before first power-on. |

## **13.1 Connector Part Numbers**

All three are through-hole, right-angle, board-edge parts. Prices and stock are as checked and will drift; the part numbers and the selection reasoning are the durable content.

| **Ref** | **Part** | **DigiKey** | **Notes** |
| --- | --- | --- | --- |
| J7A101, J7B101 | Amphenol ICC RJHSE5380 | 664-RJHSE5380-ND | 8P8C, right angle, shielded with EMI finger, no LEDs, no magnetics, gold 50µin, board lock, −55 to +85°C. About $1.72 each, deep stock. Qty 2. |
| J101 | Amphenol ICC 87180-066LF | — | 6P6C, right angle, unshielded, through hole. About $1.88. Qty 1. Würth 615006138421 (~$0.58) or Assmann A-2004-1-4-N-R (~$0.72) are equivalent for this purpose; at one per board the price is irrelevant, so pick on footprint and availability. |
| J104, J105 | NorComp 182-025-213R561 | — | Qty 2. 25-position receptacle, female sockets, right-angle through hole, solder, gold contacts, nickel-plated steel shell, board lock, integral 4-40 female screwlocks on the mating side, 5A per contact, PA9T dielectric, −55°C to +105°C. DigiKey 182-125FE-ND. Replaces the Amphenol ICC DBM25S500MN, which DigiKey does not stock. Screwlocks are part of the connector — no separate hardware line. The 182-025-213R531 is the same part with a plain threaded shell and needs two SFSO4401NR screwlocks each, which saves nothing once counted. Backset is 0.318 in (8.08mm) either way — confirm against the board edge before committing the footprint, particularly with two of these alongside the RJ45 jacks. 16-week manufacturer lead time despite stock, so order all six at once. |

*The DB25 gender needs settling before ordering, and earlier revisions of this document had it wrong. They specified male. The convention across TASCAM-pinout gear — including the A32 — is a female socket on the equipment and a male plug on the loom, so a board-to-A32 run is a male-to-male analog snake, which is a stock item. That means the trunk board should present female, not male. Confirm against the A32 before ordering, but do not assume male just because the board is the **"**source**"** end.*

J104 and J105 need 4-40 female screwlocks on the board side so the loom's jackscrews have something to bite. On most D-Sub bodies those are a separate line item; the connector specified in §13 has them integral to the mating-side flange, so there is nothing extra to order. If that part is ever substituted, check the flange feature.

*Two procurement points. The RJHSE5380 carries a 14-week manufacturer lead time against deep distributor stock — the same pattern as the relays and the PSU, so buy spares in the first order rather than discovering it later. And the DigiKey attribute table for the RJHSE5380 lists no voltage rating at all, which matters because J7A101 and J7B101 carry 141V peak. Pull the dielectric withstanding voltage from the Amphenol datasheet (rjhsex380.pdf) and confirm it before committing. Modular jacks in this class are normally rated far above this — POTS ring has run through 8P8C for decades — but it should be a checked number rather than an assumed one.*

# **14. PCB Layout Notes**

- Three high-voltage zones, not one. J7A101 and J7B101 and their trunk wiring carry 141V peak ring from either direction; the ring bus from J102 carries it whenever the generator is enabled; and the relay contact ends bridge the two. Mark all three on silkscreen and maintain 3mm creepage from every one of them to logic.

- Divide the board into a high-voltage edge carrying J102, J7A101 and J7B101, and a low-voltage edge carrying J104, J105 and J101, with the boundary printed on the silkscreen — see §8.6.

- The ring bus is the new hazard on this board and it is the one Rev 4.4 did not have. It runs from J102 to all eight relays in parallel, so it crosses the whole board. Route it as a single spine along the high-voltage edge with the relays hanging off it — not as a star, which would triple the length of HV copper.

- Route the isolation barrier as a continuous slot under each HCPL3700M body rather than relying on surface clearance.

- Group each trunk's current source, relay, driver and transformer into a strip and array it eight times. Get one trunk block right first. Confirm the J104D package dimensions before committing — 2 Form C is an eight-pin footprint.

- Node A and node B are the only two nets that are line-side when the relay is released and board-side when it is thrown. Keep both short and keep them inside the relay footprint's shadow rather than running them across the strip — they carry the audio and they sit between two high-voltage zones.

- Qx03 dissipates 0.44W steady and 1.3W averaged during an accidental ring. Give each one a clip-on heatsink and the clearance to use it, and do not bury the eight of them in the middle of the board where the heat has nowhere to go.

- Four layers: top / In1 GND / In2 power / bottom, the generator board's layer order with In2 carrying the three low-voltage rails as a split pour. Both inner layers stop 3mm short of the high-voltage edge — rule area on In1 and In2, drawn by hand, because KiCad's clearance constraint is same-layer only and the netclass rule will not keep a plane from running under the ring spine. Stack-up, split lines and rule areas are in trunk_schematic_guide §7.5.

- Each Rx06 returns to the In1 ground plane by its own via; none of the eight share a trace on the way. Through Rev 5.27 this was a star to a single point — see §12.4 for why the plane supersedes it. Place the LDO's own input bulk at U103's input pin rather than relying on the converter output bulk — see §12.6.

- Place the DC-DC converter, its input capacitors and its output capacitor in one tight corner well away from the transformer strip and both D-Subs. Its switching node is the only radiator on an otherwise passive board; the In1 plane is the pour between it and everything else, and it should be unbroken there.

- Put J101 at the low-voltage edge with J104 and J105, as far from J102, J7A101 and J7B101 as the board allows, and on the same edge as the corresponding connectors on the station boards so the chain runs cleanly down the rack. The bus carries 90V at 20Hz with 40kHz PWM residue on it, SDA and SCL have no error detection, and a corrupted expander write here energises a ring relay.

- The rev 2 board has no footprints for a second expander, an expander V_CC series resistor or I²C pull-ups, and none is wanted (Rev 5.42). L1 is gone as of Rev 5.29, not unstuffed — §12.4. Drop the P82B96 buffer footprint — §10.4 shows the bus has ample margin at this length. Board space is cheap now; a respin is not.

# **15. Safety Notes**

- This board originates ring voltage. That is the single most important difference from the station boards. 90V RMS at 20Hz (127V peak, up to 141V peak no-load) is present on J102, on the ring bus spine and on both relay NO contacts, and because the generator is shared with the switchboard it runs continuously rather than only while a trunk is ringing (§7.6). Assume the bus is live whenever the system is powered. The only things that stop it are the GPIO4 master enable switch and the GPIO14 shutdown line, both on the ring generator board — nothing on the trunk board can make the bus safe. No operator action is required to put voltage on it.

- J7A101 and J7B101 carry 141V peak. RJ45 is used for nothing else on this board or elsewhere in the system, so the connector type itself is the warning — keep it that way. Use 300V-rated cable; many Cat5e patch cords are rated 30V or 72V and are not suitable. Note that a 6P6C I²C plug will physically enter an RJ45 jack (§8.6).

- All components in the ring path must be rated 250V minimum. Maintain 3mm creepage. Note that the audio transformer is not in the ring path in normal operation — both relay poles break it clear — but Cx04 must still carry a 250V rating for the accidental case.

- The trunk pairs are referenced to board ground through Rx06, so tip and ring are not floating with respect to the board as they are on a station. The isolation barrier to the equipment side is Tx01 and the optocoupler; confirm each transformer's isolation before the D-Sub cables are connected.

- One common 24V battery now feeds the switchboard, both board types and all loops, so board ground and switchboard battery negative are the same node. Deriving board power from tip and ring is still prohibited (station §10.1), and the 24V distribution must be a star from the PSU terminals — see §12.1.1.

- Relay contacts stand off up to 165V peak when open (§7.4). Verify contact-to-contact dielectric strength from the datasheet rather than the distributor attribute table. Note that the relevant ring figure throughout is the generator's 141V peak no-load output, not the 127V peak of the 90V RMS nominal, because the bus idles unloaded.

- The board dissipates roughly 7W with all trunks seized, most of it in the eight current sources, and each Qx03 reaches 1.3W if ring is applied to its trunk. Ventilate the enclosure. The relay coil margin in station §5.4 degrades with temperature and this board runs warmer than a station board.

- Verify the HCPL3700M pull-ups are connected to 3.3V and not 5V before powering with the ESP32 connected. The ESP32 GPIO pins are not 5V tolerant.

- Do not connect trunk circuits to a live PSTN telephone line. Designed for 551 switchboard connection only.

# **16. Open Items for Bench Verification**

Everything below is a number this design assumes rather than knows. Each has a fallback identified in the section referenced.

| **Item** | **Why it matters** | **Section** |
| --- | --- | --- |
| Dial contact bounce through the 551 cord circuit | control.md Rev 24's two-sample filter assumes every bounce is shorter than one 5ms sample; the Rev 5.41 detector follows bounce faithfully. Measure on SEIZE or across Rx06 at a high sample rate while dialling. | §4.2 |
| ~~551 trunk cord circuit DC resistance~~ | Measured at Rev 5.41: 134–211Ω through the switchboard to a desk set, 357Ω to a station-board station; compliance 505–530Ω. §3.3.1 is not needed. | §3.3.3 |
| Switchboard trunk supervisory relay operate current | Bounds how far loop current can be reduced; gates the cheapest compliance fix | §3.3.1 |
| ~~HCPL3700M DC input forward drop at 6mA~~ | Closed at Rev 5.41: the DC input is a threshold buffer, V_TH+ 3.35–4.05V; measured 3.28V at 1.90mA with the Rev 5.40 values. | §4.2 |
| ~~Current source loop stability into the real line~~ | Measured at Rev 5.44: dial makes settle in under 40µs with no ringing, steady state 25–29mV p-p; Cx02 stays 1nF. | §3.3.3 |
| Current source output impedance across 300Hz–9kHz | Underpins the crosstalk claim; Early voltage is an estimate | §3.2.1 |
| Switchboard 24V draw — idle, typical, all lamps lit | The largest unmeasured term in the system budget; decides the PSU | §12.1 |
| Ring current drawn by one trunk | Sets the concurrent-ring cap and the F101 fuse value | §7.6 |
| Ring bus common-mode drift with both ends open | Confirms whether the 1MΩ reference pair is needed at the generator | §7.1.1 |
| 40kHz carrier residue at the A32 input during ring | Folds to 8kHz, on the doorstep of the trunk pilot comb | §8.1.2 |
| Ring crosstalk into an adjacent trunk pair in the same cable | Predicted −93dB; a quick confirmation with one trunk ringing and a tone on its neighbour | §8.5 |
| RJ45 jack dielectric withstanding voltage | Not in the distributor attributes; J7A101/J7B101 carry 141V peak | §13.1 |
| A32 D-Sub gender | Decides whether the board takes female sockets and a male-to-male loom | §13.1 |
| Which bus leg the switchboard puts on tip | Decides whether the open NO contact sees 0V or 141V during an accidental ring | §7.4 |
| Generator output under 1, 4 and 8 trunk load | Confirms 85–100V RMS is held; the 20W tap may be the binding limit | §7.1 |
| SEIZE pulse pattern under applied ring | Confirms the 27ms / 100ms discrimination margin on real hardware | §5.2 |
| Cx04 switching transient at the relay | Predicted 19mA peak, 282µs. Confirm it does not upset pilot detection. | §8.1.1 |
| Cord-pull transient at the jack | Scope tip-ring as a cord is pulled from a seized trunk; confirms Dx01 clamping and cord circuit inductance | §6.1 |
| Tx01 insertion loss at 8250–8906Hz | Trunks sit at the top of the comb and will show the most loss | §8.3 |
| Relay open-contact dielectric strength | 165V peak across open contacts; attribute table does not give this | §7.4 |
| Trunk-to-trunk audio crosstalk | Expected below −90dB. If measured above the floor, the shared path is the rail (C102) or the ground returns — no inductor footprint exists to stuff, by decision at Rev 5.29 | §12.4 |
| 5V rail under 8 coils energised | Relay pull-in margin is calculated against the rail's lower limit | §12.2 |

Two of these gate the layout rather than the bring-up. The cord circuit resistance decides Rx05 and therefore whether Qx03 needs a real heatsink, and the ring current per trunk decides the ring bus copper width and the fuse. Measure both before the board is cut; the rest can wait for a populated board.
