// net.cpp - the MQTT thread. See net.h for how a message flows through it.
// Every function here runs on the MQTT thread (which is main()'s thread),
// except prepare(), which runs at startup.

#include "net.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

#include "util.h"
#include "wav.h"

static const char* PREFIX = "sbgame/";

// The one Net object, for the libmosquitto callbacks to find. Set in
// prepare().
static Net* g_net = nullptr;

// topic_for()                                                           [mqtt]
//   The full topic string for a Result's (topic, idx): (Peer, 26) is
//   "sbgame/trunk/2/peer", (Test, 33) is "sbgame/audio/test/33". Returns
//   false for FreeBuf and for a slot with no circuit.
//
//   mqtt.md 3: a circuit id prefixed with "sbgame/" is that circuit's topic
//   root, which is the whole reason the id format is what it is. Built in one
//   place so the publisher and the subscriber never drift apart.
static bool topic_for(Topic t, int idx, char* out, size_t n)
{
    char id[24];
    if (t == Topic::Play && idx == chan::TAP_CH) {        // audio.md 7.4, Rev 10
        std::snprintf(out, n, "%saudio/tap/play", PREFIX);
        return true;
    }
    if (t == Topic::Play && idx == chan::MONITOR_PROG) {  // audio.md 10.4, Rev 11
        std::snprintf(out, n, "%saudio/monitor/play", PREFIX);
        return true;
    }
    switch (t) {
    case Topic::Play:
    case Topic::Tone:
    case Topic::Listen:
    case Topic::Peer:
    case Topic::Op: {
        chan::circuit_id(idx, id, sizeof id);
        if (!id[0]) return false;
        const char* leaf = (t == Topic::Play)   ? "play"
                         : (t == Topic::Tone)   ? "tone"
                         : (t == Topic::Listen) ? "listen"
                         : (t == Topic::Peer)   ? "peer" : "op";
        std::snprintf(out, n, "%s%s/%s", PREFIX, id, leaf);
        return true;
    }
    case Topic::Monitor: std::snprintf(out, n, "%saudio/monitor", PREFIX); return true;
    case Topic::MonitorSrc:
        std::snprintf(out, n, "%saudio/monitor/source", PREFIX); return true;
    case Topic::MonitorPeer:
        std::snprintf(out, n, "%saudio/monitor/peer", PREFIX); return true;
    case Topic::OpTone:  std::snprintf(out, n, "%saudio/optone",  PREFIX); return true;
    case Topic::Test:    std::snprintf(out, n, "%saudio/test/%d", PREFIX, idx); return true;
    case Topic::FreeBuf: return false;
    }
    return false;
}

// ~Net()                                                             [startup]
Net::~Net()
{
    if (m_) { mosquitto_destroy(m_); m_ = nullptr; }
    mosquitto_lib_cleanup();
}

// prepare()                                                          [startup]
//   See net.h. Also sets monitor_state_ to what the monitor will start as,
//   so the first publish_initial() reports it correctly.
bool Net::prepare()
{
    rec_.prepare();
    g_net = this;
    mosquitto_lib_init();

    // Clean session on every client (mqtt.md 2): a persistent session would
    // queue commands during an outage and replay a burst of stale ones at
    // reconnect. The birth-and-sync handshake recovers state without the replay.
    m_ = mosquitto_new(sh_.opt.client_id.c_str(), true, nullptr);
    if (!m_) { log_line("mqtt: mosquitto_new failed"); return false; }

    if (!sh_.opt.user.empty())
        mosquitto_username_pw_set(m_, sh_.opt.user.c_str(),
                                  sh_.opt.pass.empty() ? nullptr : sh_.opt.pass.c_str());

    mosquitto_connect_callback_set(m_, cb_connect);
    mosquitto_disconnect_callback_set(m_, cb_disconnect);
    mosquitto_message_callback_set(m_, cb_message);

    // The will is registered before connecting, which is the only time it can
    // be. mqtt.md 8.1: peer and op are retained, so an audio program that has
    // died leaves the last topology it saw on the broker looking current; this
    // topic is how the game knows to treat it as stale.
    char topic[64];
    std::snprintf(topic, sizeof topic, "%sctl/audio_status", PREFIX);
    mosquitto_will_set(m_, topic, 7, "offline", 1, true);

    // audio.md 10.3, 12: monitor/source is published with the rest of the
    // state before birth, and --monitor-src is what it says at start.
    {
        char b[24];
        if (chan::monitor_source_name(sh_.opt.monitor_src, b, sizeof b)) monitor_source_ = b;
    }

    monitor_state_ = sh_.opt.monitor_on ? "" : "off";
    if (sh_.opt.monitor_on) {
        char b[32];
        format_db(sh_.opt.monitor_db, b, sizeof b);
        monitor_state_ = b;
    }
    return true;
}

