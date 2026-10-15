**551 Switchboard Simulator**

**Audio Program Specification**

*Rev 14 — C++ on the Linux Host, One Duplex ALSA Stream on the Digiface USB (32 In, 34 Out, 48kHz, S32_LE), Pilot Comb and Operator Tone Always On, Pilot Detector per Station §8.7, File Playback on the Circuits and the Operator Tap and Trunk Tones on Command, Speech Detection on Command, Filtered Monitor to the Loudspeaker on A32 Output 24 from the Operator Tap or a Commanded Circuit, with a File Summed In, 1kHz Test Tone, an Output Self-Check, All Commanded and Reported over MQTT*

# 1. Overview

The audio program is one of the two host programs (mqtt.md §1). It is C++, it runs on the Linux host, and it owns every audio channel in the system: the 32 balanced channels of the Ferrofish A32 in both directions, reached through the RME Digiface USB over ADAT — one of which, A32 output 24, feeds the audience loudspeaker (station §8.8) — and the Digiface's own analog output pair, idle in normal running and kept as the fallback monitor output. It does six things:

1. Plays the pilot comb on every circuit channel and the operator tone on the tap channel, continuously, and runs the FFT pilot detector of station §8.7 on every circuit input to find which circuits the switchboard has patched together and which the operator is bridged to. This is the job the program has had since station Rev 3.1; everything below is new at this revision.
2. Plays a 48kHz `.wav` file on a station or trunk channel on command, and reports when it has finished.
3. Plays dial tone, ringback or busy tone on a trunk channel on command, in the standard cadence, until told to stop.
4. Listens for speech on a circuit channel on command and reports when speech starts, when it ends, or that it did neither in time.
5. Pipes one receive channel to the loudspeaker through the low-pass filter of station §8.8 — the operator tap's by default, or a station's or trunk's on command (§10.3) — with a commanded on/off and level.
6. Plays a 1kHz test tone on any output channel on command, as a wiring and level diagnostic.

Everything is commanded and reported over MQTT. The topics are specified in mqtt.md §5 and §6; this document says what the program does with a command, when it publishes, and how the audio is generated, mixed and analysed. Station §8 owns the pilot comb, the detector algorithm and the monitor filter specification, and this document points to those sections rather than restating them. The game program (Python) is the only client that commands; the audio program never commands anything.

Ownership. This document is the specification. The source is written to it by Claude Code, in the same way `control/control.ino` is written to `control.md`, and chat sessions do not produce or revise the source. When a revision here has a code consequence, the revision says so.

Build state as of Rev 9. The program exists — `sbaudio`, written by Claude Code against Rev 2 and reviewed in chat on 2026-09-18. §1.3 records the decisions the implementation made where the specification was silent, now adopted, and the three corrections the review sent back, which Claude Code fixed the same day. Claude Code reported on 2026-09-24 that `sbaudio` is at Rev 8, which takes in the code consequences of Rev 6, Rev 7 and Rev 8 (§1.6 to §1.8). Rev 9 settles three questions that report raised (§1.9); two of them carry small code consequences. Nothing has yet run against the A32 and the switchboard; §15 is still to be done.

Numbering. Circuits, A32 channels and Digiface channels are 1-based throughout the project documents: station n is A32 channel n, trunk n is channel 24 + n, the tap is channel 23, the monitor is A32 output 24. ALSA frame indices are 0-based, so the program's internal index for a channel is the document number less one — the tap is index 22 and the monitor index 23. Rev 1 to Rev 6 had the tap on channel 24 and the monitor on Digiface playback 33 and 34; the rough specification Rev 1 was written from gave those as 23 and 33, which were ALSA indices. §2 records the mapping.

## 1.1 Changes in Rev 1

— New document, written from a rough specification of the six functions above and from station §8 and mqtt.md Rev 4. The detector was the program's whole job until now and was specified only in station §8.7, with the program named but not described in mqtt.md §1. The five commanded functions are new.

— One decision made that the rough specification left open: how the program reports that a file has finished. It asked for "an mqtt response when a file finishes playing". The response is the `play` state topic going empty (§7.4), not a new event topic. mqtt.md §2 allows one event in the design, `digit`, and records what an event costs: unretained, not idempotent, lost across a game restart. None of that is wanted here. A retained state topic carrying the filename while it plays, and cleared when it stops, tells the game the same thing and additionally tells a game program restarted mid-file what is playing.

— One conflict with station §8.8 resolved in §8.8's favour. The rough specification asked for the monitor low-pass at 3kHz. Station §8.8 specifies a passband edge of 3.6kHz and a stopband edge of 5.6kHz, and it is the stopband edge that removes the lowest pilot at 6000Hz, not the passband edge. Moving the passband edge to 3kHz would cut the top of the 300–3400Hz band the switchboard passes and remove nothing that 3.6kHz does not already remove. The filter is as §8.8 specifies (§10). If the intent was a narrower, more "telephone" sound rather than pilot removal, that is a passband-edge parameter and is exposed as one.

— Tone frequencies are the pre-precise-tone-plan Bell tones — dial tone 600Hz modulated by 120Hz, ringback 420Hz modulated by 40Hz at 2s on, 4s off — chosen by Mark on 2026-09-17, before this document was first uploaded, in place of the precise tones (350 + 440Hz, 440 + 480Hz) the first draft carried as the default. The 551 predates the precise tone plan and the exhibit is set in that period; the precise tones are what a modern ear expects and would be the one anachronism the operator hears on every call. The precise tones are recorded in §8.2 as the alternative, since they are the same generator with a different table.

— Busy tone added to §8 at Mark's request, same day, after the first draft listed it as a possible extension: the game's scenarios will include called numbers that are busy. One more row in the §8.2 table and one more `tone/set` value; mqtt.md Rev 6 carries the payload.

— The test tone replaces the pilot on its channel rather than summing with it, so the circuit reports `deaf` while the test tone is on (§11.1). Recorded so the `deaf` is not mistaken for a fault.

## 1.2 Changes in Rev 2

— The Digiface is not addressed as `hw:Digiface`. Claude Code found on the host that ALSA registers the card under an alphanumeric identifier, not under the product name Rev 1 assumed in §4 and as the `--card` default in §14. §4 now says the card is addressed by whatever id `/proc/asound/cards` reports for it, §14's `--card` has no default and is required, and the id in use goes in the systemd unit alongside the other host-specific settings. Rev 1's default would have failed to open the device on every start.

## 1.3 Changes in Rev 3

— Written against the finished program, as control.md Rev 4 was against the firmware. Nine implementation decisions are adopted into the text with their reasoning, and three defects found in review are recorded here as code consequences for the Claude Code side.

— Adopted, §3: the MQTT thread is a polled loop — `mosquitto_loop()` with a 20ms timeout, then drain the result queue, then repeat. A result posted by the audio or analysis thread reaches the broker within 20ms, inside the 43ms detector hop, and one thread does the whole job. The alternative — libmosquitto's own network thread plus an eventfd the audio thread would have to write — was not needed.

— Adopted, §3 and §6.1: the analysis thread polls a two-slot mailbox with a 2ms sleep rather than waiting on a condition variable, so the audio thread touches nothing but an atomic to hand over a hop. Two snapshot buffers; if the analysis thread still holds the one due to be filled, the hop is dropped and counted, never waited for.

— Adopted, §14: `--no-realtime`, and the audio thread's SCHED_FIFO priority is 70. `--window rect|hann` implements station §8.2's Hann fallback, with the guard offsets moved to ±4/±5 because Hann's main lobe is ±2 bins and guards at ±2/±3 would measure the pilot's own skirt. `--mqtt-user`, `--mqtt-pass`, `--mqtt-pass-file` and `--client-id` for mqtt.md §9; `--broker` takes `host[:port]`. FFTW wisdom is cached at `$SBAUDIO_WISDOM` or `~/.cache/sbaudio-wisdom`.

— Adopted, §7.1: an empty `play/set` payload is a stop, the same as `"stop"`. A filename is at most 31 characters and may not contain a backslash or a control character, in addition to the `/` and `..` rules of mqtt.md §7. Adopted, §9.2 and §14: every dBFS figure in the program — the VAD floor and margin, the file content check, the logged levels — is referenced to a full-scale sine, RMS × √2, so `--vad-floor -50` means a signal whose RMS is that of a −50dBFS sine. Adopted, §13.2: reconnect backoff starts at 1s and doubles to 30s; the will is registered once on the handle and survives reconnects.

