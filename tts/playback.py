"""Playing audio on the Digiface (docs/audio-io.md), for the tools that play
the lines to a listener: tts/audition, tts/record and tts/scenes.

The Digiface is opened by ALSA card id, not number: the numbers follow USB
enumeration order and move between boots. The id is built from the unit's
serial number, so it is found by the card's name in /proc/asound/cards, or
given with $SBGAME_DIGIFACE or a tool's --device.

Audio goes into a 34-channel S32_LE frame, silence everywhere but the
channels asked for, handed to aplay. sbaudio holds the device while it runs.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr

DEVICE_ENV = "SBGAME_DIGIFACE"
CARDS = Path("/proc/asound/cards")
CHANNELS = 34            # the Digiface's playback count
PHONES = (32, 33)        # zero-based, the headphone jack — one-based 33/34
MAX_CIRCUIT = 32         # one-based; the circuits are 1..32, the jack is beyond them
RATE = 48000

# " 1 [USB12345678     ]: USB-Audio - Digiface USB (12345678)": index, id, rest.
_CARD = re.compile(r"^\s*\d+\s+\[(\S+)\s*\]:\s*(.*)$")


def find_digiface(cards: Path = CARDS) -> str | None:
    """"hw:<id>" of the first card whose description names the Digiface, or None."""
    try:
        text = cards.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = _CARD.match(line)
        if m is None:
            continue
        # Each card is two lines: the id and driver, then its long name.
        described = m.group(2) + " " + (lines[i + 1] if i + 1 < len(lines) else "")
        if "digiface" in described.lower():
            return f"hw:{m.group(1)}"
    return None


def digiface(given: str | None = None) -> str:
    """The playback device: `given` (a tool's --device), else $SBGAME_DIGIFACE,
    else the Digiface found in /proc/asound/cards. Exits if there is none."""
    found = given or os.environ.get(DEVICE_ENV) or find_digiface()
    if not found:
        sys.exit(f"no Digiface in {CARDS}: is it connected? Or name the ALSA "
                 f"device with --device or ${DEVICE_ENV} (hw:<card id>).")
    return found


def out_channels(channel: int | None) -> tuple[int, ...]:
    """--channel as the tools take it, one-based like tone_out; None is the
    headphone jack. Raises ValueError outside 1..32."""
    if channel is None:
        return PHONES
    if 1 <= channel <= MAX_CIRCUIT:
        return (channel - 1,)
    raise ValueError(f"--channel {channel} is outside 1..{MAX_CIRCUIT}")


def read_mono(path: Path) -> np.ndarray:
    """A sound file as mono float64 at 48kHz."""
    audio, rate = sf.read(str(path), always_2d=False, dtype="float64")
    audio = np.asarray(audio)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if rate != RATE:
        audio = soxr.resample(audio, rate, RATE, quality="VHQ")
    return audio


def send(audio: np.ndarray, device: str, gain_db: float,
         channels: tuple[int, ...] = PHONES) -> None:
    """Play mono 48kHz audio on the given zero-based channels, silence on the
    rest. A Ctrl-C that kills aplay is raised as KeyboardInterrupt."""
    audio = np.clip(audio * (10.0 ** (gain_db / 20.0)), -1.0, 1.0)
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
        if e.returncode < 0:
            raise KeyboardInterrupt from None
        sys.exit(f"aplay failed ({e.returncode}). Is {device} free — sbaudio holds "
                 f"it while it runs (sudo systemctl stop sbaudio) — and is the "
                 f"Digiface connected? docs/audio-io.md has the device notes.")


def play(path: Path, device: str, gain_db: float,
         channels: tuple[int, ...] = PHONES) -> None:
    """Send one clip to the given zero-based channels, silence on the rest."""
    send(read_mono(path), device, gain_db, channels)