void Net::cb_connect(struct mosquitto*, void*, int rc)    { if (g_net) g_net->on_connect(rc); }
void Net::cb_disconnect(struct mosquitto*, void*, int rc) { if (g_net) g_net->on_disconnect(rc); }
// cb_message()                                                          [mqtt]
//   Copies the payload into a NUL-terminated buffer - MQTT payloads are bytes
//   with a length, not C strings - truncating anything over 63 bytes, which
//   no valid command approaches.
void Net::cb_message(struct mosquitto*, void*, const struct mosquitto_message* msg)
{
    if (!g_net || !msg) return;
    char payload[64];
    const int n = std::min(msg->payloadlen, (int)sizeof payload - 1);
    if (n > 0) std::memcpy(payload, msg->payload, (size_t)n);
    payload[n > 0 ? n : 0] = '\0';
    g_net->on_message(msg->topic, payload);
}

// on_connect()                                                          [mqtt]
//   The broker has answered our CONNECT. rc 0 is success: subscribe to the
//   eight command patterns and publish the full initial state followed by
//   "online". Anything else is a refusal (usually credentials): back off.
void Net::on_connect(int rc)
{
    if (rc != 0) {
        // Bad credentials look like this (mqtt.md 9: the broker is not
        // anonymous), and retrying at speed will not fix them.
        log_line("mqtt: connection refused: %s - retry in %.0fs",
                 mosquitto_connack_string(rc), backoff_);
        next_try_ = monotonic_s() + backoff_;
        backoff_  = std::min(backoff_ * 2.0, 30.0);
        return;
    }
    connected_ = true;
    backoff_   = 1.0;
    log_line("mqtt: connected to %s:%d as %s", sh_.opt.broker.c_str(),
             sh_.opt.port, sh_.opt.client_id.c_str());

    // audio.md 12. Every pattern is named; a wildcard over every `set` would
    // deliver the ESP32's hook and ring commands here to be dropped.
    static const char* subs[] = {
        "sbgame/station/+/play/set",   "sbgame/trunk/+/play/set",
        "sbgame/audio/tap/play/set",   "sbgame/audio/monitor/play/set",
        "sbgame/trunk/+/tone/set",
        "sbgame/station/+/listen/set", "sbgame/trunk/+/listen/set",
        "sbgame/audio/monitor/set",    "sbgame/audio/monitor/source/set",
        "sbgame/audio/monitor/peer/set",
        "sbgame/audio/test/+/set",
        "sbgame/audio/record/set",     "sbgame/audio/playback/set",
        "sbgame/ctl/game_heartbeat"
    };
    for (const char* s : subs) mosquitto_subscribe(m_, nullptr, s, 1);

    publish_initial();
}

// on_disconnect()                                                       [mqtt]
//   The connection is gone, deliberately or not. Stops every file, tone and
//   listen - the broker-loss failsafe - and forgets the game heartbeat, since
//   it cannot be seen until reconnected.
void Net::on_disconnect(int rc)
{
    if (!connected_) return;
    connected_ = false;
    log_line("mqtt: disconnected (%s)", rc == 0 ? "requested" : mosquitto_strerror(rc));

    // audio.md 13.2: the same stops as a lost game, applied locally. A crashed
    // broker must not leave ringback on a trunk any more than a crashed game.
    Command c; c.verb = Verb::StopGame;
    send(c);
    game_lost_     = false;
    beat_seen_     = false;
    birth_pending_ = false;         // the next connect starts its own
}

// ---------------------------------------------------------------- inbound

// send()                                                                [mqtt]
//   Pushes a Command to the audio thread. If the queue is full - 255
//   commands unprocessed, which would mean the audio thread has stopped -
//   logs it and frees any file buffer the command carried.
void Net::send(const Command& c)
{
    if (!sh_.cmdq.push(c)) {
        log_line("command queue full - dropped %s for %d", "command", c.idx);
        delete c.buf;
    }
}

