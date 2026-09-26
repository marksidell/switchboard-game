"""A whole game, against the simulated controller, audio program and operator.

Where test_flows.py proves one call, this proves the game around it: start and
stop (§3), the tallies (§5), page commands and their clamps (§8), the slots
filling and emptying (§6.1), an `after:` scene following a connected call and
being dropped after one that was not (§4.4), and the loudspeaker going to the
tap at start and stop (§6.4).

The real script.yml is used, so the scenes and the jack map are the ones the
game will actually run.
"""

import asyncio
import logging
import sys
import tempfile
from pathlib import Path

from sbgame.board import Board
from sbgame.config import Config
from sbgame.game import Game
from sbgame.pacing import Pacing
from sbgame.script_data import build
from sbgame.session import SessionLog
from tts.script import ScriptError, load

from test_sim import FakeLink, D

logging.basicConfig(level=logging.WARNING, stream=sys.stdout)

failures = 0


def check(ok: bool, what: str) -> None:
    global failures
    print(f"    {what:<58} {'ok' if ok else 'FAIL'}")
    if not ok:
        failures += 1


class StateLink(FakeLink):
    """FakeLink plus Link.state, recording what the page would see."""

    def __init__(self, b: Board) -> None:
        super().__init__(b)
        self.state_v: dict[str, str] = {}
        self.state_order: list[tuple[str, str]] = []

    async def state(self, key: str, value: str) -> None:
        self.state_v[key] = value
        self.state_order.append((key, value))


async def build_game(tmp: Path, **cfg_kw):
    b = Board()
    link = StateLink(b)
    cfg = Config(script="../script.yml", wav_dir="../wav",
                 session_db=str(tmp / "s.db"), **cfg_kw)
    gs = build(cfg.resolved("script"), cfg.resolved("wav_dir"))
    sess = SessionLog(cfg.resolved("session_db"))
    await sess.open()
    g = Game(b, gs, cfg, sess)
    await g.on_birth(link)          # as the link does on connect
    await b.set_broker(True)
    await b.update("ctl/status", "online")
    await b.update("ctl/audio_status", "online")
    await b.update("ctl/esp_heartbeat", "1")
    return b, link, g, sess


