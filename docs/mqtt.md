**551 Switchboard Simulator**

**MQTT Design**

*Rev 50. The changes in each revision are in §12.*

# 1. Overview

Everything that is not audio moves over MQTT. The broker is Mosquitto on the Linux host. These connect to it:

| **Client** | **Program** | **Broker user** | **Connects over** | **Publishes** |
| --- | --- | --- | --- | --- |
| The ESP32 | `control/` firmware | `sbgame-control` | Ethernet, port 1883 | Hardware state and its liveness (§4) |
| The audio program | `sbaudio` | `sbgame-audio` | loopback | Detector results, echoes and its liveness (§5) |
| The game program | `sbgame` | `sbgame-game` | loopback | Commands to the two above (§6), the game's state (§6.1) |
| The page | `engine/web/`, in Safari on an iPad | `sbgame-web` | Wi-Fi, secure WebSockets through nginx | Commands to the game program (§6.2), one to netcheck (§6.3) |
| The Stream Deck program | `sbgame-streamdeck` | `sbgame-deck` | loopback | Commands to the game program (§6.2) |
| The public-address service, netcheck | `sbgame-netcheck` (`sbgame-publicip` before it also watched the public trunk) | `sbgame-host` | loopback | The public address and the public trunk (§6.3) |
| The board test, on the bench only, with no game running | `sbgame-boardtest` | `sbgame-audio`, its default | loopback | `hook/set`, `ring/set` and `dial/set` to the ESP32; its own `game_heartbeat` while the game program is not online, at QoS 0 |
| The play log | `sbgame-mqttlog`, which is `mosquitto_sub` writing to the journal | `sbgame-web` | loopback | Nothing. It records everything but the two heartbeats, and not retained messages replayed on connecting |

`sbgame-sim` (`./run-sim`) stands in for the ESP32 and the audio program when the boards are not there, with a connection for each.

The five that make up the system:

- **The ESP32** — the Olimex ESP32-POE-ISO on the ring generator board, the system's only microcontroller. It owns every relay and every supervisory input on the station and trunk boards, reached over I²C. It connects over Ethernet. Its firmware is specified in `control.md`.

- **The audio program** — C++, on the host. It owns the Ferrofish A32 and the Digiface's own analog output: it drives the 32 A32 outputs and the Digiface's two, which carry the monitor, and reads all 32 inputs. It generates the pilot tones and the operator tone, and runs the pilot detector of station §8.7, and publishes what it detects. It is commanded — to play a file or a tone on a circuit, to listen for speech, to feed the loudspeaker from the operator tap or from a circuit, to put a test tone on a channel — and echoes what it is doing as retained state. It connects over loopback. Its behaviour is specified in `audio.md`.

- **The game program** — Python, on the host. It is the game logic. It commands the ESP32 and the audio program, consumes everything both publish, and publishes the game's own state for the page. During play it is the only client that commands hardware or audio; the board test (above) commands the ESP32 on the bench, with no game running. It connects over loopback. What it does with the page's commands is specified in `game_control.md`.

- **The status page** — one HTML page with its script, in Safari on an iPad, over Wi-Fi. nginx serves its files over HTTPS and proxies its secure WebSockets connection through to Mosquitto (§9). It reads every topic. It commands the game program — start and stop, pacing, the next call (§6.2) — and, with one topic, netcheck (§6.3). It never commands hardware. It is specified in `game_control.md`.

- **The Stream Deck program** — `sbgame-streamdeck`, Python, on the host. It drives an Elgato Stream Deck+ on USB, which carries the game's controls. It reads every topic and publishes the game commands of §6.2 and nothing else, under its own user. The access list gives it the page's rights without the page's line for netcheck (§9). It connects over loopback. It is specified in `game_control.md` §10.

The ESP32 and the host are joined by wired Ethernet, with the ESP32 powered by PoE from the same cable. This replaced a USB serial link: Ethernet is deterministic, unaffected by RF conditions in the room, puts one cable rather than two into the rack, and decouples the controller's position from the host's. The hardware side of that link — the controller board, its PoE budget and the switch — is in station §9.8 and §9.9.

This document specifies the messages: the topic names, who publishes each, what the payload is, and what is retained. The circuit documents own the hardware the messages describe and say only where a message comes from; the ESP32 document owns what the controller does with a command and when it publishes state; the audio document owns the same for the audio program; `game_control.md` owns the same for the game state and the page.

## 1.1 Terms

- **The switchboard**, or **the board**, is the 551 itself. A **station board** or **trunk board** is one of our circuit boards, and is always named in full. A **jack** is a numbered socket on the switchboard.
- A **circuit** is one station or trunk line as the switchboard sees it: stations 1–22 and 24, trunks 1–8. A **strip** is one circuit's position on a station board, eight to a board. The **designation strip** is the switchboard's own label for a jack, which is another thing (§7).
- **Hook** is a station's off-hook relay: `hook` `"on"` is off-hook, loop closed. The game program commands it.
- **Seize** is the trunk's counterpart, and is reported rather than commanded: `seize` `"on"` means the switchboard is drawing loop current on the trunk.
- **Ring** is ring voltage. A station's `ring` reports ring arriving from the switchboard; a trunk's `ring` echoes the ring the trunk board is applying (§4).
- **The tap**, or operator tap, is A32 channel 23, strip 7 of station board 3: a transformer bridged across the operator's tip and ring. It has no relay, no ring detector and no pilot of its own, and is not a circuit.
- The operator is **bridged** to a circuit when her cord key puts her across it, able to hear and speak without breaking it.
- **The comb** is the set of continuous **pilot** tones, one for each circuit, sent on that circuit's output. Which circuit is patched to which is detected from them. `docs/pilot-map.md` has the frequencies.
- **Peer** is the circuit this one is patched to through the switchboard, from the comb pilot heard on its receive channel (§7).
- **Op** is the operator tone heard on a circuit's receive channel, which is how the system knows she is bridged to it.
- **The page** is the status page. **The deck** is the Stream Deck+, and the Stream Deck program is what drives it.
- **The loudspeaker** is the audience's, in the room. **The monitor** is the audio program's feed to it, on the Digiface's channels 33 and 34, and is what the `audio/monitor/…` topics name.

# 2. Design Rules

These hold across every topic. A new topic that breaks one of them needs a reason recorded here.

**One value per topic, as a plain string.** No JSON. A filename, a tone name, a number of seconds and a gain in dB are each still one value. A retained message is one value on one topic, so a station's `ring` and `hook` are separate topics rather than fields of one object. That gives four things:

- The broker holds the last value of each independently, and a subscriber coming up cold gets the whole system's state in one subscription with no sync round trip.
- Every payload stays idempotent (below).
- Wildcard subscriptions stay useful: `sbgame/station/+/hook` is every station's hook state.
- `mosquitto_sub -v -t 'sbgame/#'` on the host shows the whole system's state with no parsing.

The one place a multi-field message would be justified — a set that must change atomically — does not arise: every fact here is independent of every other.

Two game topics stretch this, for display only. `game/log` is one value that is many lines of plain text: it is read whole and never parsed, and splitting it across numbered topics would make the page reassemble what the game program already had in order. A call slot's values (`game/call/<n>/…`) change together when a stage changes, and are still separate topics; the game program publishes them in an order that keeps the page consistent (game_control.md §3.2), which is enough for a display and would not be enough for a control.

**Every message carries absolute state, never a delta.** `"on"` and `"off"`, a circuit id, an uptime, a filename, a gain — never a toggle, never a count, never a relative step. A duplicate delivery is then harmless, which is what lets the interface run at QoS 1. Never add a toggle command: it is not idempotent and would force QoS 2 across the interface. The page's steppers publish the new value, never a step.

A few messages are not state, because they ask for or report an action:

- **Events**, QoS 0 (below) and never retained:
  - `trunk/<n>/digit` (§4): a digit dialled is not a state the trunk is in.
  - `game/next/set` (§6.2): start the next call.
  - `game/more/set` (§6.2): the next part of the tutor's introduction, or the full form of her short prompt.
  - `game/repeat/set` (§6.2): the tutor says her last line again.
  - `host/public_ip/check/set` (§6.3): look the address up now.
- **Pulses**, QoS 1: `trunk/<n>/shortring/set` and `ctl/power_cut/set`, with `game/power_cut/set` that leads to it. A late duplicate acts once more, and §6 says why that is harmless on each.
- **`ctl/sync`**, QoS 1: a request, and a second copy only republishes again.

**QoS 1 for state and commands; QoS 0 for events.** QoS 0 can silently drop a hook command, which is not acceptable for something an operator is waiting on, and QoS 2 buys nothing while every payload is absolute state.

An event is the opposite case: a duplicate is as wrong as a loss, and QoS 1's redelivery on reconnect is exactly how a duplicate would arise. Over a TCP link QoS 0 delivers a message exactly once unless the connection breaks. These are the topics published at QoS 0:

- `trunk/<n>/digit`: a duplicate is a wrong number. If the connection breaks, the trunk state is being resynchronised anyway.
- `game/next/set`: a second copy would start a second call. A copy lost as the page's connection drops costs a second tap, and the operator sees that no call came. The page guards against its own double tap by disabling Next Call until `started` changes (game_control.md §5.1).
- `game/more/set`: a second copy would skip a part of the tutor's introduction. The deck guards its own double press as it does Next Call's.
- `game/repeat/set`: for the same reason, a second copy would say the line twice.
- `host/public_ip/check/set`: a second copy is a second lookup, which netcheck ignores within 5s of the first (§6.3).
- `ctl/game_heartbeat` from the board test only (§1). The game program's is QoS 1.

Subscribing is separate. The ESP32, the audio program, the game program and the board test subscribe at QoS 1. The page and the deck subscribe to `sbgame/#` at QoS 0, as netcheck does to its one command, and so receive everything at QoS 0. A message lost to them as a connection breaks is made good by the retained state on reconnect (§8.4).

**Retain state, never commands.** Retained state means a subscriber sees actual hardware state the instant it subscribes. A retained command is a hazard:

- A retained `hook/set` of `"on"` would close a relay the moment the ESP32 boots, possibly hours after the message was sent and with nothing watching.
- A retained trunk `ring/set` would put 90V on a switchboard line the same way.
- A retained `tone/set` would start ringback on a trunk the moment the audio program starts.
- A retained `game/run/set` would start a game whenever the game program restarted.

The retention column in the tables below is part of each topic's definition, not a per-message choice — the retain flag is set per publish, and a state topic published once without it leaves later subscribers seeing a stale value.

**Clean session on every client.** A persistent session would queue commands during an outage and replay a burst of stale ones at reconnect. Every client resubscribes on connect; the birth-and-sync handshake in §8 recovers state without the replay.

**Low message rate.** The ESP32 publishes debounced state changes only, never raw samples — a ringing station is a 40Hz pulse train at the detector (station §3.7) and one `ring` message on the bus. The audio program publishes detector results on change only, after two consecutive hops agree (audio.md §6.2). A whole call is a handful of messages. Round-trip latency on a local link at QoS 1 is a few milliseconds, negligible against the 150ms ring debounce.

# 3. Topic Naming

Every topic begins `sbgame/`. Two letters were used at first (`sw/`), which could mean switch, software or southwest to anything else that later lands on the same broker; `sbgame/` names the exhibit, is unlikely to collide, and is still one segment so wildcards work unchanged. `sb/` was considered for typing convenience and rejected on the same grounds — the prefix is typed once into each codebase and thereafter comes from shell history.

Below the prefix:

- `station/<n>/…`, n = 1–22 and 24, and `trunk/<n>/…`, n = 1–8 — per-circuit topics, whichever client publishes or consumes them. Station board 3's strip 7 is the operator tap (station §7.9.6) — no relay, no ring detector, no pilot of its own — and has no topics. Strip 8 is station 24, a real telephone (control.md §7.4); it was the audience monitor output until then. n is the circuit's own number, not the 1–32 comb slot of station §8.3, which exists so one formula maps a circuit to its FFT bin and is internal to the audio program's detector.
- `audio/…` — the audio program's non-circuit state and commands: the loudspeaker monitor and its source, the test tone per output channel, the tap's own-tone check. Channel numbers under `audio/test/` are 1–34 output channels as the documents number them (audio.md §2), not circuits.
- `game/…` — the game program's own state, and the page's commands to it: the run state, pacing, tallies, call slots and log. Call slot numbers under `game/call/` are 1–8 and are not circuits.
- `board/station/<n>/…`, n = 1–30, and `board/trunk/<n>/…`, n = 1–10 — the switchboard's own jacks, numbered as on the board. They are not circuits. A jack carries at most one circuit, named in its `circuit` topic.
- `ctl/…` — system-level control and liveness.
- `host/…` — facts about the host itself that the page shows, from netcheck rather than the game program: its public address and the public trunk (§6.3).