// handle_play()                                                         [mqtt]
//   play/set. "stop" (or empty) sends a stop. Anything else is a base
//   filename: load it here, on this thread, and send the loaded buffer - or,
//   if it will not load, send a stop that echoes "missing".
void Net::handle_play(int slot, const char* circuit, const char* payload)
{
    Command c;
    c.verb = Verb::Play;
    c.idx  = (int16_t)slot;

    if (std::strcmp(payload, "stop") == 0 || payload[0] == '\0') {
        log_line("mqtt: %s play/set stop", circuit);
        send(c);
        return;
    }

    AudioBuffer* buf = nullptr;
    double hf_db = 0.0;
    const LoadResult r = load_wav(sh_.opt.wav_dir, payload, sh_.opt.max_file, buf, hf_db);
    if (r != LoadResult::Ok) {
        // "missing" is a diagnostic literal on the state topic, in the same way
        // peer carries "ambiguous" (audio.md 7.4). The command still replaces
        // whatever the channel was playing: otherwise `play` would read
        // "missing" while a file went on playing underneath it.
        log_line("mqtt: %s play/set %s - %s", circuit, payload, load_result_text(r));
        std::snprintf(c.name, sizeof c.name, "missing");
        send(c);
        return;
    }

    log_line("mqtt: %s play/set %s (%.2fs, hf %.1f dBFS)", circuit, payload,
             (double)buf->samples.size() / chan::SAMPLE_RATE, hf_db);
    if (hf_db > -60.0)
        log_line("content: %s has %.1f dBFS above 5.5 kHz; audio.md 5.3 wants it "
                 "below -60 or the detector may read ambiguous", payload, hf_db);

    c.buf = buf;
    std::snprintf(c.name, sizeof c.name, "%s", payload);
    send(c);
}

// handle_tone()                                                         [mqtt]
//   tone/set, trunks only: the payload name to a ToneKind, then a Command.
void Net::handle_tone(int slot, const char* circuit, const char* payload)
{
    ToneKind k;
    if      (std::strcmp(payload, "off")      == 0) k = ToneKind::Off;
    else if (std::strcmp(payload, "dial")     == 0) k = ToneKind::Dial;
    else if (std::strcmp(payload, "ringback") == 0) k = ToneKind::Ringback;
    else if (std::strcmp(payload, "busy")     == 0) k = ToneKind::Busy;
    else if (std::strcmp(payload, "reorder")  == 0) k = ToneKind::Reorder;
    else { log_line("mqtt: %s tone/set %s - unknown tone, dropped", circuit, payload); return; }

    log_line("mqtt: %s tone/set %s", circuit, payload);
    Command c;
    c.verb = Verb::Tone;
    c.idx  = (int16_t)slot;
    c.arg  = (float)(int)k;
    send(c);
}

// handle_listen()                                                       [mqtt]
//   listen/set: the payload is a timeout in seconds, capped at 300; 0 cancels.
void Net::handle_listen(int slot, const char* circuit, const char* payload)
{
    char* end = nullptr;
    double s = std::strtod(payload, &end);
    if (end == payload || !std::isfinite(s) || s < 0.0) {
        log_line("mqtt: %s listen/set %s - not a number of seconds, dropped", circuit, payload);
        return;
    }
    if (s > 300.0) { s = 300.0; }     // capped by the audio program, mqtt.md 7

    log_line("mqtt: %s listen/set %.3f", circuit, s);
    Command c;
    c.verb = Verb::Listen;
    c.idx  = (int16_t)slot;
    c.arg  = (float)s;
    send(c);
}

// handle_monitor()                                                      [mqtt]
//   monitor/set: "off", or a gain in dB clamped to -60..+20.
void Net::handle_monitor(const char* payload)
{
    Command c;
    c.verb = Verb::Monitor;
    if (std::strcmp(payload, "off") == 0) {
        c.on = false;
        log_line("mqtt: monitor/set off");
    } else {
        char* end = nullptr;
        double db = std::strtod(payload, &end);
        if (end == payload || !std::isfinite(db)) {
            log_line("mqtt: monitor/set %s - not a gain, dropped", payload);
            return;
        }
        const double clamped = std::min(20.0, std::max(-60.0, db));
        if (clamped != db)
            log_line("mqtt: monitor/set %s clamped to %g", payload, clamped);
        c.on  = true;
        c.arg = (float)clamped;
        log_line("mqtt: monitor/set %g", clamped);
    }
    send(c);
}

// handle_monitor_source()                                               [mqtt]
//   monitor/source/set: "tap", "station/1".."station/22", "trunk/1".."trunk/8"
//   (audio.md 10.3). Anything else is logged and dropped, and the state topic
//   is left alone - the game is not told its bad payload was accepted.
void Net::handle_monitor_source(const char* payload)
{
    const int ch = chan::monitor_source_channel(payload);
    if (ch == 0) {
        log_line("mqtt: monitor/source/set %s - not a source, dropped", payload);
        return;
    }
    // audio.md Rev 9 1.9: the same refusal as at startup, for the same reason.
    // Logged and dropped with no echo, so the game is not told a source it
    // cannot have is in use.
    if (ch > sh_.ncap) {
        log_line("mqtt: monitor/source/set %s - capture channel %d, device has "
                 "only %d, dropped", payload, ch, sh_.ncap);
        return;
    }
    Command c;
    c.verb = Verb::MonitorSrc;
    c.idx  = (int16_t)ch;
    log_line("mqtt: monitor/source/set %s (capture channel %d)", payload, ch);
    send(c);
}

