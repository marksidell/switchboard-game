**Switchboard Game**

**Game Control and the Status Page**

*Rev 125. The changes in each revision are in §15.*

# 1. Overview

This document specifies how the game is run: starting and stopping a game, pacing the calls, counting how the operator did, and a status page on an iPad that shows the whole system while it runs. The controls are on an Elgato Stream Deck+ beside the switchboard (§10), and the page becomes a display. It covers three things that are written together:

- **What the game program does** with each control — the meaning of a game, of pacing, of success and failure.
- **The status page** — one HTML page with its script, served by nginx and connected to Mosquitto over MQTT on WebSockets through the same nginx. It has no server of its own and no code on the host beyond the game program's topics.
- **The Stream Deck** — a Stream Deck+ on USB to the host, driven by a small program of its own, `sbgame-streamdeck`, that talks MQTT to the same broker. It carries Start, Stop, the pacing, Next Call and the four pacing values, and shows the tallies and the health of the three clients.

Every topic named here is defined in `mqtt.md` (§6.1 and §6.2), which owns names, payloads, retention and the broker's access list. This document says what the values mean and when they change. It does not repeat the tables.

The page reads the bus directly rather than through the game program. That is the reason for the design: it shows what the controller and the audio program actually report, and it keeps working when the game program is down — which is when it is most needed. The page commands only the game program and the public-address check (`host/public_ip/check/set`), and the broker's access list holds it to that (`mqtt.md` §9).

The Stream Deck program follows the same design for the same reason (§10). It commands the game over the broker as the page does, and displays only what the broker reports.

The game program, the page and the Stream Deck program are written by Claude Code to this document, like `control/control.ino` to `control.md` and `sbaudio` to `audio.md`.

## 1.1 Terms

- **The operator** is the player, "she" throughout. **The tutor** is the voice that teaches her (§7), and is always named.
- **The switchboard**, or **the board**, is the 551 itself. The page's **Board** area is its drawing (§11.1).
- **The deck** is the Stream Deck+ (§10). **The shuffle** is the order the scenes are dealt in (§6.1).
- A **scene** is what script.yml writes; a **call** is one scene being played. **Calls in progress** are those holding a call slot (§3.2).
- **Pacing** is how calls are started: tutor, manual, auto or listen (§5). **Auto** is labelled Automatic on the page. **Scheduled pacing** means auto or listen.
- A **line** is a calling or called party's name in script.yml, a station or an outside name. A **circuit** is the hardware it runs on. `hook`, `seize`, `ring`, `op` and `peer` are what a circuit reports, defined in `mqtt.md`.

# 2. A Game

A game is one player's turn. It begins with `game/run/set` `"on"` and ends with `"off"`.

**Start.** Accepted only while `run` is `"off"`; while running it is ignored. A switchboard switched off from the page (§11.7) is powered first, `ctl/power_cut/set` `"off"`. The tallies are zeroed (§4), the call number restarts at 1, the gap returns to its configured value (§5.4), the scenes are shuffled, or the shuffle goes on if the game stopped only a little while ago (§6.1), the loudspeaker's source is set to the tap (§9.1), and `run` reads `"on"`. In scheduled pacing, auto or listen, the first call starts at once; in manual pacing nothing happens until the page asks for a call. A game is one session in the game program's SQLite log.

**Stop.** Every call in progress is torn down at once: stations on-hook, trunk ring off, every file and tone stopped, every listen cancelled; every `after:` scene that was waiting is dropped; the call slots clear (§3.2); the loudspeaker's source goes back to the tap (§9.1). `run` reads `"off"`. Calls torn down this way are neither successes nor failures (§4). Every diagnostic running is ended too (§11.4), and a board sweep (§11.5), and a chosen next scene is forgotten (§6.4). Last, with the controller online, the switchboard's power is cut for 1s, `ctl/power_cut/set` `"on"`: a trunk rung in holds its lamp and buzzer on the switchboard's own battery until a cord goes in, and only the cut clears it. The deck's reset during a game (§10) is the same cut; the calls ride through it (§4). `run` reads `"off"` without waiting for the cut to end. The tallies stay as they were until the next start, so the player can see the score.

**Left alone**. A running game with nothing from the player for `idle_stop` seconds, 600 by default, stops as if Stop had been pressed, and says so on the log: "game stopped: no activity for 10 min". Start begins a new game. The player's acts are a cord in or out (`peer`, `op`, a trunk's `seize`), a digit, a station rung, and any command from the deck or the page; nothing the game does itself counts, so a game in scheduled pacing dealing calls to an empty room stops too. 0 never stops.

**Losing a client.** If the controller or the audio program goes down during a game — `ctl/status` or `ctl/audio_status` offline, or two missed `esp_heartbeat`s (`mqtt.md` §8) — the game program does what Stop does and logs why, and `run` reads `"off"`. The player is not charged for the calls it abandons. It does not restart the game when the client returns; that is Mark's decision, from the page.

The game program always starts with `run` `"off"`.

# 3. A Call

## 3.1 From First Lamp to Hanging Up

Every call follows the same course, whichever way it comes in. The sections after this one give each step's rules.

1. **Dealt.** The game program picks a scene (§6.1) and gives the call a slot (§3.2). The tallies count it as started (§4).
2. **The caller signals.** A room goes off-hook and its line lamp lights, or a trunk chosen by §3.6 gets one short ring and its lamp lights. An unanswered trunk rings short again every 10s, unless a front cord is already in it.
3. **The operator answers** by plugging a cord into the lit jack and bridging on, which `op` shows. The loudspeaker moves to the caller (§9.1) and the request plays. If she leaves a room before the request has played, the room waits for her as after the request (§3.3, "She may leave before replying"), then asks if she is there and makes its request; a trunk caller is cut off.
4. **She routes the call.** To a room, she rings it with the other cord, and the room answers. To an outside line, she takes a trunk, hears dial tone a second after seizing it, and dials; the far end rings back and answers, or gives busy tone. A wrong move costs time, not the call (§3.5). A call to the operator has no routing: she deals with the caller herself.
5. **Connected.** The routing is done (§3.3), and scheduled pacing takes its timing from here (§5).
6. **The conversation plays**, with any waits for the operator the script asks for (§6.2).
7. **The parties hang up** after the last line (§3.4), and the call counts as a success. A call that ends any other way is a failure, with a reason (§4).

## 3.2 Call Slots

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

- `signalling` — the calling station is off-hook, or the incoming trunk has been rung (one short burst); waiting for the operator.
- `request` — the operator has answered; the request is playing.
- `routing` — waiting for the operator to ring a station or take a trunk.
- `dialling` — the operator has seized a trunk; digits are arriving. Dial tone is on the trunk from a second after the seizure to the first digit, and again on each fresh seizure if she hangs up and tries again.
- `ringing` — the called station is ringing, or ringback is on the trunk.
- `busy` — busy tone is on the trunk, or the called station is found engaged (§6.6); waiting for the operator to go back to the caller. Busy tone plays four bursts, 3.5s, and stops, whether or not her cord is still in the trunk; only then does the game listen for her on the caller's line. Through the cord the tone reaches the caller's line, and the speech detector would take it for her voice and never hear her stop.
- `talking` — the conversation is playing.
- `operator` — a call to the operator; the caller is waiting for the operator to speak.

A slot is free when `scene` is empty. The game program publishes `since` and `deadline` before `stage`, so a page never shows a new stage against the old time; and on a call's end it clears `scene` first, so the page frees the slot before the other values empty.

These stage names are what the page displays. The game program's own state machine may be finer; it maps onto these.

## 3.3 Connected

A call is **connected** at the point where the operator's routing work is done:

| **Scene** | **Connected when** |
| --- | --- |
| To a station, from a station or a trunk | the called station answers — the game takes it off-hook 3s after ring arrives |
| To an outside line | the called party answers on the trunk after ringback |
| To an outside line marked `busy: true` | busy tone starts on the trunk |
| To a station found engaged, in a scene with `if_busy:` | it is found engaged (§6.6) |
| To the operator (no `called:`), from a room or rung in on a trunk | the request has finished playing |

These are the milestones the game program must expose to the scheduler. How it reaches each one — which listens, which timeouts — is the game program's flow and not this document's.

**A call to the operator succeeds once she has replied.** After the request, each of the caller's lines waits for her to speak (§6.2); once she has begun to reply — the speech detector has heard her start, whether or not it has heard her stop — the call counts, whatever happens after. The caller's later lines, a punch line among them, are hers if she stays; if she pulls the cord, the caller hangs up and the call has still succeeded. An operator in a rush says something short and moves on, and nothing told her another line was coming.

**She may leave before replying.** Pulling the cord after the request and before she has replied does not end the call at once. From a room the station is still off-hook, so its lamp lights again, and the caller waits 30s for her alone, as any caller held before it is put through does (§4) — in tutor pacing, as long as it takes. When she comes back on its line, the caller asks "Hello? Operator? Are you there?" (its `nudge` reaction, §3.5) and the call goes on where it was. Not back in 30s, it hangs up and the call is `cut off`. A caller rung in on a trunk has no lamp to light again: her leaving before a reply cuts it off, as before. The same holds in every kind of call between her answer and the end of the request: a room waits, asks if she is there, and makes its request once she has spoken again; a trunk is cut off.

**A busy line or an engaged room is handled once she has told the caller.** After busy tone on a trunk (`busy: true`) or a station found engaged (§6.6), each of the caller's lines waits for her to speak, as above; once she has begun to — the speech detector has heard her start — the call counts, whatever happens after. The caller's reply, "Never mind, I'll try later", is hers if she stays; if she pulls the cord, the caller hangs up and the call has still succeeded. An operator in a rush says the line is busy and moves on.



## 3.4 Hanging Up

After a call's last line, the parties hang up 1.5s later, not at once: the time it takes to put a receiver down. The same after the operator's closing words, or where a call to her has none, and after an engaged caller's last line.

When the call was on a trunk, the far end has gone too. If her cord is still in the trunk 4s after the call ends, the trunk gets reorder, the fast busy, until she takes the cord down, so a line left up after the long-distance operator's charges, or a guest's outside call, is not silent. The log says so. While the trunk is patched to a line — that cord pair used to answer the next caller with its front cord still in the trunk — it is quiet, so the caller is heard, and reorder comes back if it is unpatched again. A new call taking that trunk ends it, and so does Stop.

## 3.5 Wrong Moves

A wrong connection is logged but is not a failure on its own (§4). A wrong room rung answers, "Hello?", the caller says it is not who they asked for, and it hangs up; a right room rung on a cord not patched to the caller says "Hello?" after 8s and hangs up after 8s more; a party waiting for her to speak says "Hello? Operator?" after 6s of silence; and a trunk taken and not dialled for 15s gets reorder and fails as `misdialled` (§15.60). An operator who plugs the wrong jack and corrects it within the connect timeout has made the call. A wrong number of the right length gets busy tone on the trunk until she hangs it up, and she may redial; one too long or too short is `misdialled`. The game takes a number as dialled 3s after its last digit, so as to hear a digit too many; a fresh seizure gets dial tone again, a second after it, as on every seizure for a call out. A trunk already up when a call out begins to route belongs to another call, or is a cord left in, and gets nothing, unless it is patched to this call's caller: she may take the trunk before the caller has finished asking.

A caller she leaves before it is connected, and comes back to with the answering cord alone after 5s or more, says its request again: once she has spoken, or after 6s if she does not. A guest kept waiting does not sit silent, and an operator who has lost track of a call hears what it wanted. The log says "asks again". A shorter absence, such as centring the key before the front cord goes in, does not count. Back after 10s or more, it first asks "Hello? Operator? Are you there?" (its `nudge` reaction).

After a wrong number, her first return to the caller, however short, gets the request again in the same way: she has had to take her cord out of the trunk, and the guest wants to know what happened. Her second, the call still not put through, gets the caller giving up — "Never mind, operator. I'll try again later.", its `giveup` reaction — and hanging up 1.5s later; the call fails as `not connected`. Not in tutor pacing.

## 3.6 Which Trunk a Call Rings In On

Of the trunks fitted, in service, idle — not seized, not ringing and not in a call — and not under test, the one whose `seize` changed longest ago. A trunk just released may still have the operator's cord in its jack.

# 4. Tallies and Failures

Three counts per game, each zeroed at start:

- **`started`** — calls started, including `after:` scenes.
- **`success`** — calls that ran to their scripted end: every utterance played, and the parties hung up as the script ends.
- **`fail`** — calls that ended any other way while the game was running.

The page shows **handled** as `success + fail`, the success percentage of handled, and **in progress** as the count of occupied slots. `started` minus handled minus in progress is the calls abandoned at Stop; the page does not show it.

A failure is logged with its reason:

| **Reason** | **Meaning** |
| --- | --- |
| `no answer` | The operator did not answer the calling line in time. |
| `not connected` | The operator answered but did not connect the call in time — wrong station rung, number not dialled, or nothing done. |
| `cut off` | A cord was pulled during the conversation — the calling or called line's `peer` went empty before the scene's end, and stayed empty for a second. A line that cannot hear — `peer` `"deaf"` or `"ambiguous"` — says nothing about its cord: its last `peer` stands, and a `peer` going empty or `op` going off while it cannot hear, or just as it stops, counts only after a second of hearing again, and at most 5s after it went. A howl on the loudspeaker swamps the pilots, and an operator keyed on two pairs at once makes every line on them hear two others. Not through the switchboard's reset (§2): from `ctl/power_cut` `"on"` until a second after it is `"off"` again, the lines' `peer`, `op` and `seize` stand as they were, and then take their latest values. Or, before the call was connected, the caller was left alone and hung up: the operator not on its line, the line patched to nothing, and no trunk up — for a trunk caller its own, for a station any — for 30s, or 5s once a wrong number has been dialled for the call, counted afresh from the end of the tutor's wrong-cord line if the tutor says one meanwhile (§7.7). Never in tutor pacing (§7). A call to the operator is not cut off once she has replied, and from a room is cut off only if she stays away 30s; a busy or engaged call, not once she has spoken to the caller (§3.3). |
| `timeout` | The operator did not speak when a line was waiting for them (calls to the operator, busy scenes, and a `wait:` line, §6.2). |
| `misdialled` | The operator dialled the number with too many digits — a digit more within 3s of the last it needs — or too few, stopping 10s short of it, or nothing, 30s after taking the trunk, outside tutor mode. The trunk gets reorder, the fast busy, until she releases it; she may then take a trunk and dial again, and the call fails as `misdialled` only when the connect timeout runs out after a reorder. |

Timeouts are the game program's configuration, not the page's: 60s to answer — 90s for a scenario's calls (§6.5), `scenario_answer_timeout`, since its lamps light every few seconds and each waits its turn — 90s to connect after the request has played, 30s for the operator to speak. They are starting values for play-testing.

A wrong connection is not a failure on its own (§3.5).

# 5. Call Pacing

There are four pacings, `game/pace`: tutor, which is manual with a teacher (§7); manual; auto; and listen.

## 5.1 Manual

The Next Call key on the Stream Deck, or the page's Next Call button, starts one call. Nothing else starts a call, apart from `after:` scenes (§6.1).

The key publishes `game/next/set`, at QoS 0, with an empty payload. The game program keeps its own count and starts the next call if `run` is `"on"` and a scene can be dealt (§6.1). If not, it reports why on `game/error`.

Two guards keep one tap to one call. QoS 0 is never resent on reconnect, so a connection that drops mid-send cannot deliver the command twice. The cost is that the tap may be lost, and the operator taps again. The page disables Next Call when it is tapped and re-enables it when `started` changes or `game/error` is published. It also re-enables after 3s regardless, so a lost tap does not leave the button dead. The Stream Deck's key is guarded the same way (§10). Two pages open at once could each start a call, and so could the page and the deck. That is accepted, since only Mark runs them.

`next/set` is accepted in scheduled pacing too. It starts a call at once, and the schedule then runs from that call (§5.2). In listen, that call is one more in progress, and the schedule waits for it to end as well.

## 5.2 Auto

The next call starts `gap` seconds after the most recent call to start has been **connected** (§3.3) or has ended, whichever comes first.

Timing from the most recent call rather than from every call means that at most one call is ever waiting for the operator to connect it. Calls overlap — the next one arrives while the last is still talking — but the operator is never asked to route two at once. That is the case Mark has deferred (§5.5).

While a call is waiting to be connected, no next call is scheduled and `game/next_at` is empty. Once it is scheduled, `next_at` is the host time it will start, and the page counts down to it.

## 5.3 Listen

In listen, `pace` `"listen"`, the next call starts `pause` seconds after every call has ended, however it ended, and no `after:` scene is waiting to start (§6.1). A call that succeeds ends when its parties hang up as the script ends; one that fails ends when it fails, so a missed call does not stall the game. Calls never overlap, and the audience hears each conversation through (§9.1). An `after:` scene still starts its own `delay` after the scene it follows, and the schedule waits for it too, so a story's second call is not interrupted by a new deal. If a waiting `after:` scene cannot start after all — every slot or every trunk busy — no call is in progress and the schedule runs from then. The wait is `pause` exactly, every time: listen is for enjoying the conversations, so it has no ramp and no jitter, and `gap`, `ramp`, `floor` and `jitter` are auto's alone and are not changed by it. `next_at` is the end of the last call plus `pause`; while any call is in progress it is empty.

## 5.4 The Ramp and Jitter

**The ramp.** The gap shrinks as the game goes on:

```text
gap_now = max(floor, gap − ramp × connected)
wait    = gap_now × (1 + jitter/100 × u),   u drawn evenly from −1 to 1, and never below 0
```

where `connected` is the number of calls connected so far in this game. `gap`, `ramp` and `floor` are set from the page; `gap_now` is what the scheduler uses, and it is published so the page shows it. `ramp` of 0 is a constant rate.

**Jitter**. The scheduler waits `wait`, not `gap_now`: a draw spread evenly around `gap_now` by `jitter`, a percentage. At `gap_now` 20 and `jitter` 50 every wait is between 10s and 30s, and they average 20s. `jitter` of 0 is the fixed wait. `floor` bounds `gap_now`, the centre, and not the draw, so near the floor a wait can fall below it; bounding the draw would lift the average there. The draws come from the game's seed (§6.1), so a replay draws the same sequence. `next_at` is the drawn start; `gap_now` stays the centre.

A change to any of the four takes effect at the next scheduling, not on a call already scheduled.

Ranges, clamped by the game program and echoed as applied: `gap` 0–600s, `ramp` 0–60s, `floor` 0–600s and not above `gap`, `jitter` 0–100%, and listen's `pause` 0–60s. Starting values come from the game program's configuration file: manual pacing, `gap` 20, `ramp` 1, `floor` 8, `jitter` 30, `pause` 3. They are set for a newcomer's game: the wait starts at 20s and comes down 1s for each call connected, reaching the floor at the twelfth, and never falls into a rhythm a player can count. They hold across games until changed, and return to the configured values when the game program restarts.

## 5.5 Not Yet: Calls Before Connection

Mark wants, later, a mode where a new call can arrive before the operator has connected the current one — the real pressure of a busy board. The likely form is a fixed interval, a new call every `n` seconds from the start of the last, bounded by the eight slots. It is one more value on `game/pace` and uses the same `gap`, `ramp`, `floor` and `jitter`. Not specified until it is wanted. A scenario (§6.5) is the one place a game asks it of the operator now.

# 6. Scenes

## 6.1 Which Scene, and Scenes That Follow Another

**The shuffle.** At game start the game program takes every active scene in script.yml without `after:` and shuffles it into a list, the shuffle. Every new call, manual or scheduled, is dealt from the shuffle. So every scene is played once before any is played twice, in an order that differs from game to game. A scene marked `active: false` is not played at all: it is never in the shuffle and never follows another, and its wavs need not exist.

**Dealing.** A new call takes the first scene in the shuffle whose lines and people are all free, and removes it. A scene's lines are its calling and called lines, stations and outside names alike. Its people are the `person:` under `calling` and `called`. A call to the operator has no called line or person. A line or person is busy if it belongs to a call in progress, or to a waiting `after:` scene (below). Scenes passed over stay where they are, so a scene held back because its line was busy, or by `follows:` (below), comes up at the next call. If no scene in the shuffle can be dealt, the call does not start, the log says so, and in scheduled pacing the scheduler tries again after `gap_now`. A `next/set` that cannot be satisfied this way is reported on `game/error`.

**Stories: a scene dealt after others.** A scene in the shuffle may carry `follows:`, a list of scenes. While any scene it names is still to come in this round, the shuffle passes it over, as it passes over a scene whose line is busy, and it is dealt after them. A named scene is still to come while it is in the shuffle, while it is a call in progress or a waiting `after:` scene, and, for an `after:` scene, while the scene it follows is still to come. So it can name a scene down a chain, such as `pemb-canary`. A named scene that can no longer come this round holds nothing back: one already played, one dropped because the scene before it was not connected (below), or one that is inactive or out of the circuits fitted. A chosen scene (§6.4) and a tutor lesson (§7) are dealt regardless. It is how a guest's story is told in order across the game: Pike does not leave for his train before his other calls, and the Colonel does not book a table for Mrs. Pemberton before he has asked her. `follows:` is not on an `after:` scene or a scenario's first scene (§6.5), names no scene twice, and does not loop.

**Started again soon.** A game started within `resume_within` seconds of the last stop, 600 by default, deals on from the shuffle it had, where it left off, rather than shuffling afresh: a player who stops and starts again at once is still in the same sitting and should not hear the same scenes over. The scenes dealt stay dealt, a scenario played stays played (§6.5), and in tutor mode a lesson already dealt from the shuffle is not taught again (§7.5). The tallies are still zeroed, and it is a new session in the SQLite log, recording the same seed and, as its first shuffle, the scenes left. The log says "game started, the shuffle continued: N scenes left". 0 always shuffles afresh. The shuffle lives in the game program, so a restart of it shuffles afresh too.

**Reshuffle.** When the shuffle is empty it is shuffled again from the full list, and dealing carries on. If the new shuffle would start with the scene dealt last, that scene moves to second place, so no scene plays twice in a row across the reshuffle. The log records each reshuffle.

**Replay.** The shuffle uses a seed chosen at game start. The seed and each shuffle's order go into the game's SQLite session record, not onto MQTT. The page is not told the order and does not need it.

**Scenes that follow another.** An `after:` scene (script.yml, "Order") is never in the shuffle. It starts `delay` seconds after the scene it follows has ended, in either pacing, as long as that scene was **connected** (§3.3). If it wasn't — the operator never answered, or never put the call through — the `after:` scene is dropped and the log says so. It is part of the story, not a new deal: `nbn-trace` two seconds after `nbn-kaplan`, `hale-pizza` three minutes after `hale-busy`. An `after:` scene may itself be followed, so a story can run to any number of calls; each scene has at most one follower, and the chain has no loop. From the moment it is scheduled until it starts, its lines and people count as busy for dealing. If any of them is still busy in another call when its delay runs out, it waits until all are free and then starts. It counts as a call. It has a call number, it counts in `started`, and it succeeds or fails like any other call. It does not reset the schedule. The page shows a waiting `after:` scene in the log with its start time.

**Scenes that start with another**. An `after:` scene marked `mode: concurrent` starts `delay` seconds after the scene it follows has *started*, not ended, and whether or not that scene is ever connected: it is scheduled as that call opens. So a chain of them puts several calls in progress almost at once. Its `delay` may be a pair, `[2, 5]`, for a wait drawn evenly between the two, from the game's seed apart from the shuffle's, so a replay draws the same. Like any `after:` scene its lines and people are busy while it waits, and it waits for them to come free; it waits for a free slot too (below), so a scenario longer than eight calls keeps all eight slots full rather than losing its tail. Stop drops it. The follower it has in turn is scheduled only once it starts, so the chain pauses while the slots are full.

**Two waiting scenes that need the same line or person.** A waiting `after:` scene holds its lines and people, so two of them can each need something the other holds. Once both delays have run out, one goes first and the other waits for that call to end, as for any call in progress. A scene in a scenario (§6.5) goes before one that is not; otherwise the one whose delay ran out first goes first. Until its delay has run out a waiting scene keeps its lines and people from every other, and a call in progress is never passed over. The log names both: "panic-dobbs goes before dobbs-callback, which waits for it".

At most eight calls are in progress at once — the number of call slots (§3.2). A call that would be a ninth is not started, and is treated like a scene that cannot be dealt; a waiting `mode: concurrent` scene waits for a slot instead.

## 6.2 Lines That Wait for the Operator, and Lines by Someone Else

Keys on a conversation line:

- **`wait: true`** — the line plays only after the operator has spoken on that line's side of the call and stopped: a listen on the called circuit for a `called:` line, on the calling circuit for a `caller:` line, as in the calls to the operator. If she does not speak within the speak timeout, the call fails as `timeout` (§4). It is refused in a call to the operator and in a `busy: true` scene, where every line waits already.
- **`person: <cast member>`** — the line is spoken by that person rather than by the scene's party on that side. It plays on the same circuit; only the voice changes.
- **`pause: <seconds>`** — silence before the line, up to 30s.
- **`ringback: <seconds>`** — ringback tone on the trunk before the line, up to 30s, stopped as the line starts. Only on a line spoken on a trunk: a `called:` line of a call to an outside line, or a `caller:` line of a call from one.

