"""Every call flow, against the simulated controller, audio program and operator.

No broker and no hardware — which, until the PCBs arrive, is the whole of the
verification. Each case drives one shape of scene through a scripted operator
and asserts the outcome, the §4.3 connected milestone, the §6.1 stages seen,
and that the flow cleaned up after itself.

The operator is a coroutine per case. A *good* operator does the right thing;
the failure cases are operators who do the wrong thing, or nothing.
"""

import asyncio
import logging
import sys

import sbgame.flows as flows
from sbgame.board import Board
from sbgame.calls import Call, Reason, Slots, Stage
from sbgame.config import Config
from sbgame.flows import Ctx, busy_scene, outside_to_station, station_to_station, \
    station_to_outside, to_operator
from sbgame.link import Hw
from sbgame.script_data import SceneDef, Shape, Speech

from test_sim import FakeLink, D, HOLD           # the echoing fake from the sim harness

logging.basicConfig(level=logging.WARNING, stream=sys.stdout)

failures = 0


def check(ok: bool, what: str) -> None:
    global failures
    print(f"    {what:<56} {'ok' if ok else 'FAIL'}")
    if not ok:
        failures += 1


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


# ------------------------------------------------------------- operators ----


async def answers(h: Harness, circuit: str) -> None:
    """Wait for the line to signal, then throw the listening key."""
    if circuit.startswith("station"):
        await h.b.wait_until(lambda b: b.on(f"{circuit}/hook"), 5)
    else:
        await h.b.wait_until(lambda b: b.on(f"{circuit}/ring"), 5)
    await asyncio.sleep(D)
    await h.b.update(f"{circuit}/op", "on")


async def request_heard(h: Harness, circuit: str) -> None:
    await h.b.wait_until(lambda b: b.get(f"{circuit}/play") == "t.1", 5)
    await h.b.wait_until(lambda b: not b.get(f"{circuit}/play"), 5)


async def good_station_operator(h: Harness) -> None:
    c, want = "station/12", 2
    await answers(h, c)
    await request_heard(h, c)
    await h.b.update(f"station/{want}/ring", "on")
    await h.b.wait_until(lambda b: b.on(f"station/{want}/hook"), 5)
    await h.b.update(f"station/{want}/ring", "off")
    await h.b.update(f"{c}/peer", f"station/{want}")
    await h.b.update(f"station/{want}/peer", c)


async def wrong_then_right_operator(h: Harness) -> None:
    """Rings 7, realises, then rings 2. §5: not a failure."""
    c, want = "station/12", 2
    await answers(h, c)
    await request_heard(h, c)
    await h.b.update("station/7/ring", "on")
    await asyncio.sleep(D * 4)
    await h.b.update("station/7/ring", "off")        # nobody answered it
    await asyncio.sleep(D * 2)
    await h.b.update(f"station/{want}/ring", "on")
    await h.b.wait_until(lambda b: b.on(f"station/{want}/hook"), 5)
    await h.b.update(f"station/{want}/ring", "off")
    await h.b.update(f"{c}/peer", f"station/{want}")
    await h.b.update(f"station/{want}/peer", c)


async def never_answers(h: Harness) -> None:
    await asyncio.sleep(30)


async def cuts_off(h: Harness) -> None:
    await good_station_operator(h)
    await asyncio.sleep(D * 4)
    await h.b.update("station/12/peer", "")          # yank the cord mid-conversation
    await h.b.update("station/2/peer", "")


async def switch_glitch(h: Harness) -> None:
    """Her switch moved mid-conversation: both lines break for a moment, read
    deaf and then idle, and come back (§5, Rev 45). The call rides through."""
    await good_station_operator(h)
    await asyncio.sleep(D * 4)
    for v in ("deaf", ""):
        await h.b.update("station/12/peer", v)
        await h.b.update("station/2/peer", v)
        await asyncio.sleep(HOLD / 4)
    await h.b.update("station/12/peer", "station/2")
    await h.b.update("station/2/peer", "station/12")


async def pulls_the_cord_before_routing(h: Harness) -> None:
    """She answers, hears the request, and pulls the answering cord before
    taking a trunk (§5, Rev 46): the caller is lost, and the call abandoned."""
    c = "station/12"
    await answers(h, c)
    await request_heard(h, c)
    await h.b.update(f"{c}/op", "off")
    await asyncio.sleep(60)


async def outgoing_operator(h: Harness, number: str, answer: bool = True) -> None:
    c = "station/12"
    await answers(h, c)
    await request_heard(h, c)
    await h.b.update("trunk/3/seize", "on")
    await h.b.update("trunk/3/peer", c)
    await h.b.update(f"{c}/peer", "trunk/3")     # both ends, as the controller does
    await h.b.wait_until(lambda b: b.get("trunk/3/tone") == "dial", 5)
    for i, d in enumerate(number):
        await asyncio.sleep(D / 2)
        await h.b.update("trunk/3/digit", d)
        if i == 0:                                    # dial tone stops (§5, Rev 42)
            await h.b.wait_until(lambda b: b.get("trunk/3/tone") != "dial", 5)


