"""The five call flows (game_control.md §3.3, §4, §3.2).

One coroutine per scene shape. Each drives the hardware, moves the call
through the §3.2 stages, reports the §3.3 "connected" milestone to the
scheduler, and returns a §4 outcome.

Three rules run through all five:

**A wrong connection is not a failure.** The operator who rings the wrong jack
and corrects herself within the connect timeout has made the call (§3.5). So
every "wait for the right thing" loop logs the wrong thing and keeps waiting
until the deadline, rather than ending the call. A wrong room answers, if the
script gives its occupant a "hello" reaction, and hangs up (§3.5); it never
takes the call.

**Every flow cleans up in `finally`**, on a normal end, an error, and
cancellation — which is how Stop and losing a client arrive. Cleanup commands
are allowed to fail: the controller and the audio program release everything
themselves when they lose the game (mqtt.md §8.2).

**The monitor follows the answer** (§9.1). The moment the calling circuit's
`op` goes on while the call is in `signalling` is the answer, and the only
point in a call where the loudspeaker moves.

In tutor mode (§7) `ctx.tutor` is set, and the flows stop at each
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

from .board import Abandoned, Board
from .calls import Call, Reason, Slots, Stage
from .config import Config
from .dialling import dial_tone, read_number
from .link import Hw
from .script_data import SceneDef, Shape, Speech
from .scenes import quietly, hear, ringing_station, say
from .tutor import REPEAT, REPEATS, Tutor

# §3.5: a caller left with neither the operator nor a connection, and no trunk
# up, hangs up after ABANDON before the call is connected - long enough to be
# held while she answers another lamp; after ABANDON_MISDIALLED once she has
# dialled a wrong number for it.
ABANDON = 30.0
ABANDON_MISDIALLED = 5.0
# §3.5: back after HELD or more, the caller asks whether she is there first.
HELD = 10.0
# §3.5: a trunk taken and not dialled for DIAL_FIRST gets reorder, outside
# tutor mode; time to look a number up. Free calls wait less (freecall.py).
DIAL_FIRST = 30.0
# §3.5: what a party does when the operator leaves it hanging. A party waiting
# for her to speak says "Hello? Operator?" after NUDGE_AFTER of silence, then
# goes on after as long again. A party she rings that is not patched to its
# caller says "Hello?" after PATCH_WAIT, and hangs up after as long again.
NUDGE_AFTER = 6.0
PATCH_WAIT = 8.0
AWAY = 5.0                # s away from a caller before it asks again on her return
FLICK = 0.5               # s away that is only the switch passing centre
BACK_PAUSE = 0.5          # s after she comes back before the caller asks if she is there
# §3.3: a call in on a trunk not yet answered gets another short ring every RERING.
RERING = 10.0
# §6.2: speech that runs this long without a silence is taken as ended -
# her greeting before the request, and any other wait for her. Greetings run
# 1-2.6s; the detector has held "speech" for 5-12s on the loudspeaker's loop.
GREETING_MAX = 3.0
SPEECH_MAX = 4.0
# s between a party's last words and its hanging up (§3.4): the time it takes
# to put a receiver back on its hook.
HANG_UP = 1.5
ANSWER_AFTER = 3.0        # s of ring before a room answers, right or wrong
# §3.2: busy tone plays four bursts, then stops, before the game listens for
# her. On the cord the tone reaches the caller's line, and the speech detector
# takes it for her voice, so a listen under it never hears her stop.
BUSY_HOLD = 3.5

log = logging.getLogger("flow")


class GaveUp(TimeoutError):
    """The caller gave up waiting to be put through (§3.5): not connected."""


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
    mark_connected: Callable[[], Awaitable[None]]  # §3.3, for the scheduler
    set_monitor: Callable[[str], Awaitable[None]]  # §9.1
    tutor: Tutor | None = None                     # §7, in tutor mode
    jack_of: Callable[[int], int | None] = lambda n: None   # station -> its jack (§12.1)
    misdialled: bool = False                       # a wrong number this call (§3.5)
    reordered: bool = False                        # fast busy this call (§3.5)
    # A party's reactions, by kind and cast member, and who answers a room
    # nobody expects to be rung (§3.5).
    reaction: Callable[[str, str], Speech | None] = lambda kind, voice: None
    occupant: Callable[[int], str] = lambda n: ""
    # Trunks already up when this call began to route, and not released
    # since: not this call's, so never taken as the one she seized, unless
    # patched to `out_caller`, the caller of this call out.
    stale_trunks: set[int] = field(default_factory=set)
    out_caller: str | None = None
    # Free calls (§8): the circuits of free callers, whether one is waiting
    # to be put through, and the public line, which no scene takes.
    free_callers: Callable[[], set[str]] = lambda: set()
    free_routing: Callable[[], bool] = lambda: False
    public_trunk: int = 0
    # When the tutor's last wrong-cord line for this call ends (§7.7), from
    # which a caller left alone waits afresh.
    hint_end: Callable[[], float] = lambda: 0.0

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
    """Tutor mode: her line for this step, said to its end (§7)."""
    if (t := _tutoring(ctx)) is not None:
        await t.say(key, until=until, abort_if=abort_if)


async def _operator_speaks(ctx: Ctx, where: str, sp: Speech, abort_if,
                           request: bool = False) -> bool:
    """The game waits for the operator to speak before `sp` (§6.2).

    In tutor mode she is told what to say first, and told again if she does
    not, at most REPEATS times; then the line plays, as it would after a
    listen that timed out.

    Returns whether she spoke: False when every listen timed out and the
    line goes on without her (§3.3, a reply to a call to the operator).
    """
    cap = GREETING_MAX if request else SPEECH_MAX
    t = _tutoring(ctx)
    if t is None:
        voice = ctx.scene.caller_voice if sp.by == "caller" else ctx.scene.called_voice
        nudge = ctx.reaction("nudge", voice)
        if nudge is None:
            return await hear(ctx.b, ctx.hw, where, ctx.cfg.speak_timeout,
                              abort_if=abort_if, max_speech=cap) == "silence"
        # Not 30s of silence: "Hello? Operator?", then on with the line.
        if await hear(ctx.b, ctx.hw, where, NUDGE_AFTER, abort_if=abort_if, max_speech=cap) == "timeout":
            ctx.say_event(f"{where}: the operator did not speak")
            await say(ctx.b, ctx.hw, where, nudge.name, nudge.seconds, abort_if=abort_if)
            return await hear(ctx.b, ctx.hw, where, NUDGE_AFTER,
                              abort_if=abort_if, max_speech=cap) == "silence"
        return True
    key = t.say_key(sp, request)
    speaking = lambda: ctx.b.get(f"{where}/listen") == "speech"
    timeouts = 0
    try:
        while timeouts <= REPEATS:
            await t.say(key, abort_if=abort_if, listening=speaking)
            asked = t.asked
            if asked is None:                   # tutor switched off meanwhile
                return await hear(ctx.b, ctx.hw, where, ctx.cfg.speak_timeout,
                                  abort_if=abort_if, max_speech=cap) == "silence"
            listen = asyncio.create_task(
                hear(ctx.b, ctx.hw, where, REPEAT, abort_if=abort_if, max_speech=cap))
            press = asyncio.create_task(asked.wait())
            pressed = False
            try:
                await asyncio.wait({listen, press}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                press.cancel()
                if not listen.done():
                    # Repeat Help (§7.4): stop listening, say it again, and
                    # listen afresh. hear() cancels the listen as it unwinds.
                    pressed = True
                    listen.cancel()
                await asyncio.gather(press, listen, return_exceptions=True)
            if pressed:
                if not t.active:
                    return await hear(ctx.b, ctx.hw, where, ctx.cfg.speak_timeout,
                                      abort_if=abort_if, max_speech=cap) == "silence"
                continue                        # a press: not one of her repeats
            if listen.result() == "silence":
                return True
            timeouts += 1
        return False
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

    Raises TimeoutError, which the caller turns into `no answer` (§4).
    """
    deadline = time.time() + ctx.cfg.answer_timeout
    await ctx.slots.set_stage(ctx.call, Stage.SIGNALLING, deadline)
    op = lambda b: b.on(f"{caller}/op")
    if caller.startswith("trunk/"):
        # Only a front cord seizes a trunk: the operator heard through a
        # rear cord has not answered (§9.1).
        op = lambda b: b.on(f"{caller}/op") and b.on(f"{caller}/seize")
    # tutor: from a room the game cannot see the cord go in, so both steps
    # are one line; a trunk is seized by the cord, so they are two (§7).
    if _tutoring(ctx) is not None:
        if caller.startswith("station/"):
            await _tut(ctx, "answer-station", until=op)
        else:
            seized = lambda b: b.on(f"{caller}/seize")
            await _tut(ctx, "answer-trunk", until=seized)
            await ctx.b.wait_until(seized, ctx.left(deadline))
            await _tut(ctx, "talk", until=op)
    await ctx.b.wait_until(op, ctx.left(deadline))
    # §9.1: the answer is the one point the loudspeaker moves.
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
    """A line's pause: and ringback: (§6.2), after any wait.

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
            await quietly(ctx.hw.tone(n, "off"))


async def _wait_for_right_station(ctx: Ctx, want: int, deadline: float) -> None:
    """Wait until the operator rings the wanted station (§5).

    A wrong station is logged and ignored: it rings out, the game does not
    answer it, and the operator has until the connect timeout to correct
    herself. Raises TimeoutError if she never does.
    """
    # tutor: which jack, and which switch rings it (§7).
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
            # A free caller waits to be put through, so the room is likely
            # theirs (§8): not a wrong party for this call.
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
    """She has rung station n, not the one asked for (§3.5). Whoever is
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
        await quietly(ctx.hw.hook(n, False))   # hangs up: the cord lamp lights


