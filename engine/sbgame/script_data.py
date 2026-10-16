"""script.yml, turned into what the game program needs.

The loader itself is `tts.script`, shared with the speech pipeline
(tts_task.md §3.1, game_control.md §6.3), so the file is validated in one
place and the TTS run and the game cannot disagree about it. This module adds
what only the game needs: each scene as a flow's worth of instructions, and
the jack map the page draws from.

Three things are resolved here rather than in a scene:

  - a line name becomes a circuit id, `station/11` or a trunk taken at the
    time of the call. script.yml names outside lines, not trunks: which trunk
    an outgoing call uses is the operator's choice, and an incoming one is
    the game's.
  - each utterance becomes its wav's base name and its length in seconds,
    read from the file. A flow's deadline is the length plus a margin, so a
    missing wav is a fault at load rather than a timeout mid-call.
  - the shape of the call — one of five — which decides the flow that runs it.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass, field
from pathlib import Path

from tts.script import Script, Utterance, load


class Shape:
    """Which flow runs a scene. game_control.md §4.3's table, by another name."""
    STATION_TO_STATION = "station_to_station"
    STATION_TO_OUTSIDE = "station_to_outside"
    OUTSIDE_TO_STATION = "outside_to_station"
    TO_OPERATOR = "to_operator"
    BUSY = "busy"


@dataclass(frozen=True)
class Speech:
    """One utterance: which wav, how long, and who says it."""
    name: str          # "nbn-valet.3", the wav's base name
    seconds: float
    by: str            # "caller" or "called"
    wait: bool = False # play only after the operator has spoken on that side (§4.6)
    pause: float = 0.0     # seconds of silence first (§4.6, Rev 20)
    ringback: float = 0.0  # seconds of ringback on the trunk first (§4.6, Rev 20)
    operator: str = ""     # the operator line she says before it, if any (§4.7)

    @property
    def filename(self) -> str:
        return f"{self.name}.wav"


@dataclass(frozen=True)
class SceneDef:
    id: str
    shape: str
    from_line: str              # script.yml's line name, for the page and the log
    to_line: str                # "" for a call to the operator
    from_station: int | None    # circuit number if the caller is a station
    to_station: int | None      # circuit number if the callee is a station
    dial: str                   # the number the operator must dial, else ""
    busy: bool
    request: Speech
    conversation: tuple[Speech, ...]
    after: str = ""             # the scene this one follows, else ""
    delay: float = 0.0
    delay_max: float = 0.0      # a range [delay, delay_max] if above delay (Rev 39)
    concurrent: bool = False    # mode: concurrent, starts with the one it follows (§4.4)
    after_handled: int | None = None   # starts a scenario after n handled (§4.10)
    if_busy: tuple[Speech, ...] = ()   # if the called station is engaged (§4.11)
    closing: str = ""           # her closing line's name (§4.7); the caller waits for it (Rev 47)

    @property
    def lines(self) -> tuple[str, ...]:
        """The line names this scene occupies while it runs (§4.4)."""
        return tuple(n for n in (self.from_line, self.to_line) if n)

    @property
    def needs(self) -> tuple[str, ...]:
        """The lines that must be free to deal it: a scene with if_busy: does
        not wait for its called line (§4.11)."""
        return (self.from_line,) if self.if_busy else self.lines


@dataclass(frozen=True)
class Jack:
    """One switchboard jack, for the board/ topics (§6.3)."""
    number: int          # 1-30 for stations, 1-10 for trunks
    kind: str            # "station" or "trunk"
    label: str           # "" for a trunk jack, and for a station jack jacks: does not list
    circuit: str         # "station/11", "trunk/3", or "" if nothing is cabled


