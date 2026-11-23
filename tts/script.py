"""Loader and validation for the game script, script.yml (tts_task.md 3.1).

Read by the TTS pipeline and imported by the game program (engine/), so the
public surface is small and typed: `load()` returns a `Script`, or raises
`ScriptError` carrying every failure found rather than only the first.

    from tts.script import load
    script = load()
    for u in script.utterances:
        ...
"""

from __future__ import annotations

import csv
import string
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Iterator

from ruamel.yaml import YAML
from ruamel.yaml.constructor import DuplicateKeyError

# The script is at the top of the repo, shared with the game program (engine/).
DEFAULT_SCRIPT = Path(__file__).resolve().parent.parent / "script.yml"

# audio.md 7.1 / mqtt.md 7: the constraints on a playable file name.
MAX_NAME = 31
FORBIDDEN_IN_NAME = ("/", "\\", "..")
RESERVED_NAME = "stop"

# Stations run 1..22, and 24, the real telephone (docs/real_phone.md). Slot
# 23 is the operator tap and is not a station.
MIN_STATION, MAX_STATION = 1, 22
PHONE_STATION = 24

# The switchboard's own jacks, which are not the game's circuits: 30 station
# jacks and 10 trunk jacks (game_control.md 12.1). Which circuit is cabled to
# which jack, and what every jack is labelled, changes when the board is
# recabled, so it lives in script.yml's jacks: rather than here.
MIN_JACK, MAX_JACK = 1, 30

# A conversation line's pause: and ringback:, in seconds (game_control.md 6.2).
MAX_PAUSE, MAX_RINGBACK = 30, 30

# The player's own lines (game_control.md 6.3). The game never plays
# them — the person at the board says them — but the TTS run renders them in
# this cast member's voice, for recordings of whole conversations
# (tts/scenes --batch). `operator` in the cast is the long-distance operator.
HOTEL_OPERATOR = "hotel_operator"
# The stock lines under operator_lines: are named operator.<id>, as if they
# were a scene of that name, so no scene may take it.
OPERATOR_SCENE = "operator"

# Tutor mode's lines (game_control.md 7), under tutor:, are said by
# this cast member and named tutor.<key>, so no scene may take the name. Each
# key is listed with the one placeholder it takes, if any; a template is
# rendered once per value (see _tutor_lines()).
TUTOR = "tutor"
TUTOR_KEYS: dict[str, str | None] = {
    "intro-jacks": None, "intro-cords": None, "intro-switches": None,
    "answer-station": None, "answer-trunk": None, "talk": None,
    "say": "line", "greet": None, "respond": None, "for-you": None, "stuck": None,
    "ring-front": "jack", "ring-rear": "jack", "center-ringing": None,
    "trunk-front": None, "dial": "number", "dial-operator": None,
    "center-dialled": None, "center": None, "busy-heard": None,
    "hangup-pair": None, "hangup-one": None, "ready-manual": None,
    # Ringing the wrong cord, in every pacing (game_control.md 7.7).
    "rang-trunk": None, "rang-outside": None, "rang-caller": None,
    "rear-in-trunk": None,
}
# What a party says when the operator leaves them hanging (game_control.md
# 5), under a top-level reactions:, one text each, rendered in every
# cast member's voice but the player's and the tutor's, as <kind>.<speaker>:
#   nudge  - the operator has not spoken where they wait for her
#   hello  - they have answered and nobody is on the line
#   wrong  - the operator has put them through to the wrong party
#   giveup - after a wrong number, she has come back to them a second time
REACTIONS = ("nudge", "hello", "wrong", "giveup")
# Free calls, Lenny mode (game_control.md 8), under freecall:,
# per cast member: a greeting:, the lines: said once in order, and the loop:
# said round and round after them. Named free.<cast>.g for the greeting and
# free.<cast>.<n>, 1 up, for the rest in the order they are said.
FREE = "free"
FREE_KEYS = ("greeting", "lines", "loop")

# The lines that may be given a short form under tutor: brief:, said
# from the third call she tutors on: brief-<key> in Script.tutor, and named
# brief.<key>, since tutor.brief-<key> runs past the 31 characters a name may
# have for the longest jack labels. So no scene may be called brief either. Not her introduction, and
# not the prompts before the operator speaks: a listen follows those, and
# More Help is not offered while the game listens.
BRIEF = "brief"
BRIEF_PREFIX = "brief-"
# Shorter still, from the third time on (Rev 119): terse.<key>, under
# tutor: terse:, for the same lines as brief:.
TERSE = "terse"
TERSE_PREFIX = "terse-"
SHORT = ((BRIEF, BRIEF_PREFIX), (TERSE, TERSE_PREFIX))
BRIEF_KEYS = tuple(k for k in TUTOR_KEYS
                   if not k.startswith(("intro-", "rang-", "rear-"))
                   and k not in ("say", "greet", "respond", "stuck"))
