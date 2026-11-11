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
//                      capf_ -> vad_[]         speech detection, per circuit:
//                                              frames -> Listener (vad.h)
//                      capf_ -> ringdet_       ring heard (ringdet.h)
//                      capf_ -> mon_           the loudspeaker feed (monitor.h)
//                                              play_ring -> its row while
//                                              playing back (audio.md 10.7)
//                                              its row -> rec_ring while
//                                              recording (audio.md 10.6)
//                      hop_if_due()            every 2048: ring_ -> Snapshot
//   drain_commands()   cmdq -> prog_[], vad_[], test_on_[], mon_
//   render()           pilots + prog_[] + test + monitor row -> obuf_
//   write()            obuf_ -> ALSA           34 channels, interleaved ints
//
// The order matters in one place: commands are drained after capture is
// processed, so a listen that starts this period measures its noise floor from
// history that does not include this period's command's own effects, and a
// source that starts this period is first heard in this period's render.
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <vector>

#include "aec.h"
#include "alsa.h"
#include "dsp.h"
#include "ipc.h"
#include "monitor.h"
#include "ringdet.h"
#include "tones.h"
#include "vad.h"

class Engine {
public:
    // Engine()                                                       [startup]
    //   Stores references; does no work. prepare() does the work.
    Engine(Shared& sh, AlsaStream& st)
        : sh_(sh), st_(st), tones_(tbl_), ringdet_(sh), mon_(sh) {}
    Engine(const Engine&) = delete;
    Engine& operator=(const Engine&) = delete;

    // prepare()                                                      [startup]
    //   Allocates every buffer and designs every filter. Called before the
    //   thread starts, on purpose: nothing below allocates again.
    bool prepare();

    // run()                                                            [audio]
    //   The thread body. Returns when Shared::running goes false, or on a
    //   stream failure that could not be recovered (which sets
    //   Shared::audio_failed).
    void run();

private:
    // The tests, and monitor_check, drive the real periods with no audio
    // device through this (test/engine_probe.h).
    friend struct EngineProbe;

    // Prog - what one circuit is playing on top of its pilot: nothing, a file
    // or a trunk tone (audio.md 5.2: one at a time). One per slot, in prog_[].
    // The fields for the kind not in use are ignored.
    struct Prog {
        enum class Kind : uint8_t { None, File, Tone } kind = Kind::None;
        AudioBuffer*       buf = nullptr;   // File: owned by this thread while playing
        size_t             pos = 0;         // File: next sample of buf to play
        TrunkTones::State  tone;            // Tone
    };

    // Vad - one circuit's speech detector (audio.md 9.2). One per slot, in
    // vad_[]. It runs all the time, listening or not, because the noise floor
    // a listen starts from is the second of history before the command.
    //
    // Signal path, per sample:  capture -> hp -> lp -> square -> acc
    // Every 480 samples (a 10 ms "frame") acc becomes one level in dBFS, which
    // goes to the Listener (vad.h). The Listener keeps the history and makes
    // every decision; this struct is only the signal processing in front of it.
    struct Vad {
        BiquadState hp, lp[3];              // 300-3400Hz band-pass
        double      acc      = 0.0;         // sum of squares in this frame
        int         nacc     = 0;           // samples in acc so far, 0-479
        bool        src_seen = false;       // a source ran during this frame
        Listener    lis;                    // history, floor, window, phases
    };

    // The echo canceller's reference (audio.md 9.4): the file through the
    // speech detector's band-pass, and the 8 kHz index its last echo sample
    // falls at, after which the canceller stops.
    struct AecRef {
        BiquadState hp, lp[3];
        uint32_t    until = 0;
    };

    // Per-period steps of run(). Each is described where it is defined.
    void process_capture();
    void drain_commands();
    void render();
    void check_output();
    void record_line();
    void hop_if_due();
    void aec_feed(int slot, const float* s, unsigned n);

    // Helpers for drain_commands() and friends.
    void stop_source(int slot, const char* echo);   // echo == nullptr: no publish
    void start_listen(int slot, double seconds);
    void cancel_listen(int slot, const char* echo);
    void post(Topic t, int idx, const char* value) { post_result(sh_, t, idx, value); }
    void post_free(AudioBuffer* b);

    Shared&     sh_;
    AlsaStream& st_;
    SineTable   tbl_;
    TrunkTones  tones_;
    RingDetector ringdet_;
    MonitorChain mon_;

    // Set only by the probe, so prepare() can size its buffers without an
    // open stream.
    bool     detached_ = false;
    unsigned det_period_ = 0, det_nplay_ = 0, det_ncap_ = 0;

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
    float    pilot_amp_ = 0.0f, op_amp_ = 0.0f, test_amp_ = 0.0f;
    uint32_t test_ph_ = 0, test_inc_ = 0;   // 1 kHz test tone, Q32
    std::vector<float> test_row_;           // one period of 1kHz, shared

    Biquad    vad_hp_;                      // 300-3400Hz, shared coefficients
    Biquad    vad_lp_[3];                   // the low-pass's three sections
    VadParams vad_params_;                  // from the options, set in prepare()

    // ---- per-channel state, indexed by slot 1-32 or playback channel 1-34;
    // element 0 unused (channels.h) except as MONITOR_PROG
    Prog   prog_[chan::N_SLOTS + 1];
    Vad    vad_[chan::N_SLOTS + 1];
    std::vector<EchoCanceller> aec_;        // one per slot, on the heap: 3 KB each
    AecRef aec_ref_[chan::N_SLOTS + 1];
    uint64_t g_ = 0;                        // 48 kHz samples before this period
    bool test_on_[chan::N_PLAY_CH + 1] = { false };
    bool mon_out_[chan::N_PLAY_CH + 1] = { false };  // --monitor-ch, by channel

    std::vector<float> line_row_;           // --record-line: output, capture pairs
    unsigned clips_ = 0;                    // clipped samples since last report
    unsigned rec_lost_ = 0;                 // recorded periods lost, ring full
    unsigned play_short_ = 0;               // playback periods short, ring dry
    bool     play_fed_ = false;             // this playback has had samples

    // ---- output self-check (audio.md 11.4), by playback channel 1-34.
    // render() sets out_ceil_ to the most each channel should carry this
    // period, linear full scale, or a negative value for a channel it does not
    // check; check_output() counts the periods that exceed it until the
    // once-a-second hand-over to Shared.
    float    out_ceil_[chan::N_PLAY_CH + 1] = {};
    unsigned out_over_[chan::N_PLAY_CH + 1] = {};
    float    out_pk_[chan::N_PLAY_CH + 1]   = {};
};
