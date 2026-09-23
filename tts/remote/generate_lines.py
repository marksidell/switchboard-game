#!/usr/bin/env python3
"""Session 2, on the instance: speak each line in the chosen voice.

tts_task.md 6.1. Takes the job list the local side computed (6.3) — deciding
what needs generating is not this script's business, and doing it here would
mean uploading the whole script and manifest to work it out again.

Writes raw model output; all band-limiting happens locally in tts/process.py.
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

MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
LANGUAGE = "english"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--jobs", type=Path, required=True, help="job list as JSON")
    p.add_argument("--voices", type=Path, required=True, help="reference voices")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--model", default=MODEL)
    p.add_argument("--batch", type=int, default=1,
                   help="lines per call; the API takes lists and the GPU is "
                        "badly used at 1, but takes are per-seed so a batch "
                        "shares its seed")
    args = p.parse_args()

    jobs = json.loads(args.jobs.read_text(encoding="utf-8"))
    if not jobs:
        print("nothing to generate")
        return 0

    from qwen_tts import Qwen3TTSModel

    t0 = time.monotonic()
    cuda = torch.cuda.is_available()
    model = Qwen3TTSModel.from_pretrained(
        args.model, dtype=torch.bfloat16 if cuda else torch.float32,
        device_map="cuda:0" if cuda else "cpu")
    print(f"loaded {args.model} in {time.monotonic() - t0:.1f}s "
          f"on {'cuda' if cuda else 'cpu'}", flush=True)

    args.out.mkdir(parents=True, exist_ok=True)
    done = failed = 0
    started = time.monotonic()

    for i in range(0, len(jobs), args.batch):
        chunk = jobs[i:i + args.batch]
        torch.manual_seed(chunk[0]["seed"])
        refs = [str(args.voices / Path(j["ref_wav"]).name) for j in chunk]
        missing = [r for r in refs if not Path(r).exists()]
        if missing:
            print(f"  missing reference voice: {', '.join(missing)}", file=sys.stderr)
            failed += len(chunk)
            continue
        t0 = time.monotonic()
        try:
            wavs, rate = model.generate_voice_clone(
                text=[j["text"] for j in chunk],
                ref_audio=refs,
                ref_text=[j["ref_text"] for j in chunk],
                language=LANGUAGE)
        except Exception as e:                       # one bad line must not lose the session
            print(f"  {', '.join(j['name'] for j in chunk)} FAILED: {e}", file=sys.stderr)
            failed += len(chunk)
            continue
        took = time.monotonic() - t0
        for j, w in zip(chunk, wavs):
            audio = np.asarray(w, dtype=np.float32)
            sf.write(str(args.out / f"{j['name']}.wav"), audio, rate)
            print(f"  {j['name']:<22} {j['speaker']:<12} {len(audio)/rate:5.2f}s "
                  f"@{rate}Hz  {took/len(chunk):5.1f}s", flush=True)
            done += 1

    elapsed = time.monotonic() - started
    print(f"\n{done} written, {failed} failed, {elapsed/60:.1f} min "
          f"({elapsed/max(done, 1):.1f}s per line)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