A **circuit id**, wherever a payload carries one, is the string `station/<n>` or `trunk/<n>` — the same two segments as the topic, so prefixing a circuit id with `sbgame/` gives that circuit's topic root. A slot number never appears on the wire.

A command topic is the state topic it commands with `/set` appended: `hook` is a station's hook state, `hook/set` commands it; `play` is what a circuit is playing, `play/set` commands it. The consuming client echoes the resulting state on the state topic, so a subscriber watching `hook` or `play` sees the command take effect and can tell a command that was acted on from one that was not.

Some commands have no state topic of the same name, and the tables say where each one shows:

- `shortring/set` shows on `ring`.
- `game/next/set` shows as `game/started` going up by one, `game/more/set` on `game/tutor/intro`, or `tutor/repeat` and `tutor/more`, and `game/repeat/set` as the line itself.
- `game/record/set`, `game/playback/set` and `game/power_cut/set` show on `audio/record`, `audio/playback` and `ctl/power_cut`, since the game program passes them on.
- `host/public_ip/check/set` shows as `host/public_ip/checked` changing.

# 4. Messages Published by the ESP32

The ESP32 publishes hardware state as it debounces it (`control.md` §7 and §8) and its own liveness. The game program, the page, the deck and the play log subscribe to all of it.

| **Topic** | **Payload** | **Retained** | **Meaning** |
| --- | --- | --- | --- |
| `sbgame/station/<1-22, 24>/ring` | `"on"` or `"off"` | yes | Ring voltage is arriving at this station from the switchboard. Debounced from the 40Hz detector pulse train, station §3.7. |
| `sbgame/station/<1-22, 24>/hook` | `"on"` or `"off"` | yes | Off-hook relay state, echoed from the relay drive. `"on"` is off-hook (loop closed). |
| `sbgame/station/<1-22>/dial` | digits, or `""` | yes | The digits a `dial/set` has still to finish, the one being sent included; empty when the station is not dialling (control.md §7.3). |
| `sbgame/station/24/lifted` | `"on"` or `"off"` | yes | The real telephone on station 24 is off-hook. From its hook detector, 100ms stable, held while `ring` is on (control.md §7.4). Station 24 also has `ring` and `hook` as above; `hook` there is the relay that connects the line to A32 channel 24, not the line's loop. |
| `sbgame/trunk/<1-8>/seize` | `"on"` or `"off"` | yes | The switchboard has seized this trunk — loop current is flowing. Debounced, trunk §11.1. The trunk analogue of a station's `hook`. |
| `sbgame/trunk/<1-8>/ring` | `"on"` or `"off"` | yes | This trunk's ring relay is energised — the trunk board is applying ring toward the switchboard. Actual relay state, echoed back, so a monitoring UI can show a ringing trunk. A `shortring/set` shows as one `"on"` and `"off"` 1s apart. |
| `sbgame/trunk/<1-8>/digit` | `"0"` to `"9"` | no — and QoS 0, §2 | The operator has just dialled this digit on the seized trunk. One message per completed digit, in order; ten pulses is `"0"`. Decoded by the firmware from the seizure input, control.md §8.2. Never published outside seizure, never for a partial digit. |
| `sbgame/trunk/<1-8>/fault` | `""`, `"ring_on_trunk"` or `"bad_dial"` | yes | `"ring_on_trunk"`: the operator has applied ring to this trunk by mistake (trunk §5.2). `"bad_dial"`: a pulse train outside the dial timing windows, or more than ten pulses (control.md §8.2). Empty clears either. |
| `sbgame/ctl/power_cut` | `"on"`, `"hold"` or `"off"` | yes | The switchboard's 24V is cut: `"on"` from the moment GPIO15 goes high to the moment it goes low again, 1s later unless ended early (control.md §5.4); `"hold"` while it is held off, until `"off"`. Published with the birth message and on change. |
| `sbgame/ctl/status` | `"online"` or `"offline"` | yes | Birth message and last will (§8). |
| `sbgame/ctl/esp_heartbeat` | uptime in seconds | no | Every 1s from the main loop, after the I²C poll (§8). |
| `sbgame/ctl/i2c` | `"ok"` or `"missing: "` + absent addresses in hex, e.g. `"missing: 0x22 0x23"` | yes | Result of the boot-time expander scan, republished after any rescan (control.md §4.2, §6.2). While it reads missing, commands for circuits on the absent board are dropped. |
| `sbgame/ctl/firmware` | `"control.md Rev <n>, <commit>, built <date>"` | yes | Which firmware is running: the revision of control.md it implements, the git commit it was built from (`-dirty` if `control/` had uncommitted changes, `unknown` if built without `control/compile`), and its build time in UTC. Published with the birth message (control.md §9.1). |

The trunk topics are not the station topics with a different noun. A station is commanded off-hook and reports ring arriving; a trunk is commanded to ring and reports seizure. There is no hook to set on a trunk and a station has no ring command. `ring` keeps its name on both but inverts in meaning: on a station it reports ring received, on a trunk it echoes the ring the trunk board is applying. `seize` is the trunk analogue of `hook`.

# 5. Messages Published by the Audio Program

The audio program publishes what its pilot detector finds, per circuit; the state of everything it has been commanded to do, as the echo of each command; and its own liveness. It never commands anything. The game program, the page, the deck and the play log subscribe. What each state means in detail, and when it changes, is `audio.md` §6 to §11.

| **Topic** | **Payload** | **Retained** | **Meaning** |
| --- | --- | --- | --- |
| `sbgame/station/<1-22, 24>/peer` | circuit id, `""`, `"ambiguous"` or `"deaf"` | yes | Which circuit this station is patched to through the switchboard, from the comb pilot heard on its receive channel (station §8.7). See §7 for the four values. |
| `sbgame/trunk/<1-8>/peer` | circuit id, `""`, `"ambiguous"` or `"deaf"` | yes | The same for a trunk. |
| `sbgame/station/<1-22, 24>/op` | `"on"` or `"off"` | yes | The operator tone (bin 768) is heard on this station's receive channel — the operator is bridged to it. |
| `sbgame/trunk/<1-8>/op` | `"on"` or `"off"` | yes | The same for a trunk. |
| `sbgame/station/<1-22, 24>/play`, `sbgame/trunk/<1-8>/play` | base filename, `""` or `"missing"` | yes | The file now playing on this circuit's output. Empty when nothing is — which is how a file's finishing is reported (audio.md §7.4). `"missing"`: the last `play/set` named a file that could not be loaded; persists until the next `play/set`. |
| `sbgame/audio/tap/play` | base filename, `""` or `"missing"` | yes | The file now playing on the operator tap's output, over the operator tone, as `play` for a circuit (audio.md §7). |
| `sbgame/trunk/<1-8>/tone` | `"dial"`, `"ringback"`, `"busy"`, `"reorder"` or `""` | yes | The tone now playing on this trunk. Empty when none. |
| `sbgame/station/<1-22, 24>/listen`, `sbgame/trunk/<1-8>/listen` | `"listening"`, `"speech"`, `"silence"`, `"timeout"` or `""` | yes | The listen on this circuit as it runs: `"listening"` from the command; `"speech"` when speech starts, and the listen continues; `"silence"` when it ends, which finishes the listen; `"timeout"` if speech never started within the commanded seconds or never ended within the program's cap. The final value persists until the next `listen/set`; empty after a cancel (audio.md §9.1). |
| `sbgame/station/<1-22, 24>/ringing` | `"on"` or `"off"` | yes | 20Hz ring heard on this station's capture channel, which in practice means ring sent to it while it is off-hook, when its ring detector does not see it (audio.md §9.5). `"off"` at start. On change only. |
| `sbgame/trunk/<1-8>/ringing` | `"on"` or `"off"` | yes | 20Hz ring heard on this trunk's capture channel, which is how the public line's ATA ringing the switchboard is known, with a ring every 6s of about 2s (audio.md §9.5). `"off"` at start. On change only. |
| `sbgame/audio/monitor` | `"off"` or gain in dB | yes | The loudspeaker feed: muted, or the gain applied, as a signed decimal string. Echoes `monitor/set` after clamping to range (audio.md §10.2). |
| `sbgame/audio/monitor/source` | `"tap"` or circuit id | yes | The receive channel the loudspeaker is fed from: the operator tap, or that station's or trunk's. Echoes `monitor/source/set` once the switch is made; `"tap"` after the program loses the game or the broker (audio.md §10.3, §13.2). |
| `sbgame/audio/monitor/peer` | `"auto"` or dB | yes | The loudspeaker's peer boost: measured, or fixed at this figure. Echoes `monitor/peer/set`; `"auto"` at start and after the program loses the game (audio.md §10.8, §13.2). |
| `sbgame/audio/monitor/play` | base filename, `""` or `"missing"` | yes | The file now playing on the loudspeaker, summed into the monitor, as `play` for a circuit (audio.md §10.4). |
| `sbgame/audio/record` | base name, `"off"` or `"failed"` | yes | The loudspeaker recording: the file being written, `<YYYY-MM-DD-HH-MM-SS>` without `.wav`; `"off"` when none; `"failed"` when the last `record/set` `"on"` could not open a file, until the next (audio.md §10.6). |
| `sbgame/audio/recordings` | lines of `<name> <seconds>`, or `""` | yes | The ten newest recordings, newest first, each with its length in whole seconds; not the one being written. Republished when a recording stops (audio.md §10.7). |
| `sbgame/audio/playback` | base name, `""` or `"missing"` | yes | The recording playing on the loudspeaker in place of the monitor; empty when none, which is how its end is reported. `"missing"`: the last `playback/set` named one that could not be played, until the next (audio.md §10.7). |
| `sbgame/audio/test/<1-34>` | `"on"` or `"off"` | yes | A 1kHz test tone is on this output channel, displacing everything else on it (audio.md §11.1). |
| `sbgame/audio/optone` | `"ok"` or `"deaf"` | yes | The tap's own operator tone is returning on its own receive channel (station §8.4). `"deaf"` means no circuit can hear the operator either. |
| `sbgame/ctl/audio_status` | `"online"` or `"offline"` | yes | Birth message and last will (§8). |

`peer` and `op` come from the same `identify_peer()` result and are independent facts: the operator can listen in on a connected call (`peer` set, `op` on), answer a station patched to nothing else (`peer` empty, `op` on), or be absent from either. When the operator is bridged across a connected pair, both ends report `op` on, which is correct and not a fault.

The `op` topic is per circuit rather than one set-valued topic on the operator's side because detection is per circuit (station §8.7), because a per-circuit topic is single-valued like every other state topic, and because the game program can then subscribe to `sbgame/+/+/op` and get a retained `"on"` or `"off"` per circuit rather than diffing successive lists to learn who joined or left.

`play` and `tone` are never both non-empty on one circuit: a circuit plays one thing at a time, and commanding the other replaces it (audio.md §5.2). To know what a circuit is doing, read both.

# 6. Messages Published by the Game Program

The game program is the only client that commands the audio program, and during play the only one that commands the ESP32: the board test publishes `hook/set`, `ring/set` and `dial/set` too, on the bench with no game running (§1). The consumer column says which of the ESP32 and the audio program subscribes to each; the other does not, and must not use a wildcard that would deliver the other's commands to it.

