**551 Switchboard Simulator**

**Game Control and the Status Page**

*Rev 15 — Start and Stop, Manual and Automatic Call Pacing with a Ramp and Jitter, Scenes Dealt from a Shuffled Deck, Tallies, Calls in Progress and the Log, the Switchboard's Jacks and Labels from script.yml, the Audience Loudspeaker Following the Call the Operator Last Answered, an iPad Page Served by nginx over HTTPS at game.kr3am.org and Talking MQTT over Secure WebSockets, the Game's Controls on a Stream Deck+, Only Active Scenes Played*

# 1. Overview

This document specifies how the game is run: starting and stopping a game, pacing the calls, counting how the operator did, and a status page on an iPad that shows the whole system while it runs. From Rev 13 the controls are on an Elgato Stream Deck+ beside the switchboard (§7.4), and the page becomes a display. It covers three things that are written together:

- **What the game program does** with each control — the meaning of a game, of pacing, of success and failure. There is no game program specification yet; when one is written, §3 to §6 move into it and this document keeps the page.
- **The status page** — one HTML page with its script, served by nginx and connected to Mosquitto over MQTT on WebSockets through the same nginx (Rev 10). It has no server of its own and no code on the host beyond the game program's topics.
- **The Stream Deck** (Rev 13) — a Stream Deck+ on USB to the host, driven by a small program of its own, `sbgame-streamdeck`, that talks MQTT to the same broker. It carries Start, Stop, the pacing, Next Call and the four pacing values, and shows the tallies and the health of the three clients.

Every topic named here is defined in `mqtt.md` (Rev 10, §6.1 and §6.2), which owns names, payloads, retention and the broker's access list. This document says what the values mean and when they change. It does not repeat the tables.

The page reads the bus directly rather than through the game program. That is the reason for the design: it shows what the controller and the audio program actually report, and it keeps working when the game program is down — which is when it is most needed. The page commands only the game program, and the broker's access list holds it to that (`mqtt.md` §9).

The Stream Deck program follows the same design for the same reason (§7.4). It commands the game over the broker as the page does, and displays only what the broker reports.

The game program, the page and the Stream Deck program are written by Claude Code to this document, like `control/control.ino` to `control.md` and `sbaudio` to `audio.md`.

## 1.1 Changes in Rev 1

— New document, 2026-09-24. Mark's requirements: start and stop the game; call rate either manual — a button on the page starts the next call — or automatic, the next call starting a set number of seconds after the operator has connected the current one; optionally a rate that rises over the game; tallies of calls handled, successes and failures; and a display of the state of everything, initially for Mark's own use at the bench.

— Option B of the discussion that produced it: the page talks MQTT to Mosquitto over WebSockets, and Mosquitto serves the page's files from its `http_dir`. The alternative — an aiohttp server inside the game program pushing state over its own WebSocket — was less code in the browser but more on the host, and would have taken the display down with the game program.

— Deferred at Mark's request: a new call arriving before the operator has connected the current one (§4.5).

## 1.2 Changes in Rev 2

— Which scene comes next (§4.4). Rev 1 said scenes are drawn at random, following script.yml's "Order" comment, and did not say how. An independent draw per call can repeat a scene while others have not been played. Mark wants every scene played before any repeats, in a random order. At game start the game program now shuffles every scene without `after:` into a list, the deck, and deals from it. When the deck runs out it is reshuffled, so a long game does not run out of calls. The deck is internal to the game program. The page is not told the order and does not need it, so `mqtt.md` does not change.

— A scene that cannot be dealt because one of its lines is busy stays at its place in the deck, and the next dealable scene is taken instead. Rev 1 said only that such a scene "is not drawn", which with a deck would either lose it or stall the game behind it.

— Two rules for `after:` scenes that the deck makes necessary. A line that a waiting `after:` scene will use counts as busy, so the deck does not deal a scene that would collide with a caller about to call back. And an `after:` scene follows only if the scene it follows was connected. Rev 1 started it whenever the earlier scene ended, which would have `nbn-trace` asking where a call came from when the call never reached the room.

— The shuffle's seed and the dealt order go into the SQLite session log, so a game can be replayed at the bench.

## 1.3 Changes in Rev 3

— People are now checked as well as lines (§4.4). Rev 2 held back a scene only if one of its lines was busy. The script has the same person on different lines: Pike calls room service from room 214, takes the reporter's call in room 214, and calls a cab from the lobby. With only lines checked, `pike-taxi` could be dealt while he was on the phone in his room. A scene is now held back if any of its lines or any of its people (script.yml `person:` under `calling` and `called`) is busy.

— Outside lines count as lines, as Mark decided. Rev 2 said "lines" without saying whether that meant outside names or only stations. Two calls to Sunny Hill Pizza now cannot overlap. The `operator` outside line counts like any other.

— An `after:` scene whose lines or people are busy when its delay runs out waits until they are free, then starts. Rev 2 reserved its lines only from when it was scheduled. A call already in progress at that moment could still be holding one of them.

## 1.4 Changes in Rev 4

— Next Call no longer carries a call number (§4.1), at Mark's request, because the game program keeps its own count. Rev 1 to Rev 3 had the page send one more than `started`, and the game program ignored anything else, so a resent command or a double tap started one call. Now a resent command cannot happen, because the command goes out at QoS 0. A double tap is prevented by the page disabling the button until the call starts. `mqtt.md` Rev 11 records `next/set` as the second event in the design.

## 1.5 Changes in Rev 5

— The page draws the switchboard as it is (§7.1): three rows of ten station jacks, numbered 1–30, over one row of ten trunk jacks. Each jack carries the label written on the board, such as `463` or `lobby`. Rev 1 to Rev 4 drew 22 station tiles and 8 trunk tiles in game circuit order, each named from script.yml. That order is not the board's order, and the operator never sees the circuit numbers.

— A new file, `wiring.yml`, maps game circuits to switchboard jacks and gives each jack its label (§6.3). Mark wires the 22 station circuits to whichever of the 30 station jacks he chooses, and the 8 trunk circuits to trunk jacks 1–8. The game program is the only program that reads the file. It publishes the map to the broker for the page. The controller and the audio program keep working in circuit numbers and never see jacks. `mqtt.md` Rev 12 adds the `board/` topics and removes `station/<n>/name`, which the jack labels replace.

— Tiles are simplified (§7.1). Mark expects the Rev 1 tile to be too crowded. A tile now shows the jack's label and number and one state at a time. Tapping it opens every topic for that jack's circuit. Rev 1 put all of them on the tile.

— A wiring check is added to commissioning (§9): ring each jack from the switchboard, and the matching tile on the page should flash. It uses only existing topics.

## 1.6 Changes in Rev 6

