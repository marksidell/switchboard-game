"""The game (game_control.md §2 to §13.2).

One object owns everything with a lifetime: the deck, the pacing, the eight
slots, the tallies, the running scene tasks and the `after:` timers. The MQTT
link calls into it twice — `on_birth` when a connection comes up, and
`on_command` for each page command — and it calls back out through `Link.state`
to publish.

Three shapes of task run under it:

  `_scheduler`   one, for the life of the program: starts a call when the
                 automatic gap has elapsed (§5.2).
  a flow task    one per call in progress, cancelled by Stop.
  an after timer one per waiting `after:` scene, cancelled by Stop (§6.1):
                 from the end of the scene it follows, or for `mode:
                 concurrent` from its start, which is how a scenario puts
                 its calls on the board almost together (§6.5).
  a tutor task   in tutor mode (§7), the introduction after Start, or the
                 end of a call: her line, then Next Call (Rev 70).
                 While it runs no call is dealt.

The command handler is deliberately quick (handover rule 9): it runs inside the
link's dispatch loop, and no hardware message is processed until it returns. It
validates, publishes the echo, starts or cancels tasks, and returns.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import random
import re
import time
from dataclasses import dataclass

from .board import Abandoned, Board, Change, LIVE_AUDIO, LIVE_CONTROL, Offline
from .calls import Call, N_SLOTS, Reason, Slots, Stage, Tallies
from .config import Config
from .deck import Deck, Holding
from .diag import TESTS, Diagnostics, kind_of
from .flows import Ctx, FLOWS, Outcome, outside_to_station, to_operator
from .freecall import FreeCalls
from .gamelog import GameLog
from .pacing import PACES
from .link import Hw, Link
from .scenes import say
from .script_data import GameScript, SceneDef, Shape
from .session import SessionLog
from . import sweep
from .tutor import INTRO, NO_LIMIT, Tutor

# What the player does at the board (Rev 57): a cord in or out (peer, op, a
# trunk's seize), a digit dialled, a station rung. Not `hook`, which the game
# itself drives, nor anything of the game's own.
_TRUNK_FAULT = re.compile(r"^trunk/(\d+)/fault$")     # §7.7, Rev 88
_STATION_RINGING = re.compile(r"^station/(\d+)/ringing$")   # heard by sbaudio, Rev 89
_TRUNK_OP_SEIZE = re.compile(r"^trunk/(\d+)/(?:op|seize)$")   # a rear cord in it, Rev 93
# s of op on and seize off together before it counts, beyond the board's hold
# on op going off, which outlasts a pulled front cord's seizure (§7.7, Rev 93)
REAR_HOLD = 1.0
# §3.4: after a call on a trunk ends, the far end has hung up. With her cord
# still in the trunk, the trunk gets reorder this long after, until she
# takes it down.
REORDER_AFTER = 4.0
PLAYER = re.compile(r"^(?:station|trunk)/\d+/(?:peer|op|seize|dialled|digit)$|^station/\d+/ring$")

log = logging.getLogger("game")



def pick_lessons(groups, seed: int) -> list[str]:
    """One scene from each group, in order, from the game's seed (§7, Rev 30)."""
    rng = random.Random(f"lessons {seed}")
    return [rng.choice(g) for g in groups]


