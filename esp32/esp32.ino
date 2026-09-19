/* =============================================================================
 * 551 Switchboard Simulator - Ring Generator PWM
 *
 * Target : Olimex ESP32-POE-ISO   (Arduino IDE board: "OLIMEX ESP32-PoE-ISO")
 * Implements: ring_generator.docx Rev 48, sections 5, 6, 8.3, 9.4, 12, 12.5,
 * 12.6. T1 is specified as an Antek AS-0522 toroid as of Rev 48; the OSD Black
 * 70V is retired. The Hammond 1182G22/1182J22 named in earlier notes were
 * candidates only and were never fitted.
 *
 * Also implements esp32.md Rev 2: the I2C master, expander polling, station
 * and trunk logic, dial pulse detection and the MQTT client. Those live in the
 * sb_*.{h,cpp} files beside this one; this file keeps the waveform, setup() and
 * loop(). The channel table in sb_table.cpp is the spine - 24 stations and 8
 * trunks are rows, not code.
 *
 * BENCH STATE, 2026-09-17, and expected to be short-lived. Three things on the
 * board differ from the documents, and each of them gates testing:
 *
 *   No transformer is fitted at all. The Antek is on order. Nothing that
 *   depends on T1 can be measured yet - in particular the esp32.md 5.3
 *   start-phase capture, which is only meaningful with the toroid in circuit.
 *
 *   The 74HCT02 is still fitted rather than the 74HCT04 of generator Rev 48
 *   section 5, so the duty tables below are complemented rather than in the
 *   direct form. See the note above buildDutyTables().
 *
 *   No station or trunk board exists, so no MCP23017 answers the scan. The
 *   arming gate of esp32.md 4.2 step 8 would therefore refuse every boot;
 *   BENCH_ALLOW_MISSING_EXPANDERS in sb_config.h bypasses it, loudly, until a
 *   board is fitted.
 *
 * Update or delete this block as the parts arrive; it describes a bench, not
 * a design.
 * Requires ESP32 Arduino core 3.x. The 2.x LEDC path was removed once the
 * hardware had only ever run on 3.x - see the note above pwmBegin().
 *
 * File is esp32.ino in a folder named esp32/ - the Arduino build requires the
 * sketch folder and the .ino to carry the same name. Named for the controller
 * rather than for the ring generator, because ring generation is one of the
 * three jobs esp32.md 1 gives this firmware and naming it after that one
 * misled. Was ring.ino, and ring_generator_pwm.ino before that.
 *
 * The board DOES restart by itself after an upload - no reset press needed.
 * Verified 2026-09-04: flashed with arduino-cli, which ends with "Hard
 * resetting via RTS pin", while the serial port was left closed throughout and
 * a scope watched the 20 Hz sync on GPIO15 (J9 pin 3). The sync appeared on
 * its own. A note here previously claimed the opposite; it was wrong.
 *
 * What misled it: the banner is printed inside setup(), and is gone before a
 * serial monitor reattaches - and reattaching resets the board anyway, because
 * opening the port toggles DTR/RTS. A console that shows nothing after an
 * upload therefore looks exactly like a board that never started. So the
 * banner is available on demand: send any character and printBanner() repeats
 * it, configuration and live state together, including the tick counter that
 * says whether the step timer is really dispatching.
 *
 * WHAT THIS SKETCH DOES
 *   Generates the 20.000 Hz sine on a 40 kHz carrier that drives the two
 *   IR2104 half-bridges through the 74HCT02, and sequences SD around it.
 *   The generator runs while GPIO4 is held LOW.
 *
 * WHAT IT DOES NOT DO
 *   No ETH.begin(), no I2C, no MCP23017 scan, no MQTT. Section 12.4 puts
 *   Ethernet and the expander scan ahead of arming the bridge; the gate for
 *   that is slavesPresent() below, stubbed to true. Ring cadence is not here
 *   either - the trunk board's ring relays do cadence, this board free-runs.
 *
 * POLARITY (section 5.1/5.2)
 *   IN1 = GPIO32,  IN2 = GPIO33,  SD = GPIO14.  All non-inverting.
 *
 *   Doc Rev 44 replaced the 74HCT02 with a 74HCT04 hex inverter and routed
 *   each signal through two gates. The pins are now ACTIVE HIGH and duty is
 *   written directly - no complement - and the park value is 0. LEDC's own
 *   power-on state is therefore the safe one: both pins low is IN1 = IN2 =
 *   low, Q3 and Q4 on, primary shorted to ground.
 *
 *   That is worth dwelling on, because the opposite arrangement was the most
 *   persistent trap in this design. Under the 74HCT02 the pins were active
 *   LOW, so 0 duty meant IN1 high with IN2 low - Q1 and Q4, the full rail
 *   across the 0.63 ohm primary as DC. Sections 6.1 and 6.2 specified 0 duty
 *   from Rev 5 to Rev 29 for exactly that reason. The polarity inversion
 *   removes the trap rather than defending against it.
 *
 *   R_PWMA_PD and R_PWMB_PD are PULL-DOWNS as of Rev 44, not pull-ups, and
 *   still not optional: GPIO32 and GPIO33 have no internal pull at reset, so
 *   without them both inverter inputs float through the bootloader window.
 *
 *   The 74HCT04 is not a shoot-through interlock and neither was the part it
 *   replaced. Shoot-through within a leg is prevented inside the IR2104,
 *   which derives HO and LO from one IN pin with 520ns typical deadtime
 *   (400 min, 650 max). The gate is 3.3V-to-5V level translation, needed
 *   because the ESP32's guaranteed VOH of 0.8 x VDD = 2.64V sits below the
 *   IR2104's 3.0V VIH minimum.
 * ============================================================================= */