// handle_monitor_peer()                                                 [mqtt]
//   monitor/peer/set: "auto", or the peer boost fixed at a figure in dB,
//   clamped to 0 - --monitor-peer-max (audio.md 10.8, Rev 29).
void Net::handle_monitor_peer(const char* payload)
{
    Command c;
    c.verb = Verb::MonitorPeer;
    if (std::strcmp(payload, "auto") == 0) {
        c.on = false;
        log_line("mqtt: monitor/peer/set auto");
    } else {
        char* end = nullptr;
        double db = std::strtod(payload, &end);
        if (end == payload || !std::isfinite(db)) {
            log_line("mqtt: monitor/peer/set %s - not auto or a boost, dropped", payload);
            return;
        }
        const double clamped = std::min(sh_.opt.monitor_peer_max_db, std::max(0.0, db));
        if (clamped != db)
            log_line("mqtt: monitor/peer/set %s clamped to %g", payload, clamped);
        c.on  = true;
        c.arg = (float)clamped;
        log_line("mqtt: monitor/peer/set %g", clamped);
    }
    send(c);
}

// handle_test()                                                         [mqtt]
//   audio/test/<ch>/set: "on" or "off" for playback channel ch.
void Net::handle_test(int ch, const char* payload)
{
    const bool on = std::strcmp(payload, "on") == 0;
    if (!on && std::strcmp(payload, "off") != 0) {
        log_line("mqtt: test/%d/set %s - on or off, dropped", ch, payload);
        return;
    }
    log_line("mqtt: test/%d/set %s", ch, payload);
    Command c;
    c.verb = Verb::Test;
    c.idx  = (int16_t)ch;
    c.on   = on;
    send(c);
}

// on_message()                                                          [mqtt]
//   Every inbound message. Works out which command it is from the topic,
//   range-checks the station/trunk/channel number, and dispatches to a
//   handle_xxx(). The game heartbeat is handled inline: it just records the
//   time. Anything unrecognised is logged and dropped.
void Net::on_message(const char* topic, const char* payload)
{
    int n = 0;
    char leaf[32];

    if (std::strcmp(topic, "sbgame/ctl/game_heartbeat") == 0) {
        last_beat_ = monotonic_s();
        if (!beat_seen_) { beat_seen_ = true; log_line("game: heartbeat seen"); }
        if (game_lost_)  { game_lost_ = false; log_line("game: heartbeat returned"); }
        return;
    }

    if (std::sscanf(topic, "sbgame/station/%d/%31s", &n, leaf) == 2) {
        if (!chan::is_station(n)) {
            log_line("mqtt: %s - station out of range 1-%d and %d, dropped", topic,
                     chan::N_STATIONS, chan::PHONE_STATION);
            return;
        }
        char id[24]; chan::circuit_id(chan::station_slot(n), id, sizeof id);
        if      (std::strcmp(leaf, "play/set")   == 0) handle_play(chan::station_slot(n), id, payload);
        else if (std::strcmp(leaf, "listen/set") == 0) handle_listen(chan::station_slot(n), id, payload);
        else if (std::strcmp(leaf, "tone/set")   == 0)
            // Trunks only: dial tone, ringback and busy are what a central
            // office sends toward the switchboard, and a station is the
            // telephone, which sends none of them (audio.md 8.1).
            log_line("mqtt: %s - tone is a trunk command, dropped", topic);
        else log_line("mqtt: unexpected topic %s", topic);
        return;
    }

    if (std::sscanf(topic, "sbgame/trunk/%d/%31s", &n, leaf) == 2) {
        if (n < 1 || n > chan::N_TRUNKS) {
            log_line("mqtt: %s - trunk out of range 1-%d, dropped", topic, chan::N_TRUNKS);
            return;
        }
        char id[24]; chan::circuit_id(chan::trunk_slot(n), id, sizeof id);
        if      (std::strcmp(leaf, "play/set")   == 0) handle_play(chan::trunk_slot(n), id, payload);
        else if (std::strcmp(leaf, "tone/set")   == 0) handle_tone(chan::trunk_slot(n), id, payload);
        else if (std::strcmp(leaf, "listen/set") == 0) handle_listen(chan::trunk_slot(n), id, payload);
        else log_line("mqtt: unexpected topic %s", topic);
        return;
    }

    // audio.md 7.1, Rev 10: a file on the operator tap, for the diagnostics.
    if (std::strcmp(topic, "sbgame/audio/tap/play/set") == 0) {
        handle_play(chan::TAP_CH, "tap", payload); return;
    }
    // audio.md 10.4, Rev 11: a file on the monitor, the tutor's voice.
    if (std::strcmp(topic, "sbgame/audio/monitor/play/set") == 0) {
        handle_play(chan::MONITOR_PROG, "monitor", payload); return;
    }
    if (std::strcmp(topic, "sbgame/audio/monitor/set") == 0) { handle_monitor(payload); return; }
    if (std::strcmp(topic, "sbgame/audio/monitor/source/set") == 0) {
        handle_monitor_source(payload); return;
    }
    if (std::strcmp(topic, "sbgame/audio/monitor/peer/set") == 0) {
        handle_monitor_peer(payload); return;
    }

    if (std::strcmp(topic, "sbgame/audio/record/set") == 0) { handle_record(payload); return; }
    if (std::strcmp(topic, "sbgame/audio/playback/set") == 0) { handle_playback(payload); return; }

    if (std::sscanf(topic, "sbgame/audio/test/%d/set", &n) == 1) {
        if (n < 1 || n > chan::N_PLAY_CH) {
            log_line("mqtt: %s - channel out of range 1-%d, dropped", topic, chan::N_PLAY_CH);
            return;
        }
        handle_test(n, payload);
        return;
    }

    log_line("mqtt: unexpected topic %s", topic);
}

