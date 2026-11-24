"""Every call flow, against the simulated controller, audio program and operator.

No broker and no hardware. Each case drives one shape of scene through a
scripted operator and asserts the outcome, the §3.3 connected milestone, the
§3.2 stages seen, and that the flow cleaned up after itself.

The operator is a coroutine per case. A *good* operator does the right thing;
the failure cases are operators who do the wrong thing, or nothing.
"""

import asyncio
import dataclasses
import time

import pytest

import sbgame.dialling as dialling
import sbgame.flows as flows
from sbgame.calls import Reason, Stage
from sbgame.flows import busy_scene, outside_to_station, station_to_station, \
    station_to_outside, to_operator
from sbgame.script_data import Shape, Speech

from harness import D, HOLD, FakeLink, Harness, answers, request_heard, scene, speech
from sbgame.link import Hw


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    """The flows' waits at the tests' speed: digits come D/2 apart (§3.5)."""
    monkeypatch.setattr(dialling, "DIAL_SETTLE", D)
    monkeypatch.setattr(dialling, "DIAL_PAUSE", D * 6)
    for name, v in (("NUDGE_AFTER", D * 4), ("PATCH_WAIT", D * 6), ("ANSWER_AFTER", D),
                    ("DIAL_FIRST", D * 10), ("BUSY_HOLD", D * 2), ("AWAY", D * 2),
                    ("FLICK", D)):
        monkeypatch.setattr(flows, name, v)


