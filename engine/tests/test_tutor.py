"""Tutor mode (game_control.md §4.9, Rev 29).

Her lines are checked where they are made, in the loader; then the flows are
run with her, against the echoing fake, for the order of her lines against
the operator's moves and the one rule that matters most: she is never
speaking while the game listens. Then the game around her: the switch, the
introduction, one call at a time, and the end of a call.
"""

import asyncio
import logging
import sys
import tempfile
import wave
from pathlib import Path

import sbgame.flows as flows
import sbgame.tutor as tutor_mod
from sbgame.board import Board
from sbgame.calls import Call
from sbgame.flows import outside_to_station, station_to_outside, station_to_station
from sbgame.script_data import Speech, Shape, build
from sbgame.tutor import Tutor
from tts.script import load

from test_flows import Harness, scene, speech, answers, request_heard
from test_game import StateLink
from sbgame.config import Config
from sbgame.game import Game, pick_lessons
from sbgame.session import SessionLog
from test_sim import D, HOLD

logging.basicConfig(level=logging.WARNING, stream=sys.stdout)

failures = 0


def check(ok: bool, what: str) -> None:
    global failures
    print(f"    {what:<62} {'ok' if ok else 'FAIL'}")
    if not ok:
        failures += 1


KEYS = ("intro-jacks", "intro-cords", "intro-switches", "answer-station", "answer-trunk", "talk", "greet",
        "respond", "ring-front-b", "ring-rear-b", "center-ringing", "trunk-front",
        "dial-pizza", "dial-operator", "center-dialled", "center", "busy-heard",
        "hangup-pair", "hangup-one", "ready-manual")


def lines() -> dict[str, Speech]:
    return {k: Speech(f"tutor.{k}", D * 3, "tutor") for k in KEYS}


class Watch:
    """Every change, so the order of her lines and the listens can be read back."""

    def __init__(self, b: Board) -> None:
        self.said: list[str] = []
        self.overlap: list[str] = []
        self.b = b
        self.task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        async for ch in self.b.watch():
            if ch.key == "audio/monitor/play" and ch.new.startswith("tutor."):
                self.said.append(ch.new.removeprefix("tutor."))
            if ch.key.endswith("/listen") and ch.new == "listening" \
                    and self.b.get("audio/monitor/play") not in ("", "pending"):
                self.overlap.append(ch.key)

    def stop(self) -> None:
        self.task.cancel()


def tutored(sc) -> Harness:
    h = Harness(sc)
    h.repeats = []

    async def on_repeat(key: str) -> None:
        h.repeats.append(key)
    h.ctx.tutor = Tutor(h.b, h.hw, lines(), on_repeat=on_repeat)
    h.ctx.jack_of = lambda n: 28
    return h


async def heard_tutor(h: Harness, key: str) -> None:
    await h.b.wait_until(lambda b: b.get("audio/monitor/play") == f"tutor.{key}", 5)
    await h.b.wait_until(lambda b: not b.get("audio/monitor/play"), 5)


# ------------------------------------------------------------- operators ----


async def tutored_station_operator(h: Harness) -> None:
    c, want = "station/12", 2
    await heard_tutor(h, "answer-station")
    await answers(h, c)
    await request_heard(h, c)
    await heard_tutor(h, "ring-front-b")
    await h.b.update(f"station/{want}/ring", "on")
    await h.b.wait_until(lambda b: b.on(f"station/{want}/hook"), 5)
    await h.b.update(f"station/{want}/ring", "off")
    await h.b.update(f"{c}/peer", f"station/{want}")
    await h.b.update(f"station/{want}/peer", c)


async def tutored_trunk_operator(h: Harness) -> None:
    c, want = "trunk/3", 2
    await heard_tutor(h, "answer-trunk")
    await h.b.update(f"{c}/seize", "on")          # the cord goes in
    await heard_tutor(h, "talk")
    await h.b.update(f"{c}/op", "on")
    await request_heard(h, c)
    await heard_tutor(h, "ring-rear-b")
    await h.b.update(f"station/{want}/ring", "on")
    await h.b.wait_until(lambda b: b.on(f"station/{want}/hook"), 5)
    await h.b.update(f"station/{want}/ring", "off")
    await h.b.update(f"{c}/peer", f"station/{want}")
    await h.b.update(f"station/{want}/peer", c)


