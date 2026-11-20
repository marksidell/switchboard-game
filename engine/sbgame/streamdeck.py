"""The Stream Deck program (game_control.md §10).

An Elgato Stream Deck+ on USB carries the game's controls; the page shows the
game. This drives the deck. It is a process of its own, not part of the game
program, for the page's reason (§1): it reads the bus directly, shows the game
offline rather than going dark with it, and a USB fault cannot touch a game.

Three pieces, so the middle one can be tested without a deck or a broker:

  Panel     the retained topic values, the rules of §11.2 and §10, what a
            press or a detent publishes, and the images to draw. No I/O.
  Surface   where the images go: the deck itself, or PNG files (--fake).
  run()     the broker connection, the deck's callbacks brought onto the
            event loop, and a redraw whenever something changed.

The deck shows only what was echoed (§11.2). A press publishes and changes
nothing on the deck until the game program's state topic changes, with two
exceptions that are local by nature: Stop armed for its second press, and
Next Call dark while its guard holds (§5.1).

One thing it does that is not a publish: the first dial held 3s with no game
running powers the host off, through logind (§10.2).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import aiomqtt
from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger("deck")

PREFIX = "sbgame/"
CLIENT_ID = "sbgame-deck"
USERNAME = "sbgame-deck"                 # mqtt.md §9
PASSWORD_FILE = "/etc/sbgame/mqtt-deck.pass"

STALE = 2.5          # s without a heartbeat (§11.2)
STOP_ARM = 3.0       # Stop's second press (§11.1)
NEXT_GUARD = 3.0     # Next Call re-enables regardless (§5.1)
ERROR_SHOW = 5.0     # an error across the strip (§10)
DIAL_HOLD = 1.0      # a dial's target outlives its last detent by this
RESCAN = 2.0         # look for a deck this often while there is none
DOUBLE = 0.5         # a second press within this is a double press (§11.5)

KEY_PX = 120
STRIP_W, STRIP_H = 800, 100
SEG_W = STRIP_W // 4


@dataclass(frozen=True)
class Dial:
    name: str
    step: float
    lo: float
    hi: float
    unit: str = ""


# Left to right under the strip. The page's steppers and §5.4's ranges.
DIALS = (Dial("gap", 5, 0, 600, "s"), Dial("ramp", 1, 0, 60, "s"),
         Dial("floor", 1, 0, 600, "s"), Dial("jitter", 10, 0, 100, "%"))
# In listen the first dial sets listen's own value and the others rest.
PAUSE = Dial("pause", 1, 0, 60, "s")

# Colours, the page's where it has one (style.css :root).
BG = (22, 24, 28)
PANEL = (33, 36, 43)
INK = (232, 234, 240)
DIM = (153, 160, 173)
GREY = (70, 74, 82)
REST = (92, 97, 107)
OK = (56, 161, 105)
DANGER = (197, 48, 48)
VIOLET = (124, 92, 255)
BLUE = (59, 110, 165)
TEAL = (38, 128, 128)        # the deck's own: sweeps and the tutor's Help keys

# The pacing key cycles in this order and shows all four, the echoed one lit
# (§10), so the choices are on the key and not in the manual.
PACES = (("tutor", "Tutor"), ("manual", "Manual"), ("auto", "Auto"), ("listen", "Listen"))


Command = tuple[str, str, int]           # topic under sbgame/, payload, QoS

# Keys 5 and 6 (0-based 4 and 5), double-pressed: a board sweep (§11.5).
SWEEP_KEYS = {4: "trunks", 5: "stations"}

# Key 5 held this long with no game and no sweep: the switchboard reset,
# game/power_cut/set (§10).
RESET_KEY = 4
RESET_HOLD = 2.0

# The first dial pushed and held this long with no game running: the host
# powers off (§10.2). Longer than the reset's hold; it cannot be undone from
# the deck.
SHUTDOWN_DIAL = 0
SHUTDOWN_HOLD = 3.0
NOTE_SHOW = 5.0      # the deck's own message across the strip


# ---- the panel: state and rules, no I/O ------------------------------------

class Panel:
    """Everything the deck knows and does, driven by explicit times.

    `now` is this machine's monotonic-ish clock in seconds; the tests pass
    their own. Host time, for next_at, comes from the game heartbeat (§11.2).
    """

    def __init__(self) -> None:
        self.s: dict[str, str] = {}      # retained topic values, prefix stripped
        self.broker_up = False
        self.host_offset = 0.0           # host clock minus ours
        self.game_beat: float | None = None   # our clock at the last beat
        self.esp_beat: float | None = None
        self.stop_armed_until = 0.0
        self.next_guard_until = 0.0
        self.more_guard_until = 0.0
        self.repeat_guard_until = 0.0
        self.error_until = 0.0
        # Per dial: [target, time of the last detent], or None when idle.
        self.targets: list[list[float] | None] = [None] * len(DIALS)
        # The pacing key's target, as a dial's: [pace, time of the press].
        self.pace_target: tuple[str, float] | None = None
        # The last press of a sweep key (§11.5): [key, time].
        self.last_sweep_press: tuple[int, float] | None = None
        # When key 5 went down for a switchboard reset, or None.
        self.reset_down: float | None = None
        # When the first dial was pushed for a shutdown, or None; and once
        # sent, the host is going down.
        self.shutdown_down: float | None = None
        self.shutting_down = False
        # The deck's own message on the strip, as an error's: [text, until].
        self.note: tuple[str, float] | None = None

    # -- reading --

    def get(self, k: str) -> str:
        return self.s.get(k, "")

    def num(self, k: str) -> float | None:
        try:
            v = float(self.s[k])
        except (KeyError, ValueError):
            return None
        return v if math.isfinite(v) else None

    def running(self) -> bool:
        return self.get("game/run") == "on"

    def auto(self) -> bool:
        """Automatic pacing, auto or listen: the dials and countdown apply."""
        return self.get("game/pace") in ("auto", "listen")

    def listen(self) -> bool:
        return self.get("game/pace") == "listen"

    def dial(self, i: int) -> Dial | None:
        """What dial i sets now: auto's four, or in listen pause on the first
        and nothing on the rest. Manual turns auto's four, to set them ahead."""
        if self.listen():
            return PAUSE if i == 0 else None
        return DIALS[i]

    def game_stale(self, now: float) -> bool:
        return (not self.broker_up or self.get("ctl/game_status") != "online"
                or (self.game_beat is not None and now - self.game_beat > STALE))

    def esp_stale(self, now: float) -> bool:
        return (not self.broker_up or self.get("ctl/status") != "online"
                or (self.esp_beat is not None and now - self.esp_beat > STALE))

    def audio_stale(self) -> bool:
        return not self.broker_up or self.get("ctl/audio_status") != "online"

    def intro_part(self) -> tuple[int, int] | None:
        """Her introduction's part now, and how many (§7), or None."""
        try:
            n, of = (int(x) for x in self.get("game/tutor/intro").split("/"))
        except ValueError:
            return None
        return n, of

    def more_shown(self) -> bool:
        """Key 8 is More Help: in her introduction, or while a short
        line of hers waits on the player, to hear it in full."""
        return self.intro_part() is not None or bool(self.get("game/tutor/more"))

    def more_live(self, now: float) -> bool:
        if self.game_stale(now) or now < self.more_guard_until:
            return False
        part = self.intro_part()
        if part is not None:
            return part[0] < part[1]
        # As Repeat Help is: dark while she speaks.
        return bool(self.get("game/tutor/more")) and not self.tutor_speaking()

    def flash(self, now: float, *waiting: str) -> bool:
        """Whether a key that flashes while the tutor waits (§7)
        is in its dark half now: once a second, while game/tutor/waiting is
        one of `waiting`."""
        return (self.get("game/tutor/waiting") in waiting and not self.tutor_speaking()
                and int(now * 2) % 2 == 1)

    def tutor_speaking(self) -> bool:
        """Her voice is on the loudspeaker now (audio.md §10.4)."""
        p = self.get("audio/monitor/play")
        return p not in ("", "missing") and not p.startswith("cue.")   # not the ring cue

    def repeat_shown(self) -> bool:
        """Key 7 is Repeat Help (§7)."""
        return bool(self.get("game/tutor/repeat"))

    def repeat_live(self, now: float) -> bool:
        return (self.repeat_shown() and not self.game_stale(now)
                and not self.tutor_speaking() and now >= self.repeat_guard_until)

    def in_progress(self) -> int:
        return sum(1 for n in range(1, 9) if self.get(f"game/call/{n}/scene"))

    # -- the bus --

    def on_message(self, key: str, payload: str, now: float) -> None:
        if key == "ctl/game_heartbeat":
            try:
                self.host_offset = float(payload) - time.time()
            except ValueError:
                pass
            self.game_beat = now
            return
        if key == "ctl/esp_heartbeat":
            self.esp_beat = now
            return
        if key.endswith("/digit"):
            return                       # an event, not state (mqtt.md §7)

        old = self.get(key)
        if payload:
            self.s[key] = payload
        else:
            self.s.pop(key, None)

        if key == "audio/monitor/play" and payload != old and not (
                payload.startswith("cue.") or old.startswith("cue.")):
            self.repeat_guard_until = 0.0  # she began, or finished
        if key in ("game/tutor/intro", "game/tutor/more") and payload != old:
            self.more_guard_until = 0.0  # her next part began, or the line changed
        if key == "game/started" and payload != old:
            self.next_guard_until = 0.0  # the call started (§5.1)
        elif key == "game/error" and payload and payload != old:
            self.next_guard_until = 0.0  # rejected: re-enable (§5.1)
            self.error_until = now + ERROR_SHOW
        elif key == "game/error" and not payload:
            self.error_until = 0.0
        if key == "game/pace" and payload != old:
            # The dials change meaning with the pace: no target carries over.
            self.targets = [None] * len(DIALS)
        for i in range(len(DIALS)):
            d, t = self.dial(i), self.targets[i]
            if d and key == f"game/{d.name}" and t is not None and self.num(key) == t[0]:
                self.targets[i] = None   # the echo caught up

    # -- input --

    def on_key(self, key: int, now: float) -> list[Command]:
        """Key 0-7 pressed. Returns what to publish."""
        if key == 6 and self.repeat_shown():
            # Repeat Help: dark while she speaks, and for a second
            # after a press or until her voice starts, so a double press
            # does not say it twice.
            if not self.repeat_live(now):
                return []
            self.repeat_guard_until = now + 1.0
            return [("game/repeat/set", "", 0)]
        if key == 7 and self.more_shown():
            # More Help while she introduces the board, or on a short line,
            # guarded as Next Call is:
            # dark until her next part begins or the line changes, or 3s.
            if not self.more_live(now):
                return []
            self.more_guard_until = now + NEXT_GUARD
            return [("game/more/set", "", 0)]
        if key == 7:                     # Health: show the error again
            if self.get("game/error"):
                self.error_until = now + ERROR_SHOW
            return []
        if key == RESET_KEY:
            self.reset_down = now if self._reset_allowed(now) else None
        if key in SWEEP_KEYS:
            return self._sweep_key(key, now)
        if key >= 4 or self.game_stale(now):
            return []                    # a greyed key does nothing (§10)
        running = self.running()
        if key == 0:
            return [] if running else [("game/run/set", "on", 1)]
        if key == 1:
            if not running:
                return []
            if now < self.stop_armed_until:
                self.stop_armed_until = 0.0
                return [("game/run/set", "off", 1)]
            self.stop_armed_until = now + STOP_ARM
            return []
        if key == 2:
            # Cycle from the target while presses keep coming, as a dial
            # does, so two fast presses move two places, not one.
            t = self.pace_target
            base = t[0] if t is not None and now - t[1] <= DIAL_HOLD else self.get("game/pace")
            names = [n for n, _ in PACES]
            if base not in names:
                return []                # nothing echoed yet to cycle from
            want = names[(names.index(base) + 1) % len(names)]
            self.pace_target = (want, now)
            return [("game/pace/set", want, 1)]
        if key == 3:
            if not running or now < self.next_guard_until:
                return []
            self.next_guard_until = now + NEXT_GUARD
            return [("game/next/set", "", 0)]
        return []

    def _reset_allowed(self, now: float) -> bool:
        """A hold on key 5 counts only with no sweep and a game program to
        send it to (§10), during a game too."""
        return not (self.game_stale(now) or self.get("game/sweep"))

    def on_key_up(self, key: int, now: float) -> None:
        if key == RESET_KEY:
            self.reset_down = None       # let go sooner: nothing is sent

    def holding_reset(self, now: float) -> float | None:
        """How far through the hold, 0 to 1, or None when not holding."""
        if self.reset_down is None:
            return None
        if not self._reset_allowed(now):
            self.reset_down = None
            return None
        return min(1.0, (now - self.reset_down) / RESET_HOLD)

    def reset_due(self, now: float) -> list[Command]:
        """The hold reached RESET_HOLD: send it, once per hold, while the key
        is still down, so the operator knows when to let go."""
        h = self.holding_reset(now)
        if h is None or h < 1.0:
            return []
        self.reset_down = None
        self.last_sweep_press = None     # the hold was not half a double press
        return [("game/power_cut/set", "on", 1)]

    def _sweep_key(self, key: int, now: float) -> list[Command]:
        """Keys 5 and 6 double-pressed start a board sweep with no game
        running; either double-pressed during one stops it, and so does a
        single press of the running sweep's own key (§11.5). A single
        press otherwise does nothing."""
        if (self.get("game/sweep") == SWEEP_KEYS[key]
                and not self.game_stale(now) and not self.running()):
            self.last_sweep_press = None
            return [("game/sweep/set", "off", 1)]
        last, self.last_sweep_press = self.last_sweep_press, (key, now)
        if last is None or last[0] != key or now - last[1] > DOUBLE:
            return []
        self.last_sweep_press = None
        if self.game_stale(now) or self.running():
            return []
        if self.get("game/sweep"):
            return [("game/sweep/set", "off", 1)]
        return [("game/sweep/set", SWEEP_KEYS[key], 1)]

    def _shutdown_allowed(self, now: float) -> bool:
        """Not while a game runs. With the game program offline it is
        allowed: a hung game program must not keep the host up."""
        return not (self.running() and not self.game_stale(now))

    def on_dial_push(self, dial: int, down: bool, now: float) -> None:
        """Dial 0-3 pushed or let go. Only the first does anything: held, the
        host powers off (§10.2)."""
        if dial != SHUTDOWN_DIAL or self.shutting_down:
            return
        self.shutdown_down = now if down and self._shutdown_allowed(now) else None

    def holding_shutdown(self, now: float) -> float | None:
        """How far through the hold, 0 to 1, or None when not holding."""
        if self.shutdown_down is None:
            return None
        if not self._shutdown_allowed(now):
            self.shutdown_down = None
            return None
        return min(1.0, (now - self.shutdown_down) / SHUTDOWN_HOLD)

    def shutdown_due(self, now: float) -> bool:
        """The hold reached SHUTDOWN_HOLD: true once, while the dial is still
        down, and the caller powers the host off."""
        h = self.holding_shutdown(now)
        if h is None or h < 1.0:
            return False
        self.shutdown_down = None
        self.shutting_down = True
        return True

    def shutdown_failed(self, why: str, now: float) -> None:
        self.shutting_down = False
        self.note = (f"shutdown failed: {why}", now + NOTE_SHOW)

    def on_dial(self, dial: int, detents: int, now: float) -> list[Command]:
        """Dial 0-3 turned by `detents` (negative anticlockwise)."""
        if self.game_stale(now) or detents == 0 or not 0 <= dial < len(DIALS):
            return []
        d = self.dial(dial)
        if d is None:
            return []                    # resting in listen
        t = self.targets[dial]
        if t is None or now - t[1] > DIAL_HOLD:
            base = self.num(f"game/{d.name}")
            if base is None:
                return []                # nothing echoed yet (§10)
        else:
            base = t[0]
        target = min(d.hi, max(d.lo, base + detents * d.step))
        self.targets[dial] = [target, now]
        if target == base:
            return []                    # against a stop
        return [(f"game/{d.name}/set", f"{target:g}", 1)]

    def on_touch(self, now: float) -> None:
        self.error_until = 0.0           # dismiss (§10)
        self.note = None

    def tick(self, now: float) -> None:
        """Expire what times out, so a redraw after it shows the change."""
        for i, t in enumerate(self.targets):
            if t is not None and now - t[1] > DIAL_HOLD:
                self.targets[i] = None
        if self.pace_target is not None and (
                now - self.pace_target[1] > DIAL_HOLD
                or self.get("game/pace") == self.pace_target[0]):
            self.pace_target = None

    # -- drawing --

    def keys(self, now: float) -> list[Image.Image]:
        return [f(now) for f in (self._k_start, self._k_stop, self._k_pace,
                                 self._k_next, self._k_calls, self._k_score,
                                 self._k_pct, self._k_health)]

    def strip(self, now: float) -> Image.Image:
        img = Image.new("RGB", (STRIP_W, STRIP_H), BG)
        d = ImageDraw.Draw(img)
        # The shutdown first: it works without the broker or the game.
        if self.shutting_down:
            d.rectangle((0, 0, STRIP_W, STRIP_H), fill=DANGER)
            _centre(d, (0, 0, STRIP_W, STRIP_H), "Shutting down", 40, INK)
            return img
        if self.note and now < self.note[1]:
            d.rectangle((0, 0, STRIP_W, STRIP_H), fill=(60, 18, 18))
            _wrap(d, (12, 6, STRIP_W - 12, STRIP_H - 6), self.note[0], 26, INK)
            return img
        if (h := self.holding_shutdown(now)) is not None:
            d.rectangle((0, 0, SEG_W, STRIP_H), fill=PANEL)
            _text(d, (14, 8), "hold to", 20, DIM)
            _text(d, (14, 34), "shut down", 34, INK)
            d.rectangle((0, STRIP_H - 8, round(SEG_W * h), STRIP_H), fill=DANGER)
            return img
        if not self.broker_up:
            _centre(d, (0, 0, STRIP_W, STRIP_H), "no broker", 36, DANGER)
            return img
        err = self.get("game/error")
        if err and now < self.error_until:
            d.rectangle((0, 0, STRIP_W, STRIP_H), fill=(60, 18, 18))
            _wrap(d, (12, 6, STRIP_W - 12, STRIP_H - 6), err, 26, INK)
            return img
        stale = self.game_stale(now)
        for i in range(len(DIALS)):
            x0 = i * SEG_W
            if i:
                d.line((x0, 10, x0, STRIP_H - 10), fill=GREY, width=1)
            # In listen the rest show auto's values, dimmer than manual's,
            # since no dial reaches them.
            dl = self.dial(i) or DIALS[i]
            v = self.num(f"game/{dl.name}")
            active = not stale and self.auto() and self.dial(i) is not None
            resting = self.get("game/pace") == "listen" and self.dial(i) is None
            ink = GREY if stale else REST if resting else INK if active else DIM
            _text(d, (x0 + 14, 8), dl.name, 20,
                  GREY if stale else REST if resting else DIM)
            shown = "–" if v is None else f"{v:g}{dl.unit}"
            _text(d, (x0 + 14, 34), shown, 44, ink)
            if dl.name == "gap" and self.running() and self.get("game/pace") == "auto":
                gn = self.num("game/gap_now")
                if gn is not None:
                    _text(d, (x0 + 120, 12), f"now {gn:g}", 18, ink)
        return img

    # Each key: a label, perhaps a second line, a fill that says whether it
    # does anything now.

    def _k_start(self, now: float) -> Image.Image:
        live = not self.game_stale(now) and not self.running()
        return _key("Start", fill=OK if live else PANEL, ink=INK if live else GREY)

    def _k_stop(self, now: float) -> Image.Image:
        live = not self.game_stale(now) and self.running()
        if live and now < self.stop_armed_until:
            return _key("Stop", "again", fill=DANGER, ink=INK)
        return _key("Stop", fill=(90, 30, 30) if live else PANEL,
                    ink=INK if live else GREY)

    def _k_pace(self, now: float) -> Image.Image:
        stale = self.game_stale(now)
        pace = self.get("game/pace")
        img = Image.new("RGB", (KEY_PX, KEY_PX), PANEL if stale else BG)
        d = ImageDraw.Draw(img)
        for i, (name, label) in enumerate(PACES):
            y = 2 + i * 29
            if name == pace and not stale:
                d.rounded_rectangle((4, y, KEY_PX - 4, y + 27), 6, fill=BLUE)
            ink = GREY if stale else (INK if name == pace else DIM)
            _centre(d, (0, y, KEY_PX, y + 27), label,
                    _fit(label, KEY_PX - 18, 21 if name == pace else 17), ink)
        return img

    def _k_next(self, now: float) -> Image.Image:
        live = (not self.game_stale(now) and self.running()
                and now >= self.next_guard_until)
        sub = ""
        if self.running() and self.auto():
            at = self.num("game/next_at")
            sub = "waiting" if at is None else _secs(at - (time.time() + self.host_offset))
        if live and self.flash(now, "more", "next"):
            return _key("Next", sub or "Call", fill=PANEL, ink=INK)
        return _key("Next", sub or "Call", fill=VIOLET if live else PANEL,
                    ink=INK if live else GREY)

    def _tally(self, k: str) -> int:
        v = self.num(k)
        return int(v) if v is not None else 0

    def _k_sweep(self, key: int, now: float) -> Image.Image | None:
        """A sweep key while its sweep runs, from the deck or the page
        (§11.5), else None."""
        kind = SWEEP_KEYS[key]
        if self.get("game/sweep") != kind or self.game_stale(now):
            return None
        return _key("Sweep", kind, fill=TEAL, ink=INK, size=30)

    def _k_calls(self, now: float) -> Image.Image:
        if self.get("ctl/power_cut") == "on":            # whoever sent it
            return _key("Switchboard", "reset", fill=DANGER, ink=INK, size=22)
        if self.get("ctl/power_cut") == "hold":          # off from the page
            return _key("Switchboard", "off", fill=DANGER, ink=INK, size=22)
        if (img := self._k_sweep(4, now)) is not None:
            return img
        if (h := self.holding_reset(now)) is not None:
            img = _key("Hold to", "reset", fill=PANEL, ink=INK)
            ImageDraw.Draw(img).rectangle((0, KEY_PX - 8, round(KEY_PX * h), KEY_PX), fill=DANGER)
            return img
        ink = GREY if self.game_stale(now) else INK
        return _pair(("started", str(self._tally("game/started"))),
                     ("on now", str(self.in_progress())), ink)

    def _k_score(self, now: float) -> Image.Image:
        if (img := self._k_sweep(5, now)) is not None:
            return img
        ink = GREY if self.game_stale(now) else INK
        return _pair(("ok", str(self._tally("game/success"))),
                     ("fail", str(self._tally("game/fail"))), ink)

    def _k_pct(self, now: float) -> Image.Image:
        if self.repeat_shown():          # Repeat Help (§7)
            live = self.repeat_live(now)
            return _key("Repeat", "Help", fill=TEAL if live else PANEL,
                        ink=INK if live else GREY)
        ink = GREY if self.game_stale(now) else INK
        ok, fail = self._tally("game/success"), self._tally("game/fail")
        pct = f"{round(100 * ok / (ok + fail))}%" if ok + fail else "–"
        return _key(pct, "success", fill=BG, ink=ink, size=40)

    def _k_health(self, now: float) -> Image.Image:
        # More Help while the tutor introduces the board, or on a
        # short line of hers.
        if self.more_shown():
            live = self.more_live(now)
            if live and self.flash(now, "more"):
                return _key("More", "Help", fill=PANEL, ink=INK)
            return _key("More", "Help", fill=TEAL if live else PANEL,
                        ink=INK if live else GREY)
        err = bool(self.get("game/error"))
        img = Image.new("RGB", (KEY_PX, KEY_PX), (90, 24, 24) if err else BG)
        d = ImageDraw.Draw(img)
        rows = (("game", self.game_stale(now)), ("ctl", self.esp_stale(now)),
                ("audio", self.audio_stale()))
        for i, (name, stale) in enumerate(rows):
            y = 14 + i * 34
            colour = GREY if not self.broker_up else (DANGER if stale else OK)
            d.ellipse((14, y + 4, 34, y + 24), fill=colour)
            _text(d, (44, y), name, 22, INK)
        return img


