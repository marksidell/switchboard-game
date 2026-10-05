# 551 Switchboard Simulator — Project Index

Current as of 2026-09-25. Update revision numbers here whenever a document changes —
if this file disagrees with a document, the replace step was skipped. Update the revision numbers when a document changes.

## Authoritative files

**Where the documents live, as of 2026-09-25.** Mark moved the project to Claude Code alone. The `.md` documents moved from the Syncthing share `~/s/game/` into the repository's `docs/`, `script.yml` to the repository's top level, and the repository itself from `~/game` to `~/s/sbgame`. Claude Code owns the documents and edits them in place, under version control; there is no chat project and no upload step. The chat-side rules below — writing back, `claude/` subfolders, uploading by hand, what a chat may not produce — are history. The spreadsheets, `digikey_upload.csv` and the datasheets stay in `~/s/game/`.

| File | Rev | Covers |
|---|---|---|
| `station_circuit.md` | **3.44** | Station interface, 8 strips per board, three boards built: 22 stations, the operator tap on board 3 strip 7 (A32 channel 23), and the audience monitor output on board 3 strip 8 (A32 output 24). Rev 3.28 moves operator-connection detection to each circuit's own channel (bin 768) and adds the per-circuit `op` MQTT topic; Rev 3.29 renames the MQTT topic prefix `sw/` → `sbgame/`; Rev 3.30 gives the §9.10 topic table a header and defines host, any and the circuit-id format; Rev 3.31 is formatting only (diagrams and listings fenced); Rev 3.32 adds the ESP32 → host heartbeat; Rev 3.33 names the two host programs (C++ audio, Python game) and assigns every host topic to one; Rev 3.34 moves §3.7 and §9.10–§9.12 out to `mqtt.md` and `control.md`, leaving pointers; Rev 3.35 makes all three boards built and moves the tap from station 8 to station 24 — which left the audience monitor with no A32 output; Rev 3.36 settles it on the Digiface USB’s own analog output, channels 33/34 (§8.8), confirmed on the host at Rev 3.37; Rev 3.38's §9.10 summary follows mqtt.md Rev 5 (the game program also commands the audio program); Rev 3.39 follows the `control.md` rename; Rev 3.40 (Mark, 2026-09-23) moves the monitor to A32 output 24 — balanced, level set by the A32's per-channel reference and trim — and the tap to strip 7, so stations are 1–22; strip 8 fits R2 only and the monitor leaves on a cable soldered to its R7/R8 J2-side pads until the next board revision adds a connector (new §7.9.8, §12); the Digiface route becomes the fallback; Rev 3.41 (Mark, 2026-09-24) makes the tap the monitor's default source rather than its only one — during a game the loudspeaker follows the calling line of the call the operator last answered (§8.8, audio.md Rev 8); no hardware change. Rev 3.42 corrects the P6KE120CA figures in §4.1 and the BOM — 102V standoff, not 120V; 165V clamp; no hardware change. Rev 3.43 adds C19, 100nF from U1 pin 18 (/RESET) to GND, after relay switching reset the expanders on the bench (2026-10-03); bodged on the present boards, a footprint at the next revision. Rev 3.44 names every part by its KiCad designator on the rev 2 board as built — strip parts Rx01 … (x = strip + 1), root parts R101 … — and records the board as built: U2, C7 and R9/R10 removed, R13 and R17 without footprints, C18 not fitted, R105/R106 and J106 fitted. |
| `trunk_circuit.md` | **5.42** | Trunk interface, 8 circuits. Constant-current loop feed, seizure detect, ring relay. Rev 5.30 follows the `sbgame/` prefix and carries the `op` topic in §11.3; Rev 5.31 gives that table the same header and key; Rev 5.32 is formatting only; Rev 5.33–5.34 follow the heartbeat and host-program changes; Rev 5.35 moves §11 out to `control.md` and `mqtt.md`, leaving pointers; Rev 5.36 follows the dial-pulse change; Rev 5.37 the three-board build; Rev 5.38 the `control.md` rename; Rev 5.39 the 22-station count of station Rev 3.40 (§3.3.1, §7.4, §9, §12.1, §12.1.1, §12.5, §13); Rev 5.40 adds C19, the same /RESET filter as station Rev 3.43; Rev 5.41 resizes the seizure detector after the HCPL3700M's DC threshold (3.35–4.05V, not a 1.4V LED drop) left it in its hysteresis band — R_LOOP 220Ω 2W, R_DET 150Ω, R1 unchanged — and records loop compliance measured through the switchboard (§3.3.3); Rev 5.42 names every part by its KiCad designator on the rev 2 board as built (Qx03, Rx06, U101 …) and records the board as built: Cx01 fitted, the address hardwired, R102/R103 fitted, C18 not fitted, U2, C7 and R9/R10 removed. |
| `ring_generator.md` | **72** | Ring generator, H-bridge, and the Olimex ESP32 that is the system's I²C master. Ring output splits at J2 (trunk board) and J6 (switchboard, fused at F2). Rev 51 carries the Antek T1 measurements and the lead/splice record (§9); Rev 52 adds C_OUT, the 1µF output filter across J8 (§9.6), after first power-up showed the raw carrier on the output. Rev 53 and 54 are cross-document only: §15.3 follows station Rev 3.28 and the `sbgame/` prefix. Rev 55 is formatting only — header rows on the §10/§11 tables, diagrams and listings fenced. Rev 56 moves §6.1, §6.2 and §12 out to `control.md`, leaving pointers; Rev 57 follows the three-board build. Rev 58–60 are no design change: §9.7 records the high-frequency-link alternative and why the present design stays, the modulator note, and the stage-2 filter sizing and damping finding. (Index row brought up to date 2026-09-19; the firmware header already cited Rev 60.) Rev 61 follows the `control.md` rename. Rev 62 is cross-reference only: §15 puts the operator tap on station board 3 strip 7 (station Rev 3.40). Rev 63 is a bench record: §9.4's second V_measured, 2026-09-25, on the gate-free firmware with the 74HCT04 — 15.2V RMS drive, 79.3V RMS out, ratio 5.22; Rev 64 points §12.6 at the start-phase verification now recorded in control.md §5.3; Rev 65 records the Olimex as Rev K, checked against its netlist, and assigns GPIO36 to the Next Call button; Rev 66 chooses its circuit — ISP521-1X optocoupler, 2.2kΩ from +12V through the contact. Rev 67 records the §9.7 alternative as drawn to schematic, 2026-09-25: the floating bus needs isolated stage-2 drive (NME2412SC, 6N137, ISP521), the parts chosen, and the defects in the drawing; the present design stays. Rev 68 brings the document into line with the board as built: connectors, MOSFETs and ICs renumbered to the silkscreen, a Board column in §10, the 74HCT04 gate paths as wired (GPIO33 to the left leg through gates 1 and 6), the netlist checked against the schematic, and R_SD_PD2 left off. Rev 69: §3.4 points at the firmware's network update, and records why the Olimex stays on PoE rather than USB power. Rev 70 records R_GS2 and R_GS4 bodged onto the built board, 2026-09-26, across IR2104 LO and COM (§8.4); C_TVS2 waits for the next board revision. Rev 71: the Next Call button is not fitted to this board; §3.2 keeps the circuit as drawn in ring2, switched on the low side. Rev 72 names every part by its reference on the board as built (`kicad/control`), resistors and capacitors included; §9.7 keeps the control2 schematic's. |
| `mqtt.md` | **25** | The MQTT design: broker, the three clients and the status page, `sbgame/` naming, payload conventions, every message tabled by publisher (ESP32, audio program, game program, status page), QoS and retention rules, birth/LWT, both heartbeats and the sync handshake, broker configuration and access list, the page's certificate and name. Rev 2 adds the trunk `digit` event (QoS 0, the only unretained non-command topic); Rev 4 adds `ctl/i2c` and settles the client library; Rev 5 makes the audio program a commanded client — `play/set`, `tone/set`, `listen/set` per circuit, `audio/monitor/set`, `audio/test/<ch>/set`, each echoed as retained state, plus `audio/optone` — adds the `audio/` segment, gives the audio program the game-heartbeat failsafe, and narrows the ESP32's subscriptions to `hook/set` and `ring/set` (firmware check); Rev 6 adds `"busy"` to the `tone` payloads; Rev 7 follows the `control.md` rename; Rev 8 adds `"silence"` to `listen` (end of speech reported); Rev 9 follows station Rev 3.40 — station topics n = 1–22, and `monitor/set`'s unity reference is A32 output 24; no topic or payload added; Rev 10 (2026-09-24) adds the status page of `game_control.md` — the game program's will on `ctl/game_status`, station `name`, the `game/` segment (run, pacing, tallies, eight call slots, log, error; §6.1) and the page's six `game/…/set` commands (§6.2); `game_heartbeat` now carries host Unix time (code check for Claude Code); §9 rewritten — WebSockets listener with `http_dir`, no anonymous clients, an access list holding the page to `sbgame/game/+/set`; Rev 11 makes `game/next/set` a plain command with no payload, at QoS 0 — the second event in the design, after `digit` — in place of Rev 10's call number; Rev 12 adds `board/` — each switchboard jack's label and cabled circuit, 30 station and 10 trunk, from `wiring.yml` — and removes Rev 10's `station/<n>/name`; Rev 13 adds `audio/monitor/source/set` and its echo `audio/monitor/source` — `"tap"` or a circuit id, the receive channel the loudspeaker is fed from — with the audio program returning to the tap on losing the game or the broker; Rev 14 takes the `board/` labels and circuits from script.yml's station entries (`switchboard:`, `label:`) in place of `wiring.yml`, which was never written — trunk jack n carries trunk n, trunk labels empty; no topic change; Rev 15 (Mark, 2026-09-24) puts the page's WebSockets listener under TLS on 443 as `game.kr3am.org` — a Let's Encrypt certificate by the DNS-01 challenge through Route 53, a certbot deploy hook that copies it for Mosquitto and reloads with SIGHUP (a 04:00 restart as the fallback if SIGHUP does not reload it), and the name resolved by a host entry on each router rather than by public DNS or BIND on the host (§9.1, §9.2); no topic change; Rev 16 (Mark, 2026-09-24) resolves `game.kr3am.org` at home from a public A record in Route 53 instead of an OPNsense override, and keeps the Slate 7's Edit Hosts line for the road (§9.2); Rev 18 (2026-09-25) takes the `board/` labels and circuits from script.yml's `jacks:` list — a labelled jack may have an empty circuit; no topic change; Rev 19 (2026-09-25) adds `game/jitter` and `game/jitter/set`; Rev 20 (2026-09-25) adds the Stream Deck program as a client, publishing the page's commands as the new user `sbgame-deck` with the page's access list, writes the access list into §9; `sbgame-web` keeps its write access; no topic change; Rev 21 (2026-09-26) adds `"listen"` to `game/pace` and `pace/set`; Rev 22 (2026-09-27) adds `game/pause` and `pause/set`; Rev 23 (2026-09-30) adds the diagnostics (`game/diag/…`), the chosen next scene (`game/queue`, `game/scenes`), the circuits fitted (`game/stations`, `game/trunks`) and play on the operator tap (`audio/tap/play`), with the access list's two `diag` lines; Rev 24 (2026-10-01) adds `station/<n>/dial/set` and its echo, for the board test; Rev 25 adds `ctl/firmware`. New 2026-09-17, assembled from station §9.7 and §9.10–§9.12 and trunk §11.3–§11.4. |
| `game_control.md` | **27** | Game control and the iPad status page. What a game is (start zeroes the tallies, stop tears every call down), call pacing — manual with a Next Call button, or automatic with the next call `gap` seconds after the current one is connected, shrinking by `ramp` per call to a `floor` — which scene comes next (Rev 2: dealt from a deck shuffled at game start, every scene once before any repeats, reshuffled when empty; `after:` scenes kept out of the deck and started only if the scene they follow was connected; Rev 3: a scene is held back while any of its lines — stations and outside lines — or any of its people is in a call, and a due `after:` scene waits for the same; Rev 4: Next Call is a plain command, guarded by QoS 0 and the page disabling the button until the call starts; Rev 5: the page draws the switchboard as built — three rows of ten station jacks over ten trunk jacks, with the board's labels — from `wiring.yml`, Mark's file mapping circuits to jacks (§6.3), simpler tiles with detail on tap, and a wiring check at commissioning; Rev 6: the audience loudspeaker follows the calling line of the call the operator last answered, switched when she answers rather than when the call starts, and back to the tap at game start and stop — §6.4; Rev 7: `wiring.yml` dropped — each script.yml station entry carries its jack as `switchboard:` and its board label as `label:`, trunk n is on trunk jack n, and the shared script.yml loader checks both keys — §6.3; Rev 8: the page at `https://game.kr3am.org/` over secure WebSockets, following mqtt.md Rev 15 — the scheme taken from the page's own, commissioning checks for the name, the certificate and its reload (§9 steps 1, 2 and 10), and a screen wake lock as an open item; Rev 9 follows mqtt.md Rev 16 on how the name resolves; Rev 11 (Mark, 2026-09-25): a top-level `jacks:` list in script.yml — `jack:`, `label:`, and `station:` if one is cabled — labels every station jack, cabled or not; station entries keep `number:` alone; a labelled uncabled jack is drawn as a working jack at rest — §6.3, §7.1 — and the page gives the board its full width; Rev 12 (Mark, 2026-09-25): `jitter`, each automatic wait drawn evenly from `gap_now × (1 ± jitter/100)`, from the game's seed — §4.3; Rev 13 (Mark, 2026-09-25): the controls move to an Elgato Stream Deck+ driven by `sbgame-streamdeck`, a program of its own — eight keys, the four pacing values on the dials, errors on the touch strip — §7.4, commissioning step 11 — and the page's buttons can be hidden per iPad with a Controls switch, §7.1; Rev 14 (Mark, 2026-09-26): every scene carries a required `active: true|false`, and the game builds, deals and follows active scenes only, so an inactive one needs no wavs; the TTS run still renders it — §4.4, §6.3; Rev 15 (2026-09-26): the Stream Deck commissioned on portland, §9 step 11 passed in full; Rev 16 (Mark, 2026-09-26): a third pacing, listen — the next call `gap` seconds after the board empties, so calls never overlap and every conversation is heard through — and the deck's pacing key cycles the three, showing all three names — §4.2, §7.4; Rev 17 (Mark, 2026-09-27): listen waits its own `pause`, 3s by default, with no ramp or jitter, and leaves auto's four alone; the first dial sets it in listen — §4.2, §7.4; Rev 18 (Mark, 2026-09-28): the page's countdown reads "waiting" while nothing is scheduled, as the deck's Next key does, and that key is lit violet, and in listen the three resting dials are drawn dimmer — §7.1, §7.4; Rev 19 (Mark, 2026-09-28): a conversation line may carry `wait: true`, played only after the operator has spoken on its side, and `person:`, spoken by another cast member on the same side — for a long-distance call through the local operator — §4.6; `after:` chains of any length, one follower per scene — §4.4; Rev 20 (Mark, 2026-09-28): `pause:` and `ringback:` on a conversation line, for the beats in a long-distance call's chain of operators — §4.6; Rev 21 (Mark, 2026-09-28): `ringback:` on either side's trunk, for a long-distance call back — §4.6; Rev 22 (Mark, 2026-09-29): what the player says — `operator:` on each line the game waits for her before, naming a line under a top-level `operator_lines:` or giving its own id and text, and a scene's `closing:` after the last line of a call to the operator or a busy call, rendered in a new cast member `hotel_operator`'s voice for whole-scene recordings and never played by the game — §4.7; Rev 23 (Mark, 2026-09-29): `guest:` on a station jack, the name of whoever is staying in that room, for the operator's guest list card and not read by the game — §6.3; Rev 24 (Mark, 2026-09-30): a call to the operator may ring in on a trunk, for the long-distance operator's time and charges rung through to the hotel once after each billed call — §4.3, §4.6; Rev 25 (Mark, 2026-09-30): diagnostics from the page — off-hook, ring, tone, voice and loudspeaker per circuit and on the tap — a long press on Next Call to choose the next scene, and the game fitted to the circuits built — §4.8, §6.5, §7.5; Rev 26 (Mark, 2026-09-30): the page lists those scenes alphabetically — §4.8; Rev 27 (2026-10-01): the controller's firmware in the health column — §7.1), what counts as connected, success and failure, the eight call slots and the log, and the page: served by Mosquitto from `http_dir` over HTTPS, MQTT.js over secure WebSockets, layout, echo-only display, host clock from the heartbeat, staleness, reconnect on wake. Calls before connection deferred by Mark (§4.5). New 2026-09-24; Rev 1 uploaded to top level by hand the same day, as `audio.md` Rev 1 was, and replaced in place from Rev 2. The game program and `web/` are written to it by Claude Code. |
| `audio.md` | **10** | The audio program specification, C++ on the host: one duplex ALSA stream on the Digiface USB (32 in, 34 out, 48kHz, S32_LE), three threads and two queues, the output mixer (pilot comb, operator tone, one program source per channel), the detector's scheduling and publishing (algorithm stays in station §8.7), file playback from `wav/`, period dial, ringback and busy tones on trunks (600Hz×120Hz dial and busy, 420Hz×40Hz ringback, §8.2 — settled by Mark before first upload; the precise tones are the recorded alternative; busy added the same evening for the busy-number scenarios), energy-based speech detection with own-playback exclusion, the audience monitor chain per station §8.8, the 1kHz test tone, startup/shutdown/failsafe, options, commissioning order and open items (monitor level, capture channel count, tone modulation depth). Rev 2 corrects the ALSA device address: the Digiface is opened by its card id from `/proc/asound/cards`, an alphanumeric string, not `hw:Digiface`; `--card` is now required. Rev 3 is written against the finished program: nine implementation decisions adopted (polled 20ms MQTT loop, 2ms-polled two-slot snapshot mailbox, SCHED_FIFO 70, `--window hann` fallback, broker credentials, sine-referenced dBFS, filename limits, reconnect backoff, wisdom cache) and three code consequences sent back (MQTT loop spins while disconnected; snapshot busy-flag race; `online` published before the first detector pass). Rev 4 records the three fixed and settles the default client id as `sbgame-audio`, matching `sbgame-esp32`; Rev 5 follows the `control.md` rename; Rev 6 makes the listen report the end of speech as well as the start — `"silence"`, a hangover and a maximum speech time as options — with a code consequence for Claude Code (§1.6); Rev 7 follows station Rev 3.40 — tap on channel 23, monitor out on A32 playback 24 instead of Digiface 33/34 (kept as the fallback under a new `--monitor-ch` option), capture 24 unused, stations 1–22 — with a code consequence for Claude Code (§1.7); Rev 8 (Mark, 2026-09-24) lets the monitor take any station or trunk receive channel as its source, on `audio/monitor/source/set`, switched under a 20ms ramp, with `--monitor-src`, `--monitor-tap-trim` and a return to the tap on losing the game (§10.3) — a code consequence for Claude Code (§1.8); the balance between a call's two sides on a circuit source is a bench question (§16); Rev 9 records Claude Code's report that `sbaudio` is at Rev 8 and settles the three questions it raised — the tap trim gets a range of −30 to +30dB with the summed gain left unclamped, state republished on reconnect is the program's current state, and a monitor source the device does not capture is refused — with two small code consequences (§1.9). Rev 10 (2026-09-30) lets the operator tap play a file over its operator tone, `audio/tap/play/set`, for the game program's diagnostics (§1.10). New 2026-09-17. The source is written to this by Claude Code, as `control/control.ino` is to `control.md`. |
| `control.md` | **23** | The controller firmware specification (`esp32.md` until 2026-09-19), one program with three jobs: ring waveform generation, I²C master for the expanders, MQTT client. Startup order, ring constants and start phase, polling and debounce, station and trunk handling, the trunk state machine and cadence, dial pulse detection with standard dial timing (§8.2), and the failsafe table. Rev 4 is written against the finished firmware: four implementation decisions adopted, core 3.x required, MQTT 2.5.3; Rev 5 corrects two Rev 4 slips; Rev 6 follows the firmware file's rename to `control/control.ino` and records that §9.1's by-name subscriptions already meet mqtt.md Rev 5; Rev 7 is written against the reviewed source (2026-09-18): six implementation decisions adopted, two behaviours settled (`seize` unchanged in RING_ON_TRUNK, `ring/set` dropped outside IDLE), and three code consequences sent back — the blocking QoS 1 republish burst that stalls the 200Hz loop, non-`on` payloads read as `off`, and the two behaviours — plus the bench settings to revert before the boards go on the chain; Rev 8 is build state only — the Rev 7 consequences confirmed in the source on 2026-09-19, the duty tables in the 74HCT04 form, the arming-gate bypass now a build option; Rev 9 is the rename to `control.md`, with the firmware to `control/control.ino`; Rev 10 follows station Rev 3.40 — board 3 bits 6 and 7 both unmapped, 22 stations, republish 68 messages over 30 circuits — with a code consequence for Claude Code (the station 23 row comes out of the channel table, §1.10); Rev 11 (Mark, 2026-09-25) removes the arming gate — the trunk ring relays are normally open and released with their expander absent, so the generator runs whatever the scan found, and the bench build goes (§1.11, made in the firmware the same day); Rev 12 records the §5.3 start-phase verification, 2026-09-25, and closes it in §11; Rev 13 lists GPIO36, the Next Call button, in §3, with its behaviour an open item in §11. New 2026-09-17, assembled from generator §6 and §12, station §3.7 and §9.12, trunk §7.5–§7.6 and §11. `control/control.ino` is written to this. Rev 14 follows generator Rev 68: the §3 pin table and the J1/J3 header names as built; comments and banner strings in `control.ino` only. Rev 15 adds network firmware updates (§2.1): ArduinoOTA with a SHA-256 password hash, the board put in its reset state before the first write, restart on error. Rev 16: GPIO36 reserved for Next Call, not fitted. Rev 17 (2026-10-01): a station can dial, `station/<n>/dial/set`, the firmware timing the pulses on the off-hook relay, for testing the trunk board's dial detection (§7.3). Rev 18: the firmware publishes its revision, commit and build time on `ctl/firmware`, stamped by `control/compile` (§9.1). Rev 19 (2026-10-03): each expander's configuration is read back in turn and restored if a reset has cleared it (§6.4), after a hot-plugged board reset the trunk board's and every idle trunk read seized. Rev 20: the loop no longer stalls — TCP_NODELAY on the broker socket, one absent board probed per retry, a 5ms I²C cap — and the banner names the slowest part of the loop. Rev 21: elapsed times taken signed, after a heartbeat stamped later in the same loop pass read as four billion milliseconds old and the failsafe released every relay each second. Rev 22: commands acted on after the MQTT client's loop returns, after a QoS 1 echo published from inside it made the controller drop its broker connection under load. Rev 23: a 100–250ms break before a digit's first pulse spoils the digit, after a make lost between the first two pulses published a 4 as a 2. |
| `script.yml` | — | At the repository's top level (from `~/s/game/` on 2026-09-25). Mark's file: the game's cast, outside lines, stations and scenes. As of 2026-09-25 (`game_control.md` Rev 11) each entry under `stations:` carries its circuit (`number:`, 1–22) alone, and a top-level `jacks:` list gives each station jack on the board (`jack:`, 1–30) its label (`label:`) and, if one is cabled to it, its station (`station:`). Rev 7 had `switchboard:` and `label:` on each station entry instead; Rev 5's `wiring.yml` was never written. Mark adds the labels of the uncabled jacks. From 2026-09-26 (`game_control.md` Rev 14) every scene carries `active: true` or `active: false`; the game plays only active scenes. From 2026-09-29 (`game_control.md` Rev 23) a jack may carry `guest:`, typed on the operator's guest list card. Checks in `game_control.md` §6.3 and `tts_task.md` §3.1. |
| `telephone_bom.xlsx` | — | **The BOM.** Has Have / Need / Buying columns. One source of truth. **Still on the two-board build** (station column headed "Station Boards (x2)", station relays 16, R11/R12 note "board 1 strip 8") — found 2026-09-23 while sweeping station Rev 3.40; the three-board build of station Rev 3.35 and the tap/monitor stuffing of Rev 3.40 are not yet in it. See Open items. |
| `kicad_library_plan.xlsx` | — | Symbol and footprint choices, with what is verified and what is not. |
| `trunk_schematic_guide.md` | — | Drawing guide for the trunk board schematic: five strip blocks and six root blocks, each carrying its own parts and nets. §7 (2026-09-09) carries the PCB netclasses, the HV-to-logic DRC rule, the four-layer stack-up and the full net-to-class assignment. |
| `station_schematic_guide.md` | — | The same for the station board: the eight-instance strip, the tap and monitor strips (board 3 strips 7 and 8 as of station Rev 3.40), and four strip blocks plus six root blocks. |
| `ring_generator_schematic_guide.md` | — | The same for the generator: one flat sheet, six blocks, and designator assignment. Its §4 records the four gaps it found, all fixed at Rev 32. Its designator tables are superseded by the board as built — ring_generator.md §10's Board column, Rev 68. |
| `kicad/lib/switchboard.kicad_sym` | — | Custom symbols: HCPL-3700, SP721, XFMR_TY-311P. The KiCad projects — `kicad/control` (the ring generator board as built), `kicad/control2` (the HF-link alternative, not adopted), `kicad/stations`, `kicad/trunks` — and this library moved into the repository from `~/s/kicad/game/` on 2026-09-28, where the two generator projects were `ring` and `ring2`; renamed that day to follow `control/`; the library tables point at `${KIPRJMOD}/../lib/`, so the tree opens in place on Linux and on Windows (`C:\s\sbgame\kicad`). |
| `control/control.ino` | — | Controller firmware — ring generation, I²C master, MQTT client — written to `control.md`. Folder and file renamed from `ring/esp32.ino` on 2026-09-19, and that from `ring/ring.ino` on 2026-09-17 (Claude Code and Mark), since it has been the whole controller and not the ring generator alone since control.md Rev 4; the oldest change entries across the documents keep `ring/ring.ino` as history, and every `ring/esp32.ino` reference was swept to the new name on 2026-09-19. **Owned by Claude Code as of 2026-09-04** — chat sessions must not output a copy of this file. Read it, quote it, reason about it; do not produce a revised version. |
| `kicad/lib/switchboard.pretty` | — | Custom footprints: XFMR_TY-311P (pads 1/3/4/6, dots on 1 and 4), Triad_SP-70 (now unused — T3 deleted). |

