/* =============================================================================
 * sb_station.cpp
 * ========================================================================== */

#include "sb_station.h"
#include "sb_net.h"

/* Ring is declared on four or more transitions inside a 150ms window, so the
 * four most recent transition times are all that need keeping: if the oldest of
 * the last four is within the window, four transitions have happened inside it.
 * A ring buffer of four is the whole of the ring debounce state. */
struct StationState {
  bool     raw_last;
  uint32_t trans[RING_TRANSITIONS_TO_DECLARE];
  uint8_t  head;            // next slot to write
  uint8_t  filled;          // saturates at RING_TRANSITIONS_TO_DECLARE
  uint32_t last_trans_ms;
  bool     ring;            // debounced
  bool     hook;            // commanded relay state

  int8_t   ring_pub;        // last published: -1 never, 0 off, 1 on
  int8_t   hook_pub;
};

static StationState st[N_STATIONS];

void stationInit() {
  for (uint8_t i = 0; i < N_STATIONS; ++i) {
    st[i] = StationState{};
    st[i].ring_pub = -1;
    st[i].hook_pub = -1;
  }
}

/* Publish `ring` or `hook` if the value differs from what was last sent.
 * mqtt.md 2: the ESP32 publishes debounced state changes only, never the raw
 * pulse train - a ringing station is a 40Hz train at the detector and one
 * message on the bus. */
static void publishIfChanged(const CircuitMap& c, const char* leaf,
                             bool value, int8_t& cache) {
  const int8_t now = value ? 1 : 0;
  if (cache == now) return;
  cache = now;
  netPublishState(c, leaf, value ? "on" : "off");
}

void stationPoll(uint32_t now_ms) {
  for (uint8_t i = 0; i < N_STATIONS; ++i) {
    const CircuitMap& c = circuits[i];
    StationState&     s = st[i];

    if (!circuitLive(c)) continue;

    const bool raw = circuitInput(c);       // IPOL has made 1 = ring present

    if (raw != s.raw_last) {
      s.raw_last      = raw;
      s.last_trans_ms = now_ms;
      s.trans[s.head] = now_ms;
      s.head          = (uint8_t)((s.head + 1) % RING_TRANSITIONS_TO_DECLARE);
      if (s.filled < RING_TRANSITIONS_TO_DECLARE) s.filled++;

      if (!s.ring && s.filled >= RING_TRANSITIONS_TO_DECLARE) {
        /* head now points at the oldest of the four retained transitions. */
        const uint32_t oldest = s.trans[s.head];
        if (now_ms - oldest <= RING_DECLARE_WINDOW_MS) s.ring = true;
      }
    }

    /* Ring on this switchboard is applied by the operator holding a key, so the
     * train is continuous while ring is present and does not follow a cadence
     * (esp32.md 7.1). Quiet for 100ms therefore means released, not a gap. */
    if (s.ring && (now_ms - s.last_trans_ms) >= RING_RELEASE_QUIET_MS) {
      s.ring   = false;
      s.filled = 0;
    }

    publishIfChanged(c, "ring", s.ring, s.ring_pub);
  }
}

void stationSetHook(uint8_t n, bool on) {
  const CircuitMap* c = stationCircuit(n);
  if (!c) { Serial.printf("hook/set: station %u out of range\n", (unsigned)n); return; }
  if (!circuitLive(*c)) {
    Serial.printf("hook/set: station %u dropped - expander 0x%02X absent\n",
                  (unsigned)n, expanders[c->exp].addr);
    return;
  }
  StationState& s = st[n - 1];
  s.hook = on;
  circuitSetRelay(*c, on);                 // 1 = off-hook, loop closed through R3
  publishIfChanged(*c, "hook", s.hook, s.hook_pub);
}

void stationReleaseAll() {
  for (uint8_t i = 0; i < N_STATIONS; ++i) {
    st[i].hook = false;
    circuitSetRelay(circuits[i], false);
  }
}

void stationPublishOne(uint8_t i) {
  if (i >= N_STATIONS) return;
  const CircuitMap& c = circuits[i];
  if (!circuitLive(c)) return;              // state the firmware cannot know
  StationState& s = st[i];
  s.ring_pub = s.ring ? 1 : 0;
  s.hook_pub = s.hook ? 1 : 0;
  netPublishState(c, "ring", s.ring ? "on" : "off");
  netPublishState(c, "hook", s.hook ? "on" : "off");
}
