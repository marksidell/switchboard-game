"""Configuration: the values game_control.md leaves to the game program.

Two kinds live here, and the difference matters.

**Starting values** for things the page can change — pacing (§5.4). They are
what a restart returns to; while the program runs the page owns them, and a
change from the page is not written back here.

**Timeouts and limits** the page never sees (§4). They are play-testing
values, expected to move as games are played, and moving them must not mean
editing code, which is why they are here and not constants in the flows.

Read from a TOML file if one is given, else these defaults. Anything the file
does not mention keeps its default, so a file naming one timeout is a valid
file.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

# The top of the checkout this module is in (engine/sbgame/config.py). An
# installed copy has none, and its configuration names the script instead.
REPO = Path(__file__).resolve().parents[2]
SITE_CONFIG = "/etc/sbgame/game.toml"     # the host's, for the tools that share it


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
    script: str = str(REPO / "script.yml")
    wav_dir: str = "wav"

    # ---- pacing, the starting values (game_control.md §5.4) ------------
    # "manual pacing, gap 20, ramp 1, floor 8, jitter 30"
    pace: str = "manual"
    gap: float = 20.0
    ramp: float = 1.0
    floor: float = 8.0
    jitter: float = 30.0           # percent; 0 is the fixed wait
    pause: float = 3.0             # listen's wait after the board empties
    # Back to tutor after this long stopped in another pacing, so
    # the next visitor finds the game as a newcomer should; 0 never does.
    idle_tutor: float = 300.0
    # Started again within this long of a stop, the game deals on from the
    # shuffle it had rather than shuffling afresh (§6.1); 0 always shuffles.
    resume_within: float = 600.0
    # A running game stops after this long with nothing from the player:
    # no cord, switch, dial or ringing key on the board, no key or button
    # pressed. Start resumes it as a new game. 0 never stops it.
    idle_stop: float = 600.0
    # The loudspeaker plays ringback while a station reports ring.
    ring_cue: bool = True

    # ---- timeouts (§4), all play-testing values ------------------------
    answer_timeout: float = 60.0   # operator to answer a lamp
    # A scenario's calls come every few seconds, and a lamp waits its turn
    # behind the others (§4, §6.5).
    scenario_answer_timeout: float = 90.0
    connect_timeout: float = 90.0  # to connect, after the request has played
    speak_timeout: float = 30.0    # operator to speak when a line waits
    # audio.md §14's cap on one utterance. It is not ours to choose: it must
    # match what sbaudio will allow, or our deadline fires before its does and
    # we call a good line a failure.
    max_speech: float = 20.0
    # Added to every audio deadline, so the audio program's own timeout is
    # always the one that fires first (mqtt.md §8.2).
    audio_margin: float = 3.0

    # ---- the circuits fitted (game_control.md §12.2) ------------
    # The first `stations` of 1-22, with station 24 when it is 22,
    # and the first `trunks` of 1-8. The command line's --stations and
    # --trunks override these.
    stations: int = 22
    trunks: int = 8
    # Out of service: fitted, but not to be rung in on, each with why.
    # game.toml's [out_of_service.trunks], trunk number -> reason, e.g.
    #   6 = "switchboard jack 6's lamp does not latch"
    # and [out_of_service.stations], station number -> reason: no
    # scene calling from or to one is played.
    out_of_service: dict = field(default_factory=dict)
    # The public line (§8): the trunk the Grandstream ATA feeds
    # (trunk_circuit.md 4.5). No scene takes, rings or dials on it; outside
    # free calls come in on it. 0 for none.
    public_trunk: int = 8

    # ---- the public line's ATA (mqtt.md §6.3) ------------------------------
    # The host name of the ATA that feeds the public trunk, which
    # sbgame-netcheck asks for its registration; "" for none.
    ata_host: str = ""

    def stations_out(self) -> frozenset[int]:
        """The fitted stations no scene may use (§12.2)."""
        return frozenset(int(k) for k in (self.out_of_service.get("stations") or {}))

    def fitted_trunks(self) -> range:
        """Every trunk fitted (§12.2), in service or not."""
        return range(1, self.trunks + 1)

    def working_trunks(self) -> list[int]:
        """The fitted trunks a call may ring in on (§12.2)."""
        out = {int(k) for k in (self.out_of_service.get("trunks") or {})}
        return [n for n in self.fitted_trunks() if n not in out and n != self.public_trunk]

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
        # The page's own ranges, §5.4. Applied here too: a configuration file
        # is not the page and is not clamped, it is refused.
        if not 0 <= self.gap <= 600:
            bad.append(f"gap {self.gap} outside 0-600")
        if not 0 <= self.ramp <= 60:
            bad.append(f"ramp {self.ramp} outside 0-60")
        if not 0 <= self.floor <= 600:
            bad.append(f"floor {self.floor} outside 0-600")
        if not 0 <= self.jitter <= 100:
            bad.append(f"jitter {self.jitter} outside 0-100")
        if not 0 <= self.idle_tutor <= 86400:
            bad.append(f"idle_tutor {self.idle_tutor} outside 0-86400")
        if not 0 <= self.resume_within <= 86400:
            bad.append(f"resume_within {self.resume_within} outside 0-86400")
        if not 0 <= self.idle_stop <= 86400:
            bad.append(f"idle_stop {self.idle_stop} outside 0-86400")
        if not 0 <= self.pause <= 60:
            bad.append(f"pause {self.pause} outside 0-60")
        if self.floor > self.gap:
            bad.append(f"floor {self.floor} is above gap {self.gap}")
        for name in ("answer_timeout", "scenario_answer_timeout", "connect_timeout",
                     "speak_timeout", "max_speech"):
            if getattr(self, name) <= 0:
                bad.append(f"{name} must be positive")
        if not isinstance(self.ata_host, str):
            bad.append(f"ata_host {self.ata_host!r} is not a host name")
        if not isinstance(self.ring_cue, bool):
            bad.append(f"ring_cue {self.ring_cue!r} is not true or false")
        if not (isinstance(self.stations, int) and 0 <= self.stations <= 22):
            bad.append(f"stations {self.stations!r} is not a whole number 0-22")
        if not (isinstance(self.public_trunk, int) and 0 <= self.public_trunk <= 8):
            bad.append(f"public_trunk {self.public_trunk!r} is not a trunk 1-8, or 0 for none")
        if not (isinstance(self.trunks, int) and 0 <= self.trunks <= 8):
            bad.append(f"trunks {self.trunks!r} is not a whole number 0-8")
        oos = self.out_of_service
        if not isinstance(oos, dict) or set(oos) - {"trunks", "stations"}:
            bad.append("out_of_service takes only [out_of_service.trunks] and "
                       "[out_of_service.stations] tables")
        else:
            for kind, top in (("trunks", 8), ("stations", 22)):
                for k, v in (oos.get(kind) or {}).items():
                    if not (str(k).isdigit() and (1 <= int(k) <= top
                                                  or (kind == "stations" and int(k) == 24))):
                        bad.append(f"out_of_service.{kind}: {k!r} is not a "
                                   f"{kind[:-1]} 1-{top}" + (" or 24" if kind == "stations" else ""))
                    elif not (isinstance(v, str) and v.strip()):
                        bad.append(f"out_of_service.{kind}.{k}: give the reason as text")
        if bad:
            raise ValueError("; ".join(bad))
