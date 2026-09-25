**551 Switchboard Simulator**

**Speech Generation Task — for Claude Code**

*Task 1 — 2026-09-22. Generate every scripted line in `script.yml` as a wav file the audio program will play, using Qwen3-TTS on a short-lived AWS GPU instance, with the telephone band-limiting done locally.*

# 1. What This Produces

One file per utterance in `script.yml`, `wav/<scene-id>.<utterance-id>.wav`, ready for the audio program's `play/set` (audio.md §7). For the script as it stands that is 13 scenes and 71 files.

Along the way it produces one reference voice per cast member, chosen by Mark by ear, which every line for that character is then generated from.

Nothing here touches `control/control.ino` or the audio program's source. This is new code under `tts/`.

# 2. Constraints the Output Must Meet

These come from documents already in force. Do not relax any of them.

- **Name.** Base name `<scene-id>.<utterance-id>`, 31 characters or less, no `/`, `\` or `..`, never `stop` (audio.md §7.1, mqtt.md §7).
- **Format.** 48000Hz, one channel. 16-bit, 24-bit or float PCM are all accepted; write 24-bit. Anything else is rejected by the audio program on load (audio.md §7.2).
- **Length.** Under 120 seconds. Every scripted line is a few seconds.
- **Nothing above 5.5kHz.** Energy above 5.5kHz must be below −60dBFS. The pilot comb starts at 6000Hz at −40dBFS and the detector margin is 20dB, so speech energy up there comes back on the circuit's own receive channel and can read as a pilot (audio.md §5.3). The audio program only warns about this; this pipeline must refuse to write a file that fails it.
- **Period band-limiting.** Speech is authored at 16kHz and band-limited to the telephone band, then delivered at 48kHz (station §8.8). Nothing wanted lives above about 3.5kHz.

# 3. The Script

`script.yml` is the source. Its header comments define the format; the parts this task depends on:

- `cast:` — keyed by person. Each has `sex`, `accent` and `description`. These are what the voice prompt is built from (§5.1).
- `scenes:` — keyed by scene id. Each has `calling` (a `line` and a `person`), optionally `called` (the same), a `request` (`id` and `text`), and optionally a `conversation` list whose entries are `id` plus either `caller:` or `called:` with the text.
- The request is spoken by the calling person. A `caller:` line is spoken by `calling.person`, a `called:` line by `called.person`.
- `after:`, `delay:` and `busy:` do not affect speech generation.

## 3.1 Loader and Validation — `tts/script.py`

Write one loader, used by every step here, and written so the game program can import it later.

- **Reject duplicate keys** at every level. PyYAML silently keeps the last of a repeated key, which already lost two lines of a scene once in this project. Use ruamel.yaml, which rejects them by default, or give PyYAML a mapping constructor that raises.
- **Cross-check**, and exit non-zero listing every failure, not just the first:
  - every `line` names a station or an outside entry, and no name is both;
  - every `person` names a cast member;
  - every `after` names a scene that has no `after` of its own;
  - station numbers are unique and within 1–23; outside numbers are strings and unique;
  - utterance ids are integers and unique within their scene;
  - every file name meets §2.
- **Enumerate utterances** as (scene id, utterance id, speaker, text), in script order.

`python -m tts.script` runs the checks and prints the utterance count. Every other step runs it first and stops if it fails.

# 4. AWS

Mark's account. Region **us-west-2**.

## 4.1 Before the First Run — Mark

1. **GPU quota.** Service Quotas → EC2 → "Running On-Demand G and VT instances" must be at least 4 vCPUs (one xlarge). Many accounts start at 0 and an increase can take a day. Claude Code can read it: `aws service-quotas get-service-quota --service-code ec2 --quota-code L-DB2E81BA --region us-west-2` — confirm the quota code in the console rather than trusting this line.
2. **Credentials.** A dedicated profile, `sbgame-tts`, used on every AWS call with `--profile sbgame-tts`. The draft policy is §4.2. Mark reviews it, which is his field, and tests it with `--dry-run` before the first real launch.
3. **Budget alert.** A small AWS Budgets alert on the account is cheap insurance. Optional.

## 4.2 Draft IAM Policy

A starting point, not a finished policy. The known rough edge: `CreateSecurityGroup` is authorised against the VPC as well as the new group, and a request-tag condition cannot match the VPC, so that statement may need splitting by resource. Test every action with `--dry-run`.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Sid": "OneRegionOnly", "Effect": "Deny", "Action": "ec2:*", "Resource": "*",
      "Condition": { "StringNotEquals": { "aws:RequestedRegion": "us-west-2" } } },

    { "Sid": "Read", "Effect": "Allow",
      "Action": ["ec2:Describe*", "ssm:GetParameter", "ssm:GetParameters", "servicequotas:GetServiceQuota"],
      "Resource": "*" },

    { "Sid": "LaunchTaggedGpuOnly", "Effect": "Allow", "Action": "ec2:RunInstances",
      "Resource": "arn:aws:ec2:us-west-2:*:instance/*",
      "Condition": { "StringEquals": { "ec2:InstanceType": ["g6.xlarge", "g5.xlarge"],
                                       "aws:RequestTag/project": "sbgame-tts" } } },

    { "Sid": "LaunchSupportingResources", "Effect": "Allow", "Action": "ec2:RunInstances",
      "Resource": ["arn:aws:ec2:us-west-2:*:volume/*", "arn:aws:ec2:us-west-2:*:network-interface/*",
                   "arn:aws:ec2:us-west-2:*:subnet/*", "arn:aws:ec2:us-west-2:*:security-group/*",
                   "arn:aws:ec2:us-west-2:*:key-pair/*", "arn:aws:ec2:us-west-2::image/*"] },

    { "Sid": "TagOnlyOnCreate", "Effect": "Allow", "Action": "ec2:CreateTags", "Resource": "*",
      "Condition": { "StringEquals": { "ec2:CreateAction": ["RunInstances", "CreateSecurityGroup", "CreateKeyPair"] } } },

    { "Sid": "CreateOwnSupport", "Effect": "Allow",
      "Action": ["ec2:CreateSecurityGroup", "ec2:CreateKeyPair"], "Resource": "*",
      "Condition": { "StringEquals": { "aws:RequestTag/project": "sbgame-tts" } } },

    { "Sid": "ManageOnlyOwn", "Effect": "Allow",
      "Action": ["ec2:TerminateInstances", "ec2:AuthorizeSecurityGroupIngress",
                 "ec2:RevokeSecurityGroupIngress", "ec2:DeleteSecurityGroup", "ec2:DeleteKeyPair"],
      "Resource": "*",
      "Condition": { "StringEquals": { "aws:ResourceTag/project": "sbgame-tts" } } }
  ]
}
```

