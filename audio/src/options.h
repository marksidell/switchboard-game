// options.h - command line. audio.md 14: no configuration file, because there
// are few enough options that a systemd unit's ExecStart line holds them, and
// one place is better than two. Every level station_circuit.md §8 gives as a figure is an
// option here and defaults to that figure.
//
// Options is filled once by parse_options() in main(), copied into Shared (see
// ipc.h), and from then on only read - by every thread, without locking, which
// is safe precisely because nothing writes it after startup.
#pragma once

#include <string>
#include <vector>

// Options - every setting the program has, with its default. One field per
// command-line option; the comment on each gives the document that sets its
// default. Levels are in dBFS (util.h) unless marked otherwise.
struct Options {
    // ALSA
    // The card id from /proc/asound/cards (audio.md 4). snd-usb-audio builds
    // it from the unit's serial number, so it cannot be a default; without
    // --card, parse_options() takes the one card named Digiface.
    std::string card;                   // id, index, or a full "hw:x" string
    unsigned    period  = 256;          // frames (5.3ms)
    unsigned    periods = 3;            // periods per buffer

    // MQTT
    std::string broker  = "localhost";
    int         port    = 1883;
    std::string user;                   // the broker is not anonymous, mqtt.md 9
    std::string pass;
    std::string pass_file;
    std::string client_id = "sbgame-audio";

    // Content
    std::string wav_dir  = "wav";
    double      max_file = 120.0;       // seconds

    // The loudspeaker recording, audio.md 10.6
    std::string record_dir = "recordings";
    double      record_max = 14400.0;   // seconds; a forgotten recording stops
    // --record-line: up to 8 circuit slots whose output and capture
    // are recorded raw beside each loudspeaker recording, for measuring the
    // echo of their own playback. Empty for none.
    std::vector<int> record_line;

    // Levels, all station_circuit.md §8 figures
    double pilot_db  = -40.0;           // station_circuit.md §8.4
    double op_db     = -18.0;           // station_circuit.md §7.9.3
    double tone_db   = -20.0;           // audio.md 8.3, peak
    double tone_mod  = 1.0;             // modulation depth, 0-1
    double test_db   = -20.0;           // audio.md 11.1
    double margin_db = 20.0;            // station_circuit.md §8.7 MARGIN_DB
    double peer_window_db = 25.0;       // station_circuit.md §8.7 PEER_WINDOW_DB
    double op_window_db   = 20.0;       // station_circuit.md §8.7 OP_WINDOW_DB

    // Monitor
    bool   monitor_on = false;          // default off, audio.md 10.2
    double monitor_db = 0.0;
    // --monitor-ch: the playback channels the monitor is written to
    // (audio.md 10.1, 14). Document channel numbers from {33, 34}, the
    // Digiface's analog pair. Never empty.
    std::vector<int> monitor_ch { 33, 34 };
    // audio.md 10.3, 14. The source at startup, as a capture channel, the tap
    // by default: the one source that is not about a call. The trim is
    // added to the gain only while the source is the tap, because the tap
    // arrives about 15dB below the operator's line (station_circuit.md §7.9.3).
    int    monitor_src = 23;            // chan::TAP_CH
    double monitor_tap_trim_db = 0.0;
    // audio.md 10.4. Gain added to a file on the monitor, the tutor's
    // voice, over the commanded gain, so her level is set against the calls'
    // once on the bench and monitor/set stays one number.
    double monitor_file_trim_db = 0.0;
    double monitor_limit_db     = -3.0;   // audio.md 10.1: the limiter's threshold
    // audio.md 10.5: the line-disturbance gate. Off (0) by default.
    double monitor_gate_db      = 0.0;    // below-50Hz level that shuts it, dBFS
    double monitor_gate_hold    = 0.25;   // seconds it stays shut once that is gone
    // audio.md 10.8: the peer boost. The most the source is raised
    // while the circuit it is patched to plays a file (0: off), and what it
    // is raised by until both paths are measured.
    double monitor_peer_max_db   = 15.0;
    double monitor_peer_start_db = 6.0;
    double lp_pass    = 3600.0;         // station_circuit.md §8.8
    double lp_stop    = 5600.0;
    double lp_att     = 70.0;

    // Speech detector, audio.md 9.2
    double vad_margin     = 10.0;
    double vad_floor      = -50.0;
    double vad_hangover   = 1.5;        // s of quiet that ends speech
    double vad_max_speech = 30.0;       // s of speech waited out before timeout
    // The echo canceller, audio.md 9.4
    bool   aec       = true;
    double aec_delay = 10.0;            // ms before its first tap

    // Diagnostics
    std::string dump_circuit;           // "station/5" or "trunk/2"
    double      dump_seconds = 0.0;
    bool        hann = false;           // station_circuit.md §8.2 fallback, see the comment
                                        // in detector.cpp
    bool        no_rt = false;          // skip SCHED_FIFO/mlockall (bench)

    // device()                                                    [any]
    //   The ALSA device string to open, built from `card`: "USB12345678"
    //   becomes "hw:USB12345678", "1" becomes "hw:1", and anything already
    //   containing a colon is used as given.
    std::string device() const;
};

// sbaudio_version()                                                     [any]
//   The commit the program was built from, "-dirty" if audio/ had changes.
const char* sbaudio_version();

// find_card()                                                           [any]
//   The id of the one card in `cards`, the text of /proc/asound/cards, whose
//   name contains `name`, ignoring case. "" if none does or several do, with
//   `why` saying which.
std::string find_card(const std::string& cards, const char* name, std::string& why);

// parse_options()                                                    [startup]
//   Walks argv, filling `o` from its defaults. Reads the password file if one
//   was given, finds the card if --card was not given, and range-checks the values that
//   would otherwise fail obscurely later (period size, modulation depth,
//   filter edges).
//   Returns false, having printed why to stderr, if the arguments are
//   unusable. `exit_now` is set for --help and --version, which return true:
//   they succeeded, and the caller should simply exit 0.
bool parse_options(int argc, char** argv, Options& o, bool& exit_now);