A line's own lead-in runs in that order: the wait, then the pause, then the ringback, then the line. A cord pulled during any of them cuts the call off, as during speech (§4).

**Speech that does not end.** Wherever the game waits for her to speak and stop — the greeting before a request, a reply in a call to the operator or a busy call, a `wait: true` line, the closing, a caller asking again — speech that has run without a silence for 3s in the greeting before a request or before a caller asks again, or 4s anywhere else, is taken as ended: the listen is cancelled and the line plays. Greetings run 1–2.6s and replies a little longer, so a real one is not cut; what the cap catches is the speech detector held in `speech` by sound from her own end, the loudspeaker through her headset or the room, so the caller would never speak. A free call's turns are not capped (§8): its caller is live and may talk for as long as it likes.

The long-distance call is the case they were made for. The hotel operator dials 0 on a trunk; the local operator (`called.person`) answers, "Operator"; the hotel operator asks for long distance; the next line, marked `wait: true` and `person:` the long-distance operator, answers "Long distance", and the guest talks to that operator. The party the long-distance operator rings can speak on the trunk too, with a `person:` of their own. So can each operator on the route: the long-distance operator asks the rate operator for the route and the charge, then rings through each toll center on it, each answering with its town's name after a `pause:`, and the party answers after a `ringback:`.

**Time and charges**. When a long-distance call a guest placed has ended, the long-distance operator rings the hotel to report what it cost: a call to the operator rung in on a trunk (§4.3), an `after:` of the call it bills. Its request is the whole of it — the room, the time and the charge — and it has no conversation, so the far end hangs up as soon as it has been said, whether or not the hotel operator was ready to write it down. It is not repeated. Collect calls, and calls placed from outside to a guest, have none.

## 6.3 What the Operator Says

The player speaks for the hotel operator, and the game only listens for her. script.yml still says what she is expected to say, for recordings of whole scenes (`tts/scenes --batch`) and as a prompt:

- **`operator_lines:`**, at the top level — stock lines by name, each with an `id:` and `text:`. The TTS run renders them in `hotel_operator`'s voice as `operator.<id>`, so no scene may be called `operator`.
- **`operator: <name>`**, or **`operator:`** with an `id:` and `text:`, on the request or a conversation line — what she says just before that line. The inline form is one of the scene's utterances, `<scene>.<id>`, its id unique in the scene and permanent like any other.
- **`closing:`**, on a scene, in either form — what she says after the last line, before the caller hangs up. Only in a call to the operator or a busy call: in any other she has left the line by the end. The game waits for her to say it — a listen on the caller's line, with the tutor's "Say:" prompt in tutor mode — and the caller hangs up after; a closing not said within the speak timeout, or cut short by her pulling the cord, is let go and the call still succeeds.

`operator:` is allowed only where the game waits for her to speak: the request, a `wait: true` line, and every line of a call to the operator or a busy call (§6.2). Both are optional. The game program never plays these lines and never needs their wavs.

## 6.4 A Chosen Next Scene

A long press on Next Call lists every scene that could be dealt — the active ones without `after:`, within the circuits fitted (§12.2) — from `game/scenes`, one id per line. The page shows them in alphabetical order of id. Choosing one publishes `game/queue/set` with its id; the game program echoes it on `game/queue`. The next call dealt, by Next Call or by the schedule, is that scene rather than the shuffle's, if its lines and people are free; it is then taken out of the current shuffle, so it does not come round again until the reshuffle, and `game/queue` goes empty. If they are not free, the call is dealt from the shuffle as usual and the choice stays for the call after. `game/queue/set` with an empty payload clears the choice. It may be made while no game is running, and the first call of the next game is then that scene; Stop forgets it. An id that is not in `game/scenes` is refused on `game/error`.

## 6.5 A Scenario After the Tenth Call

A scene marked `after_handled: <n>` is the first call of a scenario, and its `mode: concurrent` followers (§6.1) are the rest. It is never in the shuffle. Once `n` calls have been handled in the game (§4, success plus fail), the next call dealt — by Next Call or by the schedule — is that scene, if its lines and people are free, else the call after. It is dealt once a game. A chosen scene (§6.4) still comes first.

It is dealt in manual and auto pacing only: never in tutor mode, which is one call at a time (§7), nor in listen, where calls never overlap (§5.3). A game that changes to one of those holds it back until it changes again. Since the tutor never hears a scenario, the tutor has no Say line (§7) for an operator line that only a scenario uses.

**Chosen from the page**. A scenario is in `game/scenes`, so it can be chosen as the next scene (§6.4) to show it. Chosen, it is dealt in manual, auto and listen pacing, never in tutor mode, and only with no call in progress and no `after:` scene waiting to start. It waits for Next Call in manual pacing, and for the schedule in auto or listen, as any chosen scene does. A choice made with no game running is the first call of the next game. Until then nothing else is dealt, and Next Call is refused on `game/error`, "waiting for the board to clear". Once dealt, its followers start on their own timers, in any pacing. A chosen scenario counts as its once-a-game play: the deal after `n` calls does not come after it. It can still be chosen again.

**While the scenario is running** — any of its calls in progress or any of its scenes waiting to start — the schedule waits, as listen waits for every call to end, and runs its gap from when the last of them has ended. Next Call still deals in manual pacing.

**At most `live` waiting**. A scenario's first scene may carry `live: <n>`, 1 to 8. While any of the game's calls not yet connected (§3.3) number `n` or more, a follower whose delay has run out waits, as it waits for a free slot (§6.1), and starts when one of them is connected or ends. So the operator never has more than `n` calls waiting on her at once, however fast the scenario's delays run; a call connected and talking does not count. A call to the operator counts until its request has played. With no `live:`, the slots are the only bound.

`panic` is the first, at the tenth call, with `live: 3`: Martha the dog loose in the hotel, a complaint from every guest room but hers, from the lobby and from the restaurant, four to eight seconds apart, ending with Martha calling from her own room. Its lamps wait 90s to be answered, not 60s (§4).

## 6.6 A Station Found Engaged

A call from a room to a room may carry `if_busy:`, a list of caller lines like a busy call's conversation (§6.2), each played after the operator has spoken. It is for a station many want at once — the front desk in a scenario.

The called station is **engaged** if the game has it off-hook in another call: the room is calling, or has answered. If it is engaged when the request has played, or becomes engaged before the operator rings it, the call is found engaged. It is then **connected** (§3.3), its stage is `busy` (§3.2), and the `if_busy:` lines play, each after she has spoken — "I'm sorry, the front desk is busy" — and the caller hangs up. Once she has begun to speak to the caller, the call is handled, and she may leave (§3.3). The game does not answer a ring on an engaged station. Otherwise the call goes as any call between rooms, and `if_busy:` is not heard.

For dealing (§6.1), a scene with `if_busy:` does not hold its called line or its called person, and is not held back by them; once dealt, its call holds them as any call does. So several guests may ask for the front desk while it is talking, and the operator tells each of them to try later.

`operator:` may name what she says before each line, as in a busy call; `closing:` is not allowed there. The lines are utterances of the scene, rendered as any other.

# 7. Tutor Mode

A voice on the audience loudspeaker talks a new player through each call: a senior operator, cast member `tutor`, calm and unhurried. The game program decides when the tutor speaks, from the same topics it runs the calls on, and plays each line on the monitor with `audio/monitor/play/set` (audio.md §10.4). The lines are rendered offline like every other line (§7.6).

## 7.1 The Pacing

Tutor mode is the pacing `tutor`, first of the four on `game/pace` and the deck's pacing key (§10). It is manual pacing with a teacher: each call comes on Next Call, never on a schedule. It can be chosen whether or not a game runs:

- **Before Start.** The tutor introduces the board (§7.3), and the game starts with the lessons (§7.5).
- **Mid-game.** Tutoring begins at the next call, with no introduction and no lessons.

Choosing another pacing mid-game takes effect at once. The tutor stops mid-word and the calls in progress go on, which is how a player is moved on.

**Missing lines.** While any of the tutor's lines has no wav, `pace/set` `"tutor"` is refused on `game/error`, naming them, since a tutor with gaps is worse than none. The game program does not refuse to start for it, and a configured `pace = "tutor"` falls back to manual.

**Back to tutor.** The installation's `game.toml` sets `pace = "tutor"`, so the game program starts in tutor. A game left stopped in any other pacing returns to tutor after `idle_tutor` seconds, 300 by default, so the next visitor finds it as a newcomer should. The time is counted from the stop, from start-up, or from the last pacing chosen while stopped, whichever is latest. It never happens while a game runs, and 0 turns it off. The return is logged, "pace tutor: stopped 300s", and published on `game/pace` like any other change.

## 7.2 When the Tutor Speaks

The tutor speaks at each step, before the player has to act, and the call is held until the line has finished.

| **Step** | **The tutor says** | **The game then waits for** |
| --- | --- | --- |
| Start | the introduction's first part, the jacks, ending "press More Help, or Next Call to start playing" | More Help or Next Call |
| More Help | the next part: the cords, then the switches and the dial. The last ends "press Next Call" | More Help or Next Call; after the last, Next Call |
| A room's lamp lights | which cord, the lit jack, and the switch to push. One line, because the game cannot see a cord go into a station jack | the caller's `op` |
| A trunk's lamp lights | which cord, and the trunk jack | the trunk's `seize`, which the cord makes |
| That trunk is seized | the switch to push | the trunk's `op` |
| A call to the operator, once the caller has asked | "This call is for you, not for another line. Answer the caller yourself." | the next line |
| Before every listen | "Say:" and the operator line the script gives there (§6.3), or "Greet the caller" for a request, or "Now it is your turn to speak". A request's greeting is "Greet the caller" from its second time (§7.4) | the listen |
| Ringing a room | the cord, the jack for that room by name, and the switch that rings it: the front cord and the near switch for a call from a room, the rear cord and the far switch for a call from a trunk | that station's `ring` |
| The room rings, on a call from a trunk | return the near switch to the centre, before the room answers | — |
| Calling out | the front cord, into any free trunk | any trunk's `seize` |
| The trunk is seized, calling out | keep the switch pushed, and the number to dial when dial tone comes, as the operator's card prints it: "Sunset four, four one oh one", or "zero, for the operator" | the first digit |
| Ringback | return the switch to the centre when the party answers. Ringback runs on until the line has finished, so the far end's first line is not talked over | — |
| Busy tone | "That is a busy signal. Tell the caller", then the Say prompt | the listen |
| After the last `wait:` line | return the switch to the centre. In a call with a `wait:` line this replaces the two rows above it that say to centre the switch, since until then the call still needs the operator | — |
| The call ends | both cords out and the switches centred; for a call to the operator, the one cord | the end of the line. Once the call is down the board shows no cord: an on-hook station has no pilot, and a trunk no seizure, which runs through the station's line |
| Cleared, in manual pacing | "press Next Call when you are ready" | Next Call, the player's word that the cords are out. It may come during this line or the one before, and cuts it short |

Three rules apply to every prompt:

- **Never over a listen.** The operator's microphone hears the loudspeaker, so a listen during a tutor line would take the tutor for the operator. Every listen in tutor mode follows a tutor line that ends before the listen starts, and saying a line stops any line still repeating.
- **Stopped once done.** A prompt the game checks against the board — the answer, the switch, ring, the trunk, dial, centring the switch, the end of a call — stops mid-word as soon as the board shows the player has done it. If the board already shows it, the prompt is not said at all.
- **Said again.** A prompt the player does not act on is said again 20s after it ended, and again 20s after that, then not again. A Say prompt whose listen hears nothing in 20s is said again the same way. After the third time, the line plays as after any listen that times out.

## 7.3 The Introduction

The introduction comes in three parts, `intro-jacks`, `intro-cords` and `intro-switches`, so a new player takes in one thing at a time. Each part but the last ends by asking for More Help or Next Call, and the tutor waits for either for as long as it takes.

- **More Help** is the deck's key 8 during the introduction (§10), and publishes `game/more/set`. Pressed during a part, it cuts that part short and goes on to the next. After the last part it does nothing. At any other time it is refused on `game/error`, unless a short prompt is waiting (§7.4).
- **Next Call**, at any point, ends the introduction and deals the first call.

`game/tutor/intro` is the part under way, `"1/3"` to `"3/3"`, and `""` outside the introduction.

**The key the tutor asks for flashes** on the deck (§10). `game/tutor/waiting` names it, once the tutor has finished speaking and waits for a key:

| **Value** | **When** |
| --- | --- |
| `"more"` | after a part of the introduction that ends "press More Help, or Next Call" |
| `"next"` | after the last part, and after a call once the cords are out and the tutor has said "press Next Call when you are ready for another" |
| `""` | at any other time, including during a line and while the cords are still up |

It goes back to `""` when the call is dealt, when More Help moves on to the next part, and when the tutor stops.

## 7.4 Repeat Help and Short Prompts

**Repeat Help.** Once a line has finished and the game is waiting on the player, the line can be said again. The deck's key 7 reads "Repeat Help" and publishes `game/repeat/set`, an event at QoS 0, and the game program says the line again at once. `game/tutor/repeat` carries the line's key under `tutor:`, or `""` when nothing can be repeated.

These lines can be repeated:

- each part of the introduction;
- every prompt the game checks against the board: the answer, the switch, ring, the trunk, dial, the end of a call;
- "press Next Call when you are ready for another";
- a "Say:" prompt, while the game listens for the operator after it.

A line stays repeatable until the board shows the player has done what it asks, or the tutor says another line, whichever comes first.

Pressed on a "Say:" prompt, Repeat Help stops the listen first, so the loudspeaker is never heard as the operator. The prompt is said again and the game listens afresh. Once the operator has started speaking a press is refused, so her answer is not cut off. The press does not count among the repeats of §7.2. On any other line, a press starts those repeats over (20s, twice) from the end of the line.

`repeat/set` with nothing repeatable, or while the operator speaks, is refused on `game/error`.

**Short prompts.** Each prompt is said at one of three levels. In full the first time it comes up; the second time, brief, if script.yml's `tutor: brief:` has a form for it: "A room is calling. Rear cord into the lighted jack, then push the near switch away from you."; from the third time on, terse, if `tutor: terse:` has one: "Rear cord, push near switch." — the cord and what to do with the switch, no more. A prompt with no terse form stays brief, and one with neither is always said in full. A terse `dial` gives the number in digits alone, as a person says it today.

**A mistake sends the step back to brief.** A wrong cord (§7.7) sends the steps it is about back to the brief form for their next time — ringing the trunk or the caller, the ring prompts; ringing an outside line, the trunk and dial prompts; a rear cord in a trunk, the trunk and answer prompts — and so does a prompt said to the end of its repeats (§7.2), which the player did not manage on the shortest form. After that brief time, terse again.

- **What is counted.** Times are counted from Start, or from Tutor chosen mid-game, prompt by prompt. A jack or a number in a prompt does not make another prompt, so `ring-front` to room 403 and to the Lobby count together, while `dial-operator` counts apart from `dial`. The tutor's own repeats, Repeat Help and More Help do not count.
- **More Help for the full line.** Once a short prompt, brief or terse, has finished and the game waits on the player, More Help (the deck's key 8, as in the introduction) says the full line at once. It is offered for as long as the short line could be repeated, and `game/tutor/more` carries the full line's key while it is, `""` otherwise. After the press, Repeat Help repeats the full line, and More Help is not offered again until the next short prompt. `more/set` outside the introduction with no short prompt waiting is refused on `game/error`.
- **What may have a short form.** Every prompt but the introduction and the three said before the operator speaks (`say`, `greet`, `respond`).
- **The greeting.** A request's operator line, "Say: How may I connect your call?" or "Say: Hotel Ballard. How may I help you?", is said in full the first time each comes up, and as "Greet the caller." from the second: one step, straight to the shortest. The two count apart, and as the rest are counted. A scene's own operator line, heard once a scene, is always said in full. More Help is not offered for it, as for any prompt before a listen; Repeat Help says "Greet the caller." again.

## 7.5 Calls in Tutor Mode

**One call at a time.** No call is dealt while any of these holds:

- a call is in progress;
- an `after:` scene is waiting;
- the tutor is introducing the board;
- the cords of the last call are still up.

Next Call is refused on `game/error` meanwhile, except during the introduction, which it ends. The schedule waits for all of it, as listen pacing waits for every call to end (§5.3), then runs its gap.

**The first calls.** A game started in tutor mode first deals one call of each kind, in the order of the groups under script.yml's `tutor: lessons:`: between rooms, from a room out to a number, in from outside to a room, and to the operator.

- Each group lists suitable scenes of one kind: short, without `wait:` lines or a following `after:` scene. The loader insists only that they are of one kind, active, and not themselves `after:` scenes.
- At Start the game picks one scene from each group at random, from the game's seed apart from the shuffle's, so a restart picks again and a replay picks the same. The picks go in the log.
- Each pick is taken out of the shuffle as a chosen scene is (§6.4), and a chosen scene still comes before them.
- A scene the circuits built cannot play is left out of its group before the choice (§12.2), and an emptied group is skipped.

After the last, the shuffle deals as usual. Choosing another pacing drops the rest, and choosing Tutor mid-game deals none.

**Nothing fails for being slow.** The answer and connect timeouts are lifted for calls dealt in tutor mode, and the call slots show no deadline (§3.2). A caller left alone before connecting does not hang up (§4). A wrong jack or a wrong number is no more a failure than in any game (§3.5): the tutor does not call it wrong, but the prompt comes round again. A call can still fail by being cut off once connected. The tallies count as in any game, and the game log records each change of pacing.

## 7.6 The Tutor's Lines

The lines are in script.yml under `tutor:`. Each key is one line, rendered as `tutor.<key>`. A few keys are templates, rendered once for every value they take:

| **Key** | **Rendered for** | **Fills in** |
| --- | --- | --- |
| `ring-front`, `ring-rear` | each jack a station is cabled to, named for the station, `tutor.ring-front-room403`, so moving a label to another jack changes no file | `{jack}`: "room 403" for a numbered jack, else its label |
| `dial` | each outside line but the operator | `{number}`, as the operator's card prints it, and optionally `{number-digits}`, the number as a person today says it: "seven eight three, two two five oh", "seven eight four, five thousand" |
| `say` | each operator line | `{line}` |

Each is a whole sentence, not a phrase spliced into a sentence at play time, so it is spoken as one. A short form under `brief:` or `terse:` is expanded the same way and rendered as `brief.<key>` or `terse.<key>`, `brief.ring-front-room403`, since `tutor.brief-…` would pass the 31 characters a name may have.

The tutor's voice is designed and chosen as any cast member's (`tts/aws/design --only tutor`, `tts/audition`, `tts/choose --only tutor`), and the lines are rendered and band-limited with the rest.

## 7.7 Ringing the Wrong Cord

When the player rings the wrong cord of a call in progress, the tutor says so on the loudspeaker as the ringing ends, in every pacing, tutor or not. These lines are under `tutor:` (§7.6), and are played on the monitor like the tutor's others.

| **The ring** | **Seen as** | **The call** | **The tutor says** |
| --- | --- | --- | --- |
| On the trunk a call came in on | `trunk/<n>/fault` `"ring_on_trunk"` ending (control.md §8.3) | in from outside to a room: the front cord is in the trunk, the rear cord in the room | `rang-trunk`: ring the rear cord, with the far switch |
| On the trunk of a call out | the same | from a room to an outside line, once the trunk is known (`trunk` in its slot), or while it is not yet known | `rang-outside`: outside lines are dialled, not rung: push the switch away, wait for dial tone, dial |
| On the calling room | `station/<n>/ringing` `"on"` ending, n the calling station, from the audio program (audio.md §9.5) | from a room to a room: the rear cord is in the caller's jack | `rang-caller`: "you rang the person who called you" — a room, the desk or any station — ring the other cord, the one in the called party's jack, since either cord may have answered |

The third row is heard rather than seen: a station's own ring detector does not see ring on a line held off-hook, so ringing the caller is detected on the station's capture channel.

**A rear cord in a trunk** is told the same way, though nothing is rung. Only a front cord seizes a trunk, so a trunk that hears the operator without being seized has a rear cord in it: `trunk/<n>/op` `"on"` while its `seize` is `"off"`, for 2s together, which is 1s beyond the hold on `op` going off (§4).

- The call is found as for `rang-trunk` and `rang-outside`: the call holding that trunk, else a call out whose trunk is not yet known.
- It applies only before the call is connected, because a room hanging up on a call out drops the trunk's seizure while the operator may be in.
- The tutor says `rear-in-trunk`: pull it out and use the front cord.
- A rear cord in a trunk whose pair's front cord is in an off-hook room seizes the trunk and patches the two as a correct patch would. That is not caught.

**For all of these:**

- Each is said once a call, and the log records it as `wrong cord: <key>` against the call's number.
- A ring that matches none of them is left alone: a trunk no call holds, with no call going out; a call to the operator; a call out whose caller is rung.
- The ring cue (§9.2) sounds as for any ring, and the wrong-cord line replaces it if it is still playing.
- A line not yet rendered is not said, and unlike the tutor's other lines it does not stop tutor mode being chosen (§7.1).
- A caller left alone during the line waits its 10s afresh from the end of the line (§4).
- A prompt of the tutor's still playing when the line starts is ended by it, and the call goes on. The prompt comes round again as usual if she has still not done what it asks.

# 8. Free Calls: Lenny Mode

A free call is a real person on the switchboard rather than a scene: someone lifts the real telephone, or dials in from outside. The operator connects them to any room or number, and whoever answers replies from a list of lines, whatever the caller says, as the Lenny recordings do with telemarketers. Mark's spec, 2026-10-23:

> A real person will pick up the phone on station 24 or call in from an outside line. We assume the operator will connect the caller to one of our game stations or dial one of our pre-defined outside numbers. If the operator dials some other outside number, the game should still answer, but in this case use the "real" Lenny voice. The actor residing at the called station or outside establishment should answer in an appropriate way. Then the actor responds to speech by the caller by iterating through [their] utterances. The actor continues in this mode until the calling party disconnects, at which time the called station or trunk hangs up.

## 8.1 Who Calls

There are two kinds of free caller, both real people.

**Station 24**, the real telephone on jack 18 (§12.2, real_phone.md). When `station/24/lifted` goes on, the game closes station 24's relay (`hook/set` `"on"`), which puts the line on channel 24 so its pilot, `op` and `peer` work. The phone's own lamp is the switchboard's. The caller is gone when `lifted` goes off, and the relay is opened again.

**Trunk 8**, the public line: the Grandstream ATA's FXS port, which outside callers reach by dialling its number (trunk_circuit.md §4.5). The controller cannot see it ring. The audio program hears it, `trunk/8/ringing` (audio.md §9.5), and the page flashes the tile with each ring (§11.1). While a game runs the game does nothing with it. While none runs, a ring is logged, "trunk/8: the public line is ringing", since anyone who knows the number may call. The ring latches the trunk's signal on the switchboard's own battery until a cord goes in, and only a power cut clears it (§2), so if `seize` has not come on 30s after the first ring, the game cuts the switchboard's power for its 1s, `ctl/power_cut/set` `"on"`, and logs "switchboard reset". It waits first until the line has not rung for 10s, so that a caller still ringing does not latch the signal again straight after; a board switched off from the page (§11.7) is not cut, and the log says so. An answer is logged too. The free call begins when the operator answers it, with `trunk/8/seize` and `trunk/8/op` both on. The caller is gone when `seize` goes off for more than a second, because the operator has pulled the cord, or the far end hung up and the ATA dropped the loop. Which trunk is the public line is `public_trunk` in the configuration, 8 by default, and no scene ever uses it (§12.2).

## 8.2 Answering and Connecting

**The operator answers** when `op` comes on on the caller's line. Until then, a lifted station 24 waits for as long as it is lifted. The loudspeaker moves to the caller as for any answer (§9.1), with the peer boost fixed at 6dB: the caller is live, so the audio program has nothing on the caller's line to measure against, and the 2026-10-24 recording put the called party's files 6dB under the real telephone. She then talks to the caller herself, and the game does nothing until she connects them.

**Connecting.** While a free caller is answered and not connected, either of these is taken as connecting the call.

**A room rung:** `station/<n>/ring` on a station fitted (§12.2), not station 24, and not in another call or another free call. If a game call is routing and wants that very station, the ring is that call's. The room answers as in §3.5, 4s after she rings it: its relay closes, and once its `peer` is the free caller, its occupant answers. If it is not patched within 8s it says "Hello?", and if not within as long again it hangs up, and the free call waits for her to ring again.

**An outside number dialled:** a trunk seized, not the public line and not in a game call, whose `peer` is the free caller, since the operator's cord joins them. It gets dial tone after 1s as in §3.5. The number is seven digits, or `0` alone, and what follows depends on what she dials:

| **Dialled** | **Result** |
| --- | --- |
| A known number, then 3s with no digit more | 2s of ringback, and its establishment answers. Known numbers are the `outside:` lines' numbers, digits only; `0` is the local operator |
| An unknown number, then 3s with no digit more | 4s of ringback, and the real Lenny answers |
| Too few digits and 10s with no new one, or a digit too many | fast busy, as a game call's misdial gets (§3.5), until she releases the trunk |
| Nothing in 15s, or the trunk released | back to waiting |

**A game call routing at the same time.** While a free caller is routing, a game call does not take a rung room as a wrong party unless it is the room it wants, and does not take a trunk whose `peer` is a free caller. One operator does one thing at a time, so the two rarely meet. When they do, the game call wins.

## 8.3 Who Answers

| **Called** | **The answerer** |
| --- | --- |
| A room | its occupant: the cast member who speaks for that station most often in the scenes (§3.5) |
| An outside number | the cast member who speaks for that line most often |
| An outside number no scene speaks for | the one its `outside:` entry names with `person:`, such as the police's desk sergeant |
| A line with nobody, or a person with no `freecall:` entry, or an unknown number | the real Lenny |

## 8.4 How They Talk

The answerer plays their `greeting:`. Then, over and over:

1. **Listen** on the answerer's circuit, which hears the caller across the cord (and the operator if she is on it). The listen runs from the start of the greeting or line just said, since the echo canceller of audio.md §9.4 hears a caller who talks over it, until 3s after it ends, or 7s after a "Hello?".
2. **Nobody spoke:** say "Hello?", the person's `hello` reaction (§3.5), and listen again. Lenny says nothing and waits in silence, as the original does.
3. **Speech, then silence:** listen once more for 0.4s, so that a breath is not the end of a turn. With the audio program's own 0.8s to report silence, the answerer comes in about 1.2s after the caller's last word; Lenny waits about 1.5s. If speech comes again, go back to the start of this step.
4. **Say the next line:** the `lines:` once each, in order, then the `loop:` in order, round and round for as long as the call lasts.

## 8.5 The End

When the caller is gone the answerer hangs up: its relay opens, or for a trunk the tone and file stop.

If instead the operator pulls the cord between them, so that the answerer's `peer` is not the caller for more than a second (§4), or releases the outside trunk, the answerer hangs up. The free call then goes back to waiting for her to connect it again, as long as the caller is still there.

## 8.6 Free Calls and a Game

- Free calls run whether or not a game is running. They are not scored and have no call slot.
- Each one holds, for dealing (§6.1), the caller's line and the answerer's line and person, so no scene is dealt that would use them. It does not hold the schedule.
- A diagnostic is refused on a circuit in a free call.
- Stop does not end a free call, though its switchboard power cut (§2) may: a cord that comes back within the hold rides through it.

**What is not done.** The game does not ring station 24 or the public line, and no scene uses either. An operator who rings station 24 rings the real phone and nothing else happens. A free call to a room that a game call has off-hook is not answered.

**The log.** Each step goes in the log without a call number: `free call: phone answered`, `free call: phone to room403, thornhill answers`, `free call: phone dialled 2835678, canlis, maitre_d answers`, `free call: phone dialled 5551212, Lenny answers`, `free call: phone hung up`.

## 8.7 The Real Lenny

Lenny is sixteen recordings released freely on the internet in 2013 and used ever since to waste telemarketers' time (Sahin et al., *Using chatbots against voice spam: analyzing Lenny's effectiveness*, SOUPS 2017). He plays them in order, one at each pause, and after the sixteenth goes back to the seventh (the Asterisk dialplan in the public pack).