| **Topic** | **Payload** | **Retained** | **Consumer** | **Meaning** |
| --- | --- | --- | --- | --- |
| `sbgame/station/<1-22, 24>/hook/set` | `"on"` or `"off"` | no | ESP32 | Take this station off-hook / on-hook. On station 24, connect the real telephone's line to A32 channel 24 / disconnect it. The ESP32 echoes the result on `hook`. |
| `sbgame/station/<1-22>/dial/set` | digits `0`–`9`, at most 16, or `""` | no | ESP32 | Dial them on this off-hook station, the controller timing the pulses; `""` stops. Published by `sbgame-boardtest` only. Echoed on `dial`. |
| `sbgame/trunk/<1-8>/shortring/set` | `"on"` or `"off"` | no | ESP32 | Ring this trunk once, for 1s, then leave it idle and able to see a seizure (`control.md` §8.4); `"off"` cancels the burst. Echoed on `ring`. Not absolute state: a late duplicate rings once more, which the switchboard's latching trunk signal makes harmless (§12.26). |
| `sbgame/trunk/<1-8>/ring/set` | `"on"` or `"off"` | no | ESP32 | Start / stop ringing this trunk. The ESP32 runs the cadence and the 30s timeout (`control.md` §8) and echoes the relay state on `ring`. |
| `sbgame/station/<1-22, 24>/play/set`, `sbgame/trunk/<1-8>/play/set` | base filename, or `"stop"` | no | audio | Play `<wav-dir>/<name>.wav` on this circuit's output, replacing whatever it is playing; `"stop"` stops it. Echoed on `play`; finishing is `play` going empty. |
| `sbgame/audio/tap/play/set` | base filename, or `"stop"` | no | audio | Play a file on the operator tap's output, over the operator tone, which is never displaced; `"stop"` stops it. Echoed on `audio/tap/play`. Only the game program's diagnostics use it (game_control.md §11.4). |
| `sbgame/trunk/<1-8>/tone/set` | `"dial"`, `"ringback"`, `"busy"`, `"reorder"` or `"off"` | no | audio | Play this tone on the trunk until told otherwise; a new value replaces the current tone. Trunks only — a station is the telephone and sends none of them. Echoed on `tone`. |
| `sbgame/station/<1-22, 24>/listen/set`, `sbgame/trunk/<1-8>/listen/set` | timeout in seconds, or `"0"` | no | audio | Listen on this circuit's receive channel, allowing this long for speech to start; `"0"` cancels. The sequence — start of speech, then end or timeout — is reported on `listen`. |
| `sbgame/audio/monitor/set` | `"off"` or gain in dB | no | audio | Feed the monitor's source to the loudspeaker at this gain, 0 being unity into the Digiface's channels 33 and 34, range −60 to +20; or mute. Echoed on `monitor`. |
| `sbgame/audio/monitor/source/set` | `"tap"` or circuit id | no | audio | Feed the loudspeaker from this receive channel: the operator tap, or a station 1–22 or 24 or trunk 1–8. The game program sends the calling line when the operator answers a call, and `"tap"` when a game starts or stops (game_control.md §9.1). Echoed on `monitor/source`. |
| `sbgame/audio/monitor/peer/set` | `"auto"` or dB | no | audio | The called party's boost on the loudspeaker: `"auto"`, measured by the audio program, or a figure, 0 to its `--monitor-peer-max`. The game program sends it just before each `monitor/source/set`, `"6"` at a free call's answer and `"auto"` otherwise (game_control.md §9.1). Echoed on `monitor/peer`. |
| `sbgame/audio/monitor/play/set` | base filename, or `"stop"` | no | audio | Play a file on the loudspeaker, summed into the monitor under its gain; `"stop"` stops it. Echoed on `audio/monitor/play`. The game program's tutor (game_control.md §7). |
| `sbgame/audio/record/set` | `"on"` or `"off"` | no | audio | Start or stop recording the loudspeaker feed; on stop the program makes an MP3 beside the WAV. Echoed on `audio/record`. Sent by the game program on `game/record/set` (audio.md §10.6). |
| `sbgame/audio/playback/set` | a recording's base name, or `"stop"` | no | audio | Play that recording on the loudspeaker in place of the monitor, replacing one already playing; `"stop"` stops it. Echoed on `audio/playback`. Sent by the game program on `game/playback/set` (audio.md §10.7). |
| `sbgame/audio/test/<1-34>/set` | `"on"` or `"off"` | no | audio | 1kHz test tone on this output channel. Echoed on `test/<ch>`. |
| `sbgame/ctl/game_heartbeat` | host Unix time in seconds | no | ESP32, audio, the page and the deck | Every 1s from the game loop (§8). The ESP32 and the audio program use its arrival only; the page and the deck also take the host's clock from it. |
| `sbgame/ctl/sync` | — | no | ESP32 | Ask the ESP32 to republish every state topic (§8). |
| `sbgame/ctl/power_cut/set` | `"on"`, `"hold"` or `"off"` | no | ESP32 | Cut the switchboard's 24V for 1s, which drops every relay and lamp on it, a trunk's locked signal among them; `"hold"` cuts it until `"off"`; `"off"` ends either. Echoed on `ctl/power_cut`. Sent when a game stops, and on `game/power_cut/set` (game_control.md §2, §10). Not absolute state: a duplicate during the cut is ignored, a late one cuts once more. |

There is no `peer/set`, `op/set` or `optone/set` and never will be: topology is detected, not commanded. There is no `sync` for the audio program: its state topics are all either detector results, which it republishes on change and on start, or echoes of commands it holds, which it republishes on reconnect (§8.4).

## 6.1 Game State

Published by the game program for the page, the deck and the play log. All retained. What each value means, and when it changes, is `game_control.md` §2 to §9.

| **Topic** | **Payload** | **Retained** | **Meaning** |
| --- | --- | --- | --- |
| `sbgame/ctl/game_status` | `"online"` or `"offline"` | yes | Birth message and last will (§8.1). |
| `sbgame/board/station/<1-30>/label`, `sbgame/board/trunk/<1-10>/label` | text, or `""` | yes | The label on this switchboard jack, such as `"463"` or `"lobby"`: the `label:` of the script.yml `jacks:` item for this jack, whether or not a station is cabled to it. Empty for a station jack `jacks:` does not list, and for every trunk jack. Published at start. |
| `sbgame/board/station/<1-30>/circuit`, `sbgame/board/trunk/<1-10>/circuit` | circuit id, or `""` | yes | The game circuit cabled to this jack, such as `"station/11"`: the `number:` of the station that this jack's `jacks:` item names as its `station:`, or `trunk/n` on trunk jack n for n = 1–8. Empty otherwise, including for a labelled jack with nothing cabled. Published at start. |
| `sbgame/game/run` | `"on"` or `"off"` | yes | A game is running. Echoes `run/set`. |
| `sbgame/game/pace` | `"tutor"`, `"manual"`, `"auto"` or `"listen"` | yes | Call pacing. Echoes `pace/set`. |
| `sbgame/game/gap` | seconds | yes | Automatic pacing: the gap from a call's connection to the next call's start, at the start of a game. Echoes `gap/set` after clamping. |
| `sbgame/game/ramp` | seconds | yes | Seconds taken off the gap for each call connected. Echoes `ramp/set`. |
| `sbgame/game/floor` | seconds | yes | The least the gap can fall to. Echoes `floor/set`. |
| `sbgame/game/jitter` | percent | yes | The spread of each automatic wait around `gap_now`: each is drawn evenly from `gap_now × (1 ± jitter/100)`. Echoes `jitter/set`. |
| `sbgame/game/pause` | seconds | yes | Listen pacing: the wait from the board emptying to the next call, the same every time. Echoes `pause/set` after clamping. |
| `sbgame/game/gap_now` | seconds | yes | The gap in use now, after the ramp: the centre of the jitter's spread. |
| `sbgame/game/next_at` | host Unix time in seconds, or `""` | yes | When the next call will start, after the jitter's draw; empty when none is scheduled. |
| `sbgame/game/started` | integer | yes | Calls started this game. Goes up by one when `next/set` starts a call. |
| `sbgame/game/success` | integer | yes | Calls that ran to their scripted end this game. |
| `sbgame/game/fail` | integer | yes | Calls that failed this game. |
| `sbgame/game/call/<1-8>/number` | integer, or `""` | yes | The call number in this slot. |
| `sbgame/game/call/<1-8>/scene` | scene id, or `""` | yes | The scene in this slot; empty when the slot is free. |
| `sbgame/game/call/<1-8>/from`, `…/to` | line name, or `""` | yes | The calling and called lines from script.yml. `to` is empty for a call to the operator. |
| `sbgame/game/call/<1-8>/trunk` | circuit id, or `""` | yes | The trunk carrying the call, once known. |
| `sbgame/game/call/<1-8>/stage` | stage name, or `""` | yes | `signalling`, `request`, `routing`, `dialling`, `ringing`, `busy`, `talking` or `operator` (game_control.md §3.2). |
| `sbgame/game/call/<1-8>/since` | host Unix time in seconds, or `""` | yes | When the stage began. |
| `sbgame/game/call/<1-8>/deadline` | host Unix time in seconds, or `""` | yes | When the stage times out; empty if it does not. |
| `sbgame/game/call/<1-8>/digits` | digits, or `""` | yes | Digits dialled so far on an outgoing call. |
| `sbgame/game/scenes` | scene ids, one per line | yes | The scenes that can be chosen as the next one: active, without `after:`, and within the circuits fitted (game_control.md §6.4). Published at start. |
| `sbgame/game/sweep` | `"trunks"`, `"stations"` or `""` | yes | The board sweep running, `""` when none is. Echoes `sweep/set` (game_control.md §11.5). |
| `sbgame/game/queue` | scene id, or `""` | yes | The chosen next scene, until it is dealt, cleared or the game stops. Echoes `queue/set`. |
| `sbgame/game/tutor/intro` | `"<n>/<of>"`, or `""` | yes | The part of the tutor's introduction she is on, `"1/3"` to `"3/3"`; `""` when she is not introducing the board (game_control.md §7). |
| `sbgame/game/tutor/repeat` | a key under script.yml's `tutor:`, `brief-<key>` for a short form, or `""` | yes | The tutor's line Repeat Help would say: the last she finished while the game waits on the player, until the player acts or she says another; a "Say:" prompt included (game_control.md §7). |
| `sbgame/game/tutor/more` | a key under script.yml's `tutor:`, or `""` | yes | The full line More Help would say: set while the short form of that line, the last she finished, is repeatable (game_control.md §7). |
| `sbgame/game/tutor/waiting` | `"more"`, `"next"` or `""` | yes | The tutor has finished speaking and waits for More Help or Next Call (`"more"`), or for Next Call alone (`"next"`); `""` otherwise. The deck flashes the key (game_control.md §7). |
| `sbgame/game/stations`, `sbgame/game/trunks` | integer | yes | How many stations (0–22) and trunks (0–8) are fitted, from the configuration (game_control.md §12.2). Published at start. |
| `sbgame/game/public_trunk` | integer | yes | The trunk the ATA feeds, the public line, from the configuration (game_control.md §8). Published at start. |
| `sbgame/game/diag/<target>/<test>` | `"on"` or `"off"` | yes | A diagnostic's state: `<target>` is `station/<1-22, 24>`, `trunk/<1-8>` or `tap`; `<test>` is `hook` (stations), `ring` (trunks), `tone`, `voice` or `monitor` (game_control.md §11.4). All `"off"` at start. |
| `sbgame/game/log` | text | yes | The last 50 events, newest first, one per line (game_control.md §12.3). |
| `sbgame/game/error` | text, or `""` | yes | The last page command the game program rejected, and why; cleared by the next accepted command. |

## 6.2 Messages Published by the Status Page and the Stream Deck

The commands of the page and the deck, consumed by the game program only. The Stream Deck program publishes these same commands, the ones its keys and dials carry. Neither publishes anything else under `game/`, and the broker enforces that (§9). The page's one command outside this table is in §6.3.

