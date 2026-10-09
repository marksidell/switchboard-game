"""The five call flows (game_control.md §4.3, §5, §6.1).

One coroutine per scene shape. Each drives the hardware, moves the call
through the §6.1 stages, reports the §4.3 "connected" milestone to the
scheduler, and returns a §5 outcome.

Three rules run through all five:

**A wrong connection is not a failure.** The operator who rings the wrong jack
and corrects herself within the connect timeout has made the call (§5). So
every "wait for the right thing" loop logs the wrong thing and keeps waiting
until the deadline, rather than ending the call. The game answers only the
correct station: a wrong one rings out and nobody picks up, which is Mark's
ruling for the MVP — contriving a wrong party to answer and say something is a
later refinement.

**Every flow cleans up in `finally`**, on a normal end, an error, and
cancellation — which is how Stop and losing a client arrive. Cleanup commands
are allowed to fail: the controller and the audio program release everything
themselves when they lose the game (mqtt.md §8.2).

**The monitor follows the answer** (§6.4). The moment the calling circuit's
`op` goes on while the call is in `signalling` is the answer, and the only
point in a call where the loudspeaker moves.

In tutor mode (§4.9, Rev 29) `ctx.tutor` is set, and the flows stop at each
step for her to say what comes next. Each place is marked `# tutor`. She is
never speaking while the game listens: every listen goes through
`_operator_speaks()`, which says her prompt first and waits for it to end.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

from .board import Abandoned, Board, LIVE_AUDIO, Offline
from .calls import Call, Reason, Slots, Stage
from .config import Config
from .link import Hw
from .script_data import SceneDef, Shape, Speech
from .scenes import _quietly, hear, ringing_station, say
from .tutor import REPEAT, REPEATS, Tutor

log = logging.getLogger("flow")


@dataclass
class Outcome:
    """How a call ended. `reason` is empty on success."""
    ok: bool
    reason: str = ""


@dataclass
class Ctx:
    """Everything a flow needs, so each takes one argument."""
    board: Board
    hw: Hw
    cfg: Config
    slots: Slots
    call: Call
    scene: SceneDef
    say_event: Callable[[str], None]              # one line into the game log
    mark_connected: Callable[[], Awaitable[None]]  # §4.3, for the scheduler
    set_monitor: Callable[[str], Awaitable[None]]  # §6.4
    tutor: Tutor | None = None                     # §4.9, in tutor mode
    jack_of: Callable[[int], int | None] = lambda n: None   # station -> its jack (§6.3)

    @property
    def b(self) -> Board:
        return self.board

    def left(self, deadline: float) -> float:
        """Seconds until a deadline, never negative."""
        return max(0.0, deadline - time.time())


# ---------------------------------------------------------------- pieces ----


def _tutoring(ctx: Ctx) -> Tutor | None:
    t = ctx.tutor
    return t if t is not None and t.active else None


async def _tut(ctx: Ctx, key: str, until=None, abort_if=None) -> None:
    """Tutor mode: her line for this step, said to its end (§4.9)."""
    if (t := _tutoring(ctx)) is not None:
        await t.say(key, until=until, abort_if=abort_if)


async def _operator_speaks(ctx: Ctx, where: str, sp: Speech, abort_if,
                           request: bool = False) -> None:
    """The game waits for the operator to speak before `sp` (§4.6).

    In tutor mode she is told what to say first, and told again if she does
    not, at most REPEATS times; then the line plays, as it would after a
    listen that timed out.
    """
    t = _tutoring(ctx)
    if t is None:
        await hear(ctx.b, ctx.hw, where, ctx.cfg.speak_timeout, abort_if=abort_if)
        return
    key = t.say_key(sp, request)
    for _ in range(REPEATS + 1):
        await t.say(key, abort_if=abort_if)
        if await hear(ctx.b, ctx.hw, where, REPEAT, abort_if=abort_if) == "silence":
            return


def _last_wait(sc: SceneDef) -> int | None:
    """The index of the conversation's last wait: line, if it has one."""
    waits = [i for i, line in enumerate(sc.conversation) if line.wait]
    return waits[-1] if waits else None