# ---- drawing helpers -------------------------------------------------------

_FONTS: dict[int, ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}
_FONT_PATHS = ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def _font(size: int):
    f = _FONTS.get(size)
    if f is None:
        for p in _FONT_PATHS:
            try:
                f = ImageFont.truetype(p, size)
                break
            except OSError:
                continue
        else:
            f = ImageFont.load_default(size=size)
        _FONTS[size] = f
    return f


def _text(d: ImageDraw.ImageDraw, xy, s: str, size: int, fill) -> None:
    d.text(xy, s, font=_font(size), fill=fill)


def _centre(d: ImageDraw.ImageDraw, box, s: str, size: int, fill) -> None:
    x0, y0, x1, y1 = box
    d.text(((x0 + x1) / 2, (y0 + y1) / 2), s, font=_font(size), fill=fill, anchor="mm")


def _fit(s: str, width: int, size: int) -> int:
    """The largest size up to `size` at which `s` fits `width` pixels."""
    while size > 12 and _font(size).getlength(s) > width:
        size -= 2
    return size


def _key(label: str, sub: str = "", *, fill, ink, size: int = 30) -> Image.Image:
    img = Image.new("RGB", (KEY_PX, KEY_PX), fill)
    d = ImageDraw.Draw(img)
    size = _fit(label, KEY_PX - 12, size)
    if sub:
        _centre(d, (0, 10, KEY_PX, 70), label, size, ink)
        _centre(d, (0, 70, KEY_PX, 110), sub, _fit(sub, KEY_PX - 12, 22), ink)
    else:
        _centre(d, (0, 0, KEY_PX, KEY_PX), label, size, ink)
    return img