— The audience loudspeaker follows the calls (§6.4). Mark's decision, 2026-09-24. Until now the loudspeaker carried the operator tap alone (audio.md §10). The operator leaves a call when she throws the ring key to ring the called party, and does not come back to it, so the audience heard each request and then nothing of the conversation written for it. The game program now points the monitor at the calling line of the call the operator most recently answered, with `audio/monitor/source/set` (audio.md Rev 8 §10.3, mqtt.md Rev 13). That line's receive channel carries the caller, the operator while she is on the line, and the called party once the cord is up.

— The switch is made when the operator answers the new call, not when the call starts. Mark's first proposal was the start of the call. There is nothing on the calling line until the operator answers: a calling station is off-hook and silent, and a calling trunk is ringing, which puts a relay click on its channel at every cadence edge (trunk §8.1.1). Switching at the answer also leaves the audience on the current conversation until the operator actually picks up the next caller.

— The source goes back to the operator tap when a game starts and when it stops (§3).

— The page shows the monitor's source in its health area (§7.1), and the log records each move (§6.2). One commissioning step (§9) and one open item (§10) are added.

## 1.7 Changes in Rev 7

— The jack assignments move into script.yml, and `wiring.yml` is dropped (§6.3). Mark's decision, 2026-09-24. Rev 5 specified `wiring.yml` as a separate file mapping circuits to jacks, with labels. It was never written. Each entry under script.yml's `stations:` now carries two more keys: `switchboard:`, the jack the station's circuit is cabled to (1–30), and `label:`, the text on the board at that jack. `number:` is unchanged and is still the game's circuit. A station's name, circuit, jack and label are now in one place, which is where the script's author already looks.

— Trunks are not in script.yml, so trunk circuit n is on trunk jack n, fixed, for n = 1–8, as Mark cables them. Trunk jacks 9 and 10 carry nothing, and no trunk jack has a label. Rev 5's `wiring.yml` allowed trunk labels, and labels on station jacks with nothing cabled. Neither is carried forward: a jack that no station entry names is drawn as an empty outline.

— The checks at load follow (§6.3), and they belong in the one script.yml loader that the TTS task and the game program share (`tts_task.md` §3.1). Code consequence for Claude Code: the loader checks `switchboard:` and `label:` as well. `mqtt.md` Rev 14 corrects the `board/` rows, which said the map came from `wiring.yml`. No topic changes.

## 1.8 Changes in Rev 8

— The page is served over HTTPS as `https://game.kr3am.org/` and connects over secure WebSockets (§2), following mqtt.md Rev 15 §9, 2026-09-24, at Mark's request. Rev 1 to Rev 7 had the bookmark `http://<host>.local:9001/` and a `ws://` connection. The certificate, its renewal and how the name resolves are specified in mqtt.md §9.1 and §9.2, and are not repeated here.

— The page takes its WebSocket scheme from its own: `wss://` when loaded over `https:`, `ws://` when loaded over `http:`. Rev 1 to Rev 7 said `ws://` + `location.host`, which Safari refuses from an HTTPS page as mixed content. Code consequence for Claude Code, when the page is written.

— Commissioning (§9) follows. Steps 1 and 2 check the listener on 443 and the name and certificate from another machine. Step 10 is new: it checks whether Mosquitto reloads a renewed certificate on SIGHUP without dropping its clients. The answer decides whether renewal can safely happen during a game (mqtt.md §9.1).

— The page is now a secure origin, which lets it ask for a screen wake lock rather than rely on Auto-Lock being off (§7.3). Not specified; an open item (§10).

## 1.9 Changes in Rev 9

— Follows mqtt.md Rev 16, 2026-09-24. At home `game.kr3am.org` resolves from a public A record in Route 53; on the road the Slate 7's Edit Hosts line still answers it. Rev 8 said the name resolves only on the local network, through a host entry on both routers. §2 and the §9 preamble follow. Nothing on the page changes.

## 1.10 Changes in Rev 10

— The page is served by nginx, not by Mosquitto (§2), 2026-09-24. Rev 8 and Rev 9 had one Mosquitto listener on 443 serving the files through `http_dir` and carrying the page's MQTT connection. On portland that listener will not bind a privileged port, because libwebsockets creates its socket after Mosquitto drops from root, and it advertises HTTP/2 in ALPN without being able to serve it, so a browser negotiating HTTP/2 — which is the default — receives nothing. `mqtt.md` Rev 17 §1.17 records both, and what was tried before giving up on them.

— nginx now holds the certificate, serves `/srv/sbgame/web` on 443, and reverse-proxies the page's socket to Mosquitto on loopback. The bookmark, the name, the certificate and `sbgame-web` are unchanged, and the page still has one origin and one port.

— The page's socket takes the path `/mqtt`. It is what nginx routes on, and it is the whole of the page's change: `location.host` and the `wss://` rule of §2 stand. The page had not been written, so the path cost nothing.

— §9 step 10 is withdrawn and replaced. It chose between a SIGHUP reload and a 04:00 restart, a question that only existed while Mosquitto held the certificate. An nginx reload disconnects nobody and does not touch Mosquitto's clients at all. What remains worth checking is the renewal itself, which `certbot renew --dry-run` does against staging without spending one of the five duplicate certificates a week Let's Encrypt allows.

## 1.11 Changes in Rev 11

— Every station jack can carry a label, cabled or not (§6.3). Mark's decision, 2026-09-25. The switchboard has 30 station jacks and the game 22 station circuits, and the board's designation strips are labelled at every jack. Rev 7 let a label live only on a station entry, so a jack no entry named was drawn as an empty outline, and §10 asked where the other labels should go. They go in a new top-level list in script.yml, `jacks:`, one item per jack: `jack:` (1–30), `label:`, and `station:`, the script.yml station cabled to it, left out for a jack with nothing cabled.

— `switchboard:` and `label:` leave the station entries, which carry `number:` alone. A station entry is now the game's circuit and nothing about the board; the board is `jacks:`. Rev 7's reason for putting them together — one place to look — is kept by the list being in the same file, next to `stations:`.

— A labelled jack with no circuit is drawn as a working jack at rest (§7.1): its label, its jack number and an unlit lamp, like any idle jack. The operator sees the board as built, not which jacks are wired. A jack `jacks:` does not list keeps Rev 7's empty outline. Tapping a labelled, uncabled jack shows its circuit as none.

— The load checks follow (§6.3). Code consequence for Claude Code: the shared loader checks `jacks:` and rejects `switchboard:` and `label:` on a station entry, the game program builds the `board/` map from `jacks:`, and the page draws labelled uncabled jacks as working. `mqtt.md` Rev 18 corrects the `board/` rows to match. No topic changes. Trunk jacks are unchanged: trunk n on trunk jack n, no labels.

— The page is rearranged (§7.1), Mark's request, 2026-09-25, from the first look at it on the iPad. The health column took 380px beside the board, leaving each tile about 71 points wide, and one-word labels such as "Housekeeping" were clipped and two-word ones wrapped out of the tile. The board now takes the whole width; the calls table has the log under it, and health sits in a narrow column beside those two. A label that still does not fit is set smaller rather than clipped, and every label is set at that one size, so the board does not mix sizes.

