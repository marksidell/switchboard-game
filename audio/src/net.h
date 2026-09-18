// net.h - the MQTT thread (audio.md 3, 12).
//
// Runs the libmosquitto network loop. Translates each incoming command into a
// queue entry for the audio thread; for a file command it loads and validates
// the file first and passes the audio thread a pointer it may not free until
// the audio thread has handed it back. Drains the result queues and publishes.
// Publishes the birth message, holds the LWT, and watches game_heartbeat.
#pragma once

#include <mosquitto.h>

#include <string>

#include "ipc.h"

class Net {
public:
    explicit Net(Shared& sh) : sh_(sh) {}
    ~Net();

    bool prepare();
    void run();          // returns when Shared::running goes false
    void shutdown();     // audio.md 13.1: stop everything, say offline, cleanly

private:
    static void cb_connect(struct mosquitto*, void*, int rc);
    static void cb_disconnect(struct mosquitto*, void*, int rc);
    static void cb_message(struct mosquitto*, void*, const struct mosquitto_message*);

    void on_connect(int rc);
    void on_disconnect(int rc);
    void on_message(const char* topic, const char* payload);

    void handle_play(int slot, const char* circuit, const char* payload);
    void handle_tone(int slot, const char* circuit, const char* payload);
    void handle_listen(int slot, const char* circuit, const char* payload);
    void handle_monitor(const char* payload);
    void handle_test(int ch, const char* payload);

    void send(const Command& c);
    void publish(const char* topic, const char* value, bool retain = true);
    void publish_result(const Result& r);
    void publish_initial();
    void drain_results(bool publishing);
    void check_heartbeat(double now);
    void report_counters(double now);

    Shared&           sh_;
    struct mosquitto* m_         = nullptr;
    bool              connected_ = false;
    bool              beat_seen_ = false;
    bool              game_lost_ = false;
    double            last_beat_ = 0.0;
    double            next_try_  = 0.0;
    double            backoff_   = 1.0;
    double            last_count_report_ = 0.0;

    // The state the game does not own, shadowed so a reconnect can republish it
    // truthfully rather than assert the startup defaults (audio.md 12).
    std::string monitor_state_ = "off";
    bool        test_state_[chan::N_PLAY_CH + 1] = { false };
};