Nothing in it can touch IAM, S3, or any instance not tagged `project=sbgame-tts`, and it cannot launch anything but the two GPU types.

## 4.3 Instance

| **Item** | **Setting** | **Why** |
| --- | --- | --- |
| Type | g6.xlarge (NVIDIA L4, 24GB); g5.xlarge (A10G, 24GB) if g6 capacity is short | Qwen3-TTS recommends bfloat16 and FlashAttention 2, which needs Ampere or newer. The g4dn's T4 is older. |
| Image | Current AWS Deep Learning AMI, Ubuntu, with PyTorch | Drivers and CUDA preinstalled. Look the image up (`describe-images` by name, or the DLAMI SSM parameter) and print what was chosen. Do not hard-code an AMI id from memory. |
| Purchase | On-demand | The job is an hour. Spot interruption would cost more attention than it saves money. |
| Root volume | The AMI default, gp3, delete on termination | Model weights are a few GB. |
| Tags | `project=sbgame-tts`, `Name=sbgame-tts-<session>` on the instance and its volume | The policy depends on them, and so does teardown. |
| Key pair | `sbgame-tts`, created once, private key at `~/.ssh/sbgame-tts.pem`, mode 0600 | Reused between sessions. |
| Security group | `sbgame-tts`: inbound 22/tcp from Mark's current public IP /32 only, nothing else | Update the rule each session; the address may have changed. |

