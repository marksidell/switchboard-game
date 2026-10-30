"""The page's log (game_control.md §6.2).

The last 50 events, newest first, one per line, republished whole on each new
event. It is a display, not the record — the SQLite session log is the record
(session.py) — which is why it can afford to be a deque and to be thrown away
on a restart.

    14:02:31 [7] success
    14:02:10 [8] started pike-taxi: lobby → taxi
    14:01:40 page: gap 15

Host time, because the iPad's clock is not trusted (§11.2). The call number in
brackets where there is one.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Awaitable, Callable

MAX_LINES = 50


class GameLog:
    def __init__(self, publish: Callable[[str, str], Awaitable[None]]) -> None:
        # publish(key, value) -> awaitable; Link.state in the real program.
        self._publish = publish
        self._lines: deque[str] = deque(maxlen=MAX_LINES)

    def format(self, text: str, call: int | None = None, when: float | None = None) -> str:
        stamp = time.strftime("%H:%M:%S", time.localtime(when or time.time()))
        return f"{stamp} [{call}] {text}" if call else f"{stamp} {text}"

    async def add(self, text: str, call: int | None = None) -> str:
        """Log one event and republish the whole log."""
        line = self.format(text, call)
        self._lines.appendleft(line)
        await self._publish("game/log", "\n".join(self._lines))
        return line

    async def clear(self, first: str = "") -> None:
        self._lines.clear()
        if first:
            self._lines.appendleft(self.format(first))
        await self._publish("game/log", "\n".join(self._lines))

    def lines(self) -> list[str]:
        return list(self._lines)
