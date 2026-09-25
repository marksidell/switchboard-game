/* =============================================================================
 * sb_expander.cpp - MCP23017 register driver
 * ========================================================================== */

#include <Wire.h>
#include "sb_expander.h"

/* ---- Registers, IOCON.BANK = 0 -------------------------------------------
 * BANK = 0 is the power-on default and every path into this file has pulsed
 * /RESET first, so the addresses below are the ones in effect. IOCON is left at
 * its default rather than written: writing it is only safe once you know which
 * bank you are in, and a hardware reset is a stronger guarantee than a write.
 * ------------------------------------------------------------------------- */
static constexpr uint8_t REG_IODIRA = 0x00;
static constexpr uint8_t REG_IODIRB = 0x01;
static constexpr uint8_t REG_IPOLA  = 0x02;
static constexpr uint8_t REG_IPOLB  = 0x03;
static constexpr uint8_t REG_GPINTENA = 0x04;
static constexpr uint8_t REG_GPINTENB = 0x05;
static constexpr uint8_t REG_GPPUA  = 0x0C;
static constexpr uint8_t REG_GPPUB  = 0x0D;
static constexpr uint8_t REG_GPIOA  = 0x12;
static constexpr uint8_t REG_OLATB  = 0x15;

/* A single NAK can be noise on a daisy-chained bus with 2.2k pull-ups and six
 * feet of 6P6C cord. Three consecutive failures on the same device is a fault;
 * one is a glitch to log and retry. control.md 6.2 and 10 both give the three. */
static constexpr uint8_t BUS_FAULT_THRESHOLD = 3;

static uint8_t consecutive_errors[N_EXPANDERS];
static bool    bus_fault = false;

/* ---- Register access ---------------------------------------------------- */

static bool regWrite(uint8_t addr, uint8_t reg, uint8_t val) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission() == 0;
}

static bool regRead(uint8_t addr, uint8_t reg, uint8_t& val) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;   // repeated start
  if (Wire.requestFrom((int)addr, 1) != 1) return false;
  val = (uint8_t)Wire.read();
  return true;
}