async def _picks_up(ctx: Ctx, caller: str, n: int, deadline: float) -> bool:
    """The called room answers; True once it is patched to the caller. Not
    patched within PATCH_WAIT, it says "Hello?"; not within as long again, it
    hangs up, and False: she must ring it again (§3.5)."""
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


def _fresh(ctx: Ctx):
    """A trunk up that is this call's to take: not one already up when it
    began to route. A stale trunk released and taken again is fresh, and so
    is one patched to this call's caller, taken while the request was still
    being said (§3.5)."""
    def seized(b: Board) -> int | None:
        free = ctx.free_callers()
        for n in ctx.cfg.fitted_trunks():
            if not b.on(f"trunk/{n}/seize"):
                ctx.stale_trunks.discard(n)
            elif n == ctx.public_trunk or b.get(f"trunk/{n}/peer") in free:
                continue                # the public line, or a free call's
            elif n not in ctx.stale_trunks or (
                    ctx.out_caller and b.get(f"trunk/{n}/peer") == ctx.out_caller):
                return n
        return None
    return seized


def _note_stale(ctx: Ctx) -> None:
    """The trunks up as routing begins belong to other calls, or are cords
    left in from an earlier one."""
    ctx.stale_trunks = {n for n in ctx.cfg.fitted_trunks() if ctx.b.on(f"trunk/{n}/seize")}


