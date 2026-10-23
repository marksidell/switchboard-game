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
  bool     lifted;          // station 24 only: the phone is off-hook (7.4)

  int8_t   ring_pub;        // last published: -1 never, 0 off, 1 on
  int8_t   hook_pub;
  int8_t   lifted_pub;

  // Dialling (control.md 7.3): the digits, the one being sent, and where in it.
  char     dial[DIAL_MAX_DIGITS + 1];
  uint8_t  dial_len;
  uint8_t  dial_pos;        // digits finished
  uint8_t  pulses_left;     // in the digit being sent
  uint8_t  dial_phase;      // DIAL_IDLE, DIAL_OPEN, DIAL_CLOSED or DIAL_GAP
  uint32_t dial_until;
};

enum : uint8_t { DIAL_IDLE = 0, DIAL_OPEN, DIAL_CLOSED, DIAL_GAP };

static StationState st[N_STATION_ROWS];  // by row: stations 1-22, then 24

void stationInit() {
  for (uint8_t i = 0; i < N_STATION_ROWS; ++i) {
    st[i] = StationState{};
    st[i].ring_pub   = -1;
    st[i].hook_pub   = -1;
    st[i].lifted_pub = -1;
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

/* The digits still to finish, the echo on `dial`. */
static void publishDial(const CircuitMap& c, const StationState& s) {
  netPublishState(c, "dial", s.dial_phase == DIAL_IDLE ? "" : s.dial + s.dial_pos);
}

static void stopDial(const CircuitMap& c, StationState& s, bool publish) {
  if (s.dial_phase == DIAL_IDLE) return;
  s.dial_phase = DIAL_IDLE;
  if (publish) publishDial(c, s);
}

/* Begin the next digit: its first break. */
static void startDigit(const CircuitMap& c, StationState& s, uint32_t now_ms) {
  const char d   = s.dial[s.dial_pos];
  s.pulses_left  = d == '0' ? 10 : (uint8_t)(d - '0');
  s.dial_phase   = DIAL_OPEN;
  s.dial_until   = now_ms + DIAL_BREAK_MS;
  circuitSetRelay(c, false);                // loop open: a break
}

/* One step of the dial when its interval is up. Each interval runs from now,
 * not from the last deadline, so a late poll stretches it rather than making
 * the next one short: a break or make is never shorter than its figure. */
static void dialStep(const CircuitMap& c, StationState& s, uint32_t now_ms) {
  if (s.dial_phase == DIAL_IDLE || (int32_t)(now_ms - s.dial_until) < 0) return;
  switch (s.dial_phase) {
    case DIAL_OPEN:                         // end of a break: close the loop
      circuitSetRelay(c, true);
      if (--s.pulses_left > 0) {
        s.dial_phase = DIAL_CLOSED;
        s.dial_until = now_ms + DIAL_MAKE_MS;
      } else if (++s.dial_pos < s.dial_len) {
        s.dial_phase = DIAL_GAP;            // the digit is done; the dial returns
        s.dial_until = now_ms + DIAL_INTERDIGIT_MS;
        publishDial(c, s);
      } else {
        s.dial_phase = DIAL_IDLE;           // the last digit is done
        publishDial(c, s);
      }
      break;
    case DIAL_CLOSED:                       // end of a make: the next break
      circuitSetRelay(c, false);
      s.dial_phase = DIAL_OPEN;
      s.dial_until = now_ms + DIAL_BREAK_MS;
      break;
    case DIAL_GAP:
      startDigit(c, s, now_ms);
      break;
  }
}

void stationPoll(uint32_t now_ms) {
  for (uint8_t i = 0; i < N_STATION_ROWS; ++i) {
    const CircuitMap& c = circuits[i];
    StationState&     s = st[i];

    if (!circuitLive(c)) continue;

    dialStep(c, s, now_ms);

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
        if (elapsedMs(now_ms, oldest) <= RING_DECLARE_WINDOW_MS) s.ring = true;
      }
    }

    /* Ring on this switchboard is applied by the operator holding a key, so the
     * train is continuous while ring is present and does not follow a cadence
     * (control.md 7.1). Quiet for 100ms therefore means released, not a gap. */
    if (s.ring && elapsedMs(now_ms, s.last_trans_ms) >= RING_RELEASE_QUIET_MS) {
      s.ring   = false;
      s.filled = 0;
    }

    publishIfChanged(c, "ring", s.ring, s.ring_pub);

    /* Station 24's hook detector reads 1 while the phone is on-hook (7.4). Its
     * level counts once it has held for 100ms, and not while ring is on: a
     * ringing line pulses the input. */
    if (c.number == PHONE_STATION) {
      if (!s.ring && elapsedMs(now_ms, s.last_trans_ms) >= PHONE_HOOK_STABLE_MS)
        s.lifted = !raw;
      publishIfChanged(c, "lifted", s.lifted, s.lifted_pub);
    }
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
  StationState& s = st[stationRow(n)];
  stopDial(*c, s, true);                   // a hook command ends any dialling (7.3)
  s.hook = on;
  circuitSetRelay(*c, on);                 // 1 = off-hook, loop closed through R3
  publishIfChanged(*c, "hook", s.hook, s.hook_pub);
}

void stationDial(uint8_t n, const char* digits) {
  const CircuitMap* c = stationCircuit(n);
  if (!c) { Serial.printf("dial/set: station %u out of range\n", (unsigned)n); return; }
  if (!circuitLive(*c)) {
    Serial.printf("dial/set: station %u dropped - expander 0x%02X absent\n",
                  (unsigned)n, expanders[c->exp].addr);
    return;
  }
  if (n == PHONE_STATION) {               // 7.4: the relay does not carry the loop
    Serial.printf("dial/set: station %u is the telephone - dropped\n", (unsigned)n);
    return;
  }
  StationState& s = st[stationRow(n)];
  const size_t len = strlen(digits);
  if (len == 0) {                          // stop
    stopDial(*c, s, true);
    if (s.hook) circuitSetRelay(*c, true); // and leave the loop closed
    return;
  }
  if (len > DIAL_MAX_DIGITS || strspn(digits, "0123456789") != len) {
    Serial.printf("dial/set: station %u payload \"%s\" is not 1-%u digits - dropped\n",
                  (unsigned)n, digits, (unsigned)DIAL_MAX_DIGITS);
    return;
  }
  if (!s.hook) {
    Serial.printf("dial/set: station %u is on-hook - no loop to dial on, dropped\n",
                  (unsigned)n);
    return;
  }
  memcpy(s.dial, digits, len + 1);
  s.dial_len = (uint8_t)len;
  s.dial_pos = 0;
  startDigit(*c, s, millis());
  publishDial(*c, s);
}

void stationReleaseAll() {
  for (uint8_t i = 0; i < N_STATION_ROWS; ++i) {
    st[i].hook = false;
    st[i].dial_phase = DIAL_IDLE;          // 7.3: a release ends dialling
    circuitSetRelay(circuits[i], false);
  }
}

void stationPublishOne(uint8_t i) {
  if (i >= N_STATION_ROWS) return;
  const CircuitMap& c = circuits[i];
  if (!circuitLive(c)) return;              // state the firmware cannot know
  StationState& s = st[i];
  s.ring_pub = s.ring ? 1 : 0;
  s.hook_pub = s.hook ? 1 : 0;
  netPublishState(c, "ring", s.ring ? "on" : "off");
  netPublishState(c, "hook", s.hook ? "on" : "off");
  if (c.number == PHONE_STATION) {
    s.lifted_pub = s.lifted ? 1 : 0;
    netPublishState(c, "lifted", s.lifted ? "on" : "off");
  } else {
    publishDial(c, s);
  }
}