## 4.4 Never Leave It Running

Three layers, all required:

1. **Launch with** `--instance-initiated-shutdown-behavior terminate`, and user data that runs `shutdown -h +120` at boot. If everything else fails, the instance terminates itself two hours after it starts.
2. **Every session script tears down in a trap** — on success, on error and on Ctrl-C. Teardown terminates every running instance tagged `project=sbgame-tts`, not just the one this run thinks it started.
3. **`tts/aws/teardown`** runs the same teardown by hand, and **`tts/aws/status`** lists anything tagged `project=sbgame-tts` that is running, with its launch time. Run status at the end of every session and print the result.

Print the instance id, type and launch time at start, and the elapsed time at teardown, so Mark can see what he paid for.

## 4.5 On the Instance

- Install Qwen3-TTS following the repository's README as it stands on the day (github.com/QwenLM/Qwen3-TTS). Record the exact package versions that worked in `tts/remote/requirements.lock` so the second session installs the same.
- Models: `Qwen3-TTS-12Hz-1.7B-VoiceDesign` for session 1, `Qwen3-TTS-12Hz-1.7B-Base` for session 2 (voice cloning). Apache 2.0.
- The model's output sample rate is not stated in the README. Read it from the output and record it; the local step (§7) resamples whatever arrives.
- Copy files with `scp` or `rsync` over the same key. No S3 bucket.

# 5. Session 1 — Design the Voices

`tts/aws/design` — launches, designs, copies back, terminates.

## 5.1 The Prompt

For each cast member, build a voice description from their entry:

```text
A {sex} voice. Accent: {accent}. {description}.
Natural, conversational telephone speech, 1950s.
```

Keep the template in one place so Mark can edit it. If a cast entry has an optional `voice:` field, use it verbatim instead of the template. None does yet; it is the escape hatch for a character the template cannot describe.

Describe voices by their qualities only. A prompt never names a real person or asks for an imitation of one.

## 5.2 The Sample Text

Each candidate speaks the character's first scripted line, so Mark judges the voice on something it will actually say. If that line is under about five seconds, append the character's next line. Record the exact sample text next to each candidate; session 2 needs it as the reference transcript.

## 5.3 Output

- Three candidates per cast member, different seeds: `tts/voices/candidates/<person>.<k>.wav` for k = 1–3, plus `<person>.<k>.json` holding the prompt, sample text, seed and model id. 17 cast members is 51 clips.
- `--only <person>[,<person>…]` redesigns just those, after Mark has edited their `accent` or `description`.
- After copying back, run the local processing (§7) on each candidate into `tts/voices/preview/`, so Mark hears the voice through the telephone band as the audience will, not at full bandwidth.

## 5.4 Mark Chooses

Mark records the choice in `tts/voices.yml`:

```yaml
thornhill: 2
albright: 1
pike: 3
```

`tts/choose` copies each chosen candidate, at its raw full-bandwidth rate, to `tts/voices/<person>.wav` with its `.json`, and refuses if any cast member in `script.yml` has no choice.

# 6. Session 2 — Generate the Lines

`tts/aws/generate` — launches, uploads `script.yml`, `tts/voices/`, and the pronunciation table, generates, copies back, terminates.

## 6.1 Generation

For each utterance from the loader (§3.1): clone the speaker's reference voice, `tts/voices/<person>.wav` with its sample text as the reference transcript, and speak the utterance's text after pronunciation substitution (§6.2). Write the raw output to `tts/raw/<scene-id>.<utterance-id>.wav`.

## 6.2 Pronunciation — `tts/pronounce.yml`

A table of whole-word substitutions applied only to the text sent to the model. The script's text is never changed. Starting entries — expected to grow after Mark listens:

```yaml
"463": four sixty-three
"214": two fourteen
"308": three oh eight
"715": seven fifteen
"284-1187": two eight four, one one eight seven
"Canlis": CAN-liss
"Lindqvist": LIND-kwist
"Shilshole": SHIL-shole
```

