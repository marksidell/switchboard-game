**551 Switchboard Simulator**

**Claude Code Task — Audience Monitor to A32 Output 24, Operator Tap to Channel 23**

*Task 2 — 2026-09-23. Specification: audio.md Rev 7 (§1.7 is the change list), station_circuit.md Rev 3.40, mqtt.md Rev 9, control.md Rev 10. The documents are the authority; this file says where the change lands in code. If the code and a document disagree in a way this file does not cover, stop and report rather than decide.*

# 1. What changed in the design

Mark moved the audience monitor loudspeaker feed off the Digiface USB's own analog output and onto an A32 balanced output. To free that channel the operator tap moves down one strip. Station board 3 is now:

```text
  strip 7  = A32 channel 23 = operator tap      (was station 23)
  strip 8  = A32 channel 24 = audience monitor  (was the operator tap)
```

| | Before (audio.md Rev 6) | After (audio.md Rev 7) |
| --- | --- | --- |
| Stations | 1–23 | 1–22 |
| Operator tap, playback and capture | doc ch 24, ALSA index 23 | doc ch 23, ALSA index 22 |
| Operator tone (bin 768) out | playback index 23 | playback index 22 |
| `optone` own-tone check reads | capture index 23 | capture index 22 |
| Monitor chain input | capture index 23 | capture index 22 |
| Monitor chain output | playback indices 32 and 33 (Digiface 33/34) | playback index 23 (A32 out 24), or what `--monitor-ch` names |
| Capture doc ch 24 (index 23) | tap receive | unused — nothing fitted on the board; read nothing from it |
| Pilots generated on | doc ch 1–23, 25–32 | doc ch 1–22, 25–32 |
| Comb slots not generated | 24 (bin 696) | 23 and 24 (bins 688, 696) |
| Detector inputs | 31 circuit channels | 30 circuit channels |
| Playback channels 33/34 | monitor | silence, except test tone or `--monitor-ch 33,34` |

The ALSA stream does not change: still `hw:<id>`, 48kHz, S32_LE, 34 playback channels, capture as reported. Nothing in §4 of audio.md moves.

# 2. Changes to `sbaudio`

Work from audio.md Rev 7 §1.7 and §2. Start by grepping the source, the tests, `docs/pilot-map.md` and `CLAUDE.md` for every place that encodes the old map — literal `23`, `24`, `32`, `33`, `1-23`, `1–23`, and any constant for station count, tap channel or monitor channels. The aim is that the channel map lives in one place and everything else derives from it; if it does not today, make it so as part of this change, since this is the second time the map has moved.

1. **Channel map constants.** Stations 22. Tap document channel 23 (index 22). Monitor default document channel 24 (index 23). Trunks unchanged at 25–32. Circuit slot numbering for the comb is unchanged (station §8.3): station n is slot n, trunk n is slot 24 + n.

2. **Pilot generation.** Pilots on stations 1–22 and trunks 1–8 only. Nothing on playback index 23 except the monitor (or silence); no pilot there. Slots 23 and 24 are not generated anywhere.

3. **Operator tone.** Generated on playback index 22, same table, same `--op-db`.

4. **Detector.** Snapshot and transform the 30 circuit capture channels: indices 0–21 and 24–31. `identify_peer()` still searches all 32 comb slots — a pilot heard at slot 23 or 24 is an `ambiguous`/crosstalk diagnostic, not something to hide — but no circuit is created for them. The tap's own-tone check (`optone`, audio.md §6.3) reads bin 768 from capture index 22. Capture index 23 is read by nothing: not the detector, not the monitor, not the speech detector.

5. **Monitor chain.** Input capture index 22. Output as selected by the new option below. The filter, gain, ramp and limiter are unchanged (audio.md §10.1).

6. **New option `--monitor-ch LIST`** (audio.md §14). Comma-separated document channel numbers from the set {24, 33, 34}; default `24`. Anything else — a circuit channel, the tap channel, an empty list, a duplicate — is a startup error with a clear message, not a clamp. Every listed channel carries the same monitor samples; channels in {24, 33, 34} that are not listed carry silence. `--monitor-ch 33,34` reproduces the Rev 6 behaviour and is the fallback route.

