**551 Switchboard Simulator**

**MQTT Design**

*Rev 19 — Broker on the Linux Host, Three Clients (ESP32, Audio Program, Game Program) and the Status Page, sbgame/ Prefix, One Plain-String Value per Topic, Retained State and Unretained Commands, QoS 1 Throughout but Two Events, Birth/LWT and Two-Way Heartbeats, Dialled Digits from the Trunks, Audio Program Commanded (Play, Tone, Listen, Monitor and Its Source, Test), Game State and Game Commands from the Page over Secure WebSockets at game.kr3am.org, Served by nginx, the Switchboard's Jacks and Labels*

# 1. Overview

Everything that is not audio moves over MQTT. The broker is Mosquitto on the Linux host. Three clients connect to it, and a browser page:

- **The ESP32** — the Olimex ESP32-POE-ISO on the ring generator board, the system's only microcontroller. It owns every relay and every supervisory input on the station and trunk boards, reached over I²C. It connects over Ethernet. Its firmware is specified in `control.md`.

- **The audio program** — C++, on the host. It owns the Ferrofish A32 and the Digiface's own analog output: it drives the 32 A32 outputs — the audience monitor among them, on A32 channel 24 — and the Digiface's two, reads all 32 inputs, generates the pilot tones and the operator tone, and runs the pilot detector of station §8.7. It publishes what it detects, and it is commanded — to play a file or a tone on a circuit, to listen for speech, to feed the loudspeaker from the operator tap or from a circuit, to put a test tone on a channel — and echoes what it is doing as retained state. It never commands anything. It connects over loopback. Its behaviour is specified in `audio.md`.

- **The game program** — Python, on the host. It is the game logic. It commands the ESP32 and the audio program, consumes everything both publish, publishes the game's own state for the status page, and is the only client that commands hardware or audio. It connects over loopback. What it does with the page's commands is specified in `game_control.md`.

- **The status page** — one HTML page with its script, in Safari on an iPad, over Wi-Fi. nginx serves its files over HTTPS and proxies its secure WebSockets connection through to Mosquitto (§9, Rev 17). It reads every topic, and it commands the game program only — start and stop, pacing, the next call (§6.2). It is specified in `game_control.md`.

The ESP32 and the host are joined by wired Ethernet, with the ESP32 powered by PoE from the same cable. This replaced a USB serial link at station Rev 3.1: Ethernet is deterministic, unaffected by RF conditions in the room, puts one cable rather than two into the rack, and decouples the controller's position from the host's. The hardware side of that link — the controller board, its PoE budget and the switch — is in station §9.8 and §9.9.

This document specifies the messages: the topic names, who publishes each, what the payload is, and what is retained. The circuit documents own the hardware the messages describe and say only where a message comes from; the ESP32 document owns what the controller does with a command and when it publishes state; the audio document owns the same for the audio program; `game_control.md` owns the same for the game state and the page.

## 1.1 Changes in Rev 1

— New document. The MQTT design had been spread across station §9.7 and §9.10–§9.12, trunk §11.3–§11.4 and a paragraph of generator §15.3, and had been revised six times in two days as it was read for the first time as a whole. It now lives in one place, with the source sections replaced by pointers here. The station document's change entries from Rev 3.28 to Rev 3.33 record the decisions that produced the design as it stands; they are summarised in §10 so this document is self-contained, and the originals are left in place.

— One change of substance made in the move. The messages are tabled by publisher — ESP32, audio program, game program — rather than by board, because a reader implementing one client needs to know what it sends and what it must subscribe to, and the by-board tables answered neither question directly. Every topic in the station and trunk tables at station Rev 3.33 appears here unchanged in name, payload and retention.

## 1.2 Changes in Rev 2

— sbgame/trunk/<n>/digit added to the ESP32's messages (§4): the digit the operator has just dialled on a seized trunk, `"0"` to `"9"`, decoded by the firmware from the loop-current interruptions on the seizure input (control.md §8.2). It is the first topic in the design that is an event rather than a state, and §2 and §7 record what that changes: it is not retained, it cannot be idempotent, and it is therefore published at QoS 0, which over TCP delivers exactly once or not at all where QoS 1 could deliver twice on a reconnect. A second fault value, `"bad_dial"`, is added for a pulse train outside the timing windows.

— The alternative — publishing the accumulated digit string per trunk as retained state, which would have kept every message idempotent and survived a reconnect — is recorded in §11 rather than adopted, because the game program is the place that knows how many digits make a number and what to do with them.

## 1.3 Changes in Rev 3

— Station topics are n = 1–23, not 1–24, following station Rev 3.35: three station boards are built and the last strip, station 24, is the operator tap, which has nothing to report and nothing to command. The tables in §4 to §6 and the naming in §3 follow. Rev 1 and Rev 2 said 1–24 without excluding the tap strip, which was then station 8 and would have needed excluding just the same.

## 1.4 Changes in Rev 4

— sbgame/ctl/i2c added to the ESP32's messages (§4): the boot-time expander scan result, `"ok"` or the missing addresses, retained. Rev 3's §11 asked for it; the firmware implemented it as suggested and it is promoted into the table.

— The ESP32's MQTT client library is settled — MQTT 2.5.3, Joël Gähwiler — and the §11 item closes. It pings from the main loop, so the client-dependent gap §8.2 describes falls on the safe side; the two heartbeats stay regardless, since the game side of the argument is unchanged.

## 1.5 Changes in Rev 5

— The audio program is now commanded. Rev 1 to Rev 4 said it "publishes what it detects and nothing else", which was true while its only job was the detector. `audio.md` Rev 1 gives it five commanded functions — play a file on a circuit, play dial tone or ringback on a trunk, listen for speech on a circuit, feed the operator tap to the loudspeaker, put a 1kHz test tone on a channel — and this revision adds their commands to §6 and their state echoes to §5. The game program remains the only commander; §6 now says which client consumes each command, since it is no longer only the ESP32.

— Every new command follows the existing shape: a `/set` topic, unretained, echoed on the state topic it commands, retained. There is no new event topic. The rough specification asked for "an mqtt response when a file finishes playing"; the response is the `play` state clearing to empty (§7), because a retained state topic tells the game the same thing an event would and also tells a game program restarted mid-file what is playing. `audio.md` §1.1 records the reasoning.

— A new top-level segment, `audio/`, for the two commands that are not about a circuit — the monitor and the test tone — and for `optone`, the tap's own-tone health check (§3). The alternative was to put them under `ctl/`, which is liveness and system control; a loudspeaker level is neither. Circuit-scoped audio commands live under the circuit, as `hook/set` does, so `sbgame/station/5/#` remains everything about station 5.

— sbgame/audio/optone added (§5): `"ok"` or `"deaf"`, the tap's own 9000Hz tone returning on its own receive channel, station §8.4. A dead tap transmit path makes every circuit's `op` read off, which is indistinguishable from an operator who has not plugged in; this is the one topic that tells the difference.

— The audio program adopts the ESP32's failsafe on losing the game (§8.2, §8.4): two missed `game_heartbeat`s stop every trunk tone and file. The failure it prevents is a crashed game leaving ringback on a trunk indefinitely, which is the audio equivalent of a relay held closed.

— §8.4's ESP32 recovery step said "subscribe to every `set` topic". Now that there are `set` topics the ESP32 does not consume, that reads as a wildcard, and a wildcard subscription would deliver every `play/set` and `listen/set` to the controller to be dropped. It now says `hook/set` and `ring/set`. Firmware consequence: confirm `control/control.ino` (renamed from `ring/ring.ino` the same day) subscribes to `sbgame/station/+/hook/set` and `sbgame/trunk/+/ring/set` and not to a broader pattern. On the Claude Code side; control.md §9.1 already specifies it that way.

— `"stop"` on `play/set` is a reserved payload, so no file may be named `stop`. Recorded in §7 as the one place a filename and a verb share a topic.

## 1.6 Changes in Rev 6

