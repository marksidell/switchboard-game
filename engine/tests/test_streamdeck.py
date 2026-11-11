"""The Stream Deck program's rules, without a deck or a broker.

Panel is driven directly with explicit times, so every rule of §10 can be
checked: what each key publishes and when it does nothing, Stop's second
press, Next Call's guard, the dials' target, the error on the strip, and
staleness. Then the images are drawn once through a FileSurface, so a drawing
error shows up here rather than on the deck.
"""

import pytest

from sbgame.streamdeck import DIALS, Drawer, FileSurface, Panel, STALE

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


START, STOP, PACE, NEXT, HEALTH, MORE = 0, 1, 2, 3, 7, 7


def after_the_keys() -> Panel:
    """Each key pressed on a stopped game, and the pacing cycled round."""
    p = live()
    assert p.on_key(START, 0) == [("game/run/set", "on", 1)], "Start publishes run on"
    assert p.on_key(STOP, 0) == [], "Stop does nothing while stopped"
    assert p.on_key(NEXT, 0) == [], "Next Call does nothing while stopped"
    assert p.on_key(PACE, 0) == [("game/pace/set", "auto", 1)], "pacing publishes the next value, absolute"
    assert p.on_key(PACE, 0.3) == [("game/pace/set", "listen", 1)], "a second press before the echo moves on from the target"
    p.on_message("game/pace", "listen", 0.4)
    p.tick(0.4)
    assert p.pace_target is None, "the echo drops the target"
    assert p.on_key(PACE, 0.5) == [("game/pace/set", "tutor", 1)], "and listen wraps round to tutor, first"
    p.on_message("game/pace", "tutor", 0.55)
    p.tick(0.55)
    assert p.on_key(PACE, 0.56) == [("game/pace/set", "manual", 1)], "then manual"
    p.on_message("game/pace", "manual", 0.6)
    p.tick(3.0)
    return p


def test_keys():
    p = after_the_keys()
    assert p.on_key(4, 0) == [] and p.on_key(5, 0) == [], "tally keys publish nothing"


def test_in_listen_the_first_dial_is_pause_the_rest_rest():
    """In listen the first dial is pause, the rest rest."""
    q = live(game__pace="listen", game__pause="3", game__gap="20")
    assert q.on_dial(0, 2, 0) == [("game/pause/set", "5", 1)], "dial 1 sets pause, 1s a detent"
    assert q.on_dial(1, 1, 0) == [] and q.on_dial(3, 1, 0) == [], "dials 2-4 do nothing"
    assert q.on_dial(0, 99, 0.2) == [("game/pause/set", "60", 1)], "pause stops at 60"
    q.on_message("game/pace", "auto", 0.3)
    assert q.on_dial(0, 1, 0.4) == [("game/gap/set", "25", 1)], "back in auto dial 1 is gap again, from gap's echo, not pause's target"


def test_the_ring_cue_is_not_her_voice():
    """The ring cue is not her voice (§9.2)."""
    c = live()
    c.on_message("audio/monitor/play", "cue.ringback", 0)
    assert not c.tutor_speaking(), "the cue on the monitor is not the tutor speaking"
    c.on_message("audio/monitor/play", "tutor.answer-station", 0)
    assert c.tutor_speaking(), "her line is"


def test_board_sweeps():
    """Board sweeps (§11.5)."""
    w = live()
    w.game_stale = lambda now: False     # the heartbeat is not what is under test
    assert w.on_key(4, 0) == [], "key 5 once does nothing"
    assert w.on_key(4, 0.3) == [("game/sweep/set", "trunks", 1)], "key 5 twice: trunks"
    assert w.on_key(4, 0.4) == [], "a third press is a first press again"
    assert w.on_key(5, 1.0) == [] and w.on_key(5, 1.7) == [], "presses 0.7s apart are two singles"
    assert w.on_key(4, 2.0) == [] and w.on_key(5, 2.2) == [], "one on each key is not a double"
    assert w.on_key(5, 3.0) == [] and w.on_key(5, 3.4) == [("game/sweep/set", "stations", 1)], "key 6 twice: stations"
    assert w._k_sweep(5, 3.4) is None, "nothing shown until the game echoes it"
    w.on_message("game/sweep", "stations", 3.5)
    assert w._k_sweep(5, 3.5) is not None and w._k_sweep(4, 3.5) is None, "key 6 shows the station sweep, however it was started"
    assert w.on_key(4, 4.0) == [] and w.on_key(4, 4.2) == [("game/sweep/set", "off", 1)], "the other key twice stops it"
    assert w.on_key(5, 4.21) == [("game/sweep/set", "off", 1)], "its own key once stops it"
    w.on_message("game/sweep", "trunks", 4.25)
    assert w._k_sweep(4, 4.25) is not None and w._k_sweep(5, 4.25) is None, "key 5 the trunk sweep"
    assert w.on_key(4, 4.27) == [("game/sweep/set", "off", 1)], "key 5 once stops the trunk sweep"
    w.on_message("game/sweep", "", 4.3)
    assert w._k_sweep(4, 4.3) is None, "gone when it ends"
    w.on_message("game/run", "on", 4.3)
    assert w.on_key(4, 5.0) == [] and w.on_key(4, 5.2) == [], "nothing while a game runs"


