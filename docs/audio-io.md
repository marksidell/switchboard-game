# Audio I/O — channel map, reference levels, bench tools

Status: **measured, partial.** Everything below with a number beside it was measured on
the bench and the date is given. The channel map is complete for the hardware present;
the Ferrofish A32 Pro of the design is not yet in the path (see Devices).

## Devices

The design specifies a Ferrofish A32 Pro behind the RME Digiface USB. As of 2026-09-17
the A32 is **not fitted**: the converter on the bench is a **Behringer ADA8200**, eight
channels of AD/DA on one ADAT port, standing in on the first eight channels. Every level
in this file was measured through it and will change when the A32 arrives — the channel
*map* should not, since both present eight channels per ADAT port.

```
  RME Digiface USB (24306452)   USB 2a39:3f8c, ALSA card 1, hw:1
                                34 playback / 32 capture channels at 48 kHz
                                S32_LE, 24 bits in a 32-bit word
```

Playback has two channels more than capture; those two are the headphone jack.

## Channel map

Zero-based, as the device and the ALSA frame present them:

```
   0 –  7   ADAT port 1, via the ADA8200            8 in / 8 out
   8 – 31   ADAT ports 2–4, nothing connected      24 in / 24 out
  32 – 33   headphone jack                          out only
```

Within ADAT port 1, as wired 2026-09-17:

```
   0 –  5   loopback cables, out to in, for reference measurements
       6    switchboard circuit  (station, or the operator tap — it has been both)
       7    switchboard circuit  (trunk)
```

Channels 6 and 7 have been re-patched several times during bring-up. Any level recorded
against them names the configuration it was taken in.

## Channel numbering — read this before using the tools

The three bench tools do not agree, and the mismatch is deliberate rather than an
oversight:

```
  pilot_loopback_test   -p / -c take ZERO-based first-channel indices
  tone_out              -c takes ONE-based channel numbers
  tone_monitor          -p / -c take ONE-based channel numbers
```

`tone_out` and `tone_monitor` print both conventions on startup — *"channel 34 (0-based
index 33)"* — so the resolved pin is never in doubt. `pilot_loopback_test` reports its
result table one-based while taking its arguments zero-based, which is the trap. The
headphone pair is `-c 33,34` to `tone_out` and indices 32/33 to everything else.

## Measured reference levels

All at 48 kHz, drive −12 dBFS unless stated, through the ADA8200. Taken with
`pilot_loopback_test -D hw:1`, 2026-09-17, plain cable loopback on channels 0–5:

```
  returned level        −28.7 dBFS      (−28.46 to −29.14 across six channels)
  round-trip loss        16.7 dB        DAC → analog → ADC; the ADA8200's gain
                                        structure, not a fault
  noise floor          −103 dBFS        integrated, referenced to a full-scale sine
  pilot-to-noise         74.6 dB
  THD                  −85 to −90 dBc   H2 and H3 only; above that is past Nyquist
  hum (60 Hz family)  −103 to −106 dBFS
  worst crosstalk      −109.6 dBFS      any off-diagonal cell, ≥ 80 dB below wanted
  xruns                     0
```

A channel spread wider than about 1 dB, or a returned level away from −28.7 by more than
a dB or two, means something has changed in the analog path. That is the whole reason
these numbers are written down.

Headphone jack, indices 32/33, confirmed audible at −20 dBFS on 2026-09-17. Nothing else
is known about its gain; it has not been measured.

## The switchboard circuits

Levels here are lower and noisier than the cable channels, and that is expected — the
signal goes out through the ADA8200, through a circuit board and a transformer, and back.

Station↔trunk through a switchboard cord pair, channels 6 and 7, after contact cleaning
(2026-09-16, held over a re-patch the following day):

```
  each circuit's own return   −33.0 to −33.3 dBFS
  cord loss, either direction   5.0 dB and 4.6 dB, reciprocal to 0.4 dB
```

**A cord fault has a signature worth knowing.** The same pair, before cleaning, measured
45–65 dB of loss that *fell* with frequency at a clean 6 dB/octave. That slope is
capacitive coupling — stray capacitance across a contact that is not conducting. A
working cord is flat with frequency. Flat means metal; 6 dB/octave means no metal. Two
afternoons went into learning that, and it is the fastest way to tell a dirty contact
from a wiring error.

Contact cleaner fixed it and held across a day and a re-patch, so the fault was oxidation
rather than worn contacts.

**A differential pair on one end of a winding has a signature too, and it is the
opposite one: nothing at all.** Measured 2026-09-19 on the first trunk board, channel 1
through the ADA8200:

