# Qwen3-TTS, as found

Measured facts, so the next session does not rediscover them. Everything here was
established on 2026-09-22 with `qwen-tts` 0.1.1 unless stated.

## Output sample rate — 24000 Hz

`tts_task.md` §4.5 records this as unknown. `generate_voice_design` and
`generate_voice_clone` both return `(list[np.ndarray], int)`, and the int is the sample
rate: **24000**. `tts/process.py` resamples from whatever arrives, so nothing depends on
this staying true, but it is what to expect.

## API

The package is self-contained — the model repo carries its own processor, so the
separate `Qwen/Qwen3-TTS-Tokenizer-12Hz` repo does not need to be fetched by hand.

```python
from qwen_tts import Qwen3TTSModel
model = Qwen3TTSModel.from_pretrained(repo_id, dtype=torch.bfloat16, device_map="cuda:0")
wavs, rate = model.generate_voice_design(text=..., instruct=..., language="english")
wavs, rate = model.generate_voice_clone(text=..., ref_audio=..., ref_text=..., language="english")
```

**Language names are words, not codes.** `language="en"` raises
`ValueError: Unsupported languages: ['en']`. The accepted set is `auto`, `chinese`,
`english`, `french`, `german`, `italian`, `japanese`, `korean`, `portuguese`, `russian`,
`spanish`. Kept as `LANGUAGE` in `tts/prompt.py`.

## Two installation traps

Both were hit locally, and both would otherwise have been found on a GPU that is being
paid for by the minute. `tts/remote/setup.sh` guards against both.

1. **torchaudio comes from PyPI as a CUDA build** whatever torch is already present.
   Against a mismatched torch, `import qwen_tts` fails with
   `OSError: libcudart.so.13: cannot open shared object file`. The failure is at import,
   long after the install reported success.
2. **The `sox` Python package shells out to the `sox` binary**, which is not necessarily
   on the image. Missing, it prints "SoX could not be found!" at import and fails later.
   `apt-get install sox`.

`flash-attn` is absent by default and the package says so loudly on every import. It is
a speed and memory optimisation only; `tts_task.md` §4.3 chose g6/g5 because the model
recommends it, but nothing fails without it.

## CPU timing, for tts_task.md §10

GEEKOM, AMD Ryzen 5 7430U, 12 threads (torch used 6), float32, no GPU.

| | |
| --- | --- |
| Model load, weights already cached | 7.3s |
| Generated | 7.84s of audio from 19 words |
| Wall clock | 54.2s — **6.9x slower than realtime** |
| Per word | 2.86s of compute |
| Resident memory | 8.4GB |

Scaled by word count over the real script — 525 words in 71 utterances:

- **~25 minutes** for the whole script, one take per line.
- **~46 minutes** for the 51 design candidates of session 1.
- The average line is 7.4 words, so **about 21 seconds per line**.

§10's test was "if a line takes under a minute, the whole script is a lunch break and the
AWS path becomes optional". A line takes 21 seconds. Both sessions together are a little
over an hour of CPU on a machine that is already owned.

Two things this does not measure: the Base model used for cloning in session 2 may not
have the same speed as VoiceDesign, and 8.4GB resident is most of the GEEKOM's 15GB, so
the machine is not much use for anything else while it runs.
