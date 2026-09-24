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
from sbgame.script_data import build
from sbgame.session import SessionLog

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
    cfg = Config(script="~/s/game/script.yml", wav_dir="../wav",
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
        await sess.close()

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

    print("\n" + ("FAILURES" if failures else "the game passed"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