async def _seized_trunk(ctx: Ctx, deadline: float) -> int:
    """Which trunk the operator has taken for this call."""
    return await ctx.b.wait_until(_fresh(ctx), ctx.left(deadline))


async def _unless_abandoned(ctx: Ctx, caller: str, work: Awaitable):
    """Run `work`, the routing of a call; raise Abandoned if the caller is lost
    for ABANDON seconds first (§3.5).

    Lost: the operator is not on the caller's line, it is patched to nothing,
    and no trunk is up - for a trunk caller, its own; for a station, any, since
    she may be dialling out for it. The game cannot see a cord go into or out
    of a station jack, so a pulled answering cord and a switch centred before
    the front cord goes in look the same; the wait is what tells them apart.
    Not in tutor pacing.

    When she comes back on the caller's line, the answering cord alone, after
    AWAY or more, the caller says the request again once she has spoken, or
    after NUDGE_AFTER if she does not (§3.5): a guest kept waiting does not
    sit silent. Back after HELD or more, it first asks whether she is there.

    After a wrong number (§3.5), her first return, however short, gets the
    request again, and her second the caller giving up: GaveUp, which the
    flow takes as `not connected`. Not in tutor pacing.
    """
    def lost(b: Board) -> bool:
        if b.on(f"{caller}/op") or b.get(f"{caller}/peer"):
            return False
        if caller.startswith("trunk/"):
            return not b.on(f"{caller}/seize")
        return _fresh(ctx)(b) is None

    def on_line(b: Board) -> bool:
        return b.on(f"{caller}/op") or "/" in (b.get(f"{caller}/peer") or "")

    async def returns() -> str:
        """She leaves the caller and comes back on with the answering cord
        alone, not patched on: the caller asks again, or after a wrong
        number gives up. Returns "gave up" when it has."""
        misdial_returns = 0
        while True:
            await ctx.b.wait_until(lambda b: not on_line(b), None)
            left = time.time()
            await ctx.b.wait_until(on_line, None)
            gone_for = time.time() - left
            if "/" in (ctx.b.get(f"{caller}/peer") or ""):
                continue
            after_wrong = ctx.misdialled and _tutoring(ctx) is None
            if after_wrong:
                if gone_for < FLICK:
                    continue
                misdial_returns += 1
            elif gone_for < AWAY:
                continue
            away = lambda b: not on_line(b)
            try:
                if gone_for >= HELD:
                    nudge = ctx.reaction("nudge", ctx.scene.caller_voice)
                    if nudge is not None:
                        await asyncio.sleep(BACK_PAUSE)
                        ctx.say_event(f"{caller}: asks if the operator is there")
                        await say(ctx.b, ctx.hw, caller, nudge.name, nudge.seconds,
                                  abort_if=away)
                await hear(ctx.b, ctx.hw, caller, NUDGE_AFTER, abort_if=away,
                           max_speech=GREETING_MAX)
                if ctx.b.get(f"{caller}/play"):          # a wrong-cord line, say
                    continue
                if after_wrong and misdial_returns >= 2:
                    giveup = ctx.reaction("giveup", ctx.scene.caller_voice)
                    ctx.say_event(f"{caller}: gives up")
                    if giveup is not None:
                        await say(ctx.b, ctx.hw, caller, giveup.name, giveup.seconds,
                                  abort_if=away)
                    await asyncio.sleep(HANG_UP)
                    return "gave up"
                ctx.say_event(f"{caller}: asks again")
                try:
                    await say(ctx.b, ctx.hw, caller, ctx.scene.request.name,
                              ctx.scene.request.seconds, abort_if=away)
                except asyncio.CancelledError:          # routed meanwhile
                    await asyncio.shield(quietly(ctx.hw.stop(caller)))
                    raise
            except Abandoned:
                pass                                    # she left again

    async def watch() -> None:
        while True:
            await ctx.b.wait_until(lost, None)
            wait = ABANDON_MISDIALLED if ctx.misdialled else ABANDON
            until = time.time() + wait
            while True:
                try:
                    await ctx.b.wait_until(lambda b: not lost(b), max(0.0, until - time.time()))
                    break
                except TimeoutError:
                    # In tutor pacing nobody hangs up; checked here, at each
                    # expiry, so a change of pacing mid-call is followed.
                    if _tutoring(ctx) is not None:
                        until = time.time() + wait
                        continue
                    # A wrong-cord line restarts the wait from its end.
                    until = ctx.hint_end() + wait
                    if until <= time.time():
                        return

    def asker_failed(t: asyncio.Task) -> None:
        if not t.cancelled() and (e := t.exception()) is not None:
            log.warning("%s: asking again failed", ctx.scene.id, exc_info=e)

    task = asyncio.ensure_future(work)
    watcher = asyncio.ensure_future(watch())
    asker = asyncio.ensure_future(returns())
    asker.add_done_callback(asker_failed)
    try:
        done, _ = await asyncio.wait({task, watcher, asker}, return_when=asyncio.FIRST_COMPLETED)
        if done == {asker} and (asker.cancelled() or asker.exception() is not None
                                or asker.result() != "gave up"):
            # It failed (logged): routing goes on without it.
            done, _ = await asyncio.wait({task, watcher}, return_when=asyncio.FIRST_COMPLETED)
    except BaseException:
        for t in (task, watcher, asker):
            t.cancel()
        await asyncio.gather(task, watcher, asker, return_exceptions=True)
        raise
    if asker in done and task not in done and not asker.cancelled() \
            and asker.exception() is None and asker.result() == "gave up":
        for t in (task, watcher):
            t.cancel()
        await asyncio.gather(task, watcher, return_exceptions=True)
        raise GaveUp("the caller gave up after a wrong number")
    asker.cancel()
    await asyncio.gather(asker, return_exceptions=True)
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
    """Her closing words, waited for before the caller hangs up (§6.3).

    A scene's closing: is what she says after its last line - "That call was
    from the lobby, sir." In tutor mode she is prompted to say it. A closing
    not said within the speak timeout is let go: the caller hangs up and the
    call has still succeeded, since she has done everything it asked.
    """
    sc = ctx.scene
    if not sc.closing:
        await asyncio.sleep(HANG_UP)
        return
    sp = Speech(name=sc.closing, seconds=0.0, by="caller", operator=sc.closing)
    try:
        await _operator_speaks(ctx, caller, sp, abort_if)
        await asyncio.sleep(HANG_UP)
    except TimeoutError:
        log.info("%s: closing not heard", sc.id)
    except Abandoned:
        log.info("%s: cord pulled before the closing", sc.id)   # the call is over


