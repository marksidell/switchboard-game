"""Diagnostics from the page (game_control.md §7.5, Rev 25).

One test at a time per target and kind, each a toggle: `hook` takes a station
off-hook, `ring` rings a trunk in the controller's cadence, `tone` is the audio
program's 1kHz test tone on the output channel, `voice` plays the script's
utterances one after another, and `monitor` feeds the loudspeaker from the
target's receive channel. A target is `station/<n>`, `trunk/<n>` or `tap`.

The rules that involve the game — a circuit in a call refuses a test, a circuit
under test is busy for dealing, Stop ends them all, anything else moving the
loudspeaker ends a monitor test — are the game's to apply; it asks this module
what is under test and tells it when to end things.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Awaitable, Callable

from .board import Board, Offline
from .link import Hw
from .script_data import fitted_stations

log = logging.getLogger("diag")

TAP = "tap"
TAP_CH = 23                        # the tap's output channel (audio.md §2)
TRUNK_CH0 = 24                     # trunk n is output channel 24 + n
RING_TIMED_OUT = 6.0               # s of ring off: past the 4s off-phase, so the
                                   # controller's 30s limit has ended it (control.md §8)

TESTS = {"station": ("hook", "tone", "voice", "monitor"),
         "trunk": ("ring", "tone", "voice", "monitor"),
         TAP: ("tone", "voice", "monitor")}


def targets(stations: int, trunks: int) -> list[str]:
    """Every target fitted, in the order the page lists them."""
    return ([f"station/{n}" for n in fitted_stations(stations)]
            + [f"trunk/{n}" for n in range(1, trunks + 1)] + [TAP])


def kind_of(target: str) -> str:
    return TAP if target == TAP else target.split("/")[0]


def output_channel(target: str) -> int:
    if target == TAP:
        return TAP_CH
    kind, n = target.split("/")
    return int(n) if kind == "station" else TRUNK_CH0 + int(n)


class Diagnostics:
    def __init__(self, board: Board, hw: Hw, state: Callable[[str, str], Awaitable[None]],
                 publish: Callable[[str, str], Awaitable[None]],
                 speech: list[tuple[str, float]], stations: int, trunks: int) -> None:
        self.b = board
        self.hw = hw
        self._state = state               # link.state: retained echo
        self._publish = publish           # link.publish: a command
        self.speech = speech              # (wav base name, seconds), for voice
        self.stations, self.trunks = stations, trunks
        self.on: set[tuple[str, str]] = set()          # (target, test) running
        self._tasks: dict[tuple[str, str], asyncio.Task] = {}
        self.monitor_target = ""                        # "" when no monitor test

    # ---- what the game asks ---------------------------------------------

    def fitted(self, target: str) -> bool:
        return target in targets(self.stations, self.trunks)

    def circuits(self) -> set[str]:
        """Station and trunk circuits with any test running (not the tap)."""
        return {t for t, _ in self.on if t != TAP}

    # ---- commands --------------------------------------------------------

    async def command(self, target: str, test: str, on: bool) -> None:
        """Start or stop one test. The caller has validated target and test."""
        key = (target, test)
        if on == (key in self.on):
            await self._echo(key)                       # idempotent (mqtt.md §2)
            return
        if on:
            await self._start(target, test)
        else:
            await self._end(target, test)

    async def _start(self, target: str, test: str) -> None:
        key = (target, test)
        if test in ("tone", "voice"):                   # exclusive on one target (§11.4)
            other = "voice" if test == "tone" else "tone"
            if (target, other) in self.on:
                await self._end(target, other)
        if test == "monitor" and self.monitor_target and self.monitor_target != target:
            await self._end(self.monitor_target, "monitor", restore=False)
        self.on.add(key)
        await self._echo(key)
        if test == "hook":
            await self.hw.hook(int(target.split("/")[1]), True)
        elif test == "ring":
            await self.hw.ring_trunk(int(target.split("/")[1]), True)
            self._tasks[key] = asyncio.create_task(self._watch_ring(target))
        elif test == "tone":
            await self._publish(f"audio/test/{output_channel(target)}/set", "on")
        elif test == "voice":
            self._tasks[key] = asyncio.create_task(self._voice(target))
        elif test == "monitor":
            self.monitor_target = target
            await self.hw.monitor_source(target)

    async def _end(self, target: str, test: str, restore: bool = True) -> None:
        """Stop one test. `restore` is False when something else has already
        moved the loudspeaker, so a monitor test must not move it back."""
        key = (target, test)
        if key not in self.on:
            return
        self.on.discard(key)
        task = self._tasks.pop(key, None)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        try:
            if test == "hook":
                await self.hw.hook(int(target.split("/")[1]), False)
            elif test == "ring":
                await self.hw.ring_trunk(int(target.split("/")[1]), False)
            elif test == "tone":
                await self._publish(f"audio/test/{output_channel(target)}/set", "off")
            elif test == "voice":
                await self._stop_play(target)
            elif test == "monitor":
                self.monitor_target = ""
                if restore:
                    await self.hw.monitor_source(TAP)   # §11.4: back to the tap
        except Offline as e:
            log.warning("ending %s %s: %s", target, test, e)
        await self._echo(key)

    async def monitor_moved(self) -> None:
        """Something other than a monitor test moved the loudspeaker (§9.1)."""
        if self.monitor_target:
            await self._end(self.monitor_target, "monitor", restore=False)

    async def end_all(self) -> None:
        """Stop, a lost client, a restart: every test ends (§2)."""
        for target, test in sorted(self.on):
            await self._end(target, test)

    async def publish_all_off(self) -> None:
        """At birth: every test's echo off, and the hardware told so."""
        for target in targets(22, 8):
            for test in TESTS[kind_of(target)]:
                await self._state(f"game/diag/{target}/{test}", "off")
        for target in targets(self.stations, self.trunks):
            try:
                await self._publish(f"audio/test/{output_channel(target)}/set", "off")
            except Offline:
                pass

    # ---- the long-running ones -------------------------------------------

    async def _watch_ring(self, target: str) -> None:
        """Ring ends when the trunk is seized, or when the controller's ring
        limit has ended it: ring off for longer than the cadence allows."""
        loop = asyncio.get_running_loop()
        off_since: float | None = None
        seen_on = False
        while True:
            await asyncio.sleep(0.25)
            if self.b.on(f"{target}/seize"):
                break
            if self.b.on(f"{target}/ring"):
                seen_on, off_since = True, None
            elif seen_on:
                off_since = off_since or loop.time()
                if loop.time() - off_since > RING_TIMED_OUT:
                    break
        asyncio.create_task(self._end(target, "ring"))

    async def _voice(self, target: str) -> None:
        """The script's utterances, chosen at random, each to its end."""
        if not self.speech:
            return
        rng = random.Random()
        while True:
            name, seconds = rng.choice(self.speech)
            await self._play(target, name)
            await asyncio.sleep(seconds + 0.4)

    async def _play(self, target: str, name: str) -> None:
        topic = "audio/tap/play/set" if target == TAP else f"{target}/play/set"
        await self._publish(topic, name)

    async def _stop_play(self, target: str) -> None:
        topic = "audio/tap/play/set" if target == TAP else f"{target}/play/set"
        await self._publish(topic, "stop")

    async def _echo(self, key: tuple[str, str]) -> None:
        target, test = key
        await self._state(f"game/diag/{target}/{test}", "on" if key in self.on else "off")
