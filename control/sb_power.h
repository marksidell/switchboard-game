/* =============================================================================
 * sb_power.h - the switchboard power cut
 *
 * control.md 5.4, Rev 31. GPIO15 drives a relay in the switchboard's leg of
 * the 24V star (generator 7.8): high, the relay opens its normally closed
 * contact and the switchboard is dark. A trunk rung in holds its lamp and
 * buzzer on the 551's own battery until a cord goes in; this is the only other
 * way to clear it. A pulse, POWER_CUT_MS long, and never a level: powered is
 * the switchboard's safe state, and every failsafe returns to it.
 * ========================================================================== */

#pragma once

#include <Arduino.h>

void powerCutInit();                  // claims GPIO15, low: the switchboard powered

/* From sbgame/ctl/power_cut/set. "on" starts a cut of POWER_CUT_MS, ignored
 * and logged if one is under way; "off" ends one early. Echoed on
 * ctl/power_cut. */
void powerCutSet(bool on);

/* Ends the cut when its time is up. From the main loop. */
void powerCutService(uint32_t now_ms);

/* Every failsafe of control.md 10: power restored at once, echoed if there is
 * anyone to echo to. */
void powerCutRelease(const char* why);

/* ctl/power_cut, retained. With the birth message and on change. */
void powerCutPublish();
