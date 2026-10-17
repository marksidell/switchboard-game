"""The ring cue (game_control.md §6.6, Rev 51), against FakeLink's audio program.

    cd engine && PYTHONPATH=.:tests ./.venv/bin/python tests/test_cue.py
"""

import asyncio
import sys

from sbgame.board import Board
from sbgame.cue import CUE, PLAY, RingCue
from sbgame.link import Hw

from test_sim import D, FakeLink, HOLD, bring_up

failures = 0


def check(ok: bool, what: str) -> None:
    global failures
    print(f"    {what:<58} {'ok' if ok else 'FAIL'}")
    if not ok:
        failures += 1


def plays(link: FakeLink) -> list[str]:
    return [p for k, p in link.sent if k == f"{PLAY}/set"]


async def main() -> int:
    b = Board(hold=HOLD)
    link = FakeLink(b)
    link.file_len = 1.0                 # the cue's length, at test speed
    await bring_up(b)
    cue = RingCue(b, Hw(link))
    task = asyncio.create_task(cue.run())
    await asyncio.sleep(D)
    settle = D * 4

    print("== the ring cue")
    await b.update("station/3/ring", "on")
    await asyncio.sleep(settle)
    check(plays(link) == [CUE] and b.get(PLAY) == CUE, "ring on: the cue plays on the monitor")
    await b.update("station/5/ring", "on")
    await b.update("station/3/ring", "off")
    await asyncio.sleep(settle)
    check(plays(link) == [CUE] and b.get(PLAY) == CUE, "a second station ringing changes nothing")
    await b.update("station/5/ring", "off")
    await asyncio.sleep(settle)
    check(plays(link) == [CUE, "stop"] and b.get(PLAY) == "", "the last ring off: stopped")

    print("== the tutor first")
    link.sent.clear()
    await Hw(link).play("audio/monitor", "tutor.ring-rear-room403")
    await asyncio.sleep(settle)
    link.sent.clear()
    await b.update("station/4/ring", "on")
    await asyncio.sleep(settle)
    check(plays(link) == [], "not over her voice")
    await b.update(PLAY, "")            # she is cut short, or finishes
    await asyncio.sleep(settle)
    check(plays(link) == [CUE], "the cue as soon as she stops, while ring lasts")
    link.sent.clear()
    await Hw(link).play("audio/monitor", "tutor.answer-station")   # she begins over it
    await asyncio.sleep(settle)
    link.sent.clear()
    await b.update("station/4/ring", "off")
    await asyncio.sleep(settle)
    check(plays(link) == [] and b.get(PLAY) == "tutor.answer-station",
          "ring off leaves her alone")
    await Hw(link).stop("audio/monitor")
    await asyncio.sleep(settle)

    print("== a short ring, and a long one")
    link.sent.clear()
    await b.update("station/6/ring", "on")
    await b.update("station/6/ring", "off")      # before the echo
    await asyncio.sleep(settle)
    check(plays(link) == [CUE, "stop"] and b.get(PLAY) == "", "off before the echo: still stopped")
    link.sent.clear()
    link.file_len = D * 3
    await b.update("station/7/ring", "on")
    await asyncio.sleep(D * 12)
    check(plays(link).count(CUE) >= 2 and "stop" not in plays(link),
          "a cue run to its end starts again while ring lasts")
    await b.update("station/7/ring", "off")
    await asyncio.sleep(settle)
    check(plays(link)[-1] == "stop", "and stops with it")

    print("== the file missing")
    link.sent.clear()
    await b.update("station/8/ring", "on")
    await asyncio.sleep(D / 2)
    await b.update(PLAY, "missing")              # the audio program could not load it
    await asyncio.sleep(settle)
    await b.update("station/8/ring", "off")
    await b.update("station/8/ring", "on")
    await asyncio.sleep(settle)
    check(cue.broken and plays(link).count(CUE) == 1, "missing: given up, not retried")

    task.cancel()
    print("\nFAILURES" if failures else "\nall ok")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