— Code consequence 1, §3: the MQTT thread spins while disconnected. `mosquitto_loop()` returns at once with no connection, so between reconnect attempts the loop runs flat out — a core pegged for up to 30s at a time. Sleep 20ms per pass when not connected. Harmless to the audio thread, which is real-time, but wrong.

— Code consequence 2, §6.1: the snapshot handover has a race. The audio thread checks a buffer's busy flag before filling it, but the analysis thread sets that flag only after it has taken the buffer's index from the mailbox, so a late-waking analysis thread can claim a buffer the audio thread has just started to overwrite. Separately, a hop that the analysis thread never collected is silently superseded and not counted. The protocol is restated in §6.1 so that the audio thread owns setting busy and the analysis thread owns clearing it, and a superseded hop is reclaimed and counted.

— Code consequence 3, §12: `audio_status` `"online"` is published before the first detector pass rather than after it. The spec and mqtt.md §8.4 put state before birth; the program publishes birth and lets `peer`, `op` and `optone` follow on the next hop, up to 43ms later. Hold the birth message until the analysis thread has completed its first forced pass.

— Minor, for the same pass: `ambiguous` logs its pilot list every hop, 23 lines a second for as long as the condition lasts; log it on the transition and at most once a second after. `--version` still reports Rev 1. The tarball reviewed did not include the build file, `pilot_loopback_test.cpp` or `docs/pilot-map.md`, so the §10.1 unit test on the elliptic stopband is unconfirmed; the startup log line that reports the realised response at 6000Hz covers it in practice.

## 1.4 Changes in Rev 4

— The three Rev 3 code consequences are fixed in `sbaudio` (2026-09-18); the build-state paragraph in §1 says so.

— §14: the default MQTT client id is `sbgame-audio`, not `sbaudio`. Rev 3 wrote the binary's name; the program used `sbgame-audio`, which follows the ESP32's `sbgame-esp32` — the `sbgame-` prefix names the system the client belongs to, as the topic prefix does, and the broker's client list then reads as one system. Mark and Claude Code chose the program's form; the document follows.

## 1.5 Changes in Rev 5

— Cross-reference only. `esp32.md` is `control.md` and `ring/esp32.ino` is `control/control.ino` as of 2026-09-19 (control.md Rev 9); §1 and §1.3 follow. Nothing in this document changes.

## 1.6 Changes in Rev 6

— The listen reports the end of speech as well as the start. Rev 1 to Rev 5 made a listen one-shot: `"listening"`, then `"speech"` the moment speech was detected, and the listen was over. The game's scenarios need to know when the caller has finished talking, not only that they began — a scripted reply that starts while the caller is mid-sentence is the one thing the audience will notice. So the listen now continues after `"speech"` and reports `"silence"` when the talking stops, or `"timeout"` if it does not stop within a cap. One command still starts the whole sequence; the state topic carries it, which is what a retained state topic is for. §9.1 and §9.2.

— The payload stays one number, the time allowed for speech to start. The two new times — the silence that counts as the end of speech, and the longest speech the program will wait out — are options with defaults (§14), not payload, because they describe how people talk and not a scenario, and because mqtt.md §2 says one value per topic. If a scenario ever needs its own cap, that is the point to add a second payload form; not before.

— `"silence"` is a new value rather than the empty string, so that a listen that completed is never confused with one that was cancelled or never issued: empty stays the cleared state, as on every retained topic (mqtt.md §7). `"timeout"` is reused for both failures — speech never started, speech never stopped — because the game knows which by the value before it, and a game restarted mid-listen has lost the listen either way.

— Code consequence, for Claude Code: `Engine::start_listen`, the VAD frame loop and `cancel_listen` change to the state machine of §9.2; two options, `--vad-hangover` and `--vad-max-speech`; `mqtt.md` Rev 8 has the payload values. mqtt.md Rev 8 follows.

## 1.7 Changes in Rev 7

— The audience monitor moves to A32 output 24 and the operator tap to A32 channel 23, following station Rev 3.40 (Mark, 2026-09-23). Rev 1 to Rev 6 put the tap on channel 24 and sent the monitor to the Digiface's own analog output, playback 33 and 34. Station board 3 strip 7 is now the tap and strip 8's A32 output is the monitor feed, so stations are 1–22. §1, §2, §5.1, §6.3, §10, §11.1, §12, §14, §15 and §16 follow.

— Why. An A32 output is balanced, and its analog level is set by the A32's per-channel reference and trim, recallable from its front panel. The Digiface jack is unbalanced and fixed at +9.5dBu full scale with no TotalMix under Linux, which left this program's gain as the only control ahead of the amplifier. Station §1.19 records the decision.

— The Digiface is still opened at 34 playback channels, so nothing in §4 moves. Channels 33 and 34 carry silence except under the test tone, and are the fallback monitor output: going back to them is a command-line change, `--monitor-ch 33,34` (§14), not a code change. That option is new.

— Capture channel 24 is now unused — station board 3 strip 8 has no receive path fitted — and nothing reads it. It is not a detector input. Comb slots 23 and 24 (bins 688 and 696) are not generated.

— Code consequence, for Claude Code: the channel map of §2 and everything derived from it. Stations 1–22 in the per-circuit tables, the detector and the MQTT validation (§12); pilots on 1–22 and 25–32; the operator tone and the `optone` check on channel 23; the monitor chain reading capture 23 and writing playback 24, or the channels `--monitor-ch` names; capture 24 ignored; playback 33 and 34 silent unless named by `--monitor-ch` or under test. mqtt.md Rev 9 has the topic ranges.

## 1.8 Changes in Rev 8

— The monitor can take its input from any station or trunk receive channel as well as from the tap (§10.3). Mark's decision, 2026-09-24. Rev 1 to Rev 7 fed the loudspeaker from the tap's receive channel only. The operator leaves a call when she throws the ring key to ring the called party, and does not come back to it, so the audience heard the request and the operator and then nothing of the conversation the scene was written for. A circuit's receive channel carries the whole conversation: its own transmit returns on it at full strength, because the interface has no hybrid (station §8.4), and the far end arrives through the cord. The operator's voice is on it too while she is bridged to that line.

— One new command and its echo: `sbgame/audio/monitor/source/set` and `sbgame/audio/monitor/source`, with `"tap"` or a circuit id as the payload (mqtt.md Rev 13). `monitor/set` stays the gain alone, so the one-value rule of mqtt.md §2 holds. The game program chooses the source: the calling line of the call the operator most recently answered (game_control.md Rev 6 §6.4). This program knows nothing about calls and does not choose.

— The chain after the input is unchanged. The station §8.8 filter removes a circuit channel's own pilot, its peer's pilot and the operator tone exactly as it removes the operator tone and pilots from the tap channel.

— The switch is made under a 20ms ramp to silence and back (§10.3), the same ramp the gain uses, so a source change does not click.

— Two options (§14). `--monitor-src` sets the source at startup, `tap` by default, so a bench run with no game behaves as Rev 7 did. `--monitor-tap-trim` is a gain applied only while the source is the tap. The tap arrives about 15dB below the operator's line (station §7.9.3), and a circuit channel sees its line through T2 alone, so without a trim one monitor gain cannot suit both. Its value is a bench setting (§15 step 7).

— The source returns to the tap when the program loses the game or the broker (§13.2). The calls it was following have been torn down, and a crashed game should not leave the loudspeaker on a line nobody is using.

— Not added: any correction for the balance between the two sides of a conversation on one circuit channel. The line's own transmit returns through its own transformer's secondary only; the far end crosses two transformers and the cord circuit. The own side will be louder by an amount nothing measured so far predicts. §16 records the fix to add if the bench says it is needed.

— Code consequence, for Claude Code: subscribe to `monitor/source/set`; validate it and echo it on `monitor/source` (§12); switch the monitor's input in the audio thread as §10.3 says; `--monitor-src` and `--monitor-tap-trim`; the return to the tap in §13.2; `monitor/source` in the state published before birth (§12).

## 1.9 Changes in Rev 9

— Written against Claude Code's report of 2026-09-24: `sbaudio` is at Rev 8. The report raised three places where Rev 8 was silent or read two ways. This revision settles them.