**Filenames are stable and carry no version number.** The revision lives in each
document's title line and change list. When a chat revises a document it writes it back to
the project under the same filename, in place — as of 2026-09-16 chat sessions can read and
replace the project's text documents directly, and the download-then-upload step is gone. That
covers the `.md` documents only. The three blobs — `telephone_bom.xlsx`, `kicad_library_plan.xlsx`,
`digikey_upload.csv` — are still read-only from a chat and are replaced by hand in the UI.
A write replaces the whole document, not a section, so a revision is: read the current copy,
apply the change, write the full text back. Never write a document that was not read in the
same session, and never write one under a new name. A *new* document cannot be created at top
level from a chat — a new bare filename is filed into a `claude/` subfolder — so the first copy
of a new document is uploaded by hand, after which it is replaced in place like the rest.
`audio.md` Rev 1 was the first document to take that route, uploaded by hand on 2026-09-18;
it is replaced in place from Rev 2 on. `game_control.md` Rev 1 is the second, written to
`claude/game_control.md` and uploaded at top level on 2026-09-24; the `claude/` copy is gone.

`551_switchboard_combined_bom.xlsx` was a stale duplicate of the BOM and has been retired.
`station_conversion_checklist.md`, the 2026-09-11 working list for turning the trunk KiCad
project into the station one, retired itself once the station schematic and PCB matched the
station guide; it was removed on 2026-10-05, with the station board built at rev 2. It is in
the git history.