# ------------------------------------------------------------- operators ----


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
    """Rings 7, realises, then rings 2. §3.5: not a failure."""
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
    deaf and then idle, and come back (§4). The call rides through."""
    await good_station_operator(h)
    await asyncio.sleep(D * 4)
    for v in ("deaf", ""):
        await h.b.update("station/12/peer", v)
        await h.b.update("station/2/peer", v)
        await asyncio.sleep(HOLD / 4)
    await h.b.update("station/12/peer", "station/2")
    await h.b.update("station/2/peer", "station/12")


async def power_reset(h: Harness) -> None:
    """The switchboard reset mid-conversation (§2): every line drops
    for longer than HOLD, and comes back. The call rides through."""
    await good_station_operator(h)
    await asyncio.sleep(D * 4)
    await h.b.update("ctl/power_cut", "on")
    for c in ("station/12", "station/2"):
        await h.b.update(f"{c}/peer", "")
        await h.b.update(f"{c}/op", "off")
    await asyncio.sleep(HOLD * 3)
    await h.b.update("station/12/peer", "station/2")
    await h.b.update("station/2/peer", "station/12")
    await h.b.update("ctl/power_cut", "off")


async def pulls_the_cord_before_routing(h: Harness) -> None:
    """She answers, hears the request, and pulls the answering cord before
    taking a trunk (§5): the caller is lost, and the call abandoned."""
    c = "station/12"
    await answers(h, c)
    await request_heard(h, c)
    await h.b.update(f"{c}/op", "off")
    await asyncio.sleep(60)


async def leaves_and_comes_back(h: Harness) -> None:
    """She answers, hears the request, leaves the caller longer than AWAY, and
    comes back on with the answering cord alone (§3.5): the caller
    asks again; then she puts it through."""
    c, want = "station/12", 2
    await answers(h, c)
    await request_heard(h, c)
    await h.b.update(f"{c}/op", "off")
    await asyncio.sleep(HOLD + D * 4)     # "off" takes effect HOLD late (§4)
    await h.b.update(f"{c}/op", "on")
    await request_heard(h, c)
    await h.b.update(f"station/{want}/ring", "on")
    await h.b.wait_until(lambda b: b.on(f"station/{want}/hook"), 5)
    await h.b.update(f"station/{want}/ring", "off")
    await h.b.update(f"{c}/peer", f"station/{want}")
    await h.b.update(f"station/{want}/peer", c)


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
        if i == 0:                                    # dial tone stops (§3.5)
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
    assert h.b.get("trunk/3/tone") == "busy", h.b.get("trunk/3/tone")
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


async def rear_then_front(h: Harness) -> None:
    """A call in on trunk 3: the rear cord first, heard but not seizing it,
    then the front cord, and on as incoming_operator (§9.1)."""
    c, want = "trunk/3", 2
    await h.b.wait_until(lambda b: b.on(f"{c}/ring"), 5)
    await asyncio.sleep(D)
    await h.b.update(f"{c}/op", "on")
    await asyncio.sleep(4 * D)
    h.rear = (list(h.monitor), h.b.get(f"{c}/play"))
    await h.b.update(f"{c}/seize", "on")
    await request_heard(h, c)
    await h.b.update(f"station/{want}/ring", "on")
    await h.b.wait_until(lambda b: b.on(f"station/{want}/hook"), 5)
    await h.b.update(f"station/{want}/ring", "off")
    await h.b.update(f"{c}/peer", f"station/{want}")
    await h.b.update(f"station/{want}/peer", c)

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


async def misdialling_operator(h: Harness, number: str) -> None:
    """Dials `number`, waits for reorder, listens a while, releases, then
    takes the trunk again and dials the right number."""
    c = "station/12"
    await outgoing_operator(h, number)
    await h.b.wait_until(lambda b: b.get("trunk/3/tone") == "reorder", 5)
    h.reorder_at = h.b.get("trunk/3/dialled")
    await asyncio.sleep(D * 4)
    h.still = h.b.get("trunk/3/tone")
    await h.b.update("trunk/3/seize", "off")
    await asyncio.sleep(D)
    await h.b.update("trunk/3/seize", "on")
    await h.b.update("trunk/3/peer", c)
    await h.b.update(f"{c}/peer", "trunk/3")
    await h.b.wait_until(lambda b: b.get("trunk/3/tone") == "dial", 5)
    for d in "2754101":
        await asyncio.sleep(D / 2)
        await h.b.update("trunk/3/digit", d)


async def misdial_and_stay(h: Harness) -> None:
    """Dials too few digits and stays on the trunk through the fast busy."""
    await outgoing_operator(h, "27541")
    await asyncio.sleep(30)


def with_reactions(h: Harness) -> Harness:
    """Every party has its reactions, named <kind>.<voice>; the caller
    is "v1", the called party "v2", whoever is in a room "occ"."""
    h.ctx.scene = dataclasses.replace(h.ctx.scene, caller_voice="v1", called_voice="v2")
    h.ctx.reaction = lambda kind, voice: Speech(f"{kind}.{voice}", D * 3, "caller")
    h.ctx.occupant = lambda n: "occ"
    return h


def mute_first_listens(h: Harness, n: int) -> None:
    """The first n listens hear nothing and time out."""
    echo, left = h.link._echo, [n]

    async def _echo(key: str, p: str) -> None:
        base = key.removesuffix("/set")
        if not base.endswith("/listen") or p == "0" or left[0] <= 0:
            return await echo(key, p)
        left[0] -= 1
        await h.b.update(base, "listening")
        await asyncio.sleep(float(p))
        await h.b.update(base, "timeout")
    h.link._echo = _echo


def played(h: Harness, circuit: str) -> list[str]:
    return [v for k, v in h.link.sent if k == f"{circuit}/play/set"]


async def wrong_room_operator(h: Harness) -> None:
    """Patches the caller to room 7 and rings it, hears the wrong party, then
    re-patches to 2 and rings that."""
    c = "station/12"
    await answers(h, c)
    await request_heard(h, c)
    await h.b.update(f"{c}/peer", "station/7")
    await h.b.update("station/7/peer", c)
    await h.b.update("station/7/ring", "on")
    await h.b.wait_until(lambda b: b.on("station/7/hook"), 5)
    await h.b.update("station/7/ring", "off")
    await h.b.wait_until(lambda b: not b.on("station/7/hook"), 5)   # it hangs up
    await h.b.update("station/7/peer", "")
    await h.b.update(f"{c}/peer", "station/2")
    await h.b.update("station/2/peer", c)
    await h.b.update("station/2/ring", "on")
    await h.b.wait_until(lambda b: b.on("station/2/hook"), 5)
    await h.b.update("station/2/ring", "off")


async def unpatched_operator(h: Harness) -> None:
    """Rings room 2 on a cord not patched to the caller; once it has hung
    up, patches the pair and rings it again."""
    c = "station/12"
    await answers(h, c)
    await request_heard(h, c)
    await h.b.update("station/2/ring", "on")
    await h.b.wait_until(lambda b: b.on("station/2/hook"), 5)
    await h.b.update("station/2/ring", "off")
    await h.b.wait_until(lambda b: not b.on("station/2/hook"), 5)
    await h.b.update(f"{c}/peer", "station/2")
    await h.b.update("station/2/peer", c)
    await h.b.update("station/2/ring", "on")
    await h.b.wait_until(lambda b: b.on("station/2/hook"), 5)
    await h.b.update("station/2/ring", "off")


async def never_dials(h: Harness) -> None:
    c = "station/12"
    await answers(h, c)
    await request_heard(h, c)
    await h.b.update("trunk/3/seize", "on")
    await h.b.update("trunk/3/peer", c)
    await h.b.update(f"{c}/peer", "trunk/3")
    await h.b.wait_until(lambda b: b.get("trunk/3/tone") == "reorder", 5)
    await asyncio.sleep(D * 2)
    await h.b.update("trunk/3/seize", "off")


async def test_station_to_station_a_good_operator():
    """Station to station, a good operator"""
    h = Harness(scene(Shape.STATION_TO_STATION))
    r = await h.run(station_to_station, good_station_operator)
    assert r.ok, "succeeds"
    assert h.connected, "reports connected (§3.3)"
    assert h.monitor == ["station/12"], f"moved the monitor once, to the caller: {h.monitor}"
    assert (h.stages == [Stage.SIGNALLING, Stage.REQUEST, Stage.ROUTING,
                       Stage.RINGING, Stage.TALKING]), f"stages {h.stages}"
    assert (("station/12/hook/set", "off") in h.link.sent
          and ("station/2/hook/set", "off") in h.link.sent), "hung both up in finally"


async def test_she_leaves_the_caller_and_comes_back_it_asks():
    """She leaves the caller and comes back: it asks again (§3.5)"""
    h = Harness(scene(Shape.STATION_TO_STATION))
    r = await h.run(station_to_station, leaves_and_comes_back)
    asked = [v for k, v in h.link.sent if k == "station/12/play/set" and v == "t.1"]
    assert r.ok and len(asked) == 2, f"the request twice, and the call goes through: {len(asked)}, {r.reason!r}"
    assert any("asks again" in e for e in h.events), "logged"
    h = Harness(scene(Shape.STATION_TO_STATION))
    r = await h.run(station_to_station, good_station_operator)
    asked = [v for k, v in h.link.sent if k == "station/12/play/set" and v == "t.1"]
    assert len(asked) == 1, f"not when she never leaves: {len(asked)}"


async def test_the_operator_rings_the_wrong_station_then_the_right():
    """The operator rings the wrong station, then the right one"""
    h = Harness(scene(Shape.STATION_TO_STATION))
    r = await h.run(station_to_station, wrong_then_right_operator)
    assert r.ok, "still succeeds — a wrong connection is not a failure (§3.5)"
    assert any("wanted 2" in e for e in h.events), f"logged the wrong station: {h.events}"


async def test_nobody_answers_the_lamp():
    """Nobody answers the lamp"""
    h = Harness(scene(Shape.STATION_TO_STATION))
    h.ctx.cfg.answer_timeout = 0.3
    r = await h.run(station_to_station, never_answers)
    assert not r.ok and r.reason == Reason.NO_ANSWER, f"fails as 'no answer': {r.reason!r}"
    assert not h.connected, "never reports connected"


async def test_the_operator_answers_but_never_connects():
    """The operator answers but never connects"""
    h = Harness(scene(Shape.STATION_TO_STATION))
    h.ctx.cfg.connect_timeout = 0.3
    async def answers_only(hh):
        await answers(hh, "station/12")
        await asyncio.sleep(30)
    r = await h.run(station_to_station, answers_only)
    assert not r.ok and r.reason == Reason.NOT_CONNECTED, f"fails as 'not connected': {r.reason!r}"


async def test_a_cord_is_pulled_during_the_conversation():
    """A cord is pulled during the conversation"""
    h = Harness(scene(Shape.STATION_TO_STATION))
    r = await h.run(station_to_station, cuts_off)
    assert not r.ok and r.reason == Reason.CUT_OFF, f"fails as 'cut off': {r.reason!r}"
    assert h.connected, "was connected before it was cut"


async def test_her_switch_breaks_both_lines_for_a_moment():
    """Her switch breaks both lines for a moment (§4)"""
    h = Harness(scene(Shape.STATION_TO_STATION))
    r = await h.run(station_to_station, switch_glitch)
    assert r.ok, f"the call rides through: {r.reason!r}"


async def test_the_switchboard_reset_during_the_conversation():
    """The switchboard reset during the conversation (§2)"""
    h = Harness(scene(Shape.STATION_TO_STATION))
    r = await h.run(station_to_station, power_reset)
    assert r.ok, f"the call rides through: {r.reason!r}"
    assert h.b.get("station/12/peer") == "station/2", "and the lines read as before"


async def test_a_pull_during_the_reset_is_seen_once_it():
    """A pull during the reset is seen once it settles"""
    h = Harness(scene(Shape.STATION_TO_STATION))

    async def pulled_in_reset(h: Harness) -> None:
        await good_station_operator(h)
        await asyncio.sleep(D * 4)
        await h.b.update("ctl/power_cut", "on")
        await h.b.update("station/12/peer", "")
        await h.b.update("station/2/peer", "")
        await h.b.update("ctl/power_cut", "off")
    r = await h.run(station_to_station, pulled_in_reset)
    assert not r.ok and r.reason == Reason.CUT_OFF, f"fails as 'cut off': {r.reason!r}"


async def test_the_caller_left_alone_before_connecting_hangs_up(monkeypatch):
    """The caller left alone before connecting hangs up (§3.5)"""
    monkeypatch.setattr(flows, "ABANDON", D * 10)
    monkeypatch.setattr(flows, "ABANDON_MISDIALLED", D * 3)
    h = Harness(scene(Shape.STATION_TO_OUTSIDE, to_line="pizza", to_station=None,
                      dial="275-4101"))
    t0 = asyncio.get_running_loop().time()
    r = await h.run(station_to_outside, pulls_the_cord_before_routing)
    patient = asyncio.get_running_loop().time() - t0
    assert not r.ok and r.reason == Reason.CUT_OFF, f"fails as 'cut off': {r.reason!r}"
    assert any("hung up" in e for e in h.events), f"and says so: {h.events}"
    h = Harness(scene(Shape.STATION_TO_OUTSIDE, to_line="pizza", to_station=None,
                      dial="275-4101"))
    h.ctx.misdialled = True
    t0 = asyncio.get_running_loop().time()
    r = await h.run(station_to_outside, pulls_the_cord_before_routing)
    took = asyncio.get_running_loop().time() - t0
    assert not r.ok and r.reason == Reason.CUT_OFF, "after a wrong number too"
    assert took < patient - D * 5, f"and sooner: {took:.2f}s against {patient:.2f}s"
    # The tutor's wrong-cord line, ending while the caller is alone,
    # restarts the wait.
    h = Harness(scene(Shape.STATION_TO_OUTSIDE, to_line="pizza", to_station=None,
                      dial="275-4101"))
    said = time.time() + patient - D * 2
    h.ctx.hint_end = lambda: said
    t0 = asyncio.get_running_loop().time()
    r = await h.run(station_to_outside, pulls_the_cord_before_routing)
    took = asyncio.get_running_loop().time() - t0
    assert not r.ok and r.reason == Reason.CUT_OFF, "after a wrong-cord line too"
    assert took > patient + D * 5, f"but waiting afresh from its end: {took:.2f}s against {patient:.2f}s"


async def test_station_to_outside():
    """Station to outside"""
    h = Harness(scene(Shape.STATION_TO_OUTSIDE, to_line="pizza", to_station=None,
                      dial="275-4101"))
    r = await h.run(station_to_outside, lambda hh: outgoing_operator(hh, "2754101"))
    assert r.ok, "succeeds"
    assert h.connected, "reports connected"
    assert any("dialled 275-4101" in e for e in h.events), f"logged the number: {h.events}"
    assert Stage.DIALLING in h.stages, f"went through dialling: {h.stages}"


async def test_long_distance_a_line_that_waits_for_the_operator():
    """Long distance: a line that waits for the operator on the trunk (§4.6)"""
    h = Harness(scene(Shape.STATION_TO_OUTSIDE, to_line="operator", to_station=None,
                      dial="0",
                      conversation=(speech("t.2", "called"),
                                    Speech("t.3", D * 3, "called", wait=True),
                                    speech("t.4", "caller"))))
    r = await h.run(station_to_outside, lambda hh: outgoing_operator(hh, "0"))
    assert r.ok, "succeeds"
    listens = [k for k, _ in h.link.sent if k.endswith("/listen/set")]
    assert listens.count("trunk/3/listen/set") == 1, f"listened once on the trunk: {listens}"


async def test_a_line_with_pause_and_ringback():
    """A line with pause: and ringback: (§6.2)"""
    h = Harness(scene(Shape.STATION_TO_OUTSIDE, to_line="operator", to_station=None,
                      dial="0",
                      conversation=(speech("t.2", "called"),
                                    Speech("t.3", D * 3, "called", pause=D * 4),
                                    Speech("t.4", D * 3, "called", ringback=D * 4),
                                    speech("t.5", "caller"))))
    t0 = asyncio.get_running_loop().time()
    r = await h.run(station_to_outside, lambda hh: outgoing_operator(hh, "0"))
    took = asyncio.get_running_loop().time() - t0
    assert r.ok, "succeeds"
    tones = [v for k, v in h.link.sent if k == "trunk/3/tone/set"]
    i = max(i for i, v in enumerate(tones) if v == "ringback")
    assert "off" in tones[i + 1:], f"ringback, then off, on the trunk: {tones}"
    assert took >= D * 8, f"both waits taken: {took:.2f}s"


async def test_ringback_on_the_calling_side_of_a_call_in():
    """Ringback: on the calling side of a call in (§6.2)"""
    h = Harness(scene(Shape.OUTSIDE_TO_STATION, from_line="operator", from_station=None,
                      to_line="room105", to_station=2,
                      conversation=(speech("t.2", "called"),
                                    Speech("t.3", D * 3, "caller", ringback=D * 3))))
    r = await h.run(outside_to_station, incoming_operator, 3)
    assert r.ok, "succeeds"
    tones = [v for k, v in h.link.sent if k == "trunk/3/tone/set"]
    assert tones[:2] == ["ringback", "off"], f"rang the incoming trunk, then stopped: {tones}"


async def test_the_operator_dials_a_wrong_number_releases_and_redials():
    """The operator dials a wrong number, releases, and redials"""
    h = Harness(scene(Shape.STATION_TO_OUTSIDE, to_line="pizza", to_station=None,
                      dial="275-4101"))
    r = await h.run(station_to_outside, wrong_then_right_number)
    assert r.ok, "still succeeds (§3.5)"
    assert any("wanted 275-4101" in e for e in h.events), f"logged the wrong number: {h.events}"


@pytest.mark.parametrize("what, number", (("too many digits", "27541012"),
                                          ("too few digits", "27541")))
async def test_the_operator_dials_a_misdialled_number(what, number):
    """Too many digits or too few: reorder, then she redials (§3.5)"""
    h = Harness(scene(Shape.STATION_TO_OUTSIDE, to_line="pizza", to_station=None,
                      dial="275-4101"))
    r = await h.run(station_to_outside, lambda hh: misdialling_operator(hh, number))
    assert r.ok, f"succeeds once she redials: {r.reason!r}"
    assert h.reorder_at == number, f"reorder once {h.reorder_at!r} is in"
    assert h.still == "reorder", "and goes on while she stays on the trunk"
    tones = [v for k, v in h.link.sent if k == "trunk/3/tone/set"]
    i = tones.index("reorder")
    assert tones[i + 1] == "off" and "dial" in tones[i:] and "ringback" in tones[i:], f"stops when she releases, dial tone on the next seizure: {tones}"
    assert any("too " + ("many" if len(number) > 7 else "few") in e for e in h.events), f"logged: {h.events[-1:]}"


async def test_a_misdial_and_the_connect_timeout_runs_out():
    """A misdial and the connect timeout runs out"""
    h = Harness(scene(Shape.STATION_TO_OUTSIDE, to_line="pizza", to_station=None,
                      dial="275-4101"))
    h.ctx.cfg.connect_timeout = 3.0           # DIAL_DELAY is 1s
    r = await h.run(station_to_outside, misdial_and_stay)
    assert not r.ok and r.reason == Reason.MISDIALLED, f"fails as misdialled: {r.reason!r}"


async def test_the_operator_does_not_speak_the_caller_nudges_her():
    """The operator does not speak: the caller nudges her"""
    h = with_reactions(Harness(scene(Shape.STATION_TO_STATION)))
    mute_first_listens(h, 1)
    r = await h.run(station_to_station, good_station_operator)
    assert r.ok, f"succeeds: {r.reason!r}"
    assert played(h, "station/12")[:2] == ["nudge.v1", "t.1"], f"'Hello? Operator?' in the caller's voice, then the request: {played(h, 'station/12')[:2]}"
    assert sum(1 for k, _ in h.link.sent if k == "station/12/listen/set") >= 2, "and listened again after it"


async def test_the_wrong_room_is_rung_it_answers_and_hangs():
    """The wrong room is rung: it answers, and hangs up"""
    h = with_reactions(Harness(scene(Shape.STATION_TO_STATION)))
    r = await h.run(station_to_station, wrong_room_operator)
    assert r.ok, f"still succeeds once she rings the right one: {r.reason!r}"
    assert played(h, "station/7") == ["hello.occ"], f"the wrong party: {played(h, 'station/7')}"
    assert "wrong.v1" in played(h, "station/12"), "and the caller says so"
    assert ("station/7/hook/set", "off") in h.link.sent, "then the room hangs up"


async def test_the_right_room_on_a_cord_not_patched_to():
    """The right room on a cord not patched to the caller"""
    h = with_reactions(Harness(scene(Shape.STATION_TO_STATION)))
    r = await h.run(station_to_station, unpatched_operator)
    assert r.ok, f"succeeds once the pair is patched and it is rung again: {r.reason!r}"
    assert played(h, "station/2")[:1] == ["hello.v2"], f"'Hello?' from the room: {played(h, 'station/2')}"
    assert any("nobody on the line" in e for e in h.events), "it hung up, logged"


async def test_a_rear_cord_in_the_trunk_of_a_call():
    """A rear cord in the trunk of a call in is not an answer (§9.1)"""
    h = Harness(scene(Shape.OUTSIDE_TO_STATION, from_line="operator", from_station=None,
                      to_line="room105", to_station=2))
    r = await h.run(outside_to_station, rear_then_front, 3)
    assert h.rear == ([], ""), f"heard unseized: not answered, the caller waits {h.rear}"
    assert r.ok and h.monitor[:1] == ["trunk/3"], f"then the front cord: succeeds ({h.monitor})"


async def test_a_trunk_left_up_from_an_earlier_call_is():
    """A trunk left up from an earlier call is not this call's"""
    h = Harness(scene(Shape.STATION_TO_OUTSIDE, to_line="pizza", to_station=None,
                      dial="275-4101"))
    await h.b.update("trunk/5/seize", "on")                    # a cord left in
    r = await h.run(station_to_outside, lambda hh: outgoing_operator(hh, "2754101"))
    assert r.ok, f"succeeds: {r.reason!r}"
    assert ("trunk/5/tone/set", "dial") not in h.link.sent, "no dial tone on the stale trunk"
    assert h.call.trunk == "trunk/3", f"the trunk she took: {h.call.trunk}"


