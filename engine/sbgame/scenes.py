"""Scene building blocks and two example scenes.

A scene is a coroutine: do something, then wait for the board to reach a
state. It runs as an asyncio task. It's cancelled by the game on reset, so
every scene cleans up in `finally`.

What can end a scene early:
  TimeoutError  the operator didn't do the thing in time
  Abandoned     the operator did something that breaks the call (pulled a cord)
  Offline       the controller or audio program went away; every wait fails at once
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from .board import Abandoned, Board, LIVE_AUDIO
from .link import Hw

log = logging.getLogger("scene")

ANSWER_TIMEOUT = 60  # s for the operator to answer a lamp
MAX_SPEECH = 20  # s, audio program's speech cap (audio.md §14); used for our own deadline
MARGIN = 3  # s added to audio deadlines (mqtt.md §8.2: game applies its own)


def st(n: int) -> str:
    return f"station/{n}"


def tk(n: int) -> str:
    return f"trunk/{n}"


# ---- building blocks -------------------------------------------------------


async def say(b: Board, hw: Hw, circuit: str, name: str, length: float,
              *, abort_if=None) -> None:
    """Play one utterance on a circuit and return when it has finished.

    `length` is the file's duration, known from the wav at load time. It sets
    our own deadline, in case the audio program never reports the end. Another
    say() on the same circuit replaces it, and it returns then: the loudspeaker
    carries the tutor's prompts and the wrong-cord lines (game_control.md §7.7).
    """
    key = f"{circuit}/play"
    echoed = False

    def over(b: Board):
        nonlocal echoed
        if b.saw(key, name):
            echoed = True
        elif echoed:                    # another say()'s expect() has cleared it
            return "replaced"
        return ((b.get(key) == "missing" and "missing")
                or (b.get(key) == "" and b.saw(key, name) and "done"))

    await b.expect(key)  # "pending" until the audio program echoes
    await hw.play(circuit, name)
    try:
        # Finished ("") or failed ("missing"). The "pending" set above means
        # the "" from before the command can't pass, and "" counts only once
        # this file's own name has been echoed, so the late "" of a stop sent
        # just before cannot either.
        r = await b.wait_until(over, length + MARGIN, abort_if=abort_if)
    except BaseException:
        await quietly(hw.stop(circuit))
        raise
    if r == "missing":
        raise FileNotFoundError(name)


async def hear(b: Board, hw: Hw, circuit: str, start_within: float,
               *, abort_if=None, max_speech: float | None = None) -> str:
    """Listen for the operator to speak and stop. Returns "silence" or "timeout".

    `max_speech`: speech that has run this long without a silence is taken as
    ended - the listen is cancelled and "silence" returned (game_control.md
    §6.2). Room noise or the loudspeaker on her headset can keep the detector
    in speech long after she has stopped, and the caller then never speaks.
    """
    key = f"{circuit}/listen"
    done = lambda b: b.get(key) in ("silence", "timeout") and b.get(key)
    await b.expect(key)  # the last listen's "silence" persists until replaced
    await hw.listen(circuit, start_within)
    try:
        if max_speech is None:
            return await b.wait_until(done, start_within + MAX_SPEECH + MARGIN,
                                      abort_if=abort_if, needs=(LIVE_AUDIO,))
        r = await b.wait_until(lambda b: done(b) or (b.get(key) == "speech" and "speech"),
                               start_within + MARGIN, abort_if=abort_if, needs=(LIVE_AUDIO,))
        if r != "speech":
            return r
        try:
            return await b.wait_until(done, max_speech, abort_if=abort_if, needs=(LIVE_AUDIO,))
        except TimeoutError:
            log.info("%s: speech ran %.0fs without a silence; taken as ended",
                     circuit, max_speech)
            await quietly(hw.listen(circuit, 0))
            return "silence"
    except BaseException:
        await quietly(hw.listen(circuit, 0))
        raise


def connected(a: str, c: str):
    """abort_if predicate: the cord between a and c has been pulled."""
    def broken(b: Board):
        return b.get(f"{a}/peer") != c and f"{a} no longer connected to {c}"
    return broken


def ringing_station(b: Board) -> int | None:
    """Which station the operator is ringing, if any."""
    for n in range(1, 23):
        if b.on(f"station/{n}/ring"):
            return n
    return None


async def quietly(coro) -> None:
    try:
        await coro
    except Exception:
        pass


# ---- script data ------------------------------------------------------------


@dataclass
class Line:
    who: str  # "caller" or "called"
    wav: str  # e.g. "pike-breakfast.3"
    length: float


@dataclass
class Scene:
    id: str
    caller: str  # circuit id
    called: str | None  # circuit id for a station; None for outside or no-called
    dial: str | None  # number the operator must dial, for outgoing trunk calls
    busy: bool
    request: Line
    lines: list[Line]


# ---- scenes -----------------------------------------------------------------


async def station_to_station(b: Board, hw: Hw, sc: Scene) -> str:
    """Caller station lifts, operator answers, takes request, rings called station.

    Returns an outcome string for the session log.
    """
    caller_n = int(sc.caller.split("/")[1])
    called_n = int(sc.called.split("/")[1])
    try:
        await hw.hook(caller_n, True)  # lamp lights on the switchboard

        # Operator plugs the answering cord in and throws the listening key.
        try:
            await b.wait_until(lambda b: b.on(f"{sc.caller}/op"), ANSWER_TIMEOUT)
        except TimeoutError:
            return "unanswered"

        caller_gone = lambda b: not b.on(f"{sc.caller}/op") and not b.get(f"{sc.caller}/peer") \
            and "operator pulled the answering cord"

        await hear(b, hw, sc.caller, 8, abort_if=caller_gone)  # "Number, please"
        await say(b, hw, sc.caller, sc.request.wav, sc.request.length, abort_if=caller_gone)

        # Operator plugs the calling cord into the called jack and rings it.
        # No abort_if here: with the listening key restored and no peer yet,
        # "cord still in" and "cord pulled" look the same, so the timeout decides.
        n = await b.wait_until(ringing_station, 45)
        if n != called_n:
            log.info("%s: rang station %d, wanted %d", sc.id, n, called_n)
            return f"wrong station {n}"

        await asyncio.sleep(1.5)  # let it ring a little before picking up
        await hw.hook(called_n, True)
        await b.wait_until(lambda b: b.get(f"{sc.caller}/peer") == sc.called, 10)

        # Conversation. Pulling either cord ends it.
        broken = connected(sc.caller, sc.called)
        for line in sc.lines:
            where = sc.caller if line.who == "caller" else sc.called
            await say(b, hw, where, line.wav, line.length, abort_if=broken)
        return "completed"

    except Abandoned as e:
        return f"abandoned: {e}"
    finally:
        # Runs on normal exit, error, and cancellation (game reset).
        for n in (caller_n, called_n):
            await quietly(hw.hook(n, False))
        for c in (sc.caller, sc.called):
            await quietly(hw.stop(c))


async def dial_out(b: Board, hw: Hw, caller: str, number: str, busy: bool) -> int:
    """Operator takes a trunk and dials. Returns the trunk once the far end rings.

    Raises Abandoned if the trunk is released or the wrong number is dialled.
    """
    # A trunk seized and patched to our caller is the one she picked.
    def seized_for_caller(b: Board):
        for t in range(1, 9):
            if b.on(f"trunk/{t}/seize") and b.get(f"trunk/{t}/peer") == caller:
                return t
        return None

    t = await b.wait_until(seized_for_caller, 45)
    released = lambda b: not b.on(f"trunk/{t}/seize") and "trunk released"
    try:
        await hw.tone(t, "dial")
        # Dial tone stops at the first digit.
        await b.wait_until(lambda b: b.dialled(t), 20, abort_if=released)
        await hw.tone(t, "off")
        got = await b.wait_until(lambda b: len(b.dialled(t)) >= len(number) and b.dialled(t),
                                 30, abort_if=released)
        if got != number:
            raise Abandoned(f"dialled {got}, wanted {number}")
        await hw.tone(t, "busy" if busy else "ringback")
        return t
    except BaseException:
        await quietly(hw.tone(t, "off"))
        raise


# ---- reporting ----------------------------------------------------------------


async def log_changes(b: Board) -> None:
    """Console log of every change. SQLite and the iPad feed read the same stream."""
    async for ch in b.watch():
        log.info("%-22s %r -> %r", ch.key, ch.old, ch.new)