def _pair(a: tuple[str, str], b: tuple[str, str], ink) -> Image.Image:
    img = Image.new("RGB", (KEY_PX, KEY_PX), BG)
    d = ImageDraw.Draw(img)
    for i, (name, value) in enumerate((a, b)):
        y = i * 60
        _centre(d, (0, y + 2, KEY_PX, y + 38), value, _fit(value, KEY_PX - 10, 34), ink)
        _centre(d, (0, y + 38, KEY_PX, y + 58), name, 16, DIM if ink != GREY else GREY)
    return img


def _wrap(d: ImageDraw.ImageDraw, box, s: str, size: int, fill) -> None:
    """Left-aligned, wrapped on spaces, shrunk until it fits the box."""
    x0, y0, x1, y1 = box
    while True:
        f = _font(size)
        lines, line = [], ""
        for word in s.split():
            trial = f"{line} {word}".strip()
            if f.getlength(trial) <= x1 - x0 or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
        height = len(lines) * (size + 4)
        if height <= y1 - y0 or size <= 14:
            break
        size -= 2
    for i, ln in enumerate(lines):
        d.text((x0, y0 + i * (size + 4)), ln, font=f, fill=fill)


def _secs(v: float) -> str:
    if not math.isfinite(v):
        return "—"
    n = max(0, round(v))
    return f"{n // 60}:{n % 60:02d}" if n >= 60 else f"{n}s"


