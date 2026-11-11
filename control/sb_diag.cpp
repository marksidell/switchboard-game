/* =============================================================================
 * sb_diag.cpp
 * ========================================================================== */

#include "sb_diag.h"
#include "sb_config.h"
#include "sb_table.h"
#include "sb_expander.h"
#include "sb_trunk.h"
#include "sb_net.h"
#include "sb_ring.h"
#include "sb_failsafe.h"
#include "sb_ota.h"
#include "secrets.h"

/* Where a long loop pass goes: the worst of each section since the banner last
 * printed, and each section's time since the last poll tick, so a long gap
 * between ticks can be put down to what ran in it. */
static const char* const T_NAMES[T_N] = { "net", "verify", "inputs", "station", "trunk",
                                          "flush", "beat", "failsafe", "republish", "ota",
                                          "enable", "i2c-pub", "serial" };
static uint32_t t_max_us[T_N];
static uint32_t t_cur_us[T_N];

void diagNoteTime(int k, uint32_t us) {
  t_cur_us[k] += us;
  if (us > t_max_us[k]) t_max_us[k] = us;
}

/* Gaps between poll ticks of LONG_GAP_MS or more, kept for the banner rather
 * than printed as they happen: a line on the serial port blocks for longer than
 * the gaps being looked for. */
static constexpr uint32_t LONG_GAP_MS = 20;
static constexpr uint32_t BANNER_MIN_MS = 2000;   // at most one banner per 2s
static constexpr uint8_t  LONG_GAPS   = 16;
struct LongGap {
  uint32_t at_ms;        // millis() at the tick that ended it
  uint16_t gap_ms;
  uint16_t passes;       // loop() passes between the two ticks
  uint8_t  top;          // the section that took longest in it
  uint32_t top_us;
  uint32_t untimed_us;   // the gap less every timed section: other tasks, delay()
};
static LongGap long_gaps[LONG_GAPS];
static uint8_t  long_gap_count   = 0;     // kept, at most LONG_GAPS
static uint32_t long_gap_dropped = 0;     // seen after the buffer filled
static uint16_t passes_since_tick = 0;

/* ---- Loop timing ---------------------------------------------------------
 * Anything that holds loop() stretches the gap between poll ticks, and every
 * threshold in control.md 7 and 8 is measured in those ticks. Two figures, both
 * maxima since the banner last printed them:
 *
 *   loop_max_us     the longest single pass through loop(), start to end
 *   poll_gap_max_ms the longest interval between consecutive poll ticks;
 *                   5 when nothing is holding the loop
 *
 * The second is the one that matters to the debounce: a ringing station's
 * 100ms quiet rule (7.1) fires on a gap of 100ms, and a dial break or make
 * interval (8.2) has the gap added to it. Printed and zeroed by printBanner(),
 * so pressing a key, waiting, and pressing it again measures the interval
 * between the two presses. */
static uint32_t loop_max_us      = 0;
static uint32_t poll_gap_max_ms  = 0;
static uint32_t timing_since_ms  = 0;

static void noteGap(uint32_t now, uint32_t gap_ms) {
  if (gap_ms >= LONG_GAP_MS) {
    uint32_t sum = 0;
    uint8_t  top = 0;
    for (uint8_t k = 0; k < T_N; ++k) {
      sum += t_cur_us[k];
      if (t_cur_us[k] > t_cur_us[top]) top = k;
    }
    if (long_gap_count < LONG_GAPS) {
      LongGap& g = long_gaps[long_gap_count++];
      g.at_ms      = now;
      g.gap_ms     = (uint16_t)(gap_ms > 65535 ? 65535 : gap_ms);
      g.passes     = passes_since_tick;
      g.top        = top;
      g.top_us     = t_cur_us[top];
      g.untimed_us = gap_ms * 1000 > sum ? gap_ms * 1000 - sum : 0;
    } else {
      long_gap_dropped++;
    }
  }
  for (uint8_t k = 0; k < T_N; ++k) t_cur_us[k] = 0;
  passes_since_tick = 0;
}

void diagPollGap(uint32_t now, uint32_t gap_ms) {
  if (gap_ms > poll_gap_max_ms) poll_gap_max_ms = gap_ms;
  noteGap(now, gap_ms);
}

void diagEndPass(uint32_t pass_start_us) {
  const uint32_t pass_us = micros() - pass_start_us;
  if (pass_us > loop_max_us) loop_max_us = pass_us;
  passes_since_tick++;
}

/* Configuration and live state, on demand: once from setup() and again for
 * Enter, so "what is this board actually running" has an answer at any moment
 * rather than only in the first half second after a reset, when nothing is
 * attached to read it. */