**Document format, as of 2026-09-05.** The three design documents are markdown files:
`ring_generator.md`, `trunk_circuit.md`, `station_circuit.md`. They had carried `.docx` filenames
while already being kept as extracted text, which meant a pandoc build step and a file whose
extension lied about its contents. Renamed in one step at generator Rev 48 with no content change
to the trunk or station documents — the only deliberate exception to the stable-filename rule.
A revision edits the markdown, anchored on heading and paragraph text rather than on paragraph
index. No Word files are produced. The firmware header cites `ring_generator.md` by revision
(Rev 60 as of 2026-09-19) and is Claude Code's to keep current.

## Firmware ownership

`control/control.ino` (until 2026-09-19 `ring/esp32.ino`, until 2026-09-17 `ring/ring.ino`) is maintained through Claude Code, not
through chat sessions. A chat that
edits it produces a file that looks authoritative and is a fork — the divergence is silent,
because both copies compile and both look current. This already happened once: a separate
chat renamed `ring_generator_pwm.ino` to `ring.ino` and rewrote it for Arduino core 3.x,
and the chat side carried on editing a stale copy for several rounds without noticing.

Chat sessions may read the firmware and reason about it. Changes go through Claude Code.
When a document revision has a firmware consequence, the revision says so and the change is
made on the Claude Code side. The specification the firmware is written to is `control.md`
(`esp32.md` until 2026-09-19); the messages it exchanges with the host are `mqtt.md`.

