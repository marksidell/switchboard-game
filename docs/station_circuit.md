**551 Switchboard Simulator**

**Station Interface Circuit Design**

*Rev 3.45 — 8 Strips Per Board, Three Boards (22 Stations, the Operator Tap and the Audience Monitor Output) Plus 8 Trunk Circuits, HCPL3700M Ring Detection, DPDT Double-Pole Off-Hook, MCP23017 I/O over 6P6C I²C and MQTT, RJ45 Station Lines, D-Sub25 Female Audio to the Ferrofish A32 at 48kHz, 32-Slot Pilot Tone Comb, Operator Tap and Monitor Options on Two Strips, Common-Battery Power*

# 1. Overview

Each station interface circuit presents itself to the 551 switchboard as a subscriber station. The switchboard provides 24V DC loop current; the station circuit closes the loop (goes off-hook) on command via a relay. Each station detects incoming ring signal, passes bidirectional balanced audio to and from the Ferrofish A32 converter, and injects a pilot tone that allows the game controller to determine which stations are connected to each other through the switchboard.

Boards carry 8 strips each and three are built, 24 strips in all. Twenty-two are stations. The last two strips of the last board are not: strip 7 — A32 channel 23 — is stuffed as the operator tap (§7.9), and strip 8 carries the audience monitor output on A32 channel 24 (§7.9.8). All boards are identical; the only per-board difference is the MCP23017 address strap and the A32 D-Sub connector they land on. Rev 3.5 through Rev 3.34 described a staged build of two boards with the third as populated-later capacity; as of Rev 3.35 all three are built and the build state is no longer a variable in this document.

Alongside the stations the switchboard carries 8 trunk circuits, designed separately. They are referenced throughout this document wherever they affect the station design, which is in three places: they share the pilot tone comb (§8), they consume the remaining audio channels (§6), and they take the fourth MCP23017 address on the same I²C bus (§9.2). Thirty-two circuits in total.

Control is split between two processors. An ESP32 owns all digital I/O, reaching the per-board MCP23017 GPIO expanders over a single daisy-chained I²C bus, and talks to the Linux host over PoE Ethernet using MQTT. The host owns all audio, connected to the Ferrofish A32 through an RME Digiface USB and running at 48kHz throughout. Audio connections are fully balanced throughout. A bidirectional TVS diode across tip and ring at each station jack protects the circuit from ring voltage accidentally applied to an off-hook station.

## 1.1 Division of Labour

```text
AUDIO PATH

   LINUX HOST         audio program (C++): A32 channel I/O, voice routing,
        │             pilot tone generation, FFT pilot detection
        │  USB 2.0
   RME DIGIFACE USB
        │  4 x ADAT optical   (32 channels at 48kHz — see section 6)
   FERROFISH A32
        │  4 x D-Sub25, 8 balanced channels each
   STATION BOARDS 1-3 (ch 1-24) + TRUNK BOARD (ch 25-32)


CONTROL PATH

   LINUX HOST         game program (Python), MQTT broker (Mosquitto)
        │  Ethernet via PoE switch, MQTT over TCP
   ESP32 (PoE)        I2C master, ring debounce, relay control
                      (located on the ring generator board)
        │  I2C daisy chain over 6P6C, 3.3V, 100kHz
   GEN ── BOARD 1 (0x20) ── BOARD 2 (0x21) ── BOARD 3 (0x22) ── TRUNK (0x23)

   per board:  Port A = 8 ring detect inputs
               Port B = 8 off-hook relay outputs
```

The ESP32 and the host exchange state over MQTT: the ESP32 reports debounced ring-detect events, the host commands off-hook. Keeping ring detection and relay control on the ESP32 means loop supervision timing does not depend on the host audio thread, and the ESP32 releases every relay on its own if it loses the host — see §9.12.

## 1.2 Summary of Changes from Rev 2.1

—  Ring detector rebuilt around the HCPL3700M threshold-sensing optocoupler. Its internal diode bridge, threshold comparator and hysteresis replace the 4N35, the external D1–D4 bridge and the collector pull-up network — 4 diodes per station removed.

—  Board density raised from 6 to 8 stations. Total capacity raised from 12 stations (2 boards) to 24 stations (3 boards).

—  One MCP23017 per board now serves both functions: Port A = 8 ring-detect inputs, Port B = 8 off-hook outputs. This is an exact fit and removes the second mandatory expander.

—  Raspberry Pi replaced by an ESP32 as I²C master and digital I/O controller. Logic rail is 3.3V throughout — the MCP23017 must not be run at 5V (see §9.3).

—  Focusrite Scarlett 18i20 replaced by a Ferrofish A32 on D-Sub25, feeding an RME Digiface USB over ADAT, running at 48kHz. All 24 stations fit with eight channels spare, and the system stays coherent to 32 — see §6.

—  Two-tone DTMF-style identification abandoned in favour of a pilot tone comb: one tone per circuit, 6000.00–8906.25Hz on exact FFT bins, detected with a 4096-point FFT. This is what allows 48kHz operation, and it reduces identification to one tone and one bin lookup per station — see §8.

—  Audio transformer requirement relaxed from 27.7kHz to 8.2kHz as a direct result. Specialty wideband transformers are no longer required at every station — see §7.5. This removes the highest-risk and most expensive component in the design.

—  Pilot comb extended from 24 assigned slots to all 32, adding the 8 trunk circuits at bins 704–760. The audio channel budget, the D-Sub pairs and the I²C address space are all now exactly full — see §6.

—  ESP32 to host link changed from USB CDC serial to MQTT over PoE Ethernet, with the broker on the Linux box. Controller becomes an Olimex ESP32-POE-ISO — see §9.7 to §9.12.

—  Off-hook relay changed from SPDT to DPDT (CIT J104D2C5VDC.15S) and now breaks both tip and ring rather than tip alone — see §5.1. Two gaps share the ring standoff, the on-hook station stays balanced on the pair, and R3, C3 and T2 all lift clear of the line.

—  Board rails now generated locally by a 24V→5V DC-DC module per board — see §10.3.

—  Power architecture changed to one common 24V battery feeding the switchboard, both board types, all loops and the ring generator, replacing the separate board supply of Rev 3.2. Star distribution from the PSU terminals becomes a requirement, and the isolated DC-DC is relaxed to the non-isolated part — see §10.1. Supply changes to a Mean Well LRS-150-24.

—  Corrected: the trunk board does not share the station board’s TVS. Trunk uses P6KE150CA, station keeps P6KE120CA — see §4.1.

—  Corrected: the trunk MQTT topics do not share the station topic shape. A trunk has no hook to set and needs a ring command — see §9.12.

—  Corrected: J1 and J2 are D-Sub25 FEMALE, not male. Earlier revisions of both this and the trunk document had this wrong — see §7.6.

—  Station tip and ring move to two shielded RJ45 jacks, four stations each, one twisted pair per station — see §7.7. RJ45 now means telephone line and nothing else anywhere in the system.

—  I²C moves from a 4-pin header to two 6P6C modular jacks per station board, positions 2–5 with the grounds interleaved — see §9.4. Master is the ESP32 on the ring generator board; station boards fit no pull-ups and there is no INT conductor.

—  R_pd (10kΩ base to ground) added to every relay driver. Port B floats between reset and configuration — see §5.2.

—  TVS2 rail-clamp array added on SDA/SCL. A 6P6C plug fits an RJ45 jack, and RJ45 now carries line voltage on this board — see §7.8.

—  Rev 3.5: build state stated throughout. Three boards and 24 stations is the design capacity and is what the rack, the loom and the address plan are sized for; two boards and 16 stations is the present build. The third board is a populated-later slot, not a redesign.

—  Rev 3.5 corrected: the address table gave 0x23 to a spare fourth station board and the text below it gave 0x23 to the trunk board. The trunk board has it. There is no fourth station board — see §9.2.

—  Rev 3.5 corrected: address strapping. The station boards use SW1, the trunk board uses hard 0Ω links, and the two are different on purpose — see §9.2.

—  Rev 3.5 corrected: the I²C master pins. GPIO17 clocks the Ethernet PHY on the ESP32-POE-ISO and was never available; the bus is now SDA on GPIO13 and SCL on GPIO16 — see generator Rev 16 §3.1. Nothing on this board changes.

—  Rev 3.5 corrected: relay order quantity. 24 for the present build, 32 at full capacity — see §11.

—  Rev 3.6: cross-references follow the generator to Rev 15 and the trunk document to Rev 5.2. The generator's gate-drive logic moves to 5V on a 74HCT02 with its shutdown line buffered, correcting an IR2104 threshold figure. Nothing on the station board changes — the I²C pins, the address plan and the 6P6C pinout are all unaffected.

—  Rev 3.7: fuse and fuse holder part numbers specified. All five fuses in the system are socketed 5x20mm cartridges in the same block — see §11.

—  Rev 3.8: Q2 relay driver changed from 2N3904 to 2N2222A on both board types. Verify the TO-92 pinout against the specific orderable part before layout — see §5.2.

—  Rev 3.9: D6 changed from SS34 to 1N5822. 1N5822, 3A / 40V, DO-201AD axial. The SS34 named through earlier revisions is an SMA/DO-214AC surface-mount part with no through-hole version. 3A is oversized against a 250-500mA fuse and deliberately so: a slow-blow fuse carries well above its rating for some time before it opens. Forward drop is unchanged at roughly 0.3-0.4V.

—  Rev 3.10: TVS2 specified as the Littelfuse SP721APP, a through-hole rail-clamp array at 3pF per line rather than the 1pF earlier revisions assumed — see §7.8.

—  Rev 3.11: hardware /RESET added on 6P6C positions 1 and 6, driven from the generator board and reaching pin 18 of every expander. Adds a 10kΩ pull-up per board and a third TVS2 input; requires six-conductor cords — see §9.4.

—  Rev 3.12: J1 and J2 changed from the Amphenol ICC DBM25S500MN, which DigiKey does not stock, to the NorComp 182-025-213R531. Same gender, orientation, termination and gold contacts, with board locks — see §11.

—  Rev 3.13: SW1 specified as the CTS 206-3ST, sealed, top-actuated — see §11. Silkscreen legend for the address positions added to §9.2.

—  Rev 3.14: J1 and J2 changed to the NorComp 182-025-213R561, the same connector with integral 4-40 female screwlocks rather than a plain threaded shell. The separate screwlock line item is deleted; footprint and backset are unchanged — see §11.

—  Rev 3.15 corrected: U4 is specified in TO-220-3 (MCP1826S-3302E/AB), not SOT-223. SOT-223 is surface mount and contradicted the through-hole build of every other part on the board. The AMS1117-3.3 alternative is dropped — it exists only in SOT-223 — see §10.3.

—  Rev 3.16: RV1 deleted from both board types. The A32's recallable per-channel trim covers it, and a dual-gang through-hole trimmer is not a catalogue part — see §7.4.

—  Rev 3.17: the 5V bulk capacitor is specified at 25V rather than 10V. Derating only; capacitance unchanged — see §10.4.

—  Rev 3.18: bin 768 (9000.00Hz) allocated to the operator tone — generator Rev 21 §15. No change to this board; the transformer sweep target moves from 8906.25Hz to 9000Hz.

—  Rev 3.19: rail capacitors reviewed against the datasheets. Local input and output decoupling added at the LDO, which had none of its own, and a 1000µF audio-band bulk added at the 24V input — this board feeds its loops through 330Ω, not through a current source, so it needs that bulk more than the trunk board does. No new part numbers — see §10.6 and §10.7.

—  Rev 3.20: D6 moves from series to a shunt clamp across +24V BRD and GND, blowing F1 on a reversed supply instead of blocking. Correct change, wrong reason as stated — see the Rev 3.23 note below and §10.5.

—  Rev 3.21: D-Sub ground pins specified. Floating at this board with an unstuffed 0Ω link footprint to board GND — grounded at the A32 end only, matching trunk Rev 5.21 — see §7.6.

—  Rev 3.22: T2 specified as the Triad TY-311P on measured evidence, matching trunk Rev 5.22. Flat at 9kHz with −5.5dB passband loss, better than the SP-70 and far better than its own datasheet band suggests — see §7.5 and trunk §8.3.

—  Rev 3.23 corrects Rev 3.19 and Rev 3.20. Both described R3 as this board's loop feed drawing from +24V BRD. It is not: R3 sits in the tip-ring loop behind the relay contacts and the switchboard supplies the current, as §1 and §5.1 have said throughout. The 1000µF added at Rev 3.19 on that mistaken basis is deleted — this board's 24V rail carries only the DC-DC converters — see §10.7.

## 1.3 Changes in Rev 3.24

—  One station strip can now be stuffed as an operator tap instead of a station — a bridging transformer coupling across the operator’s talking path. Station 8 is designated. See §7.9.

—  The tap is bidirectional, and that is the point of it. It injects the 9000.00Hz operator tone, and it returns the operator’s own audio for the audience monitor loudspeaker. Both directions use one transformer.

—  The operator tone injector is deleted from the ring generator board. Generator §15 built it around a filtered square wave from GPIO15 with its own transformer T3; the tone is now an ordinary A32 output stream on the tap strip’s channel. GPIO15 is freed and T3, its filter and its coupling network come out of the generator build.

—  New §8.8 covers the audience monitor feed: the split between the raw stream for pilot detection and a low-pass filtered copy for the loudspeaker, and why that filter is not analog.

—  Configuration is a stuffing option, not a jumper. An earlier sketch called for jumpers to break the station line network out of circuit; §7.2 already does that when RLY1 releases, so the jumpers were solving a problem the relay had already solved. See §7.9.1.

—  R11 and R12 added to the BOM as per-strip footprints, fitted on the tap strip only, plus R13 as a footprint against a possible transformer resonance. Two resistors are the whole hardware addition — C3 already blocks DC on the primary, so the tap needs no coupling capacitor of its own.

## 1.4 Changes in Rev 3.25

—  The MCP23017 address pins are biased. SW1 does not on its own define an address: A0–A2 have no internal pull-up or pull-down, so three SPST switches leave them undefined in one of their two positions. Rev 3.5 through Rev 3.24 specified the switch and no biasing resistors at all. R19, R20 and R21 are added — 10kΩ from each address pin to +3.3V, with SW1 closing each pin to ground. See §9.2.

—  R17 assigned to the Vᴄᴄ series element at OC1. §3.6 has asked for the footprint since Rev 3.0 and §12 repeats the request, but it had no designator and no line in §11, so it existed only as prose. Eight per board, fitted as a 0Ω link.

—  R18 assigned to the /RESET pull-up. §9.4 has required it on every expander board since Rev 3.11 with the same problem: named in the text, absent from the BOM. One per board.

—  C15, C16 and C17 assigned to the LDO capacitors added at Rev 3.19 §10.6. These were already inside the purchased quantities — twelve 0.1µF and ten 10µF per board only reconcile with them counted — but they had no designators, so the §11 table and the parts on order disagreed.

—  T2 has no screen. §7.3 showed a screen/shield connection to chassis ground and §12 asked for all of them to star to one point. The TY-311P is a four-pin part, and the symbol drawn for it — switchboard:XFMR_TY-311P, against the matching footprint of the same name — has four pins; there is no such terminal on either. Both passages are corrected. What survives of the intent is the D-Sub ground handling in §7.6, which is a separate mechanism and unchanged.

—  R1a and R1b are not valid reference designators. A KiCad reference is a letter prefix and a number, so the pair is drawn as R14 and R15 with the document name carried in a Function field. §11 is annotated; the part, the value and the position are unchanged.

—  The operator tap is replicated on every strip rather than on one. §7.9.1 already put the footprints on all eight; this revision states why it also has to be true in the schematic, and what it costs in the exported BOM. See §7.9.1.

## **1.5 Changes in Rev 3.26**

—  C18 added, 100nF across TVS2 pins 8 and 4 at the device. TVS2 has been specified since Rev 3.10 with no bypass. The SP721 does not shunt to ground; it conducts the transient from the IN pin into V+, so V+ has to source that current locally or it lifts during the event — degrading the clamp and injecting the transient into the +3.3V rail that U1 and the master share. §12 deliberately places TVS2 at J3A/J3B, away from U1 and the LDO, so C6 and C8 are the length of the board away and cannot serve. One per board, not per station. See §9.5.

—  C18 rather than C13, C14 or the free C1 and C2. The station board has no C13 or C14 — the 1000µF withdrawn at Rev 3.23 (§10.7) never carried a designator — but the trunk board does have both, one live and one retired, and a reader moving between the two documents should not have to remember which board is which. C18 is free on both and is the same number for the same part in the same role on each. The trunk board takes C18 at trunk Rev 5.27 and the generator, which numbers functionally, takes C_TVS2 at generator Rev 34.

—  What is deliberately not fitted. The datasheet note asks for bypass on both V+ and V− and for a series resistor in the supply feed. V− is pin 4 and goes straight to GND, so bypassing it is a zero-length connection with nothing to add. The series resistor belongs to the automotive load-dump and reverse-battery case the note is written for; nothing here sees a reverse battery, and series resistance in the V+ feed would raise the clamp’s dynamic impedance, which is the opposite of the intent. Recorded so a later reader comparing the board against the datasheet sees two decisions rather than two omissions.

—  The SP721 pinout is confirmed against the Littelfuse datasheet, revision GD 07/10/24 — IN on 1–3 and 5–7, V− on 4, V+ on 8. Rev 3.10 recorded V+ on pin 8 and V− on pin 4 and was right. No change; noted so the check is on the record and need not be repeated.

—  Parts already on the board: the 0.1µF is stocked in quantity and the BOM count for this board goes from twelve per board to thirteen. Nothing new is purchased.

## **1.6 Changes in Rev 3.27**

—  R11 and R12 go from 22.1kΩ to 22kΩ, 0.25W 1% metal film, matched. No circuit change: 22kΩ is what generator §15.2 specified, and the station design carried it as 22.1kΩ only because Rev 3.24 recorded that 22.0k is E24 and “not stocked in 1% metal film”. That was wrong — 1% metal film is sold at E24 values as well as E96, and 22kΩ 1% is being bought. Every figure in §7.9.3 was computed from 44.2kΩ and moves by 0.5% at most; the loading, fault current, receive and injection levels are restated at 44kΩ and are the same numbers to the precision they were given. The matching requirement is unchanged and is the reason the part is 1%. Changed in §7.9.1, §7.9.2, §7.9.3, §11 and §12, and in the BOM, the library plan, the DigiKey upload, the station schematic guide and generator §15.4.

—  This is not the R1a/R1b change PROJECT_INDEX.md pencilled in for Rev 3.27. That change waits on the measured Antek output and takes whatever revision number is next when it comes.

## **1.7 Changes in Rev 3.28**

—  Operator connection is detected on each circuit’s own receive channel, not on the tap strip’s receive channel. Rev 3.24 through Rev 3.27 said the opposite: §8.8 called the tap reading “the better one” and §8.3 said the operator tone tells the game which circuit the operator is patched to, while the detector in §8.7 searched only comb bins 512–760 and never looked at bin 768 on any circuit channel. Neither reading was actually being produced. The tap-channel reading was also the wrong shape: the operator legitimately bridges both ends of a cord pair at once, so the tap hears two pilots in normal service, which the §8.7 detector reports as a fault. See §8.7.

—  The choice between the two places to detect it was made deliberately. Detecting bin 768 per circuit gives one more return value from an FFT already computed, a single-valued retained MQTT topic per circuit that matches the shape of every other state topic, and a result that survives a fault in the tap strip’s own receive path. Detecting on the tap channel would need a second detector with set-valued output and a set-valued topic, and the game would have to diff successive sets to learn which circuit joined or left. The tap strip’s own transmit path is still checked, by its own tone returning on its own channel (§8.4), so nothing is lost by not detecting there.

—  §8.7: identify_peer() gains an op return value from bin 768. The zero-or-one rule is restated as applying to the comb only; the operator tone is checked independently and may be present with or without a peer.

—  §8.8: the tap strip’s receive channel is monitor-only. The “both readings should agree” cross-check is withdrawn. The software filter and its specification are unchanged; the reasons for rejecting an analog filter are restated without the pilot-detection argument.

