/* =============================================================================
 * sb_net.cpp
 * ========================================================================== */

#include <ETH.h>
#include <MQTT.h>

#include "sb_net.h"
#include "sb_power.h"
#include "sb_station.h"
#include "sb_trunk.h"
#include "secrets.h"

/* Topics and payloads are short - the longest is
 * "sbgame/station/24/hook/set" - so the client buffer only has to hold one
 * small message. 512 is generous and costs nothing worth counting. */
static MQTTClient mqtt(512);

static NetworkClient net_client;

static bool     just_connected  = false;
static bool     sync_requested  = false;
static uint32_t last_game_beat  = 0;
static bool     game_beat_seen  = false;
static uint32_t last_attempt_ms = 0;
static uint32_t retry_wait_ms   = 0;      // from last_attempt_ms; 0 = try now
static uint32_t backoff_ms      = MQTT_RECONNECT_MIN_MS;
static uint32_t last_hb_ms      = 0;
static bool     eth_up_logged   = false;

/* Commands received, waiting to be acted on (control.md 9.1, Rev 22). The
 * client calls onMessage from inside mqtt.loop(), and acting there publishes
 * the echo from inside it: the nested QoS 1 publish reads the socket for its
 * PUBACK, takes bytes the outer loop() had already counted as available, and
 * the outer read then waits out its 1s timeout and closes the connection - a
 * stalled loop and every relay released. So onMessage only records the
 * command, and netService acts on it once loop() has returned. */
enum : uint8_t { CMD_HOOK, CMD_DIAL, CMD_RING, CMD_SHORTRING, CMD_POWER_CUT };
struct Command {
  uint8_t kind;
  uint8_t n;
  bool    on;
  char    digits[DIAL_MAX_DIGITS + 1];
};
/* A game stop releases every circuit at once - 30 commands in one read, more
 * with the board test's cleanup - so the queue holds two of those. */
static constexpr uint8_t CMD_QUEUE_LEN = 64;
static Command cmd_queue[CMD_QUEUE_LEN];
static uint8_t cmd_head = 0, cmd_count = 0;

static Command* cmdPush(const char* topic) {
  if (cmd_count == CMD_QUEUE_LEN) {
    Serial.printf("mqtt: command queue full - %s dropped\n", topic);
    return nullptr;
  }
  Command* c = &cmd_queue[(cmd_head + cmd_count++) % CMD_QUEUE_LEN];
  *c = Command{};
  return c;
}

static void runCommands() {
  while (cmd_count) {
    const Command c = cmd_queue[cmd_head];
    cmd_head = (uint8_t)((cmd_head + 1) % CMD_QUEUE_LEN);
    cmd_count--;
    switch (c.kind) {
      case CMD_HOOK: stationSetHook(c.n, c.on);    break;
      case CMD_DIAL: stationDial(c.n, c.digits);   break;
      case CMD_RING: trunkSetRing(c.n, c.on);      break;
      case CMD_SHORTRING: trunkShortRing(c.n, c.on); break;
      case CMD_POWER_CUT: powerCutSet((PowerCmd)c.n); break;
    }
  }
}

/* ---- topic construction -------------------------------------------------
 * mqtt.md 3: a circuit id prefixed with "sbgame/" is that circuit's topic
 * root, which is the whole reason the id format is what it is. Built in one
 * place so the two never drift apart. */
static void circuitTopic(const CircuitMap& c, const char* leaf,
                         char* out, size_t n) {
  char id[16];
  circuitId(c, id, sizeof id);
  snprintf(out, n, "%s%s/%s", TOPIC_PREFIX, id, leaf);
}

static void ctlTopic(const char* leaf, char* out, size_t n) {
  snprintf(out, n, "%sctl/%s", TOPIC_PREFIX, leaf);
}

/* ---- publishing --------------------------------------------------------- */

void netPublishState(const CircuitMap& c, const char* leaf, const char* payload) {
  char topic[64];
  circuitTopic(c, leaf, topic, sizeof topic);
  /* control.md 9.2, Rev 28: a state change that does not reach the broker is
   * logged. Only the 30s republish would otherwise put it right, and on the
   * bench, 2026-10-09, seize changes arrived only with it. */
  if (!mqtt.connected()) {
    Serial.printf("mqtt: %s \"%s\" not sent - not connected\n", topic, payload);
    return;
  }
  if (!mqtt.publish(topic, payload, /*retained=*/true, /*qos=*/1))
    Serial.printf("mqtt: %s \"%s\" publish failed, error %d\n",
                  topic, payload, (int)mqtt.lastError());
}