async def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        print("\n== birth publishes a stopped game and the whole board")
        b, link, g, sess = await build_game(tmp)
        check(link.state_v.get("game/run") == "off", "run is off at birth (§3)")
        check(link.state_v.get("game/call/1/scene") == "", "every slot is clear")
        labels = [k for k in link.state_v if k.startswith("board/station/") and k.endswith("/label")]
        check(len(labels) == 30, f"30 station jacks published, got {len(labels)}")
        check(link.state_v.get("board/station/1/label") == "Front Desk",
              f"jack 1 is {link.state_v.get('board/station/1/label')!r}")
        check(link.state_v.get("board/trunk/9/circuit") == "",
              "trunk jack 9 carries nothing")
        check(link.state_v.get("board/station/1/circuit") == "station/1",
              f"jack 1 carries {link.state_v.get('board/station/1/circuit')!r}")

        print("\n== jacks: a labelled jack with nothing cabled (§6.3)")
        real = Path("../script.yml").read_text(encoding="utf-8")
        spare = real.replace("\njacks:\n", '\njacks:\n    -   jack: 30\n        label: "Garage"\n', 1)
        (tmp / "spare.yml").write_text(spare, encoding="utf-8")
        gs = build(tmp / "spare.yml", "../wav")
        j30 = next(j for j in gs.jacks if j.kind == "station" and j.number == 30)
        check(j30.label == "Garage" and j30.circuit == "",
              f"jack 30 is labelled and uncabled: {j30.label!r} {j30.circuit!r}")
        for what, text in (
            ("a station on no jack",
             real.replace("        station: room822\n", "", 1)),
            ("a station on two jacks",
             spare.replace('label: "Garage"\n', 'label: "Garage"\n        station: lobby\n', 1)),
            ("a jack listed twice",
             spare.replace("jack: 30", "jack: 1", 1)),
            ("a jack with no label",
             spare.replace('        label: "Garage"\n', "", 1)),
            ("a jack naming no station",
             spare.replace('label: "Garage"\n', 'label: "Garage"\n        station: attic\n', 1)),
            ("the old switchboard: key on a station",
             real.replace("        number: 1\n", "        number: 1\n        switchboard: 1\n", 1)),
        ):
            (tmp / "bad.yml").write_text(text, encoding="utf-8")
            try:
                load(tmp / "bad.yml")
                check(False, f"rejects {what}")
            except ScriptError as e:
                check(True, f"rejects {what}")
                print(f"        {e.failures[0]}")

        print("\n== active: an inactive scene needs no wavs and is never dealt (§4.4)")
        new = real.replace("\nscenes:\n", "\nscenes:\n"
                           "    unrendered:\n"
                           "        active: false\n"
                           "        calling:\n"
                           "            line: lobby\n"
                           "            person: thornhill\n"
                           "        request:\n"
                           "            id: 1\n"
                           "            text: Operator, is anyone there?\n", 1)
        (tmp / "new.yml").write_text(new, encoding="utf-8")
        gs = build(tmp / "new.yml", "../wav")
        check("unrendered" in gs.script.scenes and "unrendered" not in gs.scenes,
              "loaded, but left out of the game's scenes")
        check("unrendered" not in gs.deck_scenes(), "and out of the deck")
        check(any(u.scene == "unrendered" for u in gs.script.utterances),
              "its utterances are still there for the TTS run")
        off = real.replace("    nbn-kaplan:\n        active: true\n",
                           "    nbn-kaplan:\n        active: false\n", 1)
        (tmp / "off.yml").write_text(off, encoding="utf-8")
        for what, text in (
            ("a scene with no active:",
             real.replace("    nbn-valet:\n        active: true\n", "    nbn-valet:\n", 1)),
            ("active: that is not true/false",
             real.replace("    nbn-valet:\n        active: true\n",
                          "    nbn-valet:\n        active: yes please\n", 1)),
            ("an active after: scene following an inactive one", off),
        ):
            (tmp / "bad.yml").write_text(text, encoding="utf-8")
            try:
                load(tmp / "bad.yml")
                check(False, f"rejects {what}")
            except ScriptError as e:
                check(True, f"rejects {what}")
                print(f"        {e.failures[0]}")
        off2 = off.replace("    nbn-trace:\n        active: true\n",
                           "    nbn-trace:\n        active: false\n", 1)
        (tmp / "off2.yml").write_text(off2, encoding="utf-8")
        gs = build(tmp / "off2.yml", "../wav")
        check("nbn-kaplan" not in gs.scenes and not gs.followers("nbn-kaplan"),
              "a scene and its after: both inactive: neither is played")

        print("\n== page commands: clamps and refusals (§8)")
        await g.on_command("gap", "700")
        check(link.state_v.get("game/gap") == "600", f"gap clamped to 600, got {link.state_v.get('game/gap')}")
        check("clamped" in link.state_v.get("game/error", ""), "and said so on game/error")
        await g.on_command("gap", "10")
        await g.on_command("floor", "99")
        check(link.state_v.get("game/floor") == "10", "floor is held to gap")
        await g.on_command("pace", "sideways")
        check("not manual or auto" in link.state_v.get("game/error", ""),
              "a bad pace is refused, not clamped")
        await g.on_command("run", "maybe")
        check("not on or off" in link.state_v.get("game/error", ""), "a bad run is refused")
        await g.on_command("next", "")
        check("no game" in link.state_v.get("game/error", ""),
              "next with no game running is refused")
        check(link.state_v.get("game/jitter") == "0", "jitter published at birth, 0")
        await g.on_command("jitter", "150")
        check(link.state_v.get("game/jitter") == "100", "jitter clamped to 100")
        await g.on_command("jitter", "30")
        check(link.state_v.get("game/jitter") == "30", "jitter 30 applied and echoed")
        await sess.close()

        print("\n== jitter: the spread of the automatic wait (§4.3)")
        p = Pacing(pace="auto", gap=20, ramp=0, floor=5, jitter=0)
        p.seed(1)
        check({p.wait() for _ in range(50)} == {20.0}, "jitter 0 is the fixed wait")
        p.jitter = 50
        ws = [p.wait() for _ in range(4000)]
        check(min(ws) >= 10 and max(ws) <= 30, f"50% of 20 stays in 10-30: {min(ws):.1f}-{max(ws):.1f}")
        mean = sum(ws) / len(ws)
        check(abs(mean - 20) < 0.5, f"and its mean is still gap_now: {mean:.2f}")
        p.jitter = 100
        check(min(p.wait() for _ in range(4000)) >= 0, "100% never goes below zero")
        p.gap, p.ramp, p.floor, p.jitter, p.connected = 30, 5, 8, 50, 10
        ws = [p.wait() for _ in range(4000)]
        check(min(ws) >= 4 and max(ws) <= 12 and min(ws) < 8,
              f"the floor bounds the centre, not the draw: {min(ws):.1f}-{max(ws):.1f}")
        a, b = Pacing(jitter=40), Pacing(jitter=40)
        a.seed(7); b.seed(7)
        check([a.wait() for _ in range(20)] == [b.wait() for _ in range(20)],
              "the same seed draws the same waits (replay)")
        a.pace = "auto"
        at = a.schedule(1000.0)
        check(at is not None and 12 <= at - 1000.0 <= 28, f"schedule() uses the draw: {at - 1000.0:.1f}s")

        print("\n== start, one manual call, stop")
        b, link, g, sess = await build_game(tmp, pace="manual")
        await g.start()
        check(link.state_v.get("game/run") == "on", "run is on")
        check(link.state_v.get("game/started") == "0", "started is 0 before any call")
        check(("audio/monitor/source/set", "tap") in link.sent,
              "the loudspeaker went to the tap at start (§6.4)")
        sched = asyncio.create_task(g.run_scheduler())

        await g.on_command("next", "")
        await asyncio.sleep(D * 2)
        check(link.state_v.get("game/started") == "1", "started is 1")
        occupied = [c for c in g.slots]
        check(len(occupied) == 1, f"one slot occupied, got {len(occupied)}")
        call = occupied[0]
        print(f"      dealt {call.scene}: {call.from_line} -> {call.to_line or 'operator'}")
        check(link.state_v.get(f"game/call/{call.slot}/stage") == "signalling",
              "it is signalling, waiting for the operator")
        check(link.state_v.get("game/next_at") == "",
              "nothing scheduled while a call waits to connect (§4.2)")

        await g.stop("stop")
        check(link.state_v.get("game/run") == "off", "stopped")
        check(link.state_v.get("game/call/1/scene") == "", "slots cleared")
        check(link.state_v.get("game/started") == "1", "the tallies stay after Stop (§3)")
        check(link.sent.count(("audio/monitor/source/set", "tap")) >= 2,
              "and the loudspeaker went back to the tap")
        sched.cancel()
        await sess.close()

        print("\n== the deck deals every scene before repeating, across a game")
        b, link, g, sess = await build_game(tmp, pace="manual")
        await g.start()
        dealt = []
        for _ in range(11):
            sc, why = g.deck.deal([])
            if sc:
                dealt.append(sc.id)
        check(len(set(dealt)) == 11, f"11 distinct scenes dealt, got {len(set(dealt))}")
        await g.stop("stop")
        await sess.close()

        print("\n== an after: scene is dropped when its parent never connected (§4.4)")
        b, link, g, sess = await build_game(tmp, pace="manual")
        await g.start()
        parent = g.gs.scenes["nbn-kaplan"]
        from sbgame.calls import Call as C
        from sbgame.flows import Outcome
        call = C(slot=1, number=1, scene=parent.id, from_line=parent.from_line,
                 to_line=parent.to_line)
        await g.slots.open(call)
        call.connected = False
        await g._finish_call(call, parent, Outcome(False, "no answer"))
        log = link.state_v.get("game/log", "")
        check("dropped nbn-trace" in log, f"nbn-trace dropped; log head: {log.splitlines()[0]!r}")
        check(g.tallies.fail == 1, "counted as a failure")
        await g.stop("stop")
        await sess.close()

        print("\n== and scheduled when it did connect")
        b, link, g, sess = await build_game(tmp, pace="manual")
        await g.start()
        call = C(slot=1, number=1, scene=parent.id, from_line=parent.from_line,
                 to_line=parent.to_line)
        await g.slots.open(call)
        call.connected = True
        await g._finish_call(call, parent, Outcome(True))
        await asyncio.sleep(D)      # the after: timer logs its own line from its task
        check("nbn-trace follows in 2s" in link.state_v.get("game/log", ""),
              "nbn-trace scheduled with its delay")
        check("nbn-trace" in g._pending_after, "and its lines are held meanwhile")
        check(g.tallies.success == 1, "counted as a success")
        await g.stop("stop")
        check(not g._afters, "Stop dropped the waiting after: scene")
        await sess.close()

        print("\n== losing the controller stops the game (§3)")
        b, link, g, sess = await build_game(tmp, pace="manual")
        watcher = asyncio.create_task(g.watch_clients())
        await asyncio.sleep(0)
        await g.start()
        await b.update("ctl/status", "offline")
        await asyncio.sleep(D * 3)
        check(link.state_v.get("game/run") == "off", "the game stopped")
        check("controller went offline" in link.state_v.get("game/log", ""),
              "and said why")
        watcher.cancel()
        await sess.close()

        print("\n== the session record")
        b, link, g, sess = await build_game(tmp, pace="manual")
        await g.start()
        await g.stop("stop")
        await sess.close()
        import sqlite3
        db = sqlite3.connect(tmp / "s.db")
        n_sessions = db.execute("SELECT count(*) FROM sessions").fetchone()[0]
        seeded = db.execute("SELECT count(*) FROM sessions WHERE seed IS NOT NULL").fetchone()[0]
        decks = db.execute("SELECT count(*) FROM decks").fetchone()[0]
        check(n_sessions >= 1, f"{n_sessions} sessions recorded")
        check(seeded == n_sessions, "every one has its seed, for the replay (§4.4)")
        check(decks >= 1, f"{decks} deck orders recorded")
        db.close()

        print("\n== the simulator hands out each trunk once (no broker needed)")
        from sbgame.config import Config as C
        from sbgame.simulate import Sim
        gs = build(C().resolved("script"), "../wav")
        sim = Sim(C(), gs, operator=True, delay=0)
        # Two overlapping calls used to pick the same trunk, because `seize`
        # is not true until the echo returns. Chosen synchronously now.
        picks = [sim._free_trunk_now() for _ in range(8)]
        check(len(set(picks)) == 8 and None not in picks,
              f"eight distinct trunks: {picks}")
        check(sim._free_trunk_now() is None, "a ninth request gets nothing")
        sim.taken.discard(3)
        check(sim._free_trunk_now() == 3, "a released trunk comes back")

    print("\n" + ("FAILURES" if failures else "the game passed"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