## 6.3 Only Regenerate What Changed

`tts/manifest.json` records, per utterance: a hash of the substituted text, the hash of the reference voice file, the model id and the seed. A line is generated only if its entry is missing or any of those changed. So editing one line, adding a scene, or re-choosing one character's voice regenerates only the lines affected.

`--only <scene-id>[.<utterance-id>],…` forces those, with a new seed, for lines Mark wants another take of.

# 7. Local Processing — `tts/process.py`

Runs on the GEEKOM (or any machine), no GPU. Raw files in, delivered files out. Kept separate from generation because it will be tuned and rerun, and none of that should need a GPU.

For each raw file, in order:

1. **Mono**, if the model wrote anything else.
2. **Trim** leading and trailing silence, keeping 150ms at each end.
3. **Resample to 16kHz**, high-quality (soxr).
4. **Band-limit to 300–3400Hz.** Second-order high-pass at 300Hz. Low-pass as an elliptic or Chebyshev Type II, passband edge 3400Hz, stopband edge 4500Hz, at least 70dB down, as cascaded second-order sections. The steep low-pass is what clears the region between 5.5kHz and the 8kHz Nyquist limit at 16kHz.
5. **Level.** Normalise so every line sits at the same speech level: default −20dBFS RMS over the voiced portion, with a peak ceiling of −3dBFS. Both are options. The level on the line is finally set by ear during commissioning (audio.md §15); what matters here is that the lines match each other.
6. **Resample to 48kHz** and write 24-bit PCM mono to `wav/<scene-id>.<utterance-id>.wav`. The output directory is an option, default `wav/`.
7. **Check** the written file: 48000Hz, mono, name per §2, and energy above 5.5kHz below −60dBFS, measured the way audio.md §7.2 describes. Delete the file and report it if any check fails.

No other effects. The period character comes from the real handset and the real switchboard, not from processing.

Afterwards, report:

- every utterance with no delivered file;
- every file in `wav/` that no utterance refers to;
- the total count, which should equal the loader's.

# 8. Files

```text
tts/
  script.py              loader and validation (§3.1)
  process.py             local band-limiting and delivery (§7)
  choose                 copies chosen voices (§5.4)
  pronounce.yml          pronunciation table (§6.2)
  voices.yml             Mark's choices (§5.4)
  manifest.json          what was generated from what (§6.3)
  aws/
    design               session 1 (§5)
    generate             session 2 (§6)
    teardown             terminate everything tagged project=sbgame-tts (§4.4)
    status               list anything tagged project=sbgame-tts (§4.4)
  remote/
    setup.sh             instance setup (§4.5)
    design_voices.py     runs on the instance
    generate_lines.py    runs on the instance
    requirements.lock
  voices/
    candidates/          session 1 output — not committed
    preview/             band-limited candidates — not committed
    <person>.wav/.json   chosen reference voices — commit these
  raw/                   session 2 output — not committed
wav/                     delivered files
```

The chosen reference voices are the one expensive thing to recreate, since they took Mark's ears. Commit them. Whether `wav/` is committed is Mark's call: 71 files at 48kHz 24-bit is on the order of 50MB.

# 9. Done When

- `python -m tts.script` passes on the current `script.yml`.
- `tts/aws/status` shows nothing running.
- `wav/` holds exactly one file per utterance, every one passes §7's checks, and nothing else is in it.
- Mark has listened to all of them through the telephone band and any lines he flagged have been regenerated.

# 10. Open Items

- **Speed on the GEEKOM's CPU.** Unmeasured. Worth one timing run of a single line on the CPU before the first AWS session: if a line takes under a minute, the whole script is a lunch break and the AWS path becomes optional. Mark wants to try the AWS path regardless.
- **Model output sample rate.** Record it at the first run (§4.5).
- **Takes.** One take per line to start. If Mark ends up regenerating many lines, generate two per line and let him choose, the same way as the voices.
