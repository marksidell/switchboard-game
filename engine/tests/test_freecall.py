"""Free calls, Lenny mode (game_control.md §4.12, Rev 74), against the echoing
fake controller and audio program of the sim harness. No broker, no hardware.

    cd engine && PYTHONPATH=.:tests ./.venv/bin/python tests/test_freecall.py
"""

import asyncio
import logging
import sys

import sbgame.freecall as fcm
from sbgame.board import Board
from sbgame.config import Config
from sbgame.deck import Holding
from sbgame.freecall import FreeCalls
from sbgame.link import Hw
from sbgame.script_data import FreeLines, Speech

from test_sim import FakeLink, D, HOLD

logging.basicConfig(level=logging.WARNING, stream=sys.stdout)

# The module's waits at the tests' speed.
fcm.LISTEN = D * 10
fcm.LISTEN_AGAIN = D * 15
fcm.TURN_END = D * 3
fcm.PATCH_WAIT = D * 10
fcm.DIAL_DELAY = D
fcm.DIAL_FIRST = D * 20
fcm.DIAL_PAUSE = D * 5
fcm.RINGBACK_KNOWN = D
fcm.RINGBACK_LENNY = D * 2
fcm.RETRY = D * 5

failures = 0


def check(ok: bool, what: str) -> None:
    global failures
    print(f"    {what:<60} {'ok' if ok else 'FAIL'}")
    if not ok:
        failures += 1


class Talker(FakeLink):
    """The caller speaks once per turn: a listen as short as TURN_END hears
    nothing, so the answerer's turn comes; any longer one hears speech."""

    async def _echo(self, key: str, p: str) -> None:
        if key.endswith("/listen/set") and p != "0" and float(p) <= fcm.TURN_END:
            base = key.removesuffix("/set")
            await asyncio.sleep(D)
            await self.b.update(base, "listening")
            await asyncio.sleep(float(p))
            await self.b.update(base, "timeout")
            return
        await super()._echo(key, p)


class Silent(FakeLink):
    """The caller never speaks: every listen times out."""

    async def _echo(self, key: str, p: str) -> None:
        if key.endswith("/listen/set") and p != "0":
            base = key.removesuffix("/set")
            self.listens.append(float(p))
            await self.b.update(base, "listening")
            await asyncio.sleep(float(p))
            await self.b.update(base, "timeout")
            return
        await super()._echo(key, p)


def lines(who: str, n_lines: int, n_loop: int) -> FreeLines:
    sp = lambda i: Speech(f"free.{who}.{i}", D * 2, "called")
    return FreeLines(Speech(f"free.{who}.g", D * 2, "called"),
                     tuple(sp(i) for i in range(1, n_lines + 1)),
                     tuple(sp(i) for i in range(n_lines + 1, n_lines + n_loop + 1)))


class GS:
    """The parts of GameScript that free calls read."""
    freecall = {"thornhill": lines("thornhill", 1, 4), "maitre_d": lines("maitre_d", 0, 2),
                "lenny": lines("lenny", 5, 10)}
    free_station = {21: "thornhill", 9: "nobody"}
    free_outside = {"canlis": "maitre_d"}
    numbers = {"2835678": "canlis"}

    def answerer(self, who):
        if who in self.freecall:
            return who, self.freecall[who]
        return "lenny", self.freecall["lenny"]

    def reaction(self, kind, voice):
        return Speech(f"{kind}.{voice}", D * 2, "caller") if kind == "hello" else None


class StubGame:
    def __init__(self, link=None) -> None:
        self.b = Board(hold=HOLD)
        self.link = (link or Talker)(self.b)
        self.link.listens = []
        self.hw = Hw(self.link)
        self.gs = GS()
        self.cfg = Config()
        self._station_lines = {21: frozenset({"room403"}), 24: frozenset({"phone"})}
        self.log = object()
        self.said: list[str] = []
        self.monitor: list[str] = []
        self.wanted: set[int] = set()
        self.in_calls: set[str] = set()
        self.free = FreeCalls(self)

    async def _say(self, text: str) -> None:
        self.said.append(text)

    async def _monitor(self, src: str) -> None:
        self.monitor.append(src)

    def _circuits_in_calls(self, free: bool = True) -> set[str]:
        return set(self.in_calls) | (self.free.circuits() if free else set())

    def _wanted_stations(self) -> set[int]:
        return set(self.wanted)

    async def live(self) -> None:
        await self.b.set_broker(True)
        await self.b.update("ctl/status", "online")
        await self.b.update("ctl/audio_status", "online")
        await self.b.update("ctl/esp_heartbeat", "1")

    def sent(self, key: str) -> list[str]:
        return [p for k, p in self.link.sent if k == key]

    def played(self, circuit: str) -> list[str]:
        return [p for p in self.sent(f"{circuit}/play/set") if p != "stop"]