| **Topic** | **Payload** | **Retained** | **Consumer** | **Meaning** |
| --- | --- | --- | --- | --- |
| `sbgame/game/run/set` | `"on"` or `"off"` | no | game | Start a game — ignored while one is running — or stop it. Echoed on `run`. |
| `sbgame/game/pace/set` | `"tutor"`, `"manual"`, `"auto"` or `"listen"` | no | game | Call pacing. Echoed on `pace`. `"tutor"` is refused on `error` while any of the tutor's lines has no wav (game_control.md §7). |
| `sbgame/game/gap/set` | seconds | no | game | Starting gap for automatic pacing, 0–600. Echoed on `gap`. |
| `sbgame/game/ramp/set` | seconds | no | game | Reduction per call connected, 0–60. Echoed on `ramp`. |
| `sbgame/game/floor/set` | seconds | no | game | Least gap, 0–600 and not above `gap`. Echoed on `floor`. |
| `sbgame/game/jitter/set` | percent | no | game | Spread of the automatic wait, 0–100. Echoed on `jitter`. |
| `sbgame/game/pause/set` | seconds | no | game | Listen's wait after the board empties, 0–60. Echoed on `pause`. |
| `sbgame/game/record/set` | `"on"` or `"off"` | no | game | Start or stop recording the loudspeaker. The game program passes it on as `audio/record/set`; refused on `error` while the audio program is offline, and `"on"` while a recording plays back. Allowed with or without a game. Its effect shows on `audio/record` (game_control.md §11.6). |
| `sbgame/game/playback/set` | a name from `audio/recordings`, or `"stop"` | no | game | Play a recording on the loudspeaker, or stop. Passed on as `audio/playback/set`; refused on `error` while a game runs or a recording is being made (but `"stop"`), or while the audio program is offline. Its effect shows on `audio/playback` (game_control.md §11.6). |
| `sbgame/game/sweep/set` | `"trunks"`, `"stations"` or `"off"` | no | game | Start a board sweep, or stop one. Refused on `error` while a game runs (game_control.md §11.5). |
| `sbgame/game/queue/set` | scene id, or `""` | no | game | Deal this scene next, or clear the choice. Refused on `error` if not in `game/scenes`. Echoed on `queue`. |
| `sbgame/game/repeat/set` | ignored | no | game | Repeat Help: the tutor says her last line again. QoS 0, an event (§2). Refused on `error` when `tutor/repeat` is empty. |
| `sbgame/game/more/set` | ignored | no | game | More Help: the next part of the tutor's introduction, or, while `tutor/more` is set, the full form of her short prompt. QoS 0, an event (§2). Refused on `error` when she is not introducing the board and no short prompt waits. Its effect shows on `tutor/intro`, or `tutor/repeat` and `tutor/more`. |
| `sbgame/game/diag/<target>/<test>/set` | `"on"` or `"off"` | no | game | Start or stop a diagnostic (game_control.md §11.4). Refused on `error` for a circuit in a call or not fitted. Echoed on `diag/<target>/<test>`. |
| `sbgame/game/power_cut/set` | `"on"`, `"hold"` or `"off"` | no | game | `"on"`: cut the switchboard's power for 1s, to clear lamps and buzzers left on, during a game or not. `"hold"`: switch it off until `"off"` switches it on. Passed on as `ctl/power_cut/set`; refused on `error` while the controller is offline, and `"hold"` while a game runs. Its effect shows on `ctl/power_cut` (game_control.md §10, §11.7). |
| `sbgame/game/next/set` | ignored | no — and QoS 0, §2 | game | Start the next call now, if a game is running and a scene can be dealt; otherwise reported on `error`. Shows as `started` going up by one. |

## 6.3 Messages Published by the Public-Address Service

Not the game program: `sbgame-netcheck`, a program of its own on the host, user `sbgame-host` (§9). It looks the host's public address up from `https://checkip.amazonaws.com/` when it connects, every 5 minutes after, and when the page asks, but no sooner than 5s after the last. Each lookup publishes all three state topics, in this order. It has no birth message or will: a `checked` time that has stopped moving is how the page sees it gone.

| **Topic** | **Payload** | **Retained** | **Meaning** |
| --- | --- | --- | --- |
| `sbgame/host/public_ip` | an IPv4 or IPv6 address, or `""` | yes | The address the last good lookup found. `""` until one has succeeded. A failed lookup leaves it as it was. |
| `sbgame/host/public_ip/checked` | host Unix time, whole seconds | yes | When the last lookup was made, good or not. |
| `sbgame/host/public_ip/error` | `""`, `"offline"`, or a few words | yes | `""` if the last lookup succeeded. `"offline"` if it failed and neither `1.1.1.1` nor `8.8.8.8` accepts a TCP connection on port 443 within 3s. Else why not: `"timed out"`, `"HTTP 503"`, `"not an address"`, or the network's reason. |

The public trunk, looked at every 10s and on connecting:

| **Topic** | **Payload** | **Retained** | **Meaning** |
| --- | --- | --- | --- |
| `sbgame/host/public_trunk` | `registered`, `disconnected`, `offline` or `error` | yes | The trunk 8 ATA's FXS 1 registration, from the `Port 1:` line of its `status` over SSH. `registered` if it reads `Registered`, `disconnected` if `Not Registered` or anything else. `offline` if the ATA does not answer — no name, no route, refused, or 5s without a connection. `error` for anything else that stops the look: a host key that is not the pinned one, a refused login, no credentials file, a session that does not finish in 15s, an answer with no `Port 1:` line. |
| `sbgame/host/public_trunk/checked` | host Unix time, whole seconds | yes | When the last look was made. |

A refused login is not tried again for 5 minutes: the ATA locks an account out after repeated failures.

The page's command, consumed by `sbgame-netcheck` only:

| **Topic** | **Payload** | **Retained** | **Consumer** | **Meaning** |
| --- | --- | --- | --- | --- |
| `sbgame/host/public_ip/check/set` | ignored | no — and QoS 0, §2 | netcheck | Look the address up now. Shows as `checked` changing. Within 5s of the last lookup, ignored. |

# 7. Payload Conventions

**`"on"` and `"off"`** are the only two values of every binary topic. Lower case, no quotes on the wire.

**Circuit id** is `station/<n>` or `trunk/<n>`, §3.

**Monitor source** on `monitor/source/set` and `monitor/source` is a circuit id or the literal `"tap"`, which is not a circuit id: the tap has no circuit topics (§3). Same convention as the `peer` diagnostics below.

**`peer` has four values**, and a subscriber must handle all of them:

- a circuit id — connected to that circuit;
- empty payload — idle, not patched to anything. Published retained, an empty payload deletes the retained value at the broker, so a cold subscriber sees nothing rather than a stale id. The same convention as `fault`;
- `"ambiguous"` — more than one comb pilot heard: a threshold, crosstalk or cord fault, station §8.7. A diagnostic, not a topology;
- `"deaf"` — the circuit cannot hear its own pilot: a fault in its own transmit path, transformer or cabling. Also a diagnostic.

The two diagnostics are literal strings on the same topic, rather than a separate status topic, so that a subscriber that treats anything non-empty as a circuit id fails loudly in the log rather than silently in the game. `play` uses the same convention for `"missing"`.

**Empty payload on a retained topic** means "clear": it removes the retained value. Every retained topic whose table above lists `""` uses it. On `listen`, empty is cancelled or never issued; a listen that completed reads `"silence"` or `"timeout"`, never empty, so the two are not confused.

**Filenames** on `play/set` and `play` are the base name only — no directory, no `.wav`, no path separator. The audio program rejects a payload containing `/` or `..`. `"stop"` is reserved as the stop verb on `play/set`, so no file may be named `stop`. It is the one place a filename and a verb share a topic; the alternative, a separate `play/stop` topic, would break the `/set` convention for one command.

**Tone names** on `tone/set` and `tone` are `"dial"`, `"ringback"`, `"busy"` and `"reorder"`, lower case. What each sounds like is audio.md §8.2; a new tone is a new name here and a row there.

**Gain in dB** on `monitor/set` and `monitor` is a signed decimal string: `"0"`, `"-12"`, `"6.5"`. No unit suffix, no `+`. The audio program clamps to its range and echoes what it applied, so the state topic may differ from the command.

**Seconds** on `listen/set` are a non-negative decimal string, capped by the audio program at 300. `"0"` is cancel. Seconds on the game's pacing topics are the same form; the game program clamps to the ranges in §6.2 and echoes what it applied.

**Host time** on `game_heartbeat`, `next_at`, `since` and `deadline` is Unix time in seconds as a decimal string, to a tenth of a second at most: `"1790000000.4"`. It is the host's clock, and the page measures every duration against it, not against its own.

**Integers** on the tallies and `number` are unsigned decimal strings with no leading zeros.

**Labels** on `board/…/label` are the text on the switchboard's designation strip, as the `label:` of a script.yml `jacks:` item gives it, UTF-8, no length rule beyond what fits a tile.

**Line names** on `from` and `to` are the keys of script.yml's `stations:` and `outside:` maps, as written there.

**The log** is plain UTF-8 text, lines separated by `\n`, newest first, at most 50 lines.

**Heartbeats** carry uptime in seconds on the ESP32 side, so a log shows a reboot, and host time on the game side.

**Digits** are one character each, `"0"` to `"9"`, one message per digit, on `trunk/<n>/digit`. The game program assembles them into a number: the firmware does not know how many digits to expect and does not need to. A digit is an event (§2), so the topic is never retained (a retained digit would replay into a later call) and a subscriber arriving mid-number has missed the earlier digits; there is nothing to resynchronise from, which is the cost recorded in §11. The game program's call slot `digits` carries the number so far for display, so the page does not depend on having seen every digit event.

# 8. Liveness and Recovery

Three clients have a will: the ESP32, the audio program and the game program. They have three different ways of dying, and the broker sees none of them the same way. This section is the protocol; what each client does about it is in that client's own document (`control.md` §9 for the controller, `audio.md` §13 for the audio program, `game_control.md` §2 and §11.2 for the game program and the page).

## 8.1 Birth and Last Will

The ESP32 connects with a **last will and testament** (LWT) of `"offline"` on `sbgame/ctl/status`, retained, and immediately publishes `"online"` to the same topic itself — the birth message. A last will is a message the broker holds on the client's behalf and publishes only if the client disappears without disconnecting cleanly: the TCP connection drops, or the keepalive pings stop. While the ESP32 runs, the topic reads `online`; the moment the broker loses it, the topic flips to `offline` with nothing on the ESP32's side having to act.

The audio program does the same on `sbgame/ctl/audio_status`. It exists because `peer` and `op` are retained: an audio program that has died leaves the last topology it saw on the broker looking current, and the game program must treat those values as stale while `audio_status` is `offline`. The same applies to `play`, `tone` and `listen`: a `"listening"` that outlives the audio program will never resolve, and the game program should treat every audio state topic as stale, and every wait on one as failed, while `audio_status` is `offline`.

The game program does the same on `sbgame/ctl/game_status`, for the same reason: `game/run`, the tallies and the call slots are retained, and a game program that has died leaves them on the broker looking current. The page treats every game topic as stale while `game_status` is `offline`, and disables its controls. The game heartbeat already told the ESP32 and the audio program the same thing; the will tells the page promptly without it having to time the beats, and the page times the beats as well (game_control.md §11.2).

Set the ESP32's MQTT keepalive to 5s so the broker notices a lost controller promptly and fires the will.

## 8.2 Two Heartbeats, and Why Both

The LWT is a notification, not a failsafe: it tells the host the controller has gone, but it cannot open a relay. Nothing on the host can. So the ESP32 must release every relay on its own when it loses contact, and there are two distinct ways contact can be lost:

— **Network or broker loss.** The ESP32 sees its MQTT connection drop and releases all relays immediately. The keepalive also lets the broker fire the LWT.

— **Game program dead with the broker healthy.** The connection stays up and nothing looks wrong from the ESP32's side. This is what `sbgame/ctl/game_heartbeat` is for: the game program publishes it every second from its game loop, and if the ESP32 misses two consecutive beats it releases all relays even though MQTT is healthy. Without it a crashed game program leaves stations held off-hook indefinitely, tying up switchboard cord circuits and presenting to the operator as a hardware fault. On the trunk side the same failure leaves a trunk ringing, which is why the ESP32 also runs a 30s hard ring timeout of its own (`control.md` §8).

The audio program subscribes to the same heartbeat and applies the same rule: two missed beats, or loss of the broker, stops every trunk tone and every file it is playing and cancels every listen (audio.md §13.2). The failure is the audio twin of the held relay — a crashed game leaving ringback on a trunk for as long as the program runs. The pilots, the operator tone and the monitor are not stopped; they were not started by the game and are harmless without it. The monitor's source returns to the tap, since the calls a circuit source was following have been torn down.

The same argument runs the other way. The ESP32's keepalive proves its network stack is alive, not that its main loop is polling the expanders and driving relays — and whether those are the same thing depends on the MQTT client. With a client whose ping is sent from the main loop, a wedged loop stops the ping and the LWT fires. With a client that runs in its own task, as ESP-IDF's does, a wedged loop keeps the connection alive indefinitely: the host sees `online`, commands `hook/set`, and nothing happens. The only symptom would be that the echoed `hook` never changes.

