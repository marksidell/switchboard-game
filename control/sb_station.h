/* =============================================================================
 * sb_station.h - station circuits: ring detection and the off-hook relay
 *
 * control.md 7. A station reports ring arriving and is commanded off-hook. It
 * has no ring command and no seizure; that asymmetry with the trunks is
 * deliberate (mqtt.md 4) and is why the two are separate modules over a shared
 * table.
 * ========================================================================== */

#pragma once

#include <Arduino.h>
#include "sb_table.h"

void stationInit();

/* Runs once per 200Hz poll, after expanderPollInputs(). Debounces the 40Hz
 * detector pulse train and publishes `ring` on change only; on station 24 also
 * `lifted`, the telephone's own hook (control.md 7.4). */
void stationPoll(uint32_t now_ms);

/* From sbgame/station/<n>/hook/set. Writes OFFHOOK_n and echoes `hook`.
 * A command for a circuit whose expander was absent is logged and dropped
 * (control.md 9.4). */
void stationSetHook(uint8_t n, bool on);

/* From sbgame/station/<n>/dial/set (control.md 7.3): pulse the
 * off-hook relay for each digit, timed in stationPoll(), and echo the digits
 * still to finish on `dial`. Dropped unless the station is off-hook; an empty
 * payload stops dialling. */
void stationDial(uint8_t n, const char* digits);

/* Failsafe (control.md 10): drop every off-hook relay. Does not publish - the
 * caller decides whether the host is still listening. */
void stationReleaseAll();

/* Republish `ring`, `hook` and `dial` - `lifted` in place of `dial` on station
 * 24 - for station row i (0-21 for stations 1-22, 22 for 24), ignoring
 * change detection; nothing if its expander is absent. Two QoS 1 publishes,
 * each blocking until its PUBACK, so it is called for one circuit per poll tick
 * by the spread republish in sb_net.cpp and never in a loop over every station
 * (control.md 9.2). */
void stationPublishOne(uint8_t i);