# The 1958 exchanges, for saying a number as the operator's card prints it
# (hardcopy/cards.py reads the same file). Not installed on the host, where
# only the names of the tutor's lines matter; the digits are said alone then.
EXCHANGES = Path(__file__).resolve().parent.parent / "hardcopy" / "seattle-exchanges.csv"
DIGIT_WORDS = ("oh", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")


def _seconds(v: object) -> float:
    """A pause: or ringback: that passed validation, else 0."""
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else 0.0


class ScriptError(Exception):
    """Validation failed. `failures` lists every problem found, in order."""

    def __init__(self, path: Path, failures: list[str]) -> None:
        self.path = path
        self.failures = failures
        super().__init__(f"{path}: {len(failures)} problem(s)")


@dataclass(frozen=True)
class Utterance:
    """One spoken line: what it is, who says it, and what it is called."""

    scene: str
    id: int | str
    speaker: str
    text: str
    # Which side of the call says it, "caller" or "called" — or "operator" for
    # the player's own line, which the game never plays, or "tutor" for one of
    # tutor mode's, whose id is its key under tutor:, not a number. Usually the
    # scene's party on that side is the speaker; a line's own person: overrides that.
    role: str = "caller"
    # wait: true — the game plays it only after the operator has spoken on
    # that side and stopped (game_control.md 6.2).
    wait: bool = False
    # Seconds of silence before it, and seconds of ringback on the trunk
    # before it, after any wait (game_control.md 6.2).
    pause: float = 0.0
    ringback: float = 0.0
    # The game waits for the operator to speak before this line: the request,
    # a wait: line, every line of a call to the operator or a busy call.
    after_operator: bool = False
    # What she says there, if the script gives it: the name of an operator
    # line, operator.<id> or <scene>.<id>, else "" (game_control.md 6.3).
    operator: str = ""
    # One of the scene's if_busy: lines, played only when the called station
    # is found engaged (game_control.md 6.6), not in the conversation.
    if_busy: bool = False

    @property
    def name(self) -> str:
        """Base name, without extension: `<scene-id>.<utterance-id>`."""
        return f"{self.scene}.{self.id}"

    @property
    def filename(self) -> str:
        return f"{self.name}.wav"


@dataclass
class Script:
    path: Path
    setting: dict[str, str]
    cast: dict[str, dict]
    outside: dict[str, dict]
    stations: dict[str, dict]
    scenes: dict[str, dict]
    # script.yml's jacks:, each {"jack": int, "label": str, "station": str | None,
    # "guest": str | None}
    jacks: list[dict] = field(default_factory=list)
    utterances: list[Utterance] = field(default_factory=list)
    # operator_lines: key -> the stock line's utterance (game_control.md 6.3)
    operator_lines: dict[str, Utterance] = field(default_factory=dict)
    # scene id -> the name of the operator line that closes it, if any
    closings: dict[str, str] = field(default_factory=dict)
    # tutor mode's lines, by key: "intro", "ring-front-lobby", "dial-pizza",
    # "say-operator.1" (game_control.md 7). Empty without a tutor: section.
    tutor: dict[str, Utterance] = field(default_factory=dict)
    # reactions:, by kind and then speaker: reactions["nudge"]["martha"]
    # (game_control.md 3.5). Empty without a reactions: section.
    reactions: dict[str, dict[str, Utterance]] = field(default_factory=dict)
    # freecall:, by cast member: {"greeting": Utterance, "lines": [...],
    # "loop": [...]} (game_control.md 8). Empty without it.
    freecall: dict[str, dict] = field(default_factory=dict)
    # tutor: lessons:, the scenes a tutored game starts with, one picked from
    # each group (game_control.md 7). Empty without it.
    lessons: list[list[str]] = field(default_factory=list)

    def by_speaker(self) -> dict[str, list[Utterance]]:
        out: dict[str, list[Utterance]] = {p: [] for p in self.cast}
        for u in self.utterances:
            out.setdefault(u.speaker, []).append(u)
        return out

    def active_scenes(self) -> dict[str, dict]:
        """The scenes the game plays: those marked `active: true`."""
        return {i: sc for i, sc in self.scenes.items() if sc.get("active") is True}

    def scene_lines(self, scene_id: str) -> list[Utterance]:
        """A scene's lines in order of play, request first, without the operator's
        or the if_busy: lines."""
        return [u for u in self.utterances if u.scene == scene_id and u.role != "operator"
                and not u.if_busy]

    def busy_lines(self, scene_id: str) -> list[Utterance]:
        """A scene's if_busy: lines, in order (game_control.md 6.6)."""
        return [u for u in self.utterances if u.scene == scene_id and u.if_busy]

    def by_name(self) -> dict[str, Utterance]:
        return {u.name: u for u in self.utterances}

    def first_lines(self, person: str) -> list[Utterance]:
        """That person's lines in script order — session 1 samples from these."""
        return [u for u in self.utterances if u.speaker == person]


# A long-distance call's far voices (tts_task.md 7, 2026-11-23): the side of
# a scene whose line is the long-distance operator's, less the operators in
# Seattle. Each toll operator is a hop further, in the order they first speak,
# and the far party is as far as the last of them, or one hop with none.
LONG_DISTANCE_LINE = "operator"
NEAR_OPERATORS = ("operator", "local_operator", "rate_operator", HOTEL_OPERATOR)
TOLL_PREFIX = "toll_"


def far_hops(script: Script) -> dict[str, int]:
    """Utterance name -> hops away, for every far voice of a long-distance call."""
    out: dict[str, int] = {}
    for sid, sc in script.scenes.items():
        side = next((role for role, key in (("called", "called"), ("caller", "calling"))
                     if (sc.get(key) or {}).get("line") == LONG_DISTANCE_LINE), None)
        if side is None:
            continue
        far = [u for u in script.utterances if u.scene == sid and u.role == side
               and u.speaker not in NEAR_OPERATORS]
        tolls: list[str] = []
        for u in far:
            if u.speaker.startswith(TOLL_PREFIX) and u.speaker not in tolls:
                tolls.append(u.speaker)
        for u in far:
            out[u.name] = tolls.index(u.speaker) + 1 if u.speaker in tolls else max(len(tolls), 1)
    return out


def name_problem(name: str) -> str | None:
    """Return why `name` is not a legal file base name, or None if it is."""
    if len(name) > MAX_NAME:
        return f"{len(name)} characters, limit is {MAX_NAME}"
    for bad in FORBIDDEN_IN_NAME:
        if bad in name:
            return f"contains {bad!r}"
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in name):
        return "contains a control character"
    if name == RESERVED_NAME:
        return f"{RESERVED_NAME!r} is reserved: it stops playback"
    return None


def _read(path: Path) -> dict:
    """Parse the YAML, rejecting duplicate keys at every level.

    PyYAML keeps the last of a repeated key without a word; that silently lost
    two lines of a scene once already. ruamel raises instead.
    """
    yaml = YAML(typ="safe")
    yaml.allow_duplicate_keys = False
    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.load(f)
    except DuplicateKeyError as e:
        raise ScriptError(path, [f"duplicate key: {e}"]) from None
    if not isinstance(data, dict):
        raise ScriptError(path, ["top level is not a mapping"])
    return data


def _utterances_of(scene_id: str, scene: dict) -> Iterator[tuple[int | None, str, str, str, dict]]:
    """Yield (id, role, text, where, line) for every utterance of a scene, in order.

    `role` is 'caller' or 'called'; resolving that to a person needs the
    scene's parties, which validation checks separately. `line` is the raw
    entry, for its person: and wait:.
    """
    request = scene.get("request")
    if isinstance(request, dict):
        yield request.get("id"), "caller", request.get("text", ""), "request", request
    conversation = scene.get("conversation") or []
    if isinstance(conversation, list):
        for i, line in enumerate(conversation):
            if not isinstance(line, dict):
                continue
            where = f"conversation[{i}]"
            if "caller" in line:
                yield line.get("id"), "caller", line["caller"], where, line
            elif "called" in line:
                yield line.get("id"), "called", line["called"], where, line
    if_busy = scene.get("if_busy") or []
    if isinstance(if_busy, list):
        for i, line in enumerate(if_busy):
            if isinstance(line, dict) and "caller" in line:
                yield line.get("id"), "caller", line["caller"], f"if_busy[{i}]", line


