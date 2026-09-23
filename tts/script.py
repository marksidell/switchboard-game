"""Loader and validation for the game script (tts_task.md 3.1).

The script itself lives in the Syncthing share, not in this repo, and is
maintained in chat sessions; this module only ever reads it.

Written to be imported by the game engine later, so the public surface is
small and typed: `load()` returns a `Script`, or raises `ScriptError`
carrying every failure found rather than only the first.

    from tts.script import load
    script = load()
    for u in script.utterances:
        ...
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from ruamel.yaml import YAML
from ruamel.yaml.constructor import DuplicateKeyError

# The script is outside the repo on purpose (CLAUDE.md: read, do not edit).
DEFAULT_SCRIPT = Path.home() / "s" / "game" / "script.yml"

# audio.md 7.1 / mqtt.md 7: the constraints on a playable file name.
MAX_NAME = 31
FORBIDDEN_IN_NAME = ("/", "\\", "..")
RESERVED_NAME = "stop"

# Stations run 1..23. Slot 24 is the operator tap and is not a station
# (CLAUDE.md, station 7.9.6).
MIN_STATION, MAX_STATION = 1, 23


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
    id: int
    speaker: str
    text: str

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
    utterances: list[Utterance] = field(default_factory=list)

    def by_speaker(self) -> dict[str, list[Utterance]]:
        out: dict[str, list[Utterance]] = {p: [] for p in self.cast}
        for u in self.utterances:
            out.setdefault(u.speaker, []).append(u)
        return out

    def first_lines(self, person: str) -> list[Utterance]:
        """That person's lines in script order — session 1 samples from these."""
        return [u for u in self.utterances if u.speaker == person]


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


def _utterances_of(scene_id: str, scene: dict) -> Iterator[tuple[int | None, str, str, str]]:
    """Yield (id, role, text, where) for every utterance of a scene, in order.

    `role` is 'caller' or 'called'; resolving that to a person needs the
    scene's parties, which validation checks separately.
    """
    request = scene.get("request")
    if isinstance(request, dict):
        yield request.get("id"), "caller", request.get("text", ""), "request"
    conversation = scene.get("conversation") or []
    if isinstance(conversation, list):
        for i, line in enumerate(conversation):
            if not isinstance(line, dict):
                continue
            where = f"conversation[{i}]"
            if "caller" in line:
                yield line.get("id"), "caller", line["caller"], where
            elif "called" in line:
                yield line.get("id"), "called", line["called"], where


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

    # --- lines: a name is a station or an outside entry, and never both -----
    both = sorted(set(stations) & set(outside))
    for name in both:
        bad(f"{name}", "is both a station and an outside entry")
    lines = set(stations) | set(outside)

    # --- station and outside numbering --------------------------------------
    seen_station: dict[int, str] = {}
    for name, entry in stations.items():
        number = (entry or {}).get("number")
        if not isinstance(number, int) or isinstance(number, bool):
            bad(f"stations.{name}.number", f"not an integer: {number!r}")
            continue
        if not MIN_STATION <= number <= MAX_STATION:
            bad(f"stations.{name}.number", f"{number} outside {MIN_STATION}-{MAX_STATION}")
        if number in seen_station:
            bad(f"stations.{name}.number", f"{number} already used by {seen_station[number]}")
        else:
            seen_station[number] = name

    seen_outside: dict[str, str] = {}
    for name, entry in outside.items():
        number = (entry or {}).get("number")
        if not isinstance(number, str):
            bad(f"outside.{name}.number", f"not a string: {number!r} — quote it")
            continue
        if number in seen_outside:
            bad(f"outside.{name}.number", f"{number} already used by {seen_outside[number]}")
        else:
            seen_outside[number] = name

    # --- scenes --------------------------------------------------------------
    utterances: list[Utterance] = []
    for scene_id, scene in scenes.items():
        if not isinstance(scene, dict):
            bad(f"scenes.{scene_id}", "not a mapping")
            continue

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

        # after: names a scene, and that scene has no after of its own
        after = scene.get("after")
        if after is not None:
            if after not in scenes:
                bad(f"scenes.{scene_id}.after", f"{after!r} is not a scene")
            elif isinstance(scenes[after], dict) and scenes[after].get("after") is not None:
                bad(f"scenes.{scene_id}.after",
                    f"{after!r} has an after of its own; chains of more than two are not allowed")
            elif after == scene_id:
                bad(f"scenes.{scene_id}.after", "names itself")

        # utterances: integer ids, unique in the scene, legal file names
        seen_id: dict[int, str] = {}
        for uid, role, text, where in _utterances_of(scene_id, scene):
            at = f"scenes.{scene_id}.{where}"
            if not isinstance(uid, int) or isinstance(uid, bool):
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
            u = Utterance(scene=scene_id, id=uid, speaker=speaker, text=text.strip())
            why = name_problem(u.name)
            if why is not None:
                bad(at, f"file name {u.name!r} is not usable: {why}")
                continue
            utterances.append(u)

        if not seen_id:
            bad(f"scenes.{scene_id}", "has no utterances")

    if fail:
        raise ScriptError(path, fail)

    return Script(path=path, setting=data.get("setting") or {}, cast=cast,
                  outside=outside, stations=stations, scenes=scenes,
                  utterances=utterances)


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
    print(f"{script.path}: {len(script.scenes)} scenes, {len(script.utterances)} utterances, "
          f"{len(script.cast)} cast")
    if silent:
        print(f"cast with no lines: {', '.join(silent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