// handle_record()                                                       [mqtt]
//   record/set: "on" or "off" (audio.md 10.6, Rev 22). Unlike every other
//   command this one is carried out on this thread - the file is this
//   thread's, and the audio thread only reads Shared::rec_on - so it is
//   echoed from here once the file is open or closed.
void Net::handle_record(const char* payload)
{
    if (std::strcmp(payload, "on") == 0) {
        log_line("mqtt: record/set on");
        rec_failed_ = rec_.start().empty();
    } else if (std::strcmp(payload, "off") == 0) {
        log_line("mqtt: record/set off");
        rec_.stop(true);
        rec_failed_ = false;
    } else {
        log_line("mqtt: record/set %s - not on or off, dropped", payload);
        return;
    }
    publish_record();
    publish_recordings();
}

// handle_playback()                                                     [mqtt]
//   playback/set: a recording's name, or "stop" (audio.md 10.7, Rev 22).
//   Carried out on this thread, as record/set is, and echoed from here.
void Net::handle_playback(const char* payload)
{
    log_line("mqtt: playback/set %s", payload);
    if (std::strcmp(payload, "stop") == 0) {
        player_.stop();
        play_missing_ = false;
    } else {
        play_missing_ = !player_.start(payload);
    }
    publish_playback();
}

// publish_recordings()                                                  [mqtt]
//   audio/recordings: the ten newest, newest first, "<name> <seconds>" a line.
void Net::publish_recordings()
{
    char topic[64];
    std::snprintf(topic, sizeof topic, "%saudio/recordings", PREFIX);
    publish(topic, rec_.list().c_str());
}

// publish_playback()                                                    [mqtt]
//   audio/playback: the recording playing, "missing", or "" for none.
void Net::publish_playback()
{
    char topic[64];
    std::snprintf(topic, sizeof topic, "%saudio/playback", PREFIX);
    publish(topic, !player_.name().empty() ? player_.name().c_str() : play_missing_ ? "missing" : "");
}

// publish_record()                                                      [mqtt]
//   audio/record: the base name being written, "off", or "failed".
void Net::publish_record()
{
    char topic[64];
    std::snprintf(topic, sizeof topic, "%saudio/record", PREFIX);
    publish(topic, rec_.running() ? rec_.name().c_str() : rec_failed_ ? "failed" : "off");
}

// ---------------------------------------------------------------- outbound

// publish()                                                             [mqtt]
//   Publishes one value, QoS 1, retained by default. Does nothing while
//   disconnected.
void Net::publish(const char* topic, const char* value, bool retain)
{
    if (!connected_) return;
    const int len = value ? (int)std::strlen(value) : 0;
    // An empty payload on a retained topic means "clear": it removes the
    // retained value, so a cold subscriber sees nothing rather than a stale one
    // (mqtt.md 7).
    mosquitto_publish(m_, nullptr, topic, len, len ? (const void*)value : nullptr, 1, retain);
}

// publish_result()                                                      [mqtt]
//   Publishes a Result, and keeps the shadow copies of monitor and test state
//   up to date, and logs detector changes.
void Net::publish_result(const Result& r)
{
    char topic[64];
    if (!topic_for(r.topic, r.idx, topic, sizeof topic)) return;
    publish(topic, r.value);

    switch (r.topic) {
    case Topic::Monitor:    monitor_state_  = r.value; break;
    case Topic::MonitorSrc:
        // audio.md 11.2 lists monitor source changes as their own event. Logged
        // here rather than on receipt because this is where the change actually
        // happened - at the bottom of the ramp - and because the return to the
        // tap on heartbeat loss (13.2) never passes through a command at all.
        if (monitor_source_ != r.value) log_line("monitor: source is now %s", r.value);
        monitor_source_ = r.value;
        break;
    case Topic::MonitorPeer: monitor_peer_ = r.value; break;
    case Topic::Test:
        if (r.idx >= 1 && r.idx <= chan::N_PLAY_CH)
            test_state_[r.idx] = std::strcmp(r.value, "on") == 0;
        break;
    case Topic::Peer: {
        char id[24];
        chan::circuit_id(r.idx, id, sizeof id);
        log_line("detector: %s peer = %s", id, r.value[0] ? r.value : "(idle)");
        break;
    }
    case Topic::OpTone:
        log_line("detector: optone = %s", r.value);
        break;
    default: break;
    }
}