—  §9.10: sbgame/station/<n>/op and sbgame/trunk/<n>/op added, "on" | "off", host → broker, retained, published by the same process as the peer topics. §7.9.6 no longer credits the tap input with connectivity detection.

—  §9.10 also specifies the peer payload, which no earlier revision had: a circuit id when connected, an empty retained message for idle (clearing the stored value, as fault already does), and the literal strings "ambiguous" and "deaf" for the two diagnostic states so they cannot be mistaken for a peer id. This is new specification rather than a correction; it was left open until now and the op topic made the gap obvious.

—  Cross-document: generator §15.3’s closing paragraph and its pointer to station §8.8 describe the withdrawn tap-channel reading and want the same correction at the generator’s next revision. Trunk §9’s note that a trunk carries the operator tone whenever the operator is patched to it is already consistent with this revision and needs no change.

—  No hardware change. Firmware and host software consequence only, and none of it on ring/ring.ino.

## **1.8 Changes in Rev 3.29**

—  The MQTT topic prefix changes from sw/ to sbgame/ throughout §9.10 and §9.12, and in the Rev 3.28 entries above, which now read as the topics are. No topic below the prefix changes. Nothing in firmware or host code carries the old prefix yet, so this is the last point at which the rename is free.

—  Why. sw/ was chosen for brevity and never justified. Two letters that could mean switch, software or southwest are not a safe first segment on a broker that may one day be shared with anything else on the museum network. sbgame/ names the exhibit, is unlikely to collide with anything, and is still one segment so wildcard subscriptions such as sbgame/+/+/op work unchanged. sb/ was considered for being easier to type and rejected for having the same weakness as sw/; the prefix is typed once into each codebase and thereafter comes from shell history.

—  Trunk §1.1 and §11.3 and generator §15.3 follow at trunk Rev 5.30 and generator Rev 54.

## **1.9 Changes in Rev 3.30**

—  §9.10’s topic table gets a header row and a key. It had four columns and no header since the table was written, so a reader had to infer that the second column is publisher → consumer and the third is the payload, and "host" was never defined in the section — §1.1 names the Linux box the host, §9.10 did not. Two lines in particular were unreadable cold: `hook/set host -> ESP32` did not say what host was, and `peer host -> broker circuit id` did not say that the connected circuit’s identity is the payload.

—  "host → broker" is replaced by "host → any". Every message goes through the broker, so the old wording said nothing; what it meant is that the audio process publishes and there is no single consumer — the game logic, a monitoring UI and the log all subscribe.

—  The circuit id format is specified for the first time: `station/<n>` or `trunk/<n>`, the same two segments the topic names use, so a peer payload prefixed with `sbgame/` is that circuit’s topic root. §8.7’s code returns a tuple; the host formats it as this string at publish time. No earlier revision said what a "circuit id" looked like on the wire.

—  The table is now a Markdown table. It had been fixed-width text lines separated by blank lines — an artefact of the docx extraction — which a renderer runs together as prose, so the columns the header names did not exist on screen. The ctl rows gain the payloads the prose in §9.12 already gives them.

—  Trunk §11.3 takes the same header and key at trunk Rev 5.31. No hardware, firmware or topic change.

## **1.10 Changes in Rev 3.31**

—  Formatting only. Every circuit diagram, pin list, calculation listing, stuffing table and the §8.7 Python listing — fourteen blocks — is now inside a fenced code block. They had been fixed-width text with a blank line between every row, an artefact of the original docx extraction, which a Markdown renderer collapses into run-together prose with the alignment lost. The §8.7 listing was the worst case: its `# slots 1-24 …` comment rendered as a top-level heading. Same sweep on the trunk document at Rev 5.32 and the generator at Rev 55. No word of the content changes.

—  One sentence added to the §9.10 key: the circuit id on the wire is station/<n> or trunk/<n> and never the 1–32 slot number, which is internal to §8.7’s detector. The Rev 3.30 key gave the format without saying what it was not, and §8.3 and §8.7 use "slot" and "combined space" enough that a reader could reasonably assume the flat number was the id.

## **1.11 Changes in Rev 3.32**

—  A heartbeat from the ESP32 to the host is added: sbgame/ctl/esp_heartbeat, every second from the main loop after the I²C poll, payload uptime in seconds, not retained. The host treats two missed beats as ESP32-down. The existing host → ESP32 heartbeat is renamed sbgame/ctl/host_heartbeat so the pair are distinguishable; its behaviour is unchanged. §9.10 and §9.12.

—  Why it was missing. Every revision since the MQTT link was introduced had the host heartbeat only, on the reasoning that the ESP32’s MQTT keepalive plus the LWT already told the host when the controller was gone. That reasoning was never written down in §9.12, and when it is written down its gap is visible: keepalive proves the network stack is alive, not the main loop, and with an MQTT client that pings from its own task a wedged main loop is invisible to the broker. The same argument the section already makes for the host direction — a healthy connection says nothing about the process behind it — applies to the ESP32 and was not applied. Found by a reader asking where the ESP32’s heartbeat was.

—  The beat is published after the I²C poll deliberately, so it proves the loop that drives relays rather than any task that happens to be scheduled. Firmware consequence, on the Claude Code side when the MQTT firmware is written; nothing in ring/ring.ino today.

—  Trunk §11.4 follows at Rev 5.33.

## **1.12 Changes in Rev 3.33**

—  The two host programs are named, and every host-published topic is assigned to one of them. The host runs two separate programs beside the broker: the audio program, in C++, which owns the A32 and publishes peer, op and its own audio_status; and the game program, in Python, which is the game logic and publishes hook/set, ring/set, game_heartbeat and sync. Earlier revisions said "the host", "the audio process" and "the game logic" interchangeably, and §8.7’s listing being Python made it easy to read the detector as part of the game program. It is not; §8.7 now says the listing is the specification and the implementation is C++. §1.1, §8.7, §9.10, §9.12.

—  sbgame/ctl/host_heartbeat, introduced at Rev 3.32, becomes sbgame/ctl/game_heartbeat, because it is the game program’s and the audio program’s liveness is a different question. Same behaviour.

—  sbgame/ctl/audio_status added: the audio program’s birth message and LWT, "online" | "offline", retained, the same mechanism as the ESP32’s ctl/status. It exists because peer and op are retained, so an audio program that has died leaves the last topology it saw on the broker looking current; the game program must treat those values as stale while audio_status is offline. No heartbeat for the audio program yet — its main loop is the audio callback, and if that stops the A32 stream stops with it, which is a different and louder failure than a wedged ESP32 loop.

—  Trunk §11.3 and §11.4 follow at Rev 5.34.

## **1.13 Changes in Rev 3.34**

—  The MQTT design and the firmware behaviour move out of this document into two new ones. §9.10, §9.11 and §9.12 go to mqtt.md, which tables every message by publisher — ESP32, audio program, game program — rather than by board; §3.7 and the firmware half of §9.12 go to control.md, which specifies the controller as one program for the first time. §9.7’s reasoning for MQTT over Ethernet goes with them. Each section is left as a heading with a pointer so cross-references in this document and the others still land, and the change entries from Rev 3.28 to Rev 3.33 stay here as the record of how the design was arrived at; mqtt.md §10 summarises them.

—  Nothing in the design changes in the move. This document now owns the station hardware and says where each message about it comes from; it no longer says what a message looks like on the wire or what the controller does with it.

## **1.14 Changes in Rev 3.35**

—  Three station boards are built, and the operator tap moves from station 8 (board 1, strip 8) to station 24 (board 3, strip 8). Stations are 1–23, contiguous. Rev 3.5 through Rev 3.34 described a two-board build with the third board as populated-later capacity, and Rev 3.24 chose station 8 for the tap because the last strip of the last board would have moved when the third board arrived. With all three built that objection is gone; §7.9.6 records the reversal and what the alternative buys. Nothing electrical changes — the tap is a stuffing option on identical strips.

—  Consequence: the audience monitor has no A32 output. It was on output 17, free only while board 3 was unfitted; §8.8 now carries this as an open item that blocks the monitor rather than a deferred one, with the Digiface’s own analog output as the likely answer, to be confirmed.

—  Build-state statements swept: §1, §1.1, §6, §7.9.6, §7.9.7, §8.8, §9.4, §9.5 and §11.

## **1.15 Changes in Rev 3.36**

—  The audience monitor output is settled: RME Digiface USB playback channels 33/34, its own TRS line/phones jack, +9.5dBu. §8.8. The A32pro’s rear Main Out is recorded as unusable for the purpose — a monitor mirror of one existing channel, not an addressable 33rd output — with the analog-input-24-plus-external-filter arrangement kept as the fallback. Closes the item Rev 3.35 opened.

## **1.16 Changes in Rev 3.37**

—  §8.8: the Digiface channels 33/34 route is confirmed on the host — class-compliant under Linux, 34 playback channels at 48kHz, S32_LE, tone on 33/34 heard at the phones jack — and the level and driver facts the audio program needs are recorded. No design change. The BOM’s relay count is 23 station relays plus 8 trunk, and the R11/R12 fit note names station 24. The comb slot left unused by the tap is 24 (bin 696), not 8. Trunk Rev 5.37, generator Rev 57, control.md Rev 3 and mqtt.md Rev 3 follow.

## **1.17 Changes in Rev 3.38**

—  §9.10’s summary follows mqtt.md Rev 5 and audio.md Rev 1: the game program now also commands the audio program — play/set, listen/set per circuit, tone/set per trunk, and the monitor and test tone under audio/ — and the audio program echoes each as retained state. Rev 3.34 through Rev 3.37 said the game program commands hook/set and ring/set only, which was complete when written and became a stale cross-reference the moment mqtt.md Rev 5 was. One sentence; no hardware change and nothing else in this document names a topic.

## 1.18 Changes in Rev 3.39

—  Cross-reference only. `esp32.md` is `control.md` and `ring/esp32.ino` is `control/control.ino` as of 2026-09-19 (control.md Rev 9); every reference in this document follows, the Rev 3.34 and Rev 3.37 entries included. The `ring/ring.ino` name in the Rev 3.28 and Rev 3.32 entries is history and stays. No hardware change.

## 1.19 Changes in Rev 3.40

—  The audience monitor moves from the Digiface USB’s own analog output (playback 33/34, settled at Rev 3.36) to A32 balanced output channel 24, station board 3 strip 8. To free that channel the operator tap moves from strip 8 to strip 7 of the same board — A32 channel 23 — and stations are 1–22. Mark’s decision, 2026-09-23. §7.9.6 and the new §7.9.8.

—  What it buys. A balanced output whose level the A32 sets per channel, recallable from its front panel, where the Digiface jack is unbalanced and fixed at +9.5dBu with no TotalMix under Linux to trim it (§8.8, Rev 3.37) — which left the audio program’s own gain as the only control ahead of the amplifier. The monitor also comes out of the same converter as every other channel. What it costs is one station: 22 rather than 23. Comb slots 23 and 24 (bins 688 and 696) both go unused.

—  How the signal leaves the board. Strip 8’s transmit audio arrives on J2 channel 8 like any other strip’s, but this board has no connector for anything except a station line on the far side of T2. Until the next board revision adds one, a shielded pair is soldered to the J2-side pads of the unfitted R7 and R8 — J2 pins 1 and 14 — with its shield to J2 pin 2, and run to the amplifier. Nothing else on the strip is fitted except R2. §7.9.8, with a layout note in §12 for the next revision.

—  The Digiface route is not withdrawn as wrong. It was confirmed on the host at Rev 3.37 and still works; it becomes the fallback, trading places with the A32 route that displaced it. §8.8.

—  Swept: title, §1, §5.5, §6, §7.9.6, §7.9.7, §7.9.8 (new), §8.3, §8.8, §9.2, §10.1, §11 and §12. audio.md Rev 7, mqtt.md Rev 9, control.md Rev 10, trunk Rev 5.39 and generator Rev 62 follow. The audio program and the controller firmware each have a code consequence, on the Claude Code side.

## 1.20 Changes in Rev 3.41

—  The audience loudspeaker is no longer fed from the tap strip alone. The audio program can take the monitor from any station’s or trunk’s receive channel as well as from the tap’s, and the game program points it at the calling line of the call the operator most recently answered. Mark’s decision, 2026-09-24; audio.md Rev 8 §10.3 and game_control.md Rev 6 §6.4 carry it. The operator leaves a call when she throws the ring key to ring the called party, so a monitor fed only from her talking path carried each request and none of the conversation. A calling line’s receive channel carries both sides: its own transmit returns at full strength, since the interface has no hybrid (§8.4), and the far end arrives through the cord.

—  §8.8 is corrected: it said the tap strip’s receive channel feeds the loudspeaker and that this is its only job. Monitoring is still its only job, since it takes no part in detection, but it is now the default monitor source rather than the only one. §7.9 and §7.9.6 follow in a sentence each, and the §9.10 summary names the new command (mqtt.md Rev 13).

—  No hardware change. The §8.8 filter already removes a circuit channel’s own pilot, its peer’s pilot and the operator tone, as it removes the tone and pilots from the tap channel.

## 1.21 Changes in Rev 3.42

—  §4.1 and the §11 BOM row are corrected: they gave the P6KE120CA a 120V standoff. The 120 in the part number is nominal breakdown. The datasheet figures are 102V standoff, 114–126V breakdown and 165V clamp, as `trunk_circuit.md` §6 already had them. The clamp figure used in §4.1 and §5.5 moves from 167V to the datasheet’s 165V, and the worst-case detector current from 8.1mA to 8.0mA.

—  No hardware change. The part is the same, the 24V loop is still far below standoff, and the 127V ring peak is still above breakdown, so the §4.1 reasoning stands.

## 1.22 Changes in Rev 3.43

—  C19 added: 100nF from U1 pin 18 (/RESET) to GND, at the pin, one per board (§9.4, §11). Found on the bench, 2026-10-03, with station board 1 and the trunk board wired together and the serial console attached through repeated board tests: both expanders came back at their power-on configuration — IODIR FF, IPOL 00 — about once per run, each time while a ring relay or an off-hook relay switched. Raising the 24V supply's current limit from 0.1A to 1A changed nothing. With 100nF bodged across pin 18 and ground on both boards there was no reset in twelve runs, against four in the four runs before it. /RESET crosses the bus cord and every board with nothing on it but a 10kΩ pull-up, and the MCP23017 resets on a pulse of about a microsecond, so a spike coupled into the cord was enough. R18 and C19 make a 1ms time constant, and boards in parallel keep it at 1ms; control.md §6.2 holds /RESET low for 2ms and waits 5ms after releasing it, so the deliberate reset still works with no firmware change.

—  The present boards carry C19 as a bodge. The next board revision gives it a footprint at U1 pin 18. Schematic: the root sheet as annotated runs C101–C108, so C19 takes C109 there.

## 1.24 Changes in Rev 3.45

—  The audience monitor cable's shield is not connected at the board (§7.9.8). J106 has hot and cold only, and Rev 3.44 sent the shield to the channel 8 D-Sub ground, J105 pin 2. Mark's decision, 2026-10-05: leave it unconnected at this end, on the same reasoning as §7.6, which earths an audio connection's screen at one end only — the far end — to keep it out of the loop through board GND, the PSU and mains earth. The shield is earthed at the amplifier. If the monitor hums or picks up ring clicks, the remedy is the same as §7.6's: try it, and connect at the board only if that is better.

—  No hardware change.


—  R105 and R106 are footprints left unfitted, not fitted as Rev 3.44 recorded (Mark, 2026-10-05). The D-Sub ground pins float at the board, as §7.6 intends, so the A32 cable shields, like J106's, are earthed at the far end alone. §7.6, the §11 row and the schematic guide follow.
## 1.23 Changes in Rev 3.44

—  The document now names every part by its KiCad designator as annotated on the rev 2 board, the board in hand on all three positions. The eight strips are eight instances of one sheet, numbered 2xx for strip 1 to 9xx for strip 8; a strip part is written with x for the hundreds digit, so Rx03 is R203 on strip 1 and R903 on strip 8. Root-sheet parts keep their own numbers. Change entries before this one keep the names they were written with. The former names, in the §11 BOM notes as well:

| **Former** | **Now** | **Former** | **Now** | **Former** | **Now** |
| --- | --- | --- | --- | --- | --- |
| C3 | Cx01 | R7, R8 | Rx10, Rx11 | C8 | C107 |
| C9 | Cx02 | R11, R12 | Rx04, Rx05 | C10, C11, C12 | C102, C103, C104 |
| C4 | Cx03 | R_pd | Rx02 | C15, C16, C17 | C105, C106, C108 |
| C5 | Cx04 | T2 | Tx01 | D6 | D101 |
| TVS1 | Dx01 | OC1 | Ux01 | F1 with FH1 | F101 |
| D5 | Dx02 | U1 | U101 | J1, J2 | J104, J105 |
| RLY1 | Kx01 | U3, U4 | U102, U103 | J3A, J3B | J101, J102 |
| Q2 | Qx01 | TVS2 | TVS101 | J5 | J103 |
| R4 | Rx01 | SW1 | SW101 | J7A, J7B | J7A101, J7B101 |
| R3 | Rx03 | R18 | R102 | R19, R20, R21 | R101, R103, R104 |
| R1a, R1b | Rx06, Rx07 | R2 | Rx12 | C6 | C101 |
| R5, R6 | Rx08, Rx09 | C19 (bodge) | C109 at the next revision | | |

—  The document follows the rev 2 board as built (Mark, 2026-10-05):
   - U2 and C7, the optional second expander and its decoupling, are removed. The board has no footprint for them and none will be fitted; 0x24–0x27 are unused (§9.1, §9.2).
   - R9 and R10 are removed: the board has no pull-up footprints. The bus's pull-ups are the generator board's R1 and R2 (§9.5).
   - R13, the tap-strip secondary damping, and R17, the Ux01 supply series element, have no footprints. R13 becomes a bodge across T801's secondary if the §7.9.5 sweep asks for it; Ux01 pin 8 goes straight to +3.3V (§3.6).
   - The TVS101 bypass (C18, Rev 3.26) is not on the board. It was missed in the drawing and waits for the next revision (§7.8, §11, §12; TODO.md).
   - The D-Sub ground links are two 0Ω resistors, R105 for J104 and R106 for J105, fitted (§7.6).
   - J106, a two-way MONITOR terminal on strip 8's transmit pair, is on the board: the connector §12 asked for at Rev 3.40 (§7.9.8). "The next board revision" now means rev 3.

—  No electrical change; the design is unchanged apart from recording the board as it is.

# 2. Functional Block Diagram (One Station)

```text
SWITCHBOARD STATION JACK

TIP  o───┬──── Ring Detector (Rx06/Rx07, Cx03, Ux01 HCPL3700M) ──► MCP23017 RING_DET_n
         │
         ├──── Dx01 (P6KE120CA) ──── RING
         │
         └──── Kx01 pole A (NO) ──── node A
                (MCP23017 OFFHOOK_n ──► Rx01 ──► Qx01 ──► relay coil)

RING o───┬──── Kx01 pole B (NO) ──── node B
         │
         └──── (ring detector and Dx01 return)

node A ── Rx03 (330Ω) ── node B                    loop path
node A ── Cx01 ── Tx01 primary (+)               ←→ balanced audio
node B ───────── Tx01 primary (−)

Tx01 secondary: fully floating 600Ω winding

   Hot  ──── Rx08 (1kΩ) ──── A32 ANALOG IN (+)    [receive, D-Sub25 in]
   Cold ──── Rx09 (1kΩ) ──── A32 ANALOG IN (−)

   A32 ANALOG OUT (+) ──── Rx10 (1kΩ) ──── Tx01 sec hot
   A32 ANALOG OUT (−) ──── Rx11 (1kΩ) ──── Tx01 sec cold
                              [transmit, D-Sub25 out]

   (voice audio + pilot tone mixed in software before DAC)
```

# 3. Ring Signal Detection — HCPL3700M

The switchboard applies approximately 90V RMS AC at 20Hz across tip and ring when ringing a station. The HCPL3700M is a threshold-sensing AC/DC-to-logic optocoupler rather than a plain phototransistor coupler, and it absorbs most of the discrete circuitry the Rev 2.1 detector needed.

