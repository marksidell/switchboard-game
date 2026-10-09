"""The Stream Deck program's rules, without a deck or a broker.

Panel is driven directly with explicit times, so every rule of §7.4 can be
checked: what each key publishes and when it does nothing, Stop's second
press, Next Call's guard, the dials' target, the error on the strip, and
staleness. Then the images are drawn once through a FileSurface, so a drawing
error shows up here rather than on the deck.
"""

import sys
import tempfile
from pathlib import Path

from sbgame.streamdeck import DIALS, Drawer, FileSurface, Panel, STALE

failures = 0


def check(ok: bool, what: str) -> None:
    global failures
    print(f"    {what:<58} {'ok' if ok else 'FAIL'}")
    if not ok:
        failures += 1


def live(t: float = 0.0, **state: str) -> Panel:
    """A panel on a healthy bus, game stopped, manual, the configured values."""
    p = Panel()
    p.broker_up = True
    base = {"ctl/game_status": "online", "ctl/status": "online",
            "ctl/audio_status": "online", "game/run": "off", "game/pace": "manual",
            "game/gap": "20", "game/ramp": "0", "game/floor": "5",
            "game/jitter": "0", "game/started": "0"}
    base.update({k.replace("__", "/"): v for k, v in state.items()})
    for k, v in base.items():
        p.on_message(k, v, t)
    p.on_message("ctl/game_heartbeat", "1000000.0", t)
    return p


