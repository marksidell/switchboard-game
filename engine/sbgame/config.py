"""Configuration: the values game_control.md leaves to the game program.

Two kinds live here, and the difference matters.

**Starting values** for things the page can change — pacing (§4.3). They are
what a restart returns to; while the program runs the page owns them, and a
change from the page is not written back here.

**Timeouts and limits** the page never sees (§5). They are play-testing
values: Mark will move them once he has run games, and moving them must not
mean editing code, which is why they are here and not constants in scenes.py.

Read from a TOML file if one is given, else these defaults. Anything the file
does not mention keeps its default, so a file naming one timeout is a valid
file.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass
class Config:
    # ---- broker (mqtt.md §9) -------------------------------------------
    broker_host: str = "localhost"
    broker_port: int = 1883
    username: str = "sbgame-game"
    # The password file, not the password: /etc/sbgame/mqtt-game.pass, 640,
    # owned by the group the daemon runs as (mqtt.md §9, host/README.md).
    password_file: str = "/etc/sbgame/mqtt-game.pass"

    # ---- the script ----------------------------------------------------
    script: str = "~/s/sbgame/script.yml"
    wav_dir: str = "wav"

    # ---- pacing, the starting values (game_control.md §4.3) ------------
    # "manual pacing, gap 20, ramp 0, floor 5, jitter 0"
    pace: str = "manual"
    gap: float = 20.0
    ramp: float = 0.0
    floor: float = 5.0
    jitter: float = 0.0            # percent (Rev 12); 0 is the fixed wait
    pause: float = 3.0             # listen's wait after the board empties (Rev 17)

    # ---- timeouts (§5), all play-testing values ------------------------
    answer_timeout: float = 60.0   # operator to answer a lamp
    connect_timeout: float = 90.0  # to connect, after the request has played
    speak_timeout: float = 30.0    # operator to speak when a line waits
    # audio.md §14's cap on one utterance. It is not ours to choose: it must
    # match what sbaudio will allow, or our deadline fires before its does and
    # we call a good line a failure.
    max_speech: float = 20.0
    # Added to every audio deadline, so the audio program's own timeout is
    # always the one that fires first (mqtt.md §8.2).
    audio_margin: float = 3.0

    # ---- the circuits fitted (game_control.md §6.5, Rev 25) ------------
    # The first `stations` of 1-22 and the first `trunks` of 1-8. The
    # command line's --stations and --trunks override these.
    stations: int = 22
    trunks: int = 8
    # Out of service (Rev 36): fitted, but not to be rung in on, each with why.
    # game.toml's [out_of_service.trunks], trunk number -> reason, e.g.
    #   6 = "switchboard jack 6's lamp does not latch"
    out_of_service: dict = field(default_factory=dict)

    def working_trunks(self) -> list[int]:
        """The fitted trunks a call may ring in on (§6.5)."""
        out = {int(k) for k in (self.out_of_service.get("trunks") or {})}
        return [n for n in range(1, self.trunks + 1) if n not in out]

    # ---- the session log -----------------------------------------------
    session_db: str = "~/.local/state/sbgame/sessions.db"

    def resolved(self, name: str) -> Path:
        return Path(getattr(self, name)).expanduser()

    @classmethod
    def load(cls, path: str | Path | None) -> "Config":
        c = cls()
        if path is None:
            return c
        p = Path(path).expanduser()
        raw = tomllib.loads(p.read_text(encoding="utf-8"))
        known = {f.name: f.type for f in fields(cls)}
        for k, v in raw.items():
            if k not in known:
                raise ValueError(f"{p}: unknown setting {k!r}")
            setattr(c, k, v)
        c.check()
        return c

    def check(self) -> None:
        """Refuse a configuration that would misbehave rather than fail late."""
        bad: list[str] = []
        from .pacing import PACES
        if self.pace not in PACES:
            bad.append(f"pace must be tutor, manual, auto or listen, not {self.pace!r}")
        # The page's own ranges, §4.3. Applied here too: a configuration file
        # is not the page and is not clamped, it is refused.
        if not 0 <= self.gap <= 600:
            bad.append(f"gap {self.gap} outside 0-600")
        if not 0 <= self.ramp <= 60:
            bad.append(f"ramp {self.ramp} outside 0-60")
        if not 0 <= self.floor <= 600:
            bad.append(f"floor {self.floor} outside 0-600")
        if not 0 <= self.jitter <= 100:
            bad.append(f"jitter {self.jitter} outside 0-100")
        if not 0 <= self.pause <= 60:
            bad.append(f"pause {self.pause} outside 0-60")
        if self.floor > self.gap:
            bad.append(f"floor {self.floor} is above gap {self.gap}")
        for name in ("answer_timeout", "connect_timeout", "speak_timeout", "max_speech"):
            if getattr(self, name) <= 0:
                bad.append(f"{name} must be positive")
        if not (isinstance(self.stations, int) and 0 <= self.stations <= 22):
            bad.append(f"stations {self.stations!r} is not a whole number 0-22")
        if not (isinstance(self.trunks, int) and 0 <= self.trunks <= 8):
            bad.append(f"trunks {self.trunks!r} is not a whole number 0-8")
        oos = self.out_of_service
        if not isinstance(oos, dict) or set(oos) - {"trunks"}:
            bad.append("out_of_service takes only a [out_of_service.trunks] table")
        else:
            for k, v in (oos.get("trunks") or {}).items():
                if not (str(k).isdigit() and 1 <= int(k) <= 8):
                    bad.append(f"out_of_service.trunks: {k!r} is not a trunk 1-8")
                elif not (isinstance(v, str) and v.strip()):
                    bad.append(f"out_of_service.trunks.{k}: give the reason as text")
        if bad:
            raise ValueError("; ".join(bad))