## 3.1 Why This Part Changes the Circuit

—  Internal diode bridge across the AC input pins. The external D1–D4 1N4007 bridge is deleted — 32 diodes removed from a fully populated 3-board system — while full-wave behaviour, and therefore the 40Hz pulsed output, is retained.

—  Threshold sensing ahead of the LED, with guaranteed limits over temperature (Iᵀᴴ⁺ = 1.96–3.11mA, Iᵀᴴ⁻ = 1.00–1.62mA). Detection no longer depends on the LED’s optical output or on CTR drift with age, which was the weakest assumption in the 4N35 design.

—  Built-in hysteresis of roughly 1.2mA between the rising and falling thresholds, which cleans up the edges at the zero crossings of the 20Hz waveform without any external Schmitt trigger.

—  Internal clamping diodes protect the input buffer and the LED against overvoltage and overcurrent transients — useful on a line that sees relay switching and operator-induced ring overlap.

—  Logic-level open-collector output that runs directly from the 3.3V rail (recommended Vᴄᴄ range is 2–18V), needing only a pull-up.

Isolation is 2500 V RMS minimum per the device datasheet; onsemi and Digi-Key list the HCPL3700M variant at 5000 V RMS. Input-to-output capacitance is 0.6pF, which is low enough that the detector contributes essentially nothing to audio-band coupling across the barrier.

## 3.2 Pin Assignment

| **Pin** | **Name** | **Connection in this design** |
| --- | --- | --- |
| 1 | AC | Line side, via Rx06 / Rx07 / Cx03 from TIP |
| 2 | DC+ | No connection — must be left open for AC-input operation |
| 3 | DC− | No connection — must be left open for AC-input operation |
| 4 | AC | Line side, direct to RING |
| 5 | GND | Logic ground |
| 6 | VO | RING_DET_n to MCP23017 Port A; pull-up Rx12 to +3.3V |
| 7 | NC | No connection |
| 8 | VCC | +3.3V, with Cx04 (0.1µF) to pin 5 |

 

The AC and DC input pairs are alternative entry points into the same input buffer, and the datasheet thresholds for each are specified with the other pair open. Applying the line across pins 1 and 4 with pins 2 and 3 floating is what selects the internal bridge and gives full-wave detection. Cx04 is not optional — the datasheet requires a 0.1µF bypass between pins 8 and 5.

## 3.3 Ring Detector Schematic

```text
TIP  ──── Rx06 (10kΩ) ──── Rx07 (10kΩ) ──── Cx03 (1µF, 250V) ──── Ux01 pin 1  (AC)
RING ──────────────────────────────────────────────────────── Ux01 pin 4  (AC)

Ux01 pins 2, 3   ──── open, no connection (selects the internal AC bridge)
Ux01 pin 5       ──── GND
Ux01 pin 8       ──── +3.3V, with Cx04 (0.1µF) from pin 8 to pin 5, at the device
Ux01 pin 6       ──── Rx12 (4.7kΩ) ──── +3.3V
Ux01 pin 6       ──── RING_DET_n ──── MCP23017 U101 Port A bit n
```

## 3.4 Input Network Sizing

Rx06 and Rx07 set the input current; Cx03 blocks the DC loop voltage. At 20Hz:

```text
Xc(Cx03)  = 1 / (2π × 20 × 1µF)          = 7,958Ω
|Z|     = sqrt(20,000² + 7,958²)      = 21,525Ω
Vpk     = 90V RMS × √2                = 127.3V
Vclamp  ≈ 5V  (AC threshold 4.23–5.50V; input clamp 6.1–7.3V @ 10mA)
Ipk     ≈ (127.3 − 5) / 21,525        ≈ 5.7mA
```

Peak input current of 5.7mA against a worst-case turn-on threshold of 3.11mA gives 1.8× margin. The input current exceeds the threshold for about 113° of each 180° half-cycle, so the output is a clean 40Hz pulse train at roughly 63% duty — comfortably wide for the firmware to sample.

RMS input current is about 4.0mA, so Rx06 and Rx07 dissipate 0.32W between them, 0.16W each. Half-watt parts are adequate; 1W gives thermal headroom if the operator holds the ring key for long periods. Each resistor sees roughly 42V RMS, well inside the working voltage of any standard axial film part, and splitting the value in two also spreads the pulse stress and the creepage across two bodies.

## 3.5 Why Cx03 Is Required

This is the substantive change from a straight resistive dropper. The 24V loop voltage sits across tip and ring whenever the station is on-hook. A purely resistive 20kΩ path would pass roughly 0.95mA of standing DC. That is safely below the 1.96mA minimum turn-on threshold, so the detector would never false-trigger — but it is not below the 1.00mA minimum turn-off threshold. A device at the low end of its tolerance band could therefore stay latched on after ring is removed. Cx03 removes the failure mode entirely by making the standing DC current exactly zero.

Cx03 also has to be large enough that it does not eat the ring signal, and small enough that it does not pass voice. At 1kHz its reactance falls to 159Ω and the path impedance is essentially Rx06+Rx07 alone, so reaching even the minimum turn-on threshold would need about 44V instantaneous on the line — two orders of magnitude above conversational level. A capacitor-dominant dropper (as used in the standalone ring detector on the generator side of this project) would invert that relationship and make audio-band false triggering a real concern, which is why the resistance dominates here.

Cx03 carries the 24V loop voltage as a standing DC bias plus about 45V peak of AC during ring. A 250V film part covers both with wide margin and matches the capacitor already specified elsewhere in the project.

## 3.6 Output Interface and Timing

Rx12 (4.7kΩ) matches the datasheet’s switching test load. The darlington output stage is slow by logic standards — 40µs propagation delay to the high level and 45µs typical rise time — but at a 25ms period this is under 0.2% of a cycle. Maximum recommended operating frequency for the part is 4kHz, two decades above what is being asked of it.

The output is active-low: line energised gives a logic low at pin 6. Either invert in firmware or set the MCP23017 IPOL bit for those pins so a read returns 1 for ring present. Leave the MCP23017 internal pull-ups disabled on Port A, since Rx12 already defines the idle level.

One optional hardening step from the datasheet: if common-mode dV/dt at the barrier could exceed 50,000 V/µs, a series resistor of at least 240Ω in the Vᴄᴄ feed protects the detector chip from surge current. The rev 2 board has no footprint for it: Ux01 pin 8 goes straight to +3.3V, with Cx04 between pins 8 and 5 at the device. Nothing on the bench has suggested the transients come near that figure. If they ever do, the resistor goes in the pin 8 trace with Cx04 downstream of it, at the device side, or the bypass sits on the wrong side of the series element. Rev 3.25 to Rev 3.43 carried it as R17, a footprint the board never got.

## 3.7 Firmware Validation of the Pulse Train

Moved to control.md §7.1 at Rev 3.34. The detector’s 40Hz pulse train (§3.4) is what makes the debounce possible; the debounce — four transitions in 150ms to declare ring, 100ms quiet to declare it released, at a 200Hz poll — is firmware and is specified there.

# 4. Overvoltage Protection — TVS Diode

The operator can inadvertently send ring voltage (90V RMS AC, 127V peak) to a station that is already off-hook. During this overlap the relay is closed and the audio transformer is in circuit. Although Cx01 limits the voltage across Tx01 primary, a bidirectional TVS diode across tip and ring provides a first line of defence, clamping the peak voltage before it reaches any other component.

The TVS also protects the ring detector components (Rx06, Rx07, Cx03 and the HCPL3700M input) from sustained overvoltage if the operator holds ring on the line for an extended period.

## 4.1 TVS Placement and Schematic

```text
SWITCHBOARD STATION JACK

TIP  o────────┬──── to ring detector and relay
                │
           Dx01 (P6KE120CA, bidirectional)
                │
RING o────────┴──── to ring detector and relay
```

Dx01 is a P6KE120CA bidirectional transient voltage suppressor. Standoff voltage is 102V and breakdown 114–126V — the 120 in the part number is nominal breakdown, not standoff. Both are well above the 24V normal loop voltage, so it does not affect normal operation. The 127V ring voltage peak exceeds the breakdown, so the TVS conducts on the peaks; its rated clamp is 165V, the ceiling on what it lets through. Peak pulse power rating is 600W, adequate for sustained ring conditions.

The trunk board uses a different part and this is deliberate, correcting an earlier statement here that the two boards share one. The trunk board fits a P6KE150CA (128V standoff, 143–158V breakdown). The reason is directionality: a station only ever receives ring, so mild conduction on the peaks is the protection doing its job, whereas the trunk board originates ring at 127V peak nominal and up to 141V peak no-load, and a 120V-class part there would conduct on every cycle of every ring — loading the generator, distorting the waveform and dissipating power for nothing. Do not standardise the two boards on a single TVS for the sake of a shorter parts list; the correct part on each board is set by that board’s own ring voltage, not by the other board’s.

With the line clamped at 165V, worst-case detector input current is (165 − 5) / 20,000 = 8.0mA, far below the HCPL3700M’s 140mA surge rating for 3ms pulses and its 50mA average input rating. The detector cannot be damaged by anything the TVS lets through.

Placement: directly at the station jack terminals, before the ring detector resistors Rx06/Rx07 and before the relay. This gives maximum protection to all downstream components.

# 5. Off-Hook Circuit

Going off-hook closes the tip-ring loop through series resistor Rx03, causing DC loop current to flow. The switchboard’s supervisory circuit detects this current and registers the station as answered.

## 5.1 Double-Pole Break

The relay breaks both tip and ring rather than tip alone. Rev 2.1 through Rev 3.2 specified a single-pole relay (Omron G5V-1, SPDT) switching only the tip leg, with Rx03 returning permanently to ring. Breaking both legs is better for three reasons and costs nothing once a 2 Form C part is used:

—  The 127V ring peak that appears across the open contacts of an on-hook station is shared between two gaps in series instead of standing across one. The relay is the isolation barrier between the line and everything downstream of it, so doubling the standoff is worth having.

—  The break stays symmetric. With one leg switched, an on-hook station still presents Rx03, Cx01 and Tx01 to the ring conductor, so it sits on the pair as an unbalanced load. With 8 stations on a board and 24 in the system sharing cable runs, longitudinal balance is what keeps idle stations from coupling into active ones.

—  Rx03, Cx01 and Tx01 are fully disconnected from the line when on-hook. Any leakage or component fault downstream of the contacts is then invisible to the switchboard until the station actually answers.

The ring detector and Dx01 remain permanently across the line ahead of the relay contacts — ring has to be detectable while the station is on-hook, which is the whole point of it.

## 5.2 Off-Hook Relay Schematic

```text
TIP  ──── Kx01 pole A, NO ────┬── node A
                                │
                              Rx03 (330Ω, 2W)      loop path
                                │
RING ──── Kx01 pole B, NO ────┴── node B

   node A ──── Cx01 (0.47µF, 250V) ──── Tx01 primary (+)   audio path
   node B ──────────────────────── Tx01 primary (−)

   (both poles normally open; both close when the relay is energized)

MCP23017 U101 Port B bit n ──── Rx01 (1kΩ) ──── Qx01 base (2N2222A)
Qx01 base ──── Rx02 (10kΩ) ──── GND
Qx01 collector ──── Kx01 coil (−)
Qx01 emitter   ──── GND
Kx01 coil (+) ──── +5V
```

Dx02 (1N4148) flyback diode: anode to Qx01 collector, cathode to +5V

Rx03 limits loop current to approximately 60–70mA with the 24V switchboard supply — within normal station range. Power dissipation in Rx03 at short circuit is 24²/330 ≈ 1.75W, so a 2W part is specified. Dx02 suppresses the inductive flyback spike when the relay releases.

## 5.3 Relay Selection

CIT Relay and Switch J104D2C5VDC.15S. DPDT (2 Form C), 5V coil, through-hole PC pin, fully sealed.

| **Parameter** | **Value** | **Against the requirement** |
| --- | --- | --- |
| Contact form | DPDT (2 Form C) | Both poles used — one per leg. No spare contact. |
| Coil | 5V, 167Ω, 29.9mA, 0.15W | Lower than the 33mA the G5V-1 drew |
| Must operate | 3.75 VDC at 25°C | See the temperature note below |
| Must release | 0.5 VDC | Comfortable |
| Contact rating | 2A, 250VAC / 100VDC | Switches 24V at 70mA; ring-overlap inrush 385mA peak |
| Max switching | 500VA / 200W | Worst case is 90V × 0.27A = 24VA during ring overlap |
| Contact material | AgNi, gold plated | Gold flash helps early life; AgNi carries 70mA fine |
| Operate / release | 6ms / 4ms | Irrelevant against a manual switchboard |
| Sealed | Fully | Board-washable, and keeps contact dust out over a long install |

 

Base drive: with Rx01 at 1kΩ the base current is (3.3 − 0.7) / 1000 = 2.6mA against a 29.9mA coil, a forced beta of 11.5. The 2N2222A is deeply saturated at that ratio, so Vᴄᴱ(sat) is around 0.1V and the coil sees close to the full rail. The MCP23017 sources 2.6mA comfortably against its 25mA per-pin limit, and because Qx01 switches the low side of a 5V coil the 3.3V logic rail creates no level-shifting problem. Rx02 draws 0.26mA of the base current at 3.3V, which is immaterial against the 2.6mA available.

Qx01 is a 2N2222A as of Rev 3.8, replacing the 2N3904 specified through Rev 3.7. The change is one of stock on hand rather than performance — the 2N2222A has more collector-current headroom and a marginally lower Vᴄᴱ(sat) than the part it replaces, and neither matters at 30mA into a 167Ω coil. Nothing else in this section changes.

What does need attention is the pinout. Order a TO-92 part with EBC pinout and confirm it on the datasheet for the exact orderable part, not on the generic 2N2222A number. The original 2N2222A is a TO-18 metal can and will not fit this footprint at all; TO-92 equivalents such as the onsemi PN2222A and P2N2222A are EBC, but TO-92 parts sold as 2N2222A vary between EBC, CBE and ECB by manufacturer. The footprint is committed at layout and there are 24 of these, so settle it before the boards are ordered.

Use the same part on the trunk board. Mixing pinouts across board types, or across the two station boards and the third when it is fitted, builds a trap for whoever populates the last board — which will probably be you, a year from now, working from this document rather than from memory.

Rx02 is new in this revision and it is not decoration. The MCP23017 powers up with every pin configured as an input, so Port B floats from the moment power is applied until firmware finishes configuring the expander — and again after any subsequent expander reset. A floating base on a small-signal NPN is not reliably off. On a station board the worst case is a station that answers itself before the software is running, which is untidy rather than dangerous; the trunk board has the same window and there a floating driver puts 90V on a line. The resistor costs nothing and the two boards should not differ on this.

## 5.4 Coil Margin over Temperature

This is the one parameter with less headroom than it first appears. Must-operate is specified as 3.75V at 25°C, but the coil is copper and its resistance climbs about 0.4% per °C, so the voltage needed to pull in climbs with it:

| **Coil temperature** | **Required** | **Available** | **Margin** |
| --- | --- | --- | --- |
| 25°C | 3.75V | ≈ 4.85V | 29% |
| 40°C | 3.97V | ≈ 4.85V | 22% |
| 70°C | 4.40V | ≈ 4.85V | 10% |
| 85°C | 4.62V | ≈ 4.85V | 5% |

 

Available assumes a 5V rail at its lower tolerance limit less Qx01’s saturation drop, which in turn assumes the 24V battery is set correctly at the PSU terminals — see §10.1.1. A rack at normal room temperature is entirely comfortable; the figures only get uncomfortable if eight coils and a DC-DC converter are sealed in a box with no ventilation. Two consequences for the build: ventilate the enclosure, and do not add any series resistance in the coil path — no current-limiting resistor, no LED wired in series with the coil for indication. If a per-station indicator is wanted, drive it separately.

## 5.5 Procurement and Verification

Two practical points. The footprint changes from the G5V-1: 2 Form C means eight pins rather than six, and that footprint repeats eight times per board, so pull the actual package dimensions before committing the per-station strip layout.

Second, this part carries a 20-week manufacturer lead time even though distributor stock is currently deep. At roughly $1.39 in hundreds, buy the whole system quantity plus spares in a single order rather than per board — 22 for the three station boards (the tap and monitor strips fit none) and eight for the trunks, 30 in all, and 32 counting those two strips’ unstuffed positions as spares. A four-month wait for a second order would be an avoidable and irritating way to stall the project.

One figure to confirm from the datasheet rather than the distributor attribute table: dielectric strength between open contacts. The open contacts stand off 127V peak during ring, and up to 165V if Dx01 is conducting. Parts in this class are normally rated 750–1000 VAC contact-to-contact, so this should be a non-issue, but the attribute table lists only maximum switching voltage, which is a different specification. With the double-pole break each gap sees roughly half of it in any case.

Because both poles are now carrying line current, there is no spare contact available for sensing whether the relay actually operated. If closed-loop confirmation of the hook state is ever wanted, it has to come from sensing loop current rather than contact position — a second optocoupler across Rx03 would confirm both that the contacts closed and that the switchboard is feeding the loop, which is the more useful signal anyway. That needs a spare expander input, and U101 has none (§9.1); the board has no second expander.

Worst case for the 5V rail is all eight relays on a board energised at once: 8 × 29.9mA = 239mA. Size the per-board 5V supply for at least 500mA to cover inrush and margin.

# 6. Audio Transport and Channel Capacity

The system runs at 48kHz. That choice is what makes the channel budget work, and it follows from the identification scheme in §8 no longer needing ultrasonic tones.

The Ferrofish A32 provides 32 balanced analog inputs and 32 balanced analog outputs on four D-Sub25 connectors in each direction, eight channels per connector. ADAT carries eight channels per optical port at 48kHz, and both the A32 and the RME Digiface USB have four ports in each direction, so the link between them carries 32 channels each way — the A32’s full analog complement.

With the eight trunk circuits included, the system consumes exactly that:

| **Limit** | **Capacity** | **Stations + trunks** | **Spare** |
| --- | --- | --- | --- |
| A32 analog I/O | 32 in / 32 out | 24 + 8 = 32 | 0 |
| ADAT link at 48kHz | 32 in / 32 out | 32 | 0 |
| A32 D-Sub25 pairs | 4 (8 channels each) | 3 station + 1 trunk | 0 |
| MCP23017 addresses | 8 (0x20–0x27) | 4 mandatory + 4 optional | 0 if LEDs fitted |

 

This is worth flagging clearly, because it is a change in kind rather than degree. Rev 3.1 had eight spare channels, a spare D-Sub pair and a spare board slot. The trunks consume all of it. At full build the system is exactly full, and every one of the four limits above lands on the same number at the same time — which is elegant, but it means there is no longer any margin anywhere for a fifth D-Sub of anything.

All three station boards are built (Rev 3.35), so the four limits above are reached now rather than at some future full build. Twenty-two of the 24 station channels carry stations. Channel 23 is the operator tap (§7.9.6), which consumes an A32 channel in both directions like any other strip; channel 24’s output is the audience monitor feed and its input is unused (§7.9.8).

The practical consequence: a fourth station board cannot be added without expanding the audio hardware. The options at that point are a second A32 with a second Digiface USB, clock-locked and aggregated at the host, or moving the A32-to-host link to MADI. The A32 has MADI on board and MADI carries 64 channels at 48kHz, so a single RME MADI interface in place of the Digiface USB would double the channel budget over one cable and leave the station boards untouched. If there is any real prospect of going past 32 circuits, choosing MADI now rather than later avoids buying the Digiface twice.

Nothing about the station board design changes either way. This is a decision about the box the D-Sub cables plug into.

## 6.1 Consequences of 48kHz

—  Nyquist is 24kHz and the converter passband is flat to roughly 21.7kHz. The pilot comb sits between 6.0kHz and 8.9kHz, comfortably inside it.

—  A32 converter latency rises from 9/fs to 12/fs, which is 0.25ms at 48kHz. Irrelevant against the 42–85ms identification update rate and inaudible in the voice path.

—  The transformer requirement relaxes dramatically — see §7.5. This is the largest single benefit of the change and it removes the highest-risk component in the Rev 3.0 design.

