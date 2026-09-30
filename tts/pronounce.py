"""Pronunciation substitution (tts_task.md 6.2).

Applied only to the text handed to the model. The script's own text is never
changed: what `script.yml` says is what the scene says, and this is only how it
is spoken.

Lives here rather than in the remote generator because the manifest (6.3)
hashes the substituted text to decide what needs regenerating, and that
decision is made locally, before any instance is launched.

Two kinds of entry. Top-level ones apply to every line and match the key's
exact case. Entries under `speakers:` apply only to that cast member's lines,
match whatever the case, and are applied first: one person's accent is kept
off everyone else's lines without spelling the script around it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from ruamel.yaml import YAML

DEFAULT_TABLE = Path(__file__).resolve().parent / "pronounce.yml"


Entries = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Table:
    general: Entries = ()
    speakers: dict[str, Entries] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.general) + sum(len(e) for e in self.speakers.values())


def _longest_first(raw: dict) -> Entries:
    """Longest key first, so "284-1187" is taken before "284" would be."""
    return tuple(sorted(((str(k), str(v)) for k, v in raw.items()),
                        key=lambda kv: len(kv[0]), reverse=True))


@lru_cache(maxsize=4)
def load_table(path: Path | str = DEFAULT_TABLE) -> Table:
    yaml = YAML(typ="safe")
    yaml.allow_duplicate_keys = False
    raw = yaml.load(Path(path).read_text(encoding="utf-8")) or {}
    speakers = raw.pop("speakers", None) or {}
    if not isinstance(speakers, dict) or not all(isinstance(v, dict) for v in speakers.values()):
        raise ValueError(f"{path}: speakers: must map each cast member to a table")
    return Table(_longest_first(raw),
                 {str(p): _longest_first(e) for p, e in speakers.items()})


def unknown_speakers(table: Table, cast) -> list[str]:
    """Speakers the table names who are not in the cast: a misspelt name would
    otherwise be an entry that silently never applies."""
    return sorted(p for p in table.speakers if p not in cast)


def _restore_case(replacement: str, at_sentence_start: bool) -> str:
    """"OK. 463." must not become "OK. four sixty-three."."""
    if at_sentence_start and replacement[:1].islower():
        return replacement[0].upper() + replacement[1:]
    return replacement


def _apply(text: str, entries: Entries, flags: int = 0) -> str:
    for key, value in entries:
        # Hyphens and digits count as word characters here: 284 must not match
        # inside 284-1187, and 463 must not match inside 4630.
        pattern = re.compile(rf'(?<![\w-]){re.escape(key)}(?![\w-])', flags)

        def repl(m: re.Match[str]) -> str:
            before = text[:m.start()].rstrip()
            starts = not before or before[-1] in ".!?"
            return _restore_case(value, starts)

        text = pattern.sub(repl, text)
    return text


def substitute(text: str, table: Table | None = None, speaker: str | None = None) -> str:
    """Whole-word substitution, preserving sentence capitalisation: the
    speaker's own entries first, any case, then the general ones, exact case."""
    if table is None:
        table = load_table()
    if speaker is not None:
        text = _apply(text, table.speakers.get(speaker, ()), re.IGNORECASE)
    return _apply(text, table.general)


def main(argv: list[str] | None = None) -> int:
    import argparse
    from tts.script import DEFAULT_SCRIPT, ScriptError, load

    p = argparse.ArgumentParser(description="Show every line the table changes.")
    p.add_argument("--script", default=DEFAULT_SCRIPT)
    p.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    args = p.parse_args(argv)
    try:
        script = load(args.script)
    except ScriptError as e:
        for f in e.failures:
            print(f"  {f}")
        return 1

    table = load_table(args.table)
    unknown = unknown_speakers(table, script.cast)
    if unknown:
        print(f"  {args.table}: speakers: names {', '.join(unknown)}, not in the cast")
        return 1
    changed = 0
    for u in script.utterances:
        out = substitute(u.text, table, u.speaker)
        if out != u.text:
            changed += 1
            print(f"{u.name}\n  in:  {u.text}\n  out: {out}")
    print(f"\n{len(table)} entries changed {changed} of {len(script.utterances)} utterances")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
