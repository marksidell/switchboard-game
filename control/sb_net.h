/* =============================================================================
 * sb_net.h - Ethernet and the MQTT client
 *
 * control.md 9 and mqtt.md. This module owns the connection, the subscriptions
 * and the publishing primitives. It does not own policy: the failsafe table of
 * control.md 10 lives in the main loop, which is the only place that can see all
 * of the conditions at once. So this module reports facts - connected, just
 * connected, sync asked for, game heartbeat alive - and the loop decides.
 *
 * Library: MQTT 2.5.3 (Joel Gaehwiler, 256dpi/arduino-mqtt). Chosen over
 * PubSubClient because that cannot publish at QoS 1, which mqtt.md 2 requires
 * for every state and command topic, and over AsyncMqttClient because this one
 * is pumped from loop(): mqtt.md 8.2 notes that a client running its own task
 * keeps the connection alive even when the loop that drives relays has wedged,
 * so the host would see `online` while commands did nothing. Both heartbeats
 * make either choice safe, but the main-loop client fails in the safer
 * direction without relying on them.
 * ========================================================================== */

#pragma once

#include <Arduino.h>
#include "sb_table.h"

void netInit();                       // ETH.begin() and client setup

/* Pump the client and reconnect with backoff. Must be called often; it is what
 * sends the keepalive ping and dispatches incoming commands. */
void netService(uint32_t now_ms);

bool netConnected();

/* Ethernet has a link and an address. The OTA listener (control.md 2.1) waits
 * for this rather than for the broker: an update must be possible with the
 * broker down, since a firmware that cannot reach it is one reason to update. */
bool netHasAddress();

/* True exactly once after each successful connect, so the caller can run the
 * birth sequence of control.md 9.1. */
bool netTakeJustConnected();

/* True exactly once per received ctl/sync. */
bool netTakeSyncRequest();

/* mqtt.md 8.2: two consecutive missed beats - no message for more than 2s -
 * means the game program is gone. False before the first beat has ever arrived,
 * which is correct: relays boot released and must stay that way. */
bool netGameAlive(uint32_t now_ms);

/* control.md 9.3: publish uptime every second FROM THE MAIN LOOP, after the I2C
 * poll, so that it proves the loop that drives relays is running and not merely
 * that the network stack is. */
void netHeartbeat(uint32_t now_ms);

/* Retained, QoS 1, for state (mqtt.md 2). */
void netPublishState(const CircuitMap& c, const char* leaf, const char* payload);

/* Unretained, QoS 0, for the one event topic - trunk/<n>/digit (mqtt.md 7). */
void netPublishEvent(const CircuitMap& c, const char* leaf, const char* payload);

void netPublishCtl(const char* leaf, const char* payload, bool retained, int qos);

/* The expander scan result on sbgame/ctl/i2c (mqtt.md 4): "ok", or "missing:"
 * and the absent addresses. Published at connect, and after every rescan. */
void netPublishI2cScan(bool all_present);
