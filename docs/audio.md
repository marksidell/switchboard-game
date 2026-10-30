**551 Switchboard Simulator**

**Audio Program Specification**

*Rev 33. The changes in each revision are in §17.*

# 1. Overview

The audio program is one of the two host programs (mqtt.md §1). It is C++, it runs on the Linux host, and it owns every audio channel in the system: the 32 balanced channels of the Ferrofish A32 in both directions, reached through the RME Digiface USB over ADAT, and the Digiface's own analog output pair, which feeds the audience loudspeaker (Rev 24). It does six things:

1. Plays the pilot comb on every circuit channel and the operator tone on the tap channel, continuously, and runs the FFT pilot detector of station §8.7 on every circuit input to find which circuits the switchboard has patched together and which the operator is bridged to. This is the job the program has had since station Rev 3.1; everything below is new at this revision.
2. Plays a 48kHz `.wav` file on a station or trunk channel on command, and reports when it has finished.
3. Plays dial tone, ringback or busy tone on a trunk channel on command, in the standard cadence, until told to stop.
4. Listens for speech on a circuit channel on command and reports when speech starts, when it ends, or that it did neither in time.
5. Pipes one receive channel to the loudspeaker through the low-pass filter of station §8.8 — the operator tap's by default, or a station's or trunk's on command (§10.3) — with a commanded on/off and level.
6. Plays a 1kHz test tone on any output channel on command, as a wiring and level diagnostic.

Everything is commanded and reported over MQTT. The topics are specified in mqtt.md §5 and §6; this document says what the program does with a command, when it publishes, and how the audio is generated, mixed and analysed. Station §8 owns the pilot comb, the detector algorithm and the monitor filter specification, and this document points to those sections rather than restating them. The game program (Python) is the only client that commands; the audio program never commands anything.

Ownership. This document is the specification. The source is written to it by Claude Code, in the same way `control/control.ino` is written to `control.md`, and chat sessions do not produce or revise the source. When a revision here has a code consequence, the revision says so.

Build state as of Rev 9. The program exists — `sbaudio`, written by Claude Code against Rev 2 and reviewed in chat on 2026-09-18. §17.3 records the decisions the implementation made where the specification was silent, now adopted, and the three corrections the review sent back, which Claude Code fixed the same day. Claude Code reported on 2026-09-24 that `sbaudio` is at Rev 8, which takes in the code consequences of Rev 6, Rev 7 and Rev 8 (§17.6 to §17.8). Rev 9 settles three questions that report raised (§17.9); two of them carry small code consequences. Nothing has yet run against the A32 and the switchboard; §15 is still to be done.

Numbering. Circuits, A32 channels and Digiface channels are 1-based throughout the project documents: station n is A32 channel n, trunk n is channel 24 + n, the tap is channel 23, station 24 is A32 channel 24 (Rev 24), and the monitor is on the Digiface's channels 33 and 34. ALSA frame indices are 0-based, so the program's internal index for a channel is the document number less one — the tap is index 22. Rev 1 to Rev 6 had the tap on channel 24 and the monitor on Digiface playback 33 and 34; the rough specification Rev 1 was written from gave those as 23 and 33, which were ALSA indices. §2 records the mapping.

# 2. Channel Plan

One ALSA card, the Digiface USB, opened in both directions at 48kHz, S32_LE. Playback is 34 channels — confirmed on the host at station Rev 3.37 — and capture is expected to be 32 (the four ADAT ports; the Digiface has no analog input) and is to be confirmed the same way (§16).

| **Document channel** | **ALSA index** | **Playback carries** | **Capture carries** |
| --- | --- | --- | --- |
| 1–22 | 0–21 | Station 1–22: pilot at comb slot n + program source | Station receive: detector input; speech detection on command; monitor source on command (§10.3) |
| 23 | 22 | Operator tap: 9000Hz operator tone, and a file on command (Rev 10, §7) | Tap receive: the default monitor source (§10.3) and the tap's own-tone health check (§6.3) |
| 24 | 23 | Station 24, the real telephone (Rev 24): pilot at comb slot 24 + program source | Station 24 receive, as stations 1–22 |
| 25–32 | 24–31 | Trunk 1–8: pilot at comb slot 24 + n + program source | Trunk receive: detector input; speech detection on command; monitor source on command (§10.3) |
| 33, 34 | 32, 33 | The audience monitor (§10), with a file summed in on command (§10.4) | — |

The program source on a circuit channel is one of: nothing, a file (§7), a trunk tone (§8, trunks only) or the test tone (§11.1). Exactly one is active on a channel at a time; a new one replaces the current one (§5.2). The pilot is always present on channels 1–22 and 24–32 and is not a program source; the operator tone is always present on channel 23 and is not one either. The test tone is the one source that may be placed on channels 23, 33 and 34 as well, where it replaces the operator tone or the monitor for as long as it runs.

Slot 23 of the comb (bin 688) is not generated while station board 3's strip 7 is the tap, per station §7.9.6. Slot 24 (bin 696) was not generated from Rev 7 to Rev 23, while strip 8 fed the loudspeaker; it is station 24's pilot from Rev 24. The mapping from circuit to comb bin, `512 + 8 × (slot − 1)`, is station §8.2 and is not restated here.

# 3. Program Structure

Three threads and two lock-free queues. Nothing else runs concurrently.

**Audio thread.** Owns the ALSA stream. Runs one period at a time: read a capture period, run the per-sample work on it (§9 detector front-end accumulation, §9 speech-detection frames, §10 monitor chain), render one playback period (§5), write it. SCHED_FIFO, memory locked, no allocation, no file I/O, no locks, no MQTT — it communicates only through the two queues. Everything it plays is either generated arithmetically or read from a buffer that was filled before the command reached it.

**Analysis thread.** Receives 4096-sample blocks per capture channel from the audio thread at the 2048-sample hop (§6), runs the FFT and the detector, and hands results to the MQTT thread. It also runs the detector's logging (§11.2). Normal priority. It is separate from the audio thread so that thirty-two 4096-point FFTs every 43ms — a fraction of a millisecond of work, but bursty — never sit inside a period deadline. It waits by polling the snapshot mailbox with a 2ms sleep (§6.1) — chosen over a condition variable so that the audio thread has nothing to signal but an atomic store. Two milliseconds on a 43ms hop is nothing, and 500 empty wake-ups a second are nothing on this host.

**MQTT thread.** Runs the libmosquitto network loop as a polled loop: `mosquitto_loop()` with a 20ms timeout, then drain both result queues and publish, then check the game heartbeat, then repeat. It sleeps in `select()` on the broker socket for up to 20ms or until traffic arrives, so a command is handled as it lands and a result posted by the other two threads waits at most 20ms — inside the detector hop and invisible to the game. When there is no connection `mosquitto_loop()` returns at once, and the loop must sleep the 20ms itself or it spins (Rev 3 code consequence 1). Translates each incoming command into a queue entry for the audio thread; for a file command it loads and validates the file first (§7.2), in the message callback, and passes the audio thread a pointer to a buffer it may not free until the audio thread has released it. Publishes the birth message, holds the LWT, and watches `game_heartbeat` (§13.2). It is the main thread: it becomes the MQTT thread once the other two are started.

**The loudspeaker recording and its playback** (Rev 22, §10.6, §10.7) add two more hand-overs, each a ring of samples with one writer and one reader: audio thread → MQTT thread, written while `Shared::rec_on` is set and emptied into the file; and MQTT thread → audio thread, filled from a recording and played while `Shared::play_on` is set. Neither side waits for the other; a full recording ring drops the period, and an empty playback ring plays silence.

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

**Pilot** (channels 1–22, 24–32). Level −40dBFS per station §8.4, an option. Generated from one shared 4096-entry sine table: for comb bin b, sample n of the 4096-sample cycle is `table[(b × n) mod 4096]`. Because every pilot completes an integer number of cycles per 4096 samples, a per-channel sample counter that wraps at 4096 is the whole oscillator — no phase accumulator, no rounding, no drift, and the pilot is on its bin by construction. The counter is shared across channels; only b differs.

**Operator tone** (channel 23). Bin 768, the same table at `table[(768 × n) mod 4096]`, which is 16 samples per cycle. Level per station §7.9.3: with that channel's A32 reference at +20dBu, about −18dBFS puts 12mV on the operator's line. An option, set from the bench measurement §7.9.5 asks for.

**Program source** (channels 1–22, 24–32): a file, a trunk tone, or the test tone. Unity gain for a file; the tone levels are §8.3 and §11.1.

**Monitor** (channels 33 and 34, or those of them `--monitor-ch` names): §10.

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

`sbgame/trunk/<n>/tone/set` with `"dial"`, `"ringback"`, `"busy"`, `"reorder"` (Rev 20) or `"off"`. Trunks only: dial tone, ringback, busy and reorder are what a central office sends toward the switchboard, and a station is the telephone, which sends none of them. A tone runs until `"off"`, until another `tone/set` replaces it, until a `play/set` replaces it (§5.2), or until the program loses the game (§13.2). The state topic `tone`, retained, echoes `"dial"`, `"ringback"`, `"busy"`, `"reorder"` or empty.

## 8.2 Tones

| **Tone** | **Waveform** | **Cadence** |
| --- | --- | --- |
| Dial | 600Hz, amplitude-modulated by 120Hz | Continuous |
| Ringback | the city ring of `cityring.h` (Rev 21): 48 harmonics of 20Hz, strongest at 440, 400 and 360Hz, measured from an 803C recording; nominally 420Hz mixed with 20Hz ringing current, beating at 40Hz | 2.0s on, 4.0s off |
| Busy | 600Hz, amplitude-modulated by 120Hz | 0.5s on, 0.5s off |
| Reorder (Rev 20) | 600Hz, amplitude-modulated by 120Hz | 0.25s on, 0.25s off |

These are the Bell System tones of the period the 551 belongs to, before the precise tone plan of the 1960s replaced them with two-frequency sums — dial tone 350 + 440Hz, ringback 440 + 480Hz, busy 480 + 620Hz, same cadences. The precise tones are the alternative, one table away, and are not used: they are what a modern ear expects, and on a board of this age they would be the one anachronism the operator hears on every call. The cadence starts at the beginning of the on period when the tone is commanded, so the operator always hears a burst first.

Busy is the dial-tone waveform interrupted at 60 IPM, which is how the period offices made it — one tone source, one interrupter — and a listener tells the two apart by the cadence alone. That is faithful and it is also the reason to keep the busy cadence exact: a dial tone with a dropout could be mistaken for it. A scenario switches a trunk from ringback to busy, or from dial to busy after the operator dials a busy number, with one `tone/set`; the change takes effect at the next period and the new cadence starts from its on phase.

