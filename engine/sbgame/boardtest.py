"""Bench test of a trunk board and a station board wired straight together.

With the switchboard out of the way, trunk n is cabled to the n-th station of
one station board, and each pair is put through what the switchboard would
otherwise do: the trunk rings the station, the station goes off-hook and the
trunk sees the seizure, the two hear each other's pilot, the station dials
every digit — the controller timing the pulses, control.md §7.3 — and the
trunk decodes them without losing the seizure, and on-hook undoes it. One pair at a time, and every other channel is checked to stay idle
throughout.

    sbgame-boardtest --stations a          board a, stations 1-8, on trunks 1-8
    sbgame-boardtest --stations c          board c, stations 17-22, trunks 1-6
    sbgame-boardtest --stations b --no-audio

It talks to the controller and the audio program over the broker, as the game
program does, and needs both running and no game in progress. The controller
holds every relay released without the game program's heartbeat (control.md
§10), so this sends one itself when the game program is not online.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

PREFIX = "sbgame/"
N_TRUNKS = 8
# Station boards (station §6, control.md §6.1): their stations and expander.
BOARDS = {"a": (range(1, 9), "0x20"), "b": (range(9, 17), "0x21"), "c": (range(17, 23), "0x22")}
TRUNK_EXPANDER = "0x23"


@dataclass
class Timing:
    ring: float = 10.0     # ring to reach the station: up to two 2s-on cadence bursts
    clear: float = 8.0     # ring to clear once stopped
    seize: float = 5.0     # off-hook to the trunk's seizure, and back
    peer: float = 8.0      # the pilot detector to see the change
    # Each digit to be decoded: up to ten pulses at 100ms, the 700ms return
    # before it, and the 200ms end-of-digit wait after (control.md §7.3, §8.2).
    digit: float = 3.0


@dataclass
class Result:
    passed: int = 0
    failed: list[str] = field(default_factory=list)
    stopped: list[str] = field(default_factory=list)   # pairs not finished, and why


class Stop(Exception):
    """A check the rest of the pair depends on has failed."""


def _print(line: str) -> None:
    print(line, flush=True)            # progress shows as it happens, piped or not


class BoardTest:
    """The test itself, over a state dict and a publish callable, so the
    sequence can be run against a fake as well as the broker."""

    def __init__(self, state: dict[str, str], publish: Callable[[str, str], Awaitable[None]],
                 stations: list[int], audio: bool, timing: Timing | None = None,
                 only: set[int] | None = None,
                 out: Callable[[str], None] = _print) -> None:
        self.s = state
        self.pub = publish
        self.stations = stations
        self.only = only            # pair numbers to test, 1-8; None for all
        self.audio = audio
        self.t = timing or Timing()
        self.out = out
        self.r = Result()
        self.changes: list[tuple[str, str]] = []      # every state change, for the others
        self.digits: list[tuple[str, str]] = []       # (trunk, digit), every one reported

    # ---- state -----------------------------------------------------------

    def get(self, key: str) -> str:
        return self.s.get(key, "")

    def note(self, key: str, value: str) -> None:
        """Called for every message: keep a record of what changed."""
        if key.endswith("/digit"):              # an event: the same digit twice is two
            self.digits.append((key.rsplit("/", 1)[0], value))
            return
        if self.s.get(key, "") != value:
            self.changes.append((key, value))

    async def wait(self, pred: Callable[[], bool], timeout: float) -> float | None:
        """Seconds until pred() held, or None if it never did."""
        start = time.monotonic()
        while True:
            if pred():
                return time.monotonic() - start
            if time.monotonic() - start > timeout:
                return None
            await asyncio.sleep(0.05)

    def need(self, ok: bool, step: str, what: str) -> None:
        """A check the rest of the pair depends on: on failure, stop the pair."""
        if not self.check(ok, step, what):
            raise Stop(f"{step}: {what}")

    def check(self, ok: bool, step: str, what: str) -> bool:
        self.out(f"    {step:<9} {what:<62} {'ok' if ok else 'FAIL'}")
        if ok:
            self.r.passed += 1
        else:
            self.r.failed.append(f"{step}: {what}")
        return ok

    # ---- idle --------------------------------------------------------------

    def idle_faults(self, circuit: str) -> list[str]:
        """What is not idle about one circuit."""
        kind = circuit.split("/")[0]
        bad = []
        if kind == "trunk":
            if self.get(f"{circuit}/seize") == "on":
                bad.append("seized")
            if self.get(f"{circuit}/ring") == "on":
                bad.append("ringing")
        else:
            if self.get(f"{circuit}/ring") == "on":
                bad.append("detecting ring")
            if self.get(f"{circuit}/hook") == "on":
                bad.append("off-hook")
        if self.audio:
            peer = self.get(f"{circuit}/peer")
            if peer:
                bad.append(f"hears {peer}" if "/" in peer else peer)
        return bad

    def circuits(self) -> list[str]:
        return ([f"trunk/{n}" for n in range(1, N_TRUNKS + 1)]
                + [f"station/{n}" for n in self.stations])

    def others_idle(self, pair: tuple[str, str], step: str, since: int) -> None:
        """Every circuit but the pair is idle now, and nothing of theirs moved."""
        others = [c for c in self.circuits() if c not in pair]
        now = {c: f for c in others if (f := self.idle_faults(c))}
        moved = sorted({k.rsplit("/", 1)[0] for k, _ in self.changes[since:]
                        if k.rsplit("/", 1)[0] in others
                        and k.rsplit("/", 1)[1] in ("seize", "ring", "hook", "peer")})
        what = ("the other channels stayed idle" if not now and not moved
                else "others not idle: " + "; ".join(
                    [f"{c} {', '.join(f)}" for c, f in now.items()]
                    + [f"{c} changed" for c in moved if c not in now]))
        self.check(not now and not moved, step, what)

    # ---- dialling -----------------------------------------------------------

    async def dial(self, trunk: str, station: str) -> None:
        """The station dials 1 to 0 in one command, the controller timing the
        pulses and the pauses (control.md §7.3); each digit is checked as the
        trunk decodes it, and the trunk must hold its seizure throughout."""
        pair = (trunk, station)
        mark, seen = len(self.changes), len(self.digits)
        await self.pub(f"{station}/dial/set", "1234567890")
        for d in "1234567890":
            await self.wait(lambda: any(t == trunk for t, _ in self.digits[seen:]), self.t.digit)
            got = [v for t, v in self.digits[seen:] if t == trunk][:1]
            seen += next((i + 1 for i, (t, _) in enumerate(self.digits[seen:]) if t == trunk), 0)
            fault = self.get(f"{trunk}/fault")
            if not self.check(got == [d], "5 dial",
                              f"{station} dials {d}, {trunk} decodes {d}" if got == [d]
                              else f"{station} dials {d}, {trunk} reports "
                                   + (", ".join(got) if got else "nothing")
                                   + (f" (fault {fault})" if fault else "")):
                await self.pub(f"{station}/dial/set", "")       # the rest would only repeat it
                break
        done = await self.wait(lambda: not self.get(f"{station}/dial"), self.t.digit)
        self.check(done is not None, "5 dial", f"{station} finished dialling")
        released = any(k == f"{trunk}/seize" and v != "on" for k, v in self.changes[mark:])
        self.check(not released and self.get(f"{trunk}/seize") == "on", "5 dial",
                   f"{trunk} held the seizure through every pulse" if not released
                   else f"{trunk} released its seizure during dialling")
        self.others_idle(pair, "5 dial", mark)

    # ---- the sequence ------------------------------------------------------

    async def run(self) -> Result:
        n = len(self.stations)
        self.out(f"trunks 1-{n} to stations {self.stations[0]}-{self.stations[-1]}"
                 + ("" if self.audio else ", pilot tests off"))
        self.out("\n1 idle: every channel")
        bad: set[str] = set()
        for c in self.circuits():
            f = self.idle_faults(c)
            if not self.check(not f, "idle", f"{c} idle" if not f else f"{c}: {', '.join(f)}"):
                bad.add(c)
        pairs = [(f"trunk/{k}", f"station/{st}") for k, st in enumerate(self.stations, 1)
                 if self.only is None or k in self.only]
        ready = [p for p in pairs if not (set(p) & bad)]
        for p in pairs:
            if p not in ready:
                self.r.stopped.append(f"{p[0]} <-> {p[1]}: not idle at the start")
        if not ready:
            self.out("\nno pair is idle to start from: stopping")
            return self.r

        for (trunk, station) in pairs:
            k = int(trunk.split("/")[1])
            if (trunk, station) not in ready:
                self.out(f"\npair {k} of {n}: {trunk} <-> {station} — skipped, not idle at the start")
                continue
            self.out(f"\npair {k} of {n}: {trunk} <-> {station}")
            try:
                await self.pair(trunk, station)
            except Stop as e:
                self.r.stopped.append(f"{trunk} <-> {station}: stopped at {e}")
                self.out(f"    stopped: the rest of this pair depends on that")
            finally:
                await self.pub(f"{station}/dial/set", "")
                await self.pub(f"{trunk}/ring/set", "off")
                await self.pub(f"{station}/hook/set", "off")
        return self.r

    async def pair(self, trunk: str, station: str) -> None:
        pair = (trunk, station)
        mark = len(self.changes)
        f = self.idle_faults(trunk) + self.idle_faults(station)
        self.need(not f, "1 idle", f"{trunk} and {station} idle" if not f else ", ".join(f))

        # 2 ring: the trunk rings, the station detects it; then it clears.
        await self.pub(f"{trunk}/ring/set", "on")
        took = await self.wait(lambda: self.get(f"{station}/ring") == "on", self.t.ring)
        if took is None:
            await self.pub(f"{trunk}/ring/set", "off")
        self.need(took is not None, "2 ring",
                   f"{station} detects ring" + (f" after {took:.1f}s" if took is not None else ""))
        await self.pub(f"{trunk}/ring/set", "off")
        clear = await self.wait(lambda: self.get(f"{station}/ring") != "on"
                                and self.get(f"{trunk}/ring") != "on", self.t.clear)
        self.check(clear is not None, "2 ring", f"ring stops on {trunk} and clears at {station}")
        self.others_idle(pair, "2 ring", mark)

        # 3 off-hook: the station closes the loop, the trunk sees the seizure.
        mark = len(self.changes)
        await self.pub(f"{station}/hook/set", "on")
        took = await self.wait(lambda: self.get(f"{station}/hook") == "on", self.t.seize)
        self.need(took is not None, "3 offhook", f"{station} relay echoes off-hook")
        took = await self.wait(lambda: self.get(f"{trunk}/seize") == "on", self.t.seize)
        self.need(took is not None, "3 offhook",
                   f"{trunk} detects seize" + (f" after {took:.1f}s" if took is not None else ""))

        # 4 the two hear each other's pilot.
        if self.audio:
            took = await self.wait(lambda: self.get(f"{trunk}/peer") == station
                                   and self.get(f"{station}/peer") == trunk, self.t.peer)
            self.check(took is not None, "4 pilots",
                       f"{trunk} hears {station} and {station} hears {trunk}"
                       if took is not None else
                       f"{trunk} hears {self.get(f'{trunk}/peer') or 'only itself'}, "
                       f"{station} hears {self.get(f'{station}/peer') or 'only itself'}")
        self.others_idle(pair, "4 pilots" if self.audio else "3 offhook", mark)

        # 5 dial: every digit from the station, decoded by the trunk, which
        # must hold the seizure through every break.
        if self.get(f"{trunk}/seize") == "on":
            await self.dial(trunk, station)

        # 6 on-hook: the seizure releases and they no longer hear each other.
        mark = len(self.changes)
        await self.pub(f"{station}/hook/set", "off")
        took = await self.wait(lambda: self.get(f"{trunk}/seize") != "on", self.t.seize)
        self.check(took is not None, "6 onhook",
                   f"{trunk} detects the release" + (f" after {took:.1f}s" if took is not None else ""))
        if self.audio:
            took = await self.wait(lambda: not self.get(f"{trunk}/peer")
                                   and not self.get(f"{station}/peer"), self.t.peer)
            self.check(took is not None, "6 onhook",
                       f"{trunk} and {station} no longer hear each other" if took is not None else
                       f"{trunk} hears {self.get(f'{trunk}/peer') or 'only itself'}, "
                       f"{station} hears {self.get(f'{station}/peer') or 'only itself'}")
        self.others_idle(pair, "6 onhook", mark)


# ---- the broker ---------------------------------------------------------------

def preflight(state: dict[str, str], board: str, audio: bool) -> list[str]:
    bad = []
    if state.get("ctl/status") != "online":
        bad.append("the controller is not online (ctl/status)")
    if audio and state.get("ctl/audio_status") != "online":
        bad.append("the audio program is not online (ctl/audio_status); or use --no-audio")
    if state.get("game/run") == "on":
        bad.append("a game is running; stop it first")
    i2c = state.get("ctl/i2c", "")
    for addr, what in ((BOARDS[board][1], f"station board {board}"), (TRUNK_EXPANDER, "the trunk board")):
        if addr in i2c:
            bad.append(f"the controller cannot see {what} ({addr} missing on ctl/i2c)")
    return bad


async def main_async(args) -> int:
    import aiomqtt

    host, _, port = args.broker.partition(":")
    password = Path(args.password_file).read_text(encoding="utf-8").strip()
    state: dict[str, str] = {}
    stations = list(BOARDS[args.stations][0])
    try:
        only = {int(x) for x in args.pairs.split(",") if x.strip()} or None
    except ValueError:
        print(f"--pairs {args.pairs!r}: numbers 1-8, comma-separated", file=sys.stderr)
        return 2
    if only and not only <= set(range(1, len(stations) + 1)):
        print(f"--pairs {args.pairs}: board {args.stations} has pairs 1-{len(stations)}", file=sys.stderr)
        return 2

    async with aiomqtt.Client(hostname=host, port=int(port or 1883), username=args.user,
                              password=password, identifier="sbgame-boardtest") as client:
        test: BoardTest | None = None

        async def publish(key: str, value: str) -> None:
            await client.publish(PREFIX + key, value, qos=1)

        async def reader() -> None:
            async for m in client.messages:
                key = str(m.topic).removeprefix(PREFIX)
                value = m.payload.decode() if isinstance(m.payload, bytes) else str(m.payload or "")
                if test is not None:
                    test.note(key, value)
                state[key] = value

        async def heartbeat() -> None:
            # Only while the game program is not there to send its own.
            while True:
                if state.get("ctl/game_status") != "online":
                    await client.publish(PREFIX + "ctl/game_heartbeat", f"{time.time():.1f}")
                await asyncio.sleep(1.0)

        await client.subscribe(PREFIX + "#", qos=1)
        read = asyncio.create_task(reader())
        await asyncio.sleep(1.0)                       # the retained state lands
        bad = preflight(state, args.stations, not args.no_audio)
        if bad:
            for b in bad:
                print(f"cannot test: {b}", file=sys.stderr)
            read.cancel()
            return 2
        beat = asyncio.create_task(heartbeat())
        if state.get("ctl/game_status") != "online":
            print("the game program is not online: sending its heartbeat, so the relays work")
            await asyncio.sleep(2.5)                   # the controller to see it
        test = BoardTest(state, publish, stations, not args.no_audio,
                         Timing(ring=args.ring_timeout), only=only)
        try:
            r = await test.run()
        finally:
            for k, st in enumerate(stations, 1):
                await publish(f"trunk/{k}/ring/set", "off")
                await publish(f"station/{st}/hook/set", "off")
            beat.cancel()
            read.cancel()

    print(f"\n{r.passed} passed, {len(r.failed)} failed")
    for f in r.failed:
        print(f"  FAIL {f}")
    for s in r.stopped:
        print(f"  NOT FINISHED {s}")
    return 1 if r.failed else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Test a trunk board and a station board wired straight together.")
    p.add_argument("--stations", required=True, choices=sorted(BOARDS),
                   help="the station board on the trunks: a = stations 1-8, b = 9-16, "
                        "c = 17-22 (its strip 7 is the tap; strip 8, station 24, is a real telephone)")
    p.add_argument("--no-audio", action="store_true", help="leave out the pilot tone tests")
    p.add_argument("--pairs", default="", metavar="N[,N...]",
                   help="test only these pairs, 1-8 (trunk n with the board's n-th station); "
                        "the rest are still checked to stay idle")
    p.add_argument("--ring-timeout", type=float, default=Timing.ring,
                   help="seconds for ring to reach the station (10)")
    p.add_argument("--broker", default="localhost:1883")
    # As sbgame-sim does: the audio program's identity has the rights needed,
    # and its password is on the host (mqtt.md 9).
    p.add_argument("--user", default="sbgame-audio")
    p.add_argument("--password-file", default="/etc/sbgame/mqtt-audio.pass")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
