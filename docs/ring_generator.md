**551 Switchboard Simulator**

**Ring Generator Circuit Design**

*Rev 63 — ESP32 PWM + 74HCT04 Level Translation and SD Buffer on 5V + IR2104PBF H-Bridge + IRLZ44NPBF MOSFETs + Antek AS-0522 Toroidal Transformer Driven from Its 44V Winding (OSD Black 70V Retired at Rev 48), Olimex ESP32-POE-ISO, PoE-Powered Controller, I²C Master on GPIO13/GPIO16 plus Hardware /RESET for Station and Trunk Boards via 6P6C, Common 24V Battery, 80V RMS 20Hz Output Filtered by C_OUT at the Winding and Split Across Two Terminals with the Switchboard Branch Fused, Ring Drive Monitor on J10, Operator Tone Moved to the Station Board, High-Frequency-Link Alternative Recorded in §9.7*

# 1. Overview

The ring signal is synthesized by an Olimex ESP32-POE-ISO using two LEDC hardware PWM channels with a sine lookup table. The same Olimex board also serves as the I²C master for the station and trunk boards, reaching their MCP23017 GPIO expanders over a daisy-chained I²C bus carried on 6P6C modular (RJ11-style) patch cords. The Olimex board is powered from PoE; it draws nothing from the 24V system supply. A 74HCT04 hex inverter, running from 5V, translates the two PWM outputs from 3.3V logic to 5V through two gates each before they reach the IR2104PBF half-bridge drivers, and buffers the shutdown line to 5V on its two spare gates. Two IR2104PBF ICs and four IRLZ44NPBF logic-level N-channel MOSFETs form a full H-bridge that drives the transformer primary directly from the +24V supply rail.

A Traco TSR 1-24120 switching regulator (24V→12V, 1A) provides +12V VCC for the IR2104 drivers from the local 24V bus. The Olimex ESP32-POE-ISO supplies both logic rails from PoE: +3.3V for the I²C pull-ups and +5V on EXT1 pin 1 for the 74HCT04. No on-board 5V or 3.3V regulator is required. The gate is an HCT part specifically so that its TTL input thresholds accept a 3.3V GPIO drive while its outputs swing to 5V — see §5.

A master enable input on GPIO4 allows the ring generator output to be switched on or off — typically wired to a manual switch to GND. GPIO14 drives the IR2104 SD (shutdown) pins through gates 5 and 6 of the 74HCT04, cascaded as a non-inverting buffer, so SD sees a 5V logic high; a 10kΩ pull-down to GND at GPIO14 holds the H-bridge disabled at power-on.

The 24V bus input is protected by a 500mA slow-blow fuse followed by a shunt Schottky reverse-polarity clamp — the fuse first, then the clamp, then the board. The fuse value is the same one the trunk board uses; the station boards fuse at 250mA, sized for their own smaller load. The 24V supply is a Mean Well LRS-150-24 shared across all boards with star wiring from the PSU terminals — see §6.

## 1.1 Changes in Rev 14

Rev 13 was reviewed against station Rev 3.5 and trunk Rev 5.1. The changes below are corrections and cross-document alignment; nothing in the H-bridge, transformer or waveform design has moved.

— Corrected: I²C moves off GPIO17. On the ESP32-POE-ISO, GPIO17 clocks the Ethernet PHY and was never available. SDA is now GPIO13 and SCL is GPIO16 — see §3.1.

— SD control moves from GPIO13 to GPIO14, which is what frees GPIO13 for SDA — see §6.

— TVS2, a 3.3V rail-clamp array, added on SDA and SCL at J3. The master was the only node on the bus without one — see §4.6.

— J1 (24V input) and J2 (ring output) added to the component list. Earlier revisions specified no connectors on this board at all, while the trunk board expected a ring bus feed from it — see §10.10.

— The startup scan list is now driven by the configured station board count rather than hard-coded to four devices — see §4.5.

— IR2104 input threshold against a 3.3V drive called out for verification, with the IRS2104PBF named as the drop-in if it proves marginal — see §8.6.

— Fuse comparison corrected. 500mA here and on the trunk board, 250mA on the station boards; Rev 13 claimed all three matched.

— Build state stated explicitly. Three station boards and 24 stations is the design capacity; two boards and 16 stations is the present build. The third board is a populated-later slot and changes nothing on this board but the scan list.

## 1.2 Changes in Rev 15

Rev 15 exists because the gate-drive logic threshold in Rev 14 was checked against the datasheet and did not survive it. The change is contained to the logic between the ESP32 and the IR2104 inputs; the H-bridge, transformer, waveform and I²C design are untouched.

— Corrected: the IR2104 threshold figures. The datasheet specifies VIH at 3V minimum and VSD,TH+ at 3V minimum, both for VCC of 10V to 20V. Rev 13 and Rev 14 quoted an SD threshold of 2.1V maximum, which does not appear in the datasheet — see §8.6.

— Rev 16: fuse and fuse holder part numbers specified. Earlier revisions named fuse values and never said what held them — see §10.1.

— Rev 17: D1 changed from SS34 to 1N5822. Same function and forward drop; the SS34 has no through-hole package. Same change on all three board types.

— Rev 18: TVS2 specified as the Littelfuse SP721APP. A rail clamp rather than a fixed-breakdown TVS, 3pF per line rather than the 1pF assumed, and through-hole — see §4.6. Same part on all three board types.

— Rev 19 corrected: U_12V is the Traco TSR 1-24120, not the TSR 1-2412. The latter is a 1.2V part — the trailing zero carries the output voltage — and would have left the gate drivers below their undervoltage lockout. Specified wrongly since Rev 15; see §7.3.

— Rev 20: hardware /RESET added on 6P6C positions 1 and 6, driven from GPIO5, reaching every MCP23017 in the chain. The pair was spare and the alternative use considered for it — distributing 3.3V to the other boards — was rejected because it would have put a supply return on the interleaved grounds and a live rail on a plug that fits an RJ45 telephone jack. Cords must now be six-conductor — see §4.7.

— Rev 21: operator tone injector added as §15. A filtered 9000Hz square wave from GPIO15, transformer-coupled into the operator's talking path at bin 768, so the game can tell which circuit the operator is patched to. Independent of ring generation; adds three new passive values to the BOM.

— Rev 22 corrected: the injector is built entirely on the generator board, not split with T3 at the switchboard as Rev 21 specified. T3's position decides which side of the isolation barrier the cable falls on, and Rev 21 put it on the side connected to the GPIO — see §15.5.

— Rev 23: 10µF added on the 12V output as C_12V_BULK. The rail had 100nF of decoupling and no reservoir between gate-drive pulses — see §7.5. The TSR 1 input capacitor was checked and is already correctly specified.

— Rev 24: J2 is the same 2-pin screw terminal as J1 rather than a separately specified 250V part, matching trunk Rev 5.17 J6. One connector type across both boards; the creepage and separation rules for the ring output are unchanged — see §10.10.

— Rev 25 corrects Rev 24. The terminals on hand are the OSTTE020104 at 3.50mm and 125V, below the 141V peak of the ring output. J2 reverts to a separate part, the OSTTC020162 at 5.00mm and 300V, matching trunk Rev 5.18 J6. J1 keeps the OSTTE020104.

— Rev 26: D1 moves from series to a shunt clamp across +24V and GND, matching station Rev 3.20 and trunk Rev 5.19. Blows F1 on a reversed supply rather than blocking, and costs no forward drop — see §7.2.

— Rev 27: the operator tone injector is removed from this board. The tone is now generated by the host as an ordinary A32 output stream on the operator tap strip of station board 1 — station §7.9 — which also returns the operator’s audio for the audience monitor. GPIO15, T3, the two-pole RC filter, the 22kΩ pair and the coupling capacitors all come out of this build. §15 is retained as a record of what was there and why it moved.

— Rev 28: the ring bus is split into two separately terminated branches. J2 continues to feed the trunk board's J6; a new J6 on this board feeds the switchboard's ring supply. Rev 24 through Rev 27 had both branches landing under J2's two screws. The OSTTC020162 takes one 14–22 AWG conductor per position, so that was outside the block's specification, and it also meant neither branch could be isolated for fault-finding without unwiring the other. Two terminals cost one part — see §10.10.

— Rev 28: F2 added, a 250mA fast-acting fuse in series with RING_HI ahead of J6 only. The trunk branch is protected at its far end by the trunk board's own F2, and a second fuse in series with it would add a failure point without adding protection. The switchboard branch had no fuse at either end and is the longer and more exposed of the two runs. The value follows the trunk board's part rather than being calculated, and is provisional pending the ring current measurement trunk §7.6 asks for — see §7.6 here.

— Rev 28: the switchboard's 24V does not pass through this board, and §7.1 now says so rather than leaving it to be inferred. It was proposed as three pairs of a Cat5e run sharing an RJ45 with the ring pair, and rejected on two grounds. This board already carries the Olimex's PoE RJ45, so a second RJ45 with 141V peak on it would sit beside a jack that goes to a switch port, with nothing to stop either cable entering the wrong one — unlike the 6P6C case in §4.1, that hazard runs both ways. And F1 is 500mA, sized for this board's own consumption, so 1A of switchboard load through J1 was never available without re-fusing at a value that defeats what F1 is there for. The switchboard now takes its own leg of the star from the PSU terminals on Anderson Powerpole connectors.

— Rev 28: designator note. The new terminal is J6 rather than the next free J5. J5 means the black OSTTE020104 24V input block on both the station and the trunk boards, and a blue 300V ring terminal at J5 on this board alone would invert that meaning on one board out of three — the case §13 already worries about. J6 already means ring bus on the trunk board. J5 is deliberately left unused here. If KiCad renumbers on annotation the constraint is not the specific number: it is that the two blue ring terminals stay distinct from the black 24V input, on the silkscreen as well as in the netlist.

— Rev 29: §10 component list, F1. Rev 26 through Rev 28 described F1 as "Series after D1, first component on the +24V input" — two statements that cannot both be true, and the first of them wrong since Rev 26. The entry was correct while D1 was in series; Rev 26 moved D1 to a shunt clamp and did not revisit the table. The order is the whole mechanism. With D1 upstream of the fuse, a reversed supply puts the clamp directly across the LRS-150-24 with no fuse in the fault path: F1 carries only the board’s own load current and never opens, and the 1N5822 conducts 6.5A until it fails. F1 is upstream — J1, F1, then the clamp, as §7.2 and §13 have said throughout.

— Rev 29: §11 netlist, +24V_F deleted. It was the node between D1 and F1 in the series arrangement and has no counterpart in a shunt clamp, where nothing sits between them. Left in place it lists D1 cathode, already on +24V_SW, together with F1 pin1, already on +24V_IN — so the net bridges those two and shorts across the fuse. Drawn as written, F1 would have protected nothing.

— Rev 29: §1 overview. Still called D1 a series Schottky diode, three revisions after it stopped being one.

— Rev 29: all three are Rev 26 leftovers, and all three are in the summary and table sections rather than the design sections. §7.2 and §13 were right the whole time. This is the trunk §13 J3 failure again: a correction that landed where the reasoning lives and left the tables describing the old design.

— The consequence: at a 3.3V drive both IN and SD had about 0.3V of margin against a guaranteed minimum, not the comfortable margin Rev 14 claimed for SD and flagged only as a question for IN.

— 74HC02 becomes 74HCT02, running from 5V. TTL input thresholds (VIH 2.0V) take the 3.3V GPIO drive; the 5V output gives the IR2104 inputs about 2V of margin — see §5.

— 5V comes from the Olimex EXT1 pin 1. The load is a milliamp or two against the ISO board's 2W budget — see §7.4.

— SD is no longer driven directly from GPIO14. It goes through gates 3 and 4 of the 74HCT02 as a non-inverting buffer. Those two gates were previously unused with their inputs tied to GND — see §6.

— The IRS2104PBF substitution proposed in Rev 14 §8.6 is withdrawn. It was a workaround for 3.3V drive and is not needed at 5V.

— Rev 30: §6.1 and §6.2 duty polarity corrected. Both said to configure and to park the LEDC channels at 0 duty, and had said so since the channels were first specified. On an active-low drive that is the wrong end of the range. Duty 0 holds GPIO32 low, which is IN1 high and Q1 on; GPIO33 low then gives IN2 = GPIO32 AND /GPIO33 = low, which is Q4 on. Q1 and Q4 together put the full rail across the 0.63Ω primary as DC. It never fired, because SD is low at both of those moments, but §5.3 claims the bridge is off by two independent mechanisms and at 0 duty it was off by one. The park value is full scale — both pins high, both IR2104 IN pins low — which is also the boot state §5.3 describes. §12.3 now states the rule rather than leaving it to be derived from the truth table.

— Rev 30: R_PWMA_PU and R_PWMB_PU added, 10kΩ each from GPIO32 and GPIO33 to +3.3V. §5.3 asserted from Rev 5 to Rev 29 that those two pins default high on boot, and nothing was fitted to make it true. GPIO32 and GPIO33 have no internal pull at reset, so both 74HCT02 inputs floated through the bootloader window and a floating HCT input can drive Gate 1 either way. This is the §5.3 half of the same defect as the bullet above, and it is the case the index calls a part named in prose that is not a part — except that here even the prose was wrong. The generator PCB is not laid out, so the two resistors cost nothing but the BOM line. BOM 10kΩ 1/4W generator column 1 → 3, total 42 → 44, no procurement impact against 50 on order.

— Rev 30: §12.2 records what is actually built. The end-of-period interrupt on CH0 remains the ideal source and is still described as such, but the firmware uses a 200 µs periodic esp_timer, because reaching the LEDC overflow interrupt from the Arduino IDE means writing LEDC.int_ena directly and those register struct names move between IDF versions. The jitter earlier revisions warned about does not arise: LEDC latches duty at the next carrier period boundary, so an arbitrary write instant still lands on a period edge. Recorded because otherwise the document and the firmware disagree about something a reader would have no way to check.

— Rev 30: §7 renumbering. There were two §7.5 headings — Rail Capacitors and Bulk Decoupling — and the first of them sat between §7.3 and §7.4. Rail Capacitors moves to the end of §7 as §7.7. Renumbering the later headings instead would have been tidier in sequence but would have broken every existing cross-reference to §7.4 and §7.6, including two in the component list and one in the Rev 28 change entries. Nothing in the text moved.

— Rev 30: §7.4 was checked while writing the §5.3 note and is right. With PoE absent and the 24V bus live, the 74HCT02 loses its +5V, the Gate 4 output collapses, and SD is not held high. The new pull-ups do not cover that case — they run from the same Olimex +3.3V — and they do not need to.

— Rev 30: a fourth Rev 26 leftover, missed at Rev 29. §7.7 described the TSR 1 as sitting at the end of a fused, diode-dropped rail. There has been no series diode since Rev 26 and so no drop; the rail is fused only. Rev 29 corrected the three occurrences that named D1 and did not catch this one, which describes the consequence of the old topology without naming the part. Grepping for the designator was not enough.

— Rev 31: the 74HCT02 is no longer described as a shoot-through interlock. Rev 5 through Rev 30 called gates 1 and 2 an interlock in §1, §5, §10.4 and the document title, and §14 listed them as a continuous hardware guarantee against H-bridge shoot-through. They cannot be. Each IR2104 derives HO and LO from a single IN pin, complementary, with 520ns of internal deadtime, so no state of the gates can turn both devices in a leg on together — that protection is inside the driver, upstream of anything the 74HCT02 reaches. The gates exist for level translation: 3.3V into TTL thresholds, 5V out to a 3V IR2104 input, which is the argument §5 already made at length and which is load-bearing. The interlock is a property of the topology, not a reason for it.

— Rev 31: what the topology does forbid is IN1 and IN2 both high, which is Q1 and Q2 — both high sides, both ends of the primary at +24V, no path to ground. A zero vector, not a fault. §5.2 keeps the constraint but no longer presents it as a safety mechanism.

— Rev 31: §5.2 truth table, last row relabelled. It read "both inhibited — safe state" from Rev 5. Safe is right; inhibited is not. IN1 and IN2 both low puts Q3 and Q4 on, so both drivers are actively holding their leg at ground rather than being inhibited — inhibiting is what SD does. The distinction matters because this row is the park state §6.1 and §6.2 use and the boot state §5.3 relies on, and it is the only one of the four in which the bridge is genuinely off. The table itself was correct throughout; only the label was wrong.

— Rev 31: BOM row 5 follows, "shoot-through interlock" → level translation. The part number, quantity and every electrical figure are unchanged; this revision corrects what the part is for, not what it is.

— Rev 32: J7 and J8 added, and T1 is off-board. The document specified a transformer and never said how it attached; §10.9 gave it one line and §11 wired SW_L, SW_R, RING_HI and RING_LO straight to the winding as though the part sat on the board. It does not — the OSD Black is a distribution transformer with flying leads and no board-mount pattern. J7 takes the primary pair, J8 the 20W secondary pair. Found while writing ring_generator_schematic_guide.md, which could not name a symbol or a footprint for T1 because neither should exist.

— Rev 32: J7 is the black 3.50mm OSTTE020104 and J8 the blue 5.00mm OSTTC020162, deliberately not the same part. Nothing on the primary leaves the 0 to 24V range, so the 125V block is ample there; the secondary is 141V peak and the 125V block is below its rating entirely, as J2 and J6 already record. The colour convention holds — black low-voltage, blue in the ring zone. What it does not do is key anything: these are wire-clamp blocks and any wire fits any block, so the real protection is separation and silkscreen. §9 and §13 say which swap is the destructive one and why the labels matter.

— Rev 32: §10.2 gains C_12V_BULK. It has existed since Rev 23, is in the §11 netlist on +12V_VCC, is asked for in §7.7, and is counted on the generator column of the BOM — and was in every one of those places except the component list, which is where anyone drawing from §10 would look. §10.2 listed four parts where there are five. Same defect as R17 on the station board and R_RST on the trunk board, found the same way and at the same stage: writing the drawing guide. No design change and no BOM change; the count was already right.

— Rev 32: §10.10 J1 value corrected, 300V → 3.50mm, 125V. The part is the OSTTE020104 and always was — J2’s own note says so two rows below, and the BOM says so. Only the value cell was wrong, and 125V is entirely adequate at 24V. It mattered because the value column is what gets copied onto a schematic symbol.

— Rev 32: §11 gate resistor nets split. Each of the four read, for example, "IC1 pin7 (HO), R_G1 pin1 / R_G1 pin2, Q1 gate" — both pins of the resistor on one net, which is a short across it. A gate resistor is in series and nobody would draw it otherwise, so this was unlikely to reach copper; but §11 exists to be checked against a finished schematic and a netlist that shorts four parts cannot do that job. Now eight nets: HO_L, HO_R, LO_L, LO_R on the driver side, Q1_GATE through Q4_GATE on the gate side.

— Rev 33: the IR2104 pinout was wrong and is corrected in §8.2 and in all seventeen IC1 and IC2 references in the §11 netlist. The datasheet order is 1 VCC, 2 IN, 3 /SD, 4 COM, 5 LO, 6 VS, 7 HO, 8 VB. §8.2 had 1 VB, 2 HO, 3 VS, 4 VCC, 5 LO, 6 COM, 7 IN, 8 SD — seven of eight pins wrong, with only LO on pin 5 right by coincidence. It has been wrong since §8.2 was written and every revision since has copied it forward.

— Rev 33: what this would have cost. Nothing in the design changes — the connections were always correct, only the pin numbers naming them were not. But a schematic drawn from Rev 32 against a correct KiCad symbol would have put +12V on COM, ground on VS, the bootstrap capacitor on HO and the gate drive on VB, on both drivers. That is not a board that misbehaves; it is a board that destroys itself at power-on, and there is no bench symptom beforehand because the error is upstream of anything measurable. The one thing that would have caught it is the thing that did: reading the pin list against the datasheet rather than against the previous revision.

— Rev 33: §3.1’s warning about the Olimex pin numbers should be read as covering every pinout in this document, not just that one. The Olimex was singled out because it is a module rather than a catalogue part, but the IR2104 is a catalogue part with a datasheet and it was the one that was wrong. Check the IRLZ44N, the 74HCT02, the SP721 and the TSR 1-24120 against their datasheets before the netlist is trusted — none of them has been verified that way, and this document is no longer evidence that they are right.

— Rev 34: C_TVS2 added, 100nF across TVS2 pins 8 and 4 at the device. TVS2 has been on this board since Rev 8 with no bypass, and the SP721 datasheet asks for one. The mechanism matters more than the note: the SP721 does not shunt to ground, it conducts the transient from the IN pin into V+. That current has to be sourced locally or V+ lifts during the event, which both degrades the clamp and injects the transient into the +3.3V rail the Olimex and the expanders sit on. §4.6 deliberately places TVS2 at J3 and away from everything else, so there was nothing nearby to supply it — and on this board, unlike the trunk and station boards, there is no local +3.3V decoupling anywhere, since the rail arrives from the Olimex header rather than from an on-board LDO. Found by reading the datasheet to verify the pinout, which was correct.

— Rev 34: only the V+ side is bypassed, and no series resistor is fitted. The datasheet note asks for bypass on both V+ and V− and for a series resistor in the supply feed. V− is pin 4 and goes straight to GND here, so bypassing it to ground is a zero-length connection and there is nothing to add. The series resistor belongs to the automotive load-dump and reverse-battery case the note is written for; nothing on this board sees a reverse battery, and series resistance in the V+ feed would raise the clamp’s dynamic impedance, which is the opposite of the intent. Recorded because a later reader comparing the board against the datasheet will otherwise see two omissions rather than two decisions.

— Rev 34: the SP721 pinout is confirmed correct against the Littelfuse datasheet, revision GD 07/10/24 — IN on 1–3 and 5–7, V− on 4, V+ on 8. §11 assigns SDA to pin 1, SCL to pin 2 and /RESET to pin 3, all valid inputs, with the three remaining inputs open. No change. Noted so the check is on the record and does not have to be repeated.

— Rev 35: the TSR 1-24120 input range is 15 to 36V, not 4.6 to 36V. §7.3 and §12.5 both carried the wider figure from Rev 19 onward. 4.6V is the minimum for the 9V-nominal members of the series — the 1.2V, 1.5V, 1.8V and 2.5V parts — and each output voltage in the family has its own input minimum; the 12V part needs 15V in. The error came from reading the series header rather than the row. Nothing in the design changes: the LRS-150-24 adjusts over roughly 21.6 to 28.8V and 15V is still well below it. What changes is the size of the margin, from an implied 17V to an actual 6.6V, and any future argument about how far the 24V rail may sag now has to start from the right number. §12.5’s shunt-clamp reasoning is unaffected — 0.4V off a 24V rail is nowhere near either figure — but the sentence said something false and is corrected.