def _dial_key(sc: SceneDef) -> str:
    """The tutor's line telling her what to dial (§7)."""
    return "dial-operator" if sc.dial == "0" else f"dial-{sc.to_line}"


async def _wait_for_right_number(ctx: Ctx, trunk: int, want: str,
                                 deadline: float) -> int:
    """Wait until the wanted number is dialled (§3.5).

    A wrong number is logged, and the flow keeps waiting. A redial arrives as
    a release and a fresh seizure, which clears `dialled` (board.py), so this
    also follows the operator onto another trunk if she takes one. Dial tone,
    which the caller has started, stops at the first digit and comes back on
    each fresh seizure (§3.5); a wrong number gets busy tone until she hangs
    up.
    """
    digits = "".join(c for c in want if c.isdigit())
    wrong_seen: set[str] = set()
    released = lambda b, t: not b.on(f"trunk/{t}/seize") and "released"
    while True:
        # A trunk not dialled gets reorder, as an exchange gave up on a
        # register left waiting - but not while the tutor teaches (§7).
        first = ctx.left(deadline) if _tutoring(ctx) else min(DIAL_FIRST, ctx.left(deadline))
        try:
            got = await ctx.b.wait_until(
                lambda b, t=trunk: b.dialled(t) or released(b, t), first)
        except TimeoutError:
            if first >= ctx.left(deadline):
                raise
            got = "none"
        if got == "none":
            got = await _reorder(ctx, trunk, "none", want, deadline)
        if got != "released":
            await ctx.hw.tone(trunk, "off")
            got = await read_number(ctx.b, trunk, lambda d: len(d) == len(digits), len(digits),
                                    left=lambda: ctx.left(deadline))
        if got in ("short", "long"):
            got = await _reorder(ctx, trunk, got, want, deadline)
        if got == "released":
            # She hung up the trunk: wait for the next seizure and start over.
            await ctx.hw.tone(trunk, "off")
            trunk = await _seized_trunk(ctx, deadline)
            await ctx.slots.set(ctx.call, "trunk", f"trunk/{trunk}")
            await dial_tone(ctx.b, ctx.hw, trunk)
            continue
        if got == digits:
            await ctx.slots.set(ctx.call, "digits", got)
            ctx.say_event(f"dialled {want} on trunk/{trunk}")
            return trunk
        if got not in wrong_seen:
            wrong_seen.add(got)
            ctx.say_event(f"dialled {got}, wanted {want}")
            log.info("%s: wrong number %s", ctx.scene.id, got)
        await ctx.hw.tone(trunk, "busy")                # not silence
        ctx.misdialled = True                           # less patience (§3.5)
        # Wait for her to release and try again.
        await ctx.b.wait_until(lambda b, t=trunk: not b.on(f"trunk/{t}/seize"),
                               ctx.left(deadline))


