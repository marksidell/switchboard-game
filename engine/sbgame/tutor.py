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

From the third call she tutors on (Rev 55), a line with a short form under
tutor: brief: is said short, and More Help says it in full.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from .board import Board
from .link import Hw
from .scenes import _quietly, say
from .script_data import Speech

log = logging.getLogger("tutor")

MONITOR = "audio/monitor"      # its play/set and play (audio.md §10.4)
REPEAT = 20.0                  # s without progress before a prompt is said again
REPEATS = 2                    # times a prompt is said again, at most
NO_LIMIT = 3600.0              # s, for the timeouts tutor mode lifts (§4.9)
# Her introduction, in order: each part but the last waits for More Help
# (§4.9, Rev 31).
INTRO = ("intro-jacks", "intro-cords", "intro-switches")
FULL_CALLS = 2                 # calls she tutors in full before the short forms (Rev 55)
BRIEF = "brief-"               # a short form's key: brief-<key> (tts/script.py)


class Tutor:
    """Her voice, and the one line she can be asked to repeat (Rev 34).

    `repeat_key` is the line she last finished while the game waits on the
    player — a prompt with `until`, or one said with `hold` — until the
    player acts, or she says anything else. The game program publishes it
    through `on_repeat`, for the deck's Repeat Help key, and `repeat()` says
    it again. A prompt before a listen (Rev 35) is repeatable too, but she
    does not say it herself: `repeat()` only asks, and the flow stops the
    listen, says it, and listens again, so the loudspeaker is never heard as
    the operator. While the operator is speaking it is refused.
    """

    def __init__(self, board: Board, hw: Hw, lines: dict[str, Speech],
                 on_repeat: Callable[[str], Awaitable[None]] | None = None,
                 on_more: Callable[[str], Awaitable[None]] | None = None) -> None:
        self.b = board
        self.hw = hw
        self.lines = lines
        self.active = True         # cleared when tutor mode is switched off mid-call
        self._again: asyncio.Task | None = None
        self._on_repeat = on_repeat
        self.repeat_key = ""
        # Rev 55: calls she has tutored, which decides whether this one is
        # said short; and the full line More Help would say for the short one
        # in repeat_key, published through `on_more`.
        self.calls = 0
        self.brief = False
        self._on_more = on_more
        self.more_key = ""
        self._until: Callable[[Board], object] | None = None
        # A prompt before a listen (Rev 35): set while it is repeatable, and
        # what says the operator has started, when it is refused.
        self.asked: asyncio.Event | None = None
        self._speaking: Callable[[], bool] = lambda: False

    def has(self, key: str) -> bool:
        return key in self.lines

    def say_key(self, sp: Speech, request: bool) -> str:
        """What she prompts before the operator speaks ahead of `sp` (§4.7)."""
        if sp.operator and f"say-{sp.operator}" in self.lines:
            return f"say-{sp.operator}"
        return "greet" if request else "respond"

    def next_call(self) -> None:
        """A call is starting: short forms from the third (Rev 55)."""
        self.brief = self.calls >= FULL_CALLS
        self.calls += 1

    async def _set_repeat(self, key: str) -> None:
        if key == self.repeat_key:
            return
        self.repeat_key = key
        if self._on_repeat is not None:
            try:
                await self._on_repeat(key)
            except Exception as e:
                log.info("tutor repeat state: %s", e)
        # More Help lives exactly as long as a short line is repeatable.
        full = key.removeprefix(BRIEF) if key.startswith(BRIEF) else ""
        if full != self.more_key:
            self.more_key = full
            if self._on_more is not None:
                try:
                    await self._on_more(full)
                except Exception as e:
                    log.info("tutor more state: %s", e)

    async def say(self, key: str, *, until: Callable[[Board], object] | None = None,
                  abort_if=None, hold: bool = False,
                  listening: Callable[[], bool] | None = None) -> None:
        """Say one line and return when it has finished.

        With `until`, nothing is said if it is already true, and the line is
        said again in the background while it stays false. With `until` or
        `hold`, the line can be repeated on request until the player acts or
        she says another (Rev 34). With `listening`, a prompt a listen
        follows: repeatable on request through the flow (Rev 35), refused
        while `listening()` says the operator has started speaking.
        """
        await self.hush()
        self.asked = None
        await self._set_repeat("")
        if not self.active:
            return
        sp = self.lines.get(key)
        if sp is None:
            log.warning("no tutor line %s", key)
            return
        if until is not None and until(self.b):
            return
        if self.brief and (short := self.lines.get(BRIEF + key)) is not None:
            key, sp = BRIEF + key, short
        await say(self.b, self.hw, MONITOR, sp.name, sp.seconds, abort_if=abort_if)
        if listening is not None:
            self.asked = asyncio.Event()
            self._speaking = listening
            await self._set_repeat(key)
            return
        if until is not None or hold:
            self._until = until
            await self._set_repeat(key)
        if until is not None:
            self._again = asyncio.create_task(self._repeat(sp, until),
                                              name=f"tutor-{key}")

    def repeat(self) -> bool:
        """Repeat Help (Rev 34): the line again, now, unless there is none.

        Runs in the background, as her own repeats do, so the next step's
        line stops it as it would stop them. The automatic repeats start
        over from its end.
        """
        key = self.repeat_key
        sp = self.lines.get(key)
        if not self.active or sp is None:
            return False
        if self.asked is not None:      # a listen follows: the flow says it
            if self._speaking():
                return False
            self.asked.set()
            return True
        if self._again is not None and not self._again.done():
            self._again.cancel()
        self._again = asyncio.create_task(self._replay(sp, self._until),
                                          name=f"tutor-repeat-{key}")
        return True

    async def more(self) -> bool:
        """More Help on a short line (Rev 55): the full line, now, and it is
        the one repeated from then on. False when no short line is waiting."""
        sp = self.lines.get(self.more_key)
        if not self.active or sp is None or self.asked is not None:
            return False
        await self.hush()               # her own repeat of the short one, if under way
        await self._set_repeat(self.more_key)
        self._again = asyncio.create_task(self._replay(sp, self._until),
                                          name=f"tutor-more-{self.repeat_key}")
        return True

    async def _replay(self, sp: Speech, until) -> None:
        try:
            await say(self.b, self.hw, MONITOR, sp.name, sp.seconds)
            if until is not None:
                await self._repeat(sp, until)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.info("tutor repeat of %s ended: %s", sp.name, e)

    async def _repeat(self, sp: Speech, until) -> None:
        try:
            for _ in range(REPEATS):
                try:
                    await self.b.wait_until(until, REPEAT)
                    break
                except TimeoutError:
                    pass
                if not self.active:
                    return
                await say(self.b, self.hw, MONITOR, sp.name, sp.seconds)
            # Repeatable until the player does the thing (Rev 34).
            await self.b.wait_until(until, None)
            await self._set_repeat("")
        except asyncio.CancelledError:
            raise
        except Exception as e:          # Offline, mostly: the call handles that
            log.info("tutor repeat of %s ended: %s", sp.name, e)

    async def release(self) -> None:
        """The listen after a prompt is over: nothing more to repeat."""
        self.asked = None
        await self._set_repeat("")

    async def hush(self) -> None:
        """Stop a line that is repeating, mid-word if need be."""
        t, self._again = self._again, None
        if t is not None and not t.done():
            t.cancel()                  # say() stops the file as it unwinds
            await asyncio.gather(t, return_exceptions=True)

    async def stop(self) -> None:
        """Tutor mode off, or the game stopped: silence her now."""
        self.active = False
        if self.asked is not None:
            self.asked.set()            # a flow waiting on it moves on
        self.asked = None
        await self.hush()
        await self._set_repeat("")
        await _quietly(self.hw.stop(MONITOR))