—  At 96kHz none of this would fit: ADAT sample multiplexing halves the link to 16 channels, which is half of what the 32 circuits need.

# 7. Balanced Audio Interface

Audio is coupled through a 600Ω:600Ω isolation transformer Tx01 whose secondary is left fully floating, producing a balanced signal on the equipment side. The transformer primary is placed after the relay contacts (Kx01) so it is only connected to the line when the station is off-hook. This protects Tx01 from ring voltage during the ringing phase before the station answers. A series DC blocking capacitor Cx01 on the primary prevents DC loop current from biasing the core and also limits the voltage across Tx01 during the brief overlap period after the station goes off-hook but before the operator releases the ring button.

## 7.1 Ring Overlap Protection

Because ring is controlled manually by the operator, there will be a short delay after the station goes off-hook (both relay poles close) before the operator releases the ring button and ring voltage is removed. During this overlap, 90V AC is present on the line simultaneously with the relay being closed and Tx01 in circuit. Cx01 (0.47µF, 250V film) limits the current through Tx01 primary during this overlap:

Reactance of Cx01 at 20Hz is 1/(2π × 20 × 0.47e-6) ≈ 17kΩ. Voltage across Tx01 primary during overlap is 90V × 600/17000 ≈ 3.2V, well within the transformer’s safe operating range. The 250V capacitor rating is required since Cx01 sees the full ring voltage across it during the overlap.

Cx01 also serves as a DC blocking capacitor for normal audio operation. At 0.47µF its -3dB point with the 600Ω primary is 1/(2π × 600 × 0.47e-6) ≈ 565Hz. This is slightly within the voice band, causing some rolloff at the low end. If low-frequency audio quality is important, increase Cx01 to 2.2µF (which gives -3dB at 120Hz) but ensure it is still rated 250V.

## 7.2 Complete Primary Circuit

```text
TIP  ──── Kx01 pole A (NO) ──── node A
RING ──── Kx01 pole B (NO) ──── node B

node A ──── Rx03 (330Ω, 2W) ──── node B

node A ──── Cx01 (0.47µF, 250V film) ──── Tx01 primary (+)
node B ────────────────────────── Tx01 primary (−)
```

Rx03 and the transformer primary both sit behind the contacts, in parallel with each other across nodes A and B. Rx03 carries the DC loop current the switchboard supervises; Cx01 blocks that DC from the transformer while passing audio. When the relay releases, both poles open and the entire station circuit — Rx03, Cx01 and Tx01 — is lifted clear of the line.

## 7.3 Receive Path — Station Line to A32 Analog Input

```text
Tx01 secondary hot   ──── Rx08 (1kΩ) ──── A32 ANALOG IN (+)
Tx01 secondary cold  ──── Rx09 (1kΩ) ──── A32 ANALOG IN (−)
```

The floating secondary naturally drives the balanced A32 input with good common-mode rejection. Rx08 and Rx09 are matched series resistors defining source impedance and protecting the converter input. There is no third connection here. Revisions through Rev 3.24 showed a Tx01 screen or shield earthed to chassis; the TY-311P is a four-pin part with a primary and a secondary and nothing else, so there was never a terminal to land it on. The secondary is unreferenced at this board by design and §7.6 covers what happens to the D-Sub ground pins, which is the real grounding decision on the equipment side.

## 7.4 Transmit Path — A32 Analog Output to Station Line

```text
A32 ANALOG OUT (+) ──── Rx10 (1kΩ) ──── Tx01 secondary hot
A32 ANALOG OUT (−) ──── Rx11 (1kΩ) ──── Tx01 secondary cold
```

There is no hardware attenuator in this path as of Rev 3.16 — see below. The transmit signal is the sum of voice audio and the two ID tones, mixed in software before the DAC. No hardware mixing is required.

RV1 is deleted. Earlier revisions carried a 10kΩ dual-gang trim pot here as an optional transmit attenuator, and flagged it as a deletion candidate because the A32 has switchable analog reference levels of +4dBu, +13dBu and +20dBu per channel plus digital gain trim from −8dBu to +20dBu in 1dB steps, all recallable from the front panel. That covers everything RV1 was there to do, and does it with recall.

Sourcing settled the question that the level argument had left open. A dual-gang trimmer in a through-hole PCB trimmer package is not a normal catalogue item — trimmer potentiometers are essentially all single-gang. The alternative was two single trimmers per circuit, 48 across the system, with no guaranteed tracking between the two halves of a balanced pair; a mismatch between them degrades CMRR, which is the same quantity Rx08–Rx11 are hand-matched to protect. Adding 48 uncontrolled parts to defend against a problem the converter already solves was the wrong trade.

If the ADA8200 path is ever adopted for the final build rather than the bench, this decision has to be revisited: those units have no output trim at all, and the attenuation would have to come back as hardware or as digital level in the host.

## 7.5 Transformer Selection for Station Circuits

Settled by measurement. Tx01 is the Triad TY-311P, and the full comparison against the Triad SP-70 is in trunk §8.3 — the trunk transformers work at the top of the comb and are the harder case, so the measurement was made there and applies here.

Measured, 2026-08-24, Analog Discovery 3 network analyser, 10Hz to 100kHz. Triad TY-311P: passband loss about −5.5dB, flat from roughly 400Hz to 10kHz, no rolloff whatever at 9kHz, and still only −8dB at 100kHz. Low end −8.5dB at 10Hz. Driven at 200mV.

Triad SP-70, swept 2026-08-20: passband loss about −7dB, likewise flat through the comb and past the operator tone. Low end −18dB at 10Hz. Driven at 2V.

The TY-311P is specified. It has lower insertion loss, it is flat where the comb and the operator tone live, and at roughly $5.67 against $20.49 it saves about $310 across the 24 needed. Its datasheet band of 300Hz to 3.5kHz understates it considerably — that specification describes a telephone application, not the limit of the part.

One sample has been swept. Sweep two or three of the production quantity before committing all 24 to boards. What matters is not the absolute loss but the spread between units at 9kHz: if they track within a dB, one detection threshold serves every channel; if they do not, that is a per-channel calibration problem in the detector rather than an analog one, and it is much cheaper to learn on the bench than after assembly.

Incidental, but worth carrying to layout: the two sweeps showed opposite phase in the passband, around 0° for one and 180° for the other, because one was connected dot-to-dot and the other reversed. Not a fault in either part. Make the footprint's dot convention explicit on the silkscreen and wire all 24 the same way — a single reversed transformer inverts one circuit's audio and nothing else, which is the kind of fault that survives a long time before anyone notices.

Station circuits carry voice audio (300–3400Hz) and the pilot tone comb (6000.00–8906.25Hz across all 32 station and trunk slots), plus the operator tone at 9000.00Hz when the operator is patched to that circuit (generator §15). The transformer must therefore be usable to about 9kHz, not to 28kHz as Rev 3.0 required — and 9000Hz, not 8906.25Hz, is now the figure to sweep against.

This is the most consequential downstream effect of moving off ultrasonic identification. The old plan needed a Jensen JT-11P-1 or Lundahl LL1527 at every station purely to reach 27.7kHz, and even then the insertion loss at the top of the band was an open question that had to be settled on the bench before 24 units could be ordered. At 8.9kHz that risk disappears. Ordinary 600Ω:600Ω telephone and line-matching transformers reach this comfortably, and the part becomes a cost and availability decision rather than a technical constraint.

Do still measure one before committing to 24. Standard telephone transformers begin rolling off above roughly 4kHz, so expect some attenuation at the top of the comb — a few dB is typical and entirely workable. What matters is that the rolloff is gradual and repeatable, not that it is flat. Sweep 300Hz to 10kHz and record the insertion loss at each pilot frequency.

If the loss at the top of the comb is significant, pre-emphasise the pilot injection level per station in software to equalise the received magnitudes. This is cheap to do and it is worth doing even for a few dB, because it keeps every station’s pilot at a similar level at the far end and lets one threshold value serve all of them. The ratiometric threshold in §8.4 already tolerates unequal levels, so this is refinement rather than necessity.

## 7.6 Audio Connectors — J104, J105, D-Sub25 Female

Audio terminates in two D-Sub25 connectors in TASCAM analog pinout, mating with the A32 through a standard male-to-male analog loom with no breakout. J104 carries the board’s eight outputs to the A32 analog input connector; J105 carries the A32’s eight analog outputs back to the board. Channel n on the connector is station n on that board.

Both are female sockets. Earlier revisions of this document specified male, which is wrong, and the trunk document carried the same error before correcting it. The convention across TASCAM-pinout equipment — the A32 included — is a female socket on the gear and a male plug on the loom, so a board-to-A32 run is a male-to-male analog snake, which is a stock item. Do not assume male on the grounds that the board is the source end. Confirm against the A32 before ordering. Note that the trunk document refers to the unit as the A32 Pro: both carry 32 analog channels on four D-Sub25 pairs in each direction with the TASCAM analog pinout, so nothing in this section changes either way, but the digital transport differs and the ADAT budget in §6 assumes the A32. Settle which unit is in the rack before the looms are made up.

The eight ground pins on each connector are left floating at this board, on the assumption that they are commoned at the A32, and the reasoning is the same as trunk §8.4. Tx01 isolates, Rx08 to Rx11 run between the winding and the converter, and board GND is in none of it. Grounding them at both ends closes a loop that encircles the rack: board GND to the PSU, PSU to mains earth, earth to the A32 chassis, chassis to the cable ground pins, and back to the board. Eight audio channels sharing that loop is the classic way to acquire mains hum and its harmonics. Grounding at one end only is the standard answer, and the A32 is the end that should have it.

There is a real argument the other way, which is why the decision gets a footprint rather than a piece of copper. Tx01 has interwinding capacitance and its primary sits on a line that carries 90V RMS ring when the operator rings that station. Common-mode current through that capacitance has to return somewhere, and with the secondary unreferenced at the board it returns down the snake to the converter's input. The A32's common-mode rejection should absorb it. Ring transients are fast, and the word doing the work in that sentence is "should".

So: tie the eight ground pins of each D-Sub together at the board into a single node, and take a 0Ω link from that node to board GND. The rev 2 board has one per connector, R105 for J104 and R106 for J105, and both are left unfitted, so the D-Sub grounds float at the board and each cable shield is earthed at the A32 end alone. If ring events produce clicks or thumps in the captured audio, fit them and listen again. A 100Ω resistor in parallel with 10nF is the middle position — it gives transients and RF a path to ground while presenting an open circuit to 50/60Hz loop current — and the same footprints take it.

Silkscreen the link position and what fitting it means. An unstuffed 0Ω whose purpose is undocumented gets fitted by whoever populates the next board, on the reasonable assumption that a missing part is an oversight.

| **Board channel** | **1** | **2** | **3** | **4** | **5** | **6** | **7** | **8** |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Hot (+) | 24 | 10 | 21 | 7 | 18 | 4 | 15 | 1 |
| Cold (−) | 12 | 23 | 9 | 20 | 6 | 17 | 3 | 14 |
| Ground | 25 | 11 | 22 | 8 | 19 | 5 | 16 | 2 |

 

Pin 13 is not connected. The TASCAM analog and AES/EBU digital pinouts differ and breakout cables are not interchangeable; the A32 analog connectors need the analog variant. J104 and J105 need 4-40 female screwlocks on the board side so the loom’s jackscrews have something to bite. On most D-Sub bodies those are a separate line item; the connector specified in §11 has them integral to the mating-side flange, so there is no separate hardware to order, fit or lose. If that part is ever substituted, check the flange feature — a plain threaded shell needs two screwlocks per connector and they must be ordered deliberately.

## 7.7 Station Line Connectors — J7A101, J7B101, RJ45

The eight station pairs leave on two shielded RJ45 jacks, four stations per connector, one twisted pair per station. This matches the trunk board’s arrangement and, more importantly, matches the rule the trunk document establishes for the whole system: RJ45 means telephone line and nothing else, anywhere. The connector type itself signals hazardous voltage.

| **Pin** | **T568B colour** | **J7A101** | **J7B101** |
| --- | --- | --- | --- |
| 1 | white/orange | Station 1 TIP | Station 5 TIP |
| 2 | orange | Station 1 RING | Station 5 RING |
| 3 | white/green | Station 2 TIP | Station 6 TIP |
| 6 | green | Station 2 RING | Station 6 RING |
| 5 | white/blue | Station 3 TIP | Station 7 TIP |
| 4 | blue | Station 3 RING | Station 7 RING |
| 7 | white/brown | Station 4 TIP | Station 8 TIP |
| 8 | brown | Station 4 RING | Station 8 RING |

 

One station per twisted pair, striped conductor to tip. Keeping each station on its own pair rather than splitting a pair across two stations is what preserves longitudinal balance in the cable run, and it is the same discipline the double-pole break in §5.1 exists to maintain at the board.

Use Cat5e rated 300V (CM or CMR) rather than patch cord. Ring is 90V RMS, 127V peak, and patch cords are frequently jacket-printed at 30V or 72V. Check the print rather than the catalogue description. Terminate the shield to chassis at the board end only.

## 7.8 Connector Strategy and the One Residual Mis-Plug

Three signal classes, three connector types: D-Sub25 for audio, 6P6C for I²C, RJ45 for station lines. No cable can be crossed between classes and still seat. This is worth stating as a system rule rather than a per-board choice, because the failure it prevents is severe — a station line pushed into an I²C jack would put 127V peak onto SDA and SCL, shared with every board on the chain and the master.

One case survives and is worth naming because people are surprised by it: a 6P6C plug physically fits an RJ45 jack. It is narrower, so it lands on the middle six positions and leaves the outer two unmade. An I²C cord can therefore be pushed into J7A101 or J7B101, where it would find station tip and ring conductors. The reverse is impossible — an RJ45 plug will not enter a 6P6C jack — so the hazard runs one way only and needs one control.

That control is TVS101, a Littelfuse SP721APP rail-clamp array on SDA and SCL, the same part the trunk and generator boards fit, with a 100nF bypass across its pins 8 and 4 at the device — specified since Rev 3.26 but not on the rev 2 board, so it waits for the next revision (§11). The SP721 does not shunt to ground — it conducts the transient from the IN pin into V+ — so V+ has to be able to source that current locally, or it lifts during the event and the clamp degrades exactly when it is working. Only the V+ side needs it: V− is pin 4 and goes straight to GND, so bypassing that to ground is a zero-length connection. The series resistor the same datasheet note suggests is not fitted, because that note covers automotive load-dump and reverse-battery conditions and series resistance in the V+ feed would raise the clamp’s dynamic impedance. If the station involved is on-hook the array simply clamps. If ring is present, 127V arrives and the array fails short, which pulls the bus down and halts the system rather than passing ring voltage to four expanders and the master. A failure that stops the game is a far better outcome than one that destroys the control system, and the array costs about 3pF against a bus with a large timing margin.

The SP721APP is an 8-PDIP with six protected inputs, clamping each to V+ (pin 8, here +3.3V) or V− (pin 4, here GND) through SCR/diode structures that trigger one VBE beyond the rail. It is specified over the smaller surface-mount ESD arrays because the rest of this board is through-hole and its 3pF per line costs nothing against the bus budget in §9.5 — 6pF on top of roughly 50pF. Four of its six inputs are unused.

Treat it as sacrificial. Steering 127V into a 3.3V rail is not a rated condition for any part, and it is not meant to be survivable — it is meant to stop the system. Keep spares, and a socket is worth considering given it is a DIP.

Group J7A101 and J7B101 at the high-voltage edge of the board with J104, J105 and the I²C jacks at the opposite edge, and mark the boundary on the silkscreen. Colour-code cables and jacks consistently across every board — station and trunk lines in one colour, I²C cords in another. That is now a convenience rather than the primary control, which is the right place for it to be.

## 7.9 Operator Tap Option

The operator’s talking path needs two things from this system. It needs the 9000.00Hz operator tone injected into it so the game can tell which circuit the operator is patched to, which generator §15 previously provided. And, new at this revision, it needs a tap so the audience loudspeaker can carry what the operator hears and the operator’s own voice.

Both are the same electrical connection: a transformer bridged across the operator’s tip and ring. A station strip is already that transformer plus a line interface, so one strip stuffed differently does the whole job, on a board that is already being built, landing on an A32 channel that is already wired.

Taking the monitor audio from the tap rather than synthesising it from the station and trunk channels is the more important half of this. The tap is true by construction. Whatever the switchboard actually does — sidetone, the real summation through its cord circuits, ring trip transients, busy tone, the click of the talk key, any cross-plug not anticipated — is present on that pair. A synthesised mix is only correct while the game’s model of the connection state matches reality, and the moments those two diverge are exactly the moments an audience is most interested in. The tap returns on an A32 input, so it becomes the input to the monitor mix rather than a bypass of it: level, filtering, limiting and anything else still happen in software.

As of Rev 3.41 the tap is the monitor’s default source rather than its only one. The operator leaves a call once she rings the called party, so during a conversation the loudspeaker follows the calling line of the call she last answered instead (§8.8). That is a real receive channel as well, and true by construction in the same sense.

## 7.9.1 Configuration Is a Stuffing Option, Not a Jumper

An earlier sketch of this called for a pair of three-pin jumpers per strip to select between the station line network and the tap network. That is unnecessary, and §7.2 is the reason: when Kx01 releases, both poles open and Rx03, Cx01 and Tx01 are lifted clear of the line. A strip whose relay is never energised has already disconnected everything the tap needs disconnected.

What is left is to leave Kx01 out of the strip entirely rather than rely on software never commanding it. A relay that is not fitted cannot be closed by a firmware fault, and Rx03 at 330Ω across the operator’s talking path would be a genuine fault: that path carries talk battery, and shunting it with 330Ω is not something to leave to a software interlock.

So the tap is a designated strip stuffed differently. No jumper carries ring voltage or loop current, the other seven strips are untouched, all three boards stay identical as fabricated, and the configuration is visible on the board rather than hidden in a shunt position. The footprints go on all eight strips so the strip stays a single replicated block in layout; only the stuffing differs. This has to hold in the schematic as well, and the schematic is where it is easiest to get wrong. The eight strips are eight instances of one hierarchical sheet, and a sheet instance owns its reference designators but shares everything else — values, footprints and the do-not-populate flag all belong to the symbol. Rx04 and Rx05 are therefore drawn on every strip and marked do-not-populate. That flag is a BOM attribute and does not remove the footprint from the board, so all eight PCB strips stay identical and one laid-out strip can be copied to the other seven. The cost is that an exported BOM reads zero 22kΩ where the build needs two: reconcile it by hand for Rx04 and Rx05 and for nothing else, against the project BOM, which is the authority. The damping resistor once drawn beside them, R13 until Rev 3.43, has no footprint on the rev 2 board (§7.9.5).

The cost is that reconfiguring between station and tap is a rework operation rather than a field change. For something set once per build, that is the right trade.

## 7.9.2 Circuit

```text
  OP TIP  ──── Rx04 (22k) ────── node A ──── Cx01 (0.47µF 250V) ──── Tx01 pri (+)
  OP RING ──── Rx05 (22k) ────── node B ──────────────────── Tx01 pri (−)
  Rx04 and Rx05 bridge the Kx01 pole A and pole B NO contacts. Kx01 is
  not fitted on the tap strip, so they are the only path to the line.
  Tx01 sec hot  ──── Rx08 (1k) ──── A32 ANALOG IN (+)    monitor + detection
  Tx01 sec cold ──── Rx09 (1k) ──── A32 ANALOG IN (−)
  A32 ANALOG OUT (+) ──── Rx10 (1k) ──── Tx01 sec hot     operator tone
  A32 ANALOG OUT (−) ──── Rx11 (1k) ──── Tx01 sec cold
  damping across Tx01 secondary — no footprint; a bodge only if §7.9.5 calls for it
  Dx01 stays at the jack, as on every strip
```

Two resistors are the entire addition. Cx01 already sits in series with the primary at node A and already blocks DC, so the tap needs no coupling capacitor of its own — only a path from the jack to nodes A and B that bypasses the open relay poles. Rx04 and Rx05 bridge the two NO contacts and do exactly that.

