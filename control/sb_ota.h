/* =============================================================================
 * sb_ota.h - network firmware update
 *
 * control.md 2.1. Built only when secrets.h defines OTA_PASSWORD_SHA256; off
 * without one.
 * ========================================================================== */

#pragma once

#include <Arduino.h>

/* Starts the listener once Ethernet has an address, then services it. From
 * loop(). An update runs inside this call, for seconds. */
void otaService();

/* The listener has started, or OTA is built off. */
bool otaListening();
