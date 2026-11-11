# `sbaudio` — the audio program

C++17: the program `sbaudio`, its tests and two offline tools. Specified by `docs/audio.md`, which is the authority for
everything here; `docs/mqtt.md` owns the wire, `docs/station_circuit.md` §8 owns the
pilot comb, the detector and the monitor filter, and `docs/pilot-map.md` owns the
slot ↔ bin table. This file is how to build and run it, not what it does.

## What it is

One ALSA duplex stream on the Digiface USB — 34 playback, 32 capture, 48 kHz, S32_LE —
and three threads:

| Thread | Owns | Priority |
| --- | --- | --- |
| audio | the stream, the mixer, the monitor chain, the speech detector | `SCHED_FIFO` 70, memory locked |
| analysis | 32 × 4096-point FFT per hop, the pilot detector | normal |
| MQTT | libmosquitto, file loading, all publishing | normal (it is the main thread) |

They share three lock-free queues, the hop snapshots, the sample rings of the recording
and its playback, and some atomics (`audio.md` §3). Nothing allocates, logs, locks or
touches a file in the audio thread, except when recovering from an xrun, when the
deadline has already been missed.

## Build

```
sudo apt install cmake pkg-config libasound2-dev libfftw3-dev libmosquitto-dev libsndfile1-dev
cmake -S audio -B audio/build -DCMAKE_BUILD_TYPE=Release
cmake --build audio/build -j
ctest --test-dir audio/build --output-on-failure
```

`sbaudio_test` needs no hardware and no broker. It checks the pilot map against
`docs/pilot-map.md`, the monitor low-pass against `station_circuit.md` §8.8's 70 dB at 6000 Hz and
the content check's high-pass against the telephone band it has to ignore —
which `audio.md` §10.1 asks for by name, because the lowest pilot sits exactly there —
and the detector against a synthetic block built with the same wavetable expression the
engine renders pilots with. It drives the real engine, period by period, with no audio
device.

Two tools build beside it and need no hardware either:

- `monitor_check [--dir wav] [MATCH]` plays every prompt through the loudspeaker's chain
  with the service's settings and lists any the line-disturbance gate shuts on
  (`audio.md` §10.5). Run it from the repository's top, where `wav/` is.
- `aec_check` runs the echo canceller over a `--record-line` recording (`audio.md` §9.4).

`sbaudio --version` gives the commit it was built from, `-dirty` if `audio/` had
uncommitted changes; so does the first line of its log.

## Run

```
./audio/build/sbaudio --broker localhost:1883 \
    --mqtt-user sbgame-audio --mqtt-pass-file /etc/sbgame/mqtt-audio.pass --wav-dir wav
```

`--help` lists every option; they are `audio.md` §14's list exactly. Without `--card`
the program opens the one card whose name in `/proc/asound/cards` contains "Digiface",
and refuses to start if there is none or more than one. `--card <id>` names it: the id
in the second column of `/proc/asound/cards`, which `snd-usb-audio` derives from the
device's serial number, so `USB` and eight digits. Prefer `--mqtt-pass-file` to
`--mqtt-pass`: a password in `ExecStart` is in every `ps` listing on the host. The
password file is the host's, not this program's: `/etc/sbgame/mqtt-audio.pass`, 640,
owned by root with the service user's group, made with the others by the steps in
`host/README.md`, and user `sbgame-audio` is its broker entry.

The channel map is `audio.md` §2 and `docs/pilot-map.md`: stations on document channels
1–22 and 24, the operator tap on 23, and trunks on 25–32. The audience monitor is on the
Digiface's own analog pair, 33 and 34, and the installation uses 33 (`--monitor-ch 33`).
All 32 capture channels are read. The map in use is printed at startup, beside the
negotiated ALSA parameters, so a wiring check can be made from the journal.

Without hardware, an ALSA loopback card is enough to exercise everything but the
converters:

```
sudo modprobe snd-aloop pcm_substreams=1
./audio/build/sbaudio --card Loopback --no-realtime --broker localhost:1883 \
    --mqtt-user sbgame-audio --mqtt-pass-file /etc/sbgame/mqtt-audio.pass
```

Every circuit then reads `deaf`, which is correct — nothing is writing the other side of
the loopback — and every command, echo, failsafe and shutdown path works normally.

## As a service