@dataclass
class GameScript:
    script: Script
    scenes: dict[str, SceneDef]          # active scenes only
    people: dict[str, tuple[str, str]]   # scene id -> (calling person, called person)
    jacks: tuple[Jack, ...]
    # Tutor mode (§4.9, Rev 29): the tutor's lines whose wavs are here, by
    # key as under tutor:, and the names of those that are not. Not needed to
    # play, so a missing one is not a fault at load; tutor mode is refused.
    tutor: dict[str, Speech] = field(default_factory=dict)
    tutor_missing: tuple[str, ...] = ()
    # The scenes a tutored game starts with, one from each group (§4.9, Rev 30).
    lessons: tuple[tuple[str, ...], ...] = ()

    def jack_of(self, station: int) -> int | None:
        """The switchboard jack station circuit n is cabled to (§6.3)."""
        for j in self.jacks:
            if j.kind == "station" and j.circuit == f"station/{station}":
                return j.number
        return None

    def deck_scenes(self) -> list[str]:
        """Every scene eligible for the deck: those without `after:` (§4.4),
        and not the first scene of a scenario (§4.10)."""
        return [i for i, s in self.scenes.items()
                if not s.after and s.after_handled is None]

    def choosable(self) -> list[str]:
        """What game/scenes lists (§4.8): the deck's, and each scenario's first."""
        return [i for i, s in self.scenes.items() if not s.after]

    def scenarios(self) -> list[SceneDef]:
        """The first scene of each scenario (§4.10), in script order."""
        return [s for s in self.scenes.values() if s.after_handled is not None]

    def needs_people(self, scene_id: str) -> frozenset[str]:
        """The people who must be free to deal it (§4.4, §4.11)."""
        calling, called = self.people[scene_id]
        if self.scenes[scene_id].if_busy:
            called = ""
        return frozenset(p for p in (calling, called) if p)

    def in_scenario(self, scene_id: str) -> bool:
        """Whether the scene is a scenario's first or one of its concurrent
        followers down the chain (§4.10)."""
        sc = self.scenes.get(scene_id)
        while sc is not None:
            if sc.after_handled is not None:
                return True
            if not sc.concurrent:
                return False
            sc = self.scenes.get(sc.after)
        return False

    def followers(self, scene_id: str) -> list[SceneDef]:
        return [s for s in self.scenes.values() if s.after == scene_id]


