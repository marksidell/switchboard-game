# Pilot map — slot ↔ bin ↔ circuit

Status: **authoritative.** `CLAUDE.md` names this file as the one place the mapping
lives; nothing else in the repo may recompute it inline. The arithmetic is station
§8.2 and the assignment is station §8.3; the channel plan is `audio.md` §2. This file
is the transcription, so that the audio program reads a table rather than a formula it
might get subtly wrong.

## The arithmetic

```
fs          = 48000 Hz
NFFT        = 4096                 rectangular window (see below)
hop         = 2048                 50% overlap → an update every 42.67 ms
bin width   = 48000 / 4096         = 11.71875 Hz
block       = 85.33 ms

pilot_bin(slot) = 512 + 8 × (slot − 1)          slot = 1…32
pilot_hz(slot)  = pilot_bin(slot) × 11.71875
```

Eight bins — 93.75 Hz — between neighbours, everywhere in the comb including across
the station/trunk boundary, so the ±2 and ±3 guard bins used for the noise-floor
estimate are clear of the adjacent pilots.

Every pilot completes an integer number of cycles in 4096 samples, which is the whole
point of snapping the comb to bins: leakage into other bins is zero by construction and
no window function is needed, *provided generation and analysis share one clock*. They
do while the Digiface and the A32 are locked to each other. If they are ever not, the
fallback is station §8.2's — Hann window, sum the three bins around each pilot — and
the programme carries it as `--window hann`.

## The table

Document channel, A32 channel and slot number are all the same number (station §8.6);
the ALSA frame index is one less. Slots 23 and 24 have no pilot (station Rev 3.40,
`audio.md` Rev 7 §2): 23 is the operator tap, which transmits the operator tone at bin
768 instead, and 24 is the A32 output feeding the audience loudspeaker, whose receive
side is not fitted. Bins 688 and 696 are never generated and never match.

| Slot | FFT bin | Frequency (Hz) | Circuit | A32 / doc channel | ALSA index |
| ---: | ---: | ---: | --- | ---: | ---: |
| 1 | 512 | 6000.00 | station 1 | 1 | 0 |
| 2 | 520 | 6093.75 | station 2 | 2 | 1 |
| 3 | 528 | 6187.50 | station 3 | 3 | 2 |
| 4 | 536 | 6281.25 | station 4 | 4 | 3 |
| 5 | 544 | 6375.00 | station 5 | 5 | 4 |
| 6 | 552 | 6468.75 | station 6 | 6 | 5 |
| 7 | 560 | 6562.50 | station 7 | 7 | 6 |
| 8 | 568 | 6656.25 | station 8 | 8 | 7 |
| 9 | 576 | 6750.00 | station 9 | 9 | 8 |
| 10 | 584 | 6843.75 | station 10 | 10 | 9 |
| 11 | 592 | 6937.50 | station 11 | 11 | 10 |
| 12 | 600 | 7031.25 | station 12 | 12 | 11 |
| 13 | 608 | 7125.00 | station 13 | 13 | 12 |
| 14 | 616 | 7218.75 | station 14 | 14 | 13 |
| 15 | 624 | 7312.50 | station 15 | 15 | 14 |
| 16 | 632 | 7406.25 | station 16 | 16 | 15 |
| 17 | 640 | 7500.00 | station 17 | 17 | 16 |
| 18 | 648 | 7593.75 | station 18 | 18 | 17 |
| 19 | 656 | 7687.50 | station 19 | 19 | 18 |
| 20 | 664 | 7781.25 | station 20 | 20 | 19 |
| 21 | 672 | 7875.00 | station 21 | 21 | 20 |
| 22 | 680 | 7968.75 | station 22 | 22 | 21 |
| 23 | 688 | 8062.50 | — operator tap, not generated | 23 | 22 |
| 24 | 696 | 8156.25 | — audience monitor out, not generated | 24 | 23 |
| 25 | 704 | 8250.00 | trunk 1 | 25 | 24 |
| 26 | 712 | 8343.75 | trunk 2 | 26 | 25 |
| 27 | 720 | 8437.50 | trunk 3 | 27 | 26 |
| 28 | 728 | 8531.25 | trunk 4 | 28 | 27 |
| 29 | 736 | 8625.00 | trunk 5 | 29 | 28 |
| 30 | 744 | 8718.75 | trunk 6 | 30 | 29 |
| 31 | 752 | 8812.50 | trunk 7 | 31 | 30 |
| 32 | 760 | 8906.25 | trunk 8 | 32 | 31 |

Outside the comb:

| Purpose | FFT bin | Frequency (Hz) | Channel | Notes |
| --- | ---: | ---: | ---: | --- |
| Operator tone | 768 | 9000.00 | 23 (ALSA 22) | Transmitted on the tap strip's channel, station §8.3 and §8.8. Every circuit checks it alongside the comb; hearing it means the operator is bridged to that circuit. It is not a comb slot and never counts toward the zero-or-one rule. |
| Audience monitor | — | — | 24 (ALSA 23), or 33, 34 | A32 output 24 to the loudspeaker amplifier (station §7.9.8). `--monitor-ch` may send it to the Digiface's analog pair, 33 and 34, instead — the route of `audio.md` Rev 1 to Rev 6, kept as the fallback. Playback only; no pilot. Channels not carrying it are silent. |

Bins 776 and upward are reserved (station §8.3): the deferred per-cord tone extension
of generator §15.6 would take them. If anything else wants a slot, take it from below
bin 512.

## Detector constants

```
guard offsets   ±2, ±3 bins       median of the four is the local noise floor
MARGIN_DB       20.0              a bin counts as present at that much above its floor
PEER_WINDOW_DB  40.0              and, for a comb pilot, no more than this below the own pilot
OP_WINDOW_DB    20.0              and, for bin 768, no more than this below the own pilot
own slot        excluded from the peer search; its level is the "deaf" health check
```

`MARGIN_DB` is a bench setting (station §8.7, `audio.md` §15 step 6) and is the
`--margin-db` option; 20 dB is the starting value and what this table records.
`PEER_WINDOW_DB` (station Rev 3.46) is the same kind of setting, `--peer-window-db`; 40 dB
is its starting value, chosen against the trunk board's strip-to-strip crosstalk, 72 dB
or more under the own pilot, and to be confirmed through the switchboard. `OP_WINDOW_DB`
(Rev 3.47), `--op-window-db`, starts at 20 dB, against the tap's leak, 46 dB under the
own pilot on station 22.

## How many stations there are, and why it has changed twice

Twenty-two, as of station Rev 3.40 and `audio.md` Rev 7 (2026-09-23). Station board 3
carries eight strips; the last two are not stations:

| Strip | A32 channel | What it is |
| --- | --- | --- |
| 1–6 | 17–22 | stations 17–22 |
| 7 | 23 | operator tap — transmits the 9 kHz operator tone, receives the monitor source |
| 8 | 24 | audience monitor — the output feeds the loudspeaker amplifier; nothing is fitted on the receive side |

The comb still has 32 slots and the formula is unchanged; slots 23 and 24 simply have
no circuit behind them, and `sbgame/station/23/…` and `…/24/…` are topics that never
appear.

It was 24 stations until station Rev 3.35, when the last strip became the operator tap,
and 23 until Rev 3.40, when the tap moved down one strip to free channel 24 for the
monitor. The monitor was on the Digiface's own analog output, playback 33 and 34, up to
`audio.md` Rev 6; that route survives as `--monitor-ch 33,34`. Anything in this repo
still saying 23 or 24 stations is stale.