def _caller_circuit(sc: SceneDef, trunk: int | None) -> str:
    if sc.from_station is not None:
        return f"station/{sc.from_station}"
    return f"trunk/{trunk}"


async def _answer(ctx: Ctx, caller: str) -> None:
    """Stage `signalling` until the operator answers, then move the monitor.

    Raises TimeoutError, which the caller turns into `no answer` (§5).
    """
    deadline = time.time() + ctx.cfg.answer_timeout
    await ctx.slots.set_stage(ctx.call, Stage.SIGNALLING, deadline)
    op = lambda b: b.on(f"{caller}/op")
    # tutor: from a room the game cannot see the cord go in, so both steps
    # are one line; a trunk is seized by the cord, so they are two (§4.9).
    if _tutoring(ctx) is not None:
        if caller.startswith("station/"):
            await _tut(ctx, "answer-station", until=op)
        else:
            seized = lambda b: b.on(f"{caller}/seize") or b.on(f"{caller}/op")
            await _tut(ctx, "answer-trunk", until=seized)
            await ctx.b.wait_until(seized, ctx.left(deadline))
            await _tut(ctx, "talk", until=op)
    await ctx.b.wait_until(op, ctx.left(deadline))
    # §6.4: the answer is the one point the loudspeaker moves.
    await ctx.set_monitor(caller)
    ctx.say_event(f"monitor: {ctx.scene.from_line}")


async def _request(ctx: Ctx, caller: str, abort_if) -> None:
    """Stage `request`: the operator speaks, then the caller's request plays."""
    await ctx.slots.set_stage(ctx.call, Stage.REQUEST,
                              time.time() + ctx.scene.request.seconds
                              + ctx.cfg.speak_timeout + ctx.cfg.audio_margin)
    # "Number, please" — we only need to know she spoke and stopped.
    await _operator_speaks(ctx, caller, ctx.scene.request, abort_if, request=True)
    await _play(ctx, caller, ctx.scene.request, abort_if)


async def _play(ctx: Ctx, circuit: str, sp: Speech, abort_if) -> None:
    await say(ctx.b, ctx.hw, circuit, sp.name, sp.seconds, abort_if=abort_if)


async def _hold(ctx: Ctx, seconds: float, abort_if) -> None:
    """Let `seconds` pass, unless abort_if comes true first (Abandoned)."""
    try:
        await ctx.b.wait_until(lambda b: False, seconds, abort_if=abort_if)
    except TimeoutError:
        pass


async def _lead_in(ctx: Ctx, circuit: str, sp: Speech, abort_if) -> None:
    """A line's pause: and ringback: (§4.6, Rev 20), after any wait.

    The pause is silence: the next operator on the route taking the call, a
    party walking to the telephone. Ringback is the far end ringing, heard on
    the trunk, and stops before the line that answers it.
    """
    if sp.pause:
        await _hold(ctx, sp.pause, abort_if)
    if sp.ringback and circuit.startswith("trunk/"):
        n = int(circuit.split("/")[1])
        await ctx.hw.tone(n, "ringback")
        try:
            await _hold(ctx, sp.ringback, abort_if)
        finally:
            await _quietly(ctx.hw.tone(n, "off"))


async def _wait_for_right_station(ctx: Ctx, want: int, deadline: float) -> None:
    """Wait until the operator rings the wanted station (§5).

    A wrong station is logged and ignored: it rings out, the game does not
    answer it, and the operator has until the connect timeout to correct
    herself. Raises TimeoutError if she never does.
    """
    # tutor: which jack, and which switch rings it (§4.9).
    if _tutoring(ctx) is not None and (jack := ctx.jack_of(want)) is not None:
        cord = "front" if ctx.scene.from_station is not None else "rear"
        await _tut(ctx, f"ring-{cord}-{jack}",
                   until=lambda b: b.on(f"station/{want}/ring"))
    wrong_seen: set[int] = set()
    while True:
        n = await ctx.b.wait_until(ringing_station, ctx.left(deadline))
        if n == want:
            return
        if n not in wrong_seen:
            wrong_seen.add(n)
            ctx.say_event(f"rang station {n}, wanted {want}")
            log.info("%s: wrong station %d", ctx.scene.id, n)
        # Wait for that ring to stop before looking again, or ringing_station
        # returns the same wrong one immediately and we spin.
        await ctx.b.wait_until(lambda b, n=n: not b.on(f"station/{n}/ring"),
                               ctx.left(deadline))