async def _reorder(ctx: Ctx, trunk: int, why: str, want: str, deadline: float) -> str:
    """Fast busy until she releases the trunk (§3.5); then "released", and
    she may take a trunk and dial again."""
    got = ctx.b.dialled(trunk)
    what = {"long": "too many digits", "short": "too few digits", "none": "nothing dialled"}[why]
    ctx.say_event(f"dialled {got or 'nothing'}, wanted {want}: {what}")
    log.info("%s: misdialled %s (%s)", ctx.scene.id, got, why)
    ctx.reordered = True
    try:
        await ctx.hw.tone(trunk, "reorder")
        await ctx.b.wait_until(lambda b, t=trunk: not b.on(f"trunk/{t}/seize"),
                               ctx.left(deadline))
    finally:
        await quietly(ctx.hw.tone(trunk, "off"))
    return "released"


def _cord_broken(a: str, c: str):
    """abort_if: the cord between the two lines has gone (§4, `cut off`)."""
    def broken(b: Board):
        return b.get(f"{a}/peer") != c and f"cord pulled between {a} and {c}"
    return broken


async def _converse(ctx: Ctx, caller: str, called: str) -> None:
    """Stage `talking`: play the scripted conversation, turn by turn.

    A line marked wait: plays only after the operator has spoken on its side
    and stopped (§6.2) — "Long distance, please" to the local operator before
    the long-distance operator comes on. Raises TimeoutError if she never
    does, which the flow turns into `timeout` (§4).

    In tutor mode, after the last wait: line she is told to put the switch
    back, since the call needs nothing more from her (§7).
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
    await asyncio.sleep(HANG_UP)                # then the receivers go down


def _centred(*circuits: str):
    """until: her talk switch is back in the centre - she is on none of the
    pair's lines - so the prompt to centre it can stop (§7)."""
    return lambda b: not any(b.on(f"{c}/op") for c in circuits)


def _engaged(n: int):
    """Station n off-hook in another call: calling, or answered (§6.6)."""
    return lambda b: b.on(f"station/{n}/hook")