— `"busy"` added to the `tone/set` and `tone` payloads (§5, §6), following audio.md §8.2: the game's scenarios will include called numbers that are busy. Same shape as the two existing tones — one more value on an existing topic, no new topic. The audio program's tones are the period ones (600Hz×120Hz dial and busy, 420Hz×40Hz ringback), settled the same day; nothing on the wire says which set is in use, and this document does not care.

## 1.7 Changes in Rev 7

— Cross-reference only. The controller's specification is `control.md`, renamed from `esp32.md`, and its firmware is `control/control.ino`, renamed from `ring/esp32.ino`, both on 2026-09-19 (control.md Rev 9). Every reference here follows, including the Rev 5 entry above. The client id `sbgame-esp32` (§8.1, control.md §9.1) does not change: it is on the wire, and the ESP32 is still the chip. Nothing else in this document changes.

## 1.8 Changes in Rev 8

— `"silence"` added to the `listen` values (§5, §7), following audio.md Rev 6: a listen now reports the end of speech as well as its start. The sequence on the state topic is `"listening"`, `"speech"`, then `"silence"` or `"timeout"`; `"timeout"` now also covers speech that started and did not stop within the audio program's cap. `listen/set` is unchanged — one number, the time allowed for speech to start — so no command changes and the one-value rule of §2 holds; the silence hangover and the maximum speech time are the audio program's options (audio.md §14). Same shape as Rev 6's `"busy"`: one more value on an existing topic, no new topic.

## 1.9 Changes in Rev 9

— Follows station Rev 3.40 and audio.md Rev 7. Station topics are n = 1–22, not 1–23: the operator tap moves from board 3 strip 8 to strip 7 (A32 channel 23), and strip 8's A32 output, channel 24, becomes the audience monitor feed in place of the Digiface's own analog output on 33/34. The tables in §4 to §6 and the naming in §3 follow, and `audio/monitor/set`'s unity reference is now A32 output 24. No topic is added or removed and no payload changes. `audio/test/<1-34>` keeps its range, because the audio program still opens the Digiface at 34 playback channels (audio.md §2) and a test tone on 33/34 is still the check on that jack. The ESP32 side has one fewer station row (control.md Rev 10).

## 1.10 Changes in Rev 10

— The status page, 2026-09-24, specified in the new `game_control.md` Rev 1. An iPad shows the state of the whole system and runs the game: start and stop, manual or automatic call pacing with a ramp, a Next Call button, tallies. The page talks MQTT directly over Mosquitto's WebSockets listener, which also serves its files (§9). The alternative — a web server inside the game program pushing its own WebSocket — was considered and not adopted, because the page would then show what the game program believes rather than what the controller and audio program report, and would go dark exactly when the game program fails.

— The game program now publishes state (§6.1): its own birth and last will on `sbgame/ctl/game_status`; each station's line name from script.yml on `sbgame/station/<n>/name`; and a new segment, `sbgame/game/…`, for the run state, the pacing values, the tallies, eight call slots and the event log. §3 adds the segment. Before this revision the game program published only commands, the heartbeat and `sync`.

— The page is a new publisher (§6.2), of six commands under `sbgame/game/…/set`, consumed by the game program only. §1 and §6 said the game program was the only client that sends commands; it is now the only client that commands hardware or audio, and the broker's access list holds the page to the game's own commands (§9). Every page command follows the `/set`-and-echo shape and is absolute state. The one that looks like a verb — start the next call — carries the number of the call to start, so a redelivery or a double tap starts one call (§2).

— `sbgame/ctl/game_heartbeat` now carries the host's Unix time in seconds. It carried nothing through Rev 9. The page needs the host's clock to count down against the host times in the call slots, and the iPad's clock is not trusted on the travel router. The ESP32 and the audio program act on the beat's arrival only (control.md §9.3, audio.md §13.2), so the payload changes nothing for them. Code consequence for Claude Code: confirm that neither `control/control.ino` nor `sbaudio` rejects a non-empty payload on this topic.

— Two exceptions to the one-value rule's spirit, recorded in §2: `game/log` is one retained value that is many lines of text, and the call slot's values change together but are published separately. Neither is JSON; both are for display.

— §9 rewritten. Rev 9 said anonymous connections are allowed by default, with a password for the ESP32 and the broker bound to the wired interface as the protection. With the iPad on Wi-Fi, binding cannot be the protection, and the page's password is readable by anyone who loads it. The broker now refuses anonymous clients, and an access list gives the page read access to everything and write access to `sbgame/game/+/set` only. The three existing clients keep full access. The WebSockets listener and its `http_dir` are added. Commissioning consequence: every client must present credentials that match the access list (game_control.md §9).

— §8.1 and §8.4 add the game program's birth and last will, and its start sequence: game state before birth, as the audio program does.

## 1.11 Changes in Rev 11

— `game/next/set` becomes a plain command, 2026-09-24, at Mark's request: the payload is ignored and the game program starts the next call. Rev 10 had the page send the number of the call to start, which the game program acted on only if it was one more than `started`, so that a duplicate started one call and not two. Mark's view is that the game program keeps the count itself and the page should not have to. The duplicates are handled in two other ways. The command goes out at QoS 0, which is never resent on reconnect, so the resent-command duplicate cannot happen. The page disables Next Call when it is tapped and re-enables it when `started` changes, so a double tap cannot either (game_control.md §4.1). The cost is that a tap made as the connection drops can be lost. The operator sees no new call and taps again.

— This makes `next/set` the second event in the design, after `trunk/<n>/digit`, and the one command that is not absolute state. §2 records both exceptions. It is still unretained, like every command.

## 1.12 Changes in Rev 12

— `board/` added (§3, §6.1). It holds the switchboard's own jacks, 30 station and 10 trunk, each with its label and the circuit cabled to it, as `wiring.yml` records (game_control.md Rev 5, §6.3). The game program publishes them retained at start so the page can draw the board as it is. Jack numbers are the switchboard's, not circuits. Only the page and the game program use them. The controller and the audio program never see a jack number.

— `sbgame/station/<n>/name` removed. Rev 10 added it to carry script.yml's line name to the page for each station tile. The tiles are now jacks and show the board's label, which the `board/` topics carry. Nothing else read `name`.

## 1.13 Changes in Rev 13

— `sbgame/audio/monitor/source/set` and its echo `sbgame/audio/monitor/source` added (§5, §6), following audio.md Rev 8, 2026-09-24. The payload is `"tap"` or a circuit id, and names the receive channel the loudspeaker is fed from. Rev 5 to Rev 12 fed it from the operator tap only. The operator leaves a call when she throws the ring key, so the audience heard nothing of the conversation. The game program now points the monitor at the calling line of the call the operator most recently answered (game_control.md Rev 6 §6.4). That line's receive channel carries both sides of the conversation.

— A separate topic rather than a second value on `monitor/set`, so `monitor/set` stays the gain alone and the one-value rule of §2 holds. It is absolute state, QoS 1, and not retained, like every other command. Its echo is retained.

— `"tap"` is a literal on the same topic as circuit ids, as `"ambiguous"` is on `peer` (§7). The audio program accepts `tap`, `station/1`–`station/22` and `trunk/1`–`trunk/8`, and drops anything else.

— §8.2 and §8.4 follow. On losing the game or the broker, the audio program returns the monitor's source to the tap and keeps the monitor running. On start it publishes the source it started with, `tap` unless configured otherwise.

— The broker's access list does not change. The game program already writes `sbgame/#`, and the page cannot write `audio/`.

## 1.14 Changes in Rev 14

— The `board/` topics' source is script.yml, not `wiring.yml` (§6.1, §7), following game_control.md Rev 7, 2026-09-24. Mark put each station's jack and label into its entry under script.yml's `stations:`, as `switchboard:` and `label:`, and `wiring.yml` was never written. Rev 12 and Rev 13 said the labels and circuits came from `wiring.yml`. The topics, their payloads and their retention do not change.