— Rev 36: the IR2104 pinout is verified against IR PD60046-S, lead assignments for the 8-lead PDIP — 1 VCC, 2 IN, 3 /SD, 4 COM, 5 LO, 6 VS, 7 HO, 8 VB. §8.2 and §11 have been right since Rev 33, but that correction stood on a reading rather than on the drawing, and this was the last of the five pinouts the boards depend on to be checked. The other four — IRLZ44N, 74HCT02, SP721 and TSR 1-24120 — were all correct as drawn. The IR2104 was the only one that was ever wrong, and it was wrong for the whole life of §8.2.

— Rev 36: §8.3 gains the VBS margin. C_BOOT charges to VCC less the UF4007 drop, about 11V nominal and roughly 10.8V at the low end of the TSR’s ±2%, against a recommended VB of VS+10 to VS+20. At g_amplitude = 1.00 three consecutive steps reach 100% duty and the high side conducts for 600µs unbroken, dropping a further 0.33V at the 55µA IQBS maximum — worst case about 10.4V, a few hundred millivolts of headroom rather than volts. It is not a constraint: VS+10 is a recommended condition and the IR2104 has no VBS undervoltage lockout, only VCC, and the IRLZ44N is fully enhanced at VGS = 5V. Recorded because it is the number that decides whether g_amplitude can be raised toward 1.00, or a diode with a larger forward drop substituted, and nothing in the document said so.

— Rev 36: the deadtime figure is qualified. §5 gave 520ns as though it were the specification; it is the typical, with a 400ns minimum and 650ns maximum. Nothing in the argument depends on the value — the point is that the deadtime is internal to the IR2104 and unreachable from outside — but a typical quoted as a spec is the kind of number that gets used in a later calculation as though it were guaranteed.

— Rev 37: §6.1 still said GPIO32 and GPIO33 default high. Rev 30 established that they do not — neither pin has an internal pull at reset — and fitted R_PWMA_PU and R_PWMB_PU to make the claim true. §5.3 was corrected then and §6.1’s power-on bullet was not, so the document has carried both the correction and the original assertion for seven revisions. Found by a reader asking whether the SD chain was right, which it was.

— Rev 37: SD is described in levels rather than states. LOW is shutdown, HIGH is enabled. "SD asserted" appeared in §5.3 and §10.4 and is correct — SD is the shutdown signal, so asserting it drives the pin down — but it reads backwards at a glance, and §7.4 already used the clearer form. Mixing the two in a document whose safety sections get scanned rather than parsed is how the failsafe gets inverted by someone reimplementing it. Same class of correction as §5.2’s "both inhibited" label at Rev 31: the substance was right and the word was wrong.

— Rev 37: R_SD_PD2 added, 10kΩ from the SD net to GND. R_SD_PD is on the GPIO14 side of the buffer and only holds shutdown while the 74HCT02 is powered. The uncovered case is PoE absent with the 24V bus live: the TSR keeps +12V up and both IR2104s alive while the gate has no supply, leaving SD to whatever an unpowered CMOS output settles at. §7.4 has argued since Rev 12 that this is near 0V and it is very likely right, but the argument rests on output-stage parasitics rather than on a specified behaviour, and this is the one signal on the board where being nearly certain is not the standard. One resistor makes it deterministic. It also covers what the Rev 30 pull-ups cannot, since R_PWMA_PU and R_PWMB_PU run from the same dead +3.3V rail.

— Rev 37: why the double inversion is not decorative, now stated in §5. Gate 3 inverts and Gate 4 inverts back, so GPIO14 low gives SD low and the bridge off. A single gate would put SD high when GPIO14 is low, which is what R_SD_PD does at power-on — the pull-down would then enable both drivers instead of disabling them. The buffer is what makes the pull-down mean shutdown, and neither part is optional.

— Rev 38: §9.3 is not a leakage measurement and is retitled. It carried the heading Measured Leakage Inductance from Rev 9, and §8.5 cited the 14.6mH as leakage to justify the snubber. Leakage is measured with the opposite winding shorted; 508mH at the 20W tap referred to primary is 508 / 5.89² = 14.6mH exactly, which is what an open-circuit measurement gives — magnetizing inductance. Only leakage governs the snubber, so the figure the design leaned on was the wrong quantity. Leakage is now an open measurement item.

— Rev 38: the snubber components are unchanged in value and are probably right, but for a reason the document did not give. R = √(L/C) with 10nF and 100Ω implies 100µH of leakage, ringing near 159kHz, sensibly above the 40kHz carrier. At the 14.6mH previously quoted the ring would be near 13kHz — below the carrier — and R would want to be about 4.3kΩ. §8.5 now derives the values instead of asserting them, and says plainly that the 100µH is inferred from the parts rather than measured.

— Rev 38: R_SNB becomes a 100Ω 1W part. Dissipation is C·V²·f = 10nF × 24² × 40kHz = 230mW, and Rev 5 through Rev 37 specified 1/4W with a note to uprate it if it ran warm. 230mW in a 250mW resistor is 92% of rating; that is not a margin and the note read as though it were optional. The 1W MFR-100 is already on the BOM for trunk R1, so this costs a footprint change from DIN0207 to DIN0414 and nothing else — no new line item, no additional order.

— Rev 38: C_SNB is 10nF 250V film, not 100V ceramic. §8.5 and §10.8 said ceramic from Rev 5; the BOM and the KiCad library plan have carried the Kemet R82 film part under the correct DigiKey number throughout, so only the design document was wrong. The voltage was never the problem — 100V is adequate against a 48V peak — but an X7R loses capacitance under DC bias and handles repetitive pulse current poorly, which is the entire job of a snubber capacitor.

— Rev 39: §12.2 now says where its four constants come from. The constraint 20 = 40000 / (8 × 250) has been recorded since Rev 12 with no account of why those factors and not others, which is the kind of thing that gets re-derived from scratch in two years or, worse, changed without noticing what depends on it. Two of the four are forced — 20 Hz from outside, 10-bit resolution from the 80 MHz LEDC clock against a 40 kHz period. The remaining two are one decision, since their product must be 2000; 250 steps is the choice and the 200 µs step period follows.

— Rev 39: the section is explicit that this is reconstruction, not recovery. It was worked out from the constraint during a conversation about how the firmware runs, not recovered from whatever was decided at Rev 12. The distinction is worth preserving — a plausible reconstruction presented as a record is worse than no record, because nobody thinks to question it.

— Rev 39: one thing is flagged as genuinely lost — why the carrier is 40 kHz specifically. Above T1’s 20 kHz passband, above audibility, and low enough to leave 10-bit LEDC resolution intact are all good reasons and none of them is written down anywhere. §12.2 says so rather than inventing one.

— Rev 39: §12.2 also now points at §8.3 for anyone revisiting SINE_STEPS. The step count looks like a pure software choice and is not: at g_amplitude = 1.00 three consecutive steps reach 100% duty, so the step period sets the 600 µs window of unbroken high-side conduction that the bootstrap droop is calculated against.

— Rev 35: TSR 1-24120 pinout verified against the Traco datasheet of 2 July 2026 — 1 +Vin, 2 GND, 3 +Vout, SIP-3, 2 × 2.54mm pin pitch. §11 already had it right. This was the last of the two outstanding pinout checks the Rev 33 entry listed; only the IR2104’s own package drawing remains unseen, and its pin list stands on the user’s reading rather than on the document.

— Rev 35: maximum output capacitance for the TSR 1 is 470µF, recorded in §7.3. This rail carries 100nF plus 10µF, so there is no constraint here and the rail can be added to freely. This does not settle the equivalent question for the TSR 2-2450 on the station and trunk boards against their 220µF — different part, different datasheet, still open.

— Rev 35: §13 gains a layout note — route no traces under the converter. The datasheet asks for it explicitly. It matters more here than it would on a quieter board: this is a 500kHz buck in an unshielded plastic case, and the same board carries the I²C bus and the ring output.
— Rev 40: the interlock is removed. Gate 2 input A moves from Gate 1’s output to GPIO33, so all four NOR gates become plain inverters and IN2 = /GPIO33. The cross-coupling dated from Rev 5, when it was believed to prevent both MOSFETs of one leg conducting together. It never could: the IR2104 derives HO and LO from a single IN pin with internal deadtime, so that state is unreachable from outside the driver. Rev 31 established this and corrected what the gates were called — the section heading, §14, the BOM description — but left the topology in place. Renaming a thing is not re-examining it.

— Rev 40: what the cross-coupling actually cost. It forbade IN1 = IN2 = high, which is Q1 and Q2 — both ends of the primary at the rail, no path to ground, harmless. In exchange it put the dangerous state where an unprogrammed GPIO lands: both pins low gave Q1 and Q4, the full rail across a 0.63Ω primary as DC. That is the condition R_PWMA_PU and R_PWMB_PU were fitted for at Rev 30 and the one §6.1 and §6.2 walked into from Rev 5 to Rev 29. With the change, both pins low is the zero vector and the topology fails safe by itself. The pull-ups and the full-scale park value stay; they are now redundancy rather than the only defence.

— Rev 40: nothing else moves. Same part, same gate count, same DIP-14, same firmware. Both PWM pins remain active LOW, the park value remains DUTY_MAX, the duty tables are unchanged — GPIO33 is held high through the positive half-cycle, which gave IN2 low before and gives IN2 low now. One net changes in §11: U4 pin5 leaves the IN1 net and joins GPIO33. The change also decouples the two channels, which the old arrangement did not: a glitch on GPIO32 propagated into IN2.

— Rev 40: §8.6 corrected. It said the margin at a 3.3V drive was about 0.3V. The ESP32-WROOM VOH minimum is 0.8 × VDD, or 2.64V at a 3.3V rail, against the IR2104’s 3.0V VIH minimum — a margin of −0.36V. Direct drive is outside specification, not near its edge, and the section had been understating its own case since Rev 16.

— Rev 40: the IRS2104 is closed on package, not on electrics. It is the correct answer to direct 3.3V drive and would delete the 74HCT02, C_U4, the +5V net and R_SD_PD2. It is surface-mount only, and this is a through-hole board whose §13 asks for the shortest gate drive loop the layout allows. Recorded in §8.6 because the electrical argument alone would invite the substitution a third time.

— Rev 41: §5.3 sharpened. Its account of why R_PWMA_PU and R_PWMB_PU are fitted was written at Rev 30, when the cross-coupled gates meant a floating GPIO32 alone could put IN1 either way. With the interlock gone the case is stronger, not weaker: both gates float independently, and two of the four resulting states — IN1 high with IN2 low, or IN1 low with IN2 high — are the full rail standing across the primary. The section had been describing a one-gate problem after it became a two-gate one.

— Rev 41: the two changes are recorded as addressing different failures. Rev 40 made both pins driven low safe; the pull-ups make both pins undriven determinate. Floating is not low, so one does not substitute for the other, and a reader who assumes the Rev 40 topology change makes the pull-ups redundant would be wrong. That inference is available enough that the document should close it off.

— Rev 41: §5.3 now cites the two reasons that hold whatever the bridge is doing. TI SCLS065G §5.2 note 1 requires unused inputs to sit at VCC or GND and §9.1 forbids leaving inputs floating; and a floating HCT input holds both output transistors partly on, drawing supply current and liable to oscillate, for the whole bootloader window on every boot. Neither is about the H-bridge, and both would justify the resistors on their own.

— Rev 42: GPIO15 takes a waveform sync output, new §12.5. High at step 0, low at step 125, giving one 20 Hz square wave per output cycle with the rising edge at phase zero. It is for bench work: triggering a scope or the Analog Discovery at a known point so the switching node, the gate drive and the secondary can be viewed against one reference. §3.2 gains the assignment, which it did not have — GPIO15 was listed there as free since Rev 27 and the section already warned that the list needs to be complete to be trusted.

— Rev 42: the sync writes levels rather than toggling. A toggle that misses a tick stays inverted for as long as the generator runs, which on a trigger signal means every subsequent capture is half a cycle out with nothing to show it. Writing the level re-asserts twice per cycle, so a lost tick costs one edge and not the polarity. The pin idles low when the generator is stopped, so no trigger means the bridge is genuinely idle rather than the sync having failed.

— Rev 42: GPIO15 is a strapping pin and firmware treats it as one. It must be high when the ROM bootloader samples it, and low at reset also silences the boot log, so the pin is left as an input until setup() runs and claimed only then. §3.2 has carried that warning since Rev 27; this is the first assignment to test it.

— Rev 42: recorded as a debug output that nothing depends on. If GPIO15 is later wanted for a function the system needs, the sync is what goes. Worth stating because a signal that appears in §3.2 and §12.5 looks like part of the design, and this one is a test point.

— Rev 43: J9 added, a 3-pin 0.1 inch header carrying GPIO4, GND and GPIO15. A shunt across pins 1 and 2 pulls the master enable low and the generator runs; pin 3 carries the §12.5 sync with its return on pin 2. GND is in the middle on purpose — the enable shunt is fitted once and the probe is used constantly, so the probe gets the short ground return, and a shunt fitted wrongly across 2 and 3 merely grounds a push-pull output.

— Rev 43: this replaces a 2-pin enable header that existed on the schematic and in neither this document nor the BOM. §3.2 has described GPIO4 as a master enable since Rev 8 and §11 listed the net with a single node, the Olimex pin; ring_generator_schematic_guide.md called it out as a net that goes nowhere and asked for a text note saying what grounds it. The part was real and undocumented, which is the reverse of the usual failure here and just as easy to miss — nothing in the document contradicted it, so nothing flagged it.

— Rev 43: the BOM gains two rows that were never there — the header itself and a 2.54mm shunt. The master enable had been described in prose since Rev 8 with no part counted against it, which is the defect the index calls a part named in prose is not a part. §11 also gains a GPIO15 net, which did not exist at Rev 42 because the pin went only to the Olimex.

— Rev 44: the 74HCT02 becomes a 74HCT04 hex inverter, SN74HCT04N, and each signal is routed through two gates instead of one. Same DIP-14, same footprint, same HCT thresholds, same +5V rail; different symbol, different pin numbers, ten on order unaffected because none had arrived. Once Rev 40 removed the cross-coupling, all four NOR gates were inverters written the long way — two inputs tied where one would do. Six inverters carry three signals with no tied pairs to leave half-connected.

— Rev 44: the point of two gates per signal is polarity. One inversion gives the active-low drive the board has had since Rev 5, and active low is the origin of every polarity defect in this document: parking LEDC at 0 duty then means IN1 high with IN2 low, which is Q1 and Q4 and the full rail across a 0.63Ω primary as DC. §6.1 and §6.2 specified that from Rev 5 to Rev 29. Two inversions give active high, so LEDC’s own power-on state of 0 duty is IN1 = IN2 = low — Q3 and Q4, primary shorted to ground. The trap is removed rather than defended against. Cost is about 20ns of propagation delay against a 25µs carrier period.

— Rev 44: R_PWMA_PU and R_PWMB_PU become R_PWMA_PD and R_PWMB_PD, same 10kΩ, to GND rather than +3.3V. This is an improvement beyond the rename: the pull-ups ran from the Olimex +3.3V and were therefore unpowered in exactly the PoE-absent case §7.4 describes, where the 24V bus is live and both drivers are alive. A pull-down to ground needs no rail. §5.3’s floating-input argument is unchanged, because it was never about which rail the resistors pulled to.

— Rev 44: §12.3 inverts and §5.2’s truth table inverts with it — both columns, which is the whole effect of the change. The firmware writes duty directly instead of complementing it, and parks at 0 instead of full scale. ring/ring.ino is updated to match; the waveform is unchanged at 48Vpp and 16.97 Vrms, since only the encoding moved.

— Rev 44: §11 gains PWMA_MID and PWMB_MID, the nets between the first and second inverter of each PWM path. They exist for the same reason SD_N does. An earlier draft of this revision put each gate’s input and output on one net, which shorts the second inverter — the same defect Rev 32 corrected in the gate resistor nets, made again while writing the revision that cites it. Caught by counting U4 pin occurrences: every pin must appear on exactly one net, and pins 3 and 9 appeared on none.

— Rev 44: the 74HCT04 pinout used in §5.1 and §11 — 1A 1, 1Y 2, 2A 3, 2Y 4, 3A 5, 3Y 6, GND 7, 4Y 8, 4A 9, 5Y 10, 5A 11, 6Y 12, 6A 13, VCC 14 — is the classic 7404 arrangement and has NOT been verified against the SN74HCT04N datasheet. It is the one thing in this revision standing on convention rather than a drawing, which is exactly how the IR2104 pinout was wrong for the whole life of §8.2. Check it before drawing the schematic.

— Rev 45: the 74HCT04 pinout is verified against TI SCLS042F §4 — 1A 1, 1Y 2, 2A 3, 2Y 4, 3A 5, 3Y 6, GND 7, 4Y 8, 4A 9, 5Y 10, 5A 11, 6Y 12, 6A 13, VCC 14, which is what Rev 44 used. It was the one thing in that revision standing on convention rather than a drawing, and it happens to be the same convention the 7402 breaks. Checking it cost nothing and the alternative was finding out during bring-up.

— Rev 45: the propagation delay figure is corrected. Rev 44 said the double inversion costs about 20ns; SCLS042F gives 13ns typical and 23ns maximum per gate at 5.5V, so the pair costs 26ns typical and 46ns maximum. Still a fifth of one percent of the carrier period and it changes nothing, but 20ns was a guess presented as a number.

— Rev 45: SN74HCT04N is NRND — Not Recommended for New Designs — in the PDIP package, per the SCLS042F package addendum. So is the SN74HCT02N it replaces, so this is not a reason to reconsider. It is worth recording because through-hole HCT logic is thinning out generally: the search that closed the IRS2104 question found the 74HCT244 and 74HCT540 in DIP already obsolete. Buy enough for spares while the part is orderable.

— Rev 45: with all six inverters carrying signal there is no unused input on the package. SCLS042F §5.2 note 1 and §9.1 both require unused inputs to be tied to VCC or GND, and a tied-off spare is a thing to forget. The 74HCT02 left none spare either, so nothing is given up.

— Rev 46: R_GS3 and R_GS4 added, 10kΩ from the Q3 and Q4 gates to GND. This is a defect corrected, not an improvement: the design has never had gate-to-source resistors, and a floating MOSFET gate does not stay off. Crss couples about a ninth of any drain step onto the gate, so 24V applied to the drains deposits roughly 2V against a 1.0V threshold minimum, with nothing to bleed it away. Observed on the bench during Rev 45 bring-up with the drivers unfitted — the board sat on the supply’s current limit, +24V straight to ground. A current-limited bench supply is the only reason this cost nothing.

— Rev 46: two resistors rather than four, because every DC path from the rail to ground passes through a low-side device — directly through Q3 or Q4, or through the primary as Q1, SW_L, T1, SW_R, Q4. Holding both low-side gates down removes all of them, and the Q3 and Q4 body diodes are reverse-biased whenever SW is positive so they open no alternative. A partly-on high side then does nothing: SW rises toward the rail, no current flows for want of a return, and the primary stays unenergised.

— Rev 46: high-side gate-to-source resistors are recorded as deliberately absent. 10kΩ from HO to VS draws 1.1mA out of C_BOOT while the high side conducts, which over §8.3’s 600µs window is 6.6V of droop on a 100nF capacitor against the 0.33V that section calculates. 100kΩ still roughly triples the total load against the 55µA IQBS. They would add nothing the low-side pair does not already provide and would spend the margin §8.3 exists to document. Written down so the asymmetry reads as a decision rather than an oversight.

— Rev 46: BOM 10kΩ 1/4W, generator 4 → 6 and total 45 → 47, still inside the 50 on order. Nothing new to buy.

— Rev 47: §8.3’s bootstrap margin is measured rather than calculated, and it is worse than the calculation. At g_amplitude = 1.00, VB−VS collapses from 11.8V to about 2.6V for several milliseconds at each sine peak and HO−VS reads −9V at the same instants — one event, seen from two differential probes, with VS being dragged upward while VB stays put. At 0.90 both vanish: 11.98V held, and −494mV of ordinary undershoot on HO. The section had described 1.00 as spending the margin; it closes the refill window entirely.

— Rev 47: §9.4 gains a floor on the trim value. 0.90 is what the section already expects, but nothing said 1.00 was unsafe — it read as an untrimmed default, and it was left in the firmware during bring-up for exactly that reason. A measurement calling for a trim above about 0.95 now points at the transformer tap rather than at the duty.

— Rev 47: measured on the breadboard with the high-side drains disconnected, so the bridge was unloaded. The figures should be taken again once the rail is on and T1 is connected; magnetizing current and real gate charge will move them, and the refill window is where they will show up first.

— Rev 48: the Rev 40 to Rev 47 change entries are moved here from §12.2. Eight revisions of change history sat in the middle of a firmware section, between the SINE_STEPS paragraph and “What is genuinely not recorded”, because an insertion anchored on a paragraph index rather than on the §1.2 heading, and each later revision appended to the wrong place without noticing. Nothing in the entries is changed; only their position. This is the index-based-insertion failure PROJECT_INDEX.md already warns about, and it went unnoticed in this document for eight revisions.

— Rev 48: T1 is changed. The OSD Black 70V transformer saturates at 20Hz far below the bridge's operating point. Bench, 2026-09-04, first power-up with T1 connected and the snubber fitted: the 24V rail collapsed to about 1V for roughly 10ms of every half-cycle behind a 1A supply limit, and the primary showed a 21V sine peak that fell to zero partway through each half-cycle. A rail-voltage sweep with the limit at 1A gave 70mA at 3V, 100mA at 5V, 250mA at 7V, 450mA at 9V and the limit at 11V — current per volt flat to 5V and then climbing, which is a core reaching its volt-second limit, not a linear inductance. The knee is about 4V RMS across the 4Ω winding; the design applies 15.3V RMS. §9.5 records the finding. The label's “20Hz–20kHz ±1dB at 20W” describes the 70V side into its rated load; it does not describe the 4Ω winding at nearly twice its rated voltage.