def test_switchboard_reset_key_5_held_2s():
    """Switchboard reset: key 5 held 2s (§10)."""
    r = live()
    r.game_stale = lambda now: False
    assert r.on_key(4, 10.0) == [], "the press sends nothing"
    assert r.holding_reset(11.0) == 0.5, "half way at 1s"
    assert r.reset_due(11.9) == [], "nothing before 2s"
    assert r.reset_due(12.0) == [("game/power_cut/set", "on", 1)], "at 2s, still held: power_cut"
    assert r.reset_due(12.5) == [] and r.reset_down is None, "once per hold"
    r.on_key_up(4, 12.6)
    assert r.on_key(4, 12.8) == [], "a press after the hold is a first press, not a double"
    r.on_key_up(4, 13.0)
    assert r.reset_due(15.0) == [] and r.reset_down is None, "let go sooner: nothing"
    r.on_message("ctl/power_cut", "on", 15.0)
    assert r._k_calls(15.0).getpixel((5, 5)) == (197, 48, 48), "red while the cut is on"
    r.on_message("ctl/power_cut", "hold", 15.5)
    assert r._k_calls(15.5).getpixel((5, 5)) == (197, 48, 48), "and while it is held"
    r.on_message("ctl/power_cut", "off", 16.0)
    r.on_key(4, 20.0); r.on_key_up(4, 20.1); r.on_key(4, 20.2)
    assert r.last_sweep_press is None, "a quick second press is still the trunk sweep"
    r.on_message("game/sweep", "trunks", 20.3)
    r.on_key(4, 21.0)
    assert r.reset_down is None, "no hold while a sweep runs"
    r.on_message("game/sweep", "", 22.0)
    r.on_message("game/run", "on", 23.0)
    r.on_key(4, 24.0)
    assert r.reset_due(26.0) == [("game/power_cut/set", "on", 1)], "and while a game runs"


def test_stop_needs_a_second_press_within_3s():
    """Stop needs a second press within 3s."""
    p = after_the_keys()
    p.on_message("game/run", "on", 0)
    assert p.on_key(START, 0) == [], "Start ignored while running"
    assert p.on_key(STOP, 1.0) == [], "first press only arms"
    assert p.on_key(STOP, 2.0) == [("game/run/set", "off", 1)], "second within 3s stops"
    assert p.on_key(STOP, 3.0) == [], "and disarms: the next press arms again"
    assert p.on_key(STOP, 6.5) == [], "a press after 3s arms, does not stop"


def test_next_call_guard():
    """Next Call's guard (§10)."""
    p = live(10, game__run="on")
    assert p.on_key(NEXT, 10) == [("game/next/set", "", 0)], "publishes next at QoS 0"
    assert p.on_key(NEXT, 10.2) == [], "a second press is swallowed"
    p.on_message("game/started", "1", 10.4)
    assert p.on_key(NEXT, 10.5) == [("game/next/set", "", 0)], "started changing re-enables"
    p.on_message("game/error", "next: no scene can be dealt", 10.6)
    assert p.on_key(NEXT, 10.7) == [("game/next/set", "", 0)], "an error re-enables"
    assert p.on_key(NEXT, 12.0) == [], "still guarded at 1.3s"
    p.on_message("ctl/game_heartbeat", "1000003.0", 13)
    assert p.on_key(NEXT, 13.8) == [("game/next/set", "", 0)], "re-enabled after 3s regardless"