The same rule covers the audio program's source, `sbaudio`, as of 2026-09-17: written by Claude
Code to `audio.md`, not produced or revised in chat. audio.md Rev 3 §1.3 carried three code
consequences for it — the disconnected-loop spin, the snapshot busy-flag race, and `online`
before the first detector pass — all fixed on 2026-09-18 (audio.md Rev 4). control.md Rev 7 §1.7 carried the firmware's own list — the spread republish,
strict `on`/`off` payloads, `seize` kept in RING_ON_TRUNK, `ring/set` dropped outside IDLE, stale
header and comments, and the two bench settings — all in the source as of 2026-09-19 (control.md
Rev 8). The mqtt.md Rev 5 subscription check is closed: the source subscribes to the four §9.1
patterns exactly.

The same rule covers the game program and the status page's `web/` files, as of 2026-09-24:
written by Claude Code to `game_control.md` and `mqtt.md`, not produced in chat.

**Outstanding on the Claude Code side, as of 2026-09-24:** Claude Code reported on 2026-09-24
that `sbaudio` is at audio.md Rev 8, which closes audio.md Rev 6 §1.6 (end-of-speech reporting),
Rev 7 §1.7 (the channel map of station Rev 3.40) and Rev 8 §1.8 (the monitor source). Still open:
control.md Rev 10 §1.10 — the station 23 row out of
the channel table. audio.md Rev 9 §1.9 is closed: Claude Code reported on 2026-09-24 that `sbaudio`
carries the tap trim's range check and refuses a monitor source the device does not capture, at
startup and on the command. The station-number validation in the game program and in the `tts_task.md` loader
(1–23 → 1–22) goes with them. New with mqtt.md Rev 10:
confirm that neither `control/control.ino` nor `sbaudio` rejects a non-empty `game_heartbeat`
payload, now host time; and the game program's side of `game_control.md` plus the page itself.
New with mqtt.md Rev 13 and game_control.md Rev 6: the monitor source in the game program (§6.4)
and on the page (§7.1); the `sbaudio` side is done. `monitor_source_task.md` is the task, written
2026-09-24 and uploaded at top level by hand; the `claude/` copy is gone. The game program and the
page are not started, as of Claude Code's report of 2026-09-24.
New with mqtt.md Rev 17 and game_control.md Rev 10, 2026-09-24: the broker on portland is set up —
certificate, four users, access list, both listeners — and the page is served by nginx, not by
Mosquitto. `broker_setup_task.md` is the task, written 2026-09-24. Mosquitto could not do the job
this host needed: its WebSockets listener will not bind a privileged port, because libwebsockets
creates the socket after the drop from root, and it advertises HTTP/2 in ALPN without being able to
serve it, so a browser would have received nothing. nginx holds the certificate on 443, serves
`/srv/sbgame/web`, and reverse-proxies the page's socket on the path `/mqtt` to a Mosquitto
WebSockets listener on loopback that carries no TLS. The certificate-reload question of mqtt.md
Rev 15 and Rev 16 is withdrawn with it, and so is game_control.md §9 step 10. Consequence for the
page, when it is written: its socket URL takes the path `/mqtt`; nothing else changes. Consequence
for the firmware: the controller's broker username is now `sbgame-control`, changed in
`control/secrets.h` on 2026-09-24, and the board cannot connect until it is reflashed — which also
ships the 74HCT04 duty tables, so that board needs its 74HCT04 fitted first.