So the ESP32 publishes `sbgame/ctl/esp_heartbeat` every second **from the main loop, after the I²C poll**, so that it proves the loop that matters and not the network task. The game program treats two consecutive missed beats as ESP32-down: it stops issuing commands, marks every circuit unknown, puts it on screen, and publishes `sync` when the beat returns.

The ESP32 heartbeat is also the periodic reassurance that retained state is current. A retained value is what the ESP32 last said, not what the hardware is doing now; the beat proves the loop that would have said otherwise is running.

The audio program has a will but no heartbeat. Its main loop is the audio callback, and if that stops the A32 stream stops with it — a louder failure than a wedged ESP32 loop, and one the game program can already see from `audio_status` and from `peer` values that stop changing.

That reasoning is weaker now that the program has an MQTT thread separate from its audio thread (audio.md §3): the MQTT thread can hold the connection open while the audio thread is wedged, and then a `listen` never resolves and a `play` never clears. Until §11 settles whether it gets a heartbeat, the game program applies its own deadline to anything it waits on from the audio program — the listen timeout plus a margin, the file's known length plus a margin — and treats a missed deadline as audio-program-down.

The page has neither a will nor a heartbeat. Nothing depends on it being there: it commands only the game and netcheck, and a page that vanishes mid-game leaves the game running on its own pacing, which is the right outcome. The Stream Deck program has neither, for the same reason.

## 8.3 Sync

`sbgame/ctl/sync` asks the ESP32 to republish every state topic it owns. The game program publishes it when `ctl/status` transitions to `online` and when `esp_heartbeat` returns after an outage, and the two sides are back in step without any replayed commands. The ESP32 also republishes all state every 30s of its own accord (`control.md` §9.2), which bounds how long a lost publish can leave a retained value stale. Subscribers must therefore react to changes in value, not to the arrival of a message.

## 8.4 Recovery Sequence

On ESP32 connect: LWT registered, `status` = `online`, subscribe to `hook/set`, `dial/set`, `ring/set` and `shortring/set` for every circuit, `ctl/power_cut/set`, `game_heartbeat` and `sync` — those seven patterns and not a wildcard over every `set`, since the audio program's commands share the circuit topics — then publish every state topic once. Relays are all released at that point regardless, since the ESP32 releases them on any loss of contact and boots with them released.

On game program start: connect with its will of `"offline"` on `game_status`. Publish its game state:

- `run` `"off"`, pacing values from its configuration, tallies zero;
- every call slot cleared, `next_at` and `error` cleared, the log with one start line;
- every `board/` label and circuit;
- `scenes`, `queue`, the `tutor/…` topics cleared, `stations` and `trunks`;
- every diagnostic `"off"`, `sweep` cleared.

Then `game_status` = `"online"`, state before birth as the audio program does. Then subscribe to everything, read the retained state, publish `sync` to be sure, start the heartbeat. If `status` reads `offline`, wait — commands sent now go nowhere and are not queued (clean session). If `audio_status` reads `offline`, the same for audio commands. A game program that restarts never resumes a game; the page starts a new one.

On audio program start or reconnect, publish in this order:

1. `play` and `listen` empty for every circuit, `tone` empty for every trunk, `audio/tap/play` and `audio/monitor/play` empty; `monitor`, `monitor/source` and `monitor/peer` as configured; `test/<ch>` off for every channel; `ringing` off for every station and trunk; `audio/record`, `audio/recordings` and `audio/playback`.
2. `peer`, `op` and `optone` from the first detector pass.
3. `audio_status` = `online`.

State before birth, so a subscriber that sees `online` already has consistent values (audio.md §12). Nothing it was doing before a broker loss survives it: tones and files were stopped when the connection dropped (§8.2), so the empty `play` and `tone` published on reconnect are true.

On page connect or reconnect: subscribe to `sbgame/#`. The retained topics are the whole state; there is nothing to ask for. The Stream Deck program does the same.

# 9. Broker Configuration

Mosquitto on the Linux host, portland, with two listeners — plain MQTT for every client but the page, and plain WebSockets on loopback for the page, which reaches it through nginx — no anonymous clients, and an access list. On Ubuntu, in `/etc/mosquitto/conf.d/sbgame.conf` (`host/` holds the installed copy); the distribution's own `mosquitto.conf` already sets persistence and the log and includes that directory.

```text
per_listener_settings false
allow_anonymous false
password_file /etc/mosquitto/passwd
acl_file /etc/mosquitto/acl

listener 1883
protocol mqtt

listener 9001 127.0.0.1
protocol websockets
```

Mosquitto cannot serve the page itself on this build (§12.17): libwebsockets creates the WebSockets socket after the drop to the `mosquitto` user, so a privileged port will not bind, and the listener advertises HTTP/2 in ALPN without being able to serve it, which a browser negotiates by default. nginx does both jobs instead, and Mosquitto's WebSockets listener carries no TLS and is bound to loopback, so nothing off the host can reach it.

**nginx**, `host/etc/nginx/sites-available/sbgame`, is the authority on its own configuration. What matters to the protocol is one thing: it terminates TLS on 443 for `game.kr3am.org` and proxies the exact path `/mqtt` to Mosquitto's WebSockets listener on loopback, `127.0.0.1:9001`, so the page's connection is `wss://game.kr3am.org/mqtt`. The certificate, the name and nginx's own settings are in `host/README.md`.

**The access list**, `/etc/mosquitto/acl`. A user with no line can do nothing. The ESP32, the audio program and the game program have the whole tree. The page and the Stream Deck program read everything and write only the game's commands. The board test connects as `sbgame-audio` and the play log as `sbgame-web`; neither has a user of its own.

```text
user sbgame-control
topic readwrite sbgame/#

user sbgame-audio
topic readwrite sbgame/#

user sbgame-game
topic readwrite sbgame/#

user sbgame-web
topic read sbgame/#
topic write sbgame/game/+/set
topic write sbgame/host/public_ip/check/set
topic write sbgame/game/diag/+/+/+/set
topic write sbgame/game/diag/tap/+/set

user sbgame-host
topic readwrite sbgame/host/#

user sbgame-deck
topic read sbgame/#
topic write sbgame/game/+/set
topic write sbgame/game/diag/+/+/+/set
topic write sbgame/game/diag/tap/+/set
```

The two `diag` lines are the diagnostics: a station's or trunk's, `game/diag/station/3/tone/set`, and the tap's, `game/diag/tap/tone/set`. They are two and one levels deeper than `game/+/set` covers. They still reach the game program only; the page cannot command the hardware.

`sbgame-host` is the public-address service (§6.3): it writes its own segment and reads only its own command. The page's `host/public_ip/check/set` line lets it ask for a lookup, which changes nothing on the board; the deck does not have it.

The page keeps its write line: its controls can be hidden on an iPad but not removed (game_control.md §11.1). The deck's password is in `/etc/sbgame/mqtt-deck.pass`, 640, group `sbgame-deck`, like the others.

# 10. How the Design Got Here

Recorded so the reasoning survives the move from the circuit documents, whose change lists carry the originals.

- The link was USB serial until station Rev 3.1 and MQTT over PoE Ethernet since.
- The trunk topics were once specified as the station topics with a different noun (station Rev 3.x, corrected at trunk §11.3 and station §14.0): a trunk has no hook to set and needs a ring command.
- Operator detection moved from the tap strip's receive channel to every circuit's own channel at station Rev 3.28, which is where the per-circuit `op` topic comes from, and what makes it single-valued.
- The prefix changed from `sw/` to `sbgame/` at station Rev 3.29.
- The topic tables gained headers, the `host → broker` wording became `host → any`, and the circuit-id format was specified at station Rev 3.30; the `peer` diagnostics `"ambiguous"` and `"deaf"` were specified at Rev 3.28.
- The ESP32 → host heartbeat was added at station Rev 3.32 after a reader asked where it was; the game → ESP32 one had existed alone since the MQTT link was introduced, on a keepalive argument that was correct but never written down, and that has a gap once written down (§8.2).
- The two host programs were named and every host topic assigned to one at station Rev 3.33, along with `audio_status`. Before that "the host", "the audio process" and "the game logic" were used interchangeably, and station §8.7's Python listing invited reading the detector as part of the game program. It is C++, in the audio program.
- The audio program became a commanded client at Rev 5, when `audio.md` was written. Until then its only output was the detector, and the game had no way to make a sound. Every command took the `/set`-and-echo shape already in use rather than a request/response pair, so that a restarted game can read what the audio program is doing from retained state alone.
- The status page arrived at Rev 10, with `game_control.md`. It talks MQTT over WebSockets rather than to a server in the game program, so it shows what the bus reports and survives the game program's failure; the game program gained a will and published state to feed it, and the broker gained an access list, because the page's password cannot be kept secret.
- The loudspeaker's source became a command at Rev 13. Until then it was fixed on the operator tap, and the audience lost each conversation when the operator rang the called party and left the call.
- The page's listener took TLS at Rev 15, as `game.kr3am.org` with a Let's Encrypt certificate issued through Route 53, and the name resolved by the routers rather than by public DNS or a resolver on the host. At Rev 16 the home side moved to a public A record in Route 53; the travel router keeps its host entry.

# 11. Open Items

- `digit` is an event and so cannot be recovered after a game-program restart mid-number, and cannot be made idempotent. The alternative considered was a retained `sbgame/trunk/<n>/dialled` carrying the accumulated digit string since seizure, cleared to empty on seizure and release — absolute state, idempotent, QoS 1, and a cold subscriber sees the digits so far. It was not adopted because the number's length and meaning belong to the game program, and because a game restart mid-dial is a situation the game cannot recover from anyway. Revisit if that turns out to matter. (The call slot's `digits`, covers the page's need for display.)
- Whether the audio program gets a heartbeat of its own, `sbgame/ctl/audio_heartbeat`, published from the audio thread once a second after a detector hop so that it proves the thread that plays and listens rather than the one that talks to the broker — the ESP32's argument in §8.2 applied to the audio program. Not added because the game's own deadlines on `listen` and `play` cover the cases that matter and the pilots stopping is visible anyway; add it if a wedged audio thread is ever seen with `audio_status` still online.
- Whether the audio program should accept `listen/set` on the tap channel, which always carries the operator's voice. audio.md §16.
- The page's commands can grow. Calls before connection would be one more value on `game/pace` (game_control.md §5.5), and timeouts from the page more `sbgame/game/…/set` topics (game_control.md §14), each covered by the access list's existing pattern.
- The page has only one user, `sbgame-web`, and anyone on the network who loads it can run the game. Hiding its controls does not change that; only the access list could. Acceptable at the bench and behind the travel router. For a public event where the Wi-Fi is shared, a second, private page could hold the password.
- Moving past Mosquitto 2.x: what it means for this system is the `per_listener_settings` and password-file defaults. The WebSockets listener carries MQTT alone, which is not marked for removal.

# 12. Revision History

## 12.50 Changes in Rev 50

— `sbgame/game/public_trunk` added (§6.1), following game_control.md Rev 105, 2026-10-31. An addition; no existing topic or payload changes.

## 12.49 Changes in Rev 49

— `sbgame/trunk/<1-8>/ringing` added (§5), from the audio program, following audio.md Rev 36, 2026-10-31: `"on"` while 20Hz ring is heard on the trunk's capture channel. An addition; no existing topic or payload changes.

## 12.48 Changes in Rev 48

— Correct and readable, Mark's request, 2026-10-30, as `game_control.md` Rev 99. The document follows the code where the two differed, the code being what has been played. §1 has a table of every client that connects, where it said three. §1.1 Terms is new. A short ring is 1s, not half a second (§4). Only `"hold"` is refused during a game on `game/power_cut/set` (§6.2). Station 24 is a diagnostic target and a monitor source (§6, §6.1). §2 lists the event commands and every QoS 0 topic, and says the page and the deck subscribe at QoS 0. The page also commands netcheck, and the deck does not (§1, §6.2). The board test also commands the ESP32 (§1, §6). `ctl/game_heartbeat` is consumed by the deck too. The start-up lists of §8.4 are complete, and the command topics without a state topic of their own are listed (§3).

— §8.3 and §11 settle what `control.md` §9.2 has settled: the ESP32 republishes every 30s. The bridge arming on `ctl/i2c`, the named scene and `http_dir` go. The monitor rows are together in §5 and §6.