— The §10 item "Labels on jacks the game does not use" is closed. The item named a station entry with no `number:` as one way to do it; a separate list was chosen instead, so that a station entry always means a circuit.

## 1.12 Changes in Rev 12

— Automatic pacing gains `jitter` (§4.3), Mark's decision, 2026-09-25. Rev 1 to Rev 11 waited exactly `gap_now` before every automatic call, a rhythm a player learns within a few calls. Each wait is now drawn evenly from `gap_now × (1 ± jitter/100)`, with `jitter` a percentage from 0 to 100 set on the page like the other three. Its mean is still `gap_now`, so `gap`, `ramp` and `floor` keep their meaning and the game is no harder or easier on average, only less regular.

— Bounded and even, not exponential. Calls at a real switchboard arrive nearly at random, which is an exponential wait between them, but at a mean of 20s that puts four waits in ten under 10s and one in twenty over a minute — a dead stretch for the player and the audience. The even spread keeps every wait within a known band. The exponential form, and calls that arrive whether or not the operator is ready (§4.5), stay available for when the game is played on the hardware.

— `floor` bounds `gap_now`, the centre of the spread, not each wait, so near the floor some waits fall a little below it. Holding each wait to the floor instead would raise the short ones to it and lift the mean above `gap_now` exactly where the ramp is meant to be steadiest.

— The draws come from the game's seed (§4.4), so a replay draws the same waits, and `jitter` is recorded with the other pacing values in the session record. Its starting value is 0, from the configuration file, so nothing changes until it is set.

— `mqtt.md` Rev 19 adds `game/jitter` and `game/jitter/set`. Code consequence for Claude Code: the scheduler, the configuration, the session record and a fourth stepper on the page.

## 1.13 Changes in Rev 13

— The game's controls move to an Elgato Stream Deck+ (§7.4), Mark's decision, 2026-09-25. The iPad becomes mostly a display. Eight keys carry Start, Stop, the pacing, Next Call, the tallies and the clients' health, and the four dials set `gap`, `ramp`, `floor` and `jitter`, with the touch strip above them showing the values. Stop needs a second press within 3s, as on the page.

— The deck is driven by a program of its own, `sbgame-streamdeck`, on the host. It is not part of the game program, for the reason the page is not (§1): it shows what the broker reports, keeps working and shows the game offline when the game program is down, and a USB fault cannot touch a game in progress. It connects as a new broker user, `sbgame-deck`, with the page's access list (`mqtt.md` Rev 20). It publishes the page's commands, so the game program is unchanged.

— Considered and not adopted: Elgato's own software with a community MQTT plugin, which needs a Windows or macOS machine and cannot draw the game's state on the keys; and Bitfocus Companion's generic MQTT module, which runs on Linux but keeps the layout in its own database rather than in this repository and this document.

— The page keeps its controls, behind a Controls switch in the top bar that shows or hides them on that iPad (§7.1). Mark's decision, 2026-09-25: the deck carries the controls, and the page's stay available if the deck is not there. Both publish the same commands, so both work at once. `sbgame-web` keeps its write access (`mqtt.md` §9).

— A dial reports relative steps and every command but Next Call is absolute (§7.2). The program therefore turns steps into a new absolute value, starting from the echoed value and adding every step made since, and publishes that (§7.4). Code consequence for Claude Code: the program, its unit and udev rule under `host/`, and later the page's top bar.

## 1.14 Changes in Rev 14

— Every scene in script.yml carries `active: true` or `active: false` (§4.4, §6.3), at Mark's request, 2026-09-26. He wants to write new cast and scenes before their wavs exist. Until now every scene was built at load, and a missing wav stopped the game program from starting. The game program now builds, deals and follows only active scenes, and reads wavs only for them. An inactive scene is still loaded and checked, and the TTS run still renders it, so a scene is written as `active: false`, rendered, and switched on once its wavs are in place. Every scene in the file at this revision is `active: true`.

— The key is required, not defaulted, so a scene cannot be switched on or off by omission. An active `after:` scene naming an inactive scene is rejected, since it could never play. An inactive `after:` scene following an active one is allowed; it is simply not played. Code consequence for Claude Code: the shared loader checks the key and gives `Script.active_scenes()`; the game program builds from that. No topic changes.

## 1.15 Changes in Rev 15

— Commissioning record only. §9 step 11, the Stream Deck, was run on portland on 2026-09-26, with Mark at the deck and the page. Everything passed except one check, which could not be made (below). No behaviour changes.

— Two host snags met on the way, both fixed in `host/`, not here. `libhidapi-libusb0` was not installed; the Stream Deck steps in `host/README.md` now install it. The udev rule names the `sbgame-deck` group, which did not exist when `make install` triggered udev, so the deck stayed `root:root` until udev was triggered again; `make sbgame-install` now triggers it after making the user.

# 2. Serving the Page

nginx serves the page's files over HTTPS on 443 and reverse-proxies its MQTT connection, on the path `/mqtt`, to Mosquitto's WebSockets listener on loopback. The configuration, the certificate and the name are `mqtt.md` §9. The files:

```text
web/
  index.html      the page
  app.js          everything the page does
  style.css
  mqtt.min.js     the browser build of MQTT.js, copied from the npm package's dist/
```

`web/` lives in the repository beside the game program and is installed to `/srv/sbgame/web`, readable by nginx's worker. MQTT.js is a local copy and never loaded from a CDN: on the road the travel router may have no internet, and the page would load without its library. The version copied is recorded in a comment at the top of `index.html`.

Mosquitto served the files itself through Rev 9, from `http_dir` on its own TLS listener. It cannot on this host: the listener will not bind a privileged port, and it advertises HTTP/2 without being able to speak it, which a browser negotiates by default (`mqtt.md` §1.17). The page is unaffected in everything but the path.

The bookmark is `https://game.kr3am.org/` (Rev 8; `http://<host>.local:9001/` through Rev 7). The name resolves to the host at home and on the travel router alike: from a public Route 53 record at home and from the travel router's own host entry on the road (`mqtt.md` §9.2, Rev 9). The certificate is a real one, so Safari loads the page with no warning. The page connects to `location.host` with the path `/mqtt`, over `wss://` when it was loaded over `https:` and `ws://` otherwise, so no address, port or scheme is written into it, and it works unchanged at home and on the road. It connects as the broker user `sbgame-web`; the password is in `app.js`, which anyone who loads the page can read. That is accepted: the access list, not the password, is what stops the page commanding hardware (`mqtt.md` §9, §11).

The path is what lets nginx tell the two apart: `/mqtt` goes to Mosquitto, everything else is a file. It is the only thing the page gained in Rev 10, and it was free because the page had not been written.