#include <Arduino.h>
#include <math.h>
#include <Wire.h>
#include "esp_timer.h"

#include "sb_config.h"
#include "sb_table.h"
#include "sb_expander.h"
#include "sb_station.h"
#include "sb_trunk.h"
#include "sb_net.h"
#include "secrets.h"

/* ---- Section 12.2: waveform constants ------------------------------------ */

static constexpr uint32_t CARRIER_FREQ_HZ         = 40000;  // 25 us period
static constexpr uint32_t CARRIER_CYCLES_PER_STEP = 8;      // 200 us step
static constexpr uint32_t SINE_STEPS              = 250;    // 50 ms = 20.000 Hz
static constexpr uint8_t  LEDC_RESOLUTION_BITS    = 10;     // 1024 duty levels

static_assert(CARRIER_FREQ_HZ == 20UL * CARRIER_CYCLES_PER_STEP * SINE_STEPS,
              "Section 12.2 constraint violated: 20 = f_carrier / (cycles x steps)");

static constexpr uint32_t STEP_PERIOD_US =
    (1000000UL * CARRIER_CYCLES_PER_STEP) / CARRIER_FREQ_HZ;   // 200

// 2^bits is the LEDC "always high" duty. Pin HIGH = channel inactive.
static constexpr uint32_t DUTY_MAX = 1UL << LEDC_RESOLUTION_BITS;  // 1024

/* ---- Section 9.4: output amplitude trim ----------------------------------
 * 0.90 is a working value, not a placeholder, and must not be raised towards
 * 1.00 to make anything look cleaner. Sections 8.3 and 9.4: at 1.00 the low side
 * stops turning on at the sine peak, so C_BOOT gets no refill and VB-VS
 * collapses to about 2.6 V; at 0.90 it holds 11.98 V. Rev 48 keeps 0.90 for a
 * second reason as well - it puts the Antek at 87% of rated flux at 20 Hz. A
 * trim above about 0.95 means changing the transformer tap, not the duty.
 *
 * An earlier version of this comment said to leave it at 1.00 until a no-load
 * secondary measurement existed. Rev 47 supersedes that.
 * ------------------------------------------------------------------------- */
static constexpr float G_AMPLITUDE = 0.90f;

/* ---- Section 3.2: pin assignments ---------------------------------------- */

static constexpr int PIN_PWM_A     = 32;  // LEDC CH0 -> gate 1 -> IN1
static constexpr int PIN_PWM_B     = 33;  // LEDC CH1 -> gate 2 -> IN2
static constexpr int PIN_SD        = 14;  // -> gates 3+4 -> SD. HIGH = enabled
static constexpr int PIN_ENBL      =  4;  // master enable, active LOW, pull-up
static constexpr int PIN_SYNC      = 15;  // waveform sync out to J9 pin 3, doc 12.5.
                                          // STRAPPING PIN - must be high when the ROM
                                          // bootloader samples it, and low at reset
                                          // also silences the boot log, so it is left
                                          // an input until setup() claims it.
                                          //
                                          // Because the run starts at START_STEP, the
                                          // first sync write after SD is the LOW at
                                          // k == SINE_STEPS/2, and that is a no-op -
                                          // parkOutputs() already idles it low. The
                                          // first real edge is the rising one at k == 0,
                                          // three quarters of a cycle later, so the
                                          // first 37.5 ms of output carries sync low.
                                          // Expected, not a bug.