async def plugs_in_early(h: Harness) -> None:
    """She takes the trunk while the request is still being said, and the
    peer comes in after routing has begun, as on the switchboard 2026-11-23."""
    c = "station/12"
    await answers(h, c)
    await h.b.wait_until(lambda b: b.get(f"{c}/play") == "t.1", 5)
    await h.b.update("trunk/3/seize", "on")
    await h.b.wait_until(lambda b: not b.get(f"{c}/play"), 5)
    await asyncio.sleep(D)
    await h.b.update("trunk/3/peer", c)
    await h.b.update(f"{c}/peer", "trunk/3")
    await h.b.wait_until(lambda b: b.get("trunk/3/tone") == "dial", 5)
    for d in "2754101":
        await asyncio.sleep(D / 2)
        await h.b.update("trunk/3/digit", d)


async def test_a_trunk_taken_during_the_request():
    """A trunk taken before the request ends is this call's once patched to the caller"""
    h = Harness(scene(Shape.STATION_TO_OUTSIDE, to_line="pizza", to_station=None,
                      dial="275-4101"))
    r = await h.run(station_to_outside, plugs_in_early)
    assert r.ok, f"succeeds: {r.reason!r}"
    assert ("trunk/3/tone/set", "dial") in h.link.sent, "dial tone on it"
    assert h.call.trunk == "trunk/3", f"the trunk she took: {h.call.trunk}"