def _any_seized(b: Board) -> int | None:
    for n in range(1, 9):
        if b.on(f"trunk/{n}/seize"):
            return n
    return None


async def _seized_trunk(ctx: Ctx, deadline: float) -> int:
    """Which trunk the operator has taken."""
    return await ctx.b.wait_until(_any_seized, ctx.left(deadline))


def _dial_key(sc: SceneDef) -> str:
    """The tutor's line telling her what to dial (§4.9)."""
    return "dial-operator" if sc.dial == "0" else f"dial-{sc.to_line}"


async def _wait_for_right_number(ctx: Ctx, trunk: int, want: str,
                                 deadline: float) -> int:
    """Wait until the wanted number is dialled (§5).

    A wrong number is logged, and the flow keeps waiting. A redial arrives as
    a release and a fresh seizure, which clears `dialled` (board.py), so this
    also follows the operator onto another trunk if she takes one.
    """
    digits = "".join(c for c in want if c.isdigit())
    wrong_seen: set[str] = set()
    while True:
        got = await ctx.b.wait_until(
            lambda b, t=trunk: (len(b.dialled(t)) >= len(digits) and b.dialled(t))
            or (not b.on(f"trunk/{t}/seize") and "released"),
            ctx.left(deadline))
        if got == "released":
            # She hung up the trunk: wait for the next seizure and start over.
            trunk = await _seized_trunk(ctx, deadline)
            await ctx.slots.set(ctx.call, "trunk", f"trunk/{trunk}")
            continue
        if got == digits:
            await ctx.slots.set(ctx.call, "digits", got)
            ctx.say_event(f"dialled {want} on trunk/{trunk}")
            return trunk
        if got not in wrong_seen:
            wrong_seen.add(got)
            ctx.say_event(f"dialled {got}, wanted {want}")
            log.info("%s: wrong number %s", ctx.scene.id, got)
        # Wait for her to release and try again.
        await ctx.b.wait_until(lambda b, t=trunk: not b.on(f"trunk/{t}/seize"),
                               ctx.left(deadline))


def _cord_broken(a: str, c: str):
    """abort_if: the cord between the two lines has gone (§5, `cut off`)."""
    def broken(b: Board):
        return b.get(f"{a}/peer") != c and f"cord pulled between {a} and {c}"
    return broken


async def _converse(ctx: Ctx, caller: str, called: str) -> None:
    """Stage `talking`: play the scripted conversation, turn by turn.

    A line marked wait: plays only after the operator has spoken on its side
    and stopped (§4.6) — "Long distance, please" to the local operator before
    the long-distance operator comes on. Raises TimeoutError if she never
    does, which the flow turns into `timeout` (§5).

    In tutor mode, after the last wait: line she is told to put the switch
    back, since the call needs nothing more from her (§4.9).
    """
    await ctx.slots.set_stage(ctx.call, Stage.TALKING, None)
    broken = _cord_broken(caller, called)
    last = _last_wait(ctx.scene)
    for i, line in enumerate(ctx.scene.conversation):
        where = caller if line.by == "caller" else called
        if line.wait:
            await _operator_speaks(ctx, where, line, broken)
            if i == last:
                await _tut(ctx, "center", abort_if=broken)              # tutor
        await _lead_in(ctx, where, line, broken)
        await _play(ctx, where, line, broken)


# ----------------------------------------------------------------- flows ----