class Game:
    def __init__(self, board: Board, gs: GameScript, cfg: Config,
                 session: SessionLog) -> None:
        self.b = board
        self.gs = gs
        self.cfg = cfg
        self.session = session

        self.link: Link | None = None
        self.hw: Hw | None = None
        self.slots: Slots | None = None
        self.log: GameLog | None = None

        self.running = False
        self.tallies = Tallies()
        self.deck: Deck | None = None
        self.next_number = 1
        # Set from the configuration at start-up and owned by the page after
        # that; a restart returns to the configured values (§5.4).
        from .pacing import Pacing
        self.pacing = Pacing(pace=cfg.pace, gap=cfg.gap, ramp=cfg.ramp, floor=cfg.floor,
                             jitter=cfg.jitter, pause=cfg.pause)
        if self.pacing.pace == "tutor" and gs.tutor_missing:
            log.warning("pace tutor configured, but %d of her lines have no wav: manual",
                        len(gs.tutor_missing))
            self.pacing.pace = "manual"

        self._flows: dict[int, asyncio.Task] = {}       # slot -> task
        self._hinted: set[tuple[int, str]] = set()      # (call, line) told, §7.7
        self._hint_end: dict[int, float] = {}            # call -> its line's end, Rev 91
        self._rear_since: dict[int, float] = {}          # trunk -> op on, seize off since, Rev 93
        self._afters: dict[str, asyncio.Task] = {}      # scene id -> timer task
        self._tails: dict[int, asyncio.Task] = {}       # trunk -> reorder after its call (§3.4)
        self._pending_after: dict[str, Holding] = {}    # what a waiting after holds
        self._after_due: dict[str, float] = {}          # a waiting after past its delay: when it fell due
        self._scheduler: asyncio.Task | None = None
        self._decks_recorded = 0        # how many of deck.orders are in SQLite
        self.diag: Diagnostics | None = None
        self.free = FreeCalls(self)           # §8, Rev 74
        self.queued = ""                # the chosen next scene (§6.4)
        self._scenarios_dealt: set[str] = set()   # once a game each (§6.5)
        self._delays = random.Random()  # drawn `delay` ranges, from the seed (§6.1)
        # Tutor mode (§7), the pacing `tutor` since Rev 32: `tutor` is her,
        # while a game runs in it.
        self.tutor: Tutor | None = None
        self._tutor_task: asyncio.Task | None = None
        self._intro = False             # the tutor task is the introduction
        self._unseen = False            # or the end of a call (Rev 67, Rev 70)
        self._more: asyncio.Event | None = None   # More Help, during it (Rev 31)
        self._waiting_for = ""          # game/tutor/waiting (Rev 33)
        self._lessons: list[str] = []   # the scenes a tutored game starts with
        self._to_tutor: asyncio.Task | None = None    # back to tutor when stopped (Rev 44)
        self._active_at = time.time()                 # the player's last act (Rev 57)
        self._sweep: asyncio.Task | None = None       # a board sweep (§11.5, Rev 50)
        self._sweep_kind = ""
        # Station numbers to the script's line names, for holding a station
        # under test out of dealing (§11.4).
        self._station_lines: dict[int, frozenset[str]] = {}
        for line, st in gs.script.stations.items():
            n = (st or {}).get("number")
            if n is not None:
                self._station_lines[n] = self._station_lines.get(n, frozenset()) | {line}

    # ---- wiring ----------------------------------------------------------

    def attach(self, link: Link) -> None:
        self.link = link
        self.hw = Hw(link)
        self.slots = Slots(link.state)
        self.log = GameLog(link.state)
        speech: dict[str, float] = {}
        for sc in self.gs.scenes.values():
            for sp in (sc.request, *sc.conversation):
                speech[sp.name] = sp.seconds
        self.diag = Diagnostics(self.b, self.hw, link.state, link.publish,
                                sorted(speech.items()), self.cfg.stations, self.cfg.trunks)

    async def on_birth(self, link: Link) -> None:
        """Publish the game's state before `online` (mqtt.md §8.4, §4.1).

        On a first connect that is a stopped game. On a reconnect it is the
        state as it stands, which after a broker loss is also a stopped game,
        because losing the broker stops it (§2).
        """
        self.attach(link)
        assert self.slots is not None and self.log is not None
        await link.state("game/run", "on" if self.running else "off")
        await self._publish_pacing()
        await self._publish_tallies()
        await self.slots.clear_all()
        await link.state("game/next_at", "")
        await link.state("game/error", "")
        await self.log.clear("game program started" if not self.running else "reconnected")
        self._arm_idle()
        for j in self.gs.jacks:
            await link.state(f"board/{j.kind}/{j.number}/label", j.label)
            await link.state(f"board/{j.kind}/{j.number}/circuit", j.circuit)
        # §6.4, §12.2, §11.4 (Rev 25).
        await link.state("game/scenes", "\n".join(self.gs.choosable()))
        await link.state("game/queue", self.queued)
        await link.state("game/tutor/intro", "")
        self._waiting_for = ""
        await link.state("game/tutor/waiting", "")
        await link.state("game/tutor/repeat", "")
        await link.state("game/tutor/more", "")
        await link.state("game/stations", str(self.cfg.stations))
        await link.state("game/trunks", str(self.cfg.trunks))
        await link.state("game/public_trunk", str(self.cfg.public_trunk))
        assert self.diag is not None
        await self.diag.end_all()
        await self.diag.publish_all_off()
        await self._end_sweep()
        await link.state("game/sweep", "")

    async def _publish_pacing(self) -> None:
        assert self.link is not None
        p = self.pacing
        await self.link.state("game/pace", p.pace)
        await self.link.state("game/gap", f"{p.gap:g}")
        await self.link.state("game/ramp", f"{p.ramp:g}")
        await self.link.state("game/floor", f"{p.floor:g}")
        await self.link.state("game/jitter", f"{p.jitter:g}")
        await self.link.state("game/pause", f"{p.pause:g}")
        await self.link.state("game/gap_now", f"{p.gap_now():g}")
        await self.link.state("game/next_at",
                              "" if p.next_at is None else f"{p.next_at:.0f}")

    async def _publish_tallies(self) -> None:
        assert self.link is not None
        t = self.tallies
        await self.link.state("game/started", str(t.started))
        await self.link.state("game/success", str(t.success))
        await self.link.state("game/fail", str(t.fail))

    async def _say(self, text: str, call: int | None = None) -> None:
        assert self.log
        await self.log.add(text, call)
        self.session.event(text, call)

    async def _error(self, text: str) -> None:
        assert self.link is not None
        log.warning("page: %s", text)
        await self.link.state("game/error", text)

    # ---- page commands (§13.2) ---------------------------------------------

    async def on_command(self, name: str, payload: str) -> None:
        """Quick by design: validate, echo, start or cancel, return."""
        self._active_at = time.time()               # a key or a button (Rev 57)
        try:
            if name == "run":
                if payload == "on":
                    await self.start()
                elif payload == "off":
                    await self.stop("stop")
                else:
                    await self._error(f"run: {payload!r} is not on or off")
                return

            if name == "sweep":
                await self._sweep_command(payload)
                return

            if name == "power_cut":
                # §10, Rev 63: the switchboard reset by hand, "on"; §11.7,
                # Rev 65: switched off from the page, "hold", and on again,
                # "off". Not held off during a game: it could not be played on
                # a dark board. The reset is allowed in one (Rev 66): the
                # board freezes the lines through it. On again always is.
                if payload not in ("on", "hold", "off"):
                    await self._error(f"power_cut: {payload!r} is not on, hold or off")
                    return
                if self.running and payload == "hold":
                    await self._error("power_cut: not while a game runs")
                    return
                if not self.b.control_up:
                    await self._error("power_cut: the controller is offline")
                    return
                assert self.hw is not None and self.link is not None
                await self.hw.power_cut(payload)
                await self._say(f"page: power_cut {payload}")
                await self.link.state("game/error", "")
                return

            if name == "playback":
                # §11.6, Rev 61: a recording on the loudspeaker, passed to the
                # audio program, which echoes audio/playback. Not during a
                # game: it would play over the calls.
                if not payload:
                    await self._error("playback: no recording named")
                    return
                if payload != "stop" and self.running:
                    await self._error("playback: not while a game runs")
                    return
                if payload != "stop" and self.b.get("audio/record") not in ("", "off", "failed"):
                    await self._error("playback: not while recording")
                    return
                if not self.b.audio_up:
                    await self._error("playback: the audio program is offline")
                    return
                assert self.hw is not None
                await self.hw.playback(payload)
                await self._say(f"page: playback {payload}")
                assert self.link is not None
                await self.link.state("game/error", "")
                return

            if name == "record":
                # §11.6, Rev 61: the loudspeaker recording, passed to the audio
                # program, which owns the file and echoes audio/record. Not
                # game state: it runs with or without a game, and Stop and
                # Start leave it alone.
                if payload not in ("on", "off"):
                    await self._error(f"record: {payload!r} is not on or off")
                    return
                if payload == "on" and self.b.get("audio/playback") not in ("", "missing"):
                    await self._error("record: not while a recording plays back")
                    return
                if not self.b.audio_up:
                    await self._error("record: the audio program is offline")
                    return
                assert self.hw is not None
                await self.hw.record(payload == "on")
                await self._say(f"page: recording {payload}")
                assert self.link is not None
                await self.link.state("game/error", "")
                return

            if name.startswith("diag/"):
                await self._diag_command(name.removeprefix("diag/"), payload)
                return

            if name == "queue":
                if payload and payload not in self.gs.choosable():
                    await self._error(f"queue: {payload!r} is not a scene that can be dealt")
                    return
                self.queued = payload
                await self._say(f"page: next scene {payload}" if payload else "page: next scene cleared")
                assert self.link is not None
                await self.link.state("game/queue", self.queued)
                await self.link.state("game/error", "")
                return

            if name == "repeat":
                # §7, Rev 34: the line she just finished, again. An event.
                if self.tutor is None or not self.tutor.repeat():
                    await self._error("repeat: nothing to repeat now, or the operator is speaking")
                    return
                await self._say("page: repeat help")
                return

            if name == "more":
                # §7, Rev 31: the next part of her introduction. An event, as
                # next is; a press with no further part is ignored. Rev 55: in
                # a call, the full form of the short line she last said.
                if self._more is not None:
                    self._more.set()
                elif self.tutor is None or not await self.tutor.more():
                    await self._error("more: no introduction, and no short line to say in full")
                    return
                await self._say("page: more help")
                return

            if name == "next":
                if not self.running:
                    await self._error("next: no game is running")
                    return
                if self._tutor_task is not None and (self._intro or self._unseen):
                    # §7: Next during the introduction cuts it short, and
                    # during her line at the end of a call (Rev 70).
                    self._tutor_task.cancel()
                    await asyncio.gather(self._tutor_task, return_exceptions=True)
                    self._tutor_task = None
                    self._intro = self._unseen = False
                    if self.tutor is not None:
                        await self.tutor.hush()
                await self._start_call(asked=True)
                return

            if name == "pace":
                if payload not in PACES:
                    await self._error(f"pace: {payload!r} is not tutor, manual, auto or listen")
                    return
                if payload == "tutor" and self.gs.tutor_missing:
                    m = self.gs.tutor_missing
                    await self._error(f"tutor: {len(m)} of her lines have no wav, "
                                      f"{', '.join(m[:3])}{' …' if len(m) > 3 else ''}")
                    return
                was = self.pacing.pace
                self.pacing.pace = payload
                await self._say(f"page: pace {payload}")
                if self.running and payload == "tutor" and was != "tutor":
                    # §7: she tutors from the next call; the introduction
                    # and the lessons come only with Start.
                    self.tutor = self._new_tutor()
                    assert self.slots is not None
                    self.slots.timeless = True
                elif was == "tutor" and payload != "tutor":
                    await self._end_tutor()              # silent at once
                if self.running:
                    await self._reschedule()
                else:
                    self.pacing.next_at = None
                    await self._publish_pacing()
                    self._arm_idle()                 # from the latest choice (Rev 44)
                return

            if name in ("gap", "ramp", "floor", "jitter", "pause"):
                try:
                    want = float(payload)
                except ValueError:
                    await self._error(f"{name}: {payload!r} is not a number")
                    return
                applied = self.pacing.clamp(name, want)
                setattr(self.pacing, name, applied)
                # floor is not allowed above gap, so lowering gap can pull it down.
                if name == "gap":
                    self.pacing.floor = min(self.pacing.floor, self.pacing.gap)
                await self._say(f"page: {name} {applied:g}")
                await self._publish_pacing()
                if applied != want:
                    await self._error(f"{name} clamped to {applied:g}")
                return

            await self._error(f"unknown command {name!r}")
        except Offline as e:
            log.warning("command %s dropped: %s", name, e)

    def _new_tutor(self) -> Tutor:
        assert self.hw is not None
        return Tutor(self.b, self.hw, self.gs.tutor, on_repeat=self._repeat_state,
                     on_more=self._more_state)

    async def _more_state(self, key: str) -> None:
        """game/tutor/more (§7, Rev 55): the full line More Help would say."""
        if self.link is not None:
            await self.link.state("game/tutor/more", key)

    async def _repeat_state(self, key: str) -> None:
        """game/tutor/repeat (§7, Rev 34): the line Repeat Help would say."""
        if self.link is not None:
            await self.link.state("game/tutor/repeat", key)

    async def _end_tutor(self) -> None:
        """Her task cancelled, and her voice stopped (§7)."""
        t, self._tutor_task = self._tutor_task, None
        if t is not None:
            t.cancel()
            await asyncio.gather(t, return_exceptions=True)
        self._intro = self._unseen = False
        self._lessons = []
        await self._waiting("")
        if self.tutor is not None:
            await self.tutor.stop()
            self.tutor = None
        if self.slots is not None:
            self.slots.timeless = False

    async def _diag_command(self, sub: str, payload: str) -> None:
        """game/diag/<target>/<test>/set (§11.4, Rev 25)."""
        assert self.diag is not None
        target, _, test = sub.rpartition("/")
        if payload not in ("on", "off"):
            await self._error(f"diag {sub}: {payload!r} is not on or off")
            return
        if not self.diag.fitted(target):
            await self._error(f"diag: {target or sub} is not a circuit fitted")
            return
        if test not in TESTS[kind_of(target)]:
            await self._error(f"diag: no {test!r} test on {target}")
            return
        on = payload == "on"
        if on and target in self._circuits_in_calls():
            await self._error(f"diag: {target} is in a call")
            return
        await self.diag.command(target, test, on)
        await self._say(f"page: {target} {test} {payload}")
        assert self.link is not None
        await self.link.state("game/error", "")

    async def _sweep_command(self, payload: str) -> None:
        """game/sweep/set: "trunks", "stations" or "off" (§11.5, Rev 50)."""
        if payload not in (*sweep.KINDS, "off"):
            await self._error(f"sweep: {payload!r} is not trunks, stations or off")
            return
        if payload != "off" and self.running:
            await self._error("sweep: not while a game runs")
            return
        await self._end_sweep()
        assert self.link is not None and self.hw is not None and self.diag is not None
        if payload != "off":
            self._sweep_kind = payload
            self._sweep = asyncio.create_task(self._run_sweep(payload), name=f"sweep-{payload}")
            await self.link.state("game/sweep", payload)
        await self.link.state("game/error", "")

    async def _run_sweep(self, kind: str) -> None:
        assert self.hw is not None and self.diag is not None
        out_st, working = self.cfg.stations_out(), self.cfg.working_trunks()

        def out(circuit: str) -> bool:
            k, n = circuit.split("/")
            return int(n) in out_st if k == "station" else int(n) not in working

        try:
            await sweep.run(kind, self.hw, self.gs.jacks, self.cfg.stations, self.cfg.trunks,
                            self.diag.circuits, self._say, out, self.cfg.public_trunk)
        except asyncio.CancelledError:
            raise
        except Exception as e:                       # offline, above all
            log.warning("sweep %s: %s", kind, e)
            try:
                await self._say(f"test {kind}: stopped, {e}")
            except Exception:
                pass
        finally:
            if self._sweep is asyncio.current_task():
                self._sweep, self._sweep_kind = None, ""
                if self.link is not None:
                    try:
                        await self.link.state("game/sweep", "")
                    except Exception:
                        pass

    async def _end_sweep(self) -> None:
        """Cancel a sweep in progress; its circuit is put back as it ends."""
        t, kind = self._sweep, self._sweep_kind
        self._sweep, self._sweep_kind = None, ""
        if t is None:
            return
        t.cancel()
        await asyncio.gather(t, return_exceptions=True)
        await self._say(f"test {kind}: stopped")
        if self.link is not None:
            await self.link.state("game/sweep", "")

    def _circuits_in_calls(self, free: bool = True) -> set[str]:
        """Every station and trunk a call in progress is using; and, unless
        free is false, every one a free call is using (§8)."""
        out: set[str] = self.free.circuits() if free else set()
        assert self.slots is not None
        for call in self.slots:
            sc = self.gs.scenes.get(call.scene)
            if sc is not None:
                for n in (sc.from_station, sc.to_station):
                    if n is not None:
                        out.add(f"station/{n}")
            if call.trunk:
                out.add(call.trunk)
        return out

    # ---- start and stop (§2) --------------------------------------------

    async def start(self) -> None:
        if self.running:
            return                                  # ignored while running (§2)
        assert self.link is not None and self.slots is not None and self.log is not None
        await self._end_sweep()                     # §11.5: a game takes the board
        if self.b.get("ctl/power_cut") == "hold" and self.b.control_up and self.hw is not None:
            await self.hw.power_cut("off")          # §2, Rev 65: and its power
            await self._say("switchboard powered for the game")
        if self.b.get("audio/playback") not in ("", "missing") and self.hw is not None:
            await self.hw.playback("stop")          # §11.6: and the loudspeaker
        self.running = True
        self._active_at = time.time()
        self._disarm_idle()
        self._hinted.clear()
        self._hint_end.clear()
        self._rear_since.clear()
        self.tallies.zero()
        self.next_number = 1
        self.pacing.connected = 0
        self.pacing.gap = self.cfg.gap              # the gap returns to configured (§2)
        self.deck = Deck(self.gs)
        self.pacing.seed(self.deck.seed)
        self._delays = random.Random(f"delays {self.deck.seed}")
        self._scenarios_dealt = set()
        await self.session.start_game(self.deck.seed, self.pacing.pace,
                                      self.pacing.gap, self.pacing.ramp,
                                      self.pacing.floor, self.pacing.jitter,
                                      self.pacing.pause)
        self.session.deck(1, self.deck.orders[0])
        self._decks_recorded = 1
        await self.log.clear()
        await self._say("game started")
        await self._monitor("tap")                  # §9.1
        await self.link.state("game/run", "on")
        await self.link.state("game/error", "")
        await self._publish_tallies()
        self.pacing.next_at = None
        if self.pacing.pace == "tutor":
            # §7: she introduces the board first, and the first call waits
            # for Next Call, in every pacing (Rev 31).
            self.tutor = self._new_tutor()
            self.slots.timeless = True
            # §7, Rev 30: one scene of each kind first, picked from the
            # game's seed apart from the deck's own shuffle, so a replay
            # picks the same and a restart most likely does not.
            self._lessons = pick_lessons(self.gs.lessons, self.deck.seed)
            if self._lessons:
                await self._say("tutor lessons: " + ", ".join(self._lessons))
            self._intro = True
            self._tutor_task = asyncio.create_task(self._tutor_intro(), name="tutor-intro")
        elif self.pacing.automatic:
            await self._start_call()                # the first call at once (§2)
        await self._publish_pacing()

    async def stop(self, why: str) -> None:
        """Tear every call down at once. The tallies stay (§2)."""
        if self.diag is not None:
            await self.diag.end_all()               # every diagnostic (§11.4)
        await self._end_sweep()                     # and a sweep (§11.5)
        if self.queued and self.link is not None:
            self.queued = ""                        # §6.4: Stop forgets it
            await self.link.state("game/queue", "")
        if not self.running:
            return
        assert self.link is not None and self.slots is not None
        self.running = False
        await self._end_tutor()                     # §7
        for t in list(self._flows.values()):
            t.cancel()
        for t in list(self._afters.values()) + list(self._tails.values()):
            t.cancel()
        # Let the cancellations run their `finally` blocks before clearing.
        await asyncio.gather(*self._flows.values(), *self._afters.values(),
                             *self._tails.values(), return_exceptions=True)
        self._tails.clear()
        self._flows.clear()
        self._afters.clear()
        self._pending_after.clear()
        self._after_due.clear()
        await self.slots.clear_all()
        self.pacing.next_at = None
        await self._monitor("tap")                  # §9.1
        await self._say(f"game stopped: {why}" if why != "stop" else "game stopped")
        if self.b.control_up and self.hw is not None:
            # §2, Rev 63: a trunk rung in holds its lamp and buzzer on the
            # switchboard's own battery until a cord goes in; only the cut
            # clears it. Not waited for.
            await self.hw.power_cut()
            await self._say("switchboard power cut")
        await self.session.end_game(why, self.tallies.started,
                                    self.tallies.success, self.tallies.fail)
        await self.link.state("game/run", "off")
        await self._publish_pacing()
        self._arm_idle()

    # ---- back to tutor when stopped (§7, Rev 44) ------------------------

    def _disarm_idle(self) -> None:
        if self._to_tutor is not None and self._to_tutor is not asyncio.current_task():
            self._to_tutor.cancel()
        self._to_tutor = None

    def _arm_idle(self) -> None:
        """Start, or start over, the wait that returns a stopped game to tutor."""
        self._disarm_idle()
        if (self.cfg.idle_tutor > 0 and not self.running
                and self.pacing.pace != "tutor" and not self.gs.tutor_missing):
            self._to_tutor = asyncio.create_task(self._idle_timer(), name="idle-tutor")

    async def _idle_timer(self) -> None:
        try:
            await asyncio.sleep(self.cfg.idle_tutor)
            if self.running or self.pacing.pace == "tutor":
                return
            self.pacing.pace = "tutor"
            await self._say(f"pace tutor: stopped {self.cfg.idle_tutor:g}s")
            await self._publish_pacing()
        except asyncio.CancelledError:
            raise
        except Exception as e:                       # offline: try again later
            log.info("idle tutor: %s", e)
        finally:
            if self._to_tutor is asyncio.current_task():
                self._to_tutor = None

    async def _monitor(self, source: str, peer: str = "auto") -> None:
        """The game moving the loudspeaker (§9.1), with the peer boost.
        That ends a monitor test."""
        if self.hw is None:
            return
        if self.diag is not None:
            await self.diag.monitor_moved()
        try:
            await self.hw.monitor_source(source, peer)
        except Offline as e:
            log.warning("monitor source %s dropped: %s", source, e)

    # ---- dealing and running calls --------------------------------------

    def _held(self) -> list[Holding]:
        """What every call in progress and every waiting `after:` occupies,
        and every free call (§8)."""
        out = list(self._pending_after.values()) + self.free.holdings()
        # A station under test is busy for dealing (§11.4).
        if self.diag is not None:
            for c in self.diag.circuits():
                kind, n = c.split("/")
                if kind == "station" and int(n) in self._station_lines:
                    out.append(Holding(self._station_lines[int(n)], frozenset()))
        assert self.slots is not None
        for call in self.slots:
            sc = self.gs.scenes[call.scene]
            people = frozenset(p for p in self.gs.people[sc.id] if p)
            out.append(Holding(frozenset(sc.lines), people))
        return out

    def _wanted_stations(self) -> set[int]:
        """The rooms the game calls not yet connected are to ring (§8):
        a ring on one of them is that call's, not a free call's."""
        out: set[int] = set()
        for call in (self.slots if self.slots is not None else ()):
            sc = self.gs.scenes.get(call.scene)
            if sc is not None and sc.to_station is not None and not call.connected:
                out.add(sc.to_station)
        return out

    def _waiting_to_connect(self) -> bool:
        assert self.slots is not None
        return any(not c.connected for c in self.slots)

    def _scenario_on_board(self) -> bool:
        """Any call of a scenario in progress, or any of its scenes waiting (§6.5)."""
        assert self.slots is not None
        return (any(self.gs.in_scenario(c.scene) for c in self.slots)
                or any(self.gs.in_scenario(i) for i in self._pending_after))

    def _scenario_allowed(self) -> bool:
        """A scenario is never dealt in tutor mode or listen (§6.5)."""
        return self.tutor is None and self.pacing.pace in ("manual", "auto")

    def _idle(self) -> bool:
        """Whether the automatic schedule may run now (§5.2).

        Auto: no call is waiting to be connected. Listen (Rev 16): no call in
        progress at all and no `after:` scene waiting to start, so the next
        call comes only once the story on the board has been heard out.
        Tutor mode (§7): as listen, and not while she is introducing the
        board or waiting for the cords out after a call.
        """
        assert self.slots is not None
        if self.tutor is not None:
            return (not any(True for _ in self.slots) and not self._pending_after
                    and self._tutor_task is None)
        if self.pacing.pace == "listen":
            return not any(True for _ in self.slots) and not self._pending_after
        # §6.5: a scenario on the board holds the schedule until it is over.
        return not self._waiting_to_connect() and not self._scenario_on_board()

    async def _reschedule(self, keep: bool = False) -> None:
        """Schedule the next call if the board is idle for the pace, else clear it.

        keep: a start already scheduled stands. A call that ends after it was
        connected must not restart the gap its connection began (§5.2).
        """
        if self._idle():
            if not (keep and self.pacing.next_at is not None):
                self.pacing.schedule()
        else:
            self.pacing.next_at = None
        await self._publish_pacing()

    def _free_trunk(self) -> int | None:
        """A trunk fitted and in service (§12.2), idle, and not under test (§11.4);
        of those, the one whose seizure changed longest ago (Rev 85). A trunk
        whose station has just hung up reads idle with the operator's cord still
        in its jack, since the game cannot see a cord without a loop."""
        tested = self.diag.circuits() if self.diag is not None else set()
        free = []
        for n in self.cfg.working_trunks():
            if f"trunk/{n}" in tested:
                continue
            if not self.b.on(f"trunk/{n}/seize") and not self.b.on(f"trunk/{n}/ring"):
                if not any(c.trunk == f"trunk/{n}" for c in (self.slots if self.slots is not None else ())):
                    free.append(n)
        return min(free, key=lambda n: self.b.changed_at(f"trunk/{n}/seize"), default=None)

    async def _start_call(self, asked: bool = False, scene: SceneDef | None = None) -> None:
        """Deal a scene and run it, or say why not."""
        assert self.slots is not None and self.deck is not None
        if not self.running:
            return
        if self.tutor is not None and (any(True for _ in self.slots)
                                       or self._tutor_task is not None):
            why = ("one call at a time in tutor mode" if self._tutor_task is None
                   else "the tutor is finishing")
            await self._say(f"no call: {why}")
            if asked:
                await self._error(why)
            return
        slot = self.slots.free_slot()
        if slot is None:
            why = "all eight slots are busy"
            await self._say(f"no call: {why}")
            if asked:
                await self._error(why)
            return

        if scene is None and self.queued:
            # §6.4: the chosen scene, if its lines and people are free.
            q = self.gs.scenes.get(self.queued)
            if q is not None and q.after_handled is not None and self.tutor is None:
                # §6.5, Rev 40: a chosen scenario, in any pacing but tutor,
                # waits for a clear board, and nothing else is dealt meanwhile.
                if any(True for _ in self.slots) or self._pending_after:
                    why = "waiting for the board to clear"
                    await self._say(f"no call: {q.id} {why}")
                    if asked:
                        await self._error(why)
                    if self.pacing.automatic:
                        await self._reschedule()
                    return
            if (q is not None and (q.after_handled is None or self.tutor is None)
                    and self.deck.take(q, self._held())):
                scene = q
                self.queued = ""
                if q.after_handled is not None:
                    # §6.5, Rev 49: a chosen scenario is its play for the game.
                    self._scenarios_dealt.add(q.id)
                assert self.link is not None
                await self.link.state("game/queue", "")
                await self._say(f"chosen scene {q.id} dealt")
        if scene is None and self._scenario_allowed():
            # §6.5: a scenario, once enough calls have been handled.
            for q in self.gs.scenarios():
                if (q.id not in self._scenarios_dealt
                        and self.tallies.handled >= (q.after_handled or 0)
                        and self.deck.take(q, self._held())):
                    scene = q
                    self._scenarios_dealt.add(q.id)
                    await self._say(f"scenario {q.id} dealt, after "
                                    f"{self.tallies.handled} calls handled")
                    break
        if scene is None and self.tutor is not None and self._lessons:
            # §7, Rev 30: the next lesson, taken out of the deck as a
            # chosen scene is (§6.4).
            q = self.gs.scenes.get(self._lessons.pop(0))
            if q is not None and self.deck.take(q, self._held()):
                scene = q
                await self._say(f"lesson {q.id} dealt")
        if scene is None:
            scene, why = self.deck.deal(self._held())
            if scene is None:
                await self._say(f"no call: {why}")
                if asked:
                    await self._error(why)
                if self.pacing.automatic:
                    await self._reschedule()        # try again after gap_now
                return
            # deal() reshuffles when the deck runs out (§6.1). Record each new
            # order for the replay, and log it, which the specification asks for.
            while self._decks_recorded < len(self.deck.orders):
                self._decks_recorded += 1
                self.session.deck(self._decks_recorded,
                                  self.deck.orders[self._decks_recorded - 1])
                if self._decks_recorded > 1:
                    await self._say("deck reshuffled")

        # A call from an outside line rings in on a trunk: to a room, or to
        # the operator herself (Rev 24).
        trunk = None
        if scene.from_station is None:
            trunk = self._free_trunk()
            if trunk is None:
                await self._say(f"no call: no free trunk for {scene.id}")
                if asked:
                    await self._error("no free trunk")
                return

        await self._waiting("")                     # §7, Rev 33
        call = Call(slot=slot, number=self.next_number, scene=scene.id,
                    from_line=scene.from_line, to_line=scene.to_line)
        self.next_number += 1
        self.tallies.started += 1
        await self.slots.open(call)
        await self._publish_tallies()
        to = f" → {scene.to_line}" if scene.to_line else " → operator"
        await self._say(f"started {scene.id}: {scene.from_line}{to}", call.number)
        self.session.call_started(call.number, scene.id, scene.from_line, scene.to_line)

        # A call is out and unconnected: nothing is scheduled until it connects
        # or ends (§5.2).
        self.pacing.waiting_to_connect()
        await self._publish_pacing()

        self._flows[slot] = asyncio.create_task(
            self._run_call(call, scene, trunk), name=f"call-{call.number}")

        # §6.1, Rev 39: a `mode: concurrent` follower is timed from this start.
        for follower in self.gs.followers(scene.id):
            if follower.concurrent:
                self._schedule_after(follower)

    async def _run_call(self, call: Call, scene: SceneDef, trunk: int | None) -> None:
        assert self.slots is not None and self.hw is not None
        cfg = self.cfg
        if self.tutor is not None:
            # §7: nobody fails for being slow while she teaches.
            cfg = dataclasses.replace(cfg, answer_timeout=NO_LIMIT,
                                      connect_timeout=NO_LIMIT)
        ctx = Ctx(board=self.b, hw=self.hw, cfg=cfg, slots=self.slots,
                  call=call, scene=scene,
                  say_event=lambda t, n=call.number: asyncio.create_task(
                      self._say(t, n)),
                  mark_connected=lambda: self._connected(call),
                  set_monitor=self._monitor,
                  tutor=self.tutor, jack_of=self.gs.jack_of,
                  reaction=self.gs.reaction,
                  occupant=lambda n: self.gs.occupants.get(n, ""),
                  free_callers=self.free.callers, free_routing=self.free.routing,
                  public_trunk=self.cfg.public_trunk,
                  hint_end=lambda n=call.number: self._hint_end.get(n, 0.0))
        outcome = Outcome(False, "cancelled")
        try:
            if scene.shape == Shape.OUTSIDE_TO_STATION:
                outcome = await outside_to_station(ctx, trunk or 1)
            elif scene.shape == Shape.TO_OPERATOR and trunk is not None:
                outcome = await to_operator(ctx, trunk)
            else:
                outcome = await FLOWS[scene.shape](ctx)
        except asyncio.CancelledError:
            raise                                   # Stop: not a success or a failure
        except Offline as e:
            outcome = Outcome(False, f"client lost: {e}")
            asyncio.create_task(self.stop(f"client lost ({e})"))
        except Exception:
            log.exception("call %d (%s) failed", call.number, scene.id)
            outcome = Outcome(False, "error")
        finally:
            self._flows.pop(call.slot, None)
            if self.running:
                await self._finish_call(call, scene, outcome)

    async def _connected(self, call: Call) -> None:
        """The §3.3 milestone: the operator's routing work is done."""
        if call.connected:
            return
        call.connected = True
        self.pacing.connected += 1
        self.session.call_connected(call.number)
        await self._say("connected", call.number)
        await self._reschedule()

    async def _finish_call(self, call: Call, scene: SceneDef,
                           outcome: Outcome) -> None:
        assert self.slots is not None
        if outcome.ok:
            self.tallies.success += 1
            await self._say("success", call.number)
            self.session.call_ended(call.number, "success", call.trunk, call.digits)
        else:
            self.tallies.fail += 1
            await self._say(f"failed: {outcome.reason}", call.number)
            self.session.call_ended(call.number, outcome.reason, call.trunk, call.digits)
        await self.slots.close(call)
        await self._publish_tallies()
        if call.trunk and self.running:
            n = int(call.trunk.split("/")[1])
            if n not in self._tails:
                self._tails[n] = asyncio.create_task(self._trunk_tail(n),
                                                     name=f"tail-trunk-{n}")

        if self.tutor is not None and self.running:
            # §7: she sees the call down; nothing is dealt meanwhile.
            self._intro = self._unseen = False
            self._tutor_task = asyncio.create_task(
                self._tutor_hangup(call, scene), name=f"tutor-hangup-{call.number}")

        # §6.1: an `after:` scene follows only if this call was connected.
        # A concurrent one was scheduled when this call started.
        for follower in self.gs.followers(scene.id):
            if follower.concurrent:
                continue
            if call.connected:
                self._schedule_after(follower)
            else:
                await self._say(
                    f"dropped {follower.id}: {scene.id} was never connected")

        await self._reschedule(keep=True)

    async def _trunk_tail(self, n: int) -> None:
        """§3.4: the far end has hung up. Reorder REORDER_AFTER later, while
        her cord is still in the trunk and the trunk is patched to nobody,
        until she takes it down, or a new call takes the trunk. Patched to a
        line, the trunk is quiet, so a new caller on that cord is heard."""
        seized, peer = f"trunk/{n}/seize", f"trunk/{n}/peer"
        taken = lambda: any(c.trunk == f"trunk/{n}" for c in (self.slots or ()))
        released = lambda b: not b.on(seized) or taken()
        patched = lambda b: "/" in (b.get(peer) or "")
        playing = False
        try:
            try:
                await self.b.wait_until(released, REORDER_AFTER)
                return
            except TimeoutError:
                pass
            told = False
            while not released(self.b):
                if patched(self.b):
                    if playing:
                        await self.hw.tone(n, "off")
                        playing = False
                    await self.b.wait_until(lambda b: released(b) or not patched(b), None)
                else:
                    if not playing:
                        await self.hw.tone(n, "reorder")
                        playing = True
                        if not told:
                            await self._say(f"trunk/{n}: reorder, the far end has hung up")
                            told = True
                    await self.b.wait_until(lambda b: released(b) or patched(b), None)
        except Exception:                       # Offline, or the broker gone
            pass
        finally:
            if playing and not taken():
                try:
                    await self.hw.tone(n, "off")
                except Exception:
                    pass
            if self._tails.get(n) is asyncio.current_task():
                del self._tails[n]

    # ---- tutor mode (§7) ------------------------------------------------

    async def _waiting(self, what: str) -> None:
        """game/tutor/waiting (§7, Rev 33): she has finished and waits for
        More Help or Next Call ("more"), or Next Call alone ("next"), so the
        deck can flash the key. Empty otherwise."""
        if self.link is None or what == self._waiting_for:
            return
        self._waiting_for = what
        try:
            await self.link.state("game/tutor/waiting", what)
        except Exception:
            pass

    async def _tutor_intro(self) -> None:
        """Her introduction, a part at a time (§7, Rev 31).

        After each part but the last she waits for More Help, which also cuts
        a part short; after the last, for Next Call, in every pacing. Next
        Call ends it at any point, by cancelling this task.
        """
        t = self.tutor
        assert t is not None and self.link is not None
        try:
            for i, key in enumerate(INTRO, 1):
                self._more = asyncio.Event()
                await self.link.state("game/tutor/intro", f"{i}/{len(INTRO)}")
                speaking = asyncio.create_task(t.say(key, hold=True), name=f"tutor-{key}")
                waits = {speaking}
                more = None
                if i < len(INTRO):
                    more = asyncio.create_task(self._more.wait())
                    waits.add(more)
                try:
                    await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
                    if more is None:
                        await speaking
                        await self._waiting("next")         # Rev 33: the deck flashes
                        await asyncio.Event().wait()        # until Next Call
                    if not more.done():
                        await self._waiting("more")
                    await more
                finally:
                    for x in waits:
                        x.cancel()
                    await asyncio.gather(*waits, return_exceptions=True)
                    await self._waiting("")
        except Exception as e:
            log.warning("tutor intro: %s", e)
        finally:
            self._more = None
            if self._tutor_task is asyncio.current_task():
                self._tutor_task = None
                self._intro = False
            try:
                await self.link.state("game/tutor/intro", "")
            except Exception:
                pass

    async def _tutor_hangup(self, call: Call, scene: SceneDef) -> None:
        """Her line at the end of a call, then Next Call before the next.

        Rev 70: the board cannot see the cords once a call is down. A station
        on-hook draws no loop current, so its pilot, and with it `peer`, is
        gone whether the cord is in or out (Rev 67); and a trunk's loop runs
        through the station's line, so its seizure drops when the station
        hangs up, cord in or not. Her line is said in full, and the player's
        Next Call is the word that the cords are out.
        """
        t = self.tutor
        assert t is not None
        key = "hangup-one" if scene.shape == Shape.TO_OPERATOR else "hangup-pair"
        try:
            self._unseen = True
            await t.say(key, hold=True)
            if not self.pacing.automatic:
                await t.say("ready-manual", hold=True)
                await self._waiting("next")     # until a call is dealt (Rev 33)
        except (TimeoutError, Offline) as e:
            log.info("tutor: call %d not cleared: %s", call.number, e or "timeout")
        finally:
            if self._tutor_task is asyncio.current_task():
                self._tutor_task = None
                self._unseen = False
        if self.running:
            await self._reschedule()

    # ---- `after:` scenes (§6.1) -----------------------------------------

    def _schedule_after(self, scene: SceneDef) -> None:
        self._pending_after[scene.id] = Holding(frozenset(scene.needs),
                                                self.gs.needs_people(scene.id))
        delay = scene.delay
        if scene.delay_max > scene.delay:           # a range (§6.1, Rev 39)
            delay = self._delays.uniform(scene.delay, scene.delay_max)
        self._afters[scene.id] = asyncio.create_task(
            self._after_timer(scene, delay), name=f"after-{scene.id}")

    def _after_rank(self, scene_id: str) -> tuple[int, float, str]:
        """Which of two waiting `after:` scenes, both past their delay, starts
        first when each holds what the other needs (§6.1): a scenario's scene,
        then the one due first. Lower goes first."""
        return (0 if self.gs.in_scenario(scene_id) else 1,
                self._after_due.get(scene_id, 0.0), scene_id)

    async def _after_timer(self, scene: SceneDef, delay: float) -> None:
        try:
            at = time.time() + delay
            secs = f"{delay:g}" if delay == scene.delay else f"{delay:.1f}"
            await self._say(f"{scene.id} follows in {secs}s, at "
                            f"{time.strftime('%H:%M:%S', time.localtime(at))}")
            await asyncio.sleep(delay)
            self._after_due[scene.id] = at
            # Its lines may still be busy in another call: wait for them (§6.1).
            # A concurrent one waits for a free slot too, rather than being lost.
            # Another waiting scene past its delay and ranked behind this one
            # gives way to it, so two never wait on each other.
            ahead_of: set[str] = set()
            behind: dict[int, str] = {}
            while self.running:
                mine = self._pending_after.get(scene.id)
                behind = {id(h): sid for sid, h in self._pending_after.items()
                          if sid in self._after_due
                          and self._after_rank(sid) > self._after_rank(scene.id)}
                others = [h for h in self._held() if h is not mine and id(h) not in behind]
                lines, people = set(scene.needs), set(self.gs.needs_people(scene.id))
                tutor_busy = self.tutor is not None and (
                    self._tutor_task is not None or any(True for _ in self.slots or ()))
                full = (scene.concurrent and self.slots is not None
                        and self.slots.free_slot() is None)
                if not tutor_busy and not full and not any(
                        lines & h.lines or people & h.people for h in others):
                    break
                await asyncio.sleep(0.5)
            for h in self._held():
                sid = behind.get(id(h))
                if sid and sid not in ahead_of and (lines & h.lines or people & h.people):
                    ahead_of.add(sid)
                    await self._say(f"{scene.id} goes before {sid}, which waits for it")
            self._pending_after.pop(scene.id, None)
            self._after_due.pop(scene.id, None)
            self._afters.pop(scene.id, None)
            if self.running:
                started = self.tallies.started
                await self._start_call(scene=scene)
                # In listen a waiting `after:` holds the schedule; if it could
                # not start after all, the board is empty and must not stall.
                if (self.running and self.tallies.started == started
                        and self.pacing.automatic):
                    await self._reschedule()
        except asyncio.CancelledError:
            self._pending_after.pop(scene.id, None)
            self._after_due.pop(scene.id, None)
            raise

    # ---- the scheduler (§5.2) -------------------------------------------

    async def run_scheduler(self) -> None:
        """Start a call when the automatic gap has elapsed."""
        while True:
            try:
                if (self.running and self.cfg.idle_stop > 0
                        and time.time() - self._active_at >= self.cfg.idle_stop):
                    # Rev 57: nobody at the board; Start resumes.
                    await self.stop(f"no activity for {self.cfg.idle_stop / 60:g} min")
                    continue
                if self.running and self.pacing.due():
                    await self._start_call()
                await asyncio.sleep(0.25)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("scheduler")
                await asyncio.sleep(1)

    # ---- losing a client (§2) -------------------------------------------

    def _wrong_ring(self, ch: Change) -> tuple[Call, str] | None:
        """The call and her line, when a ring just ended on the wrong cord of
        a call in progress, not yet told this call (§7.7, Rev 88)."""
        if self.slots is None:
            return None
        if m := _TRUNK_FAULT.match(ch.key):
            if ch.old != "ring_on_trunk" or ch.new == "ring_on_trunk":
                return None
            if (found := self._trunk_call(f"trunk/{m[1]}")) is None:
                return None
            c, shape = found
            key = {Shape.OUTSIDE_TO_STATION: "rang-trunk",
                   Shape.STATION_TO_OUTSIDE: "rang-outside"}.get(shape)
        elif m := _STATION_RINGING.match(ch.key):
            if ch.old != "on" or ch.new == "on":
                return None
            n = int(m[1])
            found = [c for c in self.slots
                     if (sc := self.gs.scenes[c.scene]).from_station == n
                     and sc.shape == Shape.STATION_TO_STATION]
            if not found:
                return None
            c, key = found[0], "rang-caller"
        else:
            return None
        if key is None or (c.number, key) in self._hinted:
            return None
        self._hinted.add((c.number, key))
        return c, key

    def _trunk_call(self, trunk: str) -> tuple[Call, Shape] | None:
        """The call holding this trunk, else a call out whose trunk is not
        yet known (§7.7)."""
        assert self.slots is not None
        calls = [(c, self.gs.scenes[c.scene].shape) for c in self.slots]
        held = [(c, s) for c, s in calls if c.trunk == trunk]
        if held:
            return held[0]
        out = [(c, s) for c, s in calls if s == Shape.STATION_TO_OUTSIDE and not c.trunk]
        return out[0] if out else None

    def _rear_check(self, ch: Change) -> None:
        """Start the wait when a trunk hears the operator unseized, which
        only a rear cord in it does (§7.7, Rev 93); any change ends it."""
        if not (m := _TRUNK_OP_SEIZE.match(ch.key)):
            return
        n = int(m[1])
        if self.b.get(f"trunk/{n}/op") == "on" and self.b.get(f"trunk/{n}/seize") != "on":
            if n not in self._rear_since:
                self._rear_since[n] = since = time.time()
                asyncio.create_task(self._rear_hint(n, since), name="rear-in-trunk")
        else:
            self._rear_since.pop(n, None)

    async def _rear_hint(self, n: int, since: float) -> None:
        await asyncio.sleep(self.b.hold + REAR_HOLD)
        if self._rear_since.get(n) != since or not self.running or self.slots is None:
            return
        if (found := self._trunk_call(f"trunk/{n}")) is None:
            return
        c = found[0]
        if c.connected or (c.number, "rear-in-trunk") in self._hinted:   # a hang-up drops seize
            return
        self._hinted.add((c.number, "rear-in-trunk"))
        await self._hint(c, "rear-in-trunk")

    async def _hint(self, call: Call, key: str) -> None:
        """Her line for a wrong cord, on the monitor, in any pacing (§7.7)."""
        await self._say(f"wrong cord: {key}", call.number)
        sp = self.gs.tutor.get(key)
        if sp is None or self.hw is None:
            return
        self._hint_end[call.number] = time.time() + sp.seconds
        try:
            await say(self.b, self.hw, "audio/monitor", sp.name, sp.seconds)
        except (Offline, Abandoned, FileNotFoundError, TimeoutError) as e:   # a stop, a lost client
            log.info("wrong cord: %s not said: %s", key, e)

    async def watch_clients(self) -> None:
        """Stop the game if the controller or the audio program goes away;
        and note the player's acts on the board, for idle_stop (Rev 57)."""
        async for ch in self.b.watch():
            if PLAYER.match(ch.key):
                self._active_at = time.time()
            if self.running and (key := self._wrong_ring(ch)):
                asyncio.create_task(self._hint(*key), name="wrong-cord")
            if self.running:
                self._rear_check(ch)
            if ch.key in (LIVE_CONTROL, LIVE_AUDIO) and ch.new == "off":
                if self.running:
                    who = "controller" if ch.key == LIVE_CONTROL else "audio program"
                    await self.stop(f"{who} went offline")
