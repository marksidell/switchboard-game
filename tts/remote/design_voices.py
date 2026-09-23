#!/usr/bin/env python3
"""Session 1, on the instance: three candidate voices per cast member.

tts_task.md 5.3. Writes <person>.<k>.wav and <person>.<k>.json for k in 1..3
into the output directory, which the session script copies back.

The .json is not bookkeeping for its own sake: session 2 clones from the chosen
candidate and needs that candidate's exact sample text back as the reference
transcript (5.2), and a seed is what makes a voice reproducible if the file is
ever lost.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tts.prompt import LANGUAGE, sample_text, voice_prompt   # noqa: E402
from tts.script import ScriptError, load                     # noqa: E402

MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
TAKES = 3


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--script", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--only", default="", help="comma-separated cast keys")
    p.add_argument("--takes", type=int, default=TAKES)
    p.add_argument("--model", default=MODEL)
    p.add_argument("--seed-base", type=int, default=1950)
    args = p.parse_args()

    try:
        script = load(args.script)
    except ScriptError as e:
        for f in e.failures:
            print(f"  {f}", file=sys.stderr)
        return 1

    wanted = [w for w in args.only.split(",") if w] or list(script.cast)
    unknown = [w for w in wanted if w not in script.cast]
    if unknown:
        print(f"not in the cast: {', '.join(unknown)}", file=sys.stderr)
        return 1

    from qwen_tts import Qwen3TTSModel

    t0 = time.monotonic()
    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
    model = Qwen3TTSModel.from_pretrained(args.model, dtype=dtype,
                                          device_map="cuda:0" if torch.cuda.is_available() else "cpu")
    print(f"loaded {args.model} as {dtype} in {time.monotonic() - t0:.1f}s", flush=True)

    args.out.mkdir(parents=True, exist_ok=True)
    made = 0
    for person in wanted:
        entry = script.cast[person]
        instruct = voice_prompt(person, entry)
        text, used = sample_text(script, person)
        for k in range(1, args.takes + 1):
            seed = args.seed_base + k
            torch.manual_seed(seed)
            t0 = time.monotonic()
            wavs, rate = model.generate_voice_design(text=text, instruct=instruct,
                                                     language=LANGUAGE)
            took = time.monotonic() - t0
            audio = np.asarray(wavs[0], dtype=np.float32)
            wav = args.out / f"{person}.{k}.wav"
            sf.write(str(wav), audio, rate)
            (args.out / f"{person}.{k}.json").write_text(json.dumps({
                "person": person, "take": k, "seed": seed, "model": args.model,
                "instruct": instruct, "sample_text": text,
                "sample_from": [u.name for u in used],
                "rate": int(rate), "seconds": len(audio) / rate,
                "generate_seconds": round(took, 2),
            }, indent=2) + "\n", encoding="utf-8")
            made += 1
            print(f"  {wav.name:<24} {len(audio)/rate:5.2f}s @{rate}Hz in {took:5.1f}s", flush=True)

    print(f"{made} candidates for {len(wanted)} cast members in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