— What the topics carry follows from the new source. A station jack that a script.yml entry names carries that entry's `label` and circuit. Any other station jack publishes both empty. Trunk jack n carries `trunk/n` for n = 1–8 and nothing for 9 and 10, and every trunk jack's label is empty, since trunks are not in script.yml.

— §7's list of retained topics that use an empty payload to clear still named `name`, two revisions after Rev 12 removed that topic. It now names the `board/` topics instead.

## 1.15 Changes in Rev 15

— The page's listener takes TLS (§9), 2026-09-24, at Mark's request. Rev 10 to Rev 14 served the page over plain HTTP and WebSockets on port 9001, reached as `<host>.local`. The listener now carries a Let's Encrypt certificate for `game.kr3am.org` and listens on 443, so the page is `https://game.kr3am.org/` and its MQTT connection is `wss://`. One listener still serves both, and `http_dir` is unchanged. The three clients stay on plain MQTT on 1883: the ESP32 gains nothing from TLS on a wired link inside the rack, and the two host programs connect over loopback.

— Why, when the page is Mark's and on a private network. Safari gives some features only to a page from a secure origin, among them the screen wake lock that could keep the iPad awake without turning off Auto-Lock (game_control.md §7.3). And the page's password crosses Wi-Fi, which at a venue may not be the travel router's alone. Rev 10's §11 had listener TLS as a later step for public events. It is taken now because its cost is one certificate and a renewal hook.

— The name. `kr3am.org` is one of Mark's domains, chosen over sidell.org, and its DNS is in Route 53. `game.kr3am.org` has no public address record. It resolves only on the local network, to portland, the Linux host, by a host entry on each of the two routers the page is used behind (§9.2). A public record pointing at a private address can be filtered by a router's DNS rebinding protection, and fails at a venue with no internet.

— The certificate is issued by the DNS-01 challenge, which proves control of the domain with a TXT record in Route 53 and needs no inbound connection to the host (§9.1). The HTTP-01 challenge cannot work here: the host is not reachable from the internet at home or on the road. Every certificate is logged publicly in Certificate Transparency, so the name `game.kr3am.org` is public. Nothing about it needs to be private.

— BIND on the host was considered — a resolver for kr3am.org, forwarding everything else to 1.1.1.1 — and not adopted. The iPad takes its DNS from the router in both places, so a host entry there is one line with nothing new to run on the host. It also keeps answering with no upstream at all, where forwarding does not.

— The certificate is reloaded with SIGHUP rather than a restart, because a restart drops every client and would end a game in progress. Whether SIGHUP reloads it on this listener is checked at commissioning, with a fallback if it does not (§9.1).

— Consequences. game_control.md Rev 8 follows in §2 (bookmark and scheme) and §9 (checks). Code consequence for Claude Code, when the page is written: `app.js` connects over `wss://` when the page was loaded over `https:`, taking the scheme from `location.protocol` rather than writing `ws://`.

## 1.16 Changes in Rev 16

— `game.kr3am.org` gets a public A record in Route 53, pointing at portland's fixed address, so it resolves on the home network with nothing on OPNsense (§9.2). Mark's decision, 2026-09-24. Rev 15 said the name has no public address record and resolves only through a host entry on each router. The existing Route 53 name for portland on the other domain already resolves this way at home, so OPNsense is known to pass a public answer that points at a private address.

— The travel router keeps its Edit Hosts line. Rev 15's two reasons against a public record still hold on the road: GL.iNet's DNS can drop a public answer that points at a private address, and a venue with no internet cannot reach Route 53 at all. The Edit Hosts line answers from the router in both cases. The public record is for home only.

— What the public record costs: the private address becomes visible to anyone who looks the name up. It is not reachable from outside, and the name was already public through Certificate Transparency (Rev 15).

— The certificate is not affected. The DNS-01 challenge uses a TXT record at `_acme-challenge.game.kr3am.org`, which sits beside the A record and does not replace it.

## 1.17 Changes in Rev 17

— nginx serves the page and terminates its TLS; Mosquitto no longer does either (§9, §9.1), 2026-09-24. Rev 15 and Rev 16 had one Mosquitto listener on 443 carrying both the page's files, through `http_dir`, and its MQTT connection. Neither half worked on portland, and both failures are properties of the build rather than of the configuration:

— **443 will not bind.** libwebsockets creates the WebSockets listener's socket after Mosquitto has dropped from root to the `mosquitto` user, so a privileged port fails while the plain MQTT listener, opened while still root, succeeds. The `socket_domain ipv4` the man page suggests for a listener that will not open made no difference, and neither did granting the service `CAP_NET_BIND_SERVICE` as an ambient capability with `SecureBits=keep-caps`. Rev 16's §9 said Mosquitto "starts as root and drops to the `mosquitto` user once its listeners are open, which is how it holds 443". That is true of the MQTT listener and not of the WebSockets one.

— **The listener advertises HTTP/2 and cannot speak it.** With ALPN offering `h2` and `http/1.1` the listener selects `h2`, then sends nothing and closes; the same request forced to HTTP/1.1 is served correctly. A browser negotiates HTTP/2 by default, so the page would not have loaded at all. Nothing in the Mosquitto configuration turns the advertisement off.

— What replaces it. nginx listens on 443, holds the certificate, serves `/srv/sbgame/web`, and reverse-proxies the page's MQTT socket to a Mosquitto WebSockets listener on `127.0.0.1:9001` that carries no TLS and is unreachable from off the host. The page keeps one origin and one port, so the bookmark still carries none. The three plain-MQTT clients are untouched on 1883.

— The page's socket takes the path `/mqtt`, which is new (game_control.md Rev 10 §2). nginx routes on it: `/mqtt` to Mosquitto, everything else to the files. Routing instead on the `Upgrade` header would need an `if` inside a `location`, which nginx's own documentation calls unreliable. The page was not yet written, so nothing had to change to gain a path.

— The certificate reload question of Rev 15 and Rev 16 disappears with it. Mosquitto holds no certificate, so nothing needs SIGHUP; nginx rereads the certificate on `systemctl reload`, which drops no connection. The deploy hook becomes one line and moves to `/etc/letsencrypt/renewal-hooks/deploy/nginx`. The 04:00 restart fallback and the commissioning check that chose between them are both withdrawn (game_control.md Rev 10 §9).

— §9.1 now says why the Route 53 credentials belong under `[default]` rather than a named profile. They were first put in `[sbgame-letsencrypt]`, which worked for issuance by hand and would have failed every unattended renewal: boto3 reads `[default]` unless `AWS_PROFILE` names another, and `certbot renew` runs from `certbot.timer` with an empty environment. Mark moved them to `[default]`, which is the arrangement §9.1 records; the alternative is a systemd drop-in on `certbot.service`, and the root account has no other AWS use to keep separate.

## 1.19 Changes in Rev 19

— `game/jitter` and `game/jitter/set` added (§6.1, §6.2), following game_control.md Rev 12, 2026-09-25: the spread of the automatic wait around `gap_now`, a percentage from 0 to 100. An addition; no existing topic or payload changes. `next_at` is now the drawn start, which differs from the last connection plus `gap_now` whenever `jitter` is above 0. The page's access list already covers the new command through `sbgame/game/+/set`.

## 1.18 Changes in Rev 18

— The `board/` labels and circuits come from script.yml's `jacks:` list, not from its station entries (§6.1, §7), following game_control.md Rev 11, 2026-09-25. Every station jack the list names has a label, whether or not a station is cabled to it, so `board/station/<n>/label` can now be set while `board/station/<n>/circuit` is empty. Rev 14 said a jack with no circuit had no label. The topics, their payloads and their retention do not change.

# 2. Design Rules

These hold across every topic. A new topic that breaks one of them needs a reason recorded here.

