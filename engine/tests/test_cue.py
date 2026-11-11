"""The ring cue (game_control.md §9.2), against FakeLink's audio program."""

import asyncio
import contextlib

from sbgame.board import Board
from sbgame.cue import CUE, PLAY, RingCue
from sbgame.link import Hw

from harness import D, FakeLink, HOLD, bring_up

SETTLE = D * 4


def plays(link: FakeLink) -> list[str]:
    return [p for k, p in link.sent if k == f"{PLAY}/set"]


@contextlib.asynccontextmanager
async def ring_cue():
    """A board with every client up and the ring cue watching it."""
    b = Board(hold=HOLD)
    link = FakeLink(b)
    link.file_len = 1.0                 # the cue's length, at test speed
    await bring_up(b)
    cue = RingCue(b, Hw(link))
    task = asyncio.create_task(cue.run())
    await asyncio.sleep(D)
    try:
        yield b, link, cue
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_the_cue_follows_ring():
    async with ring_cue() as (b, link, cue):
        await b.update("station/3/ring", "on")
        await asyncio.sleep(SETTLE)
        assert plays(link) == [CUE] and b.get(PLAY) == CUE, "ring on: the cue plays on the monitor"
        await b.update("station/5/ring", "on")
        await b.update("station/3/ring", "off")
        await asyncio.sleep(SETTLE)
        assert plays(link) == [CUE] and b.get(PLAY) == CUE, "a second station ringing changes nothing"
        await b.update("station/5/ring", "off")
        await asyncio.sleep(SETTLE)
        assert plays(link) == [CUE, "stop"] and b.get(PLAY) == "", "the last ring off: stopped"


async def test_never_over_the_tutor():
    async with ring_cue() as (b, link, cue):
        link.sent.clear()
        await Hw(link).play("audio/monitor", "tutor.ring-rear-room403")
        await asyncio.sleep(SETTLE)
        link.sent.clear()
        await b.update("station/4/ring", "on")
        await asyncio.sleep(SETTLE)
        assert plays(link) == [], "not over her voice"
        await b.update(PLAY, "")            # she is cut short, or finishes
        await asyncio.sleep(SETTLE)
        assert plays(link) == [CUE], "the cue as soon as she stops, while ring lasts"
        link.sent.clear()
        await Hw(link).play("audio/monitor", "tutor.answer-station")   # she begins over it
        await asyncio.sleep(SETTLE)
        link.sent.clear()
        await b.update("station/4/ring", "off")
        await asyncio.sleep(SETTLE)
        assert plays(link) == [] and b.get(PLAY) == "tutor.answer-station", "ring off leaves her alone"
        await Hw(link).stop("audio/monitor")
        await asyncio.sleep(SETTLE)


async def test_short_and_long_rings():
    async with ring_cue() as (b, link, cue):
        link.sent.clear()
        await b.update("station/6/ring", "on")
        await b.update("station/6/ring", "off")      # before the echo
        await asyncio.sleep(SETTLE)
        assert plays(link) == [CUE, "stop"] and b.get(PLAY) == "", "off before the echo: still stopped"
        link.sent.clear()
        link.file_len = D * 3
        await b.update("station/7/ring", "on")
        await asyncio.sleep(D * 12)
        assert plays(link).count(CUE) >= 2 and "stop" not in plays(link), "a cue run to its end starts again while ring lasts"
        await b.update("station/7/ring", "off")
        await asyncio.sleep(SETTLE)
        assert plays(link)[-1] == "stop", "and stops with it"


async def test_file_missing_gives_up():
    async with ring_cue() as (b, link, cue):
        link.sent.clear()
        await b.update("station/8/ring", "on")
        await asyncio.sleep(D / 2)
        await b.update(PLAY, "missing")              # the audio program could not load it
        await asyncio.sleep(SETTLE)
        await b.update("station/8/ring", "off")
        await b.update("station/8/ring", "on")
        await asyncio.sleep(SETTLE)
        assert cue.broken and plays(link).count(CUE) == 1, "missing: given up, not retried"