Here he is the cast member `lenny`, recorded. `freecall: lenny:` carries his recordings' transcripts as the greeting (1), lines (2–6) and loop (7–16), and the files themselves are his takes in `tts/recorded/`, processed like any performer's (tts_task.md §6.4). The pack's alternative sixteenth, with a song in it, is not used.

# 9. The Audience Loudspeaker

## 9.1 What It Carries

The loudspeaker carries one receive channel, chosen by the game program with `audio/monitor/source/set` (audio.md §10.3). The game program points it at the calling line of the call the operator most recently answered, and leaves it there until she answers another.

**When.** The operator answers a call when its calling circuit's `op` goes on while the call is in `signalling` — and, for a call from outside, its trunk is seized, since a rear cord in the trunk lets her be heard there without seizing it: that is the event that takes the call out of `signalling` (§3.2). At that moment the game program publishes `monitor/source/set` with the calling circuit's id. For a call from a station that is the station, such as `station/11`. For a call from outside it is the trunk that rang in, such as `trunk/3`. It does not change the source at any other point in the call. It does not change it when the operator bridges onto a call already past `signalling`, to listen in or to go back to a caller, since that is not an answer.

**Why at the answer.** Before the answer the calling line carries nothing worth hearing. A calling station is off-hook and silent. A calling trunk has been rung, and its ring relay put a click on its channel at the start and end of the burst (trunk §8.1.1). Waiting for the answer also keeps the audience on the current conversation until the operator actually leaves it for the next caller. Mark's first proposal switched at the start of the call. He changed it to the answer on 2026-09-24 for these reasons.

**What the audience hears.** The calling line's receive channel carries the caller's side at full strength, since the interface has no hybrid (station §8.4). It carries the operator while she is bridged to the line, and the called party once the cord connects them. So one source carries the request, the operator's reply and the conversation. A call to the operator, and a busy scene where the operator goes back to the caller, are heard the same way. An outgoing call's ringback and busy tone reach the caller through the cord, and the audience hears them when the caller would.

**Which call.** Only the most recent answer counts. In auto pacing the next call can arrive while the current one is talking (§5.2); in listen it cannot. When the operator answers it, the audience leaves the current conversation for the new request. An `after:` scene is a call like any other and moves the loudspeaker when it is answered.

**Start and stop.** When a game starts, and when it stops for any reason (§2), the game program publishes `monitor/source/set` `"tap"`. A monitor diagnostic moves it too, and ends when anything else moves it (§11.4). Between games the loudspeaker carries the operator tap as it always has. The audio program also returns to the tap by itself if it loses the game program (audio.md §13.2).

**The peer boost**. With each new source the game program publishes `audio/monitor/peer/set` just before it (audio.md §10.8): `"auto"`, the audio program's measurement, for every move but a free call's answer, which sends `"6"` (§8).

**What the game program does not do.** It does not set the monitor's gain, which is a bench and installation setting, and it does not turn the monitor on or off. It publishes a new source only on an answer, a start or a stop, and does not wait for the echo. The page shows the echo (§11.1).

The log records each move as `monitor: <calling line>` against the call's number, using script.yml's line name, as the other call events do.

## 9.2 The Ring Cue

While any station reports ring — `station/<n>/ring` `"on"`, ring voltage arriving from the switchboard (mqtt.md §4) — the audience loudspeaker plays ringback, so the player and the room hear the operator ringing. It starts at the first station's ring and stops when the last one's ends, so it follows her ringing key; it is steady, with no cadence. It sounds whether or not a game runs, and whichever station she rings, the right one or not.

It is a file on the monitor (audio.md §10.4), `cue.ringback.wav` in the wav directory, rendered by `tts/cue`: the period ringback of audio.md §8.2, 420Hz modulated by 40Hz, 60s long, at −28dBFS RMS by default, a few dB under the speech files, since the monitor's one file trim sets both. A cue that runs to its end while ring continues starts again.

**The tutor first.** The monitor plays one file at a time, and that file is otherwise the tutor's voice (§7). The cue does not start while the tutor speaks; it starts as soon as the monitor is free, which is usually at once, because the tutor's prompt to ring is cut short by the ring it asks for. If the tutor begins during the cue the tutor's line replaces it, and when ring ends the cue is stopped only if it is still what the monitor plays.

**Off.** `ring_cue = false` in the configuration turns it off. The game program also leaves it off, with a warning in its log, if the file is not in its wav directory at start, and gives it up until restart if the audio program reports it `missing`.

# 10. The Stream Deck

An Elgato Stream Deck+ on a USB cable from the host, beside the switchboard, carries the game's controls. It has eight LCD keys, 120×120 pixels each, in two rows of four; four dials below them, each of which turns in detents and can be pushed; and between the two a touch strip, 800×100 pixels, a 200-pixel segment over each dial.

## 10.1 The Program

`sbgame-streamdeck`, a Python program in `engine/`, drives it through the `streamdeck` library over hidapi. It is a process of its own and not part of the game program, for the page's reason (§1): it reads the bus directly, so it shows the game offline rather than going dark with it, and a USB fault cannot disturb a game. It connects to the broker on loopback as `sbgame-deck`, with the page's access list: it reads `sbgame/#` and writes only `sbgame/game/+/set` (`mqtt.md` §9). It runs as a systemd service, `sbgame-streamdeck`, as the system user `sbgame-deck`, which a udev rule lets open the deck and nothing else. It has no will and no heartbeat, for the page's reason (`mqtt.md` §8.2): nothing depends on it. One thing it does is not a publish: it powers the host off (§10.2), through logind, which a polkit rule lets `sbgame-deck` do and nothing more (`host/etc/polkit-1/rules.d/`).

It follows every rule of §11.2. It shows only what was echoed, and a press changes nothing on the deck until the echo arrives. Every command is absolute but Next Call. Durations are computed against the host's clock, taken from each `game_heartbeat`. Stale values are greyed, not blanked. It subscribes to `sbgame/#` on every connect and needs nothing else.

**No deck.** The program runs whether or not a deck is plugged in. It looks for one every 2s, and draws a deck found or replugged from the state it already holds. It drives the first Stream Deck+ it finds and ignores any other. On a clean stop it clears the deck, so it is blank rather than showing controls that no longer work. A crash leaves the last images on the keys; systemd restarts the program within 5s, and the first thing it does is redraw them.

**Brightness** is an option of the program, 60% by default. The deck has no screensaver in this program.

## 10.2 Keys and Dials

**Keys**, numbered 1–4 on the top row and 5–8 below, left to right:

| **Key** | **Shows** | **Press** |
| --- | --- | --- |
| 1 Start | "Start", lit while `run` is `"off"` | `run/set` `"on"`. Ignored while a game runs. |
| 2 Stop | "Stop", lit while `run` is `"on"`; "Stop again" in red for 3s after a first press | Arms it. A second press within 3s publishes `run/set` `"off"`. |
| 3 Pacing | "Tutor", "Manual", "Auto" and "Listen", one per line, the echoed `pace` lit | `pace/set` with the next of the four in that order, wrapping from Listen to Tutor. Absolute; counted from the last press while its echo is outstanding, and from the echo once it arrives or 1s after the press. |
| 4 Next Call | "Next" over "Call", lit violet while a game runs, flashing once a second while `game/tutor/waiting` is `"more"` or `"next"` and the tutor is not speaking (§7); in scheduled pacing, auto or listen, the countdown to `next_at` in place of "Call", or "waiting" while none is scheduled | `next/set`, at QoS 0, guarded as §5.1: dark from the press until `started` changes, `game/error` is published, or 3s pass. |
| 5 Calls | `started` and in progress; "Sweep" over "trunks", lit teal, while that sweep runs, from the deck or the page; "Switchboard" over "reset", lit red, while `ctl/power_cut` is `"on"`; "Switchboard" over "off", lit red, while it is `"hold"` | nothing. Pressed twice within 0.5s with no game running, `sweep/set` `"trunks"`; while the trunk sweep runs a single press, `"off"`, and while the station sweep runs two (§11.5); held 2s with no sweep running, `power_cut/set` `"on"`: the switchboard reset below, during a game too |
| 6 Score | success and fail; "Sweep" over "stations", lit teal, while that sweep runs, from the deck or the page | nothing. Pressed twice within 0.5s with no game running, `sweep/set` `"stations"`; while the station sweep runs a single press, `"off"`, and while the trunk sweep runs two (§11.5) |
| 7 Percent | success percentage of handled. While the tutor has a line to repeat (§7), "Repeat" over "Help" instead, lit teal, and dark while the tutor speaks | nothing. While the tutor has a line to repeat, `repeat/set` at QoS 0, then dark for 1s or until the tutor's voice starts, so a double press does not say it twice. |
| 8 Health | a lamp each for the game program, the controller and the audio program, red when offline or its heartbeat is 2.5s late; the whole key red while `game/error` is set. While the tutor introduces the board (§7), "More" over "Help" instead, lit teal while a further part remains, and flashing once a second while `game/tutor/waiting` is `"more"`. The same while `game/tutor/more` is set, a short prompt waiting, dark while the tutor speaks | shows the last `game/error` on the strip again. While the tutor introduces the board, `more/set` at QoS 0, guarded as Next Call is: dark from the press until `game/tutor/intro` changes, or 3s pass. On a short prompt, the same, until `game/tutor/more` changes. |

**Dials**, left to right: `gap`, `ramp`, `floor`, `jitter`. One detent is one step of the page's stepper: 5s, 1s, 1s and 10%. A push does nothing, except a held push of the first dial: shutting down the host, below.

**Turning a dial.** The dial reports steps and the command is absolute, so the program keeps a target. The first detent starts the target at the echoed value; each detent adds a step to the target, clamped to the §5.4 range, and publishes it. The target is held while detents keep coming and is dropped when the echo equals it or 1s after the last detent, so a fast turn loses no steps and a value the game clamped differently — `floor` above `gap` — settles on the echo. A dial whose value has not been echoed yet does nothing.

**Switchboard reset**. Key 5 held for 2s, with no sweep running, publishes `game/power_cut/set` `"on"`, once per hold, at the 2s mark rather than on release, so the operator knows when to let go. From the press until then the key reads "Hold to" over "reset", with a bar filling across its foot; let go sooner and nothing is sent. A hold is one press to the sweep's double press: a second press within 0.5s of the first still starts the trunk sweep, and the hold then counts for nothing. While a sweep runs the key behaves as the table says and a hold does nothing more. While `ctl/power_cut` reads `"on"` the key reads "Switchboard" over "reset", lit red, whoever sent it. While the game program is offline a hold does nothing and the key does not show it. During a game it works as without one: the game program freezes the lines through the cut, so the calls in progress carry on (§4), and a trunk lamp left lit clears.

**Shutting down the host.** The first dial pushed and held for 3s, with no game running, powers the host off (`systemctl poweroff`), at the 3s mark rather than on release. From the push until then its segment of the strip reads "hold to" over "shut down", with a bar filling across its foot; let go sooner and nothing happens. Then the whole strip reads "Shutting down", in red, until the deck goes dark. During a game a push does nothing: stop the game first. With the game program offline or its heartbeat late a hold works, so a hung game program cannot keep the host up; with the broker lost it works too. The services stop as at any shutdown: the game program ends a game cleanly, and the controller, losing the broker, releases every relay (`mqtt.md` §8.2). If logind refuses, the strip shows why for 5s, as an error is shown, and a touch dismisses it. Nothing is published; it is local to the host, like the deck itself.

## 10.3 Errors and Staleness

**Errors.** When `game/error` changes to a non-empty value, the strip shows it across its whole width for 5s and then returns to the dials. Key 8 stays red until the error clears, and a press on it shows the error again. A touch on the strip dismisses it.

**Staleness.** With the broker lost, every key is greyed and the strip says so. With the game program offline or its heartbeat 2.5s late, keys 1–7 and the dials are greyed and do nothing; key 8 still shows the three clients. A press that does nothing gives no other sign; the greyed key is the sign.

# 11. The Page

## 11.1 Layout

For an iPad in landscape, 1024 CSS pixels wide or more. Touch targets 44px or larger. Four areas: the top bar across the page; the board under it, across the whole width; then calls, with the log under them, beside a narrow health column:

**Top bar**, always visible. A Controls switch beside the connection lamps shows or hides its buttons — Start, Stop, the pacing, Next Call and the steppers' − and + — on this iPad. The Stream Deck carries the same controls (§10). With the buttons hidden the values stay — the four values, `gap_now`, the countdown and the tallies — and one line reads what the hidden buttons showed: Running or Stopped, and Tutor, Manual, Automatic or Listen. The setting belongs to the iPad, kept in the browser's storage, not on the bus. An iPad with no setting, or one whose storage was cleared, shows the buttons, so it can always run the game.

- Connection: broker connected or not; game program online or not.
- Start and Stop. Stop needs a second tap within 3s, because it ends a player's game.
- Pacing: Tutor | Manual | Automatic | Listen.
- Next Call: large in manual pacing, small in scheduled pacing (auto or listen). A long press, held about half a second, opens a scrolling list of the scenes to choose the next one from (§6.4); a chosen scene shows under the button until it is dealt.
- Tools: a panel of diagnostics not tied to a jack. Its sections are the operator tap: `tone`, `voice` and `monitor` (§11.4); Diagnostics, the board sweeps (§11.5); Record and Playback (§11.6); and Switchboard, its power (§11.7). A long press, about half a second, shows a key to the lamps instead: each state in the table below with its lamp as the board draws it.
- Help: a long press on a pacing button or a stepper explains it, beside the button. Escape, or a tap elsewhere, closes it and every other popup.
- `gap`, `ramp`, `floor`, `jitter`, each with − and + steppers (5s, 1s, 1s, 10% steps). Shown only in auto pacing, with `gap_now` and the countdown to `next_at` beside them. In listen, one stepper, `pause` (1s steps), and the countdown take their place. The countdown reads "waiting" while a game runs and nothing is scheduled, and "–" when no game runs.
- Tallies: started, handled, success, fail, success percentage.

**Board.** Laid out as the switchboard is: station jacks in three rows of ten, and one row of ten trunk jacks below them. Rows run 21–30, 11–20, 1–10 from the top, each left to right, as the 551 is numbered. Each tile is one jack, from the `board/` topics (§12.1).

A tile shows little:

- the jack's **label**, large, and its jack number, small. Every label on the board is set at one size, the largest at which the longest still fits its tile, so the board reads as one designation strip; a label is never clipped, and words are not broken;
- **one state**, as a colour, the most urgent first:

| **State** | **Station jack** | **Trunk jack** |
| --- | --- | --- |
| fault | `peer` `"ambiguous"` or `"deaf"` for a second, `play` `"missing"` | the same, or `fault` `"ring_on_trunk"` |
| ringing | `ring` on, flashing | `ring` on, or `ringing` on the public line (§8), flashing with the cadence |
| calling | `hook` on, `op` off and `peer` empty: the line lamp is lit, nobody has answered | — |
| connected | `peer` set, in a colour shared by both ends of the pair | `peer` set, the same way |
| operator on | `op` on | `op` on |
| busy | `hook` on | `seize` on |
| idle | none of the above | none of the above |

- the far end's **label**, when `peer` is set, taken from the board map rather than shown as a circuit number.

Tapping a tile opens a panel with everything about that jack: its circuit, `hook` or `seize`, `ring`, `peer`, `op`, `play`, `tone`, `listen`, `fault`, the digits of a call on a trunk, and the call slot using it. Tapping elsewhere closes it. Mark expects the tile to need more or less than this once it is on the iPad.

The panel's commands (§11.4), for a jack with a circuit that is fitted (§12.2): on a station, its `hook` row, and `tone`, `voice` and `monitor`; on a trunk, its `ring` row, and the same three. A row that is also a command is coloured as one — the command colour marks a tappable row, and it is lit while that test is on — so the rows that only show a value read differently from those that act. The commands are controls, hidden with the Controls switch like the others.

A station jack with a label and no circuit — listed in `jacks:` with no `station:` — is drawn as a working jack at rest: label, jack number and an unlit lamp, the same as an idle cabled jack. The operator is shown the board as it is built, not which of its jacks the game has wired. A jack with neither a label nor a circuit — a station jack `jacks:` does not list, and trunk jacks 9 and 10 — is drawn as an empty outline with its jack number, so the board keeps its shape. Trunk tiles show the jack number alone, since trunk jacks have no labels.

**Calls.** One row per occupied slot: call number, scene, from → to, trunk, stage, time in stage, time to deadline. From and to are script.yml's line names. The trunk is shown by its jack number.

**Health and log.** Controller: `status`, seconds since the last `esp_heartbeat`, `i2c`, and `firmware`. Audio: `audio_status`, `optone`, `monitor`, and the monitor's `source` — `tap`, or the jack label of the circuit it names, from the board map. Game: `game_status`, seconds since the last `game_heartbeat`. The host's public address: `public IP`, `host/public_ip` — "offline" in its place if `host/public_ip/error` is `"offline"`, "error" if it is anything else or the lookup is over 11 minutes old — and `checked`, the age of `host/public_ip/checked` — "failed" before it if `host/public_ip/error` is set, "checking…" from a tap until it changes (15s at most) — both grey when the lookup failed or is over 11 minutes old; a tap on either publishes `host/public_ip/check/set` (mqtt.md §6.3). Then `public trunk`, `host/public_trunk` — `registered`, `disconnected`, `offline` or `error`, and `error` too if `host/public_trunk/checked` is over 30s old — grey unless `registered`. Then the log, in a monospaced column, and the last `game/error` as a line that clears on the next accepted command.

## 11.2 Behaviour

**The page never shows what it asked for, only what was echoed.** A tap publishes a `/set` and changes nothing on screen; the display changes when the game program's state topic changes. A command the game rejects shows on `game/error`. This is the same `/set`-and-echo rule as every other client (`mqtt.md` §3).

**Every command but one is absolute.** The steppers publish the new value, not a step. Next Call is the exception: a plain request, guarded as §5.1 describes.

**Time.** Host times in `since`, `deadline` and `next_at` are host Unix seconds. The iPad's clock is not trusted — on the travel router neither clock may have seen a time server. The page takes the host's time from each `game_heartbeat` payload, keeps the offset from its own clock, and computes every duration against host time.

**Staleness.** Grey out, rather than blank, anything that may be out of date:

- broker disconnected: everything;
- `game_status` offline, or no `game_heartbeat` for 2.5s: the top bar's controls disabled, the tallies, calls and log greyed;
- `ctl/status` offline, or no `esp_heartbeat` for 2.5s: `hook`, `ring`, `seize`, `fault`;
- `audio_status` offline: `peer`, `op`, `play`, `tone`, `listen`, `optone`, `monitor` and its source.

**Connection.** Clean session, keepalive 10s, MQTT.js's own reconnect every 2s. Subscribe to `sbgame/#` on every connect; the retained topics give the whole state at once, and there is nothing to request. Before subscribing, drop everything held: a topic cleared while the page was away is not sent again, and anything kept from before would stay as it was. Safari closes the socket when the iPad locks or the page goes to the background; on `visibilitychange` to visible, if not connected, reconnect immediately rather than waiting for the timer. `trunk/<n>/digit` messages published while the page was away are lost; the call slot's `digits` and the log carry them.

**No hardware commands.** The page publishes only `sbgame/game/+/set`. The broker drops anything else from `sbgame-web` (`mqtt.md` §9).

## 11.3 On the iPad

Add the page to the Home Screen, so it opens without Safari's bars. Turn off Auto-Lock while it is in use at an event. The page is a secure origin (§13.1), so it could instead hold a screen wake lock while a game runs; that is not specified yet (§14). For a public exhibit, Guided Access keeps visitors on the page.

## 11.4 Diagnostics

Tests of one circuit at a time, from the page, for bring-up and fault-finding. Each is a toggle: a tap starts it, and a second tap on the same command stops it. The page publishes `game/diag/<target>/<test>/set` `"on"` or `"off"`, where `<target>` is `station/<n>`, `trunk/<n>` or `tap`; the game program does the work, since only it commands the hardware (mqtt.md §6), and echoes each test's state on `game/diag/<target>/<test>`.

| **Test** | **On** | **Where** |
| --- | --- | --- |
| `hook` | the station goes off-hook (`hook/set`) and stays so | a station's panel, on its `hook` row |
| `ring` | the trunk rings in the standard cadence, 2s on and 4s off (`ring/set`); it stops when the trunk is seized, and after the controller's 30s ring limit (control.md §8) | a trunk's panel, on its `ring` row |
| `tone` | the 1kHz test tone on the circuit's output channel (`audio/test/<ch>/set`) | stations, trunks and the tap |
| `voice` | speech on the circuit: utterances from the script chosen at random, one after another, each finishing before the next | stations, trunks and the tap |
| `monitor` | the loudspeaker is fed from the circuit's receive channel (`audio/monitor/source/set`) | stations, trunks and the tap |

**Together.** `tone` and `voice` exclude each other on one target: starting either stops the other. One `monitor` runs at a time: starting it on one target ends it on any other, and anything else that moves the loudspeaker — the operator answering a call (§9.1), a game starting or stopping — ends it too. Ending a monitor test returns the loudspeaker to the tap. `hook`, `ring`, `tone` and `voice` on different targets run side by side.

**With a game.** Tests run whether or not a game is running. A test on a circuit that is in a call, or that the call's slot has taken, is refused on `game/error`, and a circuit under test is busy for dealing (§6.1), so no scene is dealt onto it and no call takes that trunk. The tap belongs to no call, so its tests are always allowed; the operator hears them. Stop ends every test (§2), as does the game program losing a client or restarting.

**Not fitted.** A test on a circuit beyond `stations` or `trunks` (§12.2) is refused on `game/error`, and the page does not offer it.

## 11.5 Board Sweeps

A check of the cabling, with no game running, from the page's Tools, under Diagnostics: `trunks` and `stations`, a tap to start one and a tap on the same button while it runs to stop it, the button filled while its sweep runs and dimmed while a game does; and from the Stream Deck (§10), key 5 pressed twice within 0.5s for the trunks and key 6 for the stations; a single press of the running sweep's own key stops it, as does the other key pressed twice. `game/sweep/set` `"trunks"` or `"stations"` starts one, and `"off"` stops it; the game program echoes the sweep running on `game/sweep`, `""` when none is.