async def test_a_trunk_taken_and_not_dialled():
    """A trunk taken and not dialled"""
    h = Harness(scene(Shape.STATION_TO_OUTSIDE, to_line="pizza", to_station=None,
                      dial="275-4101"))
    h.ctx.cfg.connect_timeout = 3.0           # DIAL_DELAY is 1s
    r = await h.run(station_to_outside, never_dials)
    assert not r.ok and r.reason == Reason.MISDIALLED, f"fails as misdialled at the timeout: {r.reason!r}"
    assert any("nothing dialled" in e for e in h.events), f"logged: {h.events[-1:]}"


async def test_a_busy_scene():
    """A busy scene"""
    h = Harness(scene(Shape.BUSY, to_line="pizza", to_station=None, dial="275-4101",
                      busy=True, conversation=(speech("t.2", "caller"),)))
    r = await h.run(busy_scene, lambda hh: outgoing_operator(hh, "2754101"))
    assert r.ok, "succeeds"
    assert h.connected, "connected at busy tone (§3.3)"
    assert Stage.BUSY in h.stages, f"showed the busy stage: {h.stages}"
    sent = h.link.sent
    busy_at = sent.index(("trunk/3/tone/set", "busy"))
    off_at = next((i for i, m in enumerate(sent) if i > busy_at and m == ("trunk/3/tone/set", "off")), None)
    heard_at = next((i for i, (k, _) in enumerate(sent) if i > busy_at and k == "station/12/listen/set"), None)
    assert off_at is not None and heard_at is not None and off_at < heard_at, f"busy tone stops before the game listens for her (§3.2): off {off_at}, listen {heard_at}"