static bool probe(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

/* Record the outcome of a transaction against one expander. control.md 6.2: one
 * error is logged and counted, not acted on; three consecutive errors on the
 * same device is the fault. Every error is logged, so a bus that is degrading
 * but not yet failing leaves a trail - which is the only way a marginal
 * connection is ever found before it becomes a fault.
 *
 * This cannot flood the log: the device is marked absent on the third error and
 * the poll then skips it, so a failure costs three lines and not two hundred a
 * second. */
static void noteResult(uint8_t idx, bool ok) {
  if (ok) {
    consecutive_errors[idx] = 0;
    return;
  }
  if (consecutive_errors[idx] < 255) consecutive_errors[idx]++;

  if (consecutive_errors[idx] < BUS_FAULT_THRESHOLD) {
    Serial.printf("I2C: %s (0x%02X) error %u of %u - logged, not acted on\n",
                  expanders[idx].label, expanders[idx].addr,
                  (unsigned)consecutive_errors[idx],
                  (unsigned)BUS_FAULT_THRESHOLD);
    return;
  }

  if (exp_state[idx].present) {
    Serial.printf("I2C: %s (0x%02X) BUS FAULT - %u consecutive errors\n",
                  expanders[idx].label, expanders[idx].addr,
                  (unsigned)consecutive_errors[idx]);
  }
  exp_state[idx].present = false;
  bus_fault = true;
}

/* ---- /RESET ------------------------------------------------------------- */

void expanderResetPulse() {
  digitalWrite(PIN_EXP_RESET, LOW);
  delay(EXP_RESET_HOLD_MS);
  digitalWrite(PIN_EXP_RESET, HIGH);
  delay(EXP_RESET_SETTLE_MS);

  /* The reset dropped every relay in hardware. Bring the shadows into line so
   * the firmware's idea of the outputs matches the silicon, or the next flush
   * would skip a write it thinks is redundant. */
  for (uint8_t i = 0; i < N_EXPANDERS; ++i) {
    exp_state[i].relay_shadow = 0;
    exp_state[i].relay_dirty  = false;
  }
}

/* ---- Scan and configure ------------------------------------------------- */

/* control.md 4.2 step 6: Port A inputs, Port B outputs, pull-ups off (the boards
 * fit their own), IPOL on Port A so a read returns 1 for present, Port B latch
 * zero so every relay is released by command as well as by default. Interrupts
 * are disabled explicitly: there is no INT line and none is wanted (6.3). */
static bool configureOne(uint8_t idx) {
  const uint8_t a = expanders[idx].addr;
  bool ok = true;
  ok &= regWrite(a, REG_IODIRA,   0xFF);   // Port A all inputs
  ok &= regWrite(a, REG_IODIRB,   0x00);   // Port B all outputs
  ok &= regWrite(a, REG_GPPUA,    0x00);   // no internal pull-ups
  ok &= regWrite(a, REG_GPPUB,    0x00);
  ok &= regWrite(a, REG_IPOLA,    0xFF);   // detectors are active low
  ok &= regWrite(a, REG_IPOLB,    0x00);
  ok &= regWrite(a, REG_GPINTENA, 0x00);   // no interrupt-on-change
  ok &= regWrite(a, REG_GPINTENB, 0x00);
  ok &= regWrite(a, REG_OLATB,    0x00);   // all relays released
  return ok;
}

bool expanderScanAndConfigure(bool quiet) {
  bool all_present = true;

  for (uint8_t i = 0; i < N_EXPANDERS; ++i) {
    exp_state[i].present      = false;
    exp_state[i].inputs       = 0;
    exp_state[i].relay_shadow = 0;
    exp_state[i].relay_dirty  = false;
    consecutive_errors[i]     = 0;

    if (!expanderConfigured(i)) continue;       // board not fitted: not a fault

    if (!probe(expanders[i].addr)) {
      if (!quiet) Serial.printf("I2C: MISSING %s at 0x%02X\n",
                                expanders[i].label, expanders[i].addr);
      all_present = false;
      continue;
    }
    if (!configureOne(i)) {
      if (!quiet) Serial.printf("I2C: %s at 0x%02X answered but would not configure\n",
                                expanders[i].label, expanders[i].addr);
      all_present = false;
      continue;
    }
    exp_state[i].present = true;
    if (!quiet) Serial.printf("I2C: %s at 0x%02X configured\n",
                              expanders[i].label, expanders[i].addr);
  }

  /* Not an unconditional clear. A configured expander that did not answer is
   * still a fault, and has to stay one: it is skipped by every poll from here
   * on, so this is the last chance anything has to notice it. The caller's
   * once-a-second retry is driven entirely by this flag staying set, and it is
   * what lets a board that is plugged back in be configured and used again. */
  bus_fault = !all_present;
  return all_present;
}

/* ---- Poll --------------------------------------------------------------- */

bool expanderPollInputs() {
  bool ok = true;
  for (uint8_t i = 0; i < N_EXPANDERS; ++i) {
    if (!exp_state[i].present) continue;
    uint8_t v = 0;
    const bool got = regRead(expanders[i].addr, REG_GPIOA, v);
    noteResult(i, got);
    if (got) exp_state[i].inputs = v;
    else     ok = false;
  }
  return ok;
}

/* ---- Relay writes ------------------------------------------------------- */

/* Write the shadow, then read it back. A relay that did not take is worse than
 * one that never got the command: the state topic would report a closed loop
 * the hardware is not holding. */
static bool writeAndVerify(uint8_t idx) {
  const uint8_t a    = expanders[idx].addr;
  const uint8_t want = exp_state[idx].relay_shadow;

  if (!regWrite(a, REG_OLATB, want)) { noteResult(idx, false); return false; }

  uint8_t got = 0;
  if (!regRead(a, REG_OLATB, got))   { noteResult(idx, false); return false; }

  if (got != want) {
    Serial.printf("I2C: %s OLATB read back 0x%02X, wrote 0x%02X\n",
                  expanders[idx].label, got, want);
    noteResult(idx, false);
    return false;
  }
  noteResult(idx, true);
  return true;
}

bool expanderFlushRelays() {
  bool ok = true;
  for (uint8_t i = 0; i < N_EXPANDERS; ++i) {
    if (!exp_state[i].present || !exp_state[i].relay_dirty) continue;
    if (writeAndVerify(i)) exp_state[i].relay_dirty = false;
    else                   ok = false;
  }
  return ok;
}

void expanderReleaseAllRelays() {
  for (uint8_t i = 0; i < N_EXPANDERS; ++i) {
    exp_state[i].relay_shadow = 0;
    exp_state[i].relay_dirty  = false;
    if (!exp_state[i].present) continue;
    /* Unconditional and unverified: this runs on the failure paths, where the
     * bus may already be the thing that is broken. Try, and do not let a NAK
     * stop the remaining expanders from being told. */
    regWrite(expanders[i].addr, REG_OLATB, 0x00);
  }
}

/* ---- Fault and recovery ------------------------------------------------- */

bool expanderBusFault() { return bus_fault; }

bool expanderRecover(bool quiet) {
  if (!quiet) Serial.println("I2C: recovering - /RESET, rescan, reconfigure");
  expanderResetPulse();
  const bool ok = expanderScanAndConfigure(quiet);
  if (!ok && !quiet)
    Serial.println("I2C: recovery incomplete - an expander is still absent; "
                   "retrying once a second");
  return ok;
}