**One value per topic, as a plain string.** No JSON. A retained message is one value on one topic, so a station's `ring` and `hook` are separate topics rather than fields of one object: the broker holds the last value of each independently, and a subscriber coming up cold gets the whole board's state in one subscription with no sync round trip. It also keeps every payload idempotent (below), keeps wildcard subscriptions useful — `sbgame/station/+/hook` is every station's hook state — and means `mosquitto_sub -v -t 'sbgame/#'` on the host shows the whole system's state with no parsing. The one place a multi-field message would be justified — a set that must change atomically — does not arise: every fact here is independent of every other. A filename, a tone name, a number of seconds and a gain in dB are each still one value.

Two game topics stretch this, for display only (Rev 10). `game/log` is one value that is many lines of plain text: it is read whole and never parsed, and splitting it across numbered topics would make the page reassemble what the game program already had in order. A call slot's values (`game/call/<n>/…`) change together when a stage changes, and are still separate topics; the game program publishes them in an order that keeps the page consistent (game_control.md §6.1), which is enough for a display and would not be enough for a control.

**Every message carries absolute state, never a delta.** `"on"` and `"off"`, a circuit id, an uptime, a filename, a gain — never a toggle, never a count, never a relative step. A duplicate delivery is then harmless, which is what lets the interface run at QoS 1. Never add a toggle command: it is not idempotent and would force QoS 2 across the interface. The one exception is `trunk/<n>/digit` (§4), which is an event by nature — a digit dialled is not a state the trunk is in — and is handled by the rule below. The other exception is `game/next/set` (§6.2), which tells the game program to start the next call. It is a request for an action rather than a state to hold (Rev 11). Rev 10 made it absolute by carrying the number of the call to start. Rev 11 drops the number for simplicity and handles duplicates through QoS 0 and the page, below. The page's steppers publish the new value, never a step.

**QoS 1 for state and commands; QoS 0 for the one event.** QoS 0 can silently drop a hook command, which is not acceptable for something an operator is waiting on, and QoS 2 buys nothing while every payload is absolute state. A dialled digit is the opposite case: a duplicate is as wrong as a loss, and QoS 1's redelivery on reconnect is exactly how a duplicate would arise. Over a TCP link QoS 0 delivers a message exactly once unless the connection breaks, and if the connection breaks the trunk state is being resynchronised anyway. So `digit` is QoS 0. `game/next/set` is QoS 0 for the same reason (Rev 11): a second copy would start a second call. A copy lost as the page's connection drops costs a second tap, and the operator sees that no call came. The page guards against its own double tap by disabling Next Call until `started` changes (game_control.md §4.1). These two are the only QoS 0 topics.

**Retain state, never commands.** Retained state means a subscriber sees actual hardware state the instant it subscribes. A retained command is a hazard: a retained `hook/set` of `"on"` would close a relay the moment the ESP32 boots, possibly hours after the message was sent and with nothing watching, and a retained trunk `ring/set` would put 90V on a switchboard line the same way. A retained `tone/set` would start ringback on a trunk the moment the audio program starts. A retained `game/run/set` would start a game whenever the game program restarted. The retention column in the tables below is part of each topic's definition, not a per-message choice — the retain flag is set per publish, and a state topic published once without it leaves later subscribers seeing a stale value.

**Clean session on every client.** A persistent session would queue commands during an outage and replay a burst of stale ones at reconnect. Every client resubscribes on connect; the birth-and-sync handshake in §8 recovers state without the replay.

**Low message rate.** The ESP32 publishes debounced state changes only, never raw samples — a ringing station is a 40Hz pulse train at the detector (station §3.7) and one `ring` message on the bus. The audio program publishes detector results on change only, after two consecutive hops agree (audio.md §6.2). A whole call is a handful of messages. Round-trip latency on a local link at QoS 1 is a few milliseconds, negligible against the 150ms ring debounce.

# 3. Topic Naming

Every topic begins `sbgame/`. Two letters were used at first (`sw/`), which could mean switch, software or southwest to anything else that later lands on the same broker; `sbgame/` names the exhibit, is unlikely to collide, and is still one segment so wildcards work unchanged. `sb/` was considered for typing convenience and rejected on the same grounds — the prefix is typed once into each codebase and thereafter comes from shell history.

Below the prefix:

- `station/<n>/…`, n = 1–22, and `trunk/<n>/…`, n = 1–8 — per-circuit topics, whichever client publishes or consumes them. Board 3's last two strips are not stations: strip 7 is the operator tap and strip 8 is the audience monitor output (station §7.9.6) — no relay, no ring detector, no pilot of their own — and neither has topics. n is the circuit's own number, not the 1–32 comb slot of station §8.3, which exists so one formula maps a circuit to its FFT bin and is internal to the audio program's detector.
- `audio/…` — the audio program's non-circuit state and commands: the loudspeaker monitor and its source, the test tone per output channel, the tap's own-tone check. Channel numbers under `audio/test/` are 1–34 output channels as the documents number them (audio.md §2), not circuits.
- `game/…` — the game program's own state, and the page's commands to it: the run state, pacing, tallies, call slots and log (Rev 10). Call slot numbers under `game/call/` are 1–8 and are not circuits.
- `board/station/<n>/…`, n = 1–30, and `board/trunk/<n>/…`, n = 1–10 — the switchboard's own jacks, numbered as on the board (Rev 12). They are not circuits. A jack carries at most one circuit, named in its `circuit` topic.
- `ctl/…` — system-level control and liveness.

A **circuit id**, wherever a payload carries one, is the string `station/<n>` or `trunk/<n>` — the same two segments as the topic, so prefixing a circuit id with `sbgame/` gives that circuit's topic root. A slot number never appears on the wire.

A command topic is the state topic it commands with `/set` appended: `hook` is a station's hook state, `hook/set` commands it; `play` is what a circuit is playing, `play/set` commands it. The consuming client echoes the resulting state on the state topic, so a subscriber watching `hook` or `play` sees the command take effect and can tell a command that was acted on from one that was not. `game/next/set` is the one command with no state topic of the same name; its effect shows as `game/started` going up by one.

# 4. Messages Published by the ESP32

The ESP32 publishes hardware state as it debounces it (`control.md` §7 and §8) and its own liveness. The game program and the status page subscribe to all of it; the log may.

| **Topic** | **Payload** | **Retained** | **Meaning** |
| --- | --- | --- | --- |
| `sbgame/station/<1-22>/ring` | `"on"` or `"off"` | yes | Ring voltage is arriving at this station from the switchboard. Debounced from the 40Hz detector pulse train, station §3.7. |
| `sbgame/station/<1-22>/hook` | `"on"` or `"off"` | yes | Off-hook relay state, echoed from the relay drive. `"on"` is off-hook (loop closed). |
| `sbgame/trunk/<1-8>/seize` | `"on"` or `"off"` | yes | The switchboard has seized this trunk — loop current is flowing. Debounced, trunk §11.1. The trunk analogue of a station's `hook`. |
| `sbgame/trunk/<1-8>/ring` | `"on"` or `"off"` | yes | This trunk's ring relay is energised — the board is applying ring toward the switchboard. Actual relay state, echoed back, so a monitoring UI can show a ringing trunk. |
| `sbgame/trunk/<1-8>/digit` | `"0"` to `"9"` | no — and QoS 0, §2 | The operator has just dialled this digit on the seized trunk. One message per completed digit, in order; ten pulses is `"0"`. Decoded by the firmware from the seizure input, control.md §8.2. Never published outside seizure, never for a partial digit. |
| `sbgame/trunk/<1-8>/fault` | `""`, `"ring_on_trunk"` or `"bad_dial"` | yes | `"ring_on_trunk"`: the operator has applied ring to this trunk by mistake (trunk §5.2). `"bad_dial"`: a pulse train outside the dial timing windows, or more than ten pulses (control.md §8.2). Empty clears either. |
| `sbgame/ctl/status` | `"online"` or `"offline"` | yes | Birth message and last will (§8). |
| `sbgame/ctl/esp_heartbeat` | uptime in seconds | no | Every 1s from the main loop, after the I²C poll (§8). |
| `sbgame/ctl/i2c` | `"ok"` or `"missing: "` + absent addresses in hex, e.g. `"missing: 0x22 0x23"` | yes | Result of the boot-time expander scan, republished after any rescan (control.md §4.2, §6.2). While it reads missing, the bridge is not armed and commands for circuits on the absent board are dropped. |