- **Trunks.** Each fitted trunk in turn, 1 to `trunks` but not the public line (§8), gets one short ring (`shortring/set`, control.md §8.4). A working lamp lights. When the 1s burst ends the sweep waits 3s: a lamp whose ring relay latched stays lit all that time, and one that did not has gone out with the burst. Then the switchboard's power is cut for 1s (`ctl/power_cut/set` `"on"`), which resets the relay and puts the lamp out, and the next trunk follows 0.5s after power returns.
- **Stations.** Each station cabled to a jack but station 24, the real telephone, whose relay lights nothing, in jack order — the rows from the top, 21–30, 11–20, 1–10, each left to right (§11.1) — goes off-hook (`hook/set`) for 1s, and the next follows 2s after it goes back on-hook.

Out-of-service circuits (§12.2) are swept with the rest, since a sweep is how one is found to work again; the log line says it is out of service. A circuit under a diagnostic (§11.4) is passed over, so a sweep never releases a hook the page is holding. A trunk sweep's power cuts take the whole switchboard down, so a test or a free call running at the same time is interrupted by each. Each step goes on the game log (§12.3), `test stations: jack 23 (463), station 11 off-hook`, so the page shows where the sweep has got to, and the circuit's own echoes light its tile.

A sweep is refused on `game/error` while a game runs. Start ends one before the game starts, and so do Stop and anything else that stops a game (§2); the circuit under way is put back — the station on-hook, the burst cancelled. A new sweep ends one already running.

## 11.6 Recording and Playing Back the Loudspeaker

Two sections of Tools (§11.1), for keeping what the audience heard and hearing it again.

**Record.** A tap on `record` closes Tools, as choosing a recording to play does, and publishes `game/record/set` `"on"`, which the game program passes to the audio program as `audio/record/set`, refused on `game/error` while the audio program is offline. The audio program records exactly what goes to the loudspeaker into `/srv/sbgame/recordings/<YYYY-MM-DD-HH-MM-SS>.wav`, named for the host's local time at the start, and when it stops makes an MP3 beside it, keeping both (audio.md §10.6). While `audio/record` names a file, the button reads `recording`, filled, and a tap on it publishes `"off"`; and in the top bar, to the right of Tools, stand a red dot and the time recorded, the dot lit for the first half of each second recorded and dark for the second, so it lights as the count goes up, counted from the time in the name against the host's clock (§11.2); they are there only while recording. A tap on them publishes `"off"`. `audio/record` `"failed"` — no file could be opened — shows as `record (failed)` until the next try. A recording runs with or without a game; Start and Stop leave it alone, and the audio program stops one itself after four hours.

**Playback.** A tap on `play…` opens a list of the ten newest recordings, newest first, from `audio/recordings`, each as its date and time with its length. A tap on one publishes `game/playback/set` with its name, which the game program passes on as `audio/playback/set`; the audio program plays it on the loudspeaker in place of the monitor, at the level it was recorded (audio.md §10.7), and echoes the name on `audio/playback`, and `""` when it ends. While it plays, the button reads `playing`, filled, and a tap on it publishes `"stop"`; and in the top bar, to the right of Tools and of a recording's dot, stand a play triangle and the time played, there only while it plays — the length is in the list, and the bar has no room for both at the iPad's width; a tap on them publishes `"stop"`. Refused on `game/error` while a game runs, since it would play over the calls, and `play…` is dimmed then; Start stops one that is playing. A name that cannot be played comes back `"missing"`, shown as `play… (missing)`.

One at a time: `record` is dimmed and does nothing while a recording plays back, and `play…` while one is being made, and the game program refuses `record/set` `"on"` during a playback and `playback/set` with a name during a recording, on `game/error`. Stopping either is always accepted.

## 11.7 The Switchboard's Power

The last section of Tools (§11.1), Switchboard, has one button, `power`. It is filled while the switchboard is powered, `ctl/power_cut` `"off"`, and plain while it is not — held off, `"hold"`, and for the 1s of a reset, `"on"` (§2, §10). A tap while it is filled publishes `game/power_cut/set` `"hold"`: the controller cuts the switchboard's 24V and keeps it cut (control.md §5.4). A tap while it is plain publishes `"off"`, and the switchboard is powered again; during a reset that ends the reset early. A toggle, not a pulse: the switchboard stays dark until tapped on, whatever is left on it.

Not switched off while a game runs: the button is dimmed and does nothing then if the switchboard is powered, and the game program refuses `"hold"` on `game/error`. The deck's 1s reset is allowed during a game (§10); a hold is not, since a game on a dark board cannot be played. Switching on is always accepted. Start powers a switchboard left off (§2). Dimmed too while the controller or the game program is offline. Every failsafe of the controller — the connection lost, the game heartbeat missed, a restart — powers the switchboard, and the button shows it.

# 12. The Board and the Log

## 12.1 Jacks and Labels

The switchboard has 30 station jacks, numbered 1–30, and 10 trunk jacks, numbered 1–10. The game has 22 station circuits and 8 trunk circuits. Which station circuit is cabled to which station jack is Mark's choice, and it can change when he recables. It is recorded in script.yml's top-level `jacks:` list, one item per station jack, together with the label on the board at that jack whether or not anything is cabled to it:

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

(Illustrative. The real assignments are Mark's.) A station entry carries `number:` and nothing about the board. Trunk circuit n is cabled to trunk jack n for n = 1–8, fixed, and trunk jacks 9 and 10 carry nothing. No trunk jack has a label. A station jack that `jacks:` does not list has no circuit and no label. `guest:` is for the operator's guest list card and the game does not read it.

The script.yml loader rejects the file, and the game program refuses to start, if:

- `jacks:` is missing or empty, or an item has a key other than `jack:`, `label:`, `station:` and `guest:`;
- an item's `jack:` is not an integer from 1 to 30, or is the same as another item's;
- an item lacks `label:`, or its label is empty, or it has a `guest:` that is empty;
- an item's `station:` is not a station entry, or names a station another item already names;
- a station entry is named by no item in `jacks:`, or carries any key but `number:` — a station carrying `switchboard:` or `label:` fails with a message saying where they went, rather than drawing a board with no labels;
- a station's `number:` is outside 1–22, or the same number as another entry (the loader's existing check);
- a scene lacks `active:`, or its value is not `true` or `false`, or an active scene's `after:` names an inactive one.

The loader is the one `tts_task.md` §3.1 specifies, which the game program imports. These checks go into it, so the TTS run and the game both see them.

A station circuit that no entry names is not on any jack as far as the game knows. It has no tile, and a ring or hook on it goes in the log as a stray. A station entry that no scene uses is still drawn, so a stray ring on it is seen.

The game program reads wavs for active scenes only, and refuses to start if one is missing. An inactive scene's wavs are not looked for.

The game program publishes the map retained under `board/` (`mqtt.md` §6.1): each jack's label, and the circuit it carries or empty. A labelled jack with nothing cabled has a label and an empty circuit. The page builds the board from those topics alone. A change to script.yml takes effect when the game program restarts.

Recabling a station circuit to a different jack moves its `station:` from one item in `jacks:` to another. The labels stay with the jacks, and nothing else changes.

## 12.2 The Circuits Fitted

The switchboard is being built a board at a time, so the game program is told how many circuits exist: `stations` and `trunks` in its configuration file, each overridden by `--stations` and `--trunks` on its command line. Stations are the first `stations` of 1–22, and station 24, the real telephone, when `stations` is 22; trunks are the first `trunks` of 1–8; the defaults are all of them.

**Out of service.** A fitted trunk listed in the configuration file's `[out_of_service.trunks]` table, by number with the reason as text, is never rung in on; the game picks only from the rest, and logs each one listed at start. A call out goes on any trunk the operator takes, since the faults so far — a ring relay that does not latch, a lamp that does not light — matter only to a call rung in. A fitted station listed in `[out_of_service.stations]`, the same way, is in no call at all: a scene calling from it or to it is left out, as a scene on an unfitted station is, with its `after:` chain and its place in the tutor's lessons, and each one listed is logged at start.

**Scenes left out.** A scene is left out of the game if its calling or called line is a station that is not fitted, or if it needs an outside line and `trunks` is 0; an `after:` scene following one that is left out is left out as well, down the chain. Calls ring in and go out on trunks 1 to `trunks` only. The game program logs how many scenes it left out and why when it starts, publishes `game/stations` and `game/trunks`, and refuses a diagnostic on a circuit that is not fitted (§11.4).

## 12.3 The Log

`game/log` is the last 50 events of the game, newest first, one per line, as plain text: `HH:MM:SS` host time, a space, the call number in brackets where there is one, and the event.

```text
14:02:31 [7] success
14:02:10 [8] started pike-taxi: lobby → taxi
14:02:10 [7] connected
14:01:58 [7] dialled 275-5678 on trunk/3
14:01:41 [7] started lindqvist-canlis: room601 → canlis
14:01:40 page: gap 15
```

Logged: game start and stop; each call's start, connection, success or failure with its reason; dialled numbers; wrong connections; reshuffles and `after:` scenes dropped (§6.1); hardware faults the game sees (`ring_on_trunk`, `bad_dial`); client outages; each move of the loudspeaker to a call (§9.1); every accepted page command. It is a display, not the record — the SQLite session log is the record — and it is republished whole on each new event.

# 13. Setup

## 13.1 Serving the Page

nginx serves the page's files over HTTPS on 443 and reverse-proxies its MQTT connection, on the path `/mqtt`, to Mosquitto's WebSockets listener on loopback. The configuration, the certificate and the name are `mqtt.md` §9. The files:

```text
web/
  index.html      the page
  app.js          everything the page does
  style.css
  mqtt.min.js     the browser build of MQTT.js, copied from the npm package's dist/
```

`web/` lives in the repository beside the game program and is installed to `/srv/sbgame/web`, readable by nginx's worker. MQTT.js is a local copy and never loaded from a CDN: on the road the travel router may have no internet, and the page would load without its library. The version copied is recorded in a comment at the top of `index.html`.

The bookmark is `https://game.kr3am.org/`. The name resolves to the host at home and on the travel router alike: from a public Route 53 record at home and from the travel router's own host entry on the road (`host/README.md`, "The name"). The certificate is a real one, so Safari loads the page with no warning. The page connects to `location.host` with the path `/mqtt`, over `wss://` when it was loaded over `https:` and `ws://` otherwise, so no address, port or scheme is written into it, and it works unchanged at home and on the road. It connects as the broker user `sbgame-web`; the password is in `app.js`, which anyone who loads the page can read. That is accepted: the access list, not the password, is what stops the page commanding hardware (`mqtt.md` §9, §11).

The path is what lets nginx tell the two apart: `/mqtt` goes to Mosquitto, everything else is a file.

## 13.2 What the Game Program Checks

Every value arriving on `game/+/set` is checked by the game program; the access list keeps the page off hardware topics but does nothing about a bad value on the game's own. A value out of range is clamped and the applied value echoed; a value that is not understood — `run/set` other than `"on"` or `"off"`, `pace/set` other than `"tutor"`, `"manual"`, `"auto"` or `"listen"`, a number that does not parse — is dropped, logged, and reported on `game/error`. Accepted commands are logged with `page:` in front (§12.3). A command from the Stream Deck arrives on the same topic and is logged the same way; the game program cannot tell them apart and does not need to.

## 13.3 Commissioning

Before step 1: the certificate is issued (`host/README.md`, "The certificate"), nginx is configured and enabled, the Route 53 A record for `game.kr3am.org` points at the host, and the five broker users and the access list are in place. The deploy hook no longer has to be run by hand, because nginx reads the certificate from `/etc/letsencrypt/live` directly and the hook only reloads it.

1. Restart Mosquitto and nginx after the §9 changes to `mqtt.md`'s configuration. Mosquitto's log shows two listeners open, MQTT on 1883 and WebSockets on 127.0.0.1:9001; `ss -ltnp` shows nginx on 443. Mosquitto's WebSockets listener is deliberately on loopback: nothing off the host reaches it except through nginx.
2. From another machine on the LAN, `curl https://game.kr3am.org/` returns `index.html` with no certificate error. That checks the name, the certificate and nginx together.
3. The controller, the audio program and the game program still connect. `allow_anonymous false` refuses any client without credentials; control.md §9.1 and audio.md already use them, but check the usernames against the access list.
4. As `sbgame-web`, publish `sbgame/station/1/hook/set` `on`. Station 1's relay does not move and `hook` does not change: the broker has dropped it silently. Then `sbgame/game/run/set` `on`, which is accepted.
5. Lock the iPad for a minute and unlock it. The page reconnects and shows the full state without a reload.
6. Stop a game with a station off-hook, a trunk ringing and a file playing. Everything releases, and the tallies stay. A trunk's lamp and buzzer, rung in and not answered, go out with the 1s power cut, and the switchboard comes back with no lamp lit. With no game running, hold the deck's key 5 for 2s with a trunk lamp lit: the same. Then during a game with a call connected and talking: the call carries on after the cut, neither party cut off, and the call slot unchanged.
7. Kill the game program. The page shows it offline within 2.5s and keeps showing the hardware.
8. **Wiring check**. With no game running, put an answering cord into each cabled station jack in turn and ring it. The tile for that jack flashes. If another tile flashes, or none does, the cable and script.yml's `jacks:` disagree about that station. A labelled jack with nothing cabled looks like any other at rest, so a tile that never flashes is not by itself proof of a fault — tap it: its circuit reads none. For trunks, seize each trunk jack in turn: the tile for that jack shows busy. This checks the cabling against the script using only topics that already exist.
9. **The loudspeaker follows the call**. Start a game. The page shows the monitor's source as `tap`. Start a call from a station and answer it: the source changes to that station's label and the audience hears the request. Put the call through and release the operator: the conversation stays on the loudspeaker. Do the same for a call from a trunk, and confirm the source does not change while the trunk is ringing. Stop the game: the source returns to `tap`.
10. **Certificate renewal.** `sudo certbot renew --dry-run` runs the DNS-01 challenge against staging and the deploy hook without spending an issuance, and must report success. nginx rereads the certificate on `systemctl reload`, so no client is disconnected.
11. **The Stream Deck**. With `sbgame-streamdeck` running and the deck plugged in: the keys draw within 2s. Start and Stop start and stop a game, Stop only on the second press. The pacing key switches the page's pacing. Turn each dial one detent each way and check the page shows the step, then turn `gap` quickly through ten detents and check it moves 50s. Next Call starts one call per press, however fast it is pressed. Stop the game program: keys 1–7 grey within 2.5s and key 8 shows the game red. Unplug the deck and plug it in again: it redraws with the current state. `systemctl stop sbgame-streamdeck`: the deck goes blank. Then hide the page's controls with its Controls switch (§11.1), reload the page, and check they stay hidden and the line reads the game's state.
12. **Tutor mode.** With the tutor's lines rendered and in `/srv/sbgame/wav`, and the loudspeaker on: choose Tutor on the pacing key. Start a game: the tutor introduces the board a part at a time, key 8 reads More Help and takes the tutor to the next part, and Next Call at any point ends the introduction and deals the first call. Take a call from a room, one in on a trunk, and one out, following the tutor, and check that every step is prompted before it is due and that the tutor never speaks while the page shows a line `listening`. Leave a lamp lit: the tutor says it twice more, 20s apart, then stops. Finish a call and leave a cord in: Next Call is refused and the page's error says why; pull it, and the tutor asks for Next Call. Set the level of the tutor's voice against the calls' with `--monitor-file-trim` (audio.md §10.4), with the monitor at the level the room wants for the calls. Choose Manual mid-call: the tutor stops at once and the call goes on.

# 14. Open Items

- **Calls before connection** (§5.5). Deferred by Mark.
- **Timeouts from the page.** The §4 timeouts are configuration. If play-testing wants them changed between players, they become three more `game/…/set` topics.
- **Audience view.** A second page, or a mode of this one, for the room: the tallies large, the calls in progress, nothing diagnostic. Same topics; no host change.
- **Cords drawn as lines** between tiles rather than shown by colour. Only if the colour pairing is hard to read on the iPad.
- **Script names or jack labels.** script.yml's station keys (`room463`) and the board's labels (`463`) name the same thing twice. The calls panel and the log use script names, and the tiles use labels. If that reads badly, the game program can put labels in the call slots instead.
- **The loudspeaker leaving a conversation** (§9.1). In auto pacing, the operator answering the next call takes the audience away from the current conversation, possibly mid-sentence. The alternative is to stay on a call until its conversation ends and then move to the most recently answered call, at the cost of missing that call's request. At present it moves at each answer. Wants listening with an audience. Listen pacing sidesteps it when the conversations matter more than the pressure.
- **Settings across restarts.** Pacing values return to the configuration file's when the game program restarts (§5.4). If that is annoying, the game program can read its own retained values back at start.
- **Dial push** (§10). Unused. Candidates: a finer step while held, or back to the configured value — the program does not know the configured values, and the game program would have to publish them.
- **Error on the strip** (§10). 5s may be too short to read a long error, or too long to lose the dials during a game. Wants use.
- **Next Call on GPIO36** (`control.md` §11). A third way to publish `next/set`, needing the same guard as the page and the deck.
- **The tutor and a wrong move** (§7). The tutor does not say a jack or a number is wrong; the prompt only comes round again. A line per jack for "that is not room 403" would be one more template. Wants play with a new player first.
- **The tutor's voice in the headset.** The tutor is on the loudspeaker, which the audience hears too. If the room wants the tutor private, the headset needs that voice kept off the line the operator is bridged to, which the tap cannot do (§7).
- **Screen wake lock** (§11.3). Possible now that the page is served over HTTPS: the page would hold a wake lock while `run` is on, and Auto-Lock could stay on. Whether it holds reliably for a Home Screen page on the iPad's iOS version is to be tried before it replaces the Auto-Lock instruction.

# 15. Revision History

## 15.125 Changes in Rev 125

— Left before the request, a room waits for her (§3.1, §3.3), Mark's report, 2026-11-25: twice in one game the operator answered a room, her key dropped as her greeting ended, and the game cut the call off within a second, before the request was heard; answering again found nothing. Between her answer and the end of the request, her leaving now does what it does after the request in a call to the operator: the room stays off-hook, waits 30s (in tutor pacing, as long as it takes), asks "Hello? Operator? Are you there?" when she is back, and makes its request once she has spoken. A trunk caller is cut off as before.

— An unanswered trunk call rings again (§3.1), Mark's report, 2026-11-25: a call in on trunk 2 got its one short ring while he was busy, and only its lamp showed it until he stopped the game with the deck reading "Next: waiting". A trunk not yet answered now gets another short ring every 10s until she answers or the answer timeout ends it, but not while a front cord is in it.

— Code consequence, for Claude Code: `RERING` and `_rings_again()` in flows.py, started and cancelled by `_open_call()`, which now retries `_request()` after `_waits_for_her()`, whose message names what she left before; `test_she_leaves_before_the_request_and_comes_back`, `test_she_leaves_a_trunk_before_the_request`, `test_an_unanswered_trunk_rings_again`, `test_a_trunk_with_a_cord_in_it_rings_no_more`.

## 15.124 Changes in Rev 124

— The public line rung while no game runs (§8.1), Mark's request, 2026-11-24: people who know trunk 8's number sometimes call when nobody is playing, and the ring latched the trunk's signal, lamp and buzzer, until someone noticed. The game now logs the ring, and resets the switchboard if nobody answers within 30s of the first ring, once the line has been quiet for 10s.

— Code consequence, for Claude Code: `PUBLIC_ANSWER`, `PUBLIC_QUIET`, `Game._public_watch` and `Game._public_rung()` in game.py, started from `_on_change()`; `test_the_public_line_rung_while_stopped`.

## 15.123 Changes in Rev 123

— Started again soon, the shuffle goes on (§2, §6.1), Mark's request, 2026-11-24: a player often stops a game and starts again at once, and each Start shuffled afresh, so the same sitting heard scenes over. A Start within `resume_within`, 600s by default, deals on from the shuffle where it stopped. The scenarios played stay played, and a tutored game skips a lesson already dealt from the shuffle. Tallies, call numbers and the session record start new as before; the record keeps the seed and gives the scenes left as the first shuffle.

— Code consequence, for Claude Code: `Config.resume_within` and its check; `Deck.left`; `Game._stopped_at`, `_orders_seen` and the resume in `Game.start()`; `resume_within` in host/etc/sbgame/game.toml; `test_started_again_soon_the_shuffle_goes_on`.

## 15.122 Changes in Rev 122

— A trunk taken during the request (§3.5), found on the switchboard 2026-11-23, call 35, beaumont-times: the operator took trunk 1 a second before the caller finished asking for the Times, and got no dial tone. Routing began with the trunk already up, so it was counted with the cords left in from other calls (Rev 60) and never taken as this call's. A trunk up before routing is now this call's once it is patched to the caller, since a cord from the caller's own jack belongs to no other call.

— Code consequence, for Claude Code: `Ctx.out_caller`, set in `_route_out()`, and `_fresh()` in flows.py; `test_a_trunk_taken_during_the_request`.

## 15.121 Changes in Rev 121

— The greeting said short (§7.4), Mark's request, 2026-11-23: a request's greeting, "Say: How may I connect your call?", is said in full the first time and as "Greet the caller." from the second. Said in full every time, it was the longest prompt a player heard over and over, for a line learnt after one hearing. No brief step: "Greet the caller." is already as short as a prompt gets. The words do not matter to the game, which listens for speech and a pause.

— Code consequence, for Claude Code: `Tutor.greeted` and `Tutor.say_key()` in tutor.py; `test_a_greeting_in_full_once_then_greet_the_caller`. No new line: `tutor.greet` was rendered already.

## 15.120 Changes in Rev 120

— Shutting down the host from the deck (§10.1, §10.2), Mark's request, 2026-11-20: the first dial pushed and held 3s with no game running runs `systemctl poweroff`, so the host can be shut down at the end of a day without a keyboard or a VNC session. 3s, a second longer than the switchboard reset's hold, since it cannot be undone from the deck. Allowed with the game program offline, so a hung game cannot prevent it. A push of any dial did nothing before.

— Code consequence, for Claude Code: `on_dial_push()`, `holding_shutdown()`, `shutdown_due()` and the strip's hold and "Shutting down" in streamdeck.py, with `poweroff()` in `run()`; `test_shutdown_the_first_dial_held_3s`. Host: `host/etc/polkit-1/rules.d/50-sbgame-deck-poweroff.rules`, allowing `sbgame-deck` the three logind power-off actions.

## 15.119 Changes in Rev 119

— Prompts in three levels (§7.4), Mark's request, 2026-11-14: in full the first time, brief the second, terse from the third — "Rear cord, push near switch." Rev 55 said a prompt in full twice before its short form, and the short form for good; a player who had it after one hearing heard the long line again, and the short one never got shorter. A wrong cord, or a prompt that ran out of repeats, sends that step back to brief for its next time. The terse forms keep the switch movement, the part players forget; a terse `dial` is the number in digits.

— Code consequence, for Claude Code: `tutor: terse:` in script.yml, rendered as terse.<key> (`TERSE`, `SHORT` in tts/script.py; a number line may take `{number-digits}` alone); `LEVELS`, `DEMOTES` and `Tutor.demote()` in tutor.py, called by `_hint()` in game.py and at a prompt's last repeat; `test_tutor.py`.

## 15.118 Changes in Rev 118

— A line that cannot hear is not a pulled cord (§4), 2026-11-14. Twice that morning a long-distance call in conversation failed as `cut off` the instant the operator answered another lamp (10:01:59, 10:54:27): for 170ms her headset was keyed on two pairs, every line on them heard two others and reported `peer` `"ambiguous"`, which the game took at once as the cord gone, and hung the guest up. At 09:52 a howl on the loudspeaker swamped station 14's pilots; `op` went off with `peer` `"deaf"`, and a second later the call was cut off with the operator still on it. `"ambiguous"` is now treated as `"deaf"` was, and a `peer` going empty or `op` going off while the line cannot hear counts only after a second of hearing again, at most 5s.

— A busy line or an engaged room is handled once she has told the caller (§3.3, §6.6, §4), Mark's decision, 2026-11-14. In the panic two calls to an engaged front desk and housekeeping failed as `cut off`: he told the guest and pulled the cord, as an operator in a rush does; the same rule as a call to the operator (Rev 116). Busy trunks too.

— A caller held before it is put through waits 30s, not 10s, and asks "Hello? Operator? Are you there?" when she is back after 10s or more (§3.5, §4), Mark's decision, 2026-11-14. Hale asked for Sunny Hill Pizza, he went to answer the time-and-charges call on another trunk, and Hale hung up 11s later. A call to the operator left before a reply waits 30s too.

— After a wrong number, her first return to the caller gets the request again, her second the caller giving up, `not connected` (§3.5), Mark's decision, 2026-11-14 (option 3). At 09:43 he dialled a wrong number for Martha's pizza, hung up the trunk and went back to her three times; she said nothing, each absence too short to ask again, and only the connect timeout would have ended it. A new reaction, `giveup`: "Never mind, operator. I'll try again later."

— A scenario's calls wait 90s to be answered (§4, §6.5), Mark's decision, 2026-11-14: in the panic Crane's lamp went unanswered for 60s while he answered six others.

— Code consequence, for Claude Code: `Board` (board.py) treats `"ambiguous"` as `"deaf"` and defers a held fall while a line cannot hear (`DEAF_MAX`); `_replies()` returns False once she has left after speaking, in `_found_engaged()` and `busy_scene()`; `ABANDON` 30s, `HELD`, `FLICK`, `GaveUp` and the asker's `giveup` in `_unless_abandoned()` (flows.py); `scenario_answer_timeout` in config.py and game.toml, applied in `_run_call()` (game.py); `giveup` in tts/script.py's `REACTIONS` and script.yml's `reactions:`; tests.

