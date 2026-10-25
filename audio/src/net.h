// net.h - the MQTT thread (audio.md 3, 12).
//
// Runs the libmosquitto network loop. Translates each incoming command into a
// queue entry for the audio thread; for a file command it loads and validates
// the file first and passes the audio thread a pointer it may not free until
// the audio thread has handed it back. Drains the result queues and publishes.
// Publishes the birth message, holds the LWT, and watches game_heartbeat.
//
// This thread is the main thread: main() calls Net::run() once the audio and
// analysis threads are going, and it returns only at shutdown.
//
// libmosquitto is used in its simplest mode: the program calls
// mosquitto_loop() itself, every 20 ms, and libmosquitto calls back into
// cb_connect / cb_disconnect / cb_message from inside that call - so every
// callback runs on this same thread and nothing here needs a lock.
//
// Inbound, a message goes:
//   cb_message -> on_message (parse the topic) -> handle_xxx (check the
//   payload, load a file if it is play/set) -> send (push a Command)
// Outbound, a Result goes:
//   drain_results -> publish_result (topic_for builds the topic) -> publish
#pragma once

#include <mosquitto.h>

#include <string>

#include "ipc.h"
#include "rec.h"

class Net {
public:
    // Net()                                                          [startup]
    explicit Net(Shared& sh) : sh_(sh), rec_(sh), player_(sh) {}

    // ~Net()                                                         [startup]
    //   Destroys the libmosquitto client.
    ~Net();

    // prepare()                                                      [startup]
    //   Creates the client, sets credentials, callbacks and the last will.
    //   Does not connect - run() does, so a missing broker never delays the
    //   audio starting.
    bool prepare();

    // run()                                                             [mqtt]
    //   The main loop: connect or reconnect with backoff, service the
    //   network, publish results, watch the game heartbeat, log counters.
    //   Returns when Shared::quit is set (a signal, or a lost audio stream).
    void run();

    // shutdown()                                                        [mqtt]
    //   audio.md 13.1: stop everything, say offline, cleanly.
    void shutdown();

private:
    // cb_connect / cb_disconnect / cb_message                           [mqtt]
    //   libmosquitto wants plain functions; these forward to the one Net
    //   object's on_connect / on_disconnect / on_message.
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
    void handle_monitor_source(const char* payload);
    void handle_monitor_peer(const char* payload);
    void handle_test(int ch, const char* payload);
    void handle_record(const char* payload);
    void handle_playback(const char* payload);
    void publish_record();
    void publish_recordings();
    void publish_playback();

    void send(const Command& c);
    void publish(const char* topic, const char* value, bool retain = true);
    void publish_result(const Result& r);
    void publish_initial();
    void publish_birth_when_ready(double now);
    void drain_results(bool publishing);
    void check_heartbeat(double now);
    void report_counters(double now);

    Shared&           sh_;
    Recorder          rec_;                  // the loudspeaker recording (audio.md 10.6)
    bool              rec_failed_ = false;   // the last record/set "on" could not open a file
    Player            player_;               // playing a recording back (audio.md 10.7)
    bool              play_missing_ = false; // the last playback/set could not be played
    struct mosquitto* m_         = nullptr;  // the libmosquitto client
    bool              connected_ = false;    // CONNACK received, not since lost
    bool              beat_seen_ = false;    // a game heartbeat has ever arrived
    bool              game_lost_ = false;    // heartbeat lost; failsafe applied
    double            last_beat_ = 0.0;      // monotonic time of the last beat
    double            next_try_  = 0.0;      // earliest time to (re)connect
    double            backoff_   = 1.0;      // seconds; doubles to 30 on failure
    double            last_count_report_ = 0.0;
    int    last_peer_boost_ = -1;      // audio.md 10.8: what the log last said
    bool              birth_pending_ = false;  // state published, online not yet
    unsigned          birth_req_     = 0;      // the publish_req we are waiting on
    double            birth_since_   = 0.0;    // when we started waiting
    bool              birth_warned_  = false;

    // The state the game does not own, shadowed so a reconnect can republish it
    // truthfully rather than assert the startup defaults (audio.md 12).
    std::string monitor_state_ = "off";
    std::string monitor_source_ = "tap";       // audio.md 10.3, echoed retained
    std::string monitor_peer_ = "auto";        // audio.md 10.8, Rev 29, the same
    bool        test_state_[chan::N_PLAY_CH + 1] = { false };
};