static constexpr uint8_t LEDC_CH_A = 0;   // passed to ledcAttachChannel()
static constexpr uint8_t LEDC_CH_B = 1;

static constexpr uint32_t ENBL_DEBOUNCE_MS = 20;

/* ---- LEDC setup ----------------------------------------------------------
 * Core 3.x only. The 2.x path (ledcSetup + ledcAttachPin, duty addressed by
 * channel rather than by pin) was carried until the board had run, and is now
 * removed - it was untested code, and untested code that touches the bridge
 * drive is worse than no code. The #error below makes a downgrade a build
 * failure rather than a silent fallback.
 *
 * One thing the 2.x path did that this one cannot: it set duty to DUTY_MAX
 * before attaching the pin, so the pin never presented a LOW. In 3.x the
 * attach and the first duty write are separate calls, so between them both
 * PWM pins sit at duty 0.
 *
 * That window used to matter and no longer does. Doc Rev 40 removed the gate
 * cross-coupling, so both PWM pins LOW is now IN1 = IN2 = HIGH: Q1 and Q2, both
 * high sides, both ends of the primary at the rail, no path to ground. A zero
 * vector. Before Rev 40 the same window was IN1 high with IN2 low - Q1 and Q4,
 * the full rail across the primary as DC - and was survivable only because SD
 * is already driven LOW by setup(). parkOutputs() is still called immediately
 * after, but it is now tidiness rather than the thing standing between the
 * attach and a DC short.
 * ------------------------------------------------------------------------- */

#if ESP_ARDUINO_VERSION_MAJOR < 3
#error "Requires ESP32 Arduino core 3.x - the 2.x LEDC path was removed."
#endif

static inline void pwmWrite(int pin, uint32_t duty) {
  ledcWrite(pin, duty);
}

static bool pwmBegin() {
  if (!ledcAttachChannel(PIN_PWM_A, CARRIER_FREQ_HZ, LEDC_RESOLUTION_BITS, LEDC_CH_A)) return false;
  if (!ledcAttachChannel(PIN_PWM_B, CARRIER_FREQ_HZ, LEDC_RESOLUTION_BITS, LEDC_CH_B)) return false;
  return true;
}

/* ---- Duty tables ---------------------------------------------------------
 * Precomputed register values, already complemented. One leg modulates while
 * the other is parked HIGH, so the differential across T1 is +/-24V peak and
 * 48 Vpp at G_AMPLITUDE = 1.0 - the figure section 9.1 works from. At the 0.90
 * actually in use it is +/-21.6V peak, 43 Vpp. Rev 48 targets 70-80V RMS out of
 * the Antek's 230V winding; the exact ratio waits on measurement.
 *
 * TEMPORARY, 2026-09-04, and it is the firmware's only departure from Rev 48.
 * Section 5 specifies a 74HCT04 hex inverter with every signal routed through
 * two of its gates - 1-2 for PWM A, 3-4 for PWM B, 5-6 for SD - so each path
 * inverts twice and is therefore non-inverting end to end. Against that part the
 * tables want the direct Rev 44 form: duty = d on the active leg, 0 on the
 * parked leg.
 *
 * That part is not fitted. The board still carries the 74HCT02, whose single
 * gate per PWM path inverts, so the tables are complemented here to suit the
 * board as it physically exists. The Rev 44 form was flashed once, briefly, on
 * 2026-09-04 and both legs appeared to switch on the same half-cycle.
 *
 * When the 74HCT04 goes in: duty = d on the active leg, 0 on the parked leg,
 * park at 0, un-complement the peak calculation in printBanner(), and drop the
 * two digitalWrite HIGHs on the PWM pins in setup(). Note that SD was already
 * a double-inverted, non-inverting path on the 74HCT02 (gates 3+4) and does not
 * change.
 *
 * Phase is sampled at the centre of each step rather than the edge. It costs
 * nothing and avoids a step of exactly zero duty at each zero crossing.
 * ------------------------------------------------------------------------- */

static uint16_t duty_a[SINE_STEPS];
static uint16_t duty_b[SINE_STEPS];