def _wav_seconds(wav_dir: Path, name: str) -> float:
    """How long the utterance runs, from the file itself.

    The flow's deadline is this plus a margin. Reading it here means a missing
    or unreadable wav is a fault at startup, with the name of the file, rather
    than a call that fails on a timeout with nothing to say why.
    """
    p = wav_dir / f"{name}.wav"
    with wave.open(str(p), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def _shape(scene: dict, stations: dict, outside: dict) -> str:
    called = scene.get("called")
    if called is None:
        return Shape.TO_OPERATOR
    if called.get("busy"):
        return Shape.BUSY
    calling_is_station = scene["calling"]["line"] in stations
    called_is_station = called["line"] in stations
    if calling_is_station and called_is_station:
        return Shape.STATION_TO_STATION
    if calling_is_station and not called_is_station:
        return Shape.STATION_TO_OUTSIDE
    return Shape.OUTSIDE_TO_STATION


def build(script_path: str | Path, wav_dir: str | Path) -> GameScript:
    """Load script.yml and resolve everything the flows and the page need."""
    s = load(script_path)
    wav = Path(wav_dir).expanduser()
    stations, outside = s.stations, s.outside

    def speech(u: Utterance, by: str) -> Speech:
        return Speech(u.name, _wav_seconds(wav, u.name), by, u.wait, u.pause,
                      u.ringback, u.operator)

    scenes: dict[str, SceneDef] = {}
    people: dict[str, tuple[str, str]] = {}
    # Only active scenes are built, so an inactive one needs no wavs (§4.4).
    for sid, raw in s.active_scenes().items():
        us = s.scene_lines(sid)          # the operator's own lines are not played
        req = us[0]
        calling, called = raw["calling"], raw.get("called")
        shape = _shape(raw, stations, outside)
        to_line = called["line"] if called else ""
        conv = []
        for u in us[1:]:
            conv.append(speech(u, u.role))
        delay = raw.get("delay", 0) or 0
        lo, hi = (delay if isinstance(delay, list) else (delay, delay))
        scenes[sid] = SceneDef(
            id=sid, shape=shape,
            from_line=calling["line"], to_line=to_line,
            from_station=(stations.get(calling["line"]) or {}).get("number"),
            to_station=(stations.get(to_line) or {}).get("number") if to_line else None,
            dial=str((outside.get(to_line) or {}).get("number", "")) if to_line in outside else "",
            busy=bool(called and called.get("busy")),
            request=speech(req, "caller"),
            conversation=tuple(conv),
            after=raw.get("after", "") or "",
            delay=float(lo), delay_max=float(hi),
            concurrent=raw.get("mode") == "concurrent",
            after_handled=raw.get("after_handled"),
            if_busy=tuple(speech(u, "caller") for u in s.busy_lines(sid)),
            closing=s.closings.get(sid, ""),
        )
        people[sid] = (calling.get("person", ""), (called or {}).get("person", ""))

    tutor: dict[str, Speech] = {}
    missing: list[str] = []
    for key, u in s.tutor.items():
        try:
            tutor[key] = Speech(u.name, _wav_seconds(wav, u.name), "tutor")
        except (OSError, EOFError, wave.Error):
            missing.append(u.name)

    return GameScript(script=s, scenes=scenes, people=people, jacks=_jacks(s),
                      tutor=tutor, tutor_missing=tuple(missing),
                      lessons=tuple(tuple(g) for g in s.lessons))


N_STATIONS, N_TRUNKS = 22, 8


def needs_trunk(sc: SceneDef) -> bool:
    """Whether the scene rings in or goes out on a trunk."""
    return sc.from_station is None or (sc.shape != Shape.TO_OPERATOR and sc.to_station is None)


def fit(gs: GameScript, stations: int = N_STATIONS, trunks: int = N_TRUNKS,
        out: frozenset[int] = frozenset()) -> tuple[GameScript, list[str]]:
    """The game fitted to the circuits built (game_control.md §6.5, Rev 25).

    Leaves out a scene whose calling or called station is numbered above
    `stations` or is out of service (`out`, Rev 43), or that needs a trunk
    when `trunks` is 0, and every `after:` scene down the chain from one left
    out. Returns the fitted script and a line saying why for each scene left
    out.
    """
    why: dict[str, str] = {}
    for sid, sc in gs.scenes.items():
        used = [n for n in (sc.from_station, sc.to_station) if n is not None]
        high = [n for n in used if n > stations]
        down = [n for n in used if n in out]
        if high:
            why[sid] = f"station {max(high)} is not fitted"
        elif down:
            why[sid] = f"station {min(down)} is out of service"
        elif trunks == 0 and needs_trunk(sc):
            why[sid] = "no trunk is fitted"
    changed = True
    while changed:                                   # down the after: chains
        changed = False
        for sid, sc in gs.scenes.items():
            if sid not in why and sc.after in why:
                why[sid] = f"it follows {sc.after}, left out"
                changed = True
    keep = {i: s for i, s in gs.scenes.items() if i not in why}
    fitted = GameScript(script=gs.script, scenes=keep,
                        people={i: p for i, p in gs.people.items() if i in keep},
                        jacks=gs.jacks, tutor=gs.tutor, tutor_missing=gs.tutor_missing,
                        # A lesson left out goes from its group; an emptied
                        # group goes altogether (§6.5).
                        lessons=tuple(g for g in (tuple(i for i in grp if i in keep)
                                                  for grp in gs.lessons) if g))
    return fitted, [f"{i}: {w}" for i, w in why.items()]


def _jacks(s: Script) -> tuple[Jack, ...]:
    """The board map (§6.3): 30 station jacks and 10 trunk jacks.

    Station jacks come from script.yml's jacks:. A listed jack has a label
    whether or not a station is cabled to it, and the page draws a labelled
    jack with no circuit as a working one at rest. A jack jacks: does not
    list is drawn as an empty outline, so the board keeps its shape. Trunk
    circuit n is on trunk jack n for n = 1-8, fixed; jacks 9 and 10 carry
    nothing and no trunk jack has a label.
    """
    by_jack: dict[int, tuple[str, str]] = {}
    for entry in s.jacks:
        station = entry["station"]
        circuit = f"station/{s.stations[station]['number']}" if station else ""
        by_jack[entry["jack"]] = (entry["label"], circuit)

    out = []
    for n in range(1, 31):
        label, circuit = by_jack.get(n, ("", ""))
        out.append(Jack(n, "station", label, circuit))
    for n in range(1, 11):
        out.append(Jack(n, "trunk", "", f"trunk/{n}" if n <= 8 else ""))
    return tuple(out)