## 15.117 Changes in Rev 117

— A reply counts from when she starts it, not when she finishes (§3.3), 2026-11-13. In the first panic under Rev 116, five calls to the operator failed as `cut off` though she had replied: she said something short and pulled the cord 0.6–1.6s into it, before the speech detector reported the silence that ended it, and the game took her as having left before replying.

— Code consequence, for Claude Code: `to_operator()` counts a reply when she leaves during a wait for one in which the listen reached `speech`; `test_flows.py`.

## 15.116 Changes in Rev 116

— A call to the operator succeeds once she has replied, and she may leave before replying and come back (§3.3, §4), Mark's decision, 2026-11-13. Calls to the operator had never succeeded in play: 0/16 on 2026-11-08, 0/8 on 2026-11-12 and 0/8 on 2026-11-13. A call counted only if she stayed through the punch line, and an operator in a rush says something short and pulls the cord, as he did ("I said something curt and cut the guest off"). Her key off for a second after the request was a pulled cord, so she could not leave a guest to answer another lamp and come back. Now a reply is the success and the punch line a bonus; leaving before a reply, from a room, lights the lamp again and the guest waits 10s, then asks "Hello? Operator? Are you there?" when she returns. Under this rule all eight of 2026-11-13's calls to the operator would have succeeded. The review is in `panic-review.md` (gitignored, beside `TODO.md`).

— Code consequence, for Claude Code: `to_operator()` keeps its place in the conversation across her leaving; `_operator_speaks()` returns whether she spoke; `_waits_for_her()` and `BACK_PAUSE` in `flows.py`; `test_flows.py`.

## 15.115 Changes in Rev 115

— Speech that runs without a silence for 3s in a greeting, or 4s in any other wait for the operator, is taken as ended (§6.2), Mark's decision, 2026-11-13. In the panic played 2026-11-12 in a quiet room, the speech detector held the operator's greeting or reply in `speech` for 4.7–12.2s in five calls; the caller waits for the silence before speaking, so it never spoke, and she left: beaumont, thornhill, crane, lobby and martha. Greetings that ended took 1.1–2.6s. The likely cause is the loudspeaker, which plays the line she is talking on, through her headset microphone; `audio.md` Rev 38 ducks it while a listen runs on its source. The cap stays as the safety net. The review is in `panic-review.md` (gitignored, beside `TODO.md`).

— Code consequence, for Claude Code: `max_speech` on `hear()` in `scenes.py`; `GREETING_MAX` and `SPEECH_MAX` in `flows.py`, passed by `_operator_speaks()` and by the asking again; `test_flows.py`.

## 15.114 Changes in Rev 114

— Stories are dealt in order, `follows:` on a scene (§6.1), Mark's request, 2026-11-04. Some scenes tell a story across the game: `nbn-valet` makes sense only after `nbn-kaplan`, Pike leaves for his train in `pike-taxi` and should get no calls after it, and the Hales put up the do-not-disturb sign before housekeeping asks about it. The shuffle dealt them in any order. `after:` was not the way: it starts a scene on a timer after another ends, where these are ordinary deals that need only come later. Nineteen scenes carry it, in eleven stories: North by Northwest, Pike, the Hales, the Colonel and Mrs. Pemberton, Dobbs, Mrs. Albright's roses and pearls, Finch, Lindqvist's two restaurants, Lindqvist's truck, and Mary Smith.

— Code consequence, for Claude Code: `follows` in `script_data.py` and `tts/script.py`; `_ready()` and `_to_come()` in `deck.py`, and what `deal()` is given by `game.py`; `follows:` on the scenes in script.yml; `test_game.py`.

## 15.113 Changes in Rev 113

— A scenario can bound how many calls wait on the operator at once, `live:` on its first scene (§6.5), and `panic` has `live: 3`, Mark's request, 2026-11-04: the panic's calls, four to eight seconds apart, came in a little too fast even for him. Slowing them further would also slow the panic for an operator who keeps up; the bound slows it only for one who falls behind. Waiting means not yet connected (§3.3), Mark's decision: a call that is connected and talking leaves her free.

— Code consequence, for Claude Code: `live` in `script_data.py` and `tts/script.py`; the wait in `_after_timer()` in `game.py`; `live: 3` on `panic` in script.yml; `test_game.py`.

## 15.112 Changes in Rev 112

— A caller says its request again when she comes back to it (§3.5), and reorder on a trunk left up stops while the trunk is patched to a line (§3.4), Mark's request, 2026-11-03. Found on the switchboard that day, in `lobby-pike`: she answered the lobby with a cord pair whose front cord was still in trunk 1 from the call before. The reorder Rev 110 had put on that trunk came in 2s into the lobby's request and covered it. She left the lobby to answer another call, came back 35s after the request, and heard nothing, since the guest had asked once and was waiting to be put through. It looked like the game had frozen.

— Code consequence, for Claude Code: `AWAY` and `returns()` in `_unless_abandoned()` in `flows.py`; `_trunk_tail()` in `game.py`; `test_flows.py`, `test_game.py`.

## 15.111 Changes in Rev 111

— The trunk sweep holds each lamp 3s before the reset (§11.5), Mark's request, 2026-11-03. It cut the power as soon as the 1s burst ended, so a lamp that lit only while ring was applied looked the same as one whose ring relay had latched. Found the same day, when trunk 2 rang in for `ld-pike` and its lamp did not stay lit. Now a latched lamp stays lit for the 3s after the burst, and one that did not latch goes out with the burst. The wait before the next trunk is 0.5s, where it was 1s.

— Code consequence, for Claude Code: `LATCH_HOLD` and `TRUNK_PAUSE` in `sweep.py`; `test_game.py`.

## 15.110 Changes in Rev 110

— A trunk left up after its call gets reorder (§3.4), Mark's request, 2026-11-03: when the long-distance operator had given time and charges and hung up, the operator heard nothing on the cord, where a real line would give her the fast busy after a few seconds. Now, 4s after a call on a trunk ends, the trunk gets reorder while her cord is still in it, until she takes it down.

— Code consequence, for Claude Code: `REORDER_AFTER` and `_trunk_tail()` in `game.py`; `test_game.py`.

## 15.109 Changes in Rev 109

— Busy tone stops after four bursts, 3.5s, before the game listens for the operator (§3.2), Mark's decision, 2026-11-03. Found on the switchboard that day, in `beaumont-times`: the trunk gave busy tone, he told the Colonel the line was busy, and the Colonel never answered. With the front cord still in the trunk, the tone reached the caller's line; the speech detector reported speech 0.4s after the tone began, and never silence while it played, so the game waited for her to finish for 13s, until she took the cords down and the call failed as `cut off`. It worked only for an operator who took the front cord out first and kept her key thrown, which a newcomer will not know to do. A real exchange keeps busy tone on until the line is released; that waits on the speech detector learning to ignore the tone.

— Code consequence, for Claude Code: `BUSY_HOLD` and `busy_scene()` in `flows.py`; `test_flows.py`.

## 15.108 Changes in Rev 108

— The automatic pacing's starting values are `ramp` 1, `floor` 8 and `jitter` 30 (§5.4), Mark's request, 2026-11-03, for a newcomer's game. They had been 0, 5 and 0 since each was introduced, which left auto at a fixed 20s however long a game ran, with a rhythm a player could count. Now the game gets busier as it goes, as the ramp was meant to make it, and it reaches its floor at the twelfth call connected, about ten minutes into a game like the one played that day. The floor of 8s, not 5s, is because the gap is counted from the connection: at 5s the next call rang while the last conversation was still under way, which is steep for a first game. Each value can still be changed from the deck or the page during a game.

— Code consequence, for Claude Code: the defaults in `config.py`, `host/etc/sbgame/game.toml`, and the stepper help in `app.js`.

## 15.107 Changes in Rev 107

— Two waiting `after:` scenes that need the same line or person no longer wait for each other for ever (§6.1), Mark's decision, 2026-11-03. Found on the switchboard that day: `dobbs-callback`, due at 13:29:59, and the panic scenario's `panic-dobbs`, due at 13:30:01, both need Mr. Dobbs and room 105. Each found the other holding them, so neither started. Because `panic-dobbs` is in a scenario, the automatic schedule waited for it (§6.5), and no further call was dealt until Stop. Now, once both delays have run out, the scene in a scenario goes first, and otherwise the one due first. The scenario goes first so that its calls still come close together. Had `panic-dobbs` waited for the whole of `dobbs-callback`, the panic's calls after it would have waited too.

— Code consequence, for Claude Code: `_after_timer()` and `_after_rank()` in `game.py`; `test_game.py`.

## 15.106 Changes in Rev 106

— `bad_dial` does not light a trunk's tile (§11.1), Mark's request, 2026-10-31. It stays set until the next good digit, so a misdial would leave the tile showing a fault after the call had moved on. The tile's panel still shows it.

— Code consequence, for Claude Code: `tileState()` in `app.js`.

## 15.105 Changes in Rev 105

— Only the public line's tile flashes on `ringing` (§11.1), Mark's request, 2026-10-31. Rev 104 flashed any trunk's, which on the others could only be the player ringing one with a cord, and looked like a call coming in. The game publishes the trunk as `game/public_trunk` (mqtt.md Rev 50).

— A trunk's `fault` now shows on its tile, as §11.1 has always said (Mark, 2026-10-31). The page tested it for `"on"`, and the controller's values are `"ring_on_trunk"` and `"bad_dial"`, so it never did.

— Code consequence, for Claude Code: `tileState()` in `app.js`; `game/public_trunk` in `game.py`; `test_game.py`.

## 15.104 Changes in Rev 104

— The page shows a call ringing on the public line (§8, §11.1), Mark's request, 2026-10-31: a trunk tile flashes while `ringing` is on (mqtt.md Rev 49), so he can tell from the iPad that a call has arrived. It flashes only with each ring, about 2s in 6s, and the game itself takes no action on it.

— Code consequence, for Claude Code: `tileState()` and the trunk's detail panel in `app.js`.

## 15.103 Changes in Rev 103

— The trunk sweep cuts the switchboard's power for 1s after each ring (§11.5), Mark's request, 2026-10-30, so each trunk's latched ring relay is reset and its lamp goes out before the next is rung. The next trunk follows 1s after power returns, so a sweep still takes 3s a trunk, and the lamps no longer stay lit behind it. The station sweep is unchanged.

— Code consequence, for Claude Code, made in the same change: `sweep.py`; `test_game.py`.

## 15.102 Changes in Rev 102

— The tutor's `{number-digits}` is said as a person today says a number (§7), Mark's request, 2026-10-30: the first three digits, a pause, then the last four as they are said with the exchange name. "That's seven eight four, five thousand", where Rev 69 had "seven, eight, four, five, zero, zero, zero". Zero in those digits is now "oh", as with the exchange name, where Rev 69 had "zero".

— Code consequence, for Claude Code: `dial_digits` in `tts/script.py`. The dial lines are rendered again. No game program change.

## 15.101 Changes in Rev 101

— A wrong-cord line over a tutor's prompt no longer fails the call (§7.7), Mark, 2026-10-30. Played at 18:04: 15s into `ring-rear-room204`, 16.4s long, the operator rang the trunk. `rang-trunk` replaced the prompt on the loudspeaker, the prompt never saw its own end, and at its 19.4s deadline its timeout failed the call as `not connected`, in tutor pacing, where nothing fails for being slow (§7.1).

— Code consequence, for Claude Code: `say()` in `scenes.py` returns when another `say()` replaces it; `test_tutor.py`.

## 15.100 Changes in Rev 100

— §7 and §8 rewritten to be read, Mark's request, 2026-10-30: long paragraphs broken into lists and tables, and subsections added to §8. Where the rename of Rev 98 left "the call still needs the tutor's" and "never heard as the tutor's", the meaning is restored: the operator in both. No behaviour is specified differently. The page's one command beyond the game program, the public-address check, is added to §1, and the setup references follow `mqtt.md` Rev 48 to `host/README.md`.

— No code consequence.

## 15.99 Changes in Rev 99

— The document reordered to be read, Mark's request, 2026-10-30: the game first, then a call, tallies, pacing, scenes, the tutor and free calls; then the loudspeaker, the deck and the page; installation, checks and commissioning last. §3 is new and walks through one call, gathering the stages, "connected", hanging up, wrong moves and the choice of trunk from §4.3, §4.6, §5, §6.1 and §6.5 as they stood. §1.1 defines the terms. Tutor mode, the deck and the circuits fitted are divided into subsections. Sections are renumbered; references in §15 follow, here and in the other documents and the code's comments, so an old entry's number names where that subject now is. No behaviour is specified differently.

— Code consequence, for Claude Code, made in the same commit: comments' section numbers only.

## 15.98 Changes in Rev 98

— Terms made single-valued, Mark's request, 2026-10-30. "The deck" is the Stream Deck alone, and the order of scenes is the shuffle. A set of calls under way is "calls in progress", not "the board". The tutor is named, and "she" is the operator; the long-distance operator is named too. "Scheduled pacing" is auto or listen, and "auto" the one pacing, labelled Automatic on the page. The strings the game program publishes are unchanged.

— No code consequence.

## 15.97 Changes in Rev 97

— Revision numbers taken out of the body, Mark's request, 2026-10-30: the document now says what is, and §15 says when it changed and what it was before. No behaviour is specified differently.

— No code consequence.

## 15.96 Changes in Rev 96

— Out-of-date text corrected, Mark's request, 2026-10-30: §1's note that no game program specification exists; §5.1's "until the deck is commissioned"; §6.2's "Two keys" before a list of four; "at Rev 1" in §4, §11.3 and §14; Tutor added to the pacing lists of §11.1, as the page has it; §13.3's count of broker users; §13.3 step 2's `http_dir`. §13.3 step 10 keeps only the renewal check, and the Stream Deck test log of §13.3 step 11 moves to §15.15. The settled "Wrong party answers" comes out of §14.

— No code consequence.

## 15.95 Changes in Rev 95

— The document made readable, Mark's request, 2026-10-30. The line under the title had grown to 3,108 characters of accumulated topics, and now gives only the revision. The subsections of §5, §3 and §11 are put in numerical order, their numbers unchanged. The changes in each revision move from §1 to this section at the end of the document, newest first, where Rev 1 to Rev 18 had been in ascending order followed by Rev 94 down to Rev 19. Each section is renumbered from §1.N to §15.N; the text of each is unchanged, except that §4's reference to Rev 60 now reads §15.60. A new revision is added at the top of this section, and the line under the title changes only its number.

— No code consequence.

## 15.94 Changes in Rev 94
— A call in on a trunk is answered only when the trunk is seized as well as hearing the operator (§9.1), 2026-10-27. Played on the switchboard at 17:43, `times-pike`: the operator put the rear cord into trunk 2 and keyed in. `trunk/2/op` came on with `seize` off; the game took that as the answer, listened, and played the caller's first line at 17:43:39.5, 0.3s after the tutor began `rear-in-trunk`, so she talked over the caller. On the 551 an outside caller is not answered through a rear cord, since nothing seizes the trunk. The caller now waits, silent, until the front cord is in; the tutor's line plays alone. In tutor pacing `answer-trunk` likewise waits for `seize` alone, where it took `op` too. Played again at 18:03 with the rear cord first, then the front: the seizure came, but the listen for her answer, started 0.14s after it, never ended; that was the speech detector's floor, taken from the unseized line, and is audio.md Rev 32.

— Code consequence, for Claude Code: `_answer()`; `test_flows.py`.

## 15.93 Changes in Rev 93
— A rear cord plugged into a trunk is told by the tutor (§7.7), Mark, 2026-10-27: "You have plugged a back cord into an outside trunk. Pull the cord out of the trunk jack and use the front cord instead." A rear cord does not seize a trunk, so a trunk that hears the operator (`trunk/<n>/op` `"on"`) while `seize` is `"off"` has one in it. Measured on the switchboard: rear cord of a pair in trunk 1, operator keyed in, no station on the pair: `op` on, `seize` off, `peer` empty. With a station off-hook on the same pair's front cord, trunk 1 seized and the two heard each other as for a correct patch, so that case cannot be told apart and is not caught; the player usually keys in after plugging in, which is. The condition must hold for 2s: a front cord's seizure comes in milliseconds, but when one is pulled with the operator in, `op` outlasts its seizure by the 1s a line's going away is held (§4, Rev 45), and 1s more is allowed beyond that.

— Code consequence, for Claude Code: `rear-in-trunk` in `TUTOR_KEYS` and script.yml; `Game._rear_check()` in the board watch; `test_game.py`. The line needs rendering.

## 15.92 Changes in Rev 92
— In tutor pacing a caller left alone before connecting does not hang up (§4, §7), Mark, 2026-10-26. The session log has 10 calls of 663 failed that way, 4 of them tutored (10-17, 10-21), where the 10s ran on while she spoke and while the player thought. Tutor pacing already lifts the answer and connect timeouts, so that nobody fails for being slow while she teaches; this was the clock left. Checked at each expiry, so a pacing changed mid-call is followed. Other pacings keep the 10s.

— Code consequence, for Claude Code: `_unless_abandoned()`; `test_tutor.py`.

## 15.91 Changes in Rev 91
— A wrong-cord line restarts the caller's wait (§4, §7.7), 2026-10-26. Played on the switchboard at 15:35: the operator answered the desk, released her key, rang the desk by mistake and heard the tutor's 7.5s `rang-caller`; by the time she rang the right room the desk had been alone for 10s and hung up, so the call failed as `cut off` with the room ringing. The caller left alone before connecting now waits its 10s (or 5s) afresh from the end of the tutor's wrong-cord line, if that ends later.

— Code consequence, for Claude Code: `Ctx.hint_end`, set by `Game._hint()`; the abandon watch in `_unless_abandoned()`; `test_flows.py`.

## 15.90 Changes in Rev 90
— `rang-caller` no longer names a cord (§7.7), Mark, 2026-10-26: "You rang the person who called you. Ring the other cord instead, the one in the jack of the person they're calling." A call between rooms may be answered with either cord, and the game cannot tell which cord is in which jack or which switch was pulled; Rev 88's "ring the front cord" was wrong for a call answered with the front cord. `rang-trunk` keeps naming the rear cord: a trunk works only with a front cord in it. Rerendered.

## 15.89 Changes in Rev 89
— Ringing the caller is seen by the audio program, not the ring detector (§7.7), 2026-10-26. Tried on the switchboard: `station/1/ring` stayed off through three rings of the front desk while it was the caller, because the station board's loop load pulls the ring from 80V to 17V, below the detector's turn-on. The ring reaches the station's capture channel all the same, and the audio program now reports it as `station/<n>/ringing` (audio.md Rev 30, mqtt.md Rev 46). The other two cases worked as written.

— `rang-outside` now says which way to push the switch (Mark): "Push the switch away from you, wait for dial tone, and dial." Rerendered.

— Code consequence, for Claude Code: `_wrong_ring()` watches `ringing` in place of `ring` for `rang-caller`; `test_game.py`.

## 15.88 Changes in Rev 88
— The tutor says when the player has rung the wrong cord (new §7.7), in every pacing, Mark's request, 2026-10-26. A common mistake, his own too: on a call in from a trunk, with the rear cord in the room's jack, the player rings the front cord out of habit, because on a call from a room the front cord is the one rung; and the front cord is in the trunk. The controller already reports ringing a trunk, as `trunk/<n>/fault` `"ring_on_trunk"` (control.md §8.3), seen 20 times in play since 2026-10-19; the game ignored it. Ringing the rear cord on a call from a room rings the caller's own station, which its ring detector reports. Three new lines under `tutor:`, said once a call each, as the wrong ring ends.

— Code consequence, for Claude Code: `rang-trunk`, `rang-outside` and `rang-caller` in `TUTOR_KEYS` and script.yml; `Game._wrong_ring()` in the board watch; `test_game.py`. The lines need rendering.

## 15.87 Changes in Rev 87
— The panic scenario's calls start four to eight seconds apart, where they started two to five (§6.5), Mark, 2026-10-25: a little too quick. Fifteen calls follow `panic`, so the whole scenario arrives over about 90s rather than about 50s.

— Code consequence: none; `delay: [4, 8]` on each `panic-` scene in script.yml.

## 15.86 Changes in Rev 86
— A free call fixes the loudspeaker's peer boost at 6dB (§8, §9.1), Mark's suggestion, 2026-10-25. The boost (audio.md §10.8, Rev 28) measures the caller's line against the called party's from the files played on each. A free caller is a live person, so nothing plays on the caller's line, the measurement never completes, and the boost stays at the installation's 12dB start, set for game calls. The free calls in the 18:04 loudspeaker recording of 2026-10-24 put the called party's files 6dB under the live caller on the real telephone. At a free call's answer the game program now publishes `audio/monitor/peer/set` `"6"` before the source; every other move of the loudspeaker publishes `"auto"` (mqtt.md Rev 45, audio.md Rev 29).

— Code consequence, for Claude Code: `Link.monitor_source()` takes the boost; `FREE_PEER_DB` in `freecall.py`; the simulator's echo; `test_game.py`.

## 15.85 Changes in Rev 85
— A call rung in on a trunk takes the free trunk whose `seize` changed longest ago, where it took the lowest-numbered free trunk (§6.5), 2026-10-24. In play: room 401's call to Ray's on trunk 1 ended when the room hung up, which dropped trunk 1's seizure with the operator's cord still in the jack. 0.7s later the next call, times-pike, rang in on trunk 1, into the jack with the old cord in it, and she saw no new call, only its countdown. The game cannot see a cord in a trunk jack without a loop, so the trunk just released is the one most likely still to have a cord in it; taking the one free longest leaves her time to clear it.

— Code consequence, for Claude Code: `Board.changed_at()`; `_free_trunk()` in `game.py`; `test_game.py`.

## 15.84 Changes in Rev 84
— A game call's misdial can be dialled again (§4), Mark's request, 2026-10-24: he was slow finding the cab company's number, got fast busy, replugged the trunk, and nothing happened, since the call had failed when he released it. Reorder still runs until she releases the trunk, but the call now goes back to waiting for a trunk, as after a wrong number (Rev 46): a fresh seizure gets dial tone and she may dial again. The call fails as `misdialled` only if the connect timeout runs out after a reorder; otherwise as `not connected`. The caller's patience while no trunk is up stays `ABANDON`, 10s. A free call's misdial already went back to routing (Rev 80).

— A trunk taken and not dialled gets reorder after 30s, where it was 15s (Rev 60), time to look a number up.

— Code consequence, for Claude Code: `_reorder()` returns `"released"` and sets `Ctx.reordered`; `Misdialled` is gone; `DIAL_FIRST` 30s in `flows.py`; the tests.

## 15.83 Changes in Rev 83
— Station 24, the real telephone, moves from jack 10 (room 405) to jack 18 (room 203), Mark, 2026-10-24 (§12.2, real_phone.md Rev 3). Jack 10 is uncabled.

— Code consequence, for Claude Code: `station: phone` on jack 18 in script.yml; the jack 10 check in `test_game.py`.

## 15.82 Changes in Rev 82
— In a game call a room answers 3s after the operator rings it, where it answered after 1.5s, the right party and a wrong one alike (§4), Mark's choice, 2026-10-24: 1.5s is short of a single 2s ring. A free call's room keeps its 4s (Rev 81).

— Code consequence, for Claude Code: `ANSWER_AFTER` in `flows.py`, in place of `WRONG_RING` and the two 1.5s waits.

## 15.81 Changes in Rev 81
— A room rung for a free call answers 4s after the operator rings it, where it answered at once (§8), Mark's request, 2026-10-24: Thornhill picked up almost as she keyed ring. Someone has to get to the telephone. A caller who hangs up in those 4s is gone and the room never answers. Game calls keep their 1.5s (§4).

— Code consequence, for Claude Code: `ROOM_ANSWER` in `freecall.py`.

## 15.80 Changes in Rev 80
— A free call's outside number is dialled as a game call's is (§8, §4 Rev 56), Mark's request, 2026-10-24: he paused after three digits to look up the rest, the 3s pause ended the number, and the real Lenny answered. The number is now seven digits, or `0` alone for the operator, and rings once 3s pass with no digit more. Short of that, 10s with no new digit gets fast busy; so does an eighth digit. Fast busy lasts until she releases the trunk or the caller goes.

— Code consequence, for Claude Code: `_number()` in `freecall.py`, `DIAL_PAUSE` 10s, `DIAL_SETTLE` 3s.

## 15.79 Changes in Rev 79
— In a free call the answerer listens from the start of each line, the greeting and "Hello?" included, not from its end (§8), with the audio program's echo canceller (audio.md Rev 26, §9.4), Mark's request, 2026-10-24. A caller who answers over the end of a line — "What power?" — is now heard: if they have finished by the time the line ends, the answerer comes in after the usual 0.4s; if they are still talking, once they stop. The listen allows the line's length plus the 3s or 7s of Rev 78 for speech to start. Where the canceller has not converged, as it may not have on a trunk, the listen hears nothing during the line, which is what Rev 78 did.

— Code consequence, for Claude Code: `_line()` in `freecall.py`, the listen sent before the line.

