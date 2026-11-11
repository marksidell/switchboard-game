/* =============================================================================
 * sb_failsafe.cpp
 * ========================================================================== */

#include "sb_failsafe.h"
#include "sb_config.h"
#include "sb_table.h"
#include "sb_expander.h"
#include "sb_station.h"
#include "sb_trunk.h"
#include "sb_net.h"
#include "sb_power.h"

/* The scan result (control.md 4.2 step 5). Set by the boot scan and by every
 * I2C recovery, and published on ctl/i2c. It does not gate the generator: ring
 * reaches a circuit only through a trunk board ring relay, which is normally
 * open and held released by R_pd whenever its expander is absent or
 * unconfigured, so a missing expander cannot leave ring applied to anything. */
static bool expanders_all_present = false;

/* I2C recovery bookkeeping. `i2c_retries` is 0 when the bus is believed good,
 * which makes the first attempt after a fault immediate - a connector wiggle
 * that trips the error threshold and then settles is back within 5ms - and
 * every attempt after that once a second. */
static uint32_t last_i2c_retry_ms = 0;
static uint32_t last_i2c_reset_ms = 0;
static uint16_t i2c_retries       = 0;

/* Which configured expanders answered at the last report on ctl/i2c, one bit
 * each. The report goes out whenever this changes, not only when "all present"
 * flips: a trunk board found while the station boards are still out changes
 * which are missing, and the retained message has to say so (mqtt.md 4). */
static uint8_t  scan_reported    = 0;

static bool     game_was_up      = false;

static uint8_t presentMask() {
  uint8_t m = 0;
  for (uint8_t i = 0; i < N_EXPANDERS; ++i)
    if (expanderConfigured(i) && exp_state[i].present) m |= (uint8_t)(1u << i);
  return m;
}

bool     failsafeAllPresent() { return expanders_all_present; }
uint16_t failsafeI2cRetries() { return i2c_retries; }

void releaseAllRelays(const char* why) {
  Serial.printf("FAILSAFE: releasing all relays - %s\n", why);
  stationReleaseAll();
  trunkReleaseAll();
  expanderReleaseAllRelays();     // unconditional, not the dirty-flag path:
                                  // this runs when things are already wrong
  powerCutRelease(why);           // control.md 5.4: powered is its safe state

  /* Echo it if there is anyone to echo to. On the MQTT-loss path there is not,
   * and the retained values stay stale until the reconnect republishes them -
   * which is what ctl/status going to `offline` is for. On the game-heartbeat
   * path the broker is healthy, and a host that recovers must not read a
   * retained hook=on for a relay this just dropped. */
  if (netConnected()) netRequestRepublish();
}

void failsafeBootScan() {
  expanders_all_present = expanderScanAndConfigure();
  scan_reported = presentMask();

  /* The boot scan counts as the first recovery attempt, so a board that is
   * absent from power-up is not rescanned again 5ms later in the first loop
   * pass - the console would print the same block twice. The retry that
   * matters is a second from now, and every second after that. */
  if (!expanders_all_present) {
    i2c_retries = 1;
    last_i2c_retry_ms = last_i2c_reset_ms = millis();   // step 4 was the /RESET
  }
}

void failsafeService(uint32_t now) {
  const bool game_up = netGameAlive(now);

  /* Edge-triggered. A command arriving while the game heartbeat is missing is
   * still acted on (9.4) - the heartbeat's return is the recovery signal and
   * the command is evidence of it - so holding the relays down continuously
   * would fight the specified behaviour. */
  if (game_was_up && !game_up) releaseAllRelays("game heartbeat missed twice");
  if (!game_was_up && game_up) Serial.println("game heartbeat returned");
  game_was_up = game_up;

  /* ---- I2C recovery (control.md 10) --------------------------------------
   * A station or trunk board that is unplugged, or whose cable is disturbed,
   * shows up as consecutive errors on its expander; the third marks it absent
   * and raises the fault. From that moment nothing polls it, so nothing on the
   * bus can report on it again - the retry has to be timed from here, and the
   * fault deliberately stays set until a scan finds every configured expander.
   *
   * Two different faults wear the same flag, and they want opposite treatment,
   * because /RESET is one line to every chip on the bus:
   *
   *   the bus is wedged - nothing answers. /RESET is the remedy, and there are
   *   no working relays for it to disturb. This is the control.md 10 recovery.
   *
   *   a board is out - its expander is absent and the others answer fine.
   *   /RESET would drop the relays of every board that is working, and would
   *   not help the one that is unplugged: it is not on the bus to be reset.
   *   Probing the absent address and configuring it if it answers is all a
   *   returning board needs, and it disturbs nothing.
   *
   * So the fault edge takes the specified recovery once, and the retries after
   * it take whichever of the two the bus is actually showing. A board plugged
   * back in is in service about a second later, with calls on the other boards
   * still up. */
  if (expanderBusFault() &&
      (i2c_retries == 0 || now - last_i2c_retry_ms >= I2C_RETRY_MS)) {
    const bool first = (i2c_retries == 0);
    last_i2c_retry_ms = now;
    if (i2c_retries < 0xFFFF) i2c_retries++;

    /* Nothing answering at all is the bus, not a board - but /RESET is still
     * expensive and still not something a second attempt is going to fix, so
     * it gets a slower knock and the cheap probe runs in between. */
    const bool wedged = !expanderAnyPresent();

    bool ok;
    if (first || (wedged && now - last_i2c_reset_ms >= I2C_RESET_RETRY_MS)) {
      last_i2c_reset_ms = now;
      /* 6.2: inhibit ring before /RESET. A reset mid-cadence would release the
       * ring relay at an arbitrary point in the 20Hz waveform rather than at a
       * cadence boundary. Verbose on the fault edge, quiet on the repeats. */
      trunkInhibitRing();
      expanderFlushRelays();

      ok = expanderRecover(!first);

      /* The reset dropped every relay in hardware, so the firmware's own idea
       * of them has to come back to zero as well or the echoed state would be
       * a lie. Only on this path: the probe below drops nothing. */
      stationReleaseAll();
      trunkReleaseAll();
      powerCutRelease("I2C bus fault");   // 10: every release ends a cut
    } else {
      ok = expanderRescanAbsent();
    }

    if (ok && !first)
      Serial.printf("I2C: every configured expander present again, after %u retries\n",
                    (unsigned)i2c_retries);
    const uint8_t mask = presentMask();
    const bool changed = first || (ok != expanders_all_present) || mask != scan_reported;
    scan_reported = mask;
    expanders_all_present = ok;
    if (ok) i2c_retries = 0;

    /* Only when the answer changed. A board left out for ten minutes must not
     * put six hundred republishes of every state topic through the broker. */
    if (changed && netConnected()) {
      netRequestRepublish();
      netPublishI2cScan(ok);
    }
  }
}
