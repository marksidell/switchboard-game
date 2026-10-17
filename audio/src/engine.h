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
//                      capf_ row 23 -> mon_row_  the loudspeaker feed
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

#include <algorithm>
#include <cstdint>
#include <vector>

#include "alsa.h"
#include "dsp.h"
#include "ipc.h"
#include "vad.h"

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

    // ---- test hooks. sbaudio_test drives a render with no audio device, to
    // check the channel map of audio.md 2: which playback channel carries the
    // monitor, the operator tone, a pilot or silence. Nothing in the program
    // calls these.
    bool prepare_detached(unsigned period, unsigned nplay, unsigned ncap)
    {
        detached_ = true;
        det_period_ = period; det_nplay_ = nplay; det_ncap_ = ncap;
        return prepare();
    }
    void render_for_test()                       { render(); }
    void drain_for_test()                        { drain_commands(); }
    void set_monitor_row_for_test(float v)       { std::fill(mon_row_.begin(), mon_row_.end(), v); }
    void capture_for_test()                      { process_capture(); }
    float* capture_row_for_test(int ch)          { return &capf_[(size_t)(ch - 1) * period_]; }
    const std::vector<float>& monitor_row() const { return mon_row_; }
    const std::vector<int32_t>& playback() const { return obuf_; }
    std::vector<int32_t>& playback_for_test()    { return obuf_; }
    void check_output_for_test()                 { check_output(); }
    unsigned out_over_for_test(int ch) const     { return out_over_[ch]; }

    // monitor_ripple_db() / monitor_lowpass()                            [any]
    //   What prepare() designed, for the startup log and the unit test.
    double monitor_ripple_db() const { return mon_ripple_db_; }
    const std::vector<Biquad>& monitor_lowpass() const { return mon_lp_; }
    double gate_gain() const { return gate_g_; }

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
    // goes to the Listener (vad.h). The Listener keeps the history and makes
    // every decision; this struct is only the signal processing in front of it.
    struct Vad {
        BiquadState hp, lp[3];              // 300-3400Hz band-pass (Rev 18: 6th-order low)
        double      acc      = 0.0;         // sum of squares in this frame
        int         nacc     = 0;           // samples in acc so far, 0-479
        bool        src_seen = false;       // a source ran during this frame
        Listener    lis;                    // history, floor, window, phases
    };

    // Per-period steps of run(). Each is described where it is defined.
    void drain_commands();

    // monitor_target() - the gain the ramp should head for: the commanded gain
    // with the tap trim added while the source is the tap, or 0 when muted.
    double monitor_target(int src_ch) const;
    void   monitor_ramp_to(double target);
    double gate_step(float raw, double y);
    void   monitor_switch_to(int ch);       // at the bottom of the ramp
    void process_capture();
    void render();
    void check_output();
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

    // Set only by prepare_detached(), so prepare() can size its buffers
    // without an open stream.
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
    float    pilot_amp_ = 0.0f, op_amp_ = 0.0f, tone_amp_ = 0.0f, test_amp_ = 0.0f;
    double   tone_mod_ = 1.0;               // trunk tone modulation depth

    uint32_t test_ph_ = 0, test_inc_ = 0;   // 1 kHz test tone, Q32
    std::vector<float> test_row_;           // one period of 1kHz, shared
    std::vector<float> city_;               // one period of ringback, peak 1 (Rev 21)

    Biquad    vad_hp_;                      // 300-3400Hz, shared coefficients
    Biquad    vad_lp_[3];                   // the low-pass's three sections (Rev 18)
    VadParams vad_params_;                  // from the options, set in prepare()

    // ---- per-channel state, indexed by slot 1-32 or playback channel 1-34;
    // element 0 unused (channels.h)
    Prog prog_[chan::N_SLOTS + 1];
    Vad  vad_[chan::N_SLOTS + 1];           // Listener holds 400 bytes of history;
                                            // 33 of them, allocated with Engine
    bool test_on_[chan::N_PLAY_CH + 1] = { false };
    bool mon_out_[chan::N_PLAY_CH + 1] = { false };  // --monitor-ch, by channel

    // ---- monitor (audio.md 10): capture 23 (the tap) -> mon_hp_ ->
    // mon_lp_[0..3] -> + a file on prog_[24] through its own mon_lp_ ->
    // gain -> lim_ -> mon_row_ -> the playback channels --monitor-ch names,
    // 24 by default
    Biquad                   mon_hp_;       // 150 Hz high-pass
    std::vector<Biquad>      mon_lp_;       // elliptic low-pass, 4 sections
    BiquadState              mon_hp_s_;
    std::vector<BiquadState> mon_lp_s_;
    std::vector<BiquadState> mon_file_lp_s_;  // the file's own copy (10.4)
    double  mon_file_lin_ = 1.0;            // --monitor-file-trim, linear
    double  mon_file_on_tap_ = 1.0;         // the same, less the tap trim
    Limiter                  lim_;
    // ---- the line-disturbance gate (audio.md 10.5, Rev 17): the source's raw
    // capture below 50 Hz (Rev 19), and a 10ms delay on the filtered source so the
    // gate shuts before a click's onset reaches the output.
    bool    gate_on_ = false;
    Biquad  gate_lp_;                       // 50 Hz low-pass, run twice (Rev 19)
    BiquadState gate_s1_, gate_s2_;
    double  gate_thr_ = 0.0;                // linear peak threshold
    int     gate_hold_n_ = 0;               // samples it stays shut after
    int     gate_left_ = 0;                 // samples of shut remaining
    double  gate_g_ = 1.0;                  // 0 shut .. 1 open
    unsigned gate_hits_ = 0;                // times shut, for the log
    std::vector<float> gate_dly_;           // GATE_DELAY samples
    size_t  gate_pos_ = 0;
    double  mon_ripple_db_ = 0.0;
    // audio.md 10.3. The commanded gain is kept apart from the ramp's target
    // because a source switch ramps to silence and back, and has to know what
    // to come back to - which is the commanded gain plus the tap trim, if the
    // new source is the tap.
    int     mon_src_ch_ = chan::TAP_CH;     // capture channel feeding the chain
    int     mon_pend_ch_ = 0;               // switch waiting for the ramp's bottom
    double  mon_cmd_db_ = 0.0;              // what monitor/set last commanded
    bool    mon_on_ = false;
    double  mon_gain_ = 0.0;                // current gain, linear; 0 = muted
    double  mon_target_ = 0.0;              // where the ramp is heading
    double  mon_step_ = 0.0;                // gain change per sample while ramping
    int     mon_ramp_ = 0;                  // samples of ramp remaining
    std::vector<float> mon_row_;            // this period's monitor samples

    unsigned clips_ = 0;                    // clipped samples since last report

    // ---- output self-check (audio.md 11.4), by playback channel 1-34.
    // render() sets out_ceil_ to the most each channel should carry this
    // period, linear full scale, or a negative value for a channel it does not
    // check; check_output() counts the periods that exceed it until the
    // once-a-second hand-over to Shared.
    float    out_ceil_[chan::N_PLAY_CH + 1] = {};
    unsigned out_over_[chan::N_PLAY_CH + 1] = {};
    float    out_pk_[chan::N_PLAY_CH + 1]   = {};
};
