/* =============================================================================
 * sb_ring.h - the ring waveform
 *
 * control.md 3 and 5; ring_generator.md owns the bridge, the 74HCT04 and the
 * waveform arithmetic, and "ring_generator.md §N" below is that document.
 *
 * Generates the 20.000 Hz sine on a 40 kHz carrier that drives the two IR2104
 * half-bridges through the 74HCT04, and sequences SD around it. The generator
 * runs while GPIO4 is held LOW, whatever the I2C scan found; it free-runs, and
 * ring cadence is done by the trunk board's relays (control.md 8.4), not here.
 *
 * POLARITY (ring_generator.md §5.1/5.2)
 *   IN2 = GPIO32,  IN1 = GPIO33,  SD = GPIO14.  All non-inverting.
 *
 *   The 74HCT04 routes each signal through two gates, so the pins are ACTIVE
 *   HIGH, duty is written directly and the park value is 0. LEDC's own
 *   power-on state is therefore the safe one: both pins low is IN1 = IN2 =
 *   low, Q3 and Q4 on, primary shorted to ground.
 *
 *   R_PWMA_PD and R_PWMB_PD are pull-downs and not optional: GPIO32 and GPIO33
 *   have no internal pull at reset, so without them both inverter inputs float
 *   through the bootloader window.
 *
 *   The 74HCT04 is not a shoot-through interlock. Shoot-through within a leg is
 *   prevented inside the IR2104, which derives HO and LO from one IN pin with
 *   520ns typical deadtime (400 min, 650 max). The gate is 3.3V-to-5V level
 *   translation, needed because the ESP32's guaranteed VOH of 0.8 x VDD = 2.64V
 *   sits below the IR2104's 3.0V VIH minimum.
 * ========================================================================== */

#pragma once

#include <Arduino.h>

/* ---- ring_generator.md §12.2: waveform constants -------------------------- */

static constexpr uint32_t CARRIER_FREQ_HZ         = 40000;  // 25 us period
static constexpr uint32_t CARRIER_CYCLES_PER_STEP = 8;      // 200 us step
static constexpr uint32_t SINE_STEPS              = 250;    // 50 ms = 20.000 Hz
static constexpr uint8_t  LEDC_RESOLUTION_BITS    = 10;     // 1024 duty levels

static_assert(CARRIER_FREQ_HZ == 20UL * CARRIER_CYCLES_PER_STEP * SINE_STEPS,
              "Section 12.2 constraint violated: 20 = f_carrier / (cycles x steps)");

static constexpr uint32_t STEP_PERIOD_US =
    (1000000UL * CARRIER_CYCLES_PER_STEP) / CARRIER_FREQ_HZ;   // 200

// 2^bits is the LEDC "always high" duty. Through the 74HCT04's two gates a
// pin HIGH is IN HIGH, the high side of that leg on (control.md 3).
static constexpr uint32_t DUTY_MAX = 1UL << LEDC_RESOLUTION_BITS;  // 1024

/* ---- ring_generator.md §9.4: output amplitude trim -----------------------
 * 0.90 is a working value, not a placeholder, and must not be raised towards
 * 1.00 to make anything look cleaner. ring_generator.md §8.3 and §9.4: at 1.00
 * the low side stops turning on at the sine peak, so C_BOOT gets no refill and
 * VB-VS collapses to about 2.6 V; at 0.90 it holds 11.98 V. 0.90 also puts the
 * Antek at 87% of rated flux at 20 Hz. A trim above about 0.95 means changing
 * the transformer tap, not the duty.
 * ------------------------------------------------------------------------- */
static constexpr float G_AMPLITUDE = 0.90f;

/* The waveform starts at the positive peak (control.md 5.3; the reason is in
 * sb_ring.cpp). 62 of 250 is exact: phase is sampled at k+0.5, so 62.5/250 is
 * a quarter cycle and sin is precisely +1. */
static constexpr uint32_t START_STEP = SINE_STEPS / 4;

/* ---- ring_generator.md §3.2: pin assignments ------------------------------ */

static constexpr int PIN_PWM_A     = 32;  // LEDC CH0 -> gates 2+5 -> IN2 (U5, right leg)
static constexpr int PIN_PWM_B     = 33;  // LEDC CH1 -> gates 1+6 -> IN1 (U4, left leg)
static constexpr int PIN_SD        = 14;  // -> gates 3+4 -> SD. HIGH = enabled
static constexpr int PIN_ENBL      =  4;  // master enable, active LOW, pull-up

/* SD and both PWM pins driven LOW, the park state, before anything else
 * touches them (control.md 4.2). */
void ringPinsSafe();

/* Duty tables, LEDC at duty 0 and the step timer (control.md 4.2 step 8).
 * Halts with a FATAL line if the peripheral or the timer will not start. */
void ringBegin();

/* Adopt the GPIO4 level present at boot, so a board that boots with the
 * switch closed comes up running rather than waiting for an edge. */
void ringAdoptEnable();

/* Debounce GPIO4 and start or stop the waveform on a change. From loop(). */
void ringServiceEnable();

/* control.md 4.3: SD low, then the outputs parked. */
void ringStop();

bool     ringRunning();
uint32_t ringTicks();      // step callbacks since the last start: 5000/s running
uint32_t ringPeakDuty();   // the largest value in the duty tables