The trunk topics are not the station topics with a different noun. A station is commanded off-hook and reports ring arriving; a trunk is commanded to ring and reports seizure. There is no hook to set on a trunk and a station has no ring command. `ring` keeps its name on both but inverts in meaning: on a station it reports ring received, on a trunk it echoes the ring the board is applying. `seize` is the trunk analogue of `hook`.

# 5. Messages Published by the Audio Program

The audio program publishes what its pilot detector finds, per circuit; the state of everything it has been commanded to do, as the echo of each command; and its own liveness. It never commands anything. The game program and the status page subscribe; the log may. What each state means in detail, and when it changes, is `audio.md` §6 to §11.

| **Topic** | **Payload** | **Retained** | **Meaning** |
| --- | --- | --- | --- |
| `sbgame/station/<1-22>/peer` | circuit id, `""`, `"ambiguous"` or `"deaf"` | yes | Which circuit this station is patched to through the switchboard, from the comb pilot heard on its receive channel (station §8.7). See §7 for the four values. |
| `sbgame/trunk/<1-8>/peer` | circuit id, `""`, `"ambiguous"` or `"deaf"` | yes | The same for a trunk. |
| `sbgame/station/<1-22>/op` | `"on"` or `"off"` | yes | The operator tone (bin 768) is heard on this station's receive channel — the operator is bridged to it. |
| `sbgame/trunk/<1-8>/op` | `"on"` or `"off"` | yes | The same for a trunk. |
| `sbgame/station/<1-22>/play`, `sbgame/trunk/<1-8>/play` | base filename, `""` or `"missing"` | yes | The file now playing on this circuit's output. Empty when nothing is — which is how a file's finishing is reported (audio.md §7.4). `"missing"`: the last `play/set` named a file that could not be loaded; persists until the next `play/set`. |
| `sbgame/trunk/<1-8>/tone` | `"dial"`, `"ringback"`, `"busy"` or `""` | yes | The tone now playing on this trunk. Empty when none. |
| `sbgame/station/<1-22>/listen`, `sbgame/trunk/<1-8>/listen` | `"listening"`, `"speech"`, `"silence"`, `"timeout"` or `""` | yes | The listen on this circuit as it runs: `"listening"` from the command; `"speech"` when speech starts, and the listen continues; `"silence"` when it ends, which finishes the listen; `"timeout"` if speech never started within the commanded seconds or never ended within the program's cap. The final value persists until the next `listen/set`; empty after a cancel (audio.md §9.1). |
| `sbgame/audio/monitor` | `"off"` or gain in dB | yes | The loudspeaker feed: muted, or the gain applied, as a signed decimal string. Echoes `monitor/set` after clamping to range (audio.md §10.2). |
| `sbgame/audio/monitor/source` | `"tap"` or circuit id | yes | The receive channel the loudspeaker is fed from: the operator tap, or that station's or trunk's. Echoes `monitor/source/set` once the switch is made; `"tap"` after the program loses the game or the broker (audio.md §10.3, §13.2; Rev 13). |
| `sbgame/audio/test/<1-34>` | `"on"` or `"off"` | yes | A 1kHz test tone is on this output channel, displacing everything else on it (audio.md §11.1). |
| `sbgame/audio/optone` | `"ok"` or `"deaf"` | yes | The tap's own operator tone is returning on its own receive channel (station §8.4). `"deaf"` means no circuit can hear the operator either. |
| `sbgame/ctl/audio_status` | `"online"` or `"offline"` | yes | Birth message and last will (§8). |

`peer` and `op` come from the same `identify_peer()` result and are independent facts: the operator can listen in on a connected call (`peer` set, `op` on), answer a station patched to nothing else (`peer` empty, `op` on), or be absent from either. When the operator is bridged across a connected pair, both ends report `op` on, which is correct and not a fault.

The `op` topic is per circuit rather than one set-valued topic on the operator's side because detection is per circuit (station §8.7), because a per-circuit topic is single-valued like every other state topic, and because the game program can then subscribe to `sbgame/+/+/op` and get a retained `"on"` or `"off"` per circuit rather than diffing successive lists to learn who joined or left.

`play` and `tone` are never both non-empty on one circuit: a circuit plays one thing at a time, and commanding the other replaces it (audio.md §5.2). To know what a circuit is doing, read both.

# 6. Messages Published by the Game Program

The game program is the only client that commands the ESP32 and the audio program. The consumer column says which client subscribes to each; the other client does not, and must not use a wildcard that would deliver the other's commands to it.

| **Topic** | **Payload** | **Retained** | **Consumer** | **Meaning** |
| --- | --- | --- | --- | --- |
| `sbgame/station/<1-22>/hook/set` | `"on"` or `"off"` | no | ESP32 | Take this station off-hook / on-hook. The ESP32 echoes the result on `hook`. |
| `sbgame/trunk/<1-8>/ring/set` | `"on"` or `"off"` | no | ESP32 | Start / stop ringing this trunk. The ESP32 runs the cadence and the 30s timeout (`control.md` §8) and echoes the relay state on `ring`. |
| `sbgame/station/<1-22>/play/set`, `sbgame/trunk/<1-8>/play/set` | base filename, or `"stop"` | no | audio | Play `<wav-dir>/<name>.wav` on this circuit's output, replacing whatever it is playing; `"stop"` stops it. Echoed on `play`; finishing is `play` going empty. |
| `sbgame/trunk/<1-8>/tone/set` | `"dial"`, `"ringback"`, `"busy"` or `"off"` | no | audio | Play this tone on the trunk until told otherwise; a new value replaces the current tone. Trunks only — a station is the telephone and sends none of them. Echoed on `tone`. |
| `sbgame/station/<1-22>/listen/set`, `sbgame/trunk/<1-8>/listen/set` | timeout in seconds, or `"0"` | no | audio | Listen on this circuit's receive channel, allowing this long for speech to start; `"0"` cancels. The sequence — start of speech, then end or timeout — is reported on `listen`. |
| `sbgame/audio/monitor/set` | `"off"` or gain in dB | no | audio | Feed the monitor's source to the loudspeaker at this gain, 0 being unity into A32 output 24, range −60 to +20; or mute. Echoed on `monitor`. |
| `sbgame/audio/monitor/source/set` | `"tap"` or circuit id | no | audio | Feed the loudspeaker from this receive channel: the operator tap, or a station 1–22 or trunk 1–8. The game program sends the calling line when the operator answers a call, and `"tap"` when a game starts or stops (game_control.md §6.4). Echoed on `monitor/source` (Rev 13). |
| `sbgame/audio/test/<1-34>/set` | `"on"` or `"off"` | no | audio | 1kHz test tone on this output channel. Echoed on `test/<ch>`. |
| `sbgame/ctl/game_heartbeat` | host Unix time in seconds | no | ESP32, audio and the page | Every 1s from the game loop (§8). The ESP32 and the audio program use its arrival only; the page also takes the host's clock from it (Rev 10; empty through Rev 9). |
| `sbgame/ctl/sync` | — | no | ESP32 | Ask the ESP32 to republish every state topic (§8). |

There is no `peer/set`, `op/set` or `optone/set` and never will be: topology is detected, not commanded. There is no `sync` for the audio program: its state topics are all either detector results, which it republishes on change and on start, or echoes of commands it holds, which it republishes on reconnect (§8.4).

## 6.1 Game State

Published by the game program for the status page and the log (Rev 10). All retained. What each value means, and when it changes, is `game_control.md` §3 to §6.

