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
static constexpr uint8_t REG_INTFA  = 0x0E;
static constexpr uint8_t REG_GPIOA  = 0x12;
static constexpr uint8_t REG_OLATB  = 0x15;

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

/* n consecutive registers from `reg`: IOCON.SEQOP is 0 at reset, so the
 * address pointer increments. */
static bool regReadN(uint8_t addr, uint8_t reg, uint8_t* val, uint8_t n) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;   // repeated start
  if (Wire.requestFrom((int)addr, (int)n) != n) return false;
  for (uint8_t i = 0; i < n; ++i) val[i] = (uint8_t)Wire.read();
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
 * zero so every relay is released by command as well as by default. There is no
 * INT line and none is wanted (6.3); interrupt-on-change is enabled only on
 * station 24's input, for its flag, INTFA, which latches a change the 5ms poll
 * would miss (7.4, Rev 34). Every other bit's is disabled explicitly. */
static bool configureOne(uint8_t idx) {
  const uint8_t a = expanders[idx].addr;
  bool ok = true;
  ok &= regWrite(a, REG_IODIRA,   0xFF);   // Port A all inputs
  ok &= regWrite(a, REG_IODIRB,   0x00);   // Port B all outputs
  ok &= regWrite(a, REG_GPPUA,    0x00);   // no internal pull-ups
  ok &= regWrite(a, REG_GPPUB,    0x00);
  ok &= regWrite(a, REG_IPOLA,    0xFF);   // detectors are active low
  ok &= regWrite(a, REG_IPOLB,    0x00);
  ok &= regWrite(a, REG_GPINTENA, latchMask(idx));   // INTFA latches these
  ok &= regWrite(a, REG_GPINTENB, 0x00);
  ok &= regWrite(a, REG_OLATB,    0x00);   // all relays released
  return ok;
}

bool expanderScanAndConfigure(bool quiet) {
  bool all_present = true;

  for (uint8_t i = 0; i < N_EXPANDERS; ++i) {
    exp_state[i].present      = false;
    exp_state[i].inputs       = 0;
    exp_state[i].changed      = 0;
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
    bool got;
    if (latchMask(i)) {
      /* INTFA, INTFB, INTCAPA, INTCAPB, GPIOA in one read. INTFA says which
       * latched bits changed since the last read; reading GPIOA clears it. */
      uint8_t r[5];
      got = regReadN(expanders[i].addr, REG_INTFA, r, 5);
      if (got) { exp_state[i].changed = (uint8_t)(r[0] & latchMask(i)); v = r[4]; }
      else     exp_state[i].changed = 0;   // not last poll's change again
    } else {
      got = regRead(expanders[i].addr, REG_GPIOA, v);
    }
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

/* control.md 6.4 (Rev 19). The next present expander, in turn: read back its
 * directions and Port A polarity, and if a reset has put them back to the
 * power-on defaults, configure it again and mark its relays to be rewritten
 * from the shadow, which still holds what was commanded. */
static uint8_t verify_next = 0;

int8_t expanderVerifyNext() {
  for (uint8_t n = 0; n < N_EXPANDERS; ++n) {
    const uint8_t i = (uint8_t)((verify_next + n) % N_EXPANDERS);
    if (!expanderConfigured(i) || !exp_state[i].present) continue;
    verify_next = (uint8_t)(i + 1);

    const uint8_t a = expanders[i].addr;
    uint8_t iodira = 0, iodirb = 0, ipola = 0;
    const bool got = regRead(a, REG_IODIRA, iodira) && regRead(a, REG_IODIRB, iodirb) &&
                     regRead(a, REG_IPOLA, ipola);
    noteResult(i, got);
    if (!got || (iodira == 0xFF && iodirb == 0x00 && ipola == 0xFF)) return -1;

    const uint8_t keep = exp_state[i].relay_shadow;
    const bool configured = configureOne(i); // writes OLATB 0 on the way
    noteResult(i, configured);
    Serial.printf("I2C: %s at 0x%02X lost its configuration (IODIRA %02X IODIRB %02X "
                  "IPOLA %02X) - reset? %s\n",
                  expanders[i].label, a, iodira, iodirb, ipola,
                  configured ? "configured again, relays restored"
                             : "would not configure again");
    exp_state[i].relay_shadow = keep;
    exp_state[i].relay_dirty  = true;        // expanderFlushRelays() puts them back
    return (int8_t)i;
  }
  return -1;
}

bool expanderAnyPresent() {
  for (uint8_t i = 0; i < N_EXPANDERS; ++i)
    if (expanderConfigured(i) && exp_state[i].present) return true;
  return false;
}

/* control.md 6.2 (Rev 20): one absent expander per call, in turn. A probe of an
 * address nobody answers is the slowest transaction there is, and probing every
 * missing board at once held the 200Hz loop for over 100ms each second - long
 * enough to swallow dial pulses and ring transitions on the boards that are
 * there. */
static uint8_t rescan_next = 0;

bool expanderRescanAbsent() {
  for (uint8_t n = 0; n < N_EXPANDERS; ++n) {
    const uint8_t i = (uint8_t)((rescan_next + n) % N_EXPANDERS);
    if (!expanderConfigured(i) || exp_state[i].present) continue;
    rescan_next = (uint8_t)(i + 1);

    if (probe(expanders[i].addr)) {
      /* It answered. Configure it from scratch - it has been away, and
       * whatever reset it had is not one this firmware watched - and start its
       * relay shadow from the released state configureOne() just wrote. */
      exp_state[i].relay_shadow = 0;
      exp_state[i].relay_dirty  = false;
      exp_state[i].inputs       = 0;
      exp_state[i].changed      = 0;
      if (configureOne(i)) {
        exp_state[i].present  = true;
        consecutive_errors[i] = 0;
        Serial.printf("I2C: %s at 0x%02X is back - configured, in service\n",
                      expanders[i].label, expanders[i].addr);
      } else {
        Serial.printf("I2C: %s at 0x%02X answered but would not configure\n",
                      expanders[i].label, expanders[i].addr);
      }
    }
    break;                                   // one probe a call
  }

  bool all_present = true;
  for (uint8_t i = 0; i < N_EXPANDERS; ++i)
    if (expanderConfigured(i) && !exp_state[i].present) all_present = false;
  bus_fault = !all_present;
  return all_present;
}

bool expanderRecover(bool quiet) {
  if (!quiet) Serial.println("I2C: recovering - /RESET, rescan, reconfigure");
  expanderResetPulse();
  const bool ok = expanderScanAndConfigure(quiet);
  if (!ok && !quiet)
    Serial.println("I2C: recovery incomplete - an expander is still absent; "
                   "retrying once a second");
  return ok;
}
