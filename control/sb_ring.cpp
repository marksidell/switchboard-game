/* =============================================================================
 * sb_ring.cpp - LEDC, duty tables, step timer, start and stop, enable input
 * ========================================================================== */

#include <math.h>
#include "esp_timer.h"

#include "sb_ring.h"
#include "sb_config.h"

/* ---- LEDC setup ----------------------------------------------------------
 * Core 3.x only; the #error makes a downgrade a build failure rather than a
 * silent fallback to untested code that touches the bridge drive.
 *
 * In 3.x the attach and the first duty write are separate calls, so between
 * them both PWM pins sit at duty 0. Under the 74HCT04 that is the park state
 * itself - both pins LOW, IN1 = IN2 = LOW, both low sides, the primary shorted
 * to ground - so the window is harmless by construction, and SD is driven LOW
 * by setup() before it opens in any case. parkOutputs() is still called
 * immediately after; it writes the same zeros.
 * ------------------------------------------------------------------------- */

#if ESP_ARDUINO_VERSION_MAJOR < 3
#error "Requires ESP32 Arduino core 3.x - the 2.x LEDC path was removed."
#endif

static constexpr uint8_t LEDC_CH_A = 0;   // passed to ledcAttachChannel()
static constexpr uint8_t LEDC_CH_B = 1;

static inline void pwmWrite(int pin, uint32_t duty) {
  ledcWrite(pin, duty);
}

static bool pwmBegin() {
  if (!ledcAttachChannel(PIN_PWM_A, CARRIER_FREQ_HZ, LEDC_RESOLUTION_BITS, LEDC_CH_A)) return false;
  if (!ledcAttachChannel(PIN_PWM_B, CARRIER_FREQ_HZ, LEDC_RESOLUTION_BITS, LEDC_CH_B)) return false;
  return true;
}

/* ---- Duty tables ---------------------------------------------------------
 * Precomputed register values in the direct form of control.md 3: the 74HCT04
 * routes every signal through two of its gates - 2+5 for PWM A, 1+6 for PWM B,
 * 3+4 for SD - so each path is non-inverting end to end, duty is written as
 * is, and the parked leg is 0. One leg modulates at duty d while the other is
 * parked at 0, its low side on, tied to ground. The differential across T1 is
 * then +/-24V peak and 48 Vpp at G_AMPLITUDE = 1.0 - the figure
 * ring_generator.md §9.1 works from. At 0.90 it is +/-21.6V peak, 43 Vpp.
 *
 * These tables need the 74HCT04. Do not run this build on a board that still
 * carries the 74HCT02: its single gate per path inverts every leg.
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

    if (s >= 0.0f) {                                   // right leg switches
      duty_a[k] = (uint16_t)d;
      duty_b[k] = 0;                                   // left leg tied to GND
    } else {                                           // left leg switches
      duty_a[k] = 0;                                   // right leg tied to GND
      duty_b[k] = (uint16_t)d;
    }
  }
}

/* ---- Step timer (control.md 5.2) -----------------------------------------
 * A periodic esp_timer at 200 us rather than the LEDC end-of-period interrupt.
 * Equivalent here because LEDC latches a new duty at the next carrier period
 * boundary; the residual error is at most one carrier period, 25 us, and does
 * not accumulate.
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

  step_index = (k + 1 == SINE_STEPS) ? 0 : (k + 1);
  tick_count = tick_count + 1;   // not tick_count++ : C++20 deprecates ++ on volatile
}

static void parkOutputs() {
  pwmWrite(PIN_PWM_A, 0);          // both pins LOW, both IR2104 IN pins LOW:
  pwmWrite(PIN_PWM_B, 0);          // both low sides, primary at ground (control.md 3)
}

/* esp_timer_stop() stops further dispatches but does not wait for one already
 * running on the timer task, which can be on the other core and still write a
 * duty after the caller's park. The callback ends by advancing tick_count, so wait
 * until a whole step period passes with no tick, bounded, before parking. SD is
 * already low by then, so this guards the redundant off state, not the bridge. */
static void stopStepTimer() {
  esp_timer_stop(step_timer);
  const uint32_t t0 = micros();
  uint32_t seen;
  do {
    seen = tick_count;
    delayMicroseconds(STEP_PERIOD_US);
  } while (tick_count != seen && micros() - t0 < 5000);
}

