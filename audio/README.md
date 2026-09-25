# `sbaudio` — the audio program

C++17, one binary. Specified by `docs/audio.md`, which is the authority for
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

They share two lock-free queues and nothing else. Nothing allocates, logs, locks or
touches a file in the audio thread.

## Build

```
sudo apt install cmake pkg-config libasound2-dev libfftw3-dev libmosquitto-dev libsndfile1-dev
cmake -S audio -B audio/build -DCMAKE_BUILD_TYPE=Release
cmake --build audio/build -j
ctest --test-dir audio/build --output-on-failure
```

`sbaudio_test` needs no hardware and no broker. It checks the pilot map against
`docs/pilot-map.md`, the monitor low-pass against station §8.8's 70 dB at 6000 Hz and
the content check's high-pass against the telephone band it has to ignore —
which `audio.md` §10.1 asks for by name, because the lowest pilot sits exactly there —
and the detector against a synthetic block built with the same wavetable expression the
engine renders pilots with.

## Run

```
./audio/build/sbaudio --card USB24306452 --broker localhost:1883 \
    --mqtt-user sbgame --mqtt-pass-file /etc/sbaudio/mqtt.pass --wav-dir wav
```

`--help` lists every option; they are `audio.md` §14's list exactly. `--card` is
required and has no default: it is the id in the second column of `/proc/asound/cards`,
which `snd-usb-audio` derives from the device's serial number — `USB24306452` for the
Digiface on portland. Prefer `--mqtt-pass-file` to `--mqtt-pass`: a password in
`ExecStart` is in every `ps` listing on the host.

The channel map is `audio.md` §2 and `docs/pilot-map.md`: stations on document channels
1–22, the operator tap on 23, the audience monitor out of 24 — the A32 output wired to
the loudspeaker amplifier — and trunks on 25–32. `--monitor-ch 33,34` sends the monitor
to the Digiface's own analog pair instead, which is what Rev 1 to Rev 6 did and is the
fallback if the A32 output proves unsuitable; those channels are silent otherwise.
Capture channel 24 is read by nothing. The map in use is printed at startup, beside the
negotiated ALSA parameters, so a wiring check can be made from the journal.

Without hardware, an ALSA loopback card is enough to exercise everything but the
converters:

```
sudo modprobe snd-aloop pcm_substreams=1
./audio/build/sbaudio --card Loopback --no-realtime --broker localhost:1883
```

Every circuit then reads `deaf`, which is correct — nothing is writing the other side of
the loopback — and every command, echo, failsafe and shutdown path works normally.

## As a service

```
sudo install -m 755 audio/build/sbaudio /usr/local/bin/sbaudio
sudo install -d -m 755 /etc/sbaudio
printf '%s\n' 'the-broker-password' | sudo tee /etc/sbaudio/mqtt.pass > /dev/null
sudo chmod 640 /etc/sbaudio/mqtt.pass && sudo chown root:sidell /etc/sbaudio/mqtt.pass
sudo cp audio/systemd/sbaudio.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sbaudio
journalctl -u sbaudio -f
```

The unit's `ExecStart` is where bench settings live (`audio.md` §14): the program's
defaults are the figures station §8 gives, and what the bench says goes in the unit
file, not into the source. `LimitRTPRIO` and `LimitMEMLOCK` are there so `SCHED_FIFO`
and `mlockall` succeed; without them the program logs and continues, at the cost of
xruns.

The unit also gives the program a state directory, `/var/lib/sbaudio`, and points
`SBAUDIO_WISDOM` at it, so FFTW's plan cache survives restarts. Without it the cache
would default to `~/.cache`, which the unit's `ProtectHome=read-only` makes unwritable,
and every start would pay the slow plan. The log says which happened: `plan from
wisdom`, `wisdom saved`, or `could not save wisdom`.

The wav directory does not exist yet — no content is authored. Create
`/home/sidell/s/sbgame/wav` before the first `play/set`, or every one of them will publish
`missing`.

## Commissioning

`audio.md` §15 is the order, and none of it has been done: every level here is the
document's figure and not a measurement. The first two steps need nothing but the
switchboard and a terminal:

1. `mosquitto_sub -v -t 'sbgame/#'` with no game program. Every circuit — stations
   1–22, trunks 1–8, and nothing under `station/23` or `station/24` — should show
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
src/engine.*       the audio thread: mixer, tones, files, speech detector, monitor
src/vad.*          the speech detector's decisions: floor, window, speech/silence/timeout
src/detector.*     the analysis thread: FFT and station 8.7
src/net.*          the MQTT thread: commands in, state out, the failsafes
src/main.cpp       startup order (audio.md 13.1) and shutdown
test/              the checks that need no hardware
systemd/           the unit file
```