Bad = Callable[[str, str], None]


def load(path: Path | str = DEFAULT_SCRIPT) -> Script:
    """Load, validate and enumerate. Raises ScriptError listing every failure."""
    path = Path(path).expanduser()
    data = _read(path)
    fail: list[str] = []

    def bad(where: str, why: str) -> None:
        fail.append(f"{where}: {why}")

    cast: dict = data.get("cast") or {}
    outside: dict = data.get("outside") or {}
    stations: dict = data.get("stations") or {}
    scenes: dict = data.get("scenes") or {}
    for key, value in (("cast", cast), ("outside", outside),
                       ("stations", stations), ("scenes", scenes)):
        if not isinstance(value, dict) or not value:
            bad(key, "missing or empty")

    _recorded(cast, bad)
    lines = _line_names(stations, outside, scenes, bad)
    _station_numbers(stations, bad)
    board = _jacks(data.get("jacks") or [], stations, bad)
    _outside_numbers(outside, cast, bad)
    utterances: list[Utterance] = []
    op_lines, stock = _operator_lines(data.get("operator_lines"), cast, scenes, utterances, bad)
    closings: dict[str, str] = {}
    for scene_id, scene in scenes.items():
        _scene(scene_id, scene, scenes, cast, stations, outside, lines,
               op_lines, stock, utterances, closings, bad)
    _after_chains(scenes, bad)
    _follows_loops(scenes, bad)

    tutor = _tutor_lines(data.get("tutor"), cast, board, stations, outside,
                         utterances, bad, scenes)
    utterances.extend(tutor.values())
    reactions = _reactions(data.get("reactions"), cast, bad)
    for by_speaker in reactions.values():
        utterances.extend(by_speaker.values())
    freecall = _freecall(data.get("freecall"), cast, bad)
    for entry in freecall.values():
        utterances.extend([entry["greeting"], *entry["lines"], *entry["loop"]])
    lessons = _lessons((data.get("tutor") or {}).get("lessons")
                       if isinstance(data.get("tutor"), dict) else None,
                       scenes, stations, bad)

    if fail:
        raise ScriptError(path, fail)

    return Script(path=path, setting=data.get("setting") or {}, cast=cast,
                  outside=outside, stations=stations, scenes=scenes,
                  jacks=board, utterances=utterances, operator_lines=stock,
                  closings=closings, tutor=tutor, reactions=reactions, lessons=lessons,
                  freecall=freecall)


def _unknown(keys: object, allowed: set[str]) -> str:
    """"unknown key(s): a, b" for the keys not allowed, or "" if none."""
    extra = sorted(set(keys) - allowed)          # type: ignore[call-overload]
    return f"unknown key(s): {', '.join(map(str, extra))}" if extra else ""