**Ringback** (Rev 21) is one 2400-sample period of the city ring, built at startup from the partials in `audio/src/cityring.h` — each a harmonic of 20Hz with its amplitude and phase, measured from a recording of the Atlanta 755 office's 803C machine (§17.21) — set to a peak of 1 and played a sample at a time, so it costs less than the two sines it replaced. Every component is below 1.4kHz, clear of the comb. At the same peak as the other tones its RMS is 2.7dB higher.

Each other tone is a carrier sine multiplied by `(1 + m × sin(2π f_mod t))`, so the spectrum is the carrier plus one sideband either side at ± f_mod — 480, 600 and 720Hz for dial, busy and reorder (Rev 21: ringback was 380, 420 and 460Hz) — all inside the switchboard's passband and all well clear of the comb. Modulation depth m is an option, 1.0 by default; the period tones were made by beating two sources through a nonlinear element and the exact depth varied by office, so set it by ear against a recording if one is to hand. The generator is two phase-accumulator sines per tone, not the 4096-table, because these frequencies are not an integer number of cycles per 4096 samples and do not need to be — they are program audio, not pilots. Their harmonics are not a concern for the detector: a digitally generated sine has none, and the transformer's distortion at −20dBFS is far below the −60dBFS content rule.

## 8.3 Level

−20dBFS peak by default, an option, the same for every tone. The period tones had no single specified level; what matters is that dial tone is unmistakable at the headset and ringback and busy are not louder than speech. Set on the bench by measuring at the switchboard's trunk jack and listening at the headset.

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

The final value — `"silence"` or `"timeout"` — persists until the next `listen/set` on that channel; a cancel clears it to empty. The game watches the transitions: out of `"listening"` for the start of speech, out of `"speech"` for the end. A game that finds `"timeout"` and needs to know which kind reads the value it replaced; one that was restarted mid-listen has lost the listen either way and reissues it. The payload's seconds bound only the wait for speech to start. The silence hangover and the maximum speech time are options, not payload (§14, §17.6).

## 9.2 Detector

Energy-based, in the voice band, on 10ms frames, in the audio thread:

- The channel's capture is band-passed 300–3400Hz — one second-order high-pass and a sixth-order Butterworth low-pass, three biquads (Rev 18) — before anything is measured. The pilots at 6–9kHz are the loudest thing on the channel and must not count; hum must not either. The low-pass puts the lowest pilot 30dB down and the operator tone 50dB down, so that neither sets the noise floor; with one section, as Rev 1 to Rev 17 had it, the lowest pilot was only 10.9dB down and the station's own pilot set a floor near −71dBFS.
- RMS per 480-sample frame, in dBFS referenced to a full-scale sine (RMS × √2), which is the convention for every dBFS figure the program reports or accepts.
- The noise floor is the 10th percentile of the frame levels over the second before the command arrived, which the audio thread keeps as a rolling history per channel at all times so it is available the instant a listen starts. During the listen the floor may rise at no more than 1dB/s and never fall, so a slowly rising room does not trigger and a burst does not lower the bar. A step to a new steady level is the exception (Rev 32): when the last 50 frames all lie within 3dB of each other and the highest of them is more than 3dB above the floor, that highest is the floor at once and the window starts again. Only at or below −55dBFS: a held vowel is steady too, but a line's noise is 40dB under a voice. A trunk seized as a listen starts steps up 38dB to its line noise.
- Threshold is the greater of floor + 10dB and an absolute −50dBFS by default, `--vad-floor`. The absolute term is what stops a very quiet channel from triggering on nothing. The installation sets −70 (Rev 18): through the 551 an operator's normal voice reaches a station's line at −55 to −65dBFS in this band, peaks near −47, and never cleared −50 for 200ms of 300.
- Speech is declared when at least 20 of the last 30 frames — 200ms of 300ms — are above threshold, and those 30 are not all within 3dB of each other at or below −55dBFS (Rev 32): a steady level that quiet is noise waiting to become the floor. A single click or a relay operating is a frame or two; a word is many, and varies.
- Speech is declared ended when no more than 2 of the last 30 frames are above threshold and that has held for the hangover time — 1.5s by default; the installation sets 0.5s (Rev 23). The pauses inside a sentence are shorter than that; the pause after one is longer. A cough or a chair after the caller has stopped is a frame or two above threshold inside the window and does not restart the count; a second sentence does.
- The maximum speech time — 30s by default — runs from the frame that declared speech. If speech has not ended by then the listen reports `"timeout"` and stops. It is a bound on a caller who keeps talking, or on a line that has gone noisy enough to read as speech forever, so that the game is never left waiting on a listen that cannot resolve.

The thresholds, the window, the hangover and the maximum speech time are options. Set them on the bench with the operator speaking a short phrase at normal level through a real cord-pair connection, and with the room's ordinary noise present.

## 9.3 What Is Excluded

Frames during which the same channel has an active program source are discarded, and the 30-frame window restarts when the source ends — unless the echo canceller has cleaned them (§9.4, Rev 26). The reason is station §8.4's: the two-wire interface has no hybrid, so everything this channel transmits returns on its own receive at full strength, and the program would detect its own file. The echo that persists after the source stops — through the switchboard's cord circuit and the far-end transformer — is milliseconds and is covered by the window restart.

What is not excluded is the far end. If the game plays a file on station 5 while listening on trunk 2 and the two are patched together, trunk 2 hears the file and reports speech. The program cannot know that is not wanted, and the game, which issued both commands, can. Do not listen on a channel whose peer is playing, or expect the result you asked for.

## 9.4 The Echo Canceller

Rev 26. While a circuit plays a file, a line echo canceller learns the file's echo on that circuit's receive and subtracts it, so that the detector can judge what is left: a caller talking over the file. A listen started with the file, or before it, then hears such a caller; one started after it is not affected.

**Where.** In the voice band at 8kHz. The file, as summed into the circuit's output, and the capture each go through the detector's band-pass of §9.2, and every sixth sample is kept. A running sample count common to the render and the capture lines the two up, whatever the period. The canceller starts with the file and runs until 50ms after its last sample, when its echo is over. A trunk tone is not a reference: the canceller does not run for one, and a tone's frames are discarded as before.

**How.** Two NLMS filters of 128 taps, covering 10–26ms of lag, `--aec-delay` 10ms plus 16ms: the bench round trip is 11.7ms at 256 × 3 frames, and the echo was over by 26ms. The *background* filter adapts on every sample, step 0.5. The *foreground* filter is what is subtracted, and is a copy of the background taken once a frame when the background's residual has been at least 3dB below the foreground's, and at least 10dB below the capture, for three frames running. A background that falls 6dB behind the foreground is put back from it. A caller's voice therefore spoils only the background, never the filter in use, and no double-talk detector is needed — one would have to tell a caller 15dB below the echo from the echo. This is the two-path scheme (Ochiai, 1977).

**Converged.** Once a copy has taken 20dB or more off the capture, until the foreground makes the line louder than the capture for half a second, which a caller cannot cause and a changed echo path does. A canceller that has not converged changes nothing: its frames are discarded as §9.3 says. Between two files on a circuit it keeps what it learnt; after 30s with no file it starts afresh, since the next file is likely another call.

**What the detector does with it.** A frame in which the canceller ran throughout and has converged counts. Its level is the residual's; it is judged against the usual threshold and also against the echo subtracted less 20dB, so that the echo left behind — 31–40dB under the echo on the bench, against 15–25dB for a caller — does not read as speech. It is not added to the floor's history (§9.2), which stays the quiet before the file. The window does not restart when the file ends, so a caller who started over the end of a file is heard at once.

**Cost.** Two filters' outputs and one adaptation, 128 taps, 8000 times a second, on each circuit while it plays: about 3 million multiply-adds a second each.

**Bench.** On the station 21 recording of 2026-10-24, 16 lines: the canceller took 27–34dB off each line Mark did not talk over, and no window there reached more than 13 frames of 30 above threshold; the lines he talked over showed 11–19dB, the residual being him, and those he talked over for longer than the window were heard. `aec_check FILE.lineN.wav` runs the canceller over a `--record-line` recording and prints each frame.

## 9.5 Ring Heard on a Station

Rev 30. The station board's ring detector is across the line ahead of the relay (station §7.2), and it does not see ring on a station that is off-hook: the board's own loop load pulls the ring down from about 80V to 17V AC, below its turn-on. Ring on an off-hook station is what the player sends when she rings the wrong cord of a call from that room (game_control.md §6.7). It reaches the station's capture channel through Tx01, at about −25dBFS of 20Hz; without it the 20Hz band is below −85dBFS (Rev 30 measurements).

So on every station's capture channel, 1–22 and 24, at all times: a 20Hz Goertzel over blocks of 4800 samples (100ms, exactly two cycles, so DC and 60Hz fall on the window's nulls), under a Hann window, which keeps a file returning at full strength on the same channel from leaking into the band. The block's 20Hz amplitude, in dBFS of a sine's peak, is compared with −50dBFS, and its 40Hz amplitude, from a second Goertzel, must be at least 20dB below the 20Hz (Rev 31): ring has almost no second harmonic, while a plug's click or a contact's bounce spreads across the low band. Three blocks in a row passing both (300ms) set `ringing` `"on"`; three in a row below it (300ms) set `"off"`. Published on `sbgame/station/<n>/ringing` on change only, retained.

It is heard whether the station is on- or off-hook, but on-hook the relay has lifted Tx01 from the line and nothing reaches the channel, so in practice it reports off-hook ringing only. The ESP32's `station/<n>/ring` remains the report of a ringing on-hook station. Trunks are not watched: ringing a trunk is reported by the controller (control.md §8.3).

# 10. Audience Monitor

## 10.1 Chain

The source's capture channel — 23, the tap, unless `monitor/source/set` has named a circuit (§10.3) → high-pass, second order, 150Hz → low-pass per station §8.8: elliptic, 8th order as four second-order sections, passband edge 3.6kHz, stopband edge 5.6kHz, stopband 70dB → gain, plus `--monitor-tap-trim` while the source is the tap → limiter → the channels `--monitor-ch` names, 33 and 34 by default, the same samples on each. All in the audio thread, per sample, with no buffering beyond the period, because the loop through the room is the constraint §8.8 records.

Channels 33 and 34 are the Digiface's own analog output, a 6.3mm TRS jack, 33 on the tip and 34 on the ring, full scale +9.5dBu, fixed (real_phone.md §4). The amplifier takes 33 through a TS-to-XLR cable. From Rev 7 to Rev 23 the monitor was on A32 output 24, which is station 24 from Rev 24. Only 33 and 34 are accepted; a circuit or tap channel is refused at startup.