/* ---- Start and stop (control.md 4.2, 4.3, 5.3) ---------------------------
 * The waveform starts at the positive voltage peak, not at a zero crossing.
 * Do not "fix" this back to zero.
 *
 * Flux is the integral of applied volts. Starting at a zero crossing from zero
 * flux drives the first half-cycle from 0 to 2*Phi_pk - twice the steady-state
 * excursion. Starting at the peak begins the integral where steady-state flux
 * is zero, so the first half-cycle runs 0 to -Phi_pk and matches every one that
 * follows. T1, an Antek AS-0522 driven from its 44V winding, takes
 * 44 * 20/50 = 17.6 V RMS at 20 Hz before rated flux; the bridge applies
 * 15.3 V RMS at G_AMPLITUDE 0.90, so steady state sits at 87% of rated and a
 * zero-crossing start would put the first half-cycle at about 175%. The core
 * saturates, magnetizing current spikes for up to 25 ms, and F1 sees it
 * (ring_generator.md §7.2, §12.6).
 *
 * Two consequences, both expected and neither a fault:
 *
 * Bootstrap. SD is low until after the first tick, so neither C_BOOT is charged
 * when the bridge is enabled. The active leg sits at ~90% duty, whose low-side
 * window is ~2.5 us of each 25 us carrier period; C_BOOT charges through those
 * windows and the IR2104 UVLO holds HO off until it has. Expect the first few
 * carrier cycles to show no high-side drive on the active leg. At G_AMPLITUDE
 * 1.00 that refill window does not exist.
 *
 * Remanent flux. ringStop() drops SD at whatever phase it has reached, so a
 * restart carries whatever remanence the toroid kept. Accepted (control.md 5.3).
 * ------------------------------------------------------------------------- */

static bool startWaveform() {
  if (running) return true;

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
      stopStepTimer();
      parkOutputs();
      return false;
    }
  }

  digitalWrite(PIN_SD, HIGH);          // IR2104s enabled - last, not first
  running = true;
  Serial.println("RUN");
  return true;
}

void ringStop() {
  digitalWrite(PIN_SD, LOW);           // SD first: bridge off immediately
  if (step_timer) stopStepTimer();     // and any step in flight finished
  parkOutputs();                       // then the redundant off state
  running = false;
  Serial.println("IDLE");
}

/* ---- Enable input, debounced --------------------------------------------- */

static constexpr uint32_t ENBL_DEBOUNCE_MS = 20;

static bool     enbl_stable   = false;   // true = asserted = pin LOW = run
static bool     enbl_last_raw = false;
static uint32_t enbl_changed_ms = 0;

void ringServiceEnable() {
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
  else             ringStop();
}

void ringAdoptEnable() {
  enbl_last_raw   = (digitalRead(PIN_ENBL) == LOW);
  enbl_stable     = false;
  enbl_changed_ms = millis();
}

/* ---- Setup ---------------------------------------------------------------- */

void ringPinsSafe() {
  // SD low before anything else touches the PWM pins. R_SD_PD (at GPIO14)
  // already holds it low through boot; this makes it driven rather than merely
  // pulled. SD LOW = shutdown. (R_SD_PD2 is not fitted - ring_generator.md §6.)
  pinMode(PIN_SD, OUTPUT);
  digitalWrite(PIN_SD, LOW);

  // Hold the PWM pins LOW - the park state (control.md 3) - until the LEDC
  // peripheral takes them. R_PWMA_PD and R_PWMB_PD already pull them there
  // through boot; this makes it driven rather than merely pulled.
  pinMode(PIN_PWM_A, OUTPUT); digitalWrite(PIN_PWM_A, LOW);
  pinMode(PIN_PWM_B, OUTPUT); digitalWrite(PIN_PWM_B, LOW);
}

void ringBegin() {
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
}

bool     ringRunning() { return running; }
uint32_t ringTicks()   { return tick_count; }

uint32_t ringPeakDuty() {
  uint32_t peak = 0;
  for (uint32_t k = 0; k < SINE_STEPS; ++k) {
    const uint32_t da = duty_a[k];              // direct form, control.md 3
    const uint32_t db = duty_b[k];
    if (da > peak) peak = da;
    if (db > peak) peak = db;
  }
  return peak;
}
