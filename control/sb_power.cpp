/* =============================================================================
 * sb_power.cpp
 * ========================================================================== */

#include "sb_power.h"
#include "sb_config.h"
#include "sb_net.h"

static bool     cutting        = false;
static uint32_t cut_started_ms = 0;

void powerCutInit() {
  /* Claimed here, in setup(), and not before: GPIO15 is a strapping pin (MTDO).
   * Until now the Olimex's 10k pull-up against the driver's 1k and 470R holds
   * it near 0.4V, and the driver's base near 0.13V, so the relay stays
   * released through a reset (generator 7.8). */
  pinMode(PIN_POWER_CUT, OUTPUT);
  digitalWrite(PIN_POWER_CUT, LOW);
}

void powerCutPublish() {
  netPublishCtl("power_cut", cutting ? "on" : "off", /*retained=*/true, /*qos=*/1);
}

static void endCut(const char* why) {
  digitalWrite(PIN_POWER_CUT, LOW);
  cutting = false;
  Serial.printf("power cut: ended - %s\n", why);
  powerCutPublish();
}

void powerCutSet(bool on) {
  if (!on) {
    if (cutting) endCut("off commanded");
    else         powerCutPublish();      // echoed, as every command is (9.4)
    return;
  }
  /* A pulse, not a level: a duplicate is not a reason to stretch it (5.4). */
  if (cutting) {
    Serial.println("power cut: on during a cut - ignored");
    return;
  }
  digitalWrite(PIN_POWER_CUT, HIGH);
  cutting = true;
  cut_started_ms = millis();
  Serial.printf("power cut: switchboard off for %lums\n", (unsigned long)POWER_CUT_MS);
  powerCutPublish();
}

void powerCutService(uint32_t now_ms) {
  /* Signed, as netGameAlive() is (9.3, Rev 21): now_ms is read at the top of
   * the pass and the cut may have started later in it. */
  if (cutting && (int32_t)(now_ms - cut_started_ms) >= (int32_t)POWER_CUT_MS)
    endCut("time up");
}

void powerCutRelease(const char* why) {
  if (cutting) endCut(why);
}
