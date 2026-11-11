/* =============================================================================
 * 551 Switchboard Simulator - ESP32 controller firmware
 *
 * Target : Olimex ESP32-POE-ISO   (arduino-cli FQBN esp32:esp32:esp32-poe-iso)
 * Implements control.md through the revision in FIRMWARE_SPEC_REV (sb_config.h),
 * the specification for everything in this folder; the running board says
 * which on ctl/firmware and in its banner (control.md 9.1).
 * The firmware has three jobs: ring waveform generation, I2C master to the
 * station and trunk MCP23017 expanders, and MQTT client to the host - and with
 * them the relay failsafes of control.md 10 and dial pulse detection on the
 * trunks. This file is setup() and loop(); the rest is in the sb_*.{h,cpp}
 * files beside it. The channel table in sb_table.cpp is the spine - 23
 * stations and 8 trunks are rows, not code.
 *
 *   sb_ring       the waveform: LEDC, duty tables, step timer, GPIO4 enable
 *   sb_expander   the MCP23017 driver
 *   sb_station    station ring detection, off-hook relay, dialling
 *   sb_trunk      trunk seizure, dial pulses, ring cadence
 *   sb_net        Ethernet, MQTT, the spread republish
 *   sb_power      the switchboard power cut
 *   sb_failsafe   the failsafe table and I2C recovery
 *   sb_ota        network firmware update
 *   sb_diag       loop timing and the console banner
 *
 * References. "control.md N" and "mqtt.md N" are those documents, and a bare
 * section number is control.md. ring_generator.md owns the bridge, the 74HCT04
 * and the waveform arithmetic, which control.md 3 and 5 defer to.
 *
 * The board restarts by itself after an upload. The banner printed in setup()
 * is gone before a serial monitor reattaches, and reattaching resets the board
 * anyway, so press Enter for it: configuration and live state together.
 * ============================================================================= */

#include <Arduino.h>
#include <Wire.h>
#include "driver/gpio.h"

#include "sb_config.h"
#include "sb_table.h"
#include "sb_expander.h"
#include "sb_station.h"
#include "sb_trunk.h"
#include "sb_net.h"
#include "sb_power.h"
#include "sb_ring.h"
#include "sb_failsafe.h"
#include "sb_ota.h"
#include "sb_diag.h"

static uint32_t last_poll_ms         = 0;
static uint32_t last_republish_ms    = 0;
static uint32_t last_config_check_ms = 0;   // 6.4

void setup() {
  ringPinsSafe();                      // SD and both PWM pins LOW, first

  // Expander /RESET idles HIGH (ring_generator.md §4.7). The 1 ms assert and
  // the scan belong with the I2C code; this only stops the line floating.
  pinMode(PIN_EXP_RESET, OUTPUT);
  digitalWrite(PIN_EXP_RESET, HIGH);

  // The switchboard power cut, low: the switchboard powered (control.md 5.4).
  // Claimed here rather than at file scope because GPIO15 is a strapping pin.
  powerCutInit();

  pinMode(PIN_ENBL, INPUT_PULLUP);     // grounding GPIO4 enables the generator

  Serial.begin(115200);
  /* control.md 9.1: with the USB cable unplugged the USB-serial chip is
   * unpowered and the receive line floats; noise on it would read as Enter and
   * print the banner over and over. Hold it idle. */
  gpio_pullup_en(GPIO_NUM_3);
  delay(200);
  Serial.println("Starting");

  /* ---- 4.2 step 3: Ethernet, and the MQTT client configured ---------- */
  netOnLost([]() { releaseAllRelays("MQTT connection lost"); });
  netInit();

  /* ---- 4.2 step 4: expander /RESET ----------------------------------- */
  expanderResetPulse();

  /* ---- 4.2 steps 5 and 6: I2C, scan, configure ----------------------- */
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, I2C_CLOCK_HZ);
  Wire.setTimeOut(I2C_TIMEOUT_MS);             // 6.2: an absent board must not stall the loop
  stationInit();
  trunkInit();
  failsafeBootScan();

  /* ---- 4.2 step 7: MQTT birth, subscribe, publish all state ----------
   * Given a bounded wait rather than blocked on: the generator must run
   * whenever GPIO4 is low (8.5), so a broker that is down must not keep the
   * ring bus dark. If the connection does not come up here, netService() in
   * loop() keeps trying and the birth sequence runs on the connect edge. */
  const uint32_t mqtt_wait_until = millis() + MQTT_BOOT_WAIT_MS;
  while (!netConnected() && millis() < mqtt_wait_until) {
    netService(millis());
    delay(10);
  }
  if (netConnected()) {
    netRequestRepublish();             // spread over the first 31 poll ticks
    netPublishI2cScan(failsafeAllPresent());
    powerCutPublish();
    (void)netTakeJustConnected();      // the birth sequence has just been run
  } else {
    Serial.println("mqtt: not connected at boot; will connect from loop()");
  }

  /* ---- 4.2 step 8: LEDC, both channels at duty 0 ---------------------
   * Duty 0 with SD low is the hardware's own park state, so this is not
   * arming anything. Step 9 is nothing to do, and steps 10 and 11 are the
   * waveform start, which GPIO4 reaches through ringServiceEnable(). */
  ringBegin();

  printBanner();

  ringAdoptEnable();
}