async def station_to_station(ctx: Ctx) -> Outcome:
    sc = ctx.scene
    caller, called = f"station/{sc.from_station}", f"station/{sc.to_station}"
    try:
        await ctx.hw.hook(sc.from_station, True)          # the lamp lights
        try:
            await _answer(ctx, caller)
        except TimeoutError:
            return Outcome(False, Reason.NO_ANSWER)

        gone = lambda b: (not b.on(f"{caller}/op") and not b.get(f"{caller}/peer")
                          and "operator pulled the answering cord")
        try:
            await _request(ctx, caller, gone)
        except TimeoutError:
            return Outcome(False, Reason.TIMEOUT)

        deadline = time.time() + ctx.cfg.connect_timeout
        await ctx.slots.set_stage(ctx.call, Stage.ROUTING, deadline)
        try:
            await _wait_for_right_station(ctx, sc.to_station, deadline)
            await ctx.slots.set_stage(ctx.call, Stage.RINGING, deadline)
            await asyncio.sleep(1.5)                       # let it ring a little
            await ctx.hw.hook(sc.to_station, True)         # the called party answers
            await ctx.b.wait_until(
                lambda b: b.get(f"{caller}/peer") == called, ctx.left(deadline))
        except TimeoutError:
            return Outcome(False, Reason.NOT_CONNECTED)

        await ctx.mark_connected()
        try:
            await _converse(ctx, caller, called)
        except TimeoutError:
            return Outcome(False, Reason.TIMEOUT)
        return Outcome(True)
    except Abandoned:
        return Outcome(False, Reason.CUT_OFF)
    finally:
        for n in (sc.from_station, sc.to_station):
            if n is not None:
                await _quietly(ctx.hw.hook(n, False))
        for c in (caller, called):
            await _quietly(ctx.hw.stop(c))


async def station_to_outside(ctx: Ctx) -> Outcome:
    sc = ctx.scene
    caller = f"station/{sc.from_station}"
    trunk: int | None = None
    try:
        await ctx.hw.hook(sc.from_station, True)
        try:
            await _answer(ctx, caller)
        except TimeoutError:
            return Outcome(False, Reason.NO_ANSWER)

        gone = lambda b: (not b.on(f"{caller}/op") and not b.get(f"{caller}/peer")
                          and "operator pulled the answering cord")
        try:
            await _request(ctx, caller, gone)
        except TimeoutError:
            return Outcome(False, Reason.TIMEOUT)

        deadline = time.time() + ctx.cfg.connect_timeout
        await ctx.slots.set_stage(ctx.call, Stage.ROUTING, deadline)
        try:
            await _tut(ctx, "trunk-front", until=_any_seized)            # tutor
            trunk = await _seized_trunk(ctx, deadline)
            await ctx.slots.set(ctx.call, "trunk", f"trunk/{trunk}")
            await ctx.slots.set_stage(ctx.call, Stage.DIALLING, deadline)
            await ctx.hw.tone(trunk, "dial")
            await _tut(ctx, _dial_key(sc),                              # tutor
                       until=lambda b, t=trunk: b.dialled(t) or not b.on(f"trunk/{t}/seize"))
            trunk = await _wait_for_right_number(ctx, trunk, sc.dial, deadline)
        except TimeoutError:
            return Outcome(False, Reason.NOT_CONNECTED)

        called = f"trunk/{trunk}"
        await ctx.hw.tone(trunk, "ringback")
        await ctx.slots.set_stage(ctx.call, Stage.RINGING, None)
        # tutor: before the far end answers, so she does not talk over its
        # first line; ringback runs on until she has finished (§4.9).
        if _last_wait(sc) is None:
            await _tut(ctx, "center-dialled")
        await asyncio.sleep(2.0)                           # two bursts of ringback
        await ctx.hw.tone(trunk, "off")                    # the far end answers
        await ctx.mark_connected()

        try:
            await _converse(ctx, caller, called)
        except TimeoutError:
            return Outcome(False, Reason.TIMEOUT)
        return Outcome(True)
    except Abandoned:
        return Outcome(False, Reason.CUT_OFF)
    finally:
        if sc.from_station is not None:
            await _quietly(ctx.hw.hook(sc.from_station, False))
        if trunk is not None:
            await _quietly(ctx.hw.tone(trunk, "off"))
            await _quietly(ctx.hw.stop(f"trunk/{trunk}"))
        await _quietly(ctx.hw.stop(caller))


