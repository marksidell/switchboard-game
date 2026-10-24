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
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from .board import Abandoned, Board, LIVE_AUDIO, Offline
from .calls import Call, Reason, Slots, Stage
from .config import Config
from .link import Hw
from .script_data import SceneDef, Shape, Speech
from .scenes import _quietly, hear, ringing_station, say
from .tutor import REPEAT, REPEATS, Tutor

# §5, Rev 46: dial tone comes this long after the trunk is seized, as an
# exchange takes a moment to connect a register; and a caller left with
# neither the operator nor a connection, with no trunk up, hangs up after
# ABANDON before the call is connected - ABANDON_MISDIALLED once she has
# dialled a wrong number for it (Rev 48: 10s and 5s, where Rev 46 had 20s).
DIAL_DELAY = 1.0
ABANDON = 10.0
ABANDON_MISDIALLED = 5.0
# §5, Rev 56: a number dialled with too many digits or too few gets reorder,
# the fast busy, and fails the call as `misdialled`. Too few is a pause of
# DIAL_PAUSE after a digit, short of the number; too many is a digit more
# within DIAL_SETTLE of the last one it needs, which is how long the game
# waits before it takes a number as dialled - longer than a dial takes to
# return and run ten pulses (control.md §8).
DIAL_PAUSE = 10.0
DIAL_SETTLE = 3.0
# §5, Rev 60: what a party does when the operator leaves it hanging. A party
# waiting for her to speak says "Hello? Operator?" after NUDGE_AFTER of
# silence, then goes on after as long again. A party she rings that is not
# patched to its caller says "Hello?" after PATCH_WAIT, and hangs up after as
# long again; one she rings by mistake answers, and hangs up. A trunk taken
# and not dialled for DIAL_FIRST gets reorder, outside tutor mode.
NUDGE_AFTER = 6.0
PATCH_WAIT = 8.0
# s between a party's last words and its hanging up (§5, Rev 75): the time it
# takes to put a receiver back on its hook.
HANG_UP = 1.5
DIAL_FIRST = 15.0
ANSWER_AFTER = 3.0        # s of ring before a room answers, right or wrong (Rev 82; 1.5 before)


