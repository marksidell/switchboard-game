# Speech generation

Turns every scripted line into a wav the audio program will play, per
`docs/tts_task.md`. Qwen3-TTS does the speaking on a rented GPU; the
telephone band-limiting happens here, on any machine, with no GPU.

The script itself is `script.yml` at the top of the repo, shared with the game
program; this pipeline reads it and never writes it.

## Order of work

```sh
# 0. once: the venv this uses
python3 -m venv tts/.venv && tts/.venv/bin/pip install ruamel.yaml numpy scipy soundfile soxr

# 1. is the script sound?
tts/.venv/bin/python -m tts.script              # scenes, utterances, cast

# 2. session 1: three candidate voices per cast member
tts/aws/design --bake                           # --bake only on the first run
tts/.venv/bin/python -m tts.process \
    --raw tts/voices/candidates --out tts/voices/preview --no-script

# 3. audition them and record the choices
tts/audition                                    # plays on the Digiface headphone jack
tts/choose                                      # promotes the raw candidates

# 4. session 2: every line, in the chosen voices
tts/aws/generate --dry                          # what would be generated, and why
tts/aws/generate

# 5. deliver
tts/.venv/bin/python -m tts.process             # tts/raw -> wav/

# 6. always
tts/aws/status                                  # nothing should be running
```

`tts/audition` and `tts/choose` re-exec themselves under `tts/.venv`, so they can be
run straight from the repo root with no prefix and from any directory. If either one
fails with `ModuleNotFoundError`, step 0 has not been run: there is no venv for them to
find, and they fall back to the system python. The modules invoked as `python -m tts.*`
have no such trick and always need the interpreter named, as above. The two scripts in
`tts/remote/` deliberately do not re-exec — on the instance the venv is `~/tts-venv`,
not `tts/.venv`, and `aws/design` and `aws/generate` name that interpreter themselves.

Listen to `tts/voices/preview/`, not `tts/voices/candidates/`. The candidates are
full-bandwidth; the previews are through the telephone band, which is how the
audience hears them and is the only fair basis for choosing.

## What each piece is

| | |
| --- | --- |
| `script.py` | loads and validates the script; rejects duplicate keys, reports every fault at once |
| `prompt.py` | the voice-description template and the sample-text rule |
| `pronounce.py`, `pronounce.yml` | how numbers and names are spoken; never alters the script |
| `manifest.py` | decides what needs regenerating, before anything is launched |
| `process.py` | mono, trim, 16kHz, 300–3400Hz, level, 48kHz, 24-bit, then check and delete on failure |
| `audition` | plays each cast member's three candidates and records the choice |
| `choose` | promotes the candidates named in `voices.yml` |
| `aws/` | session machinery; `IAM-SETUP.md` is the credential and policy record |
| `remote/` | what runs on the instance; `NOTES.md` holds the measured model facts |

## Two things worth knowing before changing anything

**Nothing is left running.** `aws/teardown` terminates every instance tagged
`project=sbgame-tts`, the session scripts call it from a trap that fires on
success, error and Ctrl-C, and every instance is launched with
`shutdown -h +120` and terminate-on-shutdown. All three layers are required by
`tts_task.md` §4.4, and all three have now fired in anger.

**`process.py` gates on a transform, not on audio.md §7.2's meter.** That meter
is two Butterworth biquads at 5.5kHz, which at 48kHz passes the top of the
telephone band at only 19dB down and so reports wanted speech as if it were
energy above the corner. The comment in `process.py` has the measured tables.
`sbaudio` will log a content warning for files that are in fact clean; fixing
that is a change to `audio/src/wav.cpp` and to audio.md §7.2, and is not part of
this task.
