"""What was generated from what (tts_task.md 6.3).

A line is regenerated only when something it depends on changed: the words
after pronunciation substitution, the reference voice, the model, or the seed.
So editing one line, adding a scene, or re-choosing one character's voice
regenerates only the lines affected — which at 700-odd utterances is the
difference between a session and a coffee.

The decision is made here, locally, before any instance is launched. The
instance is handed a list of jobs and nothing else.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from tts.pronounce import load_table, substitute, unknown_speakers
from tts.recorded import performers, status
from tts.script import Script, Utterance

DEFAULT_MANIFEST = Path("tts/manifest.json")
VOICES = Path("tts/voices")
PRIVATE = Path("private")    # the two private voices, not in the repo (tts_task.md 5.1)
DEFAULT_RAW = Path("tts/raw")
MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
SEED_BASE = 1950


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def text_hash(text: str) -> str:
    return _sha(text.encode("utf-8"))


def file_hash(path: Path) -> str:
    return _sha(path.read_bytes()) if path.exists() else ""


@dataclass
class Job:
    """One line to generate, and everything the model needs to do it."""
    name: str
    scene: str
    id: int | str        # a tutor line's id is its key (script.py)
    speaker: str
    text: str            # after substitution — what is actually spoken
    ref_wav: str         # relative to the repo, uploaded with the job
    ref_text: str
    seed: int
    model: str
    text_sha: str
    voice_sha: str
    reason: str = ""


def reference_text(person: str, voices: Path = VOICES) -> str:
    """The sample text the chosen candidate spoke, which cloning needs (5.2)."""
    meta = voices / f"{person}.json"
    if not meta.exists():
        raise FileNotFoundError(f"{meta} is missing; run tts/choose first")
    return json.loads(meta.read_text(encoding="utf-8"))["sample_text"]


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, dict]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(entries: dict[str, dict], path: Path = DEFAULT_MANIFEST) -> None:
    path.write_text(json.dumps(entries, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def private_speakers(public: bool = False) -> set[str]:
    """Who speaks in a private voice: nobody with --public, or with no private/."""
    return set() if public else {v.stem for v in (PRIVATE / "voices").glob("*.wav")}


def plan(script: Script, *, voices: Path = VOICES, wav_dir: Path = Path("wav"),
         manifest: dict[str, dict] | None = None, model: str = MODEL,
         seed_base: int = SEED_BASE, only: set[str] | None = None,
         speakers: set[str] | None = None) -> list[Job]:
    """Which lines need generating, and why. Order follows the script.
    With speakers, only theirs."""
    manifest = {} if manifest is None else manifest
    only = only or set()
    jobs: list[Job] = []
    recorded = performers(script)       # §6.4: never rendered

    for u in script.utterances:
        if u.speaker in recorded or (speakers is not None and u.speaker not in speakers):
            continue
        spoken = substitute(u.text, speaker=u.speaker)
        t_sha = text_hash(spoken)
        ref_wav = voices / f"{u.speaker}.wav"
        v_sha = file_hash(ref_wav)
        was = manifest.get(u.name)

        forced = u.name in only or u.scene in only
        if forced:
            # A new seed, so Mark gets a different take rather than the same one.
            seed = int(was.get("seed", seed_base)) + 1 if was else seed_base
            reason = "forced"
        else:
            seed = int(was["seed"]) if was else seed_base
            if was is None:
                reason = "new"
            elif not (wav_dir / f"{u.name}.wav").exists():
                reason = "delivered file missing"
            elif was.get("text_sha") != t_sha:
                reason = "text changed"
            elif was.get("voice_sha") != v_sha:
                reason = "reference voice changed"
            elif was.get("model") != model:
                reason = "model changed"
            else:
                continue

        jobs.append(Job(name=u.name, scene=u.scene, id=u.id, speaker=u.speaker,
                        text=spoken, ref_wav=str(ref_wav),
                        ref_text=reference_text(u.speaker, voices), seed=seed,
                        model=model, text_sha=t_sha, voice_sha=v_sha, reason=reason))
    return jobs


def record(entries: dict[str, dict], job: Job) -> None:
    entries[job.name] = {k: v for k, v in asdict(job).items()
                         if k in ("speaker", "seed", "model", "text_sha", "voice_sha")}


def main(argv: list[str] | None = None) -> int:
    import argparse
    from collections import Counter
    from tts.script import DEFAULT_SCRIPT, ScriptError, load

    p = argparse.ArgumentParser(description="Show what session 2 would generate, and why.")
    p.add_argument("--script", default=DEFAULT_SCRIPT)
    p.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    p.add_argument("--voices", type=Path, default=VOICES)
    p.add_argument("--wav", type=Path, default=Path("wav"))
    p.add_argument("--only", default="")
    p.add_argument("--write-jobs", type=Path,
                   help="write the job list as JSON for the remote generator")
    p.add_argument("--record", type=Path,
                   help="a job list that has been generated: record those that produced a file")
    p.add_argument("--raw", type=Path, default=DEFAULT_RAW,
                   help="with --record, where the session's files came back to")
    p.add_argument("--public", action="store_true",
                   help="the public voices for everyone, none from private/")
    args = p.parse_args(argv)
    private = private_speakers(args.public)

    if args.record:
        # Each file goes from where it came back to beside the others of its
        # set, so a failed line cannot be recorded on the strength of an old file.
        jobs = json.loads(args.record.read_text(encoding="utf-8"))
        entries = load_manifest(args.manifest)
        private_entries = load_manifest(PRIVATE / "manifest.json") if private else {}
        kept = missing = 0
        for d in jobs:
            mine = d["speaker"] in private
            book = private_entries if mine else entries
            src = args.raw / f"{d['name']}.wav"
            if src.exists():
                dst = (PRIVATE / "raw" if mine else DEFAULT_RAW) / src.name
                dst.parent.mkdir(parents=True, exist_ok=True)
                src.replace(dst)
                record(book, Job(**{k: v for k, v in d.items()
                                    if k in Job.__dataclass_fields__}))
                kept += 1
            else:
                book.pop(d["name"], None)      # it must be tried again next time
                missing += 1
        save_manifest(entries, args.manifest)
        if private:
            save_manifest(private_entries, PRIVATE / "manifest.json")
        print(f"recorded {kept}, {missing} produced no file and stay unrecorded")
        return 1 if missing else 0

    try:
        script = load(args.script)
    except ScriptError as e:
        for f in e.failures:
            print(f"  {f}")
        return 1
    unknown = unknown_speakers(load_table(), script.cast)
    if unknown:
        print(f"  tts/pronounce.yml speakers: names {', '.join(unknown)}, not in the cast")
        return 1
    try:
        only = {o for o in args.only.split(",") if o}
        everyone = {u.speaker for u in script.utterances}
        jobs = plan(script, voices=args.voices, wav_dir=args.wav,
                    manifest=load_manifest(args.manifest), only=only,
                    speakers=everyone - private)
        if private:
            jobs += plan(script, voices=PRIVATE / "voices", wav_dir=PRIVATE / "wav",
                         manifest=load_manifest(PRIVATE / "manifest.json"), only=only,
                         speakers=private)
    except FileNotFoundError as e:
        print(f"  {e}")
        return 1

    if args.write_jobs:
        args.write_jobs.write_text(
            json.dumps([asdict(j) for j in jobs], indent=2) + "\n", encoding="utf-8")

    why = Counter(j.reason for j in jobs)
    for j in jobs[:10]:
        print(f"{j.name:<22} {j.speaker:<12} seed {j.seed:<6} {j.reason}")
    if len(jobs) > 10:
        print(f"… and {len(jobs) - 10} more")
    print(f"\n{len(jobs)} of {len(script.utterances)} to generate: "
          + ", ".join(f"{n} {r}" for r, n in why.most_common()))
    lines = status(script)
    if lines:
        s = Counter(l.state for l in lines)
        print(f"recorded parts (tts_task.md 6.4), not generated: {len(lines)} lines, "
              f"{s['ok']} taken, {s['to record']} to record, {s['re-take']} re-take"
              + ("  — tts/record --status" if s["to record"] or s["re-take"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
