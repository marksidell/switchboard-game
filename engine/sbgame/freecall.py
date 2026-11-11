"""Free calls, Lenny mode (game_control.md §8).

A real person lifts the telephone on station 24, or calls the public line
(trunk 8, the Grandstream ATA) from outside. The operator answers and puts
them through to a room, or dials an outside number for them. Whoever is
there answers in character and then keeps the caller talking as Lenny does:
one line at each pause in the caller's talk, the `lines:` once each and then
the `loop:` round and round, until the caller hangs up. A number nobody
answers gets the real Lenny.

Free calls run for the life of the program, with or without a game, and
alongside its calls. They are not scored and have no call slot. The game
asks this module what they hold (`circuits()`, `holdings()`), so it neither
deals a scene onto them nor tests them, and its routing flows leave a free
caller's trunk and rings alone while one is routing (`routing()`).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from .board import LIVE_AUDIO, LIVE_CONTROL, Abandoned, Board, Offline
from .deck import Holding
from .dialling import dial_tone, read_number
from .scenes import MARGIN, MAX_SPEECH, quietly, hear, say
from .script_data import PHONE_STATION, FreeLines, fitted_stations

if TYPE_CHECKING:
    from .game import Game

log = logging.getLogger("free")

PHONE = f"station/{PHONE_STATION}"
LISTEN = 3.0          # s after a line for the caller to start talking before "Hello?"
LISTEN_AGAIN = 7.0    # s after a "Hello?" before the next one
TURN_END = 0.4        # s more of silence before it is the answerer's turn
PATCH_WAIT = 8.0      # s for the cord to join a room that answered (§3.5)
# s for the first digit, else she is taken to have given up on the trunk.
# Half a game call's flows.DIAL_FIRST, and with no reorder.
DIAL_FIRST = 15.0
NUMBER = 7            # digits in a number; "0" alone is the operator
RINGBACK_KNOWN = 2.0  # s of ringback before an establishment answers
ROOM_ANSWER = 4.0     # s from her ringing a room to its answering
RINGBACK_LENNY = 4.0  # and before the real Lenny does
RETRY = 2.0           # s before a free call that ended on a fault starts again
FREE_PEER_DB = 6      # the loudspeaker's peer boost, dB: the caller is live


class Gone(Exception):
    """The caller hung up."""


class FreeCall:
    """One free caller, from answer to hang-up."""

    def __init__(self, fc: "FreeCalls", caller: str) -> None:
        self.fc, self.caller = fc, caller
        self.name = "phone" if caller == PHONE else caller
        self.answered = False
        self.callee = ""          # the circuit answering, while connected
        self.who = ""             # who answers there
        self.line = ""            # its script.yml line, for dealing

    @property
    def b(self) -> Board:
        return self.fc.game.b

    @property
    def hw(self):
        return self.fc.game.hw

    def gone(self, b: Board) -> bool:
        if self.caller == PHONE:
            return not b.on(f"{PHONE}/lifted")
        return not b.on(f"{self.caller}/seize")

    async def run(self) -> None:
        try:
            if self.caller == PHONE:
                await self.hw.hook(PHONE_STATION, True)   # the line onto channel 24
            got = await self.b.wait_until(
                lambda b: ("gone" if self.gone(b) else b.on(f"{self.caller}/op") and "op"),
                None, needs=(LIVE_CONTROL,))
            if got == "gone":
                return
            self.answered = True
            await self.fc.say(f"free call: {self.name} answered")
            await self.fc.game.monitor(self.caller, str(FREE_PEER_DB))  # §9.1: at the answer
            while not self.gone(self.b):
                target = await self._route()
                if target is None:
                    break
                try:
                    if target.startswith("station/"):
                        await self._room(int(target.split("/")[1]))
                    else:
                        await self._outside(int(target.split("/")[1]))
                except Abandoned:
                    pass                                   # back to routing, if still there
                finally:
                    self.callee = self.who = self.line = ""
        finally:
            if self.caller == PHONE:
                await quietly(self.hw.hook(PHONE_STATION, False))
            if self.answered:
                await self.fc.say(f"free call: {self.name} hung up")

    # ---- connecting -------------------------------------------------------

    async def _route(self) -> str | None:
        """Wait for her to ring a room or dial out for the caller. None: gone."""
        def found(b: Board):
            if self.gone(b):
                return "gone"
            return self.fc.claimable_ring(b) or self.fc.claimable_trunk(b, self.caller)
        got = await self.b.wait_until(found, None)
        return None if got == "gone" else got

    def _abort(self, peer_of: str):
        """Abandoned: the caller has gone, or the cord to the answerer is out."""
        def why(b: Board):
            if self.gone(b):
                return f"{self.name} hung up"
            return b.get(f"{peer_of}/peer") != self.caller and f"cord out from {peer_of}"
        return why

    async def _room(self, n: int) -> None:
        """A room rung: it answers, and once patched, its person talks."""
        c = f"station/{n}"
        self.callee = c
        self.who, lines = self.fc.game.gs.answerer(self.fc.game.gs.free_station.get(n, ""))
        self.line = next(iter(self.fc.game.station_lines.get(n, ())), "")
        try:
            # Someone has to get to the telephone.
            try:
                await self.b.wait_until(self.gone, ROOM_ANSWER)
                return
            except TimeoutError:
                pass
            await self.hw.hook(n, True)
            if not await self._patched(c):
                await self.b.wait_until(lambda b: not b.on(f"{c}/ring") or self.gone(b), None)
                return
            await self.fc.say(f"free call: {self.name} to {self.line or c}, "
                              f"{self.who or 'nobody'} answers")
            await self._talk(c, lines, self._abort(c))
        finally:
            await quietly(self.hw.stop(c))
            await quietly(self.hw.hook(n, False))

    async def _patched(self, c: str) -> bool:
        """The room off-hook waits for the cord; "Hello?" at PATCH_WAIT, and
        it hangs up at twice that (§3.5)."""
        joined = lambda b: self.gone(b) or b.get(f"{c}/peer") == self.caller
        hello = self.fc.game.gs.reaction("hello", self.who)
        for step in ("hello", "hang up"):
            try:
                await self.b.wait_until(joined, PATCH_WAIT)
                if self.gone(self.b):
                    raise Gone
                return True
            except TimeoutError:
                pass
            if step == "hello" and hello is not None:
                await say(self.b, self.hw, c, hello.name, hello.seconds)
        await self.fc.say(f"free call: {c} hung up, nobody on the line")
        return False

    async def _outside(self, k: int) -> None:
        """A trunk seized for the caller: dial tone, the number, ringback, and
        whoever is at that number - or the real Lenny."""
        t = f"trunk/{k}"
        self.callee = t
        up = lambda b: b.on(f"{t}/seize")
        try:
            await dial_tone(self.b, self.hw, k)
            try:
                got = await self.b.wait_until(
                    lambda b: self.gone(b) and "gone" or (not up(b) and "released") or b.dialled(k),
                    DIAL_FIRST)
            except TimeoutError:
                got = "released"
            await self.hw.tone(k, "off")
            if got in ("gone", "released"):
                await self.b.wait_until(lambda b: not up(b) or self.gone(b), None)
                return
            digits = await self._number(k)
            if digits is None:
                return
            if digits in ("short", "long"):
                # Fast busy, as a game call's misdial gets (§3.5), until
                # she releases the trunk or the caller goes.
                got = self.b.dialled(k)
                await self.fc.say(f"free call: {self.name} dialled {got}: too "
                                  + ("few" if digits == "short" else "many") + " digits")
                await self.hw.tone(k, "reorder")
                await self.b.wait_until(lambda b: not up(b) or self.gone(b), None)
                return
            gs = self.fc.game.gs
            line = gs.numbers.get(digits, "")
            self.line = line
            self.who, lines = gs.answerer(gs.free_outside.get(line, "") if line else "")
            await self.fc.say(f"free call: {self.name} dialled {digits}"
                              + (f", {line}" if line else "") + f", {self.who} answers")
            await self.hw.tone(k, "ringback")
            await asyncio.sleep(RINGBACK_KNOWN if line else RINGBACK_LENNY)
            await self.hw.tone(k, "off")
            abort = self._abort(t)
            await self._talk(t, lines, lambda b: abort(b) or (not up(b) and f"{t} released"))
        finally:
            await quietly(self.hw.tone(k, "off"))
            await quietly(self.hw.stop(t))

    async def _number(self, k: int) -> str | None:
        """The number once dialled: seven digits, or "0" for the operator.
        "long" or "short" as read_number() has it; None if she released the
        trunk or the caller went."""
        got = await read_number(self.b, k, lambda d: len(d) == NUMBER or d == "0", NUMBER,
                                stop=lambda b: self.gone(b) and "gone")
        return None if got in ("gone", "released") else got

    # ---- talking, Lenny-style ---------------------------------------------

    async def _talk(self, c: str, lines: FreeLines | None, abort) -> None:
        """The greeting, then a line at each pause, until abort fires."""
        if lines is None:
            log.warning("free call: no lines for %s, not even Lenny's; silence", self.who)
            await self.b.wait_until(lambda b: False, None, abort_if=abort)
            return
        hello = self.fc.game.gs.reaction("hello", self.who)
        k = 0
        sp, wait = lines.greeting, LISTEN
        while True:
            if await self._line(c, sp, wait, abort):
                sp, wait = lines.said(k), LISTEN
                k += 1
            elif hello is not None:
                sp, wait = hello, LISTEN_AGAIN
            else:
                # Lenny says nothing to silence: he listens until the caller speaks.
                while not await self._turn(c, LISTEN_AGAIN, abort):
                    pass
                sp, wait = lines.said(k), LISTEN
                k += 1

    async def _line(self, c: str, sp, wait: float, abort) -> bool:
        """Say a line, listening from its start: the audio program's
        echo canceller hears a caller who talks over it (audio.md 9.4). True
        once the caller has spoken, during the line or within `wait` after
        it, and then stopped for TURN_END; False if they said nothing."""
        key = f"{c}/listen"
        await self.b.expect(key)
        await self.hw.listen(c, sp.seconds + wait)
        try:
            await say(self.b, self.hw, c, sp.name, sp.seconds, abort_if=abort)
            await self.b.wait_until(
                lambda b: b.get(key) in ("silence", "timeout") and b.get(key),
                wait + MAX_SPEECH + MARGIN, abort_if=abort, needs=(LIVE_AUDIO,))
        except BaseException:
            await quietly(self.hw.listen(c, 0))
            raise
        spoke = self.b.saw(key, "speech")
        while spoke:
            await hear(self.b, self.hw, c, TURN_END, abort_if=abort)
            if not self.b.saw(key, "speech"):
                break
        return spoke

    async def _turn(self, c: str, wait: float, abort) -> bool:
        """Listen for the caller's turn. True once they have spoken and then
        stopped for TURN_END; False if they said nothing within `wait`."""
        key = f"{c}/listen"
        start = wait
        spoke = False
        while True:
            await hear(self.b, self.hw, c, start, abort_if=abort)
            if self.b.saw(key, "speech"):
                spoke, start = True, TURN_END        # a breath, or the end?
                continue
            return spoke


class FreeCalls:
    """Every free call, for the life of the program."""

    def __init__(self, game: "Game") -> None:
        self.game = game
        self.calls: dict[str, FreeCall] = {}
        self.tasks: dict[str, asyncio.Task] = {}

    async def say(self, text: str) -> None:
        log.info("%s", text)
        if self.game.log is not None:
            await self.game.say(text)

    # ---- what the game asks -------------------------------------------------

    def circuits(self) -> set[str]:
        """Every circuit a free call is using: its caller and its answerer."""
        out = set()
        for fc in self.calls.values():
            out.add(fc.caller)
            if fc.callee:
                out.add(fc.callee)
        return out

    def callers(self) -> set[str]:
        return {fc.caller for fc in self.calls.values()}

    def routing(self) -> bool:
        """Some free caller is answered and waiting to be put through."""
        return any(fc.answered and not fc.callee for fc in self.calls.values())

    def holdings(self) -> list[Holding]:
        """What the free calls hold for dealing (§6.1): the caller's line, and
        the answerer's line and person."""
        out = []
        for fc in self.calls.values():
            lines = {fc.line} if fc.line else set()
            if fc.caller == PHONE:
                lines |= set(self.game.station_lines.get(PHONE_STATION, ()))
            out.append(Holding(frozenset(lines), frozenset({fc.who} if fc.who else ())))
        return out

    def claimable_ring(self, b: Board) -> str:
        """A room rung that is a free call's to take: fitted, not station 24,
        not in a game call or another free call, and not the room a routing
        game call wants."""
        busy = self.game.circuits_in_calls(free=False) | self.circuits()
        wanted = self.game.wanted_stations()
        for n in fitted_stations(self.game.cfg.stations):
            if n == PHONE_STATION or n in wanted:
                continue
            c = f"station/{n}"
            if b.on(f"{c}/ring") and c not in busy:
                return c
        return ""

    def claimable_trunk(self, b: Board, caller: str) -> str:
        """A trunk seized for this caller: not the public line, not in a game
        call, and patched to the caller by the operator's cord."""
        busy = self.game.circuits_in_calls(free=False) | self.circuits()
        for k in self.game.cfg.fitted_trunks():
            t = f"trunk/{k}"
            if k == self.game.cfg.public_trunk or t in busy:
                continue
            if b.on(f"{t}/seize") and b.get(f"{t}/peer") == caller:
                return t
        return ""

    # ---- running -----------------------------------------------------------

    def _wants(self, b: Board) -> list[str]:
        """The callers that should have a free call now."""
        out = []
        if PHONE_STATION in fitted_stations(self.game.cfg.stations) and b.on(f"{PHONE}/lifted"):
            out.append(PHONE)
        p = self.game.cfg.public_trunk
        if p and b.on(f"trunk/{p}/seize") and b.on(f"trunk/{p}/op"):
            out.append(f"trunk/{p}")
        return out

    def _start(self, caller: str) -> None:
        if caller in self.tasks or self.game.hw is None:
            return
        fc = FreeCall(self, caller)
        self.calls[caller] = fc
        self.tasks[caller] = asyncio.create_task(self._one(fc), name=f"free:{caller}")

    async def _one(self, fc: FreeCall) -> None:
        try:
            await fc.run()
        except asyncio.CancelledError:
            raise
        except (Offline, Gone) as e:
            log.info("free call %s: %s", fc.caller, e)
        except Exception:
            log.exception("free call %s", fc.caller)
            await asyncio.sleep(RETRY)
        finally:
            self.calls.pop(fc.caller, None)
            self.tasks.pop(fc.caller, None)
        # Still lifted, or still up: a new free call, once it settles.
        if fc.caller in self._wants(self.game.b):
            await asyncio.sleep(RETRY)
            if fc.caller in self._wants(self.game.b):
                self._start(fc.caller)

    async def run(self) -> None:
        """Start a free call whenever a caller appears."""
        for caller in self._wants(self.game.b):
            self._start(caller)
        async for ch in self.game.b.watch():
            if ch.key.endswith(("/lifted", "/seize", "/op")):
                for caller in self._wants(self.game.b):
                    self._start(caller)

    async def close(self) -> None:
        for t in list(self.tasks.values()):
            t.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
