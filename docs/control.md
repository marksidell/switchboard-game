**551 Switchboard Simulator**

**Controller Firmware**

*Rev 31 — Olimex ESP32-POE-ISO on the Ring Generator Board: Ring Waveform Generation by LEDC PWM, I²C Master for the Station and Trunk MCP23017 Expanders, MQTT Client to the Host, Relay Failsafes, Dial Pulse Detection on the Trunks, Switchboard Power Cut on GPIO15*

# 1. Overview

One microcontroller runs the whole system below the host: the Olimex ESP32-POE-ISO mounted on the ring generator board. It has three jobs, and the firmware is one program doing all three:

- **Ring generation.** Two LEDC PWM channels synthesise the 20Hz ring waveform into the H-bridge — generator §5, §8 and §12 for the hardware it drives. §5 below.

- **I²C master.** It reaches one MCP23017 on each station board and one on the trunk board over a daisy-chained bus, polls their inputs at 200Hz, and drives their relay outputs. That includes decoding the digits the operator dials on a seized trunk, from the loop-current interruptions the trunk board's seizure detector already reports. §6 to §8 below.

- **MQTT client.** It reports debounced hardware state to the host and acts on the game program's commands, over Ethernet with PoE from the same cable. The messages are specified in `mqtt.md`; what the firmware does with them is §9 below.

The board itself — pinout constraints, PoE budget, the level translation between its 3.3V GPIOs and the 5V gate drivers, the pull-downs that define every safe state before the firmware runs — is generator §3, §5 and §6. This document does not repeat the hardware; it says what the firmware does with it.

**Ownership.** The firmware is `control/control.ino` — the folder and file renamed from `ring/esp32.ino` on 2026-09-19, and that from `ring/ring.ino` on 2026-09-17, since it has been the whole controller and not the ring generator alone since Rev 4 — maintained through Claude Code and not through chat sessions (PROJECT_INDEX.md, *Firmware ownership*). This document is the specification the firmware is written to. When a revision here has a firmware consequence it says so, and the change is made on the Claude Code side.

**Build state as of Rev 8.** Everything in this document is written in `control/control.ino` and its `sb_*.cpp/h` modules: the ring waveform, SD sequence, GPIO4 enable, GPIO15 sync and peak-phase start (bench-run at generator Rev 52, 2026-09-16), and as of 2026-09-17 Ethernet, the I²C scan, expander polling, relay control, the MQTT client, the trunk state machine and dial pulse detection. The source was reviewed against Rev 6 on 2026-09-18 (§1.7) and the reviewed fixes were confirmed in the source on 2026-09-19: the spread republish, strict `on`/`off` payloads, `seize` kept in RING_ON_TRUNK, `ring/set` dropped outside IDLE, the header and comments brought current. The duty tables are in the §3 form for the 74HCT04 — direct duty, park at 0 — and the source says not to run that build on a board still carrying the 74HCT02. There is no arming gate as of Rev 11 (§1.11), and so no bench build: the one build runs the generator with or without boards on the chain. The station and trunk boards themselves are not yet built, so none of the expander-side code has run against hardware; §11 lists what is still to be verified. Rev 10's channel-table change (§1.10) is a code consequence not yet in the source.

## 1.1 Changes in Rev 1

— New document. The firmware behaviour had been specified in pieces across the three circuit documents: ring generation in generator §6 and §12, expander polling and ring debounce in station §3.7 and §9.6, the trunk state machine, debounce and cadence in trunk §7.5, §7.6 and §11, and the MQTT failsafes in station §9.12 and trunk §11.4. Each was written from that board's point of view, and nothing stated the controller's behaviour as one thing — the order of the startup sequence across all three jobs, or the full list of conditions on which relays are released. Those sections are replaced by pointers here; their change lists carry the history.

— Nothing in the firmware's specified behaviour changes in the move. Two things are stated here for the first time because assembling the pieces exposed them: the complete failsafe table in §10, and the startup order in §4.2, which generator §6.1 gave for the ring generator alone and which now has the I²C scan and the MQTT connection in it.

## 1.2 Changes in Rev 2

— Dial pulse detection added, §8.2. The operator dials outgoing calls on a seized trunk with a rotary dial, and the dial interrupts the loop once per pulse. The trunk board's seizure detector sees each interruption as loop current stopping (trunk §4), so the pulses arrive on SEIZE_n with no hardware change; the firmware counts them and publishes each completed digit on sbgame/trunk/<n>/digit (mqtt.md §4). Rev 1's release rule — declare the trunk released after 25ms open — would have read every pulse as a release, so the release threshold rises to 250ms and the seizure logic becomes the three-way classifier of §8.1: pulse, digit gap, release.

— The accidental-ring discriminator changes with it. Rev 1 recognised ring from the switchboard as four or more transitions in 150ms, which a dial at the top of its speed range can also produce. Ring and dial are now separated on the interval between successive breaks — about 50ms for 20Hz ring against 67–125ms for an 8–15 pps dial — which is what actually differs between them. §8.1.

— Standard dial pulse timing is recorded in §8.2 so the thresholds can be checked against it and re-derived if a dial outside Bell System practice is ever connected.

## 1.3 Changes in Rev 3

— Follows station Rev 3.35: three station boards are built and the operator tap is station 24, board 3 strip 8. The scan list is 0x20–0x23 with nothing conditional (§4.2); the tap note in §6.1 moves from board 1 bit 7 to board 3 bit 7; stations are 1–23 and no station/24 topic is published.

## 1.4 Changes in Rev 4

— Written against the firmware, which now implements the whole document. Four decisions the implementation had to make where the specification was silent or too loose are adopted here, with the reasoning: ring-on-trunk is recognised from SEIZED as well as IDLE (§8.3), because a 20Hz break train inside a seizure would otherwise be counted as dial pulses; ring is declared on two consecutive ≤ 60ms break-to-break intervals rather than one (§8.1, §8.2), because at 5ms sampling a single interval sits one sample clear of a 15 pps dial; the 30s ring timeout runs from the first relay energisation rather than from ring/set (§8.5), so a trunk queued behind the concurrent-ring cap still gets a full cadence; and a bus fault is three consecutive I²C errors on one device, not one (§6.2, §10), because a single NAK on six feet of daisy-chained 6P6C is a glitch.

— The MQTT client library is chosen: MQTT 2.5.3 by Joël Gähwiler (256dpi/arduino-mqtt). It supports QoS 1 and sends its keepalive ping from `loop()`, so a wedged main loop stops the ping and the broker's LWT fires — the case mqtt.md §8.2 treats as client-dependent falls on the safe side. §9.1.

— The boot-time I²C scan result is published on sbgame/ctl/i2c (mqtt.md §4): `"ok"` or `"missing: 0x22 0x23"`, retained. §4.2 step 5.

— §2 corrected: the firmware requires Arduino core 3.x and refuses to build on 2.x (`#error`), since the 2.x LEDC path was removed. Rev 1 to Rev 3 said it built on both.

— The build-state paragraph in §1 and the open items in §11 are brought up to date; `ring_start_phase_task.md` is deleted from the project.

## 1.5 Changes in Rev 5

— Two Rev 4 slips, found by the firmware author. §4.2 had the scan result published at step 5, before MQTT connects at step 7; it is published at step 7, and on every reconnect and rescan. §8.3’s state-machine sketch still said one ≤ 60ms break interval where §8.1 and §8.2 say two consecutive; now consistent.

— §9.4 is explicit that the firmware drops a command for a circuit on a missing board regardless of ctl/i2c. A game program that reads ctl/i2c and does not send is cleaner, but the firmware does not depend on it doing so.

## 1.6 Changes in Rev 6

— The firmware file is `control/control.ino`, renamed from `ring/ring.ino` on 2026-09-17 on the Claude Code side. The old name dated from when the file was the ring generator's PWM sketch and nothing else; since Rev 4 it has been the whole controller. §1 follows. Earlier change entries here and in the other documents keep the old name as history. No behaviour changes.

— mqtt.md Rev 5 makes the audio program a commanded client, with `play/set`, `listen/set` and `tone/set` under the same `station/<n>/` and `trunk/<n>/` roots as `hook/set` and `ring/set`, and asks that this firmware subscribe to its two commands by name and not by a wildcard over every `set`. §9.1 has specified `sbgame/station/+/hook/set` and `sbgame/trunk/+/ring/set` since Rev 4, so the specification already meets it; the check that the source does likewise is on the Claude Code side and is the one firmware item mqtt.md Rev 5 raises.

## 1.7 Changes in Rev 7

— Written against the firmware source as reviewed on 2026-09-18 (`control.ino`, `sb_config.h`, `sb_table`, `sb_expander`, `sb_station`, `sb_trunk`, `sb_net`). The source meets §4 to §10 as written, and the §11 item to confirm the by-name subscriptions in the source is closed: they are exactly the four patterns of §9.1. Six decisions the implementation made where the specification was silent are adopted here, with the reasoning, and three items go back to Claude Code as code consequences.

— **Adopted.** (1) The MCP23017 driver is written against the registers and not over a library, §6.1: the Adafruit library exposes no way to write IPOL, and a driver whose read returns 0 on a bus failure cannot tell that from eight idle inputs. (2) The channel table gives every circuit a row and the operator tap bit none, so the tap is never polled, published or commanded, §6.1 — a cleaner statement of "leave the mapping alone". (3) The echoed `hook` and `ring` state is the commanded state, published at command time; the relay write and read-back follow at the next flush, and a relay that does not take is corrected by the bus-fault path, §7.2. (4) `bad_dial` for a break outside the pulse window is published when the digit ends, not when the break happens, and a spoiled digit abandoned by a release publishes nothing, §8.2 — one message per digit, none for a digit that was going to be abandoned anyway. (5) After a bus-fault recovery an expander that is still absent is not retried, §6.2: a retry means another /RESET, which drops every relay on the chain. (6) A reconnect attempt blocks the main loop for the TCP connect timeout plus the CONNACK wait, which can be seconds, §9.1; that is acceptable only because the MQTT-loss failsafe has already released every relay before the first retry, and that dependency is now written down.

