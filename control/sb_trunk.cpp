/* =============================================================================
 * sb_trunk.cpp
 * ========================================================================== */

#include "sb_trunk.h"
#include "sb_net.h"

/* A ring pattern is declared on two consecutive break-to-break gaps of 60ms or
 * less, not one. control.md 8.1 specifies the 60ms threshold and the two signals
 * it separates - 50ms for 20Hz ring against 67-125ms for an 8-15 pps dial - but
 * a single interval measured at 5ms granularity sits only one sample clear of a
 * fast dial. Two consecutive gaps costs 50ms of latency on a fault report and
 * cannot be produced by any dial in the 8.2 table. */
static constexpr uint8_t  RING_SHORT_GAPS_TO_DECLARE = 2;

/* No break for three ring periods means the pattern has stopped. */
static constexpr uint32_t RING_PATTERN_TIMEOUT_MS = 150;

enum class Phase : uint8_t { Idle, Ringing, Seized, RingOnTrunk };

static const char* const FAULT_NONE = "";
static const char* const FAULT_RING = "ring_on_trunk";
static const char* const FAULT_DIAL = "bad_dial";

struct TrunkState {
  Phase    phase;

  bool     raw_last;        // last SEIZE sample, 1 = loop current flowing
  uint32_t level_since;     // when the present level began

  uint8_t  pulses;          // pulses counted in the digit under way
  bool     in_digit;        // at least one pulse since the last digit boundary
  bool     digit_spoiled;   // a break outside the window landed inside the digit

  uint32_t last_break_ms;   // for the break-to-break interval test
  bool     have_break;
  uint8_t  short_gaps;

  bool     ring_requested;  // the game asked; may be waiting on the cap
  uint32_t ring_started_ms; // entry to Ringing, for the 30s hard timeout
  bool     cadence_on;
  uint32_t cadence_since;

  const char* fault;

  /* What `seize` reports: the loop as last classified. Set on entering SEIZED,
   * cleared on entering IDLE, and deliberately untouched on entering
   * RING_ON_TRUNK, so it is not simply phase == Seized (control.md 8.3, Rev 7). */
  bool        seize_on;

  int8_t      seize_pub;    // -1 never published, 0 off, 1 on
  int8_t      ring_pub;
  const char* fault_pub;
};

static TrunkState tr[N_TRUNKS];

/* ---- helpers ------------------------------------------------------------ */

static inline const CircuitMap& row(uint8_t i) { return circuits[N_STATIONS + i]; }

static void publishBoolIfChanged(const CircuitMap& c, const char* leaf,
                                 bool value, int8_t& cache) {
  const int8_t now = value ? 1 : 0;
  if (cache == now) return;
  cache = now;
  netPublishState(c, leaf, value ? "on" : "off");
}

/* mqtt.md 7: an empty payload on a retained topic clears it, so "no fault" and
 * "fault cleared" are the same message. Compared by pointer because every value
 * is one of the three literals above. */
static void setFault(uint8_t i, const char* f) {
  TrunkState& s = tr[i];
  if (s.fault == f) return;
  s.fault = f;
  if (s.fault_pub != f) {
    s.fault_pub = f;
    netPublishState(row(i), "fault", f);
  }
}

static uint8_t ringingCount() {
  uint8_t n = 0;
  for (uint8_t i = 0; i < N_TRUNKS; ++i) if (tr[i].phase == Phase::Ringing) n++;
  return n;
}

/* Energise or release this trunk's ring relay and echo the actual state, so a
 * monitoring UI sees the cadence (control.md 8.4). */
static void driveRing(uint8_t i, bool on) {
  TrunkState& s = tr[i];
  s.cadence_on = on;
  circuitSetRelay(row(i), on);
  publishBoolIfChanged(row(i), "ring", on, s.ring_pub);
}

static void enterIdle(uint8_t i, uint32_t now) {
  TrunkState& s = tr[i];
  driveRing(i, false);
  s.phase         = Phase::Idle;
  s.pulses        = 0;
  s.in_digit      = false;
  s.digit_spoiled = false;
  s.cadence_since = now;
  s.seize_on      = false;
  publishBoolIfChanged(row(i), "seize", false, s.seize_pub);
}

