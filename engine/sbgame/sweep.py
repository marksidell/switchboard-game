"""Board sweeps from the Stream Deck (game_control.md §11.5).

A check of the cabling after a recabling, with no game running: `trunks`
gives each trunk one short ring in turn, so its lamp lights on the
switchboard, holds 3s so that a lamp whose ring relay latched is seen to stay
lit, then cuts the switchboard's power for 1s, which resets the relay and puts
the lamp out; and `stations` takes each station off-hook briefly in turn, in
jack order — the switchboard's rows from the top, 21-30, 11-20, 1-10, each
left to right (§11.1) — so its lamp lights in the order the eye reads the board.
Each step is put on the game log, so the page shows where the sweep has got to,
and the hardware's own echoes light the tiles.

The game owns the task: it refuses a sweep while a game runs, and Start, Stop
and losing a client end one. A circuit under a page diagnostic is passed over,
so the sweep never releases a hook the page is holding.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Iterable

from .link import Hw
from .script_data import PHONE_STATION, Jack, fitted_stations

log = logging.getLogger("sweep")

KINDS = ("trunks", "stations")
ROWS = (range(21, 31), range(11, 21), range(1, 11))   # top row first (§11.1)

BURST = 1.0          # s: the controller's short ring (control.md §8.4)
LATCH_HOLD = 3.0     # s after the burst, the lamp lit only if its relay latched
CUT = 1.0            # s the switchboard is off: the controller's (control.md §5.4)
OFF_HOOK = 1.0       # s a station is held off-hook
PAUSE = 2.0          # s between one station and the next
TRUNK_PAUSE = 0.5    # s between one trunk's reset and the next ring


def station_order(jacks: Iterable[Jack], stations: int) -> list[tuple[int, Jack]]:
    """(station number, jack) for every fitted station, in jack order."""
    by_jack = {j.number: j for j in jacks if j.kind == "station" and j.circuit}
    fitted = set(fitted_stations(stations))
    out = []
    for row in ROWS:
        for n in row:
            j = by_jack.get(n)
            if j is not None:
                st = int(j.circuit.split("/")[1])
                if st in fitted:
                    out.append((st, j))
    return out


async def run(kind: str, hw: Hw, jacks: Iterable[Jack], stations: int, trunks: int,
              busy: Callable[[], set[str]], say: Callable[[str], Awaitable[None]],
              out_of_service: Callable[[str], bool], public_trunk: int = 0) -> None:
    """One sweep, to its end. Cancelling it puts the current circuit back.
    Not the public line nor station 24, the real telephone (§8):
    the game never rings the one, and the other's relay lights nothing."""
    if kind == "trunks":
        steps = [(f"trunk/{n}", f"trunk {n}") for n in range(1, trunks + 1)
                 if n != public_trunk]
    else:
        steps = [(f"station/{st}", f"jack {j.number} ({j.label}), station {st}")
                 for st, j in station_order(jacks, stations) if st != PHONE_STATION]
    pause = TRUNK_PAUSE if kind == "trunks" else PAUSE
    await say(f"test {kind}: {len(steps)}, {pause:g}s apart")
    for i, (circuit, name) in enumerate(steps):
        if i:
            await asyncio.sleep(pause)
        note = ", out of service" if out_of_service(circuit) else ""
        if circuit in busy():
            await say(f"test {kind}: {name} passed over, under a diagnostic")
            continue
        n = int(circuit.split("/")[1])
        if kind == "trunks":
            await say(f"test {kind}: {name} short ring; lit {LATCH_HOLD:g}s if it latched, "
                      f"then switchboard reset{note}")
            try:
                await hw.short_ring(n)
                await asyncio.sleep(BURST + LATCH_HOLD)
                await hw.power_cut()
                await asyncio.sleep(CUT)
            except asyncio.CancelledError:
                await asyncio.shield(hw.ring_trunk(n, False))
                raise
        else:
            await say(f"test {kind}: {name} off-hook{note}")
            try:
                await hw.hook(n, True)
                await asyncio.sleep(OFF_HOOK)
            finally:
                await asyncio.shield(hw.hook(n, False))
    await say(f"test {kind}: done")