The filter coefficients are computed at startup from the passband edge, stopband edge and attenuation, which are options, so that a different passband edge (§17.1) is a command-line change and not a code change. The coefficients are computed with a standard elliptic design; a unit test compares the realised stopband at 6000Hz against the requirement, because the lowest pilot sits exactly there and 70dB is what keeps it out of the loudspeaker.

Limiter: peak, threshold −3dBFS unless `--monitor-limit` sets it lower (Rev 16), instant attack, 100ms release. It is there so that setting the monitor level by ear with the operator on the headset cannot produce a clipped burst from a ring-trip transient or a shouted line, and its release is fast enough that it is not audible as pumping on speech.

## 10.2 Command

`sbgame/audio/monitor/set` with `"off"` or a gain in dB as a signed decimal string — `"0"`, `"-12"`, `"6"`. 0dB is unity from the source's capture to the monitor's output channels, with `--monitor-tap-trim` added while the source is the tap (§10.3). The analog level that corresponds to is the Digiface's fixed +9.5dBu full scale; the amplifier's input gain is where its sensitivity is matched. This gain is the running level. Accepted range −60 to +20dB; a value outside it is clamped and the clamped value is what the state topic echoes. Gain changes are applied with a 20ms ramp so a level step does not click. `"off"` is a mute, ramped the same way; the filter keeps running so that turning the monitor on is instant and has no transient from a cold filter state. The state topic `sbgame/audio/monitor`, retained, echoes `"off"` or the gain.

The monitor is on at startup only if the `--monitor` option gives a level; the default is off, because the loudspeaker is in the operator's room and a program restart should not surprise anyone.

## 10.3 Source

`sbgame/audio/monitor/source/set` with `"tap"` or a circuit id — `"station/5"`, `"trunk/2"` (mqtt.md §3). Accepted: `tap`, `station/1` to `station/22`, `trunk/1` to `trunk/8`, provided the channel it names is one the device captures. Anything else is logged and dropped, and the state topic does not change. `--monitor-src` is checked the same way at startup, and a value that fails refuses to start (Rev 9). The state topic `sbgame/audio/monitor/source`, retained, echoes the source in use. The source at startup is `--monitor-src`, `tap` by default (Rev 8).

The source names a capture channel: the tap is 23, station n is n, trunk n is 24 + n (§2). That channel's capture is the input to the chain of §10.1; nothing after the input changes. Only the monitor reads it this way. Whatever else reads that channel — the detector, a listen, the tap's own-tone check — is unaffected.

What a circuit channel carries. Its own transmit returns on it at full strength, because the interface has no hybrid (station §8.4). The far end arrives through the switchboard's cord. The operator's voice is there while she is bridged to the line. Its own pilot, its peer's pilot and, while she is bridged, the operator tone are there too, and the §8.8 filter removes all three as it removes the tone and the pilots from the tap channel. The game sets a circuit source when the operator answers that line (game_control.md §6.4), which also keeps the monitor off a trunk while its ring relay is moving: trunk §8.1.1 puts a click on that trunk's channel at each relay operate and release.

Switching, in the audio thread. A new source ramps the monitor gain down to silence over 20ms, the same ramp §10.2 uses. At the bottom of the ramp the input changes to the new channel, and the gain ramps back up over 20ms to the commanded gain, with `--monitor-tap-trim` applied or removed as the new source requires. The filter state is carried across the switch rather than cleared: the step from one input to the other happens at zero gain and has rung out by the time the ramp-up is audible. The echo is posted at the bottom of the ramp, when the input changes. A second `source/set` during a ramp takes over from wherever the ramp is. A `source/set` naming the source already in use is echoed and does nothing else. While the monitor is `"off"` the input changes at once, with no ramp, and is echoed.

The tap trim. `--monitor-tap-trim`, in dB, is added to the gain only while the source is the tap. The tap arrives about 15dB below the operator's line (station §7.9.3); a circuit channel sees its line through T2 alone. The trim is set once on the bench so that the operator's voice sounds the same on either source at one monitor gain (§15 step 7), and `monitor/set` then stays one number. It is not echoed on `monitor`, which carries the commanded gain. Its range is −30 to +30dB; outside that the program refuses to start. The sum of the commanded gain and the trim is not clamped to `monitor/set`'s range. The limiter protects the output (Rev 9, §17.9).

The game program chooses the source. This program does not know about calls, and falls back to the tap only when it loses the game or the broker (§13.2).

## 10.4 A File on the Monitor

Rev 11. `sbgame/audio/monitor/play/set` plays a file on the loudspeaker: loaded, checked, reported and stopped exactly as a circuit's (§7), echoed on `sbgame/audio/monitor/play`. The game program uses it for the tutor's voice (game_control.md §4.9).

The file is not a source in §10.3's sense and does not displace one. Per sample, the file passes through its own copy of the §10.1 low-pass — the same coefficients, its own state — and is added to the source after the source's filter, then the sum takes the gain and the limiter:

```text
source capture -> high-pass -> low-pass -----------+
                                                    +-> x gain -> limiter -> channels 33, 34
file -> low-pass (own state) -> x file trim -------+
```

The low-pass is there for the reason the source has it: the loudspeaker is in the room with the operator's microphone, and anything above 5.5kHz it puts into the room can return on the line she is bridged to and reach the detector (§5.3). Authored speech has nothing there, but the filter is free and makes it so for any file. The file has no high-pass: it carries no ring-trip click or hum. Its filter runs whether or not a file plays, so a file never starts against a cold state.

Gain. The monitor's commanded gain applies to the file as to the source, ramps and mute included, so `monitor/set` remains one number for the room and the file is silent while the monitor is `"off"` — it still plays to its end and clears its topic, so the game is not left waiting. `--monitor-file-trim`, −30 to +30dB, 0 by default, is added for the file only, so that its level is set once on the bench against the calls' (game_control.md §9 step 12). `--monitor-tap-trim` is not applied to the file: while the source is the tap, the file's share is scaled by the tap trim's inverse so that the file's level does not change with the source. A source switch's ramp passes through zero for 20ms and takes the file with it, which is inaudible in speech.

The file and the source are summed in float before the limiter, which protects the output as it does for the source alone. A file on the monitor is stopped with the game's other files when the program loses the game or the broker (§13.2).

## 10.5 The Line-Disturbance Gate

Rev 17. A switch moved on the line the monitor follows, or ringing on or near it, reaches the loudspeaker as a click or a rumble far louder than speech. Both carry most of their energy below 50Hz — a step in the line's DC current, ringing at 20Hz — where speech has next to none. So the gate watches the source's raw capture, before the chain's high-pass, through a 50Hz low-pass (a second-order Butterworth, run twice; 100Hz at Rev 17, §17.19), and while that signal's peak exceeds `--monitor-gate`, and for `--monitor-gate-hold` after (0.25s), it shuts the source: down in 1ms, back up over 20ms. The filtered source passes through a 10ms delay ahead of the gate, so the gate is shut before a click's onset reaches the output. The delay is there whether or not the gate is on, so the chain's latency does not depend on a setting, and 10ms is well inside what §10.1's acoustic loop tolerates.

Only the source is gated. A file on the monitor (§10.4) is summed in after the gate and plays on through it: the tutor is not cut off because a phone is ringing. The log's counters line reports how many times the gate shut in each ten seconds, `gate N`, so a threshold low enough to catch the operator's own voice shows up there.

Off unless `--monitor-gate` is given. The installation sets −60dBFS since Rev 27, after the gate at −70 cut speech on the loudspeaker in play. Rev 19 had set −70 from a recording of the switchboard, 2026-10-16: the gate at 50Hz and −70 brings the worst switch flip or ring at the output, at −12dB monitor gain, from −10.5dBFS to −44.5, below speech, as Rev 17's 100Hz and −60 did; and the loudest authored line reaches it at about −84dBFS on its own line, and the operator's live voice at −99.

## 10.6 Recording the Loudspeaker

Rev 22. `sbgame/audio/record/set` `"on"` starts a recording of the monitor's output — the samples written to the channels `--monitor-ch` names, after the gain and the limiter: what the audience hears, the source and a file on the monitor (§10.4) both, and silence while the monitor is muted. A 1kHz test tone on a monitor channel (§11.1) is not in it. `"off"` stops it. Recording runs whether or not a game does.

**The file.** `<--record-dir>/<YYYY-MM-DD-HH-MM-SS>.wav`, the local date and time of the start, every field joined by `-` so the names sort in time order; a second start within the same second adds `-2`. WAV, 48kHz, mono, 16-bit. The header is rewritten after every write, so a crash leaves a file that plays up to the last 20ms.

**The level.** The monitor's own level is set for the amplifier, not for a file: the installation's limiter is at −30dBFS (§10.1). So a fixed makeup gain, −1dB less `--monitor-limit`, is applied on the way to the file — +29dB at −30 — which puts the limiter's ceiling at −1dBFS in the file. Nothing in the file can exceed that, and the monitor's gain still applies, so a recording sounds as loud, relative to full scale, as the loudspeaker does relative to its limiter.

**The MP3.** When a recording stops, the program closes the WAV and starts `nice -n 10 lame --quiet -V 4` on it, writing `<name>.mp3` beside it, and does not wait: the MQTT thread collects the exit status on a later pass and logs the result. The WAV is kept either way. A recording ended by the program's own shutdown (§13.1) is closed and kept, and not converted, since stopping the service would kill the conversion; `lame` by hand does it.

**The hand-over.** The audio thread does no file I/O (§3). While `Shared::rec_on` is set, it appends each period's monitor row to a ring of 2^20 samples, 21.8s, at the end of the capture step. The MQTT thread empties the ring into the file on every pass of its loop, every 20ms, in chunks of 8192 samples, applying the makeup gain. If the MQTT thread falls more than 21s behind, the audio thread drops whole periods rather than wait, and the log's counters line counts them, `recorded periods lost N`. The MQTT thread opens the file before setting `rec_on`, and clears it before closing the file; a period the audio thread appended between the two is discarded at the next start.

**State.** `sbgame/audio/record`, retained: the base name of the file being written, `"off"`, or `"failed"` when the last `"on"` could not open a file — the directory missing or not writable — which persists until the next `record/set`. Echoed by the MQTT thread once the file is open or closed, since the file is that thread's (§12). An `"on"` while recording leaves the recording as it is and echoes its name. At `--record-max`, four hours by default, a recording stops itself, is converted, and the state goes `"off"`.