7. **Test tone.** `audio/test/<1-34>` range unchanged. On channel 23 it displaces the operator tone; on 24 (or 33/34 when named by `--monitor-ch`) it displaces the monitor; on an unlisted 33/34 it displaces silence. `optone` goes `deaf` while 23 is under test — expected, not a fault.

8. **MQTT validation** (audio.md §12, mqtt.md Rev 9). Station n valid 1–22. `station/23/...` and `station/24/...` commands are logged and dropped like any other out-of-range topic. Initial-state and reconnect publishes cover stations 1–22 only.

9. **Speech detection and `--dump`.** Stations 1–22 and trunks 1–8. `--dump` refuses station 23 and 24.

10. **Startup log.** Print the channel map actually in use — station range, tap index, monitor output indices — alongside the negotiated ALSA parameters, so a wiring check can be done from the journal.

11. **Version and header comments.** Cite audio.md Rev 7. Remove or correct any comment that names Digiface 33/34 as the monitor or channel 24 as the tap.

12. **Rev 6 end-of-speech.** If the audio.md Rev 6 §1.6 listen state machine (`"silence"`, `--vad-hangover`, `--vad-max-speech`) is not already in, it is still owed; do it in the same pass or say that it is outstanding.

# 3. Tests

- Update `pilot_loopback_test.cpp` (and anything else) for 22 stations and the new tap index. A loopback of every generated pilot should still report each circuit's own pilot and nothing at slots 23 and 24.
- Add a unit test for `--monitor-ch` parsing: `24`, `33,34`, `24,33` accepted; `23`, `1`, `25`, `""`, `24,24` rejected.
- Add a render test, or extend an existing one, showing that with default options playback index 23 carries the monitor and indices 32 and 33 are zero; and with `--monitor-ch 33,34` the reverse.
- The §10.1 elliptic stopband test is unchanged and should still pass.

# 4. Other code in the repo that encodes the station range

Same pass, separate commits, only if the code exists in this repo:

- **Controller firmware** (control.md Rev 10 §1.10). `sb_table.cpp` / `sb_table.h`: remove the station 23 row (board 3, address 0x22, bit 6), leaving 22 station rows and 8 trunk rows, 30 in all. Any station count in `sb_config.h` goes from 23 to 22, and any comment that places the tap on board 3 bit 7 now names bits 6 and 7 (tap and monitor, both unmapped). No other behaviour changes. The full republish becomes 68 messages over 30 circuits (control.md §9.2); if a constant or comment carries 70 or 31, update it.
- **Game program and the TTS loader.** Any station-number validation that accepts 1–23 accepts 1–22. `tts_task.md` §3.1 says "within 1–23" and has not been revised; treat it as 1–22. `script.yml`'s comment has already been updated and no station in it uses 23 or 24.
- **`CLAUDE.md`.** Update the invariants: 22 stations, tap on A32 channel 23, monitor on A32 output 24, Digiface 33/34 as fallback only.

# 5. One-time broker cleanup

Retained topics for `station/23` from earlier runs will sit on the broker and look current to a game program that subscribes with a wildcard. After deploying, clear them once by hand — this is an operations step, not program behaviour:

```text
for t in ring hook peer op play listen; do
  mosquitto_pub -r -n -t sbgame/station/23/$t
done
```

Add the broker credentials the host uses. `station/24` should already be clear since audio.md Rev 1; clear it the same way if anything shows up under `mosquitto_sub -v -t 'sbgame/station/24/#'`.

# 6. Done when

- It builds, the tests pass, and `sbaudio --version` reports Rev 7.
- Run against the Digiface with no game program: `mosquitto_sub -v -t 'sbgame/#'` shows stations 1–22 only, `optone` ok once the tap strip is wired, and nothing under `station/23` or `station/24`.
- Test tone on channel 24 is heard at the monitor amplifier; test tone on 33 is heard at the Digiface phones jack; with `--monitor-ch 33,34` the monitor itself moves to the phones jack.
- Report back: the files changed, anything in the documents found to be wrong or ambiguous while doing it, and whether the Rev 6 end-of-speech work was already in.
