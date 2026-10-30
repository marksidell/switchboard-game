"""Run the scene code against a simulated controller, audio program and operator.

No broker, no hardware. FakeLink stands in for Link: each command is echoed
back into the Board as the real client would echo it, after a short delay.
"""

import asyncio
import logging
import sys

from sbgame.board import Board, Offline
from sbgame.link import Hw
from sbgame.scenes import Line, Scene, dial_out, log_changes, st, station_to_station

logging.basicConfig(level=logging.INFO, format="%(relativeCreated)6.0f %(name)-6s %(message)s",
                    stream=sys.stdout)
log = logging.getLogger("test")

D = 0.02  # echo delay
HOLD = 2 * D  # Board.HOLD at the tests' speed (game_control.md §4, Rev 45)


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


async def bring_up(b: Board) -> None:
    await b.set_broker(True)
    await b.update("ctl/status", "online")
    await b.update("ctl/audio_status", "online")
    await b.update("ctl/esp_heartbeat", "1")
    assert b.control_up and b.audio_up


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


async def main() -> None:
    logging.getLogger("board").setLevel(logging.WARNING)
    quiet = logging.getLogger("scene")

    print("\n== 1. happy path")
    r, link, b = await run_scene()
    print("result:", r)
    assert r == "completed", r
    assert not b.on("station/12/hook") and not b.on("station/2/hook"), "cleanup hung up both"

    quiet.setLevel(logging.WARNING)
    print("\n== 2. operator pulls the cord mid-conversation")
    r, *_ = await run_scene(pull_after_lines=1)
    print("result:", r)
    assert r.startswith("abandoned"), r

    print("\n== 3. operator rings the wrong station")
    r, *_ = await run_scene(ring=5)
    print("result:", r)
    assert r == "wrong station 5", r

    print("\n== 4. controller drops out while the scene waits for an answer")
    b = Board(hold=HOLD); link = FakeLink(b); hw = Hw(link)
    await bring_up(b)
    t = asyncio.create_task(station_to_station(b, hw, SC))
    await asyncio.sleep(0.1)
    await b.update("ctl/status", "offline")
    try:
        await t
        raise AssertionError("expected Offline")
    except Offline as e:
        print("raised Offline:", e)
    assert ("station/12/hook/set", "off") in link.sent, "finally still hung up"

    print("\n== 5. file shorter than one wakeup: name -> '' before the waiter runs")
    b = Board(hold=HOLD); link = FakeLink(b); hw = Hw(link); link.file_len = 0
    await bring_up(b)
    from sbgame.scenes import say
    await asyncio.wait_for(say(b, hw, st(3), "blip", 0.5), 1)
    print("say() returned; play =", repr(b.get("station/3/play")))
    try:
        await say(b, hw, st(3), "nosuch", 0.5)
    except FileNotFoundError as e:
        print("missing file raised FileNotFoundError:", e)

    print("\n== 5b. a stop's late echo does not end the next play (2026-10-22)")
    b = Board(hold=HOLD); link = FakeLink(b); hw = Hw(link); link.file_len = D * 6
    await bring_up(b)
    await b.update("station/3/play", "before")
    await hw.stop(st(3))                       # its "" echo lands after say()'s expect,
    await asyncio.sleep(D / 2)                 # and before the new play's own echo
    t0 = asyncio.get_running_loop().time()
    await say(b, hw, st(3), "after", D * 6)
    took = asyncio.get_running_loop().time() - t0
    print(f"say() took {took:.3f}s for a {D * 6:.3f}s file")
    assert took >= D * 6, "say() returned on the stop's echo"

    print("\n== 6. outgoing: operator seizes trunk 4 and dials 275-4101")
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

    asyncio.create_task(dialler("2754101"))
    t = await dial_out(b, hw, "station/16", "2754101", busy=True)
    await asyncio.sleep(0.05)
    print("trunk", t, "dialled", b.dialled(t), "tone", b.get(f"trunk/{t}/tone"))
    assert b.get("trunk/4/tone") == "busy"
    await b.update("trunk/4/seize", "off")
    assert b.dialled(4) == "", "release clears the number"

    print("\n== 7. resync forgets values the broker no longer holds")
    await b.update("station/9/peer", "station/1")
    await b.reset_for_resync()
    assert b.get("station/9/peer") == ""
    assert not b.control_up
    print("after reset: control_up =", b.control_up, " station/9/peer =", repr(b.get("station/9/peer")))

    print("\nall passed")


asyncio.run(main())