| **Topic** | **Payload** | **Retained** | **Meaning** |
| --- | --- | --- | --- |
| `sbgame/ctl/game_status` | `"online"` or `"offline"` | yes | Birth message and last will (§8.1). |
| `sbgame/board/station/<1-30>/label`, `sbgame/board/trunk/<1-10>/label` | text, or `""` | yes | The label on this switchboard jack, such as `"463"` or `"lobby"`: the `label:` of the script.yml `jacks:` item for this jack, whether or not a station is cabled to it (Rev 18). Empty for a station jack `jacks:` does not list, and for every trunk jack. Published at start (Rev 12; source script.yml since Rev 14). |
| `sbgame/board/station/<1-30>/circuit`, `sbgame/board/trunk/<1-10>/circuit` | circuit id, or `""` | yes | The game circuit cabled to this jack, such as `"station/11"`: the `number:` of the station that this jack's `jacks:` item names as its `station:`, or `trunk/n` on trunk jack n for n = 1–8. Empty otherwise, including for a labelled jack with nothing cabled (Rev 18). Published at start (Rev 12; source script.yml since Rev 14). |
| `sbgame/game/run` | `"on"` or `"off"` | yes | A game is running. Echoes `run/set`. |
| `sbgame/game/pace` | `"manual"` or `"auto"` | yes | Call pacing. Echoes `pace/set`. |
| `sbgame/game/gap` | seconds | yes | Automatic pacing: the gap from a call's connection to the next call's start, at the start of a game. Echoes `gap/set` after clamping. |
| `sbgame/game/ramp` | seconds | yes | Seconds taken off the gap for each call connected. Echoes `ramp/set`. |
| `sbgame/game/floor` | seconds | yes | The least the gap can fall to. Echoes `floor/set`. |
| `sbgame/game/jitter` | percent | yes | The spread of each automatic wait around `gap_now`: each is drawn evenly from `gap_now × (1 ± jitter/100)`. Echoes `jitter/set` (Rev 19). |
| `sbgame/game/gap_now` | seconds | yes | The gap in use now, after the ramp: the centre of the jitter's spread. |
| `sbgame/game/next_at` | host Unix time in seconds, or `""` | yes | When the next call will start, after the jitter's draw; empty when none is scheduled. |
| `sbgame/game/started` | integer | yes | Calls started this game. Goes up by one when `next/set` starts a call. |
| `sbgame/game/success` | integer | yes | Calls that ran to their scripted end this game. |
| `sbgame/game/fail` | integer | yes | Calls that failed this game. |
| `sbgame/game/call/<1-8>/number` | integer, or `""` | yes | The call number in this slot. |
| `sbgame/game/call/<1-8>/scene` | scene id, or `""` | yes | The scene in this slot; empty when the slot is free. |
| `sbgame/game/call/<1-8>/from`, `…/to` | line name, or `""` | yes | The calling and called lines from script.yml. `to` is empty for a call to the operator. |
| `sbgame/game/call/<1-8>/trunk` | circuit id, or `""` | yes | The trunk carrying the call, once known. |
| `sbgame/game/call/<1-8>/stage` | stage name, or `""` | yes | `signalling`, `request`, `routing`, `dialling`, `ringing`, `busy`, `talking` or `operator` (game_control.md §6.1). |
| `sbgame/game/call/<1-8>/since` | host Unix time in seconds, or `""` | yes | When the stage began. |
| `sbgame/game/call/<1-8>/deadline` | host Unix time in seconds, or `""` | yes | When the stage times out; empty if it does not. |
| `sbgame/game/call/<1-8>/digits` | digits, or `""` | yes | Digits dialled so far on an outgoing call. |
| `sbgame/game/log` | text | yes | The last 50 events, newest first, one per line (game_control.md §6.2). |
| `sbgame/game/error` | text, or `""` | yes | The last page command the game program rejected, and why; cleared by the next accepted command. |

## 6.2 Messages Published by the Status Page

The page's commands, consumed by the game program only (Rev 10). The page publishes nothing else, and the broker enforces that (§9).

| **Topic** | **Payload** | **Retained** | **Consumer** | **Meaning** |
| --- | --- | --- | --- | --- |
| `sbgame/game/run/set` | `"on"` or `"off"` | no | game | Start a game — ignored while one is running — or stop it. Echoed on `run`. |
| `sbgame/game/pace/set` | `"manual"` or `"auto"` | no | game | Call pacing. Echoed on `pace`. |
| `sbgame/game/gap/set` | seconds | no | game | Starting gap for automatic pacing, 0–600. Echoed on `gap`. |
| `sbgame/game/ramp/set` | seconds | no | game | Reduction per call connected, 0–60. Echoed on `ramp`. |
| `sbgame/game/floor/set` | seconds | no | game | Least gap, 0–600 and not above `gap`. Echoed on `floor`. |
| `sbgame/game/jitter/set` | percent | no | game | Spread of the automatic wait, 0–100. Echoed on `jitter` (Rev 19). |
| `sbgame/game/next/set` | ignored | no — and QoS 0, §2 | game | Start the next call now, if a game is running and a scene can be dealt; otherwise reported on `error`. Shows as `started` going up by one (Rev 11; a call number through Rev 10). |

# 7. Payload Conventions

**`"on"` and `"off"`** are the only two values of every binary topic. Lower case, no quotes on the wire.

**Circuit id** is `station/<n>` or `trunk/<n>`, §3.

**Monitor source** on `monitor/source/set` and `monitor/source` is a circuit id or the literal `"tap"`, which is not a circuit id: the tap has no circuit topics (§3). Same convention as the `peer` diagnostics below (Rev 13).

**`peer` has four values**, and a subscriber must handle all of them:

- a circuit id — connected to that circuit;
- empty payload — idle, not patched to anything. Published retained, an empty payload deletes the retained value at the broker, so a cold subscriber sees nothing rather than a stale id. The same convention as `fault`;
- `"ambiguous"` — more than one comb pilot heard: a threshold, crosstalk or cord fault, station §8.7. A diagnostic, not a topology;
- `"deaf"` — the circuit cannot hear its own pilot: a fault in its own transmit path, transformer or cabling. Also a diagnostic.

The two diagnostics are literal strings on the same topic, rather than a separate status topic, so that a subscriber that treats anything non-empty as a circuit id fails loudly in the log rather than silently in the game. `play` uses the same convention for `"missing"`.

**Empty payload on a retained topic** means "clear": it removes the retained value. `fault`, `peer`, `play`, `tone` and `listen` use it, and so do the `board/` topics, `next_at`, `error` and every call slot topic (Rev 14; Rev 12 and 13 still named `name` here). On `listen`, empty is cancelled or never issued; a listen that completed reads `"silence"` or `"timeout"`, never empty, so the two are not confused.

**Filenames** on `play/set` and `play` are the base name only — no directory, no `.wav`, no path separator. The audio program rejects a payload containing `/` or `..`. `"stop"` is reserved as the stop verb on `play/set`, so no file may be named `stop`. It is the one place a filename and a verb share a topic; the alternative, a separate `play/stop` topic, would break the `/set` convention for one command.

**Tone names** on `tone/set` and `tone` are `"dial"`, `"ringback"` and `"busy"`, lower case. What each sounds like is audio.md §8.2; a new tone is a new name here and a row there.

**Gain in dB** on `monitor/set` and `monitor` is a signed decimal string: `"0"`, `"-12"`, `"6.5"`. No unit suffix, no `+`. The audio program clamps to its range and echoes what it applied, so the state topic may differ from the command.

**Seconds** on `listen/set` are a non-negative decimal string, capped by the audio program at 300. `"0"` is cancel. Seconds on the game's pacing topics are the same form; the game program clamps to the ranges in §6.2 and echoes what it applied.

**Host time** on `game_heartbeat`, `next_at`, `since` and `deadline` is Unix time in seconds as a decimal string, to a tenth of a second at most: `"1790000000.4"`. It is the host's clock, and the page measures every duration against it, not against its own (Rev 10).

**Integers** on the tallies and `number` are unsigned decimal strings with no leading zeros.