async def _route_unless_engaged(ctx: Ctx, want: int, deadline: float) -> bool:
    """Wait for the operator to ring `want`, as _wait_for_right_station does,
    unless the scene has if_busy: and the station is found engaged first.
    True if it is engaged (§6.6). Raises TimeoutError if neither happens."""
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
    the if_busy: lines, each after she has spoken (§6.6)."""
    ctx.say_event(f"{ctx.scene.to_line} is engaged")
    await ctx.slots.set_stage(ctx.call, Stage.BUSY, time.time() + ctx.cfg.speak_timeout)
    await ctx.mark_connected()                             # §3.3
    try:
        if await _replies(ctx, caller, ctx.scene.if_busy, gone):
            await asyncio.sleep(HANG_UP)
    except TimeoutError:
        return Outcome(False, Reason.TIMEOUT)
    return Outcome(True)


def _gone(caller: str):
    """abort_if: she has pulled the answering cord, and the caller is on nothing."""
    return lambda b: (not b.on(f"{caller}/op") and not b.get(f"{caller}/peer")
                      and "operator pulled the answering cord")


async def _open_call(ctx: Ctx, caller: str, trunk: int | None = None) -> Outcome | None:
    """The caller signals, she answers, and the request plays (§3.1): from a
    room, off-hook; from outside, a ring on `trunk`. None once the request has
    played, else the failure."""
    rering = None
    if trunk is None:
        await ctx.hw.hook(ctx.scene.from_station, True)        # the lamp lights
    else:
        await ctx.slots.set(ctx.call, "trunk", caller)
        await ctx.hw.short_ring(trunk)                          # §3.3
        rering = asyncio.create_task(_rings_again(ctx, caller, trunk))
    try:
        await _answer(ctx, caller)
    except TimeoutError:
        return Outcome(False, Reason.NO_ANSWER)
    finally:
        if rering is not None:
            rering.cancel()
            await asyncio.gather(rering, return_exceptions=True)
        if trunk is not None:
            await quietly(ctx.hw.ring_trunk(trunk, False))
    while True:
        try:
            await _request(ctx, caller, _gone(caller))
            return None
        except TimeoutError:
            return Outcome(False, Reason.TIMEOUT)
        except Abandoned:
            # §3.3: she left before the request was heard; a room waits for
            # her to come back, asks if she is there, and asks again.
            if not await _waits_for_her(ctx, caller, trunk, "the request"):
                raise


async def _rings_again(ctx: Ctx, caller: str, trunk: int) -> None:
    """§3.3: a short ring every RERING until the trunk is answered, so a
    call in is heard again and not only seen by its lamp. Not while a front
    cord is in it: she has it, and has only to throw the key."""
    while True:
        await asyncio.sleep(RERING)
        if not ctx.b.on(f"{caller}/seize"):
            await quietly(ctx.hw.short_ring(trunk))


async def _replies(ctx: Ctx, caller: str, lines, gone) -> bool:
    """The caller's lines, each played after she has spoken.

    A caller told the line is busy or engaged (§3.3, §6.6): once she has
    begun to speak to it - the detector has heard her start - the call is
    handled, and her leaving after that ends it as a success; the replies
    are a bonus for staying. Returns False if she left after speaking, True
    if every line played. Abandoned if she left before.
    """
    told = False
    for line in lines:
        waiting = True
        try:
            if await _operator_speaks(ctx, caller, line, gone):
                told = True
            waiting = False
            await _lead_in(ctx, caller, line, gone)
            await _play(ctx, caller, line, gone)
        except Abandoned:
            if waiting and ctx.b.saw(f"{caller}/listen", "speech"):
                told = True
            if not told:
                raise
            ctx.say_event(f"{caller}: the operator left after telling them")
            return False
    return True


async def _route_out(ctx: Ctx, caller: str) -> int:
    """Stages `routing` and `dialling`: she takes a trunk and dials the
    scene's number. The trunk, once she has; TimeoutError if she never does."""
    sc = ctx.scene
    deadline = time.time() + ctx.cfg.connect_timeout
    await ctx.slots.set_stage(ctx.call, Stage.ROUTING, deadline)
    ctx.out_caller = caller
    _note_stale(ctx)

    async def route() -> int:
        await _tut(ctx, "trunk-front", until=_fresh(ctx))            # tutor
        t = await _seized_trunk(ctx, deadline)
        await ctx.slots.set(ctx.call, "trunk", f"trunk/{t}")
        await ctx.slots.set_stage(ctx.call, Stage.DIALLING, deadline)
        await dial_tone(ctx.b, ctx.hw, t)
        await _tut(ctx, _dial_key(sc),                              # tutor
                   until=lambda b, t=t: b.dialled(t) or not b.on(f"trunk/{t}/seize"))
        return await _wait_for_right_number(ctx, t, sc.dial, deadline)
    return await _unless_abandoned(ctx, caller, route())