def test_dials_a_target_from_the_echo_steps_added_absolute():
    """Dials: a target from the echo, steps added, absolute (§10)."""
    p = live()
    gap, ramp, floor, jitter = range(4)
    assert p.on_dial(gap, 1, 0) == [("game/gap/set", "25", 1)], "gap +1 detent: 20 -> 25"
    assert p.on_dial(gap, 2, 0.1) == [("game/gap/set", "35", 1)], "more detents before the echo add to the target, not the echo"
    p.on_message("game/gap", "25", 0.15)
    assert p.on_dial(gap, 1, 0.2) == [("game/gap/set", "40", 1)], "a stale intermediate echo does not pull the target back"
    p.on_message("game/gap", "40", 0.3)
    assert p.targets[gap] is None, "the echo equal to the target drops it"
    assert p.on_dial(gap, -1, 0.4) == [("game/gap/set", "35", 1)], "anticlockwise steps down"
    assert p.on_dial(jitter, -3, 0) == [], "jitter at 0 against its stop: nothing published"
    assert p.on_dial(jitter, 20, 0) == [("game/jitter/set", "100", 1)], "jitter clamped at 100"
    assert p.on_dial(ramp, 1, 0) == [("game/ramp/set", "1", 1)], "ramp steps by 1"

    # A value the game clamps differently settles on the echo after 1s.
    p = live()
    p.on_dial(floor, 30, 0)              # floor 5 -> 35, above gap 20
    p.on_message("game/floor", "20", 0.1)
    assert p.targets[floor] is not None, "a clamped echo leaves the target held"
    p.tick(1.2)
    assert p.targets[floor] is None, "and it is dropped 1s after the last detent"
    assert p.on_dial(floor, -1, 1.3) == [("game/floor/set", "19", 1)], "the next detent starts from the echo"

    p = live()
    del p.s["game/ramp"]
    assert p.on_dial(ramp, 1, 0) == [], "a dial with nothing echoed does nothing"
    assert [d.step for d in DIALS] == [5, 1, 1, 10], "the page's steps: 5, 1, 1, 10"


def test_staleness():
    """Staleness (§10)."""
    p = live()
    assert not p.game_stale(STALE - 0.1), "fresh within 2.5s of a beat"
    assert p.game_stale(STALE + 0.1), "stale after 2.5s without one"
    assert p.on_key(START, STALE + 0.1) == [], "a stale game: Start does nothing"
    assert p.on_dial(0, 1, STALE + 0.1) == [], "a stale game: dials do nothing"
    p = live(ctl__game_status="offline")
    assert p.on_key(START, 0) == [], "game offline: Start does nothing"
    p = live()
    p.broker_up = False
    assert p.on_key(START, 0) == [], "no broker: Start does nothing"


def test_the_error_on_the_strip():
    """The error on the strip."""
    p = live()
    p.on_message("game/error", "gap: 'x' is not a number", 5)
    assert p.error_until == 10, "shown for 5s when it appears"
    p.on_touch(6)
    assert p.error_until == 0, "a touch on the strip dismisses it"
    p.on_message("game/error", "", 8)
    assert p.error_until == 0, "cleared: the strip has nothing to show"


def test_key_8_health_but_more_help_while_the_tutor_introduces():
    """Key 8: Health, but More Help while the tutor introduces."""
    p = live()
    p.on_message("game/error", "gap: 'x' is not a number", 5)
    p.on_touch(6)
    p.on_key(HEALTH, 7)
    assert p.error_until == 12, "Health shows the error again"
    p.on_message("game/error", "", 8)
    assert p.error_until == 0 and p.on_key(HEALTH, 9) == [] and p.error_until == 0, "cleared: Health has nothing to show"


def test_more_help_during_her_introduction():
    """More Help during her introduction."""
    p = live()
    assert p.on_key(MORE, 0) == [], "no introduction: key 8 publishes nothing"
    p.on_message("game/tutor/intro", "1/3", 0)
    assert p.on_key(MORE, 0) == [("game/more/set", "", 0)], "1/3: a press asks for more"
    assert p.on_key(MORE, 0.5) == [], "dark until her next part begins"
    p.on_message("game/tutor/intro", "2/3", 1)
    assert p.on_key(MORE, 1) == [("game/more/set", "", 0)], "2/3: lit again"
    p.on_message("game/tutor/intro", "3/3", 2)
    assert p.on_key(MORE, 2) == [], "3/3: nothing more"