— The tap trim has a range: −30 to +30dB, and `--monitor-tap-trim` outside it refuses to start, as any other invalid option does (§10.3, §14). Rev 8 gave no range. The effective gain — the commanded gain plus the trim — is deliberately not clamped to the −60 to +20dB of `monitor/set`. That range is for the command. The trim is an installation constant that makes the tap and a circuit sound the same at one commanded gain. Clamping the sum would cap the tap at a lower commanded gain than a circuit, which is the mismatch the trim exists to remove. The −3dBFS limiter is what protects the output (§10.1). Claude Code left the sum unclamped and asked whether that was intended. It is. Code consequence: the range check at startup.

— State republished on reconnect is what the program is doing at reconnect (§12, §13.2). §13.2 said results posted while disconnected are discarded, and §12 said reconnect republishes state. For `monitor/source` the two pulled apart. A source changed while disconnected — the return to the tap, above all — would have been discarded as a result, and reconnect would have announced a circuit the program had already left. Claude Code kept the value current while disconnected and republished it. That is adopted. The discard applies to results the other threads post. State on reconnect is read from the program as it stands, for `monitor`, `monitor/source` and `test/<ch>` alike. No code consequence.

— A source the device does not capture is refused (§10.3). Rev 8 validated a source against the circuit ranges only. So on a device presenting fewer than 32 capture channels, `--monitor-src trunk/8` started, echoed `trunk/8` and fed silence. A loudspeaker fed silence while the echo names a live line looks like a line with nobody on it, and nothing says otherwise. Now `--monitor-src` naming a channel beyond the capture count the device reports refuses to start, as `--monitor-ch` does for a bad playback channel. A `monitor/source/set` naming one is logged and dropped with no echo, like any invalid payload. On this system a capture count below 32 is itself a fault, and one the detector would suffer too (§16, capture channel count). Code consequence: the check at startup and on the command.

## 1.10 Changes in Rev 10

— The operator tap plays files (§7), following game_control.md Rev 25, 2026-09-30: `sbgame/audio/tap/play/set` and its echo `sbgame/audio/tap/play`, as a circuit's `play/set` and `play` (mqtt.md Rev 23). It is for the game program's diagnostics, which play speech into the operator's headset to check the tap's output path. The file sums over the operator tone, which is never displaced (§5.2), so the tap stays detectable while it plays; the tap has no trunk tones. Nothing else about the tap changes: its receive side, the optone check and the monitor source are as they were.

— Code consequence, made the same day: the mixer sums a file on channel 23; the MQTT thread subscribes to the tap's `play/set`, handles it as a circuit's, and publishes `audio/tap/play` at start, on stop and on shutdown as it does a circuit's `play`. `ctest` covers the mix and the topic.

## 1.11 Changes in Rev 11

— The monitor plays a file (§10.4), following game_control.md Rev 29, 2026-10-08: `sbgame/audio/monitor/play/set` and its echo `sbgame/audio/monitor/play`, as a circuit's `play/set` and `play` (mqtt.md Rev 27). It is the tutor's voice in tutor mode, heard on the loudspeaker. The file is summed into the monitor chain after the source's filter, through a second copy of the same low-pass, then takes the monitor's gain and limiter: the loudspeaker is in the room with the operator's microphone, so the file is held out of the pilot band exactly as the source is, and the monitor's one level sets both. A new option, `--monitor-file-trim`, sets the file's level against the source's. Nothing else about the monitor changes.

— Code consequence, made the same day: the file is slot 24's program source; `process_capture()` sums it into the chain and stops it at its end; the MQTT thread subscribes to the monitor's `play/set`, handles it as a circuit's, and publishes `audio/monitor/play` at start, on stop, on the game's loss and on shutdown; `ctest` covers the mix, the echo and the mute.

## 1.12 Changes in Rev 12

— An output self-check (§11.4), 2026-10-14. On the bench that afternoon, with only the audience monitor connected to the A32 and the test tone on 24, the A32's output meters showed channels 9, 17 and 25 steady near 0dBFS and, every 4–5s, a burst of about 1.5s taking nearly every output close to full scale; the detector heard the bursts on capture from 15:07:25 to 15:24:44. Nothing had been commanded, the log showed no xrun, clip or limiter count, and the A32's routing and clock were correct (ADAT 1–32 to analog 1–32, slaved to ADAT port 1, all four ports locked at 48kHz). Stopping `sbaudio` cleared the meters; `tone_out` driving the same channels at the same levels was clean; and `sbaudio` restarted, by hand at periods of 1024 and 256 and then under its service with the test tone on 24, was clean for the next half hour. So the process that had run since 07:32 got into a state that a restart cleared, and nothing says whether the bad samples were in its playback buffer or were corrupted after it. The check answers that the next time: it compares what the program is about to write with what each channel should carry. If it logs the channels the meter shows, the fault is in the program; if it stays silent while the meter misbehaves, it is after the program — ALSA, USB or the Digiface.

— Code consequence, made the same day: `render()` records each channel's ceiling, and a scan of the playback buffer before each write counts the periods that exceed it per channel; the MQTT thread logs them with the counters (§11.2). `ctest` covers a clean render and a corrupted one.

## 1.13 Changes in Rev 13

— The detector's peer window, `--peer-window-db`, following station Rev 3.46 §8.7: a comb pilot counts only if it is within that many dB of the circuit's own pilot as well as `MARGIN_DB` above its floor. On the bench, 2026-10-15, the trunk board's strip-to-strip crosstalk, 72dB under each trunk's own pilot, sat 20–39dB above the floor and made every idle trunk `ambiguous`; a station cabled straight to a trunk arrived 3dB under the own pilot. 40dB is the starting value. A peer through the switchboard will arrive lower than through a cable, so §15 step 6 sets the window with the margin.

— Code consequence, made the same day: the option, the test in the detector, and the startup log line reports both values. `ctest` has an idle trunk with that crosstalk, which reads idle, and a connected one, which reads its peer.

## 1.14 Changes in Rev 14

— `--op-window-db`, 20 by default, following station Rev 3.47: the operator tone counts only within that many dB of the circuit's own pilot. The tap's 9kHz leaks into other channels, 46dB under the own pilot on station 22, enough above the floor to light `op` on nine circuits with nothing bridged (2026-10-15). §15 step 6 now measures the operator tone on a bridged circuit as well.

— Code consequence, made the same day: the test in the detector. `ctest` has the leak on an idle trunk, which reads `op` off.

# 2. Channel Plan

One ALSA card, the Digiface USB, opened in both directions at 48kHz, S32_LE. Playback is 34 channels — confirmed on the host at station Rev 3.37 — and capture is expected to be 32 (the four ADAT ports; the Digiface has no analog input) and is to be confirmed the same way (§16).

| **Document channel** | **ALSA index** | **Playback carries** | **Capture carries** |
| --- | --- | --- | --- |
| 1–22 | 0–21 | Station 1–22: pilot at comb slot n + program source | Station receive: detector input; speech detection on command; monitor source on command (§10.3) |
| 23 | 22 | Operator tap: 9000Hz operator tone, and a file on command (Rev 10, §7) | Tap receive: the default monitor source (§10.3) and the tap's own-tone health check (§6.3) |
| 24 | 23 | Audience monitor (§10), with a file summed in on command (Rev 11, §10.4) | Unused — station board 3 strip 8 has no receive path |
| 25–32 | 24–31 | Trunk 1–8: pilot at comb slot 24 + n + program source | Trunk receive: detector input; speech detection on command; monitor source on command (§10.3) |
| 33, 34 | 32, 33 | Silence; the fallback monitor output under `--monitor-ch` (§10.1) | — |

The program source on a circuit channel is one of: nothing, a file (§7), a trunk tone (§8, trunks only) or the test tone (§11.1). Exactly one is active on a channel at a time; a new one replaces the current one (§5.2). The pilot is always present on channels 1–22 and 25–32 and is not a program source; the operator tone is always present on channel 23 and is not one either. The test tone is the one source that may be placed on channels 23, 24, 33 and 34 as well, where it replaces the operator tone, the monitor or silence for as long as it runs.

Slots 23 and 24 of the comb (bins 688 and 696) are not generated while station board 3's strips 7 and 8 are the tap and the monitor, per station §7.9.6. The mapping from circuit to comb bin, `512 + 8 × (slot − 1)`, is station §8.2 and is not restated here.

# 3. Program Structure

Three threads and two lock-free queues. Nothing else runs concurrently.