// publish_initial()                                                     [mqtt]
//   On every (re)connect: every circuit's play, listen (and tone, for
//   trunks) empty; monitor and all 34 test channels as they actually are;
//   then ask the analysis thread for a full peer/op/optone publish. "online"
//   is not published here: publish_birth_when_ready() does it once that pass
//   is done, so a subscriber that sees online already has everything else.
void Net::publish_initial()
{
    // audio.md 12: published before the birth message, so that a subscriber
    // that sees audio_status go online already has consistent values.
    char topic[64];
    for (int s = 1; s <= chan::N_SLOTS; ++s) {
        if (!chan::is_circuit_slot(s)) continue;
        const chan::Circuit c = chan::slot_circuit(s);
        if (topic_for(Topic::Play, s, topic, sizeof topic))   publish(topic, "");
        if (topic_for(Topic::Listen, s, topic, sizeof topic)) publish(topic, "");
        if (c.kind == chan::Kind::Trunk &&
            topic_for(Topic::Tone, s, topic, sizeof topic))   publish(topic, "");
    }
    if (topic_for(Topic::Play, chan::TAP_CH, topic, sizeof topic)) publish(topic, "");
    if (topic_for(Topic::Play, chan::MONITOR_PROG, topic, sizeof topic)) publish(topic, "");
    topic_for(Topic::Monitor, 0, topic, sizeof topic);
    publish(topic, monitor_state_.c_str());
    topic_for(Topic::MonitorSrc, 0, topic, sizeof topic);
    publish(topic, monitor_source_.c_str());
    topic_for(Topic::MonitorPeer, 0, topic, sizeof topic);
    publish(topic, monitor_peer_.c_str());
    for (int ch = 1; ch <= chan::N_PLAY_CH; ++ch) {
        topic_for(Topic::Test, ch, topic, sizeof topic);
        publish(topic, test_state_[ch] ? "on" : "off");
    }
    publish_record();
    publish_recordings();
    publish_playback();

    // peer, op and optone come from the analysis thread's next hop, and only
    // when that pass is done does run() publish "online" (audio.md 12).
    birth_req_     = sh_.publish_req.fetch_add(1, std::memory_order_acq_rel) + 1;
    birth_pending_ = true;
    birth_since_   = monotonic_s();
    birth_warned_  = false;
}

// publish_birth_when_ready()                                             [mqtt]
//   Called every pass of run() while a birth is pending. Once the analysis
//   thread reports the forced pass done, drains the result queues one last
//   time - the pass's results were queued before it reported, so this
//   collects any the ordinary drain missed - and only then publishes
//   "online". If no pass arrives within 2 s the audio stream is not
//   producing hops; that is logged once, and online is still withheld,
//   because saying it would claim detector state the program does not have.
void Net::publish_birth_when_ready(double now)
{
    if (!birth_pending_ || !connected_) return;

    if (sh_.publish_done.load(std::memory_order_acquire) != birth_req_) {
        if (!birth_warned_ && now - birth_since_ > 2.0) {
            log_line("mqtt: no detector pass in %.0fs - holding audio_status "
                     "until one arrives", now - birth_since_);
            birth_warned_ = true;
        }
        return;
    }

    drain_results(true);
    char topic[64];
    std::snprintf(topic, sizeof topic, "%sctl/audio_status", PREFIX);
    publish(topic, "online");
    birth_pending_ = false;
    log_line("mqtt: online (detector pass %.0f ms after the state publish)",
             1000.0 * (now - birth_since_));
}

// drain_results()                                                       [mqtt]
//   Empties both result queues. Buffers handed back are freed; everything
//   else is published if `publishing`, or discarded if not (while
//   disconnected).
void Net::drain_results(bool publishing)
{
    Result r;
    for (Spsc<Result, 512>* q : { &sh_.res_audio, &sh_.res_ana }) {
        while (q->pop(r)) {
            if (r.topic == Topic::FreeBuf) { delete r.buf; continue; }
            // While disconnected the state is discarded rather than queued: the
            // game sources were stopped when the connection dropped, so the
            // empty play and tone published on reconnect are true (mqtt.md 8.4).
            // One exception to that discard. audio.md 13.2 returns the monitor
            // to the tap on broker loss, and 12 says the republish on reconnect
            // carries the state as it is - so this topic's value is recorded
            // even while disconnected, or reconnect would announce a source the
            // program stopped using when the connection dropped.
            if (!publishing && r.topic == Topic::MonitorSrc) monitor_source_ = r.value;
            if (!publishing && r.topic == Topic::MonitorPeer) monitor_peer_ = r.value;
            if (publishing) publish_result(r);
        }
    }
}

