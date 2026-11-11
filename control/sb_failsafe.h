/* =============================================================================
 * sb_failsafe.h - the failsafe table and I2C recovery
 *
 * control.md 10. Every relay is released on any of these, independently and
 * without reference to the host. They are gathered here rather than pushed into
 * the modules that own the relays because this is the only place that sees all
 * of the conditions at once, and a failsafe split across three files is a
 * failsafe nobody can audit.
 *
 * Rows of that table that are elsewhere, each for a reason:
 *   Power-on / reset          the hardware's doing, before any of this runs (4.1)
 *   MQTT connection lost      netService() calls releaseAllRelays() through
 *                             netOnLost(), before it tries to reconnect
 *   Trunk ringing for 30s     per-trunk, in trunkPoll(), beside the cadence it
 *                             interrupts
 *   Network update starting   the OTA start callback, sb_ota.cpp
 * ========================================================================== */

#pragma once

#include <Arduino.h>

/* Release every relay, end any power cut, and republish if the broker is
 * there to hear it. */
void releaseAllRelays(const char* why);

/* control.md 4.2 steps 5 and 6: scan and configure every expander, and set up
 * the recovery bookkeeping for whatever did not answer. */
void failsafeBootScan();

/* The game heartbeat edge and the I2C recovery. Once per poll tick. */
void failsafeService(uint32_t now);

/* The last scan's answer: every configured expander present. Published on
 * ctl/i2c. It does not gate the generator. */
bool failsafeAllPresent();

/* Recovery attempts since the bus fault, for the banner. */
uint16_t failsafeI2cRetries();
