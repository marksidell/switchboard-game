# Task: the audience loudspeaker follows the calling line

2026-09-24. For Claude Code. Three parts: `sbaudio`, the game program, and the status page (`web/`).

## What changed and why

The audience loudspeaker has been fed from the operator tap only (A32 capture channel 23). The operator leaves a call when she throws the ring key to ring the called party, so the audience heard each request and then none of the conversation.

Now the monitor can take its input from any station or trunk receive channel as well as the tap. The game program points it at the calling line of the call the operator most recently answered. That line's receive channel carries the caller at full strength (no hybrid), the operator while she is bridged to it, and the called party once the cord is up. The existing monitor filter already removes the pilots and the operator tone from any of these channels. Nothing after the input changes.

The specifications are authoritative. This note is a summary and a checklist. Read these sections before writing code:

- `audio.md` Rev 8: §17.8, §2, §10.1, §10.2, §10.3 (new), §12, §13.2, §14, §16
- `mqtt.md` Rev 13: §12.13, §5, §6, §7, §8.2, §8.4
- `game_control.md` Rev 6: §11.6, §3, §6.2, §6.4 (new), §7.1, §7.2, §9 step 9

## Before you start

This builds on the `audio.md` Rev 7 channel map: tap on channel 23 (index 22), monitor out on A32 playback 24, stations 1–22. If the Rev 7 change (`audio.md` §17.7) is not in `sbaudio` yet, do it first. The indices below assume it.

## Part 1: sbaudio (audio.md Rev 8)

1. **Subscribe** to `sbgame/audio/monitor/source/set`, QoS 1.

2. **Validate the payload.** Accept exactly `tap`, `station/1` to `station/22`, `trunk/1` to `trunk/8`. Anything else: log it, drop it, don't change the echo.

3. **Map it to a capture index (0-based):** `tap` → 22. `station/n` → n − 1. `trunk/n` → 23 + n (document channel 24 + n).

4. **Switch in the audio thread**, through the command queue, as §10.3 says:
   - Ramp the monitor gain down to silence over 20 ms. This is the same ramp `monitor/set` already uses.
   - At the bottom of the ramp, change the input channel. Don't clear the filter state.
   - Ramp back up over 20 ms to the commanded gain. Add `--monitor-tap-trim` if the new source is the tap, and drop it if it isn't.
   - Post the echo when the input changes: `sbgame/audio/monitor/source`, retained, with the source string.
   - If a second `source/set` arrives during a ramp, it takes over from wherever the ramp is.
   - A `source/set` naming the current source: echo it and do nothing else.
   - While the monitor is `"off"`: change the input at once with no ramp, and echo.
   - Only the monitor reads the channel this way. The detector, listens and the tap's own-tone check are untouched.

5. **Add two options (§14):**
   - `--monitor-src SRC`: the source at startup, default `tap`. Same validation as the payload. An invalid value refuses to start.
   - `--monitor-tap-trim DB`: gain added only while the source is the tap, default 0. Not echoed on `monitor`, which keeps carrying the commanded gain.

6. **Initial state (§12).** Publish `monitor/source` with the other state before `audio_status` `online`, at start and on every reconnect.

7. **Failsafe (§13.2).** After two missed `game_heartbeat`s, return the source to the tap under the ramp and echo `"tap"`. The monitor itself keeps running, as now. On broker loss, do the same locally. The republish on reconnect then carries `"tap"`.

8. **Log** every source change (§11.2).

9. **`--version`** reports Rev 8.

Don't add `--monitor-own-duck`. `audio.md` §16 records it as a possible fix, to be added only if the bench shows the caller's and called party's levels are too far apart.

**Tests:**
- A unit test for payload validation and the source-to-index mapping.
- On the host, with the switchboard or a loopback: `mosquitto_pub` the source between `tap`, a station and a trunk while the monitor is on. Listen for clicks and watch the echo. Repeat with the monitor off. Stop the game heartbeat and confirm the source returns to `tap`.

## Part 2: the game program (game_control.md Rev 6 §6.4)

If the game program isn't written yet, build this in when you write it. Otherwise add it.

1. **On an answer.** A call is in stage `signalling` and its calling circuit's `op` goes `"on"`. That is the answer, the event that takes the call out of `signalling`. Publish `sbgame/audio/monitor/source/set` with the calling circuit id, QoS 1, not retained.
   - For a call from a station, send that station, such as `station/11`.
   - For a call from outside, send the trunk the game rang in on, such as `trunk/3`.
2. **Nowhere else in a call.** Don't change the source when the operator bridges onto a call already past `signalling`, whether she is listening in or going back to a caller. Only answers move it, and the most recent answer wins. `after:` scenes follow the same rule.
3. **Game start and every stop.** Publish `"tap"` when a game starts and whenever it stops: a page Stop, or a stop for a lost client (§3).
4. **Don't wait for the echo.** Don't touch the monitor gain or turn the monitor on or off.
5. **Log** each move in `game/log` as `HH:MM:SS [n] monitor: <calling line>`, where n is the call number and the line name comes from script.yml (§6.2).

## Part 3: the status page (game_control.md Rev 6 §7.1, §7.2)

1. In the health area, next to `monitor`, show the monitor's source. Show `tap`, or the jack label of the circuit it names, taken from the `board/` map. If no jack carries that circuit, show the circuit id.
2. Grey it out while `audio_status` is offline, like the other audio topics.

The page publishes nothing new. The broker's access list doesn't change.

## Verification

- `game_control.md` §9 step 9: the loudspeaker follows the call.
- `audio.md` §15 step 7: the tap trim, and a listen for the balance between caller and called party. These are bench settings for Mark.

## Report back

- Anything in the specifications that is ambiguous or contradicts the code.
- What is in `sbaudio` and the game program when you finish, so the next revision of `audio.md` and `game_control.md` can record the build state.