New with game_control.md Rev 7: the script.yml loader (`tts_task.md` §3.1, shared with the game
program) checks each station entry's `switchboard:` (present, 1–30, unique) and `label:` (present,
not empty) — game_control.md §6.3. `tts_task.md` itself still lists station numbers as 1–23 and
does not mention the two keys.
New with game_control.md Rev 11 (done 2026-09-25): the loader checks `jacks:` in place of each
station's `switchboard:` and `label:`, and refuses those two on a station entry; the game program
builds the `board/` map from `jacks:`; the page draws a labelled uncabled jack as a working jack.
New with game_control.md Rev 8 and mqtt.md Rev 15: the page's `app.js` connects over `wss://` when
loaded over `https:`, taking the scheme from `location.protocol` (game_control.md §2). Applies when
the page is written.
New with mqtt.md Rev 16: `broker_setup_task.md` sets up Mosquitto on portland to mqtt.md §9 — the
certificate and its deploy hook, the four broker users and the access list, anonymous off in two
stages, and the checks including the SIGHUP reload (game_control.md §9 step 10). Written 2026-09-24
to `claude/broker_setup_task.md`; to be uploaded at top level by hand, as `monitor_source_task.md` was.

## Where the project stands

Parts ordered and mostly arrived. Trunk schematic drawn and checked; trunk PCB placement
begun, strip form factor, roughly 8 × 5 inches for eight strips plus the root section.
Seizure detection verified on the breadboard — 10mV asserted, 3.2V released.