# ---- surfaces --------------------------------------------------------------

class Surface(Protocol):
    def present(self) -> bool: ...
    def set_key(self, i: int, img: Image.Image) -> None: ...
    def set_strip(self, img: Image.Image) -> None: ...


class FileSurface:
    """--fake: each image to a PNG, for looking at without a deck."""

    def __init__(self, out: Path) -> None:
        self.out = out
        out.mkdir(parents=True, exist_ok=True)

    def present(self) -> bool:
        return True

    def set_key(self, i: int, img: Image.Image) -> None:
        img.save(self.out / f"key{i + 1}.png")

    def set_strip(self, img: Image.Image) -> None:
        img.save(self.out / "strip.png")


class DeckSurface:
    """The Stream Deck+ itself, found and refound by rescan()."""

    def __init__(self, loop: asyncio.AbstractEventLoop, events: asyncio.Queue,
                 brightness: int) -> None:
        self._loop = loop
        self._events = events
        self._brightness = brightness
        self.deck = None

    def present(self) -> bool:
        d = self.deck
        if d is None:
            return False
        try:
            if d.is_open() and d.connected():
                return True
        except Exception:
            pass
        log.warning("deck lost")
        self.close(reset=False)
        return False

    def rescan(self) -> bool:
        """Open the first Stream Deck+ there is. True if one is now open."""
        from StreamDeck.DeviceManager import DeviceManager
        try:
            decks = DeviceManager().enumerate()
        except Exception as e:           # no hidapi, or no permission
            log.debug("enumerate: %s", e)
            return False
        for d in decks:
            if d.deck_type() != "Stream Deck +":
                continue
            try:
                d.open()
                d.reset()
                d.set_brightness(self._brightness)
            except Exception as e:
                log.warning("cannot open %s: %s", d.deck_type(), e)
                continue
            put = self._put
            d.set_key_callback(lambda _d, k, down: put(("key" if down else "keyup", k)))
            d.set_dial_callback(lambda _d, k, ev, v: put(("dial", k, ev.name, v)))
            d.set_touchscreen_callback(lambda _d, ev, v: put(("touch",)))
            self.deck = d
            try:
                serial = d.get_serial_number()
            except Exception:
                serial = "?"
            log.info("deck open: %s, serial %s", d.deck_type(), serial)
            return True
        return False

    def _put(self, ev: tuple) -> None:
        # The library calls back on its own reader thread.
        self._loop.call_soon_threadsafe(self._events.put_nowait, ev)

    def set_key(self, i: int, img: Image.Image) -> None:
        from StreamDeck.ImageHelpers import PILHelper
        d = self.deck
        with d:
            d.set_key_image(i, PILHelper.to_native_key_format(d, img))

    def set_strip(self, img: Image.Image) -> None:
        from StreamDeck.ImageHelpers import PILHelper
        d = self.deck
        with d:
            d.set_touchscreen_image(PILHelper.to_native_touchscreen_format(d, img),
                                    0, 0, STRIP_W, STRIP_H)

    def close(self, reset: bool = True) -> None:
        d, self.deck = self.deck, None
        if d is None:
            return
        try:
            if reset:
                with d:
                    d.reset()            # blank, not controls that do nothing
            d.close()
        except Exception:
            pass