async def busy_scene(ctx: Ctx) -> Outcome:
    """An outgoing call that meets busy tone (§4.3: connected at busy tone)."""
    sc = ctx.scene
    caller = f"station/{sc.from_station}"
    trunk: int | None = None
    try:
        await ctx.hw.hook(sc.from_station, True)
        try:
            await _answer(ctx, caller)
        except TimeoutError:
            return Outcome(False, Reason.NO_ANSWER)

        gone = lambda b: (not b.on(f"{caller}/op") and not b.get(f"{caller}/peer")
                          and "operator pulled the answering cord")
        try:
            await _request(ctx, caller, gone)
        except TimeoutError:
            return Outcome(False, Reason.TIMEOUT)

        deadline = time.time() + ctx.cfg.connect_timeout
        await ctx.slots.set_stage(ctx.call, Stage.ROUTING, deadline)
        try:
            await _tut(ctx, "trunk-front", until=_any_seized)            # tutor
            trunk = await _seized_trunk(ctx, deadline)
            await ctx.slots.set(ctx.call, "trunk", f"trunk/{trunk}")
            await ctx.slots.set_stage(ctx.call, Stage.DIALLING, deadline)
            await ctx.hw.tone(trunk, "dial")
            await _tut(ctx, _dial_key(sc),                              # tutor
                       until=lambda b, t=trunk: b.dialled(t) or not b.on(f"trunk/{t}/seize"))
            trunk = await _wait_for_right_number(ctx, trunk, sc.dial, deadline)
        except TimeoutError:
            return Outcome(False, Reason.NOT_CONNECTED)

        await ctx.hw.tone(trunk, "busy")
        await ctx.slots.set_stage(ctx.call, Stage.BUSY,
                                  time.time() + ctx.cfg.speak_timeout)
        await ctx.mark_connected()                         # §4.3: busy tone starts

        # She goes back to the caller and says the line is engaged. The scene's
        # conversation is the caller's replies, each after she has spoken.
        try:
            await _tut(ctx, "busy-heard", abort_if=gone)                # tutor
            for line in ctx.scene.conversation:
                await _operator_speaks(ctx, caller, line, gone)
                await _lead_in(ctx, caller, line, gone)
                await _play(ctx, caller, line, gone)
        except TimeoutError:
            return Outcome(False, Reason.TIMEOUT)
        return Outcome(True)
    except Abandoned:
        return Outcome(False, Reason.CUT_OFF)
    finally:
        if sc.from_station is not None:
            await _quietly(ctx.hw.hook(sc.from_station, False))
        if trunk is not None:
            await _quietly(ctx.hw.tone(trunk, "off"))
        await _quietly(ctx.hw.stop(caller))