**Audio thread.** Owns the ALSA stream. Runs one period at a time: read a capture period, run the per-sample work on it (§9 detector front-end accumulation, §9 speech-detection frames, §10 monitor chain), render one playback period (§5), write it. SCHED_FIFO, memory locked, no allocation, no file I/O, no locks, no MQTT — it communicates only through the two queues. Everything it plays is either generated arithmetically or read from a buffer that was filled before the command reached it.

**Analysis thread.** Receives 4096-sample blocks per capture channel from the audio thread at the 2048-sample hop (§6), runs the FFT and the detector, and hands results to the MQTT thread. It also runs the detector's logging (§11.2). Normal priority. It is separate from the audio thread so that thirty-two 4096-point FFTs every 43ms — a fraction of a millisecond of work, but bursty — never sit inside a period deadline. It waits by polling the snapshot mailbox with a 2ms sleep (§6.1) — chosen over a condition variable so that the audio thread has nothing to signal but an atomic store. Two milliseconds on a 43ms hop is nothing, and 500 empty wake-ups a second are nothing on this host.

**MQTT thread.** Runs the libmosquitto network loop as a polled loop: `mosquitto_loop()` with a 20ms timeout, then drain both result queues and publish, then check the game heartbeat, then repeat. It sleeps in `select()` on the broker socket for up to 20ms or until traffic arrives, so a command is handled as it lands and a result posted by the other two threads waits at most 20ms — inside the detector hop and invisible to the game. When there is no connection `mosquitto_loop()` returns at once, and the loop must sleep the 20ms itself or it spins (Rev 3 code consequence 1). Translates each incoming command into a queue entry for the audio thread; for a file command it loads and validates the file first (§7.2), in the message callback, and passes the audio thread a pointer to a buffer it may not free until the audio thread has released it. Publishes the birth message, holds the LWT, and watches `game_heartbeat` (§13.2). It is the main thread: it becomes the MQTT thread once the other two are started.

**Command queue**, MQTT thread → audio thread, single-producer single-consumer. Entries are small fixed-size structs: channel, verb, a numeric argument, a buffer pointer for files.

**Result queue**, audio thread and analysis thread → MQTT thread. Two producers, so either two SPSC queues or one MPSC; either is fine. Entries: topic key, value. The audio thread posts play-finished, listen results and the echoed state of every command it has acted on; the analysis thread posts detector results.

Buffer lifetime for files: the MQTT thread allocates, the audio thread plays, and when the audio thread stops playing a buffer — end of file, stop, or replacement — it posts the buffer back on the result queue for the MQTT thread to free. No reference counting, no atomics beyond the queues.

# 4. The ALSA Stream

- Device: the Digiface USB by its ALSA card id, `hw:<id>` and not `plughw:`, so that the driver's native S32_LE and 34-channel layout are used and no format conversion or resampling is inserted. The id is the second column of `/proc/asound/cards` (also `aplay -l`), and for the Digiface it is an alphanumeric string the driver derives from the device, not the name "Digiface" — found on the host by Claude Code, 2026-09-18. It is a command-line option (§14) with no default: the id is stable for one unit but is not something this document can predict, and a card index would depend on USB enumeration order. Record the id in the systemd unit.
- Rate 48000, format S32_LE, playback channels 34, capture channels as reported.
- Period 256 frames (5.3ms), buffer 3 periods. Small because the monitor path is an acoustic loop with the room in it (station §8.8) and every period of latency is in that loop. A class-compliant USB device may not sustain 256 without xruns; period and buffer count are options and the bench sets them.
- Playback and capture handles linked (`snd_pcm_link`) and started together, so the two directions share one start and one xrun. The detector does not depend on the relative alignment of playback and capture — each pilot's phase at the far end is arbitrary and the detector measures magnitude only — but the speech detector's own-playback exclusion (§9.3) does depend on them running, and linking is how that is guaranteed.
- Samples are converted to float once on capture and once on playback at the period boundary; all processing is float.
- An xrun on either direction: log it with the uptime, recover both handles (`snd_pcm_prepare` and restart), count it, and continue. The pilots resume on the next period; the detector discards the partial block. A file that was playing continues from where it was — a few milliseconds of silence is preferable to the game seeing a `play` state flicker. Repeated xruns are a configuration problem, not something the program works around, and the count is in the log.

Clocking. The pilots sit exactly on FFT bins only while generation and analysis share one clock (station §8.2). Both directions run through the Digiface, and the Digiface and the A32 must be locked to each other — one the master, the other slaved over ADAT — or the loop from Digiface DAC through the A32's converters and back is two clock domains and the rectangular window is no longer optimal. There is no TotalMix under Linux to set or inspect the Digiface's clock source; §15 gives the check, which is the purity of a circuit's own pilot in its own bin.

# 5. Output Mixer

## 5.1 Sources

Every playback channel is rendered per period as the sum of its fixed source and its program source, in float, then hard-clipped at ±1.0 with a clip count in the log.

**Pilot** (channels 1–22, 25–32). Level −40dBFS per station §8.4, an option. Generated from one shared 4096-entry sine table: for comb bin b, sample n of the 4096-sample cycle is `table[(b × n) mod 4096]`. Because every pilot completes an integer number of cycles per 4096 samples, a per-channel sample counter that wraps at 4096 is the whole oscillator — no phase accumulator, no rounding, no drift, and the pilot is on its bin by construction. The counter is shared across channels; only b differs.

**Operator tone** (channel 23). Bin 768, the same table at `table[(768 × n) mod 4096]`, which is 16 samples per cycle. Level per station §7.9.3: with that channel's A32 reference at +20dBu, about −18dBFS puts 12mV on the operator's line. An option, set from the bench measurement §7.9.5 asks for.

**Program source** (channels 1–22, 25–32): a file, a trunk tone, or the test tone. Unity gain for a file; the tone levels are §8.3 and §11.1.

**Monitor** (channel 24, or the channels `--monitor-ch` names): §10.

## 5.2 One Program Source per Channel

A channel plays one thing at a time. A `play/set` while a tone is running stops the tone; a `tone/set` while a file is playing stops the file; a test tone stops either. The state topics follow: the stopped source's topic clears, the new one's is set (§12). This is deliberate and matches the line being simulated — a trunk does not send ringback and a caller's voice at once, and a station does not talk over itself. It also keeps the game's model simple: to know what a channel is doing, read two retained topics, `play` and `tone`, and at most one is non-empty.

The pilot and the operator tone are not program sources and are never displaced by one, except by the test tone (§11.1). On the tap, a file (Rev 10) is its only program source: it sums over the operator tone as a circuit's file sums over its pilot. On the monitor, a file (Rev 11) is summed into the monitor chain (§10.4).

## 5.3 Content Rule for Files

The pilots are at −40dBFS and the detector's margin is 20dB, so any program energy above about 5.5kHz within 20dB of −40dBFS — that is, above −60dBFS — on a circuit channel will return on that circuit's own receive channel at full strength (the two-wire interface has no hybrid, station §8.4) and can cross the threshold in a neighbouring bin, producing `ambiguous`. Authored speech is pre-rendered at 16kHz with period band-limiting (station §8.8) and has nothing there; a file that was not authored that way must be low-passed before it is put in the wav directory. The program does not filter files on playback, because the cost of a filter in the audio thread is paid on every period forever to fix a content error that is fixed once offline. It does check on load and warn (§7.2).

# 6. Pilot Detection

The algorithm is station §8.7 and is implemented as that listing specifies; nothing about it is restated here. What this section adds is the scheduling and the publishing.

## 6.1 Blocks and Hops

The audio thread appends each capture period to a per-channel ring of 4096 samples and, every 2048 samples, hands the analysis thread a snapshot of every circuit channel's last 4096 — 50% overlap, an update every 42.7ms as §8.2 gives. One real-to-complex 4096-point FFT per circuit channel per hop, rectangular window. The FFT is FFTW3 (r2c, one plan reused, wisdom saved), chosen because it is packaged everywhere, its 4096-point real transform is a few microseconds, and the program has no reason to carry its own.

The handover. The snapshot is a copy — two `memcpy`s per channel that linearise the ring from its write index — into one of two pre-allocated blocks, never a pointer into the live ring; a transform that straddled two hops would break the exact-cycle alignment the rectangular window depends on. The two blocks and a one-slot mailbox holding the index of the block that is ready are the whole mechanism, and the rule that makes it safe is that each side owns one edge of the busy flag:

