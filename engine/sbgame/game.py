"""The game (game_control.md §3 to §8).

One object owns everything with a lifetime: the deck, the pacing, the eight
slots, the tallies, the running scene tasks and the `after:` timers. The MQTT
link calls into it twice — `on_birth` when a connection comes up, and
`on_command` for each page command — and it calls back out through `Link.state`
to publish.

Three shapes of task run under it:

  `_scheduler`   one, for the life of the program: starts a call when the
                 automatic gap has elapsed (§4.2).
  a flow task    one per call in progress, cancelled by Stop.
  an after timer one per waiting `after:` scene, cancelled by Stop (§4.4):
                 from the end of the scene it follows, or for `mode:
                 concurrent` from its start, which is how a scenario puts
                 its calls on the board almost together (§4.10).
  a tutor task   in tutor mode (§4.9), the introduction after Start, or the
                 end of a call: her line, then the wait for the cords out.
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
import time
from dataclasses import dataclass

from .board import Board, LIVE_AUDIO, LIVE_CONTROL, Offline
from .calls import Call, N_SLOTS, Reason, Slots, Stage, Tallies
from .config import Config
from .deck import Deck, Holding
from .diag import TESTS, Diagnostics, kind_of
from .flows import Ctx, FLOWS, Outcome, outside_to_station, to_operator
from .gamelog import GameLog
from .pacing import PACES
from .link import Hw, Link
from .script_data import GameScript, SceneDef, Shape
from .session import SessionLog
from .tutor import INTRO, NO_LIMIT, Tutor

log = logging.getLogger("game")



def pick_lessons(groups, seed: int) -> list[str]:
    """One scene from each group, in order, from the game's seed (§4.9, Rev 30)."""
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
        # that; a restart returns to the configured values (§4.3).
        from .pacing import Pacing
        self.pacing = Pacing(pace=cfg.pace, gap=cfg.gap, ramp=cfg.ramp, floor=cfg.floor,
                             jitter=cfg.jitter, pause=cfg.pause)
        if self.pacing.pace == "tutor" and gs.tutor_missing:
            log.warning("pace tutor configured, but %d of her lines have no wav: manual",
                        len(gs.tutor_missing))
            self.pacing.pace = "manual"

        self._flows: dict[int, asyncio.Task] = {}       # slot -> task
        self._afters: dict[str, asyncio.Task] = {}      # scene id -> timer task
        self._pending_after: dict[str, Holding] = {}    # what a waiting after holds
        self._scheduler: asyncio.Task | None = None
        self._decks_recorded = 0        # how many of deck.orders are in SQLite
        self.diag: Diagnostics | None = None
        self.queued = ""                # the chosen next scene (§4.8)
        self._scenarios_dealt: set[str] = set()   # once a game each (§4.10)
        self._delays = random.Random()  # drawn `delay` ranges, from the seed (§4.4)
        # Tutor mode (§4.9), the pacing `tutor` since Rev 32: `tutor` is her,
        # while a game runs in it.
        self.tutor: Tutor | None = None
        self._tutor_task: asyncio.Task | None = None
        self._intro = False             # the tutor task is the introduction
        self._more: asyncio.Event | None = None   # More Help, during it (Rev 31)
        self._waiting_for = ""          # game/tutor/waiting (Rev 33)
        self._lessons: list[str] = []   # the scenes a tutored game starts with
        # Station numbers to the script's line names, for holding a station
        # under test out of dealing (§7.5).
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
        because losing the broker stops it (§3).
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
        for j in self.gs.jacks:
            await link.state(f"board/{j.kind}/{j.number}/label", j.label)
            await link.state(f"board/{j.kind}/{j.number}/circuit", j.circuit)
        # §4.8, §6.5, §7.5 (Rev 25).
        await link.state("game/scenes", "\n".join(self.gs.choosable()))
        await link.state("game/queue", self.queued)
        await link.state("game/tutor/intro", "")
        self._waiting_for = ""
        await link.state("game/tutor/waiting", "")
        await link.state("game/tutor/repeat", "")
        await link.state("game/stations", str(self.cfg.stations))
        await link.state("game/trunks", str(self.cfg.trunks))
        assert self.diag is not None
        await self.diag.end_all()
        await self.diag.publish_all_off()

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

    # ---- page commands (§8) ---------------------------------------------

    async def on_command(self, name: str, payload: str) -> None:
        """Quick by design: validate, echo, start or cancel, return."""
        try:
            if name == "run":
                if payload == "on":
                    await self.start()
                elif payload == "off":
                    await self.stop("stop")
                else:
                    await self._error(f"run: {payload!r} is not on or off")
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
                # §4.9, Rev 34: the line she just finished, again. An event.
                if self.tutor is None or not self.tutor.repeat():
                    await self._error("repeat: nothing to repeat now, or the operator is speaking")
                    return
                await self._say("page: repeat help")
                return

            if name == "more":
                # §4.9, Rev 31: the next part of her introduction. An event, as
                # next is; a press with no further part is ignored.
                if self._more is None:
                    await self._error("more: the tutor is not introducing the board")
                    return
                self._more.set()
                await self._say("page: more help")
                return

            if name == "next":
                if not self.running:
                    await self._error("next: no game is running")
                    return
                if self._tutor_task is not None and self._intro:
                    # §4.9: Next during the introduction cuts it short.
                    self._tutor_task.cancel()
                    await asyncio.gather(self._tutor_task, return_exceptions=True)
                    self._tutor_task = None
                    self._intro = False
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
                    # §4.9: she tutors from the next call; the introduction
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
        return Tutor(self.b, self.hw, self.gs.tutor, on_repeat=self._repeat_state)

    async def _repeat_state(self, key: str) -> None:
        """game/tutor/repeat (§4.9, Rev 34): the line Repeat Help would say."""
        if self.link is not None:
            await self.link.state("game/tutor/repeat", key)

    async def _end_tutor(self) -> None:
        """Her task cancelled, and her voice stopped (§4.9)."""
        t, self._tutor_task = self._tutor_task, None
        if t is not None:
            t.cancel()
            await asyncio.gather(t, return_exceptions=True)
        self._intro = False
        self._lessons = []
        await self._waiting("")
        if self.tutor is not None:
            await self.tutor.stop()
            self.tutor = None
        if self.slots is not None:
            self.slots.timeless = False

    async def _diag_command(self, sub: str, payload: str) -> None:
        """game/diag/<target>/<test>/set (§7.5, Rev 25)."""
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

    def _circuits_in_calls(self) -> set[str]:
        """Every station and trunk a call in progress is using."""
        out: set[str] = set()
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

    # ---- start and stop (§3) --------------------------------------------

    async def start(self) -> None:
        if self.running:
            return                                  # ignored while running (§3)
        assert self.link is not None and self.slots is not None and self.log is not None
        self.running = True
        self.tallies.zero()
        self.next_number = 1
        self.pacing.connected = 0
        self.pacing.gap = self.cfg.gap              # the gap returns to configured (§3)
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
        await self._monitor("tap")                  # §6.4
        await self.link.state("game/run", "on")
        await self.link.state("game/error", "")
        await self._publish_tallies()
        self.pacing.next_at = None
        if self.pacing.pace == "tutor":
            # §4.9: she introduces the board first, and the first call waits
            # for Next Call, in every pacing (Rev 31).
            self.tutor = self._new_tutor()
            self.slots.timeless = True
            # §4.9, Rev 30: one scene of each kind first, picked from the
            # game's seed apart from the deck's own shuffle, so a replay
            # picks the same and a restart most likely does not.
            self._lessons = pick_lessons(self.gs.lessons, self.deck.seed)
            if self._lessons:
                await self._say("tutor lessons: " + ", ".join(self._lessons))
            self._intro = True
            self._tutor_task = asyncio.create_task(self._tutor_intro(), name="tutor-intro")
        elif self.pacing.automatic:
            await self._start_call()                # the first call at once (§3)
        await self._publish_pacing()

    async def stop(self, why: str) -> None:
        """Tear every call down at once. The tallies stay (§3)."""
        if self.diag is not None:
            await self.diag.end_all()               # every diagnostic (§7.5)
        if self.queued and self.link is not None:
            self.queued = ""                        # §4.8: Stop forgets it
            await self.link.state("game/queue", "")
        if not self.running:
            return
        assert self.link is not None and self.slots is not None
        self.running = False
        await self._end_tutor()                     # §4.9
        for t in list(self._flows.values()):
            t.cancel()
        for t in list(self._afters.values()):
            t.cancel()
        # Let the cancellations run their `finally` blocks before clearing.
        await asyncio.gather(*self._flows.values(), *self._afters.values(),
                             return_exceptions=True)
        self._flows.clear()
        self._afters.clear()
        self._pending_after.clear()
        await self.slots.clear_all()
        self.pacing.next_at = None
        await self._monitor("tap")                  # §6.4
        await self._say(f"game stopped: {why}" if why != "stop" else "game stopped")
        await self.session.end_game(why, self.tallies.started,
                                    self.tallies.success, self.tallies.fail)
        await self.link.state("game/run", "off")
        await self._publish_pacing()

    async def _monitor(self, source: str) -> None:
        """The game moving the loudspeaker (§6.4). That ends a monitor test."""
        if self.hw is None:
            return
        if self.diag is not None:
            await self.diag.monitor_moved()
        try:
            await self.hw.monitor_source(source)
        except Offline as e:
            log.warning("monitor source %s dropped: %s", source, e)

    # ---- dealing and running calls --------------------------------------

    def _held(self) -> list[Holding]:
        """What every call in progress and every waiting `after:` occupies."""
        out = list(self._pending_after.values())
        # A station under test is busy for dealing (§7.5).
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

    def _waiting_to_connect(self) -> bool:
        assert self.slots is not None
        return any(not c.connected for c in self.slots)

    def _scenario_on_board(self) -> bool:
        """Any call of a scenario in progress, or any of its scenes waiting (§4.10)."""
        assert self.slots is not None
        return (any(self.gs.in_scenario(c.scene) for c in self.slots)
                or any(self.gs.in_scenario(i) for i in self._pending_after))

    def _chosen_scenario_ready(self) -> bool:
        """A chosen scenario, outside tutor mode, and the board clear: it
        starts at once, without Next Call or the schedule (§4.10, Rev 41)."""
        q = self.gs.scenes.get(self.queued) if self.queued else None
        return (q is not None and q.after_handled is not None and self.tutor is None
                and self.slots is not None and not any(True for _ in self.slots)
                and not self._pending_after)

    def _scenario_allowed(self) -> bool:
        """A scenario is never dealt in tutor mode or listen (§4.10)."""
        return self.tutor is None and self.pacing.pace in ("manual", "auto")

    def _idle(self) -> bool:
        """Whether the automatic schedule may run now (§4.2).

        Auto: no call is waiting to be connected. Listen (Rev 16): no call in
        progress at all and no `after:` scene waiting to start, so the next
        call comes only once the story on the board has been heard out.
        Tutor mode (§4.9): as listen, and not while she is introducing the
        board or waiting for the cords out after a call.
        """
        assert self.slots is not None
        if self.tutor is not None:
            return (not any(True for _ in self.slots) and not self._pending_after
                    and self._tutor_task is None)
        if self.pacing.pace == "listen":
            return not any(True for _ in self.slots) and not self._pending_after
        # §4.10: a scenario on the board holds the schedule until it is over.
        return not self._waiting_to_connect() and not self._scenario_on_board()

    async def _reschedule(self) -> None:
        """Schedule the next call if the board is idle for the pace, else clear it."""
        if self._idle():
            self.pacing.schedule()
        else:
            self.pacing.next_at = None
        await self._publish_pacing()

    def _free_trunk(self) -> int | None:
        """A trunk fitted and in service (§6.5), idle, and not under test (§7.5)."""
        tested = self.diag.circuits() if self.diag is not None else set()
        for n in self.cfg.working_trunks():
            if f"trunk/{n}" in tested:
                continue
            if not self.b.on(f"trunk/{n}/seize") and not self.b.on(f"trunk/{n}/ring"):
                if not any(c.trunk == f"trunk/{n}" for c in (self.slots if self.slots is not None else ())):
                    return n
        return None

    async def _start_call(self, asked: bool = False, scene: SceneDef | None = None) -> None:
        """Deal a scene and run it, or say why not."""
        assert self.slots is not None and self.deck is not None
        if not self.running:
            return
        if self.tutor is not None and (any(True for _ in self.slots)
                                       or self._tutor_task is not None):
            why = ("one call at a time in tutor mode" if self._tutor_task is None
                   else "the tutor is waiting for the cords to come out")
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
            # §4.8: the chosen scene, if its lines and people are free.
            q = self.gs.scenes.get(self.queued)
            if q is not None and q.after_handled is not None and self.tutor is None:
                # §4.10, Rev 40: a chosen scenario, in any pacing but tutor,
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
                assert self.link is not None
                await self.link.state("game/queue", "")
                await self._say(f"chosen scene {q.id} dealt")
        if scene is None and self._scenario_allowed():
            # §4.10: a scenario, once enough calls have been handled.
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
            # §4.9, Rev 30: the next lesson, taken out of the deck as a
            # chosen scene is (§4.8).
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
            # deal() reshuffles when the deck runs out (§4.4). Record each new
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

        await self._waiting("")                     # §4.9, Rev 33
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
        # or ends (§4.2).
        self.pacing.waiting_to_connect()
        await self._publish_pacing()

        self._flows[slot] = asyncio.create_task(
            self._run_call(call, scene, trunk), name=f"call-{call.number}")

        # §4.4, Rev 39: a `mode: concurrent` follower is timed from this start.
        for follower in self.gs.followers(scene.id):
            if follower.concurrent:
                self._schedule_after(follower)

    async def _run_call(self, call: Call, scene: SceneDef, trunk: int | None) -> None:
        assert self.slots is not None and self.hw is not None
        cfg = self.cfg
        if self.tutor is not None:
            # §4.9: nobody fails for being slow while she teaches.
            cfg = dataclasses.replace(cfg, answer_timeout=NO_LIMIT,
                                      connect_timeout=NO_LIMIT)
        ctx = Ctx(board=self.b, hw=self.hw, cfg=cfg, slots=self.slots,
                  call=call, scene=scene,
                  say_event=lambda t, n=call.number: asyncio.create_task(
                      self._say(t, n)),
                  mark_connected=lambda: self._connected(call),
                  set_monitor=self._monitor,
                  tutor=self.tutor, jack_of=self.gs.jack_of)
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
        """The §4.3 milestone: the operator's routing work is done."""
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

        if self.tutor is not None and self.running:
            # §4.9: she sees the call down; nothing is dealt meanwhile.
            self._intro = False
            self._tutor_task = asyncio.create_task(
                self._tutor_hangup(call, scene), name=f"tutor-hangup-{call.number}")

        # §4.4: an `after:` scene follows only if this call was connected.
        # A concurrent one was scheduled when this call started.
        for follower in self.gs.followers(scene.id):
            if follower.concurrent:
                continue
            if call.connected:
                self._schedule_after(follower)
            else:
                await self._say(
                    f"dropped {follower.id}: {scene.id} was never connected")

        await self._reschedule()

    # ---- tutor mode (§4.9) ------------------------------------------------

    async def _waiting(self, what: str) -> None:
        """game/tutor/waiting (§4.9, Rev 33): she has finished and waits for
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
        """Her introduction, a part at a time (§4.9, Rev 31).

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
        """Her line at the end of a call, then every cord out and every
        switch back before the next is dealt."""
        t = self.tutor
        assert t is not None
        circuits = [c for c in (
            f"station/{scene.from_station}" if scene.from_station is not None else "",
            f"station/{scene.to_station}" if scene.to_station is not None else "",
            call.trunk) if c]
        trunks = [c for c in circuits if c.startswith("trunk/")]

        def clear(b: Board) -> bool:
            return (all(not b.on(f"{c}/op") and not b.get(f"{c}/peer") for c in circuits)
                    and all(not b.on(f"{c}/seize") for c in trunks))

        key = "hangup-one" if scene.shape == Shape.TO_OPERATOR else "hangup-pair"
        try:
            await t.say(key, until=clear)
            await self.b.wait_until(clear, NO_LIMIT)
            await t.hush()
            if not self.pacing.automatic:
                await t.say("ready-manual", hold=True)
                await self._waiting("next")     # until a call is dealt (Rev 33)
        except (TimeoutError, Offline) as e:
            log.info("tutor: call %d not cleared: %s", call.number, e or "timeout")
        finally:
            if self._tutor_task is asyncio.current_task():
                self._tutor_task = None
        if self.running:
            await self._reschedule()

    # ---- `after:` scenes (§4.4) -----------------------------------------

    def _schedule_after(self, scene: SceneDef) -> None:
        self._pending_after[scene.id] = Holding(frozenset(scene.needs),
                                                self.gs.needs_people(scene.id))
        delay = scene.delay
        if scene.delay_max > scene.delay:           # a range (§4.4, Rev 39)
            delay = self._delays.uniform(scene.delay, scene.delay_max)
        self._afters[scene.id] = asyncio.create_task(
            self._after_timer(scene, delay), name=f"after-{scene.id}")

    async def _after_timer(self, scene: SceneDef, delay: float) -> None:
        try:
            at = time.time() + delay
            secs = f"{delay:g}" if delay == scene.delay else f"{delay:.1f}"
            await self._say(f"{scene.id} follows in {secs}s, at "
                            f"{time.strftime('%H:%M:%S', time.localtime(at))}")
            await asyncio.sleep(delay)
            # Its lines may still be busy in another call: wait for them (§4.4).
            # A concurrent one waits for a free slot too, rather than being lost.
            while self.running:
                mine = self._pending_after.get(scene.id)
                others = [h for h in self._held() if h is not mine]
                lines, people = set(scene.needs), set(self.gs.needs_people(scene.id))
                tutor_busy = self.tutor is not None and (
                    self._tutor_task is not None or any(True for _ in self.slots or ()))
                full = (scene.concurrent and self.slots is not None
                        and self.slots.free_slot() is None)
                if not tutor_busy and not full and not any(
                        lines & h.lines or people & h.people for h in others):
                    break
                await asyncio.sleep(0.5)
            self._pending_after.pop(scene.id, None)
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
            raise

    # ---- the scheduler (§4.2) -------------------------------------------

    async def run_scheduler(self) -> None:
        """Start a call when the automatic gap has elapsed."""
        while True:
            try:
                if self.running and self.pacing.due():
                    await self._start_call()
                elif self.running and self._chosen_scenario_ready():
                    await self._start_call()        # §4.10, Rev 41: by itself
                await asyncio.sleep(0.25)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("scheduler")
                await asyncio.sleep(1)

    # ---- losing a client (§3) -------------------------------------------

    async def watch_clients(self) -> None:
        """Stop the game if the controller or the audio program goes away."""
        async for ch in self.b.watch():
            if ch.key in (LIVE_CONTROL, LIVE_AUDIO) and ch.new == "off":
                if self.running:
                    who = "controller" if ch.key == LIVE_CONTROL else "audio program"
                    await self.stop(f"{who} went offline")
