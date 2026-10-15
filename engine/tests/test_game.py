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
import re
import logging
import sys
import tempfile
from pathlib import Path

from sbgame.board import Board
from sbgame.config import Config
from sbgame.game import Game
from sbgame.pacing import Pacing
from sbgame.script_data import build, fit, needs_trunk
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
        check(link.state_v.get("board/station/21/label") == "Front Desk",
              f"jack 21 is {link.state_v.get('board/station/21/label')!r}")
        check(link.state_v.get("board/trunk/9/circuit") == "",
              "trunk jack 9 carries nothing")
        check(link.state_v.get("board/station/21/circuit") == "station/1",
              f"jack 21 carries {link.state_v.get('board/station/21/circuit')!r}")

        print("\n== jacks: a labelled jack with nothing cabled (§6.3)")
        real = Path("../script.yml").read_text(encoding="utf-8")
        # Jack 10 is taken out and put back first, labelled and uncabled.
        spare = re.sub(r"\n    -   jack: 10\n(        \w+:.*\n)*", "\n", real, count=1)
        spare = spare.replace("\njacks:\n", '\njacks:\n    -   jack: 10\n        label: "Garage"\n', 1)
        (tmp / "spare.yml").write_text(spare, encoding="utf-8")
        gs = build(tmp / "spare.yml", "../wav")
        j10 = next(j for j in gs.jacks if j.kind == "station" and j.number == 10)
        check(j10.label == "Garage" and j10.circuit == "",
              f"jack 10 is labelled and uncabled: {j10.label!r} {j10.circuit!r}")
        for what, text in (
            ("a station on no jack",
             real.replace("        station: room404\n", "", 1)),
            ("a station on two jacks",
             spare.replace('label: "Garage"\n', 'label: "Garage"\n        station: lobby\n', 1)),
            ("a jack listed twice",
             spare.replace("jack: 10", "jack: 21", 1)),
            ("a jack with no label",
             spare.replace('        label: "Garage"\n', "", 1)),
            ("a jack with an empty guest:",
             spare.replace('label: "Garage"\n', 'label: "Garage"\n        guest: ""\n', 1)),
            ("a jack naming no station",
             spare.replace('label: "Garage"\n', 'label: "Garage"\n        station: attic\n', 1)),
            ("wait: in a call to the operator",
             real.replace("                caller: Thank you. Room 404. Good night.\n",
                          "                caller: Thank you. Room 404. Good night.\n"
                          "                wait: true\n", 1)),
            ("a line whose person: is not in the cast",
             real.replace("                called: Valet service.\n",
                          "                called: Valet service.\n"
                          "                person: nobody\n", 1)),
            ("ringback: on a station's line",
             real.replace("                caller: Yes, fast.\n",
                          "                caller: Yes, fast.\n"
                          "                ringback: 5\n", 1)),
            ("ringback: in a call between stations",
             real.replace("                called: Valet service.\n",
                          "                called: Valet service.\n"
                          "                ringback: 5\n", 1)),
            ("a pause: that is not a number of seconds",
             real.replace("                called: Valet service.\n",
                          "                called: Valet service.\n"
                          "                pause: a while\n", 1)),
            ("the old switchboard: key on a station",
             real.replace("        number: 1\n", "        number: 1\n        switchboard: 1\n", 1)),
            ("operator: where the game does not wait for her (§4.7)",
             real.replace("                caller: Yes, fast.\n",
                          "                caller: Yes, fast.\n"
                          "                operator: busy\n", 1)),
            ("operator: naming no line under operator_lines:",
             real.replace("            operator: internal-greeting\n",
                          "            operator: good-morning\n", 1)),
            ("an inline operator: line taking an id the scene uses",
             real.replace("                    id: 5\n                    text: Three cents, sir.\n",
                          "                    id: 2\n                    text: Three cents, sir.\n", 1)),
            ("closing: in a call the operator is off the line at the end of",
             real.replace("    nbn-valet:\n        active: true\n",
                          "    nbn-valet:\n        active: true\n        closing: busy\n", 1)),
            ("operator_lines: with no hotel_operator in the cast",
             real.replace("    hotel_operator:\n", "    hotel_operator_gone:\n", 1)),
        ):
            (tmp / "bad.yml").write_text(text, encoding="utf-8")
            try:
                load(tmp / "bad.yml")
                check(False, f"rejects {what}")
            except ScriptError as e:
                check(True, f"rejects {what}")
                print(f"        {e.failures[0]}")

        gs = build("../script.yml", "../wav")
        check(all(u.by != "operator" for sc in gs.scenes.values()
                  for u in (sc.request, *sc.conversation)),
              "the operator's own lines are never played (§4.7)")
        check(gs.script.by_name()[gs.script.scene_lines("dobbs-stamp")[1].operator].text
              == "Three cents, sir.", "an inline operator: line is found by name")
        check(gs.script.by_name()[gs.script.closings["nbn-trace"]].text.startswith("That call was from the lobby"),
              "a closing: line is found by its scene")

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
            ("a scene named in two after:s",
             real.replace("\nscenes:\n", "\nscenes:\n"
                          "    twin:\n"
                          "        active: false\n"
                          "        after: nbn-kaplan\n"
                          "        calling:\n"
                          "            line: room403\n"
                          "            person: thornhill\n"
                          "        request:\n"
                          "            id: 1\n"
                          "            text: Operator, who was that?\n", 1)),
            ("mode: that is not concurrent",
             real.replace("    nbn-trace:\n        active: true\n",
                          "    nbn-trace:\n        active: true\n        mode: soon\n", 1)),
            ("mode: concurrent on a scene with no after:",
             real.replace("    nbn-valet:\n        active: true\n",
                          "    nbn-valet:\n        active: true\n        mode: concurrent\n", 1)),
            ("a delay: range upside down",
             real.replace("    nbn-trace:\n        active: true\n",
                          "    nbn-trace:\n        active: true\n        delay: [5, 2]\n", 1)
                 .replace("        delay: 2\n", "", 1)),
            ("after_handled: on an after: scene",
             real.replace("    nbn-trace:\n        active: true\n",
                          "    nbn-trace:\n        active: true\n        after_handled: 3\n", 1)),
            ("if_busy: on a call to the operator",
             real.replace("    crane-wakeup:\n        active: true\n",
                          "    crane-wakeup:\n        active: true\n"
                          "        if_busy:\n            -   id: 9\n                caller: Oh.\n", 1)),
            ("an if_busy: line said by the called party",
             real.replace("    martha-squirrel:\n        active: true\n",
                          "    martha-squirrel:\n        active: true\n"
                          "        if_busy:\n            -   id: 9\n                called: Oh.\n", 1)),
            ("a loop of after:s",
             real.replace("    nbn-kaplan:\n        active: true\n",
                          "    nbn-kaplan:\n        active: true\n        after: nbn-trace\n", 1)),
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

        chain = real.replace("\nscenes:\n", "\nscenes:\n"
                             "    third:\n"
                             "        active: false\n"
                             "        after: nbn-trace\n"
                             "        calling:\n"
                             "            line: room403\n"
                             "            person: thornhill\n"
                             "        request:\n"
                             "            id: 1\n"
                             "            text: Operator, get me the police.\n", 1)
        (tmp / "chain.yml").write_text(chain, encoding="utf-8")
        try:
            load(tmp / "chain.yml")
            check(True, "accepts a chain of three after:s (Rev 19)")
        except ScriptError as e:
            check(False, f"accepts a chain of three after:s (Rev 19): {e.failures}")

        busy = real.replace("    martha-squirrel:\n        active: true\n",
                            "    martha-squirrel:\n        active: true\n"
                            "        if_busy:\n            -   id: 9\n                caller: Busy? Grr.\n"
                            "                operator: busy\n", 1)
        (tmp / "busy.yml").write_text(busy, encoding="utf-8")
        try:
            sc = load(tmp / "busy.yml")
            names = [u.name for u in sc.scene_lines("martha-squirrel")]
            ib = sc.busy_lines("martha-squirrel")
            check("martha-squirrel.9" not in names and [u.name for u in ib] == ["martha-squirrel.9"]
                  and ib[0].after_operator and ib[0].operator == "operator.4",
                  "if_busy: lines kept out of the conversation, waiting on her (§4.11)")
        except ScriptError as e:
            check(False, f"accepts if_busy: {e.failures}")

        print("\n== page commands: clamps and refusals (§8)")
        await g.on_command("gap", "700")
        check(link.state_v.get("game/gap") == "600", f"gap clamped to 600, got {link.state_v.get('game/gap')}")
        check("clamped" in link.state_v.get("game/error", ""), "and said so on game/error")
        await g.on_command("gap", "10")
        await g.on_command("floor", "99")
        check(link.state_v.get("game/floor") == "10", "floor is held to gap")
        await g.on_command("pace", "sideways")
        check("not tutor, manual, auto or listen" in link.state_v.get("game/error", ""),
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

        print("\n== the circuits fitted (§6.5, Rev 25)")
        full = build("../script.yml", "../wav")
        small, left = fit(full, stations=5, trunks=0)
        check(all(all(n is None or n <= 5 for n in (s.from_station, s.to_station))
                  for s in small.scenes.values()), "no scene keeps a station above 5")
        check(not any(needs_trunk(s) for s in small.scenes.values()),
              "no scene keeps a trunk when none is fitted")
        check(all(not s.after or s.after in small.scenes for s in small.scenes.values()),
              "no after: scene is left whose scene was left out")
        check(len(small.scenes) + len(left) == len(full.scenes),
              f"every scene is kept or named: {len(small.scenes)} + {len(left)}")
        same, none = fit(full)
        check(len(same.scenes) == len(full.scenes) and not none, "the defaults keep everything")
        b, link, g, sess = await build_game(tmp, stations=5, trunks=2)
        check(link.state_v.get("game/stations") == "5" and link.state_v.get("game/trunks") == "2",
              "stations and trunks published at birth")
        check(g._free_trunk() in (1, 2), "a trunk is picked from the fitted ones")

        print("\n== trunks out of service (§6.5, Rev 36)")
        oos = {"trunks": {"6": "jack 6's lamp does not latch", "8": "lamp out"}}
        cfg = Config(out_of_service=oos)
        cfg.check()
        check(cfg.working_trunks() == [1, 2, 3, 4, 5, 7], f"working trunks: {cfg.working_trunks()}")
        for bad_oos in ({"trunks": {"9": "x"}}, {"trunks": {"6": ""}}, {"stations": {"1": "x"}}):
            try:
                Config(out_of_service=bad_oos).check()
                check(False, f"refused {bad_oos}")
            except ValueError:
                check(True, f"refused {bad_oos}")
        b2, _, g2, sess2 = await build_game(tmp / "oos" if (tmp / "oos").mkdir() is None else tmp,
                                            out_of_service=oos)
        for n in (1, 2, 3, 4, 5, 7):
            await b2.update(f"trunk/{n}/seize", "on")
        check(g2._free_trunk() is None, "with every working trunk busy, 6 and 8 are not offered")
        await b2.update("trunk/7/seize", "off")
        check(g2._free_trunk() == 7, "and a working one is offered when it comes free")
        await sess2.close()

        print("\n== diagnostics (§7.5, Rev 25)")
        check(link.state_v.get("game/diag/station/3/tone") == "off"
              and link.state_v.get("game/diag/tap/voice") == "off", "every test off at birth")
        link.sent.clear()
        await g.on_command("diag/station/3/hook", "on")
        check(("station/3/hook/set", "on") in link.sent, "hook takes the station off-hook")
        check(link.state_v.get("game/diag/station/3/hook") == "on", "and echoes on")
        await g.on_command("diag/station/3/tone", "on")
        check(("audio/test/3/set", "on") in link.sent, "tone is the test tone on output 3")
        await g.on_command("diag/station/3/voice", "on")
        await asyncio.sleep(D)
        check(link.state_v.get("game/diag/station/3/tone") == "off"
              and ("audio/test/3/set", "off") in link.sent, "voice ends tone (§7.5)")
        check(any(k == "station/3/play/set" and v != "stop" for k, v in link.sent),
              "voice plays a file on the station")
        await g.on_command("diag/trunk/2/tone", "on")
        check(("audio/test/26/set", "on") in link.sent, "a trunk's tone is on output 24 + n")
        await g.on_command("diag/tap/voice", "on")
        await asyncio.sleep(D)
        check(any(k == "audio/tap/play/set" and v != "stop" for k, v in link.sent),
              "voice on the tap plays through audio/tap/play/set")
        await g.on_command("diag/station/4/monitor", "on")
        check(("audio/monitor/source/set", "station/4") in link.sent, "monitor moves the loudspeaker")
        await g.on_command("diag/tap/monitor", "on")
        check(link.state_v.get("game/diag/station/4/monitor") == "off", "one monitor test at a time")
        link.sent.clear()
        await g.on_command("diag/tap/monitor", "off")
        check(("audio/monitor/source/set", "tap") in link.sent, "ending it returns to the tap")
        await g.on_command("diag/station/5/monitor", "on")
        await g._monitor("station/1")                   # the game moves it: an answer
        check(link.state_v.get("game/diag/station/5/monitor") == "off",
              "the game moving the loudspeaker ends a monitor test (§6.4)")
        await g.on_command("diag/station/9/tone", "on")
        check("not a circuit fitted" in link.state_v.get("game/error", ""),
              "a station beyond the fitted is refused")
        await g.on_command("diag/station/3/ring", "on")
        check("no 'ring' test" in link.state_v.get("game/error", ""), "ring is a trunk's test")
        await g.on_command("diag/trunk/1/ring", "on")
        check(("trunk/1/ring/set", "on") in link.sent, "ring rings the trunk")
        check(g._free_trunk() is None,
              "a trunk under test is not picked for a call: 1 rings, 2 has its tone")
        await b.update("trunk/1/seize", "on")
        await asyncio.sleep(0.6)
        check(link.state_v.get("game/diag/trunk/1/ring") == "off"
              and ("trunk/1/ring/set", "off") in link.sent, "a seizure ends the ring test")
        await b.update("trunk/1/seize", "off")
        held = g._held()
        check(any(h.lines for h in held), "a station under test is held out of dealing")
        link.sent.clear()
        await g.on_command("run", "off")                # Stop with no game running
        check(not g.diag.on, "Stop ends every test")
        check(("station/3/hook/set", "off") in link.sent and ("audio/tap/play/set", "stop") in link.sent,
              "and puts the hardware back")

        print("\n== a chosen next scene (§4.8, Rev 25)")
        scenes = link.state_v.get("game/scenes", "").split("\n")
        check(len(scenes) == len(g.gs.deck_scenes()) and scenes[0], "game/scenes lists the deck's scenes")
        await g.on_command("queue", "no-such-scene")
        check("not a scene" in link.state_v.get("game/error", ""), "an unknown scene is refused")
        want = scenes[-1]
        await g.on_command("queue", want)
        check(link.state_v.get("game/queue") == want, "the choice is echoed")
        await g.start()
        await g.on_command("next", "")
        await asyncio.sleep(D * 2)
        dealt = [c.scene for c in g.slots]
        check(dealt == [want], f"the next call is the chosen scene: {dealt}")
        check(link.state_v.get("game/queue") == "", "and the choice is spent")
        await g.on_command("queue", scenes[0])
        await g.stop("stop")
        check(link.state_v.get("game/queue") == "", "Stop forgets a choice")
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
        n = len(g.gs.deck_scenes())
        dealt = []
        for _ in range(n):
            sc, why = g.deck.deal([])
            if sc:
                dealt.append(sc.id)
        check(len(set(dealt)) == n, f"{n} distinct scenes dealt, got {len(set(dealt))}")
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

        print("\n== a scenario: dealt after n handled, followers start together (§4.10, Rev 39)")
        import dataclasses as dc
        b, link, g, sess = await build_game(tmp, pace="manual")
        ops = [sc for sc in g.gs.scenes.values()
               if sc.shape == "to_operator" and sc.from_station is not None and not sc.after]
        picked, rooms = [], set()
        for sc in ops:
            if sc.from_line not in rooms and not (set(g.gs.people[sc.id]) - {""}) & {
                    p for q in picked for p in g.gs.people[q.id]}:
                picked.append(sc)
                rooms.add(sc.from_line)
            if len(picked) == 3:
                break
        chain = [dc.replace(picked[0], id="p0", after_handled=2)]
        for i, sc in enumerate(picked[1:], 1):
            chain.append(dc.replace(sc, id=f"p{i}", after=f"p{i-1}", concurrent=True,
                                    delay=D, delay_max=D * 3))
        for sc, orig in zip(chain, picked):
            g.gs.scenes[sc.id] = sc
            g.gs.people[sc.id] = g.gs.people[orig.id]
        for orig in picked:                  # so the deck never holds their people
            del g.gs.scenes[orig.id]
        check("p0" not in g.gs.deck_scenes() and "p0" in g.gs.choosable(),
              "not in the deck, but in game/scenes")
        check(g.gs.in_scenario("p2") and not g.gs.in_scenario(ops[-1].id),
              "its followers are part of it")
        await g.start()
        await g._start_call()
        first = next(iter(g.slots)).scene
        check(first != "p0", f"not dealt before 2 handled: {first}")
        await g.stop("stop")            # that call may share a room or person with the chain
        await g.start()
        g.tallies.success = 2
        await g._start_call()
        check(any(c.scene == "p0" for c in g.slots), "dealt once 2 calls are handled")
        await asyncio.sleep(D * 10)
        on = {c.scene for c in g.slots}
        check({"p1", "p2"} <= on, f"followers on the board though p0 never connected: {sorted(on)}")
        g.pacing.pace = "auto"
        for c in g.slots:
            c.connected = True
        check(not g._idle(), "the automatic schedule waits while it is on the board")
        g.pacing.pace = "manual"
        await g._start_call()
        check(sum(c.scene == "p0" for c in g.slots) == 1, "dealt once a game")
        await g.stop("stop")
        await g.start()
        g.pacing.pace = "listen"
        g.tallies.success = 5
        await g._start_call()
        check(not any(c.scene == "p0" for c in g.slots), "never dealt in listen")
        await g.stop("stop")

        print("\n== a scenario chosen from the page (§4.10, Rev 40)")
        await g.start()
        g.pacing.pace = "manual"
        await g._start_call()                       # an ordinary call on the board
        before = g.tallies.started
        await g.on_command("queue", "p0")
        await g._start_call(asked=True)
        check(g.tallies.started == before and not any(c.scene == "p0" for c in g.slots),
              "waits for the board to clear, and nothing else is dealt")
        check(link.state_v.get("game/error") == "waiting for the board to clear",
              "Next Call refused, saying why")
        await g.stop("stop")
        sched = asyncio.create_task(g.run_scheduler())
        g.pacing.pace = "listen"
        await g.on_command("queue", "p0")           # chosen before Start
        await g.start()
        check(any(c.scene == "p0" for c in g.slots), "a choice made before Start starts the game")
        await g.stop("stop")
        g.pacing.pace = "manual"
        await g.start()
        await g.on_command("queue", "p0")
        await asyncio.sleep(0.6)
        check(any(c.scene == "p0" for c in g.slots),
              "starts by itself on a clear board, without Next Call (Rev 41)")
        check("p0" not in g._scenarios_dealt, "and its once-a-game play is not used up")
        await g.stop("stop")
        sched.cancel()
        await sess.close()

        print("\n== a full board: a concurrent follower waits for a slot")
        b, link, g, sess = await build_game(tmp, pace="manual")
        for sc, orig in zip(chain, picked):
            g.gs.scenes[sc.id] = sc
            g.gs.people[sc.id] = g.gs.people[orig.id]
        for orig in picked:
            g.gs.scenes.pop(orig.id, None)
        await g.start()
        await g._start_call(scene=g.gs.scenes["p0"])
        while g.slots.free_slot() is not None:
            await g._start_call()
        await asyncio.sleep(D * 10)
        check("p1" in g._pending_after and not any(c.scene == "p1" for c in g.slots),
              "p1 waits, not dropped")
        p1 = g.gs.scenes["p1"]
        mine = set(p1.needs) | set(g.gs.needs_people("p1"))
        clash = [c for c in g.slots if c.scene != "p0"
                 and mine & (set(g.gs.scenes[c.scene].lines) | set(g.gs.people[c.scene]))]
        for c in clash or [next(c for c in g.slots if c.scene != "p0")]:
            g._flows[c.slot].cancel()
            await asyncio.sleep(D)
            await g.slots.close(c)
        await asyncio.sleep(1.0)
        check(any(c.scene == "p1" for c in g.slots), "and starts when a slot frees")
        await g.stop("stop")
        await sess.close()

        print("\n== listen: the schedule waits for the board to empty (§4.2, Rev 16)")
        b, link, g, sess = await build_game(tmp, pace="manual")
        await g.start()
        check(link.state_v.get("game/pause") == "3", "pause published, 3 from the configuration")
        await g.on_command("pause", "90")
        check(link.state_v.get("game/pause") == "60", "pause clamped to 60")
        await g.on_command("pause", "4")
        await g.on_command("jitter", "50")
        await g.on_command("pace", "listen")
        check(link.state_v.get("game/pace") == "listen", "pace listen accepted and echoed")
        g.pacing.seed(3)
        check({g.pacing.wait() for _ in range(20)} == {4.0},
              "listen waits pause, every time: no jitter, no ramp (Rev 17)")
        check(link.state_v.get("game/next_at") != "", "an empty board schedules at once")
        lone = next(sc for sc in g.gs.scenes.values()
                    if not g.gs.followers(sc.id) and sc.id != "nbn-trace")
        call = C(slot=1, number=1, scene=lone.id, from_line=lone.from_line,
                 to_line=lone.to_line)
        await g.slots.open(call)
        g.pacing.waiting_to_connect()
        await g._connected(call)
        check(link.state_v.get("game/next_at") == "",
              "connecting does not schedule in listen: the conversation is still on")
        await g.on_command("pace", "auto")
        check(link.state_v.get("game/next_at") != "", "the same moment in auto schedules")
        await g.on_command("pace", "listen")
        check(link.state_v.get("game/next_at") == "", "and back in listen it is cleared")
        await g._finish_call(call, lone, Outcome(True))
        check(link.state_v.get("game/next_at") != "", "the call's end schedules the next")
        call = C(slot=1, number=2, scene=parent.id, from_line=parent.from_line,
                 to_line=parent.to_line)
        await g.slots.open(call)
        call.connected = True
        await g._finish_call(call, parent, Outcome(True))
        check(link.state_v.get("game/next_at") == "",
              "a waiting after: scene holds the schedule in listen")
        await g.stop("stop")
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
        pause = db.execute("SELECT pause FROM sessions ORDER BY id DESC").fetchone()[0]
        check(pause == 3.0, f"pause recorded with the pacing values (Rev 17): {pause}")
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