void netPublishBoolIfChanged(const CircuitMap& c, const char* leaf,
                             bool value, int8_t& cache) {
  const int8_t now = value ? 1 : 0;
  if (cache == now) return;
  cache = now;
  netPublishState(c, leaf, value ? "on" : "off");
}

void netPublishEvent(const CircuitMap& c, const char* leaf, const char* payload) {
  if (!mqtt.connected()) return;
  char topic[64];
  circuitTopic(c, leaf, topic, sizeof topic);
  /* Unretained and QoS 0. A retained digit would replay into a later call, and
   * QoS 1's redelivery on reconnect is exactly how a duplicate would arise -
   * and for a digit a duplicate is as wrong as a loss (mqtt.md 2, 7). */
  mqtt.publish(topic, payload, /*retained=*/false, /*qos=*/0);
}

void netPublishCtl(const char* leaf, const char* payload, bool retained, int qos) {
  if (!mqtt.connected()) return;
  char topic[64];
  ctlTopic(leaf, topic, sizeof topic);
  mqtt.publish(topic, payload, retained, qos);
}

void netPublishI2cScan(bool all_present) {
  if (all_present) { netPublishCtl("i2c", "ok", true, 1); return; }

  char payload[96] = "missing:";
  for (uint8_t i = 0; i < N_EXPANDERS; ++i) {
    if (!expanderConfigured(i) || exp_state[i].present) continue;
    char one[12];
    snprintf(one, sizeof one, " 0x%02X", expanders[i].addr);
    strncat(payload, one, sizeof(payload) - strlen(payload) - 1);
  }
  netPublishCtl("i2c", payload, true, 1);
}

void netHeartbeat(uint32_t now_ms) {
  if (now_ms - last_hb_ms < ESP_HEARTBEAT_MS) return;
  last_hb_ms = now_ms;
  char payload[12];
  snprintf(payload, sizeof payload, "%lu", (unsigned long)(now_ms / 1000));
  netPublishCtl("esp_heartbeat", payload, /*retained=*/false, /*qos=*/1);
}

/* ---- The spread state republish (control.md 9.2) --------------------------
 * A full republish is 93 retained QoS 1 messages, and with this client each
 * QoS 1 publish blocks until its PUBACK arrives. Sent as one burst it would
 * hold the 200Hz loop for 100-300ms - longer than a ringing station's 100ms
 * quiet rule (7.1) and longer than a dial pulse (8.2). Instead every full
 * republish walks the channel table one circuit per poll tick: each tick pays
 * for three round trips, and all 31 circuits are refreshed in 31 ticks, about
 * 155ms.
 *
 * A request that arrives mid-walk restarts it, so every circuit is published
 * after the latest request. While the connection is down the walk pauses; the
 * reconnect restarts it anyway.
 * ------------------------------------------------------------------------- */
static int16_t republish_row = -1;       // next circuits[] row; -1 = idle

void netRequestRepublish() { republish_row = 0; }

void netRepublishStep() {
  if (republish_row < 0 || !netConnected()) return;
  const uint8_t r = (uint8_t)republish_row;
  if (r < N_STATION_ROWS) stationPublishOne(r);
  else                    trunkPublishOne((uint8_t)(r - N_STATION_ROWS));
  republish_row = (r + 1 < N_CIRCUITS) ? (int16_t)(r + 1) : -1;
}

/* ---- incoming ----------------------------------------------------------- */

/* control.md 9.4: a command payload is exactly "on" or "off". Anything else is
 * logged and dropped - not read as "off", which the first firmware did, making
 * a malformed command a silent relay release. Returns false for a payload to
 * drop; `on` is set only when it returns true. */
static bool parseOnOff(const char* topic, const char* p, bool& on) {
  if (strcmp(p, "on") == 0)  { on = true;  return true; }
  if (strcmp(p, "off") == 0) { on = false; return true; }
  Serial.printf("mqtt: %s payload \"%s\" is neither on nor off - dropped\n",
                topic, p);
  return false;
}

/* "station/<n>/<leaf>" or "trunk/<n>/<leaf>", the topic with TOPIC_PREFIX
 * removed: the command it names and the circuit number. False for anything
 * else. n is left wide, so the caller range-checks it before it is narrowed. */
static bool parseCircuitTopic(const char* rest, uint8_t& kind, unsigned long& n) {
  bool station;
  if      (strncmp(rest, "station/", 8) == 0) { station = true;  rest += 8; }
  else if (strncmp(rest, "trunk/", 6) == 0)   { station = false; rest += 6; }
  else return false;

  if (!isdigit((unsigned char)*rest)) return false;
  char* end;
  n = strtoul(rest, &end, 10);
  if (*end != '/') return false;
  const char* leaf = end + 1;

  if (station && strcmp(leaf, "hook/set") == 0)       kind = CMD_HOOK;
  else if (station && strcmp(leaf, "dial/set") == 0)  kind = CMD_DIAL;
  else if (!station && strcmp(leaf, "ring/set") == 0) kind = CMD_RING;
  else if (!station && strcmp(leaf, "shortring/set") == 0) kind = CMD_SHORTRING;
  else return false;
  return true;
}

