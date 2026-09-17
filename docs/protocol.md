# IPC Protocol — audio ↔ engine

Status: **skeleton.** Fields marked TODO are unresolved. Nothing here is authoritative
until the TODOs are gone.

## Transport

Unix domain socket, `SOCK_STREAM`, path `TODO` (default `/run/switchboard/ipc.sock`).

Framing: 4-byte unsigned length prefix, little-endian, followed by that many bytes of
UTF-8 JSON. One JSON object per frame. No newline framing.

The audio process is the server; the engine connects. On engine disconnect the audio
process holds all circuits in their current state and continues running — it must not
drop out of the callback.

## Envelope

```json
{
  "v": 1,
  "type": "<message type>",
  "seq": 1234,
  "t_us": 1234567890,
  "body": { }
}
```

- `v` — protocol version. Bump on any incompatible change.
- `seq` — monotonic per direction.
- `t_us` — audio process monotonic clock, microseconds. Engine echoes it on replies.

## Audio → engine events

| type | body | meaning |
|---|---|---|
| `pilot` | `slot`, `present`, `level_db` | pilot tone appear/disappear for a slot |
| `seizure` | `slot`, `state` | circuit seized / released. Suppressed while ring active |
| `dial` | `slot`, `digit`, `method` | TODO: rotary pulse decode vs. other |
| `playback_done` | `slot`, `cue_id` | pre-rendered clip finished |
| `xrun` | `frames` | audio underrun, for diagnostics |

## Engine → audio commands

| type | body | meaning |
|---|---|---|
| `connect` | `slot_a`, `slot_b`, `mode` | cross-connect two circuits |
| `disconnect` | `slot_a`, `slot_b` | tear down |
| `play` | `slot`, `cue_id`, `gain_db` | play a pre-rendered clip into a circuit |
| `stop` | `slot`, `cue_id` | halt playback |
| `monitor` | `sources[]`, `gain_db` | set the bystander monitor mix |

Replies: `{"type": "ack", "seq": <echoed>}` or `{"type": "nak", "seq": <echoed>,
"reason": "..."}`. Commands are idempotent where possible.

## Shared-memory state page

Continuous state the engine polls; never carried over the socket.

Path: `TODO` (`/dev/shm/switchboard_state`). Size: TODO.

Layout: sequence-lock header, then a fixed array of 32 slot records. Writer is the audio
process only. Reader retries on odd sequence value.

```
struct SlotState {
    uint32_t flags;        // TODO: bit assignments
    float    pilot_db;
    float    rx_level_db;
    float    tx_level_db;
    uint32_t connected_to; // slot number, 0 = none
};  // TODO: confirm size and padding
```

TODO: define `flags` bits — at minimum seized, ringing, ring-masked, playback active,
fault.

## Open questions

- Rotary dial decode: audio-domain pulse detection, or does supervision come via
  MCP23017 → MQTT instead? Affects whether `dial` belongs here at all.
- Backpressure policy if the engine stops reading.
- Whether `connect` needs a gain/hybrid mode argument beyond `mode`.