```
  circuit's own pilot back    −110 dBFS, which is the noise floor
  a working circuit           −33 dBFS      (see the figures above)
  a plain cable, same channel −28.6 dBFS    (measured the same afternoon)
  worst over 75 s             −109 dBFS     — no intermittency, just nothing
```

The board had both legs of the receive pair tied together to one end of the transformer
secondary and both legs of the transmit pair to the other. A balanced output then puts
no difference across the winding and a balanced input reads none, so the pilot does not
come back at all. Every wire has continuity, which is why a continuity check passes and
the fault survives one.

Tell it apart from a dead converter or an unplugged cable by the noise floor: a live
input with nothing on it reads about −103 dBFS, and a capture path that is not running
reads −150 or lower, or exact zeros. −110 dBFS with a −103 floor means the path is
alive and carrying no signal.

That leaves three causes for a circuit that returns nothing while every wire rings out.
In the order they cost time to check: a short between pins 2 and 3 at a plug, both legs
of one pair landing on the same end of the winding, and a solder bridge across the
winding itself. Substituting a plain cable for the circuit separates the converter from
everything beyond it in one measurement, and is worth doing first.

## The operator path

Measured 2026-09-17 with channel 6 moved onto the operator tap and channel 7 on a trunk.
Swept 300 Hz–6656 Hz with `tone_out -s` and `tone_monitor`, drift-checked by repeating
1 kHz at the end (closed to 0.3 dB, so the sweep is valid end to end):

```
   500 Hz – 6656 Hz     30.8 – 32.0 dB loss, slope −0.2 to +0.34 dB/octave
   300 Hz               42.1 dB — the path rolls off below 500 Hz
   operator tap's own return   −20.5 dBFS, the hottest circuit in the rig
```

Flat across the voice band at ~31 dB is a working bridging tap: it is meant to be lossy,
because it is deliberately high-impedance so as not to load the talking path.

**The operator's receiver rolls off above about 4 kHz.** A 300 Hz–8 kHz sweep at −6 dBFS
is plainly audible until roughly 4 kHz and then fades. This matters for the pilot design:
the comb occupies 6000 Hz upward (see `pilot-map.md`), so the pilots sit above what the
operator's receiver reproduces and are inherently near-inaudible to the player. Good news
for the design, and expensive to rediscover.

**One unexplained observation, recorded so it is not chased from scratch.** On 2026-09-17
the full eight-tone pilot comb was clearly audible in the operator headset as a fairly
pure tone, for something on the order of an hour, and has never reproduced since —
not with any single pilot, not with two pilots on one circuit, not with the comb on the
cable channels only, and not with the same eight-channel comb an hour later. Nothing was
captured while it was happening, because the time went into narrowing it by ear instead.
**If it returns: record all 32 inputs first** (`arecord -D hw:1 -f S32_LE -r 48000 -c 32
-t raw -d 4`), then investigate. A spectrum taken during the event would settle in one
pass what a dozen listening tests could not.

## Bench tools

Sources in the repo root; each carries its reasoning in its own header comment.

```
  pilot_loopback_test   plays the 8-slot pilot comb on eight outputs while capturing
                        eight inputs, 4096-point FFT per channel, reports which slot
                        each input heard plus a full cross-channel matrix.
                        -l  listen mode: every pilot each input hears, no pass/fail.
                            Use this for bridged circuits — the pass/fail mode judges
                            a channel by its strongest pilot, which is the wrong
                            question once a cord joins two circuits.
                        -S  self-test on a synthetic signal, no hardware needed.

  tone_out              one or more tones on chosen output channels.
                        -c 7,8      two channels;  -c 8,8  two tones on one channel
                        -s lo,hi    repeating logarithmic sweep
                        -y secs     cycle each listed channel alone, in turn

  tone_monitor          drives one channel and logs the level on others once a second,
                        min/max over ten sub-blocks so a contact that makes for a
                        tenth of a second still shows. Built for chasing intermittents.
```

All three use a Hann window for every level reading. An earlier version of
`pilot_loopback_test` read the cross-channel matrix off a rectangular window, which is
leakage-free only while sampling stays perfectly coherent; 0.1 bin of drift throws
−67 dBFS into the neighbouring pilot bin against Hann's −103, and that artefact was
briefly mistaken for real crosstalk.

## Open items

- The Ferrofish A32 Pro is not fitted; every level here is through an ADA8200 and will
  move when it is.
- Headphone output gain unmeasured.
- Nothing is recorded about the monitor bus, which this file is also supposed to cover.
- Channels 8–31 are unconnected, so no ADAT port beyond the first has been exercised.