# ---- the program -----------------------------------------------------------

Frame = list[tuple[str, bytes, Image.Image]]     # (key or strip, its pixels, image)


class Drawer:
    """Sends only the images that changed since they were last sent.

    render() reads the Panel, so it runs on the event loop; push() does the
    slow USB writes, on a thread, with images nothing else holds.
    """

    def __init__(self, surface: Surface) -> None:
        self.surface = surface
        self._sent: dict[str, bytes] = {}

    def forget(self) -> None:
        self._sent.clear()               # a new deck: draw everything

    def render(self, panel: Panel, now: float) -> Frame:
        images = [(f"k{i}", img) for i, img in enumerate(panel.keys(now))]
        images.append(("strip", panel.strip(now)))
        out = []
        for name, img in images:
            raw = img.tobytes()
            if self._sent.get(name) != raw:
                out.append((name, raw, img))
        return out

    def push(self, frame: Frame) -> None:
        for name, raw, img in frame:
            if name == "strip":
                self.surface.set_strip(img)
            else:
                self.surface.set_key(int(name[1:]), img)
            self._sent[name] = raw

    def draw(self, panel: Panel, now: float) -> None:
        self.push(self.render(panel, now))


async def run(args: argparse.Namespace) -> int:
    loop = asyncio.get_running_loop()
    events: asyncio.Queue = asyncio.Queue()
    panel = Panel()
    client: aiomqtt.Client | None = None

    if args.fake:
        surface: Surface = FileSurface(Path(args.fake))
        deck = None
    else:
        deck = DeckSurface(loop, events, args.brightness)
        surface = deck
    drawer = Drawer(surface)
    dirty = asyncio.Event()
    dirty.set()

    try:
        password = Path(args.password_file).read_text(encoding="utf-8").strip()
    except OSError as e:
        log.warning("no broker password: %s", e)
        password = None

    async def publish(cmds: list[Command]) -> None:
        for topic, payload, qos in cmds:
            if client is None:
                log.info("no broker; dropped %s", topic)
                return
            log.info("%s %r", topic, payload)
            try:
                await client.publish(PREFIX + topic, payload, qos=qos, retain=False)
            except aiomqtt.MqttError as e:
                # The connection going: broker() reconnects. Not a reason to
                # end the task that pressed the key.
                log.warning("dropped %s: %s", topic, e)
                return

    async def poweroff(now: float) -> None:
        """The host off, through logind; a polkit rule lets this user do it
        (host/etc/polkit-1/rules.d/50-sbgame-deck-poweroff.rules). With
        --fake, only said."""
        if args.fake:
            log.info("shutdown: --fake, not powering off")
            return
        log.warning("shutdown: the first dial held %.0fs; powering the host off", SHUTDOWN_HOLD)
        try:
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "poweroff", stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT)
            out, _ = await proc.communicate()
            if proc.returncode == 0:
                return
            why = out.decode(errors="replace").strip() or f"exit {proc.returncode}"
        except OSError as e:
            why = str(e)
        log.error("shutdown failed: %s", why)
        panel.shutdown_failed(why, time.monotonic())
        dirty.set()

    async def broker() -> None:
        nonlocal client
        delay = 1.0
        while True:
            try:
                async with aiomqtt.Client(
                        hostname=args.broker, port=args.port, username=args.user,
                        password=password, identifier=CLIENT_ID,
                        clean_session=True, keepalive=10) as c:
                    client = c
                    panel.broker_up = True
                    delay = 1.0
                    log.info("connected to %s:%d as %s", args.broker, args.port, args.user)
                    # The retained topics are the whole state (mqtt.md §8.4).
                    await c.subscribe(PREFIX + "#", qos=0)
                    dirty.set()
                    async for msg in c.messages:
                        key = msg.topic.value.removeprefix(PREFIX)
                        p = msg.payload
                        payload = p.decode() if isinstance(p, (bytes, bytearray)) else str(p or "")
                        panel.on_message(key, payload, time.monotonic())
                        dirty.set()
            except aiomqtt.MqttError as e:
                log.warning("mqtt: %s; retrying in %.0fs", e, delay)
            finally:
                client = None
                panel.broker_up = False
                dirty.set()
            await asyncio.sleep(delay)
            delay = min(delay * 2, 10.0)

    async def inputs() -> None:
        while True:
            ev = await events.get()
            now = time.monotonic()
            if ev[0] == "key":
                await publish(panel.on_key(ev[1], now))
            elif ev[0] == "keyup":
                panel.on_key_up(ev[1], now)
            elif ev[0] == "dial" and ev[2] == "TURN":
                await publish(panel.on_dial(ev[1], ev[3], now))
            elif ev[0] == "dial" and ev[2] == "PUSH":
                panel.on_dial_push(ev[1], bool(ev[3]), now)
            elif ev[0] == "touch":
                panel.on_touch(now)
            dirty.set()

    async def drawing() -> None:
        # On every change, and twice a second regardless: countdowns, ages
        # and the timeouts above tick on their own.
        have = False
        while True:
            # Faster while key 5 or the first dial is held, for the bar and
            # the mark.
            held = panel.reset_down is not None or panel.shutdown_down is not None
            wait = 0.1 if held else 0.5
            try:
                await asyncio.wait_for(dirty.wait(), wait)
            except asyncio.TimeoutError:
                pass
            dirty.clear()
            now = time.monotonic()
            panel.tick(now)
            if cmds := panel.reset_due(now):
                await publish(cmds)
            if panel.shutdown_due(now):
                asyncio.create_task(poweroff(now))
            if deck is not None and not deck.present():
                have = False
                if not await asyncio.to_thread(deck.rescan):
                    await asyncio.sleep(RESCAN)
                    continue
            if not have:
                drawer.forget()
                have = True
            try:
                await asyncio.to_thread(drawer.push, drawer.render(panel, now))
            except Exception as e:       # unplugged mid-write
                log.warning("draw: %s", e)
                if deck is not None:
                    deck.close(reset=False)
                have = False

    stopping = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopping.set)

    tasks = [asyncio.create_task(f()) for f in (broker, inputs, drawing)]
    try:
        await stopping.wait()
        log.info("stopping")
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if deck is not None:
            deck.close(reset=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Drive the Stream Deck+ that carries the game's controls "
                    "(game_control.md 10).")
    p.add_argument("--broker", default="localhost")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--user", default=USERNAME)
    p.add_argument("--password-file", default=PASSWORD_FILE)
    p.add_argument("--brightness", type=int, default=60, help="percent, default 60")
    p.add_argument("--fake", metavar="DIR",
                   help="no deck: write the keys and strip as PNGs into DIR")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)-5s %(message)s", datefmt="%H:%M:%S",
        stream=sys.stdout)
    # The library logs every HID report at INFO on its dummy transport.
    logging.getLogger("StreamDeck").setLevel(logging.WARNING)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