— §9.1 The Certificate and §9.2 The Name move to `host/README.md`, with what §9's nginx block explained. The block itself goes, to `host/etc/nginx/sites-available/sbgame`, which it had drifted from: it had `location /mqtt` where the site has `location = /mqtt`. §9 keeps the listeners, the access list and what nginx does for the protocol. Revision numbers leave the body, as in `game_control.md` Rev 97; §10 keeps its own, being a history. Topics and behaviour are unchanged.

— No code consequence.

## 12.47 Changes in Rev 47

— The document made readable, Mark's request, 2026-10-30, as `game_control.md` Rev 95. The line under the title had grown into a list of topics and now gives only the revision. The changes in each revision move out of the Overview to this section at the end of the document, newest first, where Rev 27 to Rev 46 had been in descending order after Rev 26. The text of each entry is unchanged except for references to the renumbered sections, and wording that said an entry was "above". A new revision is added at the top of this section, and the line under the title changes only its number.

— No code consequence.

## 12.46 Changes in Rev 46

— `sbgame/station/<1-22, 24>/ringing` added (§5), from the audio program, following audio.md Rev 30, 2026-10-26: `"on"` while 20Hz ring is heard on the station's capture channel. The ESP32's `station/<n>/ring` does not see ring on a station held off-hook, which is what the player sends when she rings the caller of a call between rooms (game_control.md §7.7, Rev 89). An addition; no existing payload changes.

## 12.45 Changes in Rev 45

— `sbgame/audio/monitor/peer/set` and its echo `sbgame/audio/monitor/peer` added (§5, §6), following audio.md Rev 29, 2026-10-25. The payload is `"auto"` or a boost in dB for the called party on the loudspeaker (audio.md §10.8). The game program publishes it just before each `monitor/source/set`: `"6"` at a free call's answer, `"auto"` otherwise (game_control.md Rev 86). A new topic rather than a second value on `monitor/source/set`, so the one-value rule of §2 holds.

## 12.44 Changes in Rev 44

— The audio program treats station 24 as a circuit (§5, §6), following audio.md Rev 24, 2026-10-23: `station/24/peer`, `op`, `play` and `listen`, their `set`s, and `"station/24"` as a monitor source, a peer and a circuit id, as for stations 1–22. Rev 43's note that it did not is withdrawn. The monitor moves to the Digiface's analog output, so `monitor/set`'s unity is into channels 33 and 34. Additions; no existing payload changes.

## 12.43 Changes in Rev 43

— Station 24, a real telephone on station board 3 strip 8 (§3, §4, §6), following control.md Rev 33 and real_phone.md Rev 2, 2026-10-23. The ESP32 publishes `station/24/ring` and `station/24/hook` as for any station, and one new topic, `station/24/lifted`: `"on"` while the phone is off-hook. It takes `station/24/hook/set`, which connects the phone's line to A32 channel 24, and drops `station/24/dial/set`. Station numbers are now 1–22 and 24; 23, the operator tap, still has no topics. An addition; no existing topic or payload changes. Rev 44 adds station 24's audio topics.

## 12.42 Changes in Rev 42

— The public trunk is asked over SSH, not through the ATA's web interface (§6.3), 2026-10-23. The web interface keeps one session for the whole device, whatever the account: Rev 41's look every 10s, as `admin` and then as `viewer`, logged Mark out of the ATA's pages each time. An SSH session leaves them alone (Mark, 2026-10-23). The ATA's command shell takes no remote command, so the service sends `status` and `exit` on stdin and reads the `Port 1:` line, `On Hook<TAB>Registered` or `Not Registered`. SSH takes the `admin` account only. The password reaches ssh through SSH_ASKPASS, the service's own program reading `/etc/sbgame/ata.cred`, and the ATA's host key is pinned in `/etc/sbgame/ata-known_hosts`, which replaces Rev 41's pinned certificate. The topics and their four values are unchanged.

— Code consequence, for Claude Code: `engine/sbgame/ata.py` rewritten, `--ata-known-hosts` in place of `--ata-cert` in `netcheck.py`, the test, and the known-hosts file in `host/`.

## 12.41 Changes in Rev 41

— The public trunk's registration (§6.3), following game_control.md Rev 72, Mark's request, 2026-10-23. `sbgame-netcheck` also looks every 10s at the Grandstream ATA that feeds trunk 8 (trunk_circuit.md §4.5), `switchboard.sidell.org`, through the JSON API its own web pages use — `/cgi-bin/dologin`, the password base64-encoded as the login page sends it, then `/cgi-bin/api.values.get` for `P4921`, FXS 1's registration — and publishes `host/public_trunk` and `host/public_trunk/checked`, retained. It logs in as the ATA's read-only `viewer` account, since the ATA keeps one session per account and an `admin` login would end the administrator's web session at every look. Its login is in `/etc/sbgame/ata.cred`, and its certificate is pinned (`host/README.md`). A look at a device on the LAN, not the game program's business, and the service already writes `host/#`, so the access list does not change. Topics added; nothing removed or changed.

— The service is renamed `sbgame-netcheck`, from `sbgame-publicip`, since it now looks at more than the address (Mark, 2026-10-23): its unit, program, module and client identifier. Its user, `sbgame-host`, and every topic stay as they were.

— Code consequence, for Claude Code: `engine/sbgame/ata.py`, its run loop in `netcheck.py` (was `publicip.py`), the test, the unit's new name, and the certificate and credentials file in `host/`. On the host, the old unit is disabled and removed and the new one enabled.

## 12.40 Changes in Rev 40

— `host/public_ip/error` gains one fixed value, `"offline"` (§6.3), following game_control.md Rev 71, Mark's request, 2026-10-23: the page says "offline" when portland cannot reach the internet, and "error" for any other failure, so the service has to tell the two apart. After a failed lookup it tries a TCP connection to `1.1.1.1` and then `8.8.8.8` on port 443, by number, 3s each. If neither answers, the error is `"offline"`. If either does, the internet is there and the error is the lookup's own reason, as before; a DNS fault alone is not offline. A value added to an existing topic; nothing removed or changed.

— Code consequence, for Claude Code: `online()` and `Looker` in `engine/sbgame/publicip.py`, and its test.

## 12.39 Changes in Rev 39

— The host's public address on the page, following game_control.md Rev 68, Mark's request, 2026-10-22. A fourth host program, `sbgame-publicip`, asks `checkip.amazonaws.com` for portland's public address every 5 minutes and publishes it under a new top-level segment, `host/` (§3): `host/public_ip`, `host/public_ip/checked` and `host/public_ip/error`, retained (§6.3). The page asks for a lookup now with `host/public_ip/check/set`, QoS 0, an event like `game/next/set`. It is a program of its own, and not part of the game program, because a lookup is a call out of the house, and the game makes no network calls during a session; the certificate renewal's calls to Let's Encrypt and Route 53 on their own timer are the precedent. A failed lookup reaches the page and nothing else.

— The access list (§9) gains a user, `sbgame-host`, with `sbgame/host/#` and nothing else, and one write line for the page, `sbgame/host/public_ip/check/set`: the first page command that does not go to the game program. It commands a lookup and nothing on the board. The deck does not get it. §6.3 sits under §6 so that §7 onwards keep their numbers. Topics added; nothing removed or changed.

— Code consequence, for Claude Code: `engine/sbgame/publicip.py` and its test, the page's two health rows, the unit, the user and the ACL in `host/`.

## 12.38 Changes in Rev 38

— The switchboard held off, following control.md Rev 32 and game_control.md Rev 65, 2026-10-20: `ctl/power_cut/set` and `game/power_cut/set` gain `"hold"`, the switchboard's 24V cut until `"off"`, and `ctl/power_cut` reads `"hold"` while it is. `game/power_cut/set` gains `"off"` too. For the page's Switchboard power button. A value added to three topics; nothing removed.

## 12.37 Changes in Rev 37

— The switchboard power cut, following control.md Rev 31 and game_control.md Rev 63, 2026-10-19. To the ESP32, from the game program (§6): `ctl/power_cut/set`, `"on"` to drop the switchboard's 24V for 1s, `"off"` to end the cut early. From the ESP32 (§4): its echo, `ctl/power_cut`, retained. From the page and the Stream Deck (§6.2): `game/power_cut/set`, which the game program passes on, refusing it while a game runs, so the game program stays the only client that commands the ESP32 (§1). The access list already covers both: the deck and the page write `sbgame/game/+/set`, and the game program reads and writes `sbgame/#`. The ESP32 subscribes to one more pattern.

— It is under `ctl/` rather than a new top-level segment: it is not about a circuit, and the switchboard as a whole has no other topic. Like `shortring/set` it is a pulse, not absolute state: a late duplicate cuts the power once more, which on a stopped board is harmless, and a duplicate during the cut is ignored.

## 12.36 Changes in Rev 36

— Recording the loudspeaker and playing a recording back, following audio.md Rev 22 and game_control.md Rev 61, 2026-10-18. From the audio program (§5): `audio/record`, the file being written, `"off"` or `"failed"`; `audio/recordings`, the ten newest; `audio/playback`, the recording playing. To it, from the game program (§6): `audio/record/set` and `audio/playback/set`. From the page (§6.2): `game/record/set` and `game/playback/set`, which the game program passes on, so the game program stays the only client that commands audio (§1).

## 12.35 Changes in Rev 35

— `"reorder"` added to the `tone/set` and `tone` payloads (§5, §6), following audio.md Rev 20 and game_control.md Rev 56, 2026-10-17: the fast busy, for a number dialled with too many digits or too few. One more value on an existing topic; no new topic.

## 12.34 Changes in Rev 34

— `game/tutor/more` added (§6.1), following game_control.md Rev 55, 2026-10-17: the full line More Help would say for the short prompt the tutor last finished, or `""`. `game/more/set` is now accepted outside the introduction while it is set. `game/tutor/repeat` may name a short form, `brief-<key>`. All additions; no existing topic or payload changes.

## 12.33 Changes in Rev 33

— `game/sweep/set` and its echo `game/sweep` (§6, §6.1), following game_control.md Rev 50, 2026-10-17: the Stream Deck starts or stops a sweep of the trunks or the stations. Covered by the existing `game/+/set` in the access list. All additions; no existing topic or payload changes.

## 12.32 Changes in Rev 32

— `trunk/<n>/shortring/set` rings for 1s, not 0.5s (§6), following control.md Rev 30, 2026-10-10: one of the switchboard's trunk jacks did not latch on 0.5s. No topic or payload changes.

## 12.31 Changes in Rev 31

— `game/repeat/set` and `game/tutor/repeat` added (§6.1, §6.2), following game_control.md Rev 34, 2026-10-09: Repeat Help. `repeat/set` is an event at QoS 0, for `next/set`'s reason — a second copy would say the line twice — and the deck guards its own double press. `game/tutor/repeat` is the key of the line Repeat Help would say, or `""`. With it there are four QoS 0 topics. No existing topic or payload changes.

## 12.30 Changes in Rev 30

— `game/tutor/waiting` added (§6.1), following game_control.md Rev 33, 2026-10-09: `"more"` or `"next"` while the tutor has finished speaking and waits for More Help or Next Call, or for Next Call alone; `""` otherwise. The deck flashes the key. No existing topic or payload changes.

## 12.29 Changes in Rev 29

— `game/pace` and `pace/set` take `"tutor"`, and `game/tutor/set` and `game/tutor` are withdrawn (§6.1, §6.2), following game_control.md Rev 32, 2026-10-09: tutor mode is a pacing rather than a switch beside it. `game/tutor/intro` and `game/more/set` are unchanged. The game program no longer publishes `game/tutor`; a retained value left on the broker by an earlier version is harmless and is cleared with `mosquitto_pub -r -n -t sbgame/game/tutor`. Nothing reads it.

## 12.28 Changes in Rev 28

— `game/more/set` and `game/tutor/intro` added (§6.1, §6.2), following game_control.md Rev 31, 2026-10-09. `more/set` is the Stream Deck's More Help during the tutor's introduction: an event at QoS 0 for `next/set`'s reason, since a second copy would skip a part of the introduction. With it there are three QoS 0 topics. `game/tutor/intro` is the part of the introduction she is on, `"1/3"` to `"3/3"`, or `""`. The access list already covers both. No existing topic or payload changes.

## 12.27 Changes in Rev 27