## 15.78 Changes in Rev 78
— A free call's answerer says "Hello?" 3s after the greeting or a line with no reply, where it waited 7s (§8), Mark's choice, 2026-10-24, from playing it. The line has no hybrid, so a caller who speaks over the end of a line is not heard (audio.md §9.3): Mark's "What power?" to Thornhill's "The man with the power" went unheard, and he waited over 4s before saying it again. A missed reply now gets "Hello?", which is natural after words that did not get through. After a "Hello?" the wait stays 7s, so a silent caller is not nagged. Lenny still says nothing: the original waits for the caller in silence, with room noise. Not adopted: going on to the next line after a silence, which Lenny never does.

— Code consequence, for Claude Code: `LISTEN` 3s and a new `LISTEN_AGAIN` 7s in `freecall.py`.

## 15.77 Changes in Rev 77
— The page drops everything it holds on every connect and rebuilds from the retained topics (§11.2, Connection). Found 2026-10-24: the iPad was away while the station and trunk boards were plugged in, and on return it still showed red lamps on circuits that had gone from `deaf` back to idle. A circuit's `peer` clears by deleting its retained topic, so a page that reconnects gets nothing for it and kept the `deaf` it had. The station sweep cleared them one by one, since each step makes a fresh `deaf` and idle. The one-second hold on `deaf` (Rev 52) is dropped with the rest.

— Code consequence, for Claude Code: the connect handler in `app.js`.

## 15.76 Changes in Rev 76
— In a free call the answerer comes in sooner after the caller stops (§8), Mark's request, 2026-10-23, from playing it: the game's extra listen at the end of a turn is 0.4s, down from 1s. With the audio program's own 0.8s to report silence (audio.md §9.2, the 0.5s hangover), the answerer now starts about 1.2s after the caller's last word, against about 2s before.

— Code consequence, for Claude Code: `TURN_END` in `freecall.py`.

## 15.75 Changes in Rev 75
— A party hangs up 1.5s after its last words, not the moment they end (§6.2), Mark's request, 2026-10-23: the time it takes to put a receiver back on its hook. After a call's last line, after the operator's closing words or where a call has none, and after an engaged caller's last line, the game waits 1.5s before its stations go on-hook and its trunk tone and files stop. A call cut off, timed out or failed still ends at once.

— Code consequence, for Claude Code: `HANG_UP` in `flows.py`, at the end of `_converse()`, `_closing()` and `_found_engaged()`.

## 15.74 Changes in Rev 74
— Free calls, "Lenny mode" (§8), Mark's spec of 2026-10-23 (`docs/lenny-spec.txt`, kept in §8's words): a real person lifts the telephone on station 24, or calls in from outside on trunk 8, the public line (trunk_circuit.md §4.5). The operator answers, and connects them to a room or dials an outside number. Whoever is there answers in character and then keeps the caller talking, the way Lenny does: a line of their own each time the caller pauses, in order, round and round, until the caller hangs up. An outside number the game does not know is answered by the real Lenny. Free calls run whether or not a game is running, alongside its calls (Mark, 2026-10-23), are not scored, and keep the lines and people they use out of the deck while they last.

— script.yml gains `freecall:`: per cast member, a `greeting:`, the `lines:` said once in order, and the `loop:` said round and round after them. `lenny`, the real Lenny, is a recorded cast member: his sixteen public recordings, transcribed, in his own order (§8). Each line is an utterance named `free.<cast>.<n>`.

— `public_trunk` in the configuration (default 8): the trunk the ATA feeds. No scene ever takes it, rings it or dials on it; it is where outside free calls come from.

— Code consequence, for Claude Code: `engine/sbgame/freecall.py`; the loader's `freecall:` (`tts/script.py`) and `build()`; the routing flows leave the public trunk and a free call's circuits alone; `_held()`, `_circuits_in_calls()` and the diagnostics count free calls; the Lenny recordings into `tts/recorded/`; script.yml.

## 15.73 Changes in Rev 73
— Station 24, a real telephone on station board 3 strip 8, cabled to switchboard jack 10 (§12.1, §12.2), following real_phone.md Rev 2 (adopted 2026-10-23), control.md Rev 38, audio.md Rev 24 and mqtt.md Rev 44. It is a station like the others in script.yml (`stations:` number 24, on jack 10), and the board draws it there. It is **fitted when `stations` is 22**, since it is on board 3 with stations 17–22; `stations` still counts the first N of 1–22. No scene calls from it or to it yet. What happens when someone lifts it and the operator answers, the free-call mode of real_phone.md §6, is to come in a later revision (Mark, 2026-10-23). Until then, plugging into jack 10 is an unscripted patch, as on any jack the game has no call for.

— The page draws station 24's tile from `lifted`, the phone's own hook, where every other station's comes from `hook`, which for 24 is the relay that connects the line to channel 24 (§11.1). Its panel shows `lifted` as well. Diagnostics reach it as any station: `hook` closes that relay.

— Code consequence, for Claude Code: the loader takes station numbers 1–22 and 24 (`tts/script.py`); `fitted_stations()` in `script_data.py`, used by `fit()`, the diagnostics, the sweep and the simulator; `out_of_service.stations` takes 24; the page's `fitted()` and tile; script.yml.

## 15.72 Changes in Rev 72
— A `public trunk` row in the health column (§11.1), under the public address, Mark's request, 2026-10-23: whether outside callers can reach the switchboard through trunk 8's Grandstream ATA (trunk_circuit.md §4.5). It reads `registered` when the ATA's FXS port is registered, `disconnected` when it is not, `offline` when the ATA cannot be reached, and `error` when anything else stops the service from finding out — or when the last look is more than 30s old, the service having stopped. Grey unless `registered`. From `host/public_trunk` (mqtt.md Rev 41, §6.3). No tap.

— Code consequence, for Claude Code: the row in `app.js`; the service in mqtt.md's consequence.

## 15.71 Changes in Rev 71
— The `public IP` row shows "offline" in place of the address when portland is not connected to the internet, and "error" when anything else keeps it from finding the address (§11.1), Mark's request, 2026-10-23. Rev 68 showed the last good address, grey, after a failed lookup, which looked like an answer. "offline" is `host/public_ip/error` reading `"offline"` (mqtt.md Rev 40, §6.3). "error" is any other error, or a last lookup over 11 minutes old, which means the service has stopped. Both are grey; `checked` is unchanged.

— Code consequence, for Claude Code: `ipShown` in `app.js`; the service in mqtt.md's consequence.

## 15.70 Changes in Rev 70
— In tutor pacing every call now ends on her line in full and Next Call (§7), not only a call with no trunk as at Rev 67. A trunk does not show its cord after the call either, 2026-10-22, dobbs-paramount, room 105 to Paramount on trunk 1: the trunk's seizure dropped 0.27s after the game put station 13 on-hook, with both cords still in, and one second later, Rev 45's hold, her "The lamps in front of the cord pair…" was cut off for "press Next Call". The switchboard passes the station's loop through the cord to the trunk, so once the station hangs up nothing holds the trunk seized, cord or not. Rev 67's statement that a trunk is held seized while its cord is in is withdrawn. Next Call during either line cuts it short and deals, as Rev 67 had for a call with no trunk.

— Fixed the same day, no specification change: a line taken as finished as soon as it started. Next Call cut the introduction short, the game stopped it and at once played answer-station, and the audio program's echo of the stop arrived after the new play had been sent; the game read that echo as the new line's end, and 20s later said it again over itself. A play now ends only on its own end: `""` counts once the file's own name has been echoed (`Board.saw`, `scenes.say`).

— Code consequence, for Claude Code: `_tutor_hangup` in `game.py`, `Board.saw` and `scenes.say`; `tests/test_tutor.py`, `tests/test_sim.py` §4b.

## 15.69 Changes in Rev 69
— The tutor's `dial` line may say the digits to dial, one at a time, after the number as the card prints it (§7), Mark's request, 2026-10-22: `{number-digits}` beside `{number}`, so "dial Sunset three, two two five oh. That's seven, eight, three, two, two, five, zero." A new player does not know that the exchange's letters are dialled as digits, and "two two five oh" read as a number is not the holes to put a finger in. The digits are comma-separated, so the voice gives each a beat, and zero is "zero", not the card's "oh": she is naming a hole in the dial. `{number}` is still required; `{number-digits}` is optional, in the full line and its short form alike.

— Code consequence, for Claude Code: `dial_digits` and the placeholder check in `tts/script.py`. The dial lines are rendered again. No game program change.

## 15.68 Changes in Rev 68
— The health column shows the host's public address (§11.1), Mark's request, 2026-10-22: a row `public IP`, the address, and under it `checked`, how long ago it was looked up — "2:10 ago", "failed 0:40 ago" when the last lookup failed, or "checking…" from a tap until the answer comes. Tapping either row asks for a lookup now. Both rows are grey when the last lookup failed, or is more than 11 minutes old, which means the service that makes it is not running. The address comes from `sbgame-publicip`, a program of its own every 5 minutes (mqtt.md Rev 39, §6.3), not from the game program, which makes no network calls during a session.

— Code consequence, for Claude Code: the two rows and the tap in `app.js`; the service in mqtt.md's consequence. No game program change.

## 15.67 Changes in Rev 67
— In tutor pacing, the end of a call with no trunk — between two rooms, or a room's call to the operator — no longer waits for the cords out (§7), Mark's choice, 2026-10-21. Once the game puts the stations on-hook they draw no loop current, so their pilot tones stop and `peer` and `op` go clear whether the cords are in or out: one second after the call ended, Rev 45's hold ran out and the game took the cords for pulled, cutting her "The lamps in front of the cord pair…" off after its first words with the cords still up (17:20, hollis-valet). The pilot cannot see an on-hook station; only a trunk, which is held seized while its cord is in, still shows its cord after the call. Now a call with no trunk gets her end-of-call line in full, then "press Next Call when you are ready", and the player's Next Call is the word that the cords are out. Next Call during her line cuts it short and deals, as during the introduction. A call with a trunk waits for the cords as before. Rejected: keeping a station off-hook until its cord comes out (its supervisory lamp, which her line points to, would not light), and taking a station off-hook now and then to look for its cord (the lamp would flicker).

— Code consequence, for Claude Code: `_tutor_hangup` in `game.py` and Next Call's cut-short; `tests/test_tutor.py`. No topic change.

## 15.66 Changes in Rev 66
— The deck's switchboard reset works during a game (§2, §10), Mark's request, 2026-10-20. Rev 63 refused it, since the cut drops every line on the board: the switchboard supplies the stations' loop current, and for its 1s plus the relay's times the game would read each call's cord as pulled — longer than Rev 45's one-second hold. The game program now freezes the lines through the cut instead (§4): from `ctl/power_cut` `"on"` until 1s after it returns to `"off"`, each circuit's `peer` and `op`, and each trunk's `seize`, keep the values they had, and then take their latest, through Rev 45's hold as usual. A call in progress carries on; a cord pulled during the cut is seen once it settles. A freeze whose `"off"` never comes ends after 3s. The page's `"hold"` is still refused while a game runs. Not yet seen on the switchboard: the relay is commissioned in the week of 2026-10-26, and that is when a connected call through the cut is checked (§13.3 step 6).

— Code consequence, for Claude Code: the board's freeze in `board.py`, the game program accepting `"on"` while running, the deck's hold during a game; tests. No topic change.

## 15.65 Changes in Rev 65
— The switchboard can be switched off and on from the page (§11.7), Mark's request, 2026-10-20: a Switchboard section in Tools with one button, `power`, filled while the switchboard is powered, a tap switching it off and the next on again. Not the deck's 1s reset (§10): the switchboard stays dark until tapped on. `game/power_cut/set` gains `"hold"` and `"off"` beside Rev 63's `"on"`, passed on as `ctl/power_cut/set` (control.md Rev 32, mqtt.md Rev 38); `"hold"` is refused while a game runs, as `"on"` is, and `"off"` is always accepted. Start powers a switchboard left off (§2), since a game on a dark board cannot be played. The deck's key 5 reads "Switchboard" over "off", lit red, while it is held off (§10).

— Code consequence, for Claude Code: the game program accepts the two values and powers the switchboard at Start; the page's button; the deck's key 5; the simulator; tests. No new topic.

## 15.64 Changes in Rev 64
— A chosen scenario no longer starts by itself (§6.5), Mark's request, 2026-10-19, withdrawing Rev 41. It is staged, as any chosen scene is (§6.4): in manual pacing it starts on Next Call, in automatic pacing it is the next call the schedule deals. Rev 41 started it at once on a clear board and only on Next Call or the schedule when chosen with calls on the board, so the same choice behaved two ways. Rev 41's reason, that nothing showed a choice waiting, no longer holds: the page shows the chosen scene under Next Call (§11.1). The clear board of Rev 40 stays: until it clears, Next Call is refused, "waiting for the board to clear", and the schedule deals nothing else.

— Code consequence, for Claude Code: the scheduler's start on a clear board goes, with its test. No topic change.

## 15.63 Changes in Rev 63
— Stop cuts the switchboard's power for 1s (§2), Mark's request, 2026-10-19. A trunk rung in locks its lamp and buzzer on the switchboard until a cord goes into the jack, and Stop, which releases our ring relay, did not clear it; nothing did. The controller now drops the switchboard's 24V on `ctl/power_cut/set` (control.md Rev 31, mqtt.md Rev 37), and every relay and lamp on the switchboard drops with it. Stop sends it after the calls are torn down, so a game always ends on a dark board. A stop for the controller going offline cannot send it, and does not try.

