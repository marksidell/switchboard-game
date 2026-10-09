"""Tutor mode (game_control.md §4.9, Rev 29).

A senior operator's voice on the loudspeaker talks a new player through each
call. The flows call `Tutor.say()` at each step, and wait for her to finish:
the loudspeaker is in the room with the operator's microphone, so nothing the
game listens for may overlap her (§4.9). Every listen in tutor mode is
therefore preceded by a line of hers, and `say()` is what silences any line
still repeating from the step before.

Her lines are files on the monitor (`audio/monitor/play/set`, audio.md §10.4),
named tutor.<key> as script.yml's tutor: renders them.

A prompt given with `until` is said again after REPEAT seconds while the
condition stays false, at most REPEATS times, in the background, so a player
who has not found the jack hears it again without the call waiting on her.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

from .board import Board
from .link import Hw
from .scenes import _quietly, say
from .script_data import Speech

log = logging.getLogger("tutor")

MONITOR = "audio/monitor"      # its play/set and play (audio.md §10.4)
REPEAT = 20.0                  # s without progress before a prompt is said again
REPEATS = 2                    # times a prompt is said again, at most
NO_LIMIT = 3600.0              # s, for the timeouts tutor mode lifts (§4.9)


class Tutor:
    def __init__(self, board: Board, hw: Hw, lines: dict[str, Speech]) -> None:
        self.b = board
        self.hw = hw
        self.lines = lines
        self.active = True         # cleared when tutor mode is switched off mid-call
        self._again: asyncio.Task | None = None

    def has(self, key: str) -> bool:
        return key in self.lines

    def say_key(self, sp: Speech, request: bool) -> str:
        """What she prompts before the operator speaks ahead of `sp` (§4.7)."""
        if sp.operator and f"say-{sp.operator}" in self.lines:
            return f"say-{sp.operator}"
        return "greet" if request else "respond"

    async def say(self, key: str, *, until: Callable[[Board], object] | None = None,
                  abort_if=None) -> None:
        """Say one line and return when it has finished.

        With `until`, nothing is said if it is already true, and the line is
        said again in the background while it stays false.
        """
        await self.hush()
        if not self.active:
            return
        sp = self.lines.get(key)
        if sp is None:
            log.warning("no tutor line %s", key)
            return
        if until is not None and until(self.b):
            return
        await say(self.b, self.hw, MONITOR, sp.name, sp.seconds, abort_if=abort_if)
        if until is not None:
            self._again = asyncio.create_task(self._repeat(sp, until),
                                              name=f"tutor-{key}")

    async def _repeat(self, sp: Speech, until) -> None:
        try:
            for _ in range(REPEATS):
                try:
                    await self.b.wait_until(until, REPEAT)
                    return
                except TimeoutError:
                    pass
                if not self.active:
                    return
                await say(self.b, self.hw, MONITOR, sp.name, sp.seconds)
        except asyncio.CancelledError:
            raise
        except Exception as e:          # Offline, mostly: the call handles that
            log.info("tutor repeat of %s ended: %s", sp.name, e)

    async def hush(self) -> None:
        """Stop a line that is repeating, mid-word if need be."""
        t, self._again = self._again, None
        if t is not None and not t.done():
            t.cancel()                  # say() stops the file as it unwinds
            await asyncio.gather(t, return_exceptions=True)

    async def stop(self) -> None:
        """Tutor mode off, or the game stopped: silence her now."""
        self.active = False
        await self.hush()
        await _quietly(self.hw.stop(MONITOR))