— `audio/monitor/play/set` and its echo `audio/monitor/play` added (§5, §6), following audio.md Rev 11, 2026-10-08: a file on the loudspeaker, summed into the monitor, for the tutor's voice. And `game/tutor/set` and its echo `game/tutor` (§6.1, §6.2), following game_control.md Rev 29: tutor mode's switch, `"on"` or `"off"`, from the Stream Deck. The access list already covers all four: the audio program and the game program read and write `sbgame/#`, and the deck writes `sbgame/game/+/set`. The audio program subscribes to one more pattern. No existing topic or payload changes.

## 12.26 Changes in Rev 26

— `trunk/<n>/shortring/set` added (§6, §8.4), following control.md Rev 25, 2026-10-05: `"on"` rings the trunk once for 0.5s, `"off"` cancels the burst; the ESP32 echoes the relay on the existing `ring` topic, `"on"` then `"off"`. The game program uses it to signal a call in on a trunk (game_control.md Rev 28). It is the third command that is not absolute state, after `next/set` and the station's `dial/set`: a duplicate delivered after the first burst has ended rings once more. That is harmless — the switchboard's trunk signal latches, and a second burst on an unanswered trunk changes nothing the operator sees; a duplicate during the burst, or after the trunk is seized, is ignored by the controller. QoS 1 as for every command. The ESP32 subscribes to one more pattern. No existing topic or payload changes.

## 12.25 Changes in Rev 25

— `ctl/firmware` added (§4), following control.md Rev 18, 2026-10-01: the controller's firmware, its specification revision, git commit and build time, retained and published on every connection. An addition; no existing topic or payload changes, and the heartbeat's payload stays as it was.

## 12.24 Changes in Rev 24

— `station/<n>/dial/set` and its echo `station/<n>/dial` added (§4, §6), following control.md Rev 17, 2026-10-01: the station's off-hook relay pulses the digits, the controller timing them. Published by `sbgame-boardtest` on the bench, not by the game program, which never makes a station dial; so §6's "the game program is the only client that commands the ESP32" has one bench exception. An addition; no existing topic or payload changes. The access list already gives the board test's identity, `sbgame-audio`, the whole tree.

## 12.23 Changes in Rev 23

— Following game_control.md Rev 25 and audio.md Rev 10, 2026-09-30. Diagnostics: the page publishes `game/diag/<target>/<test>/set` and the game program echoes `game/diag/<target>/<test>` (§6.1, §6.2), `<target>` being `station/<n>`, `trunk/<n>` or `tap`. They are two levels deeper than `game/+/set`, so the access list gives the page and the deck `sbgame/game/diag/+/+/+/set` and `sbgame/game/diag/tap/+/set` as well (§9). The chosen next scene: `game/queue/set`, with `game/queue` and `game/scenes` (§6.1, §6.2), the one covered by the existing `game/+/set`. The circuits fitted: `game/stations` and `game/trunks` (§6.1). Voice on the operator tap: `audio/tap/play/set` and its echo `audio/tap/play` (§5, §6). All additions; no existing topic or payload changes. `game/scenes`, like `game/log`, is one value that is many lines.

## 12.22 Changes in Rev 22

— `game/pause` and `game/pause/set` added (§6.1, §6.2), following game_control.md Rev 17, 2026-09-27: listen pacing's own wait, the seconds from the board emptying to the next call, 0–60. An addition; no existing topic or payload changes. The page's and the deck's access lists already cover the command through `sbgame/game/+/set`.

## 12.21 Changes in Rev 21

— `game/pace` and `game/pace/set` take a third value, `"listen"` (§6.1, §6.2), following game_control.md Rev 16, 2026-09-26: automatic pacing that waits for the board to empty rather than for the last call to connect. An addition of a value; the existing two are unchanged. A subscriber that knows only `"manual"` and `"auto"` should treat any other value as automatic.

## 12.20 Changes in Rev 20

— A fifth client, the Stream Deck program, `sbgame-streamdeck` (§1), following game_control.md Rev 13, 2026-09-25. It publishes the commands of §6.2 and nothing else, as a new broker user, `sbgame-deck`, whose access list is the page's (§9). No topic or payload changes: the game program cannot tell the deck's commands from the page's and does not need to. Like the page it has no will and no heartbeat (§8.2).

— The page keeps its commands, behind a switch that hides them on an iPad (game_control.md §11.1), so `sbgame-web` keeps its write access and both users write the same commands.

## 12.19 Changes in Rev 19

— `game/jitter` and `game/jitter/set` added (§6.1, §6.2), following game_control.md Rev 12, 2026-09-25: the spread of the automatic wait around `gap_now`, a percentage from 0 to 100. An addition; no existing topic or payload changes. `next_at` is now the drawn start, which differs from the last connection plus `gap_now` whenever `jitter` is above 0. The page's access list already covers the new command through `sbgame/game/+/set`.

## 12.18 Changes in Rev 18

— The `board/` labels and circuits come from script.yml's `jacks:` list, not from its station entries (§6.1, §7), following game_control.md Rev 11, 2026-09-25. Every station jack the list names has a label, whether or not a station is cabled to it, so `board/station/<n>/label` can now be set while `board/station/<n>/circuit` is empty. Rev 14 said a jack with no circuit had no label. The topics, their payloads and their retention do not change.

## 12.17 Changes in Rev 17

— nginx serves the page and terminates its TLS; Mosquitto no longer does either (§9, §9.1), 2026-09-24. Rev 15 and Rev 16 had one Mosquitto listener on 443 carrying both the page's files, through `http_dir`, and its MQTT connection. Neither half worked on portland, and both failures are properties of the build rather than of the configuration:

— **443 will not bind.** libwebsockets creates the WebSockets listener's socket after Mosquitto has dropped from root to the `mosquitto` user, so a privileged port fails while the plain MQTT listener, opened while still root, succeeds. The `socket_domain ipv4` the man page suggests for a listener that will not open made no difference, and neither did granting the service `CAP_NET_BIND_SERVICE` as an ambient capability with `SecureBits=keep-caps`. Rev 16's §9 said Mosquitto "starts as root and drops to the `mosquitto` user once its listeners are open, which is how it holds 443". That is true of the MQTT listener and not of the WebSockets one.

— **The listener advertises HTTP/2 and cannot speak it.** With ALPN offering `h2` and `http/1.1` the listener selects `h2`, then sends nothing and closes; the same request forced to HTTP/1.1 is served correctly. A browser negotiates HTTP/2 by default, so the page would not have loaded at all. Nothing in the Mosquitto configuration turns the advertisement off.

— What replaces it. nginx listens on 443, holds the certificate, serves `/srv/sbgame/web`, and reverse-proxies the page's MQTT socket to a Mosquitto WebSockets listener on `127.0.0.1:9001` that carries no TLS and is unreachable from off the host. The page keeps one origin and one port, so the bookmark still carries none. The three plain-MQTT clients are untouched on 1883.

— The page's socket takes the path `/mqtt`, which is new (game_control.md Rev 10 §13.1). nginx routes on it: `/mqtt` to Mosquitto, everything else to the files. Routing instead on the `Upgrade` header would need an `if` inside a `location`, which nginx's own documentation calls unreliable. The page was not yet written, so nothing had to change to gain a path.

— The certificate reload question of Rev 15 and Rev 16 disappears with it. Mosquitto holds no certificate, so nothing needs SIGHUP; nginx rereads the certificate on `systemctl reload`, which drops no connection. The deploy hook becomes one line and moves to `/etc/letsencrypt/renewal-hooks/deploy/nginx`. The 04:00 restart fallback and the commissioning check that chose between them are both withdrawn (game_control.md Rev 10 §13.3).

— §9.1 now says why the Route 53 credentials belong under `[default]` rather than a named profile. They were first put in `[sbgame-letsencrypt]`, which worked for issuance by hand and would have failed every unattended renewal: boto3 reads `[default]` unless `AWS_PROFILE` names another, and `certbot renew` runs from `certbot.timer` with an empty environment. Mark moved them to `[default]`, which is the arrangement §9.1 records; the alternative is a systemd drop-in on `certbot.service`, and the root account has no other AWS use to keep separate.

## 12.16 Changes in Rev 16

— `game.kr3am.org` gets a public A record in Route 53, pointing at portland's fixed address, so it resolves on the home network with nothing on OPNsense (§9.2). Mark's decision, 2026-09-24. Rev 15 said the name has no public address record and resolves only through a host entry on each router. The existing Route 53 name for portland on the other domain already resolves this way at home, so OPNsense is known to pass a public answer that points at a private address.

— The travel router keeps its Edit Hosts line. Rev 15's two reasons against a public record still hold on the road: GL.iNet's DNS can drop a public answer that points at a private address, and a venue with no internet cannot reach Route 53 at all. The Edit Hosts line answers from the router in both cases. The public record is for home only.

— What the public record costs: the private address becomes visible to anyone who looks the name up. It is not reachable from outside, and the name was already public through Certificate Transparency (Rev 15).

— The certificate is not affected. The DNS-01 challenge uses a TXT record at `_acme-challenge.game.kr3am.org`, which sits beside the A record and does not replace it.

## 12.15 Changes in Rev 15

— The page's listener takes TLS (§9), 2026-09-24, at Mark's request. Rev 10 to Rev 14 served the page over plain HTTP and WebSockets on port 9001, reached as `<host>.local`. The listener now carries a Let's Encrypt certificate for `game.kr3am.org` and listens on 443, so the page is `https://game.kr3am.org/` and its MQTT connection is `wss://`. One listener still serves both, and `http_dir` is unchanged. The three clients stay on plain MQTT on 1883: the ESP32 gains nothing from TLS on a wired link inside the rack, and the two host programs connect over loopback.

— Why, when the page is Mark's and on a private network. Safari gives some features only to a page from a secure origin, among them the screen wake lock that could keep the iPad awake without turning off Auto-Lock (game_control.md §11.3). And the page's password crosses Wi-Fi, which at a venue may not be the travel router's alone. Rev 10's §11 had listener TLS as a later step for public events. It is taken now because its cost is one certificate and a renewal hook.

— The name. `kr3am.org` is one of Mark's domains, chosen over sidell.org, and its DNS is in Route 53. `game.kr3am.org` has no public address record. It resolves only on the local network, to portland, the Linux host, by a host entry on each of the two routers the page is used behind (§9.2). A public record pointing at a private address can be filtered by a router's DNS rebinding protection, and fails at a venue with no internet.

— The certificate is issued by the DNS-01 challenge, which proves control of the domain with a TXT record in Route 53 and needs no inbound connection to the host (§9.1). The HTTP-01 challenge cannot work here: the host is not reachable from the internet at home or on the road. Every certificate is logged publicly in Certificate Transparency, so the name `game.kr3am.org` is public. Nothing about it needs to be private.

— BIND on the host was considered — a resolver for kr3am.org, forwarding everything else to 1.1.1.1 — and not adopted. The iPad takes its DNS from the router in both places, so a host entry there is one line with nothing new to run on the host. It also keeps answering with no upstream at all, where forwarding does not.

— The certificate is reloaded with SIGHUP rather than a restart, because a restart drops every client and would end a game in progress. Whether SIGHUP reloads it on this listener is checked at commissioning, with a fallback if it does not (§9.1).

— Consequences. game_control.md Rev 8 follows in §2 (bookmark and scheme) and §9 (checks). Code consequence for Claude Code, when the page is written: `app.js` connects over `wss://` when the page was loaded over `https:`, taking the scheme from `location.protocol` rather than writing `ws://`.

## 12.14 Changes in Rev 14

— The `board/` topics' source is script.yml, not `wiring.yml` (§6.1, §7), following game_control.md Rev 7, 2026-09-24. Mark put each station's jack and label into its entry under script.yml's `stations:`, as `switchboard:` and `label:`, and `wiring.yml` was never written. Rev 12 and Rev 13 said the labels and circuits came from `wiring.yml`. The topics, their payloads and their retention do not change.

— What the topics carry follows from the new source. A station jack that a script.yml entry names carries that entry's `label` and circuit. Any other station jack publishes both empty. Trunk jack n carries `trunk/n` for n = 1–8 and nothing for 9 and 10, and every trunk jack's label is empty, since trunks are not in script.yml.

— §7's list of retained topics that use an empty payload to clear still named `name`, two revisions after Rev 12 removed that topic. It now names the `board/` topics instead.

## 12.13 Changes in Rev 13