# 3. A Game

A game is one player's turn. It begins with `game/run/set` `"on"` and ends with `"off"`.

**Start.** Accepted only while `run` is `"off"`; while running it is ignored. The tallies are zeroed (§5), the call number restarts at 1, the gap returns to its configured value (§4.3), the deck is shuffled (§4.4), the loudspeaker's source is set to the tap (§6.4), and `run` reads `"on"`. In automatic pacing the first call starts at once; in manual pacing nothing happens until the page asks for a call. A game is one session in the game program's SQLite log.

**Stop.** Every call in progress is torn down at once: stations on-hook, trunk ring off, every file and tone stopped, every listen cancelled; every `after:` scene that was waiting is dropped; the call slots clear (§6.1); the loudspeaker's source goes back to the tap (§6.4). `run` reads `"off"`. Calls torn down this way are neither successes nor failures (§5). The tallies stay as they were until the next start, so the player can see the score.

**Losing a client.** If the controller or the audio program goes down during a game — `ctl/status` or `ctl/audio_status` offline, or two missed `esp_heartbeat`s (`mqtt.md` §8) — the game program does what Stop does and logs why, and `run` reads `"off"`. The player is not charged for the calls it abandons. It does not restart the game when the client returns; that is Mark's decision, from the page.

The game program always starts with `run` `"off"`.

# 4. Call Pacing

## 4.1 Manual