static void buildDutyTables(float g) {
  if (g < 0.0f) g = 0.0f;
  if (g > 1.0f) g = 1.0f;

  for (uint32_t k = 0; k < SINE_STEPS; ++k) {
    const float s = sinf(2.0f * (float)M_PI * ((float)k + 0.5f) / (float)SINE_STEPS);
    long d = lroundf(g * fabsf(s) * (float)DUTY_MAX);
    if (d < 0)                    d = 0;
    if (d > (long)DUTY_MAX)       d = (long)DUTY_MAX;

    if (s >= 0.0f) {                                   // left leg switches
      duty_a[k] = (uint16_t)((long)DUTY_MAX - d);
      duty_b[k] = (uint16_t)DUTY_MAX;                  // right leg tied to GND
    } else {                                           // right leg switches
      duty_a[k] = (uint16_t)DUTY_MAX;                  // left leg tied to GND
      duty_b[k] = (uint16_t)((long)DUTY_MAX - d);
    }
  }
}

/* ---- Step timer ----------------------------------------------------------
 * Section 12.2 asks for the LEDC end-of-period interrupt on CH0 rather than a
 * separate timer, to avoid fractional-period jitter. This uses a periodic
 * esp_timer at 200 us instead. The reason it is equivalent here: LEDC latches
 * a new duty at the next carrier period boundary, so a duty written at an
 * arbitrary instant still takes effect on a period edge. The only residual
 * error is which period it lands on - occasionally 7 or 9 carrier cycles
 * rather than 8, which is at most 25 us on a 50 ms waveform and does not
 * accumulate, since the timer free-runs at its own rate.
 *
 * Dispatch is ESP_TIMER_TASK, so the callback runs in task context and
 * ledcWrite() is legal in it. It is not an ISR; do not mark it IRAM_ATTR.
 * ------------------------------------------------------------------------- */

static esp_timer_handle_t step_timer  = nullptr;
static volatile uint32_t  step_index  = 0;
static volatile uint32_t  tick_count  = 0;
static bool               running     = false;

static void stepCallback(void*) {
  const uint32_t k = step_index;
  pwmWrite(PIN_PWM_A, duty_a[k]);
  pwmWrite(PIN_PWM_B, duty_b[k]);

  // Sync out on J9 pin 3: rising edge at the start of the positive half-cycle,
  // falling at the start of the negative. One 20Hz square wave, 50% duty.
  // Levels are written, not toggled - a toggle that misses a tick stays
  // inverted for the whole run, where this re-asserts twice per cycle.
  if (k == 0)                    digitalWrite(PIN_SYNC, HIGH);
  else if (k == SINE_STEPS / 2)  digitalWrite(PIN_SYNC, LOW);
  step_index = (k + 1 == SINE_STEPS) ? 0 : (k + 1);
  tick_count = tick_count + 1;   // not tick_count++ : C++20 deprecates ++ on volatile
}

static void parkOutputs() {
  pwmWrite(PIN_PWM_A, DUTY_MAX);   // both pins HIGH
  pwmWrite(PIN_PWM_B, DUTY_MAX);   // both IR2104 IN pins LOW
  digitalWrite(PIN_SYNC, LOW);     // sync idles low whenever the generator is stopped
}

/* ---- Section 4.5 gate ----------------------------------------------------
 * "Do not arm the H-bridge if a required slave is absent." Replace this with
 * the real scan result when the I2C layer lands.
 * ------------------------------------------------------------------------- */
/* esp32.md 4.2 step 8. Set by the boot scan and by every I2C recovery. The
 * bridge is not armed while a configured expander is missing: the generator
 * would be feeding a ring bus whose relays the firmware cannot see or release. */
static bool expanders_all_present = false;

static bool slavesPresent() {
  if (expanders_all_present) return true;
  return BENCH_ALLOW_MISSING_EXPANDERS;   // see sb_config.h; temporary
}

/* ---- Section 6.1 / 6.2: start and stop ----------------------------------- */

