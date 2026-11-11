/* =============================================================================
 * sb_ota.cpp
 *
 * ArduinoOTA's handle() runs a whole update inside itself, so for those seconds
 * nothing else runs: no poll, no publish, no failsafe. The start callback
 * therefore puts the board where a reset would, before the first byte reaches
 * flash - the waveform stopped and every relay released. The broker notices
 * the lapsed keepalive and publishes the will; the retained state it leaves
 * behind is covered by ctl/status going to `offline`, as on any other loss.
 *
 * A wrong password raises the error callback too, before anything has been
 * stopped. That must change nothing, so the restart is only for errors once an
 * update has actually begun: by then the calls are gone anyway, and a restart
 * is the one state that is known. The old image is still in its partition until
 * the new one verifies, so it is what the board restarts into.
 * ========================================================================== */

#include "sb_ota.h"
#include "sb_net.h"
#include "sb_ring.h"
#include "sb_failsafe.h"
#include "secrets.h"

#ifdef OTA_PASSWORD_SHA256
#include <ArduinoOTA.h>
#endif

static bool ota_started = false;          // listener started, or OTA is off
#ifdef OTA_PASSWORD_SHA256
static bool ota_in_progress = false;      // past the start callback
#endif

static void otaBegin() {
#ifdef OTA_PASSWORD_SHA256
  ArduinoOTA.setHostname(MQTT_CLIENT_ID);
  ArduinoOTA.setPasswordHash(OTA_PASSWORD_SHA256);
  ArduinoOTA.setRebootOnSuccess(true);
  ArduinoOTA.onStart([]() {
    ota_in_progress = true;
    ringStop();
    releaseAllRelays("network firmware update starting");
    Serial.println("OTA: receiving");
  });
  ArduinoOTA.onEnd([]() { Serial.println("OTA: complete, restarting"); });
  ArduinoOTA.onError([](ota_error_t e) {
    Serial.printf("OTA: error %u%s\n", (unsigned)e,
                  ota_in_progress ? ", restarting" : " - nothing changed");
    if (ota_in_progress) {
      delay(100);                    // let the line reach the console
      ESP.restart();
    }
  });
  ArduinoOTA.begin();
  Serial.printf("OTA: listening as %s.local:3232\n", MQTT_CLIENT_ID);
#endif
  ota_started = true;
}

void otaService() {
  if (!ota_started) {
    if (netHasAddress()) otaBegin();
    return;
  }
#ifdef OTA_PASSWORD_SHA256
  ArduinoOTA.handle();
#endif
}

bool otaListening() { return ota_started; }
