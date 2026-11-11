"""The building blocks in scenes.py, and the Board under them, against the
simulated controller, audio program and operator of harness.py.
"""

import asyncio

import pytest

from sbgame.board import Board, Offline
from sbgame.link import Hw
from sbgame.scenes import Line, Scene, dial_out, log_changes, say, st, station_to_station

from harness import D, FakeLink, HOLD, bring_up


SC = Scene(
    id="pike-breakfast", caller=st(12), called=st(2), dial=None, busy=False,
    request=Line("caller", "pike-breakfast.1", 1),
    lines=[Line("called", "pike-breakfast.2", 1), Line("caller", "pike-breakfast.3", 1),
           Line("called", "pike-breakfast.4", 1)],
)


async def operator(b: Board, *, ring: int = 2, pull_after_lines: int | None = None) -> None:
    """A simulated operator: answer, take the request, ring, connect."""
    changes: asyncio.Queue = asyncio.Queue()
    b._watchers.add(changes)  # test-only: see every change from here on

    async def plays_finished(keys, n):
        """Wait until n files have finished playing on any of these circuits."""
        done = 0
        while done < n:
            ch = await changes.get()
            if ch.key in keys and ch.new == "" and ch.old not in ("", "pending"):
                done += 1

    await b.wait_until(lambda b: b.on("station/12/hook"), 5)          # lamp
    await asyncio.sleep(0.05)
    await b.update("station/12/op", "on")                              # answer
    await plays_finished({"station/12/play"}, 1)                       # request heard
    await b.update(f"station/{ring}/ring", "on")                       # ring
    await b.wait_until(lambda b: b.on(f"station/{ring}/hook"), 5)
    await b.update(f"station/{ring}/ring", "off")
    await b.update("station/12/peer", f"station/{ring}")
    await b.update(f"station/{ring}/peer", "station/12")
    if pull_after_lines is not None:
        await plays_finished({"station/12/play", "station/2/play"}, pull_after_lines)
        await b.update("station/12/peer", "")                          # yank the cord
        await b.update("station/2/peer", "")


async def run_scene(**op_kw):
    b = Board(hold=HOLD)
    link = FakeLink(b)
    hw = Hw(link)
    await bring_up(b)
    logger = asyncio.create_task(log_changes(b))
    opr = asyncio.create_task(operator(b, **op_kw))
    result = await station_to_station(b, hw, SC)
    await asyncio.sleep(0.1)
    opr.cancel()
    logger.cancel()
    return result, link, b


async def test_happy_path():
    r, link, b = await run_scene()
    assert r == "completed", r
    assert not b.on("station/12/hook") and not b.on("station/2/hook"), "cleanup hung up both"


async def test_cord_pulled_mid_conversation():
    r, *_ = await run_scene(pull_after_lines=1)
    assert r.startswith("abandoned"), r


async def test_wrong_station_rung():
    r, *_ = await run_scene(ring=5)
    assert r == "wrong station 5", r


async def test_controller_drops_out_while_waiting():
    b = Board(hold=HOLD); link = FakeLink(b); hw = Hw(link)
    await bring_up(b)
    t = asyncio.create_task(station_to_station(b, hw, SC))
    await asyncio.sleep(0.1)
    await b.update("ctl/status", "offline")
    with pytest.raises(Offline):
        await t
    assert ("station/12/hook/set", "off") in link.sent, "finally still hung up"


async def test_file_shorter_than_one_wakeup():
    """name -> '' before the waiter runs."""
    b = Board(hold=HOLD); link = FakeLink(b); hw = Hw(link); link.file_len = 0
    await bring_up(b)
    await asyncio.wait_for(say(b, hw, st(3), "blip", 0.5), 1)
    with pytest.raises(FileNotFoundError):
        await say(b, hw, st(3), "nosuch", 0.5)


async def test_late_stop_echo_does_not_end_next_play():
    b = Board(hold=HOLD); link = FakeLink(b); hw = Hw(link); link.file_len = D * 6
    await bring_up(b)
    await b.update("station/3/play", "before")
    await hw.stop(st(3))                       # its "" echo lands after say()'s expect,
    await asyncio.sleep(D / 2)                 # and before the new play's own echo
    t0 = asyncio.get_running_loop().time()
    await say(b, hw, st(3), "after", D * 6)
    took = asyncio.get_running_loop().time() - t0
    assert took >= D * 6, f"say() returned on the stop's echo, after {took:.3f}s"


async def test_dial_out_and_resync():
    """Outgoing: she seizes trunk 4 and dials 275-4101; then a resync forgets
    values the broker no longer holds."""
    b = Board(hold=HOLD); link = FakeLink(b); hw = Hw(link)
    await bring_up(b)

    async def dialler(number: str):
        await asyncio.sleep(0.05)
        await b.update("trunk/4/seize", "on")
        await b.update("trunk/4/peer", "station/16")
        await b.wait_until(lambda b: b.get("trunk/4/tone") == "dial", 2)
        for d in number:
            await asyncio.sleep(0.01)
            await b.update("trunk/4/digit", d)

    dialling = asyncio.create_task(dialler("2754101"))
    t = await dial_out(b, hw, "station/16", "2754101", busy=True)
    await dialling
    await asyncio.sleep(0.05)
    assert t == 4 and b.get("trunk/4/tone") == "busy"
    await b.update("trunk/4/seize", "off")
    assert b.dialled(4) == "", "release clears the number"

    await b.update("station/9/peer", "station/1")
    await b.reset_for_resync()
    assert b.get("station/9/peer") == ""
    assert not b.control_up