def main() -> int:
    START, STOP, PACE, NEXT, TUTOR = 0, 1, 2, 3, 7

    print("== keys")
    p = live()
    check(p.on_key(START, 0) == [("game/run/set", "on", 1)], "Start publishes run on")
    check(p.on_key(STOP, 0) == [], "Stop does nothing while stopped")
    check(p.on_key(NEXT, 0) == [], "Next Call does nothing while stopped")
    check(p.on_key(PACE, 0) == [("game/pace/set", "auto", 1)],
          "pacing publishes the next value, absolute")
    check(p.on_key(PACE, 0.3) == [("game/pace/set", "listen", 1)],
          "a second press before the echo moves on from the target (Rev 16)")
    p.on_message("game/pace", "listen", 0.4)
    p.tick(0.4)
    check(p.pace_target is None, "the echo drops the target")
    check(p.on_key(PACE, 0.5) == [("game/pace/set", "manual", 1)],
          "and listen wraps round to manual")
    p.on_message("game/pace", "manual", 0.6)
    p.tick(3.0)

    print("\n== in listen the first dial is pause, the rest rest (Rev 17)")
    q = live(game__pace="listen", game__pause="3", game__gap="20")
    check(q.on_dial(0, 2, 0) == [("game/pause/set", "5", 1)], "dial 1 sets pause, 1s a detent")
    check(q.on_dial(1, 1, 0) == [] and q.on_dial(3, 1, 0) == [], "dials 2-4 do nothing")
    check(q.on_dial(0, 99, 0.2) == [("game/pause/set", "60", 1)], "pause stops at 60")
    q.on_message("game/pace", "auto", 0.3)
    check(q.on_dial(0, 1, 0.4) == [("game/gap/set", "25", 1)],
          "back in auto dial 1 is gap again, from gap's echo, not pause's target")
    check(p.on_key(4, 0) == [] and p.on_key(5, 0) == [], "tally keys publish nothing")

    p.on_message("game/run", "on", 0)
    check(p.on_key(START, 0) == [], "Start ignored while running")

    print("\n== Stop needs a second press within 3s")
    check(p.on_key(STOP, 1.0) == [], "first press only arms")
    check(p.on_key(STOP, 2.0) == [("game/run/set", "off", 1)], "second within 3s stops")
    check(p.on_key(STOP, 3.0) == [], "and disarms: the next press arms again")
    check(p.on_key(STOP, 6.5) == [], "a press after 3s arms, does not stop")

    print("\n== Next Call's guard (4.1)")
    p = live(10, game__run="on")
    check(p.on_key(NEXT, 10) == [("game/next/set", "", 0)], "publishes next at QoS 0")
    check(p.on_key(NEXT, 10.2) == [], "a second press is swallowed")
    p.on_message("game/started", "1", 10.4)
    check(p.on_key(NEXT, 10.5) == [("game/next/set", "", 0)], "started changing re-enables")
    p.on_message("game/error", "next: no scene can be dealt", 10.6)
    check(p.on_key(NEXT, 10.7) == [("game/next/set", "", 0)], "an error re-enables")
    check(p.on_key(NEXT, 12.0) == [], "still guarded at 1.3s")
    p.on_message("ctl/game_heartbeat", "1000003.0", 13)
    check(p.on_key(NEXT, 13.8) == [("game/next/set", "", 0)], "re-enabled after 3s regardless")

    print("\n== dials: a target from the echo, steps added, absolute (7.4)")
    p = live()
    gap, ramp, floor, jitter = range(4)
    check(p.on_dial(gap, 1, 0) == [("game/gap/set", "25", 1)], "gap +1 detent: 20 -> 25")
    check(p.on_dial(gap, 2, 0.1) == [("game/gap/set", "35", 1)],
          "more detents before the echo add to the target, not the echo")
    p.on_message("game/gap", "25", 0.15)
    check(p.on_dial(gap, 1, 0.2) == [("game/gap/set", "40", 1)],
          "a stale intermediate echo does not pull the target back")
    p.on_message("game/gap", "40", 0.3)
    check(p.targets[gap] is None, "the echo equal to the target drops it")
    check(p.on_dial(gap, -1, 0.4) == [("game/gap/set", "35", 1)], "anticlockwise steps down")
    check(p.on_dial(jitter, -3, 0) == [], "jitter at 0 against its stop: nothing published")
    check(p.on_dial(jitter, 20, 0) == [("game/jitter/set", "100", 1)], "jitter clamped at 100")
    check(p.on_dial(ramp, 1, 0) == [("game/ramp/set", "1", 1)], "ramp steps by 1")

    # A value the game clamps differently settles on the echo after 1s.
    p = live()
    p.on_dial(floor, 30, 0)              # floor 5 -> 35, above gap 20
    p.on_message("game/floor", "20", 0.1)
    check(p.targets[floor] is not None, "a clamped echo leaves the target held")
    p.tick(1.2)
    check(p.targets[floor] is None, "and it is dropped 1s after the last detent")
    check(p.on_dial(floor, -1, 1.3) == [("game/floor/set", "19", 1)],
          "the next detent starts from the echo")

    p = live()
    del p.s["game/ramp"]
    check(p.on_dial(ramp, 1, 0) == [], "a dial with nothing echoed does nothing")
    check([d.step for d in DIALS] == [5, 1, 1, 10], "the page's steps: 5, 1, 1, 10")

    print("\n== staleness (7.2)")
    p = live()
    check(not p.game_stale(STALE - 0.1), "fresh within 2.5s of a beat")
    check(p.game_stale(STALE + 0.1), "stale after 2.5s without one")
    check(p.on_key(START, STALE + 0.1) == [], "a stale game: Start does nothing")
    check(p.on_dial(0, 1, STALE + 0.1) == [], "a stale game: dials do nothing")
    p = live(ctl__game_status="offline")
    check(p.on_key(START, 0) == [], "game offline: Start does nothing")
    p = live()
    p.broker_up = False
    check(p.on_key(START, 0) == [], "no broker: Start does nothing")

    print("\n== the error on the strip")
    p = live()
    p.on_message("game/error", "gap: 'x' is not a number", 5)
    check(p.error_until == 10, "shown for 5s when it appears")
    p.on_touch(6)
    check(p.error_until == 0, "a touch on the strip dismisses it")
    p.on_message("game/error", "", 8)
    check(p.error_until == 0, "cleared: the strip has nothing to show")

    print("\n== the tutor key (Rev 29)")
    p = live()
    check(p.on_key(TUTOR, 0) == [], "nothing echoed yet: nothing sent")
    p.on_message("game/tutor", "off", 0)
    check(p.on_key(TUTOR, 0) == [("game/tutor/set", "on", 1)], "off: a press asks for on")
    check(p.get("game/tutor") == "off", "and the key does not change until the echo")
    p.on_message("game/tutor", "on", 0)
    check(p.on_key(TUTOR, 0) == [("game/tutor/set", "off", 1)], "on: a press asks for off")
    check(p.on_key(TUTOR, STALE + 0.1) == [], "a stale game: the key does nothing")

    print("\n== More Help during her introduction (Rev 31)")
    MORE = 6
    p = live()
    check(p.on_key(MORE, 0) == [], "no introduction: the percent key does nothing")
    p.on_message("game/tutor/intro", "1/3", 0)
    check(p.on_key(MORE, 0) == [("game/more/set", "", 0)], "1/3: a press asks for more")
    check(p.on_key(MORE, 0.5) == [], "dark until her next part begins")
    p.on_message("game/tutor/intro", "2/3", 1)
    check(p.on_key(MORE, 1) == [("game/more/set", "", 0)], "2/3: lit again")
    p.on_message("game/tutor/intro", "3/3", 2)
    check(p.on_key(MORE, 2) == [], "3/3: nothing more")

    print("\n== drawing")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        d = Drawer(FileSurface(out))
        for name, p, t in (
                ("stopped", live(), 0),
                ("running", live(game__run="on", game__pace="auto", game__gap_now="15",
                                 game__next_at="1000012", game__success="7",
                                 game__fail="2", game__call__1__scene="x"), 0),
                ("listen", live(game__run="on", game__pace="listen", game__pause="3"), 0),
                ("tutor", live(game__tutor="on"), 0),
                ("intro", live(game__tutor="on", game__tutor__intro="1/3"), 0),
                ("error", live(game__error="floor: 30 is above gap 20; set to 20"), 0),
                ("stale", live(), 10),
                ("no broker", Panel(), 0)):
            try:
                d.forget()
                d.draw(p, t)
                ok = all((out / f"key{i}.png").exists() for i in range(1, 9)) \
                    and (out / "strip.png").exists()
            except Exception as e:
                print(f"      {e!r}")
                ok = False
            check(ok, f"draws: {name}")
        sent = []
        d.surface.set_key = lambda i, im: sent.append(i)
        d.surface.set_strip = lambda im: sent.append("strip")
        p = live()
        d.forget()
        d.draw(p, 0)
        n = len(sent)
        d.draw(p, 0.1)
        check(n == 9 and len(sent) == n, "unchanged images are not sent again")

    print("\n" + ("FAILURES" if failures else "the Stream Deck passed"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
