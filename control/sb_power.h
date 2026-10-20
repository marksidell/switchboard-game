/* =============================================================================
 * sb_power.h - the switchboard power cut
 *
 * control.md 5.4, Rev 31. GPIO15 drives a relay in the switchboard's leg of
 * the 24V star (generator 7.8): high, the relay opens its normally closed
 * contact and the switchboard is dark. A trunk rung in holds its lamp and
 * buzzer on the 551's own battery until a cord goes in; a pulse, POWER_CUT_MS
 * long, clears it. Rev 32 adds a held cut, for switching the switchboard off
 * from the page: it lasts until "off" or a failsafe. Powered is the
 * switchboard's safe state, and every failsafe returns to it.
 * ========================================================================== */

#pragma once

#include <Arduino.h>

enum PowerCmd : uint8_t { POWER_OFF, POWER_PULSE, POWER_HOLD };

void powerCutInit();                  // claims GPIO15, low: the switchboard powered

/* From sbgame/ctl/power_cut/set. "on" (POWER_PULSE) starts a cut of
 * POWER_CUT_MS, ignored and logged during any cut; "hold" (POWER_HOLD) cuts
 * until "off", and turns a pulse under way into a hold; "off" (POWER_OFF)
 * ends either. Echoed on ctl/power_cut: "on", "hold" or "off". */
void powerCutSet(PowerCmd cmd);

/* Ends a pulse when its time is up. From the main loop. */
void powerCutService(uint32_t now_ms);

/* Every failsafe of control.md 10: power restored at once, echoed if there is
 * anyone to echo to. */
void powerCutRelease(const char* why);

/* ctl/power_cut, retained. With the birth message and on change. */
void powerCutPublish();