- Audio thread, each hop: if the block it is due to fill is busy, drop the hop, count it in `hops_lost`, and do not advance — the analysis thread is behind and must never be waited for. Otherwise fill the block, set its busy flag, and exchange its index into the mailbox. If the exchange returns an index rather than empty, the analysis thread never collected that earlier block: clear its busy flag and count that hop as lost too.
- Analysis thread: exchange the mailbox to empty; if it held an index, transform that block and clear its busy flag when done; otherwise sleep 2ms and try again.

The audio thread sets busy and the analysis thread clears it, so there is no window in which both believe a block is theirs. (Rev 2's program had the analysis thread set busy after taking the index, which leaves such a window, and superseded a stale mailbox entry without counting it — Rev 3 code consequence 2.) A dropped hop costs 43ms of detector latency and nothing else; the two-hop confirmation in §6.2 is indifferent to it.

## 6.2 Publishing

`identify_peer()` runs per circuit channel per hop. The result is published to that circuit's `peer` and `op` topics (mqtt.md §5) on change only, and only after the same result has been seen on two consecutive hops. The two-hop confirmation costs 43ms of latency and removes the flicker a cord produces as it is pushed into a jack — a plug making intermittent contact would otherwise publish a burst of `""` / id / `""` that the game would have to debounce itself. Nothing in the game needs a peer faster than 100ms.

`ambiguous` is published as the literal string, and the analysis thread logs the full list of pilots heard with their levels (§11.2), which is the information that distinguishes a threshold problem from crosstalk from a cord fault (station §8.7).

On start, the first hop's results are published for every circuit regardless of the two-hop rule, so the broker carries a value for every circuit within about 100ms of the stream starting (mqtt.md §8.4).

## 6.3 The Tap's Own Tone

The tap's receive channel (23) is not a detector input — it carries the operator tone at close to full level and the pilots of whatever the operator is bridged to, and station §8.8 withdrew it from detection. The one thing read from it is bin 768, the tap's own tone returning, which is the health check on the tap's transmit path (station §8.4). It is checked every hop against the same 20dB guard-bin margin and published retained to `sbgame/audio/optone` as `"ok"` or `"deaf"`, with the two-hop confirmation. This topic is new at mqtt.md Rev 5 and exists because a dead tap transmit path makes every circuit's `op` read off, which looks exactly like an operator who has not plugged in; the game needs the one topic that says the difference.

# 7. File Playback

## 7.1 Command

`sbgame/station/<n>/play/set`, `sbgame/trunk/<n>/play/set`, for the operator tap (Rev 10) `sbgame/audio/tap/play/set`, or for the monitor (Rev 11, §10.4) `sbgame/audio/monitor/play/set`, with the base filename as payload: `greeting_1` plays `wav/greeting_1.wav`. No directory, no extension, no path separator — a payload containing `/`, `\` or `..`, or any control character, or longer than 31 characters, is rejected as a bad name and echoed as `"missing"` (§7.4) with the reason in the log. `"stop"`, or an empty payload, stops whatever is playing on the channel; a file cannot be named `stop`. The wav directory is `wav/` relative to the program's working directory by default and is an option (§14).

## 7.2 Loading

The MQTT thread opens the file with libsndfile, checks it, converts it to float mono in memory, and queues it. A file is accepted if it is 48000Hz and one channel; 16-bit, 24-bit and float PCM are all accepted and converted. Any other rate is rejected rather than resampled — the game's content is rendered at 48kHz on purpose (station §8.8 describes the 16kHz authoring and band-limiting step, after which the delivered file is 48kHz), and a file at the wrong rate is a content error the program should name, not hide. A stereo file is rejected for the same reason: the channel is mono and there is no right answer to which side to take.

On accepting a file the loader also computes the energy above 5.5kHz relative to full scale and logs a warning if it exceeds −60dBFS (§5.3). It does not refuse the file.

Files are loaded whole. Authored content is a few seconds to perhaps a minute; a minute of float mono at 48kHz is 11.5MB. A cap of 120 seconds is an option, and a longer file is rejected with the length in the log.

Files are not cached. Loading a few megabytes from the page cache takes less than the MQTT round trip, and a cache is a second thing to invalidate when content is edited.

## 7.3 Playing

The audio thread starts the buffer at the beginning of the next period after the command arrives, at unity gain, summed with the pilot. A `play/set` on a channel already playing replaces the file from the next period; there is no crossfade. The file plays once. There is no loop, no pause and no seek; none is needed for authored prompts, and each would be a new state to report.

## 7.4 Reporting

The circuit's `play` topic — `sbgame/audio/tap/play` for the tap (Rev 10), `sbgame/audio/monitor/play` for the monitor (Rev 11) — retained, carries the base filename from the period the file starts until the period after it ends, then clears to empty. That clearing is the "finished" response. The game distinguishes finished from stopped by knowing whether it sent `stop`, and from replaced by seeing the new filename instead of empty. A file that could not be loaded publishes `"missing"` — a diagnostic literal on the same topic, in the same way `peer` carries `"ambiguous"` — and the log says why (not found, wrong rate, stereo, too long). `"missing"` persists until the next `play/set` on that channel.

# 8. Trunk Tones

## 8.1 Command

`sbgame/trunk/<n>/tone/set` with `"dial"`, `"ringback"`, `"busy"` or `"off"`. Trunks only: dial tone, ringback and busy tone are what a central office sends toward the switchboard, and a station is the telephone, which sends none of them. A tone runs until `"off"`, until another `tone/set` replaces it, until a `play/set` replaces it (§5.2), or until the program loses the game (§13.2). The state topic `tone`, retained, echoes `"dial"`, `"ringback"`, `"busy"` or empty.

## 8.2 Tones

| **Tone** | **Waveform** | **Cadence** |
| --- | --- | --- |
| Dial | 600Hz, amplitude-modulated by 120Hz | Continuous |
| Ringback | 420Hz, amplitude-modulated by 40Hz | 2.0s on, 4.0s off |
| Busy | 600Hz, amplitude-modulated by 120Hz | 0.5s on, 0.5s off |

These are the Bell System tones of the period the 551 belongs to, before the precise tone plan of the 1960s replaced them with two-frequency sums — dial tone 350 + 440Hz, ringback 440 + 480Hz, busy 480 + 620Hz, same cadences. The precise tones are the alternative, one table away, and are not used: they are what a modern ear expects, and on a board of this age they would be the one anachronism the operator hears on every call. The cadence starts at the beginning of the on period when the tone is commanded, so the operator always hears a burst first.

Busy is the dial-tone waveform interrupted at 60 IPM, which is how the period offices made it — one tone source, one interrupter — and a listener tells the two apart by the cadence alone. That is faithful and it is also the reason to keep the busy cadence exact: a dial tone with a dropout could be mistaken for it. A scenario switches a trunk from ringback to busy, or from dial to busy after the operator dials a busy number, with one `tone/set`; the change takes effect at the next period and the new cadence starts from its on phase.

Each tone is a carrier sine multiplied by `(1 + m × sin(2π f_mod t))`, so the spectrum is the carrier plus one sideband either side at ± f_mod — 480, 600 and 720Hz for dial and busy tone, 380, 420 and 460Hz for ringback — all inside the switchboard's passband and all well clear of the comb. Modulation depth m is an option, 1.0 by default; the period tones were made by beating two sources through a nonlinear element and the exact depth varied by office, so set it by ear against a recording if one is to hand. The generator is two phase-accumulator sines per tone, not the 4096-table, because these frequencies are not an integer number of cycles per 4096 samples and do not need to be — they are program audio, not pilots. Their harmonics are not a concern for the detector: a digitally generated sine has none, and the transformer's distortion at −20dBFS is far below the −60dBFS content rule.

## 8.3 Level

−20dBFS peak by default, an option, the same for all three tones. The period tones had no single specified level; what matters is that dial tone is unmistakable at the headset and ringback and busy are not louder than speech. Set on the bench by measuring at the switchboard's trunk jack and listening at the headset.

# 9. Speech Detection

## 9.1 Command

`sbgame/station/<n>/listen/set` or `sbgame/trunk/<n>/listen/set` with the timeout in seconds as payload — an integer or decimal, capped at 300. `"0"` cancels a listen in progress. A new `listen/set` on a channel already listening restarts it with the new timeout. The state topic `listen`, retained, carries the listen as it runs:

```text
  "listening"   from the command. Waiting for speech to start.
  "speech"      speech has started. The listen continues.
  "silence"     speech has ended: nothing above threshold for the hangover
                time. The listen is over.
  "timeout"     the listen is over without a clean end: either speech never
                started within the payload's seconds, or it started and had
                not stopped after the maximum speech time.
  ""            cancelled, or never issued. Empty is the cleared state.
```

The final value — `"silence"` or `"timeout"` — persists until the next `listen/set` on that channel; a cancel clears it to empty. The game watches the transitions: out of `"listening"` for the start of speech, out of `"speech"` for the end. A game that finds `"timeout"` and needs to know which kind reads the value it replaced; one that was restarted mid-listen has lost the listen either way and reissues it. The payload's seconds bound only the wait for speech to start. The silence hangover and the maximum speech time are options, not payload (§14, §1.6).

## 9.2 Detector

Energy-based, in the voice band, on 10ms frames, in the audio thread:

- The channel's capture is band-passed 300–3400Hz — one second-order high-pass and one second-order low-pass biquad — before anything is measured. The pilots at 6–9kHz are the loudest thing on the channel and must not count; hum must not either.
- RMS per 480-sample frame, in dBFS referenced to a full-scale sine (RMS × √2), which is the convention for every dBFS figure the program reports or accepts.
- The noise floor is the 10th percentile of the frame levels over the second before the command arrived, which the audio thread keeps as a rolling history per channel at all times so it is available the instant a listen starts. During the listen the floor may rise at no more than 1dB/s and never fall, so a slowly rising room does not trigger and a burst does not lower the bar.
- Threshold is the greater of floor + 10dB and an absolute −50dBFS. The absolute term is what stops a very quiet channel from triggering on nothing.
- Speech is declared when at least 20 of the last 30 frames — 200ms of 300ms — are above threshold. A single click or a relay operating is a frame or two; a word is many.
- Speech is declared ended when no more than 2 of the last 30 frames are above threshold and that has held for the hangover time — 1.5s by default. The pauses inside a sentence are shorter than that; the pause after one is longer. A cough or a chair after the caller has stopped is a frame or two above threshold inside the window and does not restart the count; a second sentence does.
- The maximum speech time — 30s by default — runs from the frame that declared speech. If speech has not ended by then the listen reports `"timeout"` and stops. It is a bound on a caller who keeps talking, or on a line that has gone noisy enough to read as speech forever, so that the game is never left waiting on a listen that cannot resolve.

The thresholds, the window, the hangover and the maximum speech time are options. Set them on the bench with the operator speaking a short phrase at normal level through a real cord-pair connection, and with the room's ordinary noise present.

## 9.3 What Is Excluded

Frames during which the same channel has an active program source are discarded, and the 30-frame window restarts when the source ends. The reason is station §8.4's: the two-wire interface has no hybrid, so everything this channel transmits returns on its own receive at full strength, and the program would detect its own file. The echo that persists after the source stops — through the switchboard's cord circuit and the far-end transformer — is milliseconds and is covered by the window restart.

What is not excluded is the far end. If the game plays a file on station 5 while listening on trunk 2 and the two are patched together, trunk 2 hears the file and reports speech. The program cannot know that is not wanted, and the game, which issued both commands, can. Do not listen on a channel whose peer is playing, or expect the result you asked for.

# 10. Audience Monitor

## 10.1 Chain

The source's capture channel — 23, the tap, unless `monitor/source/set` has named a circuit (§10.3) → high-pass, second order, 150Hz → low-pass per station §8.8: elliptic, 8th order as four second-order sections, passband edge 3.6kHz, stopband edge 5.6kHz, stopband 70dB → gain, plus `--monitor-tap-trim` while the source is the tap → limiter → playback channel 24, or the channels `--monitor-ch` names, the same samples on each. All in the audio thread, per sample, with no buffering beyond the period, because the loop through the room is the constraint §8.8 records.

Channel 24 is the A32 output wired to the loudspeaker amplifier (station §7.9.8). `--monitor-ch 33,34` sends the monitor to the Digiface's own analog output instead — the route of Rev 1 to Rev 6, kept as the fallback (station §8.8) — and channel 24 then carries silence. Only 24, 33 and 34 are accepted; a circuit or tap channel is refused at startup.

The filter coefficients are computed at startup from the passband edge, stopband edge and attenuation, which are options, so that a different passband edge (§1.1) is a command-line change and not a code change. The coefficients are computed with a standard elliptic design; a unit test compares the realised stopband at 6000Hz against the requirement, because the lowest pilot sits exactly there and 70dB is what keeps it out of the loudspeaker.

Limiter: peak, threshold −3dBFS, instant attack, 100ms release. It is there so that setting the monitor level by ear with the operator on the headset cannot produce a clipped burst from a ring-trip transient or a shouted line, and its release is fast enough that it is not audible as pumping on speech.

## 10.2 Command

`sbgame/audio/monitor/set` with `"off"` or a gain in dB as a signed decimal string — `"0"`, `"-12"`, `"6"`. 0dB is unity from the source's capture to A32 output 24, with `--monitor-tap-trim` added while the source is the tap (§10.3). The analog level that corresponds to is set by that channel's A32 reference and trim (station §7.9.8), which is where the amplifier's input sensitivity is matched; this gain is the running level, the A32 setting is the installation's. Accepted range −60 to +20dB; a value outside it is clamped and the clamped value is what the state topic echoes. Gain changes are applied with a 20ms ramp so a level step does not click. `"off"` is a mute, ramped the same way; the filter keeps running so that turning the monitor on is instant and has no transient from a cold filter state. The state topic `sbgame/audio/monitor`, retained, echoes `"off"` or the gain.

The monitor is on at startup only if the `--monitor` option gives a level; the default is off, because the loudspeaker is in the operator's room and a program restart should not surprise anyone.

## 10.3 Source

`sbgame/audio/monitor/source/set` with `"tap"` or a circuit id — `"station/5"`, `"trunk/2"` (mqtt.md §3). Accepted: `tap`, `station/1` to `station/22`, `trunk/1` to `trunk/8`, provided the channel it names is one the device captures. Anything else is logged and dropped, and the state topic does not change. `--monitor-src` is checked the same way at startup, and a value that fails refuses to start (Rev 9). The state topic `sbgame/audio/monitor/source`, retained, echoes the source in use. The source at startup is `--monitor-src`, `tap` by default (Rev 8).

The source names a capture channel: the tap is 23, station n is n, trunk n is 24 + n (§2). That channel's capture is the input to the chain of §10.1; nothing after the input changes. Only the monitor reads it this way. Whatever else reads that channel — the detector, a listen, the tap's own-tone check — is unaffected.

What a circuit channel carries. Its own transmit returns on it at full strength, because the interface has no hybrid (station §8.4). The far end arrives through the switchboard's cord. The operator's voice is there while she is bridged to the line. Its own pilot, its peer's pilot and, while she is bridged, the operator tone are there too, and the §8.8 filter removes all three as it removes the tone and the pilots from the tap channel. The game sets a circuit source when the operator answers that line (game_control.md §6.4), which also keeps the monitor off a trunk while its ring relay is moving: trunk §8.1.1 puts a click on that trunk's channel at each relay operate and release.

Switching, in the audio thread. A new source ramps the monitor gain down to silence over 20ms, the same ramp §10.2 uses. At the bottom of the ramp the input changes to the new channel, and the gain ramps back up over 20ms to the commanded gain, with `--monitor-tap-trim` applied or removed as the new source requires. The filter state is carried across the switch rather than cleared: the step from one input to the other happens at zero gain and has rung out by the time the ramp-up is audible. The echo is posted at the bottom of the ramp, when the input changes. A second `source/set` during a ramp takes over from wherever the ramp is. A `source/set` naming the source already in use is echoed and does nothing else. While the monitor is `"off"` the input changes at once, with no ramp, and is echoed.

The tap trim. `--monitor-tap-trim`, in dB, is added to the gain only while the source is the tap. The tap arrives about 15dB below the operator's line (station §7.9.3); a circuit channel sees its line through T2 alone. The trim is set once on the bench so that the operator's voice sounds the same on either source at one monitor gain (§15 step 7), and `monitor/set` then stays one number. It is not echoed on `monitor`, which carries the commanded gain. Its range is −30 to +30dB; outside that the program refuses to start. The sum of the commanded gain and the trim is not clamped to `monitor/set`'s range. The limiter protects the output (Rev 9, §1.9).

The game program chooses the source. This program does not know about calls, and falls back to the tap only when it loses the game or the broker (§13.2).

## 10.4 A File on the Monitor

Rev 11. `sbgame/audio/monitor/play/set` plays a file on the loudspeaker: loaded, checked, reported and stopped exactly as a circuit's (§7), echoed on `sbgame/audio/monitor/play`. The game program uses it for the tutor's voice (game_control.md §4.9).

The file is not a source in §10.3's sense and does not displace one. Per sample, the file passes through its own copy of the §10.1 low-pass — the same coefficients, its own state — and is added to the source after the source's filter, then the sum takes the gain and the limiter:

```text
source capture -> high-pass -> low-pass -----------+
                                                    +-> x gain -> limiter -> channel 24
file -> low-pass (own state) -> x file trim -------+
```

The low-pass is there for the reason the source has it: the loudspeaker is in the room with the operator's microphone, and anything above 5.5kHz it puts into the room can return on the line she is bridged to and reach the detector (§5.3). Authored speech has nothing there, but the filter is free and makes it so for any file. The file has no high-pass: it carries no ring-trip click or hum. Its filter runs whether or not a file plays, so a file never starts against a cold state.

Gain. The monitor's commanded gain applies to the file as to the source, ramps and mute included, so `monitor/set` remains one number for the room and the file is silent while the monitor is `"off"` — it still plays to its end and clears its topic, so the game is not left waiting. `--monitor-file-trim`, −30 to +30dB, 0 by default, is added for the file only, so that its level is set once on the bench against the calls' (game_control.md §9 step 12). `--monitor-tap-trim` is not applied to the file: while the source is the tap, the file's share is scaled by the tap trim's inverse so that the file's level does not change with the source. A source switch's ramp passes through zero for 20ms and takes the file with it, which is inaudible in speech.

The file and the source are summed in float before the limiter, which protects the output as it does for the source alone. A file on the monitor is stopped with the game's other files when the program loses the game or the broker (§13.2).

# 11. Diagnostics

## 11.1 Test Tone

`sbgame/audio/test/<1-34>/set`, `"on"` or `"off"`, any playback channel. A 1kHz sine at −20dBFS (an option) replaces everything on that channel — the program source, and also the pilot, the operator tone or the monitor — for as long as it is on. It replaces rather than sums so that a scope or a meter at the far end sees one clean tone at a known level, which is the point of a wiring and level check. The consequence is that the circuit reports `deaf` while its pilot is displaced (station §8.7), the operator tone is off the line while channel 23 is under test, and the loudspeaker carries the test tone while 24 is (or 33 or 34, when `--monitor-ch` names them). All of that is correct and none of it is a fault. The state topic `sbgame/audio/test/<ch>`, retained, echoes `"on"` or `"off"`. More than one channel may be under test at once. On `"off"` the displaced source resumes from the next period.

1kHz is bin 85.33, so it does not land on a bin and is not a pilot; it is chosen because every meter and every scope trigger on it, not for any property in the detector.

## 11.2 Log

To stderr, one line per event, with uptime, and picked up by the journal when run under systemd. Events: start with the ALSA parameters actually negotiated, every MQTT command received and what was done with it, every `peer` and `op` change, every `ambiguous` with the list of pilots and levels, `deaf` and `optone` changes, monitor source changes, file load results and warnings, xruns and clip counts, output-check excesses (§11.4), MQTT connect and disconnect, game-heartbeat loss (§13.2).

## 11.3 Spectrum Dump

`--dump <circuit> <seconds>` writes that circuit's per-hop magnitude spectrum in dB above its guard-bin floor for every comb bin and bin 768, as CSV, for the stated duration, then continues normally. This is the commissioning tool for setting `MARGIN_DB` (station §8.7) and for the clock check in §15, and it is a command-line option rather than an MQTT command because it is used with a terminal open and nothing else running.

## 11.4 Output Self-Check

Every period, after `render()` and before the write, the program scans the playback buffer it is about to hand to ALSA and compares each channel's peak with the most that channel should carry this period: the pilot level on a circuit with no program source, the operator tone's on the tap with no file, the test tone's under test, the limiter's −3dBFS on a monitor channel, and nothing on a silent one. A channel with a file or a trunk tone is not checked — its source can reach full scale by design. A peak more than 0.5dB over its ceiling counts that period as an excess on that channel. The audio thread keeps the count and the highest peak per channel and hands them to Shared once a second; the MQTT thread logs them every ten seconds with the counters, one line naming each channel, its count of periods and its peak in dBFS. Silence in the log means every channel carried what it should. The scan is one pass over the buffer already in cache, with no allocation and no lock, and costs a few microseconds a period.

It sees only the program's own buffer. Samples corrupted after the write — in ALSA, the USB stream or the Digiface — do not appear in it, and that is the point: a meter at the A32 that misbehaves while this check is silent puts the fault downstream of the program.

# 12. MQTT Interface

The topics, payloads and retention are mqtt.md §5 and §6, which are the authority. This section is the program's side of them.

Subscriptions, all QoS 1:

```text
sbgame/station/+/play/set      sbgame/trunk/+/play/set
sbgame/audio/tap/play/set      sbgame/audio/monitor/play/set
sbgame/trunk/+/tone/set
sbgame/station/+/listen/set    sbgame/trunk/+/listen/set
sbgame/audio/monitor/set
sbgame/audio/monitor/source/set
sbgame/audio/test/+/set
sbgame/ctl/game_heartbeat
```

Station n is validated 1–22 and trunk n 1–8; a topic outside those ranges, or a `tone/set` on a station, is logged and dropped. The same ranges apply to the circuit id in a `monitor/source/set` payload (§10.3). Nothing is acted on that the program cannot echo.

Every command is acknowledged by its state topic changing, retained, from the audio thread after it has taken effect — the same convention as the ESP32's `hook` echoing `hook/set` (mqtt.md §3). A command that arrives while the program is running and produces no change in the state topic was not acted on, and the log says why.

Published state at start, before the birth message, so that a subscriber that sees `audio_status` go `online` already has consistent values: `play`, `tone` and `listen` empty for every circuit, `monitor` and `monitor/source` as started, `test/<ch>` off for every channel, then `peer`, `op` and `optone` from the analysis thread's first pass — the MQTT thread raises a flag asking for a full publish and waits for the analysis thread to report that pass done. Only then `sbgame/ctl/audio_status` = `"online"`. The same sequence runs on every reconnect. The values republished are what the program is doing at that moment, not the last values that reached the broker, so a change made while disconnected is what reconnect announces (Rev 9). (Rev 2's program published `online` first and let the detector topics follow up to a hop later — Rev 3 code consequence 3.)

# 13. Startup, Shutdown and Failure

## 13.1 Sequence

Parse options → open and configure both ALSA handles, link, allocate every buffer, lock memory → compute filter coefficients and FFT plan → start the audio thread and the stream, pilots and operator tone on from the first period → start the analysis thread → connect to the broker with the LWT, subscribe, publish the initial state (§12), publish the birth message. Audio starts before MQTT deliberately: the pilots and the operator tone are part of the switchboard's electrical environment and nothing about them depends on the broker.

SIGTERM or SIGINT: stop every program source and the test tones, clear their state topics, publish `audio_status` = `"offline"` cleanly so the broker does not fire the will, disconnect, stop the stream, exit. The pilots stop with the stream, and every `peer` on the broker goes stale at that moment — which is why `audio_status` exists (mqtt.md §8.1).

## 13.2 Losing the Game or the Broker

The program mirrors the ESP32's rule (mqtt.md §8.2) for the same reason. A game program that has crashed can leave a trunk sending ringback to the operator indefinitely, which presents as a hardware fault. So:

- **Two consecutive missed `game_heartbeat`s** (no beat for 2s): stop every trunk tone and every file, clear their state topics, log it. Pilots, the operator tone and the monitor continue — they are not things the game started and are harmless without it. The monitor's source returns to the tap, under the §10.3 ramp, and `monitor/source` echoes `"tap"`: the calls a circuit source was following have been torn down, and the tap is the one source that is not about a call (Rev 8). Listens in progress are cancelled and cleared; their results would go nowhere. Test tones continue: they are a bench diagnostic, not game state, and stopping them under someone's meter is unhelpful.
- **Broker connection lost**: the same stops, applied locally, and reconnect with backoff — 1s, doubling to a 30s ceiling, reset on success; a refused connection (bad credentials, mqtt.md §9) backs off the same way rather than retrying at speed. The will is registered once on the client handle and survives every reconnect. On reconnect: republish all state as at start, then `online`. The will has already published `offline` on the program's behalf. Results the audio and analysis threads post while disconnected are discarded, not queued: the sources they describe were stopped at the disconnect, and the detector republishes in full on reconnect. State is not a result. The state republished on reconnect is read from the program as it stands, so the monitor's return to the tap, made locally while disconnected, is what reconnect announces on `monitor/source` (Rev 9).
- **The stream fails** and cannot be recovered: exit non-zero. Under systemd, `Restart=on-failure` brings it back and the birth/LWT sequence tells the game what happened. There is no attempt to run without audio.

## 13.3 What Is Not Failsafed

The program has no heartbeat of its own (mqtt.md §8.2 records why). With three threads that reasoning is weaker than it was: the MQTT thread can keep `audio_status` online while the audio thread is wedged, and then a `listen` never resolves and a `play` never clears. The game program should apply its own deadline to anything it waits on from the audio program — the listen timeout plus a second, the file's known length plus a second — and treat a missed deadline as audio-program-down. mqtt.md §11 carries the heartbeat as an open item.

# 14. Configuration and Build

C++17. Libraries: libasound (ALSA), libmosquitto, FFTW3 (single precision), libsndfile. Built with CMake; one binary, `sbaudio`. Runs as a user in the `audio` group with rtprio and memlock limits set in `limits.conf` or via rtkit, so that SCHED_FIFO at priority 70 and `mlockall` succeed — the program logs and continues if they do not, at the cost of xruns. `--no-realtime` skips both for a bench run under a debugger.

Command-line options, each with the default given here, and no configuration file — there are few enough that a systemd unit's `ExecStart` line holds them, and one place is better than two:

```text
--card ID              ALSA card id from /proc/asound/cards (required, no default)
--period N             frames per period (256)
--periods N            periods per buffer (3)
--no-realtime          no SCHED_FIFO, no mlockall
--broker HOST[:PORT]   MQTT broker (localhost:1883)
--mqtt-user USER       broker credentials (mqtt.md 9); --mqtt-pass PASS,
--mqtt-pass-file PATH    or the password from a file
--client-id ID         MQTT client id (sbgame-audio)
--window rect|hann     detector window (rect); hann is station 8.2's fallback,
                       three-bin sum, guards at +-4/+-5
--wav-dir PATH         wav directory (wav)
--max-file SECONDS     longest file accepted (120)
--pilot-db DB          pilot level (-40)
--op-db DB             operator tone level (-18)
--tone-db DB           trunk tone peak level (-20)
--tone-mod M           trunk tone modulation depth, 0-1 (1.0)
--test-db DB           test tone level (-20)
--margin-db DB         detector MARGIN_DB (20)
--peer-window-db DB    detector PEER_WINDOW_DB: a pilot further than this
                       below the circuit's own is not heard (40)
--op-window-db DB      detector OP_WINDOW_DB: the operator tone further than
                       this below the circuit's own pilot is not heard (20)
--monitor DB           start with the monitor on at this gain (off)
--monitor-ch LIST      playback channels for the monitor, comma-separated,
                       from 24, 33, 34 (24); 33,34 is the Digiface fallback
--monitor-src SRC      monitor source at startup: tap, station/<n> or
                       trunk/<n> (tap); refused if the device does not
                       capture that channel
--monitor-tap-trim DB  gain added while the monitor source is the tap,
                       -30 to +30 (0)
--monitor-file-trim DB gain added to a file on the monitor, -30 to +30 (0)
                       (§10.4)
--monitor-lp HZ HZ DB  monitor low-pass passband edge, stopband edge,
                       stopband dB (3600 5600 70)
--vad-margin DB        speech threshold above floor (10)
--vad-floor DB         speech absolute threshold (-50)
--vad-hangover S       silence that ends speech (1.5)
--vad-max-speech S     longest speech waited out before timeout (30)
--dump CIRCUIT SECONDS spectrum dump (§11.3)
```

Every level that station §8 gives as a figure is an option here and defaults to that figure, so the document and the program agree until the bench says otherwise, and what the bench says goes into the unit file, not into the source. FFTW's plan is cached as wisdom at `$SBAUDIO_WISDOM`, or `~/.cache/sbaudio-wisdom`, so the first start after a build is the only slow one.

# 15. Commissioning

In order, with the switchboard connected:

1. Start with no game program and `mosquitto_sub -v -t 'sbgame/#'` open. Every circuit should show `peer` empty and `op` off within a second, `optone` ok, and `audio_status` online. A `deaf` here is a wiring fault on that circuit's own strip or D-Sub channel, and is the first thing to find.
2. Clock check. `--dump` one station for ten seconds with nothing patched. Its own pilot should sit in its own bin at a steady level with the two neighbouring bins 40dB or more below it. Energy in the neighbouring bins that varies slowly is two clock domains — the Digiface and the A32 are not locked — and must be fixed at the hardware before anything else is measured, or the Hann fallback of station §8.2 adopted.
3. Test tone on each channel in turn, meter at the board's D-Sub, then at the switchboard jack. This is the wiring check for all 32 A32 channels and the two Digiface outputs, and the level reference for everything after. For channel 24 the meter goes at the amplifier end of the monitor cable (station §7.9.8).
4. Set the trunk tone level by measuring at the switchboard's trunk jack with dial tone on.
5. Set the operator tone level per station §7.9.5, and confirm the operator cannot hear it.
6. Set `MARGIN_DB`, `PEER_WINDOW_DB` and `OP_WINDOW_DB` per station §8.7, against a real cord-pair connection, and confirm no `ambiguous` with every cord patched. For the window, `--dump` both ends of the weakest connections — station to station and station to trunk, each with the operator bridged on and off — and read the peer's level, and bin 768's with the operator bridged on, against the own pilot's: each window must take the weakest with room to spare, and stay short of the trunk board's crosstalk, 72dB or more under the own pilot (station §1.25).
7. Set A32 channel 24's reference and trim for the amplifier's input sensitivity with the test tone on it, then set the monitor gain by ear with the operator on the headset and the limiter's activity in the log — it should be silent on ordinary speech. Then set `--monitor-tap-trim`: on a real call with the operator bridged to the calling line, switch `monitor/source/set` between `tap` and that circuit and trim until her voice is the same level on both. On the same call, once it is connected and talking, listen to the balance between the caller and the called party on the circuit source (§16).
8. Set the speech detector's margin and floor with the operator speaking through a real connection, and confirm it does not trigger on a ring-trip or a relay.

# 16. Open Items

- **Monitor level.** The monitor is on A32 output 24 as of Rev 7 (station §7.9.8); channel 24's A32 reference and trim against the amplifier's input sensitivity are bench settings (§15 step 7). This replaces the Rev 1 to Rev 6 item asking which Digiface jack the amplifier was on.
- **Capture channel count.** Expected 32 at 48kHz; confirm from the driver as the playback count was at station Rev 3.37.
- **Tone modulation depth and level.** §8.2 and §8.3; bench settings, by ear.
- **Detector `MARGIN_DB`, `PEER_WINDOW_DB` and `OP_WINDOW_DB`, tone, operator tone and monitor levels**: all bench settings, §15, none yet made.
- **Period size.** 256 is the target for the monitor loop; whether the class-compliant driver sustains it is a bench question.
- **Audio program heartbeat.** §13.3; open in mqtt.md §11.
- **Listening on the tap channel.** Not offered — the rough specification says station or trunk — but the tap always carries the operator's voice, and "has the operator said anything" may turn out to be a question the game wants to ask. One more accepted topic if so.
- **The two sides of a call on a circuit source** (Rev 8). A circuit's own transmit returns on its own receive through its own transformer's secondary. The far end crosses two transformers and the cord circuit. The caller will be louder than the called party by an amount nothing measured so far predicts. Measure it at §15 step 7. If the difference is large enough to matter, the fix is a fixed cut applied to the monitor while the source channel has an active program source, which this program already knows for §9.3's exclusion: one more option, `--monitor-own-duck DB`, default 0. It would also cut the far end during any overlap, which scripted content rarely has. Not added until the bench asks for it.
- **Reorder tone.** Not asked for and not added. If a scenario ever needs "the number you have dialled is not in service" as a tone rather than a recording, the period version is the busy waveform at 120 IPM — 0.25s on, 0.25s off — and is one more row here.
