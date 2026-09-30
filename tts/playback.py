"""Playing a clip on the Digiface (docs/audio-io.md), for the tools that let
Mark listen: tts/audition and tts/record.

The Digiface is opened by card id, not number: the numbers follow USB
enumeration order and moved on portland (card 1, then card 2). audio.md Rev 2.
Each clip goes into a 34-channel S32_LE frame, silence everywhere but the
channels asked for, handed to aplay. sbaudio holds the device while it runs.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr

DEVICE = "hw:USB24306452"
CHANNELS = 34            # the Digiface's playback count
PHONES = (32, 33)        # zero-based, the headphone jack — one-based 33/34
MAX_CIRCUIT = 32         # one-based; the circuits are 1..32, the jack is beyond them
RATE = 48000


def out_channels(channel: int | None) -> tuple[int, ...]:
    """--channel as the tools take it, one-based like tone_out; None is the
    headphone jack. Raises ValueError outside 1..32."""
    if channel is None:
        return PHONES
    if 1 <= channel <= MAX_CIRCUIT:
        return (channel - 1,)
    raise ValueError(f"--channel {channel} is outside 1..{MAX_CIRCUIT}")


def play(path: Path, device: str, gain_db: float,
         channels: tuple[int, ...] = PHONES) -> None:
    """Send one clip to the given zero-based channels, silence on the rest."""
    audio, rate = sf.read(str(path), always_2d=False, dtype="float64")
    audio = np.asarray(audio)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if rate != RATE:
        audio = soxr.resample(audio, rate, RATE, quality="VHQ")
    audio = audio * (10.0 ** (gain_db / 20.0))
    np.clip(audio, -1.0, 1.0, out=audio)

    frame = np.zeros((len(audio), CHANNELS), dtype=np.int32)
    # S32_LE carrying 24 bits left-justified in the 32-bit word; full scale is
    # the top of the int32 range and the device ignores the low byte.
    samples = (audio * (2 ** 31 - 1)).astype(np.int32)
    for ch in channels:
        frame[:, ch] = samples

    try:
        subprocess.run(
            ["aplay", "-D", device, "-t", "raw", "-f", "S32_LE",
             "-r", str(RATE), "-c", str(CHANNELS), "-q", "-"],
            input=frame.tobytes(), check=True)
    except FileNotFoundError:
        sys.exit("aplay not found: install alsa-utils")
    except subprocess.CalledProcessError as e:
        sys.exit(f"aplay failed ({e.returncode}). Is {device} free — sbaudio holds "
                 f"it while it runs (sudo systemctl stop sbaudio) — and is the "
                 f"Digiface connected? docs/audio-io.md has the device notes.")