The secondary side is untouched. Rx08–Rx11 are the same matched 1kΩ pairs as every other strip, the D-Sub25 wiring is unchanged, and the tap lands on its board channel exactly as a station would. On the primary, the only difference from a station strip is that 44kΩ of series resistance replaces a pair of closed relay contacts, and Rx03 is absent.

The resistance is split between the legs rather than put entirely in one, but not for the reason generator §15.2 gave. That section said splitting it “keeps the injection balanced”, and that is wrong: the primary floats, so there is no ground reference to define a common mode and the injected current loop is differential wherever the resistance sits. Nor is this the same argument as the matched Rx08–Rx11 pairs, which set the CMRR of a real balanced receiver on the secondary.

What splitting it actually buys is common-mode rejection in the receive direction. Common-mode voltage on the operator pair only becomes differential through a return path, and the only one available is Tx01’s interwinding capacitance to the grounded secondary — a few tens of megohms at mains frequencies. Leg imbalance divides against that. With the resistance split, the imbalance is resistor tolerance, a couple of hundred ohms; with it all in one leg, the imbalance is the full 44kΩ, some 45dB worse. Two resistors instead of one is the cheapest 45dB in the design, and the capacitor imbalance Cx01 leaves behind costs perhaps 25dB of that — worth knowing, not worth a second capacitor and 24 unstuffed footprints to recover.

That estimate rests on an interwinding capacitance nobody has measured, so treat it as a reason to split the resistance rather than as a predicted hum figure. If the tap turns out to hum, short Cx01 and re-measure: that separates a capacitor-imbalance problem from common mode arriving by some other route.

Rx04 and Rx05 are 22kΩ, 1% metal film. Rev 3.24 through Rev 3.26 specified 22.1kΩ on the grounds that 22.0k is E24 and 1% metal film is E96 only; that was wrong, 22kΩ is stocked at 1%, and Rev 3.27 returned to the round value generator §15.2 always called for. The two values differ by 0.5% and nothing in §7.9.3 could tell them apart. What matters is that the two resistors are 1% parts and match each other.

## 7.9.3 Loading, Levels and Fault Current

The 22kΩ per leg is carried over from generator §15.2 rather than re-derived, and the reasons it was chosen there hold here unchanged.

Loading. The bridge presents 44kΩ in series with the transformer primary, which is itself loaded by roughly 12kΩ reflected from the secondary — 2kΩ of Rx08/Rx09 plus the A32 input impedance. The total shunt across the operator’s talking path is about 56kΩ, which on a 600Ω circuit is 0.05dB of insertion loss. The operator cannot hear the tap.

Fault current. The operator’s talking path can see ring voltage and talk battery. At 90V RMS the bridge passes about 2mA and each 22kΩ resistor dissipates about 90mW, inside a 0.25W part with margin. This is the reason not to drop the value. 4.75kΩ per leg would give roughly 8dB more receive level and 13dB more injection, both of which would be welcome — but it also puts about 0.4W into a 0.25W resistor during a ring fault and more than quadruples the current the transformer barrier is asked to hold off. The level problem has a free solution and the fault problem does not, so the level problem is the one to solve.

Receive level. A 44kΩ source into a 12kΩ load is −13.4dB at the primary, and the secondary divider costs another 1.6dB, so the A32 input sees roughly 15dB below whatever is on the operator’s line. For a monitor feed that is ample: even a quiet line at −25dBu arrives some 65dB above the converter noise floor.

Injection level. Driving the other way is the hard direction, because the tone has to get through the same 44kΩ into the line’s 600Ω. The A32 output has to sit about 38dB above the wanted level on the line. For the 12mV that matches the pilot comb in §8.4, that is roughly +1.6dBu at the D-Sub — unremarkable in absolute terms, but only about 2dB below full scale if the channel is left at the +4dBu reference, which is no headroom at all for a continuously running tone.

Set that channel’s analog reference to +20dBu and the tone lands near −18dBFS with the whole of the headroom back. §7.4 already relies on the A32’s per-channel reference and digital trim for exactly this class of problem, and this is another instance of it rather than a new mechanism. Record the setting with the other commissioning values — it is not recoverable by inspecting the board.

Low-frequency corner. Cx01 at 0.47µF against the 56kΩ loop puts the corner near 6Hz — far below the 565Hz it sets in a standard station strip, because there the capacitor works against a 600Ω primary and here it works against the tap bridge. The §7.1 note about raising Cx01 to 2.2µF for low-end response does not apply to this strip. Nothing in the voice band is affected, and the high-pass in §8.8 sets the real low-end limit of the monitor feed anyway.

## 7.9.4 Where to Tap

The same point generator §15.5 specified for the injector: across tip and ring of the operator’s talking path, on the line side of the 63 induction coil — not the transmitter side, which sits in a DC loop with the carbon element and the 12AD retard coil at a few ohms. Identify the pair on the switchboard itself rather than from the drawing.

The tap point now determines what the audience hears as well as where the tone goes in, which raises the stakes on getting it right. Across the talking path you get the far end plus the operator’s own sidetone, which is the mix wanted. Across the receiver alone you get the far end, and the operator’s voice only at whatever level the switchboard’s hybrid sets — which will be too quiet, and the monitor would then need a second source after all, which is the outcome this whole arrangement exists to avoid. Confirm it on the bench before committing the wiring.

The run to the switchboard is line wiring like the station and trunk lines: one pair of 300V Cat5e, landed on the tap strip’s RJ45 position per §7.7. The transformer is the galvanic barrier and Rx04/Rx05 limit fault current into it, exactly the arrangement generator §15.5 argued for and for exactly the same reasons. Nothing about that argument changes by moving the transformer from the generator board to a station strip.

## 7.9.5 Bench Verification

The transformer is working into a much higher impedance than it was swept at. §7.5’s measurement drove the TY-311P in a 600Ω system; here the primary sees 44kΩ and the secondary about 12kΩ. Leakage inductance ringing against winding self-capacitance can produce a high-frequency peak in a lightly loaded transformer that does not appear at all in a matched sweep, so the earlier flat result does not carry over and has to be re-measured in this configuration.

Sweep the assembled tap network, 20Hz to 20kHz, with a 600Ω source at the operator terminals and 10kΩ across the A32 input pair standing in for the converter. Expect about −15dB, flat, with the low-frequency corner near 12Hz. If a peak appears above 8kHz, damp the secondary — 2.2kΩ across Tx01's secondary to start, reduced until it flattens — and re-sweep. The rev 2 board has no footprint for it (it was R13 until Rev 3.43), so on the tap strip (board 3 strip 7) it is a resistor bodged across T801's secondary pads; nothing is fitted until the measurement asks for it.

Confirm the A32 analog input impedance from the Ferrofish specification rather than taking the 10kΩ used above. Every receive-level figure in §7.9.3 depends on it, and it is the one number in the chain that came from an assumption rather than a datasheet.

Then, in order:

—  Measure the injection level actually reaching the line and set the A32 output reference from the measurement rather than from the calculation above.

—  Confirm the operator cannot hear the tone. A period receiver rolls off hard above 3.4kHz and 9000Hz at 12mV should be inaudible at the earpiece, but the path from the tap point through the switchboard to the receiver has never been measured, and “should be” is doing the work in that sentence.

—  Sweep two or three transformers in this configuration, not one. §7.5 asks for the same thing for the station strips and for the same reason — what matters is the spread between units, not the absolute figure.

One question the bench cannot answer: whether 9000Hz survives the switchboard’s cord circuits and repeat coils well enough to be detected at the far end. That needs the real switchboard in the path. The pilot comb runs into the same question across 6000.00–8906.25Hz so it is not a new risk, but the operator tone sits highest of anything in the system and is the first thing that fails if the path rolls off.

## 7.9.6 Which Strip, and What It Costs

Strip 7 of board 3 — A32 channel 23 — is the designated tap, and the rest of this document assumes it. Strip 8 of the same board is the audience monitor output (§7.9.8). Stations are therefore 1–22, contiguous.

Rev 3.24 through Rev 3.34 designated station 8 on board 1, and recorded the last strip of the last board as the alternative, rejected because in a two-board build it would have meant putting the tap on station 16 and moving it when the third board arrived. With all three boards built (Rev 3.35) that objection was gone and the tap moved to board 3 strip 8, for contiguous station numbering and a place at the end of the I²C chain and of the station channels rather than in the middle of both. Rev 3.40 moves it one strip over, to strip 7, so that strip 8’s A32 output can carry the audience monitor. The advantages are unchanged, and the tap and the monitor now sit side by side on one board. Nothing electrical changes: the tap is a stuffing option on a strip that is identical on every board (§7.9.1), and moving it is a matter of which strip gets the Rx04/Rx05 pair and omits its relay and ring detector (§7.9.7).

Channel cost. The tap consumes A32 channel 23 in both directions — the output carries the operator tone, the input carries the default monitor source (§8.8). The monitor takes channel 24’s output. The system is 22 stations, 8 trunks, the tap and the monitor, which is all 32 A32 outputs; on the input side channel 24 is the one channel left unused. Rev 3.35 through Rev 3.39 gave the tap channel 24, left no A32 output for the loudspeaker, and sent the monitor out of the Digiface USB instead; §8.8 keeps that route as the fallback.

Slots 23 and 24 of the pilot comb (bins 688 and 696, 8062.50Hz and 8156.25Hz) go unused while those two strips are the tap and the monitor. Leave them allocated rather than reassigning them. The detector needs no change either way, and a strip reverted to station service gets its pilot back with no firmware edit.

## 7.9.7 Stuffing

Relative to a standard station strip:

```text
  FIT          Tx01, Cx01, Rx08, Rx09, Rx10, Rx11, Dx01     as any station strip
               Rx04, Rx05                         tap bridge, new
               Rx12                               see note below
               secondary damping                  a bodge, only if §7.9.5 requires it
  DO NOT FIT   Kx01, Qx01, Dx02, Rx01, Rx02, Cx02       off-hook path
               Rx03                               loop current resistor
               Rx06, Rx07, Cx03, Ux01, Cx04            ring detector
```

The off-hook path comes out because the strip must never be able to close a loop across the operator’s talking circuit, and the surest way to guarantee that is for the relay not to exist. MCP23017 Port B bit 6 on board 3 then drives nothing; leave the firmware’s output mapping alone rather than special-casing it.

The ring detector comes out because the operator’s talking path is not rung, so the detector has nothing to report, and leaving it fitted would put its 20kΩ input network across the tap for about 0.26dB of additional loading. Not fatal, but there is no reason to pay it.

Rx12 is the exception and stays fitted. It is the 4.7kΩ pull-up on the HCPL3700M output; with Ux01 absent it holds Port A bit 6 of board 3’s expander high, which the firmware reads as a steady no-ring. Omit Rx12 as well and that input floats, which will eventually be read as an intermittent ring on a station that does not exist — the kind of fault that wastes an afternoon.

Cx01 stays fitted and is doing the same job it does everywhere else. Rx03 does not: it is the loop current resistor and has no business across the operator’s talking path.

## 7.9.8 Audience Monitor Strip

Strip 8 of board 3 carries the audience monitor. The filtered, limited mix of §8.8 leaves the host on A32 output 24, arrives at the board on J105 channel 8 like any other strip’s transmit audio, and goes from there to the loudspeaker amplifier. It is not a line interface: nothing on the switchboard side connects to it, J7B101’s strip-8 pair (pins 7 and 8) stays empty, and there is no receive signal, so A32 input 24 is unused.

```text
  FIT          Rx12                               holds Port A bit 7 high
  DO NOT FIT   Tx01, Cx01, Rx08, Rx09, Rx10, Rx11, Dx01     audio and line side
               Rx04, Rx05                         tap parts
               Kx01, Qx01, Dx02, Rx01, Rx02, Cx02, Rx03   off-hook path
               Rx06, Rx07, Cx03, Ux01, Cx04            ring detector
  CONNECTOR    J106, the MONITOR terminal, on strip 8's transmit pair:
               pin 2  AOUT+_8, hot   (J105 pin 1, the J105-side pad of R910)
               pin 1  AOUT−_8, cold  (J105 pin 14, the J105-side pad of R911)
  CABLE        shielded pair from J106 to the amplifier;
               shield not connected at the board, earthed at the amplifier
```

T901 is not fitted because it would put 2kΩ of R910/R911 and a transformer between the A32 and the amplifier for nothing: the A32 output is already balanced, and the amplifier is not a telephone line. J106 picks the signal up where the A32 delivers it, on the J105 side of R910 and R911.

The shield is not connected at the board (Rev 3.45). It is earthed at the amplifier end only, which keeps the monitor run out of the ground loop §7.6 describes — board GND to the PSU, the PSU to mains earth, and earth back through the amplifier's chassis. At the amplifier end, terminate as its balanced input expects. If the run hums or picks up clicks when a station is rung, try the shield on the board's GND as well, as §7.6 does for the D-Sub grounds, and keep whichever is quieter.

The rev 2 board carries J106 for it, a two-way terminal at the low-voltage edge. Rev 3.40 to Rev 3.43 described the first board, which had no connector and took the cable on two resistor pads. J106 carries hot and cold only, and the shield stays unconnected at this end.

Level. Channel 24’s A32 analog reference and digital trim (§7.4) set the output level for the amplifier’s input sensitivity, and are recorded with the other commissioning values; the audio program’s gain and limiter sit ahead of them (§8.8, audio.md §10).

Rx12 stays for the reason §7.9.7 gives: with Ux01 absent it holds Port A bit 7 of board 3’s expander at a steady no-ring. Port B bit 7 drives nothing.

# 8. Station Identification — Pilot Tone Comb

When the switchboard connects two stations via a cord pair, each station needs to know which other station it is connected to. Every station continuously injects a single pilot tone at its own assigned frequency. A station’s receive channel therefore carries its own pilot plus the pilot of the one station patched to it, and a single transform per channel resolves the connection.

This replaces the two-tone DTMF-style scheme used through Rev 3.0. The reasons it is better are worth stating, because they are not only about simplicity:

—  One frequency per station instead of a pair, and one lookup instead of a 5×5 grid decode.

—  A wrong answer becomes distinguishable from no answer. The old scheme took the strongest tone in each group and returned whatever that decoded to, so it produced an answer whether or not one was warranted. A comb reports how many pilots crossed the threshold, and since this switchboard makes point-to-point connections only, any count other than zero or one is a fault rather than a topology — see §8.7.

—  Detection looks for energy in specific bins rather than broadband energy in a band, so board crosstalk and hybrid leakage do not produce false positives — they raise the floor, and the threshold in §8.4 is measured against that floor.

—  The comb lives in the audio band, which is what allows 48kHz operation and everything that follows from it.

## 8.1 Why 6–8kHz Rather Than Ultrasonic

The pilots need to be outside the voice band but inside something a 600Ω telephone transformer will actually pass. Placing them just above the voice band satisfies both. A telephone receiver rolls off hard above 3.4kHz, so a pilot an octave above that is heavily attenuated at the earpiece even though it is nominally within human hearing, and at −40dBFS injection it is inaudible in practice.

The change in transformer requirement is the real prize. Rev 3.0 asked the transformer to pass 27.7kHz, which ruled out ordinary telephone transformers and forced a Jensen or Lundahl part at every one of 24 stations. At 8.2kHz the requirement is ordinary. See §7.5.

The trade-off is that the pilots are now inside the passband of the audio path rather than above it, so they are present in the recorded signal. Low-pass the receive audio at 4kHz before it is used as voice — the line is band-limited to 300–3400Hz anyway, so nothing is lost — and run the identification FFT on the unfiltered signal. Filter for listening, transform for detection.

## 8.2 Frequency Plan

Detection uses a 4096-point FFT at 48kHz. That gives a bin resolution of 48000/4096 = 11.71875Hz and a block duration of 85.3ms; with 50% overlap the update rate is roughly 43ms.

Pilot frequencies must land exactly on FFT bins. This matters more than it looks. A round 100Hz spacing starting at 6000Hz does not: 6000Hz is bin 512 exactly, but 6100Hz is bin 520.53, and an off-bin tone smears across neighbouring bins and loses up to 3.9dB of peak amplitude to scalloping with a rectangular window. Snapping the spacing to a whole number of bins removes both problems.

The comb is therefore spaced eight bins apart — 93.75Hz — starting at bin 512:

```text
pilot_bin(n)  = 512 + 8 x (n - 1)          n = station number, 1-based
pilot_hz(n)   = pilot_bin(n) x 48000/4096
```

Because generation and analysis both run on the host inside a single clock domain slaved to the A32, every pilot completes an exact integer number of cycles per 4096-sample block. Leakage into other bins is then zero by construction and a rectangular window is optimal — no window function is needed. If generation and analysis ever end up in separate clock domains, switch to a Hann window and sum the three bins around each pilot.

## 8.3 Circuit Assignments

The comb carries 32 slots: 24 stations and 8 trunk circuits. Trunks are designed separately but must share the comb, because a station patched to a trunk has to identify it exactly as it would identify another station. Slots 1–24 are the stations, unchanged from Rev 3.1, and slots 25–32 are the trunks.

| **Station** | **FFT bin** | **Frequency** | **Board** | **Board channel** |
| --- | --- | --- | --- | --- |
| 1 | 512 | 6000.00 Hz | 1 | 1 |
| 2 | 520 | 6093.75 Hz | 1 | 2 |
| 3 | 528 | 6187.50 Hz | 1 | 3 |
| 4 | 536 | 6281.25 Hz | 1 | 4 |
| 5 | 544 | 6375.00 Hz | 1 | 5 |
| 6 | 552 | 6468.75 Hz | 1 | 6 |
| 7 | 560 | 6562.50 Hz | 1 | 7 |
| 8 | 568 | 6656.25 Hz | 1 | 8 |
| 9 | 576 | 6750.00 Hz | 2 | 1 |
| 10 | 584 | 6843.75 Hz | 2 | 2 |
| 11 | 592 | 6937.50 Hz | 2 | 3 |
| 12 | 600 | 7031.25 Hz | 2 | 4 |
| 13 | 608 | 7125.00 Hz | 2 | 5 |
| 14 | 616 | 7218.75 Hz | 2 | 6 |
| 15 | 624 | 7312.50 Hz | 2 | 7 |
| 16 | 632 | 7406.25 Hz | 2 | 8 |
| 17 | 640 | 7500.00 Hz | 3 | 1 |
| 18 | 648 | 7593.75 Hz | 3 | 2 |
| 19 | 656 | 7687.50 Hz | 3 | 3 |
| 20 | 664 | 7781.25 Hz | 3 | 4 |
| 21 | 672 | 7875.00 Hz | 3 | 5 |
| 22 | 680 | 7968.75 Hz | 3 | 6 |
| 23 | 688 | 8062.50 Hz | 3 | 7 |
| 24 | 696 | 8156.25 Hz | 3 | 8 |

 

Slots 23 and 24 stay in the table and in the comb but are not generated while board 3’s strips 7 and 8 are the operator tap and the audience monitor (§7.9.6). Stations in service are 1–22.

Trunk circuits occupy the top eight slots. Numbering runs from trunk 1 to trunk 8; the slot number in the combined space is 24 plus the trunk number, which is what the detector in §8.7 reports.

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

 

The full comb now spans 6000.00Hz to 8906.25Hz. That top figure was already anticipated as headroom in Rev 3.1 and remains well inside what the transformer and the converter will pass, so adding the trunks costs nothing on the analog side.

One slot above the comb is now spoken for. Bin 768, exactly 9000.00Hz, carries the operator tone injected into the operator's talking path at the switchboard. As of Rev 3.24 that tone is generated by the host as an ordinary A32 output stream on the operator tap strip’s channel (§7.9) rather than by the ring generator board’s ESP32; the frequency, the injection point and the detector are unchanged. It continues the same eight-bin spacing and is one more bin in an FFT already computed: every station and trunk channel checks bin 768 alongside the comb, and a circuit that hears it is bridged by the operator — see §8.7. That is how the game learns which station or trunk the operator is patched to, which the switchboard gives no electrical indication of.

Bins 776 and upward are reserved rather than free. Generator §15.6 records a deferred extension putting a distinct tone on each of the ten cord pairs, which would identify the cord as well as the connection. If anything else ever wants a comb slot, take it from below bin 512, not above 768.

