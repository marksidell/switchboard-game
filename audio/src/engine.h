// engine.h - the audio thread (audio.md 3).
//
// Owns the ALSA stream. Runs one period at a time: read a capture period, run
// the per-sample work on it (detector front-end accumulation, speech-detection
// frames, the monitor chain), render one playback period, write it. No
// allocation, no file I/O, no locks, no logging, no MQTT: it communicates only
// through the two queues in Shared.
#pragma once

#include <cstdint>
#include <vector>

#include "alsa.h"
#include "dsp.h"
#include "ipc.h"

class Engine {
public:
    Engine(Shared& sh, AlsaStream& st) : sh_(sh), st_(st) {}

    // Allocates every buffer and designs every filter. Called before the thread
    // starts, on purpose: nothing below allocates again.
    bool prepare();

    // The thread body. Returns when Shared::running goes false, or on a stream
    // failure that could not be recovered (which sets Shared::audio_failed).
    void run();

    // Reported by prepare() for the startup log and for the unit test.
    double monitor_ripple_db() const { return mon_ripple_db_; }
    const std::vector<Biquad>& monitor_lowpass() const { return mon_lp_; }

private:
    // ---- per-circuit programme source (audio.md 5.2: one at a time)
    struct Prog {
        enum class Kind : uint8_t { None, File, Tone } kind = Kind::None;
        AudioBuffer* buf  = nullptr;
        size_t       pos  = 0;
        ToneKind     tone = ToneKind::Off;
        uint32_t     ph   = 0;      // carrier phase, Q32
        uint32_t     mph  = 0;      // modulation phase, Q32
        uint32_t     cad  = 0;      // samples into the cadence period
    };

    // ---- per-circuit speech detector (audio.md 9.2)
    struct Vad {
        BiquadState hp, lp;                 // 300-3400Hz band-pass
        double      acc      = 0.0;         // sum of squares in this frame
        int         nacc     = 0;
        float       hist[100] = { 0 };      // one second of frame levels, dBFS
        int         hist_n   = 0, hist_w = 0;
        bool        active   = false;
        bool        src_seen = false;       // a source ran during this frame
        double      floor_db = -120.0;
        uint32_t    win      = 0;           // last 30 frames, one bit each
        int         win_n    = 0;
        uint64_t    left     = 0;           // samples until timeout
    };

    void drain_commands();
    void process_capture();
    void render();
    void hop_if_due();

    void stop_source(int slot, const char* echo);   // echo == nullptr: no publish
    void start_listen(int slot, double seconds);
    void cancel_listen(int slot, const char* echo);
    void post(Topic t, int idx, const char* value);
    void post_free(AudioBuffer* b);

    Shared&     sh_;
    AlsaStream& st_;
    SineTable   tbl_;

    unsigned period_ = 0, nplay_ = 0, ncap_ = 0;

    std::vector<int32_t> ibuf_, obuf_;      // interleaved, as ALSA wants them
    std::vector<float>   capf_;             // ncap * period, channel-major
    std::vector<float>   ring_;             // N_CAP_CH * FFT_N, per-channel ring
    size_t               ring_w_ = 0;
    unsigned             since_hop_ = 0;
    uint64_t             hop_ = 0;
    int                  snap_next_ = 0;

    uint32_t pilot_n_ = 0;                  // wraps at 4096; the whole oscillator
    float    pilot_amp_ = 0.0f, op_amp_ = 0.0f, tone_amp_ = 0.0f, test_amp_ = 0.0f;
    double   tone_mod_ = 1.0;

    uint32_t test_ph_ = 0, test_inc_ = 0;
    std::vector<float> test_row_;           // one period of 1kHz, shared

    Biquad vad_hp_, vad_lp_;                // 300-3400Hz, shared coefficients

    Prog prog_[chan::N_SLOTS + 1];
    Vad  vad_[chan::N_SLOTS + 1];
    bool test_on_[chan::N_PLAY_CH + 1] = { false };

    // ---- monitor (audio.md 10)
    Biquad                   mon_hp_;
    std::vector<Biquad>      mon_lp_;
    BiquadState              mon_hp_s_;
    std::vector<BiquadState> mon_lp_s_;
    Limiter                  lim_;
    double  mon_ripple_db_ = 0.0;
    double  mon_gain_ = 0.0, mon_target_ = 0.0, mon_step_ = 0.0;
    int     mon_ramp_ = 0;
    std::vector<float> mon_row_;

    unsigned clips_ = 0;
};