async def test_a_call_to_the_operator():
    """A call to the operator"""
    h = Harness(scene(Shape.TO_OPERATOR, to_line="", to_station=None,
                      conversation=(speech("t.2", "caller"),)))
    r = await h.run(to_operator, speaks_when_asked)
    assert r.ok, "succeeds"
    assert h.connected, "connected when the request finished (§3.3)"
    assert Stage.OPERATOR in h.stages, f"showed the operator stage: {h.stages}"


async def test_a_question_to_the_operator_waits_for_her_answer():
    """A question to the operator waits for her answer, the closing (§6.3)"""
    h = Harness(scene(Shape.TO_OPERATOR, to_line="", to_station=None,
                      conversation=(), closing="t.2"))
    r = await h.run(to_operator, speaks_when_asked)
    listens = [k for k, v in h.link.sent if k == "station/12/listen/set"]
    assert r.ok, "succeeds"
    assert len(listens) == 2, f"listened for her greeting and her answer: {len(listens)}"
    h = Harness(scene(Shape.TO_OPERATOR, to_line="", to_station=None, conversation=()))
    r = await h.run(to_operator, speaks_when_asked)
    listens = [k for k, v in h.link.sent if k == "station/12/listen/set"]
    assert r.ok and len(listens) == 1, "with no closing, only the greeting"


async def test_time_and_charges_a_call_to_the_operator_rung():
    """Time and charges: a call to the operator rung in on a trunk"""
    h = Harness(scene(Shape.TO_OPERATOR, from_line="operator", from_station=None,
                      to_line="", to_station=None, conversation=()))
    t0 = asyncio.get_running_loop().time()
    r = await h.run(to_operator, answers_the_trunk, 3)
    took = asyncio.get_running_loop().time() - t0
    assert r.ok, "succeeds"
    assert h.connected, "connected when the request finished (§3.3)"
    assert ("trunk/3/shortring/set", "on") in h.link.sent, "rang the trunk once, short"
    assert ("trunk/3/ring/set", "off") in h.link.sent, "stopped ringing it once answered"
    assert h.monitor == ["trunk/3"], f"monitor followed the trunk: {h.monitor}"
    assert took < 5, f"hung up as soon as the request played, not waiting on her: {took:.2f}s"
    assert not any(k.startswith("station/") and k.endswith("/hook/set") for k, _ in h.link.sent), "took no station off-hook"


async def test_time_and_charges_nobody_answers():
    """Time and charges nobody answers"""
    h = Harness(scene(Shape.TO_OPERATOR, from_line="operator", from_station=None,
                      to_line="", to_station=None, conversation=()))
    h.ctx.cfg.answer_timeout = 0.3
    r = await h.run(to_operator, never_answers, 3)
    assert not r.ok and r.reason == Reason.NO_ANSWER, f"fails as 'no answer': {r.reason!r}"
    assert ("trunk/3/ring/set", "off") in h.link.sent, "and stops ringing the trunk"


async def test_a_call_in_from_outside():
    """A call in from outside"""
    h = Harness(scene(Shape.OUTSIDE_TO_STATION, from_line="pizza", from_station=None,
                      to_line="room214", to_station=2))
    r = await h.run(outside_to_station, incoming_operator, 3)
    assert r.ok, "succeeds"
    assert h.monitor == ["trunk/3"], f"monitor followed the trunk: {h.monitor}"
    assert ("trunk/3/shortring/set", "on") in h.link.sent, "rang the trunk once, short"
    assert ("trunk/3/ring/set", "on") not in h.link.sent, "and never with the cadence"
    assert ("trunk/3/ring/set", "off") in h.link.sent, "stopped ringing the trunk"


