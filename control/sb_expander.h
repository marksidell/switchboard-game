/* =============================================================================
 * sb_expander.h - MCP23017 driver, scan, poll and relay writes
 *
 * Written against the registers rather than over a general-purpose library, for
 * three reasons that are specific to this design:
 *
 *   control.md 6.1 asks for IPOL set on Port A so a read returns 1 for ring or
 *   seizure present. The Adafruit MCP23017 library defines the register but
 *   exposes no way to write it.
 *
 *   control.md 10 requires a NAK or a read-back mismatch to trigger /RESET and a
 *   rescan. A driver whose read returns 0 on bus failure cannot distinguish that
 *   from eight idle inputs, so the fault would present as every circuit going
 *   quiet - the one failure mode that looks exactly like normal.
 *
 *   The poll reads whole ports at 200Hz. Per-pin digitalRead() would be eight
 *   transactions where one will do.
 *
 * The whole driver is about a hundred lines, which is less than the cost of
 * working around a library that does not fit.
 * ========================================================================== */

#pragma once

#include <Arduino.h>
#include "sb_table.h"

/* Pulse /RESET and wait for the expanders to settle (control.md 6.2). Drops
 * every relay on the chain: IODIR returns to 0xFF and R_pd holds the drivers
 * off. The caller must have inhibited ring first - never assert /RESET while
 * ring is applied (control.md 6.2, 8.5). */
void expanderResetPulse();

/* Scan the configured addresses and configure every device that answers.
 * Returns true only if every configured expander is present, which is the
 * arming gate of control.md 4.2 step 8. Logs each device that does not
 * respond, unless `quiet`, which the repeated retries of a board that is out
 * use so that one unplugged cable does not fill the console at one block a
 * second. */
bool expanderScanAndConfigure(bool quiet = false);

/* Read Port A of every present expander into exp_state[].inputs, IPOL having
 * already made 1 mean present. Returns false if any read failed. */
bool expanderPollInputs();

/* Write Port B to every expander whose shadow is dirty, then read it back and
 * compare. Returns false on a NAK or a mismatch. */
bool expanderFlushRelays();

/* Clear every relay shadow and write it out now, ignoring the dirty flags.
 * This is the failsafe path of control.md 10 and must not depend on anything
 * having gone right. */
void expanderReleaseAllRelays();

/* True once consecutive bus errors have crossed the threshold, and while any
 * configured expander is absent. Cleared only by a scan in which every
 * configured expander answered and configured.
 *
 * It stays set deliberately. A device marked absent is skipped by
 * expanderPollInputs() and expanderFlushRelays(), so no further error can be
 * counted against it and nothing on the bus would ever raise the fault a
 * second time. Holding it is what makes the caller's retry happen at all. */
bool expanderBusFault();

/* The control.md 10 recovery: /RESET, rescan, reconfigure. The caller inhibits
 * ring first, and rate-limits the retries. Returns true if the bus came back. */
bool expanderRecover(bool quiet = false);
