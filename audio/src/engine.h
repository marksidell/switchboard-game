// engine.h - the audio thread (audio.md 3).
//
// Owns the ALSA stream. Runs one period at a time: read a capture period, run
// the per-sample work on it (detector front-end accumulation, speech-detection
// frames, the monitor chain), render one playback period, write it. No
// allocation, no file I/O, no locks, no logging, no MQTT: it communicates only
// through the two queues in Shared.
//
// One trip round the loop in run(), every 256 samples (5.3 ms):
//
//   read()             ALSA -> ibuf_           32 channels, interleaved ints
//   convert            ibuf_ -> capf_          floats, one row per channel
//   process_capture()  capf_ -> ring_          last 4096 samples per channel
//                      capf_ -> vad_[]         speech detection, per circuit
//                      capf_ row 24 -> mon_row_  the loudspeaker feed
//                      hop_if_due()            every 2048: ring_ -> Snapshot
//   drain_commands()   cmdq -> prog_[], vad_[], test_on_[], monitor gain
//   render()           pilots + prog_[] + test + mon_row_ -> obuf_
//   write()            obuf_ -> ALSA           34 channels, interleaved ints
//
// The order matters in one place: commands are drained after capture is
// processed, so a listen that starts this period measures its noise floor from
// history that does not include this period's command's own effects, and a
// source that starts this period is first heard in this period's render.
#pragma once

#include <cstdint>
#include <vector>

#include "alsa.h"
#include "dsp.h"
#include "ipc.h"

class Engine {
public:
    // Engine()                                                       [startup]
    //   Stores references; does no work. prepare() does the work.
    Engine(Shared& sh, AlsaStream& st) : sh_(sh), st_(st) {}

    // prepare()                                                      [startup]
    //   Allocates every buffer and designs every filter. Called before the
    //   thread starts, on purpose: nothing below allocates again.
    bool prepare();

    // run()                                                            [audio]
    //   The thread body. Returns when Shared::running goes false, or on a
    //   stream failure that could not be recovered (which sets
    //   Shared::audio_failed).
    void run();

    // monitor_ripple_db() / monitor_lowpass()                            [any]
    //   What prepare() designed, for the startup log and the unit test.
    double monitor_ripple_db() const { return mon_ripple_db_; }
    const std::vector<Biquad>& monitor_lowpass() const { return mon_lp_; }

private:
    // Prog - what one circuit is playing on top of its pilot: nothing, a file
    // or a trunk tone (audio.md 5.2: one at a time). One per slot, in prog_[].
    // The fields for the kind not in use are ignored.
    struct Prog {
        enum class Kind : uint8_t { None, File, Tone } kind = Kind::None;
        // File
        AudioBuffer* buf  = nullptr;    // owned by this thread while playing
        size_t       pos  = 0;          // next sample of buf to play
        // Tone
        ToneKind     tone = ToneKind::Off;
        uint32_t     ph   = 0;      // carrier phase, Q32 (see SineTable)
        uint32_t     mph  = 0;      // modulation phase, Q32
        uint32_t     cad  = 0;      // samples into the cadence period
    };

    // Vad - one circuit's speech detector (audio.md 9.2). One per slot, in
    // vad_[]. It runs all the time, listening or not, because the noise floor
    // a listen starts from is the second of history before the command.
    //
    // Signal path, per sample:  capture -> hp -> lp -> square -> acc
    // Every 480 samples (a 10 ms "frame") acc becomes one level in dBFS, which
    // goes into hist[] and, while listening, is compared to the threshold; the
    // yes/no answer is shifted into win.
    struct Vad {
        BiquadState hp, lp;                 // 300-3400Hz band-pass
        double      acc      = 0.0;         // sum of squares in this frame
        int         nacc     = 0;           // samples in acc so far, 0-479
        float       hist[100] = { 0 };      // one second of frame levels, dBFS
        int         hist_n   = 0;           // how many of hist[] are filled
        int         hist_w   = 0;           // next hist[] slot to write (ring)
        bool        active   = false;       // a listen is in progress
        bool        src_seen = false;       // a source ran during this frame
        double      floor_db = -120.0;      // noise floor while listening
        uint32_t    win      = 0;           // last 30 frames, one bit each;
                                            // bit 0 newest, 1 = above threshold
        int         win_n    = 0;           // frames in win so far, up to 30
        uint64_t    left     = 0;           // samples until timeout
    };

    // Per-period steps of run(). Each is described where it is defined.
    void drain_commands();
    void process_capture();
    void render();
    void hop_if_due();

    // Helpers for drain_commands() and friends.
    void stop_source(int slot, const char* echo);   // echo == nullptr: no publish
    void start_listen(int slot, double seconds);
    void cancel_listen(int slot, const char* echo);
    void post(Topic t, int idx, const char* value);
    void post_free(AudioBuffer* b);

    Shared&     sh_;
    AlsaStream& st_;
    SineTable   tbl_;

    unsigned period_ = 0, nplay_ = 0, ncap_ = 0;    // from AlsaStream

    // ---- buffers, all sized once in prepare()
    std::vector<int32_t> ibuf_, obuf_;      // interleaved, as ALSA wants them
    std::vector<float>   capf_;             // ncap * period, channel-major:
                                            // channel c is capf_[c*period ..]
    std::vector<float>   ring_;             // N_CAP_CH * FFT_N, per-channel ring:
                                            // channel c's last 4096 samples
                                            // at ring_[c*4096 ..], oldest at
                                            // ring_w_
    size_t               ring_w_ = 0;       // next write position, same for
                                            // every channel
    unsigned             since_hop_ = 0;    // samples since the last snapshot
    uint64_t             hop_ = 0;          // snapshots taken so far
    int                  snap_next_ = 0;    // which Shared::snap[] to fill next

    // ---- oscillators
    uint32_t pilot_n_ = 0;                  // wraps at 4096; the whole oscillator
    float    pilot_amp_ = 0.0f, op_amp_ = 0.0f, tone_amp_ = 0.0f, test_amp_ = 0.0f;
    double   tone_mod_ = 1.0;               // trunk tone modulation depth

    uint32_t test_ph_ = 0, test_inc_ = 0;   // 1 kHz test tone, Q32
    std::vector<float> test_row_;           // one period of 1kHz, shared

    Biquad vad_hp_, vad_lp_;                // 300-3400Hz, shared coefficients

    // ---- per-channel state, indexed by slot 1-32 or playback channel 1-34;
    // element 0 unused (channels.h)
    Prog prog_[chan::N_SLOTS + 1];
    Vad  vad_[chan::N_SLOTS + 1];
    bool test_on_[chan::N_PLAY_CH + 1] = { false };

    // ---- monitor (audio.md 10): tap capture -> mon_hp_ -> mon_lp_[0..3]
    // -> gain -> lim_ -> mon_row_ -> playback 33 and 34
    Biquad                   mon_hp_;       // 150 Hz high-pass
    std::vector<Biquad>      mon_lp_;       // elliptic low-pass, 4 sections
    BiquadState              mon_hp_s_;
    std::vector<BiquadState> mon_lp_s_;
    Limiter                  lim_;
    double  mon_ripple_db_ = 0.0;
    double  mon_gain_ = 0.0;                // current gain, linear; 0 = muted
    double  mon_target_ = 0.0;              // where the ramp is heading
    double  mon_step_ = 0.0;                // gain change per sample while ramping
    int     mon_ramp_ = 0;                  // samples of ramp remaining
    std::vector<float> mon_row_;            // this period's monitor samples

    unsigned clips_ = 0;                    // clipped samples since last report
};