— Rev 48: an error in the history is recorded with it. §9.3 has given 14.6mH referred to the primary since Rev 9, and no revision computed the magnetizing current that implies: 15.3V RMS into 1.83Ω of reactance at 20Hz is about 8A RMS before any saturation. F1 at 500mA and the LRS-150-24 at 6.5A were never sized against that number because the number was never written down. With the replacement transformer the magnetizing current is tens of milliamps and F1 stands; the point is recorded so the check is made the next time a winding changes.

— Rev 48: the replacement is an Antek AS-0522 toroidal mains transformer — 50VA, two 22V secondaries, two 115V primaries, 115/230V 50/60Hz — used in reverse. The two 22V windings in series (44V nominal) are driven by the bridge from J7; the two 115V windings in series (230V nominal) are the ring output into J8. A 44V winding rated at 50Hz takes 44 × 20/50 = 17.6V RMS at 20Hz before rated flux, and the bridge's 15.3V RMS at g_amplitude = 0.90 is 87% of that. Output at the nameplate ratio is 230/44 × 15.3 = 80V RMS; at the open-circuit ratio — 44V is the full-load figure, and a 50VA toroid at 12–14% regulation has roughly 50V of turns — about 72V RMS. Antek publishes no regulation figure, so the ratio is unknown until measured. Two units are on hand. Hammond 1182J22 and 1182G22 are the same electrical case and were the first candidates; both are factory-stock at DigiKey, and the Antek is $20 and in stock direct.

— Rev 48: §9.1 to §9.4 keep their OSD figures, marked as such, until the Antek has been measured on the Analog Discovery: DC resistance of each of the four windings; open-circuit ratio, 44V series to 230V series, at a few volts at 20Hz; magnetizing inductance of the 44V series winding, open; leakage of the same winding with the 230V series winding shorted. Those four rewrite §9.2, §9.3 and §8.5 at the next revision. Leakage on a toroid is expected in the low microhenries — someone dissecting the 6V unit of the same series measured 2.5µH — against the 100µH §8.5's snubber values imply, so R_SNB is expected to fall to the tens of ohms and the ring frequency to rise toward 1MHz. Dissipation is C·V²·f and does not contain R, so the 1W part stands whatever R becomes.

— Rev 48: the reversed-mains-transformer approach was considered early in the project and rejected, and the reasoning was never recorded. Reconstructed, and flagged as reconstruction: the candidate was a doorbell transformer, whose 16V or 24V winding takes only 5–8V RMS at 20Hz before saturating — the same flux limit that has now retired the OSD. The rejection was right for that part. The fix is not a different kind of transformer but a drive winding rated at least three times the drive voltage, which a 44V winding provides against 15.3V.

— Rev 48: the output target changes from ~90V RMS to 70–80V RMS, recorded as the target rather than as a shortfall. 90 was never a requirement of anything downstream: telco ringing is specified at 40–130V RMS with 90 nominal, the switchboard's trunk ring relay has been operating from a lower-voltage commercial generator throughout bring-up, and vintage ringers ring from about 50V. Lower is better everywhere the operator can hold ring on — TVS clamp events, C3's current into T2 during ring overlap on the station board, R1a/R1b dissipation, the operator-tap resistors under a ring fault, and F2. Station §3.4 at 72V gives 4.5mA peak detector current against a 3.11mA worst-case threshold, 1.45× rather than the 1.8× it designed for, and a 50% rather than 63% output pulse train, which the 200Hz polling still samples five times per half-cycle. If the measured output lands near 72V, R1a/R1b go to 2 × 7.5k at station Rev 3.27; near 80V they stay. The title line changes with this.

— Rev 48: g_amplitude stays at 0.90. §8.3's bootstrap refill argument is unchanged by the transformer, and 0.90 puts the toroid at 87% of rated flux. There is no reason to trim up and one to leave it; §9.4 is rewritten accordingly.

— Rev 48: a firmware consequence, made on the Claude Code side per PROJECT_INDEX.md. Starting the sine at a zero crossing integrates flux from zero and puts the first half-cycle's excursion at twice the steady-state peak — about 175% of rated flux for the toroid — which saturates the core once at every power-up and puts a current spike through F1 that its slow-blow rating may not survive; §7.2 already reasons that ten times rating opens it in milliseconds. The fix is to start the duty table at its positive peak, SINE_STEPS/4, so the flux integral starts where steady-state flux is zero. §12.6 records the requirement. The OSD never showed this because it was saturated in steady state. The generator runs continuously from power-up and ring cadence is switched on the secondary by the trunk board, so the transient is once per power-up, not once per ring.

— Rev 48: §8.7 adds a ring drive monitor — R_MON1 and R_MON2 (4.7k) from SW_L and SW_R into C_MON (100nF) between them, with the two filtered nodes and GND on a new 3-pin header J10. It is a balanced 170Hz low-pass that presents the 20Hz drive with the 40kHz carrier 47dB down, so what the transformer sees can be read on a scope without a filter in the instrument. Every capture of the primary during bring-up has been either aliased at low sample rate or a filled band at high rate, and the collapse of 2026-09-04 was diagnosed from the density of an aliased trace. This puts a line on the screen. Three passives already on the BOM, 1mA from the rail. GND in the middle of J10 as on J9, so a single-ended probe has its return adjacent and a differential pair lands on the outer pins.

— Rev 48: C_MON is the 100nF 50V X7R already used for decoupling, not film. The filter sees ±22V; X7R capacitance falls under that bias and moves the corner, which for a viewing filter is irrelevant — at 20Hz the response is within 1% of unity across any capacitance the part could fall to. Film matters in C_SNB for pulse current and in station C4 for threshold accuracy, and neither reason applies here. The film parts that would substitute — Kemet R82 and Panasonic ECQ-E at 100nF — were on 20 to 29-week factory lead times at DigiKey at the time of writing. The ceramic adds no line item and nothing to order.

— Rev 48: stale text and lost markup. Two §11 rows had lost their net names — U4 pin4 → IC1 pin2 and U4 pin8 → IC2 pin2 read as pin lists with no name column; they are IN1 and IN2, the names the schematic guide already uses. §12.4's heading had lost its heading markup. §13 still said “74HCT02”. §9, §10.10 and §11 said “4Ω primary”, “20W tap” and “141V peak” in seven places; each now names the Antek windings and the 113V peak of the new output, with the OSD figure kept where the reasoning was built on it.

— Rev 48: BOM — 4.7k 0.25W generator 0 → 2, total 24 → 26, the 50 on order covers it; 100nF ceramic generator 10 → 12, total 49 → 51 against 50 on order, one short, so Buying 50 → 55 and digikey_upload.csv follows; 3-pin header generator 1 → 2 for J10 beside J9; OSD transformer generator 1 → 0, marked retired, row kept; Antek AS-0522 added, generator 1, two on hand. Nothing further to order beyond five more 100nF. Library plan: 3-pin header total 1 → 2; OSD row marked retired; Antek row added — off-board, no symbol, no footprint, the same J7/J8 arrangement.

— Rev 49: no design change. §7.3 and the §10.2 row for C_12V_OUT now say what the capacitor is for. It was labelled "output bypass", which invited the question of whether it is needed given C_VCC1/C_VCC2 at the drivers and C_12V_BULK beside it. It is not needed for function — the TSR 1 regulates without it and the drivers' edge current comes from their own capacitors — and it stays for the regulator's few-hundred-kilohertz switching ripple, which the electrolytic's ESL handles poorly. A part whose purpose is not written down is a part someone will remove.

— Rev 50: no design change on this board. §15.4 said the station tap's R11/R12 are 22.1kΩ; they are 22kΩ 1% metal film as of station Rev 3.27. The 22.1k value came in at station Rev 3.24 on a claim that 22.0k is not stocked in 1% metal film, which was wrong, so the station has gone back to the 22kΩ that §15.2 specified in the first place. The §15.2 note that the pair “reappears… at the catalogue value of 22.1kΩ” is left as written, since it records what Rev 27 did, with a pointer added. The fault-current figure in §15.4 is unchanged at about 2mA.

— Rev 51: the four Antek measurements §9.5 asked for at Rev 48 are made, 2026-09-15 and 16, on the Analog Discovery 3 with the Impedance Analyzer Adapter. They rewrite §9.2, §9.3, §8.5 and the two provisional paragraphs of §7.6, and confirm §7.2. No part changes. The figures: 115V windings 23Ω each, 22V windings 1.1Ω each with the lead resistance nulled; open-circuit ratio 5.23, single 22V winding to single 115V winding at 2V peak; magnetizing inductance of the 44V series pair 3.10H at 20Hz and 1V, |Z| 410Ω at 71.9°; leakage of the same pair with the 230V pair shorted 160µH, flat from 1kHz to 100kHz. Series phasing of both pairs was verified by driving one 22V winding and reading the sum across each candidate series pair; both follow Antek's own convention.

— Rev 51: the ratio corrects Rev 48. Rev 48 took 44V as a full-load figure, put about 50V of turns behind it and expected the open-circuit output near 72V. The measured open-circuit ratio is 5.23, which is 115/22 to three figures — the nameplate ratio is the turns ratio for this part, and the output at 15.3V RMS is 80V RMS, 113V peak, the top of the 70–80V band. Under Rev 48's own rule the station R1a/R1b stay at their present value; no station change. Regulation into the expected ring load is now calculable and is negligible — see §9.4.

— Rev 51: the leakage figure corrects Rev 48, which expected low single-digit microhenries from a report on a 6V unit of the same series and said R_SNB would fall to the tens of ohms with the ring frequency rising toward 1MHz. The measured 160µH is sixty times that and within a factor of 1.6 of the 100µH §8.5's parts already implied. √(160µH / 10nF) is 126Ω, so R_SNB stays at 100Ω 1W and the ring is about 125kHz rather than 159kHz, still three times the carrier. The snubber's justification now runs forward from a measurement; §9.3's Rev 38 complaint that it ran backward from the parts is closed.

— Rev 51: magnetizing inductance confirms §7.2. 3.10H at 20Hz is 390Ω of reactance, 37mA RMS at 15.3V, about 12mA of it the in-phase core-loss component — the "tens of milliamps" Rev 48 assumed, against 8A for the OSD. The 1kHz figure is 0.57H, a fifth of the 20Hz one; that is eddy-current shielding of the laminations and is why a 1kHz measurement, as §9.2 was made for the OSD, is not the number that matters at 20Hz.

— Rev 51: §7.6's shorted-output paragraphs are reworked with measured resistances, and one Rev 48 statement is withdrawn. Rev 48 said the Antek's drive-side resistance was "a fraction of an ohm" and a shorted output would reflect to the bridge as "something close to a short", with F1 opening in milliseconds. The drive pair is 2.2Ω and the output pair 46Ω, which referred through 5.23² is 1.7Ω, so a shorted ring bus is about 4Ω at the bridge — roughly 3.6A RMS from 15.3V. F1 at 500mA slow-blow opens in seconds, not milliseconds; the MOSFETs and the LRS-150-24 do not notice either way. On the ring side the same short is about 0.8A, so F2 at 250mA fast still opens well ahead of F1 on the switchboard branch. The fusing order Rev 28 argued for holds; only the speed was overstated.

— Rev 51: the lead colours and splices are recorded in §9 and §10.9 so the transformer can be wired from the document. Antek's sheet: each 115V winding is RED/BLACK, each 22V winding is GREEN/BLUE, PURPLE is the static shield. With the windings numbered 1 and 2 by which GREEN/BLUE pair was driven during the phasing test: drive pair splice BLUE1–GREEN2, GREEN1 and BLUE2 to J7; output pair splice RED1–BLACK2, BLACK1 and RED2 to J8. The second unit on hand has not been phased and the numbering is per unit; verify before splicing it.

— Rev 51: two measurement notes for whoever repeats this. The WaveForms Impedance tool must be set to "Adapter" when the Impedance Analyzer Adapter is used; in the manual W1-C1-DUT-C2-R-GND mode the adapter's relays are not driven, no reference is in circuit, and the tool reports tens of kilohms with a "resistor too low" flag whatever the reference setting. And a 10Hz–1kHz sweep with no averaging read about 180Ω at 20Hz where the Meter view with 500ms averaging read 410Ω twice; the sweep agrees with the meter at 1kHz. The averaged single-frequency figure is the one recorded. The 20Hz point on a fast sweep is a cycle or two of data and should not be read for a low-frequency inductance.

— Rev 52: first power-up with the Antek, 2026-09-16, and one part added. The drive side passed: J10 showed a clean 20Hz sine at ±22V with the rail steady and the bench supply reading 30mA — the operating-point check on §9.3's 37mA small-signal magnetizing figure, and against the 1A limit and collapsing rail of 2026-09-04. The output side did not: J8, read through an 11:1 resistive divider into the Analog Discovery, was not a sine but the 40kHz carrier at ±125V with a 20Hz duty envelope, and its peaks clipped the ±25V input — above ±250V at the winding. A 1µF 250V film capacitor from stock clipped across J8 turned it into a sine: 78.9V RMS on the DMM, about 81V read from the scope trace, against 80V predicted in §9.2. The §12.6 start at SINE_STEPS/4 was already in `ring/ring.ino` for this run — Claude Code made the change before first power-up — so the first-half-cycle saturation §12.6 describes was never exercised on the Antek; the verification capture in §12.6 is still to be made. The generator then rang a Western Electric 304 desk set — supply 30mA idle, 60mA ringing, about 9mA in phase at the bell — recorded in §9.5 as the first end-to-end ring and as a load figure heavier than service will ever present. That capacitor is C_OUT, new §9.6, and is on the BOM from the existing 1µF row.

— Rev 52: why the output was the carrier. A transformer transforms voltage. The primary sees the bridge's 0/24V PWM at 40kHz and the secondary sees 5.23 times that; the 20Hz sine is only the average of the pulse train and exists on the output only after something integrates it. The magnetizing inductance integrates nothing — it is in parallel with the winding, not in series with the output. §8.7 said "the 20Hz sine exists only as the transformer's integral of it" and §12.2 relied on "T1's 20kHz passband" and on "multiples of 5kHz, which neither T1 nor a ringer passes"; all three were beliefs carried from the OSD audio transformer, whose output was never seen unsaturated, and none was ever tested. The peaks above ±250V are §9.3's 160µH of leakage — 4.4mH referred to the secondary — ringing against the winding's own stray capacitance on every PWM edge, undamped because nothing was loading it. Every downstream part in the ring zone is rated 250V or 300V against an expected 113V peak, and would have had no margin.

— Rev 52: why it was not caught earlier, recorded because the document has this failure class in its history already. The transformer was reviewed as a 20Hz device — flux, magnetizing current, ratio, start phase — and never as a 40kHz transmission path. The Rev 48 list of what the transformer change touched was complete for the core and silent on the winding. The leakage was measured at Rev 51 and used only to size the snubber; 4.4mH on the secondary was one multiplication away and was not made. §8.7's own existence — a filter is needed to see a sine on the primary — implied the secondary needed one too. The lesson is the one PROJECT_INDEX.md already draws: a statement carried over from a retired part is a claim to re-derive, not a fact to cite.

— Rev 52: C_OUT, sized from the Rev 51 measurements. Across J8, RING_HI to RING_LO, ahead of F2 and both branches. The 4.4mH of leakage referred to the secondary is already in series between the bridge and that node, so C_OUT makes a second-order low-pass with it: 1µF gives a corner near 2.4kHz, about 280× attenuation at 40kHz (125V pulses become under half a volt of ripple), and 8kΩ of reactance at 20Hz, 10mA reactive on the secondary and 50mA reflected to the bridge. The loop's 106Ω of copper damps it at Q ≈ 0.6 with no resistor added — the payoff for having measured Rs. A capacitor across the primary instead would sit directly on the switch nodes with nothing between it and the MOSFETs; on the secondary the leakage is in the right place. 2.2µF would give 1.6kHz and 600× at 22mA reactive; 1µF is enough.

— Rev 52: what C_OUT changes elsewhere. The leakage now carries the carrier's ripple current the way a buck inductor does — up to about 0.9A peak-to-peak triangular at the primary worst case, 0.3A RMS, 0.2W in the drive copper and 0.15A RMS at 40kHz in C_OUT itself. Both are inside every rating involved and the supply's 30mA shows the average is unaffected; §9.6 gives the arithmetic. The §8.5 snubber analysis is unchanged — the turn-off ring is leakage against switch-node capacitance and C_OUT sits at the far end of the leakage — but the switch node should be scoped with C_OUT fitted, as §8.5 already asks. §7.6's fault arithmetic is unchanged: C_OUT is upstream of F2 and its 10mA never crosses the fuse, and a shorted output shorts the capacitor with the winding. §14 gains a line: C_OUT holds about 6mJ at peak and discharges through the 46Ω winding in microseconds, so there is no stored charge after power-off. §9.4's V_measured is recorded at 81V RMS; station R1a/R1b stay. §13 puts C_OUT beside J8 in the ring zone.

— Rev 52: BOM — 1µF 250V film generator 0 → 1, total 16 → 17 against 20 on hand, nothing to buy. Library plan: same row 16 → 17, the generator now placing one of the footprints the station already needed. Antek row notes updated from "measure before" to the measured figures.

— Rev 53: §15.3's closing paragraph withdrawn to match station Rev 3.28. It said the tap strip's receive channel gives "a second and more direct reading" of which circuits the operator is bridged to, and that the two readings should agree. Station Rev 3.28 records that neither reading was actually being produced — the station detector never looked at bin 768 on circuit channels, and the tap channel hears both ends of a cord pair in normal service, which that detector would have reported as a fault — and settles it the other way: every station and trunk channel checks bin 768 itself and reports operator presence per circuit on sbgame/<type>/<n>/op; the tap's receive channel is monitor-only. Nothing on this board changes. Recorded here because §15.3 was the document that first made the claim, and a reader following its pointer to station §8.8 would otherwise find the opposite of what it promised.

— Rev 54: the MQTT topic prefix is sbgame/, not sw/, following station Rev 3.29. The Rev 53 entry above is restated with the new prefix; nothing else in this document names a topic. Nothing on this board changes and ring/ring.ino carries no topic strings.

— Rev 55: formatting only. Two things. Every table in §10 and the §11 netlist had no header row — the first part or net was sitting in the header position above the `---` separator, so a renderer showed `PS1 | Mean Well LRS-150-24 | …` in bold as column headings and the real first row was missing; twelve tables, each now headed Designator / Part / Notes or Net / Connections. And the signal-path diagrams, GPIO and pin lists, truth table, bridge topology, measurement listings and firmware constants — seventeen blocks — are now fenced code blocks; they had been fixed-width text with a blank line between every row, an artefact of the docx extraction, which renders as run-together prose. Same sweep as station Rev 3.31 and trunk Rev 5.32. No word of the content changes.

— Rev 56: the firmware sections move to control.md, following station Rev 3.34 and trunk Rev 5.35. §6.1, §6.2 and all of §12 are now pointers; §4.5 and the last two paragraphs of §4.7 likewise. control.md is the specification the firmware is written to and states, for the first time, the startup order across all three of the controller’s jobs and the full list of conditions on which relays are released. Nothing about the hardware on this board, and nothing in the specified firmware behaviour, changes; ring/ring.ino is unaffected and stays on the Claude Code side.

— Rev 57: follows station Rev 3.35 — three station boards built. §2.2, §4.1 and §4.7 no longer describe board 3 as unfitted capacity; the I²C chain is generator, station 1, 2, 3, trunk, and the scan list is 0x20–0x23. Nothing on this board changes.

— Rev 58: no design change. §9.7 records an alternative topology raised on 2026-09-18 and never considered before: a high-frequency link — a small ferrite transformer driven at tens of kilohertz, rectified to a DC bus of about 115V on the secondary side, and a second H-bridge synthesising the 20Hz sine from that bus with the same sine PWM the board already uses, into a discrete LC filter. It moves the transformer's job from 20Hz to 50kHz and shrinks the core by three orders of magnitude. It was not on the table at Rev 48: when the OSD saturated, the response was a larger core at 20Hz, and the question of whether the core had to be at 20Hz at all was not asked. §9.5's "two directions were considered" now points at §9.7 as the third.

— Rev 58: the conclusion is that the present design stays. It is built, measured and has rung a bell; the alternative buys weight and volume the rack does not need, and pays for them with a 115V DC bus on the board, a second converter stage, MOSFETs and drivers in the 200V class, a current limit that the winding copper currently supplies for free, stored energy that §14 would have to address, and an inductor that the Antek's leakage currently supplies for free. §9.7 records the trade-offs, the cases in which the balance would tip, and the note that commercial 12V-to-90V 20Hz ring generator modules use exactly this topology.

— Rev 59: no design change. §9.7 gains a closing paragraph on the modulator, raised the same day: an analog comparator with the 20Hz sine on one input and a high-frequency sawtooth on the other is the classical way to make this PWM, and it is what the LEDC peripheral does digitally — its counter is the sawtooth and the duty write is the sine sample. Recorded because the two are the same principle and the differences (a stepped versus continuous reference, where the amplitude trim lives, what happens when the controller hangs) are worth having in one place beside the topology alternative.

— Rev 60: no design change. §9.7 gains the stage-2 filter sizing and a damping finding, and a reference. The filter is the same LC as §9.6 — 1µF and about 4.4mH, the leakage figure by construction — but a discrete inductor has a few ohms of DCR where the toroid's copper supplied 106Ω, so the same filter has Q ≈ 13 instead of 0.6 and needs damping fitted: 47–68Ω in series with the inductor, which also recovers most of the fault-current limit §9.7 listed as needing a design. The start-phase requirement of §12.6 inverts in this topology, since there is no core in the 20Hz path and the LC wants a zero-crossing start rather than a peak. The reference is the video that prompted the idea; the consumer inverter it describes is this topology with the numbers moved. Nothing on this board changes.

— Rev 61: cross-reference only. The controller's specification is `control.md`, renamed from `esp32.md`, and the firmware is `control/control.ino`, renamed from `ring/esp32.ino`, both on 2026-09-19 (control.md Rev 9). Every pointer in §4.5, §4.7, §6.1, §6.2 and §12 follows, and the Rev 56 entry above now reads the new names. `ring/ring.ino` in the Rev 44, 52, 54 and 56 entries is history and stays. Nothing on this board changes.

— Rev 62: cross-reference only. §15 put the operator tap on station board 1. It moved to board 3 at station Rev 3.35, and to strip 7 of that board at station Rev 3.40, when strip 8's A32 output, channel 24, became the audience monitor feed in place of the Digiface's own analog output. §15 follows; §15.5's channel-budget argument is unchanged, since all 32 A32 channels are still allocated. The Rev 27 entry keeps board 1 as history. Nothing on this board changes.

