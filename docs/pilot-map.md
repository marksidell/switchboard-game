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
the ALSA frame index is one less. Slot 24 is the operator tap strip, which has no
pilot of its own — it transmits the operator tone at bin 768 instead — so bin 696 is
never generated and never matches (station §7.9.6, `audio.md` §2).

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
| 23 | 688 | 8062.50 | station 23 | 23 | 22 |
| 24 | 696 | 8156.25 | — operator tap, not generated | 24 | 23 |
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
| Operator tone | 768 | 9000.00 | 24 (ALSA 23) | Transmitted on the tap strip's channel, station §8.3 and §8.8. Every circuit checks it alongside the comb; hearing it means the operator is bridged to that circuit. It is not a comb slot and never counts toward the zero-or-one rule. |
| Audience monitor | — | — | 33, 34 (ALSA 32, 33) | Digiface analog out, station §8.8. Playback only; no pilot. |

Bins 776 and upward are reserved (station §8.3): the deferred per-cord tone extension
of generator §15.6 would take them. If anything else wants a slot, take it from below
bin 512.

## Detector constants

```
guard offsets   ±2, ±3 bins       median of the four is the local noise floor
MARGIN_DB       20.0              a bin counts as present at that much above its floor
own slot        excluded from the peer search; its level is the "deaf" health check
```

`MARGIN_DB` is a bench setting (station §8.7, `audio.md` §15 step 6) and is the
`--margin-db` option; 20 dB is the starting value and what this table records.

## Station 24 and the count of stations

`CLAUDE.md`'s system context says 24 stations. Station Rev 3.35, `mqtt.md` Rev 3 and
`audio.md` Rev 1 all say 23: the last strip, station 24, is the operator tap (station
§7.9.6) and has no relay, no ring detector and no pilot. The comb still has 32 slots
and the formula is unchanged — slot 24 simply has no circuit behind it. There is no
`sbgame/station/24/…` topic of any kind.
