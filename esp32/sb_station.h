/* =============================================================================
 * sb_station.h - station circuits: ring detection and the off-hook relay
 *
 * esp32.md 7. A station reports ring arriving and is commanded off-hook. It has
 * no ring command and no seizure; that asymmetry with the trunks is deliberate
 * (mqtt.md 4) and is why the two are separate modules over a shared table.
 * ========================================================================== */

#pragma once

#include <Arduino.h>
#include "sb_table.h"

void stationInit();

/* Runs once per 200Hz poll, after expanderPollInputs(). Debounces the 40Hz
 * detector pulse train and publishes `ring` on change only. */
void stationPoll(uint32_t now_ms);

/* From sbgame/station/<n>/hook/set. Writes OFFHOOK_n and echoes `hook`.
 * A command for a circuit whose expander was absent is logged and dropped
 * (esp32.md 9.4). */
void stationSetHook(uint8_t n, bool on);

/* Failsafe (esp32.md 10): drop every off-hook relay. Does not publish - the
 * caller decides whether the host is still listening. */
void stationReleaseAll();

/* Republish `ring` and `hook` for every live station, ignoring change
 * detection. Used by the birth sequence, ctl/sync and the 30s timer. */
void stationPublishAll();