// check_heartbeat()                                                     [mqtt]
//   If the game has been heard from and has now been silent for more than
//   2 s, applies the failsafe once: stop every file, tone and listen.
void Net::check_heartbeat(double now)
{
    // mqtt.md 8.2 and audio.md 13.2: two consecutive missed beats. The failure
    // it prevents is a crashed game leaving ringback on a trunk indefinitely,
    // which presents to the operator as a hardware fault.
    if (!beat_seen_ || game_lost_) return;
    if (now - last_beat_ <= 2.0) return;

    game_lost_ = true;
    log_line("game: two missed heartbeats - stopping every tone, file and listen");
    Command c; c.verb = Verb::StopGame;
    send(c);
}

// report_counters()                                                     [mqtt]
//   Every ten seconds, reads and zeroes the counters in Shared and logs one
//   line if any of them is non-zero. Silence in the log means all is well.
void Net::report_counters(double now)
{
    // audio.md 10.8, Rev 28: the peer boost, when it or its peer changes by
    // enough to matter. The audio thread writes it once a second.
    const int pb = sh_.peer_boost.load(std::memory_order_relaxed);
    if (pb != last_peer_boost_) {
        const int peer = pb < 0 ? 0 : (pb % 1000) / 10, was = last_peer_boost_ < 0 ? 0 : (last_peer_boost_ % 1000) / 10;
        const int measured = pb < 0 ? 0 : pb % 10, was_m = last_peer_boost_ < 0 ? 0 : last_peer_boost_ % 10;
        const int cdb = pb < 0 ? 0 : pb / 1000, was_cdb = last_peer_boost_ < 0 ? 0 : last_peer_boost_ / 1000;
        if (peer != was || measured != was_m || std::abs(cdb - was_cdb) > 50) {
            if (peer) {
                char id[24];
                chan::circuit_id(peer, id, sizeof id);
                log_line("monitor: peer boost %+.1fdB, peer %s (%s)", cdb / 100.0, id,
                         measured == 2 ? "fixed" : measured ? "measured" : "start");
            }
            last_peer_boost_ = pb;
        }
    }
    if (now - last_count_report_ < 10.0) return;
    last_count_report_ = now;

    const unsigned x = sh_.xruns.exchange(0);
    const unsigned h = sh_.hops_lost.exchange(0);
    const unsigned c = sh_.clips.exchange(0);
    const unsigned l = sh_.limiter_hits.exchange(0);
    const unsigned d = sh_.res_dropped.exchange(0);
    const unsigned g = sh_.gate_hits.exchange(0);
    const unsigned r = sh_.rec_dropped.exchange(0);
    const unsigned p = sh_.play_short.exchange(0);
    if (x || h || c || l || d || g || r || p)
        log_line("counters: xruns %u, hops dropped %u, clipped samples %u, "
                 "limiter %u, gate %u, results dropped %u, recorded periods lost %u, "
                 "playback periods short %u", x, h, c, l, g, d, r, p);

    // The output self-check (audio.md 11.4): one line naming every channel
    // that carried more than it should, with its count of periods and its
    // peak. Nothing logged means every channel was as rendered.
    char line[1024];
    size_t n = 0;
    for (int ch = 1; ch <= chan::N_PLAY_CH; ++ch) {
        const unsigned k   = sh_.out_over[ch].exchange(0);
        const int      cdb = sh_.out_over_cdb[ch].exchange(0);
        if (!k || n >= sizeof line) continue;
        const int w = std::snprintf(line + n, sizeof line - n, " ch%d %u@%.1f",
                                    ch, k, (cdb - 100000) / 100.0);
        if (w > 0) n = std::min(n + (size_t)w, sizeof line - 1);
    }
    if (n) log_line("output check: over ceiling (periods@peak dBFS):%s", line);
}

// ---------------------------------------------------------------- loop