async def test_if_busy_the_called_station_engaged_when_the_request():
    """If_busy: the called station engaged when the request ends (§6.6)"""
    h = Harness(scene(Shape.STATION_TO_STATION, if_busy=(speech("t.9", "caller"),)))
    await h.b.update("station/2/hook", "on")         # the front desk is on another call
    r = await h.run(station_to_station, speaks_when_asked)
    assert r.ok, "succeeds"
    assert h.connected, "connected when found engaged (§3.3)"
    assert h.stages == [Stage.SIGNALLING, Stage.REQUEST, Stage.ROUTING, Stage.BUSY], f"stages {h.stages}"
    assert ("station/12/play/set", "t.9") in h.link.sent, "played the if_busy: line"
    assert not any(k == "station/2/hook/set" for k, _ in h.link.sent), "left the engaged station to its own call"
    assert any("is engaged" in e for e in h.events), f"logged it: {h.events}"


async def test_if_busy_engaged_while_she_routes():
    """If_busy: engaged while she routes"""
    h = Harness(scene(Shape.STATION_TO_STATION, if_busy=(speech("t.9", "caller"),)))
    async def routes_slowly(hh):
        await answers(hh, "station/12")
        await request_heard(hh, "station/12")
        await asyncio.sleep(D * 4)
        await hh.b.update("station/2/hook", "on")    # another call takes it first
        await asyncio.sleep(60)
    r = await h.run(station_to_station, routes_slowly)
    assert r.ok and Stage.BUSY in h.stages, f"found engaged: {r.reason!r} {h.stages}"


async def test_if_busy_the_station_free_the_call_goes_through():
    """If_busy: the station free, the call goes through as usual"""
    h = Harness(scene(Shape.STATION_TO_STATION, if_busy=(speech("t.9", "caller"),)))
    r = await h.run(station_to_station, good_station_operator)
    assert r.ok and Stage.TALKING in h.stages and Stage.BUSY not in h.stages, f"talked: {h.stages}"
    assert ("station/12/play/set", "t.9") not in h.link.sent, "and no if_busy: line"
    assert ("station/2/hook/set", "off") in h.link.sent, "hung the called station up"


class EndlessSpeech(FakeLink):
    """The detector hears speech and never silence: the loudspeaker's loop
    through the operator's headset (2026-11-12, game_control.md §6.2)."""

    async def _echo(self, key: str, p: str) -> None:
        base = key.removesuffix("/set")
        if base.endswith("/listen") and p != "0":
            await asyncio.sleep(D)
            await self.b.update(base, "listening")
            await asyncio.sleep(D)
            await self.b.update(base, "speech")
            return
        await super()._echo(key, p)


async def test_speech_that_never_ends_is_taken_as_ended():
    """hear(): speech past max_speech is ended, and the listen cancelled (§6.2)"""
    from sbgame.scenes import hear
    h = Harness(scene(Shape.TO_OPERATOR, to_line="", to_station=None))
    h.link = EndlessSpeech(h.b)
    h.hw = Hw(h.link)
    await h.live()
    t0 = asyncio.get_running_loop().time()
    r = await hear(h.b, h.hw, "station/12", 1.0, max_speech=D * 5)
    took = asyncio.get_running_loop().time() - t0
    assert r == "silence", f"taken as ended: {r!r}"
    assert ("station/12/listen/set", "0") in h.link.sent, "the listen cancelled"
    assert took < D * 15, f"after the cap, not the audio program's 30s: {took:.2f}s"
    # A silence before the cap is the silence, with nothing cancelled.
    h2 = Harness(scene(Shape.TO_OPERATOR, to_line="", to_station=None))
    await h2.live()
    assert await hear(h2.b, h2.hw, "station/12", 1.0, max_speech=D * 50) == "silence"
    assert ("station/12/listen/set", "0") not in h2.link.sent, "nothing to cancel"


async def test_a_call_to_the_operator_with_a_greeting_that_never_ends(monkeypatch):
    """Her greeting heard as endless speech: the caller still speaks (§6.2)"""
    monkeypatch.setattr(flows, "GREETING_MAX", D * 5)
    monkeypatch.setattr(flows, "SPEECH_MAX", D * 5)
    h = Harness(scene(Shape.TO_OPERATOR, to_line="", to_station=None,
                      conversation=(speech("t.2", "caller"),)))
    h.link = EndlessSpeech(h.b)
    h.hw = Hw(h.link)
    h.ctx = dataclasses.replace(h.ctx, hw=h.hw)
    r = await h.run(to_operator, speaks_when_asked)
    played = [v for k, v in h.link.sent if k == "station/12/play/set"]
    assert r.ok, f"succeeds: {r.reason!r}"
    assert "t.1" in played and "t.2" in played, f"the request and the reply both played: {played}"


# ---- §3.3: a call to the operator, and her leaving it (2026-11-13) ----------


def _op_scene():
    return scene(Shape.TO_OPERATOR, to_line="", to_station=None,
                 conversation=(speech("t.2", "caller"), speech("t.3", "caller")))


def _nudge(h: Harness) -> None:
    h.ctx = dataclasses.replace(
        h.ctx, reaction=lambda kind, voice: speech("nudge.1", "caller") if kind == "nudge" else None)


async def test_she_leaves_after_replying_the_call_counts():
    """She replies to the request and leaves during the punch line: success (§3.3)"""
    h = Harness(_op_scene())

    async def op(h: Harness) -> None:
        c = "station/12"
        await answers(h, c)
        await h.b.wait_until(lambda b: b.get(f"{c}/play") == "t.2", 5)   # after her reply
        await h.b.update(f"{c}/op", "off")
        await asyncio.sleep(60)

    r = await h.run(to_operator, op)
    played = [v for k, v in h.link.sent if k == "station/12/play/set"]
    assert r.ok, f"succeeds: {r.reason!r}"
    assert "t.3" not in played, f"the rest is not played: {played}"
    assert any("left after replying" in e for e in h.events), h.events


