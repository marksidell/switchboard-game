#include "net.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <ctime>

#include "util.h"
#include "wav.h"

static const char* PREFIX = "sbgame/";

static Net* g_net = nullptr;

// mqtt.md 3: a circuit id prefixed with "sbgame/" is that circuit's topic root,
// which is the whole reason the id format is what it is. Built in one place so
// the publisher and the subscriber never drift apart.
static bool topic_for(Topic t, int idx, char* out, size_t n)
{
    char id[24];
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
    case Topic::OpTone:  std::snprintf(out, n, "%saudio/optone",  PREFIX); return true;
    case Topic::Test:    std::snprintf(out, n, "%saudio/test/%d", PREFIX, idx); return true;
    case Topic::FreeBuf: return false;
    }
    return false;
}

Net::~Net()
{
    if (m_) { mosquitto_destroy(m_); m_ = nullptr; }
    mosquitto_lib_cleanup();
}

bool Net::prepare()
{
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
void Net::cb_message(struct mosquitto*, void*, const struct mosquitto_message* msg)
{
    if (!g_net || !msg) return;
    char payload[64];
    const int n = std::min(msg->payloadlen, (int)sizeof payload - 1);
    if (n > 0) std::memcpy(payload, msg->payload, (size_t)n);
    payload[n > 0 ? n : 0] = '\0';
    g_net->on_message(msg->topic, payload);
}

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
        "sbgame/trunk/+/tone/set",
        "sbgame/station/+/listen/set", "sbgame/trunk/+/listen/set",
        "sbgame/audio/monitor/set",    "sbgame/audio/test/+/set",
        "sbgame/ctl/game_heartbeat"
    };
    for (const char* s : subs) mosquitto_subscribe(m_, nullptr, s, 1);

    publish_initial();
}

void Net::on_disconnect(int rc)
{
    if (!connected_) return;
    connected_ = false;
    log_line("mqtt: disconnected (%s)", rc == 0 ? "requested" : mosquitto_strerror(rc));

    // audio.md 13.2: the same stops as a lost game, applied locally. A crashed
    // broker must not leave ringback on a trunk any more than a crashed game.
    Command c; c.verb = Verb::StopGame;
    send(c);
    game_lost_ = false;
    beat_seen_ = false;
}

// ---------------------------------------------------------------- inbound

void Net::send(const Command& c)
{
    if (!sh_.cmdq.push(c)) {
        log_line("command queue full - dropped %s for %d", "command", c.idx);
        delete c.buf;
    }
}

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

void Net::handle_tone(int slot, const char* circuit, const char* payload)
{
    ToneKind k;
    if      (std::strcmp(payload, "off")      == 0) k = ToneKind::Off;
    else if (std::strcmp(payload, "dial")     == 0) k = ToneKind::Dial;
    else if (std::strcmp(payload, "ringback") == 0) k = ToneKind::Ringback;
    else if (std::strcmp(payload, "busy")     == 0) k = ToneKind::Busy;
    else { log_line("mqtt: %s tone/set %s - unknown tone, dropped", circuit, payload); return; }

    log_line("mqtt: %s tone/set %s", circuit, payload);
    Command c;
    c.verb = Verb::Tone;
    c.idx  = (int16_t)slot;
    c.arg  = (float)(int)k;
    send(c);
}

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
        if (n < 1 || n > chan::N_STATIONS) {
            log_line("mqtt: %s - station out of range 1-%d, dropped", topic, chan::N_STATIONS);
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

    if (std::strcmp(topic, "sbgame/audio/monitor/set") == 0) { handle_monitor(payload); return; }

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

// ---------------------------------------------------------------- outbound

void Net::publish(const char* topic, const char* value, bool retain)
{
    if (!connected_) return;
    const int len = value ? (int)std::strlen(value) : 0;
    // An empty payload on a retained topic means "clear": it removes the
    // retained value, so a cold subscriber sees nothing rather than a stale one
    // (mqtt.md 7).
    mosquitto_publish(m_, nullptr, topic, len, len ? (const void*)value : nullptr, 1, retain);
}

void Net::publish_result(const Result& r)
{
    char topic[64];
    if (!topic_for(r.topic, r.idx, topic, sizeof topic)) return;
    publish(topic, r.value);

    switch (r.topic) {
    case Topic::Monitor: monitor_state_ = r.value; break;
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
    topic_for(Topic::Monitor, 0, topic, sizeof topic);
    publish(topic, monitor_state_.c_str());
    for (int ch = 1; ch <= chan::N_PLAY_CH; ++ch) {
        topic_for(Topic::Test, ch, topic, sizeof topic);
        publish(topic, test_state_[ch] ? "on" : "off");
    }

    // peer, op and optone follow from the analysis thread on the next hop.
    sh_.force_publish.store(true);

    std::snprintf(topic, sizeof topic, "%sctl/audio_status", PREFIX);
    publish(topic, "online");
}

void Net::drain_results(bool publishing)
{
    Result r;
    for (Spsc<Result, 512>* q : { &sh_.res_audio, &sh_.res_ana }) {
        while (q->pop(r)) {
            if (r.topic == Topic::FreeBuf) { delete r.buf; continue; }
            // While disconnected the state is discarded rather than queued: the
            // game sources were stopped when the connection dropped, so the
            // empty play and tone published on reconnect are true (mqtt.md 8.4).
            if (publishing) publish_result(r);
        }
    }
}

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

void Net::report_counters(double now)
{
    if (now - last_count_report_ < 10.0) return;
    last_count_report_ = now;

    const unsigned x = sh_.xruns.exchange(0);
    const unsigned h = sh_.hops_lost.exchange(0);
    const unsigned c = sh_.clips.exchange(0);
    const unsigned l = sh_.limiter_hits.exchange(0);
    const unsigned d = sh_.res_dropped.exchange(0);
    if (x || h || c || l || d)
        log_line("counters: xruns %u, hops dropped %u, clipped samples %u, "
                 "limiter %u, results dropped %u", x, h, c, l, d);
}

// ---------------------------------------------------------------- loop

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

        drain_results(connected_);
        check_heartbeat(now);
        report_counters(now);

        if (sh_.audio_failed.load()) {
            log_line("audio: stream lost and not recoverable - exiting");
            sh_.quit.store(true);
        }
    }
}

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
    for (int ch = 1; ch <= chan::N_PLAY_CH; ++ch) {
        topic_for(Topic::Test, ch, topic, sizeof topic);
        publish(topic, "off");
    }
    std::snprintf(topic, sizeof topic, "%sctl/audio_status", PREFIX);
    publish(topic, "offline");

    for (int i = 0; i < 20 && connected_; ++i) mosquitto_loop(m_, 10, 1);
    mosquitto_disconnect(m_);
    mosquitto_loop(m_, 10, 1);
}