void loop() {
  const uint32_t now = millis();
  const uint32_t pass_start_us = micros();

  TIMED(T_NET, netService(now));   // keepalive ping and inbound commands

  /* A reconnect, a ctl/sync and the 30s timer of 9.2 all mean the same thing:
   * republish every state topic. The timer bounds how long a lost publish can
   * leave a retained value stale at the broker; subscribers react to changes in
   * value, so a repeated value is harmless (mqtt.md 8.3). */
  const bool reconnected = netTakeJustConnected();
  const bool sync_asked  = netTakeSyncRequest();
  if (netConnected() &&
      (reconnected || sync_asked || (now - last_republish_ms >= STATE_REPUBLISH_MS))) {
    last_republish_ms = now;
    netRequestRepublish();           // spread, one circuit per poll tick (9.2)
    if (reconnected) TIMED(T_I2C_PUB, netPublishI2cScan(failsafeAllPresent()));
    if (reconnected) powerCutPublish();
  }

  /* ---- the 200Hz sample stream (6.3) --------------------------------
   * Everything in 7 and 8 runs from here. Nothing samples independently. */
  if (now - last_poll_ms >= POLL_PERIOD_MS) {
    if (last_poll_ms != 0) diagPollGap(now, now - last_poll_ms);
    last_poll_ms = now;

    /* 6.4: one expander's configuration a second, before the poll, so a chip
     * that has reset is set right before its inputs are read. */
    if (now - last_config_check_ms >= CONFIG_CHECK_MS) {
      last_config_check_ms = now;
      TIMED(T_VERIFY, expanderVerifyNext());
    }

    TIMED(T_INPUTS, expanderPollInputs());
    /* The samples are timed from when they were read, not from the top of
     * the pass: netService() above can hold the pass for a few hundred ms
     * waiting on the broker, and a change stamped with `now` would look that
     * much older than it was (6.3). */
    const uint32_t sampled = millis();
    TIMED(T_STATION, stationPoll(sampled));
    TIMED(T_TRUNK, trunkPoll(sampled));
    TIMED(T_FLUSH, expanderFlushRelays());

    /* 9.3: after the poll and from this loop - never from a timer or the
     * network task - so the beat proves the loop that drives relays is running
     * and not merely that the network stack is alive. */
    TIMED(T_BEAT, netHeartbeat(now));

    TIMED(T_FAILSAFE, failsafeService(now));

    TIMED(T_REPUB, netRepublishStep()); // at most one circuit's state per tick
  }

  TIMED(T_ENABLE, ringServiceEnable());

  powerCutService(now);

  TIMED(T_OTA, otaService());

  diagEndPass(pass_start_us);
  diagServiceConsole(now);

  /* 1ms, so the idle task runs and mqtt.loop() is still called five times per
   * 5ms poll. The poll interval is compared against millis() rather than being
   * driven by this delay, so the work above does not accumulate into drift. */
  delay(1);
}