**Circuits raw** (Rev 25, bench use). With `--record-line SLOT[,SLOT...]`, up to eight circuit slots, each recording also writes `<name>.line<SLOT>[-<SLOT>...].wav`: WAV, 48kHz, 32-bit float, unscaled, two channels a slot in the order given — the slot's output as given to ALSA (pilot, file or tone, and test tone, whatever the render made), then its capture as ALSA gave it, period by period, so the round-trip delay is fixed and measurable. The audio thread writes the frames to a second ring of 2^20 samples, 10.9s for one slot and 1.4s for eight, after the render; the MQTT thread drains it with the recording's and closes it with the WAV. It is never converted, and the `.` in its name keeps it out of `audio/recordings` and playback. A full ring loses the period, counted with the recording's.

## 10.7 Playing a Recording Back

Rev 22. `sbgame/audio/playback/set` with a recording's base name, as `audio/recordings` gives it, plays `<--record-dir>/<name>.wav` on the loudspeaker; `"stop"` stops it. A name of anything but digits and dashes in the form §10.6 makes is refused, so the wire cannot reach outside the directory, and so is a file that is not 48kHz mono; either echoes `"missing"`.

**In place of the monitor.** While a recording plays, its samples are the monitor's output: the chain still runs — its filters stay warm and its gate keeps counting — but what goes to the monitor's channels is the recording, divided by the makeup gain of §10.6, which brings it back to the level the loudspeaker carried when it was made. It is not passed through the monitor's gain or limiter again, which have already acted on it, and it plays whether the monitor is muted or not. A test tone on a monitor channel (§11.1) still displaces it. A recording made while one plays back records the playback.

**Streaming.** An hour's recording is 690MB as floats, so it is not loaded as a file to play is (§7.2). The MQTT thread opens it and keeps a second ring, of the same size as the recording's, two seconds ahead of the audio thread, reading 8192 samples at a time on every pass of its loop. The audio thread takes a period from the ring while `Shared::play_on` is set, and fills with silence anything the ring cannot give; a period short once samples have begun to arrive is counted in the log's counters line, `playback periods short N`. While `play_on` is clear it empties the ring every period, so a new playback started the pass after a stop never begins with the last one's tail. When the file is read to its end and the ring has run dry, the MQTT thread clears `play_on`, closes the file, and `audio/playback` goes `""`.

**State.** `sbgame/audio/playback`, retained: the name playing, `""`, or `"missing"` until the next `playback/set`. Echoed by the MQTT thread, which carries the command out. `sbgame/audio/recordings`, retained: the ten newest recordings in `--record-dir`, newest first, one per line as `<name> <seconds>`, leaving out one being written; published with the initial state and again whenever a recording starts or stops.

Losing the game or the broker does not stop a playback (§13.2); it runs to its end. Shutdown stops it.

## 10.8 The Peer Boost

Rev 28. The monitor follows the calling line (game_control.md §6.4). On that line the caller's file returns at full strength, since the interface has no hybrid, and the called party's arrives only after crossing the operator's cord to it — on the switchboard, a good many dB lower. The audio program knows what every circuit is playing and, from its own detector, what the source is patched to, so it evens the two by measurement rather than by riding the level.

**The peer.** The detector writes each circuit's heard peer, every hop, to `Shared::heard_peer`: the slot of the one circuit heard, or 0 for idle, deaf or ambiguous. The audio thread takes the source's, and holds it through 2s of anything else, since a circuit's own playback makes its peer flicker to idle (§6.2). A different peer starts its measurement afresh; so does a different source, or the tap.

**The two paths.** While a file plays on the source and none on the peer, the source's monitor signal — after the filters and the gate, before the gain — is summed as energy against the energy of the file sent, period by period: the **own** path. While a file plays on the peer and none on the source, the same sums give the **peer** path. A file counts as playing until 50ms after its last sample, for the echo. A period in which the gate is shut is left out of both. Each sum is halved once it holds 10s, so it follows the call.

**The boost.** Once each path holds a second of file, the boost is the own path's gain over the peer's, in dB, clamped to 0 – `--monitor-peer-max` (15dB). Until then it is `--monitor-peer-start` (6dB). It is applied to the source only while a file plays on the peer and none on the source, eased in and out with a 20ms one-pole, ahead of the gain and the limiter. Anything else on the line — the operator, a live caller on the real telephone, the caller's own file — is untouched; so is a file on the monitor (§10.4). `--monitor-peer-max 0` turns it off.

**Fixed by the game** (Rev 29). `sbgame/audio/monitor/peer/set` is `"auto"`, the measurement above, or a boost in dB, 0 to `--monitor-peer-max`, which is applied as is, at the same moments and with the same easing, and nothing is measured. A figure outside that range is clamped and logged; anything else is logged and dropped. The retained `sbgame/audio/monitor/peer` echoes `"auto"` or the figure. The program starts in `auto` and returns to it, with the source, when it loses the game program (§13.2). `--monitor-peer-max 0` turns the boost off whatever is sent. The game program fixes it for a free call, whose caller is live (game_control.md §4.12, Rev 86).

**Installation.** `sbaudio.service` sets `--monitor-peer-max 20 --monitor-peer-start 12` from the measurement in Rev 28's note.