The Next Call key on the Stream Deck starts one call (Rev 13; until the deck is commissioned the page's Next Call button does too). Nothing else starts a call, apart from `after:` scenes (§4.4).

The key publishes `game/next/set`, at QoS 0, with an empty payload. The game program keeps its own count and starts the next call if `run` is `"on"` and a scene can be dealt (§4.4). If not, it reports why on `game/error`.

Two guards keep one tap to one call (Rev 4). QoS 0 is never resent on reconnect, so a connection that drops mid-send cannot deliver the command twice. The cost is that the tap may be lost, and the operator taps again. The page disables Next Call when it is tapped and re-enables it when `started` changes or `game/error` is published. It also re-enables after 3s regardless, so a lost tap does not leave the button dead. The Stream Deck's key is guarded the same way (§7.4). Two pages open at once could each start a call, and so could the page and the deck. That is accepted, since only Mark runs them.

`next/set` is accepted in automatic pacing too. It starts a call at once, and the automatic schedule then runs from that call (§4.2).

## 4.2 Automatic

The next call starts `gap` seconds after the most recent call to start has been **connected** (§4.3) or has ended, whichever comes first.

Timing from the most recent call rather than from every call means that at most one call is ever waiting for the operator to connect it. Calls overlap — the next one arrives while the last is still talking — but the operator is never asked to route two at once. That is the case Mark has deferred (§4.5).

While a call is waiting to be connected, no next call is scheduled and `game/next_at` is empty. Once it is scheduled, `next_at` is the host time it will start, and the page counts down to it.

## 4.3 Connected, and the Ramp

A call is **connected** at the point where the operator's routing work is done:

| **Scene** | **Connected when** |
| --- | --- |
| To a station, from a station or a trunk | the called station answers — the game takes it off-hook after ring arrives |
| To an outside line | the called party answers on the trunk after ringback |
| To an outside line marked `busy: true` | busy tone starts on the trunk |
| To the operator (no `called:`) | the request has finished playing |

These are the milestones the game program must expose to the scheduler. How it reaches each one — which listens, which timeouts — is the game program's flow and not this document's.

**The ramp.** The gap shrinks as the game goes on:

```text
gap_now = max(floor, gap − ramp × connected)
wait    = gap_now × (1 + jitter/100 × u),   u drawn evenly from −1 to 1, and never below 0
```

where `connected` is the number of calls connected so far in this game. `gap`, `ramp` and `floor` are set from the page; `gap_now` is what the scheduler uses, and it is published so the page shows it. `ramp` of 0 is a constant rate.

**Jitter** (Rev 12). The scheduler waits `wait`, not `gap_now`: a draw spread evenly around `gap_now` by `jitter`, a percentage. At `gap_now` 20 and `jitter` 50 every wait is between 10s and 30s, and they average 20s. `jitter` of 0 is the fixed wait. `floor` bounds `gap_now`, the centre, and not the draw, so near the floor a wait can fall below it; bounding the draw would lift the average there. The draws come from the game's seed (§4.4), so a replay draws the same sequence. `next_at` is the drawn start; `gap_now` stays the centre.

A change to any of the four takes effect at the next scheduling, not on a call already scheduled.

Ranges, clamped by the game program and echoed as applied: `gap` 0–600s, `ramp` 0–60s, `floor` 0–600s and not above `gap`, `jitter` 0–100%. Starting values come from the game program's configuration file: manual pacing, `gap` 20, `ramp` 0, `floor` 5, `jitter` 0. They hold across games until changed, and return to the configured values when the game program restarts.

## 4.4 Which Scene, and Scenes That Follow Another

**The deck.** At game start the game program takes every active scene in script.yml without `after:` and shuffles it into a list, the deck. Every new call, manual or automatic, is dealt from the deck. So every scene is played once before any is played twice, in an order that differs from game to game (Rev 2). A scene marked `active: false` is not played at all: it is never in the deck and never follows another, and its wavs need not exist (Rev 14).

**Dealing.** A new call takes the first scene in the deck whose lines and people are all free, and removes it. A scene's lines are its calling and called lines, stations and outside names alike (Rev 3). Its people are the `person:` under `calling` and `called`. A call to the operator has no called line or person. A line or person is busy if it belongs to a call in progress, or to a waiting `after:` scene (below). Scenes passed over stay where they are, so a scene held back because its line was busy comes up at the next call. If no scene in the deck can be dealt, the call does not start, the log says so, and in automatic pacing the scheduler tries again after `gap_now`. A `next/set` that cannot be satisfied this way is reported on `game/error`.

**Reshuffle.** When the deck is empty it is shuffled again from the full list, and dealing carries on. If the new deck would start with the scene dealt last, that scene moves to second place, so no scene plays twice in a row across the reshuffle. The log records each reshuffle.

**Replay.** The shuffle uses a seed chosen at game start. The seed and each deck's order go into the game's SQLite session record, not onto MQTT. The page is not told the order and does not need it.

**Scenes that follow another.** An `after:` scene (script.yml, "Order") is never in the deck. It starts `delay` seconds after the scene it follows has ended, in either pacing, as long as that scene was **connected** (§4.3). If it wasn't — the operator never answered, or never put the call through — the `after:` scene is dropped and the log says so (Rev 2; Rev 1 started it whenever the earlier scene ended). It is part of the story, not a new deal: `nbn-trace` two seconds after `nbn-kaplan`, `hale-pizza` three minutes after `hale-busy`. From the moment it is scheduled until it starts, its lines and people count as busy for dealing. If any of them is still busy in another call when its delay runs out, it waits until all are free and then starts (Rev 3). It counts as a call. It has a call number, it counts in `started`, and it succeeds or fails like any other call. It does not reset the automatic schedule. The page shows a waiting `after:` scene in the log with its start time.

At most eight calls are in progress at once — the number of call slots (§6.1). A call that would be a ninth is not started, and is treated like a scene that cannot be dealt.

## 4.5 Not Yet: Calls Before Connection

Mark wants, later, a mode where a new call can arrive before the operator has connected the current one — the real pressure of a busy board. The likely form is a fixed interval, a new call every `n` seconds from the start of the last, bounded by the eight slots. It is one more value on `game/pace` and uses the same `gap`, `ramp`, `floor` and `jitter`. Not specified until it is wanted.

# 5. Tallies

Three counts per game, each zeroed at start:

- **`started`** — calls started, including `after:` scenes.
- **`success`** — calls that ran to their scripted end: every utterance played, and the parties hung up as the script ends.
- **`fail`** — calls that ended any other way while the game was running.

The page shows **handled** as `success + fail`, the success percentage of handled, and **in progress** as the count of occupied slots. `started` minus handled minus in progress is the calls abandoned at Stop; the page does not show it.

A failure is logged with its reason. The reasons at Rev 1:

| **Reason** | **Meaning** |
| --- | --- |
| `no answer` | The operator did not answer the calling line in time. |
| `not connected` | The operator answered but did not connect the call in time — wrong station rung, number not dialled, or nothing done. |
| `cut off` | A cord was pulled during the conversation — the calling or called line's `peer` went empty before the scene's end. |
| `timeout` | The operator did not speak when a line was waiting for them (calls to the operator and busy scenes). |

Timeouts are the game program's configuration, not the page's, at Rev 1: 60s to answer, 90s to connect after the request has played, 30s for the operator to speak. They are starting values for play-testing.

A wrong connection is logged but is not a failure on its own. An operator who plugs the wrong jack and corrects it within the connect timeout has made the call. Whether a wrong party answering should end the call is open (§10).

# 6. Calls in Progress, the Log and the Board

## 6.1 Call Slots

Each call in progress occupies one of eight slots, `game/call/<1-8>/…`. A slot's topics:

| **Topic** | **Value** |
| --- | --- |
| `number` | the call number within this game |
| `scene` | the scene id |
| `from`, `to` | the calling and called line names from script.yml; `to` is empty for a call to the operator |
| `trunk` | the trunk carrying the call, as a circuit id, once known; empty for a station-to-station call |
| `stage` | where the call is (below) |
| `since` | host time the stage began |
| `deadline` | host time the stage times out, or empty |
| `digits` | the digits dialled so far on an outgoing call |

`stage` is one of:

- `signalling` — the calling station is off-hook, or the incoming trunk is ringing; waiting for the operator.
- `request` — the operator has answered; the request is playing.
- `routing` — waiting for the operator to ring a station or take a trunk.
- `dialling` — the operator has seized a trunk; digits are arriving.
- `ringing` — the called station is ringing, or ringback is on the trunk.
- `busy` — busy tone is on the trunk; waiting for the operator to go back to the caller.
- `talking` — the conversation is playing.
- `operator` — a call to the operator; the caller is waiting for the operator to speak.

A slot is free when `scene` is empty. The game program publishes `since` and `deadline` before `stage`, so a page never shows a new stage against the old time; and on a call's end it clears `scene` first, so the page frees the slot before the other values empty.

These stage names are what the page displays. The game program's own state machine may be finer; it maps onto these.

## 6.2 The Log

`game/log` is the last 50 events of the game, newest first, one per line, as plain text: `HH:MM:SS` host time, a space, the call number in brackets where there is one, and the event.

```text
14:02:31 [7] success
14:02:10 [8] started pike-taxi: lobby → taxi
14:02:10 [7] connected
14:01:58 [7] dialled 275-5678 on trunk/3
14:01:41 [7] started lindqvist-canlis: room601 → canlis
14:01:40 page: gap 15
```

Logged: game start and stop; each call's start, connection, success or failure with its reason; dialled numbers; wrong connections; reshuffles of the deck and `after:` scenes dropped (§4.4); hardware faults the game sees (`ring_on_trunk`, `bad_dial`); client outages; each move of the loudspeaker to a call (§6.4); every accepted page command. It is a display, not the record — the SQLite session log is the record — and it is republished whole on each new event.

## 6.3 The Board: Jacks and Labels

The switchboard has 30 station jacks, numbered 1–30, and 10 trunk jacks, numbered 1–10. The game has 22 station circuits and 8 trunk circuits. Which station circuit is cabled to which station jack is Mark's choice, and it can change when he recables. It is recorded in script.yml's top-level `jacks:` list, one item per station jack, together with the label on the board at that jack whether or not anything is cabled to it (Rev 11):

```yaml
stations:
    room463:
        number: 11          # the game's station circuit, 1-22

jacks:
    -   jack: 23            # the switchboard jack, 1-30
        label: "463"        # the text on the board at that jack
        station: room463    # the station cabled to it
    -   jack: 24
        label: "465"        # labelled on the board, nothing cabled: no station:
```

(Illustrative. The real assignments are Mark's.) A station entry carries `number:` and nothing about the board. Trunk circuit n is cabled to trunk jack n for n = 1–8, fixed, and trunk jacks 9 and 10 carry nothing. No trunk jack has a label. A station jack that `jacks:` does not list has no circuit and no label.

The script.yml loader rejects the file, and the game program refuses to start, if:

- `jacks:` is missing or empty, or an item has a key other than `jack:`, `label:` and `station:`;
- an item's `jack:` is not an integer from 1 to 30, or is the same as another item's;
- an item lacks `label:`, or its label is empty;
- an item's `station:` is not a station entry, or names a station another item already names;
- a station entry is named by no item in `jacks:`, or carries any key but `number:` — a file still in Rev 7's form, with `switchboard:` and `label:` on its stations, fails with a message saying where they went, rather than drawing a board with no labels;
- a station's `number:` is outside 1–22, or the same number as another entry (the loader's existing check);
- a scene lacks `active:`, or its value is not `true` or `false`, or an active scene's `after:` names an inactive one (Rev 14).

The loader is the one `tts_task.md` §3.1 specifies, which the game program imports. These checks go into it, so the TTS run and the game both see them.

A station circuit that no entry names is not on any jack as far as the game knows. It has no tile, and a ring or hook on it goes in the log as a stray. A station entry that no scene uses is still drawn, so a stray ring on it is seen.

The game program reads wavs for active scenes only, and refuses to start if one is missing. An inactive scene's wavs are not looked for.

The game program publishes the map retained under `board/` (`mqtt.md` §6.1): each jack's label, and the circuit it carries or empty. A labelled jack with nothing cabled has a label and an empty circuit. The page builds the board from those topics alone. A change to script.yml takes effect when the game program restarts.

Recabling a station circuit to a different jack moves its `station:` from one item in `jacks:` to another. The labels stay with the jacks, and nothing else changes.

## 6.4 The Audience Loudspeaker

The loudspeaker carries one receive channel, chosen by the game program with `audio/monitor/source/set` (audio.md §10.3). New at Rev 6. The game program points it at the calling line of the call the operator most recently answered, and leaves it there until she answers another.

**When.** The operator answers a call when its calling circuit's `op` goes on while the call is in `signalling`: that is the event that takes the call out of `signalling` (§6.1). At that moment the game program publishes `monitor/source/set` with the calling circuit's id. For a call from a station that is the station, such as `station/11`. For a call from outside it is the trunk that rang in, such as `trunk/3`. It does not change the source at any other point in the call. It does not change it when the operator bridges onto a call already past `signalling`, to listen in or to go back to a caller, since that is not an answer.

**Why at the answer.** Before the answer the calling line carries nothing worth hearing. A calling station is off-hook and silent. A calling trunk is ringing, and its ring relay puts a click on its channel at every cadence edge (trunk §8.1.1). Waiting for the answer also keeps the audience on the current conversation until the operator actually leaves it for the next caller. Mark's first proposal switched at the start of the call. He changed it to the answer on 2026-09-24 for these reasons.

**What the audience hears.** The calling line's receive channel carries the caller's side at full strength, since the interface has no hybrid (station §8.4). It carries the operator while she is bridged to the line, and the called party once the cord connects them. So one source carries the request, the operator's reply and the conversation. A call to the operator, and a busy scene where the operator goes back to the caller, are heard the same way. An outgoing call's ringback and busy tone reach the caller through the cord, and the audience hears them when the caller would.

**Which call.** Only the most recent answer counts. In automatic pacing the next call can arrive while the current one is talking (§4.2). When the operator answers it, the audience leaves the current conversation for the new request. An `after:` scene is a call like any other and moves the loudspeaker when it is answered.

**Start and stop.** When a game starts, and when it stops for any reason (§3), the game program publishes `monitor/source/set` `"tap"`. Between games the loudspeaker carries the operator tap as it always has. The audio program also returns to the tap by itself if it loses the game program (audio.md §13.2).

**What the game program does not do.** It does not set the monitor's gain, which is a bench and installation setting, and it does not turn the monitor on or off. It publishes a new source only on an answer, a start or a stop, and does not wait for the echo. The page shows the echo (§7.1).

The log records each move as `monitor: <calling line>` against the call's number, using script.yml's line name, as the other call events do.

# 7. The Page

## 7.1 Layout

For an iPad in landscape, 1024 CSS pixels wide or more. Touch targets 44px or larger. Four areas: the top bar across the page; the board under it, across the whole width; then calls, with the log under them, beside a narrow health column (Rev 11):

**Top bar**, always visible. A Controls switch beside the connection lamps shows or hides its buttons — Start, Stop, the pacing, Next Call and the steppers' − and + — on this iPad (Rev 13). The Stream Deck carries the same controls (§7.4). With the buttons hidden the values stay — the four values, `gap_now`, the countdown and the tallies — and one line reads what the hidden buttons showed: Running or Stopped, and Manual or Automatic. The setting belongs to the iPad, kept in the browser's storage, not on the bus. An iPad with no setting, or one whose storage was cleared, shows the buttons, so it can always run the game.

- Connection: broker connected or not; game program online or not.
- Start and Stop. Stop needs a second tap within 3s, because it ends a player's game.
- Pacing: Manual | Automatic.
- Next Call: large in manual pacing, small in automatic.
- `gap`, `ramp`, `floor`, `jitter`, each with − and + steppers (5s, 1s, 1s, 10% steps; `jitter` Rev 12). Shown only in automatic pacing, with `gap_now` and the countdown to `next_at` beside them.
- Tallies: started, handled, success, fail, success percentage.

**Board.** Laid out as the switchboard is (Rev 5): station jacks in three rows of ten, and one row of ten trunk jacks below them. Rows run 1–10, 11–20, 21–30 from the top, left to right, until checked against the board (§10). Each tile is one jack, from the `board/` topics (§6.3).

A tile shows little:

- the jack's **label**, large, and its jack number, small. Every label on the board is set at one size, the largest at which the longest still fits its tile, so the board reads as one designation strip; a label is never clipped, and words are not broken (Rev 11);
- **one state**, as a colour, the most urgent first:

| **State** | **Station jack** | **Trunk jack** |
| --- | --- | --- |
| fault | `peer` `"ambiguous"` or `"deaf"`, `play` `"missing"` | the same, or `fault` set |
| ringing | `ring` on, flashing | `ring` on, flashing with the cadence |
| calling | `hook` on, `op` off and `peer` empty: the line lamp is lit, nobody has answered | — |
| connected | `peer` set, in a colour shared by both ends of the pair | `peer` set, the same way |
| operator on | `op` on | `op` on |
| busy | `hook` on | `seize` on |
| idle | none of the above | none of the above |

- the far end's **label**, when `peer` is set, taken from the board map rather than shown as a circuit number.

Tapping a tile opens a panel with everything about that jack: its circuit, `hook` or `seize`, `ring`, `peer`, `op`, `play`, `tone`, `listen`, `fault`, the digits of a call on a trunk, and the call slot using it. Tapping elsewhere closes it. Mark expects the tile to need more or less than this once it is on the iPad.

A station jack with a label and no circuit — listed in `jacks:` with no `station:` — is drawn as a working jack at rest: label, jack number and an unlit lamp, the same as an idle cabled jack (Rev 11). The operator is shown the board as it is built, not which of its jacks the game has wired. A jack with neither a label nor a circuit — a station jack `jacks:` does not list, and trunk jacks 9 and 10 — is drawn as an empty outline with its jack number, so the board keeps its shape (Rev 7). Trunk tiles show the jack number alone, since trunk jacks have no labels.

**Calls.** One row per occupied slot: call number, scene, from → to, trunk, stage, time in stage, time to deadline. From and to are script.yml's line names. The trunk is shown by its jack number.

**Health and log.** Controller: `status`, seconds since the last `esp_heartbeat`, `i2c`. Audio: `audio_status`, `optone`, `monitor`, and the monitor's `source` — `tap`, or the jack label of the circuit it names, from the board map (Rev 6). Game: `game_status`, seconds since the last `game_heartbeat`. Then the log, in a monospaced column, and the last `game/error` as a line that clears on the next accepted command.

## 7.2 Behaviour

**The page never shows what it asked for, only what was echoed.** A tap publishes a `/set` and changes nothing on screen; the display changes when the game program's state topic changes. A command the game rejects shows on `game/error`. This is the same `/set`-and-echo rule as every other client (`mqtt.md` §3).

**Every command but one is absolute.** The steppers publish the new value, not a step. Next Call is the exception: a plain request, guarded as §4.1 describes.

**Time.** Host times in `since`, `deadline` and `next_at` are host Unix seconds. The iPad's clock is not trusted — on the travel router neither clock may have seen a time server. The page takes the host's time from each `game_heartbeat` payload, keeps the offset from its own clock, and computes every duration against host time.

**Staleness.** Grey out, rather than blank, anything that may be out of date:

- broker disconnected: everything;
- `game_status` offline, or no `game_heartbeat` for 2.5s: the top bar's controls disabled, the tallies, calls and log greyed;
- `ctl/status` offline, or no `esp_heartbeat` for 2.5s: `hook`, `ring`, `seize`, `fault`;
- `audio_status` offline: `peer`, `op`, `play`, `tone`, `listen`, `optone`, `monitor` and its source.

**Connection.** Clean session, keepalive 10s, MQTT.js's own reconnect every 2s. Subscribe to `sbgame/#` on every connect; the retained topics give the whole state at once, and there is nothing to request. Safari closes the socket when the iPad locks or the page goes to the background; on `visibilitychange` to visible, if not connected, reconnect immediately rather than waiting for the timer. `trunk/<n>/digit` messages published while the page was away are lost; the call slot's `digits` and the log carry them.

**No hardware commands.** The page publishes only `sbgame/game/+/set`. The broker drops anything else from `sbgame-web` (`mqtt.md` §9).

## 7.3 On the iPad

Add the page to the Home Screen, so it opens without Safari's bars. Turn off Auto-Lock while it is in use at an event. The page is a secure origin (§2), so it could instead hold a screen wake lock while a game runs; that is not specified yet (§10, Rev 8). For a public exhibit, Guided Access keeps visitors on the page; for Rev 1 the page is Mark's.

## 7.4 The Stream Deck

New at Rev 13. An Elgato Stream Deck+ on a USB cable from the host, beside the switchboard, carries the game's controls. It has eight LCD keys, 120×120 pixels each, in two rows of four; four dials below them, each of which turns in detents and can be pushed; and between the two a touch strip, 800×100 pixels, a 200-pixel segment over each dial.

**The program.** `sbgame-streamdeck`, a Python program in `engine/`, drives it through the `streamdeck` library over hidapi. It is a process of its own and not part of the game program, for the page's reason (§1): it reads the bus directly, so it shows the game offline rather than going dark with it, and a USB fault cannot disturb a game. It connects to the broker on loopback as `sbgame-deck`, with the page's access list: it reads `sbgame/#` and writes only `sbgame/game/+/set` (`mqtt.md` §9). It runs as a systemd service, `sbgame-streamdeck`, as the system user `sbgame-deck`, which a udev rule lets open the deck and nothing else. It has no will and no heartbeat, for the page's reason (`mqtt.md` §8.2): nothing depends on it.

It follows every rule of §7.2. It shows only what was echoed, and a press changes nothing on the deck until the echo arrives. Every command is absolute but Next Call. Durations are computed against the host's clock, taken from each `game_heartbeat`. Stale values are greyed, not blanked. It subscribes to `sbgame/#` on every connect and needs nothing else.

**Keys**, numbered 1–4 on the top row and 5–8 below, left to right:

| **Key** | **Shows** | **Press** |
| --- | --- | --- |
| 1 Start | "Start", lit while `run` is `"off"` | `run/set` `"on"`. Ignored while a game runs. |
| 2 Stop | "Stop", lit while `run` is `"on"`; "Stop again" in red for 3s after a first press | Arms it. A second press within 3s publishes `run/set` `"off"`. |
| 3 Pacing | "Manual" or "Auto", the echoed `pace` | `pace/set` with the other value, which is absolute: the one not now echoed. |
| 4 Next Call | "Next" over "Call", lit while a game runs; in automatic pacing the countdown to `next_at` in place of "Call" | `next/set`, at QoS 0, guarded as §4.1: dark from the press until `started` changes, `game/error` is published, or 3s pass. |
| 5 Calls | `started` and in progress | nothing |
| 6 Score | success and fail | nothing |
| 7 Percent | success percentage of handled | nothing |
| 8 Health | a lamp each for the game program, the controller and the audio program, red when offline or its heartbeat is 2.5s late; the whole key red while `game/error` is set | shows the last `game/error` on the strip again |

**Dials**, left to right: `gap`, `ramp`, `floor`, `jitter`. One detent is one step of the page's stepper: 5s, 1s, 1s and 10%. A push does nothing at Rev 13. The strip segment above each dial shows its name and its echoed value, and above `gap` also `gap_now` while a game runs. The four are dimmed in manual pacing but still turn, so the values can be set before switching to automatic.

**Turning a dial.** The dial reports steps and the command is absolute, so the program keeps a target. The first detent starts the target at the echoed value; each detent adds a step to the target, clamped to the §4.3 range, and publishes it. The target is held while detents keep coming and is dropped when the echo equals it or 1s after the last detent, so a fast turn loses no steps and a value the game clamped differently — `floor` above `gap` — settles on the echo. A dial whose value has not been echoed yet does nothing.

**Errors.** When `game/error` changes to a non-empty value, the strip shows it across its whole width for 5s and then returns to the dials. Key 8 stays red until the error clears, and a press on it shows the error again. A touch on the strip dismisses it.

**Staleness.** With the broker lost, every key is greyed and the strip says so. With the game program offline or its heartbeat 2.5s late, keys 1–7 and the dials are greyed and do nothing; key 8 still shows the three clients. A press that does nothing gives no other sign; the greyed key is the sign.

**No deck.** The program runs whether or not a deck is plugged in. It looks for one every 2s, and draws a deck found or replugged from the state it already holds. It drives the first Stream Deck+ it finds and ignores any other. On a clean stop it clears the deck, so it is blank rather than showing controls that no longer work. A crash leaves the last images on the keys; systemd restarts the program within 5s, and the first thing it does is redraw them.

**Brightness** is an option of the program, 60% by default. The deck has no screensaver in this program.

# 8. What the Game Program Checks

Every value arriving on `game/+/set` is checked by the game program; the access list keeps the page off hardware topics but does nothing about a bad value on the game's own. A value out of range is clamped and the applied value echoed; a value that is not understood — `run/set` other than `"on"` or `"off"`, `pace/set` other than `"manual"` or `"auto"`, a number that does not parse — is dropped, logged, and reported on `game/error`. Accepted commands are logged with `page:` in front (§6.2). A command from the Stream Deck arrives on the same topic and is logged the same way; the game program cannot tell them apart and does not need to (Rev 13).

# 9. Commissioning

Before step 1: the certificate is issued (`mqtt.md` §9.1), nginx is configured and enabled, the Route 53 A record for `game.kr3am.org` points at the host, and the broker users and the access list are in place — four, and `sbgame-deck` the fifth from Rev 13. The deploy hook no longer has to be run by hand, because nginx reads the certificate from `/etc/letsencrypt/live` directly and the hook only reloads it.

1. Restart Mosquitto and nginx after the §9 changes to `mqtt.md`'s configuration. Mosquitto's log shows two listeners open, MQTT on 1883 and WebSockets on 127.0.0.1:9001; `ss -ltnp` shows nginx on 443. Mosquitto's WebSockets listener is deliberately on loopback: nothing off the host reaches it except through nginx (Rev 10).
2. From another machine on the LAN, `curl https://game.kr3am.org/` returns `index.html` with no certificate error. That checks the name, the certificate and `http_dir` together (Rev 8; `curl http://<host>.local:9001/` through Rev 7).
3. The controller, the audio program and the game program still connect. `allow_anonymous false` refuses any client without credentials; control.md §9.1 and audio.md already use them, but check the usernames against the access list.
4. As `sbgame-web`, publish `sbgame/station/1/hook/set` `on`. Station 1's relay does not move and `hook` does not change: the broker has dropped it silently. Then `sbgame/game/run/set` `on`, which is accepted.
5. Lock the iPad for a minute and unlock it. The page reconnects and shows the full state without a reload.
6. Stop a game with a station off-hook, a trunk ringing and a file playing. Everything releases, and the tallies stay.
7. Kill the game program. The page shows it offline within 2.5s and keeps showing the hardware.
8. **Wiring check** (Rev 5). With no game running, put an answering cord into each cabled station jack in turn and ring it. The tile for that jack flashes. If another tile flashes, or none does, the cable and script.yml's `jacks:` disagree about that station (Rev 11; each station's `switchboard:` at Rev 7–10, `wiring.yml` at Rev 5–6). A labelled jack with nothing cabled looks like any other at rest, so a tile that never flashes is not by itself proof of a fault — tap it: its circuit reads none. For trunks, seize each trunk jack in turn: the tile for that jack shows busy. This checks the cabling against the script using only topics that already exist.
9. **The loudspeaker follows the call** (Rev 6). Start a game. The page shows the monitor's source as `tap`. Start a call from a station and answer it: the source changes to that station's label and the audience hears the request. Put the call through and release the operator: the conversation stays on the loudspeaker. Do the same for a call from a trunk, and confirm the source does not change while the trunk is ringing. Stop the game: the source returns to `tap`.
10. **Certificate reload** (Rev 10). Nothing to check. Mosquitto holds no certificate: nginx terminates TLS and rereads the certificate on `systemctl reload`, which starts new workers and lets the old ones finish, so no client is disconnected and no client of Mosquitto is touched at all. Rev 8 and Rev 9 had this step decide between SIGHUP and a 04:00 restart, because whether Mosquitto's libwebsockets listener reloads a certificate on SIGHUP was unconfirmed. Both are withdrawn (`mqtt.md` §9.1). Confirm the renewal path itself instead, without spending an issuance: `sudo certbot renew --dry-run` runs the DNS-01 challenge against staging and the deploy hook, and must report success.
11. **The Stream Deck** (Rev 13). With `sbgame-streamdeck` running and the deck plugged in: the keys draw within 2s. Start and Stop start and stop a game, Stop only on the second press. The pacing key switches the page's pacing. Turn each dial one detent each way and check the page shows the step, then turn `gap` quickly through ten detents and check it moves 50s. Next Call starts one call per press, however fast it is pressed. Stop the game program: keys 1–7 grey within 2.5s and key 8 shows the game red. Unplug the deck and plug it in again: it redraws with the current state. `systemctl stop sbgame-streamdeck`: the deck goes blank. Then hide the page's controls with its Controls switch (§7.1), reload the page, and check they stay hidden and the line reads the game's state.

    Run 2026-09-26 (Rev 15). Passed: the keys drew; Start and Stop, Stop on the second press; the pacing key; each dial one step per detent (`gap` 5s, `ramp` and `floor` 1, `jitter` 10), and eight quick `gap` detents moved it 40s, published in order within a second; with the game program stopped the keys greyed and key 8 went red; replugged, the deck redrew; with `sbgame-streamdeck` stopped it went blank; the page's controls stayed hidden across a reload. A fast turn can carry two detents in one message (`jitter` 100 → 80); the total comes out right. Not yet checked: Next Call pressed fast, one call per press. With the audio program offline every call fails at once and the game stops (§3), so the presses after the first land on a stopped game. Make the check once `sbaudio` is running.

