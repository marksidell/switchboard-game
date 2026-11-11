"""What the engine's tests share: a fake link that echoes like the controller
and the audio program, a flow harness, and a whole game against them.

No broker and no hardware. FakeLink stands in for Link: each command is echoed
back into the Board as the real clients would echo it, after a short delay.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from sbgame.board import Board
from sbgame.calls import Call, Slots
from sbgame.config import Config
from sbgame.flows import Ctx
from sbgame.game import Game
from sbgame.link import Hw
from sbgame.script_data import SceneDef, Speech, build
from sbgame.session import SessionLog

ENGINE = Path(__file__).resolve().parent.parent
REPO = ENGINE.parent

D = 0.02            # echo delay
HOLD = 2 * D        # Board.HOLD at the tests' speed (game_control.md §4)


class FakeLink:
    def __init__(self, b: Board) -> None:
        self.b = b
        self.sent: list[tuple[str, str]] = []
        self.file_len = D * 3

    async def publish(self, key: str, payload: str = "") -> None:
        self.sent.append((key, payload))
        asyncio.get_running_loop().create_task(self._echo(key, payload))

    async def _echo(self, key: str, p: str) -> None:
        base = key.removesuffix("/set")
        u = self.b.update
        await asyncio.sleep(D)
        if base.endswith("/play"):
            if p == "stop":
                await u(base, "")
            elif p.startswith("nosuch"):
                await u(base, "missing")
            else:
                await u(base, p)
                await asyncio.sleep(self.file_len)
                if self.b.get(base) == p:
                    await u(base, "")
        elif base.endswith("/listen"):
            if p == "0":
                await u(base, "")
            else:
                await u(base, "listening")
                await asyncio.sleep(D)
                await u(base, "speech")
                await asyncio.sleep(D)
                await u(base, "silence")
        elif base.endswith("/tone"):
            await u(base, "" if p == "off" else p)
        elif base.endswith("/shortring"):   # one burst on the ring echo (control.md §8.4)
            ring = base.removesuffix("/shortring") + "/ring"
            await u(ring, p)
            if p == "on":
                await asyncio.sleep(D * 5)
                if self.b.get(ring) == "on":
                    await u(ring, "off")
        elif base == "ctl/power_cut":       # a 1s cut, then "off" (control.md §5.4)
            await u(base, p)
            if p == "on":
                await asyncio.sleep(D * 5)
                if self.b.get(base) == "on":
                    await u(base, "off")
        else:  # hook, ring
            await u(base, p)


class StateLink(FakeLink):
    """FakeLink plus Link.state, recording what the page would see."""

    def __init__(self, b: Board) -> None:
        super().__init__(b)
        self.state_v: dict[str, str] = {}
        self.state_order: list[tuple[str, str]] = []

    async def state(self, key: str, value: str) -> None:
        self.state_v[key] = value
        self.state_order.append((key, value))


async def bring_up(b: Board) -> None:
    """The broker, the controller and the audio program, all up."""
    await b.set_broker(True)
    await b.update("ctl/status", "online")
    await b.update("ctl/audio_status", "online")
    await b.update("ctl/esp_heartbeat", "1")
    assert b.control_up and b.audio_up


# ---- one call flow -----------------------------------------------------------


def speech(name: str, by: str) -> Speech:
    return Speech(name, D * 3, by)


def scene(shape: str, **kw) -> SceneDef:
    base = dict(id="t", shape=shape, from_line="a", to_line="b",
                from_station=12, to_station=2, dial="", busy=False,
                request=speech("t.1", "caller"),
                conversation=(speech("t.2", "called"), speech("t.3", "caller")))
    base.update(kw)
    return SceneDef(**base)


class Harness:
    """Board, fake link, slots and a Ctx, with what happened recorded."""

    def __init__(self, sc: SceneDef) -> None:
        self.b = Board(hold=HOLD)
        self.link = FakeLink(self.b)
        self.hw = Hw(self.link)
        self.events: list[str] = []
        self.stages: list[str] = []
        self.monitor: list[str] = []
        self.connected = False
        self.published: list[tuple[str, str]] = []
        self.slots = Slots(self._publish)
        self.call = Call(slot=1, number=1, scene=sc.id,
                         from_line=sc.from_line, to_line=sc.to_line)
        self.ctx = Ctx(board=self.b, hw=self.hw, cfg=Config(), slots=self.slots,
                       call=self.call, scene=sc,
                       say_event=self.events.append,
                       mark_connected=self._connected,
                       set_monitor=self._monitor)

    async def _publish(self, key: str, value: str) -> None:
        self.published.append((key, value))
        if key.endswith("/stage") and value:
            self.stages.append(value)

    async def _connected(self) -> None:
        self.connected = True

    async def _monitor(self, src: str) -> None:
        self.monitor.append(src)

    async def live(self) -> None:
        await self.b.set_broker(True)
        await self.b.update("ctl/status", "online")
        await self.b.update("ctl/audio_status", "online")
        await self.b.update("ctl/esp_heartbeat", "1")

    async def run(self, flow, operator, *args):
        await self.live()
        op = asyncio.create_task(operator(self))
        try:
            return await asyncio.wait_for(flow(self.ctx, *args), 20)
        finally:
            op.cancel()


async def answers(h: Harness, circuit: str) -> None:
    """Wait for the line to signal, then throw the listening key."""
    if circuit.startswith("station"):
        await h.b.wait_until(lambda b: b.on(f"{circuit}/hook"), 5)
    else:
        await h.b.wait_until(lambda b: b.on(f"{circuit}/ring"), 5)
    await asyncio.sleep(D)
    if circuit.startswith("trunk"):
        await h.b.update(f"{circuit}/seize", "on")      # the front cord in it
    await h.b.update(f"{circuit}/op", "on")


async def request_heard(h: Harness, circuit: str) -> None:
    await h.b.wait_until(lambda b: b.get(f"{circuit}/play") == "t.1", 5)
    await h.b.wait_until(lambda b: not b.get(f"{circuit}/play"), 5)


# ---- a whole game ------------------------------------------------------------


async def build_game(tmp: Path, wav: str | Path = REPO / "wav", **cfg_kw):
    """A Game on the real script.yml, born on a StateLink with every client up."""
    b = Board(hold=HOLD)
    link = StateLink(b)
    cfg = Config(script=str(REPO / "script.yml"), wav_dir=str(wav),
                 session_db=str(tmp / "s.db"), **cfg_kw)
    gs = build(cfg.resolved("script"), cfg.resolved("wav_dir"))
    sess = SessionLog(cfg.resolved("session_db"))
    await sess.open()
    g = Game(b, gs, cfg, sess)
    await g.on_birth(link)          # as the link does on connect
    await bring_up(b)
    return b, link, g, sess