System power settled at generator Rev 28: the switchboard takes 24V as its own leg of the
star from the PSU terminals on Anderson Powerpole, and ring reaches it from the generator's
own J6 through F2. Nothing but ring crosses between the rack and the switchboard on the
generator board.

T1 settled at generator Rev 32: mounted off the board, drive winding to J7 (black 3.50mm) and
output winding to J8 (blue 5.00mm). No symbol or footprint needed for the transformer itself.
**T1 changed at Rev 48.** The OSD Black 70V saturated at 20Hz at the bridge drive level — bench,
2026-09-04, generator §9.5. Replaced by an Antek AS-0522 mains toroid used in reverse, 44V series
winding driven, 230V series winding out; two on hand, measurements pending. Output target is now
70–80V RMS, recorded as the target. The same session confirmed the whole bridge — both drivers,
both bootstraps, both legs, 40kHz carrier at 90% peak duty, zero-crossing handover — with the
drains at 24V and no transformer, before T1 was connected.

**Three station boards, as of 2026-09-17.** The build is no longer staged: all three station
boards are built, and every A32 channel is taken. **As of 2026-09-23 (station Rev 3.40)** board 3's
last two strips are not stations: strip 7 is the operator tap (A32 channel 23) and strip 8 carries
the audience monitor out on A32 output 24, so there are 22 stations. The monitor leaves the present
board on a cable soldered to strip 8's R7/R8 J2-side pads; the next board revision adds a connector.
The Digiface USB's own analog output (playback 33/34, station Rev 3.36) is kept as the fallback.

