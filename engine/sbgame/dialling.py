"""A number read off a trunk as it is dialled (game_control.md §3.5, §8.2).

Shared by the game's calls out (flows.py) and free calls (freecall.py). The
controller decodes the pulses (control.md §8); the board keeps the digits
since the trunk was last seized, `Board.dialled()`.
"""

from __future__ import annotations

import asyncio
import math
from typing import Callable

from .board import Board
from .link import Hw

# s from seizure to dial tone: an exchange takes a moment to connect a register.
DIAL_DELAY = 1.0
# s with no new digit, short of a number: too few digits.
DIAL_PAUSE = 10.0
# s after the last digit a number needs before it counts as dialled, so a digit
# more is caught; longer than a dial takes to return and run ten pulses.
DIAL_SETTLE = 3.0


async def dial_tone(b: Board, hw: Hw, trunk: int) -> None:
    """Dial tone on a freshly seized trunk, after DIAL_DELAY, unless she has
    started dialling already."""
    await asyncio.sleep(DIAL_DELAY)
    if not b.dialled(trunk):
        await hw.tone(trunk, "dial")


async def read_number(b: Board, trunk: int, whole: Callable[[str], bool], longest: int,
                      *, left: Callable[[], float] = lambda: math.inf,
                      stop: Callable[[Board], object] | None = None) -> str:
    """The digits once a whole number is dialled, with DIAL_SETTLE and no digit
    more; else "long" for a digit beyond `longest`, "short" for DIAL_PAUSE with
    no digit short of a whole number, "released" if she releases the trunk, or
    what `stop` returns once it is true. The first digit is in already.

    `left` is the time left on the caller's own deadline: when it runs out
    first, TimeoutError.
    """
    seized = f"trunk/{trunk}/seize"
    while True:
        have = b.dialled(trunk)
        if len(have) > longest:
            return "long"
        done = whole(have)
        wait, remaining = (DIAL_SETTLE if done else DIAL_PAUSE), left()
        try:
            got = await b.wait_until(
                lambda b, k=len(have): ((stop is not None and stop(b))
                                        or (not b.on(seized) and "released")
                                        or len(b.dialled(trunk)) > k),
                min(wait, remaining))
        except TimeoutError:
            if wait >= remaining:
                raise                   # the caller's deadline, not the pause
            return have if done else "short"
        if got is not True:
            return got