void printBanner() {
  Serial.println();
  Serial.println("551 switchboard controller");
  Serial.printf("  carrier      %lu Hz, %u bits\n",
                (unsigned long)CARRIER_FREQ_HZ, LEDC_RESOLUTION_BITS);
  Serial.printf("  step         %lu us, %lu steps, %.3f Hz output\n",
                (unsigned long)STEP_PERIOD_US, (unsigned long)SINE_STEPS,
                1000000.0 / (double)(STEP_PERIOD_US * SINE_STEPS));
  Serial.printf("  g_amplitude  %.4f, peak duty %lu / %lu\n",
                (double)G_AMPLITUDE, (unsigned long)ringPeakDuty(), (unsigned long)DUTY_MAX);
  Serial.printf("  start step   %lu of %lu, phase %.1f deg (positive peak)\n",
                (unsigned long)START_STEP, (unsigned long)SINE_STEPS,
                360.0 * ((double)START_STEP + 0.5) / (double)SINE_STEPS);
  Serial.println("  GPIO4 LOW to run (J1 pins 1-2)");
  Serial.printf ("  power cut on GPIO%d (J1 pin 4), %lums, now %s\n", PIN_POWER_CUT,
                 (unsigned long)POWER_CUT_MS, digitalRead(PIN_POWER_CUT) ? "cutting" : "idle");
  // ticks advancing at 5000/s is the only visibility into whether the
  // esp_timer is really dispatching: a stalled timer with the bridge armed
  // looks exactly like a working one until a scope goes on GPIO32. enbl is the
  // raw pin, before debounce, so a jumper can be checked against what
  // ringServiceEnable() decided.
  Serial.printf("  state        %s, enbl=%d, ticks=%lu\n",
                ringRunning() ? "RUN" : "IDLE",
                (digitalRead(PIN_ENBL) == LOW) ? 1 : 0,
                (unsigned long)ringTicks());

  Serial.print("  expanders   ");
  for (uint8_t i = 0; i < N_EXPANDERS; ++i) {
    if (!expanderConfigured(i)) continue;
    Serial.printf(" 0x%02X:%s", expanders[i].addr,
                  exp_state[i].present ? "ok" : "MISSING");
  }
  Serial.printf("   (%u station board(s) fitted)\n",
                (unsigned)STATION_BOARDS_FITTED);
  // Only when there is something to say: silence means the bus is whole.
  if (expanderBusFault())
    Serial.printf("  i2c recovery probing every %lu ms%s, %u attempts so far\n",
                  (unsigned long)I2C_RETRY_MS,
                  expanderAnyPresent() ? ""
                                       : " and /RESET on the slow knock (nothing answers)",
                  (unsigned)failsafeI2cRetries());
  Serial.printf("  firmware     control.md Rev %u, %s, built %s\n",
                FIRMWARE_SPEC_REV, FIRMWARE_COMMIT, FIRMWARE_BUILT);
  Serial.printf("  mqtt         %s, broker %s:%u\n",
                netConnected() ? "connected" : "down",
                MQTT_BROKER_HOST, (unsigned)MQTT_PORT);
#ifdef OTA_PASSWORD_SHA256
  Serial.printf("  ota          %s\n",
                otaListening() ? "listening, " MQTT_CLIENT_ID ".local:3232"
                               : "waiting for an address");
#else
  Serial.println("  ota          OFF - no OTA_PASSWORD_SHA256 in secrets.h");
#endif
  // The heartbeat is the one thing the MQTT side cannot tell you about itself:
  // a game program that has died leaves `online` and current-looking state.
  Serial.printf("  game beat    %s\n",
                netGameAlive(millis()) ? "alive" : "MISSING - relays held released");
  Serial.printf("  trunks       %u ringing, %u queued (cap %u)\n",
                (unsigned)trunkRingingCount(), (unsigned)trunkQueuedCount(),
                (unsigned)MAX_TRUNKS_RINGING);

  /* Maxima since the last banner, then zeroed, so two keypresses a minute
   * apart bracket at least one 30s republish. */
  const uint32_t now = millis();
  Serial.printf("  loop timing  longest pass %lu us, longest poll gap %lu ms "
                "(nominal %lu), over the last %lu s\n",
                (unsigned long)loop_max_us, (unsigned long)poll_gap_max_ms,
                (unsigned long)POLL_PERIOD_MS,
                (unsigned long)((now - timing_since_ms) / 1000));
  Serial.print("  worst (us)  ");
  for (int k = 0; k < T_N; ++k) {
    Serial.printf(" %s %lu", T_NAMES[k], (unsigned long)t_max_us[k]);
    t_max_us[k] = 0;
  }
  Serial.println();
  /* Every gap of LONG_GAP_MS or more since the last banner, with what ran in
   * it. The banner's own printing shows as the first, under "serial". */
  Serial.printf("  long gaps    %u of %lu ms or more", (unsigned)long_gap_count,
                (unsigned long)LONG_GAP_MS);
  if (long_gap_dropped) Serial.printf(", and %lu more not kept", (unsigned long)long_gap_dropped);
  Serial.println();
  for (uint8_t i = 0; i < long_gap_count; ++i) {
    const LongGap& g = long_gaps[i];
    Serial.printf("    %lus before: %u ms over %u pass(es), %s %lu us, untimed %lu us\n",
                  (unsigned long)((now - g.at_ms) / 1000), (unsigned)g.gap_ms,
                  (unsigned)g.passes, T_NAMES[g.top], (unsigned long)g.top_us,
                  (unsigned long)g.untimed_us);
  }
  long_gap_count   = 0;
  long_gap_dropped = 0;
  loop_max_us     = 0;
  poll_gap_max_ms = 0;
  timing_since_ms = now;
}

/* The banner for Enter only, at most every BANNER_MIN_MS: anything else on the
 * line is discarded, so a floating or noisy receive line cannot hold the loop. */
void diagServiceConsole(uint32_t now) {
  static uint32_t last_banner_ms = 0;
  bool enter = false;
  while (Serial.available()) {
    const int ch = Serial.read();
    if (ch == '\r' || ch == '\n') enter = true;
  }
  if (enter && (last_banner_ms == 0 || now - last_banner_ms >= BANNER_MIN_MS)) {
    last_banner_ms = now;
    TIMED(T_SERIAL, printBanner());
  }
}