async def until(b: Board, pred, t: float = 5.0):
    """Poll: some conditions are on the stub, not the board, and wake nothing."""
    async with asyncio.timeout(t):
        while not (r := pred(b)):
            await asyncio.sleep(D / 4)
        return r


async def phone_to_room() -> None:
    print("\n== the phone, put through to room 403 (§4.12)")
    g = StubGame()
    await g.live()
    runner = asyncio.create_task(g.free.run())
    b = g.b
    await b.update("station/24/lifted", "on")
    await until(b, lambda b: b.on("station/24/hook"))
    check(True, "lifted: station 24's relay closes")
    await b.update("station/24/op", "on")
    await until(b, lambda b: g.monitor == ["station/24"])
    check("free call: phone answered" in g.said, "answered: logged, and the loudspeaker moves to it")
    check(g.free.routing(), "routing until she puts it through")

    g.wanted = {21}
    await b.update("station/21/ring", "on")
    await asyncio.sleep(D * 5)
    check(not b.on("station/21/hook"), "a room a game call wants is that call's")
    g.wanted = set()
    await b.update("station/21/ring", "off")
    await asyncio.sleep(D)
    await b.update("station/21/ring", "on")
    await until(b, lambda b: b.on("station/21/hook"))
    check(True, "a room rung: it answers")
    await b.update("station/21/ring", "off")
    await b.update("station/21/peer", "station/24")
    await b.update("station/24/peer", "station/21")
    await until(b, lambda b: len(g.played("station/21")) >= 7, 10)
    p = g.played("station/21")
    check(p[:7] == ["free.thornhill.g", "free.thornhill.1", "free.thornhill.2", "free.thornhill.3",
                    "free.thornhill.4", "free.thornhill.5", "free.thornhill.2"],
          f"greeting, his line, then the loop round: {p[:7]}")
    check(any("phone to room403, thornhill answers" in s for s in g.said), "logged who answers")
    held = g.free.holdings()
    check(held == [Holding(frozenset({"room403", "phone"}), frozenset({"thornhill"}))],
          f"holds the lines and the person: {held}")
    check(g.free.circuits() == {"station/24", "station/21"}, "its circuits")

    await b.update("station/24/lifted", "off")
    await until(b, lambda b: not b.on("station/21/hook") and not b.on("station/24/hook"))
    check(True, "hung up: the room and station 24's relay open")
    await until(b, lambda b: "free call: phone hung up" in g.said)
    check(not g.free.circuits(), "and the free call is gone")
    runner.cancel()


async def cord_out_then_again() -> None:
    print("\n== the cord pulled: back to waiting, then put through again")
    g = StubGame()
    await g.live()
    runner = asyncio.create_task(g.free.run())
    b = g.b
    await b.update("station/24/lifted", "on")
    await b.update("station/24/op", "on")
    await until(b, lambda b: g.free.routing())
    await b.update("station/21/ring", "on")
    await until(b, lambda b: b.on("station/21/hook"))
    await b.update("station/21/ring", "off")
    await b.update("station/21/peer", "station/24")
    await until(b, lambda b: "free.thornhill.g" in g.played("station/21"))
    await b.update("station/21/peer", "")
    await until(b, lambda b: not b.on("station/21/hook"))
    check(True, "cord out: the room hangs up")
    await until(b, lambda b: g.free.routing())
    check(g.free.circuits() == {"station/24"}, "and the caller waits again")
    await b.update("station/24/lifted", "off")
    await until(b, lambda b: not g.free.circuits())
    runner.cancel()


async def nobody_patched() -> None:
    print("\n== a room answers and no cord comes (§5, Rev 60)")
    g = StubGame()
    await g.live()
    runner = asyncio.create_task(g.free.run())
    b = g.b
    await b.update("station/24/lifted", "on")
    await b.update("station/24/op", "on")
    await until(b, lambda b: g.free.routing())
    await b.update("station/21/ring", "on")
    await until(b, lambda b: b.on("station/21/hook"))
    await b.update("station/21/ring", "off")
    await until(b, lambda b: not b.on("station/21/hook"))
    check(g.played("station/21") == ["hello.thornhill"], "Hello?, then it hangs up")
    check(g.free.routing(), "and the caller waits again")
    await b.update("station/24/lifted", "off")
    await until(b, lambda b: not g.free.circuits())
    runner.cancel()