def _not_routed(ctx: Ctx) -> Outcome:
    """A call out not connected in time: misdialled if it met reorder (§4)."""
    return Outcome(False, Reason.MISDIALLED if ctx.reordered else Reason.NOT_CONNECTED)


# ----------------------------------------------------------------- flows ----


async def station_to_station(ctx: Ctx) -> Outcome:
    sc = ctx.scene
    caller, called = f"station/{sc.from_station}", f"station/{sc.to_station}"
    answered = False                # the called station is off-hook for this call
    try:
        if (failed := await _open_call(ctx, caller)) is not None:
            return failed
        gone = _gone(caller)

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
                await quietly(ctx.hw.hook(n, False))
        await quietly(ctx.hw.stop(caller))
        if answered or not sc.if_busy:
            await quietly(ctx.hw.stop(called))


async def station_to_outside(ctx: Ctx) -> Outcome:
    sc = ctx.scene
    caller = f"station/{sc.from_station}"
    trunk: int | None = None
    try:
        if (failed := await _open_call(ctx, caller)) is not None:
            return failed
        try:
            trunk = await _route_out(ctx, caller)
        except TimeoutError:
            return _not_routed(ctx)

        called = f"trunk/{trunk}"
        await ctx.hw.tone(trunk, "ringback")
        await ctx.slots.set_stage(ctx.call, Stage.RINGING, None)
        # tutor: before the far end answers, so she does not talk over its
        # first line; ringback runs on until she has finished (§7).
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
            await quietly(ctx.hw.hook(sc.from_station, False))
        if trunk is not None:
            await quietly(ctx.hw.tone(trunk, "off"))
            await quietly(ctx.hw.stop(f"trunk/{trunk}"))
        await quietly(ctx.hw.stop(caller))


async def busy_scene(ctx: Ctx) -> Outcome:
    """An outgoing call that meets busy tone (§3.3: connected at busy tone)."""
    sc = ctx.scene
    caller = f"station/{sc.from_station}"
    trunk: int | None = None
    try:
        if (failed := await _open_call(ctx, caller)) is not None:
            return failed
        gone = _gone(caller)
        try:
            trunk = await _route_out(ctx, caller)
        except TimeoutError:
            return _not_routed(ctx)

        await ctx.hw.tone(trunk, "busy")
        await ctx.slots.set_stage(ctx.call, Stage.BUSY,
                                  time.time() + ctx.cfg.speak_timeout)
        await ctx.mark_connected()                         # §3.3: busy tone starts

        # She goes back to the caller and says the line is engaged. The scene's
        # conversation is the caller's replies, each after she has spoken.
        try:
            await _hold(ctx, BUSY_HOLD, gone)
            await ctx.hw.tone(trunk, "off")
            await _tut(ctx, "busy-heard", abort_if=gone)                # tutor
            if not await _replies(ctx, caller, sc.conversation, gone):
                return Outcome(True)                   # told, and left (§3.3)
        except TimeoutError:
            return Outcome(False, Reason.TIMEOUT)
        await _closing(ctx, caller, gone)
        return Outcome(True)
    except Abandoned:
        return Outcome(False, Reason.CUT_OFF)
    finally:
        if sc.from_station is not None:
            await quietly(ctx.hw.hook(sc.from_station, False))
        if trunk is not None:
            await quietly(ctx.hw.tone(trunk, "off"))
        await quietly(ctx.hw.stop(caller))


async def outside_to_station(ctx: Ctx, trunk: int) -> Outcome:
    """A call in from outside: the game rings a free trunk (§3.6)."""
    sc = ctx.scene
    caller, called = f"trunk/{trunk}", f"station/{sc.to_station}"
    try:
        if (failed := await _open_call(ctx, caller, trunk)) is not None:
            return failed

        deadline = time.time() + ctx.cfg.connect_timeout
        await ctx.slots.set_stage(ctx.call, Stage.ROUTING, deadline)
        async def route() -> None:
            while True:
                await _wait_for_right_station(ctx, sc.to_station, deadline)
                await ctx.slots.set_stage(ctx.call, Stage.RINGING, deadline)
                await asyncio.sleep(ANSWER_AFTER)
                # tutor: she rang with the far switch, and the near one still
                # has her on the line, so before the room answers (§7).
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
        await quietly(ctx.hw.ring_trunk(trunk, False))
        if sc.to_station is not None:
            await quietly(ctx.hw.hook(sc.to_station, False))
        for c in (caller, called):
            await quietly(ctx.hw.stop(c))