async def wrong_then_right_number(h: Harness) -> None:
    c = "station/12"
    await answers(h, c)
    await request_heard(h, c)
    await h.b.update("trunk/3/seize", "on")
    await h.b.update("trunk/3/peer", c)
    await h.b.update(f"{c}/peer", "trunk/3")     # both ends, as the controller does
    await h.b.wait_until(lambda b: b.get("trunk/3/tone") == "dial", 5)
    for d in "2759999":                               # wrong
        await asyncio.sleep(D / 2)
        await h.b.update("trunk/3/digit", d)
    await asyncio.sleep(D * 3)
    assert h.b.get("trunk/3/tone") == "busy", h.b.get("trunk/3/tone")   # Rev 46
    await h.b.update("trunk/3/seize", "off")          # release clears dialled
    await asyncio.sleep(D)
    await h.b.update("trunk/3/seize", "on")
    await h.b.update("trunk/3/peer", c)
    await h.b.update(f"{c}/peer", "trunk/3")
    await h.b.wait_until(lambda b: b.get("trunk/3/tone") == "dial", 5)
    for d in "2754101":                               # right
        await asyncio.sleep(D / 2)
        await h.b.update("trunk/3/digit", d)


async def speaks_when_asked(h: Harness) -> None:
    """For calls to the operator and busy scenes: she answers and then talks."""
    c = "station/12"
    await answers(h, c)
    # The fake audio program drives listen through speech to silence by itself,
    # so there is nothing more for the operator to do.
    await asyncio.sleep(60)


async def answers_the_trunk(h: Harness) -> None:
    """A call to the operator rung in on trunk 3: she answers and waits."""
    await answers(h, "trunk/3")
    await asyncio.sleep(60)


async def incoming_operator(h: Harness) -> None:
    c, want = "trunk/3", 2
    await answers(h, c)
    await request_heard(h, c)
    await h.b.update(f"station/{want}/ring", "on")
    await h.b.wait_until(lambda b: b.on(f"station/{want}/hook"), 5)
    await h.b.update(f"station/{want}/ring", "off")
    await h.b.update(f"{c}/peer", f"station/{want}")
    await h.b.update(f"station/{want}/peer", c)


# ----------------------------------------------------------------- cases ----