async def silent_caller() -> None:
    print("\n== a caller who says nothing: Hello? soon, then less often (Rev 78)")
    g = StubGame(Silent)
    await g.live()
    runner = asyncio.create_task(g.free.run())
    b = g.b
    await b.update("station/24/lifted", "on")
    await b.update("station/24/op", "on")
    await until(b, lambda b: g.free.routing())
    await b.update("station/21/ring", "on")
    await until(b, lambda b: b.on("station/21/hook"))
    await b.update("station/21/ring", "off")
    await b.update("station/21/peer", "station/24")
    await b.update("station/24/peer", "station/21")
    await until(b, lambda b: g.played("station/21").count("hello.thornhill") >= 2, 10)
    p = g.played("station/21")
    check(p[:3] == ["free.thornhill.g", "hello.thornhill", "hello.thornhill"],
          f"greeting, then Hello? and Hello? again, no line: {p[:3]}")
    check(g.link.listens[:2] == [fcm.LISTEN, fcm.LISTEN_AGAIN],
          f"the first wait LISTEN, then LISTEN_AGAIN: {g.link.listens[:2]}")
    await b.update("station/24/lifted", "off")
    await until(b, lambda b: not g.free.circuits())
    runner.cancel()


async def public_line_out(number: str, who: str, ringback: str) -> None:
    print(f"\n== the public line, {number} dialled on trunk 3")
    g = StubGame()
    await g.live()
    runner = asyncio.create_task(g.free.run())
    b = g.b
    await b.update("trunk/8/seize", "on")
    await asyncio.sleep(D * 3)
    check(not g.free.circuits(), "seized but not answered: nothing yet")
    await b.update("trunk/8/op", "on")
    await until(b, lambda b: g.free.routing())
    check(g.free.circuits() == {"trunk/8"}, "answered: a free call")
    await b.update("trunk/3/seize", "on")
    await asyncio.sleep(D * 3)
    check(not g.sent("trunk/3/tone/set"), "a trunk not patched to the caller is not its")
    await b.update("trunk/3/peer", "trunk/8")
    await until(b, lambda b: b.get("trunk/3/tone") == "dial")
    check(True, "patched: dial tone")
    for d in number:
        await b.update("trunk/3/digit", d)
        await asyncio.sleep(D / 2)
    await until(b, lambda b: f"free.{who}.g" in g.played("trunk/3"))
    tones = g.sent("trunk/3/tone/set")
    check(tones[:4] == ["dial", "off", "ringback", "off"], f"dial tone, ringback: {tones[:4]}")
    check(any(f"dialled {number}" in s and f"{who} answers" in s for s in g.said),
          f"{who} answers")
    await until(b, lambda b: len(g.played("trunk/3")) >= 3)
    await b.update("trunk/8/seize", "off")
    await until(b, lambda b: not g.free.circuits())
    check(g.sent("trunk/3/play/set")[-1] == "stop", "the caller gone: the trunk's file stops")
    runner.cancel()


async def scene_trunk_rules() -> None:
    print("\n== the routing flows leave the public line and a free call's trunk alone")
    from sbgame.flows import Ctx, _fresh
    from sbgame.calls import Call, Slots
    from sbgame.script_data import SceneDef
    b = Board(hold=HOLD)
    sc = SceneDef(id="t", shape="station_to_outside", from_line="a", to_line="b",
                  from_station=12, to_station=None, dial="1", busy=False,
                  request=Speech("t.1", 1, "caller"), conversation=())

    async def pub(k, v):
        pass
    ctx = Ctx(board=b, hw=None, cfg=Config(), slots=Slots(pub), call=Call(1, 1, "t", "a", "b"),
              scene=sc, say_event=lambda t: None, mark_connected=None, set_monitor=None,
              free_callers=lambda: {"station/24"}, public_trunk=8)
    await b.update("trunk/8/seize", "on")
    check(_fresh(ctx)(b) is None, "the public line is never a scene's")
    await b.update("trunk/2/seize", "on")
    await b.update("trunk/2/peer", "station/24")
    check(_fresh(ctx)(b) is None, "nor a trunk patched to a free caller")
    await b.update("trunk/4/seize", "on")
    check(_fresh(ctx)(b) == 4, "any other trunk seized is")


async def main() -> int:
    await phone_to_room()
    await cord_out_then_again()
    await nobody_patched()
    await silent_caller()
    await public_line_out("2835678", "maitre_d", "known")
    await public_line_out("5551212", "lenny", "unknown")
    await scene_trunk_rules()
    print("\nall passed" if not failures else f"\nFAILURES: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