**Log.** `monitor: peer boost +N.NdB, peer <circuit> (measured|start|fixed)` when the boost or its peer changes by more than 0.5dB, at most once a second.

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
sbgame/audio/monitor/peer/set
sbgame/audio/test/+/set
sbgame/audio/record/set        sbgame/audio/playback/set
sbgame/ctl/game_heartbeat
```

Station n is validated 1–22 or 24 (Rev 24) and trunk n 1–8; a topic outside those ranges, or a `tone/set` on a station, is logged and dropped. The same ranges apply to the circuit id in a `monitor/source/set` payload (§10.3). Nothing is acted on that the program cannot echo.

Every command is acknowledged by its state topic changing, retained, from the audio thread after it has taken effect — `record/set` and `playback/set` from the MQTT thread, which carries them out (§10.6, §10.7) — — the same convention as the ESP32's `hook` echoing `hook/set` (mqtt.md §3). A command that arrives while the program is running and produces no change in the state topic was not acted on, and the log says why.

Published state at start, before the birth message, so that a subscriber that sees `audio_status` go `online` already has consistent values: `play`, `tone` and `listen` empty for every circuit, `monitor`, `monitor/source` and `monitor/peer` as started, `test/<ch>` off for every channel, `record`, `recordings` and `playback` as they are (Rev 22), `ringing` off for every station (Rev 30), then `peer`, `op` and `optone` from the analysis thread's first pass — the MQTT thread raises a flag asking for a full publish and waits for the analysis thread to report that pass done. Only then `sbgame/ctl/audio_status` = `"online"`. The same sequence runs on every reconnect. The values republished are what the program is doing at that moment, not the last values that reached the broker, so a change made while disconnected is what reconnect announces (Rev 9). (Rev 2's program published `online` first and let the detector topics follow up to a hop later — Rev 3 code consequence 3.)

# 13. Startup, Shutdown and Failure

## 13.1 Sequence

Parse options → open and configure both ALSA handles, link, allocate every buffer, lock memory → compute filter coefficients and FFT plan → start the audio thread and the stream, pilots and operator tone on from the first period → start the analysis thread → connect to the broker with the LWT, subscribe, publish the initial state (§12), publish the birth message. Audio starts before MQTT deliberately: the pilots and the operator tone are part of the switchboard's electrical environment and nothing about them depends on the broker.

SIGTERM or SIGINT: stop every program source and the test tones, clear their state topics, `ringing` off for every station (Rev 30), close a recording, unconverted (§10.6), with `record` `"off"`, stop a playback, publish `audio_status` = `"offline"` cleanly so the broker does not fire the will, disconnect, stop the stream, exit. The pilots stop with the stream, and every `peer` on the broker goes stale at that moment — which is why `audio_status` exists (mqtt.md §8.1).

## 13.2 Losing the Game or the Broker

The program mirrors the ESP32's rule (mqtt.md §8.2) for the same reason. A game program that has crashed can leave a trunk sending ringback to the operator indefinitely, which presents as a hardware fault. So:

- **Two consecutive missed `game_heartbeat`s** (no beat for 2s): stop every trunk tone and every file, clear their state topics, log it. Pilots, the operator tone and the monitor continue — they are not things the game started and are harmless without it. The monitor's source returns to the tap, under the §10.3 ramp, and `monitor/source` echoes `"tap"`, and the peer boost returns to `auto` (Rev 29): the calls a circuit source was following have been torn down, and the tap is the one source that is not about a call (Rev 8). Listens in progress are cancelled and cleared; their results would go nowhere. Test tones continue: they are a bench diagnostic, not game state, and stopping them under someone's meter is unhelpful. So does a recording (§10.6, Rev 22): the moment the game is lost is one worth having on it, and `--record-max` ends a forgotten one. A playback (§10.7) runs to its end.
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
--record-dir PATH      where loudspeaker recordings go (recordings) (§10.6)
--record-max SECONDS   longest recording; it then stops itself (14400)
--record-line SLOT[,SLOT...]  with each recording, also up to 8 slots'
                       output and capture, raw, as <name>.line<SLOT>[-<SLOT>...].wav
                       (none; bench use, §10.6)
--pilot-db DB          pilot level (-40)
--op-db DB             operator tone level (-18)
--tone-db DB           trunk tone peak level (-20)
--tone-mod M           trunk tone modulation depth, 0-1 (1.0); dial, busy, reorder
--test-db DB           test tone level (-20)
--margin-db DB         detector MARGIN_DB (20)
--peer-window-db DB    detector PEER_WINDOW_DB: a pilot further than this
                       below the circuit's own is not heard (25)
--op-window-db DB      detector OP_WINDOW_DB: the operator tone further than
                       this below the circuit's own pilot is not heard (20)
--monitor DB           start with the monitor on at this gain (off)
--monitor-ch LIST      playback channels for the monitor, comma-separated,
                       from 33, 34 (33,34), the Digiface's analog output
--monitor-src SRC      monitor source at startup: tap, station/<n> or
                       trunk/<n> (tap); refused if the device does not
                       capture that channel
--monitor-tap-trim DB  gain added while the monitor source is the tap,
                       -30 to +30 (0)
--monitor-file-trim DB gain added to a file on the monitor, -30 to +30 (0)
                       (§10.4)
--monitor-limit DB     the monitor limiter's threshold, -60 to -3 dBFS (-3)
                       (§10.1, Rev 16)
--monitor-gate DB      mute the source while its line carries more than this
                       below 50Hz, -90 to -10 dBFS (off) (§10.5, Rev 17, 19)
--monitor-gate-hold S  how long it stays muted after, 0.05 to 2 (0.25)
--monitor-peer-max DB  most the source is raised while its peer plays a file,
                       0 to 24, 0 = off (15) (§10.8, Rev 28)
--monitor-peer-start DB the boost until both paths are measured, 0 to the
                       max (6)
--monitor-lp HZ HZ DB  monitor low-pass passband edge, stopband edge,
                       stopband dB (3600 5600 70)
--vad-margin DB        speech threshold above floor (10)
--vad-floor DB         speech absolute threshold (-50)
--vad-hangover S       silence that ends speech (1.5)
--vad-max-speech S     longest speech waited out before timeout (30)
--aec on|off           the echo canceller while a circuit plays a file (on) (§9.4)
--aec-delay MS         lag before its first tap; it covers 16 ms from there (10)
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
6. Set `MARGIN_DB`, `PEER_WINDOW_DB` and `OP_WINDOW_DB` per station §8.7, against a real cord-pair connection, and confirm no `ambiguous` with every cord patched. For the windows, run the program by hand for a few seconds with `--peer-window-db 200 --op-window-db 200`, so that everything above the floor is heard and every circuit hearing more than one pilot logs `ambiguous` with each level against the own pilot in brackets — the figure the window reads (`--dump` gives levels above each bin's floor, which is not it; station §14.48). Do it with the weakest connections patched — station to station and station to trunk, each with the operator bridged on and off. Each window must take the weakest connection with room to spare and stay short of the crosstalk: on the switchboard as cabled, 44dB or more under the own pilot (station §14.48).
7. Set the amplifier's input gain with the test tone on channel 33, then set the monitor gain by ear with the operator on the headset and the limiter's activity in the log — it should be silent on ordinary speech. Then set `--monitor-tap-trim`: on a real call with the operator bridged to the calling line, switch `monitor/source/set` between `tap` and that circuit and trim until her voice is the same level on both. On the same call, once it is connected and talking, listen to the balance between the caller and the called party on the circuit source (§16).
8. Set the speech detector's margin and floor with the operator speaking through a real connection, and confirm it does not trigger on a ring-trip or a relay.

# 16. Open Items

- **Monitor level.** The monitor is on the Digiface's channels 33 and 34 again as of Rev 24, at its fixed +9.5dBu full scale; the amplifier's input gain is the bench setting (§15 step 7).
- **Capture channel count.** Expected 32 at 48kHz; confirm from the driver as the playback count was at station Rev 3.37.
- **Tone modulation depth and level.** §8.2 and §8.3; bench settings, by ear.
- **Detector `MARGIN_DB`, `PEER_WINDOW_DB` and `OP_WINDOW_DB`, tone, operator tone and monitor levels**: all bench settings, §15, none yet made.
- **Period size.** 256 is the target for the monitor loop; whether the class-compliant driver sustains it is a bench question.
- **Audio program heartbeat.** §13.3; open in mqtt.md §11.
- **Listening on the tap channel.** Not offered — the rough specification says station or trunk — but the tap always carries the operator's voice, and "has the operator said anything" may turn out to be a question the game wants to ask. One more accepted topic if so.
- **The two sides of a call on a circuit source** (Rev 8). A circuit's own transmit returns on its own receive through its own transformer's secondary. The far end crosses two transformers and the cord circuit. The caller will be louder than the called party by an amount nothing measured so far predicts. Measure it at §15 step 7. If the difference is large enough to matter, the fix is a fixed cut applied to the monitor while the source channel has an active program source, which this program already knows for §9.3's exclusion: one more option, `--monitor-own-duck DB`, default 0. It would also cut the far end during any overlap, which scripted content rarely has. Not added until the bench asks for it.
- **Reorder tone.** Not asked for and not added. If a scenario ever needs "the number you have dialled is not in service" as a tone rather than a recording, the period version is the busy waveform at 120 IPM — 0.25s on, 0.25s off — and is one more row here.

# 17. Revision History

## 17.33 Changes in Rev 33

— The document made readable, Mark's request, 2026-10-30, as `game_control.md` Rev 95. The line under the title had grown into a list of topics and now gives only the revision. The changes in each revision move out of the Overview to this section at the end of the document, newest first, where Rev 19 to Rev 32 had been in descending order after Rev 18. The text of each entry is unchanged except for references to the renumbered sections, and wording that said an entry was "above". A new revision is added at the top of this section, and the line under the title changes only its number.

— No code consequence.

## 17.32 Changes in Rev 32

— A steady level is noise, not speech, and becomes the floor at once (§9.2), 2026-10-27. Played on the switchboard at 18:03, `times-pike`: the operator, her key already in, plugged the front cord into trunk 1, and the game listened for her 0.14s after the seizure. The floor came from the second before, the unseized trunk; `speech` was reported 0.3s in and `silence` never came, so the caller waited until she gave up and the call failed `cut off`. A raw capture of trunk 1 the same evening, in the detector's band: −107.7dBFS unseized, −69.2 seized and silent, steady to ±0.3dB, broadband and centred near 1.5kHz — the line's own noise once loop current flows — and her "Number, please" peaking −24 to −28. The installation's bar of −70 sat under the seized line. A listen started a second or more after a seizure takes the seized noise as its floor, which is why answers had worked. Two rules are added: 50 frames, 0.5s, of history that all lie within 3dB of each other, their highest more than 3dB above the floor, make that highest the floor at once, and the window starts again; and speech cannot be declared while the 30 frames of the window are that steady. Both apply only to a level at or below −55dBFS: a word varies by 10dB frame to frame, but a held vowel can be steady for half a second, and it is 40dB above the seized line's noise and 30dB above the bar, so a steady level that loud is a talker. Replayed through the detector, the capture with a listen started anywhere from 13.90s, the end of the plug's two contact clicks, reports no speech until her words and their end 1.3s later; started before or during the clicks, which the seizure's 100ms (control.md §8.1) and the game's reaction make unlikely, it reports a short false speech.

— Code consequence, made the same day: `Listener::steady()` and the two rules in `vad.cpp`; `ctest` has the capture's levels, with her words both later and at once, and a held vowel at −30dBFS, at once and mid-sentence. The game program's 1.5s wait after a seizure, tried first, is not adopted: it would miss her if she spoke as she plugged in.

## 17.31 Changes in Rev 31

— A plug's click is not ring (§9.5), 2026-10-26. In play the same afternoon, plugging the rear cord into the called room's jack set `station/1/ringing` on the caller for 300ms (two blocks, the least that passed), and the game told the player she had rung the caller. Ring is nearly free of even harmonics, a click is not: each block's 40Hz amplitude must now be 20dB below its 20Hz as well, and three blocks in a row are needed, not two. In the Rev 30 capture the ring's 20Hz stood a median 53dB above its 40Hz, and 88 of its 94 blocks pass both tests; the six that do not are the edges of the three rings.

— Code consequence: a second Goertzel at 40Hz in `ring_step()`; `RING_ON_BLOCKS` 3; the click in `ctest`.

## 17.30 Changes in Rev 30

— Ring heard on an off-hook station (new §9.5, §12, §13.1), Mark's request, 2026-10-26: `sbgame/station/<n>/ringing`, `"on"` or `"off"` (mqtt.md Rev 46). The station board's ring detector does not see ring on a station held off-hook: the board's loop load pulls the line from 80V to 17V AC on the front desk (Mark's meter), below the detector's turn-on, and `station/1/ring` stayed off through three rings. The ring reaches the station's capture channel through Tx01 all the same: in a raw capture of station 1 the same afternoon, 20Hz at −25.4dBFS during each ring against −85 to −123dBFS without one, its third harmonic at −38dBFS. The game program needs it to tell the player she has rung the caller (game_control.md §6.7, Rev 89).

— Code consequence: a 20Hz Goertzel per station in `process_capture()`; `Topic::Ringing`; the `"off"` publish at start and at shutdown; `ctest`.

## 17.29 Changes in Rev 29

— The peer boost can be fixed by the game (§10.8, §12), 2026-10-25: `sbgame/audio/monitor/peer/set`, `"auto"` or a boost in dB, echoed on `sbgame/audio/monitor/peer` (mqtt.md Rev 45). On a free call the caller is live and nothing plays on the caller's line, so the own path is never measured and the boost would sit at `--monitor-peer-start`, which the installation sets for game calls. The game program knows which kind of call it is and sends the figure for a free call (game_control.md Rev 86). The program starts in `auto`, and returns to it with the source when it loses the game program (§13.2).

— Code consequence: `Verb::MonitorPeer` and `Topic::MonitorPeer`; the subscription, its check and its echo; the fixed boost in `peer_boost_begin()` and `peer_boost_end()`; `fixed` in the log line; `ctest`.

## 17.28 Changes in Rev 28

— The peer boost (§10.8), Mark's request, 2026-10-24: on the loudspeaker the called party is usually much quieter than the caller. The monitor follows the caller's line, where the caller's file returns at full strength and the called party's arrives only through the cord. While a file plays on the line the source is patched to, and none on the source, the source is now raised by the difference between the two paths, measured in the call: each file's energy as sent against what it brings to the monitor. A measurement, not an AGC, so the gaps, the hiss and the clicks are not raised. Up to `--monitor-peer-max`; `--monitor-peer-start` until both paths are measured. Measured the same evening from a loudspeaker recording, line by line within about 1dB: station to station (2 ↔ 21) the own path +4.3dB and the peer path −11.5dB, 15.8dB apart; station to long distance (16 ↔ trunk 1) +3.2dB and −5.6dB, 8.7dB apart. The program's defaults are 15dB and 6dB; the installation sets 20dB and 12dB, between the two kinds of call.

— Code consequence: `Shared::heard_peer`, written by the detector each hop; the boost in `process_capture()`, the file energies in `render()`; the two options; the log line; `ctest`.

## 17.27 Changes in Rev 27

— The installation's line-disturbance gate threshold goes from −70dBFS to −60 (§10.5), 2026-10-24. Mark heard a caller cut in and out on the loudspeaker in play (crane-stoneburner, station 22 as the monitor source, headset not keyed): the gate shut 1, 3 and 4 times in the call's three 10s windows with no xrun, no lost period and no cord moving, the 2026-10-19 symptom on the V16 salesman again. The live test of 2026-10-19 was never run; −60 is a step back toward Rev 17's figure, not a measurement. It lets about 10dB more LF through before the gate shuts, so a switch flip or a ring may now be heard faintly on the loudspeaker; if it is, the threshold is between the two and wants the recording.

— Code consequence: none in the program; `sbaudio.service` sets `--monitor-gate -60`.

## 17.26 Changes in Rev 26

— An echo canceller on every circuit while it plays a file (§9.4), so a listen hears a caller who talks over the file instead of discarding those frames (§9.3). Asked for 2026-10-24 for free calls (game_control.md Rev 79), where Mark's "What power?" over the end of Thornhill's line went unheard. Measured first with `--record-line` (Rev 25) on station 21, the real phone at the far end: the file returns 12–15 dB down, 11.7ms late, its echo over within 26ms; a fixed filter takes 36–40dB off it. Trunks are not measured: their pilot returns only 5dB down, and the public line's audio from outside does not work yet. The canceller needs no measurement to be safe on them — until it has converged it changes nothing.

— Regular play is unchanged. The game listens there only after a line has ended, and nothing a canceller does reaches a listen that starts after the file: its frames are kept out of the history the floor comes from, and a listen clears its window when it starts.

— Code consequence, made the same day: `aec.h` and `aec.cpp`; `Engine::aec_feed()` in the render and the canceller's step in `process_capture()`; `Listener::frame()` gains `keep` and `min_db`; `--aec` and `--aec-delay`; `test_aec()`; `aec_check`, the canceller over a recording, for the bench.

## 17.25 Changes in Rev 25

— `--record-line SLOT[,SLOT...]`, a bench option (§10.6, §14): with every loudspeaker recording, the program also writes up to eight slots' output and capture, raw, to `<name>.line<SLOT>[-<SLOT>...].wav` beside it. It is for measuring how the circuit's own playback returns on its receive — the echo that §9.3 discards — to decide whether a software echo canceller can let the speech detector hear a caller who talks over a file (game_control.md Rev 78, 2026-10-24). Not set in service; added to the unit for a bench session and taken out after.

— Code consequence, made the same day: `Engine::record_line()` after the render, `Shared::line_ring`, the second file in the Recorder.

## 17.24 Changes in Rev 24

— Slot 24 is a circuit again: station 24, a real telephone on station board 3 strip 8 (§2), following real_phone.md Rev 2 (adopted 2026-10-23), control.md Rev 33 and mqtt.md Rev 44. Strip 8 now has its relay, Cx01 and Tx01 fitted, so A32 channel 24 is a line interface in both directions like stations 1–22: its pilot, bin 696, is generated, its capture is a detector input, and it takes `play`, `listen`, `peer`, `op`, the monitor source and the test tone as any station does. Measured on the bench the same day, with the phone corded to station 22: 1kHz crossing in 9.3dB each way, reciprocal.

— The monitor leaves A32 output 24 for the Digiface's own analog output, channels 33 and 34, the fallback of Rev 7 (§10.1). The default `--monitor-ch` is now `33,34`, and only 33 and 34 are accepted; 24 is a circuit and is refused like any other. The service already ran with `--monitor-ch 33`. The level is the Digiface's fixed +9.5dBu full scale; real_phone.md §4 has the cable.

— Code consequence, for Claude Code: `channels.h` (slot 24 a station; `can_carry_monitor()` 33 and 34 only); the monitor's file kept in `prog_[0]`, the element no slot uses, where it was in `prog_[24]`; station numbers 1–22 and 24 wherever a station topic is validated; the tests.

## 17.23 Changes in Rev 23

— The installation's speech hangover is 0.5s, not the default 1.5s (§9.2), Mark's request, 2026-10-19: the pause between the operator's last word and the caller's line was too long, long enough to wonder whether the game had heard her. The caller's line starts on `"silence"`, which comes about 0.3s after her last loud frame, for the 30-frame window to clear, plus the hangover: about 1.8s at 1.5s, about 0.8s at 0.5s. The cost is that a pause of more than 0.5s inside what she says ends it there, and the caller speaks over the rest; Mark judges that the lesser fault.

— Code consequence, made the same day: `sbaudio.service` sets `--vad-hangover 0.5`. The default is unchanged.

## 17.22 Changes in Rev 22

— The loudspeaker feed can be recorded (§10.6), Mark's request, 2026-10-18: a WAV of what is sent to the audience loudspeaker, named for the local date and time it started, `2026-10-18-14-32-05.wav`, converted to an MP3 beside it when it stops; both are kept. `audio/record/set` `"on"` or `"off"`, echoed on `audio/record` with the file's name, `"off"` or `"failed"` (mqtt.md Rev 36). The game program sends it from the page's Tools (game_control.md Rev 61, §7.7).

— And played back (§10.7): `audio/playback/set` with a recording's name plays it on the loudspeaker in place of the monitor, at the level it was recorded, streamed from the file through a second ring, MQTT thread → audio thread, since an hour's recording is 690MB as floats. `audio/recordings` lists the ten newest with their lengths, for the page to choose from.

— The audio thread touches no file for it (§3): while a recording runs it appends each period's monitor row to a 2^20-sample ring, 21.8s, and the MQTT thread empties the ring into the file on every pass of its 20ms loop. A full ring loses the period and counts it in the log. The MQTT thread already does file I/O, loading files to play (§7.2), so it gains no new kind of work. A recording is not game state: it continues through game and broker loss (§13.2), and stops at `--record-max`, four hours, so a forgotten one does not fill the disk.

— Code consequence, made the same day: `rec.h` and `rec.cpp`, the ring and the Recorder; `Shared::rec_ring` and `rec_on`; the hand-over at the end of `process_capture()`; `handle_record()` and `publish_record()` in `net.cpp`; the Player, `Shared::play_ring` and `play_on`, the playback in place of the monitor row, `handle_playback()`, `publish_playback()` and `publish_recordings()`; `--record-dir` and `--record-max`; `test_recording()`. `sbaudio.service` gains `--record-dir /srv/sbgame/recordings`, which `make -C host sbgame-data` makes, owned by `sidell`. The MP3 needs `lame` on the host (`apt install lame`); without it the WAV is kept and the log says why.

## 17.21 Changes in Rev 21

— Ringback is the city ring of a real 803C tone alternator, measured from a recording, in place of a 420Hz carrier amplitude-modulated by 40Hz (§8.2). Mark's request, 2026-10-17, after comparing the two: ours had exactly three lines, 380, 420 and 460Hz, and none of the machine's character. The recording, of the Atlanta "755" step-by-step office (atlantatelephonehistory.org, `atlanta:ringing`, `1060-A-1333-755R.wav`; Mark's choice of the samples there), measured: every component a whole multiple of the ringing frequency, 19.744Hz — the machine ran 1.3% slow, and its cadence with it, 1.95s in 6.08s; almost no energy at the nominal 420Hz; the strongest lines at 420 ± 20, ± 60 and ± 100Hz, which is 420Hz multiplied by the 20Hz ringing current, and the 40Hz beat of that; a group near 1240Hz, three times 420, 18dB down; and a comb of low harmonics, 100–320Hz, 17–30dB down. The other two city rings measured, Tucker "938" and "577", have the same lines with the lower sideband strongest. A least-squares fit of the 755 recording to the harmonics of 19.744Hz, kept within 40dB of the strongest — 48 of them, all below 1.4kHz — is set on 20Hz exactly, so 420Hz nominal and the cadence 2s in 6s as before, and one period is 2400 samples. The hiss and the mercury interrupters' "shhh" of the recording, about 20dB under the ring in the silent interval, are not reproduced.

— Code consequence, made the same day: `audio/src/cityring.h`, the 48 partials; the table built once in `prepare()` and played a sample at a time for ringback in `engine.cpp`; `test_trunk_tones()` in the tests, which checks reorder's cadence too. `tts/cue` reads the same partials for the loudspeaker's ring cue (game_control.md §6.6), so the trunks and the loudspeaker sound alike. `--tone-mod` now sets dial, busy and reorder only. No MQTT change.

## 17.20 Changes in Rev 20

— Reorder, the fast busy, added to the trunk tones (§8.1, §8.2), following game_control.md Rev 56, 2026-10-17: the game plays it on a trunk when the operator dials a number with too many digits or too few. The busy waveform interrupted at 120 IPM, 0.25s on and 0.25s off, which is how the period offices made it, from the same source as busy. `"reorder"` on `tone/set` (mqtt.md Rev 35).

— Code consequence, made the same day: `ToneKind::Reorder`, its row in `TONES[]` and `TONE_NAME[]` in `engine.cpp`, and its name in `net.cpp`.

## 17.19 Changes in Rev 19

— The line-disturbance gate listens below 50Hz, not 100Hz, and the installation's threshold is −70dBFS, not −60 (§10.5). In play on the switchboard, 2026-10-16, the gate shut four and seven times in ten seconds in the middle of a conversation, with nobody at the board. A man's voice has its fundamental near 100–130Hz: the authored lines carry up to −42.5dBFS below 100Hz, which reaches a line at about −60, the threshold, and the gate was cutting words out of the loudspeaker. Below 50Hz the loudest line reaches it at −84 and the operator's own voice at −99, while ringing and switch thumps are still at −15 to −45; at −70 the recording of the switchboard is gated exactly as before.

— Code consequence, made the same day: `GATE_LP_HZ`, and `sbaudio.service` sets `--monitor-gate -70`.

## 17.18 Changes in Rev 18

— The speech detector's low-pass is sixth-order, and the installation's `--vad-floor` is −70dBFS (§9.2). Found on the switchboard, 2026-10-16: the detector heard the operator only when she spoke loudly. Bridged onto station 13 and counting one to ten at a normal level, she was not heard in a 30s listen. A recording of the line put her voice at −55 to −65dBFS in the detector's band, peaks −47, against a threshold of −50, the absolute bound, which no word cleared for the 200ms of 300 a start needs. Lowering the bound alone does not do: through one low-pass section the station's own pilot, measured at −58.4dBFS on the line, arrives at −71.5 and sets the floor, so floor + 10dB is −61, still above most of her voice. With three sections the pilot is at −97, under the line's own noise near −91, and with the bound at −70 the recording declares speech one second into the count, with no frame above −70 in the quiet before it. Her voice is about 30dB below the authored speech on the line; a stronger transmitter would give more margin, and the electret headset (kicad/electret) is the way to it.

— Code consequence, made the same day: `butter_lowpass6()` in `dsp.cpp`, the detector's three sections, and the tests. `sbaudio.service` gains `--vad-floor -70`.

## 17.17 Changes in Rev 17

— The line-disturbance gate (§10.5), 2026-10-16: the switch clicks were still heard at speech level under Rev 16's limiter, and ringing a station rumbled on the loudspeaker. A recording of the switchboard showed both as energy below 100Hz far above anything speech carries, so the source is muted while that lasts, plus a quarter second, behind a 10ms delay that lets it shut before the onset. This is the click suppressor Rev 16 kept in reserve, keyed on the low band rather than on a jump in level. `--monitor-gate` and `--monitor-gate-hold`; the counters line gains `gate`.

— Code consequence, made the same day: `Engine::gate_step()`, the options, and the counter. `ctest` has speech passing, ringing shutting it, the hold, and the reopening.

## 17.16 Changes in Rev 16

— The monitor limiter's threshold is a setting, `--monitor-limit`, −60 to −3dBFS, −3 by default as before (§10.1). Found on the switchboard, 2026-10-16: moving a cord pair's switch clicks loudly on the loudspeaker. The switch makes and breaks the line the monitor follows, and the click reaches the output far above speech, where a limiter at −3dBFS never touches it. Set just above the loudest speech, the limiter holds the click to that level. The installation sets −30dBFS: with the monitor at −12dB and the tutor's files at −18, speech peaks about −33dBFS at the output. A click suppressor that mutes the monitor for a few tens of milliseconds on a jump no speech makes is the next step if the clicks at speech level still bother; it is not done.

— Code consequence, made the same day: the option, and the limiter releases before it attacks, so the sample that sets its gain is never let back above the threshold. In the old order it overshot by a little — nothing at −3dBFS, about 0.6% at −30. `ctest` has a click at −1dBFS held to −30, and speech below it untouched.

## 17.15 Changes in Rev 15

— Following station Rev 3.48: `--peer-window-db` and `--op-window-db` compare absolute bin levels, not each bin's level above its own floor, and `--peer-window-db` defaults to 25, down from 40. With the trunks on the switchboard, floors 15–30dB apart made trunk crosstalk 44dB under the own pilot read 12dB under it, and false trunk-to-trunk peers were published (2026-10-16).

— Code consequence, made the same day: the change in the detector, and the `ambiguous` log gives each pilot's level against the own pilot in brackets after its level above the floor, which is what the window reads. `ctest` has an idle trunk whose own bin's floor is raised 40dB, which reads idle.

## 17.14 Changes in Rev 14

— `--op-window-db`, 20 by default, following station Rev 3.47: the operator tone counts only within that many dB of the circuit's own pilot. The tap's 9kHz leaks into other channels, 46dB under the own pilot on station 22, enough above the floor to light `op` on nine circuits with nothing bridged (2026-10-15). §15 step 6 now measures the operator tone on a bridged circuit as well.

— Code consequence, made the same day: the test in the detector. `ctest` has the leak on an idle trunk, which reads `op` off.

## 17.13 Changes in Rev 13

— The detector's peer window, `--peer-window-db`, following station Rev 3.46 §8.7: a comb pilot counts only if it is within that many dB of the circuit's own pilot as well as `MARGIN_DB` above its floor. On the bench, 2026-10-15, the trunk board's strip-to-strip crosstalk, 72dB under each trunk's own pilot, sat 20–39dB above the floor and made every idle trunk `ambiguous`; a station cabled straight to a trunk arrived 3dB under the own pilot. 40dB is the starting value. A peer through the switchboard will arrive lower than through a cable, so §15 step 6 sets the window with the margin.

— Code consequence, made the same day: the option, the test in the detector, and the startup log line reports both values. `ctest` has an idle trunk with that crosstalk, which reads idle, and a connected one, which reads its peer.

## 17.12 Changes in Rev 12

— An output self-check (§11.4), 2026-10-14. On the bench that afternoon, with only the audience monitor connected to the A32 and the test tone on 24, the A32's output meters showed channels 9, 17 and 25 steady near 0dBFS and, every 4–5s, a burst of about 1.5s taking nearly every output close to full scale; the detector heard the bursts on capture from 15:07:25 to 15:24:44. Nothing had been commanded, the log showed no xrun, clip or limiter count, and the A32's routing and clock were correct (ADAT 1–32 to analog 1–32, slaved to ADAT port 1, all four ports locked at 48kHz). Stopping `sbaudio` cleared the meters; `tone_out` driving the same channels at the same levels was clean; and `sbaudio` restarted, by hand at periods of 1024 and 256 and then under its service with the test tone on 24, was clean for the next half hour. So the process that had run since 07:32 got into a state that a restart cleared, and nothing says whether the bad samples were in its playback buffer or were corrupted after it. The check answers that the next time: it compares what the program is about to write with what each channel should carry. If it logs the channels the meter shows, the fault is in the program; if it stays silent while the meter misbehaves, it is after the program — ALSA, USB or the Digiface.

— Code consequence, made the same day: `render()` records each channel's ceiling, and a scan of the playback buffer before each write counts the periods that exceed it per channel; the MQTT thread logs them with the counters (§11.2). `ctest` covers a clean render and a corrupted one.

## 17.11 Changes in Rev 11

— The monitor plays a file (§10.4), following game_control.md Rev 29, 2026-10-08: `sbgame/audio/monitor/play/set` and its echo `sbgame/audio/monitor/play`, as a circuit's `play/set` and `play` (mqtt.md Rev 27). It is the tutor's voice in tutor mode, heard on the loudspeaker. The file is summed into the monitor chain after the source's filter, through a second copy of the same low-pass, then takes the monitor's gain and limiter: the loudspeaker is in the room with the operator's microphone, so the file is held out of the pilot band exactly as the source is, and the monitor's one level sets both. A new option, `--monitor-file-trim`, sets the file's level against the source's. Nothing else about the monitor changes.

— Code consequence, made the same day: the file is slot 24's program source; `process_capture()` sums it into the chain and stops it at its end; the MQTT thread subscribes to the monitor's `play/set`, handles it as a circuit's, and publishes `audio/monitor/play` at start, on stop, on the game's loss and on shutdown; `ctest` covers the mix, the echo and the mute.

## 17.10 Changes in Rev 10

— The operator tap plays files (§7), following game_control.md Rev 25, 2026-09-30: `sbgame/audio/tap/play/set` and its echo `sbgame/audio/tap/play`, as a circuit's `play/set` and `play` (mqtt.md Rev 23). It is for the game program's diagnostics, which play speech into the operator's headset to check the tap's output path. The file sums over the operator tone, which is never displaced (§5.2), so the tap stays detectable while it plays; the tap has no trunk tones. Nothing else about the tap changes: its receive side, the optone check and the monitor source are as they were.

— Code consequence, made the same day: the mixer sums a file on channel 23; the MQTT thread subscribes to the tap's `play/set`, handles it as a circuit's, and publishes `audio/tap/play` at start, on stop and on shutdown as it does a circuit's `play`. `ctest` covers the mix and the topic.

## 17.9 Changes in Rev 9

— Written against Claude Code's report of 2026-09-24: `sbaudio` is at Rev 8. The report raised three places where Rev 8 was silent or read two ways. This revision settles them.

— The tap trim has a range: −30 to +30dB, and `--monitor-tap-trim` outside it refuses to start, as any other invalid option does (§10.3, §14). Rev 8 gave no range. The effective gain — the commanded gain plus the trim — is deliberately not clamped to the −60 to +20dB of `monitor/set`. That range is for the command. The trim is an installation constant that makes the tap and a circuit sound the same at one commanded gain. Clamping the sum would cap the tap at a lower commanded gain than a circuit, which is the mismatch the trim exists to remove. The −3dBFS limiter is what protects the output (§10.1). Claude Code left the sum unclamped and asked whether that was intended. It is. Code consequence: the range check at startup.

— State republished on reconnect is what the program is doing at reconnect (§12, §13.2). §13.2 said results posted while disconnected are discarded, and §12 said reconnect republishes state. For `monitor/source` the two pulled apart. A source changed while disconnected — the return to the tap, above all — would have been discarded as a result, and reconnect would have announced a circuit the program had already left. Claude Code kept the value current while disconnected and republished it. That is adopted. The discard applies to results the other threads post. State on reconnect is read from the program as it stands, for `monitor`, `monitor/source` and `test/<ch>` alike. No code consequence.

— A source the device does not capture is refused (§10.3). Rev 8 validated a source against the circuit ranges only. So on a device presenting fewer than 32 capture channels, `--monitor-src trunk/8` started, echoed `trunk/8` and fed silence. A loudspeaker fed silence while the echo names a live line looks like a line with nobody on it, and nothing says otherwise. Now `--monitor-src` naming a channel beyond the capture count the device reports refuses to start, as `--monitor-ch` does for a bad playback channel. A `monitor/source/set` naming one is logged and dropped with no echo, like any invalid payload. On this system a capture count below 32 is itself a fault, and one the detector would suffer too (§16, capture channel count). Code consequence: the check at startup and on the command.

## 17.8 Changes in Rev 8

— The monitor can take its input from any station or trunk receive channel as well as from the tap (§10.3). Mark's decision, 2026-09-24. Rev 1 to Rev 7 fed the loudspeaker from the tap's receive channel only. The operator leaves a call when she throws the ring key to ring the called party, and does not come back to it, so the audience heard the request and the operator and then nothing of the conversation the scene was written for. A circuit's receive channel carries the whole conversation: its own transmit returns on it at full strength, because the interface has no hybrid (station §8.4), and the far end arrives through the cord. The operator's voice is on it too while she is bridged to that line.

— One new command and its echo: `sbgame/audio/monitor/source/set` and `sbgame/audio/monitor/source`, with `"tap"` or a circuit id as the payload (mqtt.md Rev 13). `monitor/set` stays the gain alone, so the one-value rule of mqtt.md §2 holds. The game program chooses the source: the calling line of the call the operator most recently answered (game_control.md Rev 6 §6.4). This program knows nothing about calls and does not choose.

— The chain after the input is unchanged. The station §8.8 filter removes a circuit channel's own pilot, its peer's pilot and the operator tone exactly as it removes the operator tone and pilots from the tap channel.

— The switch is made under a 20ms ramp to silence and back (§10.3), the same ramp the gain uses, so a source change does not click.

— Two options (§14). `--monitor-src` sets the source at startup, `tap` by default, so a bench run with no game behaves as Rev 7 did. `--monitor-tap-trim` is a gain applied only while the source is the tap. The tap arrives about 15dB below the operator's line (station §7.9.3), and a circuit channel sees its line through T2 alone, so without a trim one monitor gain cannot suit both. Its value is a bench setting (§15 step 7).

— The source returns to the tap when the program loses the game or the broker (§13.2). The calls it was following have been torn down, and a crashed game should not leave the loudspeaker on a line nobody is using.

— Not added: any correction for the balance between the two sides of a conversation on one circuit channel. The line's own transmit returns through its own transformer's secondary only; the far end crosses two transformers and the cord circuit. The own side will be louder by an amount nothing measured so far predicts. §16 records the fix to add if the bench says it is needed.

— Code consequence, for Claude Code: subscribe to `monitor/source/set`; validate it and echo it on `monitor/source` (§12); switch the monitor's input in the audio thread as §10.3 says; `--monitor-src` and `--monitor-tap-trim`; the return to the tap in §13.2; `monitor/source` in the state published before birth (§12).

## 17.7 Changes in Rev 7

— The audience monitor moves to A32 output 24 and the operator tap to A32 channel 23, following station Rev 3.40 (Mark, 2026-09-23). Rev 1 to Rev 6 put the tap on channel 24 and sent the monitor to the Digiface's own analog output, playback 33 and 34. Station board 3 strip 7 is now the tap and strip 8's A32 output is the monitor feed, so stations are 1–22. §1, §2, §5.1, §6.3, §10, §11.1, §12, §14, §15 and §16 follow.

— Why. An A32 output is balanced, and its analog level is set by the A32's per-channel reference and trim, recallable from its front panel. The Digiface jack is unbalanced and fixed at +9.5dBu full scale with no TotalMix under Linux, which left this program's gain as the only control ahead of the amplifier. Station §14.40 records the decision.

— The Digiface is still opened at 34 playback channels, so nothing in §4 moves. Channels 33 and 34 carry silence except under the test tone, and are the fallback monitor output: going back to them is a command-line change, `--monitor-ch 33,34` (§14), not a code change. That option is new.

— Capture channel 24 is now unused — station board 3 strip 8 has no receive path fitted — and nothing reads it. It is not a detector input. Comb slots 23 and 24 (bins 688 and 696) are not generated.

— Code consequence, for Claude Code: the channel map of §2 and everything derived from it. Stations 1–22 in the per-circuit tables, the detector and the MQTT validation (§12); pilots on 1–22 and 25–32; the operator tone and the `optone` check on channel 23; the monitor chain reading capture 23 and writing playback 24, or the channels `--monitor-ch` names; capture 24 ignored; playback 33 and 34 silent unless named by `--monitor-ch` or under test. mqtt.md Rev 9 has the topic ranges.

## 17.6 Changes in Rev 6

— The listen reports the end of speech as well as the start. Rev 1 to Rev 5 made a listen one-shot: `"listening"`, then `"speech"` the moment speech was detected, and the listen was over. The game's scenarios need to know when the caller has finished talking, not only that they began — a scripted reply that starts while the caller is mid-sentence is the one thing the audience will notice. So the listen now continues after `"speech"` and reports `"silence"` when the talking stops, or `"timeout"` if it does not stop within a cap. One command still starts the whole sequence; the state topic carries it, which is what a retained state topic is for. §9.1 and §9.2.

— The payload stays one number, the time allowed for speech to start. The two new times — the silence that counts as the end of speech, and the longest speech the program will wait out — are options with defaults (§14), not payload, because they describe how people talk and not a scenario, and because mqtt.md §2 says one value per topic. If a scenario ever needs its own cap, that is the point to add a second payload form; not before.

— `"silence"` is a new value rather than the empty string, so that a listen that completed is never confused with one that was cancelled or never issued: empty stays the cleared state, as on every retained topic (mqtt.md §7). `"timeout"` is reused for both failures — speech never started, speech never stopped — because the game knows which by the value before it, and a game restarted mid-listen has lost the listen either way.

— Code consequence, for Claude Code: `Engine::start_listen`, the VAD frame loop and `cancel_listen` change to the state machine of §9.2; two options, `--vad-hangover` and `--vad-max-speech`; `mqtt.md` Rev 8 has the payload values. mqtt.md Rev 8 follows.

## 17.5 Changes in Rev 5

— Cross-reference only. `esp32.md` is `control.md` and `ring/esp32.ino` is `control/control.ino` as of 2026-09-19 (control.md Rev 9); §1 and §17.3 follow. Nothing in this document changes.

## 17.4 Changes in Rev 4

— The three Rev 3 code consequences are fixed in `sbaudio` (2026-09-18); the build-state paragraph in §1 says so.

— §14: the default MQTT client id is `sbgame-audio`, not `sbaudio`. Rev 3 wrote the binary's name; the program used `sbgame-audio`, which follows the ESP32's `sbgame-esp32` — the `sbgame-` prefix names the system the client belongs to, as the topic prefix does, and the broker's client list then reads as one system. Mark and Claude Code chose the program's form; the document follows.

## 17.3 Changes in Rev 3

— Written against the finished program, as control.md Rev 4 was against the firmware. Nine implementation decisions are adopted into the text with their reasoning, and three defects found in review are recorded here as code consequences for the Claude Code side.

— Adopted, §3: the MQTT thread is a polled loop — `mosquitto_loop()` with a 20ms timeout, then drain the result queue, then repeat. A result posted by the audio or analysis thread reaches the broker within 20ms, inside the 43ms detector hop, and one thread does the whole job. The alternative — libmosquitto's own network thread plus an eventfd the audio thread would have to write — was not needed.

— Adopted, §3 and §6.1: the analysis thread polls a two-slot mailbox with a 2ms sleep rather than waiting on a condition variable, so the audio thread touches nothing but an atomic to hand over a hop. Two snapshot buffers; if the analysis thread still holds the one due to be filled, the hop is dropped and counted, never waited for.

— Adopted, §14: `--no-realtime`, and the audio thread's SCHED_FIFO priority is 70. `--window rect|hann` implements station §8.2's Hann fallback, with the guard offsets moved to ±4/±5 because Hann's main lobe is ±2 bins and guards at ±2/±3 would measure the pilot's own skirt. `--mqtt-user`, `--mqtt-pass`, `--mqtt-pass-file` and `--client-id` for mqtt.md §9; `--broker` takes `host[:port]`. FFTW wisdom is cached at `$SBAUDIO_WISDOM` or `~/.cache/sbaudio-wisdom`.

— Adopted, §7.1: an empty `play/set` payload is a stop, the same as `"stop"`. A filename is at most 31 characters and may not contain a backslash or a control character, in addition to the `/` and `..` rules of mqtt.md §7. Adopted, §9.2 and §14: every dBFS figure in the program — the VAD floor and margin, the file content check, the logged levels — is referenced to a full-scale sine, RMS × √2, so `--vad-floor -50` means a signal whose RMS is that of a −50dBFS sine. Adopted, §13.2: reconnect backoff starts at 1s and doubles to 30s; the will is registered once on the handle and survives reconnects.

— Code consequence 1, §3: the MQTT thread spins while disconnected. `mosquitto_loop()` returns at once with no connection, so between reconnect attempts the loop runs flat out — a core pegged for up to 30s at a time. Sleep 20ms per pass when not connected. Harmless to the audio thread, which is real-time, but wrong.

— Code consequence 2, §6.1: the snapshot handover has a race. The audio thread checks a buffer's busy flag before filling it, but the analysis thread sets that flag only after it has taken the buffer's index from the mailbox, so a late-waking analysis thread can claim a buffer the audio thread has just started to overwrite. Separately, a hop that the analysis thread never collected is silently superseded and not counted. The protocol is restated in §6.1 so that the audio thread owns setting busy and the analysis thread owns clearing it, and a superseded hop is reclaimed and counted.

— Code consequence 3, §12: `audio_status` `"online"` is published before the first detector pass rather than after it. The spec and mqtt.md §8.4 put state before birth; the program publishes birth and lets `peer`, `op` and `optone` follow on the next hop, up to 43ms later. Hold the birth message until the analysis thread has completed its first forced pass.

— Minor, for the same pass: `ambiguous` logs its pilot list every hop, 23 lines a second for as long as the condition lasts; log it on the transition and at most once a second after. `--version` still reports Rev 1. The tarball reviewed did not include the build file, `pilot_loopback_test.cpp` or `docs/pilot-map.md`, so the §10.1 unit test on the elliptic stopband is unconfirmed; the startup log line that reports the realised response at 6000Hz covers it in practice.

## 17.2 Changes in Rev 2

— The Digiface is not addressed as `hw:Digiface`. Claude Code found on the host that ALSA registers the card under an alphanumeric identifier, not under the product name Rev 1 assumed in §4 and as the `--card` default in §14. §4 now says the card is addressed by whatever id `/proc/asound/cards` reports for it, §14's `--card` has no default and is required, and the id in use goes in the systemd unit alongside the other host-specific settings. Rev 1's default would have failed to open the device on every start.

## 17.1 Changes in Rev 1

— New document, written from a rough specification of the six functions above and from station §8 and mqtt.md Rev 4. The detector was the program's whole job until now and was specified only in station §8.7, with the program named but not described in mqtt.md §1. The five commanded functions are new.

— One decision made that the rough specification left open: how the program reports that a file has finished. It asked for "an mqtt response when a file finishes playing". The response is the `play` state topic going empty (§7.4), not a new event topic. mqtt.md §2 allows one event in the design, `digit`, and records what an event costs: unretained, not idempotent, lost across a game restart. None of that is wanted here. A retained state topic carrying the filename while it plays, and cleared when it stops, tells the game the same thing and additionally tells a game program restarted mid-file what is playing.

— One conflict with station §8.8 resolved in §8.8's favour. The rough specification asked for the monitor low-pass at 3kHz. Station §8.8 specifies a passband edge of 3.6kHz and a stopband edge of 5.6kHz, and it is the stopband edge that removes the lowest pilot at 6000Hz, not the passband edge. Moving the passband edge to 3kHz would cut the top of the 300–3400Hz band the switchboard passes and remove nothing that 3.6kHz does not already remove. The filter is as §8.8 specifies (§10). If the intent was a narrower, more "telephone" sound rather than pilot removal, that is a passband-edge parameter and is exposed as one.

— Tone frequencies are the pre-precise-tone-plan Bell tones — dial tone 600Hz modulated by 120Hz, ringback 420Hz modulated by 40Hz at 2s on, 4s off — chosen by Mark on 2026-09-17, before this document was first uploaded, in place of the precise tones (350 + 440Hz, 440 + 480Hz) the first draft carried as the default. The 551 predates the precise tone plan and the exhibit is set in that period; the precise tones are what a modern ear expects and would be the one anachronism the operator hears on every call. The precise tones are recorded in §8.2 as the alternative, since they are the same generator with a different table.

— Busy tone added to §8 at Mark's request, same day, after the first draft listed it as a possible extension: the game's scenarios will include called numbers that are busy. One more row in the §8.2 table and one more `tone/set` value; mqtt.md Rev 6 carries the payload.

— The test tone replaces the pilot on its channel rather than summing with it, so the circuit reports `deaf` while the test tone is on (§11.1). Recorded so the `deaf` is not mistaken for a fault.