async def test_she_leaves_before_replying_and_comes_back(monkeypatch):
    """She leaves after the request, comes back: the caller asks if she is there (§3.3)"""
    monkeypatch.setattr(flows, "ABANDON", D * 30)
    monkeypatch.setattr(flows, "BACK_PAUSE", D)
    h = Harness(_op_scene())
    _nudge(h)

    async def op(h: Harness) -> None:
        c = "station/12"
        await answers(h, c)
        await request_heard(h, c)
        await h.b.update(f"{c}/op", "off")              # before her reply is heard
        await asyncio.sleep(D * 10)
        await h.b.update(f"{c}/op", "on")
        await asyncio.sleep(60)

    # Her reply is heard only after she comes back: the listen echoes speech
    # and silence on its own, so hold it until she is on the line again.
    real = h.link._echo

    async def echo(key: str, p: str) -> None:
        if key.endswith("/listen/set") and p != "0":
            await h.b.wait_until(lambda b: b.on("station/12/op"), 5)
            await asyncio.sleep(D * 2)
        await real(key, p)
    h.link._echo = echo

    r = await h.run(to_operator, op)
    played = [v for k, v in h.link.sent if k == "station/12/play/set"]
    assert r.ok, f"succeeds: {r.reason!r}"
    assert "nudge.1" in played, f"asked if she is there: {played}"
    assert played.index("nudge.1") < played.index("t.2"), f"before going on: {played}"
    assert ("station/12/hook/set", "off") not in h.link.sent[:h.link.sent.index(("station/12/play/set", "nudge.1"))], \
        "the station stayed off-hook while it waited, so its lamp lit"


async def test_she_leaves_before_replying_and_does_not_come_back(monkeypatch):
    """She leaves after the request and stays away: cut off after the wait (§3.3)"""
    monkeypatch.setattr(flows, "ABANDON", D * 10)
    h = Harness(_op_scene())

    async def op(h: Harness) -> None:
        c = "station/12"
        await answers(h, c)
        await request_heard(h, c)
        await h.b.update(f"{c}/op", "off")
        await asyncio.sleep(60)

    real = h.link._echo

    async def echo(key: str, p: str) -> None:       # she never replies
        if key.endswith("/listen/set") and p != "0" and h.b.saw("station/12/play", "t.1"):
            await asyncio.sleep(D)
            await h.b.update(key.removesuffix("/set"), "listening")
            return
        await real(key, p)
    h.link._echo = echo

    r = await h.run(to_operator, op)
    assert not r.ok and r.reason == Reason.CUT_OFF, f"cut off: {r.reason!r}"
    assert any("waits for the operator" in e for e in h.events), h.events


async def test_she_replies_and_leaves_before_her_reply_ends():
    """A curt reply and the cord pulled before the silence: it counts (§3.3)"""
    h = Harness(_op_scene())

    async def op(h: Harness) -> None:
        c = "station/12"
        await answers(h, c)
        await request_heard(h, c)
        await h.b.wait_until(lambda b: b.get(f"{c}/listen") == "speech", 5)
        await h.b.update(f"{c}/op", "off")
        await asyncio.sleep(60)

    real = h.link._echo

    async def echo(key: str, p: str) -> None:       # her reply never ends
        if key.endswith("/listen/set") and p != "0" and h.b.saw("station/12/play", "t.1"):
            base = key.removesuffix("/set")
            await asyncio.sleep(D)
            await h.b.update(base, "listening")
            await asyncio.sleep(D)
            await h.b.update(base, "speech")
            return
        await real(key, p)
    h.link._echo = echo

    r = await h.run(to_operator, op)
    assert r.ok, f"succeeds: {r.reason!r}"
    assert any("left after replying" in e for e in h.events), h.events


# ------------------------------------------------- Rev 118 (2026-11-14) ----


def _reactions(h: Harness) -> None:
    """nudge and giveup, as rendered reactions (§3.5)."""
    lines = {"nudge": speech("nudge.1", "caller"), "giveup": speech("giveup.1", "caller")}
    h.ctx = dataclasses.replace(h.ctx, reaction=lambda kind, voice: lines.get(kind))


async def test_ambiguous_in_conversation_is_not_a_pulled_cord():
    """Keyed on two pairs for a moment: `ambiguous` is not a pulled cord (§4)"""
    h = Harness(scene(Shape.STATION_TO_STATION))

    async def op(h: Harness) -> None:
        await good_station_operator(h)
        await h.b.wait_until(lambda b: b.get("station/2/play") == "t.2", 5)
        for c in ("station/12", "station/2"):
            await h.b.update(f"{c}/peer", "ambiguous")
        await asyncio.sleep(D * 4)
        await h.b.update("station/12/peer", "station/2")
        await h.b.update("station/2/peer", "station/12")
        await asyncio.sleep(60)

    r = await h.run(station_to_station, op)
    assert r.ok, f"succeeds: {r.reason!r}"


async def test_a_line_that_cannot_hear_keeps_the_operator():
    """A howl: `op` off with `deaf`, for longer than HOLD, then back (§4)"""
    h = Harness(scene(Shape.STATION_TO_STATION))

    async def op(h: Harness) -> None:
        c, want = "station/12", 2
        await answers(h, c)
        await h.b.wait_until(lambda b: b.get(f"{c}/play") == "t.1", 5)
        await h.b.update(f"{c}/op", "off")
        await h.b.update(f"{c}/peer", "deaf")
        await asyncio.sleep(HOLD * 2)
        await h.b.update(f"{c}/peer", "")             # hearing again
        await h.b.update(f"{c}/op", "on")             # she was there all along
        await h.b.wait_until(lambda b: not b.get(f"{c}/play"), 5)
        await h.b.update(f"station/{want}/ring", "on")
        await h.b.wait_until(lambda b: b.on(f"station/{want}/hook"), 5)
        await h.b.update(f"station/{want}/ring", "off")
        await h.b.update(f"{c}/peer", f"station/{want}")
        await h.b.update(f"station/{want}/peer", c)
        await asyncio.sleep(60)

    r = await h.run(station_to_station, op)
    assert r.ok, f"succeeds: {r.reason!r}"


async def test_a_line_deaf_for_good_is_cut_off_in_the_end():
    """`op` off and the line deaf from then on: cut off after DEAF_MAX (§4)"""
    h = Harness(scene(Shape.STATION_TO_STATION))

    async def op(h: Harness) -> None:
        await good_station_operator(h)
        await h.b.wait_until(lambda b: b.get("station/2/play") == "t.2", 5)
        await h.b.update("station/12/peer", "deaf")
        await h.b.update("station/12/peer", "")
        await asyncio.sleep(60)

    r = await h.run(station_to_station, op)
    assert not r.ok and r.reason == Reason.CUT_OFF, f"cut off: {r.reason!r}"


