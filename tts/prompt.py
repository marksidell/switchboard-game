"""Voice prompts and sample text for session 1 (tts_task.md 5.1, 5.2).

Kept in one small module so Mark can edit the wording without going near the
session machinery — the template is the thing most likely to want changing
after the first listen.
"""

from __future__ import annotations

from tts.script import Script, Utterance

# The model takes language names in full, not ISO codes: passing "en" raises
# ValueError with the supported list, which is ['auto', 'chinese', 'english',
# 'french', 'german', 'italian', 'japanese', 'korean', 'portuguese', 'russian',
# 'spanish'].
LANGUAGE = "english"

# tts_task.md 5.1. A cast entry may carry a `voice:` field, which is used
# verbatim instead; none does yet.
TEMPLATE = (
    "A {sex} voice. Accent: {accent}. {description}.\n"
    "Natural, conversational telephone speech, 1950s."
)

# 5.2: if the first line is shorter than this, the next one is appended, so
# Mark judges a voice on enough speech to judge.
MIN_SAMPLE_SECONDS = 5.0

# Conversational speech, unhurried, in words per second. Only used to decide
# whether one line is enough; nothing downstream depends on it being right.
WORDS_PER_SECOND = 2.6


def voice_prompt(person: str, entry: dict) -> str:
    """The description the VoiceDesign model is given for this cast member.

    Qualities only. A prompt never names a real person or asks for an
    imitation of one (5.1).
    """
    verbatim = entry.get("voice")
    if verbatim:
        return str(verbatim).strip()
    missing = [k for k in ("sex", "accent", "description") if not entry.get(k)]
    if missing:
        raise ValueError(f"cast.{person} has no {', '.join(missing)}")
    return TEMPLATE.format(sex=entry["sex"], accent=entry["accent"],
                           description=str(entry["description"]).rstrip("."))


def estimate_seconds(text: str) -> float:
    return len(text.split()) / WORDS_PER_SECOND


def sample_text(script: Script, person: str) -> tuple[str, list[Utterance]]:
    """The character's first line, plus the next if the first is too short.

    Returns the text and the utterances it came from. Session 2 needs this
    exact string back as the reference transcript for voice cloning, so it is
    recorded beside every candidate rather than recomputed.
    """
    lines = script.first_lines(person)
    if not lines:
        raise ValueError(f"{person} has no lines in the script")
    used = [lines[0]]
    if estimate_seconds(lines[0].text) < MIN_SAMPLE_SECONDS and len(lines) > 1:
        used.append(lines[1])
    return " ".join(u.text for u in used), used


def main(argv: list[str] | None = None) -> int:
    import argparse
    from tts.script import DEFAULT_SCRIPT, ScriptError, load

    p = argparse.ArgumentParser(description="Show the voice prompt and sample text per cast member.")
    p.add_argument("--script", default=DEFAULT_SCRIPT)
    p.add_argument("--only", default="", help="comma-separated cast keys")
    args = p.parse_args(argv)
    try:
        script = load(args.script)
    except ScriptError as e:
        for f in e.failures:
            print(f"  {f}")
        return 1

    wanted = {w for w in args.only.split(",") if w} or set(script.cast)
    for person, entry in script.cast.items():
        if person not in wanted:
            continue
        text, used = sample_text(script, person)
        print(f"--- {person} ({len(script.first_lines(person))} lines) ---")
        print(voice_prompt(person, entry))
        print(f"  sample [{', '.join(u.name for u in used)}, "
              f"~{estimate_seconds(text):.1f}s]: {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