```
sudo install -m 755 audio/build/sbaudio /usr/local/bin/sbaudio
make -C host install          # the unit, with the rest of the host's files
sudo systemctl enable --now sbaudio
journalctl -u sbaudio -f
```

After a rebuild, the `install` line and `sudo systemctl restart sbaudio`: the service
runs the copy in `/usr/local/bin`, not the build directory.

The unit is `host/etc/systemd/system/sbaudio.service`, so `make -C host diff` reports
it when the installed copy drifts. The unit's `ExecStart` is where bench settings live (`audio.md` §14): the program's
defaults are the figures `station_circuit.md` §8 gives, and what the bench says goes in the unit
file, not into the source. `LimitRTPRIO` and `LimitMEMLOCK` are there so `SCHED_FIFO`
and `mlockall` succeed; without them the program logs and continues, at the cost of
xruns.

The unit also gives the program a state directory, `/var/lib/sbaudio`, and points
`SBAUDIO_WISDOM` at it, so FFTW's plan cache survives restarts. Without it the cache
would default to `~/.cache`, which the unit's `ProtectHome=read-only` makes unwritable,
and every start would pay the slow plan. The log says which happened: `plan from
wisdom`, `wisdom saved`, or `could not save wisdom`.

The prompts are installed by `./release` into the directory the unit's `--wav-dir`
names. A `play/set` for a file not there publishes `missing`.

## Commissioning

`audio.md` §15 is the order, §14 has the levels the installation sets, and §16 those
still at the document's figure. The first two steps need nothing but the
switchboard and a terminal:

1. `mosquitto_sub -v -t 'sbgame/#'` with no game program. Every circuit — stations
   1–22 and 24, trunks 1–8, and nothing under `station/23` — should show
   `peer` empty, `op` off, `optone` ok and `audio_status` online within a second. A
   `deaf` is a wiring fault on that circuit's own strip or D-Sub channel.
2. `sbaudio --dump station/5 10 > clock.csv` with nothing patched. Station 5's own pilot
   should sit in its own bin at a steady level with the neighbouring bins 40 dB or more
   below. Energy in the neighbours that varies slowly means the Digiface and the A32 are
   not locked to each other, which must be fixed at the hardware — or `--window hann`
   adopted, which is the documented fallback and costs sensitivity.

## Reading the code

Start with five comments, in this order:

1. `src/ipc.h` — a picture of the three threads and what passes between them.
2. `src/engine.h` — one 5.3 ms audio period, step by step.
3. `src/vad.h` — a listen's three phases and what each publishes on `listen`.
4. `src/detector.h` — the pilot detector in one paragraph.
5. `src/net.h` — the path of a command in and a result out.

Every function has a header comment. The bracketed tag on each names the thread it
runs on: `[startup]`, `[audio]`, `[analysis]`, `[mqtt]` or `[any]`. That tag answers
most "can this block?" and "does this need a lock?" questions before you have to
ask them. Almost every array is indexed by slot, 1–32, with element 0 unused;
`src/channels.h` explains why.

## Files

```
src/channels.h     the channel plan and the comb; docs/pilot-map.md in code
src/options.*      the command line; there is no configuration file
src/util.*         logging, uptime, dB
src/spsc.h         the lock-free queue both directions use
src/ipc.h          what crosses between the threads
src/dsp.*          sine table, biquads, the elliptic design, the limiter
src/alsa.*         the duplex stream, linked, and the sample conversion
src/wav.*          loading and validating a prompt
src/engine.*       the audio thread: one period, the mixer, files, speech detector
src/monitor.*      the loudspeaker's chain: filters, gate, peer boost, ramp, limiter
src/tones.h, .cpp  the trunk tones
src/cityring.h     the ringback waveform, measured from a recording
src/ringdet.*      ring heard on a circuit
src/vad.*          the speech detector's decisions: floor, window, speech/silence/timeout
src/aec.*          the echo canceller under a circuit's own file
src/rec.*          recording the loudspeaker, and playing a recording back
src/detector.*     the analysis thread: FFT and station_circuit.md §8.7
src/net.*          the MQTT thread: commands in, state out, the failsafes
src/main.cpp       startup order (audio.md 13.1) and shutdown
version.cmake      the commit stamp --version prints
test/              the checks that need no hardware, the probe they drive the
                   engine through, and monitor_check and aec_check
```

The unit file is `host/etc/systemd/system/sbaudio.service`.