**Labels** on `board/…/label` are the text on the switchboard's designation strip, as the `label:` of a script.yml `jacks:` item gives it (Rev 14; from the station entry until Rev 18), UTF-8, no length rule beyond what fits a tile.

**Line names** on `from` and `to` are the keys of script.yml's `stations:` and `outside:` maps, as written there.

**The log** is plain UTF-8 text, lines separated by `\n`, newest first, at most 50 lines.

**Heartbeats** carry uptime in seconds on the ESP32 side, so a log shows a reboot, and host time on the game side (Rev 10; nothing through Rev 9).

**Digits** are one character each, `"0"` to `"9"`, one message per digit, on `trunk/<n>/digit`. The game program assembles them into a number: the firmware does not know how many digits to expect and does not need to. A digit is an event — one of two in the design, with `game/next/set` — so the topic is never retained (a retained digit would replay into a later call) and a subscriber arriving mid-number has missed the earlier digits; there is nothing to resynchronise from, which is the cost recorded in §11. The game program's call slot `digits` carries the number so far for display, so the page does not depend on having seen every digit event.

# 8. Liveness and Recovery

Three clients, three different ways of dying, and the broker sees none of them the same way. This section is the protocol; what each client does about it is in that client's own document (`control.md` §9 for the controller, `audio.md` §13 for the audio program, `game_control.md` §3 and §7.2 for the game program and the page).

## 8.1 Birth and Last Will

The ESP32 connects with a **last will and testament** (LWT) of `"offline"` on `sbgame/ctl/status`, retained, and immediately publishes `"online"` to the same topic itself — the birth message. A last will is a message the broker holds on the client's behalf and publishes only if the client disappears without disconnecting cleanly: the TCP connection drops, or the keepalive pings stop. While the ESP32 runs, the topic reads `online`; the moment the broker loses it, the topic flips to `offline` with nothing on the ESP32's side having to act.

The audio program does the same on `sbgame/ctl/audio_status`. It exists because `peer` and `op` are retained: an audio program that has died leaves the last topology it saw on the broker looking current, and the game program must treat those values as stale while `audio_status` is `offline`. The same applies to `play`, `tone` and `listen`: a `"listening"` that outlives the audio program will never resolve, and the game program should treat every audio state topic as stale, and every wait on one as failed, while `audio_status` is `offline`.

The game program does the same on `sbgame/ctl/game_status` (Rev 10), for the same reason: `game/run`, the tallies and the call slots are retained, and a game program that has died leaves them on the broker looking current. The page treats every game topic as stale while `game_status` is `offline`, and disables its controls. The game heartbeat already told the ESP32 and the audio program the same thing; the will tells the page promptly without it having to time the beats, and the page times the beats as well (game_control.md §7.2).

Set the ESP32's MQTT keepalive to 5s so the broker notices a lost controller promptly and fires the will.

## 8.2 Two Heartbeats, and Why Both

The LWT is a notification, not a failsafe: it tells the host the controller has gone, but it cannot open a relay. Nothing on the host can. So the ESP32 must release every relay on its own when it loses contact, and there are two distinct ways contact can be lost:

— **Network or broker loss.** The ESP32 sees its MQTT connection drop and releases all relays immediately. The keepalive also lets the broker fire the LWT.

— **Game program dead with the broker healthy.** The connection stays up and nothing looks wrong from the ESP32's side. This is what `sbgame/ctl/game_heartbeat` is for: the game program publishes it every second from its game loop, and if the ESP32 misses two consecutive beats it releases all relays even though MQTT is healthy. Without it a crashed game program leaves stations held off-hook indefinitely, tying up switchboard cord circuits and presenting to the operator as a hardware fault. On the trunk side the same failure leaves a trunk ringing, which is why the ESP32 also runs a 30s hard ring timeout of its own (`control.md` §8).

The audio program subscribes to the same heartbeat and applies the same rule: two missed beats, or loss of the broker, stops every trunk tone and every file it is playing and cancels every listen (audio.md §13.2). The failure is the audio twin of the held relay — a crashed game leaving ringback on a trunk for as long as the program runs. The pilots, the operator tone and the monitor are not stopped; they were not started by the game and are harmless without it. The monitor's source returns to the tap, since the calls a circuit source was following have been torn down (Rev 13).

The same argument runs the other way. The ESP32's keepalive proves its network stack is alive, not that its main loop is polling the expanders and driving relays — and whether those are the same thing depends on the MQTT client. With a client whose ping is sent from the main loop, a wedged loop stops the ping and the LWT fires; with a client that runs in its own task, as ESP-IDF's does, a wedged loop keeps the connection alive indefinitely, the host sees `online`, commands `hook/set`, and nothing happens. The only symptom would be that the echoed `hook` never changes. So the ESP32 publishes `sbgame/ctl/esp_heartbeat` every second **from the main loop, after the I²C poll**, so that it proves the loop that matters and not the network task. The game program treats two consecutive missed beats as ESP32-down: it stops issuing commands, marks every circuit unknown, puts it on screen, and publishes `sync` when the beat returns.

The ESP32 heartbeat is also the periodic reassurance that retained state is current. A retained value is what the ESP32 last said, not what the hardware is doing now; the beat proves the loop that would have said otherwise is running.

The audio program has a will but no heartbeat. Its main loop is the audio callback, and if that stops the A32 stream stops with it — a louder failure than a wedged ESP32 loop, and one the game program can already see from `audio_status` and from `peer` values that stop changing. That reasoning is weaker now that the program has an MQTT thread separate from its audio thread (audio.md §3): the MQTT thread can hold the connection open while the audio thread is wedged, and then a `listen` never resolves and a `play` never clears. Until §11 settles whether it gets a heartbeat, the game program applies its own deadline to anything it waits on from the audio program — the listen timeout plus a margin, the file's known length plus a margin — and treats a missed deadline as audio-program-down.

The page has neither a will nor a heartbeat. Nothing depends on it being there: it commands only the game, and a page that vanishes mid-game leaves the game running on its own pacing, which is the right outcome.

## 8.3 Sync

`sbgame/ctl/sync` asks the ESP32 to republish every state topic it owns. The game program publishes it when `ctl/status` transitions to `online` and when `esp_heartbeat` returns after an outage, and the two sides are back in step without any replayed commands. The ESP32 may also republish all state on a slow timer of its own (`control.md` §9), which bounds how long a lost publish can leave a retained value stale; subscribers must therefore react to changes in value, not to the arrival of a message.

## 8.4 Recovery Sequence

On ESP32 connect: LWT registered, `status` = `online`, subscribe to `hook/set` and `ring/set` for every circuit, `game_heartbeat` and `sync` — those four patterns and not a wildcard over every `set`, since the audio program's commands share the circuit topics — then publish every state topic once. Relays are all released at that point regardless, since the ESP32 releases them on any loss of contact and boots with them released.

On game program start: connect with its will of `"offline"` on `game_status`; publish its game state — `run` `"off"`, pacing values from its configuration, tallies zero, every call slot cleared, `next_at` and `error` cleared, the log with one start line, every `board/` label and circuit — then `game_status` = `"online"`, state before birth as the audio program does. Then subscribe to everything, read the retained state, publish `sync` to be sure, start the heartbeat. If `status` reads `offline`, wait — commands sent now go nowhere and are not queued (clean session). If `audio_status` reads `offline`, the same for audio commands. A game program that restarts never resumes a game; the page starts a new one.

On audio program start or reconnect: publish `play`, `tone` and `listen` empty for every circuit, `monitor` and `monitor/source` as configured, `test/<ch>` off for every channel; then `peer`, `op` and `optone` from the first detector pass; then `audio_status` = `online`. State before birth, so a subscriber that sees `online` already has consistent values (audio.md §12). Nothing it was doing before a broker loss survives it: tones and files were stopped when the connection dropped (§8.2), so the empty `play` and `tone` published on reconnect are true.

On page connect or reconnect: subscribe to `sbgame/#`. The retained topics are the whole state; there is nothing to ask for.

# 9. Broker Configuration