/* ---- Start phase ---------------------------------------------------------
 * The waveform starts at the positive voltage peak, not at a zero crossing.
 *
 * Flux is the integral of applied volts. Starting at a zero crossing from zero
 * flux drives the first half-cycle from 0 to 2*Phi_pk - twice the steady-state
 * excursion. Starting at the peak begins the integral where steady-state flux
 * is zero, so the first half-cycle runs 0 to -Phi_pk and matches every one that
 * follows. T1 is specified as an Antek AS-0522 toroid driven from its 44V
 * winding, which takes 44 * 20/50 = 17.6 V RMS at 20 Hz before rated flux -
 * see the bench-state note in the header; it is not yet fitted. The bridge applies
 * 15.3 V RMS at g_amplitude 0.90, so steady state sits at 87% of rated and a
 * zero-crossing start would put the first half-cycle at about 175%. The core
 * saturates, magnetizing current spikes for up to 25 ms, and F1 sees it - Rev 48
 * section 7.2 reasons that ten times a slow-blow's rating opens it in
 * milliseconds. The generator free-runs from power-up, so this happened once per
 * power-up, which is once too often. Soft-start modules for large mains toroids
 * switch at the mains peak for exactly this reason.
 *
 * Rev 48 section 12.6 is the requirement. Do not "fix" this back to zero.
 *
 * Two consequences, both expected and neither a fault:
 *
 * Bootstrap. SD is low until after the first tick, so neither C_BOOT is charged
 * when the bridge is enabled. The active leg sits at ~90% duty, whose low-side
 * window is ~2.5 us of each 25 us carrier period; C_BOOT charges through those
 * windows and the IR2104 UVLO holds HO off until it has. Expect the first few
 * carrier cycles to show no high-side drive on the active leg. The parked leg's
 * low side is on continuously, so the primary is simply held at zero for a few
 * tens of microseconds. See the G_AMPLITUDE note: at 1.00 that refill window
 * does not exist, which is why the trim must not be raised to tidy the start.
 *
 * Remanent flux. stopWaveform() still drops SD at whatever phase it has
 * reached, so a restart carries whatever remanence the toroid kept. The peak
 * start removes the drive's own contribution to the first-half-cycle excursion,
 * not that. Acceptable while the generator runs continuously; not solved here.
 * ------------------------------------------------------------------------- */
static constexpr uint32_t START_STEP = SINE_STEPS / 4;   // 62 of 250. Exact:
                                                         // phase is sampled at
                                                         // k+0.5, so 62.5/250 is
                                                         // a quarter cycle and
                                                         // sin is precisely +1.

static bool startWaveform() {
  if (running) return true;
  if (!slavesPresent()) {
    Serial.println("ARM REFUSED: required I2C slave absent (section 4.5)");
    return false;
  }

  step_index = START_STEP;
  tick_count = 0;
  pwmWrite(PIN_PWM_A, duty_a[START_STEP]);
  pwmWrite(PIN_PWM_B, duty_b[START_STEP]);

  if (esp_timer_start_periodic(step_timer, STEP_PERIOD_US) != ESP_OK) {
    Serial.println("ARM REFUSED: step timer would not start");
    parkOutputs();
    return false;
  }

  // Wait for the first tick so the waveform phase is established before SD.
  const uint32_t t0 = micros();
  while (tick_count == 0) {
    if (micros() - t0 > 5000) {
      Serial.println("ARM REFUSED: no step tick within 5 ms");
      esp_timer_stop(step_timer);
      parkOutputs();
      return false;
    }
  }

  digitalWrite(PIN_SD, HIGH);          // IR2104s enabled - last, not first
  running = true;
  Serial.println("RUN");
  return true;
}

static void stopWaveform() {
  digitalWrite(PIN_SD, LOW);           // SD first: bridge off immediately
  if (step_timer) esp_timer_stop(step_timer);
  parkOutputs();                       // then the redundant off state
  running = false;
  Serial.println("IDLE");
}

/* ---- Enable input, debounced --------------------------------------------- */

static bool     enbl_stable   = false;   // true = asserted = pin LOW = run
static bool     enbl_last_raw = false;
static uint32_t enbl_changed_ms = 0;

static void serviceEnable() {
  const bool raw = (digitalRead(PIN_ENBL) == LOW);
  const uint32_t now = millis();

  if (raw != enbl_last_raw) {
    enbl_last_raw   = raw;
    enbl_changed_ms = now;
    return;
  }
  if (raw == enbl_stable) return;
  if (now - enbl_changed_ms < ENBL_DEBOUNCE_MS) return;

  enbl_stable = raw;
  if (enbl_stable) startWaveform();
  else             stopWaveform();
}

/* ---- setup / loop -------------------------------------------------------- */

/* Configuration and live state, on demand. Called once from setup() and again
 * whenever a character arrives on the console, so the question "what is this
 * board actually running" has an answer at any moment rather than only in the
 * first half second after a reset - which is exactly when nothing is attached
 * to read it. peak is recomputed here rather than cached; it is 250 iterations
 * and this is not a hot path. */