— **Two behaviours settled by Mark and by this revision, not by the source.** RING_ON_TRUNK entered from SEIZED keeps `seize` = `"on"`, §8.3; the source published `"off"`, which a game program reading `seize` as the call's existence would take as a release and tear the call down for an operator's slip. `fault` carries the news; `seize` reports the loop. And `ring/set "on"` is acted on in IDLE only and is a no-op in RINGING; in SEIZED or RING_ON_TRUNK it is dropped with a log line and the echo stays `"off"`, §8.3. The source dropped it in SEIZED and queued it in RING_ON_TRUNK to fire when the pattern stopped; a request that fires seconds later, after the operator has finished with the trunk, is a command the game did not mean at that moment. The game re-issues if it still wants it.

— **Code consequences, for Claude Code.** (a) The full-state republish — reconnect, `ctl/sync` and the 30s timer — is 70 QoS 1 messages, and in MQTT 2.5.3 a QoS 1 publish blocks until its PUBACK. The burst holds the 200Hz loop for something like 100–300ms on a LAN, during which a ringing station's 100ms quiet rule fires and a digit under way has the stall added to a break or make interval. §9.2 now requires the republish to be spread one circuit per poll tick. Measure the maximum loop-tick length first so the fix is sized to a number. (b) Any `hook/set` or `ring/set` payload other than `"on"` is treated as `"off"`; §9.4 now requires `"on"` and `"off"` to be accepted and anything else logged and dropped. (c) The two behaviours above: keep `seize` on in RING_ON_TRUNK from SEIZED; drop `ring/set "on"` in RING_ON_TRUNK as in SEIZED. Also: the `control.ino` header says "Implements control.md Rev 2", cites the `.docx` generator revision and carries a "WHAT IT DOES NOT DO" block that the code contradicts — bring it to this revision and delete the block; `sb_config.h` and `sb_table.cpp` claim §6.1 puts the tap on board 1 and mqtt.md says stations 1–24, both stale since Rev 3; `sb_table.h` says twenty-four stations and rows 0..23/24..31 where there are 23 and 31 rows; `sb_expander.cpp` says §10 gives no error count where §6.2 and §10 both say three; the "section 4.5" in the arm-refused message is the old `.docx` numbering. `BENCH_ALLOW_MISSING_EXPANDERS` should default to `false` with the bench build setting it, so a fresh checkout is safe. The duty tables and both park writes go to the 74HCT04 form of §3 — direct duty, park at 0 — in one commit.

## 1.8 Changes in Rev 8

— Build state only. The Rev 7 §1.7 code consequences are in the source as of 2026-09-19 and were checked in chat: the republish walks one circuit per 5ms tick from a single row counter shared by the reconnect, `ctl/sync`, timer and failsafe paths; payloads other than `"on"` and `"off"` are logged and dropped; a trunk carries its own `seize_on` flag so RING_ON_TRUNK reports the seizure it was entered with; `ring/set "on"` is a no-op in RINGING and dropped with a log line in SEIZED and RING_ON_TRUNK. The console banner now reports the longest loop pass and the longest poll gap since it was last printed, which is the §11 measurement. The arming-gate bypass became a build option rather than a constant, so the departure cannot be committed by accident; §1 says so. The Rev 7 §11 pre-chain item is reduced to what is left: build without the bench option, and read the banner's loop timing with the broker up.

## 1.9 Changes in Rev 9

— Rename only. This document is `control.md`, from `esp32.md`, and the firmware is `control/control.ino`, from `ring/esp32.ino` — both on 2026-09-19, Claude Code and Mark. The `esp32` name said which chip; `control` says what the program is, and it is the name the folder now carries. `ESP32` stays wherever it means the chip or the Olimex board, and `sbgame-esp32` stays as the MQTT client id — that is on the wire and nothing asked for it to move. Every cross-reference in the other documents follows at their next revision (station 3.39, trunk 5.38, generator 61, mqtt 7, audio 5, PROJECT_INDEX). Earlier change entries here and elsewhere now read `control.md` and `control/control.ino` where they said `esp32.md` and `ring/esp32.ino`, so that a reference followed from an old entry lands; the `ring/ring.ino` name in the oldest entries is kept as history, since nothing points at it. No behaviour changes.

## 1.10 Changes in Rev 10

— Follows station Rev 3.40. Stations are 1–22: the operator tap moves from board 3 strip 8 to strip 7, and strip 8 carries the audience monitor output on A32 channel 24 with nothing fitted on its line side. §6.1 now names both strips and both unmapped bits. §9.2's counts follow: a full republish is 68 messages, where Rev 7 to Rev 9 said 70, and the round-robin is over 30 circuits, about 150ms, where they said 31 and 155ms. The Rev 3 and Rev 7 entries keep their figures as history.

— Firmware consequence, for Claude Code: the channel table in `sb_table.cpp` / `sb_table.h` loses the station 23 row (board 3, address 0x22, bit 6), leaving 22 station rows and 8 trunk rows, 30 in all, and any constant or comment that counts stations (`sb_config.h`) goes from 23 to 22. No other behaviour changes.

## 1.11 Changes in Rev 11

— The arming gate is removed (Mark, 2026-09-25). §4.2 step 8 said not to arm the H-bridge while a configured expander was absent, on the reasoning that the generator would be feeding a ring bus whose relays the firmware could not see or release. That reasoning does not hold for this hardware. Ring reaches a circuit through the trunk board's ring relays alone, and they are normally open: with their expander absent or unconfigured, R_pd holds every driver off and every relay released (§4.1), so the bus goes nowhere. The station boards take no ring from the bus. The switchboard's own ring supply on generator J6 was never switched by any relay the firmware drives, so the gate never protected it either. What the gate did do was refuse to run the generator on a board with nothing on the chain, which is the configuration the generator is brought up and characterised in.

— §4.2 loses step 8 and its later steps renumber, 8 to 11; §4.3's reference follows. §6.2's note that the bridge stays armed through a recovery now rests on this rather than on the gate being a boot check. §10's row for an expander absent at boot becomes report-only. §11 loses the pre-chain item to build without the bench option. The scan is unchanged and still published on `ctl/i2c`. Generator §6's Rev 56 pointers name the gate as what moved here; they are history and are left.

— Firmware consequence, for Claude Code, made in the same commit: `startWaveform()` no longer refuses on a missing expander; `slavesPresent()`, the banner's arming-gate line, the boot-time `ARM INHIBITED` message and the `BENCH_ALLOW_MISSING_EXPANDERS` build option are removed. `CLAUDE.md` and `TODO.md` lose the bench build.

## 1.12 Changes in Rev 12

— Bench record only. The §5.3 start-phase verification is made on the Antek, and §5.3 records it; §11 loses the item. No behaviour changes.

## 1.13 Changes in Rev 13

— Follows generator Rev 65. GPIO36 is the operator's Next Call button, an optoisolator pulling the pin low against the Olimex's own 10k pull-up; §3 lists it. What the firmware does with it — debounce, the press event and its MQTT topic — is not yet specified, and §11 carries it as an open item. No firmware consequence until it is.

## 1.14 Changes in Rev 14

— Follows generator Rev 68, which brings that document into line with the board as built. Nothing the firmware does changes; the names it uses for the hardware do. §3: GPIO32 (PWM A) reaches IN2 and the right leg, U5, through 74HCT04 gates 2 and 5; GPIO33 (PWM B) reaches IN1 and the left leg, U4, through gates 1 and 6; SD goes through gates 3 and 4. The enable and sync header is J1 (pin 1 GPIO4, pins 2 and 3 GND, pin 4 GPIO15), not J9; the drive monitor is J3, not J10; the Antek's output terminal is J6, not J8. §4.1: R_SD_PD2 is not fitted, and the low-side gate pull-downs are R_GS2 and R_GS4. §5.2 says which leg the positive half-cycle drives on this board.

— Firmware consequence, for Claude Code, made in the same commit: the pin comments in `control.ino` and the two banner lines that name J9 now name J1 and its pins. Comments and strings only.

## 1.15 Changes in Rev 15

— Firmware updates over the network (§2.1), so that the installed board can be reflashed without a USB cable. A cable left attached would join portland's ground to the system's 24V ground, which PoE's isolation keeps apart, and anything that opened the port would reset the board; Mark weighed powering the Olimex from USB and chose to stay on PoE (with a TL-SG105PE PoE switch in place of a separate injector) and update over the network instead. The generator §3.4 recommendation to prefer OTA in the installed system is now something the firmware can do.

— Firmware consequence, for Claude Code, made in the same commit: ArduinoOTA started once Ethernet has an address, with the hostname `sbgame-esp32` and a SHA-256 password hash from `secrets.h` (`OTA_PASSWORD_SHA256`; without it the firmware builds with OTA off). The start callback stops the waveform and releases every relay before anything is written to flash; an error after that point restarts the board. §10 gains the row.

## 1.31 Changes in Rev 31

— GPIO15 cuts the switchboard's 24V for 1s on command (§3, §5.4, §9.4), Mark's request, 2026-10-19, and the waveform sync it carried is withdrawn. A trunk rung in locks its lamp and buzzer on the switchboard until a cord goes into the jack: the 551 holds the signal on its own battery, so releasing our ring relay does not clear it, and nothing else did. A relay in the switchboard's leg of the supply star, normally closed, opens while GPIO15 is high (generator §7.8, Rev 75), and every relay and lamp on the switchboard drops. The game program sends it when a game stops (game_control.md Rev 63), and the Stream Deck can send it by hand.