class Misdialled(Exception):
    """A number dialled with too many digits or too few (§5, Rev 56)."""

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
    misdialled: bool = False                       # a wrong number this call (§5, Rev 48)
    # Rev 60: a party's reactions, by kind and cast member, and who answers a
    # room nobody expects to be rung.
    reaction: Callable[[str, str], Speech | None] = lambda kind, voice: None
    occupant: Callable[[int], str] = lambda n: ""
    # Rev 60: trunks already up when this call began to route, and not
    # released since: not this call's, so never taken as the one she seized.
    stale_trunks: set[int] = field(default_factory=set)
    # Rev 74: free calls (§4.12). The circuits of free callers, whether one is
    # waiting to be put through, and the public line, which no scene takes.
    free_callers: Callable[[], set[str]] = lambda: set()
    free_routing: Callable[[], bool] = lambda: False
    public_trunk: int = 0

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
        voice = ctx.scene.caller_voice if sp.by == "caller" else ctx.scene.called_voice
        nudge = ctx.reaction("nudge", voice)
        if nudge is None:
            await hear(ctx.b, ctx.hw, where, ctx.cfg.speak_timeout, abort_if=abort_if)
            return
        # Rev 60: not 30s of silence. "Hello? Operator?", then on with the line.
        if await hear(ctx.b, ctx.hw, where, NUDGE_AFTER, abort_if=abort_if) == "timeout":
            ctx.say_event(f"{where}: the operator did not speak")
            await say(ctx.b, ctx.hw, where, nudge.name, nudge.seconds, abort_if=abort_if)
            await hear(ctx.b, ctx.hw, where, NUDGE_AFTER, abort_if=abort_if)
        return
    key = t.say_key(sp, request)
    speaking = lambda: ctx.b.get(f"{where}/listen") == "speech"
    timeouts = 0
    try:
        while timeouts <= REPEATS:
            await t.say(key, abort_if=abort_if, listening=speaking)
            asked = t.asked
            if asked is None:                   # tutor switched off meanwhile
                await hear(ctx.b, ctx.hw, where, ctx.cfg.speak_timeout, abort_if=abort_if)
                return
            listen = asyncio.create_task(
                hear(ctx.b, ctx.hw, where, REPEAT, abort_if=abort_if))
            press = asyncio.create_task(asked.wait())
            pressed = False
            try:
                await asyncio.wait({listen, press}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                press.cancel()
                if not listen.done():
                    # Repeat Help (Rev 35): stop listening, say it again, and
                    # listen afresh. hear() cancels the listen as it unwinds.
                    pressed = True
                    listen.cancel()
                await asyncio.gather(press, listen, return_exceptions=True)
            if pressed:
                if not t.active:
                    await hear(ctx.b, ctx.hw, where, ctx.cfg.speak_timeout, abort_if=abort_if)
                    return
                continue                        # a press: not one of her repeats
            if listen.result() == "silence":
                return
            timeouts += 1
    finally:
        await t.release()


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
    if _tutoring(ctx) is not None and ctx.jack_of(want) is not None:
        cord = "front" if ctx.scene.from_station is not None else "rear"
        await _tut(ctx, f"ring-{cord}-{ctx.scene.to_line}",
                   until=lambda b: b.on(f"station/{want}/ring"))
    wrong_seen: set[int] = set()
    while True:
        n = await ctx.b.wait_until(ringing_station, ctx.left(deadline))
        if n == want:
            return
        if ctx.free_routing():
            # Rev 74: a free caller waits to be put through, so the room is
            # likely theirs (§4.12): not a wrong party for this call.
            await ctx.b.wait_until(lambda b, n=n: not b.on(f"station/{n}/ring"),
                                   ctx.left(deadline))
            continue
        if n not in wrong_seen:
            wrong_seen.add(n)
            ctx.say_event(f"rang station {n}, wanted {want}")
            log.info("%s: wrong station %d", ctx.scene.id, n)
        await _wrong_party(ctx, n, deadline)
        # Wait for that ring to stop before looking again, or ringing_station
        # returns the same wrong one immediately and we spin.
        await ctx.b.wait_until(lambda b, n=n: not b.on(f"station/{n}/ring"),
                               ctx.left(deadline))


async def _wrong_party(ctx: Ctx, n: int, deadline: float) -> None:
    """She has rung station n, not the one asked for (§5, Rev 60). Whoever is
    in that room answers, "Hello?"; the caller, if patched to it, says that is
    not who they asked for; and the room hangs up. Not a room already in a
    call, nor the caller's own."""
    caller = (f"station/{ctx.scene.from_station}" if ctx.scene.from_station is not None
              else ctx.call.trunk)
    room = f"station/{n}"
    hello = ctx.reaction("hello", ctx.occupant(n))
    if hello is None or ctx.b.on(f"{room}/hook") or n == ctx.scene.from_station:
        return
    try:
        await asyncio.sleep(ANSWER_AFTER)
        if ctx.b.on(f"{room}/hook"):
            return                      # taken meanwhile, by another call
        await ctx.hw.hook(n, True)
        ctx.say_event(f"station {n} answered: wrong party")
        await say(ctx.b, ctx.hw, room, hello.name, hello.seconds)
        wrong = ctx.reaction("wrong", ctx.scene.caller_voice)
        if wrong is not None and caller and ctx.b.get(f"{caller}/peer") == room:
            await say(ctx.b, ctx.hw, caller, wrong.name, wrong.seconds)
        await asyncio.sleep(0.5)
    finally:
        await _quietly(ctx.hw.hook(n, False))   # hangs up: the cord lamp lights


async def _picks_up(ctx: Ctx, caller: str, n: int, deadline: float) -> bool:
    """The called room answers; True once it is patched to the caller. Not
    patched within PATCH_WAIT, it says "Hello?"; not within as long again, it
    hangs up, and False: she must ring it again (§5, Rev 60)."""
    called = f"station/{n}"
    joined = lambda b: b.get(f"{caller}/peer") == called
    await ctx.hw.hook(n, True)                     # the called party answers
    hello = ctx.reaction("hello", ctx.scene.called_voice)
    if hello is None:
        await ctx.b.wait_until(joined, ctx.left(deadline))
        return True
    for step in ("hello", "hang up"):
        try:
            await ctx.b.wait_until(joined, min(PATCH_WAIT, ctx.left(deadline)))
            return True
        except TimeoutError:
            if ctx.left(deadline) <= 0:
                raise
        if step == "hello":
            ctx.say_event(f"{called} answered, not patched to {caller}")
            await say(ctx.b, ctx.hw, called, hello.name, hello.seconds)
    ctx.say_event(f"{called} hung up: nobody on the line")
    await ctx.hw.hook(n, False)
    return False


def _any_seized(b: Board) -> int | None:
    for n in range(1, 9):
        if b.on(f"trunk/{n}/seize"):
            return n
    return None


def _fresh(ctx: Ctx):
    """A trunk up that is this call's to take (Rev 60): not one already up
    when it began to route. A stale trunk released and taken again is fresh."""
    def seized(b: Board) -> int | None:
        free = ctx.free_callers()
        for n in range(1, 9):
            if not b.on(f"trunk/{n}/seize"):
                ctx.stale_trunks.discard(n)
            elif n == ctx.public_trunk or b.get(f"trunk/{n}/peer") in free:
                continue                # the public line, or a free call's (Rev 74)
            elif n not in ctx.stale_trunks:
                return n
        return None
    return seized


def _note_stale(ctx: Ctx) -> None:
    """The trunks up as routing begins belong to other calls, or are cords
    left in from an earlier one (Rev 60)."""
    ctx.stale_trunks = {n for n in range(1, 9) if ctx.b.on(f"trunk/{n}/seize")}


async def _seized_trunk(ctx: Ctx, deadline: float) -> int:
    """Which trunk the operator has taken for this call."""
    return await ctx.b.wait_until(_fresh(ctx), ctx.left(deadline))


async def _dial_tone(ctx: Ctx, trunk: int) -> None:
    """Dial tone on a freshly seized trunk, after DIAL_DELAY (§5, Rev 46)."""
    await asyncio.sleep(DIAL_DELAY)
    await ctx.hw.tone(trunk, "dial")


async def _unless_abandoned(ctx: Ctx, caller: str, work: Awaitable):
    """Run `work`, the routing of a call; raise Abandoned if the caller is lost
    for ABANDON seconds first (§5, Rev 46).

    Lost: the operator is not on the caller's line, it is patched to nothing,
    and no trunk is up - for a trunk caller, its own; for a station, any, since
    she may be dialling out for it. The game cannot see a cord go into or out
    of a station jack, so a pulled answering cord and a switch centred before
    the front cord goes in look the same; the wait is what tells them apart.
    """
    def lost(b: Board) -> bool:
        if b.on(f"{caller}/op") or b.get(f"{caller}/peer"):
            return False
        if caller.startswith("trunk/"):
            return not b.on(f"{caller}/seize")
        return _fresh(ctx)(b) is None

    async def watch() -> None:
        while True:
            await ctx.b.wait_until(lost, None)
            wait = ABANDON_MISDIALLED if ctx.misdialled else ABANDON
            try:
                await ctx.b.wait_until(lambda b: not lost(b), wait)
            except TimeoutError:
                return

    task = asyncio.ensure_future(work)
    watcher = asyncio.ensure_future(watch())
    try:
        done, _ = await asyncio.wait({task, watcher}, return_when=asyncio.FIRST_COMPLETED)
    except BaseException:
        task.cancel()
        watcher.cancel()
        await asyncio.gather(task, watcher, return_exceptions=True)
        raise
    if task in done:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
        return task.result()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    watcher.result()                                  # Offline, if that is what ended it
    ctx.say_event(f"{caller} hung up, left alone before connecting")
    raise Abandoned("caller lost before connecting")


async def _closing(ctx: Ctx, caller: str, abort_if) -> None:
    """Her closing words, waited for before the caller hangs up (§4.7, Rev 47).

    A scene's closing: is what she says after its last line - "That call was
    from the lobby, sir." In tutor mode she is prompted to say it. A closing
    not said within the speak timeout is let go: the caller hangs up and the
    call has still succeeded, since she has done everything it asked.
    """
    sc = ctx.scene
    if not sc.closing:
        await asyncio.sleep(HANG_UP)            # Rev 75
        return
    sp = Speech(name=sc.closing, seconds=0.0, by="caller", operator=sc.closing)
    try:
        await _operator_speaks(ctx, caller, sp, abort_if)
        await asyncio.sleep(HANG_UP)            # Rev 75
    except TimeoutError:
        log.info("%s: closing not heard", sc.id)
    except Abandoned:
        log.info("%s: cord pulled before the closing", sc.id)   # the call is over


def _dial_key(sc: SceneDef) -> str:
    """The tutor's line telling her what to dial (§4.9)."""
    return "dial-operator" if sc.dial == "0" else f"dial-{sc.to_line}"


async def _wait_for_right_number(ctx: Ctx, trunk: int, want: str,
                                 deadline: float) -> int:
    """Wait until the wanted number is dialled (§5).

    A wrong number is logged, and the flow keeps waiting. A redial arrives as
    a release and a fresh seizure, which clears `dialled` (board.py), so this
    also follows the operator onto another trunk if she takes one. Dial tone,
    which the caller has started, stops at the first digit and comes back on
    each fresh seizure (§5, Rev 42); a wrong number gets busy tone until she
    hangs up (Rev 46).
    """
    digits = "".join(c for c in want if c.isdigit())
    wrong_seen: set[str] = set()
    released = lambda b, t: not b.on(f"trunk/{t}/seize") and "released"
    while True:
        # Rev 60: a trunk not dialled gets reorder, as an exchange gave up on
        # a register left waiting - but not while the tutor teaches (§4.9).
        first = ctx.left(deadline) if _tutoring(ctx) else min(DIAL_FIRST, ctx.left(deadline))
        try:
            got = await ctx.b.wait_until(
                lambda b, t=trunk: b.dialled(t) or released(b, t), first)
        except TimeoutError:
            if first >= ctx.left(deadline):
                raise
            got = "none"
        if got == "none":
            await _reorder(ctx, trunk, "none", want, deadline)
        if got != "released":
            await ctx.hw.tone(trunk, "off")
            got = await _number(ctx, trunk, len(digits), deadline)
        if got in ("short", "long"):
            await _reorder(ctx, trunk, got, want, deadline)
        if got == "released":
            # She hung up the trunk: wait for the next seizure and start over.
            await ctx.hw.tone(trunk, "off")
            trunk = await _seized_trunk(ctx, deadline)
            await ctx.slots.set(ctx.call, "trunk", f"trunk/{trunk}")
            await _dial_tone(ctx, trunk)
            continue
        if got == digits:
            await ctx.slots.set(ctx.call, "digits", got)
            ctx.say_event(f"dialled {want} on trunk/{trunk}")
            return trunk
        if got not in wrong_seen:
            wrong_seen.add(got)
            ctx.say_event(f"dialled {got}, wanted {want}")
            log.info("%s: wrong number %s", ctx.scene.id, got)
        await ctx.hw.tone(trunk, "busy")                # Rev 46: not silence
        ctx.misdialled = True                           # Rev 48: less patience
        # Wait for her to release and try again.
        await ctx.b.wait_until(lambda b, t=trunk: not b.on(f"trunk/{t}/seize"),
                               ctx.left(deadline))


async def _number(ctx: Ctx, trunk: int, n: int, deadline: float) -> str:
    """The digits once a number of `n` is dialled, or "short", "long" or
    "released" (§5, Rev 56). The first digit is in already."""
    while True:
        have = ctx.b.dialled(trunk)
        if len(have) > n:
            return "long"
        wait = DIAL_SETTLE if len(have) == n else DIAL_PAUSE
        left = ctx.left(deadline)
        try:
            got = await ctx.b.wait_until(
                lambda b, t=trunk, k=len(have): ((not b.on(f"trunk/{t}/seize") and "released")
                                                 or len(b.dialled(t)) > k),
                min(wait, left))
        except TimeoutError:
            if wait >= left:
                raise                   # the call's own deadline, not the pause
            return have if len(have) == n else "short"
        if got == "released":
            return "released"


async def _reorder(ctx: Ctx, trunk: int, why: str, want: str, deadline: float) -> None:
    """Fast busy until she releases the trunk, then the call fails (§5, Rev 56)."""
    got = ctx.b.dialled(trunk)
    what = {"long": "too many digits", "short": "too few digits", "none": "nothing dialled"}[why]
    ctx.say_event(f"dialled {got or 'nothing'}, wanted {want}: {what}")
    log.info("%s: misdialled %s (%s)", ctx.scene.id, got, why)
    try:
        await ctx.hw.tone(trunk, "reorder")
        await ctx.b.wait_until(lambda b, t=trunk: not b.on(f"trunk/{t}/seize"),
                               ctx.left(deadline))
    finally:
        await _quietly(ctx.hw.tone(trunk, "off"))
    raise Misdialled(why)


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
                await _tut(ctx, "center", until=_centred(caller, called),  # tutor
                           abort_if=broken)
        await _lead_in(ctx, where, line, broken)
        await _play(ctx, where, line, broken)
    await asyncio.sleep(HANG_UP)                # Rev 75: then the receivers go down


def _centred(*circuits: str):
    """until: her talk switch is back in the centre - she is on none of the
    pair's lines - so the prompt to centre it can stop (§4.9, Rev 58)."""
    return lambda b: not any(b.on(f"{c}/op") for c in circuits)


def _engaged(n: int):
    """Station n off-hook in another call: calling, or answered (§4.11)."""
    return lambda b: b.on(f"station/{n}/hook")


async def _route_unless_engaged(ctx: Ctx, want: int, deadline: float) -> bool:
    """Wait for the operator to ring `want`, as _wait_for_right_station does,
    unless the scene has if_busy: and the station is found engaged first.
    True if it is engaged (§4.11). Raises TimeoutError if neither happens."""
    if not ctx.scene.if_busy:
        await _wait_for_right_station(ctx, want, deadline)
        return False
    engaged = _engaged(want)
    if engaged(ctx.b):
        return True
    route = asyncio.create_task(_wait_for_right_station(ctx, want, deadline))
    found = asyncio.create_task(ctx.b.wait_until(engaged, ctx.left(deadline)))
    try:
        await asyncio.wait({route, found}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in (route, found):
            if not t.done():
                t.cancel()
        await asyncio.gather(route, found, return_exceptions=True)
    if route.done() and not route.cancelled() and route.exception() is None:
        return engaged(ctx.b)       # rung, but taken meanwhile: still engaged
    if found.done() and not found.cancelled() and found.exception() is None:
        return True
    raise TimeoutError


async def _found_engaged(ctx: Ctx, caller: str, gone) -> Outcome:
    """The called station is engaged: she tells the caller, who replies with
    the if_busy: lines, each after she has spoken (§4.11)."""
    ctx.say_event(f"{ctx.scene.to_line} is engaged")
    await ctx.slots.set_stage(ctx.call, Stage.BUSY, time.time() + ctx.cfg.speak_timeout)
    await ctx.mark_connected()                             # §4.3, Rev 39
    try:
        for line in ctx.scene.if_busy:
            await _operator_speaks(ctx, caller, line, gone)
            await _lead_in(ctx, caller, line, gone)
            await _play(ctx, caller, line, gone)
        await asyncio.sleep(HANG_UP)            # Rev 75
    except TimeoutError:
        return Outcome(False, Reason.TIMEOUT)
    return Outcome(True)


# ----------------------------------------------------------------- flows ----


async def station_to_station(ctx: Ctx) -> Outcome:
    sc = ctx.scene
    caller, called = f"station/{sc.from_station}", f"station/{sc.to_station}"
    answered = False                # the called station is off-hook for this call
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
        async def route() -> Outcome | None:
            nonlocal answered
            while True:
                if await _route_unless_engaged(ctx, sc.to_station, deadline):
                    return await _found_engaged(ctx, caller, gone)
                await ctx.slots.set_stage(ctx.call, Stage.RINGING, deadline)
                await asyncio.sleep(ANSWER_AFTER)          # let it ring a little
                if sc.if_busy and _engaged(sc.to_station)(ctx.b):
                    return await _found_engaged(ctx, caller, gone)
                answered = True
                if await _picks_up(ctx, caller, sc.to_station, deadline):
                    return None
                answered = False                           # hung up: ring it again
                await ctx.slots.set_stage(ctx.call, Stage.ROUTING, deadline)
        try:
            engaged = await _unless_abandoned(ctx, caller, route())
            if engaged is not None:
                return engaged
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
        # A station found engaged belongs to the other call: leave it be.
        for n in (sc.from_station, sc.to_station if answered or not sc.if_busy else None):
            if n is not None:
                await _quietly(ctx.hw.hook(n, False))
        await _quietly(ctx.hw.stop(caller))
        if answered or not sc.if_busy:
            await _quietly(ctx.hw.stop(called))


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
        _note_stale(ctx)
        async def route() -> int:
            await _tut(ctx, "trunk-front", until=_fresh(ctx))            # tutor
            t = await _seized_trunk(ctx, deadline)
            await ctx.slots.set(ctx.call, "trunk", f"trunk/{t}")
            await ctx.slots.set_stage(ctx.call, Stage.DIALLING, deadline)
            await _dial_tone(ctx, t)
            await _tut(ctx, _dial_key(sc),                              # tutor
                       until=lambda b, t=t: b.dialled(t) or not b.on(f"trunk/{t}/seize"))
            return await _wait_for_right_number(ctx, t, sc.dial, deadline)
        try:
            trunk = await _unless_abandoned(ctx, caller, route())
        except TimeoutError:
            return Outcome(False, Reason.NOT_CONNECTED)
        except Misdialled:
            return Outcome(False, Reason.MISDIALLED)            # Rev 56

        called = f"trunk/{trunk}"
        await ctx.hw.tone(trunk, "ringback")
        await ctx.slots.set_stage(ctx.call, Stage.RINGING, None)
        # tutor: before the far end answers, so she does not talk over its
        # first line; ringback runs on until she has finished (§4.9).
        if _last_wait(sc) is None:
            await _tut(ctx, "center-dialled", until=_centred(caller, called))
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
        _note_stale(ctx)
        async def route() -> int:
            await _tut(ctx, "trunk-front", until=_fresh(ctx))            # tutor
            t = await _seized_trunk(ctx, deadline)
            await ctx.slots.set(ctx.call, "trunk", f"trunk/{t}")
            await ctx.slots.set_stage(ctx.call, Stage.DIALLING, deadline)
            await _dial_tone(ctx, t)
            await _tut(ctx, _dial_key(sc),                              # tutor
                       until=lambda b, t=t: b.dialled(t) or not b.on(f"trunk/{t}/seize"))
            return await _wait_for_right_number(ctx, t, sc.dial, deadline)
        try:
            trunk = await _unless_abandoned(ctx, caller, route())
        except TimeoutError:
            return Outcome(False, Reason.NOT_CONNECTED)
        except Misdialled:
            return Outcome(False, Reason.MISDIALLED)            # Rev 56

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
        await _closing(ctx, caller, gone)
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
        async def route() -> None:
            while True:
                await _wait_for_right_station(ctx, sc.to_station, deadline)
                await ctx.slots.set_stage(ctx.call, Stage.RINGING, deadline)
                await asyncio.sleep(ANSWER_AFTER)
                # tutor: she rang with the far switch, and the near one still
                # has her on the line, so before the room answers (§4.9).
                if _last_wait(sc) is None:
                    await _tut(ctx, "center-ringing", until=_centred(caller))
                if await _picks_up(ctx, caller, sc.to_station, deadline):
                    return
                await ctx.slots.set_stage(ctx.call, Stage.ROUTING, deadline)
        try:
            await _unless_abandoned(ctx, caller, route())
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
        if ctx.scene.conversation or sc.closing:
            # tutor: this caller wants her, not a connection (§4.9, Rev 59).
            await _tut(ctx, "for-you", abort_if=gone)
        try:
            for line in ctx.scene.conversation:
                await _operator_speaks(ctx, caller, line, gone)
                await _lead_in(ctx, caller, line, gone)
                await _play(ctx, caller, line, gone)
        except TimeoutError:
            return Outcome(False, Reason.TIMEOUT)
        await _closing(ctx, caller, gone)
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
