"""Free calls, Lenny mode (game_control.md §8), against the echoing fake
controller and audio program of harness.py. No broker, no hardware.
"""

import asyncio

import pytest

import sbgame.dialling as dialling
import sbgame.freecall as fcm
from sbgame.board import Board
from sbgame.config import Config
from sbgame.deck import Holding
from sbgame.freecall import FreeCalls
from sbgame.link import Hw
from sbgame.script_data import FreeLines, Speech

from harness import FakeLink, D, HOLD


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    """The module's waits at the tests' speed."""
    for mod, name, v in ((fcm, "LISTEN", D * 10), (fcm, "LISTEN_AGAIN", D * 15),
                         (fcm, "TURN_END", D * 3), (fcm, "PATCH_WAIT", D * 10),
                         (dialling, "DIAL_DELAY", D), (fcm, "DIAL_FIRST", D * 20),
                         (dialling, "DIAL_PAUSE", D * 8), (dialling, "DIAL_SETTLE", D * 5),
                         (fcm, "RINGBACK_KNOWN", D), (fcm, "RINGBACK_LENNY", D * 2),
                         (fcm, "RETRY", D * 5), (fcm, "ROOM_ANSWER", D * 4)):
        monkeypatch.setattr(mod, name, v)


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
        self.station_lines = {21: frozenset({"room403"}), 24: frozenset({"phone"})}
        self.log = object()
        self.said: list[str] = []
        self.monitored: list[str] = []
        self.wanted: set[int] = set()
        self.in_calls: set[str] = set()
        self.free = FreeCalls(self)

    async def say(self, text: str) -> None:
        self.said.append(text)

    async def monitor(self, src: str, peer: str = "auto") -> None:
        self.monitored.append(src)
        self.peer = peer

    def circuits_in_calls(self, free: bool = True) -> set[str]:
        return set(self.in_calls) | (self.free.circuits() if free else set())

    def wanted_stations(self) -> set[int]:
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


async def test_phone_to_room() -> None:
    """The phone, put through to room 403 (§8)."""
    g = StubGame()
    await g.live()
    runner = asyncio.create_task(g.free.run())
    b = g.b
    await b.update("station/24/lifted", "on")
    await until(b, lambda b: b.on("station/24/hook"))
    # lifted: station 24's relay closes
    await b.update("station/24/op", "on")
    await until(b, lambda b: g.monitored == ["station/24"])
    assert "free call: phone answered" in g.said, "answered: logged, and the loudspeaker moves to it"
    assert g.peer == "6", "with the peer boost fixed at 6dB"
    assert g.free.routing(), "routing until she puts it through"

    g.wanted = {21}
    await b.update("station/21/ring", "on")
    await asyncio.sleep(D * 5)
    assert not b.on("station/21/hook"), "a room a game call wants is that call's"
    g.wanted = set()
    await b.update("station/21/ring", "off")
    await asyncio.sleep(D)
    await b.update("station/21/ring", "on")
    await asyncio.sleep(fcm.ROOM_ANSWER / 2)
    assert not b.on("station/21/hook"), "a room rung: not at once"
    await until(b, lambda b: b.on("station/21/hook"))
    # a room rung: it answers after ROOM_ANSWER
    await b.update("station/21/ring", "off")
    await b.update("station/21/peer", "station/24")
    await b.update("station/24/peer", "station/21")
    await until(b, lambda b: len(g.played("station/21")) >= 7, 10)
    p = g.played("station/21")
    assert (p[:7] == ["free.thornhill.g", "free.thornhill.1", "free.thornhill.2", "free.thornhill.3",
                    "free.thornhill.4", "free.thornhill.5", "free.thornhill.2"]), f"greeting, his line, then the loop round: {p[:7]}"
    assert any("phone to room403, thornhill answers" in s for s in g.said), "logged who answers"
    held = g.free.holdings()
    assert held == [Holding(frozenset({"room403", "phone"}), frozenset({"thornhill"}))], f"holds the lines and the person: {held}"
    assert g.free.circuits() == {"station/24", "station/21"}, "its circuits"

    await b.update("station/24/lifted", "off")
    await until(b, lambda b: not b.on("station/21/hook") and not b.on("station/24/hook"))
    # hung up: the room and station 24's relay open
    await until(b, lambda b: "free call: phone hung up" in g.said)
    assert not g.free.circuits(), "and the free call is gone"
    runner.cancel()


async def test_cord_out_then_again() -> None:
    """The cord pulled: back to waiting, then put through again."""
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
    # cord out: the room hangs up
    await until(b, lambda b: g.free.routing())
    assert g.free.circuits() == {"station/24"}, "and the caller waits again"
    await b.update("station/24/lifted", "off")
    await until(b, lambda b: not g.free.circuits())
    runner.cancel()