// run()                                                                 [mqtt]
//   One pass every ~20 ms: try to connect if due; mosquitto_loop() (network
//   I/O and callbacks, waiting up to 20 ms for traffic - or, with no
//   connection, a plain 20 ms sleep); publish results; publish "online" if a
//   connect is waiting on it; check the heartbeat; report counters; notice a
//   dead audio stream.
void Net::run()
{
    while (!sh_.quit.load(std::memory_order_relaxed)) {
        const double now = monotonic_s();

        if (!connected_ && now >= next_try_) {
            const int rc = mosquitto_connect(m_, sh_.opt.broker.c_str(), sh_.opt.port, 5);
            if (rc == MOSQ_ERR_SUCCESS) {
                // The socket is open and CONNECT is sent, but the CONNACK has
                // not arrived: connected_ becomes true in the callback, several
                // loop iterations later. Hold off another attempt until then,
                // or the next iteration tears this connection down and opens a
                // new one - and every torn-down connection fires the will, so
                // the broker sees audio_status flicker offline in a tight loop.
                next_try_ = now + 2.0;
            } else {
                // Reconnecting hard against a broker that is down achieves
                // nothing and floods the log.
                log_line("mqtt: connect to %s:%d failed: %s - retry in %.0fs",
                         sh_.opt.broker.c_str(), sh_.opt.port,
                         mosquitto_strerror(rc), backoff_);
                next_try_ = now + backoff_;
                backoff_  = std::min(backoff_ * 2.0, 30.0);
            }
        }

        const int rc = mosquitto_loop(m_, 20, 1);
        if (rc != MOSQ_ERR_SUCCESS && connected_) {
            on_disconnect(rc);
            next_try_ = monotonic_s() + backoff_;
        }
        if (rc != MOSQ_ERR_SUCCESS) {
            // With no connection mosquitto_loop() returns at once rather than
            // waiting in select(), so without this the loop would run flat out
            // between reconnect attempts - a core pegged for up to 30s at a
            // time (audio.md 3, Rev 3 code consequence 1). While connecting
            // or connected it returns SUCCESS and has already waited.
            struct timespec ts = { 0, 20 * 1000 * 1000 };
            nanosleep(&ts, nullptr);
        }

        drain_results(connected_);
        publish_birth_when_ready(now);
        check_heartbeat(now);
        report_counters(now);
        if (rec_.service(now)) { publish_record(); publish_recordings(); }
        if (player_.service()) publish_playback();

        if (sh_.audio_failed.load()) {
            log_line("audio: stream lost and not recoverable - exiting");
            sh_.quit.store(true);
        }
    }
}

// shutdown()                                                            [mqtt]
//   Tells the audio thread to stop everything, gives it 50 ms, publishes the
//   cleared state itself regardless, publishes "offline", and disconnects
//   cleanly so the broker does not also fire the will.
void Net::shutdown()
{
    // audio.md 13.1: stop every programme source and the test tones, clear
    // their state topics, publish offline cleanly so the broker does not fire
    // the will, disconnect. The pilots stop with the stream, and every peer on
    // the broker goes stale at that moment - which is why audio_status exists.
    Command c; c.verb = Verb::StopGame; send(c);
    for (int ch = 1; ch <= chan::N_PLAY_CH; ++ch) {
        if (!test_state_[ch]) continue;
        Command t; t.verb = Verb::Test; t.idx = (int16_t)ch; t.on = false;
        send(t);
    }

    // Give the audio thread a couple of periods to act, then say so ourselves
    // rather than wait on an echo that may never come if it has wedged.
    struct timespec ts = { 0, 50 * 1000 * 1000 };
    nanosleep(&ts, nullptr);
    drain_results(connected_);

    char topic[64];
    for (int s = 1; s <= chan::N_SLOTS; ++s) {
        if (!chan::is_circuit_slot(s)) continue;
        const chan::Circuit cc = chan::slot_circuit(s);
        if (topic_for(Topic::Play, s, topic, sizeof topic))   publish(topic, "");
        if (topic_for(Topic::Listen, s, topic, sizeof topic)) publish(topic, "");
        if (cc.kind == chan::Kind::Trunk &&
            topic_for(Topic::Tone, s, topic, sizeof topic))   publish(topic, "");
    }
    if (topic_for(Topic::Play, chan::TAP_CH, topic, sizeof topic)) publish(topic, "");
    if (topic_for(Topic::Play, chan::MONITOR_PROG, topic, sizeof topic)) publish(topic, "");
    for (int ch = 1; ch <= chan::N_PLAY_CH; ++ch) {
        topic_for(Topic::Test, ch, topic, sizeof topic);
        publish(topic, "off");
    }
    // audio.md 10.6: a recording ends with the program. Its WAV is closed
    // and kept; lame is not started, since the service's stop would kill it.
    rec_.stop(false);
    publish_record();
    player_.stop();
    publish_playback();
    std::snprintf(topic, sizeof topic, "%sctl/audio_status", PREFIX);
    publish(topic, "offline");

    for (int i = 0; i < 20 && connected_; ++i) mosquitto_loop(m_, 10, 1);
    mosquitto_disconnect(m_);
    mosquitto_loop(m_, 10, 1);
}
