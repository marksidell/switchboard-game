"""Recorded parts (tts_task.md §6.4).

A cast member with `recorded: <performer>` is performed by a person: each of
their lines is a take in tts/recorded/<scene>.<id>.wav, never rendered.
tts/recorded/takes.json says, for each take, who read it, when, and a hash of
the script text it was read from, so an edit to the line shows as a re-take.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from tts.script import Script, Utterance

RECORDED = Path("tts/recorded")
TAKES = RECORDED / "takes.json"


def performers(script: Script) -> dict[str, str]:
    """Cast member -> performer, for every recorded part."""
    return {p: str(e["recorded"]) for p, e in script.cast.items()
            if isinstance(e, dict) and e.get("recorded")}


def text_hash(text: str) -> str:
    """The script's own text, as the performer read it — not the §6.2
    substitution, which is for the model."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


def load_takes(path: Path = TAKES) -> dict[str, dict]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_takes(takes: dict[str, dict], path: Path = TAKES) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(takes, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def note_take(takes: dict[str, dict], u: Utterance, performer: str) -> None:
    takes[u.name] = {"performer": performer, "date": date.today().isoformat(),
                     "text_sha": text_hash(u.text)}


@dataclass
class Line:
    utterance: Utterance
    performer: str
    state: str          # "ok", "to record" or "re-take"


def status(script: Script, takes: dict[str, dict] | None = None,
           recorded: Path = RECORDED) -> list[Line]:
    """Every line of every recorded part, in script order, and where it stands."""
    who = performers(script)
    takes = load_takes(recorded / "takes.json") if takes is None else takes
    out: list[Line] = []
    for u in script.utterances:
        if u.speaker not in who:
            continue
        take = takes.get(u.name)
        if take is None or not (recorded / f"{u.name}.wav").exists():
            state = "to record"
        elif take.get("text_sha") != text_hash(u.text):
            state = "re-take"
        else:
            state = "ok"
        out.append(Line(u, who[u.speaker], state))
    return out