Firmware complete against `control.md` Rev 4 as of 2026-09-17 — ring generation, Ethernet, the
I²C scan, expander polling, relay control, the MQTT client, the trunk state machine and dial
pulse detection — on Arduino core 3.x only, reviewed against Rev 6 on 2026-09-18 (control.md
Rev 7 §1.7 has the outcome) and brought to Rev 7 on 2026-09-19 (Rev 8 records it). None of the
expander-side code has run against a station or trunk board yet, because none is built.

Audio program written by Claude Code against `audio.md` Rev 2 and reviewed in chat 2026-09-18; `audio.md` Rev 3 adopts its decisions and carried three fixes for the Claude Code side (§1.3), all in as of Rev 4 the same day. Not yet run against the A32. Claude Code reports it at Rev 8 as of 2026-09-24; Rev 9's two small code consequences are with Claude Code.

Status page specified 2026-09-24 (`game_control.md` Rev 1–9, `mqtt.md` Rev 10–16): an iPad page served
by Mosquitto, MQTT over WebSockets, showing the whole bus and running the game. Mosquitto's
`http_dir` confirmed present in the host's man page by Mark. Served over HTTPS as `game.kr3am.org`
as of `mqtt.md` Rev 15, with a Let's Encrypt certificate through Route 53; the name resolves from a public Route 53
record at home and the travel router's host entry on the road (§9.1, §9.2). Not yet written.

## Open items

**Blocking layout**
- ~~Pinout verification~~ **DONE.** Every part the boards depend on is checked against a
  manufacturer drawing: IR2104 (IR PD60046-S), IRLZ44N (IR PD-94831), 74HCT04 (TI SCLS042F),
  74HCT02 (TI SCLS065G, now superseded), SP721 (Littelfuse rev GD 07/10/24), TSR 1-24120
  (Traco 2 July 2026). Document numbers are in
  the Notes column of `kicad_library_plan.xlsx`. The IR2104 was the only one wrong — seven of
  eight pins, from the day generator §8.2 was written until Rev 33
- 2N2222A pinout unverified against physical stock (EBC vs CBE vs ECB) — diode-test it
- D-Sub footprint: NorComp backset is 8.08mm, stock KiCad offsets are 7.70 and 9.40
- OSTTC020162 5.00mm terminal footprint — not 5.08mm. Two of these on the generator now,
  J2 and J6, both in the high-voltage zone with F2 between the secondary and J6