/* ---- Loop timing (esp32.md 1.7 code consequence (a)) --------------------
 * The 200Hz poll is only as good as the loop that runs it. Anything that holds
 * loop() - a burst of QoS 1 publishes each waiting for its PUBACK, a blocking
 * reconnect - stretches the gap between poll ticks, and every threshold in
 * esp32.md 7 and 8 is measured in those ticks. Two figures, both maxima since
 * the banner last printed them:
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

static void printBanner() {
  uint32_t peak = 0;
  for (uint32_t k = 0; k < SINE_STEPS; ++k) {
    const uint32_t da = DUTY_MAX - duty_a[k];   // tables are complemented
    const uint32_t db = DUTY_MAX - duty_b[k];
    if (da > peak) peak = da;
    if (db > peak) peak = db;
  }

  Serial.println();
  Serial.println("551 ring generator - PWM only");
  Serial.printf("  carrier      %lu Hz, %u bits\n",
                (unsigned long)CARRIER_FREQ_HZ, LEDC_RESOLUTION_BITS);
  Serial.printf("  step         %lu us, %lu steps, %.3f Hz output\n",
                (unsigned long)STEP_PERIOD_US, (unsigned long)SINE_STEPS,
                1000000.0 / (double)(STEP_PERIOD_US * SINE_STEPS));
  Serial.printf("  g_amplitude  %.4f, peak duty %lu / %lu\n",
                (double)G_AMPLITUDE, (unsigned long)peak, (unsigned long)DUTY_MAX);
  Serial.printf("  start step   %lu of %lu, phase %.1f deg (positive peak)\n",
                (unsigned long)START_STEP, (unsigned long)SINE_STEPS,
                360.0 * ((double)START_STEP + 0.5) / (double)SINE_STEPS);
  Serial.println("  GPIO4 LOW to run (J9 pins 1-2)");
  Serial.printf ("  sync on GPIO%d (J9 pin 3): rising = positive half-cycle\n", PIN_SYNC);
  // tick_count advancing at 5000/s is the only visibility into whether the
  // esp_timer is really dispatching: a stalled timer with the bridge armed
  // looks exactly like a working one until a scope goes on GPIO32. enbl is the
  // raw pin, before debounce, so a jumper can be checked against what
  // serviceEnable() decided.
  Serial.printf("  state        %s, enbl=%d, ticks=%lu\n",
                running ? "RUN" : "IDLE",
                (digitalRead(PIN_ENBL) == LOW) ? 1 : 0,
                (unsigned long)tick_count);

  /* ---- the rest of the controller ------------------------------------
   * The expander line is the arming gate's input, so a refused arm can be
   * explained from the same keypress that reported it. The heartbeat line is
   * the one thing the MQTT side cannot tell you about itself: a game program
   * that has died leaves `online` on the broker and retained state that looks
   * current. */
  Serial.print("  expanders   ");
  for (uint8_t i = 0; i < N_EXPANDERS; ++i) {
    if (!expanderConfigured(i)) continue;
    Serial.printf(" 0x%02X:%s", expanders[i].addr,
                  exp_state[i].present ? "ok" : "MISSING");
  }
  Serial.printf("   (%u station board(s) fitted)\n",
                (unsigned)STATION_BOARDS_FITTED);
  Serial.printf("  arming gate  %s\n",
                slavesPresent() ? "pass" : "INHIBITED - expander absent");
  Serial.printf("  mqtt         %s, broker %s:%u\n",
                netConnected() ? "connected" : "down",
                MQTT_BROKER_HOST, (unsigned)MQTT_PORT);
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
  loop_max_us     = 0;
  poll_gap_max_ms = 0;
  timing_since_ms = now;
}