What it does cost is the spare capacity. All 32 slots are now allocated, where Rev 3.1 held eight in reserve against a fourth station board. If a fourth board is ever added, extend the comb upward to slots 33–40 — bins 768 to 824, 9000.00Hz to 9656.25Hz — and give those slots to the new stations. Do not renumber the trunks to keep station numbering contiguous with slot numbering; renumbering means reflashing pilot assignments on working hardware to solve a cosmetic problem. Note that a fourth station board runs into the channel limit in §6 before it runs into the comb.

Neighbouring pilots are eight bins apart across the whole comb, including the station-to-trunk boundary, so the guard bins used for the noise-floor estimate in §8.4 stay clear everywhere.

## 8.4 Injection Level and Threshold

Inject each pilot at approximately −40dBFS, summed with the voice audio before the DAC. With the A32 analog outputs set to the +4dBu reference this puts roughly 12mV on the line — far below voice, but the received signal still arrives tens of dB above the converter noise floor even after transformer and cord-circuit loss. There is no reason to run it hotter, and doing so risks audibility at the earpiece.

Make the threshold ratiometric, never absolute. Compare each pilot bin against the median magnitude of the guard bins around it (offsets of ±2 and ±3 bins are clear of the neighbouring pilots) and require a fixed margin — 20dB is a sensible starting point. This makes detection immune to converter gain settings, A32 digital trim, transformer insertion loss varying station to station, and drift over time. An absolute threshold would need recalibrating every time any of those changed.

A station’s own pilot returns on its own receive channel at full strength, because the two-wire interface has no hybrid. Exclude that bin from the search, and use its magnitude as a health check: if a station stops hearing its own pilot, the fault is in that station’s own transmit path, transformer or cabling, not in the switchboard. The same applies to the operator tap strip: bin 768 returns on its own receive channel at full strength, is excluded from the pilot search there, and its magnitude is the health check on the tap’s own transmit path.

## 8.5 Intermodulation

A uniformly spaced comb has a property worth being explicit about: because the pilot frequencies form an arithmetic progression, every third-order difference product of the form 2fₐ − fᵇ lands exactly on another comb slot rather than near one. Second-order products are harmless — harmonics fall between 12.0kHz and 16.3kHz, and sums higher still, all clear of the comb — but third-order products cannot be designed around while the spacing stays uniform.

In practice this does not matter. Pilots are injected at −40dBFS; the converters are linear to better than −105dB and the transformer, the only meaningfully nonlinear element, contributes far less distortion at that level than the 20dB ratiometric margin allows for. An intermodulation product would need to sit within 20dB of a genuine pilot to cause a false report, which is tens of dB away from anything the chain will produce.

If bench measurement ever shows products approaching the threshold, the fix is to perturb the comb so the spacings are not all equal — alternating 8 and 9 bin steps, for instance — which breaks the arithmetic progression and moves every third-order product off the slots. Do not do this pre-emptively; the uniform comb is worth keeping for the simplicity of a single formula mapping station number to bin.

## 8.6 Channel Mapping

Circuit number maps to A32 analog channel directly. Station board 1 lands on A32 channels 1–8, board 2 on 9–16, board 3 on 17–24, and the eight trunk circuits on 25–32, in both directions. Keeping the input and output channel numbers identical for a given circuit removes an entire class of routing bug during commissioning, and it means the A32 D-Sub pair number is also the board number.

## 8.7 Detection

Each circuit channel answers two questions from one FFT: which other circuit, if any, is it patched to, and is the operator bridged onto it. The two are independent — the operator can listen in on a connected call, answer a station that is patched to nothing else, or be absent from either.

The first question is answered from the comb. This switchboard makes point-to-point connections only — no conferencing, no bridging a third station onto a cord. The detector should therefore expect exactly zero or one comb pilot above threshold, and treat anything else as a fault to be reported rather than a result to be acted on.

The second is answered from bin 768, the operator tone from the tap strip (§7.9, §8.8). It is not a comb slot and is never counted toward the zero-or-one rule. Its presence on a circuit channel means the operator is bridged to that circuit; its absence means the operator is not. Earlier revisions detected the operator on the tap strip’s receive channel instead — §1.7 records why that was withdrawn.

```python
import numpy as np

FS         = 48000
NFFT       = 4096
HOP        = 2048            # 50% overlap -> ~43ms update
BIN_HZ     = FS / NFFT       # 11.71875 Hz
PILOT_BIN0 = 512             # 6000.00 Hz
PILOT_STEP = 8               # 93.75 Hz between adjacent pilots
N_STATIONS = 24
N_TRUNKS   = 8

# slots 1-24 are stations, slots 25-32 are trunks
CIRCUIT = {}
for i in range(1, N_STATIONS + 1):
    CIRCUIT[i] = ("station", i)
for i in range(1, N_TRUNKS + 1):
    CIRCUIT[N_STATIONS + i] = ("trunk", i)

PILOT_BIN = {s: PILOT_BIN0 + PILOT_STEP * (s - 1) for s in CIRCUIT}
OP_BIN     = 768                 # 9000.00 Hz, operator tone (§8.3)

GUARD_OFFSETS = (-3, -2, 2, 3)   # clear of the neighbouring pilots
MARGIN_DB     = 20.0

def bin_db(mag, b):
    # dB of one bin above the median of its guard bins.
    floor = np.median([mag[b + o] for o in GUARD_OFFSETS])
    return (20.0 * np.log10(mag[b] / floor)
            if floor > 0.0 else float("-inf"))

def pilot_levels(block):
    # Return ({slot: dB above local noise floor} for every comb
    # pilot, dB for the operator tone).
    # Rectangular window: pilots sit exactly on bins in a single
    # clock domain, so there is no leakage to window away.
    mag = np.abs(np.fft.rfft(block))
    comb = {slot: bin_db(mag, b) for slot, b in PILOT_BIN.items()}
    return comb, bin_db(mag, OP_BIN)

def identify_peer(block, own_slot):
    # block: NFFT samples from one circuit input channel.
    # own_slot is the combined-space slot number (1-32).
    # Returns (status, peer, op, own_db). status is one of:
    #   "idle"       no comb pilot heard -> circuit not patched
    #   "connected"  exactly one         -> peer is ("station"|"trunk", n)
    #   "ambiguous"  more than one       -> fault, see notes below
    #   "deaf"       own pilot missing   -> local fault
    # op is True when the operator tone is heard, independently
    # of status: the operator may be bridged to an idle circuit
    # or to one end of a connected pair.

    lvl, op_db = pilot_levels(block)
    own_db = lvl.pop(own_slot)         # own pilot returns on own line
    op     = op_db >= MARGIN_DB

    if own_db < MARGIN_DB:
        return ("deaf", None, op, own_db)

    heard = [s for s, db in lvl.items() if db >= MARGIN_DB]

    if not heard:
        return ("idle", None, op, own_db)
    if len(heard) == 1:
        return ("connected", CIRCUIT[heard[0]], op, own_db)
    return ("ambiguous", [CIRCUIT[s] for s in heard], op, own_db)
```

The listing is the specification of the detector, written in Python because that is the shortest way to state it; the implementation is in the audio program, which is C++ (§9.10). Run identify_peer() on every circuit input channel each hop, trunks included. Trunk circuits inject and detect pilots exactly as stations do, so a station patched to a trunk gets back ("trunk", 3) and the trunk gets back ("station", 17). On a working system the only states seen in normal play are idle and connected, each with op either way.

The op flag is deliberately not folded into status. A station the operator has answered but not yet connected through is idle with op set; a station the operator is listening in on is connected with op set. Both are ordinary play, and the game reads them as two facts rather than as one of six states. Bin 768 uses the same ±2 and ±3 guard offsets as the comb, which keeps its floor estimate clear of trunk 8 at bin 760 below it and the reserved bin 776 above.

The other two states are the useful part. Because only one pilot can legitimately be present, a count above one is unambiguous evidence of a problem rather than something the game logic has to interpret. In descending order of likelihood the causes are: MARGIN_DB set too low, so the noise floor or a neighbouring pilot’s skirt is crossing it; crosstalk between adjacent channels on a D-Sub cable or between adjacent station strips on a board; or a switchboard cord fault genuinely shorting two circuits together. Log the full list from an ambiguous result together with the level of each entry — that alone usually identifies which of the three it is, since a threshold problem shows several weak pilots while crosstalk shows one strong and one weak.

The deaf state is the local health check. A station always hears its own pilot, because the two-wire interface has no hybrid and the signal never leaves the board. Losing it means the fault is in that station’s own transmit path, transformer or cabling. It is worth checking first, because a deaf station also cannot be identified by anyone else and so presents as a silent failure from the far end.

Cross-check reciprocity as a second layer. If station 4 reports trunk 2 as its peer, trunk 2 should report station 4. A one-sided report points to a transmit or receive fault on one of the two rather than a real connection change, and catching it here is much easier than debugging it from the game logic later. Publish the result to the peer topics in §9.10 so the mismatch is visible in the log rather than only inside the audio program.

There is no reciprocity check for op, because the tap strip does not detect. Its health check is the one in §8.4: its own tone returns on its own receive channel, and if that goes, no circuit will hear the operator either. Two related consequences are worth knowing. When the operator is bridged across a connected pair, both ends report op, which is correct and not a fault. And the op flag says the operator is bridged, not which cord or which end was plugged first — generator §15.6 records the deferred cord-tone extension that would add that.

Load is negligible. Thirty-two real 4096-point FFTs every 43ms is under a million operations per second on a machine that is already handling 32 channels of audio, and it comes with a full spectrum per channel for free, which is worth having during commissioning.

Set MARGIN_DB empirically against a real cord-pair connection rather than a loopback, since the peer pilot has crossed the switchboard and the loopback path flatters it. Then confirm the setting by verifying that no circuit reports ambiguous with every cord in the switchboard patched at once — with all 32 pilots live this is also the worst case for crosstalk between adjacent D-Sub channels.

## 8.8 Audience Monitor Feed

The audience loudspeaker is fed from one receive channel at a time. By default it is the operator tap strip’s. During a game it is the calling line of the call the operator most recently answered, chosen by the game program (audio.md §10.3, game_control.md §6.4). Rev 3.24 through Rev 3.40 fed it from the tap strip alone. The operator leaves a call when she throws the ring key to ring the called party, so the tap carried each request and none of the conversation; §1.20 records the change.

Feeding the loudspeaker is the tap channel’s only job: operator connectivity is detected per circuit from bin 768 (§8.7), and the tap channel takes no part in it. Rev 3.24 through Rev 3.27 had the tap channel doing detection as well, and treated its reading as the authoritative one; §1.7 records why that was withdrawn. A station or trunk channel used as the source keeps its other jobs. The monitor reads a copy of it.

Listening needs the pilots gone. The tap channel carries the operator tone at close to full level plus the pilots of whichever circuits the operator is bridged to, anywhere from 6000.00Hz to 8906.25Hz. A circuit channel carries its own pilot at full strength, its peer’s pilot, and the operator tone while she is bridged to it. All of it sits above the content: speech is pre-rendered at 16kHz with period band-limiting and the switchboard path is 300–3400Hz, so nothing wanted lives above about 3.5kHz.

The one thing still read from the raw tap stream is bin 768 itself — the tap’s own tone returning on its own channel, which is its transmit-path health check (§8.4). Take that from the raw stream and send a filtered copy to the loudspeaker.

An analog low-pass on this input was considered and rejected. It would have to be jumpered, because the same channel has to pass 6–9kHz whenever the strip is in station service, and a jumper on a replicated strip is one more stuffing hazard of the kind §12 already warns about for Rx04/Rx05. It loads the transformer secondary at high frequency, which drags on the tone injection in the other direction. And it would remove the returned tone that is the tap’s health check. A software filter costs nothing and has none of these problems.

Filter specification for the monitor branch:

—  Low-pass, 6th to 8th order elliptic or Chebyshev Type II, as cascaded biquads in second-order-section form. Passband edge 3.6kHz, stopband edge 5.6kHz, stopband attenuation 70dB or better. That removes the operator tone and the entire comb in one filter, whichever channel is the source.

—  Second-order high-pass at about 150Hz in the same chain. Switchboard hum through a loudspeaker is unpleasant and nothing below 150Hz is wanted.

—  A limiter after both. Monitor gain will be set by ear with the operator wearing the headset, and the limiter is what keeps that process uneventful.

Butterworth is not adequate here. A 6th-order Butterworth at 3.4kHz is only about 29dB down at 6000Hz, and the lowest pilots sit exactly there. The elliptic transition is what the specification is buying, and the passband ripple it costs is irrelevant on a feed that is already band-limited to a telephone.

IIR rather than FIR, because of the acoustic loop. The loudspeaker feeds the room and the operator’s transmitter is in that room, so there is a feedback path with converter and buffer latency already in it. FIR brick-wall latency makes that worse, and a loop with several milliseconds of delay rings rather than howling cleanly, which is harder to gain-stage against. Biquad group delay near cutoff is a millisecond or two, and nobody is judging the phase response of a monitor feed.

Headroom is not a concern. With the output reference at +20dBu per §7.9.3 the tone arrives at the input around 20dB above speech, which costs about three bits of a 24-bit converter.

Tone generation. The operator tone is now an ordinary output stream on the tap strip’s channel, summed with nothing else. 9000Hz at 48kHz is exactly 768 cycles per 4096-sample block, so a 4096-sample wavetable loops seamlessly and the tone sits dead centre in bin 768 with no leakage into its neighbours — the same property §8.2 relies on for the pilots, arrived at the same way.

Monitor output channel. A32 output 24, board 3 strip 8, as of Rev 3.40 (§7.9.8). The audio program sends the filtered, limited monitor mix there, balanced, and channel 24’s A32 reference and trim set its level for the amplifier; nothing in this section’s software design changes. The amplifier connects to the cable soldered at strip 8 until the board carries a connector for it.

The route before that is kept as the fallback. Rev 3.24 through Rev 3.34 had the monitor on output 17, free only while the third board was not yet fitted; Rev 3.35 put the tap on channel 24 and left no A32 output at all; Rev 3.36 settled on the RME Digiface USB’s own analog output — a 6.3mm TRS line/phones jack on the interface that the host sees as playback channels 33 and 34 alongside the 32 ADAT channels, +9.5dBu at 0dBFS. Confirmed on the host, 2026-09-17: under Linux the Digiface USB runs class-compliant on the stock snd-usb-audio driver and reports CHANNELS [10 34], S32_LE, 32–192kHz, so at 48kHz the audio program opens it at 34 channels and writes the 32 A32 outputs to channels 1–32; a test tone on 33/34 was heard at the phones jack. The program still opens it at 34, and 33/34 still work. What moved the monitor off them at Rev 3.40: there is no TotalMix on Linux and so no RME-side volume on that output — it sits at its default, +9.5dBu at full scale, unbalanced — which leaves the program’s own gain and limiter as the only stages before the amplifier’s input sensitivity, where an A32 channel is balanced and has a recallable reference and trim. The A32pro’s rear Main Out was considered at Rev 3.36 and is not usable for this: it is a monitor output with its own DAC that mirrors any one input, output or internal mix, not a channel the host can address. It could be pointed at analog input 23 — the tap’s raw receive audio — but that carries the operator tone and the pilots unfiltered, and would need an analog low-pass and limiter built between it and the amplifier.

# 9. Digital Control — ESP32 and MCP23017

## 9.1 Expander Allocation

Eight stations need eight ring-detect inputs and eight relay outputs: exactly one MCP23017. This is a much tidier fit than the 6-station arrangement in Rev 2.1, which left ten pins idle on the first expander and needed a second one for anything else.

| **Device** | **Pins** | **Function** |
| --- | --- | --- |
| U101 (MCP23017) | Port A 0–7 | RING_DET_1..8 — inputs from HCPL3700M outputs. External pull-ups fitted (Rx12), so leave GPPU off. Set IPOL to invert the active-low sense. |
| U101 (MCP23017) | Port B 0–7 | OFFHOOK_1..8 — outputs, drive high to go off-hook |

 

Note that U101 is exactly full: eight ring-detect inputs and eight relay drives is precisely 16 pins, with nothing spare. Any additional per-station signal — loop-current confirmation of the hook state being the obvious candidate, since both relay poles now carry line current and none is free for contact sensing — needs a second expander, and the board has none: Rev 3.0 to Rev 3.43 kept a footprint for an optional one (U2) that the rev 2 board does not carry and will not. Adding one would take a second I²C address per board, which with four boards is the entire address space.

## 9.2 Addressing

The MCP23017 has three address pins, giving eight addresses from 0x20 to 0x27. With one mandatory expander per board the address plan is straightforward and exactly fills the space at the 24-station target. Three station boards and one trunk board is the whole mandatory allocation; there is no fourth station board, and 0x23 belongs to the trunk:

| **Board** | **Stations** | **U101 address** |
| --- | --- | --- |
| 1 | 1–8 | 0x20  (A2:A0 = 000) |
| 2 | 9–16 | 0x21  (A2:A0 = 001) |
| 3 | 17–22, tap, monitor | 0x22  (A2:A0 = 010) |
| Trunk | — (8 trunks) | 0x23  (A2:A0 = 011) |

 

Strap A0–A2 with SW101, the 3-position DIP switch, rather than hard-wiring. Every station board is then identical and interchangeable, which matters when one comes off the rack for repair and matters more when the third board is fitted and has to take 0x22 without rework. The trunk board does the opposite — its address pins are wired straight to +3.3V and GND, no switch and no links — because there is exactly one of it and nothing to distinguish; see trunk §10.2. That difference between the two boards is deliberate, not an inconsistency between the documents.

SW101 alone is not enough, and this is a correction rather than an addition. The MCP23017's three address pins have no internal pull-up or pull-down and have to be biased externally, so a bank of three SPST switches defines the address in one position and leaves it floating in the other. Rev 3.5 through Rev 3.24 specified the switch and no resistors, which would have produced a board whose address depended on leakage and on what was next to it — and an expander that answers intermittently at the wrong address is a fault that presents as a bus problem rather than a strapping one.

Fit R101, R103 and R104: 10kΩ from A0, A1 and A2 respectively to +3.3V, with each SW101 position closing its pin to ground. Pull-up and switch-to-ground rather than the reverse, so a closed switch reads 0.

Board 1 at 0x20 is therefore all three closed; board 2 at 0x21 has A0 open; board 3 at 0x22 has A1 open. A2 is closed on every station board. An unstrapped board with all three switches open reads 0x27, which is not a station address at all — no board uses it. So a board that arrives from the bench with its switch untouched drops off the master's startup scan as a missing device rather than colliding silently with another station board. That asymmetry is the reason to prefer pull-ups here: the unset state is the conspicuous one.

Silkscreen the sense as well as the addresses. With an active-low strap ON means 0, which is the opposite of what most people assume from a switch marked ON, and this is the one setting on the board that invites being changed by someone who does not know why it is set the way it is.

One consequence of a switch rather than links: it is the only setting on this board that invites being changed by someone who does not know why it is set the way it is. Silkscreen the address against each position — 0x20, 0x21, 0x22 — next to SW101, so the board carries its own explanation. That costs nothing at layout and removes the failure where a board comes back from the bench at the wrong address.

The trunk board takes the fourth address, 0x23. That fills the allocation at four expanders and leaves 0x24–0x27 unused: no board fits a second expander.

If a further expander is ever needed the escape hatch is cheap: the ESP32 has two hardware I²C controllers, so a second bus gives another eight addresses without a mux. The pins for it come out on the generator board, which is where the master lives — generator Rev 16 §10.10 specified an unstuffed header for it (J4), which the generator board as built does not carry. Nothing on the station boards changes if that bus is ever brought into use; a board simply moves to the other chain.

## 9.3 I²C Bus — 3.3V Only

The ESP32 GPIO pins are not 5V tolerant. The MCP23017 will run from 1.8V to 5.5V and would work fine at 5V, but its bus pull-ups would then sit at 5V and would damage the ESP32. Run Vᴅᴅ on every expander from the 3.3V rail. The relay coils stay on 5V; because Qx01 switches the low side, nothing crosses between the two domains.