**Bench**
- Compliance sweep: load the current source 0–700Ω, find the knee. Predicted 554Ω,
  station load measured at 330Ω, so margin is 1.7× — the binding case
- Optocoupler release threshold in LED current terms
- Seizure behaviour during ring (the 20Hz pulse train §11 masks)
- TY-311P sweep in the tap configuration — lightly loaded, may show an HF peak (station §7.9.5)
- Sweep 2–3 transformers of the production lot, not one — spread at 9kHz decides whether
  one detection threshold serves all channels
- ~~Antek AS-0522 characterisation~~ — done at generator Rev 51 (2026-09-15/16). Ratio 5.23
  (nameplate), magnetizing 3.10H, leakage 160µH — not low µH, so R_SNB stays at 100Ω.
- Generator §12.6 start-phase verification: firmware change is in `control/control.ino`; the capture
  (first half-cycle through J10 with the rail on the other channel, triggered on SD) is still to be made
- ~~Station R1a/R1b~~ — measured output 78.9V RMS at generator Rev 52; 2 × 10k stands, no station change
- ~~Generator §7.6 F2 reasoning~~ — reworked at generator Rev 51 with measured windings
- Generator §8.5: scope the switch node with C_OUT fitted (new at Rev 52), and confirm C_OUT
  runs cool after an hour — it carries about 0.15A RMS of 40kHz ripple (generator §9.6)
- **Ring current, both figures** (trunk §7.6). Per-trunk with the switchboard connected, and
  the switchboard's own draw when the operator rings one station. This measurement now sizes
  three things: the concurrent-ring cap, trunk F2 (which sits at 71% of rating on the present
  estimate) and generator F2. It also decides whether generator §9.4's no-load trim stands
- Audio commissioning order is `audio.md` §15: clock lock between Digiface and A32 first,
  then channel wiring by test tone, then every level and threshold — including the period
  tones' modulation depth, set by ear (`audio.md` §8.2), and A32 channel 24's reference and
  trim against the loudspeaker amplifier's input sensitivity (§15 step 7), then the tap trim and
  a listen for the balance between caller and called party on a circuit source (audio.md §16)
- Broker to `mqtt.md` Rev 15 §9 — the WebSockets listener under TLS on 443, no anonymous clients,
  the access list, the certificate for `game.kr3am.org` with its IAM user and deploy hook (§9.1),
  the Route 53 A record and the Slate 7's host entry (§9.2) — and the `game_control.md` §9 commissioning checks,
  including the certificate reload (step 10), before the page is first loaded

**Decisions deferred**
- Station §11 counts the tap parts ×8 as footprints; the BOM counts them 2 as purchases.
  Both are defensible, neither is wrong, and they are not the same convention
- TSR 2-2450 maximum output capacitance. Still open — the TSR 1 limit is 470µF against
  10µF on the generator, but that is a different part and a different datasheet — affects the 220µF, and the failure mode is a
  board that will not start with no diagnostic symptom
- ~~A32 output channel for the audience monitor~~ — settled at station Rev 3.36 on Digiface USB
  channels 33/34, and moved at station Rev 3.40 to A32 output 24 (board 3 strip 8); the Digiface
  route is the fallback
- **Monitor connector for the next station board revision** (station §7.9.8, §12). On strip 8's
  J2 side of R7/R8, at the low-voltage edge; type not chosen, not RJ45 and not 6P6C
- **BOM to the three-board build.** `telephone_bom.xlsx` still carries the two-board quantities
  in its station column and "board 1 strip 8" in the R11/R12 note. At station Rev 3.40 the per-strip
  station counts are 22 fitted (relays, Q2, D5, R3, R4, R_pd, C9, ring detector parts), 23 for the
  audio path (T2, C3, R5–R8, TVS1 — the monitor strip fits none of them), R11/R12 on board 3 strip 7,
  and R2 on all 24. Check Have/Need before relying on any station line
- Rack packaging
- Station and generator PCB layout not started. Two 10kΩ pull-ups (R_PWMA_PU, R_PWMB_PU)
  land on the generator at Rev 30 and are only free while it is unrouted
- Powerpole contact gauge for the switchboard 24V run — set by run length and lamp inrush,
  not by the 1A average. Pick the wire first
- Protection for that run. As drawn it is unfused and the LRS-150-24 will source 6.5A into a
  damaged cable. Wants a fuse at the PSU end; not yet sized
- ~~Trunk tone plan~~ — settled 2026-09-17, before `audio.md` Rev 1 was uploaded: the period
  tones (600Hz×120Hz dial and busy, 420Hz×40Hz ringback), not the precise tone plan. `audio.md` §8.2
- ~~Which Digiface jack the loudspeaker amplifier is on~~ — moot at station Rev 3.40: the monitor
  is on A32 output 24
- Calls arriving before the operator has connected the current one — deferred by Mark
  (`game_control.md` §4.5); and the rest of that document's §10

**Not yet bought**
0Ω links (3), Cat5e 300V (9 runs — was 7; the operator tone run was miscounted against the
generator, and both ring bus runs were never counted at all), 6P6C six-conductor cords (3),
PoE switch, Powerpole housings and contacts. Two more OSTTC020162 (4, not 2), one more
0217.250MXP (2, not 1) and one more 649 fuse block (6, not 5) for the generator's F2 and J6 —
none of these are in `digikey_upload.csv`, which covers passives only. A shielded pair and an
XLR (or whatever the amplifier takes) for the monitor cable from station board 3 strip 8.

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
  and each later revision appended to the same wrong place. Moved to §1.2 at Rev 48. Anchor on the
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