static void enterSeized(uint8_t i, uint32_t now) {
  TrunkState& s = tr[i];
  /* A seizure cancels any ring on this trunk: the switchboard has taken the
   * line outward and the incoming call is moot (control.md 8.3). */
  driveRing(i, false);
  s.ring_requested = false;
  s.phase          = Phase::Seized;
  s.pulses         = 0;
  s.in_digit       = false;
  s.digit_spoiled  = false;
  s.cadence_since  = now;
  s.seize_on       = true;
  setFault(i, FAULT_NONE);
  publishBoolIfChanged(row(i), "seize", true, s.seize_pub);
}

static void enterRinging(uint8_t i, uint32_t now) {
  TrunkState& s = tr[i];
  s.phase           = Phase::Ringing;
  s.ring_started_ms = now;      // the 30s guard runs from the first ring, not
  s.cadence_since   = now;      // from the command, so a queued trunk still
  driveRing(i, true);           // gets its full cadence
}

/* ---- the digit counter (control.md 8.2) ----------------------------------- */

static void completeDigit(uint8_t i) {
  TrunkState& s = tr[i];
  if (!s.in_digit) return;

  if (s.digit_spoiled) {
    setFault(i, FAULT_DIAL);
  } else if (s.pulses >= 1 && s.pulses <= MAX_DIAL_PULSES) {
    const uint8_t digit = (s.pulses == MAX_DIAL_PULSES) ? 0 : s.pulses;  // ten pulses is "0"
    char payload[2] = { (char)('0' + digit), '\0' };
    netPublishEvent(row(i), "digit", payload);
    setFault(i, FAULT_NONE);           // a valid digit clears a previous bad_dial
  } else {
    setFault(i, FAULT_DIAL);           // eleven or more pulses: no digit
  }

  s.pulses        = 0;
  s.in_digit      = false;
  s.digit_spoiled = false;
}

/* A release interval has just ended. Classify it by length: a dial pulse break,
 * or something that is neither a pulse nor a release. A release of 250ms or more
 * has already been handled by the dwell test in trunkPoll(). */
static void classifyBreak(uint8_t i, uint32_t len) {
  TrunkState& s = tr[i];
  if (s.phase != Phase::Seized) return;   // dialling is only meaningful in SEIZED

  if (len >= PULSE_BREAK_MIN_MS && len < PULSE_BREAK_MAX_MS) {
    if (s.pulses < 255) s.pulses++;
    s.in_digit = true;
    return;
  }

  /* Shorter than 25ms, or between 100ms and 250ms: neither a pulse nor a
   * release. Log it, and if it landed inside a digit that digit is spoiled. */
  Serial.printf("trunk %u: break of %lums is neither pulse nor release\n",
                (unsigned)row(i).number, (unsigned long)len);
  if (s.in_digit) s.digit_spoiled = true;
}

/* ---- poll --------------------------------------------------------------- */

void trunkInit() {
  for (uint8_t i = 0; i < N_TRUNKS; ++i) {
    tr[i] = TrunkState{};
    tr[i].phase     = Phase::Idle;
    tr[i].fault     = FAULT_NONE;
    tr[i].fault_pub = nullptr;      // force the first publish
    tr[i].seize_pub = -1;
    tr[i].ring_pub  = -1;
  }
}