async def outside_to_station(ctx: Ctx, trunk: int) -> Outcome:
    """A call in from outside: the game rings a free trunk (§6.1 signalling)."""
    sc = ctx.scene
    caller, called = f"trunk/{trunk}", f"station/{sc.to_station}"
    try:
        await ctx.slots.set(ctx.call, "trunk", caller)
        await ctx.hw.short_ring(trunk)          # game_control.md §4.3, Rev 28
        try:
            await _answer(ctx, caller)
        finally:
            await _quietly(ctx.hw.ring_trunk(trunk, False))
    except TimeoutError:
        return Outcome(False, Reason.NO_ANSWER)

    try:
        gone = lambda b: (not b.on(f"{caller}/op") and not b.get(f"{caller}/peer")
                          and "operator pulled the answering cord")
        try:
            await _request(ctx, caller, gone)
        except TimeoutError:
            return Outcome(False, Reason.TIMEOUT)

        deadline = time.time() + ctx.cfg.connect_timeout
        await ctx.slots.set_stage(ctx.call, Stage.ROUTING, deadline)
        try:
            await _wait_for_right_station(ctx, sc.to_station, deadline)
            await ctx.slots.set_stage(ctx.call, Stage.RINGING, deadline)
            await asyncio.sleep(1.5)
            # tutor: she rang with the far switch, and the near one still has
            # her on the line, so before the room answers (§4.9).
            if _last_wait(sc) is None:
                await _tut(ctx, "center-ringing")
            await ctx.hw.hook(sc.to_station, True)
            await ctx.b.wait_until(
                lambda b: b.get(f"{caller}/peer") == called, ctx.left(deadline))
        except TimeoutError:
            return Outcome(False, Reason.NOT_CONNECTED)

        await ctx.mark_connected()
        try:
            await _converse(ctx, caller, called)
        except TimeoutError:
            return Outcome(False, Reason.TIMEOUT)
        return Outcome(True)
    except Abandoned:
        return Outcome(False, Reason.CUT_OFF)
    finally:
        await _quietly(ctx.hw.ring_trunk(trunk, False))
        if sc.to_station is not None:
            await _quietly(ctx.hw.hook(sc.to_station, False))
        for c in (caller, called):
            await _quietly(ctx.hw.stop(c))


async def to_operator(ctx: Ctx, trunk: int | None = None) -> Outcome:
    """No called party: the caller asks the operator something (§4.3).

    Connected when the request has finished playing. The conversation is the
    caller's lines alone, each played after the operator has spoken and
    stopped — script.yml's "Order" note, and why every line waits on a listen.

    From a room the station goes off-hook; from an outside line (Rev 24) the
    game rings `trunk`, as for a call in to a room. With no conversation the
    caller hangs up once the request has played — the long-distance operator's
    time and charges, said once and not waited on.
    """
    sc = ctx.scene
    caller = _caller_circuit(sc, trunk)
    try:
        if sc.from_station is not None:
            await ctx.hw.hook(sc.from_station, True)
        else:
            await ctx.slots.set(ctx.call, "trunk", caller)
            await ctx.hw.short_ring(trunk)      # game_control.md §4.3, Rev 28
        try:
            await _answer(ctx, caller)
        except TimeoutError:
            return Outcome(False, Reason.NO_ANSWER)
        finally:
            if trunk is not None:
                await _quietly(ctx.hw.ring_trunk(trunk, False))

        gone = lambda b: (not b.on(f"{caller}/op") and not b.get(f"{caller}/peer")
                          and "operator pulled the answering cord")
        try:
            await _request(ctx, caller, gone)
        except TimeoutError:
            return Outcome(False, Reason.TIMEOUT)
        await ctx.mark_connected()                         # §4.3: the request has played

        await ctx.slots.set_stage(ctx.call, Stage.OPERATOR,
                                  time.time() + ctx.cfg.speak_timeout)
        try:
            for line in ctx.scene.conversation:
                await _operator_speaks(ctx, caller, line, gone)
                await _lead_in(ctx, caller, line, gone)
                await _play(ctx, caller, line, gone)
        except TimeoutError:
            return Outcome(False, Reason.TIMEOUT)
        return Outcome(True)
    except Abandoned:
        return Outcome(False, Reason.CUT_OFF)
    finally:
        if sc.from_station is not None:
            await _quietly(ctx.hw.hook(sc.from_station, False))
        if trunk is not None:
            await _quietly(ctx.hw.ring_trunk(trunk, False))
        await _quietly(ctx.hw.stop(caller))


FLOWS = {
    Shape.STATION_TO_STATION: station_to_station,
    Shape.STATION_TO_OUTSIDE: station_to_outside,
    Shape.BUSY: busy_scene,
    Shape.TO_OPERATOR: to_operator,
    # outside_to_station, and to_operator from an outside line, take the trunk
    # they ring in on, so the game picks it.
}
