"""Tutor mode (game_control.md §7).

Her lines are checked where they are made, in the loader; then the flows are
run with her, against the echoing fake, for the order of her lines against
the operator's moves and the one rule that matters most: she is never
speaking while the game listens. Then the game around her: the switch, the
introduction, one call at a time, and the end of a call.
"""

import asyncio
import wave
from pathlib import Path

import sbgame.flows as flows
import sbgame.tutor as tutor_mod
from sbgame.board import Board
from sbgame.calls import Call
from sbgame.flows import outside_to_station, station_to_outside, station_to_station, to_operator
from sbgame.game import pick_lessons
from sbgame.scenes import say
from sbgame.script_data import Speech, Shape
from sbgame.tutor import Tutor
from tts.script import ScriptError, load, scene_kind

from harness import D, HOLD, REPO, Harness, answers, build_game, request_heard, scene, speech


KEYS = ("intro-jacks", "intro-cords", "intro-switches", "answer-station", "answer-trunk", "talk", "greet",
        "respond", "for-you", "ring-front-b", "ring-rear-b", "center-ringing", "trunk-front",
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


async def tutored_slow_station_operator(h: Harness) -> None:
    """She answers, hears the request and her line, takes her key off the
    caller and leaves the caller alone well past ABANDON before ringing."""
    c, want = "station/12", 2
    await heard_tutor(h, "answer-station")
    await answers(h, c)
    await request_heard(h, c)
    await heard_tutor(h, "ring-front-b")
    await h.b.update(f"{c}/op", "off")
    await asyncio.sleep(flows.ABANDON * 3)
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
    """Asks for the greeting again while the game listens for her."""
    c, want = "station/12", 2
    await answers(h, c)
    await heard_tutor(h, "greet")
    await h.b.wait_until(lambda b: b.get(f"{c}/listen") == "listening", 5)
    h.asked_ok = await h.ctx.tutor.repeat()
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


def make_wavs(tmp: Path, names) -> Path:
    """The real wavs but hers, and a short silent one for each tutor line."""
    d = tmp / "wav"
    d.mkdir()
    for f in (REPO / "wav").glob("*.wav"):
        if not f.name.startswith("tutor."):
            (d / f.name).symlink_to(f.resolve())
    for n in names:
        stub = d / f"{n}.wav"
        if stub.is_symlink():
            stub.unlink()       # or writing it would go through to the real wav
        with wave.open(str(stub), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(48000)
            w.writeframes(b"\0\0" * 2400)
    return d


async def test_her_lines_from_script_yml_s_tutor():
    """Her lines, from script.yml's tutor: (§7)"""
    s = load(REPO / "script.yml")
    t = s.tutor
    assert all(k in t for k in ("intro-jacks", "answer-station", "hangup-pair")), "the plain lines are there"
    # Not for the real telephone, which no scene rings (game_control.md §8.1).
    cabled = [j["station"] for j in s.jacks
              if j["station"] and s.stations[j["station"]]["number"] != 24]
    assert all(f"ring-front-{st}" in t and f"ring-rear-{st}" in t for st in cabled), f"a ring line each way for each of {len(cabled)} cabled stations, by name"
    assert not any(k.endswith("-phone") for k in t), "and none for the real telephone"
    assert "room 403" in t["ring-front-room403"].text, "a numbered jack is said as a room"
    assert "dial Sunset four, four one oh one." in t["dial-pizza"].text, f"a number as the card prints it: {t['dial-pizza'].text[-80:]!r}"
    assert t["dial-pizza"].text.endswith("That's seven eight four, four one oh one."), "and as a person today says it, the exchange as digits"
    assert t["dial-rays"].text.endswith("That's seven eight four, five thousand."), "round thousands said whole, as with the exchange name"
    assert t["say-operator.1"].text == "Say: How may I connect your call?", "an operator line, as she is to say it"
    def named(k: str) -> str:
        for p in ("brief", "terse"):
            if k.startswith(p + "-"):
                return p + "." + k.removeprefix(p + "-")
        return "tutor." + k
    assert all(u.speaker == "tutor" and u.name == named(k) for k, u in t.items()), \
        "each said by the tutor, as tutor.<key>, or brief.<key> or terse.<key> for a short form"
    assert t["terse-ring-rear-room403"].text == "Rear cord to room 403. Pull far switch to ring.", "a terse form per jack"
    assert t["terse-dial-pizza"].text == "Dial seven eight four, four one oh one.", "a terse dial in digits alone"
    assert t["brief-ring-front-room403"].text.startswith("Front cord to room 403."), "a short form expanded per jack like its full line"
    assert all(f"brief-ring-rear-{st}" in t for st in cabled), "for every cabled station"
    assert not any(k.startswith(("brief-greet", "brief-say", "brief-intro")) for k in t), "none for the introduction or before the operator speaks"
    assert max(len(u.name) for u in t.values()) <= 31, "every name within 31 characters"
    assert all(len(u.name) <= 31 for u in t.values()), "every name fits audio.md §7.1"


async def test_the_lessons(tmp_path):
    """The lessons (§7)"""
    s = load(REPO / "script.yml")
    kinds = [{scene_kind(s.scenes[i], s.stations) for i in g} for g in s.lessons]
    assert (kinds == [{"between rooms"}, {"out to a number"}, {"in from outside"},
                    {"to the operator"}]), f"four groups, one kind each, in order: {kinds}"
    picks = {tuple(pick_lessons(s.lessons, seed)) for seed in range(20)}
    assert len(picks) > 10, f"different games pick differently: {len(picks)} of 20"
    assert pick_lessons(s.lessons, 7) == pick_lessons(s.lessons, 7), "the same seed picks the same"
    real = (REPO / "script.yml").read_text(encoding="utf-8")
    for what, old, new in (
            ("a scene of another kind", "-   [times-pike,", "-   [crane-wakeup, times-pike,"),
            ("an after: scene", "-   [times-pike,", "-   [taxi-pike, times-pike,"),
            ("no such scene", "-   [times-pike,", "-   [nosuch, times-pike,")):
        f = tmp_path / "bad.yml"
        f.write_text(real.replace(old, new, 1), encoding="utf-8")
        try:
            load(f)
            assert False, f"refused: {what}"
        except ScriptError as e:
            assert any("lessons" in x for x in e.failures), f"refused: {what}"
    f = tmp_path / "bad.yml"
    f.write_text(real.replace("    brief:\n", "    brief:\n        greet: Hello.\n", 1),
                 encoding="utf-8")
    try:
        load(f)
        assert False, "refused: a short form of a prompt before the operator speaks"
    except ScriptError as e:
        assert any("brief.greet" in x for x in e.failures), "refused: a short form of a prompt before the operator speaks"


async def test_a_call_between_rooms_tutored():
    """A call between rooms, tutored"""
    h = tutored(scene(Shape.STATION_TO_STATION))
    out = await run(h, station_to_station, tutored_station_operator)
    assert out.ok, f"success, {out.reason!r}"
    assert h.w.said[:3] == ["answer-station", "greet", "ring-front-b"], f"answer, greet, ring, in that order: {h.w.said}"
    assert not h.w.overlap, f"she is never speaking as a listen starts: {h.w.overlap}"
    shown = [k for k in h.repeats if k]
    assert shown == ["answer-station", "greet", "ring-front-b"], f"Repeat Help offers each line she waits on the player after: {shown}"
    assert h.repeats[-1] == "", "and goes once the player has acted"


async def test_repeat_help_while_the_game_listens_for_her():
    """Repeat Help while the game listens for her"""
    h = tutored(scene(Shape.STATION_TO_STATION))
    slow_listens(h)
    out = await run(h, station_to_station, repeating_operator)
    assert out.ok, f"success, {out.reason!r}"
    assert h.asked_ok, "the press is taken"
    assert h.w.said.count("greet") == 2, f"the greeting said again: {h.w.said}"
    assert ("station/12/listen/set", "0") in h.link.sent, "the listen stopped first"
    assert not h.w.overlap, "and she is never speaking as a listen starts"
    assert "greet" in h.repeats, "the Say prompt is offered for repeating"
    t = Tutor(h.b, h.hw, lines())
    t.repeat_key, t.asked, t._speaking = "greet", asyncio.Event(), lambda: True
    assert not await t.repeat() and not t.asked.is_set(), "refused once she has started speaking"


async def test_a_prompt_full_then_brief_then_terse_more_help_in():
    """A prompt full, then brief, then terse; More Help in full (§7.4)"""
    h = tutored(scene(Shape.STATION_TO_STATION))
    await h.live()
    t = h.ctx.tutor
    for k in ("answer-station", "hangup-pair"):
        t.lines["brief-" + k] = Speech("brief." + k, D * 2, "tutor")
    t.lines["terse-answer-station"] = Speech("terse.answer-station", D * 2, "tutor")
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
    assert (tutor_mod.prompt_of("ring-front-room403") == "ring-front"
          and tutor_mod.prompt_of("dial-operator") == "dial-operator"
          and tutor_mod.prompt_of("dial-pizza") == "dial"
          and tutor_mod.prompt_of("center-ringing") == "center-ringing"), "every jack and number is the one prompt"
    never = lambda b: b.on("station/9/hook")
    await t.say("hangup-pair", hold=True)
    await t.say("answer-station", hold=True)
    await t.say("answer-station", hold=True)
    assert plays[-3:] == ["tutor.hangup-pair", "tutor.answer-station", "brief.answer-station"], \
        f"in full the first time, brief the second: {plays}"
    await t.say("answer-station", until=never)
    assert plays[-1:] == ["terse.answer-station"], f"then terse: {plays[-1:]}"
    assert (t.repeat_key == "terse-answer-station" and t.more_key == "answer-station"
          and mores[-1:] == ["answer-station"]), "More Help offered, naming the full line"
    assert await t.more(), "More Help taken"
    await asyncio.sleep(D * 4)
    assert plays[-1:] == ["tutor.answer-station"], f"the full line said: {plays}"
    assert t.repeat_key == "answer-station" and t.more_key == "" and mores[-1:] == [""], "Repeat Help repeats the full line now, and More Help is done"
    assert not await t.more(), "a second More Help refused"
    await t.say("talk", hold=True)
    assert plays[-1:] == ["tutor.talk"] and t.more_key == "", "a line with no short form said in full, no More Help"
    await t.say("hangup-pair", hold=True)
    assert plays[-1:] == ["brief.hangup-pair"], "a prompt said once so far: brief, its own count"
    await t.say("hangup-pair", hold=True)
    assert plays[-1:] == ["brief.hangup-pair"], "and with no terse form it stays brief"
    t.demote("answer-station")
    await t.say("answer-station", hold=True)
    assert plays[-1:] == ["brief.answer-station"], f"a mistake sends it back to brief: {plays[-1:]}"
    await t.say("answer-station", hold=True)
    assert plays[-1:] == ["terse.answer-station"], f"and then terse again: {plays[-1:]}"
    await t.stop()
    watch.cancel()


async def test_a_greeting_in_full_once_then_greet_the_caller():
    """A greeting in full once, then "Greet the caller." (§7.4, Rev 121)"""
    h = tutored(scene(Shape.STATION_TO_STATION))
    ln = lines() | {k: Speech(f"tutor.{k}", D * 3, "tutor")
                    for k in ("say-operator.1", "say-operator.2", "say-crane-wakeup.3")}
    t = Tutor(h.b, h.hw, ln)
    room, trunk = Speech("x.1", 1.0, "caller", operator="operator.1"), Speech("y.1", 1.0, "caller", operator="operator.2")
    assert t.say_key(room, True) == "say-operator.1", "the room greeting in full the first time"
    assert t.say_key(trunk, True) == "say-operator.2", "and the trunk greeting, counted apart"
    assert t.say_key(room, True) == t.say_key(trunk, True) == "greet", "then each is Greet the caller"
    reply = Speech("crane-wakeup.2", 1.0, "caller", operator="crane-wakeup.3")
    assert t.say_key(reply, False) == t.say_key(reply, False) == "say-crane-wakeup.3", "a scene's own line is said in full every time"
    assert Tutor(h.b, h.hw, ln).say_key(room, True) == "say-operator.1", "a new game starts in full again"


async def test_after_the_last_repeat_how_to_hear_it_again(monkeypatch):
    """After the last repeat, how to hear it again"""
    h = tutored(scene(Shape.STATION_TO_STATION))
    await h.live()
    t = h.ctx.tutor
    t.lines["stuck"] = Speech("tutor.stuck", D * 3, "tutor")
    heard: list[str] = []

    async def heard_all() -> None:
        async for ch in h.b.watch():
            if ch.key == "audio/monitor/play" and ch.new.startswith("tutor."):
                heard.append(ch.new.removeprefix("tutor."))
    w = asyncio.create_task(heard_all())
    monkeypatch.setattr(tutor_mod, "REPEAT", D * 6)
    await t.say("talk", until=lambda b: b.on("station/9/op"))
    await asyncio.sleep(D * 40)
    assert heard == ["talk", "talk", "talk", "stuck"], f"the prompt, twice more, then 'press Repeat Help': {heard}"
    assert t.repeat_key == "talk", "and Repeat Help still has the prompt"
    await t.stop()
    w.cancel()


async def test_a_prompt_stops_once_the_player_has_done_it():
    """A prompt stops once the player has done it"""
    h = tutored(scene(Shape.STATION_TO_STATION))
    await h.live()
    t = h.ctx.tutor
    t.lines["talk"] = Speech("tutor.talk", 2.0, "tutor")      # a long line
    task = asyncio.create_task(t.say("talk", until=lambda b: b.on("station/9/op")))
    await h.b.wait_until(lambda b: b.get("audio/monitor/play") == "tutor.talk", 5)
    t0 = asyncio.get_running_loop().time()
    await h.b.update("station/9/op", "on")                    # she pushes the switch
    await asyncio.wait_for(task, 1.0)
    took = asyncio.get_running_loop().time() - t0
    assert took < 0.5, f"the line ends at once, not after its 2s: {took:.2f}s"
    assert ("audio/monitor/play/set", "stop") in h.link.sent, "the file is stopped"
    assert t.repeat_key == "" and t._again is None, "nothing left to repeat, and no repeats"
    await t.stop()


async def test_a_wrong_cord_line_over_her_prompt_fails_nothing():
    """A wrong-cord line over her prompt fails nothing (§7.7)"""
    h = tutored(scene(Shape.STATION_TO_STATION))
    await h.live()
    t = h.ctx.tutor
    t.lines["talk"] = Speech("tutor.talk", 2.0, "tutor")      # a long line
    task = asyncio.create_task(t.say("talk", until=lambda b: b.on("station/9/op")))
    await h.b.wait_until(lambda b: b.get("audio/monitor/play") == "tutor.talk", 5)
    hint = asyncio.create_task(say(h.b, h.hw, "audio/monitor", "tutor.center", 0.2))
    # Her prompt returns once replaced, with no timeout.
    await asyncio.wait_for(asyncio.shield(task), 1.0)
    await hint
    assert ("audio/monitor/play/set", "stop") not in h.link.sent, "and does not stop the line"
    assert t.repeat_key == "talk", "and comes round again"
    await t.stop()


async def test_a_caller_left_alone_does_not_hang_up_in_tutor_pacing(monkeypatch):
    """A caller left alone does not hang up in tutor pacing"""
    monkeypatch.setattr(flows, "ABANDON", D * 10)
    h = tutored(scene(Shape.STATION_TO_STATION))
    out = await run(h, station_to_station, tutored_slow_station_operator)
    assert out.ok, f"success after {flows.ABANDON * 3:.2f}s alone: {out.reason!r}"


async def test_a_call_in_on_a_trunk_tutored():
    """A call in on a trunk, tutored"""
    h = tutored(scene(Shape.OUTSIDE_TO_STATION, from_station=None, from_line="pizza"))
    out = await run(h, outside_to_station, tutored_trunk_operator, 3)
    assert out.ok, f"success, {out.reason!r}"
    assert h.w.said == ["answer-trunk", "talk", "greet", "ring-rear-b", "center-ringing"], f"the cord, then the switch, and the switch back before the room answers: {h.w.said}"
    assert not h.w.overlap, "never over a listen"


async def test_a_call_out_tutored():
    """A call out, tutored"""
    h = tutored(scene(Shape.STATION_TO_OUTSIDE, to_station=None, to_line="pizza",
                      dial="784-4101"))
    out = await run(h, station_to_outside, tutored_dialling_operator)
    assert out.ok, f"success, {out.reason!r}"
    assert h.w.said == ["answer-station", "greet", "trunk-front", "dial-pizza", "center-dialled"], f"the trunk, the number, the switch back during ringback: {h.w.said}"


async def test_a_call_to_the_operator_the_call_is_for():
    """A call to the operator: the call is for her"""
    h = tutored(scene(Shape.TO_OPERATOR, to_line="", to_station=None,
                      conversation=(speech("t.2", "caller"),)))
    out = await run(h, to_operator, lambda hh: answers(hh, "station/12"))
    assert out.ok, f"success, {out.reason!r}"
    assert h.w.said[:3] == ["answer-station", "greet", "for-you"], f"told the call is for her, after the request: {h.w.said}"
    assert not h.w.overlap, "never over a listen"


async def test_a_call_out_whose_conversation_waits_for_her():
    """A call out whose conversation waits for her"""
    conv = (speech("t.2", "called"), Speech("t.3", D * 3, "called", wait=True),
            speech("t.4", "caller"))
    h = tutored(scene(Shape.STATION_TO_OUTSIDE, to_station=None, to_line="pizza",
                      dial="784-4101", conversation=conv))
    out = await run(h, station_to_outside, tutored_dialling_operator)
    assert out.ok, f"success, {out.reason!r}"
    assert h.w.said[-2:] == ["respond", "center"] and "center-dialled" not in h.w.said, f"the switch back after her last word, not during ringback: {h.w.said}"
    assert not h.w.overlap, "never over a listen"


async def test_told_again_while_nothing_happens_twice_at_most(monkeypatch):
    """Told again while nothing happens, twice at most"""
    monkeypatch.setattr(flows, "REPEAT", D * 8)
    monkeypatch.setattr(tutor_mod, "REPEAT", D * 8)
    h = tutored(scene(Shape.STATION_TO_STATION))
    out = await run(h, station_to_station, slow_operator)
    assert out.ok, f"success, {out.reason!r}"
    assert h.w.said.count("answer-station") == 3, f"said three times: {h.w.said}"
    assert not h.w.overlap, "never over a listen"


async def test_pace_tutor_without_her_wavs(tmp_path):
    """Pace tutor, without her wavs"""
    tmp = tmp_path
    bare = tmp / "bare"
    bare.mkdir()
    for f in (REPO / "wav").glob("*.wav"):
        if not f.name.startswith("tutor."):
            (bare / f.name).symlink_to(f.resolve())
    b, link, g, sess = await build_game(tmp, str(bare))
    assert link.state_v.get("game/pace") == "manual", "manual at birth, as configured"
    await g.on_command("pace", "tutor")
    assert (link.state_v.get("game/pace") == "manual"
          and "have no wav" in link.state_v.get("game/error", "")), f"refused while her lines are unrendered: {link.state_v.get('game/error')!r}"
    await sess.close()


async def test_a_game_with_her(tmp_path):
    """A game with her: the introduction, a lesson, the end of a call"""
    tmp = tmp_path
    s = load(REPO / "script.yml")
    wav = make_wavs(tmp, [u.name for u in s.tutor.values()])
    b, link, g, sess = await build_game(tmp, str(wav))
    w = Watch(b)
    await g.on_command("pace", "tutor")
    assert link.state_v.get("game/pace") == "tutor", "pace tutor, and echoed"
    await g.on_command("run", "on")
    await b.wait_until(lambda b: w.said == ["intro-jacks"], 5)
    assert link.state_v.get("game/tutor/intro") == "1/3", "Start: her first part, 1/3"
    await asyncio.sleep(D * 8)                  # she finishes, and waits
    assert w.said == ["intro-jacks"] and g.tallies.started == 0, "after it she waits for More Help or Next Call"
    assert link.state_v.get("game/tutor/waiting") == "more", "and says so: waiting more"
    assert link.state_v.get("game/tutor/repeat") == "intro-jacks", "Repeat Help offers the part she finished"
    await g.on_command("repeat", "")
    await b.wait_until(lambda b: w.said == ["intro-jacks", "intro-jacks"], 5)
    # Repeat Help: the part again.
    await asyncio.sleep(D * 8)
    assert g.tallies.started == 0 and link.state_v.get("game/tutor/intro") == "1/3", "and she waits again, on the same part"
    await g.on_command("more", "")
    await b.wait_until(lambda b: w.said[-1:] == ["intro-cords"], 5)
    assert (link.state_v.get("game/tutor/intro") == "2/3"
          and link.state_v.get("game/tutor/waiting") == ""), "More Help: the second part, 2/3, and not waiting while she speaks"
    await g.on_command("more", "")              # mid-part: cut short, and on
    await b.wait_until(lambda b: w.said[-1:] == ["intro-switches"], 5)
    assert (("audio/monitor/play/set", "stop") in link.sent
          and link.state_v.get("game/tutor/intro") == "3/3"), "More Help mid-part cuts it short: the last part, 3/3"
    await asyncio.sleep(D * 8)
    await g.on_command("more", "")
    await asyncio.sleep(D * 4)
    assert w.said[-1:] == ["intro-switches"] and g.tallies.started == 0, "after the last, More Help does nothing and no call comes"
    assert link.state_v.get("game/tutor/waiting") == "next", "waiting next"
    await g.on_command("next", "")
    assert link.state_v.get("game/tutor/intro") == "" and g._tutor_task is None, "Next Call ends the introduction"
    await g.on_command("next", "")
    assert g.tallies.started == 1, "Next deals one"
    first = link.state_v.get("game/call/1/scene")
    assert first in g.gs.lessons[0] and len(g._lessons) == 3, f"the first lesson, between rooms: {first}"
    await g.on_command("next", "")
    assert g.tallies.started == 1 and "one call at a time" in link.state_v.get("game/error", ""), "a second is refused while it runs"
    await g.on_command("run", "off")
    assert g.tutor is None and ("audio/monitor/play/set", "stop") in link.sent, "Stop silences her"
    await g.on_command("more", "")
    assert "no short line" in link.state_v.get("game/error", ""), "More Help with no introduction and no short line is refused"
    await g.on_command("repeat", "")
    assert "nothing to repeat now" in link.state_v.get("game/error", ""), "Repeat Help with nothing to repeat is refused"


    # the end of a call with a trunk: her line, then Next Call
    await g.on_command("run", "on")
    await b.wait_until(lambda b: w.said.count("intro-jacks") == 2, 5)
    g._tutor_task.cancel()                    # as Next Call would, without a call
    await asyncio.gather(g._tutor_task, return_exceptions=True)
    g._tutor_task, g._intro = None, False
    # The last Stop's switchboard reset freezes the lines: let it end.
    await b.wait_until(lambda b: b.get("ctl/power_cut") != "on", 5)
    await asyncio.sleep(HOLD * 2)
    sc = next(x for x in g.gs.scenes.values() if x.shape == Shape.STATION_TO_OUTSIDE)
    await b.update(f"station/{sc.from_station}/peer", "trunk/3")
    await b.update("trunk/3/peer", f"station/{sc.from_station}")
    await b.update("trunk/3/seize", "on")
    call = Call(slot=1, number=9, scene=sc.id, from_line=sc.from_line, to_line=sc.to_line,
                trunk="trunk/3")
    g._tutor_task = asyncio.create_task(g._tutor_hangup(call, sc))
    await b.wait_until(lambda b: "hangup-pair" in w.said, 5)
    await b.wait_until(lambda b: w.said[-1:] == ["ready-manual"], 5)
    assert b.on("trunk/3/seize"), "with the trunk still seized she goes on: its seizure says nothing of the cord"
    for _ in range(50):
        if g._tutor_task is None:
            break
        await asyncio.sleep(D)
    assert g._tutor_task is None, "cleared: she says so, and the game is free"
    assert link.state_v.get("game/tutor/waiting") == "next", "waiting for Next Call"
    await g.on_command("next", "")
    assert g.tallies.started == 1 and link.state_v.get("game/tutor/waiting") == "", "and Next deals, and she is no longer waiting"


    # the end of a call with no trunk: the same
    await g.on_command("run", "off")
    await g.on_command("run", "on")
    await b.wait_until(lambda b: w.said.count("intro-jacks") == 3, 5)
    g._tutor_task.cancel()
    await asyncio.gather(g._tutor_task, return_exceptions=True)
    g._tutor_task, g._intro = None, False
    await b.wait_until(lambda b: b.get("ctl/power_cut") != "on", 5)
    await asyncio.sleep(HOLD * 2)
    sc = next(x for x in g.gs.scenes.values() if x.shape == Shape.STATION_TO_STATION)
    await b.update(f"station/{sc.from_station}/peer", f"station/{sc.to_station}")
    await b.update(f"station/{sc.to_station}/peer", f"station/{sc.from_station}")
    call = Call(slot=1, number=10, scene=sc.id, from_line=sc.from_line, to_line=sc.to_line)
    n = w.said.count("hangup-pair")
    g._tutor_task = asyncio.create_task(g._tutor_hangup(call, sc))
    await b.wait_until(lambda b: w.said.count("hangup-pair") == n + 1, 5)
    await b.wait_until(lambda b: w.said[-1:] == ["ready-manual"], 5)
    assert b.get(f"station/{sc.from_station}/peer"), "with the peers still up, she goes on to Next Call: on-hook, no cord shows"
    for _ in range(50):
        if link.state_v.get("game/tutor/waiting") == "next":
            break
        await asyncio.sleep(D)
    await g.on_command("next", "")
    assert g.tallies.started == 1, "and Next deals"
    await g.on_command("run", "off")
    await g.on_command("run", "on")
    await b.wait_until(lambda b: w.said.count("intro-jacks") == 4, 5)
    g._tutor_task.cancel()
    await asyncio.gather(g._tutor_task, return_exceptions=True)
    g._tutor_task, g._intro = None, False
    await b.wait_until(lambda b: b.get("ctl/power_cut") != "on", 5)
    await asyncio.sleep(HOLD * 2)
    n = w.said.count("hangup-pair")
    g._tutor_task = asyncio.create_task(g._tutor_hangup(call, sc))
    await b.wait_until(lambda b: w.said.count("hangup-pair") == n + 1, 5)
    k = len(link.sent)
    await g.on_command("next", "")
    assert g.tallies.started == 1 and ("audio/monitor/play/set", "stop") in link.sent[k:], "Next during her line cuts it short and deals"
    await g.on_command("pace", "manual")
    assert g.tutor is None and link.state_v.get("game/pace") == "manual", "another pace mid-game: she stops at once"
    await g.on_command("pace", "tutor")
    assert g.tutor is not None and g._tutor_task is None and not g._lessons, "tutor again mid-game: tutored from the next call, no introduction or lessons"
    await g.on_command("run", "off")
    w.stop()
    await sess.close()
