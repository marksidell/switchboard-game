"""The ring cue (game_control.md §6.6, Rev 51).

While any station reports ring (`station/<n>/ring`, ring voltage arriving from
the switchboard), the audience loudspeaker plays a steady ringback tone, so the
room hears the operator ringing and the tone follows her ringing key. It is a
file on the monitor (audio.md §10.4), `cue.ringback`, rendered by `tts/cue`.

The monitor plays one file at a time, and that file is otherwise the tutor's
voice. She comes first. The cue starts only when the monitor is free — at the
ring, or as soon as she finishes or is cut short — and she replaces it if she
begins during it, which the audio program reports by going straight to her
file's name (audio.md §7.4). When ring ends the cue is stopped only if it is
still what the monitor is playing. A cue that runs to its end while ring
continues starts again.
"""

from __future__ import annotations

import logging
import re

from .board import Board, Offline
from .link import Hw

log = logging.getLogger("cue")

CUE = "cue.ringback"
MONITOR = "audio/monitor"
PLAY = f"{MONITOR}/play"
_RING = re.compile(r"station/\d+/ring$")


class RingCue:
    def __init__(self, b: Board, hw: Hw) -> None:
        self.b, self.hw = b, hw
        self.ringing: set[str] = set()
        self.asked = False       # play/set sent, its echo not yet seen
        self.playing = False     # the monitor's play topic has shown the cue
        self.broken = False      # the file is missing: give up until restart
        self.stale = False       # stopped before its echo: that echo is not a new cue

    async def run(self) -> None:
        """For the life of the program."""
        async for ch in self.b.watch():
            if _RING.match(ch.key):
                if ch.new == "on":
                    self.ringing.add(ch.key)
                else:
                    self.ringing.discard(ch.key)
            elif ch.key == PLAY:
                self._seen(ch.new)
            else:
                continue
            try:
                await self._step()
            except Offline as e:
                log.info("ring cue: %s", e)

    def _seen(self, now: str) -> None:
        if now == CUE and self.stale:
            self.stale = False
        elif now == CUE:
            self.asked, self.playing = False, True
        elif self.asked and now == "missing":
            log.warning("ring cue: %s.wav is missing in the audio program's wav dir; off", CUE)
            self.asked, self.broken = False, True
        elif self.asked and now in ("", "pending"):
            pass                 # our echo not here yet
        else:
            # Ended (""), or replaced by her (another name): not ours now.
            self.asked = self.playing = False

    async def _step(self) -> None:
        if self.broken:
            return
        ours = self.asked or self.playing
        if self.ringing and not ours:
            if self.b.get(PLAY) in ("", "missing"):      # free: never over her
                self.asked, self.stale = True, False
                await self.hw.play(MONITOR, CUE)
        elif not self.ringing and ours:
            self.stale = self.asked
            self.asked = self.playing = False
            if self.b.get(PLAY) in ("", CUE):            # not hers, if she began
                await self.hw.stop(MONITOR)