void trunkPoll(uint32_t now) {
  for (uint8_t i = 0; i < N_TRUNKS; ++i) {
    const CircuitMap& c = row(i);
    TrunkState&       s = tr[i];
    if (!circuitLive(c)) continue;

    /* ---- cadence and the hard timeout, before the input is looked at ----
     * During the ring-on phase pole 2 has lifted the return off R_LOOP and
     * SEIZE reads nothing, so the input is only meaningful in the off phase. */
    if (s.phase == Phase::Ringing) {
      if (now - s.ring_started_ms >= RING_HARD_TIMEOUT_MS) {
        Serial.printf("trunk %u: 30s ring timeout\n", (unsigned)c.number);
        enterIdle(i, now);
        s.ring_requested = false;
        continue;
      }
      const uint32_t phase_ms = s.cadence_on ? CADENCE_ON_MS : CADENCE_OFF_MS;
      if (now - s.cadence_since >= phase_ms) {
        s.cadence_since = now;
        driveRing(i, !s.cadence_on);
        if (!s.cadence_on) {
          /* Entering the off phase. SEIZE was unreadable for the whole ring-on
           * interval, so the level recorded before it began says nothing about
           * now: rebaseline instead of letting a seconds-old "transition"
           * appear the moment the input becomes meaningful again. Dwell then
           * runs from the start of the off phase, which also gives the DC feed
           * time to re-establish before the 100ms seizure test can fire. */
          s.raw_last    = circuitInput(c);
          s.level_since = now;
        }
      }
    }

    const bool raw    = circuitInput(c);
    const bool blind  = (s.phase == Phase::Ringing && s.cadence_on);

    if (!blind && raw != s.raw_last) {
      const uint32_t len = now - s.level_since;
      s.raw_last    = raw;
      s.level_since = now;

      if (!raw) {
        /* Asserted -> released: this edge is a break. The break-to-break
         * interval is what separates ring from a dial (control.md 8.1). */
        if (s.have_break && (now - s.last_break_ms) <= RING_BREAK_GAP_MS) {
          if (s.short_gaps < 255) s.short_gaps++;
        } else {
          s.short_gaps = 0;
        }
        s.last_break_ms = now;
        s.have_break    = true;

        if (s.short_gaps >= RING_SHORT_GAPS_TO_DECLARE &&
            s.phase != Phase::Ringing) {
          if (s.phase != Phase::RingOnTrunk) {
            Serial.printf("trunk %u: ring applied from the switchboard\n",
                          (unsigned)c.number);
            /* `seize` is left as it was (control.md 8.3, Rev 7). Entered from
             * SEIZED it stays "on": publishing "off" here would look to the
             * game like a release and tear the call down for an operator's
             * slip. `fault` = "ring_on_trunk" is the report. When the pattern
             * stops with the loop still closed, enterSeized() finds seize
             * already "on" and publishes nothing. */
            s.phase         = Phase::RingOnTrunk;
            s.pulses        = 0;
            s.in_digit      = false;
            s.digit_spoiled = false;
          }
          setFault(i, FAULT_RING);
        }
      } else {
        /* Released -> asserted: the interval that just ended was a release. */
        classifyBreak(i, len);
      }
    }

    const uint32_t dwell = now - s.level_since;

    switch (s.phase) {
      case Phase::Idle:
      case Phase::RingOnTrunk:
        /* An accidental ring never holds the line asserted for longer than
         * about 27ms against this 100ms threshold, so a long assertion is a
         * genuine seizure whichever of the two states we are in. */
        if (raw && dwell >= SEIZE_DECLARE_MS) {
          setFault(i, FAULT_NONE);
          enterSeized(i, now);
        } else if (s.phase == Phase::RingOnTrunk && s.have_break &&
                   (now - s.last_break_ms) >= RING_PATTERN_TIMEOUT_MS) {
          s.short_gaps = 0;
          setFault(i, FAULT_NONE);
          enterIdle(i, now);
        }
        break;

      case Phase::Ringing:
        /* Answer detection, only in the off phase. Worst-case latency is one
         * ring-on interval, which is also what real trunk ring sounds like. */
        if (!s.cadence_on && raw && dwell >= SEIZE_DECLARE_MS) {
          enterSeized(i, now);
        }
        break;

      case Phase::Seized:
        if (!raw && dwell >= RELEASE_OPEN_MS) {
          /* A digit in progress is abandoned, not published (control.md 8.1). */
          s.pulses        = 0;
          s.in_digit      = false;
          s.digit_spoiled = false;
          setFault(i, FAULT_NONE);
          enterIdle(i, now);
        } else if (raw && s.in_digit && dwell >= DIGIT_END_MAKE_MS) {
          completeDigit(i);
        }
        break;
    }
  }

  /* ---- the concurrent-ring cap (control.md 8.5) -------------------------
   * Queued requests are started lowest trunk first, so the order is
   * deterministic and a low-numbered trunk cannot be starved by a busy one. */
  for (uint8_t i = 0; i < N_TRUNKS && ringingCount() < MAX_TRUNKS_RINGING; ++i) {
    if (tr[i].ring_requested && tr[i].phase == Phase::Idle && circuitLive(row(i))) {
      enterRinging(i, now);
    }
  }
}