def test_more_help_on_a_short_line():
    """More Help on a short line."""
    p = live(game__run="on", game__pace="tutor")
    assert p.on_key(MORE, 0) == [], "no short line: key 8 publishes nothing"
    p.on_message("game/tutor/more", "answer-station", 0)
    assert p.more_shown() and p.on_key(MORE, 0) == [("game/more/set", "", 0)], "a short line waiting: key 8 is More Help, and a press asks"
    assert p.on_key(MORE, 0.5) == [], "dark after a press"
    p.on_message("game/tutor/more", "", 0.6)
    assert not p.more_shown(), "said in full: key 8 is Health again"
    p.on_message("game/tutor/more", "talk", 1)
    p.on_message("audio/monitor/play", "brief.talk", 1)
    assert p.on_key(MORE, 1.1) == [], "dark while she speaks"


def test_repeat_help_on_key_7():
    """Repeat Help on key 7."""
    REPEAT = 6
    p = live(game__run="on", game__pace="tutor")
    assert p.on_key(REPEAT, 0) == [], "nothing to repeat: the percent key does nothing"
    p.on_message("game/tutor/repeat", "answer-station", 0)
    assert p.on_key(REPEAT, 0) == [("game/repeat/set", "", 0)], "a line to repeat: a press asks"
    assert p.on_key(REPEAT, 0.3) == [], "dark for a second after"
    p.on_message("audio/monitor/play", "tutor.answer-station", 0.4)
    assert p.on_key(REPEAT, 1.5) == [], "and while she speaks"
    p.on_message("audio/monitor/play", "", 2)
    assert p.on_key(REPEAT, 2) == [("game/repeat/set", "", 0)], "lit again once she has finished"
    p.on_message("game/tutor/repeat", "", 2.1)
    assert p.on_key(REPEAT, 2.2) == [], "the player acted: nothing to repeat"


def test_flashing_while_the_tutor_waits():
    """Flashing while the tutor waits."""
    p = live(game__run="on", game__pace="tutor", game__tutor__intro="1/3")
    lit = [p._k_next(t).getpixel((5, 5)) for t in (0.1, 0.6)]
    assert lit[0] == lit[1], "she is speaking: Next Call steady"
    p.on_message("game/tutor/waiting", "more", 1)
    nx = [p._k_next(t).getpixel((5, 5)) for t in (1.1, 1.6, 2.1)]
    mh = [p._k_health(t).getpixel((5, 5)) for t in (1.1, 1.6, 2.1)]
    assert nx[0] != nx[1] and nx[0] == nx[2], "she waits for either: Next Call flashes once a second"
    assert mh[0] != mh[1] and mh[0] == mh[2], "and More Help with it"
    p.on_message("ctl/game_heartbeat", "1000003", 3)
    p.on_message("game/tutor/intro", "3/3", 3)
    p.on_message("game/tutor/waiting", "next", 3)
    mh = [p._k_health(t).getpixel((5, 5)) for t in (3.1, 3.6)]
    nx = [p._k_next(t).getpixel((5, 5)) for t in (3.1, 3.6)]
    assert nx[0] != nx[1] and mh[0] == mh[1], "Next Call alone: only Next Call flashes"


STATES = {
    "stopped": (dict(), 0),
    "running": (dict(game__run="on", game__pace="auto", game__gap_now="15",
                     game__next_at="1000012", game__success="7",
                     game__fail="2", game__call__1__scene="x"), 0),
    "listen": (dict(game__run="on", game__pace="listen", game__pause="3"), 0),
    "tutor": (dict(game__pace="tutor"), 0),
    "intro": (dict(game__pace="tutor", game__tutor__intro="1/3"), 0),
    "repeat": (dict(game__pace="tutor", game__tutor__repeat="talk"), 0),
    "error": (dict(game__error="floor: 30 is above gap 20; set to 20"), 0),
    "stale": (dict(), 10),
    "no broker": (None, 0),
}


@pytest.mark.parametrize("name", STATES)
def test_drawing(tmp_path, name):
    """Each state draws every key and the strip."""
    state, t = STATES[name]
    p = Panel() if state is None else live(**state)
    Drawer(FileSurface(tmp_path)).draw(p, t)
    assert all((tmp_path / f"key{i}.png").exists() for i in range(1, 9))
    assert (tmp_path / "strip.png").exists()


def test_unchanged_images_not_sent_again(tmp_path):
    d = Drawer(FileSurface(tmp_path))
    sent = []
    d.surface.set_key = lambda i, im: sent.append(i)
    d.surface.set_strip = lambda im: sent.append("strip")
    p = live()
    d.draw(p, 0)
    n = len(sent)
    d.draw(p, 0.1)
    assert n == 9 and len(sent) == n, "unchanged images are not sent again"
