/* =============================================================================
 * sb_trunk.h - trunk circuits: seizure, dial pulses, ring cadence
 *
 * control.md 8. Everything the switchboard does on a trunk arrives on one
 * input, SEIZE_n, because the trunk board has no other supervisory signal.
 * Seizure is a long assertion, release a long release, a dial pulse a short
 * release inside a seizure, and ring applied by mistake a 20Hz alternation.
 * The classifier in 8.1 separates them on interval length, never on a
 * transition count.
 * ========================================================================== */

#pragma once

#include <Arduino.h>
#include "sb_table.h"

void trunkInit();

/* Runs once per 200Hz poll, after expanderPollInputs(). Drives the classifier,
 * the digit counter, the state machine and the ring cadence. */
void trunkPoll(uint32_t now_ms);

/* From sbgame/trunk/<n>/ring/set. Starts or stops the cadence. A request beyond
 * the concurrent-ring cap is queued rather than rung (control.md 8.5). */
void trunkSetRing(uint8_t n, bool on);

/* From sbgame/trunk/<n>/shortring/set (control.md 8.4). "on" rings one
 * burst of SHORT_RING_MS and returns the trunk to IDLE; "off" cancels it. Same
 * phase rules and cap as ring/set. */
void trunkShortRing(uint8_t n, bool on);

/* Failsafe (control.md 10): drop every ring relay, cancel every request and
 * return every ringing trunk to IDLE. */
void trunkReleaseAll();

/* Drop ring relays without discarding state. Called before asserting /RESET,
 * which must never happen while ring is applied (control.md 6.2, 8.5). */
void trunkInhibitRing();

/* Republish seize, ring and fault for trunk row i (0-7, trunk i+1), ignoring
 * change detection; nothing if the trunk board is absent. Three QoS 1
 * publishes - one circuit per poll tick, as for stationPublishOne(). */
void trunkPublishOne(uint8_t i);

/* How many trunks are ringing, and how many are queued behind the cap. For the
 * console banner: the cap is invisible from the MQTT side, because a queued
 * trunk publishes ring="off" exactly like an idle one. */
uint8_t trunkRingingCount();
uint8_t trunkQueuedCount();