void setup() {
  // SD low before anything else touches the PWM pins. R_SD_PD (at GPIO14) and
  // R_SD_PD2 (on the SD net itself) already hold it low through boot; this
  // makes it driven rather than merely pulled. SD LOW = shutdown.
  pinMode(PIN_SD, OUTPUT);
  digitalWrite(PIN_SD, LOW);

  // Park the PWM pins HIGH before the LEDC peripheral takes them.
  pinMode(PIN_PWM_A, OUTPUT); digitalWrite(PIN_PWM_A, HIGH);
  pinMode(PIN_PWM_B, OUTPUT); digitalWrite(PIN_PWM_B, HIGH);

  // Expander /RESET idles HIGH (section 4.7). The 1 ms assert and the scan
  // belong with the I2C code; this only stops the line floating.
  pinMode(PIN_EXP_RESET, OUTPUT);
  digitalWrite(PIN_EXP_RESET, HIGH);

  // Sync output. Claimed here rather than at file scope because GPIO15 is a
  // strapping pin: driving it before the ROM bootloader samples it changes boot
  // behaviour and silences the boot log.
  pinMode(PIN_SYNC, OUTPUT);
  digitalWrite(PIN_SYNC, LOW);

  pinMode(PIN_ENBL, INPUT_PULLUP);     // grounding GPIO4 enables the generator

  Serial.begin(115200);
  delay(200);
  Serial.println("Starting");

  /* ---- 4.2 step 3: Ethernet, and the MQTT client configured ---------- */
  netInit();

  /* ---- 4.2 step 4: expander /RESET ----------------------------------- */
  expanderResetPulse();

  /* ---- 4.2 steps 5 and 6: I2C, scan, configure ----------------------- */
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, I2C_CLOCK_HZ);
  stationInit();
  trunkInit();
  expanders_all_present = expanderScanAndConfigure();

  /* ---- 4.2 step 7: MQTT birth, subscribe, publish all state ----------
   * Given a bounded wait rather than blocked on: the generator must run
   * whenever GPIO4 is low (8.5), so a broker that is down must not keep the
   * ring bus dark. If the connection does not come up here, netService() in
   * loop() keeps trying and the birth sequence runs on the connect edge. */
  const uint32_t mqtt_wait_until = millis() + 6000;
  while (!netConnected() && millis() < mqtt_wait_until) {
    netService(millis());
    delay(10);
  }
  if (netConnected()) {
    stationPublishAll();
    trunkPublishAll();
    netPublishI2cScan(expanders_all_present);
    (void)netTakeJustConnected();      // the birth sequence has just been run
  } else {
    Serial.println("mqtt: not connected at boot; will connect from loop()");
  }

  /* ---- 4.2 step 8: the arming gate ----------------------------------- */
  if (!expanders_all_present) {
    if (BENCH_ALLOW_MISSING_EXPANDERS) {
      Serial.println("BENCH OVERRIDE: a configured expander is absent, but "
                     "BENCH_ALLOW_MISSING_EXPANDERS is set, so the bridge will "
                     "still arm. Clear it in sb_config.h once a board is fitted.");
    } else {
      Serial.println("ARM INHIBITED: a configured expander is absent (4.2 step 8)");
    }
  }

  /* ---- 4.2 step 9: LEDC, both channels at duty 0 ---------------------
   * Configured whether or not the gate passed. Duty 0 with SD low is the
   * hardware's own park state - the peripheral comes up that way - so this is
   * not arming anything. Steps 10 to 12 are startWaveform(), which the enable
   * input reaches through serviceEnable() and which refuses on a failed gate. */
  buildDutyTables(G_AMPLITUDE);

  if (!pwmBegin()) {
    Serial.println("FATAL: LEDC would not configure at 40 kHz / 10 bits");
    while (true) delay(1000);
  }
  parkOutputs();

  esp_timer_create_args_t args = {};
  args.callback        = &stepCallback;
  args.arg             = nullptr;
  args.dispatch_method = ESP_TIMER_TASK;
  args.name            = "ring_step";
  if (esp_timer_create(&args, &step_timer) != ESP_OK) {
    Serial.println("FATAL: could not create step timer");
    while (true) delay(1000);
  }

  printBanner();

  // Adopt the switch position already present at power-on rather than waiting
  // for an edge, so a board that boots with the switch closed comes up running.
  enbl_last_raw   = (digitalRead(PIN_ENBL) == LOW);
  enbl_stable     = false;
  enbl_changed_ms = millis();
}

/* The console is silent unless something happens: RUN and IDLE are announced
 * by startWaveform()/stopWaveform() as they occur, and anything else is had by
 * asking. Send any character and printBanner() reports the configuration and
 * the live state together. A once-a-second heartbeat lived here while the
 * board was first being brought up; it had served its purpose and only made
 * captured logs harder to read. */
/* ---- The failsafe table (esp32.md 10) ------------------------------------
 * Every relay is released on any of these, independently and without reference
 * to the host. They are gathered here rather than pushed into the modules that
 * own the relays because this is the only place that sees all of the conditions
 * at once, and because a failsafe split across three files is a failsafe nobody
 * can audit.
 *
 * Three rows of that table are elsewhere, each for a reason:
 *   Power-on / reset          the hardware's doing, before any of this runs (4.1)
 *   Expander absent at boot   the arming gate in setup(), via slavesPresent()
 *   Trunk ringing for 30s     per-trunk, in trunkPoll(), beside the cadence it
 *                             interrupts
 * ------------------------------------------------------------------------- */