async def test_nobody_patched() -> None:
    """A room answers and no cord comes (§3.5)."""
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
    assert g.played("station/21") == ["hello.thornhill"], "Hello?, then it hangs up"
    assert g.free.routing(), "and the caller waits again"
    await b.update("station/24/lifted", "off")
    await until(b, lambda b: not g.free.circuits())
    runner.cancel()


async def test_silent_caller() -> None:
    """A caller who says nothing: Hello? soon, then less often."""
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
    assert p[:3] == ["free.thornhill.g", "hello.thornhill", "hello.thornhill"], f"greeting, then Hello? and Hello? again, no line: {p[:3]}"
    want = [D * 2 + fcm.LISTEN, D * 2 + fcm.LISTEN_AGAIN]
    assert all(abs(a - b) < 1e-6 for a, b in zip(g.link.listens[:2], want)) and len(g.link.listens) >= 2, f"each listen from the line's start, the line and LISTEN, then LISTEN_AGAIN: {g.link.listens[:2]}"
    await b.update("station/24/lifted", "off")
    await until(b, lambda b: not g.free.circuits())
    runner.cancel()


@pytest.mark.parametrize("number, who, ringback",
                         [("2835678", "maitre_d", "known"), ("5551212", "lenny", "unknown")])
async def test_public_line_out(number: str, who: str, ringback: str) -> None:
    """The public line: a number dialled on trunk 3."""
    g = StubGame()
    await g.live()
    runner = asyncio.create_task(g.free.run())
    b = g.b
    await b.update("trunk/8/seize", "on")
    await asyncio.sleep(D * 3)
    assert not g.free.circuits(), "seized but not answered: nothing yet"
    await b.update("trunk/8/op", "on")
    await until(b, lambda b: g.free.routing())
    assert g.free.circuits() == {"trunk/8"}, "answered: a free call"
    await b.update("trunk/3/seize", "on")
    await asyncio.sleep(D * 3)
    assert not g.sent("trunk/3/tone/set"), "a trunk not patched to the caller is not its"
    await b.update("trunk/3/peer", "trunk/8")
    await until(b, lambda b: b.get("trunk/3/tone") == "dial")
    # patched: dial tone
    for d in number:
        await b.update("trunk/3/digit", d)
        await asyncio.sleep(D / 2)
    await until(b, lambda b: f"free.{who}.g" in g.played("trunk/3"))
    tones = g.sent("trunk/3/tone/set")
    assert tones[:4] == ["dial", "off", "ringback", "off"], f"dial tone, ringback: {tones[:4]}"
    assert any(f"dialled {number}" in s and f"{who} answers" in s for s in g.said), f"{who} answers"
    await until(b, lambda b: len(g.played("trunk/3")) >= 3)
    await b.update("trunk/8/seize", "off")
    await until(b, lambda b: not g.free.circuits())
    assert g.sent("trunk/3/play/set")[-1] == "stop", "the caller gone: the trunk's file stops"
    runner.cancel()


async def test_public_line_short() -> None:
    """Three digits and a pause: fast busy, not Lenny."""
    g = StubGame()
    await g.live()
    runner = asyncio.create_task(g.free.run())
    b = g.b
    await b.update("trunk/8/seize", "on")
    await b.update("trunk/8/op", "on")
    await until(b, lambda b: g.free.routing())
    await b.update("trunk/3/seize", "on")
    await b.update("trunk/3/peer", "trunk/8")
    await until(b, lambda b: b.get("trunk/3/tone") == "dial")
    for d in "283":
        await b.update("trunk/3/digit", d)
        await asyncio.sleep(D / 2)
    await asyncio.sleep(dialling.DIAL_PAUSE / 2)
    assert b.get("trunk/3/tone") != "reorder", "a pause shorter than DIAL_PAUSE: still dialling"
    await until(b, lambda b: b.get("trunk/3/tone") == "reorder")
    assert not g.played("trunk/3"), "then fast busy, and nobody answers"
    assert any("too few digits" in s for s in g.said), "logged as too few digits"
    await b.update("trunk/3/seize", "off")
    await until(b, lambda b: g.sent("trunk/3/tone/set")[-1] == "off")
    # released: the fast busy stops
    await b.update("trunk/8/seize", "off")
    await until(b, lambda b: not g.free.circuits())
    runner.cancel()


async def test_scene_trunk_rules() -> None:
    """The routing flows leave the public line and a free call's trunk alone."""
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
    assert _fresh(ctx)(b) is None, "the public line is never a scene's"
    await b.update("trunk/2/seize", "on")
    await b.update("trunk/2/peer", "station/24")
    assert _fresh(ctx)(b) is None, "nor a trunk patched to a free caller"
    await b.update("trunk/4/seize", "on")
    assert _fresh(ctx)(b) == 4, "any other trunk seized is"