— A long press on key 5 cuts the power by hand (§10): held 2s with no game and no sweep running, `game/power_cut/set` `"on"`, which the game program passes on. While a game runs the deck ignores the hold, as it ignores the sweep's double press, and the game program refuses `game/power_cut/set` on `error` all the same, since the cut would drop the calls on the switchboard under the game's feet; Stop does it anyway. Key 5 because it already starts the trunk sweep, the other thing done to the board with no game running (Mark's choice, 2026-10-19; a long press on the first dial was drafted first).

— Code consequence, for Claude Code: the game program sends `ctl/power_cut/set` `"on"` at the end of `stop()` when the controller is online, and accepts `game/power_cut/set`; the deck program times key 5's hold and draws it; tests for both. The firmware's half is control.md Rev 31.

## 15.62 Changes in Rev 62
— The sweeps come back to the Stream Deck, as at Rev 50, and stay on the page (§10, §11.5), Mark's request, 2026-10-18: key 5 pressed twice within 0.5s sweeps the trunks, key 6 the stations. A single press of the running sweep's own key stops it, and so does the other key pressed twice. While a sweep runs its key reads "Sweep" over "trunks" or "stations", lit teal, however the sweep was started — the key follows `game/sweep`, so a sweep started from the page shows on the deck too. Rev 50 read "Testing".

— Teal (38, 128, 128), a colour of the deck's own, in place of amber on the sweep keys and on Repeat Help and More Help (§10), Mark's choice, 2026-10-18.

— Code consequence, made the same day: keys 5 and 6 in `streamdeck.py`, and its test. No topic change.

## 15.61 Changes in Rev 61
— The page's Tools gains three sections under Operator (§11.1), Mark's request, 2026-10-18: Diagnostics, the board sweeps; Record, a recording of the loudspeaker; and Playback, a recording played back on it (§11.6). Tools is where the tools are, and the deck's keys keep one meaning each.

— Record starts a recording, and while it runs a red dot pulsing once a second and the time recorded stand in the top bar to the right of Tools; a tap on them stops it. The audio program writes `/srv/sbgame/recordings/<YYYY-MM-DD-HH-MM-SS>.wav` and makes an MP3 beside it when it stops (audio.md Rev 22, §10.6). A recording is not part of a game: it runs with or without one, and Start and Stop leave it alone.

— One at a time: Record is dimmed while a playback runs and Playback while a recording does, and the game program refuses either then. Each button, filled while its own runs, stops it on a tap, as its indicator in the top bar does.

— Playback opens a list of the ten newest recordings, newest first, each with its length; a tap plays that one on the loudspeaker, in place of the monitor, at the level it was recorded (audio.md §10.7). While it plays a play triangle and the time stand in the top bar to the right of Tools, and a tap on them stops it. Not while a game runs, and Start stops one.

— The sweeps move off the Stream Deck: keys 5 and 6 are the tallies again and nothing more (§10). Pressing a sweep's button on the page starts it, and pressing it again while it runs stops it (§11.5).

— `game/record/set` and `game/playback/set`, which the game program passes to the audio program as `audio/record/set` and `audio/playback/set`, so the game program stays the only client that commands audio; the page reads `audio/record`, `audio/recordings` and `audio/playback` directly (mqtt.md Rev 36).

— Code consequence, made the same day: Tools and the Recordings sheet in `index.html`, `app.js` and `style.css`; the `record` and `playback` commands in `game.py`, and Start stopping a playback; `Hw.record()` and `Hw.playback()` in `link.py`; the sweep keys out of `streamdeck.py`; the tests.

## 15.60 Changes in Rev 60
— An audit of where the game fell silent on a player's mistake, Mark's request, 2026-10-17, and a fix for each (§4, §7). Each new line is a reaction under a new top-level `reactions:` in script.yml, rendered in every cast member's voice but the operator's and the tutor's, as `<kind>.<speaker>` — 171 lines — so a party reacts in its own voice. A reaction not rendered is done without, as before.

1. **She does not speak** where the game waits for her — the greeting, a reply, the closing — or spoke before the listen began. Outside tutor mode it was 30s of silence before the caller went on. Now after 6s of silence the waiting party says "Hello? Operator? Are you there?" (`nudge`), the game listens 6s more, and the line plays either way. In tutor mode her Say prompt does this already.
2. **She rings the wrong room.** It rang out unanswered and the caller said nothing until the connect timeout. Now, 1.5s into the ring (3s since Rev 82), whoever the scenes most often have in that room answers, "Hello? … Hello? Is anybody there?" (`hello`); if the caller is patched to it, the caller says "Operator, that's not who I asked for." (`wrong`); and the room hangs up, so its cord lamp lights. Not a room already off-hook, nor the caller's own. The call goes on, and she may ring the right one. It is not a failure, since she can recover (Mark, 2026-10-17); §14's open item on a wrong party is settled this way.
3. **She rings the right room on a cord not patched to the caller.** The room was taken off-hook and the game waited in silence for the two to be joined. Now, not joined in 8s, the room says "Hello?" (`hello`, in the called party's voice); not in 8s more, it hangs up, and she must patch and ring it again.
4. **A trunk cord left in from an earlier call** was taken for the trunk of the next call out: dial tone went to it and her digits on the trunk she had taken were never seen. A trunk already up when a call begins to route is no longer that call's, until it is released and taken again. The same applies to the caller-left-alone check (Rev 46), which a stale trunk held off.
5. **She takes a trunk and never dials.** Dial tone ran until the connect timeout. Now, outside tutor mode, 15s without a digit gets reorder and the call fails as `misdialled`, as a number dialled too short does (Rev 56).
6. **In tutor mode, after a prompt's last repeat** she was silent for good, the timeouts being lifted. Now, after the second repeat, she says once "If you are not sure what to do, press Repeat Help, and I will tell you again." (`stuck`, under `tutor:`).

— Code consequence for Claude Code, made the same day: `REACTIONS` and `_reactions()` in `tts/script.py`, `reactions:` and `tutor: stuck:` in script.yml; `caller_voice`, `called_voice`, `GameScript.reactions`, `occupants` and `reaction()` in `script_data.py`; `NUDGE_AFTER`, `PATCH_WAIT`, `DIAL_FIRST`, `WRONG_RING`, `_wrong_party()`, `_picks_up()`, `_fresh()`, `_note_stale()` and the nudge in `_operator_speaks()` in `flows.py`; the stuck line in `Tutor._repeat()`; the tests. No topic changes.

## 15.59 Changes in Rev 59
— On a call to the operator, once the caller has asked, the tutor says the call is for her before her first reply: "This call is for you, not for another line. Answer the caller yourself." (§7). Mark's request, 2026-10-17: the fourth lesson is such a call, and a new player expects to plug a cord in after every request. A new line under `tutor:`, `for-you`, with a short form, "This call is for you."; said on every tutored call to the operator that has a reply or a closing for her, so not on time and charges rung in on a trunk.

— Code consequence for Claude Code, made the same day: `for-you` in `TUTOR_KEYS` in `tts/script.py`, its lines in script.yml, said in `to_operator()` in `flows.py`, and the test. Two lines to render, `tutor.for-you` and `brief.for-you`. No topic changes.

## 15.58 Changes in Rev 58
— A tutor prompt the game waits on the board after stops mid-word once the board shows the player has done it (§7). Mark's report, 2026-10-17: she talked on after the cord was in. Before, the condition was checked only before she began and between her repeats. Now it is checked throughout the line, and her repeats, Repeat Help and More Help stop the same way; a line cut short leaves nothing to repeat. The three prompts to centre the switch — `center`, `center-dialled`, `center-ringing` — are given the condition too, the operator off the pair's lines, so they also stop, are not said if the switch is already centred, are said again if it is not, and are offered to Repeat Help and, in short form, to More Help.

— Code consequence for Claude Code, made the same day: `Tutor._line()` in `tutor.py`, `_centred()` in `flows.py`, and the test. No topic changes.

## 15.57 Changes in Rev 57
— A running game stops by itself after 10 minutes with nothing from the player, so Start must be pressed to play again (§2). Mark's request, 2026-10-17. Activity is what the player does: a cord in or out — a circuit's `peer` or `op`, a trunk's `seize` — a digit dialled, a station rung, and any key or button on the deck or the page. The game's own doing is not: a station taken off-hook, a trunk rung in, the tutor speaking, a call dealt on the automatic schedule. The stop is an ordinary one, logged "game stopped: no activity for 10 min", and the stopped game goes back to tutor 5 minutes later as before (§7, Rev 44). `idle_stop` in the configuration, 600s by default; 0 never stops.

— Code consequence for Claude Code, made the same day: `idle_stop` in `config.py`; `PLAYER`, `_active_at`, its updates in `on_command()` and `watch_clients()`, and the check in `run_scheduler()`, in `game.py`; the test. No topic changes.

## 15.56 Changes in Rev 56
— A number dialled with too many digits or too few gets reorder, the fast busy, on the trunk until the operator releases it, and the call fails as `misdialled` (§4). Mark's request, 2026-10-17. Too many: a digit more within 3s of the last digit the number needs — the game now waits that long after the last digit before taking a number as dialled, so the extra digit can be heard; 3s is longer than a dial takes to return and run ten pulses (control.md §8). Too few: 10s after a digit with the number not complete. The failure is counted when she releases the trunk, so the fast busy is heard for as long as she stays on it; a deadline passing first fails the call as `not connected`, as before. A wrong number of the right length is unchanged: busy tone, and she may redial (Rev 46). The rule holds in tutor mode as well, where it is the one failure that is not about the cords.

— Code consequence for Claude Code, made the same day: `DIAL_SETTLE`, `DIAL_PAUSE`, `_number()`, `_reorder()` and `Misdialled` in `flows.py`, `Reason.MISDIALLED` in `calls.py`, and the tests. The tone is new in the audio program, `"reorder"` on `tone/set` (audio.md Rev 20, mqtt.md Rev 35): `ToneKind::Reorder` and a row of the tone table in `engine.cpp`, its name in `net.cpp`.

## 15.55 Changes in Rev 55
— Once the tutor has said a prompt in full twice, she says its short form where script.yml gives one, under `tutor: brief:`, and More Help says the full line (§7, §10). Mark's request, 2026-10-17: the full prompts are right at first and too long once the player has done that step twice. Counted per prompt, not per call, since each kind of call has prompts of its own: a call out is the first to need `dial`, however many calls between rooms came before it. Every jack and number is the one prompt — `ring-front` to any room — and `dial-operator` is its own. Counted from Start, or from Tutor chosen mid-game; her own repeats, Repeat Help and More Help do not count. A short form may be given for any prompt but the introduction's three parts and the prompts before the operator speaks — `say`, `greet`, `respond` — which are short already and have a listen after them. A line with no short form is said in full every time. More Help is offered once she has finished a short line the game then waits on the player after — the answer, the switch, ring, the trunk, dial, the end of a call, "press Next Call" — for as long as Repeat Help would repeat it. A press says the full line at once; Repeat Help then repeats the full line, and More Help is done until the next short one. Her own repeats, 20s apart, say the line she last said. Short forms are rendered as `brief.<key>`, in her voice with the rest; one not yet rendered is not a gap, and she says the full line in its place.

— Code consequence for Claude Code, made the same day: `tutor: brief:` in script.yml, read by `tts/script.py` (`BRIEF_KEYS`, `brief-<key>` in `Script.tutor`, rendered as `brief.<key>`, since `tutor.brief-<key>` passes the 31-character limit on a name); `Tutor.said`, `prompt_of()`, `Tutor.more()` and `more_key` in `tutor.py`; `game/tutor/more` and the `more` command outside the introduction in `game.py`; key 8 in `streamdeck.py`; the tests. One new topic, `game/tutor/more` (mqtt.md Rev 34). The short forms are to be rendered.

## 15.54 Changes in Rev 54
— A long press, about half a second, on a pacing button — Tutor, Manual, Automatic, Listen — or on a stepper — `pause`, `gap`, `ramp`, `floor`, `jitter`, its label or either button — opens a short help beside it: what the pacing does, or what the value means, its range, its step and its starting value (§11.1). Mark's request, 2026-10-17. Works the same with a mouse held down. The press that opens it changes nothing; a tap still does what it did. A tap elsewhere or Escape closes it, as it does every popup. The pacing buttons are drawn dimmed rather than disabled while the game program is away, so that their help still opens; a tap on one then does nothing.

— Code consequence for Claude Code, made the same day: `HELP` and `showHelp()` in `web/app.js`, `data-help` and `#help` in `web/index.html`, and `web/style.css`. No topic changes.

## 15.53 Changes in Rev 53
— A long press on Tools, about half a second as on Next Call (§6.4), shows a key to the lamps: each state of §11.1's table, most urgent first, with the lamp drawn as on the board, lit as it is there, and a line saying what it means (§11.1). Mark's request, 2026-10-17. A tap still opens Tools; a tap elsewhere closes the key. Tools is a control, so the key is hidden with the Controls switch too.

— Code consequence for Claude Code, made the same day: `#lamps` in `web/index.html`, its long press in `web/app.js`, and `web/style.css`, where the lit lamp's glow now follows `lit` on any element and not only on a tile. No topic changes.

## 15.52 Changes in Rev 52
— On the page, a `peer` of `"deaf"` or `"ambiguous"` makes a tile a fault only once it has stayed so for a second (§11.1); until then the tile shows the `peer` before it. Found 2026-10-17 with the station `hook` test: the lamp flashed red as the station went off-hook and again as it went back, because the relay breaks the line for a moment and the detector reports `deaf` for that long, as it does for the cord switch's 0.2s break (Rev 45). A real fault is shown a second later. The tile's panel still shows the detector's own value, and `play` `"missing"` and `fault` are shown at once. The deck shows no `peer` faults, so it is unchanged.

— Code consequence for Claude Code, made the same day: `tileState()` in `web/app.js`. No topic changes.

## 15.51 Changes in Rev 51
— The loudspeaker plays ringback while a station reports ring (§9.2), Mark's request, 2026-10-17, so the player and the room hear the operator ringing, for as long as she holds the ringing key. Steady, not in the 2s-on cadence: it follows her key. A file on the monitor, `cue.ringback`, rendered by `tts/cue` — the period ringback of audio.md §8.2 — so the audio program is unchanged. The monitor plays one file at a time and that file is otherwise the tutor's voice; she comes first. A configuration switch, `ring_cue`, true by default. No topic changes.

— Code consequence for Claude Code, made the same day: `cue.py`, started from `main.py`; `ring_cue` in `config.py`; the Stream Deck does not take the cue for her voice (§10's Repeat Help and the flashing key); `tts/process` leaves `cue.*` out of its check for files in no scene; `tests/test_cue.py`.

## 15.50 Changes in Rev 50
— A sweep of the board from the Stream Deck (§10, §11.5), Mark's request, 2026-10-17, for checking the cabling after a recabling. Key 5 pressed twice within 0.5s gives each trunk in turn one short ring, 2s apart, so its lamp latches; key 6 pressed twice takes each station in turn off-hook for 1s, 2s apart, in jack order — the board's rows from the top, each left to right — rather than circuit order, so the lamps light in the order the eye reads the board. Either key pressed twice during a sweep stops it. Only with no game running: the game program refuses one while a game runs, and Start, Stop and losing a client end one. Each step goes on the game log, so the page shows it, and the hardware's own echoes light the tiles. Keys 5 and 6 did nothing on a press before, and a single press still does nothing. One new command and its echo, `game/sweep/set` and `game/sweep` (mqtt.md Rev 33), covered by the access list's `game/+/set`.

— Code consequence for Claude Code, made the same day: `sweep.py`, `_sweep_command()` in `game.py`, keys 5 and 6 in `streamdeck.py`, and the tests.

## 15.49 Changes in Rev 49
— A scenario chosen from the page counts as its once-a-game play (§6.5), Mark's request, 2026-10-16. Rev 40 left the deal after `n` calls to come regardless, and in the first play of `panic` on the switchboard it did: chosen, its sixteen calls counted as handled, so the whole scenario was dealt again the moment the board cleared, and the same rooms lit with the same complaints, which looked like callers ringing back. Choosing it again from the page still plays it.

— Code consequence for Claude Code, made the same day: `_start_call()` in `game.py` and the test. No topic changes.

## 15.48 Changes in Rev 48
— A caller left alone hangs up after 10s, and after 5s once a wrong number has been dialled for the call (§4, `cut off`), Mark's decision, 2026-10-16. Rev 46's 20s, restarted each time the operator came back on the line, kept a call he had given up on alive while he tried the cords: a real guest left in silence hangs up, and one just told it was the wrong number sooner.

— Code consequence for Claude Code, made the same day: `ABANDON`, `ABANDON_MISDIALLED` and `Ctx.misdialled` in `flows.py`, and the tests. No topic changes.

## 15.47 Changes in Rev 47
— The caller waits for her `closing:` (§6.3), found in a game on the switchboard, 2026-10-16: nbn-trace's guest asks "was that an outside call or from the lobby?" and hung up as the question ended, before she could answer, because a call to the operator with no conversation hangs up once its request has played. The game listens for her closing now, in every call that has one, and the tutor prompts it. Not saying it does not fail the call: she has done what it asked.

— Code consequence for Claude Code, made the same day: `SceneDef.closing`, `_closing()` in `flows.py`, called at the end of a call to the operator and of a busy call, and the tests. No topic changes.

## 15.46 Changes in Rev 46
— Three changes from a tutored game on the switchboard, 2026-10-16 (§4). A wrong number was met with silence, which tells the operator nothing; it gets busy tone now, until she hangs the trunk up. Pulling both cords mid-call, before it was connected, left the call open for good: from routing until connection the game watched only the trunk, the caller stayed off-hook with its lamp lit, and tutor mode has no timeouts, so nothing could end it and Next Call was refused. Now a caller lost for 20s before connection — no operator on its line, patched to nothing, no trunk up — is abandoned as `cut off`. The 20s is what tells a pulled answering cord from the switch centred before the front cord goes in, which look the same, since the game cannot see a cord in a station jack. And dial tone comes a second after the seizure rather than at once, as an exchange takes a moment to answer (Mark's request; tried at half a second first, and lengthened the same afternoon).

— Code consequence for Claude Code, made the same day: `_dial_tone()`, `_unless_abandoned()` and the busy tone in `_wait_for_right_number()` in `flows.py`, and the tests. No topic changes.

## 15.45 Changes in Rev 45
— A circuit's `peer` going empty, or its `op` going off, counts only once it has stayed so for a second, and `deaf` leaves the last `peer` standing (§4, `cut off`). Found on the switchboard, 2026-10-16: returning a cord pair's switch to its centre position, as the tutor asks once the far end answers, breaks both lines for about 0.2s. The detector reports both ends `deaf` and then idle for that long, and the game read it as a cord pulled: it ended the call with the parties still talking, and the tutor said the call was over. The same happened while the operator answered, and on every dial pulse. A real pull is now noticed a second later, which nothing in the game minds. The game program applies the hold as the messages arrive, so every wait in it sees the held value; the page and the deck show the detector's own.

— Code consequence for Claude Code, made the same day: `Board.HOLD` and `Board._hold()` in `board.py`, and the tests, which run it at their own speed. No topic changes.

## 15.44 Changes in Rev 44
— The game starts in tutor, and returns to tutor after five minutes stopped (§7), Mark's request, 2026-10-16: the installation's `game.toml` sets `pace = "tutor"`, and a new setting, `idle_tutor`, 300s, returns a stopped game in another pacing to tutor. A player who has moved on to manual or auto leaves it that way, and the next visitor, who has never seen a switchboard, should meet the tutor.

— Code consequence for Claude Code, made the same day: `Config.idle_tutor`, the timer in `game.py`, and the tests. No topic changes.

## 15.43 Changes in Rev 43
— Stations can be marked out of service (§12.2), Mark's request, 2026-10-16: `game.toml` gains `[out_of_service.stations]`, a station's number and the reason, beside Rev 36's trunks. Found on the switchboard: jacks 21–30 draw no loop current after a spark while station 3 was being moved from jack 23 to 29, so no lamp on that row lights, and the first lesson of a tutored game was a call from Housekeeping on jack 26, waiting for good. A station is out of every call, not only calls rung in, because a dead line can neither call nor be heard: its scenes are left out as if it were not fitted, `after:` chains and tutor lessons with them. Rev 36 noted stations might need this.

— Code consequence for Claude Code, made the same day: `Config.stations_out()` and its check, `fit()` in `script_data.py`, the start and `--check` logs in `main.py`, and the tests. No topic changes.

## 15.42 Changes in Rev 42
— Dial tone stops at the first digit (§4, `dialling`), found in the first game on the switchboard, 2026-10-16. It ran on under the dialling until the whole number was in, where a real exchange drops it as the first pulse arrives. It also comes back on a fresh seizure when the operator hangs up a trunk and tries again; before, a redial got no dial tone at all.

— Code consequence for Claude Code, made the same day: `_wait_for_right_number()` in `flows.py`, and the tests. No topic changes.

## 15.41 Changes in Rev 41
— A chosen scenario starts by itself as soon as the board is clear (§6.5), Mark's request, 2026-10-14: at once if it is clear when chosen, else the moment the last call ends, in any pacing but tutor. Rev 40 waited for Next Call or the schedule, and nothing on the deck shows that a choice is waiting. Other chosen scenes are unchanged: still the next call dealt.

— Code consequence for Claude Code, made the same day: `game.py`'s scheduler loop, and the tests. No topic changes.

## 15.40 Changes in Rev 40
— A scenario can be chosen from the page to show it (§6.5), Mark's request, 2026-10-14, for showing the game to friends. Rev 39 let it be chosen in manual and auto only, and dealt it on top of whatever was running. Chosen, it is now allowed in listen too, still never in tutor mode, and waits for a clear board: no call in progress and no `after:` scene waiting. Until then nothing else is dealt, and Next Call is refused on `game/error`. A chosen scenario does not use up its once-a-game play after `after_handled:` calls, so it can be shown as often as wanted. The automatic deal after `after_handled:` calls is unchanged.

— Code consequence for Claude Code, made the same day: `game.py` and the tests. No topic changes.

## 15.39 Changes in Rev 39
— A scenario: calls that arrive almost together, so the board lights up at once, Mark's request, 2026-10-14, from Remco's suggestion and Beth's story of Martha loose in the hotel. Three keys in script.yml, each usable on its own:

- **`mode: concurrent`** on an `after:` scene (§6.1): it starts `delay` seconds after the scene it follows has *started*, not ended, and whether or not that scene is ever connected. It waits for a free slot as well as its lines, rather than being dropped. `delay` may be a range, `[2, 5]`, drawn evenly from the game's seed.
- **`after_handled: <n>`** on a scene that follows none (§6.5): it is never in the deck, and is dealt once a game, as the next call after `n` calls have been handled. Not in tutor or listen pacing. While its scenario is on the board the automatic schedule waits. It stays in `game/scenes`, so it can be chosen from the page to try it.
- **`if_busy:`** on a call from a room to a room (§6.6): caller lines played, as in a busy call, when the called station turns out to be engaged in another call. So several guests can ask for the front desk at once, and the operator tells all but one to try later. A scene with `if_busy:` does not hold its called line or person for dealing.

Calls before connection in general stay deferred (§5.5); the scenario is the one place the operator is asked to route several calls at once. The first is `panic`, after the tenth call: Martha the dog loose in the hotel, a complaint from every guest room, the lobby and the restaurant, ending with Martha calling from her room to say someone is chasing her with a broom.

— Code consequence for Claude Code, made the same day: the loader checks the three keys (`tts/script.py`), renders `if_busy:` lines, and gives the tutor no Say line for an operator line only a scenario uses; `script_data.py`, `deck.py`, `game.py` and `flows.py`; `busy` is also the stage of a call found engaged (§3.2); the tests. No topic changes.

## 15.38 Changes in Rev 38
— The tutor's `ring-front` and `ring-rear` lines are named for the station, `tutor.ring-front-room403`, not the jack, `tutor.ring-front-29` (§7), Mark's request, 2026-10-12. Rev 37's renumbering moved no label off its station, yet 30 of those lines looked new or changed to the TTS run, since a line's text follows its label and its name followed the jack. Named for the station, a line changes only when what she says does: a new label, or the station cabled to a jack with another. Renumbering jacks changes no file.

— Code consequence for Claude Code, made the same day: the loader names the lines by station (`tts/script.py`); the game looks them up by the called line's name (`flows.py`); the 88 wavs, raw and delivered, and their manifest entries renamed, nothing rendered; the tests.

## 15.37 Changes in Rev 37
— The board's station rows run 21–30, 11–20, 1–10 from the top (§11.1), checked against the 551 by Mark, 2026-10-12, closing the §14 item. Rev 5 assumed jack 1 at top left. Rows still run left to right. The labels stay where they were on the board — the hotel's services on the top row, the rooms in ascending order on the two below — so script.yml's `jacks:` items move: the top row's labels go from jacks 1–10 to 21–30 and the bottom row's from 21–30 to 1–10. `hardcopy/strips.py` already printed the strips in this order.

— Code consequence for Claude Code, made the same day: `app.js` draws the rows in the new order; script.yml's `jacks:` renumbered. No topic changes.

## 15.36 Changes in Rev 36
— Trunks can be marked out of service (§12.2), Mark's request, 2026-10-10. Ringing each of the 551's trunk jacks in turn showed two that cannot take a call rung in: jack 6's lamp lights only while ring is applied and does not latch, and jack 8's lamp does not light at all, though its relay operates. Both are faults in the switchboard, to be repaired later; six working trunks are enough for the game. `game.toml` gains an `[out_of_service.trunks]` table, a trunk's number and the reason, and no call is rung in on a trunk listed there. Stations may need the same later; the table takes only trunks for now.

— Code consequence for Claude Code, made the same day: `Config.out_of_service` and `working_trunks()` in `config.py`, checked at load; `Game._free_trunk()` picks only from the working trunks; `main.py` fits the scenes to them and logs each trunk out of service at start and under `--check`; the tests.

## 15.35 Changes in Rev 35
— Repeat Help after a "Say:" prompt too (§7), Mark's request, 2026-10-09. Rev 34 left it out because the game listens for the operator after one, and the loudspeaker would be heard as her. Now a press there stops the listen first, she says the prompt again, and the game listens afresh. A press once the operator has started speaking is refused, so her answer is not cut off. A press does not count as one of her own repeats.

— Code consequence for Claude Code, made the same day: `_operator_speaks()` in `flows.py` races the listen against the press; `Tutor.asked` and `release()` in `tutor.py`; the tests.

## 15.34 Changes in Rev 34
— Repeat Help (§7, §10), Mark's request, 2026-10-09: once the tutor has finished a line and the game is waiting on the player, the deck's key 7 says "Repeat Help", and a press says the line again. That covers each part of the introduction, the call steps that wait on the board — answer, the switch, ring, the trunk, dial, the end of a call — and "press Next Call when you are ready for another". Not a "Say:" prompt: the game is listening for the operator then, and the loudspeaker would be heard as her. The line stays repeatable until the player does what it asks or she says another. The game program publishes it on `game/tutor/repeat` and takes `game/repeat/set`, an event at QoS 0 (mqtt.md Rev 31).

— Code consequence for Claude Code, made the same day: `Tutor.repeat()`, `repeat_key` and `hold` in `tutor.py`; the `repeat` command in `game.py`; key 7 in `streamdeck.py`; the tests.

## 15.33 Changes in Rev 33
— While the tutor waits for a key, the deck flashes it (§7, §10), Mark's request, 2026-10-09: More Help and Next Call after each part of the introduction but the last, Next Call alone after the last, and Next Call after a call once the cords are out and she has asked for the next. Only once she has finished speaking, so the flashing does not compete with her. The game program publishes what she is waiting for on `game/tutor/waiting`, `"more"`, `"next"` or `""` (mqtt.md Rev 30), since the deck cannot tell her waiting for Next Call from her waiting for the cords to come out.

— Code consequence for Claude Code, made the same day: `_waiting()` in `game.py`; `Panel.flash()` and keys 4 and 8 in `streamdeck.py`; the tests.

## 15.32 Changes in Rev 32
— Tutor mode becomes a pacing, `tutor`, the first of four (§7), Mark's decision, 2026-10-09. It was manual pacing with tutoring in all but name: one call at a time, each on Next Call. As a switch beside the pacing it allowed tutor with auto or listen, which nobody wanted, and two controls where one will do. Moving a player on is now a change of pacing, mid-game if need be. `game/tutor/set` and `game/tutor` are withdrawn (mqtt.md Rev 29); `pace/set` takes `"tutor"`, refused while any of her lines has no wav. A configured `pace = "tutor"` falls back to manual at start-up, with a warning, while any is missing.

— The deck's pacing key shows four names, Tutor first, and cycles Tutor, Manual, Auto, Listen (§10). Key 8 is the health lamps again, as through Rev 28, and More Help while she introduces the board; key 7 is the success percentage throughout. The page has a fourth pacing button.

— Code consequence for Claude Code, made the same day: `PACES` in `pacing.py`; the switch moves into the `pace` command in `game.py`; `streamdeck.py`; `index.html` and `app.js`; the tests.

## 15.31 Changes in Rev 31
— The tutor's introduction is in three parts — the jacks, the cords, the switches and dial — Mark's request, 2026-10-09: all at once it was too much to take in (§7). After each part but the last she says to press More Help, or Next Call to start playing, and waits for one; after the last, for Next Call. This is the same in every pacing: in auto and listen the first call no longer follows the introduction by itself. More Help pressed mid-part cuts it short and goes on to the next part; Next Call at any point ends the introduction and deals the first call, as before. script.yml's `intro:` and `begin-manual:` give way to `intro-jacks:`, `intro-cords:` and `intro-switches:`.

— While she introduces the board, the Stream Deck's key 7 is More Help in place of the success percentage (§10). It publishes `game/more/set`, an event at QoS 0 like `next/set`, guarded the same way, and the game program publishes the part she is on as `game/tutor/intro`, `"1/3"` to `"3/3"`, or `""` (mqtt.md Rev 28). The key is lit while a further part remains.

— Code consequence for Claude Code, made the same day: `INTRO` in `tutor.py`; `_tutor_intro()` and the `more` command in `game.py`; key 7 in `streamdeck.py`; `tts/scenes --tutor` joins the three parts; the tests.

## 15.30 Changes in Rev 30
— A tutored game starts with one call of each kind (§7), Mark's request, 2026-10-08: between rooms, out to a number, in from outside, and to the operator, in that order, so a new player meets every interaction before the deck takes over. Each kind is a group of suitable scenes under `tutor: lessons:` in script.yml, and each game picks one from each group at random, so a restart does not repeat the last game's. The picks come from the game's seed, so a replay picks the same, and they are logged. The loader refuses a group that mixes kinds, or names a scene that is inactive, unknown or an `after:` scene. No topic changes.

— Code consequence for Claude Code, made the same day: `lessons` and `scene_kind()` in `tts/script.py`; `GameScript.lessons`, fitted to the circuits built (§12.2); `pick_lessons()` and the dealing in `game.py`; `test_tutor.py`.

## 15.29 Changes in Rev 29
— Tutor mode (§7), Mark's request, 2026-10-08, in place of an instruction sheet: a new player has too many steps to take in from paper. With it on, a senior operator's voice on the audience loudspeaker says what to do at each step of a call — which cord, which jack, which switch, what to say, what to dial — at the moment the game sees the step is due, and the game waits for her. She introduces the board when the game starts. One call is in progress at a time, nothing fails for being slow, a prompt not acted on is said again, and the next call waits for the cords to come out. Her lines are rendered offline like every other, from a `tutor:` section of script.yml, one whole sentence for every jack, number and operator line they name.

— The Stream Deck's key 8 is the tutor switch (§10). It showed three health lamps, which the page already shows; the error that turned it red is on the strip as before. `game/tutor/set` and `game/tutor` are new (mqtt.md Rev 27), and the page's state line says "Tutor" while it is on (§11.1).

— She is on the loudspeaker, not in the headset, which is the reason for most of §7's rules. In the headset her voice would go out on the line the operator is bridged to and set off that line's speech detection. On the loudspeaker it reaches the operator's microphone acoustically, so she is still never speaking while the game listens. The audio program needed a file source on the monitor for it: audio.md Rev 11.

— Code consequence for Claude Code, made the same day: `tutor.py`; hooks in `flows.py` at each step; the switch, the introduction, one call at a time and the end of a call in `game.py`; `Slots.timeless`; `script_data.py` loads her wavs, and refuses tutor mode while any is missing rather than refusing to start; the loader in `tts/script.py` renders `tutor:`; key 8 in `streamdeck.py`; `app.js`; `test_tutor.py`.

## 15.28 Changes in Rev 28
— A call in on a trunk is signalled with one short burst of ring, `shortring/set` (§3.3, §3.2, §9.1; mqtt.md Rev 26, control.md Rev 25), Mark's request, 2026-10-05, in place of ring in the standard cadence until answered. The trunk cannot see a seizure while it is ringing, so an operator who plugged in during a 2s ring-on interval was not seen until it ended. The 551's trunk signal latches on a short burst, so the lamp stays lit without further ring and the trunk is readable from the moment the burst ends. Nothing else about the call changes: the answer timeout runs from the start of the call as before, and an unanswered call fails as `no answer`. The game still sends `ring/set` `"off"` when the call ends, which cancels a burst that is still ringing. The page's `ring` diagnostic keeps the cadence (§11.4).

— Code consequence for Claude Code, made the same day: `Hw.short_ring()` in `link.py`; `outside_to_station` and `to_operator` from an outside line call it instead of `ring_trunk(…, True)`; the simulator and the tests' fake echo a 0.5s burst on `ring`.

## 15.27 Changes in Rev 27
— The health column shows the controller's firmware, `ctl/firmware` (§11.1, mqtt.md Rev 25), 2026-10-01, so a stale build on the board is seen at a glance. Display only.

## 15.26 Changes in Rev 26
— The page lists the scenes for a chosen next scene in alphabetical order of id (§6.4), Mark's request, 2026-09-30. The page sorts them; `game/scenes` is unchanged. Code consequence for Claude Code, made the same day: `app.js`.

## 15.25 Changes in Rev 25
— Diagnostics from the page (§11.4), Mark's request, 2026-09-30, for bring-up and for finding a fault at the board. A station's panel takes it off-hook and plays a 1kHz tone, a run of speech, or feeds its receive channel to the loudspeaker; a trunk's panel rings it, and plays tone, speech or loudspeaker the same way; a new Tools button opens the same three for the operator tap. Each is a toggle. They run whether or not a game is running, and are kept apart from the calls: a circuit in a call refuses a test, and a circuit under test is busy for dealing (§6.1). Stop ends them all (§2). Voice on the tap needs the audio program to play a file there, which it did not; audio.md Rev 10 adds it.

— A chosen next scene (§6.4). A long press on Next Call lists the scenes; the one chosen is the next dealt. `game/scenes` and `game/queue` are new, with `game/queue/set`. §14's open item "Start a named scene" is closed by it.

— The game fitted to the circuits built (§12.2): the game program's configuration, and two command-line options, say how many stations and trunks exist. A scene that needs a station beyond the first `stations`, or an outside line when `trunks` is 0, is left out with the scenes that follow it; calls ring in and go out only on the first `trunks` trunks. `game/stations` and `game/trunks` say what was set, so the page offers tests only on circuits that exist.

— Code consequence for Claude Code, made the same day: the game program, the page, the access list (mqtt.md Rev 23), the configuration file, and the audio program (audio.md Rev 10).

## 15.24 Changes in Rev 24
— A call to the operator may ring in on a trunk (§4.3, §4.6), Mark's request, 2026-09-30. Its calling line is an outside name and it has no `called:`: the game rings a free trunk, as for a call in to a room, and the operator answers it with her listening key. The rest is as for a call to the operator from a room: the request plays after she has spoken, it is connected when the request has played, and any conversation lines each wait for her. A call with a request and no conversation hangs up as soon as the request has played, without waiting for her to answer it.

— It is for the long-distance operator's time and charges. After a long-distance call a guest placed is over, the long-distance operator rings the hotel with the time and the charge, once, so that the hotel can put it on the room bill, and hangs up (§6.2). Peter at the museum had it from a guest who worked as a hotel clerk: if you did not have your pencil ready you had missed it, and the hotel could not charge the room. Five scenes gain one, each an `after:` of the call it bills. A collect call, and a call placed by someone outside to a guest, are not billed to the hotel and have none. A guest who asked for time and charges still hears them from her at the end of the call as well.

— An unanswered one fails as `no answer`, as any unanswered call does (§4); whether she wrote the figures down is not something the game can know.

— Code consequence for Claude Code, made the same day: the game picks a free trunk for such a call as it does for a call in to a room, and the call-to-the-operator flow rings it. `test_game.py` covers it.

## 15.23 Changes in Rev 23
— A station jack may carry `guest:`, the name of whoever is staying in the room at that jack (§12.1), Mark's decision, 2026-09-29. It is typed on the operator's guest list card, `hardcopy/cards.py`. The card had worked out each guest's room from the scenes, which put a guest on whichever line they called from — Mr. Pike on the lobby house phone as well as in 204 — and took the names from a table of its own. The jack is where the room is, so the guest goes there too. It is left out for an unoccupied room and for a jack that is not a room.

— The game does not read it. The loader refuses an empty one.

— Code consequence for Claude Code, made the same day: the loader accepts the key and checks it, `test_game.py` tests the refusal, and `hardcopy/cards.py` builds the guest list from it.

## 15.22 Changes in Rev 22
— script.yml says what the player says (§6.3), Mark's request, 2026-09-29: an `operator:` key on each line the game waits for the operator before, naming a line under a new top-level `operator_lines:`, or giving an id and text of the scene's own. Mark wants every scene as one recording, both halves of the conversation, which needs the operator's half written and rendered. The TTS run renders the lines in the voice of a new cast member, `hotel_operator` — `operator` in the cast is already the long-distance operator.

— The game ignores them: the person at the board speaks them. An `operator:` is refused where the game does not wait for her, because there the next line would play over it; and one that names no line under `operator_lines:`, or whose inline id the scene already uses. It is optional: `python -m tts.script` counts the places still without one.

— Considered and not adopted: operator lines as conversation entries of their own, beside `caller:` and `called:`. That is the more natural form to write, but it changes what the flows iterate over and would make `wait:` redundant with a preceding operator line. A key on the line it precedes changes nothing the game reads.

— A scene-level `closing:`, in either form, for what she says after the last line (§6.3), Mark's request, the same day: without it a call to the operator ended on the guest's question. Refused in a call where she has left the line by the end — any but a call to the operator or a busy call. The 13 such scenes each have one of their own.

— Code consequence for Claude Code, made the same day: the loader, the game program's exclusion of the operator's lines from a scene (`script_data.py`), tests of the five refusals, and `tts/scenes --batch`, which writes each scene to an mp3 with the operator's lines in their places. Every place in the 105 scenes has its `operator:`: four stock lines and 25 of the scenes' own.

## 15.21 Changes in Rev 21
— `ringback:` is allowed on any line spoken on a trunk (§4.6), Mark's request, 2026-09-28: the called side of a call out, as in Rev 20, and now also the calling side of a call in. A long-distance operator who could not get through calls back when she has the party (script.yml, "Long distance"): the call rings in on a trunk, the hotel operator puts it through to the room, and only then does the far end ring — on the calling side. The loader's refusal now names a line spoken on a station, or in a scene where every line waits already.

— Code consequence for Claude Code, made the same day: the loader's check only — the flows already rang whichever trunk the line is spoken on. A test covers ringback on the calling side of a call in.

## 15.20 Changes in Rev 20
— Two more keys on a conversation line, `pause:` and `ringback:` (§6.2), Mark's request, 2026-09-28. Rev 19's long-distance call runs through a chain of operators — the rate operator, then each toll center on the route answering with its town's name — as the 1950s calls did. Played back to back, the chain is a gabble; the real ones had a beat at each step while the next operator came on, and the far end rang before anyone answered. `pause:` is that beat, silence before the line; `ringback:` is ringback tone on the trunk before the line, the far end ringing.

— `ringback:` is refused anywhere but a `called:` line of a call to an outside line: ringback is a trunk tone, and only there is the called side a trunk. Both are refused unless a number of seconds above 0 and at most 30.

— Considered and not adopted: a gap between every pair of lines, set once for the game. It would slow every conversation, and the beats that matter are particular ones.

— Code consequence for Claude Code, made the same day: the loader and the flows; the game program's tests cover both keys and the three refusals.

## 15.19 Changes in Rev 19
— A conversation line may wait for the operator (§6.2), Mark's request, 2026-09-28. A long-distance call from the hotel goes through the local operator: the hotel operator dials 0, the local operator answers, the hotel operator asks for long distance, and only then does the long-distance operator come on and talk to the guest. Until now a scene with a called party played its conversation straight through once connected, so there was no place for the hotel operator to speak in the middle of one. A line marked `wait: true` plays only after the operator has spoken on that line's side of the call and stopped — the listen that calls to the operator and busy scenes already make before every line.

— A conversation line may name its own speaker with `person:` (§6.2). The long-distance operator is not the local operator who answered, and neither is the party she rings, but all three speak on the same trunk. The line plays on its side of the call as before; `person:` changes only whose voice the TTS run uses, and it must be in the cast.

— `after:` scenes may form a chain of any length (§6.1), Mark's request, 2026-09-28: a guest whose requests to housekeeping grow more absurd call by call is a story in five calls, in order. The loader refused a scene following one that itself follows another; that rule is gone. It now refuses a scene named in two `after:`s — both followers would be scheduled together, each would hold the guest, and each would wait forever for the other to let go — and a loop of `after:`s. The game program needed no change: a follower's own follower is scheduled when it ends, as any other.

— `timeout` (§4) now also covers a `wait:` line the operator never speaks before. Considered and not adopted: a new scene shape for long distance. Two keys on a line cover it, and cover a guest handing the telephone to someone else as well.

— Code consequence for Claude Code, made the same day: the shared loader allows chains of `after:`s and refuses two followers and loops; it checks both keys and rejects `wait:` where every line waits already, and on a line with neither `caller:` nor `called:`; the flows listen before a `wait:` line; the game program's tests cover a wait on the trunk and both rejections.

## 15.18 Changes in Rev 18
— The page's countdown says "waiting" while a game runs in automatic pacing and no next call is scheduled — `next_at` empty, because in auto the latest call is not yet connected or ended, and in listen the board is not yet empty (§5.2) — and "–" when no game runs (§11.1), Mark's request, 2026-09-28. It said "–" in both. The deck's Next key already said "waiting" in that case; §10 now says so too. It is on the countdown rather than on the Next Call button because the button is hidden with the controls and the countdown is not.

— The deck's Next Call key is lit violet, where it was amber (§10), Mark's choice, 2026-09-28: no other key or page colour uses violet. In listen the three resting segments of the strip are drawn dimmer than manual's, name and value alike, so the one dial that does something stands out (§10). Code consequence for Claude Code, made the same day: `app.js` and `streamdeck.py`.

## 15.17 Changes in Rev 17
— Listen gets one value of its own, `pause`, in place of auto's four (§5.2, §3.3), Mark's decision, 2026-09-27. Rev 16 ran listen on `gap`, `ramp`, `floor` and `jitter`, counted from the end of a call. But listen is for entertaining with the conversations, not for pressure: Mark wants the next call a few seconds after the last one ends, every time. So listen waits `pause` seconds, 0–60, starting at 3 from the configuration file, with no ramp and no jitter. Auto's four are untouched by listen, so switching between a demonstration and a real game needs nothing reset.

— Considered and not adopted: a separate set of all four for each pace. Eight values, with dials and steppers whose meaning changes with the pace, for three knobs listen has no use for.

— In listen the first dial sets `pause` and the other three rest, dimmed and showing auto's values, as in manual (§10); the page shows one stepper, `pause`, in place of the four (§11.1). `mqtt.md` Rev 22 adds `game/pause` and `game/pause/set`, and the session record gains a `pause` column. Code consequence for Claude Code, made the same day.

## 15.16 Changes in Rev 16
— A third pacing, **Listen** (§5.2), Mark's request, 2026-09-26. It is for showing the game: the next call waits until the board is empty — the last call has ended and no `after:` scene is waiting — so calls never overlap and the room hears every conversation to its hang-up. Automatic pacing times from the connection, so the next call can arrive mid-conversation and the operator's answer takes the loudspeaker away from it (§9.1). Listen is the other half of that open item (§14): it keeps the loudspeaker on each conversation by never starting two.

— A third value of `pace`, not a special value of `gap`. Listen still wants a pause after the hang-up, and `gap`, `ramp`, `floor` and `jitter` keep their meaning, counted from the end instead of the connection. `mqtt.md` Rev 21 adds `"listen"` to `pace` and `pace/set`. "Automatic pacing" in this document now means auto or listen wherever the two behave alike: the first call at once (§2), the dials and steppers, the countdown.

— The deck has no key to spare, so its pacing key cycles Manual → Auto → Listen → Manual, and shows all three names, the echoed one lit, so the choices can be read off the key (§10). Presses count from the last press while its echo is outstanding, as a dial's detents do, so two quick presses go two places. Going from Auto to Manual passes through Listen and from Manual to Listen through Auto; the pass is a fraction of a second, and a call is started on the way only if `gap_now` is shorter than that. The page gains a third segment (§11.1).

— Code consequence for Claude Code, made the same day: the scheduler, the configuration check, the deck's pacing key and the page. The game program's tests cover the schedule in listen, including a waiting `after:` scene holding it; the deck's tests cover the cycle.

## 15.15 Changes in Rev 15
— Commissioning record only. §13.3 step 11, the Stream Deck, was run on portland on 2026-09-26, with Mark at the deck and the page. Everything passed. Fast Next Call presses needed the audio program running and were checked once it was. No behaviour changes.

— The run in detail: passed: the keys drew; Start and Stop, Stop on the second press; the pacing key; each dial one step per detent (`gap` 5s, `ramp` and `floor` 1, `jitter` 10), and eight quick `gap` detents moved it 40s, published in order within a second; with the game program stopped the keys greyed and key 8 went red; replugged, the deck redrew; with `sbgame-streamdeck` stopped it went blank; the page's controls stayed hidden across a reload. A fast turn can carry two detents in one message (`jitter` 100 → 80); the total comes out right. Next Call pressed fast, checked the same day with `sbaudio` running: six presses about 0.4s apart gave six `next/set` and six calls, each a different scene, none doubled or lost. With the audio program offline this could not be checked, since every call fails at once and the game stops (§2).

— Two host snags met on the way, both fixed in `host/`, not here. `libhidapi-libusb0` was not installed; the Stream Deck steps in `host/README.md` now install it. The udev rule names the `sbgame-deck` group, which did not exist when `make install` triggered udev, so the deck stayed `root:root` until udev was triggered again; `make sbgame-install` now triggers it after making the user.

## 15.14 Changes in Rev 14
— Every scene in script.yml carries `active: true` or `active: false` (§6.1, §12.1), at Mark's request, 2026-09-26. He wants to write new cast and scenes before their wavs exist. Until now every scene was built at load, and a missing wav stopped the game program from starting. The game program now builds, deals and follows only active scenes, and reads wavs only for them. An inactive scene is still loaded and checked, and the TTS run still renders it, so a scene is written as `active: false`, rendered, and switched on once its wavs are in place. Every scene in the file at this revision is `active: true`.

— The key is required, not defaulted, so a scene cannot be switched on or off by omission. An active `after:` scene naming an inactive scene is rejected, since it could never play. An inactive `after:` scene following an active one is allowed; it is simply not played. Code consequence for Claude Code: the shared loader checks the key and gives `Script.active_scenes()`; the game program builds from that. No topic changes.

## 15.13 Changes in Rev 13
— The game's controls move to an Elgato Stream Deck+ (§10), Mark's decision, 2026-09-25. The iPad becomes mostly a display. Eight keys carry Start, Stop, the pacing, Next Call, the tallies and the clients' health, and the four dials set `gap`, `ramp`, `floor` and `jitter`, with the touch strip above them showing the values. Stop needs a second press within 3s, as on the page.

— The deck is driven by a program of its own, `sbgame-streamdeck`, on the host. It is not part of the game program, for the reason the page is not (§1): it shows what the broker reports, keeps working and shows the game offline when the game program is down, and a USB fault cannot touch a game in progress. It connects as a new broker user, `sbgame-deck`, with the page's access list (`mqtt.md` Rev 20). It publishes the page's commands, so the game program is unchanged.

— Considered and not adopted: Elgato's own software with a community MQTT plugin, which needs a Windows or macOS machine and cannot draw the game's state on the keys; and Bitfocus Companion's generic MQTT module, which runs on Linux but keeps the layout in its own database rather than in this repository and this document.

— The page keeps its controls, behind a Controls switch in the top bar that shows or hides them on that iPad (§11.1). Mark's decision, 2026-09-25: the deck carries the controls, and the page's stay available if the deck is not there. Both publish the same commands, so both work at once. `sbgame-web` keeps its write access (`mqtt.md` §9).

— A dial reports relative steps and every command but Next Call is absolute (§11.2). The program therefore turns steps into a new absolute value, starting from the echoed value and adding every step made since, and publishes that (§10). Code consequence for Claude Code: the program, its unit and udev rule under `host/`, and later the page's top bar.

## 15.12 Changes in Rev 12
— Automatic pacing gains `jitter` (§3.3), Mark's decision, 2026-09-25. Rev 1 to Rev 11 waited exactly `gap_now` before every automatic call, a rhythm a player learns within a few calls. Each wait is now drawn evenly from `gap_now × (1 ± jitter/100)`, with `jitter` a percentage from 0 to 100 set on the page like the other three. Its mean is still `gap_now`, so `gap`, `ramp` and `floor` keep their meaning and the game is no harder or easier on average, only less regular.

— Bounded and even, not exponential. Calls at a real switchboard arrive nearly at random, which is an exponential wait between them, but at a mean of 20s that puts four waits in ten under 10s and one in twenty over a minute — a dead stretch for the player and the audience. The even spread keeps every wait within a known band. The exponential form, and calls that arrive whether or not the operator is ready (§5.5), stay available for when the game is played on the hardware.

— `floor` bounds `gap_now`, the centre of the spread, not each wait, so near the floor some waits fall a little below it. Holding each wait to the floor instead would raise the short ones to it and lift the mean above `gap_now` exactly where the ramp is meant to be steadiest.

— The draws come from the game's seed (§6.1), so a replay draws the same waits, and `jitter` is recorded with the other pacing values in the session record. Its starting value is 0, from the configuration file, so nothing changes until it is set.

— `mqtt.md` Rev 19 adds `game/jitter` and `game/jitter/set`. Code consequence for Claude Code: the scheduler, the configuration, the session record and a fourth stepper on the page.

## 15.11 Changes in Rev 11
— Every station jack can carry a label, cabled or not (§12.1). Mark's decision, 2026-09-25. The switchboard has 30 station jacks and the game 22 station circuits, and the board's designation strips are labelled at every jack. Rev 7 let a label live only on a station entry, so a jack no entry named was drawn as an empty outline, and §14 asked where the other labels should go. They go in a new top-level list in script.yml, `jacks:`, one item per jack: `jack:` (1–30), `label:`, and `station:`, the script.yml station cabled to it, left out for a jack with nothing cabled.

— `switchboard:` and `label:` leave the station entries, which carry `number:` alone. A station entry is now the game's circuit and nothing about the board; the board is `jacks:`. Rev 7's reason for putting them together — one place to look — is kept by the list being in the same file, next to `stations:`.

— A labelled jack with no circuit is drawn as a working jack at rest (§11.1): its label, its jack number and an unlit lamp, like any idle jack. The operator sees the board as built, not which jacks are wired. A jack `jacks:` does not list keeps Rev 7's empty outline. Tapping a labelled, uncabled jack shows its circuit as none.

— The load checks follow (§12.1). Code consequence for Claude Code: the shared loader checks `jacks:` and rejects `switchboard:` and `label:` on a station entry, the game program builds the `board/` map from `jacks:`, and the page draws labelled uncabled jacks as working. `mqtt.md` Rev 18 corrects the `board/` rows to match. No topic changes. Trunk jacks are unchanged: trunk n on trunk jack n, no labels.

— The page is rearranged (§11.1), Mark's request, 2026-09-25, from the first look at it on the iPad. The health column took 380px beside the board, leaving each tile about 71 points wide, and one-word labels such as "Housekeeping" were clipped and two-word ones wrapped out of the tile. The board now takes the whole width; the calls table has the log under it, and health sits in a narrow column beside those two. A label that still does not fit is set smaller rather than clipped, and every label is set at that one size, so the board does not mix sizes.

— The §14 item "Labels on jacks the game does not use" is closed. The item named a station entry with no `number:` as one way to do it; a separate list was chosen instead, so that a station entry always means a circuit.

## 15.10 Changes in Rev 10
— The page is served by nginx, not by Mosquitto (§13.1), 2026-09-24. Rev 8 and Rev 9 had one Mosquitto listener on 443 serving the files through `http_dir` and carrying the page's MQTT connection. On portland that listener will not bind a privileged port, because libwebsockets creates its socket after Mosquitto drops from root, and it advertises HTTP/2 in ALPN without being able to serve it, so a browser negotiating HTTP/2 — which is the default — receives nothing. `mqtt.md` Rev 17 §12.17 records both, and what was tried before giving up on them.

— nginx now holds the certificate, serves `/srv/sbgame/web` on 443, and reverse-proxies the page's socket to Mosquitto on loopback. The bookmark, the name, the certificate and `sbgame-web` are unchanged, and the page still has one origin and one port.

— The page's socket takes the path `/mqtt`. It is what nginx routes on, and it is the whole of the page's change: `location.host` and the `wss://` rule of §13.1 stand. The page had not been written, so the path cost nothing.

— §13.3 step 10 is withdrawn and replaced. It chose between a SIGHUP reload and a 04:00 restart, a question that only existed while Mosquitto held the certificate. An nginx reload disconnects nobody and does not touch Mosquitto's clients at all. What remains worth checking is the renewal itself, which `certbot renew --dry-run` does against staging without spending one of the five duplicate certificates a week Let's Encrypt allows.

## 15.9 Changes in Rev 9
— Follows mqtt.md Rev 16, 2026-09-24. At home `game.kr3am.org` resolves from a public A record in Route 53; on the road the Slate 7's Edit Hosts line still answers it. Rev 8 said the name resolves only on the local network, through a host entry on both routers. §13.1 and the §13.3 preamble follow. Nothing on the page changes.

## 15.8 Changes in Rev 8
— The page is served over HTTPS as `https://game.kr3am.org/` and connects over secure WebSockets (§13.1), following mqtt.md Rev 15 §9, 2026-09-24, at Mark's request. Rev 1 to Rev 7 had the bookmark `http://<host>.local:9001/` and a `ws://` connection. The certificate, its renewal and how the name resolves are specified in mqtt.md §9.1 and §9.2, and are not repeated here.

— The page takes its WebSocket scheme from its own: `wss://` when loaded over `https:`, `ws://` when loaded over `http:`. Rev 1 to Rev 7 said `ws://` + `location.host`, which Safari refuses from an HTTPS page as mixed content. Code consequence for Claude Code, when the page is written.

— Commissioning (§13.3) follows. Steps 1 and 2 check the listener on 443 and the name and certificate from another machine. Step 10 is new: it checks whether Mosquitto reloads a renewed certificate on SIGHUP without dropping its clients. The answer decides whether renewal can safely happen during a game (mqtt.md §9.1).

— The page is now a secure origin, which lets it ask for a screen wake lock rather than rely on Auto-Lock being off (§11.3). Not specified; an open item (§14).

## 15.7 Changes in Rev 7
— The jack assignments move into script.yml, and `wiring.yml` is dropped (§12.1). Mark's decision, 2026-09-24. Rev 5 specified `wiring.yml` as a separate file mapping circuits to jacks, with labels. It was never written. Each entry under script.yml's `stations:` now carries two more keys: `switchboard:`, the jack the station's circuit is cabled to (1–30), and `label:`, the text on the board at that jack. `number:` is unchanged and is still the game's circuit. A station's name, circuit, jack and label are now in one place, which is where the script's author already looks.

— Trunks are not in script.yml, so trunk circuit n is on trunk jack n, fixed, for n = 1–8, as Mark cables them. Trunk jacks 9 and 10 carry nothing, and no trunk jack has a label. Rev 5's `wiring.yml` allowed trunk labels, and labels on station jacks with nothing cabled. Neither is carried forward: a jack that no station entry names is drawn as an empty outline.

— The checks at load follow (§12.1), and they belong in the one script.yml loader that the TTS task and the game program share (`tts_task.md` §3.1). Code consequence for Claude Code: the loader checks `switchboard:` and `label:` as well. `mqtt.md` Rev 14 corrects the `board/` rows, which said the map came from `wiring.yml`. No topic changes.

## 15.6 Changes in Rev 6
— The audience loudspeaker follows the calls (§9.1). Mark's decision, 2026-09-24. Until now the loudspeaker carried the operator tap alone (audio.md §10). The operator leaves a call when she throws the ring key to ring the called party, and does not come back to it, so the audience heard each request and then nothing of the conversation written for it. The game program now points the monitor at the calling line of the call the operator most recently answered, with `audio/monitor/source/set` (audio.md Rev 8 §10.3, mqtt.md Rev 13). That line's receive channel carries the caller, the operator while she is on the line, and the called party once the cord is up.

— The switch is made when the operator answers the new call, not when the call starts. Mark's first proposal was the start of the call. There is nothing on the calling line until the operator answers: a calling station is off-hook and silent, and a calling trunk is ringing, which puts a relay click on its channel at every cadence edge (trunk §8.1.1). Switching at the answer also leaves the audience on the current conversation until the operator actually picks up the next caller.

— The source goes back to the operator tap when a game starts and when it stops (§2).

— The page shows the monitor's source in its health area (§11.1), and the log records each move (§12.3). One commissioning step (§13.3) and one open item (§14) are added.

## 15.5 Changes in Rev 5
— The page draws the switchboard as it is (§11.1): three rows of ten station jacks, numbered 1–30, over one row of ten trunk jacks. Each jack carries the label written on the board, such as `463` or `lobby`. Rev 1 to Rev 4 drew 22 station tiles and 8 trunk tiles in game circuit order, each named from script.yml. That order is not the board's order, and the operator never sees the circuit numbers.

— A new file, `wiring.yml`, maps game circuits to switchboard jacks and gives each jack its label (§12.1). Mark wires the 22 station circuits to whichever of the 30 station jacks he chooses, and the 8 trunk circuits to trunk jacks 1–8. The game program is the only program that reads the file. It publishes the map to the broker for the page. The controller and the audio program keep working in circuit numbers and never see jacks. `mqtt.md` Rev 12 adds the `board/` topics and removes `station/<n>/name`, which the jack labels replace.

— Tiles are simplified (§11.1). Mark expects the Rev 1 tile to be too crowded. A tile now shows the jack's label and number and one state at a time. Tapping it opens every topic for that jack's circuit. Rev 1 put all of them on the tile.

— A wiring check is added to commissioning (§13.3): ring each jack from the switchboard, and the matching tile on the page should flash. It uses only existing topics.

## 15.4 Changes in Rev 4
— Next Call no longer carries a call number (§5.1), at Mark's request, because the game program keeps its own count. Rev 1 to Rev 3 had the page send one more than `started`, and the game program ignored anything else, so a resent command or a double tap started one call. Now a resent command cannot happen, because the command goes out at QoS 0. A double tap is prevented by the page disabling the button until the call starts. `mqtt.md` Rev 11 records `next/set` as the second event in the design.

## 15.3 Changes in Rev 3
— People are now checked as well as lines (§6.1). Rev 2 held back a scene only if one of its lines was busy. The script has the same person on different lines: Pike calls room service from room 214, takes the reporter's call in room 214, and calls a cab from the lobby. With only lines checked, `pike-taxi` could be dealt while he was on the phone in his room. A scene is now held back if any of its lines or any of its people (script.yml `person:` under `calling` and `called`) is busy.

— Outside lines count as lines, as Mark decided. Rev 2 said "lines" without saying whether that meant outside names or only stations. Two calls to Sunny Hill Pizza now cannot overlap. The `operator` outside line counts like any other.

— An `after:` scene whose lines or people are busy when its delay runs out waits until they are free, then starts. Rev 2 reserved its lines only from when it was scheduled. A call already in progress at that moment could still be holding one of them.

## 15.2 Changes in Rev 2
— Which scene comes next (§6.1). Rev 1 said scenes are drawn at random, following script.yml's "Order" comment, and did not say how. An independent draw per call can repeat a scene while others have not been played. Mark wants every scene played before any repeats, in a random order. At game start the game program now shuffles every scene without `after:` into a list, the deck, and deals from it. When the deck runs out it is reshuffled, so a long game does not run out of calls. The deck is internal to the game program. The page is not told the order and does not need it, so `mqtt.md` does not change.

— A scene that cannot be dealt because one of its lines is busy stays at its place in the deck, and the next dealable scene is taken instead. Rev 1 said only that such a scene "is not drawn", which with a deck would either lose it or stall the game behind it.

— Two rules for `after:` scenes that the deck makes necessary. A line that a waiting `after:` scene will use counts as busy, so the deck does not deal a scene that would collide with a caller about to call back. And an `after:` scene follows only if the scene it follows was connected. Rev 1 started it whenever the earlier scene ended, which would have `nbn-trace` asking where a call came from when the call never reached the room.

— The shuffle's seed and the dealt order go into the SQLite session log, so a game can be replayed at the bench.

## 15.1 Changes in Rev 1
— New document, 2026-09-24. Mark's requirements: start and stop the game; call rate either manual — a button on the page starts the next call — or automatic, the next call starting a set number of seconds after the operator has connected the current one; optionally a rate that rises over the game; tallies of calls handled, successes and failures; and a display of the state of everything, initially for Mark's own use at the bench.

— Option B of the discussion that produced it: the page talks MQTT to Mosquitto over WebSockets, and Mosquitto serves the page's files from its `http_dir`. The alternative — an aiohttp server inside the game program pushing state over its own WebSocket — was less code in the browser but more on the host, and would have taken the display down with the game program.

— Deferred at Mark's request: a new call arriving before the operator has connected the current one (§5.5).
