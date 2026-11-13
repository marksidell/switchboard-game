// fbx.h - the monitor's feedback eliminator (audio.md 10.10).
//
// The loudspeaker is in the room with the operator's headset microphone, and
// the monitor plays the line she talks on, so the room can close a loop:
// speaker -> microphone -> line -> monitor -> speaker. With enough gain it
// howls at one frequency. This finds that frequency and puts a narrow notch on
// it, ahead of the limiter, as a stage feedback suppressor does.
//
//   per sample, at 48 kHz:  x -> notch bank (up to NOTCHES peaking cuts) -> y
//   every 4th y, at 12 kHz, into a 512-point window; every 256 of those, a
//   Hann-windowed FFT and the test below.
//
// Howl is one tone standing far above everything else, and holding: a bin at
// least PROMINENCE_DB above the mean of the rest of the band, with nothing
// outside its neighbours (+-4 bins) within ISOLATION_DB of it, louder than MIN_DBFS, on the same bin
// (+-1) for HOLD_FRAMES frames running, about 210 ms. Speech has many harmonics
// close in level; the trunk tones and the ringback cue are two tones; neither
// passes. A new notch starts at FIRST_DB; howl again within a notch's width
// deepens that notch by STEP_DB, to MAX_DB. With the bank full, the notch
// least recently placed or deepened is moved. Notches stay until the program
// restarts: the room's loop does not change with the call.
//
// prepare() allocates and plans; run() allocates nothing, takes no lock and
// does not log. What it did is counted for hand_over().
#pragma once

#include <cstdint>
#include <vector>

#include <fftw3.h>

#include "dsp.h"

class FeedbackEliminator {
public:
    static constexpr int    DECIM        = 4;       // 48 kHz -> 12 kHz for analysis
    static constexpr int    N            = 512;     // analysis window, 42.7 ms
    static constexpr int    HOP          = 256;     // 21.3 ms
    static constexpr int    NOTCHES      = 8;
    static constexpr double LOW_HZ       = 150.0;   // band searched, the monitor's
    static constexpr double HIGH_HZ      = 3600.0;  // high-pass to its passband edge
    static constexpr double MIN_DBFS     = -45.0;   // sine-referenced peak level
    static constexpr double PROMINENCE_DB = 25.0;   // over the rest of the band's mean power
    static constexpr double ISOLATION_DB = 20.0;    // over anything outside +-4 bins
    static constexpr int    HOLD_FRAMES  = 10;      // ~210 ms on one bin
    static constexpr double Q            = 10.0;    // notch width f/Q
    static constexpr double FIRST_DB     = -12.0;
    static constexpr double STEP_DB      = -6.0;
    static constexpr double MAX_DB       = -30.0;

    FeedbackEliminator() = default;
    ~FeedbackEliminator();
    FeedbackEliminator(const FeedbackEliminator&) = delete;
    FeedbackEliminator& operator=(const FeedbackEliminator&) = delete;

    // prepare()                                                      [startup]
    //   Plans the FFT and sizes the buffers. `on` false makes run() a wire.
    //   False if FFTW cannot allocate or plan.
    bool prepare(double fs, bool on);

    // run()                                                            [audio]
    //   One 48 kHz sample through the notches; feeds the analysis.
    double run(double x);

    // What it has done, for the log: notches placed or deepened since the
    // last take, and the most recent one's frequency and depth.
    struct Event { unsigned count; double hz; double db; };
    Event take();

    // For the tests.
    int    active() const;                  // notches in use
    double notch_hz(int i) const { return n_[i].hz; }
    double notch_db(int i) const { return n_[i].db; }

private:
    struct Notch {
        bool        on = false;
        double      hz = 0.0, db = 0.0;
        uint64_t    used = 0;               // frame it was last placed or deepened
        Biquad      c;
        BiquadState s;
    };

    void analyse();
    void place(double hz);

    bool     on_ = false;
    double   fs_ = 48000.0;
    Notch    n_[NOTCHES];

    float*         in_   = nullptr;         // N, windowed copy for the FFT
    fftwf_complex* out_  = nullptr;         // N/2 + 1
    fftwf_plan     plan_ = nullptr;
    std::vector<float> ring_;               // the last N decimated samples
    std::vector<float> win_;                // Hann
    int      ring_w_ = 0;
    int      decim_ = 0;
    int      since_ = 0;                    // decimated samples since the last FFT
    uint64_t frame_ = 0;

    int      cand_bin_ = -1;                // the bin howling, frames running
    int      cand_n_ = 0;

    unsigned events_ = 0;
    double   last_hz_ = 0.0, last_db_ = 0.0;
};