— Rev 63: bench record only. §9.4 gains a second V_measured, 2026-09-25, the first run on the firmware without the arming gate (control.md Rev 11) and with the 74HCT04 fitted: 15.2V RMS drive at J10, 79.3V RMS output through the 11:1 divider, ratio 5.22, 20.0Hz. It agrees with the 2026-09-16 record and with the §9.2 prediction. Nothing on this board changes.

# 2. Signal Path

## 2.1 Ring Generator

```text
Olimex GPIO32 —► 74HCT04 Gate 1 —► Gate 2 —► IN1 —► IR2104 #1 IN
                          |
                          └—► Gate 2 (input A) —┬
Olimex GPIO33 ———————————► Gate 2 (input B) ┴—► IN2 —► IR2104 #2 IN
Olimex GPIO14 —► Gate 3 —► Gate 4 —► IR2104 #1 & #2 SD  (5V; 10kΩ pull-down at GPIO14)
```

Olimex GPIO4  ◄— Master enable input (active LOW, internal pull-up)

## 2.2 I²C Bus

```text
Olimex GPIO13 (SDA) —► J3 (6P6C pin 4) —► station/trunk boards
Olimex GPIO16 (SCL) —► J3 (6P6C pin 2) —► station/trunk boards
Pull-ups: 2.2kΩ SDA→+3.3V,  2.2kΩ SCL→+3.3V
          fitted on this board only — DO NOT FIT on other boards
```

MCP23017 addresses:

```text
  Station board 1 : 0x20
  Station board 2 : 0x21
  Station board 3 : 0x22
  Trunk board     : 0x23
```

# 3. Olimex ESP32-POE-ISO

The Olimex ESP32-POE-ISO carries an ESP32-WROOM module, LAN8710A Ethernet PHY, 802.3af PoE receiver, and a 2W isolated DC-DC converter between the PoE supply and the board’s 3.3V rail. Galvanic isolation (3000V DC) is on the Ethernet side; board GND is common with the rest of the system.

## 3.1 GPIO Constraints

The LAN8710A PHY uses the RMII interface and takes its 50MHz reference clock from the ESP32. Between them these permanently occupy the following GPIOs, which must not be used for any other function:

```text
  RMII data and control:  GPIO19, GPIO21, GPIO22, GPIO25, GPIO26, GPIO27
  SMI management:         GPIO18 (MDIO), GPIO23 (MDC)
  PHY 50MHz clock out:    GPIO17  (EMAC_CLK_OUT_180)
  PHY power enable:       GPIO12  (on some Olimex revisions)
```

GPIO17 is the one that matters, and Rev 13 had it wrong twice over in the same section — listed as reserved, then assigned to I²C SCL two lines later. The LAN8710A on this board has no crystal of its own; it is clocked from the ESP32 on GPIO17. Taking that pin for anything else does not degrade Ethernet, it stops the PHY, and with it MQTT and the host link.

I²C therefore moves to GPIO13 (SDA) and GPIO16 (SCL) — the pins Olimex itself brings out for I²C on this board's UEXT connector, which is the useful confirmation that both are free — and SD control moves to GPIO14. GPIO14 is not a strapping pin and R_SD_PD holds it low through boot, so the safe power-on state is unchanged.

Verify all four assignments against the Olimex schematic for the board revision in hand before committing the footprint. Olimex has changed pin usage between ESP32-POE variants, and this is the single assumption in this document whose failure costs a respin rather than a firmware edit.

## 3.2 GPIO Assignments

```text
  GPIO32  LEDC CH0   PWM output A (IN1 via 74HCT04 gates 1-2, active HIGH)
  GPIO33  LEDC CH1   PWM output B (IN2 via 74HCT04 gates 3-4, active HIGH)
  GPIO14  Output     SD enable via 74HCT04 gates 5-6 (HIGH = on, LOW = off)
  GPIO4   Input      Master enable (active LOW, internal pull-up) — J9 pin 1
  GPIO5   Output     Expander /RESET (active LOW, idles HIGH) — §4.7
  GPIO13  I²C SDA    I²C data  (2.2kΩ pull-up to 3.3V on this board)
  GPIO16  I²C SCL    I²C clock (2.2kΩ pull-up to 3.3V on this board)
```

GPIO15 Output  Waveform sync, for scope and logic analyser triggering — §12.5. Assigned at Rev 42; brought out on J9 pin 3 at Rev 43.

GPIO15 was assigned to the operator tone injector at Rev 21, freed again at Rev 27, and taken at Rev 42 for the waveform sync output — see §15 for the first use and §12.5 for the present one. It was never listed above, which is worth noting because the argument in the old §15.1 for choosing it depended on this list being complete. Anything wanting a spare output should still verify against the Olimex schematic for the board revision in hand, and should remember that GPIO15 is a strapping pin that must be high at boot.

## 3.3 PoE Power Budget

802.3af delivers up to 12.95W to the powered device. The Olimex’s internal 2W isolated DC-DC converter is the binding constraint. All H-bridge, driver and transformer power comes from the 24V bus. The only loads this board puts on PoE are the 74HCT04 on +5V and the I²C pull-ups on +3.3V, a milliamp or two together — see §7.4.

## 3.4 Programming

Program via USB while PoE is disconnected, or use OTA. The -ISO variant tolerates USB and PoE simultaneously; confirm from the Olimex documentation. Prefer OTA for updates in the installed system.

# 4. I²C Bus

## 4.1 Topology

The Olimex ESP32-POE-ISO is the sole I²C master. The bus daisy-chains from this board through up to three station boards and terminates at the trunk board. This board carries one 6P6C jack (J3, output only); each station board carries two (in and through); the trunk board carries one (end of chain). All three station boards are built, so the chain is generator, station 1, station 2, station 3, trunk.

```text
  ring generator ——[RJ11]—— station 1 ——[RJ11]—— station 2 ——[RJ11]—— TRUNK
  (master, 1× jack)    (2× jack, thru)  (2× jack, thru)  (1× jack, end)
  Total bus length ≈ 600mm
```

The 6P6C connector is distinct from the RJ45 used for trunk lines and the D-Sub25 used for audio. A 6P6C plug fits physically into an RJ45 jack but an RJ45 plug will not enter a 6P6C jack, so the hazard is one-directional and fully contained. Keep 6P6C jacks at the low-voltage edge of each board, away from trunk and ring wiring.

## 4.2 6P6C Pinout

The following pinout applies to J3 on this board and to both 6P6C jacks on the station and trunk boards. Use straight-through cords only — see cabling note below.

| Pos. | Signal | Pair | Notes |
| --- | --- | --- | --- |
| 1 | /RESET | 3 (1–6) | /RESET — expander hardware reset, paired with GND at position 6 |
| 2 | SCL | 2 (2–5) | I²C clock — paired with GND at position 5 |
| 3 | GND | 1 (3–4) | SDA return — paired with SDA at position 4 |
| 4 | SDA | 1 (3–4) | I²C data — paired with GND at position 3 |
| 5 | GND | 2 (2–5) | SCL return — paired with SCL at position 2 |
| 6 | GND | 3 (1–6) | /RESET return — paired with /RESET at position 1 |

Each signal has its return on its own pair: SCL with GND at position 5, SDA with GND at position 3, /RESET with GND at position 6. A grounded conductor is interleaved between SCL (position 2) and SDA (position 4), which reduces capacitive coupling between clock and data by approximately 12dB compared to placing them adjacent. This matters because a clock edge coupled onto SDA while SCL is high is interpreted as a START or STOP condition — a corrupted transaction rather than a corrupted byte.

All six positions are now occupied, so the cords must be six-conductor. A four-conductor cord in positions 2–5 still carries a working I²C bus, and the system runs — it simply has no hardware reset, and every expander sits at its local pull-up. That is a usable degraded mode, not a failure, and worth knowing when a cord is the only one to hand.

## 4.3 Cabling

**Use straight-through cords only.** Standard voice line cords are wired reversed end-to-end (position 2 lands on 5, 3 on 4), which with this pinout shorts SCL to GND and SDA to GND. That is a harmless failure — the pull-ups source about 1.5mA into ground, nothing is damaged, and the bus is dead, which the startup scan reports immediately as all devices missing. But reversed cords are the commonly stocked kind: crimp the cords for this system deliberately and label them.

Prefer round twisted six-conductor cable over flat satin cord. Either works with this pinout, but twisted cable gives better common-mode rejection.

## 4.4 Pull-ups

2.2kΩ pull-up resistors from SDA to +3.3V and from SCL to +3.3V are fitted on this board only (R_SDA, R_SCL). Station and trunk boards must not fit pull-ups on their I²C lines — their footprints should be marked DO NOT FIT on the silkscreen rather than left empty. Multiple pull-up sets in parallel lower the effective resistance and slow the bus.

2.2kΩ at ~50pF estimated total bus capacitance gives a rise time of approximately 94ns, well within the 1µs I²C budget at 100kHz.

## 4.5 Bus Initialisation

Moved to control.md §4.2 (step 5) at Rev 56: scan the configured device list before arming, drive the list from the configured board count rather than hard-coding it, and do not arm the H-bridge if a required expander is absent. The bus is polled; there is no INT line.

## 4.6 Mis-plug Protection — TVS2

A 6P6C plug fits physically into an RJ45 jack, and RJ45 carries 141V peak trunk line and 127V peak station line elsewhere in the system. The station and trunk boards each fit a 3.3V low-capacitance TVS array on SDA and SCL against exactly that case. This board had none, which was backwards: the bus is a single node, so line voltage arriving at any jack on the chain arrives here too, and what it reaches here is the master.

C_TVS2, 100nF from pin 8 to pin 4, is fitted at the device as of Rev 34. The SP721 does not shunt to ground; it conducts the transient from the IN pin into V+, so V+ has to be able to source that current locally or it lifts during the event and the clamp degrades exactly when it is needed. The datasheet’s own peak-current test circuit hangs a capacitor across V+/V− for the same reason. Only the V+ side needs one: V− is pin 4 and goes straight to GND, so bypassing it to ground is a zero-length connection. 100nF rather than the datasheet’s suggested 0.01µF because it is the part already stocked in quantity and the extra capacitance costs nothing here.

What is deliberately not fitted is the series resistor the same datasheet note suggests. That note is written for automotive load-dump and reverse-battery conditions, and the resistor is there to limit reverse current into the supply pins. Nothing on this board sees a reverse battery, and series resistance in the V+ feed would raise the clamp’s dynamic impedance — the opposite of what is wanted.

Fit TVS2 on SDA and SCL at J3 — the same part as the station and trunk boards, a Littelfuse SP721APP at 3pF per line. If line voltage does arrive, the array clamps or fails short; a short pulls the bus down and stops the system, which is the outcome to want when the alternative is 127V into the Olimex, three expanders and the Ethernet side of the rack. The timing cost is nothing: roughly 3pF added to a ~50pF bus with a 94ns rise time in a 1µs budget.

The SP721APP is specified because it is the only credible through-hole option, and one surface-mount part on an otherwise through-hole board is a poor trade for capacitance that is not needed. It is not a fixed-breakdown TVS but a rail clamp: six inputs, each with SCR/diode structures that trigger one VBE above V+ or one VBE below V−. Tie pin 8 to +3.3V, pin 4 to GND and two of the six inputs to SDA and SCL. Four inputs are left spare on every board that fits one.

3pF per line rather than the 1pF earlier revisions assumed. The margin absorbs it without argument: 6pF across the pair against roughly 50pF of bus capacitance moves the 94ns rise time in §4.4 by nothing that matters against a 1µs budget.

## 4.7 Hardware /RESET

Positions 1 and 6 of the 6P6C were spare and are now the expander reset line. GPIO5 on the Olimex drives /RESET to every MCP23017 in the chain — three station boards plus the trunk board. There is no expander on this board, so this line is generated here and consumed everywhere else.

The line is active low and idles high. GPIO5 is chosen because it is a strapping pin that must be high at boot, and the safe idle state of an active-low reset is also high — the requirement and the design intent point the same way, so a pull-up satisfies both. Verify GPIO5 against the Olimex schematic for the board revision in hand, as with every other pin assignment in §3.1.

Pull-ups sit on each expander board rather than once at the master, which is the opposite of the rule for SDA and SCL in §4.4 and the difference is deliberate. Parallel pull-ups on an I²C bus lower the effective resistance and load the bus; on a static line driven by a CMOS output, three 10kΩ resistors in parallel are 3.3kΩ and the driver does not notice. What local pull-ups buy is that a board unplugged from the chain still holds its own expander out of reset instead of leaving the pin floating, and the MCP23017 reset pin must not float.

/RESET leaves the board on a connector that a station or trunk line can be mis-plugged into, so it gets the same protection as SDA and SCL: a third input of TVS2, which had four spare (§4.6).

What the line is for is recovery. The MCP23017 comes out of reset with IODIR = 0xFF and every pin an input, so a reset drops every relay it controls — off-hook relays on the station boards, ring relays on the trunk board. R_pd holds the drivers off through the window between reset and reconfiguration, which is the case station §5.2 and trunk §7.3 were already written around; the difference now is that the window can be entered deliberately rather than only at power-on.

When the firmware asserts it, the pulse sequence, and the rule that it is never asserted while ring is applied, are control.md §6.2 as of Rev 56.

# 5. 74HCT04 Level Translation and SD Buffer

A 74HCT04 hex inverter, all six gates used, each signal routed through two of them. Gates 1–2 buffer PWM output A, gates 3–4 buffer PWM output B, gates 5–6 buffer the shutdown line. Two inversions each, so every path is non-inverting: IN1 = GPIO32, IN2 = GPIO33, SD = GPIO14. The part runs from the Olimex +5V pin, so everything the IR2104 sees is 5V logic.

This replaces the 74HCT02 at Rev 44. The NOR part arrived at Rev 5 for an interlock that Rev 40 established was never needed, and once the cross-coupling went, all four gates were NORs with their inputs tied — inverters written the long way. A hex inverter does the same work with one input per gate and no tied pairs to leave half-connected.

The reason for two gates per signal rather than one is polarity, and it is the point of the change. A single inversion makes the PWM pins active low, which is what the board has had since Rev 5, and active low is where every polarity defect in this document came from: parking LEDC at 0 duty then means IN1 high with IN2 low — Q1 and Q4, the full rail across a 0.63Ω primary as DC. §6.1 and §6.2 specified exactly that from Rev 5 to Rev 29. With two inversions the drive is active high, LEDC’s own power-on state of 0 duty is IN1 = IN2 = low, and that is Q3 and Q4 with the primary shorted to ground. The safe state becomes the default rather than something firmware has to remember to write.

It costs 26ns of extra propagation delay typical and 46ns maximum — SCLS042F gives 13ns typical and 23ns maximum per gate at VCC 5.5V, and there are two of them. Against a 25µs carrier period that is a fifth of one percent. Rev 44 said about 20ns, which was a guess at one gate’s delay doubled rather than a figure from the datasheet.

It leaves no spare gates, and that turns out to be an advantage rather than a wash. SCLS042F §5.2 note 1 and §9.1 both require every unused input to be tied to VCC or GND; with all six inverters carrying signal there is no unused input to forget. The 74HCT02 also left none spare, so nothing is lost. R_PWMA_PU and R_PWMB_PU become R_PWMA_PD and R_PWMB_PD, same value, to GND instead of +3.3V.

What gates 1 and 2 are for is level translation, and that is the whole of it. Rev 5 through Rev 30 called them an interlock and §14 called them a continuous hardware guarantee against shoot-through, which is not something they can provide. Each IR2104 takes one IN pin and derives HO and LO from it internally, complementary, with built-in deadtime of 520ns typical — 400ns minimum, 650ns maximum, per IR PD60046-S. No input combination turns the high and low side of a leg on together, because the driver never presents that combination to the gates. Shoot-through within a leg is handled inside the IR2104, upstream of anything the gate can reach.

Gate 2 was wired from Gate 1’s output from Rev 5 to Rev 39, making IN2 = GPIO32 AND /GPIO33 and forbidding the state IN1 = IN2 = high. Rev 40 moves Gate 2 input A to GPIO33, so both its inputs tie together like the other three and IN2 = /GPIO33. The cross-coupling is gone.

The reason is that the constraint was worth less than nothing. What it forbade was Q1 and Q2 — both high sides, both ends of the primary at +24V, no path to ground and no current. A zero vector, not a fault. What it cost was the direction of the natural failure. With the cross-coupling, both GPIOs low gave IN1 high and IN2 low, which is Q1 and Q4: the full rail standing across a 0.63Ω primary as DC. Without it, both GPIOs low gives IN1 = IN2 = high, the harmless zero vector. The safe state and the dangerous one have swapped places.

That is the condition R_PWMA_PU and R_PWMB_PU were added at Rev 30 to defend against, and the one §6.1 and §6.2 walked into by parking at zero duty from Rev 5 to Rev 29. Both defences stay — the pull-ups still make the boot state deterministic and the park value is still full scale — but they are no longer the only thing between a floating GPIO and a DC short. The topology now fails safe on its own.

One net, and nothing else changes: same part, same gate count, same package, same firmware. Both PWM pins remain active LOW, the park value remains DUTY_MAX, and the duty tables are untouched — during the positive half-cycle GPIO33 is held high, which gave IN2 low before and gives IN2 low now. It also decouples the two channels, which the old arrangement did not: a glitch on GPIO32 propagated into IN2.

The HCT suffix is not interchangeable with HC here and the substitution is the whole point of the revision. A 74HC part at VCC = 5V wants VIH of 0.7 × VCC, which is 3.5V, and the ESP32 GPIOs deliver 3.3V — moving an HC part to 5V would take the marginal threshold off the IR2104 input and put a worse one on the gate input. The HCT part has TTL thresholds, VIH 2.0V, so it accepts 3.3V comfortably on the input side and drives 5V on the output side. That is exactly the translation this board needs, in a package it already has.

## 5.1 Circuit

