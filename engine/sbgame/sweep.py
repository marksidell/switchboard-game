"""Board sweeps from the Stream Deck (game_control.md §7.6, Rev 50).

A check of the cabling after a recabling, with no game running: `trunks`
gives each trunk one short ring in turn, so its lamp latches on the
switchboard, and `stations` takes each station off-hook briefly in turn, in
jack order — the switchboard's rows from the top, 21-30, 11-20, 1-10, each
left to right (§7.1) — so its lamp lights in the order the eye reads the board.
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
from .script_data import Jack, fitted_stations

log = logging.getLogger("sweep")

KINDS = ("trunks", "stations")
ROWS = (range(21, 31), range(11, 21), range(1, 11))   # top row first (§7.1)

BURST = 1.0          # s: the controller's short ring (control.md §8.4, Rev 30)
OFF_HOOK = 1.0       # s a station is held off-hook
PAUSE = 2.0          # s between one circuit and the next


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
              out_of_service: Callable[[str], bool]) -> None:
    """One sweep, to its end. Cancelling it puts the current circuit back."""
    if kind == "trunks":
        steps = [(f"trunk/{n}", f"trunk {n}") for n in range(1, trunks + 1)]
    else:
        steps = [(f"station/{st}", f"jack {j.number} ({j.label}), station {st}")
                 for st, j in station_order(jacks, stations)]
    await say(f"test {kind}: {len(steps)}, {PAUSE:g}s apart")
    for i, (circuit, name) in enumerate(steps):
        if i:
            await asyncio.sleep(PAUSE)
        note = ", out of service" if out_of_service(circuit) else ""
        if circuit in busy():
            await say(f"test {kind}: {name} passed over, under a diagnostic")
            continue
        n = int(circuit.split("/")[1])
        if kind == "trunks":
            await say(f"test {kind}: {name} short ring{note}")
            try:
                await hw.short_ring(n)
                await asyncio.sleep(BURST)
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