def _whole(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _recorded(cast: dict, bad: Bad) -> None:
    """recorded: names the performer of a part (tts_task.md 6.4)."""
    for name, entry in cast.items():
        if isinstance(entry, dict) and "recorded" in entry:
            r = entry["recorded"]
            if not isinstance(r, str) or not r.strip():
                bad(f"cast.{name}.recorded", "must name the performer")


def _line_names(stations: dict, outside: dict, scenes: dict, bad: Bad) -> set[str]:
    """Every line's name, a station or an outside entry and never both; and
    the scene names reserved for lines that are not a scene's."""
    for name in sorted(set(stations) & set(outside)):
        bad(f"{name}", "is both a station and an outside entry")
    if OPERATOR_SCENE in scenes:
        bad(f"scenes.{OPERATOR_SCENE}", "is reserved for the names of operator_lines:")
    for reserved in (TUTOR, BRIEF, TERSE, FREE, *REACTIONS):
        if reserved in scenes:
            bad(f"scenes.{reserved}", "is reserved for the names of the tutor's lines")
    return set(stations) | set(outside)


def _station_numbers(stations: dict, bad: Bad) -> None:
    seen: dict[int, str] = {}
    for name, entry in stations.items():
        number = (entry or {}).get("number")
        if not _whole(number):
            bad(f"stations.{name}.number", f"not an integer: {number!r}")
            continue
        if not (MIN_STATION <= number <= MAX_STATION or number == PHONE_STATION):
            bad(f"stations.{name}.number",
                f"{number} outside {MIN_STATION}-{MAX_STATION} and {PHONE_STATION}")
        if number in seen:
            bad(f"stations.{name}.number", f"{number} already used by {seen[number]}")
        else:
            seen[number] = name


def _jacks(jacks: object, stations: dict, bad: Bad) -> list[dict]:
    """jacks: checked, as Script.jacks (game_control.md 12.1).

    Every station jack the board draws, with its label, and the station cabled
    to it if any. The game program refuses to start without a jack for every
    station: the page builds the board from these alone, and a station with no
    jack is a circuit with no tile.
    """
    seen: set[int] = set()
    jack_of: dict[str, int | None] = {}
    board: list[dict] = []
    if not isinstance(jacks, list) or not jacks:
        bad("jacks", "missing, empty or not a list")
        jacks = []
    for i, entry in enumerate(jacks):
        at = f"jacks[{i}]"
        if not isinstance(entry, dict):
            bad(at, "not a mapping")
            continue
        if extra := _unknown(entry, {"jack", "label", "station", "guest"}):
            bad(at, extra)
        jack = entry.get("jack")
        if not _whole(jack):
            bad(f"{at}.jack", f"not an integer: {jack!r}")
        elif not MIN_JACK <= jack <= MAX_JACK:
            bad(f"{at}.jack", f"{jack} outside {MIN_JACK}-{MAX_JACK}")
        elif jack in seen:
            bad(f"{at}.jack", f"jack {jack} listed twice")
        else:
            seen.add(jack)
        label = entry.get("label")
        if not isinstance(label, str) or not label.strip():
            bad(f"{at}.label", f"missing, empty or not text: {label!r}")
        station = entry.get("station")
        if station is not None:
            if station not in stations:
                bad(f"{at}.station", f"{station!r} is not a station")
            elif station in jack_of:
                bad(f"{at}.station", f"{station} is already on jack {jack_of[station]}")
            else:
                jack_of[station] = jack
        guest = entry.get("guest")
        if guest is not None and (not isinstance(guest, str) or not guest.strip()):
            bad(f"{at}.guest", f"empty or not text: {guest!r}")
        board.append({"jack": jack, "label": label.strip() if isinstance(label, str) else "",
                      "station": station,
                      "guest": guest.strip() if isinstance(guest, str) and guest.strip() else None})
    for name in stations:
        if name not in jack_of:
            bad(f"stations.{name}", "on no jack: name it as station: under jacks: (game_control.md 12.1)")
        extra = sorted(set(stations[name] or {}) - {"number"})
        if extra:
            bad(f"stations.{name}", f"unknown key(s): {', '.join(map(str, extra))}"
                + (" — the jack and its label are under jacks: now"
                   if {"switchboard", "label"} & set(extra) else ""))
    return board


def _outside_numbers(outside: dict, cast: dict, bad: Bad) -> None:
    seen: dict[str, str] = {}
    for name, entry in outside.items():
        number = (entry or {}).get("number")
        if not isinstance(number, str):
            bad(f"outside.{name}.number", f"not a string: {number!r} — quote it")
            continue
        person = (entry or {}).get("person")
        if person is not None and person not in cast:
            bad(f"outside.{name}.person", f"{person!r} is not in the cast")
        if number in seen:
            bad(f"outside.{name}.number", f"{number} already used by {seen[number]}")
        else:
            seen[number] = name


def _operator_lines(raw: object, cast: dict, scenes: dict, utterances: list[Utterance],
                    bad: Bad) -> tuple[dict, dict[str, Utterance]]:
    """operator_lines:, the operator's stock lines (game_control.md 6.3): the
    raw mapping, and each valid one's utterance by key, also appended to
    `utterances`."""
    op_lines = raw or {}
    if not isinstance(op_lines, dict):
        bad("operator_lines", "not a mapping")
        op_lines = {}
    if (op_lines or _any_operator_label(scenes)) and HOTEL_OPERATOR not in cast:
        bad("cast", f"no {HOTEL_OPERATOR}, who speaks the operator's lines")
    stock: dict[str, Utterance] = {}
    seen: dict[int, str] = {}
    for key, entry in op_lines.items():
        at = f"operator_lines.{key}"
        if not isinstance(entry, dict):
            bad(at, "not a mapping")
            continue
        if extra := _unknown(entry, {"id", "text"}):
            bad(at, extra)
        uid, text = entry.get("id"), entry.get("text")
        if not _whole(uid):
            bad(f"{at}.id", f"not an integer: {uid!r}")
            continue
        if uid in seen:
            bad(f"{at}.id", f"{uid} already used by {seen[uid]}")
            continue
        seen[uid] = str(key)
        if not isinstance(text, str) or not text.strip():
            bad(at, "empty text")
            continue
        u = Utterance(scene=OPERATOR_SCENE, id=uid, speaker=HOTEL_OPERATOR,
                      text=text.strip(), role="operator")
        stock[str(key)] = u
        utterances.append(u)
    return op_lines, stock


def _scene(scene_id: str, scene: object, scenes: dict, cast: dict, stations: dict,
           outside: dict, lines: set[str], op_lines: dict, stock: dict[str, Utterance],
           utterances: list[Utterance], closings: dict[str, str], bad: Bad) -> None:
    """One scene checked, its utterances appended to `utterances` and its
    closing:, if any, to `closings`."""
    if not isinstance(scene, dict):
        bad(f"scenes.{scene_id}", "not a mapping")
        return
    parties = _parties(scene_id, scene, cast, lines, bad)
    _scene_order(scene_id, scene, scenes, bad)
    _if_busy(scene_id, scene, cast, stations, bad)
    # A call to the operator, or one that meets busy, waits for her before
    # every line already (flows.py), so wait: has nothing to add there.
    called = scene.get("called")
    waits_anyway = not isinstance(called, dict) or bool(called.get("busy"))
    _conversation(scene_id, scene, cast, outside, waits_anyway, bad)
    _scene_utterances(scene_id, scene, parties, cast, op_lines, stock, waits_anyway,
                      utterances, closings, bad)


def _parties(scene_id: str, scene: dict, cast: dict, lines: set[str],
             bad: Bad) -> dict[str, str | None]:
    """calling: and called:, as the person on each side, or None."""
    parties: dict[str, str | None] = {}
    for role, key in (("caller", "calling"), ("called", "called")):
        party = scene.get(key)
        if party is None:
            parties[role] = None
            continue
        if not isinstance(party, dict):
            bad(f"scenes.{scene_id}.{key}", "not a mapping")
            parties[role] = None
            continue
        line = party.get("line")
        if line not in lines:
            bad(f"scenes.{scene_id}.{key}.line",
                f"{line!r} is not a station or an outside entry")
        person = party.get("person")
        if person not in cast:
            bad(f"scenes.{scene_id}.{key}.person", f"{person!r} is not in the cast")
        parties[role] = person if person in cast else None
    if parties["caller"] is None and not isinstance(scene.get("calling"), dict):
        bad(f"scenes.{scene_id}.calling", "missing")
    return parties


def _scene_order(scene_id: str, scene: dict, scenes: dict, bad: Bad) -> None:
    """What decides when a scene is dealt: active:, after:, delay:, mode:,
    after_handled:, live: and follows: (game_control.md 4.4, 6.1, 6.5)."""
    # active: the game plays the scene; TTS renders every scene regardless, so
    # a new one can be rendered before it plays.
    active = scene.get("active")
    if not isinstance(active, bool):
        bad(f"scenes.{scene_id}.active", f"missing or not true/false: {active!r}")

    # after: names a scene. Loops and a scene with two followers are checked
    # over all scenes, in _after_chains().
    after = scene.get("after")
    if after is not None:
        if after not in scenes:
            bad(f"scenes.{scene_id}.after", f"{after!r} is not a scene")
        elif (active is True and isinstance(scenes[after], dict)
              and scenes[after].get("active") is False):
            bad(f"scenes.{scene_id}.after",
                f"{after!r} is inactive, so this active scene could never play")
        elif after == scene_id:
            bad(f"scenes.{scene_id}.after", "names itself")

    # delay: seconds, or a range [low, high] drawn from. mode: concurrent
    # starts it with the scene it follows.
    if "delay" in scene:
        d = scene["delay"]
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0
        if not (num(d) or (isinstance(d, list) and len(d) == 2
                           and all(num(v) for v in d) and d[0] <= d[1])):
            bad(f"scenes.{scene_id}.delay",
                f"not a number of seconds or a range [low, high]: {d!r}")
        if after is None:
            bad(f"scenes.{scene_id}.delay", "only on a scene with after:")
    if "mode" in scene:
        if scene["mode"] != "concurrent":
            bad(f"scenes.{scene_id}.mode", f"not concurrent: {scene['mode']!r}")
        elif after is None:
            bad(f"scenes.{scene_id}.mode", "only on a scene with after:")
    # after_handled: the first scene of a scenario.
    if "after_handled" in scene:
        n = scene["after_handled"]
        if not _whole(n) or n < 0:
            bad(f"scenes.{scene_id}.after_handled", f"not a whole number of calls: {n!r}")
        if after is not None:
            bad(f"scenes.{scene_id}.after_handled", "not on a scene with after:")
    # live: at most n of the game's calls waiting on the operator while the
    # scenario deals.
    if "live" in scene:
        n = scene["live"]
        if not _whole(n) or not 1 <= n <= 8:
            bad(f"scenes.{scene_id}.live", f"not a number of calls from 1 to 8: {n!r}")
        if "after_handled" not in scene:
            bad(f"scenes.{scene_id}.live", "only on a scenario's first scene, with after_handled:")

    # follows: scenes the shuffle deals this one after. A loop through them, or
    # through after:, is checked in _follows_loops().
    if "follows" in scene:
        at = f"scenes.{scene_id}.follows"
        f = scene["follows"]
        if not isinstance(f, list) or not f or not all(isinstance(x, str) for x in f):
            bad(at, f"not a list of scenes: {f!r}")
        else:
            for x in f:
                if x not in scenes:
                    bad(at, f"{x!r} is not a scene")
                elif x == scene_id:
                    bad(at, "names itself")
            if len(set(f)) != len(f):
                bad(at, "names a scene twice")
        if after is not None:
            bad(at, "not on a scene with after:; it is dealt on a timer, not from the shuffle")
        if "after_handled" in scene:
            bad(at, "not on a scenario's first scene")


def _if_busy(scene_id: str, scene: dict, cast: dict, stations: dict, bad: Bad) -> None:
    """if_busy: caller lines for a called station found engaged
    (game_control.md 6.6). Only between two rooms."""
    if "if_busy" not in scene:
        return
    at = f"scenes.{scene_id}.if_busy"
    ib = scene["if_busy"]
    cg, cd = scene.get("calling"), scene.get("called")
    if not (isinstance(cg, dict) and isinstance(cd, dict)
            and cg.get("line") in stations and cd.get("line") in stations
            and not cd.get("busy")):
        bad(at, "only on a call from a room to a room")
    if not isinstance(ib, list) or not ib:
        bad(at, "not a list of caller lines")
        return
    for i, line in enumerate(ib):
        if not isinstance(line, dict):
            bad(f"{at}[{i}]", "not a mapping")
            continue
        extra = sorted(set(line) - {"id", "caller", "person", "pause", "operator"})
        if extra:
            bad(f"{at}[{i}]", f"unknown key(s): {', '.join(map(str, extra))}"
                + (" — every if_busy: line is the caller's" if "called" in extra else ""))
        if "caller" not in line:
            bad(f"{at}[{i}]", "has no caller:")
        if "pause" in line:
            v = line["pause"]
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 < v <= MAX_PAUSE:
                bad(f"{at}[{i}].pause", f"not a number of seconds above 0 and up to {MAX_PAUSE}: {v!r}")
        if "person" in line and line["person"] not in cast:
            bad(f"{at}[{i}].person", f"{line['person']!r} is not in the cast")


def _conversation(scene_id: str, scene: dict, cast: dict, outside: dict,
                  waits_anyway: bool, bad: Bad) -> None:
    """conversation:'s keys, and request:'s (game_control.md 6.2)."""
    called = scene.get("called")
    conv = scene.get("conversation") or []
    for i, line in enumerate(conv if isinstance(conv, list) else []):
        at = f"scenes.{scene_id}.conversation[{i}]"
        if not isinstance(line, dict):
            bad(at, "not a mapping")
            continue
        if extra := _unknown(line, {"id", "caller", "called", "person", "wait",
                                    "pause", "ringback", "operator"}):
            bad(at, extra)
        if "caller" in line and "called" in line:
            bad(at, "has both caller: and called:")
        elif "caller" not in line and "called" not in line:
            bad(at, "has neither caller: nor called:")
        if "wait" in line:
            if not isinstance(line["wait"], bool):
                bad(f"{at}.wait", f"not true/false: {line['wait']!r}")
            elif line["wait"] and waits_anyway:
                bad(f"{at}.wait", "every line of a call to the operator or a busy call waits already")
        for key, top in (("pause", MAX_PAUSE), ("ringback", MAX_RINGBACK)):
            if key in line:
                v = line[key]
                if not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 < v <= top:
                    bad(f"{at}.{key}", f"not a number of seconds above 0 and up to {top}: {v!r}")
        if "ringback" in line:
            # Ringback is a trunk tone: it can only be heard on a line spoken
            # on a trunk — the called side of a call out, or the calling side
            # of a call in.
            side = called if "called" in line else scene.get("calling")
            on = side.get("line") if isinstance(side, dict) else None
            if on not in outside or waits_anyway:
                bad(f"{at}.ringback", "only on a line spoken on a trunk: a call's outside end")
        if "person" in line and line["person"] not in cast:
            bad(f"{at}.person", f"{line['person']!r} is not in the cast")
    req = scene.get("request")
    if isinstance(req, dict):
        if extra := _unknown(req, {"id", "text", "operator"}):
            bad(f"scenes.{scene_id}.request", extra)


def _scene_utterances(scene_id: str, scene: dict, parties: dict[str, str | None],
                      cast: dict, op_lines: dict, stock: dict[str, Utterance],
                      waits_anyway: bool, utterances: list[Utterance],
                      closings: dict[str, str], bad: Bad) -> None:
    """A scene's utterances, appended: integer ids unique in the scene, legal
    file names, and the operator's own lines placed before the line each
    precedes (game_control.md 6.3)."""
    seen_id: dict[int, str] = {}
    # The operator's own lines in the scene come after its ids are known,
    # since an inline one shares them.
    labels: list[tuple[str, object, int]] = []   # where, operator: value, index into utterances
    for uid, role, text, where, raw in _utterances_of(scene_id, scene):
        at = f"scenes.{scene_id}.{where}"
        if not _whole(uid):
            bad(f"{at}.id", f"not an integer: {uid!r}")
            continue
        if uid in seen_id:
            bad(f"{at}.id", f"{uid} already used by {seen_id[uid]}")
            continue
        seen_id[uid] = where
        if not isinstance(text, str) or not text.strip():
            bad(at, "empty text")
            continue
        speaker = parties[role]
        if speaker is None:
            bad(at, f"is a {role} line but the scene has no usable {role}")
            continue
        if raw.get("person") in cast:
            speaker = raw["person"]
        busy_line = where.startswith("if_busy")
        listens = (where == "request" or raw.get("wait") is True or waits_anyway
                   or busy_line)
        u = Utterance(scene=scene_id, id=uid, speaker=speaker, text=text.strip(),
                      role=role, wait=raw.get("wait") is True,
                      pause=_seconds(raw.get("pause")),
                      ringback=_seconds(raw.get("ringback")),
                      after_operator=listens, if_busy=busy_line)
        why = name_problem(u.name)
        if why is not None:
            bad(at, f"file name {u.name!r} is not usable: {why}")
            continue
        if "operator" in raw:
            if not listens:
                bad(f"{at}.operator", "the game does not wait for the operator before "
                    "this line: mark it wait: true, or drop operator:")
            else:
                labels.append((at, raw["operator"], len(utterances)))
        utterances.append(u)

    # operator: is a key under operator_lines:, or an inline {id, text} for a
    # line only this scene needs. Inline lines are utterances of the scene,
    # placed before the line they precede.
    def resolve(at: str, label: object) -> tuple[Utterance | None, bool]:
        """The operator line a label names, and whether it is the scene's own."""
        if isinstance(label, str):
            if label not in stock and label not in op_lines:
                bad(at, f"{label!r} is not under operator_lines:")
            return stock.get(label), False
        if not isinstance(label, dict):
            bad(at, f"not a name under operator_lines: or an id and text: {label!r}")
            return None, False
        if extra := _unknown(label, {"id", "text"}):
            bad(at, extra)
        uid, text = label.get("id"), label.get("text")
        if not _whole(uid):
            bad(f"{at}.id", f"not an integer: {uid!r}")
            return None, False
        if uid in seen_id:
            bad(f"{at}.id", f"{uid} already used by {seen_id[uid]}")
            return None, False
        seen_id[uid] = at[len(f"scenes.{scene_id}."):]
        if not isinstance(text, str) or not text.strip():
            bad(at, "empty text")
            return None, False
        return Utterance(scene=scene_id, id=uid, speaker=HOTEL_OPERATOR,
                         text=text.strip(), role="operator"), True

    for at, label, i in reversed(labels):
        op, own = resolve(f"{at}.operator", label)
        if op is None:
            continue
        utterances[i] = replace(utterances[i], operator=op.name)
        if own:
            utterances.insert(i, op)

    # closing: what she says after the last line, before she pulls the cord.
    # Only where she is still on the line with the caller: a call to the
    # operator, or a busy call.
    if "closing" in scene:
        at = f"scenes.{scene_id}.closing"
        if not waits_anyway:
            bad(at, "only in a call to the operator or a busy call: "
                "in any other the operator is off the line when it ends")
        else:
            op, own = resolve(at, scene["closing"])
            if op is not None:
                closings[scene_id] = op.name
                if own:
                    utterances.append(op)

    if not seen_id:
        bad(f"scenes.{scene_id}", "has no utterances")


def _after_chains(scenes: dict, bad: Bad) -> None:
    """after: chains (game_control.md 6.1): one follower per scene, since two
    would each wait for the other's people to come free and neither would ever
    start; and no loop, which would never reach the deck at all."""
    after_of = {i: sc.get("after") for i, sc in scenes.items()
                if isinstance(sc, dict) and sc.get("after") in scenes and sc.get("after") != i}
    followed: dict[str, str] = {}
    for i, a in after_of.items():
        if a in followed:
            bad(f"scenes.{i}.after", f"{a!r} is already followed by {followed[a]}; a scene has one follower")
        else:
            followed[a] = i
    for i in after_of:
        seen, at = {i}, after_of[i]
        while at in after_of:
            if at in seen:
                bad(f"scenes.{i}.after", "is part of a loop of after:s")
                break
            seen.add(at)
            at = after_of[at]


def _follows_loops(scenes: dict, bad: Bad) -> None:
    """follows: makes no loop (game_control.md 6.1). A scene waits for those it
    names, and an after: scene for the one it follows; a loop through either
    would hold every scene in it for ever."""
    waits_on: dict[str, list[str]] = {}
    for i, sc in scenes.items():
        if not isinstance(sc, dict):
            continue
        w = [x for x in (sc.get("follows") or []) if isinstance(x, str) and x in scenes]
        if sc.get("after") in scenes:
            w.append(sc["after"])
        waits_on[i] = w
    state: dict[str, int] = {}

    def loops(i: str) -> bool:
        state[i] = 1
        for j in waits_on.get(i, []):
            if state.get(j) == 1 or (state.get(j) is None and loops(j)):
                return True
        state[i] = 2
        return False

    for i, sc in scenes.items():
        if isinstance(sc, dict) and sc.get("follows") and state.get(i) is None:
            if loops(i):
                bad(f"scenes.{i}.follows", "is part of a loop of follows: and after:")


def scene_kind(scene: dict, stations: dict) -> str:
    """Which kind of call a scene is, as game_control.md 3.3 tells them apart."""
    called = scene.get("called")
    if not isinstance(called, dict):
        return "to the operator"
    if called.get("busy"):
        return "busy"
    calling = scene.get("calling") if isinstance(scene.get("calling"), dict) else {}
    from_room, to_room = calling.get("line") in stations, called.get("line") in stations
    if from_room:
        return "between rooms" if to_room else "out to a number"
    return "in from outside"


def _lessons(raw: object, scenes: dict, stations: dict, bad) -> list[list[str]]:
    """tutor: lessons:, checked: groups of scene ids, one kind of call to a group."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        bad("tutor.lessons", "not a list of groups")
        return []
    out: list[list[str]] = []
    for i, group in enumerate(raw):
        at = f"tutor.lessons[{i}]"
        if not isinstance(group, list) or not group:
            bad(at, "not a list of scene ids")
            continue
        kinds: dict[str, str] = {}
        for sid in group:
            sc = scenes.get(sid)
            if not isinstance(sc, dict):
                bad(at, f"{sid!r} is not a scene")
                continue
            if sc.get("active") is not True:
                bad(at, f"{sid} is not active")
            if sc.get("after") is not None:
                bad(at, f"{sid} follows {sc['after']}, so it is never dealt")
            if sc.get("after_handled") is not None:
                bad(at, f"{sid} starts a scenario, and is never dealt in tutor mode")
            kinds[sid] = scene_kind(sc, stations)
        if len(set(kinds.values())) > 1:
            bad(at, "mixes kinds of call: " + ", ".join(f"{k} {v}" for k, v in kinds.items()))
        out.append([str(x) for x in group])
    return out


def jack_words(label: str) -> str:
    """How the tutor names a jack: "room 403" for a numbered one, else its label."""
    return f"room {label}" if label.isdigit() else label


def _exchanges() -> dict[str, str]:
    """"783" -> "Sunset three", from the exchange list, if it is here."""
    out: dict[str, str] = {}
    try:
        with EXCHANGES.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name, digit = row["Exchange"].split()
                out[row["Numeric"]] = f"{name.capitalize()} {DIGIT_WORDS[int(digit)]}"
    except OSError:
        pass
    return out


_TEENS = ("ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
          "seventeen", "eighteen", "nineteen")
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")


def _two_digits(n: int) -> str:
    """10-99 in words: "fourteen", "forty-four"."""
    if n < 20:
        return _TEENS[n - 10]
    return _TENS[n // 10] + (f"-{DIGIT_WORDS[n % 10]}" if n % 10 else "")


def _line_words(four: str) -> str:
    """The four digits after the exchange, as an operator says them: round
    thousands and hundreds whole, as tts/pronounce.yml has the cast say
    them - "5000" "five thousand", "1400" "fourteen hundred" - and anything
    else digit by digit."""
    if len(four) == 4 and four[0] != "0":
        if four[1:] == "000":
            return f"{DIGIT_WORDS[int(four[0])]} thousand"
        if four[2:] == "00" and four[1] != "0":
            return f"{_two_digits(int(four[:2]))} hundred"
    return " ".join(DIGIT_WORDS[int(c)] for c in four)


def number_words(number: str, exchanges: dict[str, str]) -> str:
    """783-2250 as an operator says it from the card: "Sunset three, two two five oh";
    784-5000, "Sunset four, five thousand"."""
    digits = "".join(c for c in number if c.isdigit())
    ex = exchanges.get(digits[:3]) if len(digits) == 7 else None
    if ex is None:
        return " ".join(DIGIT_WORDS[int(c)] for c in digits)
    return f"{ex}, " + _line_words(digits[3:])


DIGITS_FIELD = "number-digits"


def dial_digits(number: str, exchanges: dict[str, str]) -> str:
    """What the player dials, as a person today says it: 783-2250 as "seven
    eight three, two two five oh", 784-5000 as "seven eight four, five
    thousand" (game_control.md 7). The exchange's letters are said as
    their digits, the comma gives the voice its pause, and the last four are
    said as number_words says them."""
    digits = "".join(c for c in number if c.isdigit())
    return " ".join(DIGIT_WORDS[int(c)] for c in digits[:3]) + ", " + _line_words(digits[3:])


def _tutor_lines(raw: object, cast: dict, board: list[dict], stations: dict,
                 outside: dict, utterances: list[Utterance], bad,
                 scenes: dict | None = None) -> dict[str, Utterance]:
    """tutor: expanded into one utterance per line the tutor can say.

    A template is rendered whole for each value it can take, rather than
    spliced from a sentence and a name at play time, so every line is spoken
    as one sentence.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        bad("tutor", "not a mapping")
        return {}
    if TUTOR not in cast:
        bad("cast", f"no {TUTOR}, who speaks the lines under tutor:")
    for key in sorted(set(map(str, raw)) - set(TUTOR_KEYS) - {"lessons", BRIEF, TERSE}):
        bad(f"tutor.{key}", "is not one of the tutor's lines (game_control.md 7)")
    shorts: dict[str, dict] = {}
    for section, _ in SHORT:
        given = raw.get(section) or {}
        if not isinstance(given, dict):
            bad(f"tutor.{section}", "not a mapping")
            given = {}
        for key in sorted(set(map(str, given)) - set(BRIEF_KEYS)):
            bad(f"tutor.{section}.{key}", "has no short form: not one of "
                + ", ".join(BRIEF_KEYS) + " (game_control.md 7, Rev 55)")
        shorts[section] = given

    def checked(key: str, text: object, at: str) -> str | None:
        field_ = TUTOR_KEYS[key]
        if not isinstance(text, str) or not text.strip():
            bad(at, "missing or empty")
            return None
        try:
            used = {f for _, f, _, _ in string.Formatter().parse(text) if f is not None}
        except ValueError as e:
            bad(at, f"unreadable placeholder: {e}")
            return None
        want = {field_} if field_ else set()
        # {number-digits} beside {number}, or in its place: what to dial, as
        # said today.
        may = want | ({DIGITS_FIELD} if field_ == "number" else set())
        if field_ == "number" and DIGITS_FIELD in used:
            want = set()
        if not want <= used or used - may:
            bad(at, "takes " + (f"{{{field_}}}" if field_ else "no placeholder")
                + (" and may take {" + DIGITS_FIELD + "}" if may - want else "")
                + (f", not {', '.join('{' + u + '}' for u in sorted(used - may))}"
                   if used - may else ""))
            return None
        return " ".join(text.split())

    # (key under tutor:, prefix of what it makes, its text): the full lines,
    # then the short forms given, each expanded the same way.
    texts: list[tuple[str, str, str]] = []
    for key in TUTOR_KEYS:
        if (t := checked(key, raw.get(key), f"tutor.{key}")) is not None:
            texts.append((key, "", t))
    for section, prefix in SHORT:
        for key in BRIEF_KEYS:
            given = shorts[section]
            if key in given and (t := checked(key, given[key], f"tutor.{section}.{key}")) is not None:
                texts.append((key, prefix, t))

    out: dict[str, Utterance] = {}

    def add(key: str, text: str) -> None:
        scene, id_ = next(((section, key.removeprefix(prefix)) for section, prefix in SHORT
                           if key.startswith(prefix)), (TUTOR, key))
        u = Utterance(scene=scene, id=id_, speaker=TUTOR, text=text, role=TUTOR)
        why = name_problem(u.name)
        if why is not None:
            bad(f"tutor.{key}", f"file name {u.name!r} is not usable: {why}")
            return
        if key in out:
            bad(f"tutor.{key}", f"{u.name} would be rendered twice: rename the line that makes it")
            return
        out[key] = u

    for key, prefix, text in texts:
        field_ = TUTOR_KEYS[key]
        if field_ is None:
            add(prefix + key, text)
        elif field_ == "jack":
            # Named by station, not jack, so moving a label to another jack
            # leaves the file alone; what is said follows the label. Not for
            # the real telephone, which no scene rings.
            for j in board:
                if (j["station"] and isinstance(j["jack"], int)
                        and (stations.get(j["station"]) or {}).get("number") != PHONE_STATION):
                    add(f"{prefix}{key}-{j['station']}", text.format(jack=jack_words(j["label"])))
        elif field_ == "number":
            ex = _exchanges()
            for line, entry in outside.items():
                number = str((entry or {}).get("number", ""))
                if number and number != "0":
                    add(f"{prefix}{key}-{line}", text.format(**{
                        "number": number_words(number, ex),
                        DIGITS_FIELD: dial_digits(number, ex)}))
        elif field_ == "line":
            # A scenario is never played in tutor mode (game_control.md 6.5),
            # so she needs no Say for a line only a scenario uses.
            scenario = _scenario_scenes(scenes or {})
            used: dict[str, set[str]] = {}
            for u in utterances:
                if u.operator:
                    used.setdefault(u.operator, set()).add(u.scene)
            for u in utterances:
                if u.role == "operator":
                    if u.scene in scenario:
                        continue
                    if used.get(u.name) and used[u.name] <= scenario:
                        continue
                    add(f"{key}-{u.name}", text.format(line=u.text))
    return out


def _reactions(raw: object, cast: dict, bad) -> dict[str, dict[str, Utterance]]:
    """reactions: expanded into one utterance per kind and cast member."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        bad("reactions", "not a mapping")
        return {}
    for key in sorted(set(map(str, raw)) - set(REACTIONS)):
        bad(f"reactions.{key}", "is not one of " + ", ".join(REACTIONS))
    out: dict[str, dict[str, Utterance]] = {}
    for kind in REACTIONS:
        text = raw.get(kind)
        if not isinstance(text, str) or not text.strip():
            bad(f"reactions.{kind}", "missing or empty")
            continue
        text = " ".join(text.split())
        out[kind] = {}
        for who in cast:
            if who in (TUTOR, HOTEL_OPERATOR) or "recorded" in (cast[who] or {}):
                continue                    # a recorded part says only its takes
            u = Utterance(scene=kind, id=who, speaker=who, text=text, role="caller")
            why = name_problem(u.name)
            if why is not None:
                bad(f"reactions.{kind}", f"file name {u.name!r} is not usable: {why}")
                continue
            out[kind][who] = u
    return out


def _freecall(raw: object, cast: dict, bad) -> dict[str, dict]:
    """freecall: expanded into each answerer's utterances (game_control.md 8)."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        bad(FREE + "call", "not a mapping")
        return {}
    out: dict[str, dict] = {}
    for who, entry in raw.items():
        at = f"freecall.{who}"
        if who not in cast or who in (TUTOR, HOTEL_OPERATOR):
            bad(at, "is not a cast member who can answer")
            continue
        if not isinstance(entry, dict):
            bad(at, "not a mapping")
            continue
        for key in sorted(set(map(str, entry)) - set(FREE_KEYS)):
            bad(f"{at}.{key}", "is not one of " + ", ".join(FREE_KEYS))
        greeting = entry.get("greeting")
        lines, loop = entry.get("lines") or [], entry.get("loop")
        if not isinstance(greeting, str) or not greeting.strip():
            bad(f"{at}.greeting", "missing or empty")
            continue
        if not isinstance(loop, list) or not loop:
            bad(f"{at}.loop", "missing or empty: the lines said round and round")
            continue
        if not isinstance(lines, list):
            bad(f"{at}.lines", "not a list")
            continue
        texts = [*lines, *loop]
        if any(not isinstance(t, str) or not t.strip() for t in texts):
            bad(at, "every line must be text")
            continue
        made = [Utterance(scene=f"{FREE}.{who}", id="g", speaker=who,
                          text=" ".join(greeting.split()), role="called")]
        for i, t in enumerate(texts, 1):
            made.append(Utterance(scene=f"{FREE}.{who}", id=str(i), speaker=who,
                                  text=" ".join(t.split()), role="called"))
        if any((why := name_problem(u.name)) is not None for u in made):
            bad(at, f"file name {made[-1].name!r} is not usable: {why}")
            continue
        out[who] = {"greeting": made[0], "lines": made[1:1 + len(lines)],
                    "loop": made[1 + len(lines):]}
    return out


def _scenario_scenes(scenes: dict) -> set[str]:
    """Each scenario's scenes: its first, with after_handled:, and the
    mode: concurrent followers down its chain (game_control.md 6.5)."""
    out = {i for i, sc in scenes.items() if isinstance(sc, dict) and "after_handled" in sc}
    grew = True
    while grew:
        grew = False
        for i, sc in scenes.items():
            if (i not in out and isinstance(sc, dict) and sc.get("mode") == "concurrent"
                    and sc.get("after") in out):
                out.add(i)
                grew = True
    return out


def _any_operator_label(scenes: dict) -> bool:
    for scene in scenes.values():
        if not isinstance(scene, dict):
            continue
        lines = [scene.get("request")] + list(scene.get("conversation") or [])
        if any(isinstance(x, dict) and "operator" in x for x in lines):
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Validate the game script and count its utterances.")
    p.add_argument("--script", type=Path, default=DEFAULT_SCRIPT, help=f"default {DEFAULT_SCRIPT}")
    p.add_argument("--list", action="store_true", help="print every utterance")
    args = p.parse_args(argv)

    try:
        script = load(args.script)
    except ScriptError as e:
        print(f"{e.path}: {len(e.failures)} problem(s)", file=sys.stderr)
        for f in e.failures:
            print(f"  {f}", file=sys.stderr)
        return 1

    if args.list:
        for u in script.utterances:
            print(f"{u.name:<20} {u.speaker:<12} {u.text}")
    speakers = script.by_speaker()
    silent = sorted(p for p, us in speakers.items() if not us)
    print(f"{script.path}: {len(script.scenes)} scenes ({len(script.active_scenes())} active), "
          f"{len(script.utterances)} utterances, "
          f"{len(script.cast)} cast, {len(script.jacks)} jacks "
          f"({sum(1 for j in script.jacks if j['station'])} cabled)")
    if silent:
        print(f"cast with no lines: {', '.join(silent)}")
    # operator: is optional; say where it is still to be written (4.7)
    unsaid = [u for u in script.utterances if u.after_operator and not u.operator]
    if unsaid:
        print(f"{len(unsaid)} place(s) the operator speaks with no operator: line, "
              f"in {len({u.scene for u in unsaid})} scene(s)"
              + (": " + ", ".join(u.name for u in unsaid) if args.list else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