async def tutored_dialling_operator(h: Harness) -> None:
    c = "station/12"
    await answers(h, c)
    await request_heard(h, c)
    await heard_tutor(h, "trunk-front")
    await h.b.update("trunk/1/seize", "on")
    await h.b.update(f"{c}/peer", "trunk/1")
    await h.b.update("trunk/1/peer", c)
    await heard_tutor(h, "dial-pizza")
    for d in "7844101":
        await h.b.update("trunk/1/digit", d)


def slow_listens(h: Harness) -> None:
    """The operator takes a while to start speaking, and a cancelled listen
    hears nothing: room to press Repeat Help mid-listen."""
    echo = h.link._echo

    async def _echo(key: str, p: str) -> None:
        base = key.removesuffix("/set")
        if not base.endswith("/listen") or p == "0":
            return await echo(key, p)
        u = h.b.update
        await asyncio.sleep(D)
        await u(base, "listening")
        await asyncio.sleep(D * 8)
        if h.b.get(base) != "listening":
            return
        await u(base, "speech")
        await asyncio.sleep(D)
        await u(base, "silence")
    h.link._echo = _echo


async def repeating_operator(h: Harness) -> None:
    """Asks for the greeting again while the game listens for her (Rev 35)."""
    c, want = "station/12", 2
    await answers(h, c)
    await heard_tutor(h, "greet")
    await h.b.wait_until(lambda b: b.get(f"{c}/listen") == "listening", 5)
    h.asked_ok = h.ctx.tutor.repeat()
    await request_heard(h, c)
    await h.b.update(f"station/{want}/ring", "on")
    await h.b.wait_until(lambda b: b.on(f"station/{want}/hook"), 5)
    await h.b.update(f"station/{want}/ring", "off")
    await h.b.update(f"{c}/peer", f"station/{want}")
    await h.b.update(f"station/{want}/peer", c)


async def slow_operator(h: Harness) -> None:
    """Leaves the lamp lit long enough to be told twice more."""
    await h.b.wait_until(lambda b: len([s for s in h.w.said if s == "answer-station"]) == 3, 10)
    await answers(h, "station/12")
    await request_heard(h, "station/12")
    await h.b.update("station/2/ring", "on")
    await h.b.wait_until(lambda b: b.on("station/2/hook"), 5)
    await h.b.update("station/2/ring", "off")
    await h.b.update("station/12/peer", "station/2")
    await h.b.update("station/2/peer", "station/12")


async def run(h: Harness, flow, operator, *args):
    h.w = Watch(h.b)
    try:
        return await h.run(flow, operator, *args)
    finally:
        await asyncio.sleep(D)
        h.w.stop()


async def build_game(tmp: Path, wav: str = "../wav"):
    """test_game's, with a wav directory of our own."""
    b = Board(hold=HOLD)
    link = StateLink(b)
    cfg = Config(script="../script.yml", wav_dir=wav, session_db=str(tmp / "s.db"))
    gs = build(cfg.resolved("script"), cfg.resolved("wav_dir"))
    sess = SessionLog(cfg.resolved("session_db"))
    await sess.open()
    g = Game(b, gs, cfg, sess)
    await g.on_birth(link)
    await b.set_broker(True)
    await b.update("ctl/status", "online")
    await b.update("ctl/audio_status", "online")
    await b.update("ctl/esp_heartbeat", "1")
    return b, link, g, sess