/* mqtt.md 6 is the whole of the inbound surface: four per-circuit commands -
 * hook/set and dial/set (control.md 7.3, Rev 17) on a station, ring/set and
 * shortring/set (control.md 8.4, Rev 25) on a trunk - and three ctl topics, power_cut/set
 * (control.md 5.4, Rev 31) the third. Parsed rather than dispatched through a table
 * because the circuit number has to come out of the middle. */
static void onMessage(String& topic, String& payload) {
  const char* t = topic.c_str();
  const char* p = payload.c_str();

  const size_t prefix_len = strlen(TOPIC_PREFIX);
  if (strncmp(t, TOPIC_PREFIX, prefix_len) != 0) {
    Serial.printf("mqtt: unexpected topic %s\n", t);
    return;
  }
  const char* rest = t + prefix_len;

  if (strcmp(rest, "ctl/game_heartbeat") == 0) {
    last_game_beat = millis();
    game_beat_seen = true;
    return;
  }
  if (strcmp(rest, "ctl/sync") == 0) {
    sync_requested = true;
    return;
  }
  if (strcmp(rest, "ctl/power_cut/set") == 0) {
    /* "on", "off", or "hold" (control.md 5.4, Rev 32): n carries which. */
    bool on = false;
    Command* c;
    const bool hold = strcmp(p, "hold") == 0;
    if ((hold || parseOnOff(t, p, on)) && (c = cmdPush(t))) {
      c->kind = CMD_POWER_CUT;
      c->n = hold ? POWER_HOLD : on ? POWER_PULSE : POWER_OFF;
    }
    return;
  }

  uint8_t       kind;
  unsigned long n;
  if (!parseCircuitTopic(rest, kind, n)) {
    Serial.printf("mqtt: unexpected topic %s\n", t);
    return;
  }
  /* Checked before Command::n narrows it, or station/280 would be station 24. */
  if (n > 255) {
    Serial.printf("mqtt: %s - circuit %lu out of range, dropped\n", t, n);
    return;
  }

  if (kind == CMD_DIAL) {
    /* control.md 7.3, Rev 17. Too long to copy is too long to dial: an
     * over-long payload is replaced by one stationDial() refuses, with its log. */
    if (Command* c = cmdPush(t)) {
      c->kind = CMD_DIAL; c->n = (uint8_t)n;
      if (strlen(p) <= DIAL_MAX_DIGITS) strcpy(c->digits, p);
      else                              strcpy(c->digits, "x");
    }
    return;
  }

  bool on = false;
  Command* c;
  if (parseOnOff(t, p, on) && (c = cmdPush(t))) {
    c->kind = kind; c->n = (uint8_t)n; c->on = on;
  }
}

/* ---- connection --------------------------------------------------------- */

void netInit() {
  /* control.md 4.2 step 3. The no-argument form resolves to the Olimex PHY
   * parameters through the esp32-poe-iso variant header: LAN8720 at address 0,
   * MDC 23, MDIO 18, power 12, clock on GPIO17. That last one holds only while
   * PSRAM is disabled - with PSRAM on, the variant moves the clock to GPIO0 and
   * I2C SCL off GPIO16, which would collide with control.md 3's pin map. Leave
   * PSRAM off for this board. */
  ETH.begin();

  mqtt.begin(MQTT_BROKER_HOST, MQTT_PORT, net_client);
  mqtt.setKeepAlive(MQTT_KEEPALIVE_S);      // mqtt.md 8.1: 5s, so the broker
  mqtt.setCleanSession(true);               // notices a lost controller promptly
  mqtt.onMessage(onMessage);

  /* The will is registered before connecting, which is the only time it can be:
   * the broker holds it on our behalf and publishes it if we disappear without
   * disconnecting cleanly (mqtt.md 8.1). */
  char status_topic[64];
  ctlTopic("status", status_topic, sizeof status_topic);
  mqtt.setWill(status_topic, "offline", /*retained=*/true, /*qos=*/1);
}

/* control.md 9.1: publish the birth message, subscribe, then publish every state
 * topic once. A clean session forgets subscriptions, so every reconnect repeats
 * all of it. The state publish is left to the caller, which owns the circuits. */
