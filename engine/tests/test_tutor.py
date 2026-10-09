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
from sbgame.game import Game
from sbgame.session import SessionLog
from test_sim import D

logging.basicConfig(level=logging.WARNING, stream=sys.stdout)

failures = 0


def check(ok: bool, what: str) -> None:
    global failures
    print(f"    {what:<62} {'ok' if ok else 'FAIL'}")
    if not ok:
        failures += 1


KEYS = ("intro", "begin-manual", "answer-station", "answer-trunk", "talk", "greet",
        "respond", "ring-front-28", "ring-rear-28", "center-ringing", "trunk-front",
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
    h.ctx.tutor = Tutor(h.b, h.hw, lines())
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
    await heard_tutor(h, "ring-front-28")
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
    await heard_tutor(h, "ring-rear-28")
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
    b = Board()
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
    """The real wavs, and a short silent one for each tutor line."""
    d = tmp / "wav"
    d.mkdir()
    for f in Path("../wav").glob("*.wav"):
        (d / f.name).symlink_to(f.resolve())
    for n in names:
        with wave.open(str(d / f"{n}.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(48000)
            w.writeframes(b"\0\0" * 2400)
    return d


async def main() -> int:
    print("\n== her lines, from script.yml's tutor: (§4.9)")
    s = load("../script.yml")
    t = s.tutor
    check(all(k in t for k in ("intro", "answer-station", "hangup-pair")), "the plain lines are there")
    cabled = [j["jack"] for j in s.jacks if j["station"]]
    check(all(f"ring-front-{j}" in t and f"ring-rear-{j}" in t for j in cabled),
          f"a ring line each way for each of {len(cabled)} cabled jacks")
    check("room 403" in t[f"ring-front-{next(j['jack'] for j in s.jacks if j['label'] == '403')}"].text,
          "a numbered jack is said as a room")
    check(t["dial-pizza"].text.endswith("dial Sunset four, four one oh one."),
          f"a number as the card prints it: {t['dial-pizza'].text[-40:]!r}")
    check(t["say-operator.1"].text == "Say: How may I connect your call?",
          "an operator line, as she is to say it")
    check(all(u.speaker == "tutor" and u.name.startswith("tutor.") for u in t.values()),
          "each said by the tutor, as tutor.<key>")
    check(all(len(u.name) <= 31 for u in t.values()), "every name fits audio.md §7.1")

    print("\n== a call between rooms, tutored")
    h = tutored(scene(Shape.STATION_TO_STATION))
    out = await run(h, station_to_station, tutored_station_operator)
    check(out.ok, f"success, {out.reason!r}")
    check(h.w.said[:3] == ["answer-station", "greet", "ring-front-28"],
          f"answer, greet, ring, in that order: {h.w.said}")
    check(not h.w.overlap, f"she is never speaking as a listen starts: {h.w.overlap}")

    print("\n== a call in on a trunk, tutored")
    h = tutored(scene(Shape.OUTSIDE_TO_STATION, from_station=None, from_line="pizza"))
    out = await run(h, outside_to_station, tutored_trunk_operator, 3)
    check(out.ok, f"success, {out.reason!r}")
    check(h.w.said == ["answer-trunk", "talk", "greet", "ring-rear-28", "center-ringing"],
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

        print("\n== the switch, without her wavs")
        b, link, g, sess = await build_game(tmp)
        check(link.state_v.get("game/tutor") == "off", "off at birth")
        await g.on_command("tutor", "on")
        check(link.state_v.get("game/tutor") == "off"
              and "have no wav" in link.state_v.get("game/error", ""),
              f"refused while her lines are unrendered: {link.state_v.get('game/error')!r}")
        await sess.close()

        print("\n== a game with her")
        wav = make_wavs(tmp, [u.name for u in s.tutor.values()])
        b, link, g, sess = await build_game(tmp, str(wav))
        w = Watch(b)
        await g.on_command("tutor", "on")
        check(link.state_v.get("game/tutor") == "on", "on, and echoed")
        await g.on_command("run", "on")
        await b.wait_until(lambda b: "begin-manual" in w.said, 5)
        check(w.said == ["intro", "begin-manual"], f"Start: the introduction, then Next Call: {w.said}")
        check(g.tallies.started == 0, "and no call yet, in manual")
        await g.on_command("next", "")
        check(g.tallies.started == 1, "Next deals one")
        await g.on_command("next", "")
        check(g.tallies.started == 1 and "one call at a time" in link.state_v.get("game/error", ""),
              "a second is refused while it runs")
        await g.on_command("run", "off")
        check(g.tutor is None and ("audio/monitor/play/set", "stop") in link.sent,
              "Stop silences her")

        print("\n== the end of a call: the cords out before another")
        await g.on_command("run", "on")
        await b.wait_until(lambda b: w.said.count("begin-manual") == 2, 5)
        while g._tutor_task is not None:          # to the end of her introduction
            await asyncio.sleep(D)
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
        await g.on_command("next", "")
        check(g.tallies.started == 1, "and Next deals")
        await g.on_command("tutor", "off")
        check(g.tutor is None and link.state_v.get("game/tutor") == "off",
              "off mid-game: she stops at once")
        await g.on_command("run", "off")
        w.stop()
        await sess.close()

    print(f"\n{'FAILURES: ' + str(failures) if failures else 'tutor mode passed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