— Active high. GPIO15 idles low and is driven high to cut. The Olimex pulls GPIO15 up with 10kΩ (Olimex's ESP32-POE pinout, from Mark, 2026-10-19), so through a reset, before `setup()` claims the pin, it would sit high; the driver's 470Ω base pull-down against the 1kΩ base resistor holds it to about 0.4V there, and the transistor's base to about 0.13V, so the relay stays released (generator §7.8). An active-low drive through an optoisolator was drafted first, on the guess that the pull-up might be 2.2kΩ, and needs +3.3V, which J1 does not carry; the pinout made it unnecessary.

— `ctl/power_cut/set` `"on"` starts the cut and `"off"` ends it early; `ctl/power_cut` echoes `"on"` and `"off"` (mqtt.md Rev 37). The cut ends by itself after `POWER_CUT_MS`; a second `"on"` during it is ignored. Every failsafe of §10 ends it too: power restored is the safe state.

— **Wire the relay only after this firmware is running.** Rev 30 and earlier drive GPIO15 as a 20Hz square wave while the generator runs, which would chatter the switchboard's supply.

— Firmware consequence, for Claude Code: `PIN_SYNC` and its writes in the step ISR, in §4.3 and in the banner come out; `PIN_POWER_CUT` 15, claimed low in `setup()`; `POWER_CUT_MS` 1000 in `sb_config.h`; subscribe to `ctl/power_cut/set`; publish `ctl/power_cut` with the birth message and on change; end the cut in every §10 release. FIRMWARE_SPEC_REV 31.

## 1.30 Changes in Rev 30

— `shortring/set`'s burst is 1s, not 0.5s (§8.3, §8.4), Mark's finding on the switchboard, 2026-10-10: ringing each of the 551's trunk jacks in turn, one did not latch its trunk signal on 0.5s of ring. The answer is still readable from the moment the burst ends; the operator cannot plug in before it does in practice.

— Firmware consequence, for Claude Code, made in the same commit: `SHORT_RING_MS` 1000 in `sb_config.h`. FIRMWARE_SPEC_REV 30.

## 1.29 Changes in Rev 29

— The serial banner is printed for Enter only — CR or LF — and at most once every 2s; every other byte on the line is discarded. The receive pin is pulled up. Found on the bench, 2026-10-10, and the cause of the stalls of Rev 27 and of 2026-10-09: with the USB cable unplugged, the board's USB-serial chip is unpowered and the receive line floats, and noise on it read as keypresses. Each printed the banner, about 100ms of blocking output, so the loop stalled tens of milliseconds at a time: the controller acknowledged commands 2–92ms late (network capture) and the station dial's breaks stretched from 61ms to about 118ms, so every digit of the board test was refused as `bad_dial`. With the cable plugged in, the line is driven idle and the controller answered in 4ms and dialled true. A reset did not help, which ruled out the power-on boot; the cable did. The installed controller runs without the cable (§2.1), so this was its normal state.

— Rev 28's log line for each trunk state change is removed; the log of a state publish that fails or is skipped stays.

— Firmware consequence, for Claude Code, made in commit 7d0ad22: `loop()` in `control.ino` looks for CR or LF and rate-limits the banner to `BANNER_MIN_MS` (2000); `setup()` enables the pull-up on GPIO3 (U0RXD) after `Serial.begin()`. FIRMWARE_SPEC_REV 29.

## 1.28 Changes in Rev 28

— Diagnostics only. A state publish that does not reach the broker is logged on the serial console, with the topic, the payload and the client's error, as is one skipped because the client is not connected; and each trunk's `seize`, `ring` and `fault` change is logged as it is published. Found on the bench, 2026-10-09, with trunk 1 through the switchboard: a cord plugged in or pulled out produced the `fault` message at once, but its `seize` change arrived only with the next 30s republish (§9.2), and no non-empty `fault` arrived at all, while the heartbeat came every second and the broker logged nothing. In a game the program would wait up to 30s to see the operator answer.

— Firmware consequence, for Claude Code, made in the same commit: `netPublishState()` in `sb_net.cpp` checks `publish()`'s result and logs `lastError()`; `publishBoolIfChanged()` and `setFault()` in `sb_trunk.cpp` log the change. FIRMWARE_SPEC_REV 28.

## 1.27 Changes in Rev 27

— Diagnostics only: the banner lists every gap between poll ticks of 20ms or more since it last printed, each with how long ago it was, its length, the number of loop passes in it, the section that took longest in it and for how long, and the time no section accounts for (§11). Found on the bench, 2026-10-09: after an unplanned outage the controller came back stalling for about 100ms at a time — commands echoed 108–139ms late and the station dial's breaks stretched to 88–122ms, outside §8.2's window — until a reset cleared it; and even healthy, the banner reported an 81ms poll gap when its longest pass was 13ms, so most of that gap ran in no timed section. One such gap was the banner itself, which printed after the pass timing and so landed between ticks unmeasured. The gaps are kept in a buffer of sixteen and printed with the banner, not as they happen, because a line on the serial port blocks for longer than the gaps being looked for. The enable check, the ctl/i2c publish on reconnect and the banner's own printing are now timed sections, so the banner's stall shows as the first gap, under "serial".

— Firmware consequence, for Claude Code, made in the same commit: in `control.ino`, `TIMED` also accumulates each section's time since the last poll tick; the tick computes the gap and, at 20ms or more, records it with the largest section and the untimed remainder; `printBanner()` prints and clears the buffer. Sections `enable`, `scan` and `serial` added. FIRMWARE_SPEC_REV 27.

## 1.26 Changes in Rev 26

— Bench record only: dial pulse timing and contact bounce through the real 551 cord circuit and dial, measured 2026-10-05 (§8.2, §11). The operator seized trunk 1 with a cord and dialled 0, 1, 2, 3 on the switchboard's dial; loop current was recorded across the trunk's sense resistor (R206) with an Analog Discovery 3 at 50kHz for 45s, upstream of the seizure detector, so the figures are the dial's own and not the detector's.

| **Digit** | **Pulses** | **Break** | **Make** | **Rate** | **Make before the next digit** |
| --- | --- | --- | --- | --- | --- |
| 0 | 10 | 68.7–76.0ms | 37.0–40.2ms | 9.2pps | 1.56s |
| 1 | 1 | 81.5ms | — | — | 1.34s |
| 2 | 2 | 76.6–76.7ms | 41.6ms | 8.5pps | 1.29s |
| 3 | 3 | 76.3–78.2ms | 41.5–41.8ms | 8.4pps | — |

Every break is inside §8.2's 25–100ms window, the longest with 18.5ms to spare; every make is far below the 200ms end of digit and every inter-digit make far above it. The dial runs a little slow, 8.4–9.2pps against 10 nominal, and a little long on break, 64–68%, both inside what §8.2 accepts. Bounce is at the start of each break only: an open of up to about 3ms, then the contacts close again for 0.34–0.96ms, then stay open; 18 such re-closes in 16 breaks, and none inside any make. The longest, 0.96ms, is a fifth of one 5ms sample, so the Rev 24 glitch filter rejects it with margin, and no firmware change follows. A 12V spike across the sense resistor about 1.5s after the last digit was the operator throwing the key that takes the dial off the trunk, not the dial.

— The firmware's own decode of these digits could not be checked in the same run: trunk 1 still carried the Rev 5.40 seizure detector values, which hold the HCPL3700M inside its hysteresis band (trunk Rev 5.41), and the controller published no digits. That check waits on the Rev 5.41 resistors.

## 1.25 Changes in Rev 25

— A second ring command, `trunk/<n>/shortring/set` (§8.3, §8.4, §9.4; mqtt.md Rev 26), Mark's request, 2026-10-05. `"on"` rings the trunk once, for 0.5s, and returns it to IDLE; `"off"` cancels a burst that has not finished. The trunk cannot see a seizure while its ring relay is energised, because pole 2 lifts the return off R_LOOP (trunk §4.3), so under the cadence an operator who answered during the 2s on phase was not seen until the off phase began. The 551's trunk signal is a latching relay that one short burst of ring is enough to operate, so a single burst signals the call and leaves the trunk readable from the moment it ends, which is when the operator can first plug in. The same phase rules and the same concurrent-ring cap apply as for `ring/set`: acted on in IDLE only, a no-op while RINGING, dropped with a log line in SEIZED or RING_ON_TRUNK, queued behind the cap. `ring/set` keeps the cadence, and `ring/set "off"` also cancels a short burst. The `ring` echo goes `"on"` for the burst and `"off"` after it.

— Firmware consequence, for Claude Code, made in the same commit: `trunkShortRing()` beside `trunkSetRing()` in `sb_trunk.cpp`, both through one `requestRing()`; a `short_burst` flag on the trunk ends RINGING after `SHORT_RING_MS` (500) and rebaselines the seizure input as at the start of an off phase; `shortring/set` is subscribed and queued like `ring/set` in `sb_net.cpp`. FIRMWARE_SPEC_REV 25.

## 1.24 Changes in Rev 24

— A change of level on SEIZE_n is accepted only when two consecutive samples agree on it (§8.1). Found in review of trunk Rev 5.41, 2026-10-05: the resized detector drives the HCPL3700M well past its threshold, so it now follows every bounce of the switchboard's dial contacts, which the input sitting near its threshold had partly hidden. The input is sampled every 5ms with nothing in between, and one sample caught inside a bounce is a break shorter than 25ms in a digit — spoiling it with `bad_dial` — or a make that splits a break in two. Bounce lasts a few milliseconds, so it can disagree with the settled level in one sample at most, and a two-sample rule drops it. The accepted edge is timed from the first of the two samples, so both edges of a pulse move by the same amount and every interval in §8.1 and §8.2 keeps its length; the cost is 5ms of latency on each edge, nothing against a 100ms seizure test or a 25ms shortest break. Ring applied from the switchboard alternates at about 25ms on and 25ms off, five samples a side, and passes unchanged. The dial bounce itself is still to be measured on the bench, through the real cord circuit (§11).

— Firmware consequence, for Claude Code, made in the same commit: `trunkPoll()` in `sb_trunk.cpp` holds a candidate level and its time, accepts it on the second agreeing sample, and stamps the edge — `level_since` and the break-to-break time — from the candidate. The state machine reads the filtered level. FIRMWARE_SPEC_REV 24.

## 1.23 Changes in Rev 23

— A break of 100–250ms spoils the digit it falls in even when it comes before the digit's first counted pulse (§8.2). Found on the bench, 2026-10-03, with the serial console attached through a board test: a station dialled 4, the trunk missed the make after the first pulse, logged a 177ms break as neither pulse nor release, and published `"2"`; a station dialling 2 lost the same make and published nothing, and its `bad_dial` never came. Rev 7 spoiled a digit only on a bad break *inside* it, meaning after a pulse had been counted, so a lost make between the first two pulses left the remainder to be counted as a shorter, valid digit — a wrong number, with no fault. A break of that length in SEIZED can only be pulses run together, so it now opens a digit already spoiled, which ends in `bad_dial` at the 200ms make like any other. A break under 25ms before the first pulse is still only logged: it is a glitch, not a lost pulse, and a seized trunk sitting idle should not report a fault for it.

— Firmware consequence, for Claude Code, made in the same commit: `classifyBreak()` in `sb_trunk.cpp` sets `in_digit` and `digit_spoiled` on a 100–250ms break whatever came before it. FIRMWARE_SPEC_REV 23.

## 1.22 Changes in Rev 22

— Commands are acted on after the MQTT client's loop returns, never inside it (§9.4). Found on the bench, 2026-10-03, with the serial console attached through a board test: the controller closed its own broker connection four times in 88s, each time after a stall of up to 939ms in the network step, and each loss released every relay. A command's handler publishes its echo at QoS 1, and the client library calls the handler from inside its own loop; the nested publish read the socket for its PUBACK, consumed bytes the outer loop had already counted as available, and the outer read then waited out the library's 1s timeout and closed the connection. The more commands arrive, the more often it happens — the board test sends one every few hundred milliseconds. This accounts for the seizures still dropped part-way through dialling after Rev 21, a 61ms break measured as 175ms, and other circuits changing state while one pair was under test.

— Firmware consequence, for Claude Code, made the same day: `onMessage` records a `hook/set`, `dial/set` or `ring/set` in a queue of sixty-four — a game stop releases thirty circuits in one read, and the first bench build, with sixteen, dropped two of the board test's cleanup commands and `netService` acts on them once `mqtt.loop()` has returned; a full queue drops the command with a log line. The game heartbeat and `ctl/sync` were already only recorded. FIRMWARE_SPEC_REV 22.

## 1.21 Changes in Rev 21

— Elapsed times no longer wrap. Found on the bench, 2026-10-03, with station 4 dialling for the scope: the serial console logged "game heartbeat missed twice", every relay released, and "game heartbeat returned" 10ms later — every second, while the game's heartbeats left the broker evenly a second apart. The loop reads the clock once a pass; a message handled in that pass's network step is stamped with a later reading, and `now - then` on unsigned milliseconds turned that small negative age into four billion. The heartbeat read as two seconds late and the failsafe fired. The same trap was set for a ring started by `ring/set` — its 30s hard timeout and its cadence step could fire on the next pass — and for the dial's interval. This accounts for the seizures dropped part-way through dialling, the relays that did not echo and, perhaps, the stations that heard no ring; the board test is rerun on this firmware before the boards are blamed.

— Every elapsed time is now taken as a signed difference, and a stamp later than the pass's clock reads as no time elapsed.

— Firmware consequence, for Claude Code, made the same day: `elapsedMs()` in `sb_config.h`, used by the trunk ring timing, cadence and dial detection and the station ring detector; the game-heartbeat age compared signed. FIRMWARE_SPEC_REV 21.

## 1.20 Changes in Rev 20

— The 200Hz loop no longer stalls, found on the bench 2026-10-03 with station board 1 and the trunk board wired together. The banner showed passes of 130ms against the 5ms nominal, long enough to swallow dial pulses — no trunk decoded a digit — and to drop seizures and miss ring. Three causes, all fixed:

— **Nagle on the broker connection.** Every QoS 1 publish waits for its PUBACK (§9.2), and with Nagle on, the small packets met the broker's delayed ACK: about 40ms a message, so a station's three-message republish tick took 90ms and each heartbeat 39ms. The socket is now TCP_NODELAY (§9.1); they take 8ms and 3.5ms.

— **One absent board probed per retry**, in turn (§6.2), not every absent board at once, and every I²C transaction capped at 5ms, where the core's default is 50ms and a probe of an absent address could take all of it.

— **The banner reports the worst time of each part of the loop** since it last printed — network, configuration check, input poll, station and trunk logic, relay flush, heartbeat, failsafes, republish, OTA — beside the loop timing, so a stall can be traced to its source.

— After the fixes the longest pass is 14ms. The same board test that decoded no digit then decoded all ten on three pairs; what failed on the other five is left to the boards.

## 1.19 Changes in Rev 19

— Each expander's configuration is checked, one a second in turn, and restored if it has been lost (§6.4). Found on the bench, 2026-10-03: plugging station board 1 into the chain reset the trunk board's MCP23017 without the controller noticing — it still answered — and with IPOL back at its default every idle SEIZE input read as a seizure, all eight at once. A chip that resets loses its directions and polarities silently, and nothing in §6.2 catches that, since §6.2 acts on errors and a reset chip makes none.

— Firmware consequence, for Claude Code, made the same day: the check, the reconfiguration, the relays restored to their commanded state, and the log line. FIRMWARE_SPEC_REV 19.

## 1.18 Changes in Rev 18

— The firmware says which it is (§9.1), Mark's request, 2026-10-01. On every connection it publishes `sbgame/ctl/firmware`, retained: the revision of this document it implements, the git commit it was built from — with `-dirty` if `control/` had uncommitted changes — and when it was built, as one string, `"control.md Rev 18, 4118077-dirty, built 2026-10-01 21:14Z"`. The banner shows the same. A retained topic rather than the heartbeat's payload: the revision is a state, read once by whoever subscribes, and the heartbeat is an event whose arrival is all anyone reads.

— The revision is a constant in the source, `FIRMWARE_SPEC_REV`, raised with this document whenever a revision has a firmware consequence. The commit and the date are stamped at build time by `control/compile`, which writes `control/sb_version.h` — not committed — and then runs `arduino-cli compile` with whatever it was given. A build without it reports the commit as `unknown`.

— Firmware consequence, for Claude Code, made the same day: the constant, the stamp, the publish and the banner line. The header's "Implements control.md Rev 9" was stale: Rev 10's channel table was made in `930f208`, and the firmware is current to Rev 17 before this one.

## 1.17 Changes in Rev 17

— A station can dial (§7.3), Mark's request, 2026-10-01, for testing the trunk board's dial pulse detection without a switchboard: `sbgame/station/<n>/dial/set` with digits pulses that station's off-hook relay at standard dial timing, 61ms break and 39ms make, with 700ms closed between digits, and echoes the digits still to send on `sbgame/station/<n>/dial`. The firmware does the timing because its 5ms loop sits next to the relay: timed from the host, every edge crosses the network and the broker, and the pulses carry their jitter into the classifier the test is meant to check. Only `sbgame-boardtest` uses it; the game does not, since in the game the operator dials and the stations never do.

— §9.2's republish is 90 messages, where it was 68: each station's tick now carries `dial` as well as `ring` and `hook`, three round trips where it was two.

— Firmware consequence, for Claude Code, made the same day: the station module's dial sequencer, the subscription, and the echo.

## 1.16 Changes in Rev 16

— Follows generator Rev 71: the Next Call button is not fitted to the ring generator board as built. GPIO36 stays reserved for it (§3) and is unconnected; §11's item on the firmware's handling waits on hardware that has it. No firmware change — nothing reads GPIO36.

# 2. Platform and Build

Olimex ESP32-POE-ISO. Arduino IDE: "ESP32-POE-ISO" under the Olimex ESP32 boards package; PlatformIO: `board = esp32-poe-iso`, `framework = arduino`. The firmware requires Arduino core 3.x and carries an `#error` against 2.x — the 2.x LEDC API path was removed rather than maintained. The reason it avoids the LEDC overflow interrupt (§5.2) is that the register struct names it would need move between IDF versions. MQTT client: MQTT 2.5.3, Joël Gähwiler (256dpi/arduino-mqtt) — §9.1.

## 2.1 Updating over the Network

The installed board is updated over Ethernet with the core's ArduinoOTA, not over USB. The first flash of a board, and recovery from a firmware that does not reach the network, are still by USB (CLAUDE.md, Commands).

- **When it listens.** From the first time Ethernet has an address, on UDP port 3232, advertised over mDNS as `sbgame-esp32` (the MQTT client id). `ArduinoOTA.handle()` is called once per loop pass; while no update is under way it costs a UDP poll.
- **Password.** Required. `secrets.h` carries its SHA-256 as `OTA_PASSWORD_SHA256` (`echo -n 'password' | sha256sum`), so the plaintext is not in the firmware image; the uploader gives the plaintext. A firmware built without it has OTA off and says so in the banner. A wrong password is refused and changes nothing on the board.
- **What an update does to the system.** An update in progress blocks the main loop for its duration, some seconds, so nothing is polled, published or commanded. Before the first byte is written to flash the firmware therefore puts the board in the state a reset would: SD low and the bridge parked (§4.3), every relay released (§10). The broker sees the keepalive lapse and publishes the will, `offline` on `sbgame/ctl/status` (mqtt.md §8.1), which is how the game program learns the controller has gone. On success the board restarts into the new firmware and runs §4.2 from the top. On any error after that first write it restarts into the old one, which is still in its own partition: an interrupted update leaves the board running what it had, having dropped the calls in progress.
- **Not during a show.** An update drops every call, exactly as a USB upload does. The firmware does not refuse one while calls are up: a relay-idle test misses a seized trunk, which energises no relay, and a game-state test would need a new topic. Updating is an operator action taken between games.
- **Why not USB, since it is there.** The USB connector was the update path until Rev 15. Left attached in the installed system it would join portland's ground to the 24V system ground, and every program that opened the port — a serial monitor, ModemManager probing a new tty — would reset the board. PoE keeps the grounds apart, and the network path needs no cable.

The partition table is the core's default for the board: two 1.25MB application slots, which is what an update needs — the new image is written to the slot not running and the boot pointer moved only when it verifies. The firmware is about 0.56MB.

# 3. Pins and Polarity

The GPIO assignments and the reasons for them are generator §3.1 and §3.2, which are the authority; verify every assignment against the Olimex schematic for the board revision in hand before committing anything, as that section says. What the firmware needs to know about each pin:

```text
  GPIO32  LEDC CH0   PWM A → IN2 (U5, right leg) via 74HCT04 gates 2 and 5. Active HIGH. Idle LOW (duty 0).
  GPIO33  LEDC CH1   PWM B → IN1 (U4, left leg) via gates 1 and 6.          Active HIGH. Idle LOW (duty 0).
  GPIO14  output     SD via gates 3 and 4, non-inverting.     HIGH = bridge enabled, LOW = disabled.
  GPIO4   input      Master enable, active LOW, internal pull-up. LOW = generator may run. J1 pin 1.
  GPIO5   output     Expander /RESET, active LOW, idles HIGH. Strapping pin — must be high at boot.
  GPIO13  I²C SDA    Wire.begin(13, 16) — note the argument order.
  GPIO16  I²C SCL    100kHz.
  GPIO15  output     Switchboard power cut (§5.4), active HIGH, idles LOW. J1 pin 4. Strapping pin — leave as input until setup().
  GPIO36  input      Reserved for the Next Call button, active LOW; not fitted (generator Rev 71). Pull-up is R37 on the Olimex.
```

Both PWM pins are active HIGH as of generator Rev 44, so duty is written directly and the idle value is 0, which is LEDC's own power-on state: the peripheral comes up parked without the firmware doing anything. Under the earlier 74HCT02 the pins were active low, every duty was a complement, and parking at 0 put the full rail across the primary as DC; generator §12.3 keeps that history so an older board is legible.

Say SD in levels, not states: LOW is shutdown, HIGH is enabled. "SD asserted" is correct and reads backwards.

# 4. Boot, Safe State, Startup and Shutdown

## 4.1 What the Hardware Guarantees Before the Firmware Runs

The firmware does not create the safe state; it inherits one. R_PWMA_PD and R_PWMB_PD hold GPIO32 and GPIO33 low through boot, so both IR2104 IN pins are low and the bridge is parked with the primary at ground. R_SD_PD holds GPIO14 low, so both drivers are in shutdown. When PoE is absent, the 24V bus is live and the 74HCT04 has no supply, SD is held near 0V by the unpowered gate's output clamp rather than by a resistor — R_SD_PD2 is not fitted (generator §6, Rev 68). R_GS2 and R_GS4 hold the low-side gates down when nothing drives them. Generator §5.3 and §6 have the reasoning; the point for the firmware is that the bridge is off by two independent mechanisms until it deliberately turns both on, and that nothing the firmware does at boot can make it otherwise.

On the expander side, the MCP23017 comes out of reset with IODIR = 0xFF, every pin an input, so Port B floats until the firmware configures it. R_pd on every relay driver holds the driver off through that window (station §5.2, trunk §7.3). A reset therefore drops every relay — see §6.2.

## 4.2 Startup Sequence

In this order, and the order matters:

1. Power-on. Bridge off by hardware (§4.1). GPIO15 left as an input.
2. Claim GPIO5 high (its idle) and GPIO15 as an output, low (its idle: the switchboard powered).
3. Ethernet: `ETH.begin()`.
4. Expander reset: drive GPIO5 low for at least 1ms, release, wait for the expanders to settle (§6.2).
5. I²C: `Wire.begin(13, 16)` at 100kHz. Scan the configured device list — 0x20, 0x21, 0x22 and 0x23 with the three station boards and the trunk board all built. The list is driven from the configured station board count, not hard-coded, so that a board pulled for repair is a configuration change rather than a phantom missing device logged on every boot, which trains whoever reads the log to ignore the one message that matters. Log any device that does not respond and remember the result; it is published on `sbgame/ctl/i2c` at step 7, once there is a connection to publish on.
6. Configure every expander that answered: IODIR Port A inputs, Port B outputs; GPPU off on Port A (the boards fit their own pull-ups); IPOL on Port A so a read returns 1 for ring or seize present (the detectors are active low); OLAT Port B all zero. Every relay is now released by command as well as by default.
7. MQTT: connect with the last will, publish the birth message, subscribe, publish every state topic once (§9.1), and publish the step-5 scan result on `sbgame/ctl/i2c`, retained: `"ok"`, or `"missing: "` followed by the absent addresses in hex, space-separated. It is republished on every reconnect and after any rescan (§6.2).
8. LEDC channels configured, both at duty 0.
9. GPIO14 driven LOW (it already is, by R_SD_PD; this makes it a firmware fact as well).
10. The 200µs step timer enabled; waveform generation armed at the peak-phase index (§5.3).
11. GPIO14 driven HIGH — drivers enabled. The generator runs while GPIO4 is held LOW.

Steps 3 to 7 are new relative to generator §6.1, which listed the ring generator's own startup and named the Ethernet and I²C steps without ordering them against it. Nothing about the ring generator's own sequence changes. The scan result does not gate steps 8 to 11: an absent expander leaves its relays released, and the generator runs regardless (§1.11). Until Rev 11 a step 8 here refused to arm the bridge on a missing expander.

## 4.3 Shutdown Sequence

1. GPIO14 driven LOW — both IR2104s disabled immediately.
2. LEDC duty parked at 0 on both channels. Both IN pins low; bridge fully off.

Release of the GPIO4 enable is the operator's shutdown; the firmware runs this sequence when it sees GPIO4 go high and re-runs §4.2 steps 8 to 11 when it returns low. Remanence after a stop is accepted rather than addressed (§5.3).

# 5. Ring Waveform Generation

## 5.1 Constants

```text
  CARRIER_FREQ_HZ         = 40000   (25 µs period)
  CARRIER_CYCLES_PER_STEP = 8       (200 µs step period)
  SINE_STEPS              = 250     (50 ms = 20.000 Hz exact)
  LEDC_RESOLUTION_BITS    = 10      (1024 duty levels)
  g_amplitude             = 0.90    (see §5.5)
  Constraint: 20 = 40000 / (8 × 250)
```

Where the four numbers come from — reconstructed at generator Rev 39 from the constraint rather than recovered from the original decision; treat it as the best available account. Two are fixed from outside: 20Hz is the ring frequency, and 10 bits follows from the carrier, since LEDC counts at 80MHz, a 40kHz period is 2000 counts, and 1024 fits inside that where 2048 would not. The other two are one decision, because their product must be 2000. 250 steps buys 1.44° of phase per step and costs 5000 duty writes per second; 125 would very likely have served, since output purity barely enters into it — the carrier is 2000× the output frequency, the stepping residue sits at multiples of 5kHz which C_OUT attenuates with the carrier (generator §9.6), and a ringer needs the right frequency and enough current to move an armature, not a clean sine.

The step count has one physical consequence and it is not the sine shape: at g_amplitude = 1.00 three consecutive steps reach 100% duty, giving 600µs of unbroken high-side conduction, which is the bootstrap case generator §8.3 works through. Halving the step period halves that window. Anyone revisiting SINE_STEPS reads generator §8.3 first.

Why the carrier is 40kHz specifically is not recorded. Above audibility, and low enough to leave 10-bit resolution intact, are the obvious reasons; if the original one was something else it is lost.

## 5.2 Step Timing

Duty is updated once per step, phase-locked to the carrier. The end-of-period interrupt on CH0 would be the ideal source and needs no separate timer, but reaching it from the Arduino IDE means writing `LEDC.int_ena` directly, and those register struct names move between IDF versions — a build that breaks on a core update rather than on a design change. What is built instead is a periodic `esp_timer` at 200µs. The equivalence holds because LEDC latches a new duty at the next carrier period boundary: a duty written at an arbitrary instant still takes effect on a period edge, so there is no mid-period glitch. What remains is which period the write lands on — occasionally 7 or 9 carrier cycles rather than 8, at most 25µs on a 50ms waveform, non-accumulating because the timer free-runs at its own rate. Dispatch is `ESP_TIMER_TASK`, so the callback is task context and `ledcWrite()` is legal in it.

During each half-cycle one leg is driven and the other is held at duty 0; during the positive half GPIO33 is held low and GPIO32 carries the sine, and the reverse during the negative half (generator §5.2's truth table). On the board as built GPIO32 drives the right leg, U5, so the positive half-cycle drives SW_R high (generator §5.1).

## 5.3 Start Phase

The sine starts at its positive peak, duty-table index SINE_STEPS/4, not at the zero crossing at index 0. Flux in the transformer is the integral of the applied voltage; integrating from a zero crossing, starting from zero flux, gives a first half-cycle that swings from 0 to 2Φpk instead of −Φpk to +Φpk. The Antek runs at 87% of rated flux in steady state, so a zero-crossing start puts the first half-cycle at about 175% of rated: the core saturates, magnetizing current spikes for up to 25ms, and F1 sees it. Starting at the voltage peak begins the integral where steady-state flux is zero, so the first half-cycle follows the steady-state trajectory. Mains soft-start modules for large toroids switch on at the peak for the same reason.

What it does not solve is remanence: after a stop, the core keeps some flux from whichever half-cycle it stopped in, and a restart carries it. The generator runs continuously from power-up with ring cadence switched on the secondary by the trunk board, so restarts are rare and this is accepted.

In the firmware, the active leg goes from parked to about 90% duty on the first PWM period after SD, which is a single edge and not a transient. Its bootstrap capacitor is uncharged at that instant and fills through the low-side windows over the first few carrier cycles, during which UVLO holds HO off — harmless, the parked leg holds the primary at zero meanwhile. The sync output's first real edge (§5.4, through Rev 30) is the rising one at index 0, three quarters of a cycle after SD. The fallback, if the peak start ever proves awkward downstream of sync, is a zero-crossing start with g_amplitude ramped over the first two cycles.

Verification, as specified: capture from SD rising on GPIO14, 10ms/div, primary through the J3 monitor on one channel and the rail at the bridge on the other. Pass is a first half-cycle of the same amplitude as those that follow and no dip on the rail. The change was in the firmware before the Antek's first power-up (generator Rev 52), so the transient it prevents has never been seen on that transformer.

Verified 2026-09-25, Analog Discovery 3 (Mark's capture `ring11.png`, not in the repository): 10ms/div, triggered on the first rising edge of the §5.4 sync on DIO 0 with the start 37.6ms before it in the pre-trigger record, channel 1 on J10, channel 2 on J8 (J3 and J6 in the board's numbering, generator Rev 68) through the 11:1 divider, no load, C_OUT fitted, firmware at control.md Rev 11. The start is at −38ms. J8 steps from 0 to 112V peak and the first half-cycle is the same amplitude and shape as every one after it; J10's first peak reads 19.5V against 21.5V steady, which is the §8.7 filter settling (0.94ms) while the sine is already 3.5ms past its peak — 21.5 × cos 25° = 19.5V — and from the second half-cycle it is ±21V. The rail was not captured, as the procedure asked; J8 stands in for it, since the output is duty × rail × ratio and a rail dip of the 2026-09-04 kind would show as a sag in the first output half-cycle, and there is none. Inrush current in the first 10ms was not measured and is not practical on this bench; steady-state supply current is 30mA, as at Rev 52. Channel 1 was connected reversed, so both traces read inverted: the start shows as a negative peak and the sync edge as a negative-going zero crossing. With the probe the right way round the start is the positive peak and sync rises into the positive half-cycle, as written. Pass.

## 5.4 Switchboard Power Cut

GPIO15 drives the relay in the switchboard's 24V leg (generator §7.8, Rev 75), on J1 pin 4: low, the relay is released and its normally closed contact feeds the switchboard; high, the relay operates and the switchboard is dark. It idles low from `setup()` on.

`ctl/power_cut/set` `"on"` drives it high for `POWER_CUT_MS`, 1000, then low again; `"off"` drives it low at once. The 551's relays drop and its locked trunk signals with them in well under that. A second `"on"` while the cut is under way is ignored and logged: the cut is a pulse, not a level, and a duplicate is not a reason to stretch it. `ctl/power_cut` reads `"on"` from the moment the pin goes high to the moment it goes low, published retained as for every state topic. The timing runs in the main loop against `millis()`; a stall of the loop lengthens the cut by the stall and nothing worse.

Every failsafe of §10 — the connection lost, the game heartbeat missed, a bus fault, an update starting — drives GPIO15 low with everything else it releases. The switchboard is our load, not a relay of the game's, but powered is its safe state and the rule is simpler kept whole.

GPIO15 is a strapping pin (MTDO). The firmware leaves it as an input until `setup()`. Meanwhile the Olimex's 10kΩ pull-up and the driver's 1kΩ and 470Ω to ground hold it near 0.4V, which the strap reads as low: the ROM's boot log is silenced and nothing else this board uses changes. The driver's base sits near 0.13V, so the relay stays released through a reset (generator §7.8).

Through Rev 30 GPIO15 was the waveform sync for the bench: high at step 0, low at step 125, for triggering a scope against phase zero. §5.3's verification used it. A bench session that needs it again can take it back temporarily, with the relay's driver unplugged from J1.

## 5.5 Amplitude

g_amplitude stays at 0.90 and must stay clear of 1.00. At 1.00 enough consecutive steps reach 100% duty that the low side stops turning on, C_BOOT gets no refill window and the bootstrap collapses to about 2.6V at each sine peak (generator §8.3, measured); at 0.90 it holds 11.98V. 0.90 also puts the toroid at 87% of rated flux where 1.00 would put it at 97%. A measurement that calls for a trim above 0.95 points at the transformer wiring, not the duty (generator §9.4).

# 6. I²C Master

## 6.1 Bus and Expanders

One bus, 100kHz, SDA on GPIO13 and SCL on GPIO16, the single 2.2kΩ pull-up pair on the generator board. One MCP23017 per station board at 0x20, 0x21 and 0x22 and one on the trunk board at 0x23; 0x24–0x27 are reserved for optional second expanders that are not fitted. Hardware in generator §4, station §9.2–§9.5, trunk §10.2–§10.4.

On every expander: Port A is eight inputs, Port B eight relay outputs. Station boards: Port A = RING_DET_1..8, Port B = OFFHOOK_1..8. Trunk board: Port A = SEIZE_1..8, Port B = RING_EN_1..8. The detectors are active low, so set IPOL on Port A and read 1 for present. Leave GPPU off — the boards fit their own pull-ups. On station board 3 the last two strips are not stations (station §7.9.6 to §7.9.8). Strip 7 — A32 channel 23 — is the operator tap and strip 8 — A32 channel 24 — is the audience monitor output. Neither has a relay or a ring detector fitted, so Port B bits 6 and 7 drive nothing and Port A bits 6 and 7 read a steady no-ring, held high by R2. Leave the mapping alone rather than special-casing it, and never publish station/23 or station/24 topics: there are 22 stations, 1–22. In the firmware this is a channel table with one row per circuit and no row for either bit, so nothing polls, publishes or commands them (Rev 7, Rev 10).

The MCP23017 driver is written against the registers, not over a general-purpose library (Rev 7). Two reasons that are specific to this design: §6.1 asks for IPOL on Port A, which the Adafruit library defines but gives no way to write; and §6.2 needs a NAK or a read-back mismatch to be visible as a failure, where a driver whose read returns 0 on a bus error cannot distinguish that from eight idle inputs — the one failure that looks exactly like normal. The poll reads whole ports, one transaction per expander. IOCON is left at its reset default rather than written, since every path into the driver has pulsed /RESET first and a hardware reset is a stronger guarantee of BANK = 0 than a write.

## 6.2 Hardware /RESET

GPIO5 drives /RESET to every expander on 6P6C positions 1 and 6 (generator §4.7 for the design). Sequence: drive GPIO5 low, hold at least 1ms — chosen as unambiguously safe rather than as a minimum; confirm the datasheet figure — release, wait for the expanders to settle, then configure IODIR, IPOL and OLAT on every device before anything else.

A reset returns every expander to IODIR = 0xFF and so drops every relay it controls — off-hook relays on the station boards, ring relays on the trunk board — with R_pd holding the drivers off through the window. Assert it at startup before the scan (§4.2 step 4), and on a detected bus fault: three consecutive errors on one device — NAKs, or reads that return a value inconsistent with what was written. One error is logged and counted, not acted on; a single NAK on six feet of daisy-chained 6P6C is a glitch, and resetting every relay on the chain for it would be the worse fault. Do not assert it while calls are up unless recovering from a fault, and **never while ring is applied** (§8.4): a reset mid-cadence releases the ring relay at an arbitrary point in the 20Hz waveform rather than at the cadence boundary. A wedged expander holding a ring relay closed is the one failure a firmware watchdog alone cannot clear, and this is the tool for it — with ring inhibited first.

The recovery is one reset, one rescan and one reconfigure. An expander that is still absent afterwards stays absent until the next boot: its circuits are not polled, its commands are dropped (§9.4), and `ctl/i2c` says so. It is not retried, because a retry is another /RESET and another drop of every relay on the chain (Rev 7). The bridge stays armed: an absent expander's ring relays are released, so nothing is ringing that the firmware cannot stop (§1.11).

## 6.3 Polling

Poll Port A of every expander at 200Hz (every 5ms). There is no INT line and none is wanted: with the station ring detector pulsing at 40Hz, interrupt-on-change would mean 80 interrupts per second per ringing station, each needing an I²C transaction to identify and clear, and on the trunk board an accidental ring gives 40 per second for something that is not even a state change. Polling gives the debounce logic five samples per half-cycle of the 40Hz pulse train, makes the timing deterministic, and costs about 6% of a 100kHz bus for four expanders. Station §9.6 and trunk §10.4 have the hardware side.

Everything in §7 and §8 runs from this 200Hz sample stream. The MQTT heartbeat (§9.3) is published from the same loop after the poll, so that it proves this loop is running.

## 6.4 Configuration Check

Rev 19. Once a second, take the next present expander in turn and read back IODIRA, IODIRB and IPOLA. They should read 0xFF, 0x00 and 0xFF (§4.2 step 6). Anything else means the chip has been reset — a glitch on /RESET or on its supply, typically while a board is plugged into the chain — and has come back with its power-on defaults, every pin an input and no polarity inversion, so its idle inputs read as present. Log it, configure it again as at startup, and write its Port B latch back to the relay state the firmware holds, since the reset dropped every relay in hardware while the game's commands still stand. A read that fails is an ordinary bus error and counts toward §6.2's fault threshold like any other. One device a second costs three register reads, under a millisecond, in one poll tick in two hundred; four boards are each checked every four seconds.

# 7. Station Circuits

## 7.1 Ring Detection

The HCPL3700M output pulses at 40Hz while ring is present rather than sitting steady (station §3.4, §3.7), so the firmware can distinguish genuine ring voltage from a stuck line or a DC fault. Declare ringing after four or more transitions on RING_DET_n within a 150ms window; declare ring released after 100ms with no transition. Ring on this switchboard is applied manually by the operator holding a key, so the pulse train is continuous for as long as ring is present and does not follow a cadence.

Publish the debounced state on `sbgame/station/<n>/ring` on change only, never the pulse train.

## 7.2 Off-Hook

On `sbgame/station/<n>/hook/set`, write OFFHOOK_n on Port B — 1 is off-hook, relay energised, loop closed through R3 — and echo the new state on `sbgame/station/<n>/hook`. The echo is what lets the game program tell a command that was acted on from one that was not. The echo is the commanded state, published when the command is accepted; the relay write and its read-back happen at the next 5ms flush (Rev 7). A relay that does not take is a read-back mismatch, counted under §6.2, and the bus-fault path that follows releases everything and republishes every state topic, so the echo is corrected within three polls. A command for a circuit on an absent board is not echoed at all — it is dropped (§9.4).

Release every OFFHOOK_n on any of the conditions in §10.

## 7.3 Dialling

Rev 17. On `sbgame/station/<n>/dial/set` with a payload of digits, `0`–`9`, at most 16, the station dials them by pulsing OFFHOOK_n as a rotary dial does (§8.2): N breaks for digit N, ten for 0, each **61ms open** then **39ms closed** — 10 pulses a second at 61% break, the nominal Bell figures — and **700ms closed** between digits, as a dial's return. Only while the station is off-hook: a `dial/set` on an on-hook station is logged and dropped, since there is no loop to break. A new `dial/set` replaces any dialling in progress; an empty payload stops it. `hook/set` `"off"` stops it and puts the station on-hook; every condition in §10 that releases the relay stops it too.

The echo is `sbgame/station/<n>/dial`, retained: the digits not yet finished, including the one being sent, and empty when there are none — set at the command, shortened as each digit's last pulse ends, empty at the end or when stopped. `hook` is not republished during the pulses: the station is off-hook throughout, and the breaks are the dial's, not the hook's. The timing is on the 5ms poll tick, so each interval is good to one tick; the §8.2 thresholds have 35ms in hand either side of both.

# 8. Trunk Circuits

## 8.1 The Seizure Input

One input per trunk, SEIZE_n, sampled at 200Hz. It is asserted whenever loop current flows and nothing else — the trunk board has no other supervisory signal — so everything the switchboard does on a trunk arrives as a pattern of assertions and releases on this one line: seizure is a long assertion, release is a long release, a dial pulse is a short release inside a seizure, and ring applied by mistake is a 20Hz alternation. The firmware classifies each release interval by its length and each assertion interval by its length and by what preceded it:

| **Interval on SEIZE_n** | **Length** | **Interpretation** |
| --- | --- | --- |
| Asserted, from idle | ≥ 100ms | Seizure. Declare SEIZED; publish `seize` = `"on"`. |
| Released, from seized | 25–100ms | A dial pulse break (§8.2). Count it; do not release. |
| Released, from seized | ≥ 250ms | Release. Declare IDLE; publish `seize` = `"off"`. A digit in progress is abandoned, not published. |
| Asserted, after ≥ 1 pulse | ≥ 200ms | End of digit. Publish the count on `digit` (§8.2). |
| Alternating, either state | two consecutive break-to-break intervals ≤ 60ms | Ring applied from the switchboard by mistake (trunk §5.2). Publish `fault` = `"ring_on_trunk"`; clear it when the pattern stops. Not a seizure, not a dial. |

Two things separate the cases, and neither is a count of transitions. Seizure against ring is duration: an accidental ring never holds the line asserted for longer than about 27ms (trunk §5.2) against a 100ms threshold, roughly four times margin. Dial against ring is the interval between successive breaks: 20Hz ring gives one every 50ms, and a dial gives one every 67–125ms across the whole 8–15 pps window in §8.2, so a ≤ 60ms break-to-break interval is ring and a 67ms or longer one is a dial pulse, with no overlap on paper. At 5ms sampling the two are one sample apart at the 15 pps end, so ring is declared on two consecutive intervals ≤ 60ms, not one; a dial cannot produce two in a row and ring produces them continuously. Rev 1 used a transition count — four or more in 150ms — which a 12 pps dial can just reach; the interval test is what actually differs between the two signals. A break shorter than 25ms or between 100ms and 250ms is neither a pulse nor a release: log it, publish `fault` = `"bad_dial"` if it occurs inside a digit — or, for one of 100–250ms, before the digit's first pulse (Rev 23, §8.2) — and carry on.

**Glitch filter** (Rev 24). A change of level is accepted only when two consecutive samples show it, and is timed from the first of them. A pulse of either sense shorter than one sample interval — dial contact bounce — cannot occupy two samples and is ignored; every interval in the table above keeps its length, and each edge is reported 5ms later than it happened.

The 100ms of seizure latency and the 250ms of release latency are invisible on a manual switchboard. The 25ms release threshold of Rev 1 is gone because it is shorter than a dial pulse.

## 8.2 Dial Pulse Detection

The operator dials outgoing calls on a seized trunk with a rotary dial. A rotary dial interrupts the loop once per pulse — the pulsing contacts open for the break interval and close for the make interval — and sends N pulses for digit N, ten for 0. Between digits the loop stays closed for as long as the dial takes to return. On this trunk board the loop is fed by a current source and sensed by the HCPL3700M across R_LOOP (trunk §3, §4), so each break is loop current stopping and each make is the current source re-establishing it; the 85mA make inrush lasts about 2µs (trunk §3.2.2) and the detector's own delay is tens of microseconds, so the pulse arrives on SEIZE_n with its timing essentially intact. No hardware changes.

**Standard timing, Bell System practice.** These are the figures the thresholds below are derived from; if a dial outside them is ever connected, re-derive rather than widen blindly.

| **Parameter** | **Dial as manufactured** | **Accepted by receiving equipment** | **Note** |
| --- | --- | --- | --- |
| Pulse rate | 10 pps nominal, 9.5–10.5 pps | 8–12 pps; some registers accept 7.5–12 | Period 100ms nominal, 83–125ms accepted |
| Percent break | 61% nominal, 58–64% | roughly 50–70% | At 10 pps: break 61ms, make 39ms |
| Break duration | 61ms at nominal | about 42–88ms across the accepted rate and break ranges | This is what a pulse looks like on SEIZE_n |
| Make duration within a digit | 39ms at nominal | about 25–62ms | Never long enough to be mistaken for an inter-digit pause |
| Inter-digit interval | ≥ 600ms typical from a mechanical dial return | equipment requires ≥ about 200ms of make to delimit a digit | The loop is closed throughout; it is a long make, not a long break |
| Digit 0 | 10 pulses | | |

**Thresholds.** From the table, with margin on each side and with 5ms sampling, the classifier in §8.1 uses:

```text
  pulse break        25 ms  <= open   <  100 ms     count one pulse
  make within digit           closed  <  200 ms     wait for the next break
  end of digit                closed  >= 200 ms     after >= 1 pulse: digit complete
  release                     open    >= 250 ms     trunk released; abandon any partial digit
  ring, not dial     two consecutive break-to-break intervals <= 60 ms
```

A break of 25ms is 5 samples and one of 100ms is 20, so a nominal 61ms pulse sits at 12 samples with 7 in hand either way; a nominal 39ms make is 8 samples against the 40-sample end-of-digit threshold. The end-of-digit threshold at 200ms is below the shortest inter-digit interval any real dial produces and far above the longest make within a digit, so a digit is never split and two digits are never merged. The release threshold at 250ms is above the longest pulse break by a factor of three and below any plausible operator action after a digit — an operator does not release a trunk within a quarter second of finishing dialling it.

**Reporting.** When a digit completes, publish `sbgame/trunk/<n>/digit` with the digit as a single character `"0"` to `"9"` — ten pulses is `"0"`, eleven or more is a `"bad_dial"` fault and no digit. Not retained, and at QoS 0, for the reason in mqtt.md §7: it is the one message that is an event rather than a state, and over a TCP link QoS 0 delivers it exactly once or not at all, where QoS 1 could deliver it twice on a reconnect. A partial digit is abandoned without publishing if the trunk releases during it. A break outside the 25–100ms window inside a digit spoils it, and so does a 100–250ms break before the digit's first pulse, which opens the digit already spoiled (Rev 23 — a make lost between the first two pulses would otherwise leave the rest to be counted as a shorter, valid digit; a break under 25ms before the first pulse is only logged): the digit is not published, and `fault` = `"bad_dial"` is published in its place when the digit ends — at the 200ms make — not at the moment of the bad break (Rev 7; one message per digit). A spoiled digit that the trunk releases out of is abandoned like any other and publishes nothing. `bad_dial` is cleared on the next valid digit and on release.

The game program assembles digits into a number and decides what the call means; the firmware knows nothing about how many digits to expect and does not need to. Dialling is only meaningful in SEIZED. Pulses seen in any other state are not counted — in RINGING the sense line is lifted off R_LOOP during the on phase in any case (§8.3), and pulses in IDLE are a break pattern with no seizure in front of them, which the classifier already treats as ring or as noise.

## 8.3 State Machine

```text
  IDLE          RING_EN off. SEIZE watched.
                  SEIZE asserted 100ms       -> SEIZED
                  ring pattern (two breaks <=60ms apart) -> RING_ON_TRUNK
                  ring/set "on"              -> RINGING
                  shortring/set "on"         -> RINGING, one burst (Rev 25)

  RINGING       Cadence 2s on / 4s off (§8.4), or one 1s burst for shortring/set (Rev 30; 0.5s at Rev 25). SEIZE unreadable during the on phase
                (pole 2 has lifted the return off R_LOOP).
                  SEIZE asserted 100ms in off phase -> SEIZED, cancel ring
                  ring/set "off", or 30s hard timeout -> IDLE
                  burst of shortring/set ends, or shortring/set "off" -> IDLE
                  ring/set "on", shortring/set "on" -> no-op

  SEIZED        Loop current flowing. Audio path live. Dial pulses counted (§8.2).
                  break 25-100ms             -> pulse counted, stay SEIZED
                  make >= 200ms after pulses -> publish digit, stay SEIZED
                  open >= 250ms              -> IDLE (partial digit abandoned)
                  ring pattern               -> RING_ON_TRUNK (partial digit abandoned)
                  ring/set or shortring/set "on" -> dropped, logged; echo stays "off"

  RING_ON_TRUNK Operator has rung a trunk. Report; take no other action.
                `seize` keeps the value it had on entry.
                  pattern stops, SEIZE asserted 100ms -> SEIZED
                  pattern stops, otherwise            -> IDLE
                  ring/set or shortring/set "on" -> dropped, logged; echo stays "off"
```

RING_ON_TRUNK is a report, not a mode — the board keeps feeding the loop and the audio path stays live throughout. It exists so the game program can distinguish a trunk being rung into from an idle one and put it on screen; without it the operator gets silence and no explanation. Dialling is likewise not a state: the trunk is SEIZED throughout, and the digit counter is a sub-state of SEIZED that the classifier in §8.1 drives. RING_ON_TRUNK is entered from SEIZED as well as from IDLE — the operator can ring a trunk that is already seized — and on the pattern stopping the trunk returns to whichever of SEIZED or IDLE the line then reads. Rev 2 and Rev 3 listed the transition from IDLE only, which would have left a 20Hz break train inside a seizure to be counted as pulses.

`seize` is not changed on entering RING_ON_TRUNK (Rev 7). Entered from SEIZED it stays `"on"`; entered from IDLE it stays `"off"`. `fault` = `"ring_on_trunk"` is the report, and `seize` keeps reporting the loop as last classified. The alternative — publishing `seize` = `"off"` for the duration of the pattern, which is what the first firmware did — would look to the game program like a release and tear the call down for an operator's slip; when the pattern stops and the loop is still closed, SEIZED is re-entered with `seize` already `"on"` and nothing is published.

`ring/set "on"` is acted on in IDLE, where it starts the cadence or queues behind the concurrent-ring cap (§8.5), and is a no-op in RINGING. In SEIZED and RING_ON_TRUNK it is dropped with a log line and the `ring` echo stays `"off"`, which is how the game program learns it was not acted on (Rev 7). It is not held for later: a ring that starts seconds after the command, once the operator has released the trunk, is a command the game did not mean at that moment. The game re-issues it if it still wants it. The cap queue is different — that request was accepted in IDLE and is only waiting for the generator.

## 8.4 Ring Cadence

The trunk board cannot detect seizure while it is ringing, because relay pole 2 has lifted the ring conductor off the sense resistor (trunk §7.5). Dial pulses are not expected during ring either — a trunk being rung is an incoming call, and the operator dials only on a trunk the switchboard has seized outward. Cadenced ring solves that without masking anything:

```text
  RING_EN asserted   2.0s   relay energised, ring on line, seizure blind
  RING_EN released   4.0s   relay released, DC feed restored, seizure readable
  repeat until answered, cancelled by the game program, or the timeout expires
```

**Short ring** (Rev 25). `shortring/set` `"on"` energises the relay once, for 1s (Rev 30; 0.5s at Rev 25, which one jack's latching relay did not always catch), and returns the trunk to IDLE, with no off phase and no repeat; the seizure input is rebaselined as at the start of an off phase, so a seizure is read from the moment the burst ends. The 551's trunk signal is a latching relay that a short burst operates, so this is what the game program uses to signal an incoming call (game_control.md §4.3, Rev 28): the lamp stays lit until the operator answers, and the answer is never hidden behind a ring-on interval. The 30s hard timeout does not arise. The cadence below remains for `ring/set`, which the page's diagnostics use.

Worst-case answer-detection latency is one ring-on interval, 2s, which is also what real incoming trunk ring sounds like. A 1s/2s cadence halves the latency if 2s proves annoying in play; it is a constant here, not a hardware choice. Releasing the relay mid-cycle is 3.6VA against a 500VA contact rating and needs no zero-crossing logic. Echo the relay state on `sbgame/trunk/<n>/ring` at every transition, so a monitoring UI sees the cadence.

## 8.5 Guards

**Hard ring timeout.** No trunk rings for longer than 30 seconds regardless of what the game program asks for. A host bug that commands ring and never cancels it must not leave 90V cycling onto a switchboard line indefinitely; the timeout is three lines and independent of everything on the host. The 30s runs from the first energisation of that trunk’s ring relay, not from receipt of ring/set: a trunk queued behind the concurrent-ring cap has not rung yet, and timing it from the command would give it a shortened cadence or none. What the timeout bounds is time with ring on the line, and that is what it measures.

**Concurrent-ring cap.** Eight trunks and the switchboard share one generator, and the operator can ring a station at any moment on top of whatever trunks are ringing. Cap the number of trunks ringing at once — four is the starting value, to be set from the ring-current measurements trunk §7.6 asks for — and queue trunks beyond it rather than ring them. Leave headroom for one station ring, since the firmware cannot see the operator's ring key coming.

**Never assert /RESET while ring is applied** (§6.2).

**Never publish a digit outside SEIZED**, and never publish a partial one (§8.2).

**Generator enable is not per-call.** The generator runs continuously whenever GPIO4 is low; ring cadence is switched by the trunk relays, not by SD. The operator's ring key can be pressed at any moment and the firmware cannot see it coming, so the bus must be live for the whole session (trunk §7.6).

# 9. MQTT Client

The topics, payloads and retention are `mqtt.md`; this section is what the firmware does with them.

## 9.1 Connection

The client library is MQTT 2.5.3 by Joël Gähwiler (256dpi/arduino-mqtt), chosen because it supports QoS 1 and because its keepalive ping is sent from `loop()` rather than from a background task — so a wedged main loop stops the ping, the broker fires the last will, and the client-dependent gap mqtt.md §8.2 describes closes on the safe side. Connect over the wired interface with a clean session, keepalive 5s, and a last will of `"offline"` on `sbgame/ctl/status`, retained. On connect: publish `"online"` to `ctl/status`, retained; subscribe to `sbgame/station/+/hook/set`, `sbgame/trunk/+/ring/set`, `sbgame/ctl/power_cut/set` (Rev 31), `sbgame/ctl/game_heartbeat` and `sbgame/ctl/sync` — those patterns and no wildcard over `set`, since the audio program's `play/set`, `listen/set` and `tone/set` share the circuit roots (mqtt.md Rev 5 §8.4); publish every state topic once (`ring` and `hook` for every station, `seize`, `ring` and `fault` for every trunk). Reconnect with backoff on loss — 500ms doubling to 8s — and every reconnect repeats this sequence, since a clean session forgets the subscriptions. A connect attempt is blocking: the TCP connect timeout plus the wait for CONNACK, which against a host that is down can be seconds, during which the 200Hz loop does not run (Rev 7). That is tolerable only because the loss of the connection has already released every relay (§10) before the first retry is due, so nothing is being driven while the loop is stalled. The loss release must stay immediate for that reason. Ring detection and dialling are not sampled during a stall; with no host to report to, nothing is lost that could have been used.

Use a username and password; the broker is not anonymous (`mqtt.md` §9). Set TCP_NODELAY on the socket (Rev 20): with Nagle on, each QoS 1 publish waits about 40ms for the broker's delayed ACK, and the loop with it.

With the birth message, publish `sbgame/ctl/firmware`, retained: `"control.md Rev <n>, <commit>, built <date>"` (Rev 18). `<n>` is `FIRMWARE_SPEC_REV`, the revision of this document the source implements; `<commit>` is the short commit hash at build time, with `-dirty` if `control/` had uncommitted changes, and `<date>` the build's UTC time, both stamped by `control/compile`, or `unknown` without it.

## 9.2 Publishing

State topics are published retained, QoS 1, on change only, from the 200Hz loop. The one event topic, `trunk/<n>/digit`, is published unretained at QoS 0 (§8.2). Commands are never published by the ESP32. On `ctl/sync`, republish every state topic. Also republish every state topic on a slow timer — every 30s — which bounds how long a lost publish can leave a retained value stale at the broker; the game program reacts to changes in value, so a repeated value is harmless.

A full republish is 90 messages — 68 until Rev 17 added each station's `dial` — and with this client a QoS 1 publish blocks until its PUBACK arrives. Sent as one burst it holds the 200Hz loop for on the order of 100–300ms on a LAN, which is longer than the station ring-release quiet time (§7.1) and longer than a dial pulse (§8.2): a ringing station would report `off`/`on` every 30s and a digit under way would be spoiled or split. So the republish — on reconnect, on `ctl/sync` and on the timer alike — is spread one circuit per 5ms poll tick, round-robin over the 30 circuits, so each tick pays one round trip and the whole set is refreshed in about 150ms (Rev 7; 31 circuits and 155ms until Rev 10). The first firmware sent it as a burst; the fix is a code consequence of Rev 7.

## 9.3 Heartbeats

Publish `sbgame/ctl/esp_heartbeat` every second, payload uptime in seconds, not retained, **from the main loop after the I²C poll** — never from a timer or the network task — so that it proves the loop that drives relays is running (`mqtt.md` §8.2).

Watch `sbgame/ctl/game_heartbeat`. If two consecutive beats are missed — no message for more than 2s — treat the game program as gone: release every relay (§10) and log it. Resume normal operation when the beat returns; the game program will send `sync`.

## 9.4 Commands

`hook/set`, `ring/set`, `shortring/set` (Rev 25), `dial/set` (Rev 17) and `ctl/power_cut/set` (Rev 31, §5.4) are acted on immediately and echoed on the state topic — immediately meaning as soon as the MQTT client's loop has returned, in the same pass, and never from inside the client's message callback (Rev 22): an echo published there nests a QoS 1 exchange inside the client's own read, which the library cannot survive. The payload must be exactly `"on"` or `"off"`; anything else is logged and dropped, not read as `"off"` (Rev 7 — the first firmware released the relay on any payload that was not `"on"`, so a malformed command was a silent release). A command received while the game heartbeat is missing is still acted on — the heartbeat's return is the recovery signal, and the command is evidence of it. A command for a circuit whose expander was absent at the scan is logged, with the address it was dropped for, and dropped. This holds whether or not the game program has read ctl/i2c: a game program that consults it and does not send is cleaner, but the firmware does not depend on it.

# 10. Failsafe Summary

Every relay on every board is released — OFFHOOK_n all zero, RING_EN_n all zero — on any of these, independently and without reference to the host:

| **Condition** | **Detected by** | **Action** |
| --- | --- | --- |
| Power-on / reset | Hardware | Relays released by IODIR default and R_pd before the firmware runs (§4.1) |
| Expander /RESET asserted | Firmware (§6.2) | All relays on the chain drop; firmware must have inhibited ring first |
| MQTT connection lost | Client callback / failed publish | Release all relays immediately; keep polling; reconnect |
| Game heartbeat missed twice | 2s timer on `game_heartbeat`, its age taken signed (Rev 21) | Release all relays; log; resume when it returns |
| Trunk ringing for 30s | Per-trunk timer | Release that trunk's ring relay; state → IDLE |
| Required expander absent at boot | I²C scan | Report over MQTT; its relays stay released (§4.1); the generator is not stopped (§1.11) |
| I²C bus fault in service | Three consecutive errors on one device (NAK or read-back mismatch); single errors logged only | Inhibit ring, assert /RESET, rescan, reconfigure, republish ctl/i2c |
| Network firmware update starting | ArduinoOTA start callback (§2.1) | Stop the waveform, release every relay, then write; restart when done or on error |

Each release also ends a switchboard power cut in progress: GPIO15 low (§5.4, Rev 31).

What the firmware cannot do is make the ring bus safe: the generator runs whenever GPIO4 is low, and the only things that stop it are that switch and SD. Nothing on the station or trunk boards can (trunk §15).

# 11. Open Items

- The Next Call button on GPIO36 (Rev 13): debounce, the press event, its `mqtt.md` topic and the game program's handling of it, as an alternative to the page's `game/next/set`. Not yet written, and waiting on hardware: the button is not fitted to the board as built (Rev 16); the circuit is drawn in ring2.
- Nothing in §6 to §10 has yet run against a station or trunk board, because none is built. First bring-up with a board on the chain: scan result on ctl/i2c, IPOL sense, relay drive and echo, ring and seize debounce against the real detectors.
- The concurrent-ring cap value waits on the ring-current measurements in trunk §7.6.
- ~~Dial pulse timing through the real 551 trunk cord circuit and dial~~ — measured 2026-10-05 (Rev 26): breaks 68.7–81.5ms, makes 37.0–41.8ms, 8.4–9.2pps, bounce at break start only, re-closes of 0.96ms at most, inside every §8.2 window and the Rev 24 glitch filter. Still open: the firmware's decode of those digits end to end, which waits on the trunk Rev 5.41 resistors.
- The 1ms /RESET pulse width is chosen as safe, not read from the MCP23017 datasheet; confirm.
- The three-error bus-fault threshold (§6.2) and the two-interval ring threshold (§8.1) are judgement values; revisit both once there is a bus and a switchboard to measure against.
- Read the banner's loop timing — longest pass and longest poll gap — with the broker up and a republish cycle in the window, and confirm the gap stays at the 5ms nominal. From Rev 27 the banner lists each gap of 20ms or more with what ran in it: find what holds the loop when no section accounts for the time, and reproduce the 2026-10-09 degraded state after an outage (Rev 27 change entry) with the Ethernet unplugged for 30s and the serial log running.