This is the most likely thing to get wrong when adapting a Raspberry Pi design, since the Pi tolerates the same mistake no better but the older schematic shows a 5V part.

## 9.4 Bus Topology and Connectors — J101, J102

The I²C master is the Olimex ESP32-POE-ISO, which lives on the ring generator board. The bus daisy-chains from there through the station boards and terminates at the trunk board. The generator carries one connector, each station board two, and the trunk board one. The chain is generator, station boards 1 to 3, trunk.

```text
ring generator ──[6P6C]── station 1 ──[6P6C]── station 2
               ──[6P6C]──[station 3]──[6P6C]── TRUNK

  (master, 1x)            (2x each, thru)         (1x, end)

  ~600mm total bus length
```

Station boards sit in the middle of the chain, so each carries two 6P6C jacks wired in parallel, J101 and J102. Which one is in and which is out does not matter electrically — they are the same node — and leaving them interchangeable is one less thing to get wrong at install.

| **Position** | **Signal** | **Pair** | **Connection on this board** |
| --- | --- | --- | --- |
| 1 | — | 3 (1–6) | /RESET — expander hardware reset from the generator board, paired with GND at position 6 |
| 2 | SCL | 2 (2–5) | U101 pin 12 |
| 3 | GND | 1 (3–4) | Board ground — SDA return |
| 4 | SDA | 1 (3–4) | U101 pin 13 |
| 5 | GND | 2 (2–5) | Board ground — SCL return |
| 6 | — | 3 (1–6) | /RESET return — paired with /RESET at position 1 |

 

Each signal has its return on its own concentric pair — SCL with the ground at position 5, SDA with the ground at position 3, /RESET with the ground at position 6. All six positions are occupied as of Rev 3.11, so the cords must be six-conductor. A four-conductor cord in positions 2–5 leaves a working I²C bus with no hardware reset, which is a usable degraded mode rather than a failure.

The grounds are interleaved rather than grouped, and the reason is worth recording. Putting SCL and SDA on adjacent conductors couples the clock edge straight into the data line: at roughly 25pF of mutual capacitance the glitch is Cc/(Cc+Cn) × 3.3V ≈ 0.66V, and a ground conductor between them drops the coupling to about 5pF and 0.16V. With the MCP23017 at 3.3V its VɪH is 2.64V, so a 0.66V dip lands SDA exactly on the threshold. A false edge on SDA while SCL is high reads as a START or STOP — not a corrupted byte but a corrupted transaction. Interleaving buys about 12dB for free. Prefer round twisted six-conductor cable over flat satin cord for the same reason, though the pinout works with either.

Use straight-through cords and verify rather than assume. Standard voice line cords are wired reversed end to end — position 2 lands on 5, 3 on 4 — which with this pinout shorts both SCL and SDA to ground. That is a harmless failure: the pull-ups source about 1.5mA into ground, nothing is damaged, and the bus is simply dead, which the master’s startup scan reports immediately as every device missing. But reversed cords are the commonly stocked kind, so crimp the cords for this system deliberately and label them.

Positions 1 and 6 carry /RESET and its return. The line comes from GPIO5 on the Olimex, arrives at J101, passes through to J102 in parallel with SDA and SCL, and goes to pin 18 of U101. Generator §4.7 owns the design; what matters on this board is four things.

First, fit a 10kΩ pull-up to +3.3V on the /RESET line on every board — R102 (§11). This is deliberately the opposite of the DO NOT FIT rule for the I²C pull-ups in §9.3. On a static line driven by a CMOS output, three 10kΩ resistors in parallel are 3.3kΩ and nothing notices; what they buy is that a board unplugged from the chain still holds its own expander out of reset rather than leaving pin 18 floating, which the MCP23017 does not tolerate.

Second, /RESET now leaves the board on a jack that a station line can be mis-plugged into, so it takes a third input of TVS101 alongside SDA and SCL. The SP721APP has six inputs and this is the third — see §7.8.

Third, and this is the part worth thinking about before using it: a reset drops every off-hook relay on the board. The MCP23017 returns to IODIR = 0xFF with every pin an input, Rx02 holds the drivers off, and any station that was connected is released. That is the same window §5.2 describes at power-on, with the difference that it can now be entered on command. Firmware should assert /RESET at startup and on a detected bus fault, not as routine housekeeping.

Fourth, filter the line at the pin: 100nF from U101 pin 18 to GND, as close to the pin as the layout allows (Rev 3.43). The rev 2 boards carry it as a bodge; it takes C109 at the next revision. /RESET is a long, high-impedance line — the cord, every board, and only 10kΩ pull-ups holding it up — and the MCP23017 resets on a pulse of about a microsecond. On the bench, a relay switching on the board reset the expander about once per board test until the capacitor was fitted, and never after. With R102 it is a 1ms time constant, well inside the 2ms pulse and 5ms settle of control.md §6.2.

## 9.5 Pull-Ups and Bus Loading

Fit no pull-ups on station boards. The single 2.2kΩ pair for the whole bus lives on the ring generator board. The generator's R1 and R2 are that pair. The station board has no pull-up footprints at all, so there is nothing to populate by mistake; three boards each fitting their own pair would take the effective pull-up to 730Ω. Rev 3.0 to Rev 3.43 carried R9 and R10 as DO NOT FIT footprints, which the rev 2 board does not have.

Loading is comfortable. Four expanders at roughly 10pF each plus 600mm of cord comes to about 50pF, which against 2.2kΩ gives a rise time near 94ns — an order of magnitude inside the 1µs I²C budget. Run the bus at 100kHz; polling four expanders at 200Hz needs about 6% of it. No bus buffer is required at this length, and the P82B96 footprint suggested in earlier revisions of this document can be dropped.

## 9.6 Polling, and Why There Is No INT Line

The 6P6C pinout carries SDA, SCL and two grounds, with no conductor left for an interrupt. That is deliberate rather than a shortfall: this system polls, and an interrupt line would be actively unhelpful.

With the HCPL3700M output pulsing at 40Hz, interrupt-on-change means a single ringing station generates 80 interrupts per second, each requiring an I²C transaction to identify and clear. Polling GPIOA from every expander at 200Hz gives five samples per half-cycle of the 40Hz pulse train, which is exactly what the debounce logic in control.md §7.1 needs, and it makes ring-detect timing deterministic — which matters more here than latency.

Consequently the IOCON.MIRROR and open-drain wire-OR arrangement described in earlier revisions is dropped, along with the INT conductor it needed. Leave the expander INT pins unconnected.

## 9.7 ESP32 to Host Communication — MQTT over Ethernet

The controller reaches the host over wired Ethernet with PoE from the same cable and exchanges state through an MQTT broker on the host, replacing the USB serial link of Rev 3.1. The reasons, and the whole message design, are in mqtt.md §1 as of Rev 3.34. This document keeps the hardware side of the link: §9.8 and §9.9.

## 9.8 Controller Hardware and PoE Budget

The ESP32 needs an Ethernet MAC and PHY, which rules out the plain Thing Plus module. The Olimex ESP32-POE-ISO is the recommended board: ESP32-WROOM, LAN8710A PHY, 802.3af PoE, and — the reason to prefer it over the non-isolated ESP32-POE — 3000VDC galvanic isolation between the Ethernet side and the board’s own supply.

That isolation is worth paying for in this application. The controller shares an I²C ground with boards whose ring detector strips sit a few millimetres from 90V ring voltage. The non-isolated variant bonds Ethernet ground directly to board ground, which puts the network — and anything else on it — in the fault path. The isolated board also tolerates USB and PoE connected at the same time, which the non-isolated one does not; on that board connecting USB for programming while PoE is live can destroy the board, the computer, or both.

There is a trap in the power budget worth stating plainly. 802.3af nominally delivers 12.95W to the powered device, which looks like ample headroom to run relays from the Ethernet cable. It is not available. The ESP32-POE-ISO achieves its isolation with a 2W DC-DC converter, and that converter, not the PoE standard, is the binding constraint. The ESP32 itself draws 50–200mA depending on mode, so essentially nothing is left over.

Power the controller from PoE and everything else from a local supply. Twenty-four station relays alone come to about 4W at 5V, with the trunk board and logic rails on top, so the station and trunk boards need their own PSU regardless — see §10. Grounds must still be common between the controller and the boards for I²C to work; the isolation is on the Ethernet side, not the I²C side.

## 9.9 Switch Requirements

Any switch that supplies 802.3af on the controller’s port will do. The link is 100Mbps at the ESP32 PHY and carries a handful of small messages per call, so throughput is irrelevant — this is a power and cabling decision, not a networking one.

One caveat on the 5-port UniFi Flex specifically: it is itself a PoE-powered device rather than a mains-powered switch. Port 1 is PoE in, ports 2–5 are PoE out, and its full 46W output budget is only available when it is fed from an 802.3bt source or the matching 60W injector. Fed from plain 802.3af it has very little to pass on. That is fine for one ESP32 drawing under 2W, but the injector is an extra part to buy and a second thing that can be misconfigured. A small mains-powered PoE switch avoids the dependency entirely, and the Linux box can then connect to the same switch on a non-PoE port.

## 9.10 MQTT Topic Structure

Moved to mqtt.md at Rev 3.34 — §3 for naming, §4 to §6 for the messages tabled by publisher, §7 for payloads. In summary, for a reader of this document: the ESP32 publishes ring and hook per station, seize, ring and fault per trunk; the audio program publishes peer and op per circuit from the detector of §8.7, and echoes what it has been commanded to do (play, tone, listen per circuit; monitor and test tone under audio/); the game program commands hook/set and ring/set to the ESP32, and play/set, listen/set, tone/set, audio/monitor/set, audio/monitor/source/set and audio/test/<ch>/set to the audio program (mqtt.md Rev 5 and Rev 13, audio.md). All under sbgame/.

## 9.11 Quality of Service and Retention

Moved to mqtt.md §2 at Rev 3.34: QoS 1 throughout, state retained and commands never, clean sessions, no toggles.

## 9.12 Failure Handling

Moved at Rev 3.34. The protocol — birth message and last will on ctl/status, the two heartbeats and why both are needed, the sync handshake — is mqtt.md §8. What the ESP32 does about each failure, including the full list of conditions on which every relay is released, is control.md §10. The broker security note is mqtt.md §9. What stays here is the hardware fact those sections rest on: nothing on the host can open a relay, so every failsafe has to be in the controller, and Rx02 (§5.2) is what holds the relays off before the controller is running at all.

# 10. Power

Each board generates its own low-voltage rails from a 24V bus using an on-board DC-DC converter. The ESP32 controller is powered separately from PoE and supplies nothing to the boards.

## 10.1 One Common Battery

This section is revised. Earlier revisions drew a hard line between the switchboard’s loop supply and a separate board supply and said the two must never be tied together. The trunk board design settles the question the other way: a single 24V supply feeds the trunk loops, the station and trunk board rails, the switchboard itself and the ring generator. That is what a real exchange does — common battery is the defining feature of the architecture the 551 was built for — and it removes the labelling hazard the old wording was written around, because there are no longer two 24V supplies to confuse.

What the earlier warning was actually guarding against remains prohibited and nothing here relaxes it:

—  Never derive board power from tip and ring. Tapping the pair would put a standing load on the loop that the switchboard reads as a supervision fault or a false answer, and would need 24 independent isolated converters since every station pair floats separately. Board power comes from the PSU terminals, never from a jack.

—  Never tap the board supply anywhere downstream of the PSU terminals. Common battery means common at one point, not common wherever two conductors happen to meet.

What does relax is the isolated DC-DC module the previous revision asked for. The non-isolated Traco or Murata part in §10.3 is now correct, on one condition: the 24V distribution must be a true star from the PSU terminals, with a separate pair to the switchboard, a separate pair to the ring generator and a separate pair to each interface board.

The condition is not decoration. Isolation was wanted to keep board logic ground off a conductor carrying loop current, and star wiring achieves that directly. Daisy-chaining does not. At 22 stations the station loops draw about 1.5A all-off-hook, and returning that through a shared conductor puts tens of millivolts between one board’s ground and the next — an offset that lands squarely on the I²C reference every expander shares. This was a minor concern when the boards drew 300mA between them and it is a real one at an amp.

## 10.1.1 System Supply

The station boards are a small part of the total load and do not size the supply; the station loops and the switchboard do. Sizing is worked in the trunk document, and the answer is a Mean Well LRS-150-24 (24V, 6.5A) rather than the LRS-35-24 named in earlier revisions, which is undersized by two to three times once station loop current is drawn from the same supply.

Two consequences land back on this board. First, set the LRS-150 output to 24.0V at the terminals under load rather than accepting the factory setting — its adjustment range is wide, and the relay coil margin in §5.4 is calculated against the 5V rail at its lower limit, so everything upstream feeds into it. Second, the LRS-150 has a 115V/230V input select switch where the LRS-35 had universal input; set it before first power-on.

## 10.2 Rail Budget

| **Rail** | **Per board** | **Notes** |
| --- | --- | --- |
| +24V BRD | ≈ 71mA | Board supply input. 1.45W out at ~85% efficiency. |
| +5V | ≈ 290mA | Relay coils 8 × 29.9mA = 239mA all-on, plus the 3.3V LDO input current. |
| +3.3V | ≈ 50mA | MCP23017 ~1mA, 8 × HCPL3700M at 4mA max when output low, output pull-ups ~6mA. |
| Loop current | ≈ 560mA | Not a board rail, but drawn from the same battery: 8 × 70mA through Rx03 with every station off-hook. See §10.1. |
| ESP32 controller | PoE, < 2W | Separate. Powers nothing but itself — see §9.8. |

 

Size for the all-on case, not a typical case. The whole point of the switchboard is that an operator can be working many circuits at once, and a supply that sags when the room gets busy presents as intermittent loop-current faults that are very hard to diagnose from the software side. Across three station boards and one trunk board that is 32 coils, roughly 957mA of 5V load and about 285mA on the 24V bus.

Rail tolerance matters more than the headline current here. The relay coil margin in §5.4 is calculated against the 5V rail at its lower limit, so a converter that sags under the all-on load eats directly into pull-in margin. Size for the all-on case and check the rail under it rather than assuming.

## 10.3 Converter Selection

A 3-pin SIP switching module in the 7805 footprint is the right answer here: no heatsink, no layout work, and roughly 90% efficiency instead of the 25% a linear part would manage dropping 24V to 5V. The Traco TSR 2-2450 (36V max input, 2A) or the Murata OKI-78SR-5/1.5-W36-C (36V max, 1.5A) both suit. Either gives four to five times the headroom needed.

Prefer a 36V-rated part over the common 28V-maximum modules such as the Recom R-78E5.0. A 24V rack supply sits within a few volts of 28V before you account for tolerance, load dump when eight relay coils release at once, or someone connecting a 24V supply that idles high. The margin is worth the small price difference.

Derive 3.3V with an LDO from the 5V rail rather than a second switcher. The load is about 50mA at a 1.7V drop, so dissipation is 85mW and almost any small LDO will do. An LDO also gives the logic rail good rejection of whatever the switcher is doing, which is worth having on the rail that feeds the ring detector outputs.

Note the package. SOT-223, specified through earlier revisions, is surface mount and sits oddly on a board that is otherwise entirely through-hole — the same objection that ruled out the SS34 for D101 and kept TVS101 on the SP721APP. The MCP1826S-3302E/AB in TO-220-3 is the through-hole variant and is what this design uses. Thermally it is enormous overkill for 85mW and that costs nothing; the price is board area, roughly 10 × 4.5mm plus height, one per board. Confirm the tab connection on the datasheet before layout — on most 3-pin TO-220 regulators it is common with the ground pin, which is harmless, but it is exposed metal near the 24V rail. The AMS1117-3.3 named as an alternative in earlier revisions exists only in SOT-223 and is dropped.

## 10.4 Capacitive Load at the Converter Output

One thing to fix from the previous revision. The Rev 3.1 BOM called for a 100µF electrolytic at each relay coil, which is 800µF of bulk on the 5V rail across eight stations. That was written for a linear regulator, which does not care. A switching module does: most SIP converters specify a maximum output capacitance, typically in the low hundreds of microfarads, and exceeding it can hold the output down during soft-start until the module current-limits and retries. The symptom is a board that fails to start, or starts intermittently, with nothing obviously wrong.

Reduce the per-relay capacitors to 10µF and fit a single 220µF bulk capacitor at the converter output. That is about 300µF total, which is inside the rating of the modules above, and it still gives each coil a local reservoir for its switching transient. Check the figure against the datasheet of whichever module is actually chosen rather than trusting the number here.

Specify that bulk capacitor at 25V, not the 10V of earlier revisions. On a 5V rail 10V is only 2:1 derating, which is the bare minimum for an electrolytic and buys nothing; 25V is 5:1, costs a millimetre or two of can diameter, and is the same voltage class as the rest of the low-voltage bulk on the board. Do not increase the capacitance to match — the total on that rail still has to stay inside the DC-DC module's output rating.

## 10.5 Input Protection

—  Fuse each board separately on its 24V input, 250mA slow-blow — Littelfuse 0218.250MXP in a 64900001039 PC-mount block. Four boards on one bus means a fault on one should not take down the rack, and a shorted relay driver is a plausible fault. With eight drivers per board that is the fault worth socketing for: a blown fuse should be a five-second swap, not a desoldering job.

—  Fit reverse-polarity protection as a shunt clamp rather than in series. D101 cathode to +24V BRD, anode to GND, reverse-biased and carrying nothing in normal operation. A screw terminal on a 24V bus will eventually be connected backwards; when it is, the diode conducts hard and blows F101, and the board sits at about −0.5V until it opens. F101 must be upstream of D101 — J103, then F101, then the clamp.

The fuse does open, and it is worth showing rather than assuming. The LRS-150-24 sources 6.5A before its own limiting acts, so a 250mA slow-blow on this board sees roughly twenty times its rating and opens in a few milliseconds. The 1N5822 is rated 80A non-repetitive for 8.3ms, an I²t of roughly 26A²s against the 0.25A²s of 5A for 10ms — two orders of magnitude of margin. If the diode does fail, it fails short, which is a dead short across a reversed supply and opens the fuse anyway. Both outcomes end the same way.

The earlier revisions of this section proposed a series Schottky and noted that its 0.4V was headroom the converter could spare. That was correct, and Rev 3.20's stated reason for preferring the clamp was not: it claimed Rx03's loop feed comes off the same rail and that the drop was therefore not free. Rx03 is in the tip-ring loop and is fed by the switchboard, so on this board the 0.4V genuinely was free. The clamp is still the right choice — it is the same arrangement as the trunk and generator boards, where the drop does cost something, and one reverse-polarity topology across three boards is worth more than a diode's forward voltage. A P-channel MOSFET is not worth considering either way.

—  Put 47µF at 50V plus 100nF at the converter input, close to the pins. The input loop of a buck converter is the noisiest current path on the board.

—  Distribute the 24V bus as a star from the PSU terminals. This is now a requirement rather than good practice — see §10.1. Daisy-chaining board to board puts station loop current through a shared ground conductor and offsets the I²C reference between expanders.

The converter and its input and output loops are the only switching-frequency noise source on an otherwise entirely passive board. Nothing in the audio path is conducted from these rails — the 5V rail reaches only relay coils and the 3.3V rail only logic — so the coupling risk is radiated, and the mitigation is layout. See §12.

## 10.6 Rail Capacitors — Review Findings

The rail capacitors were reviewed against the module and regulator datasheets rather than against habit. Three findings, one of which is a real omission.

The 47µF at the DC-DC input is required, not advisory. Traco's TSR 2 datasheet calls for an input capacitor of 22µF/50V for input voltages above 20VDC, to prevent damage at power-on, and repeats the requirement where the input is switched electromechanically. At 24V from a fused rail that is switched at the PSU, both conditions apply. The 47µF clears the requirement and the 100nF alongside it handles the high-frequency current the electrolytic cannot.

Confirm the capacitive-load limit before committing the 220µF at the converter output. These modules specify a maximum load capacitance, and exceeding it produces a start-up failure rather than an instability that shows on a scope — the board simply does not come up, with no symptom pointing at the cause. 220µF on a 2A part almost certainly has margin, but find the line in the datasheet rather than assume it; §10.4 already caps the total, and this is the number that cap has to respect.