— `sbgame/audio/monitor/source/set` and its echo `sbgame/audio/monitor/source` added (§5, §6), following audio.md Rev 8, 2026-09-24. The payload is `"tap"` or a circuit id, and names the receive channel the loudspeaker is fed from. Rev 5 to Rev 12 fed it from the operator tap only. The operator leaves a call when she throws the ring key, so the audience heard nothing of the conversation. The game program now points the monitor at the calling line of the call the operator most recently answered (game_control.md Rev 6 §9.1). That line's receive channel carries both sides of the conversation.

— A separate topic rather than a second value on `monitor/set`, so `monitor/set` stays the gain alone and the one-value rule of §2 holds. It is absolute state, QoS 1, and not retained, like every other command. Its echo is retained.

— `"tap"` is a literal on the same topic as circuit ids, as `"ambiguous"` is on `peer` (§7). The audio program accepts `tap`, `station/1`–`station/22` and `trunk/1`–`trunk/8`, and drops anything else.

— §8.2 and §8.4 follow. On losing the game or the broker, the audio program returns the monitor's source to the tap and keeps the monitor running. On start it publishes the source it started with, `tap` unless configured otherwise.

— The broker's access list does not change. The game program already writes `sbgame/#`, and the page cannot write `audio/`.

## 12.12 Changes in Rev 12

— `board/` added (§3, §6.1). It holds the switchboard's own jacks, 30 station and 10 trunk, each with its label and the circuit cabled to it, as `wiring.yml` records (game_control.md Rev 5, §12.1). The game program publishes them retained at start so the page can draw the board as it is. Jack numbers are the switchboard's, not circuits. Only the page and the game program use them. The controller and the audio program never see a jack number.

— `sbgame/station/<n>/name` removed. Rev 10 added it to carry script.yml's line name to the page for each station tile. The tiles are now jacks and show the board's label, which the `board/` topics carry. Nothing else read `name`.

## 12.11 Changes in Rev 11

— `game/next/set` becomes a plain command, 2026-09-24, at Mark's request: the payload is ignored and the game program starts the next call. Rev 10 had the page send the number of the call to start, which the game program acted on only if it was one more than `started`, so that a duplicate started one call and not two. Mark's view is that the game program keeps the count itself and the page should not have to. The duplicates are handled in two other ways. The command goes out at QoS 0, which is never resent on reconnect, so the resent-command duplicate cannot happen. The page disables Next Call when it is tapped and re-enables it when `started` changes, so a double tap cannot either (game_control.md §5.1). The cost is that a tap made as the connection drops can be lost. The operator sees no new call and taps again.

— This makes `next/set` the second event in the design, after `trunk/<n>/digit`, and the one command that is not absolute state. §2 records both exceptions. It is still unretained, like every command.

## 12.10 Changes in Rev 10

— The status page, 2026-09-24, specified in the new `game_control.md` Rev 1. An iPad shows the state of the whole system and runs the game: start and stop, manual or automatic call pacing with a ramp, a Next Call button, tallies. The page talks MQTT directly over Mosquitto's WebSockets listener, which also serves its files (§9). The alternative — a web server inside the game program pushing its own WebSocket — was considered and not adopted, because the page would then show what the game program believes rather than what the controller and audio program report, and would go dark exactly when the game program fails.

— The game program now publishes state (§6.1): its own birth and last will on `sbgame/ctl/game_status`; each station's line name from script.yml on `sbgame/station/<n>/name`; and a new segment, `sbgame/game/…`, for the run state, the pacing values, the tallies, eight call slots and the event log. §3 adds the segment. Before this revision the game program published only commands, the heartbeat and `sync`.

— The page is a new publisher (§6.2), of six commands under `sbgame/game/…/set`, consumed by the game program only. §1 and §6 said the game program was the only client that sends commands; it is now the only client that commands hardware or audio, and the broker's access list holds the page to the game's own commands (§9). Every page command follows the `/set`-and-echo shape and is absolute state. The one that looks like a verb — start the next call — carries the number of the call to start, so a redelivery or a double tap starts one call (§2).

— `sbgame/ctl/game_heartbeat` now carries the host's Unix time in seconds. It carried nothing through Rev 9. The page needs the host's clock to count down against the host times in the call slots, and the iPad's clock is not trusted on the travel router. The ESP32 and the audio program act on the beat's arrival only (control.md §9.3, audio.md §13.2), so the payload changes nothing for them. Code consequence for Claude Code: confirm that neither `control/control.ino` nor `sbaudio` rejects a non-empty payload on this topic.

— Two exceptions to the one-value rule's spirit, recorded in §2: `game/log` is one retained value that is many lines of text, and the call slot's values change together but are published separately. Neither is JSON; both are for display.

— §9 rewritten. Rev 9 said anonymous connections are allowed by default, with a password for the ESP32 and the broker bound to the wired interface as the protection. With the iPad on Wi-Fi, binding cannot be the protection, and the page's password is readable by anyone who loads it. The broker now refuses anonymous clients, and an access list gives the page read access to everything and write access to `sbgame/game/+/set` only. The three existing clients keep full access. The WebSockets listener and its `http_dir` are added. Commissioning consequence: every client must present credentials that match the access list (game_control.md §13.3).

— §8.1 and §8.4 add the game program's birth and last will, and its start sequence: game state before birth, as the audio program does.

## 12.9 Changes in Rev 9

— Follows station Rev 3.40 and audio.md Rev 7. Station topics are n = 1–22, not 1–23: the operator tap moves from board 3 strip 8 to strip 7 (A32 channel 23), and strip 8's A32 output, channel 24, becomes the audience monitor feed in place of the Digiface's own analog output on 33/34. The tables in §4 to §6 and the naming in §3 follow, and `audio/monitor/set`'s unity reference is now A32 output 24. No topic is added or removed and no payload changes. `audio/test/<1-34>` keeps its range, because the audio program still opens the Digiface at 34 playback channels (audio.md §2) and a test tone on 33/34 is still the check on that jack. The ESP32 side has one fewer station row (control.md Rev 10).

## 12.8 Changes in Rev 8

— `"silence"` added to the `listen` values (§5, §7), following audio.md Rev 6: a listen now reports the end of speech as well as its start. The sequence on the state topic is `"listening"`, `"speech"`, then `"silence"` or `"timeout"`; `"timeout"` now also covers speech that started and did not stop within the audio program's cap. `listen/set` is unchanged — one number, the time allowed for speech to start — so no command changes and the one-value rule of §2 holds; the silence hangover and the maximum speech time are the audio program's options (audio.md §14). Same shape as Rev 6's `"busy"`: one more value on an existing topic, no new topic.

## 12.7 Changes in Rev 7

— Cross-reference only. The controller's specification is `control.md`, renamed from `esp32.md`, and its firmware is `control/control.ino`, renamed from `ring/esp32.ino`, both on 2026-09-19 (control.md Rev 9). Every reference here follows, including the Rev 5 entry. The client id `sbgame-esp32` (§8.1, control.md §9.1) does not change: it is on the wire, and the ESP32 is still the chip. Nothing else in this document changes.

## 12.6 Changes in Rev 6

— `"busy"` added to the `tone/set` and `tone` payloads (§5, §6), following audio.md §8.2: the game's scenarios will include called numbers that are busy. Same shape as the two existing tones — one more value on an existing topic, no new topic. The audio program's tones are the period ones (600Hz×120Hz dial and busy, 420Hz×40Hz ringback), settled the same day; nothing on the wire says which set is in use, and this document does not care.

## 12.5 Changes in Rev 5

— The audio program is now commanded. Rev 1 to Rev 4 said it "publishes what it detects and nothing else", which was true while its only job was the detector. `audio.md` Rev 1 gives it five commanded functions — play a file on a circuit, play dial tone or ringback on a trunk, listen for speech on a circuit, feed the operator tap to the loudspeaker, put a 1kHz test tone on a channel — and this revision adds their commands to §6 and their state echoes to §5. The game program remains the only commander; §6 now says which client consumes each command, since it is no longer only the ESP32.

— Every new command follows the existing shape: a `/set` topic, unretained, echoed on the state topic it commands, retained. There is no new event topic. The rough specification asked for "an mqtt response when a file finishes playing"; the response is the `play` state clearing to empty (§7), because a retained state topic tells the game the same thing an event would and also tells a game program restarted mid-file what is playing. `audio.md` §17.1 records the reasoning.

— A new top-level segment, `audio/`, for the two commands that are not about a circuit — the monitor and the test tone — and for `optone`, the tap's own-tone health check (§3). The alternative was to put them under `ctl/`, which is liveness and system control; a loudspeaker level is neither. Circuit-scoped audio commands live under the circuit, as `hook/set` does, so `sbgame/station/5/#` remains everything about station 5.

— sbgame/audio/optone added (§5): `"ok"` or `"deaf"`, the tap's own 9000Hz tone returning on its own receive channel, station §8.4. A dead tap transmit path makes every circuit's `op` read off, which is indistinguishable from an operator who has not plugged in; this is the one topic that tells the difference.

— The audio program adopts the ESP32's failsafe on losing the game (§8.2, §8.4): two missed `game_heartbeat`s stop every trunk tone and file. The failure it prevents is a crashed game leaving ringback on a trunk indefinitely, which is the audio equivalent of a relay held closed.

— §8.4's ESP32 recovery step said "subscribe to every `set` topic". Now that there are `set` topics the ESP32 does not consume, that reads as a wildcard, and a wildcard subscription would deliver every `play/set` and `listen/set` to the controller to be dropped. It now says `hook/set` and `ring/set`. Firmware consequence: confirm `control/control.ino` (renamed from `ring/ring.ino` the same day) subscribes to `sbgame/station/+/hook/set` and `sbgame/trunk/+/ring/set` and not to a broader pattern. On the Claude Code side; control.md §9.1 already specifies it that way.

— `"stop"` on `play/set` is a reserved payload, so no file may be named `stop`. Recorded in §7 as the one place a filename and a verb share a topic.

## 12.4 Changes in Rev 4

— sbgame/ctl/i2c added to the ESP32's messages (§4): the boot-time expander scan result, `"ok"` or the missing addresses, retained. Rev 3's §11 asked for it; the firmware implemented it as suggested and it is promoted into the table.

— The ESP32's MQTT client library is settled — MQTT 2.5.3, Joël Gähwiler — and the §11 item closes. It pings from the main loop, so the client-dependent gap §8.2 describes falls on the safe side; the two heartbeats stay regardless, since the game side of the argument is unchanged.

## 12.3 Changes in Rev 3

— Station topics are n = 1–23, not 1–24, following station Rev 3.35: three station boards are built and the last strip, station 24, is the operator tap, which has nothing to report and nothing to command. The tables in §4 to §6 and the naming in §3 follow. Rev 1 and Rev 2 said 1–24 without excluding the tap strip, which was then station 8 and would have needed excluding just the same.

## 12.2 Changes in Rev 2

— sbgame/trunk/<n>/digit added to the ESP32's messages (§4): the digit the operator has just dialled on a seized trunk, `"0"` to `"9"`, decoded by the firmware from the loop-current interruptions on the seizure input (control.md §8.2). It is the first topic in the design that is an event rather than a state, and §2 and §7 record what that changes: it is not retained, it cannot be idempotent, and it is therefore published at QoS 0, which over TCP delivers exactly once or not at all where QoS 1 could deliver twice on a reconnect. A second fault value, `"bad_dial"`, is added for a pulse train outside the timing windows.

— The alternative — publishing the accumulated digit string per trunk as retained state, which would have kept every message idempotent and survived a reconnect — is recorded in §11 rather than adopted, because the game program is the place that knows how many digits make a number and what to do with them.

## 12.1 Changes in Rev 1

— New document. The MQTT design had been spread across station §9.7 and §9.10–§9.12, trunk §11.3–§11.4 and a paragraph of generator §15.3, and had been revised six times in two days as it was read for the first time as a whole. It now lives in one place, with the source sections replaced by pointers here. The station document's change entries from Rev 3.28 to Rev 3.33 record the decisions that produced the design as it stands; they are summarised in §10 so this document is self-contained, and the originals are left in place.

— One change of substance made in the move. The messages are tabled by publisher — ESP32, audio program, game program — rather than by board, because a reader implementing one client needs to know what it sends and what it must subscribe to, and the by-board tables answered neither question directly. Every topic in the station and trunk tables at station Rev 3.33 appears here unchanged in name, payload and retention.