Mosquitto on the Linux host, portland, with two listeners — plain MQTT for the three clients, and plain WebSockets on loopback for the page, which reaches it through nginx — no anonymous clients, and an access list. On Ubuntu, in `/etc/mosquitto/conf.d/sbgame.conf`; the distribution's own `mosquitto.conf` already sets persistence and the log and includes that directory.

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

Mosquitto served the page itself through Rev 16, from `http_dir` on a TLS listener on 443. It cannot on this build (§1.17): libwebsockets creates the WebSockets socket after the drop to the `mosquitto` user, so a privileged port will not bind, and the listener advertises HTTP/2 in ALPN without being able to serve it, which a browser negotiates by default. nginx does both jobs instead, and Mosquitto's WebSockets listener carries no TLS and is bound to loopback, so nothing off the host can reach it.

**nginx**, `/etc/nginx/sites-available/sbgame`, enabled and with the distribution's default site removed:

```text
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name game.kr3am.org;

    ssl_certificate     /etc/letsencrypt/live/game.kr3am.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/game.kr3am.org/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    root /srv/sbgame/web;
    index index.html;

    location /mqtt {
        proxy_pass http://127.0.0.1:9001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    location / {
        try_files $uri $uri/ =404;
    }
}
```

`listen 443 ssl http2` is the form Ubuntu 24.04's nginx 1.24 takes; the `http2 on` directive is 1.25.1 and later. The read and send timeouts are an hour because a game can sit idle between calls and the socket must not be dropped for it.

nginx's master process runs as root and reads the certificate straight from `/etc/letsencrypt/live`, so no copy of the key is made and the deploy hook is a reload (§9.1). The page's files are read by the worker, as `www-data`, from `/srv/sbgame/web`, which is world-readable.

## 9.1 The Certificate

Let's Encrypt, for `game.kr3am.org`, by the DNS-01 challenge through Route 53 (Rev 15). On the host:

```text
apt install certbot python3-certbot-dns-route53
certbot certonly --dns-route53 -d game.kr3am.org
```

The plugin writes the TXT record `_acme-challenge.game.kr3am.org`, waits for it to propagate, and removes it after validation. It uses the AWS credentials of the user certbot runs as, which is root, from `/root/.aws/credentials`. Those belong to an IAM user whose policy allows only what the plugin needs, on kr3am.org's hosted zone alone:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow",
      "Action": ["route53:ListHostedZones", "route53:GetChange"],
      "Resource": "*" },
    { "Effect": "Allow",
      "Action": "route53:ChangeResourceRecordSets",
      "Resource": "arn:aws:route53:::hostedzone/<kr3am.org zone id>" }
  ]
}
```

The credentials go under `[default]`. boto3 reads that profile unless `AWS_PROFILE` names another, and `certbot renew` runs from `certbot.timer` with an empty environment, so a named profile would need a systemd drop-in to be seen and every unattended renewal would fail without one. `[default]` in the root account, which has no other AWS use, avoids that.

**Renewal.** The certbot package installs a systemd timer that runs `certbot renew` twice a day, and a certificate is renewed once it is within 30 days of expiry. No cron job is written. Renewal needs the host to reach Let's Encrypt and Route 53, which it does at home. On the road it may not, and does not need to: a certificate last renewed at home has at least 30 days left.

**Handing it to nginx.** nginx's master process is root and reads `/etc/letsencrypt/live` directly, so nothing is copied and the key never leaves that directory. The deploy hook, which certbot runs after each successful renewal, only tells nginx to reread it. `/etc/letsencrypt/renewal-hooks/deploy/nginx`, mode 755:

```sh
#!/bin/sh
set -e
systemctl reload nginx
```

**Reload, not restart** — and with nginx it is no longer in doubt. A reload starts new worker processes with the new certificate and lets the old ones finish their connections, so no client is disconnected. Rev 15 and Rev 16 had Mosquitto holding the certificate, where whether SIGHUP rereads it on a libwebsockets listener was unconfirmed and had to be checked at commissioning, with a 04:00 restart as the fallback if it did not. Mosquitto holds no certificate now, so the check and the fallback are both withdrawn (Rev 17).

This matters because a restart of Mosquitto drops every client: the ESP32 releases every relay on losing the broker (§8.2), and the game program stops a game in progress (game_control.md §3). A reload of nginx touches neither — their connections are to Mosquitto, which is not reloaded at all.

## 9.2 The Name

`game.kr3am.org` resolves to portland's address. That address is the same at home and on the travel router, whose LAN mirrors the home subnet and its reservations. How the name reaches the iPad differs by place (Rev 16):

- **At home**, public DNS: an A record in Route 53, in the kr3am.org zone, `game.kr3am.org` to portland's address. OPNsense's resolver returns it as it does for portland's existing Route 53 name on the other domain. No entry on OPNsense.
- **On the road**, the GL.iNet Slate 7: NETWORK → DNS → Edit Hosts, one line with the same name and address. It answers without an upstream, so it works at a venue with no internet, and it is not subject to the router's filtering of public answers that point at private addresses. If AdGuard Home is turned on in that router, the router stops consulting Edit Hosts, and the entry moves to AdGuard Home's DNS rewrites.

The iPad takes its DNS from whichever router it is on, so it needs no setting of its own. The certificate's challenge TXT record sits in the same zone during issue and renewal and does not disturb the A record.

If the host's address ever changes, the Route 53 record and the Edit Hosts line change together.

A certificate validates offline once issued, so the page works at a venue with no internet. What must be right is the name, which the travel router answers without an upstream, and the iPad's clock, which iOS keeps.

# 10. How the Design Got Here

Recorded so the reasoning survives the move from the circuit documents, whose change lists carry the originals.

- The link was USB serial until station Rev 3.1 and MQTT over PoE Ethernet since.
- The trunk topics were once specified as the station topics with a different noun (station Rev 3.x, corrected at trunk §11.3 and station §1.2): a trunk has no hook to set and needs a ring command.
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

- Whether the ESP32 republishes all state on a timer as well as on `sync`, and at what interval, is left to `control.md`.
- `digit` is an event and so cannot be recovered after a game-program restart mid-number, and cannot be made idempotent. The alternative considered was a retained `sbgame/trunk/<n>/dialled` carrying the accumulated digit string since seizure, cleared to empty on seizure and release — absolute state, idempotent, QoS 1, and a cold subscriber sees the digits so far. It was not adopted because the number's length and meaning belong to the game program, and because a game restart mid-dial is a situation the game cannot recover from anyway. Revisit if that turns out to matter. (The call slot's `digits`, Rev 10, covers the page's need for display.)
- Whether the audio program gets a heartbeat of its own, `sbgame/ctl/audio_heartbeat`, published from the audio thread once a second after a detector hop so that it proves the thread that plays and listens rather than the one that talks to the broker — the ESP32's argument in §8.2 applied to the audio program. Not added at Rev 5 because the game's own deadlines on `listen` and `play` cover the cases that matter and the pilots stopping is visible anyway; add it if a wedged audio thread is ever seen with `audio_status` still online.
- Whether the audio program should accept `listen/set` on the tap channel, which always carries the operator's voice. audio.md §16.
- The page's commands will grow as `game_control.md` §10 settles — a fixed-interval pacing value on `pace`, a named scene to start, timeouts. Each is one more `sbgame/game/…/set` and covered by the access list's existing pattern.
- The page has only one user, `sbgame-web`, and anyone on the network who loads it can run the game. Acceptable at the bench and behind the travel router. For a public event where the Wi-Fi is shared, a second, private page could hold the password. Rev 10 to Rev 14 listed TLS on the listener here as the other half of that; it was taken at Rev 15 (§9).
- `http_dir` is no longer used, so its removal in Mosquitto 3.0 no longer matters (Rev 17, §9). nginx serves the page's files and Mosquitto's WebSockets listener carries MQTT alone, which is not marked for removal. What moving past 2.x now means for this system is the `per_listener_settings` and password-file defaults, not the page.