async def main() -> int:
    print("\n== station to station, a good operator")
    h = Harness(scene(Shape.STATION_TO_STATION))
    r = await h.run(station_to_station, good_station_operator)
    check(r.ok, "succeeds")
    check(h.connected, "reports connected (§4.3)")
    check(h.monitor == ["station/12"], f"moved the monitor once, to the caller: {h.monitor}")
    check(h.stages == [Stage.SIGNALLING, Stage.REQUEST, Stage.ROUTING,
                       Stage.RINGING, Stage.TALKING], f"stages {h.stages}")
    check(("station/12/hook/set", "off") in h.link.sent
          and ("station/2/hook/set", "off") in h.link.sent, "hung both up in finally")

    print("\n== the operator rings the wrong station, then the right one")
    h = Harness(scene(Shape.STATION_TO_STATION))
    r = await h.run(station_to_station, wrong_then_right_operator)
    check(r.ok, "still succeeds — a wrong connection is not a failure (§5)")
    check(any("wanted 2" in e for e in h.events), f"logged the wrong station: {h.events}")

    print("\n== nobody answers the lamp")
    h = Harness(scene(Shape.STATION_TO_STATION))
    h.ctx.cfg.answer_timeout = 0.3
    r = await h.run(station_to_station, never_answers)
    check(not r.ok and r.reason == Reason.NO_ANSWER, f"fails as 'no answer': {r.reason!r}")
    check(not h.connected, "never reports connected")

    print("\n== the operator answers but never connects")
    h = Harness(scene(Shape.STATION_TO_STATION))
    h.ctx.cfg.connect_timeout = 0.3
    async def answers_only(hh):
        await answers(hh, "station/12")
        await asyncio.sleep(30)
    r = await h.run(station_to_station, answers_only)
    check(not r.ok and r.reason == Reason.NOT_CONNECTED, f"fails as 'not connected': {r.reason!r}")

    print("\n== a cord is pulled during the conversation")
    h = Harness(scene(Shape.STATION_TO_STATION))
    r = await h.run(station_to_station, cuts_off)
    check(not r.ok and r.reason == Reason.CUT_OFF, f"fails as 'cut off': {r.reason!r}")
    check(h.connected, "was connected before it was cut")

    print("\n== her switch breaks both lines for a moment (§5, Rev 45)")
    h = Harness(scene(Shape.STATION_TO_STATION))
    r = await h.run(station_to_station, switch_glitch)
    check(r.ok, f"the call rides through: {r.reason!r}")

    print("\n== the caller lost before connecting is abandoned (§5, Rev 46)")
    was = flows.ABANDON
    flows.ABANDON = D * 10
    try:
        h = Harness(scene(Shape.STATION_TO_OUTSIDE, to_line="pizza", to_station=None,
                          dial="275-4101"))
        r = await h.run(station_to_outside, pulls_the_cord_before_routing)
        check(not r.ok and r.reason == Reason.CUT_OFF, f"fails as 'cut off': {r.reason!r}")
        check(any("lost" in e for e in h.events), f"and says so: {h.events}")
    finally:
        flows.ABANDON = was

    print("\n== station to outside")
    h = Harness(scene(Shape.STATION_TO_OUTSIDE, to_line="pizza", to_station=None,
                      dial="275-4101"))
    r = await h.run(station_to_outside, lambda hh: outgoing_operator(hh, "2754101"))
    check(r.ok, "succeeds")
    check(h.connected, "reports connected")
    check(any("dialled 275-4101" in e for e in h.events), f"logged the number: {h.events}")
    check(Stage.DIALLING in h.stages, f"went through dialling: {h.stages}")

    print("\n== long distance: a line that waits for the operator on the trunk (§4.6)")
    h = Harness(scene(Shape.STATION_TO_OUTSIDE, to_line="operator", to_station=None,
                      dial="0",
                      conversation=(speech("t.2", "called"),
                                    Speech("t.3", D * 3, "called", wait=True),
                                    speech("t.4", "caller"))))
    r = await h.run(station_to_outside, lambda hh: outgoing_operator(hh, "0"))
    check(r.ok, "succeeds")
    listens = [k for k, _ in h.link.sent if k.endswith("/listen/set")]
    check(listens.count("trunk/3/listen/set") == 1, f"listened once on the trunk: {listens}")

    print("\n== a line with pause: and ringback: (§4.6, Rev 20)")
    h = Harness(scene(Shape.STATION_TO_OUTSIDE, to_line="operator", to_station=None,
                      dial="0",
                      conversation=(speech("t.2", "called"),
                                    Speech("t.3", D * 3, "called", pause=D * 4),
                                    Speech("t.4", D * 3, "called", ringback=D * 4),
                                    speech("t.5", "caller"))))
    t0 = asyncio.get_running_loop().time()
    r = await h.run(station_to_outside, lambda hh: outgoing_operator(hh, "0"))
    took = asyncio.get_running_loop().time() - t0
    check(r.ok, "succeeds")
    tones = [v for k, v in h.link.sent if k == "trunk/3/tone/set"]
    i = max(i for i, v in enumerate(tones) if v == "ringback")
    check("off" in tones[i + 1:], f"ringback, then off, on the trunk: {tones}")
    check(took >= D * 8, f"both waits taken: {took:.2f}s")

    print("\n== ringback: on the calling side of a call in (§4.6, Rev 21)")
    h = Harness(scene(Shape.OUTSIDE_TO_STATION, from_line="operator", from_station=None,
                      to_line="room105", to_station=2,
                      conversation=(speech("t.2", "called"),
                                    Speech("t.3", D * 3, "caller", ringback=D * 3))))
    r = await h.run(outside_to_station, incoming_operator, 3)
    check(r.ok, "succeeds")
    tones = [v for k, v in h.link.sent if k == "trunk/3/tone/set"]
    check(tones[:2] == ["ringback", "off"], f"rang the incoming trunk, then stopped: {tones}")

    print("\n== the operator dials a wrong number, releases, and redials")
    h = Harness(scene(Shape.STATION_TO_OUTSIDE, to_line="pizza", to_station=None,
                      dial="275-4101"))
    r = await h.run(station_to_outside, wrong_then_right_number)
    check(r.ok, "still succeeds (§5)")
    check(any("wanted 275-4101" in e for e in h.events), f"logged the wrong number: {h.events}")

    print("\n== a busy scene")
    h = Harness(scene(Shape.BUSY, to_line="pizza", to_station=None, dial="275-4101",
                      busy=True, conversation=(speech("t.2", "caller"),)))
    r = await h.run(busy_scene, lambda hh: outgoing_operator(hh, "2754101"))
    check(r.ok, "succeeds")
    check(h.connected, "connected at busy tone (§4.3)")
    check(Stage.BUSY in h.stages, f"showed the busy stage: {h.stages}")

    print("\n== a call to the operator")
    h = Harness(scene(Shape.TO_OPERATOR, to_line="", to_station=None,
                      conversation=(speech("t.2", "caller"),)))
    r = await h.run(to_operator, speaks_when_asked)
    check(r.ok, "succeeds")
    check(h.connected, "connected when the request finished (§4.3)")
    check(Stage.OPERATOR in h.stages, f"showed the operator stage: {h.stages}")

    print("\n== time and charges: a call to the operator rung in on a trunk (Rev 24)")
    h = Harness(scene(Shape.TO_OPERATOR, from_line="operator", from_station=None,
                      to_line="", to_station=None, conversation=()))
    t0 = asyncio.get_running_loop().time()
    r = await h.run(to_operator, answers_the_trunk, 3)
    took = asyncio.get_running_loop().time() - t0
    check(r.ok, "succeeds")
    check(h.connected, "connected when the request finished (§4.3)")
    check(("trunk/3/shortring/set", "on") in h.link.sent, "rang the trunk once, short (Rev 28)")
    check(("trunk/3/ring/set", "off") in h.link.sent, "stopped ringing it once answered")
    check(h.monitor == ["trunk/3"], f"monitor followed the trunk: {h.monitor}")
    check(took < 5, f"hung up as soon as the request played, not waiting on her: {took:.2f}s")
    check(not any(k.startswith("station/") and k.endswith("/hook/set") for k, _ in h.link.sent),
          "took no station off-hook")

    print("\n== time and charges nobody answers")
    h = Harness(scene(Shape.TO_OPERATOR, from_line="operator", from_station=None,
                      to_line="", to_station=None, conversation=()))
    h.ctx.cfg.answer_timeout = 0.3
    r = await h.run(to_operator, never_answers, 3)
    check(not r.ok and r.reason == Reason.NO_ANSWER, f"fails as 'no answer': {r.reason!r}")
    check(("trunk/3/ring/set", "off") in h.link.sent, "and stops ringing the trunk")

    print("\n== a call in from outside")
    h = Harness(scene(Shape.OUTSIDE_TO_STATION, from_line="pizza", from_station=None,
                      to_line="room214", to_station=2))
    r = await h.run(outside_to_station, incoming_operator, 3)
    check(r.ok, "succeeds")
    check(h.monitor == ["trunk/3"], f"monitor followed the trunk: {h.monitor}")
    check(("trunk/3/shortring/set", "on") in h.link.sent, "rang the trunk once, short (Rev 28)")
    check(("trunk/3/ring/set", "on") not in h.link.sent, "and never with the cadence")
    check(("trunk/3/ring/set", "off") in h.link.sent, "stopped ringing the trunk")

    print("\n== if_busy: the called station engaged when the request ends (§4.11, Rev 39)")
    h = Harness(scene(Shape.STATION_TO_STATION, if_busy=(speech("t.9", "caller"),)))
    await h.b.update("station/2/hook", "on")         # the front desk is on another call
    r = await h.run(station_to_station, speaks_when_asked)
    check(r.ok, "succeeds")
    check(h.connected, "connected when found engaged (§4.3)")
    check(h.stages == [Stage.SIGNALLING, Stage.REQUEST, Stage.ROUTING, Stage.BUSY],
          f"stages {h.stages}")
    check(("station/12/play/set", "t.9") in h.link.sent, "played the if_busy: line")
    check(not any(k == "station/2/hook/set" for k, _ in h.link.sent),
          "left the engaged station to its own call")
    check(any("is engaged" in e for e in h.events), f"logged it: {h.events}")

    print("\n== if_busy: engaged while she routes")
    h = Harness(scene(Shape.STATION_TO_STATION, if_busy=(speech("t.9", "caller"),)))
    async def routes_slowly(hh):
        await answers(hh, "station/12")
        await request_heard(hh, "station/12")
        await asyncio.sleep(D * 4)
        await hh.b.update("station/2/hook", "on")    # another call takes it first
        await asyncio.sleep(60)
    r = await h.run(station_to_station, routes_slowly)
    check(r.ok and Stage.BUSY in h.stages, f"found engaged: {r.reason!r} {h.stages}")

    print("\n== if_busy: the station free, the call goes through as usual")
    h = Harness(scene(Shape.STATION_TO_STATION, if_busy=(speech("t.9", "caller"),)))
    r = await h.run(station_to_station, good_station_operator)
    check(r.ok and Stage.TALKING in h.stages and Stage.BUSY not in h.stages,
          f"talked: {h.stages}")
    check(("station/12/play/set", "t.9") not in h.link.sent, "and no if_busy: line")
    check(("station/2/hook/set", "off") in h.link.sent, "hung the called station up")

    print("\n" + ("FAILURES" if failures else "all flows passed"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