def make_wavs(tmp: Path, names) -> Path:
    """The real wavs but hers, and a short silent one for each tutor line."""
    d = tmp / "wav"
    d.mkdir()
    for f in Path("../wav").glob("*.wav"):
        if not f.name.startswith("tutor."):
            (d / f.name).symlink_to(f.resolve())
    for n in names:
        stub = d / f"{n}.wav"
        if stub.is_symlink():
            stub.unlink()       # or writing it would go through to ../wav
        with wave.open(str(stub), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(48000)
            w.writeframes(b"\0\0" * 2400)
    return d


async def main() -> int:
    print("\n== her lines, from script.yml's tutor: (§4.9)")
    s = load("../script.yml")
    t = s.tutor
    check(all(k in t for k in ("intro-jacks", "answer-station", "hangup-pair")), "the plain lines are there")
    cabled = [j["station"] for j in s.jacks if j["station"]]
    check(all(f"ring-front-{st}" in t and f"ring-rear-{st}" in t for st in cabled),
          f"a ring line each way for each of {len(cabled)} cabled stations, by name")
    check("room 403" in t["ring-front-room403"].text, "a numbered jack is said as a room")
    check(t["dial-pizza"].text.endswith("dial Sunset four, four one oh one."),
          f"a number as the card prints it: {t['dial-pizza'].text[-40:]!r}")
    check(t["say-operator.1"].text == "Say: How may I connect your call?",
          "an operator line, as she is to say it")
    check(all(u.speaker == "tutor" and u.name == ("brief." + k.removeprefix("brief-")
                                                   if k.startswith("brief-") else "tutor." + k)
              for k, u in t.items()),
          "each said by the tutor, as tutor.<key>, or brief.<key> for a short form (Rev 55)")
    check(t["brief-ring-front-room403"].text.startswith("Front cord to room 403."),
          "a short form expanded per jack like its full line")
    check(all(f"brief-ring-rear-{st}" in t for st in cabled), "for every cabled station")
    check(not any(k.startswith(("brief-greet", "brief-say", "brief-intro")) for k in t),
          "none for the introduction or before the operator speaks")
    check(max(len(u.name) for u in t.values()) <= 31, "every name within 31 characters")
    check(all(len(u.name) <= 31 for u in t.values()), "every name fits audio.md §7.1")

    print("\n== the lessons (§4.9, Rev 30)")
    from tts.script import scene_kind, ScriptError
    kinds = [{scene_kind(s.scenes[i], s.stations) for i in g} for g in s.lessons]
    check(kinds == [{"between rooms"}, {"out to a number"}, {"in from outside"},
                    {"to the operator"}], f"four groups, one kind each, in order: {kinds}")
    picks = {tuple(pick_lessons(s.lessons, seed)) for seed in range(20)}
    check(len(picks) > 10, f"different games pick differently: {len(picks)} of 20")
    check(pick_lessons(s.lessons, 7) == pick_lessons(s.lessons, 7), "the same seed picks the same")
    real = Path("../script.yml").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as td:
        for what, old, new in (
                ("a scene of another kind", "-   [times-pike,", "-   [crane-wakeup, times-pike,"),
                ("an after: scene", "-   [times-pike,", "-   [taxi-pike, times-pike,"),
                ("no such scene", "-   [times-pike,", "-   [nosuch, times-pike,")):
            f = Path(td) / "bad.yml"
            f.write_text(real.replace(old, new, 1), encoding="utf-8")
            try:
                load(f)
                check(False, f"refused: {what}")
            except ScriptError as e:
                check(any("lessons" in x for x in e.failures), f"refused: {what}")
        f = Path(td) / "bad.yml"
        f.write_text(real.replace("    brief:\n", "    brief:\n        greet: Hello.\n", 1),
                     encoding="utf-8")
        try:
            load(f)
            check(False, "refused: a short form of a prompt before the operator speaks")
        except ScriptError as e:
            check(any("brief.greet" in x for x in e.failures),
                  "refused: a short form of a prompt before the operator speaks")

    print("\n== a call between rooms, tutored")
    h = tutored(scene(Shape.STATION_TO_STATION))
    out = await run(h, station_to_station, tutored_station_operator)
    check(out.ok, f"success, {out.reason!r}")
    check(h.w.said[:3] == ["answer-station", "greet", "ring-front-b"],
          f"answer, greet, ring, in that order: {h.w.said}")
    check(not h.w.overlap, f"she is never speaking as a listen starts: {h.w.overlap}")
    shown = [k for k in h.repeats if k]
    check(shown == ["answer-station", "greet", "ring-front-b"],
          f"Repeat Help offers each line she waits on the player after (Rev 34, 35): {shown}")
    check(h.repeats[-1] == "", "and goes once the player has acted")

    print("\n== Repeat Help while the game listens for her (Rev 35)")
    h = tutored(scene(Shape.STATION_TO_STATION))
    slow_listens(h)
    out = await run(h, station_to_station, repeating_operator)
    check(out.ok, f"success, {out.reason!r}")
    check(h.asked_ok, "the press is taken")
    check(h.w.said.count("greet") == 2, f"the greeting said again: {h.w.said}")
    check(("station/12/listen/set", "0") in h.link.sent, "the listen stopped first")
    check(not h.w.overlap, "and she is never speaking as a listen starts")
    check("greet" in h.repeats, "the Say prompt is offered for repeating")
    t = Tutor(h.b, h.hw, lines())
    t.repeat_key, t.asked, t._speaking = "greet", asyncio.Event(), lambda: True
    check(not t.repeat() and not t.asked.is_set(), "refused once she has started speaking")

    print("\n== a prompt short once said twice, More Help in full (Rev 55)")
    h = tutored(scene(Shape.STATION_TO_STATION))
    await h.live()
    t = h.ctx.tutor
    for k in ("answer-station", "hangup-pair"):
        t.lines["brief-" + k] = Speech("brief." + k, D * 2, "tutor")
    mores: list[str] = []

    async def on_more(key: str) -> None:
        mores.append(key)
    t._on_more = on_more
    plays: list[str] = []

    async def played() -> None:
        async for ch in h.b.watch():
            if ch.key == "audio/monitor/play" and ch.new not in ("", "pending"):
                plays.append(ch.new)
    watch = asyncio.create_task(played())
    check(tutor_mod.prompt_of("ring-front-room403") == "ring-front"
          and tutor_mod.prompt_of("dial-operator") == "dial-operator"
          and tutor_mod.prompt_of("dial-pizza") == "dial"
          and tutor_mod.prompt_of("center-ringing") == "center-ringing",
          "every jack and number is the one prompt")
    never = lambda b: b.on("station/9/hook")
    await t.say("hangup-pair", hold=True)
    for _ in range(2):
        await t.say("answer-station", hold=True)
    check(plays[-3:] == ["tutor.hangup-pair", "tutor.answer-station", "tutor.answer-station"],
          f"each prompt in full twice: {plays}")
    await t.say("answer-station", until=never)
    check(plays[-1:] == ["brief.answer-station"], f"then the short form: {plays[-1:]}")
    check(t.repeat_key == "brief-answer-station" and t.more_key == "answer-station"
          and mores[-1:] == ["answer-station"], "More Help offered, naming the full line")
    check(await t.more(), "More Help taken")
    await asyncio.sleep(D * 4)
    check(plays[-1:] == ["tutor.answer-station"], f"the full line said: {plays}")
    check(t.repeat_key == "answer-station" and t.more_key == "" and mores[-1:] == [""],
          "Repeat Help repeats the full line now, and More Help is done")
    check(not await t.more(), "a second More Help refused")
    await t.say("talk", hold=True)
    check(plays[-1:] == ["tutor.talk"] and t.more_key == "",
          "a line with no short form said in full, no More Help")
    await t.say("hangup-pair", hold=True)
    check(plays[-1:] == ["tutor.hangup-pair"], "a prompt said once so far: in full, its own count")
    await t.stop()
    watch.cancel()

    print("\n== a call in on a trunk, tutored")
    h = tutored(scene(Shape.OUTSIDE_TO_STATION, from_station=None, from_line="pizza"))
    out = await run(h, outside_to_station, tutored_trunk_operator, 3)
    check(out.ok, f"success, {out.reason!r}")
    check(h.w.said == ["answer-trunk", "talk", "greet", "ring-rear-b", "center-ringing"],
          f"the cord, then the switch, and the switch back before the room answers: {h.w.said}")
    check(not h.w.overlap, "never over a listen")

    print("\n== a call out, tutored")
    h = tutored(scene(Shape.STATION_TO_OUTSIDE, to_station=None, to_line="pizza",
                      dial="784-4101"))
    out = await run(h, station_to_outside, tutored_dialling_operator)
    check(out.ok, f"success, {out.reason!r}")
    check(h.w.said == ["answer-station", "greet", "trunk-front", "dial-pizza", "center-dialled"],
          f"the trunk, the number, the switch back during ringback: {h.w.said}")

    print("\n== a call out whose conversation waits for her")
    conv = (speech("t.2", "called"), Speech("t.3", D * 3, "called", wait=True),
            speech("t.4", "caller"))
    h = tutored(scene(Shape.STATION_TO_OUTSIDE, to_station=None, to_line="pizza",
                      dial="784-4101", conversation=conv))
    out = await run(h, station_to_outside, tutored_dialling_operator)
    check(out.ok, f"success, {out.reason!r}")
    check(h.w.said[-2:] == ["respond", "center"] and "center-dialled" not in h.w.said,
          f"the switch back after her last word, not during ringback: {h.w.said}")
    check(not h.w.overlap, "never over a listen")

    print("\n== told again while nothing happens, twice at most")
    flows.REPEAT = tutor_mod.REPEAT = D * 8
    try:
        h = tutored(scene(Shape.STATION_TO_STATION))
        out = await run(h, station_to_station, slow_operator)
        check(out.ok, f"success, {out.reason!r}")
        check(h.w.said.count("answer-station") == 3, f"said three times: {h.w.said}")
        check(not h.w.overlap, "never over a listen")
    finally:
        flows.REPEAT = tutor_mod.REPEAT = 20.0

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        print("\n== pace tutor, without her wavs")
        bare = tmp / "bare"
        bare.mkdir()
        for f in Path("../wav").glob("*.wav"):
            if not f.name.startswith("tutor."):
                (bare / f.name).symlink_to(f.resolve())
        b, link, g, sess = await build_game(tmp, str(bare))
        check(link.state_v.get("game/pace") == "manual", "manual at birth, as configured")
        await g.on_command("pace", "tutor")
        check(link.state_v.get("game/pace") == "manual"
              and "have no wav" in link.state_v.get("game/error", ""),
              f"refused while her lines are unrendered: {link.state_v.get('game/error')!r}")
        await sess.close()

        print("\n== a game with her")
        wav = make_wavs(tmp, [u.name for u in s.tutor.values()])
        b, link, g, sess = await build_game(tmp, str(wav))
        w = Watch(b)
        await g.on_command("pace", "tutor")
        check(link.state_v.get("game/pace") == "tutor", "pace tutor, and echoed (Rev 32)")
        await g.on_command("run", "on")
        await b.wait_until(lambda b: w.said == ["intro-jacks"], 5)
        check(link.state_v.get("game/tutor/intro") == "1/3", "Start: her first part, 1/3")
        await asyncio.sleep(D * 8)                  # she finishes, and waits
        check(w.said == ["intro-jacks"] and g.tallies.started == 0,
              "after it she waits for More Help or Next Call")
        check(link.state_v.get("game/tutor/waiting") == "more", "and says so: waiting more (Rev 33)")
        check(link.state_v.get("game/tutor/repeat") == "intro-jacks",
              "Repeat Help offers the part she finished (Rev 34)")
        await g.on_command("repeat", "")
        await b.wait_until(lambda b: w.said == ["intro-jacks", "intro-jacks"], 5)
        check(True, "Repeat Help: the part again")
        await asyncio.sleep(D * 8)
        check(g.tallies.started == 0 and link.state_v.get("game/tutor/intro") == "1/3",
              "and she waits again, on the same part")
        await g.on_command("more", "")
        await b.wait_until(lambda b: w.said[-1:] == ["intro-cords"], 5)
        check(link.state_v.get("game/tutor/intro") == "2/3"
              and link.state_v.get("game/tutor/waiting") == "",
              "More Help: the second part, 2/3, and not waiting while she speaks")
        await g.on_command("more", "")              # mid-part: cut short, and on
        await b.wait_until(lambda b: w.said[-1:] == ["intro-switches"], 5)
        check(("audio/monitor/play/set", "stop") in link.sent
              and link.state_v.get("game/tutor/intro") == "3/3",
              "More Help mid-part cuts it short: the last part, 3/3")
        await asyncio.sleep(D * 8)
        await g.on_command("more", "")
        await asyncio.sleep(D * 4)
        check(w.said[-1:] == ["intro-switches"] and g.tallies.started == 0,
              "after the last, More Help does nothing and no call comes")
        check(link.state_v.get("game/tutor/waiting") == "next", "waiting next")
        await g.on_command("next", "")
        check(link.state_v.get("game/tutor/intro") == "" and g._tutor_task is None,
              "Next Call ends the introduction")
        await g.on_command("next", "")
        check(g.tallies.started == 1, "Next deals one")
        first = link.state_v.get("game/call/1/scene")
        check(first in g.gs.lessons[0] and len(g._lessons) == 3,
              f"the first lesson, between rooms: {first}")
        await g.on_command("next", "")
        check(g.tallies.started == 1 and "one call at a time" in link.state_v.get("game/error", ""),
              "a second is refused while it runs")
        await g.on_command("run", "off")
        check(g.tutor is None and ("audio/monitor/play/set", "stop") in link.sent,
              "Stop silences her")
        await g.on_command("more", "")
        check("no short line" in link.state_v.get("game/error", ""),
              "More Help with no introduction and no short line is refused")
        await g.on_command("repeat", "")
        check("nothing to repeat now" in link.state_v.get("game/error", ""),
              "Repeat Help with nothing to repeat is refused")

        print("\n== the end of a call: the cords out before another")
        await g.on_command("run", "on")
        await b.wait_until(lambda b: w.said.count("intro-jacks") == 2, 5)
        g._tutor_task.cancel()                    # as Next Call would, without a call
        await asyncio.gather(g._tutor_task, return_exceptions=True)
        g._tutor_task, g._intro = None, False
        sc = next(x for x in g.gs.scenes.values() if x.shape == Shape.STATION_TO_STATION)
        await b.update(f"station/{sc.from_station}/peer", f"station/{sc.to_station}")
        await b.update(f"station/{sc.to_station}/peer", f"station/{sc.from_station}")
        call = Call(slot=1, number=9, scene=sc.id, from_line=sc.from_line, to_line=sc.to_line)
        g._tutor_task = asyncio.create_task(g._tutor_hangup(call, sc))
        await b.wait_until(lambda b: "hangup-pair" in w.said, 5)
        await g.on_command("next", "")
        check(g.tallies.started == 0 and "cords" in link.state_v.get("game/error", ""),
              "Next is refused while a cord is up")
        await b.update(f"station/{sc.from_station}/peer", "")
        await b.update(f"station/{sc.to_station}/peer", "")
        await b.wait_until(lambda b: w.said[-1:] == ["ready-manual"], 5)
        for _ in range(50):
            if g._tutor_task is None:
                break
            await asyncio.sleep(D)
        check(g._tutor_task is None, "cleared: she says so, and the game is free")
        check(link.state_v.get("game/tutor/waiting") == "next", "waiting for Next Call")
        await g.on_command("next", "")
        check(g.tallies.started == 1 and link.state_v.get("game/tutor/waiting") == "",
              "and Next deals, and she is no longer waiting")
        await g.on_command("pace", "manual")
        check(g.tutor is None and link.state_v.get("game/pace") == "manual",
              "another pace mid-game: she stops at once")
        await g.on_command("pace", "tutor")
        check(g.tutor is not None and g._tutor_task is None and not g._lessons,
              "tutor again mid-game: tutored from the next call, no introduction or lessons")
        await g.on_command("run", "off")
        w.stop()
        await sess.close()

    print(f"\n{'FAILURES: ' + str(failures) if failures else 'tutor mode passed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
