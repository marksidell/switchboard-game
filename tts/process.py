"""Local band-limiting and delivery (tts_task.md 7).

Raw model output in, files the audio program will accept out. No GPU, no
network, no broker: this is the step that gets tuned and rerun, so it is kept
away from anything that needs a rented machine.

The order of operations is fixed by the task document and is not arbitrary —
trimming happens at the original rate, the band-limiting happens at 16kHz
where the elliptic low-pass is steep in relative terms, and only then is the
result carried up to the 48kHz the program loads.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr
from scipy import signal

from tts.script import DEFAULT_SCRIPT, Script, ScriptError, load, name_problem

WORK_RATE = 16000          # station 8.8: speech is authored here
DELIVERY_RATE = 48000      # audio.md 7.2: anything else is refused on load
SUBTYPE = "PCM_24"

HIGHPASS_HZ = 300.0        # telephone band, low edge
PASSBAND_HZ = 3400.0       # telephone band, high edge
STOPBAND_HZ = 4500.0
STOPBAND_DB = 70.0
PASSBAND_RIPPLE_DB = 0.5

KEEP_SILENCE_S = 0.150     # left at each end after trimming
TRIM_FLOOR_DB = 40.0       # a frame this far below the loudest is silence
FRAME_S = 0.010

TARGET_RMS_DBFS = -20.0
PEAK_CEILING_DBFS = -3.0

# audio.md 5.3 / 7.2: the program warns above this; here it is a refusal.
HF_LIMIT_DBFS = -60.0
HF_CORNER_HZ = 5500.0
MAX_SECONDS = 120.0


@dataclass
class Result:
    src: Path
    dst: Path | None
    ok: bool
    note: str
    in_rate: int = 0
    seconds: float = 0.0
    hf_db: float = float("-inf")
    hf_program_db: float = float("-inf")
    rms_db: float = float("-inf")
    peak_db: float = float("-inf")


def db(x: float) -> float:
    return 20.0 * math.log10(x) if x > 0.0 else float("-inf")


# ---------------------------------------------------------------- HF measure
#
# audio/src/wav.cpp measures the energy above 5.5kHz with two cascaded RBJ
# Butterworth biquads rather than a transform, and references the result to a
# full-scale sine. Reproduced here coefficient for coefficient so that what
# this pipeline refuses is exactly what the program would warn about; a check
# that disagreed with the program would be worse than no check.
def _rbj_highpass(fc: float, fs: float) -> tuple[np.ndarray, np.ndarray]:
    w0 = 2.0 * math.pi * fc / fs
    c, s = math.cos(w0), math.sin(w0)
    al = s / (2.0 * (1.0 / math.sqrt(2.0)))
    b = np.array([(1.0 + c) / 2.0, -(1.0 + c), (1.0 + c) / 2.0])
    a = np.array([1.0 + al, -2.0 * c, 1.0 - al])
    return b / a[0], a / a[0]


def hf_energy_program_db(x: np.ndarray, rate: float) -> float:
    """What sbaudio will report for this file. See the note below."""
    if x.size == 0:
        return float("-inf")
    b, a = _rbj_highpass(HF_CORNER_HZ, rate)
    y = signal.lfilter(b, a, signal.lfilter(b, a, x.astype(np.float64)))
    return db(float(np.sqrt(np.mean(y * y))) * math.sqrt(2.0))


# That biquad pair is too shallow at 48kHz to be used as a gate. Its own
# response, cascaded, measured at the rate the delivered file is in:
#
#       1000Hz   2000Hz   2600Hz   3000Hz   3400Hz   4500Hz   5500Hz
#  16k  -77.9    -52.4    -42.0    -35.9    -30.3    -16.3     -6.0
#  48k  -60.7    -36.6    -27.6    -22.8    -18.7    -10.6     -6.0
#
# At 48kHz it passes the top of the telephone band at only 19dB down, so it
# reports wanted speech as if it were energy above 5.5kHz. Measured on
# correctly band-limited speech at -20dBFS RMS with nothing whatever above
# 5.5kHz (true content there is around -200dBFS), it reads -71.6dBFS for a
# -12dB/octave spectrum but -45.7dBFS for a flat one: the reading tracks how
# bright the voice is, not what is above the corner.
#
# So the gate here is a transform, which answers the question actually asked
# in audio.md 5.3 — is there anything up there for the detector to mistake for
# a pilot. The program's number is computed too and reported, because a file
# that passes the gate can still make sbaudio log a content warning, and it is
# better to know that here than to wonder at commissioning.
def hf_energy_db(x: np.ndarray, rate: float) -> float:
    """Energy above 5.5kHz, referenced to a full-scale sine (docs/audio-io.md)."""
    if x.size == 0:
        return float("-inf")
    x = x.astype(np.float64)
    w = np.blackman(len(x))
    sp = np.abs(np.fft.rfft(x * w)) ** 2
    freq = np.fft.rfftfreq(len(x), 1.0 / rate)
    total = float(sp.sum())
    if total <= 0.0:
        return float("-inf")
    fraction = float(sp[freq > HF_CORNER_HZ].sum()) / total
    if fraction <= 0.0:
        return float("-inf")
    return db(float(np.sqrt(np.mean(x * x))) * math.sqrt(2.0)) + 10.0 * math.log10(fraction)


# ------------------------------------------------------------------- stages
def to_mono(x: np.ndarray) -> np.ndarray:
    return x if x.ndim == 1 else x.mean(axis=1)


def _voiced_mask(x: np.ndarray, rate: int) -> np.ndarray:
    """Per-frame boolean: is this frame speech rather than silence."""
    n = max(1, int(rate * FRAME_S))
    frames = x[: len(x) // n * n].reshape(-1, n)
    if frames.size == 0:
        return np.ones(1, dtype=bool)
    rms = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
    loudest = rms.max()
    if loudest <= 0.0:
        return np.zeros(len(rms), dtype=bool)
    return rms > loudest * (10.0 ** (-TRIM_FLOOR_DB / 20.0))


def trim(x: np.ndarray, rate: int) -> np.ndarray:
    """Cut leading and trailing silence, leaving KEEP_SILENCE_S at each end."""
    mask = _voiced_mask(x, rate)
    if not mask.any():
        return x
    n = max(1, int(rate * FRAME_S))
    keep = int(rate * KEEP_SILENCE_S)
    first = int(np.argmax(mask)) * n
    last = (len(mask) - int(np.argmax(mask[::-1]))) * n
    return x[max(0, first - keep): min(len(x), last + keep)]


def band_limit(x: np.ndarray, rate: int) -> np.ndarray:
    """300-3400Hz. The steep top edge is what clears 5.5kHz upward."""
    hp = signal.butter(2, HIGHPASS_HZ, btype="highpass", fs=rate, output="sos")
    order, wn = signal.ellipord(PASSBAND_HZ, STOPBAND_HZ,
                                PASSBAND_RIPPLE_DB, STOPBAND_DB, fs=rate)
    lp = signal.ellip(order, PASSBAND_RIPPLE_DB, STOPBAND_DB, wn,
                      btype="lowpass", fs=rate, output="sos")
    y = signal.sosfiltfilt(hp, x)
    return signal.sosfiltfilt(lp, y)


def level(x: np.ndarray, rate: int, target_db: float,
          ceiling_db: float) -> tuple[np.ndarray, float, float]:
    """Match the speech level across lines, then obey the peak ceiling."""
    mask = _voiced_mask(x, rate)
    n = max(1, int(rate * FRAME_S))
    voiced = x[: len(mask) * n].reshape(-1, n)[mask].ravel() if mask.any() else x
    rms = float(np.sqrt(np.mean(voiced.astype(np.float64) ** 2)))
    if rms <= 0.0:
        return x, float("-inf"), float("-inf")
    y = x * (10.0 ** (target_db / 20.0) / rms)
    peak = float(np.max(np.abs(y)))
    ceiling = 10.0 ** (ceiling_db / 20.0)
    if peak > ceiling:
        y *= ceiling / peak
    return y, db(float(np.sqrt(np.mean((y[: len(mask) * n].reshape(-1, n)[mask].ravel()
                                        if mask.any() else y) ** 2)))), db(float(np.max(np.abs(y))))


# -------------------------------------------------------------------- driver
def process_file(src: Path, dst: Path, target_db: float = TARGET_RMS_DBFS,
                 ceiling_db: float = PEAK_CEILING_DBFS) -> Result:
    why = name_problem(dst.stem)
    if why is not None:
        return Result(src, None, False, f"name {dst.stem!r} is not usable: {why}")

    x, in_rate = sf.read(str(src), always_2d=False, dtype="float64")
    x = to_mono(np.asarray(x))
    if x.size == 0:
        return Result(src, None, False, "empty file", in_rate)

    x = trim(x, in_rate)
    x = soxr.resample(x, in_rate, WORK_RATE, quality="VHQ")
    x = band_limit(x, WORK_RATE)
    x, rms_db, peak_db = level(x, WORK_RATE, target_db, ceiling_db)
    y = soxr.resample(x, WORK_RATE, DELIVERY_RATE, quality="VHQ")

    seconds = len(y) / DELIVERY_RATE
    if seconds > MAX_SECONDS:
        return Result(src, None, False, f"{seconds:.1f}s exceeds the {MAX_SECONDS:.0f}s cap",
                      in_rate, seconds)

    dst.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(dst), y, DELIVERY_RATE, subtype=SUBTYPE)

    # Check what was actually written, not what was about to be.
    back, rate = sf.read(str(dst), always_2d=True, dtype="float64")
    problems: list[str] = []
    if rate != DELIVERY_RATE:
        problems.append(f"wrote {rate}Hz, not {DELIVERY_RATE}")
    if back.shape[1] != 1:
        problems.append(f"wrote {back.shape[1]} channels, not 1")
    hf_db = hf_energy_db(back[:, 0], rate)
    hf_prog = hf_energy_program_db(back[:, 0], rate)
    if hf_db > HF_LIMIT_DBFS:
        problems.append(f"{hf_db:.1f} dBFS above 5.5kHz, limit is {HF_LIMIT_DBFS:.0f}")
    if problems:
        dst.unlink(missing_ok=True)
        return Result(src, None, False, "; ".join(problems), in_rate, seconds, hf_db, hf_prog)

    return Result(src, dst, True, "", in_rate, seconds, hf_db, hf_prog, rms_db, peak_db)


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Band-limit raw TTS output into deliverable wavs.")
    p.add_argument("--raw", type=Path, default=Path("tts/raw"), help="input directory")
    p.add_argument("--recorded", type=Path, default=Path("tts/recorded"),
                   help="performers' takes, which win over --raw (tts_task.md 6.4)")
    p.add_argument("--out", type=Path, default=Path("wav"), help="output directory")
    p.add_argument("--script", type=Path, default=DEFAULT_SCRIPT)
    p.add_argument("--rms", type=float, default=TARGET_RMS_DBFS, help="target speech level, dBFS")
    p.add_argument("--peak", type=float, default=PEAK_CEILING_DBFS, help="peak ceiling, dBFS")
    p.add_argument("--only", default="", help="comma-separated base names to process")
    p.add_argument("--no-script", action="store_true",
                   help="process whatever is in --raw without checking it against the script")
    p.add_argument("--public", action="store_true",
                   help="leave private/ alone (tts_task.md 5.1)")
    args = p.parse_args(argv)

    # The private voices first: private/raw to private/wav. A name in --only
    # that has a private file means that one; --public means the other.
    private_rc = 0
    wanted_here = {s for s in args.only.split(",") if s}
    private_raw = Path("private/raw")
    if not args.public and args.raw != private_raw and private_raw.is_dir():
        have = {s.stem for s in private_raw.glob("*.wav")}
        mine = wanted_here & have if wanted_here else have
        if mine:
            private_rc = main(["--raw", str(private_raw), "--recorded", "private/recorded",
                               "--out", "private/wav", "--no-script",
                               "--only", ",".join(sorted(mine))])
        if wanted_here:
            args.only = ",".join(sorted(wanted_here - mine))
            if not args.only:
                return private_rc

    script: Script | None = None
    if not args.no_script:
        try:
            script = load(args.script)
        except ScriptError as e:
            print(f"{e.path}: {len(e.failures)} problem(s)", file=sys.stderr)
            for f in e.failures:
                print(f"  {f}", file=sys.stderr)
            return 1

    wanted = {s for s in args.only.split(",") if s}
    # §6.4: a performer's take is processed in place of a file of the same name.
    by_name = {s.stem: s for s in args.raw.glob("*.wav")}
    by_name.update({s.stem: s for s in args.recorded.glob("*.wav")})
    sources = sorted(by_name.values(), key=lambda s: s.stem)
    if wanted:
        sources = [s for s in sources if s.stem in wanted]
    if not sources:
        print(f"no input files in {args.raw}", file=sys.stderr)
        return 1

    results = [process_file(s, args.out / f"{s.stem}.wav", args.rms, args.peak) for s in sources]
    for r in sorted(results, key=lambda r: r.src.name):
        if r.ok:
            warn = "  <- sbaudio will warn" if r.hf_program_db > HF_LIMIT_DBFS else ""
            print(f"{r.src.stem:<20} {r.in_rate:>6}Hz  {r.seconds:5.2f}s  "
                  f"rms {r.rms_db:6.1f}  peak {r.peak_db:6.1f}  "
                  f"hf {r.hf_db:7.1f}  (7.2 meter {r.hf_program_db:6.1f}){warn}")
        else:
            print(f"{r.src.stem:<20} FAILED: {r.note}", file=sys.stderr)

    failed = [r for r in results if not r.ok]
    noisy = [r for r in results if r.ok and r.hf_program_db > HF_LIMIT_DBFS]
    rates = sorted({r.in_rate for r in results if r.in_rate})
    print(f"\n{len(results) - len(failed)}/{len(results)} written to {args.out}/"
          f"   model output rate: {', '.join(f'{r}Hz' for r in rates) or 'unknown'}")

    if noisy:
        print(f"{len(noisy)} file(s) pass the transform gate but read above "
              f"{HF_LIMIT_DBFS:.0f} dBFS on audio.md 7.2's biquad meter, so sbaudio will "
              f"log a content warning for them on load. See the note in process.py.")

    if script is not None:
        # cue.* are tones made by tts/cue, not utterances (game_control.md §9.2).
        delivered = {p.stem for p in args.out.glob("*.wav") if not p.stem.startswith("cue.")}
        expected = {u.name for u in script.utterances}
        missing = sorted(expected - delivered)
        orphan = sorted(delivered - expected)
        if missing:
            print(f"no delivered file for {len(missing)}: {', '.join(missing)}")
        from tts.recorded import status as recorded_status
        pending = [l for l in recorded_status(script, recorded=args.recorded) if l.state != "ok"]
        if pending:
            print(f"recorded parts: {len(pending)} line(s) still to record or re-take, "
                  f"playing their earlier file until then — tts/record --status")
        if orphan:
            print(f"in {args.out}/ but in no scene, {len(orphan)}: {', '.join(orphan)}")
        print(f"{len(delivered)} delivered, {len(expected)} utterances in the script")
        if missing or orphan or failed:
            return 1
    return 1 if failed or private_rc else 0


if __name__ == "__main__":
    raise SystemExit(main())
