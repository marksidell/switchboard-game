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
  an after timer one per waiting `after:` scene, cancelled by Stop (§4.4).

The command handler is deliberately quick (handover rule 9): it runs inside the
link's dispatch loop, and no hardware message is processed until it returns. It
validates, publishes the echo, starts or cancels tasks, and returns.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from .board import Board, LIVE_AUDIO, LIVE_CONTROL, Offline
from .calls import Call, N_SLOTS, Reason, Slots, Stage, Tallies
from .config import Config
from .deck import Deck, Holding
from .flows import Ctx, FLOWS, Outcome, outside_to_station
from .gamelog import GameLog
from .link import Hw, Link
from .script_data import GameScript, SceneDef, Shape
from .session import SessionLog

log = logging.getLogger("game")

N_TRUNKS = 8


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
                             jitter=cfg.jitter)

        self._flows: dict[int, asyncio.Task] = {}       # slot -> task
        self._afters: dict[str, asyncio.Task] = {}      # scene id -> timer task
        self._pending_after: dict[str, Holding] = {}    # what a waiting after holds
        self._scheduler: asyncio.Task | None = None
        self._decks_recorded = 0        # how many of deck.orders are in SQLite

    # ---- wiring ----------------------------------------------------------

    def attach(self, link: Link) -> None:
        self.link = link
        self.hw = Hw(link)
        self.slots = Slots(link.state)
        self.log = GameLog(link.state)

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

    async def _publish_pacing(self) -> None:
        assert self.link is not None
        p = self.pacing
        await self.link.state("game/pace", p.pace)
        await self.link.state("game/gap", f"{p.gap:g}")
        await self.link.state("game/ramp", f"{p.ramp:g}")
        await self.link.state("game/floor", f"{p.floor:g}")
        await self.link.state("game/jitter", f"{p.jitter:g}")
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

            if name == "next":
                if not self.running:
                    await self._error("next: no game is running")
                    return
                await self._start_call(asked=True)
                return

            if name == "pace":
                if payload not in ("manual", "auto"):
                    await self._error(f"pace: {payload!r} is not manual or auto")
                    return
                self.pacing.pace = payload
                await self._say(f"page: pace {payload}")
                if payload == "auto" and self.running and not self._waiting_to_connect():
                    self.pacing.schedule()
                elif payload == "manual":
                    self.pacing.next_at = None
                await self._publish_pacing()
                return

            if name in ("gap", "ramp", "floor", "jitter"):
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
        await self.session.start_game(self.deck.seed, self.pacing.pace,
                                      self.pacing.gap, self.pacing.ramp,
                                      self.pacing.floor, self.pacing.jitter)
        self.session.deck(1, self.deck.orders[0])
        self._decks_recorded = 1
        await self.log.clear()
        await self._say("game started")
        await self._monitor("tap")                  # §6.4
        await self.link.state("game/run", "on")
        await self.link.state("game/error", "")
        await self._publish_tallies()
        if self.pacing.pace == "auto":
            await self._start_call()                # the first call at once (§3)
        else:
            self.pacing.next_at = None
        await self._publish_pacing()

    async def stop(self, why: str) -> None:
        """Tear every call down at once. The tallies stay (§3)."""
        if not self.running:
            return
        assert self.link is not None and self.slots is not None
        self.running = False
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
        if self.hw is None:
            return
        try:
            await self.hw.monitor_source(source)
        except Offline as e:
            log.warning("monitor source %s dropped: %s", source, e)

    # ---- dealing and running calls --------------------------------------

    def _held(self) -> list[Holding]:
        """What every call in progress and every waiting `after:` occupies."""
        out = list(self._pending_after.values())
        assert self.slots is not None
        for call in self.slots:
            sc = self.gs.scenes[call.scene]
            people = frozenset(p for p in self.gs.people[sc.id] if p)
            out.append(Holding(frozenset(sc.lines), people))
        return out

    def _waiting_to_connect(self) -> bool:
        assert self.slots is not None
        return any(not c.connected for c in self.slots)

    def _free_trunk(self) -> int | None:
        for n in range(1, N_TRUNKS + 1):
            if not self.b.on(f"trunk/{n}/seize") and not self.b.on(f"trunk/{n}/ring"):
                if not any(c.trunk == f"trunk/{n}" for c in (self.slots if self.slots is not None else ())):
                    return n
        return None

    async def _start_call(self, asked: bool = False, scene: SceneDef | None = None) -> None:
        """Deal a scene and run it, or say why not."""
        assert self.slots is not None and self.deck is not None
        if not self.running:
            return
        slot = self.slots.free_slot()
        if slot is None:
            why = "all eight slots are busy"
            await self._say(f"no call: {why}")
            if asked:
                await self._error(why)
            return

        if scene is None:
            scene, why = self.deck.deal(self._held())
            if scene is None:
                await self._say(f"no call: {why}")
                if asked:
                    await self._error(why)
                if self.pacing.pace == "auto":
                    self.pacing.schedule()
                    await self._publish_pacing()
                return
            # deal() reshuffles when the deck runs out (§4.4). Record each new
            # order for the replay, and log it, which the specification asks for.
            while self._decks_recorded < len(self.deck.orders):
                self._decks_recorded += 1
                self.session.deck(self._decks_recorded,
                                  self.deck.orders[self._decks_recorded - 1])
                if self._decks_recorded > 1:
                    await self._say("deck reshuffled")

        trunk = None
        if scene.shape == Shape.OUTSIDE_TO_STATION:
            trunk = self._free_trunk()
            if trunk is None:
                await self._say(f"no call: no free trunk for {scene.id}")
                if asked:
                    await self._error("no free trunk")
                return

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

    async def _run_call(self, call: Call, scene: SceneDef, trunk: int | None) -> None:
        assert self.slots is not None and self.hw is not None
        ctx = Ctx(board=self.b, hw=self.hw, cfg=self.cfg, slots=self.slots,
                  call=call, scene=scene,
                  say_event=lambda t, n=call.number: asyncio.create_task(
                      self._say(t, n)),
                  mark_connected=lambda: self._connected(call),
                  set_monitor=self._monitor)
        outcome = Outcome(False, "cancelled")
        try:
            if scene.shape == Shape.OUTSIDE_TO_STATION:
                outcome = await outside_to_station(ctx, trunk or 1)
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
        if not self._waiting_to_connect():
            self.pacing.schedule()
        await self._publish_pacing()

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

        # §4.4: an `after:` scene follows only if this call was connected.
        for follower in self.gs.followers(scene.id):
            if call.connected:
                self._schedule_after(follower)
            else:
                await self._say(
                    f"dropped {follower.id}: {scene.id} was never connected")

        if not self._waiting_to_connect():
            self.pacing.schedule()
        await self._publish_pacing()

    # ---- `after:` scenes (§4.4) -----------------------------------------

    def _schedule_after(self, scene: SceneDef) -> None:
        people = frozenset(p for p in self.gs.people[scene.id] if p)
        self._pending_after[scene.id] = Holding(frozenset(scene.lines), people)
        self._afters[scene.id] = asyncio.create_task(
            self._after_timer(scene), name=f"after-{scene.id}")

    async def _after_timer(self, scene: SceneDef) -> None:
        try:
            at = time.time() + scene.delay
            await self._say(f"{scene.id} follows in {scene.delay:g}s, at "
                            f"{time.strftime('%H:%M:%S', time.localtime(at))}")
            await asyncio.sleep(scene.delay)
            # Its lines may still be busy in another call: wait for them (§4.4).
            while self.running:
                mine = self._pending_after.get(scene.id)
                others = [h for h in self._held() if h is not mine]
                lines, people = set(scene.lines), {p for p in self.gs.people[scene.id] if p}
                if not any(lines & h.lines or people & h.people for h in others):
                    break
                await asyncio.sleep(0.5)
            self._pending_after.pop(scene.id, None)
            self._afters.pop(scene.id, None)
            if self.running:
                await self._start_call(scene=scene)
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
