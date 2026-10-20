**551 Switchboard Simulator**

**Game Control and the Status Page**

*Rev 64 — Start and Stop, Tutor, Manual, Automatic and Listen Call Pacing, Automatic with a Ramp and Jitter and Listen with a Pause of Its Own, Scenes Dealt from a Shuffled Deck, Lines That Wait for the Operator, Pauses and Ringback Within a Call, What the Operator Says, Tallies, Calls in Progress and the Log, the Switchboard's Jacks and Labels from script.yml, the Audience Loudspeaker Following the Call the Operator Last Answered, an iPad Page Served by nginx over HTTPS at game.kr3am.org and Talking MQTT over Secure WebSockets, the Game's Controls on a Stream Deck+, Only Active Scenes Played, the Guest in Each Room Named on Its Jack, Long-Distance Time and Charges Rung In to the Hotel, Circuit Diagnostics and a Chosen Next Scene from the Page, a Game Fitted to the Circuits Built, a Tutor Who Talks a New Player Through Each Call, Starting with One Call of Each Kind, and an Introduction a Part at a Time, with the Key She Asks For Flashing, and Repeat Help, and Trunks Out of Service, and the Board's Rows in the 551's Order, with the Tutor's Ring Lines Named for the Station, and a Scenario of Calls Arriving Together After the Tenth Call, with a Station Found Engaged, and a Scenario Chosen from the Page on a Clear Board, Starting by Itself, and Then Not Dealt Again, and a Sweep of the Trunks or the Stations from the Stream Deck, and Ringback on the Loudspeaker While the Operator Rings a Station, and a Line's Momentary Break Not Shown as a Fault, and a Key to the Lamps on a Long Press of Tools, and Help on a Long Press of the Pacing Buttons and the Steppers, and the Tutor's Prompts Said Shortly Once Each Has Been Said Twice, with More Help for the Full Line, and Fast Busy and a Failed Call for a Number Dialled Too Long or Too Short, and a Game Left Alone for Ten Minutes Stopped, and the Tutor Stopping Mid-Word Once the Player Has Done What She Asks, and Telling Her When a Call Is for Her, and No Silence When the Player Goes Wrong, and Recording the Loudspeaker, and the Sweeps from the Deck and the Page Both, the Switchboard Power Cut on Stop and on the Deck, and a Chosen Scenario Waiting for Next Call or the Schedule Like Any Chosen Scene*

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

— Commissioning record only. §9 step 11, the Stream Deck, was run on portland on 2026-09-26, with Mark at the deck and the page. Everything passed. Fast Next Call presses needed the audio program running and were checked once it was. No behaviour changes.

— Two host snags met on the way, both fixed in `host/`, not here. `libhidapi-libusb0` was not installed; the Stream Deck steps in `host/README.md` now install it. The udev rule names the `sbgame-deck` group, which did not exist when `make install` triggered udev, so the deck stayed `root:root` until udev was triggered again; `make sbgame-install` now triggers it after making the user.

## 1.16 Changes in Rev 16

— A third pacing, **Listen** (§4.2), Mark's request, 2026-09-26. It is for showing the game: the next call waits until the board is empty — the last call has ended and no `after:` scene is waiting — so calls never overlap and the room hears every conversation to its hang-up. Automatic pacing times from the connection, so the next call can arrive mid-conversation and the operator's answer takes the loudspeaker away from it (§6.4). Listen is the other half of that open item (§10): it keeps the loudspeaker on each conversation by never starting two.

— A third value of `pace`, not a special value of `gap`. Listen still wants a pause after the hang-up, and `gap`, `ramp`, `floor` and `jitter` keep their meaning, counted from the end instead of the connection. `mqtt.md` Rev 21 adds `"listen"` to `pace` and `pace/set`. "Automatic pacing" in this document now means auto or listen wherever the two behave alike: the first call at once (§3), the dials and steppers, the countdown.

— The deck has no key to spare, so its pacing key cycles Manual → Auto → Listen → Manual, and shows all three names, the echoed one lit, so the choices can be read off the key (§7.4). Presses count from the last press while its echo is outstanding, as a dial's detents do, so two quick presses go two places. Going from Auto to Manual passes through Listen and from Manual to Listen through Auto; the pass is a fraction of a second, and a call is started on the way only if `gap_now` is shorter than that. The page gains a third segment (§7.1).

— Code consequence for Claude Code, made the same day: the scheduler, the configuration check, the deck's pacing key and the page. The game program's tests cover the schedule in listen, including a waiting `after:` scene holding it; the deck's tests cover the cycle.

## 1.17 Changes in Rev 17

— Listen gets one value of its own, `pause`, in place of auto's four (§4.2, §4.3), Mark's decision, 2026-09-27. Rev 16 ran listen on `gap`, `ramp`, `floor` and `jitter`, counted from the end of a call. But listen is for entertaining with the conversations, not for pressure: Mark wants the next call a few seconds after the last one ends, every time. So listen waits `pause` seconds, 0–60, starting at 3 from the configuration file, with no ramp and no jitter. Auto's four are untouched by listen, so switching between a demonstration and a real game needs nothing reset.

— Considered and not adopted: a separate set of all four for each pace. Eight values, with dials and steppers whose meaning changes with the pace, for three knobs listen has no use for.

— In listen the first dial sets `pause` and the other three rest, dimmed and showing auto's values, as in manual (§7.4); the page shows one stepper, `pause`, in place of the four (§7.1). `mqtt.md` Rev 22 adds `game/pause` and `game/pause/set`, and the session record gains a `pause` column. Code consequence for Claude Code, made the same day.

## 1.18 Changes in Rev 18

— The page's countdown says "waiting" while a game runs in automatic pacing and no next call is scheduled — `next_at` empty, because in auto the latest call is not yet connected or ended, and in listen the board is not yet empty (§4.2) — and "–" when no game runs (§7.1), Mark's request, 2026-09-28. It said "–" in both. The deck's Next key already said "waiting" in that case; §7.4 now says so too. It is on the countdown rather than on the Next Call button because the button is hidden with the controls and the countdown is not.

— The deck's Next Call key is lit violet, where it was amber (§7.4), Mark's choice, 2026-09-28: no other key or page colour uses violet. In listen the three resting segments of the strip are drawn dimmer than manual's, name and value alike, so the one dial that does something stands out (§7.4). Code consequence for Claude Code, made the same day: `app.js` and `streamdeck.py`.

## 1.64 Changes in Rev 64

— A chosen scenario no longer starts by itself (§4.10), Mark's request, 2026-10-19, withdrawing Rev 41. It is staged, as any chosen scene is (§4.8): in manual pacing it starts on Next Call, in automatic pacing it is the next call the schedule deals. Rev 41 started it at once on a clear board and only on Next Call or the schedule when chosen with calls on the board, so the same choice behaved two ways. Rev 41's reason, that nothing showed a choice waiting, no longer holds: the page shows the chosen scene under Next Call (§7.1). The clear board of Rev 40 stays: until it clears, Next Call is refused, "waiting for the board to clear", and the schedule deals nothing else.

— Code consequence, for Claude Code: the scheduler's start on a clear board goes, with its test. No topic change.

## 1.63 Changes in Rev 63

— Stop cuts the switchboard's power for 1s (§3), Mark's request, 2026-10-19. A trunk rung in locks its lamp and buzzer on the switchboard until a cord goes into the jack, and Stop, which releases our ring relay, did not clear it; nothing did. The controller now drops the switchboard's 24V on `ctl/power_cut/set` (control.md Rev 31, mqtt.md Rev 37), and every relay and lamp on the switchboard drops with it. Stop sends it after the calls are torn down, so a game always ends on a dark board. A stop for the controller going offline cannot send it, and does not try.