static void onConnected() {
  /* control.md 9.1 (Rev 20): no Nagle. Every QoS 1 publish waits for its PUBACK,
   * and with Nagle on, the small packets met the broker's delayed ACK: about
   * 40ms a message, which held the 200Hz loop for up to 130ms while state was
   * republished. With TCP_NODELAY each round trip is the LAN's, about 1ms. */
  net_client.setNoDelay(true);
  netPublishCtl("status", "online", /*retained=*/true, /*qos=*/1);
  // control.md 9.1, Rev 18: which firmware this is, with the birth message.
  char fw[96];
  snprintf(fw, sizeof fw, "control.md Rev %u, %s, built %s",
           FIRMWARE_SPEC_REV, FIRMWARE_COMMIT, FIRMWARE_BUILT);
  netPublishCtl("firmware", fw, /*retained=*/true, /*qos=*/1);

  char topic[64];
  snprintf(topic, sizeof topic, "%sstation/+/hook/set", TOPIC_PREFIX);
  mqtt.subscribe(topic, 1);
  snprintf(topic, sizeof topic, "%sstation/+/dial/set", TOPIC_PREFIX);
  mqtt.subscribe(topic, 1);
  snprintf(topic, sizeof topic, "%strunk/+/ring/set", TOPIC_PREFIX);
  mqtt.subscribe(topic, 1);
  snprintf(topic, sizeof topic, "%strunk/+/shortring/set", TOPIC_PREFIX);
  mqtt.subscribe(topic, 1);
  ctlTopic("game_heartbeat", topic, sizeof topic); mqtt.subscribe(topic, 1);
  ctlTopic("sync",           topic, sizeof topic); mqtt.subscribe(topic, 1);
  ctlTopic("power_cut/set",  topic, sizeof topic); mqtt.subscribe(topic, 1);

  backoff_ms     = MQTT_RECONNECT_MIN_MS;
  retry_wait_ms  = 0;
  just_connected = true;
  Serial.printf("mqtt: connected to %s as %s\n", MQTT_BROKER_HOST, MQTT_CLIENT_ID);
}

static bool was_connected = false;
static void (*on_lost)() = nullptr;

void netOnLost(void (*fn)()) { on_lost = fn; }

void netService(uint32_t now_ms) {
  mqtt.loop();                       // sends the keepalive and dispatches messages
  runCommands();                     // outside loop(): they publish (Rev 22)

  if (mqtt.connected()) { was_connected = true; return; }

  /* Rev 40: before the connect below, which blocks and may succeed, so a
   * connection back within this pass still releases the relays. */
  if (was_connected) {
    was_connected = false;
    if (on_lost) on_lost();
  }

  /* Nothing to attempt until the PHY has a link and an address. */
  if (!ETH.linkUp()) { eth_up_logged = false; return; }
  if (ETH.localIP() == IPAddress((uint32_t)0)) return;
  if (!eth_up_logged) {
    Serial.print("eth: link up, address ");
    Serial.println(ETH.localIP());
    eth_up_logged = true;
  }

  if (elapsedMs(now_ms, last_attempt_ms) < retry_wait_ms) return;   // wrap-safe

  if (mqtt.connect(MQTT_CLIENT_ID, MQTT_USERNAME, MQTT_PASSWORD)) {
    onConnected();
    return;
  }

  /* Backoff, doubling to a ceiling. Reconnecting hard in a tight loop against a
   * broker that is down achieves nothing and floods the log. */
  last_attempt_ms = now_ms;
  retry_wait_ms   = backoff_ms;
  backoff_ms = (backoff_ms * 2 > MQTT_RECONNECT_MAX_MS) ? MQTT_RECONNECT_MAX_MS
                                                        : backoff_ms * 2;
  Serial.printf("mqtt: connect failed, retry in %lums\n", (unsigned long)retry_wait_ms);
}

bool netConnected() { return mqtt.connected(); }

bool netHasAddress() {
  return ETH.linkUp() && ETH.localIP() != IPAddress((uint32_t)0);
}

bool netTakeJustConnected() {
  const bool v = just_connected;
  just_connected = false;
  return v;
}

bool netTakeSyncRequest() {
  const bool v = sync_requested;
  sync_requested = false;
  return v;
}

bool netGameAlive(uint32_t now_ms) {
  if (!game_beat_seen) return false;
  /* Signed (control.md 9.3, Rev 21). `now_ms` is read at the top of the loop
   * pass and a heartbeat that arrives later in the same pass is stamped after
   * it; unsigned, that small negative age wrapped to four billion, the game
   * read as gone, and every relay was released - each second, intermittently. */
  return (int32_t)(now_ms - last_game_beat) <= (int32_t)GAME_HEARTBEAT_TIMEOUT_MS;
}