async def test_engaged_she_tells_the_caller_and_leaves():
    """Engaged: she starts to tell the caller and pulls the cord: success (§3.3, §6.6)"""
    h = Harness(scene(Shape.STATION_TO_STATION, if_busy=(speech("t.9", "caller"),)))
    await h.b.update("station/2/hook", "on")

    async def op(h: Harness) -> None:
        c = "station/12"
        await answers(h, c)
        await request_heard(h, c)
        await h.b.wait_until(lambda b: b.get(f"{c}/listen") == "speech", 5)
        await h.b.update(f"{c}/op", "off")
        await asyncio.sleep(60)

    real = h.link._echo

    async def echo(key: str, p: str) -> None:       # her words never end
        if key.endswith("/listen/set") and p != "0" and h.b.saw("station/12/play", "t.1"):
            base = key.removesuffix("/set")
            await asyncio.sleep(D)
            await h.b.update(base, "listening")
            await asyncio.sleep(D)
            await h.b.update(base, "speech")
            return
        await real(key, p)
    h.link._echo = echo

    r = await h.run(station_to_station, op)
    played = [v for k, v in h.link.sent if k == "station/12/play/set"]
    assert r.ok, f"succeeds: {r.reason!r}"
    assert "t.9" not in played, f"the reply is a bonus: {played}"
    assert any("left after telling them" in e for e in h.events), h.events


async def test_engaged_she_leaves_without_a_word_is_cut_off(monkeypatch):
    """Engaged: she pulls the cord before speaking: cut off, as before (§4)"""
    monkeypatch.setattr(flows, "ABANDON", D * 10)
    h = Harness(scene(Shape.STATION_TO_STATION, if_busy=(speech("t.9", "caller"),)))
    await h.b.update("station/2/hook", "on")

    async def op(h: Harness) -> None:
        c = "station/12"
        await answers(h, c)
        await request_heard(h, c)
        await h.b.update(f"{c}/op", "off")
        await asyncio.sleep(60)

    real = h.link._echo

    async def echo(key: str, p: str) -> None:       # she never speaks
        if key.endswith("/listen/set") and p != "0" and h.b.saw("station/12/play", "t.1"):
            await asyncio.sleep(D)
            await h.b.update(key.removesuffix("/set"), "listening")
            return
        await real(key, p)
    h.link._echo = echo

    r = await h.run(station_to_station, op)
    assert not r.ok and r.reason == Reason.CUT_OFF, f"cut off: {r.reason!r}"


async def test_a_caller_held_asks_if_she_is_there(monkeypatch):
    """Held while she answers another lamp, then back: "Hello? Operator?" (§3.5)"""
    monkeypatch.setattr(flows, "ABANDON", D * 40)
    monkeypatch.setattr(flows, "HELD", D * 8)
    monkeypatch.setattr(flows, "BACK_PAUSE", D)
    h = Harness(scene(Shape.STATION_TO_OUTSIDE, to_line="pizza", to_station=None,
                      dial="275-4101"))
    _reactions(h)

    async def op(h: Harness) -> None:
        c = "station/12"
        await answers(h, c)
        await request_heard(h, c)
        await h.b.update(f"{c}/op", "off")
        await asyncio.sleep(HOLD + D * 10)
        await h.b.update(f"{c}/op", "on")
        await h.b.wait_until(lambda b: b.saw(f"{c}/play", "nudge.1"), 5)
        await request_heard(h, c)                       # and asks again
        await h.b.update("trunk/3/seize", "on")
        await h.b.update("trunk/3/peer", c)
        await h.b.update(f"{c}/peer", "trunk/3")
        await h.b.wait_until(lambda b: b.get("trunk/3/tone") == "dial", 5)
        for d in "2754101":
            await asyncio.sleep(D / 2)
            await h.b.update("trunk/3/digit", d)
        await asyncio.sleep(60)

    r = await h.run(station_to_outside, op)
    played = [v for k, v in h.link.sent if k == "station/12/play/set"]
    assert r.ok, f"succeeds: {r.reason!r}"
    assert played.index("nudge.1") < len(played) - 1 - played[::-1].index("t.1"), \
        f"asked if she was there, then asked again: {played}"


async def test_after_a_wrong_number_asks_again_then_gives_up():
    """Wrong number: first return asks again, second gives up, not connected (§3.5)"""
    h = Harness(scene(Shape.STATION_TO_OUTSIDE, to_line="pizza", to_station=None,
                      dial="275-4101"))
    _reactions(h)

    async def op(h: Harness) -> None:
        c = "station/12"
        await answers(h, c)
        await request_heard(h, c)
        await h.b.update("trunk/3/seize", "on")
        await h.b.update("trunk/3/peer", c)
        await h.b.update(f"{c}/peer", "trunk/3")
        await h.b.wait_until(lambda b: b.get("trunk/3/tone") == "dial", 5)
        for d in "2754109":                             # wrong
            await asyncio.sleep(D / 2)
            await h.b.update("trunk/3/digit", d)
        await h.b.wait_until(lambda b: b.get("trunk/3/tone") == "busy", 5)
        for _ in range(2):                              # out of the trunk, back to her
            await h.b.update(f"{c}/op", "off")
            await h.b.update("trunk/3/seize", "off")
            await h.b.update("trunk/3/peer", "")
            await h.b.update(f"{c}/peer", "")
            await asyncio.sleep(HOLD + D * 2)
            await h.b.update(f"{c}/op", "on")
            await asyncio.sleep(D * 20)
        await asyncio.sleep(60)

    r = await h.run(station_to_outside, op)
    played = [v for k, v in h.link.sent if k == "station/12/play/set"]
    assert not r.ok and r.reason == Reason.NOT_CONNECTED, f"not connected: {r.reason!r}"
    assert played.count("t.1") == 2, f"asked again once: {played}"
    assert played[-1] == "giveup.1" or "giveup.1" in played, f"then gave up: {played}"
    assert any("gives up" in e for e in h.events), h.events