/* ---- commands ----------------------------------------------------------- */

void trunkSetRing(uint8_t n, bool on) {
  const CircuitMap* c = trunkCircuit(n);
  if (!c) { Serial.printf("ring/set: trunk %u out of range\n", (unsigned)n); return; }
  if (!circuitLive(*c)) {
    Serial.printf("ring/set: trunk %u dropped - expander 0x%02X absent\n",
                  (unsigned)n, expanders[c->exp].addr);
    return;
  }

  const uint8_t i = (uint8_t)(n - 1);
  TrunkState&   s = tr[i];
  const uint32_t now = millis();

  if (!on) {
    s.ring_requested = false;
    if (s.phase == Phase::Ringing) enterIdle(i, now);
    return;
  }

  /* control.md 8.3, Rev 7: "on" is acted on in IDLE only. In RINGING it is a
   * no-op. In SEIZED and RING_ON_TRUNK it is dropped with a log line and not
   * held for later - a ring that started seconds after the command, once the
   * operator had finished with the trunk, is not what the game meant. Nothing
   * is published, so the `ring` echo stays "off", which is how the game
   * learns it was not acted on; it re-issues if it still wants the ring. */
  switch (s.phase) {
    case Phase::Ringing:
      return;
    case Phase::Seized:
    case Phase::RingOnTrunk:
      Serial.printf("ring/set: trunk %u is %s - dropped, not ringing it\n",
                    (unsigned)n,
                    s.phase == Phase::Seized ? "seized" : "being rung from the switchboard");
      return;
    case Phase::Idle:
      break;
  }

  /* IDLE: ring now, or queue behind the concurrent-ring cap (8.5). A queued
   * request was accepted here and is only waiting for the generator, which is
   * why it survives where a dropped one does not. */
  s.ring_requested = true;
  if (ringingCount() < MAX_TRUNKS_RINGING) {
    enterRinging(i, now);
  } else {
    Serial.printf("ring/set: trunk %u queued - %u already ringing\n",
                  (unsigned)n, (unsigned)ringingCount());
  }
}

void trunkInhibitRing() {
  for (uint8_t i = 0; i < N_TRUNKS; ++i) {
    if (circuitRelay(row(i))) driveRing(i, false);
  }
}

void trunkReleaseAll() {
  const uint32_t now = millis();
  for (uint8_t i = 0; i < N_TRUNKS; ++i) {
    tr[i].ring_requested = false;
    if (tr[i].phase == Phase::Ringing) enterIdle(i, now);
    else                               circuitSetRelay(row(i), false);
  }
}

uint8_t trunkRingingCount() { return ringingCount(); }

uint8_t trunkQueuedCount() {
  uint8_t n = 0;
  for (uint8_t i = 0; i < N_TRUNKS; ++i)
    if (tr[i].ring_requested && tr[i].phase != Phase::Ringing) n++;
  return n;
}

void trunkPublishOne(uint8_t i) {
  if (i >= N_TRUNKS) return;
  const CircuitMap& c = row(i);
  if (!circuitLive(c)) return;
  TrunkState& s = tr[i];
  const bool seized = s.seize_on;        // not phase == Seized: see seize_on
  s.seize_pub = seized ? 1 : 0;
  s.ring_pub  = s.cadence_on ? 1 : 0;
  s.fault_pub = s.fault;
  netPublishState(c, "seize", seized ? "on" : "off");
  netPublishState(c, "ring",  s.cadence_on ? "on" : "off");
  netPublishState(c, "fault", s.fault);
}