async def to_operator(ctx: Ctx, trunk: int | None = None) -> Outcome:
    """No called party: the caller asks the operator something (§3.3).

    Connected when the request has finished playing. The conversation is the
    caller's lines alone, each played after the operator has spoken and
    stopped — script.yml's "Order" note, and why every line waits on a listen.

    From a room the station goes off-hook; from an outside line the game
    rings `trunk`, as for a call in to a room. With no conversation the
    caller hangs up once the request has played — the long-distance operator's
    time and charges, said once and not waited on.
    """
    sc = ctx.scene
    caller = _caller_circuit(sc, trunk)
    try:
        if (failed := await _open_call(ctx, caller, trunk)) is not None:
            return failed
        gone = _gone(caller)
        await ctx.mark_connected()                         # §3.3: the request has played

        await ctx.slots.set_stage(ctx.call, Stage.OPERATOR,
                                  time.time() + ctx.cfg.speak_timeout)
        lines = sc.conversation
        i = 0                   # the next line, kept across her leaving
        replied = False         # §3.3: she has answered the request
        told = False
        while True:
            waiting = False     # a listen for her reply is running
            try:
                if (lines or sc.closing) and not told:
                    # tutor: this caller wants her, not a connection (§7).
                    await _tut(ctx, "for-you", abort_if=gone)
                    told = True
                while i < len(lines):
                    line = lines[i]
                    waiting = True
                    if await _operator_speaks(ctx, caller, line, gone):
                        replied = True
                    waiting = False
                    await _lead_in(ctx, caller, line, gone)
                    await _play(ctx, caller, line, gone)
                    i += 1
                await _closing(ctx, caller, gone)
                return Outcome(True)
            except TimeoutError:
                return Outcome(False, Reason.TIMEOUT)
            except Abandoned:
                # She started to reply and pulled the cord before the
                # detector heard her stop: a curt answer is still an answer.
                if waiting and ctx.b.saw(f"{caller}/listen", "speech"):
                    replied = True
                if replied:
                    # §3.3: she has answered it; the rest was a bonus.
                    ctx.say_event(f"{caller}: the operator left after replying")
                    return Outcome(True)
                if not await _waits_for_her(ctx, caller, trunk):
                    raise
    except Abandoned:
        return Outcome(False, Reason.CUT_OFF)
    finally:
        if sc.from_station is not None:
            await quietly(ctx.hw.hook(sc.from_station, False))
        if trunk is not None:
            await quietly(ctx.hw.ring_trunk(trunk, False))
        await quietly(ctx.hw.stop(caller))


async def _waits_for_her(ctx: Ctx, caller: str, trunk: int | None,
                         before: str = "a reply") -> bool:
    """§3.3: she has left a caller before its request was heard, or a
    caller to the operator before answering it (`before` says which).

    From a room the station is still off-hook, so its lamp lights again; the
    caller waits ABANDON for her to come back on its line - in tutor pacing,
    for as long as it takes - and then asks whether she is there, the
    `nudge` reaction, and the call goes on where it was. Returns False if she
    does not come back, or for a caller on a trunk, which has nothing to
    light: the call is then cut off.
    """
    if trunk is not None:
        return False
    ctx.say_event(f"{caller}: left before {before}; waits for the operator")
    back = lambda b: b.on(f"{caller}/op")
    while True:
        until = time.time() + ABANDON
        while not back(ctx.b):
            left = until - time.time()
            if left <= 0:
                if _tutoring(ctx) is not None:          # nobody hangs up (§7)
                    until = time.time() + ABANDON
                    continue
                return False
            try:
                await ctx.b.wait_until(back, min(left, 1.0))
            except TimeoutError:
                pass
        nudge = ctx.reaction("nudge", ctx.scene.caller_voice)
        try:
            await asyncio.sleep(BACK_PAUSE)
            if nudge is not None:
                await say(ctx.b, ctx.hw, caller, nudge.name, nudge.seconds,
                          abort_if=_gone(caller))
            ctx.say_event(f"{caller}: asks if the operator is there")
            return True
        except Abandoned:
            continue                                    # she left again

FLOWS = {
    Shape.STATION_TO_STATION: station_to_station,
    Shape.STATION_TO_OUTSIDE: station_to_outside,
    Shape.BUSY: busy_scene,
    Shape.TO_OPERATOR: to_operator,
    # outside_to_station, and to_operator from an outside line, take the trunk
    # they ring in on, so the game picks it.
}