— A long press on key 5 cuts the power by hand (§7.4): held 2s with no game and no sweep running, `game/power_cut/set` `"on"`, which the game program passes on. While a game runs the deck ignores the hold, as it ignores the sweep's double press, and the game program refuses `game/power_cut/set` on `error` all the same, since the cut would drop the calls on the switchboard under the game's feet; Stop does it anyway. Key 5 because it already starts the trunk sweep, the other thing done to the board with no game running (Mark's choice, 2026-10-19; a long press on the first dial was drafted first).

— Code consequence, for Claude Code: the game program sends `ctl/power_cut/set` `"on"` at the end of `stop()` when the controller is online, and accepts `game/power_cut/set`; the deck program times key 5's hold and draws it; tests for both. The firmware's half is control.md Rev 31.

## 1.62 Changes in Rev 62

— The sweeps come back to the Stream Deck, as at Rev 50, and stay on the page (§7.4, §7.6), Mark's request, 2026-10-18: key 5 pressed twice within 0.5s sweeps the trunks, key 6 the stations. A single press of the running sweep's own key stops it, and so does the other key pressed twice. While a sweep runs its key reads "Sweep" over "trunks" or "stations", lit teal, however the sweep was started — the key follows `game/sweep`, so a sweep started from the page shows on the deck too. Rev 50 read "Testing".

— Teal (38, 128, 128), a colour of the deck's own, in place of amber on the sweep keys and on Repeat Help and More Help (§7.4), Mark's choice, 2026-10-18.

— Code consequence, made the same day: keys 5 and 6 in `streamdeck.py`, and its test. No topic change.

## 1.61 Changes in Rev 61

— The page's Tools gains three sections under Operator (§7.1), Mark's request, 2026-10-18: Diagnostics, the board sweeps; Record, a recording of the loudspeaker; and Playback, a recording played back on it (§7.7). Tools is where the tools are, and the deck's keys keep one meaning each.

— Record starts a recording, and while it runs a red dot pulsing once a second and the time recorded stand in the top bar to the right of Tools; a tap on them stops it. The audio program writes `/srv/sbgame/recordings/<YYYY-MM-DD-HH-MM-SS>.wav` and makes an MP3 beside it when it stops (audio.md Rev 22, §10.6). A recording is not part of a game: it runs with or without one, and Start and Stop leave it alone.

— One at a time: Record is dimmed while a playback runs and Playback while a recording does, and the game program refuses either then. Each button, filled while its own runs, stops it on a tap, as its indicator in the top bar does.

— Playback opens a list of the ten newest recordings, newest first, each with its length; a tap plays that one on the loudspeaker, in place of the monitor, at the level it was recorded (audio.md §10.7). While it plays a play triangle and the time stand in the top bar to the right of Tools, and a tap on them stops it. Not while a game runs, and Start stops one.

— The sweeps move off the Stream Deck: keys 5 and 6 are the tallies again and nothing more (§7.4). Pressing a sweep's button on the page starts it, and pressing it again while it runs stops it (§7.6).

— `game/record/set` and `game/playback/set`, which the game program passes to the audio program as `audio/record/set` and `audio/playback/set`, so the game program stays the only client that commands audio; the page reads `audio/record`, `audio/recordings` and `audio/playback` directly (mqtt.md Rev 36).

— Code consequence, made the same day: Tools and the Recordings sheet in `index.html`, `app.js` and `style.css`; the `record` and `playback` commands in `game.py`, and Start stopping a playback; `Hw.record()` and `Hw.playback()` in `link.py`; the sweep keys out of `streamdeck.py`; the tests.

## 1.60 Changes in Rev 60

— An audit of where the game fell silent on a player's mistake, Mark's request, 2026-10-17, and a fix for each (§5, §4.9). Each new line is a reaction under a new top-level `reactions:` in script.yml, rendered in every cast member's voice but the operator's and the tutor's, as `<kind>.<speaker>` — 171 lines — so a party reacts in its own voice. A reaction not rendered is done without, as before.

1. **She does not speak** where the game waits for her — the greeting, a reply, the closing — or spoke before the listen began. Outside tutor mode it was 30s of silence before the caller went on. Now after 6s of silence the waiting party says "Hello? Operator? Are you there?" (`nudge`), the game listens 6s more, and the line plays either way. In tutor mode her Say prompt does this already.
2. **She rings the wrong room.** It rang out unanswered and the caller said nothing until the connect timeout. Now, 1.5s into the ring, whoever the scenes most often have in that room answers, "Hello? … Hello? Is anybody there?" (`hello`); if the caller is patched to it, the caller says "Operator, that's not who I asked for." (`wrong`); and the room hangs up, so its cord lamp lights. Not a room already off-hook, nor the caller's own. The call goes on, and she may ring the right one. It is not a failure, since she can recover (Mark, 2026-10-17); §10's open item on a wrong party is settled this way.
3. **She rings the right room on a cord not patched to the caller.** The room was taken off-hook and the game waited in silence for the two to be joined. Now, not joined in 8s, the room says "Hello?" (`hello`, in the called party's voice); not in 8s more, it hangs up, and she must patch and ring it again.
4. **A trunk cord left in from an earlier call** was taken for the trunk of the next call out: dial tone went to it and her digits on the trunk she had taken were never seen. A trunk already up when a call begins to route is no longer that call's, until it is released and taken again. The same applies to the caller-left-alone check (Rev 46), which a stale trunk held off.
5. **She takes a trunk and never dials.** Dial tone ran until the connect timeout. Now, outside tutor mode, 15s without a digit gets reorder and the call fails as `misdialled`, as a number dialled too short does (Rev 56).
6. **In tutor mode, after a prompt's last repeat** she was silent for good, the timeouts being lifted. Now, after the second repeat, she says once "If you are not sure what to do, press Repeat Help, and I will tell you again." (`stuck`, under `tutor:`).

— Code consequence for Claude Code, made the same day: `REACTIONS` and `_reactions()` in `tts/script.py`, `reactions:` and `tutor: stuck:` in script.yml; `caller_voice`, `called_voice`, `GameScript.reactions`, `occupants` and `reaction()` in `script_data.py`; `NUDGE_AFTER`, `PATCH_WAIT`, `DIAL_FIRST`, `WRONG_RING`, `_wrong_party()`, `_picks_up()`, `_fresh()`, `_note_stale()` and the nudge in `_operator_speaks()` in `flows.py`; the stuck line in `Tutor._repeat()`; the tests. No topic changes.

## 1.59 Changes in Rev 59

— On a call to the operator, once the caller has asked, the tutor says the call is for her before her first reply: "This call is for you, not for another line. Answer the caller yourself." (§4.9). Mark's request, 2026-10-17: the fourth lesson is such a call, and a new player expects to plug a cord in after every request. A new line under `tutor:`, `for-you`, with a short form, "This call is for you."; said on every tutored call to the operator that has a reply or a closing for her, so not on time and charges rung in on a trunk.

— Code consequence for Claude Code, made the same day: `for-you` in `TUTOR_KEYS` in `tts/script.py`, its lines in script.yml, said in `to_operator()` in `flows.py`, and the test. Two lines to render, `tutor.for-you` and `brief.for-you`. No topic changes.

## 1.58 Changes in Rev 58

— A tutor prompt the game waits on the board after stops mid-word once the board shows the player has done it (§4.9). Mark's report, 2026-10-17: she talked on after the cord was in. Before, the condition was checked only before she began and between her repeats. Now it is checked throughout the line, and her repeats, Repeat Help and More Help stop the same way; a line cut short leaves nothing to repeat. The three prompts to centre the switch — `center`, `center-dialled`, `center-ringing` — are given the condition too, the operator off the pair's lines, so they also stop, are not said if the switch is already centred, are said again if it is not, and are offered to Repeat Help and, in short form, to More Help.

— Code consequence for Claude Code, made the same day: `Tutor._line()` in `tutor.py`, `_centred()` in `flows.py`, and the test. No topic changes.

## 1.57 Changes in Rev 57

— A running game stops by itself after 10 minutes with nothing from the player, so Start must be pressed to play again (§3). Mark's request, 2026-10-17. Activity is what the player does: a cord in or out — a circuit's `peer` or `op`, a trunk's `seize` — a digit dialled, a station rung, and any key or button on the deck or the page. The game's own doing is not: a station taken off-hook, a trunk rung in, the tutor speaking, a call dealt on the automatic schedule. The stop is an ordinary one, logged "game stopped: no activity for 10 min", and the stopped game goes back to tutor 5 minutes later as before (§4.9, Rev 44). `idle_stop` in the configuration, 600s by default; 0 never stops.

— Code consequence for Claude Code, made the same day: `idle_stop` in `config.py`; `PLAYER`, `_active_at`, its updates in `on_command()` and `watch_clients()`, and the check in `run_scheduler()`, in `game.py`; the test. No topic changes.

## 1.56 Changes in Rev 56

— A number dialled with too many digits or too few gets reorder, the fast busy, on the trunk until the operator releases it, and the call fails as `misdialled` (§5). Mark's request, 2026-10-17. Too many: a digit more within 3s of the last digit the number needs — the game now waits that long after the last digit before taking a number as dialled, so the extra digit can be heard; 3s is longer than a dial takes to return and run ten pulses (control.md §8). Too few: 10s after a digit with the number not complete. The failure is counted when she releases the trunk, so the fast busy is heard for as long as she stays on it; a deadline passing first fails the call as `not connected`, as before. A wrong number of the right length is unchanged: busy tone, and she may redial (Rev 46). The rule holds in tutor mode as well, where it is the one failure that is not about the cords.

— Code consequence for Claude Code, made the same day: `DIAL_SETTLE`, `DIAL_PAUSE`, `_number()`, `_reorder()` and `Misdialled` in `flows.py`, `Reason.MISDIALLED` in `calls.py`, and the tests. The tone is new in the audio program, `"reorder"` on `tone/set` (audio.md Rev 20, mqtt.md Rev 35): `ToneKind::Reorder` and a row of the tone table in `engine.cpp`, its name in `net.cpp`.

## 1.55 Changes in Rev 55

— Once the tutor has said a prompt in full twice, she says its short form where script.yml gives one, under `tutor: brief:`, and More Help says the full line (§4.9, §7.4). Mark's request, 2026-10-17: the full prompts are right at first and too long once the player has done that step twice. Counted per prompt, not per call, since each kind of call has prompts of its own: a call out is the first to need `dial`, however many calls between rooms came before it. Every jack and number is the one prompt — `ring-front` to any room — and `dial-operator` is its own. Counted from Start, or from Tutor chosen mid-game; her own repeats, Repeat Help and More Help do not count. A short form may be given for any prompt but the introduction's three parts and the prompts before the operator speaks — `say`, `greet`, `respond` — which are short already and have a listen after them. A line with no short form is said in full every time. More Help is offered once she has finished a short line the game then waits on the player after — the answer, the switch, ring, the trunk, dial, the end of a call, "press Next Call" — for as long as Repeat Help would repeat it. A press says the full line at once; Repeat Help then repeats the full line, and More Help is done until the next short one. Her own repeats, 20s apart, say the line she last said. Short forms are rendered as `brief.<key>`, in her voice with the rest; one not yet rendered is not a gap, and she says the full line in its place.

— Code consequence for Claude Code, made the same day: `tutor: brief:` in script.yml, read by `tts/script.py` (`BRIEF_KEYS`, `brief-<key>` in `Script.tutor`, rendered as `brief.<key>`, since `tutor.brief-<key>` passes the 31-character limit on a name); `Tutor.said`, `prompt_of()`, `Tutor.more()` and `more_key` in `tutor.py`; `game/tutor/more` and the `more` command outside the introduction in `game.py`; key 8 in `streamdeck.py`; the tests. One new topic, `game/tutor/more` (mqtt.md Rev 34). The short forms are to be rendered.

## 1.54 Changes in Rev 54

— A long press, about half a second, on a pacing button — Tutor, Manual, Automatic, Listen — or on a stepper — `pause`, `gap`, `ramp`, `floor`, `jitter`, its label or either button — opens a short help beside it: what the pacing does, or what the value means, its range, its step and its starting value (§7.1). Mark's request, 2026-10-17. Works the same with a mouse held down. The press that opens it changes nothing; a tap still does what it did. A tap elsewhere or Escape closes it, as it does every popup. The pacing buttons are drawn dimmed rather than disabled while the game program is away, so that their help still opens; a tap on one then does nothing.

— Code consequence for Claude Code, made the same day: `HELP` and `showHelp()` in `web/app.js`, `data-help` and `#help` in `web/index.html`, and `web/style.css`. No topic changes.

## 1.53 Changes in Rev 53

— A long press on Tools, about half a second as on Next Call (§4.8), shows a key to the lamps: each state of §7.1's table, most urgent first, with the lamp drawn as on the board, lit as it is there, and a line saying what it means (§7.1). Mark's request, 2026-10-17. A tap still opens Tools; a tap elsewhere closes the key. Tools is a control, so the key is hidden with the Controls switch too.

— Code consequence for Claude Code, made the same day: `#lamps` in `web/index.html`, its long press in `web/app.js`, and `web/style.css`, where the lit lamp's glow now follows `lit` on any element and not only on a tile. No topic changes.

## 1.52 Changes in Rev 52

— On the page, a `peer` of `"deaf"` or `"ambiguous"` makes a tile a fault only once it has stayed so for a second (§7.1); until then the tile shows the `peer` before it. Found 2026-10-17 with the station `hook` test: the lamp flashed red as the station went off-hook and again as it went back, because the relay breaks the line for a moment and the detector reports `deaf` for that long, as it does for the cord switch's 0.2s break (Rev 45). A real fault is shown a second later. The tile's panel still shows the detector's own value, and `play` `"missing"` and `fault` are shown at once. The deck shows no `peer` faults, so it is unchanged.

— Code consequence for Claude Code, made the same day: `tileState()` in `web/app.js`. No topic changes.

## 1.51 Changes in Rev 51

— The loudspeaker plays ringback while a station reports ring (§6.6), Mark's request, 2026-10-17, so the player and the room hear the operator ringing, for as long as she holds the ringing key. Steady, not in the 2s-on cadence: it follows her key. A file on the monitor, `cue.ringback`, rendered by `tts/cue` — the period ringback of audio.md §8.2 — so the audio program is unchanged. The monitor plays one file at a time and that file is otherwise the tutor's voice; she comes first. A configuration switch, `ring_cue`, true by default. No topic changes.

— Code consequence for Claude Code, made the same day: `cue.py`, started from `main.py`; `ring_cue` in `config.py`; the Stream Deck does not take the cue for her voice (§7.4's Repeat Help and the flashing key); `tts/process` leaves `cue.*` out of its check for files in no scene; `tests/test_cue.py`.

## 1.50 Changes in Rev 50

— A sweep of the board from the Stream Deck (§7.4, §7.6), Mark's request, 2026-10-17, for checking the cabling after a recabling. Key 5 pressed twice within 0.5s gives each trunk in turn one short ring, 2s apart, so its lamp latches; key 6 pressed twice takes each station in turn off-hook for 1s, 2s apart, in jack order — the board's rows from the top, each left to right — rather than circuit order, so the lamps light in the order the eye reads the board. Either key pressed twice during a sweep stops it. Only with no game running: the game program refuses one while a game runs, and Start, Stop and losing a client end one. Each step goes on the game log, so the page shows it, and the hardware's own echoes light the tiles. Keys 5 and 6 did nothing on a press before, and a single press still does nothing. One new command and its echo, `game/sweep/set` and `game/sweep` (mqtt.md Rev 33), covered by the access list's `game/+/set`.

— Code consequence for Claude Code, made the same day: `sweep.py`, `_sweep_command()` in `game.py`, keys 5 and 6 in `streamdeck.py`, and the tests.

## 1.49 Changes in Rev 49

— A scenario chosen from the page counts as its once-a-game play (§4.10), Mark's request, 2026-10-16. Rev 40 left the deal after `n` calls to come regardless, and in the first play of `panic` on the switchboard it did: chosen, its sixteen calls counted as handled, so the whole scenario was dealt again the moment the board cleared, and the same rooms lit with the same complaints, which looked like callers ringing back. Choosing it again from the page still plays it.

— Code consequence for Claude Code, made the same day: `_start_call()` in `game.py` and the test. No topic changes.

## 1.48 Changes in Rev 48

— A caller left alone hangs up after 10s, and after 5s once a wrong number has been dialled for the call (§5, `cut off`), Mark's decision, 2026-10-16. Rev 46's 20s, restarted each time the operator came back on the line, kept a call he had given up on alive while he tried the cords: a real guest left in silence hangs up, and one just told it was the wrong number sooner.

— Code consequence for Claude Code, made the same day: `ABANDON`, `ABANDON_MISDIALLED` and `Ctx.misdialled` in `flows.py`, and the tests. No topic changes.

## 1.47 Changes in Rev 47

— The caller waits for her `closing:` (§4.7), found in a game on the switchboard, 2026-10-16: nbn-trace's guest asks "was that an outside call or from the lobby?" and hung up as the question ended, before she could answer, because a call to the operator with no conversation hangs up once its request has played. The game listens for her closing now, in every call that has one, and the tutor prompts it. Not saying it does not fail the call: she has done what it asked.

— Code consequence for Claude Code, made the same day: `SceneDef.closing`, `_closing()` in `flows.py`, called at the end of a call to the operator and of a busy call, and the tests. No topic changes.

## 1.46 Changes in Rev 46

— Three changes from a tutored game on the switchboard, 2026-10-16 (§5). A wrong number was met with silence, which tells the operator nothing; it gets busy tone now, until she hangs the trunk up. Pulling both cords mid-call, before it was connected, left the call open for good: from routing until connection the game watched only the trunk, the caller stayed off-hook with its lamp lit, and tutor mode has no timeouts, so nothing could end it and Next Call was refused. Now a caller lost for 20s before connection — no operator on its line, patched to nothing, no trunk up — is abandoned as `cut off`. The 20s is what tells a pulled answering cord from the switch centred before the front cord goes in, which look the same, since the game cannot see a cord in a station jack. And dial tone comes a second after the seizure rather than at once, as an exchange takes a moment to answer (Mark's request; tried at half a second first, and lengthened the same afternoon).

— Code consequence for Claude Code, made the same day: `_dial_tone()`, `_unless_abandoned()` and the busy tone in `_wait_for_right_number()` in `flows.py`, and the tests. No topic changes.

## 1.45 Changes in Rev 45

— A circuit's `peer` going empty, or its `op` going off, counts only once it has stayed so for a second, and `deaf` leaves the last `peer` standing (§5, `cut off`). Found on the switchboard, 2026-10-16: returning a cord pair's switch to its centre position, as the tutor asks once the far end answers, breaks both lines for about 0.2s. The detector reports both ends `deaf` and then idle for that long, and the game read it as a cord pulled: it ended the call with the parties still talking, and the tutor said the call was over. The same happened while the operator answered, and on every dial pulse. A real pull is now noticed a second later, which nothing in the game minds. The game program applies the hold as the messages arrive, so every wait in it sees the held value; the page and the deck show the detector's own.

— Code consequence for Claude Code, made the same day: `Board.HOLD` and `Board._hold()` in `board.py`, and the tests, which run it at their own speed. No topic changes.

## 1.44 Changes in Rev 44

— The game starts in tutor, and returns to tutor after five minutes stopped (§4.9), Mark's request, 2026-10-16: the installation's `game.toml` sets `pace = "tutor"`, and a new setting, `idle_tutor`, 300s, returns a stopped game in another pacing to tutor. A player who has moved on to manual or auto leaves it that way, and the next visitor, who has never seen a switchboard, should meet the tutor.

— Code consequence for Claude Code, made the same day: `Config.idle_tutor`, the timer in `game.py`, and the tests. No topic changes.

## 1.43 Changes in Rev 43

— Stations can be marked out of service (§6.5), Mark's request, 2026-10-16: `game.toml` gains `[out_of_service.stations]`, a station's number and the reason, beside Rev 36's trunks. Found on the switchboard: jacks 21–30 draw no loop current after a spark while station 3 was being moved from jack 23 to 29, so no lamp on that row lights, and the first lesson of a tutored game was a call from Housekeeping on jack 26, waiting for good. A station is out of every call, not only calls rung in, because a dead line can neither call nor be heard: its scenes are left out as if it were not fitted, `after:` chains and tutor lessons with them. Rev 36 noted stations might need this.

— Code consequence for Claude Code, made the same day: `Config.stations_out()` and its check, `fit()` in `script_data.py`, the start and `--check` logs in `main.py`, and the tests. No topic changes.

## 1.42 Changes in Rev 42

— Dial tone stops at the first digit (§5, `dialling`), found in the first game on the switchboard, 2026-10-16. It ran on under the dialling until the whole number was in, where a real exchange drops it as the first pulse arrives. It also comes back on a fresh seizure when the operator hangs up a trunk and tries again; before, a redial got no dial tone at all.

— Code consequence for Claude Code, made the same day: `_wait_for_right_number()` in `flows.py`, and the tests. No topic changes.

## 1.41 Changes in Rev 41

— A chosen scenario starts by itself as soon as the board is clear (§4.10), Mark's request, 2026-10-14: at once if it is clear when chosen, else the moment the last call ends, in any pacing but tutor. Rev 40 waited for Next Call or the schedule, and nothing on the deck shows that a choice is waiting. Other chosen scenes are unchanged: still the next call dealt.

— Code consequence for Claude Code, made the same day: `game.py`'s scheduler loop, and the tests. No topic changes.

## 1.40 Changes in Rev 40

— A scenario can be chosen from the page to show it (§4.10), Mark's request, 2026-10-14, for showing the game to friends. Rev 39 let it be chosen in manual and auto only, and dealt it on top of whatever was running. Chosen, it is now allowed in listen too, still never in tutor mode, and waits for a clear board: no call in progress and no `after:` scene waiting. Until then nothing else is dealt, and Next Call is refused on `game/error`. A chosen scenario does not use up its once-a-game play after `after_handled:` calls, so it can be shown as often as wanted. The automatic deal after `after_handled:` calls is unchanged.

— Code consequence for Claude Code, made the same day: `game.py` and the tests. No topic changes.

## 1.39 Changes in Rev 39

— A scenario: calls that arrive almost together, so the board lights up at once, Mark's request, 2026-10-14, from Remco's suggestion and Beth's story of Martha loose in the hotel. Three keys in script.yml, each usable on its own:

- **`mode: concurrent`** on an `after:` scene (§4.4): it starts `delay` seconds after the scene it follows has *started*, not ended, and whether or not that scene is ever connected. It waits for a free slot as well as its lines, rather than being dropped. `delay` may be a range, `[2, 5]`, drawn evenly from the game's seed.
- **`after_handled: <n>`** on a scene that follows none (§4.10): it is never in the deck, and is dealt once a game, as the next call after `n` calls have been handled. Not in tutor or listen pacing. While its scenario is on the board the automatic schedule waits. It stays in `game/scenes`, so it can be chosen from the page to try it.
- **`if_busy:`** on a call from a room to a room (§4.11): caller lines played, as in a busy call, when the called station turns out to be engaged in another call. So several guests can ask for the front desk at once, and the operator tells all but one to try later. A scene with `if_busy:` does not hold its called line or person for dealing.

Calls before connection in general stay deferred (§4.5); the scenario is the one place the operator is asked to route several calls at once. The first is `panic`, after the tenth call: Martha the dog loose in the hotel, a complaint from every guest room, the lobby and the restaurant, ending with Martha calling from her room to say someone is chasing her with a broom.

— Code consequence for Claude Code, made the same day: the loader checks the three keys (`tts/script.py`), renders `if_busy:` lines, and gives the tutor no Say line for an operator line only a scenario uses; `script_data.py`, `deck.py`, `game.py` and `flows.py`; `busy` is also the stage of a call found engaged (§6.1); the tests. No topic changes.

## 1.38 Changes in Rev 38

— The tutor's `ring-front` and `ring-rear` lines are named for the station, `tutor.ring-front-room403`, not the jack, `tutor.ring-front-29` (§4.9), Mark's request, 2026-10-12. Rev 37's renumbering moved no label off its station, yet 30 of those lines looked new or changed to the TTS run, since a line's text follows its label and its name followed the jack. Named for the station, a line changes only when what she says does: a new label, or the station cabled to a jack with another. Renumbering jacks changes no file.

— Code consequence for Claude Code, made the same day: the loader names the lines by station (`tts/script.py`); the game looks them up by the called line's name (`flows.py`); the 88 wavs, raw and delivered, and their manifest entries renamed, nothing rendered; the tests.

## 1.37 Changes in Rev 37

— The board's station rows run 21–30, 11–20, 1–10 from the top (§7.1), checked against the 551 by Mark, 2026-10-12, closing the §10 item. Rev 5 assumed jack 1 at top left. Rows still run left to right. The labels stay where they were on the board — the hotel's services on the top row, the rooms in ascending order on the two below — so script.yml's `jacks:` items move: the top row's labels go from jacks 1–10 to 21–30 and the bottom row's from 21–30 to 1–10. `hardcopy/strips.py` already printed the strips in this order.

— Code consequence for Claude Code, made the same day: `app.js` draws the rows in the new order; script.yml's `jacks:` renumbered. No topic changes.

## 1.36 Changes in Rev 36

— Trunks can be marked out of service (§6.5), Mark's request, 2026-10-10. Ringing each of the 551's trunk jacks in turn showed two that cannot take a call rung in: jack 6's lamp lights only while ring is applied and does not latch, and jack 8's lamp does not light at all, though its relay operates. Both are faults in the switchboard, to be repaired later (TODO.md); six working trunks are enough for the game. `game.toml` gains an `[out_of_service.trunks]` table, a trunk's number and the reason, and no call is rung in on a trunk listed there. Stations may need the same later; the table takes only trunks for now.

— Code consequence for Claude Code, made the same day: `Config.out_of_service` and `working_trunks()` in `config.py`, checked at load; `Game._free_trunk()` picks only from the working trunks; `main.py` fits the scenes to them and logs each trunk out of service at start and under `--check`; the tests.

## 1.35 Changes in Rev 35

— Repeat Help after a "Say:" prompt too (§4.9), Mark's request, 2026-10-09. Rev 34 left it out because the game listens for the operator after one, and the loudspeaker would be heard as her. Now a press there stops the listen first, she says the prompt again, and the game listens afresh. A press once the operator has started speaking is refused, so her answer is not cut off. A press does not count as one of her own repeats.

— Code consequence for Claude Code, made the same day: `_operator_speaks()` in `flows.py` races the listen against the press; `Tutor.asked` and `release()` in `tutor.py`; the tests.

## 1.34 Changes in Rev 34

— Repeat Help (§4.9, §7.4), Mark's request, 2026-10-09: once the tutor has finished a line and the game is waiting on the player, the deck's key 7 says "Repeat Help", and a press says the line again. That covers each part of the introduction, the call steps that wait on the board — answer, the switch, ring, the trunk, dial, the end of a call — and "press Next Call when you are ready for another". Not a "Say:" prompt: the game is listening for the operator then, and the loudspeaker would be heard as her. The line stays repeatable until the player does what it asks or she says another. The game program publishes it on `game/tutor/repeat` and takes `game/repeat/set`, an event at QoS 0 (mqtt.md Rev 31).

— Code consequence for Claude Code, made the same day: `Tutor.repeat()`, `repeat_key` and `hold` in `tutor.py`; the `repeat` command in `game.py`; key 7 in `streamdeck.py`; the tests.

## 1.33 Changes in Rev 33

— While the tutor waits for a key, the deck flashes it (§4.9, §7.4), Mark's request, 2026-10-09: More Help and Next Call after each part of the introduction but the last, Next Call alone after the last, and Next Call after a call once the cords are out and she has asked for the next. Only once she has finished speaking, so the flashing does not compete with her. The game program publishes what she is waiting for on `game/tutor/waiting`, `"more"`, `"next"` or `""` (mqtt.md Rev 30), since the deck cannot tell her waiting for Next Call from her waiting for the cords to come out.

— Code consequence for Claude Code, made the same day: `_waiting()` in `game.py`; `Panel.flash()` and keys 4 and 8 in `streamdeck.py`; the tests.

## 1.32 Changes in Rev 32

— Tutor mode becomes a pacing, `tutor`, the first of four (§4.9), Mark's decision, 2026-10-09. It was manual pacing with tutoring in all but name: one call at a time, each on Next Call. As a switch beside the pacing it allowed tutor with auto or listen, which nobody wanted, and two controls where one will do. Moving a player on is now a change of pacing, mid-game if need be. `game/tutor/set` and `game/tutor` are withdrawn (mqtt.md Rev 29); `pace/set` takes `"tutor"`, refused while any of her lines has no wav. A configured `pace = "tutor"` falls back to manual at start-up, with a warning, while any is missing.

— The deck's pacing key shows four names, Tutor first, and cycles Tutor, Manual, Auto, Listen (§7.4). Key 8 is the health lamps again, as through Rev 28, and More Help while she introduces the board; key 7 is the success percentage throughout. The page has a fourth pacing button.

— Code consequence for Claude Code, made the same day: `PACES` in `pacing.py`; the switch moves into the `pace` command in `game.py`; `streamdeck.py`; `index.html` and `app.js`; the tests.

## 1.31 Changes in Rev 31

— The tutor's introduction is in three parts — the jacks, the cords, the switches and dial — Mark's request, 2026-10-09: all at once it was too much to take in (§4.9). After each part but the last she says to press More Help, or Next Call to start playing, and waits for one; after the last, for Next Call. This is the same in every pacing: in auto and listen the first call no longer follows the introduction by itself. More Help pressed mid-part cuts it short and goes on to the next part; Next Call at any point ends the introduction and deals the first call, as before. script.yml's `intro:` and `begin-manual:` give way to `intro-jacks:`, `intro-cords:` and `intro-switches:`.

— While she introduces the board, the Stream Deck's key 7 is More Help in place of the success percentage (§7.4). It publishes `game/more/set`, an event at QoS 0 like `next/set`, guarded the same way, and the game program publishes the part she is on as `game/tutor/intro`, `"1/3"` to `"3/3"`, or `""` (mqtt.md Rev 28). The key is lit while a further part remains.

— Code consequence for Claude Code, made the same day: `INTRO` in `tutor.py`; `_tutor_intro()` and the `more` command in `game.py`; key 7 in `streamdeck.py`; `tts/scenes --tutor` joins the three parts; the tests.

## 1.30 Changes in Rev 30

— A tutored game starts with one call of each kind (§4.9), Mark's request, 2026-10-08: between rooms, out to a number, in from outside, and to the operator, in that order, so a new player meets every interaction before the deck takes over. Each kind is a group of suitable scenes under `tutor: lessons:` in script.yml, and each game picks one from each group at random, so a restart does not repeat the last game's. The picks come from the game's seed, so a replay picks the same, and they are logged. The loader refuses a group that mixes kinds, or names a scene that is inactive, unknown or an `after:` scene. No topic changes.

— Code consequence for Claude Code, made the same day: `lessons` and `scene_kind()` in `tts/script.py`; `GameScript.lessons`, fitted to the circuits built (§6.5); `pick_lessons()` and the dealing in `game.py`; `test_tutor.py`.

## 1.29 Changes in Rev 29

— Tutor mode (§4.9), Mark's request, 2026-10-08, in place of an instruction sheet: a new player has too many steps to take in from paper. With it on, a senior operator's voice on the audience loudspeaker says what to do at each step of a call — which cord, which jack, which switch, what to say, what to dial — at the moment the game sees the step is due, and the game waits for her. She introduces the board when the game starts. One call is in progress at a time, nothing fails for being slow, a prompt not acted on is said again, and the next call waits for the cords to come out. Her lines are rendered offline like every other, from a `tutor:` section of script.yml, one whole sentence for every jack, number and operator line they name.

— The Stream Deck's key 8 is the tutor switch (§7.4). It showed three health lamps, which the page already shows; the error that turned it red is on the strip as before. `game/tutor/set` and `game/tutor` are new (mqtt.md Rev 27), and the page's state line says "Tutor" while it is on (§7.1).

— She is on the loudspeaker, not in the headset, which is the reason for most of §4.9's rules. In the headset her voice would go out on the line the operator is bridged to and set off that line's speech detection. On the loudspeaker it reaches the operator's microphone acoustically, so she is still never speaking while the game listens. The audio program needed a file source on the monitor for it: audio.md Rev 11.

— Code consequence for Claude Code, made the same day: `tutor.py`; hooks in `flows.py` at each step; the switch, the introduction, one call at a time and the end of a call in `game.py`; `Slots.timeless`; `script_data.py` loads her wavs, and refuses tutor mode while any is missing rather than refusing to start; the loader in `tts/script.py` renders `tutor:`; key 8 in `streamdeck.py`; `app.js`; `test_tutor.py`.

## 1.28 Changes in Rev 28

— A call in on a trunk is signalled with one short burst of ring, `shortring/set` (§4.3, §6.1, §6.4; mqtt.md Rev 26, control.md Rev 25), Mark's request, 2026-10-05, in place of ring in the standard cadence until answered. The trunk cannot see a seizure while it is ringing, so an operator who plugged in during a 2s ring-on interval was not seen until it ended. The 551's trunk signal latches on a short burst, so the lamp stays lit without further ring and the trunk is readable from the moment the burst ends. Nothing else about the call changes: the answer timeout runs from the start of the call as before, and an unanswered call fails as `no answer`. The game still sends `ring/set` `"off"` when the call ends, which cancels a burst that is still ringing. The page's `ring` diagnostic keeps the cadence (§7.5).

— Code consequence for Claude Code, made the same day: `Hw.short_ring()` in `link.py`; `outside_to_station` and `to_operator` from an outside line call it instead of `ring_trunk(…, True)`; the simulator and the tests' fake echo a 0.5s burst on `ring`.

## 1.27 Changes in Rev 27

— The health column shows the controller's firmware, `ctl/firmware` (§7.1, mqtt.md Rev 25), 2026-10-01, so a stale build on the board is seen at a glance. Display only.

## 1.26 Changes in Rev 26

— The page lists the scenes for a chosen next scene in alphabetical order of id (§4.8), Mark's request, 2026-09-30. The page sorts them; `game/scenes` is unchanged. Code consequence for Claude Code, made the same day: `app.js`.

## 1.25 Changes in Rev 25

— Diagnostics from the page (§7.5), Mark's request, 2026-09-30, for bring-up and for finding a fault at the board. A station's panel takes it off-hook and plays a 1kHz tone, a run of speech, or feeds its receive channel to the loudspeaker; a trunk's panel rings it, and plays tone, speech or loudspeaker the same way; a new Tools button opens the same three for the operator tap. Each is a toggle. They run whether or not a game is running, and are kept apart from the calls: a circuit in a call refuses a test, and a circuit under test is busy for dealing (§4.4). Stop ends them all (§3). Voice on the tap needs the audio program to play a file there, which it did not; audio.md Rev 10 adds it.

— A chosen next scene (§4.8). A long press on Next Call lists the scenes; the one chosen is the next dealt. `game/scenes` and `game/queue` are new, with `game/queue/set`. §10's open item "Start a named scene" is closed by it.

— The game fitted to the circuits built (§6.5): the game program's configuration, and two command-line options, say how many stations and trunks exist. A scene that needs a station beyond the first `stations`, or an outside line when `trunks` is 0, is left out with the scenes that follow it; calls ring in and go out only on the first `trunks` trunks. `game/stations` and `game/trunks` say what was set, so the page offers tests only on circuits that exist.

— Code consequence for Claude Code, made the same day: the game program, the page, the access list (mqtt.md Rev 23), the configuration file, and the audio program (audio.md Rev 10).

## 1.24 Changes in Rev 24

— A call to the operator may ring in on a trunk (§4.3, §4.6), Mark's request, 2026-09-30. Its calling line is an outside name and it has no `called:`: the game rings a free trunk, as for a call in to a room, and the operator answers it with her listening key. The rest is as for a call to the operator from a room: the request plays after she has spoken, it is connected when the request has played, and any conversation lines each wait for her. A call with a request and no conversation hangs up as soon as the request has played, without waiting for her to answer it.

— It is for the long-distance operator's time and charges. After a long-distance call a guest placed is over, the long-distance operator rings the hotel with the time and the charge, once, so that the hotel can put it on the room bill, and hangs up (§4.6). Peter at the museum had it from a guest who worked as a hotel clerk: if you did not have your pencil ready you had missed it, and the hotel could not charge the room. Five scenes gain one, each an `after:` of the call it bills. A collect call, and a call placed by someone outside to a guest, are not billed to the hotel and have none. A guest who asked for time and charges still hears them from her at the end of the call as well.

— An unanswered one fails as `no answer`, as any unanswered call does (§5); whether she wrote the figures down is not something the game can know.

— Code consequence for Claude Code, made the same day: the game picks a free trunk for such a call as it does for a call in to a room, and the call-to-the-operator flow rings it. `test_game.py` covers it.

## 1.23 Changes in Rev 23

— A station jack may carry `guest:`, the name of whoever is staying in the room at that jack (§6.3), Mark's decision, 2026-09-29. It is typed on the operator's guest list card, `hardcopy/cards.py`. The card had worked out each guest's room from the scenes, which put a guest on whichever line they called from — Mr. Pike on the lobby house phone as well as in 204 — and took the names from a table of its own. The jack is where the room is, so the guest goes there too. It is left out for an unoccupied room and for a jack that is not a room.

— The game does not read it. The loader refuses an empty one.

— Code consequence for Claude Code, made the same day: the loader accepts the key and checks it, `test_game.py` tests the refusal, and `hardcopy/cards.py` builds the guest list from it.

## 1.22 Changes in Rev 22

— script.yml says what the player says (§4.7), Mark's request, 2026-09-29: an `operator:` key on each line the game waits for the operator before, naming a line under a new top-level `operator_lines:`, or giving an id and text of the scene's own. Mark wants every scene as one recording, both halves of the conversation, which needs the operator's half written and rendered. The TTS run renders the lines in the voice of a new cast member, `hotel_operator` — `operator` in the cast is already the long-distance operator.

— The game ignores them: the person at the board speaks them. An `operator:` is refused where the game does not wait for her, because there the next line would play over it; and one that names no line under `operator_lines:`, or whose inline id the scene already uses. It is optional: `python -m tts.script` counts the places still without one.

— Considered and not adopted: operator lines as conversation entries of their own, beside `caller:` and `called:`. That is the more natural form to write, but it changes what the flows iterate over and would make `wait:` redundant with a preceding operator line. A key on the line it precedes changes nothing the game reads.

— A scene-level `closing:`, in either form, for what she says after the last line (§4.7), Mark's request, the same day: without it a call to the operator ended on the guest's question. Refused in a call where she has left the line by the end — any but a call to the operator or a busy call. The 13 such scenes each have one of their own.

— Code consequence for Claude Code, made the same day: the loader, the game program's exclusion of the operator's lines from a scene (`script_data.py`), tests of the five refusals, and `tts/scenes --batch`, which writes each scene to an mp3 with the operator's lines in their places. Every place in the 105 scenes has its `operator:`: four stock lines and 25 of the scenes' own.

## 1.21 Changes in Rev 21

— `ringback:` is allowed on any line spoken on a trunk (§4.6), Mark's request, 2026-09-28: the called side of a call out, as in Rev 20, and now also the calling side of a call in. A long-distance operator who could not get through calls back when she has the party (script.yml, "Long distance"): the call rings in on a trunk, the hotel operator puts it through to the room, and only then does the far end ring — on the calling side. The loader's refusal now names a line spoken on a station, or in a scene where every line waits already.

— Code consequence for Claude Code, made the same day: the loader's check only — the flows already rang whichever trunk the line is spoken on. A test covers ringback on the calling side of a call in.

## 1.20 Changes in Rev 20

— Two more keys on a conversation line, `pause:` and `ringback:` (§4.6), Mark's request, 2026-09-28. Rev 19's long-distance call runs through a chain of operators — the rate operator, then each toll center on the route answering with its town's name — as the 1950s calls did. Played back to back, the chain is a gabble; the real ones had a beat at each step while the next operator came on, and the far end rang before anyone answered. `pause:` is that beat, silence before the line; `ringback:` is ringback tone on the trunk before the line, the far end ringing.

— `ringback:` is refused anywhere but a `called:` line of a call to an outside line: ringback is a trunk tone, and only there is the called side a trunk. Both are refused unless a number of seconds above 0 and at most 30.

— Considered and not adopted: a gap between every pair of lines, set once for the game. It would slow every conversation, and the beats that matter are particular ones.

— Code consequence for Claude Code, made the same day: the loader and the flows; the game program's tests cover both keys and the three refusals.

## 1.19 Changes in Rev 19

— A conversation line may wait for the operator (§4.6), Mark's request, 2026-09-28. A long-distance call from the hotel goes through the local operator: the hotel operator dials 0, the local operator answers, the hotel operator asks for long distance, and only then does the long-distance operator come on and talk to the guest. Until now a scene with a called party played its conversation straight through once connected, so there was no place for the hotel operator to speak in the middle of one. A line marked `wait: true` plays only after the operator has spoken on that line's side of the call and stopped — the listen that calls to the operator and busy scenes already make before every line.

— A conversation line may name its own speaker with `person:` (§4.6). The long-distance operator is not the local operator who answered, and neither is the party she rings, but all three speak on the same trunk. The line plays on its side of the call as before; `person:` changes only whose voice the TTS run uses, and it must be in the cast.

— `after:` scenes may form a chain of any length (§4.4), Mark's request, 2026-09-28: a guest whose requests to housekeeping grow more absurd call by call is a story in five calls, in order. The loader refused a scene following one that itself follows another; that rule is gone. It now refuses a scene named in two `after:`s — both followers would be scheduled together, each would hold the guest, and each would wait forever for the other to let go — and a loop of `after:`s. The game program needed no change: a follower's own follower is scheduled when it ends, as any other.

— `timeout` (§5) now also covers a `wait:` line the operator never speaks before. Considered and not adopted: a new scene shape for long distance. Two keys on a line cover it, and cover a guest handing the telephone to someone else as well.

— Code consequence for Claude Code, made the same day: the shared loader allows chains of `after:`s and refuses two followers and loops; it checks both keys and rejects `wait:` where every line waits already, and on a line with neither `caller:` nor `called:`; the flows listen before a `wait:` line; the game program's tests cover a wait on the trunk and both rejections.

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

**Start.** Accepted only while `run` is `"off"`; while running it is ignored. The tallies are zeroed (§5), the call number restarts at 1, the gap returns to its configured value (§4.3), the deck is shuffled (§4.4), the loudspeaker's source is set to the tap (§6.4), and `run` reads `"on"`. In automatic pacing, auto or listen, the first call starts at once; in manual pacing nothing happens until the page asks for a call. A game is one session in the game program's SQLite log.

**Stop.** Every call in progress is torn down at once: stations on-hook, trunk ring off, every file and tone stopped, every listen cancelled; every `after:` scene that was waiting is dropped; the call slots clear (§6.1); the loudspeaker's source goes back to the tap (§6.4). `run` reads `"off"`. Calls torn down this way are neither successes nor failures (§5). Every diagnostic running is ended too (§7.5, Rev 25), and a board sweep (§7.6, Rev 50), and a chosen next scene is forgotten (§4.8). Last, with the controller online, the switchboard's power is cut for 1s, `ctl/power_cut/set` `"on"` (Rev 63): a trunk rung in holds its lamp and buzzer on the switchboard's own battery until a cord goes in, and only the cut clears it. `run` reads `"off"` without waiting for the cut to end. The tallies stay as they were until the next start, so the player can see the score.

**Left alone** (Rev 57). A running game with nothing from the player for `idle_stop` seconds, 600 by default, stops as if Stop had been pressed, and says so on the log: "game stopped: no activity for 10 min". Start begins a new game. The player's acts are a cord in or out (`peer`, `op`, a trunk's `seize`), a digit, a station rung, and any command from the deck or the page; nothing the game does itself counts, so a game in automatic pacing dealing calls to an empty room stops too. 0 never stops.

**Losing a client.** If the controller or the audio program goes down during a game — `ctl/status` or `ctl/audio_status` offline, or two missed `esp_heartbeat`s (`mqtt.md` §8) — the game program does what Stop does and logs why, and `run` reads `"off"`. The player is not charged for the calls it abandons. It does not restart the game when the client returns; that is Mark's decision, from the page.

The game program always starts with `run` `"off"`.

# 4. Call Pacing

## 4.1 Manual

The Next Call key on the Stream Deck starts one call (Rev 13; until the deck is commissioned the page's Next Call button does too). Nothing else starts a call, apart from `after:` scenes (§4.4).

The key publishes `game/next/set`, at QoS 0, with an empty payload. The game program keeps its own count and starts the next call if `run` is `"on"` and a scene can be dealt (§4.4). If not, it reports why on `game/error`.

Two guards keep one tap to one call (Rev 4). QoS 0 is never resent on reconnect, so a connection that drops mid-send cannot deliver the command twice. The cost is that the tap may be lost, and the operator taps again. The page disables Next Call when it is tapped and re-enables it when `started` changes or `game/error` is published. It also re-enables after 3s regardless, so a lost tap does not leave the button dead. The Stream Deck's key is guarded the same way (§7.4). Two pages open at once could each start a call, and so could the page and the deck. That is accepted, since only Mark runs them.

`next/set` is accepted in automatic pacing too. It starts a call at once, and the automatic schedule then runs from that call (§4.2). In listen, that call is one more on the board, and the schedule waits for it to end as well.

## 4.2 Automatic

The next call starts `gap` seconds after the most recent call to start has been **connected** (§4.3) or has ended, whichever comes first.

Timing from the most recent call rather than from every call means that at most one call is ever waiting for the operator to connect it. Calls overlap — the next one arrives while the last is still talking — but the operator is never asked to route two at once. That is the case Mark has deferred (§4.5).

While a call is waiting to be connected, no next call is scheduled and `game/next_at` is empty. Once it is scheduled, `next_at` is the host time it will start, and the page counts down to it.

**Listen** (Rev 16), `pace` `"listen"`. The next call starts `pause` seconds after the board has emptied (Rev 17; Rev 16 used `gap`): every call has ended, however it ended, and no `after:` scene is waiting to start (§4.4). A call that succeeds ends when its parties hang up as the script ends; one that fails ends when it fails, so a missed call does not stall the game. Calls never overlap, and the audience hears each conversation through (§6.4). An `after:` scene still starts its own `delay` after the scene it follows, and the schedule waits for it too, so a story's second call is not interrupted by a new deal. If a waiting `after:` scene cannot start after all — every slot or every trunk busy — the board is empty and the schedule runs from then. The wait is `pause` exactly, every time: listen is for enjoying the conversations, so it has no ramp and no jitter, and `gap`, `ramp`, `floor` and `jitter` are auto's alone and are not changed by it (Rev 17). `next_at` is the board's emptying plus `pause`; while anything is on the board it is empty.

## 4.3 Connected, and the Ramp

A call is **connected** at the point where the operator's routing work is done:

| **Scene** | **Connected when** |
| --- | --- |
| To a station, from a station or a trunk | the called station answers — the game takes it off-hook after ring arrives |
| To an outside line | the called party answers on the trunk after ringback |
| To an outside line marked `busy: true` | busy tone starts on the trunk |
| To a station found engaged, in a scene with `if_busy:` (Rev 39) | it is found engaged (§4.11) |
| To the operator (no `called:`), from a room or rung in on a trunk (Rev 24) | the request has finished playing |

These are the milestones the game program must expose to the scheduler. How it reaches each one — which listens, which timeouts — is the game program's flow and not this document's.

**The ramp.** The gap shrinks as the game goes on:

```text
gap_now = max(floor, gap − ramp × connected)
wait    = gap_now × (1 + jitter/100 × u),   u drawn evenly from −1 to 1, and never below 0
```

where `connected` is the number of calls connected so far in this game. `gap`, `ramp` and `floor` are set from the page; `gap_now` is what the scheduler uses, and it is published so the page shows it. `ramp` of 0 is a constant rate.

**Jitter** (Rev 12). The scheduler waits `wait`, not `gap_now`: a draw spread evenly around `gap_now` by `jitter`, a percentage. At `gap_now` 20 and `jitter` 50 every wait is between 10s and 30s, and they average 20s. `jitter` of 0 is the fixed wait. `floor` bounds `gap_now`, the centre, and not the draw, so near the floor a wait can fall below it; bounding the draw would lift the average there. The draws come from the game's seed (§4.4), so a replay draws the same sequence. `next_at` is the drawn start; `gap_now` stays the centre.

A change to any of the four takes effect at the next scheduling, not on a call already scheduled.

Ranges, clamped by the game program and echoed as applied: `gap` 0–600s, `ramp` 0–60s, `floor` 0–600s and not above `gap`, `jitter` 0–100%, and listen's `pause` 0–60s (Rev 17). Starting values come from the game program's configuration file: manual pacing, `gap` 20, `ramp` 0, `floor` 5, `jitter` 0, `pause` 3. They hold across games until changed, and return to the configured values when the game program restarts.

## 4.4 Which Scene, and Scenes That Follow Another

**The deck.** At game start the game program takes every active scene in script.yml without `after:` and shuffles it into a list, the deck. Every new call, manual or automatic, is dealt from the deck. So every scene is played once before any is played twice, in an order that differs from game to game (Rev 2). A scene marked `active: false` is not played at all: it is never in the deck and never follows another, and its wavs need not exist (Rev 14).

**Dealing.** A new call takes the first scene in the deck whose lines and people are all free, and removes it. A scene's lines are its calling and called lines, stations and outside names alike (Rev 3). Its people are the `person:` under `calling` and `called`. A call to the operator has no called line or person. A line or person is busy if it belongs to a call in progress, or to a waiting `after:` scene (below). Scenes passed over stay where they are, so a scene held back because its line was busy comes up at the next call. If no scene in the deck can be dealt, the call does not start, the log says so, and in automatic pacing the scheduler tries again after `gap_now`. A `next/set` that cannot be satisfied this way is reported on `game/error`.

**Reshuffle.** When the deck is empty it is shuffled again from the full list, and dealing carries on. If the new deck would start with the scene dealt last, that scene moves to second place, so no scene plays twice in a row across the reshuffle. The log records each reshuffle.

**Replay.** The shuffle uses a seed chosen at game start. The seed and each deck's order go into the game's SQLite session record, not onto MQTT. The page is not told the order and does not need it.

**Scenes that follow another.** An `after:` scene (script.yml, "Order") is never in the deck. It starts `delay` seconds after the scene it follows has ended, in either pacing, as long as that scene was **connected** (§4.3). If it wasn't — the operator never answered, or never put the call through — the `after:` scene is dropped and the log says so (Rev 2; Rev 1 started it whenever the earlier scene ended). It is part of the story, not a new deal: `nbn-trace` two seconds after `nbn-kaplan`, `hale-pizza` three minutes after `hale-busy`. An `after:` scene may itself be followed, so a story can run to any number of calls; each scene has at most one follower, and the chain has no loop (Rev 19). From the moment it is scheduled until it starts, its lines and people count as busy for dealing. If any of them is still busy in another call when its delay runs out, it waits until all are free and then starts (Rev 3). It counts as a call. It has a call number, it counts in `started`, and it succeeds or fails like any other call. It does not reset the automatic schedule. The page shows a waiting `after:` scene in the log with its start time.

**Scenes that start with another** (Rev 39). An `after:` scene marked `mode: concurrent` starts `delay` seconds after the scene it follows has *started*, not ended, and whether or not that scene is ever connected: it is scheduled as that call opens. So a chain of them puts several calls on the board almost at once. Its `delay` may be a pair, `[2, 5]`, for a wait drawn evenly between the two, from the game's seed apart from the deck's shuffle, so a replay draws the same. Like any `after:` scene its lines and people are busy while it waits, and it waits for them to come free; it waits for a free slot too (below), so a scenario longer than eight calls keeps the board full rather than losing its tail. Stop drops it. The follower it has in turn is scheduled only once it starts, so the chain pauses while the board is full.

At most eight calls are in progress at once — the number of call slots (§6.1). A call that would be a ninth is not started, and is treated like a scene that cannot be dealt; a waiting `mode: concurrent` scene waits for a slot instead.

## 4.8 A Chosen Next Scene

Rev 25. A long press on Next Call lists every scene that could be dealt — the active ones without `after:`, within the circuits fitted (§6.5) — from `game/scenes`, one id per line. The page shows them in alphabetical order of id (Rev 26). Choosing one publishes `game/queue/set` with its id; the game program echoes it on `game/queue`. The next call dealt, by Next Call or by the automatic schedule, is that scene rather than the deck's, if its lines and people are free; it is then taken out of the current deck, so it does not come round again until the reshuffle, and `game/queue` goes empty. If they are not free, the call is dealt from the deck as usual and the choice stays for the call after. `game/queue/set` with an empty payload clears the choice. It may be made while no game is running, and the first call of the next game is then that scene; Stop forgets it. An id that is not in `game/scenes` is refused on `game/error`.

## 4.9 Tutor Mode

Rev 29. A voice on the audience loudspeaker talks a new player through each call: a senior operator, cast member `tutor`, calm and unhurried. Her lines are in script.yml under `tutor:`, rendered offline in her voice like every other line, and played on the monitor with `audio/monitor/play/set` (audio.md §10.4). The game program decides when she speaks, from the same topics it runs the calls on.

**The pacing** (Rev 32). Tutor mode is the pacing `tutor`, first of the four on `game/pace` and the deck's pacing key (§7.4). It is manual pacing with her: each call on Next Call, never on a schedule. Rev 29 to Rev 31 had it as a switch of its own, `game/tutor/set`, beside the pacing. It may be chosen whether or not a game runs. Chosen before Start, she introduces the board and the game starts with the lessons; chosen mid-game, she tutors from the next call, with no introduction and no lessons. Another pacing chosen mid-game takes effect at once: she stops mid-word, and calls in progress go on without her — which is how a player is moved on. `pace/set` `"tutor"` is refused on `game/error` while any of her lines has no wav, naming them, since a tutor with gaps is worse than none; the game program does not refuse to start for it, and a configured `pace = "tutor"` falls back to manual.

**Back to tutor** (Rev 44). The installation's `game.toml` sets `pace = "tutor"`, so the game program starts in tutor. A game left stopped in any other pacing returns to tutor after `idle_tutor` seconds, 300 by default — counted from the stop, from start-up, or from the last pacing chosen while stopped, whichever is latest — so the next visitor finds it as a newcomer should. Never while a game runs; 0 turns it off. The return is logged, "pace tutor: stopped 300s", and published on `game/pace` like any other change.

**When she speaks.** At each step, before the player has to act, with the call held until she has finished:

| **Step** | **She says** | **The game then waits for** |
| --- | --- | --- |
| Start | the introduction's first part, the jacks, ending "press More Help, or Next Call to start playing" (Rev 31) | More Help or Next Call |
| More Help | the next part: the cords, then the switches and the dial. The last ends "press Next Call" | More Help or Next Call; after the last, Next Call |
| A room's lamp lights | which cord, the lit jack, and the switch to push. One line: the game cannot see a cord go into a station jack | the caller's `op` |
| A trunk's lamp lights | which cord, and the trunk jack | the trunk's `seize`, which the cord makes |
| The trunk is seized | the switch to push | the trunk's `op` |
| A call to the operator, once the caller has asked (Rev 59) | "This call is for you, not for another line. Answer the caller yourself." | the next line |
| Before every listen | "Say:" and the operator line the script gives there (§4.7), or "Greet the caller" for a request, or "Now it is your turn to speak" | the listen |
| Ringing a room | the cord, the jack for that room by name, and the switch that rings it: the front cord and the near switch for a call from a room, the rear cord and the far switch for a call from a trunk | that station's `ring` |
| The room rings, call from a trunk | return the near switch to the centre, before the room answers | — |
| Calling out | the front cord, into any free trunk | any trunk's `seize` |
| The trunk is seized | keep the switch pushed, and the number to dial when dial tone comes, as the operator's card prints it: "Sunset four, four one oh one", or "zero, for the operator" | the first digit |
| Ringback | return the switch to the centre when the party answers. Ringback runs on until she has finished, so she does not talk over the far end's first line | — |
| Busy tone | "That is a busy signal. Tell the caller", then the Say prompt | the listen |
| After the last `wait:` line | return the switch to the centre. In a call with a `wait:` line this replaces the two above: the call still needs her | — |
| The call ends | both cords out and the switches centred; for a call to the operator, the one cord | every `op` and `peer` of the call's circuits clear and its trunk released |
| Cleared, in manual pacing | "press Next Call when you are ready" | — |

**Never over a listen.** The operator's microphone hears the loudspeaker, so a listen while she speaks would hear her as the operator. Every listen in tutor mode is preceded by one of her lines, which ends before the listen starts, and saying a line stops any line still repeating.

**Stopped once done** (Rev 58). A prompt the game waits on the board after — the answer, the switch, ring, the trunk, dial, centring the switch, the end of a call — stops mid-word as soon as the board shows the player has done it, and is not said at all if it already does.

**Said again.** A prompt the player does not act on is said again 20s after it ended, and again 20s after that, then not again. A Say prompt whose listen hears nothing in 20s is said again the same way; after the third, the line plays as after any listen that times out.

**The introduction** (Rev 31) is in parts, `intro-jacks`, `intro-cords` and `intro-switches`, so a new player takes in one thing at a time. Each part but the last ends by asking for More Help or Next Call, and she waits for either, as long as it takes. More Help is the Stream Deck's key 8 while she is introducing (§7.4; key 7 at Rev 31), and publishes `game/more/set`; pressed while she is still speaking, it cuts the part short and goes on to the next. After the last part More Help does nothing, and at any other time it is refused on `game/error`, unless a short prompt is waiting (Rev 55, below). Next Call at any point ends the introduction and deals the first call. The part she is on is `game/tutor/intro`, `"1/3"` to `"3/3"`, and `""` when she is not introducing.

**The key she asks for flashes** (Rev 33). Once she has finished speaking and waits for a key, the game program says which on `game/tutor/waiting`: `"more"` after a part of the introduction that ends "press More Help, or Next Call", `"next"` after the last part and after a call once the cords are out and she has said "press Next Call when you are ready for another", and `""` at any other time, including while she speaks and while the cords are still up. It goes back to `""` when the call is dealt, when More Help moves her on, and when she stops. The deck flashes the key she asks for (§7.4).

**Repeat Help** (Rev 34). Once she has finished a line and the game is waiting on the player, the line can be said again: the deck's key 7 reads "Repeat Help" and publishes `game/repeat/set`, an event at QoS 0, and the game program says the line again at once. Repeatable are each part of the introduction, every prompt the game waits on the board after — the answer, the switch, ring, the trunk, dial, the end of a call — and "press Next Call when you are ready for another". It stays repeatable until the board shows the player has done what it asks, or she says another line, whichever comes first; the game program publishes it on `game/tutor/repeat`, the line's key under `tutor:`, or `""`. A "Say:" prompt is repeatable too, from Rev 35, while the game listens for the operator after it: a press stops the listen first, so the loudspeaker is never heard as her, she says the prompt again, and the game listens afresh. Once the operator has started speaking a press is refused, so her answer is not cut off; a press is not one of her own repeats. Elsewhere a repeat on request starts her own repeats over (20s, twice) from its end. `repeat/set` with nothing repeatable, or while the operator speaks, is refused on `game/error`.

**Short prompts** (Rev 55). She says each prompt in full the first two times it comes up, counted from Start or from Tutor chosen mid-game, prompt by prompt: a jack or a number in it does not make another prompt, so `ring-front` to room 403 and to the Lobby count together, while `dial-operator` counts apart from `dial`. Her own repeats, Repeat Help and More Help do not count. From the third time, a prompt with a short form under script.yml's `tutor: brief:` is said short — "Rear cord into the lighted jack, then push the near switch away from you." — and one without is said in full. Once she has finished a short prompt and the game waits on the player, More Help — the deck's key 8, as in the introduction — says the full line, at once. It is offered for as long as the short line could be repeated, and the game program publishes the full line's key on `game/tutor/more` while it is, `""` otherwise. After the press the full line is the one Repeat Help repeats, and More Help is not offered again until her next short prompt. `more/set` outside the introduction with no short prompt waiting is refused on `game/error`. Short forms may be given for every prompt but the introduction and the three said before the operator speaks (`say`, `greet`, `respond`).

**One call at a time.** No call is dealt while one is in progress, an `after:` scene is waiting, she is introducing the board, or the cords of the last call are still up. Next Call is refused on `game/error` while that holds, except during the introduction, which it ends. The automatic schedule waits for all of it, as listen pacing waits for an empty board (§4.2), then runs its gap.

**The first calls** (Rev 30). A game started in tutor mode deals one call of each kind first: between rooms, from a room out to a number, in from outside to a room, and to the operator, in the order of the groups under script.yml's `tutor: lessons:`. Each group lists suitable scenes of one kind — short, without `wait:` lines or a following `after:` scene, though the loader insists only on one kind, active, and not itself an `after:` scene. At Start the game picks one scene from each group at random, from the game's seed apart from the deck's shuffle, so a restart picks again and a replay picks the same; the picks go in the log. Each is taken out of the deck as a chosen scene is (§4.8), and a chosen scene still comes before them. A pick that the circuits built cannot play is left out of its group before the choice (§6.5), and an emptied group is skipped. After the last, the deck deals as usual. Choosing another pacing drops the rest; choosing Tutor mid-game deals none.

**Nothing fails for being slow.** The answer and connect timeouts are lifted for calls dealt in tutor mode, and the call slots show no deadline (§6.1). A wrong jack or a wrong number is no more a failure than in any game (§5); she does not say it is wrong, but her prompt comes round again. A call can still fail by being cut off. The tallies count as in any game, and the game log records each change of pacing.

**Her lines** (script.yml `tutor:`). Each key is one line, rendered as `tutor.<key>`. Three keys are templates rendered once for every value they take: `ring-front` and `ring-rear` for each jack a station is cabled to (`{jack}`, "room 403" for a numbered jack, else its label), named for the station, `tutor.ring-front-room403`, so moving a label to another jack changes no file (Rev 38), `dial` for each outside line but the operator (`{number}`, as above), and `say` for each operator line (`{line}`). A whole sentence for each, not a phrase spliced into a sentence at play time, so each is spoken as one. A short form under `brief:` (Rev 55) is expanded the same way and rendered as `brief.<key>`, `brief.ring-front-room403`, since `tutor.brief-…` would pass the 31 characters a name may have. Her voice is designed and chosen as any cast member's (`tts/aws/design --only tutor`, `tts/audition`, `tts/choose --only tutor`); her lines are rendered and band-limited with the rest.

## 4.10 A Scenario After the Tenth Call

Rev 39. A scene marked `after_handled: <n>` is the first call of a scenario, and its `mode: concurrent` followers (§4.4) are the rest. It is never in the deck. Once `n` calls have been handled in the game (§5, success plus fail), the next call dealt — by Next Call or by the automatic schedule — is that scene, if its lines and people are free, else the call after. It is dealt once a game. A chosen scene (§4.8) still comes first.

It is dealt in manual and automatic pacing only: never in tutor mode, which is one call at a time (§4.9), nor in listen, where calls never overlap (§4.2). A game that changes to one of those holds it back until it changes again. Since the tutor never hears a scenario, she has no Say line (§4.9) for an operator line that only a scenario uses.

**Chosen from the page** (Rev 40). A scenario is in `game/scenes`, so it can be chosen as the next scene (§4.8) to show it. Chosen, it is dealt in manual, automatic and listen pacing, never in tutor mode, and only on a clear board: no call in progress and no `after:` scene waiting to start. It waits for Next Call in manual pacing, and for the schedule in automatic, as any chosen scene does (Rev 64; Rev 41 to Rev 63 started it by itself on a clear board). A choice made with no game running is the first call of the next game. Until the board clears nothing else is dealt, and Next Call is refused on `game/error`, "waiting for the board to clear". Once dealt, its followers start on their own timers, in any pacing. A chosen scenario counts as its once-a-game play (Rev 49): the deal after `n` calls does not come after it. It can still be chosen again.

**While the scenario is on the board** — any of its calls in progress or any of its scenes waiting to start — the automatic schedule waits, as listen waits for an empty board, and runs its gap from when the last of them has ended. Next Call still deals in manual pacing.

`panic` is the first, at the tenth call: Martha the dog loose in the hotel, a complaint from every guest room but hers, from the lobby and from the restaurant, two to five seconds apart, ending with Martha calling from her own room.

## 4.11 A Station Found Engaged

Rev 39. A call from a room to a room may carry `if_busy:`, a list of caller lines like a busy call's conversation (§4.6), each played after the operator has spoken. It is for a station many want at once — the front desk in a scenario.

The called station is **engaged** if the game has it off-hook in another call: the room is calling, or has answered. If it is engaged when the request has played, or becomes engaged before the operator rings it, the call is found engaged. It is then **connected** (§4.3), its stage is `busy` (§6.1), and the `if_busy:` lines play, each after she has spoken — "I'm sorry, the front desk is busy" — and the caller hangs up. The game does not answer a ring on an engaged station. Otherwise the call goes as any call between rooms, and `if_busy:` is not heard.

For dealing (§4.4), a scene with `if_busy:` does not hold its called line or its called person, and is not held back by them; once dealt, its call holds them as any call does. So several guests may ask for the front desk while it is talking, and the operator tells each of them to try later.

`operator:` may name what she says before each line, as in a busy call; `closing:` is not allowed there. The lines are utterances of the scene, rendered as any other.

## 4.5 Not Yet: Calls Before Connection

Mark wants, later, a mode where a new call can arrive before the operator has connected the current one — the real pressure of a busy board. The likely form is a fixed interval, a new call every `n` seconds from the start of the last, bounded by the eight slots. It is one more value on `game/pace` and uses the same `gap`, `ramp`, `floor` and `jitter`. Not specified until it is wanted. A scenario (§4.10, Rev 39) is the one place a game asks it of the operator now.

## 4.6 Lines That Wait for the Operator, and Lines by Someone Else

Two keys on a conversation line (Rev 19):

- **`wait: true`** — the line plays only after the operator has spoken on that line's side of the call and stopped: a listen on the called circuit for a `called:` line, on the calling circuit for a `caller:` line, as in the calls to the operator. If she does not speak within the speak timeout, the call fails as `timeout` (§5). It is refused in a call to the operator and in a `busy: true` scene, where every line waits already.
- **`person: <cast member>`** — the line is spoken by that person rather than by the scene's party on that side. It plays on the same circuit; only the voice changes.
- **`pause: <seconds>`** (Rev 20) — silence before the line, up to 30s.
- **`ringback: <seconds>`** (Rev 20) — ringback tone on the trunk before the line, up to 30s, stopped as the line starts. Only on a line spoken on a trunk: a `called:` line of a call to an outside line, or a `caller:` line of a call from one (Rev 21).

A line's own lead-in runs in that order: the wait, then the pause, then the ringback, then the line. A cord pulled during any of them cuts the call off, as during speech (§5).

The long-distance call is the case they were made for. The hotel operator dials 0 on a trunk; the local operator (`called.person`) answers, "Operator"; the hotel operator asks for long distance; the next line, marked `wait: true` and `person:` the long-distance operator, answers "Long distance", and the guest talks to her. The party she rings can speak on the trunk too, with a `person:` of their own. So can each operator on the route: she asks the rate operator for the route and the charge, then rings through each toll center on it, each answering with its town's name after a `pause:`, and the party answers after a `ringback:`.

**Time and charges** (Rev 24). When a long-distance call a guest placed has ended, the long-distance operator rings the hotel to report what it cost: a call to the operator rung in on a trunk (§4.3), an `after:` of the call it bills. Its request is the whole of it — the room, the time and the charge — and it has no conversation, so the far end hangs up as soon as she has said it, whether or not the hotel operator was ready to write it down. It is not repeated. Collect calls, and calls placed from outside to a guest, have none.

## 4.7 What the Operator Says

The player speaks for the hotel operator, and the game only listens for her. script.yml still says what she is expected to say (Rev 22), for recordings of whole scenes (`tts/scenes --batch`) and as a prompt:

- **`operator_lines:`**, at the top level — stock lines by name, each with an `id:` and `text:`. The TTS run renders them in `hotel_operator`'s voice as `operator.<id>`, so no scene may be called `operator`.
- **`operator: <name>`**, or **`operator:`** with an `id:` and `text:`, on the request or a conversation line — what she says just before that line. The inline form is one of the scene's utterances, `<scene>.<id>`, its id unique in the scene and permanent like any other.

- **`closing:`**, on a scene, in either form — what she says after the last line, before the caller hangs up. Only in a call to the operator or a busy call: in any other she has left the line by the end. The game waits for her to say it (Rev 47) — a listen on the caller's line, with the tutor's "Say:" prompt in tutor mode — and the caller hangs up after; a closing not said within the speak timeout, or cut short by her pulling the cord, is let go and the call still succeeds.

`operator:` is allowed only where the game waits for her to speak: the request, a `wait: true` line, and every line of a call to the operator or a busy call (§4.6). Both are optional. The game program never plays these lines and never needs their wavs.

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
| `cut off` | A cord was pulled during the conversation — the calling or called line's `peer` went empty before the scene's end, and stayed empty for a second (Rev 45). Or, before the call was connected, the caller was left alone and hung up: the operator not on its line, the line patched to nothing, and no trunk up — for a trunk caller its own, for a station any — for 10s, or 5s once a wrong number has been dialled for the call (Rev 48; 20s at Rev 46). |
| `timeout` | The operator did not speak when a line was waiting for them (calls to the operator, busy scenes, and a `wait:` line, §4.6). |
| `misdialled` | The operator dialled the number with too many digits — a digit more within 3s of the last it needs — or too few, stopping 10s short of it (Rev 56), or nothing, 15s after taking the trunk, outside tutor mode (Rev 60). The trunk gets reorder, the fast busy, until she releases it, and the call fails then. |

Timeouts are the game program's configuration, not the page's, at Rev 1: 60s to answer, 90s to connect after the request has played, 30s for the operator to speak. They are starting values for play-testing.

A wrong connection is logged but is not a failure on its own. From Rev 60 a wrong room rung answers, "Hello?", the caller says it is not who they asked for, and it hangs up; a right room rung on a cord not patched to the caller says "Hello?" after 8s and hangs up after 8s more; a party waiting for her to speak says "Hello? Operator?" after 6s of silence; and a trunk taken and not dialled for 15s gets reorder and fails as `misdialled` (§1.60). An operator who plugs the wrong jack and corrects it within the connect timeout has made the call. A wrong number of the right length gets busy tone on the trunk until she hangs it up (Rev 46), and she may redial; one too long or too short is `misdialled` (Rev 56). The game takes a number as dialled 3s after its last digit, so as to hear a digit too many; a fresh seizure gets dial tone again, a second after it, as on every seizure for a call out. Whether a wrong party answering should end the call is open (§10).

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

- `signalling` — the calling station is off-hook, or the incoming trunk has been rung (one short burst, Rev 28); waiting for the operator.
- `request` — the operator has answered; the request is playing.
- `routing` — waiting for the operator to ring a station or take a trunk.
- `dialling` — the operator has seized a trunk; digits are arriving. Dial tone is on the trunk from a second after the seizure (Rev 46; half a second in its first form) to the first digit, and again on each fresh seizure if she hangs up and tries again (Rev 42).
- `ringing` — the called station is ringing, or ringback is on the trunk.
- `busy` — busy tone is on the trunk, or the called station is found engaged (§4.11, Rev 39); waiting for the operator to go back to the caller.
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
        guest: "Mr. Earl Dobbs"   # who is staying there; left out if nobody is
    -   jack: 24
        label: "465"        # labelled on the board, nothing cabled: no station:
```

(Illustrative. The real assignments are Mark's.) A station entry carries `number:` and nothing about the board. Trunk circuit n is cabled to trunk jack n for n = 1–8, fixed, and trunk jacks 9 and 10 carry nothing. No trunk jack has a label. A station jack that `jacks:` does not list has no circuit and no label. `guest:` is for the operator's guest list card and the game does not read it (Rev 23).

The script.yml loader rejects the file, and the game program refuses to start, if:

- `jacks:` is missing or empty, or an item has a key other than `jack:`, `label:`, `station:` and `guest:`;
- an item's `jack:` is not an integer from 1 to 30, or is the same as another item's;
- an item lacks `label:`, or its label is empty, or it has a `guest:` that is empty (Rev 23);
- an item's `station:` is not a station entry, or names a station another item already names;
- a station entry is named by no item in `jacks:`, or carries any key but `number:` — a file still in Rev 7's form, with `switchboard:` and `label:` on its stations, fails with a message saying where they went, rather than drawing a board with no labels;
- a station's `number:` is outside 1–22, or the same number as another entry (the loader's existing check);
- a scene lacks `active:`, or its value is not `true` or `false`, or an active scene's `after:` names an inactive one (Rev 14).

The loader is the one `tts_task.md` §3.1 specifies, which the game program imports. These checks go into it, so the TTS run and the game both see them.

A station circuit that no entry names is not on any jack as far as the game knows. It has no tile, and a ring or hook on it goes in the log as a stray. A station entry that no scene uses is still drawn, so a stray ring on it is seen.

The game program reads wavs for active scenes only, and refuses to start if one is missing. An inactive scene's wavs are not looked for.

The game program publishes the map retained under `board/` (`mqtt.md` §6.1): each jack's label, and the circuit it carries or empty. A labelled jack with nothing cabled has a label and an empty circuit. The page builds the board from those topics alone. A change to script.yml takes effect when the game program restarts.

Recabling a station circuit to a different jack moves its `station:` from one item in `jacks:` to another. The labels stay with the jacks, and nothing else changes.

## 6.5 The Circuits Fitted

Rev 25. The switchboard is being built a board at a time, so the game program is told how many circuits exist: `stations` and `trunks` in its configuration file, each overridden by `--stations` and `--trunks` on its command line. Stations are the first `stations` of 1–22 and trunks the first `trunks` of 1–8; the defaults are all of them. **Out of service** (Rev 36): a fitted trunk listed in the configuration file's `[out_of_service.trunks]` table, by number with the reason as text, is never rung in on; the game picks only from the rest, and logs each one listed at start. A call out goes on any trunk the operator takes, since the faults so far — a ring relay that does not latch, a lamp that does not light — matter only to a call rung in. A fitted station listed in `[out_of_service.stations]` (Rev 43), the same way, is in no call at all: a scene calling from it or to it is left out, as a scene on an unfitted station is, with its `after:` chain and its place in the tutor's lessons, and each one listed is logged at start. A scene is left out of the game if its calling or called line is a station numbered above `stations`, or if it needs an outside line and `trunks` is 0; an `after:` scene following one that is left out is left out as well, down the chain. Calls ring in and go out on trunks 1 to `trunks` only. The game program logs how many scenes it left out and why when it starts, publishes `game/stations` and `game/trunks`, and refuses a diagnostic on a circuit that is not fitted (§7.5).

## 6.4 The Audience Loudspeaker

The loudspeaker carries one receive channel, chosen by the game program with `audio/monitor/source/set` (audio.md §10.3). New at Rev 6. The game program points it at the calling line of the call the operator most recently answered, and leaves it there until she answers another.

**When.** The operator answers a call when its calling circuit's `op` goes on while the call is in `signalling`: that is the event that takes the call out of `signalling` (§6.1). At that moment the game program publishes `monitor/source/set` with the calling circuit's id. For a call from a station that is the station, such as `station/11`. For a call from outside it is the trunk that rang in, such as `trunk/3`. It does not change the source at any other point in the call. It does not change it when the operator bridges onto a call already past `signalling`, to listen in or to go back to a caller, since that is not an answer.

**Why at the answer.** Before the answer the calling line carries nothing worth hearing. A calling station is off-hook and silent. A calling trunk has been rung, and its ring relay put a click on its channel at the start and end of the burst (trunk §8.1.1; one short burst from Rev 28, a click at every cadence edge before). Waiting for the answer also keeps the audience on the current conversation until the operator actually leaves it for the next caller. Mark's first proposal switched at the start of the call. He changed it to the answer on 2026-09-24 for these reasons.

**What the audience hears.** The calling line's receive channel carries the caller's side at full strength, since the interface has no hybrid (station §8.4). It carries the operator while she is bridged to the line, and the called party once the cord connects them. So one source carries the request, the operator's reply and the conversation. A call to the operator, and a busy scene where the operator goes back to the caller, are heard the same way. An outgoing call's ringback and busy tone reach the caller through the cord, and the audience hears them when the caller would.

**Which call.** Only the most recent answer counts. In auto pacing the next call can arrive while the current one is talking (§4.2); in listen it cannot. When the operator answers it, the audience leaves the current conversation for the new request. An `after:` scene is a call like any other and moves the loudspeaker when it is answered.

**Start and stop.** When a game starts, and when it stops for any reason (§3), the game program publishes `monitor/source/set` `"tap"`. A monitor diagnostic moves it too, and ends when anything else moves it (§7.5, Rev 25). Between games the loudspeaker carries the operator tap as it always has. The audio program also returns to the tap by itself if it loses the game program (audio.md §13.2).

**What the game program does not do.** It does not set the monitor's gain, which is a bench and installation setting, and it does not turn the monitor on or off. It publishes a new source only on an answer, a start or a stop, and does not wait for the echo. The page shows the echo (§7.1).

The log records each move as `monitor: <calling line>` against the call's number, using script.yml's line name, as the other call events do.

## 6.6 The Ring Cue

Rev 51. While any station reports ring — `station/<n>/ring` `"on"`, ring voltage arriving from the switchboard (mqtt.md §4) — the audience loudspeaker plays ringback, so the player and the room hear the operator ringing. It starts at the first station's ring and stops when the last one's ends, so it follows her ringing key; it is steady, with no cadence. It sounds whether or not a game runs, and whichever station she rings, the right one or not.

It is a file on the monitor (audio.md §10.4), `cue.ringback.wav` in the wav directory, rendered by `tts/cue`: the period ringback of audio.md §8.2, 420Hz modulated by 40Hz, 60s long, at −28dBFS RMS by default, a few dB under the speech files, since the monitor's one file trim sets both. A cue that runs to its end while ring continues starts again.

**The tutor first.** The monitor plays one file at a time, and that file is otherwise the tutor's voice (§4.9). The cue does not start while she speaks; it starts as soon as the monitor is free, which is usually at once, because her prompt to ring is cut short by the ring it asks for. If she begins during the cue her line replaces it, and when ring ends the cue is stopped only if it is still what the monitor plays.

**Off.** `ring_cue = false` in the configuration turns it off. The game program also leaves it off, with a warning in its log, if the file is not in its wav directory at start, and gives it up until restart if the audio program reports it `missing`.

# 7. The Page

## 7.5 Diagnostics

Rev 25. Tests of one circuit at a time, from the page, for bring-up and fault-finding. Each is a toggle: a tap starts it, and a second tap on the same command stops it. The page publishes `game/diag/<target>/<test>/set` `"on"` or `"off"`, where `<target>` is `station/<n>`, `trunk/<n>` or `tap`; the game program does the work, since only it commands the hardware (mqtt.md §6), and echoes each test's state on `game/diag/<target>/<test>`.

| **Test** | **On** | **Where** |
| --- | --- | --- |
| `hook` | the station goes off-hook (`hook/set`) and stays so | a station's panel, on its `hook` row |
| `ring` | the trunk rings in the standard cadence, 2s on and 4s off (`ring/set`); it stops when the trunk is seized, and after the controller's 30s ring limit (control.md §8) | a trunk's panel, on its `ring` row |
| `tone` | the 1kHz test tone on the circuit's output channel (`audio/test/<ch>/set`) | stations, trunks and the tap |
| `voice` | speech on the circuit: utterances from the script chosen at random, one after another, each finishing before the next | stations, trunks and the tap |
| `monitor` | the loudspeaker is fed from the circuit's receive channel (`audio/monitor/source/set`) | stations, trunks and the tap |

**Together.** `tone` and `voice` exclude each other on one target: starting either stops the other. One `monitor` runs at a time: starting it on one target ends it on any other, and anything else that moves the loudspeaker — the operator answering a call (§6.4), a game starting or stopping — ends it too. Ending a monitor test returns the loudspeaker to the tap. `hook`, `ring`, `tone` and `voice` on different targets run side by side.

**With a game.** Tests run whether or not a game is running. A test on a circuit that is in a call, or that the call's slot has taken, is refused on `game/error`, and a circuit under test is busy for dealing (§4.4), so no scene is dealt onto it and no call takes that trunk. The tap belongs to no call, so its tests are always allowed; the operator hears them. Stop ends every test (§3), as does the game program losing a client or restarting.

**Not fitted.** A test on a circuit beyond `stations` or `trunks` (§6.5) is refused on `game/error`, and the page does not offer it.

## 7.6 Board Sweeps

Rev 50. A check of the cabling, with no game running, from the page's Tools, under Diagnostics: `trunks` and `stations`, a tap to start one and a tap on the same button while it runs to stop it, the button filled while its sweep runs and dimmed while a game does (Rev 61); and from the Stream Deck (§7.4), key 5 pressed twice within 0.5s for the trunks and key 6 for the stations; a single press of the running sweep's own key stops it, as does the other key pressed twice (Rev 50 to Rev 60, and again from Rev 62). `game/sweep/set` `"trunks"` or `"stations"` starts one, and `"off"` stops it; the game program echoes the sweep running on `game/sweep`, `""` when none is.

- **Trunks.** Each fitted trunk in turn, 1 to `trunks`, gets one short ring (`shortring/set`, control.md §8.4), and the next follows 2s after the 1s burst ends. Each trunk lamp that works latches and stays lit until a cord goes in and out of its jack.
- **Stations.** Each station cabled to a jack, in jack order — the rows from the top, 21–30, 11–20, 1–10, each left to right (§7.1) — goes off-hook (`hook/set`) for 1s, and the next follows 2s after it goes back on-hook.

Out-of-service circuits (§6.5) are swept with the rest, since a sweep is how one is found to work again; the log line says it is out of service. A circuit under a diagnostic (§7.5) is passed over, so a sweep never releases a hook the page is holding. Each step goes on the game log (§6.2), `test stations: jack 23 (463), station 11 off-hook`, so the page shows where the sweep has got to, and the circuit's own echoes light its tile.

A sweep is refused on `game/error` while a game runs. Start ends one before the game starts, and so do Stop and anything else that stops a game (§3); the circuit under way is put back — the station on-hook, the burst cancelled. A new sweep ends one already running.

## 7.7 Recording and Playing Back the Loudspeaker

Rev 61. Two sections of Tools (§7.1), for keeping what the audience heard and hearing it again.

**Record.** A tap on `record` closes Tools, as choosing a recording to play does, and publishes `game/record/set` `"on"`, which the game program passes to the audio program as `audio/record/set`, refused on `game/error` while the audio program is offline. The audio program records exactly what goes to the loudspeaker into `/srv/sbgame/recordings/<YYYY-MM-DD-HH-MM-SS>.wav`, named for the host's local time at the start, and when it stops makes an MP3 beside it, keeping both (audio.md §10.6). While `audio/record` names a file, the button reads `recording`, filled, and a tap on it publishes `"off"`; and in the top bar, to the right of Tools, stand a red dot and the time recorded, the dot lit for the first half of each second recorded and dark for the second, so it lights as the count goes up, counted from the time in the name against the host's clock (§7.2); they are there only while recording. A tap on them publishes `"off"`. `audio/record` `"failed"` — no file could be opened — shows as `record (failed)` until the next try. A recording runs with or without a game; Start and Stop leave it alone, and the audio program stops one itself after four hours.

**Playback.** A tap on `play…` opens a list of the ten newest recordings, newest first, from `audio/recordings`, each as its date and time with its length. A tap on one publishes `game/playback/set` with its name, which the game program passes on as `audio/playback/set`; the audio program plays it on the loudspeaker in place of the monitor, at the level it was recorded (audio.md §10.7), and echoes the name on `audio/playback`, and `""` when it ends. While it plays, the button reads `playing`, filled, and a tap on it publishes `"stop"`; and in the top bar, to the right of Tools and of a recording's dot, stand a play triangle and the time played, there only while it plays — the length is in the list, and the bar has no room for both at the iPad's width; a tap on them publishes `"stop"`. Refused on `game/error` while a game runs, since it would play over the calls, and `play…` is dimmed then; Start stops one that is playing. A name that cannot be played comes back `"missing"`, shown as `play… (missing)`.

One at a time: `record` is dimmed and does nothing while a recording plays back, and `play…` while one is being made, and the game program refuses `record/set` `"on"` during a playback and `playback/set` with a name during a recording, on `game/error`. Stopping either is always accepted.

## 7.1 Layout

For an iPad in landscape, 1024 CSS pixels wide or more. Touch targets 44px or larger. Four areas: the top bar across the page; the board under it, across the whole width; then calls, with the log under them, beside a narrow health column (Rev 11):

**Top bar**, always visible. A Controls switch beside the connection lamps shows or hides its buttons — Start, Stop, the pacing, Next Call and the steppers' − and + — on this iPad (Rev 13). The Stream Deck carries the same controls (§7.4). With the buttons hidden the values stay — the four values, `gap_now`, the countdown and the tallies — and one line reads what the hidden buttons showed: Running or Stopped, and Manual, Automatic or Listen. The setting belongs to the iPad, kept in the browser's storage, not on the bus. An iPad with no setting, or one whose storage was cleared, shows the buttons, so it can always run the game.

- Connection: broker connected or not; game program online or not.
- Start and Stop. Stop needs a second tap within 3s, because it ends a player's game.
- Pacing: Manual | Automatic | Listen (Rev 16).
- Next Call: large in manual pacing, small in automatic (auto or listen). A long press, held about half a second, opens a scrolling list of the scenes to choose the next one from (§4.8, Rev 25); a chosen scene shows under the button until it is dealt.
- Tools (Rev 25): a panel of diagnostics not tied to a jack. Its one section at Rev 25 is the operator tap: `tone`, `voice` and `monitor` (§7.5). From Rev 61 three more follow it: Diagnostics, the board sweeps (§7.6); Record; and Playback (§7.7). A long press, about half a second, shows a key to the lamps instead: each state in the table below with its lamp as the board draws it (Rev 53).
- Help (Rev 54): a long press on a pacing button or a stepper explains it, beside the button. Escape, or a tap elsewhere, closes it and every other popup.
- `gap`, `ramp`, `floor`, `jitter`, each with − and + steppers (5s, 1s, 1s, 10% steps; `jitter` Rev 12). Shown only in auto pacing, with `gap_now` and the countdown to `next_at` beside them. In listen, one stepper, `pause` (1s steps), and the countdown take their place (Rev 17). The countdown reads "waiting" while a game runs and nothing is scheduled, and "–" when no game runs (Rev 18).
- Tallies: started, handled, success, fail, success percentage.

**Board.** Laid out as the switchboard is (Rev 5): station jacks in three rows of ten, and one row of ten trunk jacks below them. Rows run 21–30, 11–20, 1–10 from the top, each left to right, as the 551 is numbered (Rev 37). Each tile is one jack, from the `board/` topics (§6.3).

A tile shows little:

- the jack's **label**, large, and its jack number, small. Every label on the board is set at one size, the largest at which the longest still fits its tile, so the board reads as one designation strip; a label is never clipped, and words are not broken (Rev 11);
- **one state**, as a colour, the most urgent first:

| **State** | **Station jack** | **Trunk jack** |
| --- | --- | --- |
| fault | `peer` `"ambiguous"` or `"deaf"` for a second (Rev 52), `play` `"missing"` | the same, or `fault` set |
| ringing | `ring` on, flashing | `ring` on, flashing with the cadence |
| calling | `hook` on, `op` off and `peer` empty: the line lamp is lit, nobody has answered | — |
| connected | `peer` set, in a colour shared by both ends of the pair | `peer` set, the same way |
| operator on | `op` on | `op` on |
| busy | `hook` on | `seize` on |
| idle | none of the above | none of the above |

- the far end's **label**, when `peer` is set, taken from the board map rather than shown as a circuit number.

Tapping a tile opens a panel with everything about that jack: its circuit, `hook` or `seize`, `ring`, `peer`, `op`, `play`, `tone`, `listen`, `fault`, the digits of a call on a trunk, and the call slot using it. Tapping elsewhere closes it. Mark expects the tile to need more or less than this once it is on the iPad.

The panel's commands (Rev 25, §7.5), for a jack with a circuit that is fitted (§6.5): on a station, its `hook` row, and `tone`, `voice` and `monitor`; on a trunk, its `ring` row, and the same three. A row that is also a command is coloured as one — the command colour marks a tappable row, and it is lit while that test is on — so the rows that only show a value read differently from those that act. The commands are controls, hidden with the Controls switch like the others.

A station jack with a label and no circuit — listed in `jacks:` with no `station:` — is drawn as a working jack at rest: label, jack number and an unlit lamp, the same as an idle cabled jack (Rev 11). The operator is shown the board as it is built, not which of its jacks the game has wired. A jack with neither a label nor a circuit — a station jack `jacks:` does not list, and trunk jacks 9 and 10 — is drawn as an empty outline with its jack number, so the board keeps its shape (Rev 7). Trunk tiles show the jack number alone, since trunk jacks have no labels.

**Calls.** One row per occupied slot: call number, scene, from → to, trunk, stage, time in stage, time to deadline. From and to are script.yml's line names. The trunk is shown by its jack number.

**Health and log.** Controller: `status`, seconds since the last `esp_heartbeat`, `i2c`, and `firmware` (Rev 27). Audio: `audio_status`, `optone`, `monitor`, and the monitor's `source` — `tap`, or the jack label of the circuit it names, from the board map (Rev 6). Game: `game_status`, seconds since the last `game_heartbeat`. Then the log, in a monospaced column, and the last `game/error` as a line that clears on the next accepted command.

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
| 3 Pacing | "Tutor", "Manual", "Auto" and "Listen", one per line, the echoed `pace` lit (Rev 16; Tutor from Rev 32) | `pace/set` with the next of the four in that order, wrapping from Listen to Tutor. Absolute; counted from the last press while its echo is outstanding, and from the echo once it arrives or 1s after the press. |
| 4 Next Call | "Next" over "Call", lit violet while a game runs (Rev 18), flashing once a second while `game/tutor/waiting` is `"more"` or `"next"` and she is not speaking (§4.9, Rev 33); in automatic pacing, auto or listen, the countdown to `next_at` in place of "Call", or "waiting" while none is scheduled | `next/set`, at QoS 0, guarded as §4.1: dark from the press until `started` changes, `game/error` is published, or 3s pass. |
| 5 Calls | `started` and in progress; "Sweep" over "trunks", lit teal, while that sweep runs, from the deck or the page (Rev 62); "Switchboard" over "reset", lit red, while `ctl/power_cut` is `"on"` (Rev 63) | nothing. Pressed twice within 0.5s with no game running, `sweep/set` `"trunks"`; while the trunk sweep runs a single press, `"off"`, and while the station sweep runs two (§7.6; Rev 50, and again from Rev 62; Rev 61 had none); held 2s with no game and no sweep running, `power_cut/set` `"on"`: the switchboard reset below (Rev 63) |
| 6 Score | success and fail; "Sweep" over "stations", lit teal, while that sweep runs, from the deck or the page (Rev 62) | nothing. Pressed twice within 0.5s with no game running, `sweep/set` `"stations"`; while the station sweep runs a single press, `"off"`, and while the trunk sweep runs two (§7.6; Rev 50, and again from Rev 62; Rev 61 had none) |
| 7 Percent | success percentage of handled. While the tutor has a line to repeat (§4.9, Rev 34), "Repeat" over "Help" instead, lit teal (amber before Rev 62), and dark while she speaks | nothing. While she has a line to repeat, `repeat/set` at QoS 0, then dark for 1s or until her voice starts, so a double press does not say it twice. At Rev 31 only, More Help during the tutor's introduction |
| 8 Health | a lamp each for the game program, the controller and the audio program, red when offline or its heartbeat is 2.5s late; the whole key red while `game/error` is set. While the tutor introduces the board (§4.9, Rev 32), "More" over "Help" instead, lit teal (amber before Rev 62) while a further part remains, and flashing once a second while `game/tutor/waiting` is `"more"` (Rev 33). The same while `game/tutor/more` is set, a short prompt waiting (Rev 55), dark while she speaks | shows the last `game/error` on the strip again. While the tutor introduces the board, `more/set` at QoS 0, guarded as Next Call is: dark from the press until `game/tutor/intro` changes, or 3s pass. On a short prompt (Rev 55), the same, until `game/tutor/more` changes. Rev 29 to Rev 31 key 8 was the tutor switch. |

**Dials**, left to right: `gap`, `ramp`, `floor`, `jitter`. One detent is one step of the page's stepper: 5s, 1s, 1s and 10%. A push does nothing at Rev 13.

**Switchboard reset** (Rev 63). Key 5 held for 2s, with no game and no sweep running, publishes `game/power_cut/set` `"on"`, once per hold, at the 2s mark rather than on release, so the operator knows when to let go. From the press until then the key reads "Hold to" over "reset", with a bar filling across its foot; let go sooner and nothing is sent. A hold is one press to the sweep's double press: a second press within 0.5s of the first still starts the trunk sweep, and the hold then counts for nothing. While a sweep runs the key behaves as the table says and a hold does nothing more. While `ctl/power_cut` reads `"on"` the key reads "Switchboard" over "reset", lit red, whoever sent it. While a game runs, or the game program is offline, a hold does nothing and the key does not show it, as the double press does nothing then; the game program refuses `game/power_cut/set` while a game runs in any case.

**Turning a dial.** The dial reports steps and the command is absolute, so the program keeps a target. The first detent starts the target at the echoed value; each detent adds a step to the target, clamped to the §4.3 range, and publishes it. The target is held while detents keep coming and is dropped when the echo equals it or 1s after the last detent, so a fast turn loses no steps and a value the game clamped differently — `floor` above `gap` — settles on the echo. A dial whose value has not been echoed yet does nothing.

**Errors.** When `game/error` changes to a non-empty value, the strip shows it across its whole width for 5s and then returns to the dials. Key 8 stays red until the error clears, and a press on it shows the error again (not at Rev 29 to Rev 31). A touch on the strip dismisses it.

**Staleness.** With the broker lost, every key is greyed and the strip says so. With the game program offline or its heartbeat 2.5s late, keys 1–7 and the dials are greyed and do nothing; key 8 still shows the three clients, as it did through Rev 28. A press that does nothing gives no other sign; the greyed key is the sign.

**No deck.** The program runs whether or not a deck is plugged in. It looks for one every 2s, and draws a deck found or replugged from the state it already holds. It drives the first Stream Deck+ it finds and ignores any other. On a clean stop it clears the deck, so it is blank rather than showing controls that no longer work. A crash leaves the last images on the keys; systemd restarts the program within 5s, and the first thing it does is redraw them.

**Brightness** is an option of the program, 60% by default. The deck has no screensaver in this program.

# 8. What the Game Program Checks

Every value arriving on `game/+/set` is checked by the game program; the access list keeps the page off hardware topics but does nothing about a bad value on the game's own. A value out of range is clamped and the applied value echoed; a value that is not understood — `run/set` other than `"on"` or `"off"`, `pace/set` other than `"tutor"`, `"manual"`, `"auto"` or `"listen"`, a number that does not parse — is dropped, logged, and reported on `game/error`. Accepted commands are logged with `page:` in front (§6.2). A command from the Stream Deck arrives on the same topic and is logged the same way; the game program cannot tell them apart and does not need to (Rev 13).

# 9. Commissioning

Before step 1: the certificate is issued (`mqtt.md` §9.1), nginx is configured and enabled, the Route 53 A record for `game.kr3am.org` points at the host, and the broker users and the access list are in place — four, and `sbgame-deck` the fifth from Rev 13. The deploy hook no longer has to be run by hand, because nginx reads the certificate from `/etc/letsencrypt/live` directly and the hook only reloads it.

1. Restart Mosquitto and nginx after the §9 changes to `mqtt.md`'s configuration. Mosquitto's log shows two listeners open, MQTT on 1883 and WebSockets on 127.0.0.1:9001; `ss -ltnp` shows nginx on 443. Mosquitto's WebSockets listener is deliberately on loopback: nothing off the host reaches it except through nginx (Rev 10).
2. From another machine on the LAN, `curl https://game.kr3am.org/` returns `index.html` with no certificate error. That checks the name, the certificate and `http_dir` together (Rev 8; `curl http://<host>.local:9001/` through Rev 7).
3. The controller, the audio program and the game program still connect. `allow_anonymous false` refuses any client without credentials; control.md §9.1 and audio.md already use them, but check the usernames against the access list.
4. As `sbgame-web`, publish `sbgame/station/1/hook/set` `on`. Station 1's relay does not move and `hook` does not change: the broker has dropped it silently. Then `sbgame/game/run/set` `on`, which is accepted.
5. Lock the iPad for a minute and unlock it. The page reconnects and shows the full state without a reload.
6. Stop a game with a station off-hook, a trunk ringing and a file playing. Everything releases, and the tallies stay. A trunk's lamp and buzzer, rung in and not answered, go out with the 1s power cut, and the switchboard comes back with no lamp lit (Rev 63). With no game running, hold the deck's key 5 for 2s with a trunk lamp lit: the same.
7. Kill the game program. The page shows it offline within 2.5s and keeps showing the hardware.
8. **Wiring check** (Rev 5). With no game running, put an answering cord into each cabled station jack in turn and ring it. The tile for that jack flashes. If another tile flashes, or none does, the cable and script.yml's `jacks:` disagree about that station (Rev 11; each station's `switchboard:` at Rev 7–10, `wiring.yml` at Rev 5–6). A labelled jack with nothing cabled looks like any other at rest, so a tile that never flashes is not by itself proof of a fault — tap it: its circuit reads none. For trunks, seize each trunk jack in turn: the tile for that jack shows busy. This checks the cabling against the script using only topics that already exist.
9. **The loudspeaker follows the call** (Rev 6). Start a game. The page shows the monitor's source as `tap`. Start a call from a station and answer it: the source changes to that station's label and the audience hears the request. Put the call through and release the operator: the conversation stays on the loudspeaker. Do the same for a call from a trunk, and confirm the source does not change while the trunk is ringing. Stop the game: the source returns to `tap`.
10. **Certificate reload** (Rev 10). Nothing to check. Mosquitto holds no certificate: nginx terminates TLS and rereads the certificate on `systemctl reload`, which starts new workers and lets the old ones finish, so no client is disconnected and no client of Mosquitto is touched at all. Rev 8 and Rev 9 had this step decide between SIGHUP and a 04:00 restart, because whether Mosquitto's libwebsockets listener reloads a certificate on SIGHUP was unconfirmed. Both are withdrawn (`mqtt.md` §9.1). Confirm the renewal path itself instead, without spending an issuance: `sudo certbot renew --dry-run` runs the DNS-01 challenge against staging and the deploy hook, and must report success.
11. **The Stream Deck** (Rev 13). With `sbgame-streamdeck` running and the deck plugged in: the keys draw within 2s. Start and Stop start and stop a game, Stop only on the second press. The pacing key switches the page's pacing. Turn each dial one detent each way and check the page shows the step, then turn `gap` quickly through ten detents and check it moves 50s. Next Call starts one call per press, however fast it is pressed. Stop the game program: keys 1–7 grey within 2.5s and key 8 shows the game red. Unplug the deck and plug it in again: it redraws with the current state. `systemctl stop sbgame-streamdeck`: the deck goes blank. Then hide the page's controls with its Controls switch (§7.1), reload the page, and check they stay hidden and the line reads the game's state.

    Run 2026-09-26 (Rev 15). Passed: the keys drew; Start and Stop, Stop on the second press; the pacing key; each dial one step per detent (`gap` 5s, `ramp` and `floor` 1, `jitter` 10), and eight quick `gap` detents moved it 40s, published in order within a second; with the game program stopped the keys greyed and key 8 went red; replugged, the deck redrew; with `sbgame-streamdeck` stopped it went blank; the page's controls stayed hidden across a reload. A fast turn can carry two detents in one message (`jitter` 100 → 80); the total comes out right. Next Call pressed fast, checked the same day with `sbaudio` running: six presses about 0.4s apart gave six `next/set` and six calls, each a different scene, none doubled or lost. With the audio program offline this could not be checked, since every call fails at once and the game stops (§3).
12. **Tutor mode** (Rev 29; a pacing from Rev 32). With her lines rendered and in `/srv/sbgame/wav`, and the loudspeaker on: choose Tutor on the pacing key. Start a game: she introduces the board a part at a time, key 8 reads More Help and takes her to the next part, and Next Call at any point ends the introduction and deals the first call. Take a call from a room, one in on a trunk, and one out, following her, and check that every step is prompted before it is due and that she never speaks while the page shows a line `listening`. Leave a lamp lit: she says it twice more, 20s apart, then stops. Finish a call and leave a cord in: Next Call is refused and the page's error says why; pull it, and she asks for Next Call. Set the level of her voice against the calls' with `--monitor-file-trim` (audio.md §10.4), with the monitor at the level the room wants for the calls. Choose Manual mid-call: she stops at once and the call goes on.

# 10. Open Items

- **Calls before connection** (§4.5). Deferred by Mark.
- **Wrong party answers.** Whether ringing the wrong station, or dialling a wrong number, ends the call as a failure or only costs time. Rev 1 lets the connect timeout decide. Rev 60 settles it for a wrong room: it answers and hangs up, and the call goes on; it is not a failure, since she can recover (Mark, 2026-10-17). A wrong number, the same: busy tone, and she redials (Rev 46).
- **Timeouts from the page.** The §5 timeouts are configuration at Rev 1. If play-testing wants them changed between players, they become three more `game/…/set` topics.
- **Audience view.** A second page, or a mode of this one, for the room: the tallies large, the calls in progress, nothing diagnostic. Same topics; no host change.
- **Cords drawn as lines** between tiles rather than shown by colour. Only if the colour pairing is hard to read on the iPad.
- **Script names or jack labels.** script.yml's station keys (`room463`) and the board's labels (`463`) name the same thing twice. The calls panel and the log use script names, and the tiles use labels. If that reads badly, the game program can put labels in the call slots instead.
- **The loudspeaker leaving a conversation** (§6.4). In automatic pacing, the operator answering the next call takes the audience away from the current conversation, possibly mid-sentence. The alternative is to stay on a call until its conversation ends and then move to the most recently answered call, at the cost of missing that call's request. Rev 6 moves at each answer. Wants listening with an audience. Rev 16's listen pacing sidesteps it when the conversations matter more than the pressure.
- **Settings across restarts.** Pacing values return to the configuration file's when the game program restarts (§4.3). If that is annoying, the game program can read its own retained values back at start.
- **Dial push** (§7.4). Unused at Rev 13. Candidates: a finer step while held, or back to the configured value — the program does not know the configured values, and the game program would have to publish them.
- **Error on the strip** (§7.4). 5s may be too short to read a long error, or too long to lose the dials during a game. Wants use.
- **Next Call on GPIO36** (`control.md` §11). A third way to publish `next/set`, needing the same guard as the page and the deck.
- **The tutor and a wrong move** (§4.9). She does not say a jack or a number is wrong; her prompt only comes round again. A line per jack for "that is not room 403" would be one more template. Wants play with a new player first.
- **The tutor's voice in the headset.** Rev 29 puts her on the loudspeaker, which the audience hears too. If the room wants her private, the headset needs her kept off the line the operator is bridged to, which the tap cannot do (§4.9).
- **Screen wake lock** (§7.3, Rev 8). Possible now that the page is served over HTTPS: the page would hold a wake lock while `run` is on, and Auto-Lock could stay on. Whether it holds reliably for a Home Screen page on the iPad's iOS version is to be tried before it replaces the Auto-Lock instruction.