The omission is at the LDO. The 3.3V rail has bulk at the regulator's output but nothing at its own input pin: the 220µF sits at the converter output, which may be an inch or more away with trace inductance in between, and an LDO wants local bulk at its own pins. Fit 10µF plus 100nF at U103's input — C105 and C106 — and add a 100nF ceramic, C108, at its output in parallel with the existing C107. A lone aluminium electrolytic has poor impedance exactly where the regulator's control loop needs it, and the MCP1826 is specified with a ceramic on the output.

These are parts already on the board in quantity — one more 10µF and two more 100nF per board — so nothing new is purchased.

## 10.7 Audio-Band Rail Bulk — Withdrawn

Rev 3.19 added a 1000µF electrolytic at the 24V board input on this board. Rev 3.23 deletes it. The reasoning given for it was wrong, and wrong in a way that matters more than the capacitor does.

The claim was that this board's loop feed is Rx03 and that audio-band current from every off-hook station therefore reaches the shared 24V rail through 330Ω, where the trunk board's current sources keep it out. That describes a board this one is not. Rx03 is a series resistor in the tip-ring loop, sitting behind the relay contacts between node A and node B — §5.1 and §7.2 are explicit about it. It is never connected to +24V BRD. Nothing in the line-side circuit is.

The architecture is the other way round from the trunk board, and this is the distinction to hold on to. The 551 switchboard supplies loop current to a station: this circuit presents itself as a subscriber station and closes the loop on command, exactly as §1 says. The trunk board is the opposite — there our circuit is the source of loop current and the switchboard is the load. So the trunk board's 24V rail carries loop current and its C13 has a real audio-band job; this board's 24V rail carries nothing but the DC-DC converters that make 5V for the relay coils and 3.3V for the logic.

With no loop current and no audio on the rail, there is nothing for a 1000µF electrolytic to do. It goes, for the same reason trunk Rev 5.23 withdrew the trunk board's per-strip 100µF: a capacitor whose purpose cannot be stated is a part fitted out of habit. (That part was fitted on the trunk board as built anyway, as Cx01, and does no harm — trunk §12.4.) The 47µF and 100nF at the DC-DC input stay — those are a datasheet requirement, see §10.6.

Worth stating what the loop current does come from, since §10.2 has caused confusion. It is drawn from the same battery — one LRS-150-24 feeds the whole system — but it reaches the station through the switchboard's own supply and its cord circuit, not through this board. That is why §10.2 counts 8 × 70mA in the system budget while this board's own rail budget is only the converters.

# 11. Bill of Materials (Per 8-Station Board)

| **Designator** | **Value / Part** | **Description / Notes** |
| --- | --- | --- |
| Dx01 ×8 | P6KE120CA | Bidirectional TVS, 102V standoff, 114–126V breakdown, 165V clamp; one per station jack. Formerly TVS1. |
| Rx06, Rx07 ×8 | 10kΩ, 0.5W (×2 in series) | Ring detector current-setting resistors, two per station. 1W preferred for sustained ring. Formerly R1a and R1b; the first schematic drew them as R14 and R15, since a KiCad reference is a letter prefix and a number. |
| Cx03 ×8 | 1µF, 250V film | Ring detector DC blocking capacitor — new in Rev 3.0, see §3.5. Formerly C4. |
| Rx12 ×8 | 4.7kΩ, 0.25W | HCPL3700M output pull-up to 3.3V. Formerly R2. |
| Cx04 ×8 | 0.1µF ceramic | HCPL3700M Vᴄᴄ bypass, pins 8–5, mounted at the device. Required. Formerly C5. |
| Ux01 ×8 | HCPL3700M (onsemi) | Threshold-sensing ring detect optocoupler, 8-pin PDIP. Replaces 4N35 + D1–D4. Formerly OC1. |
| Rx03 ×8 | 330Ω, 2W | Off-hook loop current limiting resistor (24V supply). Formerly R3. |
| Rx01 ×8 | 1kΩ, 0.25W | Qx01 base resistor. Formerly R4. |
| Qx01 ×8 | 2N2222A (TO-92, EBC) | NPN relay driver transistor. Formerly Q2. |
| Dx02 ×8 | 1N4148 | Relay flyback diode. Formerly D5. |
| Kx01 ×8 | CIT J104D2C5VDC.15S | DPDT (2 Form C) off-hook relay, 5V/167Ω/29.9mA coil, sealed THT. Both poles used — one per leg. 20-week factory lead time. 22 across the three boards — the tap and monitor strips on board 3 fit none — order the system quantity in one order, with the trunk board's 8 on top. Formerly RLY1. |
| Cx01 ×8 | 0.47µF, 250V film | Tx01 primary DC block and ring overlap protection. Formerly C3. |
| Tx01 ×8 | Triad TY-311P, 600Ω:600Ω | Audio isolation transformer. Needs usable response to ~9kHz only — see §7.5. Specialty wideband parts no longer required. Formerly T2. |
| Rx08, Rx09 ×8 | 1kΩ, 0.25W matched pair | Receive balanced output series resistors. Formerly R5, R6. |
| Rx10, Rx11 ×8 | 1kΩ, 0.25W matched pair | Transmit balanced input series resistors. Formerly R7, R8. |
| Rx04, Rx05 ×8 | 22kΩ, 0.25W 1% metal film matched pair | Operator tap series bridge resistors, bridging the Kx01 pole A and pole B NO contacts. Footprints on all eight strips; FIT ONLY on the designated tap strip (board 3 strip 7, A32 channel 23) — see §7.9. The tap needs no coupling capacitor of its own: Cx01 is already in series with the primary. The value generator §15.2 specified. Rev 3.24–3.26 substituted 22.1k on a mistaken claim that 22.0k is not stocked in 1% metal film; corrected at Rev 3.27. Yageo MFR-25FBF52-22K. Formerly R11, R12. |
| U101 | MCP23017-E/SP | I²C GPIO expander, 28-pin PDIP. Port A ring detect, Port B relay drive. Vᴅᴅ = 3.3V. Formerly U1. |
| C101 | 0.1µF ceramic | MCP23017 decoupling, at U101’s VDD pin. Formerly C6. |
| C107 | 10µF electrolytic | 3.3V rail bulk capacitor. Formerly C8. |
| Cx02 ×8 | 10µF electrolytic | Local 5V reservoir, one near each relay coil. Reduced from 100µF — see §10.4. Formerly C9. |
| U102 | Traco TSR 2-2450 | 24V→5V switching module, SIP-3 (7805 footprint). Murata OKI-78SR-5/1.5-W36-C equivalent. 36V input rating required. Formerly U3. |
| U103 | MCP1826S-3302E/AB | 3.3V LDO from the 5V rail, TO-220-3 through hole, 1A. ~50mA load, 85mW dissipation. DigiKey MCP1826S-3302E/AB-ND. NOT the SOT-223 suffix (E/DB) — this board is through-hole throughout. See §10.3. Formerly U4. |
| C102 | 47µF, 50V electrolytic | 24V input bulk, at the U102 pins. Formerly C10. |
| C103 | 0.1µF ceramic, 50V | 24V input decoupling, at the U102 pins. Formerly C11. |
| C104 | 220µF, 25V electrolytic | 5V output bulk at U102. Total output capacitance must stay inside the module rating. Formerly C12. |
| C105 | 10µF electrolytic | LDO input bulk, at U103’s own input pin rather than at the converter output. The distance between the two is trace inductance the regulator has to work through — §10.6. Formerly C15. |
| C106 | 0.1µF ceramic | LDO input decoupling, at U103’s input pin alongside C105 — §10.6. Formerly C16. |
| C108 | 0.1µF ceramic | LDO output ceramic, in parallel with C107 at U103’s output pin. The MCP1826 is specified with a ceramic on the output; a lone aluminium electrolytic has poor impedance exactly where the control loop needs it — §10.6. Formerly C17. |
| D101 | 1N5822 | Reverse-polarity protection on the 24V board input. SHUNT clamp: cathode to +24V BRD, anode to GND — not in series. Blows F101 on a reversed supply and costs no forward drop — see §10.5. Formerly D6. |
| F101 | 250mA slow-blow, 5x20mm — Littelfuse 0218.250MXP | Per-board fuse on the 24V board input. 250V, 5x20mm glass cartridge, socketed — see §10. F101 is the fuse and its holder together: a Littelfuse 64900001039, 649 series PC-mount 5x20mm block, 6.3A / 250VAC, solder lug, the same holder on all three board types. Formerly F1, with the holder as FH1. |
| J104, J105 | NorComp 182-025-213R561 | DB25 FEMALE, right-angle THT, gold, board lock, integral 4-40 female screwlocks on the mating side. Analog I/O to the A32, TASCAM analog pinout. Gender is female — see §7.6. 25-position receptacle, solder termination, nickel-plated steel shell, 5A per contact, PA9T dielectric, −55°C to +105°C. DigiKey 182-125FE-ND. Replaces the Amphenol ICC DBM25S500MN, which DigiKey does not stock. Screwlocks are part of the connector — no separate screwlock line item. The 182-025-213R531 is the same part with a plain threaded shell, about $1 cheaper, and needs two SFSO4401NR screwlocks each; that route saves nothing once the hardware is counted. Backset is 0.318 in (8.08mm), identical either way — confirm against the board edge before committing the footprint, particularly with two of these alongside the RJ45 jacks. Manufacturer lead time is 16 weeks despite stock, so order all six at once. Formerly J1, J2. |
| R105, R106 | 0Ω | D-Sub ground pins to board GND, one per DB25: R105 for J104, R106 for J105. **DO NOT FIT** — footprints only, unfitted on the rev 2 board; the D-Sub grounds float at the board — see §7.6. |
| J101, J102 | Amphenol ICC 87180-066LF | 6P6C modular jack, right angle, unshielded, THT. I²C in and out — two per station board, wired in parallel. Würth 615006138421 or Assmann A-2004-1-4-N-R equivalent. Pinout in §9.4. Formerly J3A, J3B. |
| J7A101, J7B101 | Amphenol ICC RJHSE5380 | RJ45 shielded right-angle jack, EMI finger, no LEDs or magnetics, gold 50µin. Station tip/ring, four stations per connector. Pinout in §7.7. 14-week factory lead time — buy spares in the first order. Confirm dielectric withstanding voltage from the Amphenol datasheet; the distributor attribute table lists none. Formerly J7A, J7B. |
| TVS101 | Littelfuse SP721APP, 3pF SCR/diode rail-clamp array | ESD and mis-plug protection on SDA and SCL. 8-PDIP through-hole, 6 inputs, 3pF per line. Rail clamp, not a fixed-breakdown TVS: V+ (pin 8) to +3.3V, V- (pin 4) to GND, SDA and SCL to two of the six inputs, four spare. Sacrificial after a mis-plug — keep spares and consider a socket, since it is a DIP anyway. See §7.8. Not optional now that RJ45 is on the board. Formerly TVS2. |
| — | 0.1µF ceramic, 50V | Bypass across TVS101, pin 8 (V+) to pin 4 (V−), at the device. **Not on the rev 2 board** — specified since Rev 3.26 and missed in the drawing; it waits for the next board revision (TODO.md). The SP721 clamps by conducting the transient from its IN pin into V+, so V+ must source that current locally or it lifts while the clamp is working. TVS101 sits at J101/J102 by design, away from U101 and the LDO, so C101 and C107 are too far to serve. Formerly C18. |
| J103 | 2-pin screw terminal | Board supply in: +24V BRD, GND. Star-wired from the PSU terminals — see §10.1. Formerly J5. |
| J106 | 2-pin screw terminal | MONITOR: the audience monitor output on board 3 strip 8’s transmit pair, pin 2 AOUT+_8 (hot), pin 1 AOUT−_8 (cold), at the J105 side of R910/R911. Fitted on every board; used on board 3 only — see §7.9.8. New on the rev 2 board. |
| SW101 | CTS 206-3ST | MCP23017 address strap A0–A2. SPST, 3 position, through hole, slide actuator, 2.54mm pitch in a DIP-6 footprint, 50mA / 24VDC. Top tape and bottom epoxy seal — worth the small premium over the unsealed 206-3, because this switch is set once and then left for years, and flux ingress presents later as an expander that intermittently vanishes from the bus. Not the right-angle variants (206-3RAS, 194-3MST, 195-3MSN); those actuate off the board edge. Formerly SW1. |
| Rx02 ×8 | 10kΩ, 0.25W | Qx01 base pulldown. Not optional — holds the driver off while Port B floats between reset and configuration. See §5.2. Formerly R_pd. |
| R102 | 10kΩ, 0.25W | /RESET pull-up to +3.3V, one per board. Fitted on every expander board — deliberately the opposite of the rule that leaves the bus pull-ups to the generator, and for the reason in §9.4. Required in the text since Rev 3.11; the designator is new in Rev 3.25. Formerly R18. |
| C109 (bodge) | 0.1µF ceramic, 50V | /RESET filter, U101 pin 18 to GND, at the pin. One per board. With R102 a 1ms time constant, so a spike coupled into the bus cord cannot reset the expander, while a deliberate reset — 2ms low, 5ms settle (control.md §6.2) — still works. Added at Rev 3.43 — see §9.4. Bodged onto the rev 2 boards; C109 is its designator at the next revision. Formerly C19. |
| R101, R103, R104 | 10kΩ, 0.25W | MCP23017 address bias: A0, A1, A2 to +3.3V, with SW101 closing each pin to ground. New in Rev 3.25. Without them the address pins are undefined with the switch open — see §9.2. Three per board. Formerly R19, R20, R21. |
| Cable — station lines | Cat5e, 300V (CM/CMR) | Voltage rating is not optional at 127V peak. Check the jacket print — patch cords are often marked 30V or 72V. |
| Cable — I²C | 4- or 6-conductor modular, STRAIGHT-THROUGH | Not a standard voice line cord — those are reversed and short the bus to ground. See §9.4. |

 

Three boards: 24 of each per-strip part and 3 × U101, less the parts §7.9.7 and §7.9.8 leave off the tap and monitor strips. No pull-ups on this board in either case — the single 2.2kΩ pair for the whole bus is on the ring generator board (its R1 and R2), and this board has no footprints for them.

# 12. PCB Layout Notes

—  Place the eight ring detector sections (Rx06/Rx07 pairs, Cx03, Ux01) along one board edge with clear physical separation from the logic section. Mark the high-voltage zone on silkscreen. Maintain 3mm creepage from ring detector traces to all logic traces, and route the isolation barrier as a continuous slot under each HCPL3700M body rather than relying on surface clearance alone.

—  Group each station’s relay, driver transistor and audio transformer together in a dedicated strip. With eight stations per board this repetition is the whole layout — get one station block right, then array it. Confirm the J104D package dimensions first: 2 Form C is an eight-pin footprint rather than the six the G5V-1 used, and the difference is multiplied by eight.

—  Both relay poles carry line voltage, so treat the whole relay except its coil pins as part of the high-voltage zone. Keep the coil and its driver on the logic side of the strip and route nothing at logic potential under the contact end of the package.

—  There is no transformer screen to ground. Revisions through Rev 3.24 asked for a star ground bringing each Tx01 shield to one chassis point; the TY-311P has no such terminal (§7.3). Keep the audio strip physically away from the expander and the relay bank instead, which is what that instruction was really buying, and treat §7.6’s D-Sub ground links, R105 and R106, as the one deliberate connection between the equipment side and board ground.

—  Decouple each MCP23017 with a 100nF ceramic from VDD to GND as close to the chip as possible, and each HCPL3700M with its required 100nF between pins 8 and 5. Add a 10µF bulk capacitor on the 3.3V rail, and a 100nF ceramic in parallel with it at the LDO output pin — see §10.6.

—  Place the LDO's own input bulk — 10µF and 100nF — at U103's input pin, not at the converter output. The distance between them is trace inductance the regulator has to work through.

—  There is no audio-band bulk on this board's 24V rail and none is needed — see §10.7. The rail feeds the DC-DC converters only; no loop current and no audio reach it.

—  Add a 10µF capacitor close to each relay coil on the 5V rail, with the 220µF bulk at the converter output rather than distributed. Eight coils is a meaningful switching load, but the total must stay inside the DC-DC module’s maximum output capacitance — see §10.4.

—  Place the DC-DC converter, its input capacitors and its output capacitor in one tight corner well away from the transformer strip and both D-Sub connectors, with a ground pour between. Its switching node and input loop are the only radiators on an otherwise passive board, and the audio lines are the only thing on the board that would care.

—  Keep the 24V board input entirely separate from the tip and ring traces — different connector, different side of the board, clearly labelled on the silkscreen. These are two unrelated 24V supplies and the consequence of bridging them is a switchboard that reads every station as off-hook.

—  Place the two DB25 connectors on the board edge with the eight balanced pairs routed as differential pairs with matched length. Keep them away from the relay bank and the ring detector strip.

—  Put J101 and J102 at the low-voltage edge alongside J104 and J105, and J7A101/J7B101 at the high-voltage edge with the ring detector strip. Mark the boundary on the silkscreen. The physical separation of the two connector classes is what makes the mis-plug case in §7.8 hard to reach by accident as well as electrically survivable.

—  Place TVS101 immediately at J101/J102 on the SDA and SCL traces, not near the expanders. It is protecting the whole bus from something arriving at the jack, so it needs to be the first thing that energy meets. Its 100nF bypass goes across TVS101 pins 8 and 4 at the device, in the same place — it is the local source for the clamp current and it does nothing anywhere else. The rev 2 board does not have it; the next revision must (§11).

—  Place Rx04 and Rx05 inside the per-station strip so the strip stays a single replicated block — they are unstuffed on seven strips out of eight and must not become a reason to hand-place one of them. Rx04 and Rx05 sit directly across the Kx01 pole A and pole B NO contacts, in the high-voltage zone with the same 3mm creepage as the ring detector section. They are placed on all eight strips because the strip is laid out once and replicated; a do-not-populate flag in the schematic does not remove a footprint from the board, so replication and correct stuffing are not in tension (§7.9.1). Mark them on silkscreen as tap-only: a strip with Rx04/Rx05 fitted AND Kx01 fitted leaves 22kΩ permanently bridging the contacts, which puts Cx01 and Tx01 partly on the line with the station on-hook. That is a wiring fault, and it is invisible once the board is in the rack.

—  The audience monitor output leaves on J106, a two-way terminal on strip 8’s transmit pair, J105 side of R910 and R911, at the low-voltage edge with J104 and J105 (§7.9.8). It is on the rev 2 board, as asked for here at Rev 3.40. It must not be RJ45 (§7.7) or 6P6C (§7.8), and it is neither.

# 13. Safety Notes

—  Ring voltage (90V AC, 20Hz) arrives from the switchboard on tip and ring when a station is being rung. Dx01 clamps the peak; Rx06, Rx07 and the HCPL3700M’s isolation prevent this voltage from reaching any logic. All components in the ring detector path must still be rated for the full peak ring voltage of approximately 127V, since the TVS does not suppress the ring signal itself.

—  The loop voltage from the switchboard (24V DC) is present on tip and ring whenever the station jack is connected. Relay contacts, Rx03, Cx03 and Tx01 primary must be rated accordingly. Note that Cx03 holds this voltage as a standing DC bias.

—  The HCPL3700M and the relay contacts together form the isolation barrier between the telephone line and the ESP32 logic. Both relay poles switch line conductors, so nothing on the relay is at logic potential except the coil. Verify the contact-to-contact and contact-to-coil isolation ratings from the relay datasheet before assembly; the optocoupler barrier is rated at 2500 V RMS minimum.

—  The A32 analog inputs and outputs are the second path into the equipment side. Tx01’s floating secondary is what keeps line voltage off the converter — confirm each transformer’s isolation before the D-Sub cables are connected.

—  One common 24V battery feeds the switchboard, both board types and all loops, so board ground and switchboard battery negative are the same node. Deriving board power from tip and ring is still prohibited — it places a permanent load on the loop that the switchboard reads as a supervision fault — and the 24V distribution must be a star from the PSU terminals. See §10.1.

—  Do not connect station boards to a live PSTN line. Designed for 551 switchboard connection only.