static bool     mqtt_was_up       = false;
static bool     game_was_up       = false;
static uint32_t last_poll_ms      = 0;
static uint32_t last_republish_ms = 0;


static void releaseAllRelays(const char* why) {
  Serial.printf("FAILSAFE: releasing all relays - %s\n", why);
  stationReleaseAll();
  trunkReleaseAll();
  expanderReleaseAllRelays();     // unconditional, not the dirty-flag path:
                                  // this runs when things are already wrong

  /* Echo it if there is anyone to echo to. On the MQTT-loss path there is not,
   * and the retained values stay stale until the reconnect republishes them -
   * which is what ctl/status going to `offline` is for. On the game-heartbeat
   * path the broker is healthy, and a host that recovers must not read a
   * retained hook=on for a relay this just dropped. */
  if (netConnected()) {
    stationPublishAll();
    trunkPublishAll();
  }
}

static void serviceFailsafes(uint32_t now) {
  const bool mqtt_up = netConnected();
  const bool game_up = netGameAlive(now);

  /* Edge-triggered. A command arriving while the game heartbeat is missing is
   * still acted on (9.4) - the heartbeat's return is the recovery signal and
   * the command is evidence of it - so holding the relays down continuously
   * would fight the specified behaviour. */
  if (mqtt_was_up && !mqtt_up) releaseAllRelays("MQTT connection lost");
  if (game_was_up && !game_up) releaseAllRelays("game heartbeat missed twice");
  if (!game_was_up && game_up) Serial.println("game heartbeat returned");
  mqtt_was_up = mqtt_up;
  game_was_up = game_up;

  if (expanderBusFault()) {
    /* 6.2: inhibit ring before /RESET. A reset mid-cadence would release the
     * ring relay at an arbitrary point in the 20Hz waveform rather than at a
     * cadence boundary. */
    trunkInhibitRing();
    expanderFlushRelays();

    const bool ok = expanderRecover();
    expanders_all_present = ok;

    /* The reset dropped every relay in hardware, so the firmware's own idea of
     * them has to come back to zero as well or the echoed state would be a lie. */
    stationReleaseAll();
    trunkReleaseAll();

    if (netConnected()) {
      stationPublishAll();
      trunkPublishAll();
      netPublishI2cScan(ok);
    }
  }
}

void loop() {
  const uint32_t now = millis();
  const uint32_t pass_start_us = micros();

  netService(now);            // keepalive ping and inbound commands

  /* A reconnect, a ctl/sync and the 30s timer of 9.2 all mean the same thing:
   * republish every state topic. The timer bounds how long a lost publish can
   * leave a retained value stale at the broker; subscribers react to changes in
   * value, so a repeated value is harmless (mqtt.md 8.3). */
  const bool reconnected = netTakeJustConnected();
  const bool sync_asked  = netTakeSyncRequest();
  if (netConnected() &&
      (reconnected || sync_asked || (now - last_republish_ms >= STATE_REPUBLISH_MS))) {
    last_republish_ms = now;
    stationPublishAll();
    trunkPublishAll();
    if (reconnected) netPublishI2cScan(expanders_all_present);
  }

  /* ---- the 200Hz sample stream (6.3) --------------------------------
   * Everything in 7 and 8 runs from here. Nothing samples independently. */
  if (now - last_poll_ms >= POLL_PERIOD_MS) {
    const uint32_t gap = now - last_poll_ms;
    if (last_poll_ms != 0 && gap > poll_gap_max_ms) poll_gap_max_ms = gap;
    last_poll_ms = now;

    expanderPollInputs();
    stationPoll(now);
    trunkPoll(now);
    expanderFlushRelays();

    /* 9.3: after the poll and from this loop - never from a timer or the
     * network task - so the beat proves the loop that drives relays is running
     * and not merely that the network stack is alive. */
    netHeartbeat(now);

    serviceFailsafes(now);
  }

  serviceEnable();

  const uint32_t pass_us = micros() - pass_start_us;
  if (pass_us > loop_max_us) loop_max_us = pass_us;

  if (Serial.available()) {
    while (Serial.available()) Serial.read();
    printBanner();
  }

  /* 1ms, so the idle task runs and mqtt.loop() is still called five times per
   * 5ms poll. The poll interval is compared against millis() rather than being
   * driven by this delay, so the work above does not accumulate into drift. */
  delay(1);
}