**Gate 1:** GPIO32 → pin 1. Output pin 2 → pin 3. Gate 2 output pin 4 → IN1 (IR2104 #1 IN). Two inversions, so IN1 follows GPIO32.

**Gate 2:** GPIO33 → pin 5. Output pin 6 → pin 9. Gate 4 output pin 8 → IN2 (IR2104 #2 IN). IN2 follows GPIO33.

**Gate 3:** GPIO14 → pin 11. Output pin 10 → pin 13.

Gate 4: output pin 12 → SD on both IR2104s. GPIO14 buffered and level-shifted to 5V; the polarity at SD matches GPIO14 and the boot state is unchanged. The pinout — 1A 1, 1Y 2, 2A 3, 2Y 4, 3A 5, 3Y 6, GND 7, 4Y 8, 4A 9, 5Y 10, 5A 11, 6Y 12, 6A 13, VCC 14 — is VERIFIED against TI SCLS042F §4, 14-pin PDIP top view. Rev 44 took it from the 7404 convention and flagged it as unchecked; the convention held, which the 7402 did not.

## 5.2 Truth Table

```text
  GPIO32  GPIO33 | IN1   IN2
  ───────────────┬───────────
    L       L    |  L     L     both low sides on — primary at GND (park)
    L       H    |  L     H     IR2104 #2 drives, #1 clamps low
    H       L    |  H     L     IR2104 #1 drives, #2 clamps low
    H       H    |  H     H     both high sides on — primary at +24V
```

The table is the Rev 40 table with both columns inverted, which is the whole effect of the polarity change. All four states are reachable and none is dangerous. The two middle rows are the drive states the firmware uses. The last row, both GPIOs high, is Q1 and Q2 — both ends of the primary at the rail, no path to ground, no current.

The first row is the one that matters. Both GPIOs low is Q3 and Q4, both ends at ground, the state in which the bridge is genuinely off — and it is now also LEDC’s power-on state, the park state §6.1 and §6.2 use, and the boot state §5.3 relies on. Under the 74HCT02 that row read H L: Q1 and Q4, the rail across the primary as DC, and everything from the Rev 30 pull-ups to the Rev 29 firmware correction existed to keep the board out of it.

Rev 5 through Rev 30 labelled the both-low-IN row "both inhibited", which it is not — nothing is inhibited, both drivers are actively holding their leg at ground. Inhibiting is what SD does.

## 5.3 Boot State

GPIO32 and GPIO33 are held low through boot by R_PWMA_PD and R_PWMB_PD, 10kΩ each to GND. Both IR2104 IN pins are therefore low — H-bridge off before firmware runs. The resistors changed from pull-ups to pull-downs at Rev 44 with the polarity; the reasoning below is unaffected, since it is about floating inputs rather than about which rail they are pulled to. GPIO14 is held low by R_SD_PD through boot, so the Gate 4 output is low and SD is low as well — shutdown in force: the bridge is off by two independent mechanisms before any firmware runs.

The two resistors are new at Rev 30 and became pull-downs at Rev 44. Rev 5 through Rev 29 asserted that GPIO32 and GPIO33 default high on boot and fitted nothing to make it so. They do not: GPIO32 and GPIO33 are among the ESP32 pins with no internal pull at reset, so both inverter inputs floated through the bootloader window.

Floating is not the same as low, and the distinction matters more since Rev 40 than it did before. Both pins driven low is now the park state itself — IN1 = IN2 = low, Q3 and Q4, primary at ground. That says nothing about both pins undriven. Each gate now resolves independently, and two of the four outcomes are the full rail across the primary: IN1 high with IN2 low is Q1 and Q4, IN1 low with IN2 high is Q2 and Q3. A floating HCT input sits near its own threshold, so which of the four appears is not predictable and need not be the same on successive boots.

Nothing conducts, because SD is low. But that is one mechanism and not two, and it is why the resistors are not made redundant by the Rev 40 or Rev 44 changes: the interlock removal fixed a determinate state, the pull-downs fix an indeterminate one, and neither substitutes for the other.

Two reasons hold independently of the bridge. TI specifies it outright — SCLS065G §5.2 note 1 requires all unused inputs to be held at VCC or GND, and §9.1 states that inputs must never be left floating because undefined voltages give undefined operational states. And a floating HCT input holds both transistors of its output stage partly on, drawing supply current and liable to oscillate, for the whole bootloader window on every boot. Neither has anything to do with what the H-bridge is doing.

The pull-downs go to GND, which needs no rail at all — an improvement on the pull-ups they replace, since those ran from the Olimex +3.3V and were unpowered in exactly the PoE-absent case §7.4 describes. 10kΩ against a push-pull GPIO output is nothing to overcome once firmware runs, and a pull-down against an HCT input needs no threshold argument: 0V is 0V.

## 5.4 Pin Connections

```text
  VCC     : Olimex +5V, EXT1 pin 1 (pin 14)
  GND     : GND (pin 7)
  Gate 1  : pin 2 = GPIO32, pin 3 = GPIO32, pin 1 (out) = IN1 & Gate 2 in A
  Gate 2  : pin 5 = Gate 1 out, pin 6 = GPIO33, pin 4 (out) = IN2
  Gate 3  : pin 8 = GPIO14, pin 9 = GPIO14, pin 10 (out) = Gate 4 in
  Gate 4  : pin 11 = Gate 3 out, pin 12 = Gate 3 out, pin 13 (out) = SD
  Bypass  : 100nF ceramic, pin 14 to pin 7 (at the device)
```

# 6. SD Control

Say it in levels, not in states. SD LOW is shutdown; SD HIGH is enabled. This document previously wrote "SD asserted" for the low condition, which is correct but reads backwards to anyone scanning — SD is the shutdown signal, so asserting it means driving the pin down. Rev 37 uses the level everywhere and drops "asserted" for this net.

That convention is what makes the double inversion necessary rather than decorative. Gate 3 gives /GPIO14 and Gate 4 gives GPIO14 back, so the pair is a non-inverting buffer: GPIO14 low puts SD low and the bridge off. A single gate would invert, and R_SD_PD holding GPIO14 low would then drive SD high and enable both drivers before firmware runs — the failsafe exactly backwards. The second gate is load-bearing; the pull-down only means what it means because of it.

R_SD_PD2, 10kΩ from the SD net to GND, is added at Rev 37. R_SD_PD sits on the GPIO14 side and therefore only works while the gate is powered. With PoE absent and the 24V bus live — §7.4 — the +12V rail is up and both IR2104s are alive, but the gate has no supply and SD is left to whatever an unpowered CMOS output settles at. §7.4 argues that is near 0V, which is very likely right, but it rests on the output stage’s parasitics rather than on anything specified. A 10kΩ to ground makes it deterministic. The 74HCT04 sources 4mA and overcomes it without difficulty: VOH stays near 5V, far above the 3V VSD,TH+ minimum. It covers the case the Rev 30 PWM pull-ups do not, since those run from the same dead +3.3V rail.

The IR2104 SD pin is active low, and the datasheet specifies VSD,TH+ at 3V minimum for VCC of 10V to 20V — the same figure as the IN threshold. Rev 13 and Rev 14 of this document both quoted 2.1V maximum, which is wrong and made a 0.3V margin look like a comfortable one. GPIO14 therefore drives SD through gates 5 and 6 of the 74HCT04 rather than directly, so the pin sees a 5V logic high. R_SD_PD (10kΩ from GPIO14 to GND) holds the buffer input low from power-on, which holds SD low, until the ESP32 explicitly drives it high.

## 6.1 Startup Sequence

Moved to control.md §4.2 at Rev 56, where it is now the whole controller’s startup — Ethernet, expander reset, the I²C scan, MQTT and the arming gate ordered against the ring generator’s own steps, which are unchanged: LEDC parked at duty 0, SD low, step timer armed at the peak-phase index, then SD high while GPIO4 is low.

## 6.2 Shutdown Sequence

Moved to control.md §4.3 at Rev 56. SD low first, then both LEDC channels parked at 0.

# 7. Power

## 7.1 System Supply

Mean Well LRS-150-24 (24V, 6.5A), shared across all boards with star wiring from the PSU terminals. This board receives a dedicated pair from the PSU terminals. Set the output to 24.0V under load. The LRS-150-24 has a 115V/230V input select switch; set it before first power-on.

The switchboard's own 24V is a separate leg of that star and does not pass through this board. It runs from the PSU terminals to the switchboard on Anderson Powerpole connectors — polarised, genderless, touch-safe unmated, and rated far above the load. The estimate is 1A steady, with lamp inrush well above that; size the run for the inrush, not the average. Nothing on this board carries it. J1 feeds this board alone and F1 at 500mA is sized for this board alone, so routing the switchboard supply through J1 would mean re-fusing at 1.5A or more, at which point F1 no longer protects what it was put there to protect. The Powerpole run wants its own protection at the PSU end — the LRS-150-24 will source 6.5A into a damaged cable — which is a system-level item and is not specified here.

## 7.2 Board Input Protection

— D1: 1N5822 Schottky, SHUNT clamp across +24V and GND — cathode to +24V, anode to GND, not in series. Reverse-polarity protection with no forward drop. 1N5822, 3A / 40V, DO-201AD axial. The SS34 named through earlier revisions is an SMA/DO-214AC surface-mount part with no through-hole version. 3A is oversized against a 250-500mA fuse and deliberately so: a slow-blow fuse carries well above its rating for some time before it opens. Forward drop is unchanged at roughly 0.3-0.4V.

— F1: 500mA slow-blow fuse, between J1 and the D1 clamp. A fault on this board should not trip the system. Same value as the trunk board; the station boards use 250mA. Littelfuse 0218.500MXP in a 64900001039 block — socketed rather than soldered, on all three board types, so a blown fuse is a diagnosis rather than a rework.

F1 was reviewed at Rev 48 for the transformer change and stands; the measurement at Rev 51 confirms it. The Antek's 44V series pair measures 3.10H at 20Hz (§9.3), 390Ω of reactance, so at 15.3V RMS the magnetizing current is 37mA RMS, an order of magnitude inside 500mA. A shorted ring output reflects to about 4Ω at the bridge and roughly 3.6A RMS (§7.6), which opens F1 in seconds. The first-half-cycle flux transient that a zero-crossing start would produce is removed in firmware (§12.6) rather than absorbed by the fuse. The OSD, had it not saturated, would have drawn about 8A RMS through this fuse (§9.5); no revision computed that figure before Rev 48.

## 7.3 +12V Rail (IR2104 VCC)

Traco TSR 1-24120 (24V→12V, 1A, 15—36V input, SIP-3). Pinout is 1 +Vin, 2 GND, 3 +Vout, verified against the Traco datasheet of 2 July 2026. No heatsink required. Bypass: 47µF electrolytic + 100nF ceramic on input, 100nF ceramic on output (C_12V_OUT), plus C_12V_BULK — see §7.7.

What C_12V_OUT is for, since it is not obvious and the question has been asked. The TSR 1 needs no external capacitor to regulate, and the IR2104s take their gate-drive edge current from C_VCC1 and C_VCC2 at their own pins, so C_12V_OUT is not there for either of them. It is there for the regulator's own switching: the TSR 1 is a buck converter with ripple at a few hundred kilohertz on its output, and C_12V_BULK's ESL makes it a poor bypass at that frequency. The 100nF beside it keeps that ripple at the regulator pin rather than sending it down the traces to the drivers, where C_VCC1 and C_VCC2 would otherwise have to catch it. The board would work without it; it stays as one footprint of insurance for rail cleanliness. Wording added at Rev 49.

The input range is 15 to 36V, not 4.6 to 36V. Rev 19 through Rev 34 gave the wider figure, which belongs to the 9V-nominal members of the series — the 1.2V, 1.5V, 1.8V and 2.5V parts. Each output voltage in the TSR 1 family carries its own minimum input, and the 12V part needs 15V in. Against an LRS-150-24 adjustable over roughly 21.6 to 28.8V there is still margin at both ends, so nothing about the design changes; what changes is that the margin at the bottom is 6.6V rather than the 17V the old figure implied, and any future argument about how far the 24V rail may sag has to start from 15V.

Maximum output capacitance is 470µF. This rail carries C_12V_OUT at 100nF and C_12V_BULK at 10µF, so it is nowhere near the limit and the rail may be added to freely. This does not settle the TSR 2 question on the station and trunk boards — that is a different datasheet and a different limit against a 220µF.

Note the trailing zero. Traco puts the output voltage in the final digits of the part number, so TSR 1-24120 is the 12V part and TSR 1-2412 — which Rev 15 through Rev 18 of this document specified — is a 1.2V part in the same package. Fitting it would put about a volt on the IR2104 VCC pins, below their undervoltage lockout: no ring, no smoke, and a fault that looks like firmware. The same convention explains TSR 2-2450 on the station and trunk boards, which is 5.0V and is correct.

## 7.4 Logic Rails — 5V and 3.3V

Both logic rails come from the Olimex board. The I²C pull-ups run from its 3.3V output pin; the 74HCT04 runs from +5V on EXT1 pin 1, which Olimex documents as usable as an output when the board is powered from PoE or USB.

The budget is not close. The ISO variant's 2W isolation converter caps the whole board at about 400mA at 5V and the Olimex itself draws 50–200mA depending on mode, which leaves a couple of hundred milliamps; the 74HCT04 driving four IR2104 logic pins needs a milliamp or two. IR2104 input bias current is 3µA typical per pin, and the switched charge at 40kHz into a few picofarads is smaller still.

Two things to know about that pin. It is tied to the USB 5V line on the Olimex, so it must not be used to feed power into the board while USB is connected — as an output supplying this board it is fine, but it means programming over USB energises the gate from the USB rail. And if PoE drops, the 5V rail and the SD buffer go with it: the Gate 4 output collapses, SD is no longer held high, R_SD_PD2 pulls the SD net to ground, and R_SD_PD holds GPIO14 low regardless. Losing the controller therefore disables the bridge rather than leaving it in an unknown state.

If the 5V budget is ever contested — anything else added to this board that wants 5V — the alternative is a local 24V→5V regulator, which is what earlier revisions used before the rail was deleted. It costs one part and removes the dependency on the Olimex entirely. There is no reason to fit it for a 74HCT04 alone.

## 7.5 Bulk Decoupling

100µF electrolytic + 100nF ceramic close to the H-bridge MOSFET drains on the +24V switched rail.

## 7.6 Ring Output Fusing — F2

F2 is a 250mA fast-acting 5x20mm fuse — Littelfuse 0217.250MXP in a 64900001039 block — in series with RING_HI between T1's output winding and J6. It protects the switchboard branch of the ring bus only. J2's branch is not fused on this board.

Why one branch and not both. The J2 branch terminates at the trunk board, which fuses its own ring input at its J6 with the same part and the same value; a second fuse in series with that adds a failure point and protects nothing already unprotected. The J6 branch has no board at its far end, so this is the only place a fuse can live for it. The two runs are also not comparable in exposure: generator to trunk is a short run inside the rack, while the switchboard run leaves the rack and is the cable that gets coiled, dragged and stood on.

Fast-acting rather than slow-blow, matching the trunk board's F2. There is no inrush on this branch to ride through — the load is the switchboard's ring key feeding station ringers, which draws its steady current from the first cycle. F1 is slow-blow because it feeds an H-bridge with 100µF of bulk behind it, and that argument does not transfer here.

What F2 buys, since the board is not unprotected without it. With the Antek's measured windings (§9.3): the output pair is 46Ω and the drive pair 2.2Ω. A shorted ring bus sees the 80V open-circuit output through 46Ω plus the 2.2Ω reflected up by 5.23², about 106Ω in all, so roughly 0.8A RMS flows on the ring side. That reflects to about 4Ω at the bridge — 1.7Ω of output copper referred down plus the 2.2Ω of drive copper — and roughly 3.6A RMS from the 15.3V drive. F1 at 500mA slow-blow opens in seconds at seven times rating; the IRLZ44N at 47A and the LRS-150-24 at 6.5A carry that without noticing. The board survives a shorted ring cable either way. What F2 changes is the cost and the diagnosis: a damaged switchboard cable opens a 250mA fast fuse at three times its rating, in well under a second, on the branch that caused it — rather than the 500mA slow-blow that carries the whole board and says nothing about which of the two branches was at fault.

The OSD record, for comparison: a shorted secondary was about 44Ω to the 20W tap, 2.3A on the secondary, about 7A reflected, and F1 within milliseconds. Rev 48 predicted the Antek would reflect a short as "something close to a short" on the strength of a drive-side resistance assumed at a fraction of an ohm; measured at 2.2Ω it does not, and the fault current is half the OSD's rather than more. The fusing order is unchanged — F2 first on the switchboard branch, F1 for everything else — but the opening times are seconds, not milliseconds, and are recorded as such at Rev 51.

The value is generous rather than calculated, and it is provisional. The J6 branch carries only the operator's station ringing; trunk §7.6 puts a station ring detector at about 4mA RMS through its 20kΩ dropper, so even several stations ringing at once is a small fraction of 250mA. That is an estimate, not a measurement — confirm it against the ring current measurement trunk §7.6 asks for before treating this value as settled. The BOM also flags the 0217.250MXP listing as needing confirmation; the 0217.500MXP is the verified sibling in that series.

One fuse, one leg. The secondary is floating and RING_LO is not bonded to GND anywhere, so opening RING_HI does break the circuit. It does not make the cable dead: with F2 open, RING_LO stays connected to the transformer secondary through J6. A blown F2 is not an isolation method — see §14.

## 7.7 Rail Capacitors — Review Findings

Checked against the Traco datasheets alongside the station and trunk boards. This board came out better than those two, with one addition.

The TSR 1 input capacitor is already fitted. Traco requires it above 32VDC input rather than the 20VDC threshold that applies to the TSR 2, so at 24V this board is outside the mandatory case — but C_12V_IN1 (47µF) and C_12V_IN2 (100nF) are specified regardless, which is the right call. These modules are known to misbehave when fed from a source with meaningful impedance, and this one sits at the end of a fused rail.

The addition is bulk on the 12V output. C_12V_OUT is 100nF, which decouples but stores nothing. The IR2104s draw gate-drive current in pulses at 40kHz, and while C_VCC1 and C_VCC2 handle the fast edge locally and the bootstrap capacitors supply the high-side charge, there is nothing on that rail to hold it up between pulses. Fit a 10µF electrolytic at U_12V's output alongside the existing 100nF.

No 24V audio-band bulk is needed here. C_BULK1 at 100µF exists for a different problem — H-bridge switching current, not audio-band crosstalk — and this board carries no audio on its 24V rail. Station §10.7 and trunk §12.4 do not apply.

# 8. H-Bridge Circuit

## 8.1 Topology

```text
              +24V
               |
        +──────+──────+
        |              |
      [Q1]            [Q2]     ← High side (IRLZ44NPBF)
        |              |
   SW_L +———[T1]——————+ SW_R
        |              |
      [Q3]            [Q4]     ← Low side (IRLZ44NPBF)
        |              |
        +──────+───────+
               |
              GND
      IR2104 #1        IR2104 #2
      drives Q1+Q3     drives Q2+Q4
```

## 8.2 IR2104 Pin Connections

```text
  Pin 1  VCC : +12V from TSR 1-24120; bypass 100nF to COM
  Pin 2  IN  : IC1 ← Gate 1 out (IN1);  IC2 ← Gate 2 out (IN2)
  Pin 3  /SD : ← 74HCT04 Gate 6 out (5V);  R_SD_PD 10kΩ at GPIO14, R_SD_PD2 10kΩ at this net. LOW = shutdown
  Pin 4  COM : GND
  Pin 5  LO  : → R_G → low-side MOSFET gate
  Pin 6  VS  : Switching node (SW_L or SW_R)
  Pin 7  HO  : → R_G → high-side MOSFET gate
  Pin 8  VB  : Top of bootstrap capacitor
```

## 8.3 Bootstrap Circuit

One per IR2104. D_BOOT: UF4007 (not 1N4148), anode to +12V, cathode to VB. C_BOOT: 100nF ceramic, VB to VS.

The VBS margin is real but not generous, and it is worth stating rather than discovering. IR PD60046-S gives VB as a recommended VS+10 to VS+20. C_BOOT charges to VCC less the UF4007 drop, so about 11V nominal; at the low end of the TSR 1-24120’s ±2% that is roughly 10.8V. Against a recommended floor of VS+10 the headroom is a few hundred millivolts, not volts.

Droop during conduction is small. IQBS is 30µA typical and 55µA maximum, so 100nF loses about 14mV over a single 25µs carrier cycle. The case that matters is the sine peak at g_amplitude = 1.00, where three consecutive steps reach 100% duty and the high side conducts for 600µs unbroken: 55µA over 600µs is 0.33V, taking the worst case to about 10.4V. At the 0.90 trim §9.4 expects, no step reaches 100% duty at all and the question does not arise.

Two things keep this from being a constraint. VS+10 is a recommended operating condition, not a threshold — the IR2104 specifies an undervoltage lockout on VCC, 8.9V typical rising, and none on VBS, so falling below it degrades gate drive rather than latching the driver off. And the load is an IRLZ44N, a logic-level part specified at VGS = 5.0V with 0.025Ω against 0.022Ω at 10V, fully enhanced well below anything reachable here. MEASURED at Rev 47, and the conclusion changes. At g_amplitude = 1.00 the bootstrap does not merely lose margin, it collapses: VB−VS falls from 11.8V to about 2.6V for several milliseconds at each sine peak, once per half-cycle. HO−VS simultaneously reads about −9V, which is the same event seen from the other side — VS is dragged upward while VB stays put, so both differential measurements move by the same 9V.

At g_amplitude = 0.90 both disappear. VB−VS holds 11.98V and HO−VS bottoms at −494mV, which is ordinary switching undershoot. Every step then leaves the low side a refill window.

So 1.00 is outside the bootstrap’s working range rather than at the edge of it. The calculation above covers three consecutive steps at 100% duty; at 1.00 there are more, and the refill window closes entirely for long enough that C_BOOT cannot recover. The design needs no change — §9.4 expects 0.90 as the trim value — but 1.00 is not a safe placeholder to leave in the firmware while bringing a board up, which is how this was found. Measured on the breadboard with the high-side drains disconnected; expect the numbers to shift once the bridge is loaded.

## 8.4 Gate Resistors

10Ω in series with each MOSFET gate (R_G1–R_G4). R_GS3 and R_GS4, 10kΩ each, from the Q3 and Q4 gates to GND — added at Rev 46.

The low-side gate-to-source resistors exist because a floating gate does not stay off. Applying 24V to the drains injects charge into the gate through Crss: 150pF against 1700pF Ciss is roughly a 1:11 divider, so a 24V step can deposit about 2V against a V_GS(th) minimum of 1.0V. With no bleed path that charge has nowhere to go and both devices in a leg come partly on and stay there. This was observed on the bench during Rev 45 bring-up, with the drivers unfitted and the gates floating: the board drew the bench supply’s current limit straight across from +24V to ground. The resistors do not fight the instantaneous Miller current — no practical value can — they give the injected charge somewhere to drain.

Two resistors, not four, and the asymmetry is the point. Every DC path from +24V to ground runs through a low-side device: directly through Q3 or Q4, or through the primary as Q1 to SW_L to T1 to SW_R to Q4. Hold both low-side gates down and none of those paths exists. The body diodes offer no alternative, since Q3 and Q4 have anode at ground and cathode at SW and are reverse-biased whenever SW is positive. A partly-on high side then achieves nothing either — SW rises toward the rail, no current flows for want of a return, the primary stays unenergised and no secondary voltage appears.

High-side gate-to-source resistors are deliberately NOT fitted, and this is a decision rather than an omission. A 10kΩ from HO to VS draws about 1.1mA continuously while the high side conducts, all of it out of C_BOOT. Over the 600µs window §8.3 works through that is 6.6V of droop on a 100nF capacitor starting near 11V — against the 0.33V §8.3 currently calculates, and enough to take VBS below anything usable. Raising the value to 100kΩ cuts the load to 110µA but still roughly triples the total against the 55µA IQBS. They would buy nothing the low-side pair does not already buy, and would cost the margin §8.3 exists to document.

10kΩ gives τ = 17µs against Ciss, comparable to the 25µs carrier period, which sounds marginal and is not: when the driver is actually driving it discharges the gate through the 10Ω series resistor in about 100ns. The 17µs figure applies only when nothing is driving, which is exactly the condition the resistors are for.

## 8.5 RC Snubber

R_SNB (100Ω 1W) and C_SNB (10nF 250V film, Kemet R82) in series across SW_L to SW_R. Install it; do not omit it.

What it does. At each turn-off the current in the transformer’s leakage inductance has nowhere to go and rings against the capacitance at the switching node — 400pF of Coss per IRLZ44N plus the winding’s own. The series RC gives that energy a lossy path so the ring decays in a cycle or two. It matters here because the IRLZ44N is a 55V part on a 24V rail, about 2.3× headroom, and ringing overshoot eats it. Avalanche is cumulative rather than dramatic: the part works, and then one day does not.

How the values follow. Choose C_SNB well above the node’s parasitic capacitance so it sets the ring, then take R_SNB = √(L_leak / C_SNB). The Antek's leakage, measured at Rev 51 with the output pair shorted (§9.3), is 160µH, flat from 1kHz to 100kHz. √(160µH / 10nF) = 126Ω; 100Ω is within the tolerance of a √ estimate and stays. The ring is 1 / (2π√(LC)) ≈ 125kHz, three times the 40kHz carrier, which is what you want.

History. Rev 38 noted that 10nF and 100Ω imply 100µH and that the figure was inferred from the parts rather than measured; Rev 48 expected the toroid's leakage to be single-digit microhenries and R_SNB to fall to the tens of ohms. The measurement landed within a factor of 1.6 of the original inference and sixty times above the Rev 48 expectation. The 14.6mH §9.3 once quoted as leakage was the OSD's magnetizing inductance and never bore on this section.

Dissipation is C·V²·f. One leg switches at a time, so the node moves 24V per edge: 10nF × 24² × 40kHz = 230mW. Rev 5 through Rev 37 specified a 1/4W resistor and said to uprate it if it ran warm, which is 92% of rating — not a margin, and not something to discover on the bench. R_SNB is a 100Ω 1W part as of Rev 38: the same resistor the trunk board already buys for R1, so no new line item and nothing further to order. The footprint moves from DIN0207 to DIN0414.

C_SNB is film, not ceramic. This section and §10.8 said 10nF, 100V, ceramic through Rev 37 while the BOM carried the Kemet R82 at 250V under the correct part number. An X7R ceramic loses capacitance under DC bias and handles repetitive pulse current poorly, which is the whole job here. 100V would have been adequate for a 48V peak; the wrong dielectric would not.

Scope the switching node before and after fitting. Leakage is measured (§9.3) and 100Ω is settled on that basis; a ring on the node far from 125kHz means the node capacitance is not what §8.5 assumes, not that the leakage figure is wrong.

## 8.6 IR2104 Input Thresholds

The IR2104 specifies VIH at 3V minimum and VSD,TH+ at 3V minimum, both for VCC of 10V to 20V. Those two numbers are what drive the 5V logic rail in §5 and the SD buffer in §6, and they are worth stating plainly because earlier revisions of this document got them wrong in both directions: Rev 13 did not check IN at all, and Rev 13 and Rev 14 both quoted an SD threshold of 2.1V that does not appear in the datasheet.

The margin at a 3.3V drive is not 0.3V. It is negative. Espressif specifies the ESP32-WROOM VOH as a minimum of 0.8 × VDD, which at a 3.3V rail is 2.64V — the same figure the source-current table uses when it specifies 40mA at VOH ≥ 2.64V. Against the IR2104’s 3.0V the guaranteed margin is −0.36V, so a directly driven IR2104 is outside specification rather than close to its edge. It would very likely work, because a lightly loaded CMOS output sits near its rail and the IR2104 input draws 10µA, but working on the bench while failing specification is the same trap as fitting an HC part in place of an HCT. Earlier revisions of this section said 0.3V and understated their own case; corrected at Rev 40 against the ESP32-WROOM-32E datasheet. At 5V through the gate the margin is about 2V.

The IRS2104PBF substitution proposed in Rev 14 is withdrawn, and was reconsidered and rejected again at Rev 40 for a different reason. Electrically it is the right answer to direct 3.3V drive, and taking it would delete the gate, C_U4, the +5V net and R_SD_PD2 outright. It is only available in surface mount. This is a through-hole board — DIP-8 drivers, DIP-14 gate, TO-220 MOSFETs, axial passives — and an SOIC part on an adapter is the wrong thing to put in a gate drive loop that §13 already asks to be kept as short as the layout allows. The package closes it, not the electrical case, which is worth recording because nobody would rediscover that from the thresholds. With the gate at 5V the IR2104PBF is inside specification with room to spare. Confirm VIH against the datasheet for whatever is actually supplied, as always, but at a 5V drive a revision-to-revision difference in that number no longer decides the design.

## 8.7 Ring Drive Monitor

R_MON1 (4.7k 1/4W) from SW_L to MON_A. R_MON2 (4.7k 1/4W) from SW_R to MON_B. C_MON (100nF 50V X7R) between MON_A and MON_B. J10, a 3-pin 0.1-inch header: pin 1 MON_A, pin 2 GND, pin 3 MON_B. Added at Rev 48.

What it is for. Every node in the bridge carries the 40kHz carrier, and the 20Hz sine exists only as its average — on the primary, which is what this filter shows, and on the secondary only once C_OUT (§9.6) integrates it; Rev 48 through Rev 51 said here that the transformer itself did the integrating, which is wrong and was found on the bench at Rev 52. On the bench that means the primary can be seen aliased — 16k samples across 100ms is a filled band with no waveform in it — or at full rate, where a few carrier cycles fill the screen and the sine is a change in duty from one edge to the other. Neither view answers what the transformer is seeing. This filter does.

How it works. C_MON sees the two resistors in series, 9.4k, so the corner is 1/(2π × 9.4k × 100nF) ≈ 170Hz. At 20Hz the response is within 1% of unity with about 7° of lag; at 40kHz the carrier is 47dB down, leaving roughly 100mV of residual on a 21V sine. Both nodes are filtered rather than one referenced to the other, so the common-mode carrier — each SW node swings 0 to 24V — is filtered too, and the measurement does not depend on an instrument's common-mode rejection at 40kHz.

How to use it. Analog Discovery: 1+ on pin 1, 1− on pin 3; the channel reads the bipolar 20Hz drive directly, and pin 2 is there if a ground reference is wanted. Single-ended scope: tip on pin 1 or pin 3, ground clip on pin 2; the channel shows that leg's contribution — positive half-cycles only on one, negative only on the other, since the idle leg sits at zero — and two channels in A−B recover the bipolar waveform. The 7° lag matters only when comparing against the J9 sync edge.

What it does not do. It is not an output filter and shapes nothing the transformer sees: 9.4k across the primary is 1mA from the rail and 60mW across the pair. It is not the snubber and does not interact with it — the resistors isolate C_MON from C_SNB, and at 20Hz C_SNB is 800kΩ of reactance in any case. Swap C_MON for 4.7nF (corner 1.7kHz) if enough carrier to read duty is wanted; the header does not change.

Why GND is in the middle. The same reason as J9: the probe ground lead wants to be adjacent to whichever outer pin the tip is on, and a shunt fitted across J10 in error grounds one filtered node through 4.7k, which nothing minds.

Why X7R and not film. See the Rev 48 change entry: the filter's accuracy at 20Hz does not depend on the capacitance to any degree that bias drift can reach, the reasons film is required in C_SNB and station C4 do not apply, and the film alternatives were on 20-week lead times when this was written.

# 9. Transformer

T1: Antek AS-0522 toroidal mains transformer, 50VA, used in reverse. The two 22V secondaries in series (44V nominal) are the primary as this board sees it, driven from J7; the two 115V primaries in series (230V nominal) are the ring output into J8. The static-shield lead goes to GND at the board or is left unconnected — either; it was left unconnected for the first bench work. Replaces the OSD Black 70V audio distribution transformer at Rev 48; §9.5 records why.

Leads and splices, recorded at Rev 51 from Antek's sheet and the phasing measurement. Nine leads: each 115V winding is RED/BLACK, each 22V winding is GREEN/BLUE, PURPLE is the shield. The two windings of each pair are numbered 1 and 2 by the unit that was phased on the bench; the numbering is per unit and the second unit on hand must be phased before it is spliced. Drive pair: splice BLUE1 to GREEN2; GREEN1 and BLUE2 to J7, order irrelevant. Output pair: splice RED1 to BLACK2; BLACK1 and RED2 to J8, order irrelevant. Both splices follow Antek's published series convention. Heat-shrink both; the output splice sits at 113V peak. Phasing was verified by driving one 22V winding at 2V peak and reading the sum across the outer ends of each spliced pair — 20.8V peak on the output pair against 10.45V for one winding, 4V on the drive pair against 2V — so a wrong splice reads near zero, not double. A wrong drive-pair splice on the bridge would be a 2.2Ω load with almost no inductance; a wrong output-pair splice would merely give no output.

T1 is mounted off the board and wired to it, settled at Rev 32. It is a toroid with flying leads and no board-mount pattern, so there is no footprint to draw and none is wanted. The drive-winding pair lands on J7 and the output-winding pair on J8. Nothing else changes electrically — SW_L and SW_R now reach the winding through J7 rather than directly, and RING_HI and RING_LO now originate at J8 rather than at the transformer.

The two terminals are deliberately different parts. J7 is the black 3.50mm OSTTE020104, the same block as the 24V input, which is adequate because neither primary leg leaves the 0 to 24V range. J8 is the blue 5.00mm OSTTC020162, the same block as J2 and J6, because the output is up to 80V RMS and 113V peak — 141V with the OSD — and the 125V block is below that either way. That keeps the board’s colour convention intact: black is a low-voltage terminal, blue is a terminal in the ring zone.

What the colours cannot do is prevent a swap. These are wire-clamp blocks, not mating connectors, and any wire fits any block — the 3.50mm and 5.00mm pitches distinguish the parts on the board but key nothing. The protection is separation and silkscreen: J7 lives with the MOSFETs and J8 lives with J2, F2 and J6 at the far edge, with both pairs labelled T1-PRI and T1-SEC. The swap that matters is secondary leads onto J7, which puts the output winding's 113V peak on SW_L and SW_R against a 55V IRLZ44N rating and takes out four MOSFETs and both drivers. The reverse swap is harmless by comparison. Label accordingly, and dress the two pairs so they do not run together.

## 9.1 Differential H-Bridge Voltage

```text
  Differential across primary = 48Vpp  (each leg swings full 24V rail)
  V_primary_rms = 48 / (2√2) ≈ 17.0 Vrms  at g_amplitude = 1.0
```

## 9.2 Measured Turns Ratio and Output Voltage

Antek AS-0522, measured 2026-09-15, Analog Discovery 3 wavegen driving one 22V winding, scope on the others:

```text
  V_in (one 22V winding, peak) = 2.00V    V_out (one 115V winding, peak) = 10.45V
  N = 5.23 : 1 per winding, and the same for the two series pairs (20.8V across the output pair)
  V_output (no load, g_amplitude = 0.90, 15.3V RMS drive) = 80 Vrms, 113V peak, calculated
  V_output (loaded, ~30mA) ≈ 79 Vrms — 46Ω of output copper plus 60Ω of reflected drive copper drops about 1.4V
```

5.23 is 115/22 to three figures. Rev 48 assumed the 44V nameplate was a full-load figure with about 50V of open-circuit turns behind it and predicted 72V; the nameplate ratio is the turns ratio, and the output sits at the top of the 70–80V band. Confirm V_output at J8 at first power-up per §9.4; the figure above is a calculation from the measured ratio, not a measurement of the bridge.

The OSD record, for the history: N = 5.89 at 1kHz (46mV in, 271mV out), 100V RMS no-load at g_amplitude 1.0, 95–100V at 25mA.

## 9.3 Measured Winding Resistance and Inductance

Antek AS-0522, measured 2026-09-15 and 16. Resistance with the DMM, leads nulled at 0.1Ω; inductance on the Analog Discovery 3 Impedance Analyzer Adapter, Meter view, 1V, 500ms averaging, series model.

```text
  DC resistance: 115V windings 23Ω each, 46Ω in series; 22V windings 1.1Ω each, 2.2Ω in series
  Magnetizing, 44V series pair, output open, 20Hz:  Ls = 3.10H, |Z| = 410Ω at 71.9°, Rs = 127Ω, Xs = 389Ω, Q = 3.1   [OPEN-CIRCUIT]
  Same, 1kHz:  |Z| ≈ 3600Ω, about 0.57H
  Leakage, 44V series pair, 230V series pair shorted:  Ls = 169µH at 1kHz, 165µH at 10kHz, 161µH at 100kHz; Rs = 3.8Ω, 4.0Ω, 14Ω   [SHORT-CIRCUIT]
```

What the magnetizing figure gives. 3.10H at 20Hz is 390Ω of reactance; at 15.3V RMS the magnetizing current is 37mA RMS, of which 12mA is in phase with the drive — the Rs term, core loss, about 0.2W at this level. This is a small-signal measurement at about one seventeenth of operating flux; silicon steel's permeability rises with flux from here, so the operating-point current is expected at or below 37mA. The bench supply's DC reading at first power-up is the operating-point check. F1 at 500mA is confirmed with an order of magnitude in hand (§7.2). The drop across the 2.2Ω of drive copper at 37mA is 80mV — negligible. The 1kHz inductance is a fifth of the 20Hz figure because eddy currents in the laminations shield the core as frequency rises; the 20Hz number is the one that matters, and the OSD's §9.2 measurement at 1kHz would have flattered it for the same reason.

What the leakage figure gives. 160µH, flat over two decades, is leakage — it is what remains with the far winding shorted, and it does not move with frequency the way magnetizing does. Rs rising from 4Ω to 14Ω over the same range is skin and proximity effect in the copper and does not enter the snubber. The 4.0Ω at 10kHz is a check on the short and the ratio: 2.2Ω of drive copper plus 46Ω of output copper referred through 5.23² is 3.9Ω. The snubber follows in §8.5: √(160µH / 10nF) = 126Ω, R_SNB stays at 100Ω, ring at about 125kHz.

Measurement notes. The Impedance tool must be in "Adapter" mode when the adapter is used; the manual-wiring modes leave the adapter's reference relays undriven and report nonsense with a "resistor too low" flag. A 10Hz–1kHz amplitude sweep with no averaging read about 180Ω at 20Hz against the meter's 410Ω, twice; the two agree at 1kHz. The averaged meter figure is recorded. Reference resistor 1kΩ for magnetizing, 10Ω for leakage at 10kHz, 100Ω at 100kHz.

The OSD record, for the history: 508mH / 22Ω at the 20W tap, 14.6mH / 0.63Ω referred to the 4Ω primary, open circuit — 1.83Ω of reactance at 20Hz and 8.3A RMS of magnetizing current, which no revision computed before Rev 48 and which is the number that explains §9.5. That figure was headed Measured Leakage Inductance from Rev 9 to Rev 37 and quoted by §8.5 as leakage; it was magnetizing, and the OSD's leakage was never measured.

## 9.4 Output Voltage Trimming

— Power up with no telephone connected. Measure the output winding RMS at J8 or at J10 through the monitor (§8.7, times the measured ratio).

— g_amplitude stays at 0.90. Record V_measured. The target is 70–80V RMS and no trim is expected: the measured ratio is the nameplate 5.23 (§9.2), so the expected figure is 80V RMS, 113V peak. If V_measured falls outside the band, the wiring is wrong — check the splices and the J7/J8 leads against §9 before touching the duty. 113V peak is above the Analog Discovery's ±25V input; use a 10× probe or the bench scope at J8, or read the drive at J10 and multiply by 5.23.

The trim value must stay clear of 1.00. §8.3 records the measurement: at 1.00 enough consecutive steps reach 100% duty that the low side stops turning on, C_BOOT gets no refill window and the bootstrap collapses to about 2.6V at each sine peak. At 0.90 it holds 11.98V. There is now a second reason: 0.90 puts the toroid at 87% of rated flux at 20Hz, and 1.00 would put it at 97%. A measurement that calls for a trim above 0.95 points at the winding, not at the duty.

— V_measured, 2026-09-16, C_OUT fitted, no load: 78.9V RMS on the DMM; about 114V peak, 81V RMS read from the Analog Discovery trace through an 11:1 divider. The DMM figure is the record — the scope figure was read from a trace at 5V/div — and the two bracket the 80V predicted from the ratio within 2%. No trim; g_amplitude stays at 0.90 and station R1a/R1b stay at their present value.

— V_measured, 2026-09-25, C_OUT fitted, no load, 74HCT04 fitted, firmware at control.md Rev 11 (commit b7cac13): Analog Discovery 3 at 5V/div, 20ms/div (Mark's capture `ring10.png`, not in the repository). Channel 1 on J10 after the §8.7 filter: ±21.5V peak, 15.2V RMS, against 15.3V at g_amplitude 0.90. Channel 2 on J8 through the 11:1 divider — 100k in series and 10k to ground on each leg, read differentially across the two 10k: ±10.2V peak, so 112V peak and 79.3V RMS at the winding. Ratio 112 / 21.5 = 5.22 against the 5.23 of §9.2; period 50.0ms, 20.0Hz. Both traces clean sines with no flat-topping. The output leads the J10 trace by about 1.5ms, 11°, most of which is the §8.7 filter's 7° lag on the J10 side rather than anything in the transformer. Read from the trace, so the 2026-09-16 DMM figure stays the record; the two agree within 0.5%.

— Only then connect to telephone line.

Open item as of Rev 28, unchanged in substance. This is a no-load trim and the ring load is expected to be small — the trunk board's relays at about 25mA plus the switchboard's own ringing, estimated in trunk §7.6 at roughly 4mA per station detector. With the measured windings — 46Ω of output copper plus 2.2Ω of drive copper referred up by 5.23², about 106Ω in all — 30mA of ring load drops about 3V, under 4%, so the no-load figure is the loaded one to within the accuracy that matters. Settle the load current itself with the measurement trunk §7.6 asks for.

## 9.5 Core Saturation at 20Hz — Bench Finding of 2026-09-04

First power-up with T1 connected, snubber fitted, secondary open, 24V bench supply limited to 1A, both drivers and both legs already confirmed correct with the drains at 24V and no transformer (§8.3). Across the primary at 10ms/div: a 21V sine peak, the expected 0.9 × 24, holding for 8–12ms of each 25ms half-cycle and then falling abruptly to zero with an exponential tail before the next reversal. On the rail at the bridge: 22V falling to about 1V in step with each collapse and refilling slowly over the rest of the half-cycle — a supply in constant-current mode, the rail being replenished while the reversing magnetizing current flows back into C_BULK1 and folding when the current passes through zero and demand exceeds the limit.

The supply limit was then held at 1A and the rail stepped:

```text
  3V   70mA
  5V   100mA
  7V   250mA
  9V   450mA
  11V  limit, alternating CV and CC
```

Current per volt is about 20mA/V to 5V, 36mA/V at 7V, 50mA/V at 9V. A linear magnetizing inductance holds that ratio constant; this one bends upward from between 5V and 7V on the rail, which is about 4V RMS across the 4Ω winding at 20Hz. That is the core's volt-second limit. The design applies 15.3V RMS — three and a half times it. The supply reading is DC average current rather than primary current, and the bridge returns energy to C_BULK1 every half-cycle that the supply cannot sink, so the numbers are indicative rather than a magnetizing curve; the shape is not in doubt.

This is not a supply, fuse or bridge problem and a larger PSU would not have fixed it. The OSD transformer, driven from its 4Ω winding, cannot be run at 24V at 20Hz. Its “20Hz–20kHz ±1dB at 20W” is the 70V side into its rated load, where the same 508mH is 64Ω against a 245Ω tap impedance. From the 4Ω side at nearly twice the winding's rated voltage it is a different device, and the label does not describe it.

Two directions were considered. Keeping the OSD at the 4V RMS its core allows and recovering the ratio from a lower-power tap — 2.5W is about 16:1 for 65–70V, and secondary resistance rises with turns squared — or a transformer whose core is sized for this flux. A 50/60Hz mains transformer takes one third of its rated winding voltage at 20Hz, so a winding rated 44V takes 17.6V RMS, which is the drive this bridge already produces. The second direction keeps the rail, the duty tables and all of §8 unchanged; only T1 and this section move. Antek AS-0522, two 22V windings in series driven and two 115V windings in series as the output, is the part.

A third direction was not considered at the time and is recorded at Rev 58 in §9.7: take the transformer out of the 20Hz path altogether by running it at tens of kilohertz into a rectifier, and synthesise the 20Hz from the resulting DC bus. Both directions above accept that the core must carry 20Hz flux and differ only in how big a core that needs; the third asks whether it must. It was not taken, and §9.7 says why, but it is the question a saturated core should have prompted.

What it changes elsewhere. Output 70–80V RMS rather than 90 (see the Rev 48 change entry for why this is the target, not a shortfall). Leakage on a toroid is low, so §8.5's snubber is sized for a leakage forty times what to expect and R_SNB comes down once leakage is measured. The start phase of the sine matters for the first time (§12.6). F1 stands (§7.2).

The four measurements this section asked for at Rev 48 were made on 2026-09-15 and 16 and are recorded in §9.2 and §9.3: resistance 23Ω and 1.1Ω per winding; ratio 5.23, the nameplate; magnetizing 3.10H at 20Hz, 37mA RMS at the drive voltage; leakage 160µH. Two Rev 48 expectations did not survive them — the open-circuit output is 80V rather than 72V, and leakage is 160µH rather than single-digit microhenries — and neither changes a part. The Rev 51 change entries carry the corrections.

With the bridge, 2026-09-16: the primary through the §8.7 monitor at 10ms/div showed a clean 20Hz sine at ±22V, the rail steady, the bench supply at 30mA against the 1A limit it sat on with the OSD. The collapse is gone. The same capture showed the output problem §9.6 records. The §12.6 start-phase capture remains to be made.

First end-to-end ring, same day, C_OUT fitted: a Western Electric 304 desk set across the output rang. Supply current 30mA idle, 60mA with the bell ringing — 0.72W of real power, about 9mA in phase at 79V, total current estimated 10–15mA allowing for the ringer's power factor; not measured directly. A bell is a heavier load than anything the generator sees in service, where the ring bus feeds the switchboard's trunk ring relays on the J2 branch and station ring detectors at a few milliamps each on the J6 branch. F2 at 250mA is comfortably sized on either figure.

## 9.6 Output Filter — C_OUT

C_OUT: 1µF 250V film (Kemet R82, the BOM's ring-detector blocking part) across J8, RING_HI to RING_LO, on the board, ahead of F2, J2 and J6. Added at Rev 52 after the first power-up with the Antek.

What it is for. The bridge applies a 40kHz PWM square wave, 0 to 24V on each leg, to the primary. A transformer transforms voltage, so the secondary carries the same square wave times 5.23: ±125V pulses at 40kHz whose duty follows the 20Hz sine. The 20Hz sine is only the average of that pulse train and does not exist on the output until something integrates it. The magnetizing inductance cannot — it is across the winding, not in series with the load — and the document's earlier belief that the transformer's passband would strip the carrier was inherited from the OSD and was never true of a mains toroid. Seen on the bench 2026-09-16 with nothing on the output but an 11:1 divider: a filled band of carrier with a 20Hz envelope, clipping the Analog Discovery's ±25V input, so above ±250V at the winding. The overshoot beyond ±125V is the leakage — §9.3's 160µH, 4.4mH referred to the secondary — ringing against the winding's stray capacitance on every edge with nothing to damp it.

How it works. The 4.4mH of leakage is already in series between the bridge and the J8 node, so a capacitor at J8 completes a second-order LC low-pass with it. With 1µF: corner 1/(2π√(4.4mH × 1µF)) ≈ 2.4kHz; attenuation at 40kHz about (40/2.4)² ≈ 280×, so 125V of pulse becomes under half a volt of ripple on an 80V sine; reactance at 20Hz 8kΩ, so 10mA of reactive current on the secondary and about 50mA reflected to the bridge. Damping: the loop resistance is the 46Ω of output copper plus the 2.2Ω of drive copper referred up by 5.23², about 106Ω, giving Q = ωL/R ≈ 0.6 at the corner — no resonant peak and no damping resistor. That number is only available because §9.3 measured Rs. The 5kHz stepping residue §12.2 mentions is above the corner and attenuated with the carrier. Measured: the output became 114V peak, 81V RMS, with a trace of carrier visible as fuzz on the sine.

Why the secondary and not the primary. A capacitor across SW_L–SW_R would sit directly on the switch nodes with nothing between it and the MOSFETs, so the bridge would be hard-switching into it — the same reason C_SNB is 10nF behind 100Ω and not a bulk part. On the secondary the leakage inductance is between the bridge and the capacitor, which is where an LC filter's inductor has to be. The primary-side equivalent would be 27µF at the switch nodes, and it would be wrong there.

What it costs. The leakage now carries the carrier's ripple current the way a buck converter's inductor does, because its far end is held by C_OUT. Worst case at 50% duty, ΔI = V·D(1−D)/(f·L) = 24 × 0.25 / (40kHz × 160µH) ≈ 0.9A peak-to-peak triangular at the primary, about 0.3A RMS — 0.2W in the 2.2Ω of drive copper, nothing to the IRLZ44N or the bridge, and it circulates through C_BULK1 rather than the supply, whose 30mA reading confirms the average is unchanged. On the secondary that is about 0.15A RMS at 40kHz in C_OUT; a polyester film part at that current dissipates a few milliwatts, but check that it runs cool the first time the generator runs for an hour, since the R82 is specified as a DC-blocking part and this is not that job. The ripple voltage across C_OUT at that current is about 0.7V, which is the fuzz on the trace.

What it does not change. §8.5's snubber: the turn-off ring at the switch node is leakage against the node's capacitance, and C_OUT is at the other end of the leakage; scope the node with C_OUT fitted as §8.5 asks. §7.6's fault arithmetic: C_OUT is upstream of F2, its 10mA never crosses the fuse, and a shorted output shorts the capacitor along with the winding. §9.4: the no-load output is 81V rather than 80V. Stored energy: ½ × 1µF × 114V² ≈ 6mJ at peak, and the 46Ω winding is permanently across the capacitor, so it discharges in tens of microseconds when the drive stops — there is no charge to bleed after power-off, and no bleeder is fitted.

Alternatives considered. 2.2µF: corner 1.6kHz, 600× at 40kHz, 22mA reactive on the secondary, Q ≈ 0.4. More than needed and twice the reactive current. A separate LC on the secondary with its own inductor: the leakage already is the inductor, and a discrete 4.4mH at 113V peak would be a large part solving a problem the transformer solves for free. An LC on the primary: see above. Nothing: every part in the ring zone is rated 250V or 300V against a design peak of 113V, and the unfiltered output exceeded 250V; the trunk and station boards would have seen a 40kHz square wave into their ring detectors, C3s and TVS arrays. Not an option.

## 9.7 Alternative Not Taken — High-Frequency Link

Recorded at Rev 58. Raised 2026-09-18, after the Antek design was built and ringing, as a question rather than a proposal. It is written down so that the reasoning survives and so that anyone who later needs a lighter, smaller or higher-voltage ring generator starts here rather than at the OSD.

What it is. Two stages instead of one.

```text
  Stage 1 — DC-to-DC, isolated:
    24V —► H-bridge at ~50kHz, fixed 50% duty —► small ferrite transformer, ~1:5
        —► bridge rectifier —► bus capacitor —► ~115V DC, floating

  Stage 2 — DC-to-20Hz, on the floating bus:
    115V DC —► H-bridge, sine PWM at 40kHz with a 20Hz reference (the present firmware)
        —► discrete LC filter —► 80V RMS 20Hz to the ring bus
```

Stage 2 is the bridge this board already has, moved from the 24V rail to a 115V bus and run into an inductor instead of a transformer. Stage 1 is what replaces the toroid: the transformer still provides the isolation and the voltage ratio, but it does so at 50kHz, where the core's job is easy.

Why the core shrinks. Flux swing per half-cycle is the volt-second integral divided by turns and core area, so for a given winding voltage and turns the core area needed scales as 1/f. Moving the transformer from 20Hz to 50kHz cuts the required volt-second capacity by a factor of 2500. That is the difference between a 50VA silicon-steel toroid and a ferrite core of a few cubic centimetres — the class of part used in an isolated gate-drive supply or a small flyback. The saturation that retired the OSD at Rev 48, and the 87%-of-rated-flux operating point the Antek runs at, both disappear as concerns: at 50kHz a ferrite the size of a thumbnail carries this power at a small fraction of its rated flux.

Why stage 2 has to be PWM, not a 20Hz square wave. A square wave on the 115V bus, chopped at 20Hz and filtered to a sine, wants an LC with a corner near 30Hz. At 115V that is henries of inductance and tens of microfarads of film capacitance at 250V — a filter larger and heavier than the toroid it is meant to replace. Sine PWM at 40kHz keeps the filter's job to removing the carrier, and that is a corner of a few kilohertz, as C_OUT's is now. The stage-2 filter is then a discrete inductor of a few millihenries and a capacitor of about a microfarad — small at tens of milliamps, but a real inductor rather than the leakage the Antek supplies for free, because in this topology the transformer sits on the far side of the rectifier and its leakage does nothing for the 20Hz stage. The firmware, the duty tables, the 250-step sine and the bootstrap refill argument of §8.3 all carry over to stage 2 unchanged; stage 1 needs only a fixed 50% complementary pair, which is a third LEDC channel or a self-oscillating driver.

What it buys.

— Weight and volume. The 50VA toroid becomes a ferrite the size of a thumbnail; the whole ring generator could sit on one board with nothing off-board.

— Headroom on output voltage. The Antek's output is fixed by its turns ratio at 80V RMS with g_amplitude at 0.90, and §9.4 records that the trim cannot go above about 0.95 for two independent reasons. A DC bus is set by the stage-1 turns ratio, which is chosen freely, so 90V RMS nominal or the full 130V of the telco range is a winding choice rather than a limit. Nothing downstream wants it — Rev 48 argues that lower is better everywhere — but the present design cannot offer it and this one can.

— Regulation. A DC bus is stiff; output does not sag with load. The Antek's 4% at 30mA is already negligible, so this is a difference on paper.

— Independence from a catalogue part. The Antek is a $20 stock item today. If it or its Hammond equivalents stop being stocked, the 20Hz design has to find another 50VA transformer with a 44V winding; the high-frequency design winds its own or uses any of hundreds of small ferrite parts.

What it costs.

— A 115V DC bus on the board. Every part in stage 2 — four MOSFETs, two half-bridge drivers, the bus capacitor, the filter — is in the 200V class rather than the 55V class. The IRLZ44N is out; the IR2104 is a 600V part and would serve, with its bootstrap now flying at 115V rather than 24V. The creepage and separation rules §13 applies to the J8/J2/J6 zone would extend to roughly half the board.

— A current limit that has to be designed. Today a shorted ring bus is limited by 106Ω of winding copper to 0.8A on the ring side and 3.6A at the bridge, and §7.6 needed no part to make that true. A DC bus behind a bridge limits nothing: a short is the bus capacitor discharging through the MOSFETs and the filter inductor, and the stage-2 bridge needs a sense resistor and a comparator into SD, or a driver with its own current sense, before it is safe to connect to a cable that gets stood on.

— Stored energy. C_OUT holds 6mJ and discharges through the winding in microseconds; §14 says so. A bus capacitor sized to hold 115V across a 20Hz half-cycle at the ring load — tens of microfarads — holds a few hundred millijoules and discharges through nothing unless a bleeder is fitted. §14 would need a bleeder, a discharge time, and a warning that power-off does not make the board safe to touch.

— Two converter stages, and the parts of both. Four more MOSFETs, two more drivers, a bridge rectifier that is fast at 50kHz, a bus capacitor, an output inductor, a snubber for stage 1's own leakage, and a ferrite transformer that is either custom-wound or a catalogue part chosen for a job it was not specified for. Against the present design's one transformer, one capacitor and the bridge it already had.

— A second switching node at 50kHz beside the I²C bus and the Olimex, on a board §13 already works to keep quiet.

— Efficiency, not a concern at 3W and mentioned only for completeness: two stages lose more than one.

Why the present design stays. It is built, measured and has rung a bell (§9.5). The toroid is off-board and the rack does not care what it weighs. The output voltage is inside the band the whole system was designed to and Rev 48 gave reasons to want it no higher. The fault arithmetic of §7.6, the stored-energy line of §14 and the LC filter of §9.6 all come free from the winding copper and leakage of a part that costs $20, and the alternative would have to design each of them. What the alternative buys is weight, volume and voltage headroom, none of which this installation needs.

When the balance would tip. A second unit for a portable exhibit, where the toroid's weight and the off-board wiring matter. A future requirement for more than about 85V RMS, which the Antek cannot reach at any safe trim. The Antek and its equivalents becoming unobtainable. Any of those reopens this section; none is in prospect.

Commercial ring generator modules — the 12V or 24V input, 90V RMS 20Hz output bricks sold for PBX and test use — are built this way, and a bought module is the shortest route to this topology if it is ever wanted. It would replace stage 1, stage 2 and T1 but not the Olimex, the I²C master, the ring-bus terminals or F2, and ring cadence would still be switched on the trunk board. No specific module has been evaluated and none is recommended here.

The modulator, for completeness — added at Rev 59. The classical way to make sine PWM is an analog comparator with the 20Hz sine on one input and a high-frequency sawtooth on the other; the output is high while the sine exceeds the ramp, and the duty follows the sine directly. That is what the LEDC peripheral does in digits: the timer counting 0 to 1023 and resetting at 40kHz is the sawtooth, the duty register is the sine sample, and the compare is in hardware. The principle is the same and so is the spectrum — a sawtooth carrier in either form puts the leading edge at a fixed phase and moves only the trailing edge, which leaves a sideband at the carrier; a triangle carrier, centring the pulse, would suppress it, and neither matters behind a filter with 280× at 40kHz. What differs is elsewhere. The analog reference is continuous where the table is 250 steps, so the 5kHz stepping residue §9.6 mentions would not exist at the source. The amplitude trim becomes a potentiometer on the reference rather than g_amplitude in firmware, which is convenient on the bench and worse in the design: §8.3's bootstrap collapse at 1.00 and §9.4's ceiling at 0.95 are exactly the limits that belong in a constant rather than within reach of a screwdriver. And a free-running analog modulator keeps producing a sine if the controller hangs, where LEDC holds the last duty written — a DC level on the primary until SD drops. This board answers that case with SD, R_SD_PD2 and the pull-downs rather than in the modulator, which is a sound answer and a different one. The LEDC modulator is measured and working and stays; this paragraph exists so the analog form is recognised as the same thing rather than reinvented as an improvement.

Sizing the stage-2 filter — added at Rev 60. The corner is the one §9.6 chose for the same reasons, 2–3kHz: above it the 5kHz stepping residue and the 40kHz carrier are both in the stopband, below it the 20Hz sine is untouched. With C = 1µF, the R82 already on the board as C_OUT, L = 1 / ((2π × 2.4kHz)² × 1µF) ≈ 4.4mH — the Antek's leakage referred to the secondary, by construction, since §9.6 is this filter with the transformer supplying the inductor. A 4.7mH catalogue part serves, and its ratings are modest: the 20Hz current is the load plus C_OUT's reactive current, under 50mA; the 40kHz ripple is ΔI = V·D(1−D) / (f·L) = 115 × 0.25 / (40kHz × 4.7mH) ≈ 0.15A peak-to-peak, so a saturation rating of 0.3–0.5A is enough. That is a 12–15mm radial drum or a small toroid — the size of a medium electrolytic, and much smaller than the stage-1 transformer. It must be ferrite, since it carries 40kHz, and shielded or toroidal, since an open drum core switching at 115V radiates. It is better fitted as 2 × 2.2mH, one per leg: the bridge output is differential, and one inductor in RING_HI alone leaves RING_LO as a hard switching node.

What is not obvious, and would have been found on the bench: damping. §9.6's filter has Q ≈ 0.6 because 106Ω of winding copper sits in series with the leakage. A discrete inductor has a few ohms of DCR, so the same L and C give Q = ωL/R ≈ 66/5 ≈ 13 at the corner, and the ring load does not help — parallel damping needs R_load below √(L/C) ≈ 66Ω, and 3kΩ is fifty times above it. Nothing in a 20Hz sine excites 2.4kHz in steady state; a step does, and start-up would provide one. The fix is 47–68Ω, 1W, in series with the inductor — the toroid's copper loss put back deliberately. It costs about 2V of the 80V and roughly 0.15W, brings Q to 1–1.5, and limits a shorted ring bus to about 2A from the 115V bus rather than the bus capacitor discharging through the MOSFETs, which recovers most of the current-limit design the cost list above asks for. The alternative, an RC damping leg across C_OUT at about 68Ω and 4.7µF 250V film, works and makes that capacitor the largest part in the filter.

A firmware consequence follows from the damping. §12.6 starts the sine at SINE_STEPS/4, the voltage peak, so that the toroid's flux integral starts where steady-state flux is zero. With no core in the 20Hz path that reason is gone and the peak start becomes the wrong one: a 113V step into an LC at Q ≈ 1.5 overshoots. Stage 2 wants the zero-crossing start the firmware used before Rev 48. The requirement inverts with the topology; it does not go away.

Reference. The topology was prompted by the consumer-inverter explanation in "How Inverters Turn Battery Power into AC" (YouTube, https://www.youtube.com/watch?v=KYI7zjYRj-M), watched 2026-09-17. A 12V car inverter is this circuit: a bridge at tens of kilohertz into a small ferrite, rectified to about 170V, then an H-bridge with sine PWM and an LC filter to make 60Hz. The ring generator is the same thing with 24V in, a 115V bus, 20Hz out and three watts instead of a thousand; what it does not need is the feedback loop regulating the bus against battery sag, since the LRS-150-24 is already regulated and the ring load barely moves. The video's "modified sine wave" inverters, which step the bus through +V, 0, −V with no PWM and no filter, are the square-wave case argued against above — they get away with it because their loads tolerate it, and a ringer or the switchboard's ring relay would too, but the station ring detectors were designed against a sine (station §3.4) and that shortcut would mean revisiting them.

# 10. Component List

## 10.1 Power Input

| **Designator** | **Part** | **Notes** |
| --- | --- | --- |
| PS1 | Mean Well LRS-150-24 | System 24V supply, shared with all boards |
| D1 | 1N5822 | Reverse-polarity protection, SHUNT clamp across +24V and GND — cathode to +24V, anode to GND, NOT in series. 3A / 40V, DO-201AD axial — through-hole; the SS34 of earlier revisions is surface-mount only. See §7.2. |
| F1 | 500mA slow-blow, 5x20mm — Littelfuse 0218.500MXP | Between J1 and the D1 clamp — the first component on the +24V input, upstream of D1, not after it. 250V, 5x20mm glass cartridge; same part as trunk F1. See §7.2 and §13. |
| FH1 | 5x20mm PC-mount fuse block | Littelfuse 64900001039, 649 series PC-mount block, 5x20mm, 6.3A / 250VAC, solder lug. Holds F1. |
| C_BULK1 | 100µF / 35V electrolytic | +24V bulk decoupling, at MOSFET drains |
| C_BULK2 | 100nF ceramic | +24V HF decoupling |

## 10.2 +12V Regulator

| **Designator** | **Part** | **Notes** |
| --- | --- | --- |
| U_12V | Traco TSR 1-24120 | 24V→12V, 1A, 36V max input, SIP-3 |
| C_12V_IN1 | 47µF electrolytic | TSR 1-24120 input bulk |
| C_12V_IN2 | 100nF ceramic | TSR 1-24120 input HF bypass |
| C_12V_OUT | 100nF ceramic | TSR 1-24120 output bypass — for the regulator's own switching ripple, not for the drivers, which have C_VCC1/C_VCC2. Not functionally required; see §7.3 |
| C_12V_BULK | 10µF 50V electrolytic | Reservoir on the +12V rail between IR2104 gate-drive pulses. At U_12V’s output alongside C_12V_OUT — the 100nF decouples but stores nothing. Added at Rev 23 and listed here from Rev 32; see §7.7 |

## 10.3 Controller and I²C

| **Designator** | **Part** | **Notes** |
| --- | --- | --- |
| U_ESP32 | Olimex ESP32-POE-ISO | ESP32-WROOM, LAN8710A, 802.3af PoE, 3kV isolated |
| R_SDA | 2.2kΩ 1/4W | SDA pull-up to +3.3V — DO NOT FIT on other boards |
| R_SCL | 2.2kΩ 1/4W | SCL pull-up to +3.3V — DO NOT FIT on other boards |
| TVS2 | Littelfuse SP721APP, 3pF SCR/diode rail-clamp array | ESD and mis-plug protection on SDA and SCL. 8-PDIP through-hole, 6 inputs, 3pF per line. Rail clamp, not a fixed-breakdown TVS: V+ (pin 8) to +3.3V, V- (pin 4) to GND, SDA and SCL to two of the six inputs, four spare. Sacrificial after a mis-plug — keep spares and consider a socket, since it is a DIP anyway. Same part as the station and trunk boards — see §4.6. |
| C_TVS2 | 100nF ceramic 50V | Bypass across TVS2, pin 8 (V+) to pin 4 (V−), at the device. The SP721 clamps by conducting the transient from IN into V+, and that current has to come from somewhere local or V+ lifts while the clamp is working. §4.6 puts TVS2 at J3, away from the expanders, so there is no other +3.3V decoupling anywhere near it — on this board there is none on the rail at all, since +3V3 arrives from the Olimex header. Added at Rev 34; see §4.6 |
| J3 | Amphenol ICC 87180-066LF | 6P6C modular jack, right angle, through-hole. I²C bus out. Würth 615006138421 or Assmann A-2004-1-4-N-R equivalent. |

## 10.4 Level Translation and SD Buffer

| **Designator** | **Part** | **Notes** |
| --- | --- | --- |
| U4 | 74HCT04 | Hex inverter, TTL inputs, powered from Olimex +5V (EXT1 pin 1). SN74HCT04N, DIP-14. Gates 1–2 buffer PWM A, gates 3–4 PWM B, gates 5–6 the SD line — two inversions each, so every path is non-inverting. Replaces the 74HCT02 at Rev 44; same package and footprint, different symbol and pin numbers. HCT, not HC — see §5. |
| C_U4 | 100nF ceramic | 74HCT04 VCC bypass, pin 14 to pin 7 |

## 10.5 SD Control & Gate Drive

| **Designator** | **Part** | **Notes** |
| --- | --- | --- |
| R_SD_PD | 10kΩ 1/4W | Pull-down at GPIO14, ahead of the SD buffer — holds SD low, shutdown in force, from power-on |
| R_SD_PD2 | 10kΩ 1/4W | Pull-down on the SD net itself, at the IR2104 end. Holds SD low — shutdown — when the 74HCT04 is unpowered, which R_SD_PD cannot do because it sits on the GPIO14 side of the buffer. The case is PoE absent with the 24V bus live: +12V up, both drivers alive, gate dead. Added at Rev 37; see §5 |
| R_PWMA_PD | 10kΩ 1/4W | Pull-down, GPIO32 to GND — holds PWM output A low through boot so IN1 is low before firmware runs. Was a pull-up to +3.3V until Rev 44 inverted the drive polarity. New at Rev 30; see §5.3 |
| R_PWMB_PD | 10kΩ 1/4W | Pull-down, GPIO33 to GND — same for PWM output B and IN2. Was a pull-up until Rev 44. New at Rev 30; see §5.3 |
| R_G1 | 10Ω 1/4W | Q1 gate resistor |
| R_G2 | 10Ω 1/4W | Q2 gate resistor |
| R_G3 | 10Ω 1/4W | Q3 gate resistor |
| R_G4 | 10Ω 1/4W | Q4 gate resistor |
| R_GS3 | 10kΩ 1/4W | Gate-to-source, Q3 gate to GND. Holds the low side off when nothing is driving the gate — an unfitted, unpowered or socketed-out IR2104. Added at Rev 46 after a floating gate shorted the rail on the bench; see §8.4 |
| R_GS4 | 10kΩ 1/4W | Gate-to-source, Q4 gate to GND. Same for the right leg. No high-side equivalent is fitted — see §8.4 |

## 10.6 H-Bridge Drivers

| **Designator** | **Part** | **Notes** |
| --- | --- | --- |
| IC1 | IR2104PBF | Half-bridge driver, left (DIP-8) |
| IC2 | IR2104PBF | Half-bridge driver, right (DIP-8) |
| C_VCC1 | 100nF ceramic | IC1 VCC bypass |
| C_VCC2 | 100nF ceramic | IC2 VCC bypass |
| D_BOOT1 | UF4007 | Bootstrap diode, IC1 |
| D_BOOT2 | UF4007 | Bootstrap diode, IC2 |
| C_BOOT1 | 100nF ceramic | Bootstrap capacitor, IC1 |
| C_BOOT2 | 100nF ceramic | Bootstrap capacitor, IC2 |

## 10.7 MOSFETs

| **Designator** | **Part** | **Notes** |
| --- | --- | --- |
| Q1 | IRLZ44NPBF | High-side, left (TO-220) |
| Q2 | IRLZ44NPBF | High-side, right (TO-220) |
| Q3 | IRLZ44NPBF | Low-side, left (TO-220) |
| Q4 | IRLZ44NPBF | Low-side, right (TO-220) |

## 10.8 RC Snubber

| **Designator** | **Part** | **Notes** |
| --- | --- | --- |
| R_SNB | 100Ω 1W (MFR-100, DIN0414) | Snubber resistor, across primary. Value confirmed against measured leakage at Rev 51 — §8.5. |
| C_SNB | 10nF 250V film (Kemet R82) | Snubber capacitor |

## 10.9 Transformer

| **Designator** | **Part** | **Notes** |
| --- | --- | --- |
| T1 | Antek AS-0522 toroidal mains transformer, 50VA | Two 22V secondaries in series as the drive winding (J7), two 115V primaries in series as the ring output (J8), static shield (PURPLE) to GND or unconnected. Leads: 115V windings RED/BLACK, 22V windings GREEN/BLUE; splices BLUE1–GREEN2 (drive) and RED1–BLACK2 (output), phased per unit — see §9. Off-board, flying leads, no footprint. Two on hand, one measured and phased. Added at Rev 48 — see §9.5; measured at Rev 51 — §9.2, §9.3. |
| (retired) | OSD Black 70V audio distribution transformer | 4Ω primary / 20W tap. Retired at Rev 48: the core saturates at about 4V RMS on the 4Ω winding at 20Hz against a 15.3V RMS drive — §9.5. Row kept so the change is visible; BOM generator quantity 0. |
| C_OUT | 1µF 250V film (Kemet R82) | Output filter across J8, RING_HI to RING_LO, ahead of F2 and both branches. Completes an LC low-pass with T1's leakage (4.4mH referred to the secondary): corner 2.4kHz, 280× at 40kHz, damped by the winding copper. Without it the output is the 40kHz carrier at ±125V with edge ringing past ±250V — §9.6. Same part as the station ring-detector blocking capacitors; one from the 20 on hand. Added at Rev 52. |

## 10.10 Connectors and Ring Output Fuse

| **Designator** | **Part** | **Notes** |
| --- | --- | --- |
| J1 | 2-pin screw terminal, 3.50mm, 125V | +24V and GND in, from a dedicated pair at the PSU terminals — see §7.1. Not daisy-chained from another board. |
| J2 | 2-pin screw terminal, 5.00mm, 300V | RING_HI and RING_LO out to the trunk board ring bus (its J6). On Shore OSTTC020162 (DigiKey ED2600-ND), 5.00mm pitch, 300V, 15A, 14-22 AWG, side entry, blue. NOT the same part as J1, which is the OSTTE020104 at 3.50mm and 125V — inadequate here, since 100V RMS ring is 141V peak, above that block's rating entirely. 300V gives 2.1x margin, in line with the 250V film capacitors and 300V cable elsewhere in this zone. Blue against black, so both ring terminals are visually distinct from the 24V input on the same board. Own zone, 3mm creepage, physically separated from J3 and the Olimex — see §13. Not fused on this board: the trunk board fuses its own ring input at its J6 — see §7.6. |
| J4 | 4-pin header, footprint only | Second I²C bus (the ESP32's spare controller) brought out unstuffed. Station §9.2 names this as the escape hatch if the address space fills; the footprint costs nothing now. |
| J6 | 2-pin screw terminal, 5.00mm, 300V | RING_HI through F2, and RING_LO, out to the switchboard's ring supply. Same part as J2 — On Shore OSTTC020162 (DigiKey ED2600-ND), blue. Added at Rev 28; Rev 24 through Rev 27 ran this branch off J2's screws alongside the trunk feed, two conductors per position on a block specified for one. Numbered J6 rather than the next free J5 deliberately: J5 is the black 24V input block on the station and trunk boards and is left unused here. Same zone, creepage and separation rules as J2 — see §13. |
| F2 | 250mA FAST-acting, 5x20mm — Littelfuse 0217.250MXP | In series with RING_HI to J6 only, between T1's output winding and the terminal. Fast-acting, not slow-blow, and the same part and value as the trunk board's F2. Protects the switchboard branch of the ring bus; the trunk branch is protected at its far end. Value provisional pending the measurement trunk §7.6 asks for — see §7.6. |
| FH2 | 5x20mm PC-mount fuse block | Littelfuse 64900001039, 649 series PC-mount block, 5x20mm, 6.3A / 250VAC, solder lug. Second block on this board. Open rather than shrouded, as on the trunk board and for the same reason: the ring output zone is exposed at J2, at J6 and at the transformer secondary regardless, so a shrouded holder would protect one point on a zone that is hazardous by design. |
| J7 | 2-pin screw terminal, 3.50mm, 125V | T1 DRIVE WINDING, off-board. SW_L and SW_R out to the Antek's two 22V windings in series. On Shore OSTTE020104 (DigiKey ED2740-ND), black — the same part as J1. 125V is ample: each leg swings 0 to 24V and the differential is 48Vpp, so nothing here exceeds the rail. Belongs in the low-voltage zone beside the MOSFET drains, not in the ring zone — see §13. Added at Rev 32. |
| J8 | 2-pin screw terminal, 5.00mm, 300V | T1 OUTPUT WINDING (the Antek's two 115V windings in series), off-board. RING_HI and RING_LO in from the winding. On Shore OSTTC020162 (DigiKey ED2600-ND), blue — the same part as J2 and J6, and for the same reason: 80V RMS is 113V peak — it was 141V with the OSD — and the 125V block is not the right part for either. This is the origin of the ring bus on this board, so it sits inside the hazardous zone with J2, F2 and J6 at 3mm creepage — see §13. Added at Rev 32. |
| J9 | 3-pin header, 0.1 inch | Master enable and waveform sync. Pin 1 GPIO4, pin 2 GND, pin 3 GPIO15. A 2.54mm shunt across pins 1 and 2 pulls GPIO4 low and the generator runs; remove it and the generator stops. Pin 3 carries the §12.5 sync with its return on pin 2. GND sits in the middle deliberately: the enable shunt is fitted once and the scope probe is used constantly, so the probe gets the short ground return. A shunt fitted wrongly across pins 2 and 3 grounds a push-pull output, which it survives. Added at Rev 43 — a 2-pin enable header existed on the schematic before this and was in neither this document nor the BOM. |
| J10 | 3-pin header, 0.1 inch | Ring drive monitor — §8.7. Pin 1 MON_A, pin 2 GND, pin 3 MON_B. The filtered 20Hz drive waveform: differential across pins 1 and 3 on the Analog Discovery, or single-ended on either outer pin with the ground clip on pin 2. Same part as J9. Added at Rev 48. |

## 10.11 Ring Drive Monitor

| **Designator** | **Part** | **Notes** |
| --- | --- | --- |
| R_MON1 | 4.7k 1/4W | SW_L to MON_A — §8.7 |
| R_MON2 | 4.7k 1/4W | SW_R to MON_B |
| C_MON | 100nF 50V X7R | MON_A to MON_B. The decoupling part, deliberately — see the Rev 48 change entry. |


# 11. Netlist

| **Net** | **Connections** |
| --- | --- |
| +24V_IN | J1 pin1 (system 24V bus), F1 pin1 |
| +24V_SW | F1 pin2, D1 cathode, C_BULK1+, C_BULK2+, Q1 drain, Q2 drain, U_12V Vin, C_12V_IN1+, C_12V_IN2+ |
| +12V_VCC | U_12V Vout, C_12V_OUT+, C_12V_BULK+, IC1 pin1, IC2 pin1, D_BOOT1 anode, D_BOOT2 anode |
| +3V3 | Olimex 3.3V pin, R_SDA pin1, R_SCL pin1, TVS2 pin8 (V+), C_TVS2+ |
| +5V | Olimex +5V (EXT1 pin 1), U4 pin14, C_U4+ |
| SD_N | U4 pin10 (Gate 5 out), U4 pin13 (Gate 6 in) |
| SD | U4 pin12 (Gate 6 out), IC1 pin3, IC2 pin3, R_SD_PD2 pin1 |
| GND | System GND, D1 anode, C_BULK1−, C_BULK2−, U_12V GND, C_12V_IN1−, C_12V_IN2−, C_12V_OUT−, U4 pin7, IC1 pin4, IC2 pin4, Q3 source, Q4 source, R_SD_PD pin2, R_SD_PD2 pin2, R_PWMA_PD pin2, R_PWMB_PD pin2, R_GS3 pin2, R_GS4 pin2, J9 pin2, J10 pin2, Olimex GND, TVS2 pin4 (V−), C_TVS2−, J1 pin2, J3 pin3, J3 pin5, J3 pin6 |
| GPIO32 | Olimex GPIO32, U4 pin1, R_PWMA_PD pin1 |
| GPIO15 | Olimex GPIO15 (waveform sync), J9 pin3 |
| GPIO33 | Olimex GPIO33, U4 pin5, R_PWMB_PD pin1 |
| GPIO14 | Olimex GPIO14, R_SD_PD pin1, U4 pin11 |
| GPIO4 | Olimex GPIO4 (master enable, active LOW), J9 pin1 |
| SDA | Olimex GPIO13, R_SDA pin2, TVS2 pin1 (IN), J3 pin4 |
| SCL | Olimex GPIO16, R_SCL pin2, TVS2 pin2 (IN), J3 pin2 |
| /RESET | Olimex GPIO5, TVS2 pin3 (IN), J3 pin1 |
| PWMA_MID | U4 pin2 (Gate 1 out), U4 pin3 (Gate 2 in) |
| IN1 | U4 pin4 (Gate 2 out), IC1 pin2 |
| PWMB_MID | U4 pin6 (Gate 3 out), U4 pin9 (Gate 4 in) |
| IN2 | U4 pin8 (Gate 4 out), IC2 pin2 |
| SW_L | Q1 source, Q3 drain, IC1 pin6 (VS), C_BOOT1 (VS side), R_SNB pin1, R_MON1 pin1, J7 pin1 |
| SW_R | Q2 source, Q4 drain, IC2 pin6 (VS), C_BOOT2 (VS side), C_SNB pin2, R_MON2 pin1, J7 pin2 |
| SNUB_MID | R_SNB pin2, C_SNB pin1 |
| MON_A | R_MON1 pin2, C_MON pin1, J10 pin1 |
| MON_B | R_MON2 pin2, C_MON pin2, J10 pin3 |
| VB_L | IC1 pin8, D_BOOT1 cathode, C_BOOT1 (VB side) |
| VB_R | IC2 pin8, D_BOOT2 cathode, C_BOOT2 (VB side) |
| HO_L | IC1 pin7 (HO), R_G1 pin1 |
| Q1_GATE | R_G1 pin2, Q1 gate |
| HO_R | IC2 pin7 (HO), R_G2 pin1 |
| Q2_GATE | R_G2 pin2, Q2 gate |
| LO_L | IC1 pin5 (LO), R_G3 pin1 |
| Q3_GATE | R_G3 pin2, Q3 gate, R_GS3 pin1 |
| LO_R | IC2 pin5 (LO), R_G4 pin1 |
| Q4_GATE | R_G4 pin2, Q4 gate, R_GS4 pin1 |
| RING_HI | J8 pin1 (T1 output winding), C_OUT pin1, J2 pin1, F2 pin1 |
| RING_HI_SB | F2 pin2, J6 pin1 |
| RING_LO | J8 pin2 (T1 output winding), C_OUT pin2, J2 pin2, J6 pin2 |

# 12. Firmware Notes

Moved to control.md at Rev 56. The headings are kept so that the many cross-references to §12.x in this document and the others still land; each points at its new home.

## 12.1 Platform

control.md §2.

## 12.2 Sine Generation

control.md §5.1 and §5.2 — the four constants and where they come from, the 200µs esp_timer in place of the LEDC overflow interrupt, and why SINE_STEPS is coupled to the bootstrap case in §8.3.

## 12.3 Pin Polarity

control.md §3. Both PWM pins active HIGH as of Rev 44, idle at duty 0; the history of the active-low trap is kept there.

## 12.5 Waveform Sync Output

control.md §5.4. GPIO15, one square wave per cycle, levels written not toggled, left as an input until setup() because it is a strapping pin.

## 12.4 I²C Initialisation

control.md §4.2 and §6.

## 12.6 Start Phase

control.md §5.3. The requirement — start at SINE_STEPS/4, not at the zero crossing — and the flux reasoning are there; the verification capture is still to be made and is listed in control.md §11.

# 13. Layout Notes

— Place C_BULK1/C_BULK2 close to Q1/Q2 drain pins.

— Place C_VCC1/C_VCC2 at IR2104 VCC and COM pins.

— Place the 74HCT04 close to the IR2104 IN and SD pins rather than close to the Olimex. The 5V feed is a single low-current wire and does not care about length; the four logic outputs into the drivers do.

— Place C_BOOT1/C_BOOT2 at IR2104 VB and VS pins.

— Keep gate drive loops (driver → R_G → gate → source → COM) as short as possible.

— Route RING_HI/RING_LO away from all low-voltage signal wiring.

— Place J3 (6P6C) at the low-voltage edge of the board, away from the H-bridge, transformer, and any trunk or ring wiring. Mark the high-voltage zone boundary on the silkscreen.

— Place R_SDA and R_SCL close to J3. Route SDA and SCL away from the switching node and gate drive loops.

— Place TVS2 at J3 itself, ahead of R_SDA and R_SCL, with the shortest ground return the layout allows. A clamp sitting behind the pull-ups is a clamp that arrives late. C_TVS2 goes across pins 8 and 4 at the device, in the same zone — it is the local source for the clamp current and it is useless anywhere else.

— Place J8, J2, F2 and J6 together at the high-voltage edge, as far from J3, the Olimex and the 6P6C wiring as the board allows. J8 is where the secondary arrives, so it is the head of that zone rather than an addition to it. Maintain 3mm creepage from the secondary and from all three to everything else, and mark the zone on silkscreen. F2 belongs inside that zone: both of its ends sit at ring potential, and it is not a low-voltage part merely because it is a fuse. C_OUT sits directly at J8, across the two winding pins and before the net fans out to J2 and F2, so the capacitor and the leakage form their filter at the winding rather than at the far end of a trace; it carries 0.15A of 40kHz ripple, so keep that loop short.

— RING_HI reaches J2 and F2 directly from the secondary, and only the short segment from F2 to J6 (RING_HI_SB) is fused. Keep that spine compact so the unfused copper it shares with J2 stays inside the marked zone.

— Place F1 then the D1 clamp at the board 24V input, in that order, before anything else on the rail.

— Place J9 at the low-voltage edge where a hand and a probe can reach it with the board racked, and silkscreen the three pins ENBL / GND / SYNC. It is the only part on the board a user touches in normal operation.

— Place J10 beside J9 at the same edge, silkscreened MON_A / GND / MON_B, and R_MON1, R_MON2 and C_MON between J7 and J10 rather than at the header. The two 4.7k resistors are the only things on this board that carry the switching node away from the MOSFET zone, and 9.4k of series resistance means the trace from them to J10 carries nothing worth worrying about; keep the resistors at the SW_L/SW_R end so the unfiltered node stays short.

— Place J7 beside Q1–Q4, inside the low-voltage zone. It carries the switching node out to the primary, so the two wires to T1 are a 40kHz loop: keep the terminal close to the drains, keep the pair short, and dress the leads together as a pair rather than running them apart. Silkscreen it T1-PRI, and silkscreen J8 T1-SEC, so the two are not interchangeable to someone wiring the transformer with the board in a rack.

Fit D1 as a shunt clamp, not in series. Cathode to +24V, anode to GND, reverse-biased and carrying nothing in normal operation. If the supply is connected backwards the diode conducts hard and blows F1; the board sits at about −0.5V until it opens, which everything on it survives. F1 must be upstream of D1 for this to work — J1, then F1, then the D1 clamp, then the board.

The fuse does open, and it is worth showing rather than assuming. The LRS-150-24 sources 6.5A before its own limiting acts, so a 500mA slow-blow sees roughly ten times its rating and opens in a few milliseconds. The 1N5822 is rated 80A non-repetitive for 8.3ms, an I²t of roughly 26A²s against the 0.25A²s of 5A for 10ms — two orders of magnitude of margin. If the diode does fail, it fails short, which is a dead short across a reversed supply and opens the fuse anyway. Both outcomes end the same way.

On this board the 0.4V matters least of the three — the H-bridge runs from the rail directly and does not care, and the TSR 1-24120 needs 15V in against a 24V rail. The change is made here for consistency rather than necessity: one reverse-polarity arrangement across all three boards is one thing to get right rather than three, and a board that behaves differently from its neighbours is the board that gets wired wrong at three in the morning.

— Place the Traco TSR 1-24120 away from heat-sensitive components; allow airflow clearance. Route no traces under the converter — the datasheet asks for it explicitly, and the part is a 500kHz buck in an unshielded plastic case sitting on a board that also carries a 20Hz ring detector and the I²C bus.

— Star wiring is a system-level requirement. Run a dedicated 24V pair from the PSU terminals to this board.

# 14. Safety Notes

The transformer output winding produces 81V RMS, 114V peak, at no load (measured 2026-09-16, C_OUT fitted). This voltage is potentially lethal. Without C_OUT it is a 40kHz square wave at ±125V with edge ringing beyond ±250V — never run the generator with C_OUT unfitted and anything on J2 or J6. C_OUT holds about 6mJ and is discharged through the winding within microseconds of the drive stopping; there is no stored charge after power-off.

— Enclose in a suitable enclosure; no exposed conductors on secondary side.

— The ring output feeds the shared ring bus on two terminals: J2 to the trunk board's J6, and J6 to the switchboard's ring supply. It is never connected to a telephone line directly, and the station and trunk boards are what gate it onto a line.

— Do not touch secondary wiring or transformer terminals when powered.

— F1 (500mA slow-blow) protects the board 24V input.

— F2 (250mA fast-acting) protects the switchboard branch of the ring bus at J6. It is in RING_HI only. An open F2 stops current flowing but leaves RING_LO connected to the transformer secondary through J6, so a blown fuse is not an isolation method and does not make the switchboard cable safe to handle. Isolate at the GPIO4 master enable or by removing power.

— Shoot-through within each leg is prevented inside the IR2104, which derives HO and LO from a single IN pin with 520ns of deadtime. The 74HCT02 does not and cannot contribute to that; Rev 5 through Rev 30 said here that it did. What disables the bridge is SD, and below it R_SD_PD.

— R_SD_PD ensures the H-bridge is disabled from power-on until the ESP32 explicitly enables it, and if PoE is lost the 5V rail and the SD buffer collapse with the controller, which leaves SD low rather than floating.

— Mean Well LRS-150-24: mains input terminals are lethal. Set 115V/230V selector before first power-on. DC output GND is common across all boards.

— Olimex ESP32-POE-ISO: 3kV DC galvanic isolation on the Ethernet side only. Board GND is not isolated from the 24V system ground.

— A 6P6C plug fits physically into an RJ45 jack. Keep J3 at the low-voltage board edge, well away from the trunk RJ45 jacks on the trunk board and ring wiring on this board.

— Do not connect to a live PSTN line. Designed for 551 switchboard connection only.

# 15. Operator Tone — Moved to the Station Board

This section described an operator tone injector built on this board: a filtered 9000Hz square wave from GPIO15, through a two-pole RC network and a 600:600 transformer T3, coupled into the operator’s talking path through a 22kΩ resistor and a 250V capacitor in each leg. It is deleted as of Rev 27. Nothing on this board generates or couples audio any more.

The function has not gone away — it has moved to a station strip. Station §7.9 stuffs one strip of station board 3 — strip 7, A32 channel 23 — as an operator tap: the same bridging transformer across the same pair, at the same 22kΩ per leg, injecting the same 9000.00Hz at bin 768 into the same point on the switchboard.

## 15.1 Why It Moved

The requirement changed. The injector was one-way by design; all it had to do was put a tone on the operator’s pair. The system now also wants to hear that pair, so the audience loudspeaker can carry what the operator hears and the operator’s own voice, rather than a mix synthesised from the station and trunk channels that is only correct while the game’s model of the connection state matches reality.

Once audio has to travel in both directions, the connection is a station circuit in everything but name: a transformer bridged across a pair, a matched series resistor in each leg, a DC block, and a balanced pair to and from the A32. The station board already has eight of those, laid out, with the D-Sub25 wiring and the channel allocation done. Building a second, one-way version of the same thing on this board and then a receive path somewhere else would be two circuits where one will do.

Generating the tone on the host rather than in firmware is a simplification that comes free with the move. The frequency accuracy argument in the old §15.1 was about not using an RC oscillator, and it is satisfied better by the A32 than by the ESP32: generation and detection now share one clock domain, so the tone completes an exact 768 cycles per 4096-sample block and lands dead centre in its bin with no leakage — the same property the pilot comb relies on, arrived at the same way. The LEDC channel, the divider error calculation and the filter that turned a square wave into one spectral line all become unnecessary.

## 15.2 What Comes Out of This Board

```text
  GPIO15                             freed — see §3.2
  T3, 600:600 transformer            deleted
  1k + 10k + 15nF + 1.5nF filter     deleted
  100nF DC block                     deleted
  2 × 22kΩ series resistors           deleted
  2 × 0.47µF 250V coupling caps      deleted
  pair to the operator’s talking path  deleted from this board
```

None of these appear in the §10 component list — §15 was added at Rev 21 and its parts were never carried into it — so no line item there changes. They do appear in the combined system BOM, where they are removed, and the 22kΩ pair reappears against the station board as R11/R12 at the catalogue value of 22.1kΩ. (Returned to 22kΩ, 1% metal film, at station Rev 3.27 — the E24 value is stocked at 1% after all.)

The third LEDC channel is also freed. §12.2 continues to describe the two channels that generate the ring waveform and is unaffected.

## 15.3 Comb Allocation — Unchanged

The tone still occupies bin 768 at exactly 9000Hz, continuing the eight-bin spacing of the pilot comb above the last trunk slot at bin 760 (8906.25Hz). No change to the detector: it is one more bin in an FFT already being computed. See station §8.3 and trunk §9 for the comb itself.

The tone still appears at both ends of the cord pair, since a cord circuit bridges two jacks. What the game learns is therefore that a connection exists between two circuits, not which end the operator answered first. That is almost certainly what is wanted, but it is connection detection and not direction detection.

Where it is detected. Every station and trunk channel checks bin 768 on its own receive path and reports operator presence as a per-circuit flag — station §8.7 and the op topics in station §9.10. The tap strip's receive channel does not detect; it feeds the audience monitor (station §8.8) and returns the tap's own tone as its transmit-path health check. Rev 27 through Rev 52 said here that the tap channel gave a second, better reading of the same fact; that was withdrawn at Rev 53 — see the change list.

## 15.4 Injection Point — Unchanged

Across tip and ring of the operator’s talking path, on the line side of the 63 induction coil — not the transmitter side, which sits in a DC loop with the carbon element and the 12AD retard coil at a few ohms. Identify the pair on the switchboard itself rather than from the drawing.

The isolation argument that settled §15.5 at Rev 22 survives the move intact, which is the main reason the move is safe. The point was never that the transformer belonged on this board specifically; it was that the transformer must sit between the controller and the cable, so the cable to the switchboard is on the floating, line-referenced side and a fault on it cannot reach a GPIO. On the station strip T2 is in exactly that position, the 22kΩ resistors limit fault current into it to about 2mA at full ring voltage, and the run is treated as line wiring like every other station and trunk line. Same barrier, same cable discipline, different board.

The optocoupler-in-the-cable option rejected at Rev 22 stays rejected, for the same reason: with the transformer where it is, the cable is already on the isolated side and there is nothing left to isolate.

## 15.5 Extension to Cord Pairs

Ten cord pairs could each carry their own tone at bins 776, 784, 792 and upward, which would identify the cord as well as the connection. Recorded here so the comb allocation above bin 768 is understood to be reserved rather than free.

The move changes the shape of this if it is ever taken up. Under the old arrangement it meant ten oscillator channels against three free GPIOs plus ten sets of filter, transformer and coupling components at the switchboard. Under the new one it means ten more A32 output channels and ten more tap strips, which the channel budget cannot currently supply — station §7.9.6 shows all 32 channels allocated at full capacity. Neither is cheap. It stays deferred, and it would need conversion capacity before it needed anything else.