# 10. Open Items

- **Calls before connection** (§4.5). Deferred by Mark.
- **Wrong party answers.** Whether ringing the wrong station, or dialling a wrong number, ends the call as a failure or only costs time. Rev 1 lets the connect timeout decide. Wants play-testing.
- **Timeouts from the page.** The §5 timeouts are configuration at Rev 1. If play-testing wants them changed between players, they become three more `game/…/set` topics.
- **Start a named scene.** Useful at the bench, to test one scene repeatedly. One more command topic, `game/scene/set`, and the scene ids published for the page to list.
- **Audience view.** A second page, or a mode of this one, for the room: the tallies large, the calls in progress, nothing diagnostic. Same topics; no host change.
- **Cords drawn as lines** between tiles rather than shown by colour. Only if the colour pairing is hard to read on the iPad.
- **Row order on the board.** §7.1 assumes jack 1 at top left and rows of ten running left to right. Check against the 551's designation strips and correct §7.1 if the board runs otherwise.
- **Script names or jack labels.** script.yml's station keys (`room463`) and the board's labels (`463`) name the same thing twice. The calls panel and the log use script names, and the tiles use labels. If that reads badly, the game program can put labels in the call slots instead.
- **The loudspeaker leaving a conversation** (§6.4). In automatic pacing, the operator answering the next call takes the audience away from the current conversation, possibly mid-sentence. The alternative is to stay on a call until its conversation ends and then move to the most recently answered call, at the cost of missing that call's request. Rev 6 moves at each answer. Wants listening with an audience.
- **Settings across restarts.** Pacing values return to the configuration file's when the game program restarts (§4.3). If that is annoying, the game program can read its own retained values back at start.
- **Dial push** (§7.4). Unused at Rev 13. Candidates: a finer step while held, or back to the configured value — the program does not know the configured values, and the game program would have to publish them.
- **Error on the strip** (§7.4). 5s may be too short to read a long error, or too long to lose the dials during a game. Wants use.
- **Next Call on GPIO36** (`control.md` §11). A third way to publish `next/set`, needing the same guard as the page and the deck.
- **Screen wake lock** (§7.3, Rev 8). Possible now that the page is served over HTTPS: the page would hold a wake lock while `run` is on, and Auto-Lock could stay on. Whether it holds reliably for a Home Screen page on the iPad's iOS version is to be tried before it replaces the Auto-Lock instruction.
