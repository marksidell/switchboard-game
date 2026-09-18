// options.h - command line. audio.md 14: no configuration file, because there
// are few enough options that a systemd unit's ExecStart line holds them, and
// one place is better than two. Every level station 8 gives as a figure is an
// option here and defaults to that figure.
#pragma once

#include <string>

struct Options {
    // ALSA
    // The ALSA id snd-usb-audio gives the Digiface is built from its serial
    // number, not its product name - see options.cpp.
    std::string card    = "USB24306452"; // name, index, or a full "hw:x" string
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

    // Levels, all station 8 figures
    double pilot_db  = -40.0;           // station 8.4
    double op_db     = -18.0;           // station 7.9.3
    double tone_db   = -20.0;           // audio.md 8.3, peak
    double tone_mod  = 1.0;             // modulation depth, 0-1
    double test_db   = -20.0;           // audio.md 11.1
    double margin_db = 20.0;            // station 8.7 MARGIN_DB

    // Monitor
    bool   monitor_on = false;          // default off, audio.md 10.2
    double monitor_db = 0.0;
    double lp_pass    = 3600.0;         // station 8.8
    double lp_stop    = 5600.0;
    double lp_att     = 70.0;

    // Speech detector, audio.md 9.2
    double vad_margin = 10.0;
    double vad_floor  = -50.0;

    // Diagnostics
    std::string dump_circuit;           // "station/5" or "trunk/2"
    double      dump_seconds = 0.0;
    bool        hann = false;           // station 8.2 fallback, see the comment
                                        // in detector.cpp
    bool        no_rt = false;          // skip SCHED_FIFO/mlockall (bench)

    std::string device() const;         // ALSA device string from card
};

// Returns false and prints to stderr if the arguments are unusable. `exit_now`
// is set for --help and --version, which are a success.
bool parse_options(int argc, char** argv, Options& o, bool& exit_now);
