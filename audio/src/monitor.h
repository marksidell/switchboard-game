// monitor.h - the audience monitor's chain (audio.md 10), run by the audio
// thread once a period.
//
//   the source's capture (the tap, 23, unless monitor/source/set named a
//   circuit) -> 150 Hz high-pass -> elliptic low-pass -> 10 ms delay -> the
//   line-disturbance gate (10.5) -> the peer boost (10.8)
//   + a file on the monitor, through its own copy of the low-pass (10.4)
//   -> gain, under a 20 ms ramp (10.2, 10.3) -> limiter -> row()
//
// Engine sends the row to the channels --monitor-ch names. Everything here is
// allocated in prepare(); the rest runs on the audio thread and does not
// allocate, lock or log.
#pragma once

#include <cmath>
#include <cstdint>
#include <vector>

#include "dsp.h"
#include "ipc.h"

class MonitorChain {
public:
    // The most the limiter's threshold may be (audio.md 10.1), and so the most
    // the output self-check expects on a monitor channel (audio.md 11.4).
    static constexpr double LIMIT_DB = -3.0;
    static float ceiling() { return (float)std::pow(10.0, LIMIT_DB / 20.0); }

    explicit MonitorChain(Shared& sh) : sh_(sh) {}

    // prepare()                                                      [startup]
    //   Designs the filters, sizes the row and the gate's delay, sets the
    //   starting source and gain. False, having logged why, if the low-pass
    //   design fails or --monitor-src names a channel not captured.
    bool prepare(unsigned period, unsigned ncap);

    // Commands, each echoed on its topic.                              [audio]
    void set_level(bool on, double db);     // monitor/set: a gain, or muted
    void set_source(int ch);                // monitor/source/set
    void set_peer(bool fixed, double db);   // monitor/peer/set: a figure, or auto
    // stop_game()                                                      [audio]
    //   audio.md 13.2: the source back to the tap, the boost back to auto.
    void stop_game();

    // file_sent()                                                      [audio]
    //   render() reports each circuit's file as sent this period: its energy
    //   and the 48 kHz sample count `end` its last sample went at. The peer
    //   boost measures against it.
    void file_sent(int slot, double energy, uint64_t end);

    // process()                                                        [audio]
    //   One period: capf is the capture, channel-major; file, fn the monitor's
    //   file for this period (nullptr, 0 for none); g the 48 kHz samples
    //   before this period. Fills row().
    void process(const float* capf, const float* file, unsigned fn, uint64_t g);

    // hand_over()                                                      [audio]
    //   Once a second: the gate and limiter counts and the boost in use, to
    //   Shared for the log.
    void hand_over();

    std::vector<float>& row() { return row_; }

private:
    friend struct EngineProbe;

    struct PathSum {
        double mon = 0.0, file = 0.0;       // energies, monitor and file
        double n   = 0.0;                   // samples summed
    };

    double target(int src_ch) const;
    void   ramp_to(double target);
    void   switch_to(int ch);               // at the bottom of the ramp
    double gate_step(float raw, double y);
    int    peer_boost_begin(uint64_t g);    // which path this period measures
    void   peer_boost_end(int mode, double energy, bool gated);

    Shared& sh_;
    unsigned period_ = 0, ncap_ = 0;
    std::vector<float> row_;                // this period's monitor samples

    // ---- filters
    Biquad                   hp_;           // 150 Hz high-pass
    std::vector<Biquad>      lp_;           // elliptic low-pass, 4 sections
    BiquadState              hp_s_;
    std::vector<BiquadState> lp_s_;
    std::vector<BiquadState> file_lp_s_;    // the file's own copy (10.4)
    double  ripple_db_ = 0.0;
    double  file_lin_ = 1.0;                // --monitor-file-trim, linear
    double  file_on_tap_ = 1.0;             // the same, less the tap trim
    Limiter lim_;

    // ---- the line-disturbance gate (10.5)
    bool    gate_on_ = false;
    Biquad  gate_lp_;                       // 50 Hz low-pass, run twice
    BiquadState gate_s1_, gate_s2_;
    double  gate_thr_ = 0.0;                // linear peak threshold
    int     gate_hold_n_ = 0;               // samples it stays shut after
    int     gate_left_ = 0;                 // samples of shut remaining
    double  gate_g_ = 1.0;                  // 0 shut .. 1 open
    unsigned gate_hits_ = 0;                // times shut, for the log
    std::vector<float> gate_dly_;
    size_t  gate_pos_ = 0;

    // ---- gain and source (10.2, 10.3). The commanded gain is kept apart
    // from the ramp's target: a source switch ramps to silence and back, and
    // comes back to the commanded gain plus the tap trim if the new source is
    // the tap.
    int     src_ch_ = chan::TAP_CH;         // capture channel feeding the chain
    int     pend_ch_ = 0;                   // switch waiting for the ramp's bottom
    double  cmd_db_ = 0.0;                  // what monitor/set last commanded
    bool    on_ = false;
    double  gain_ = 0.0;                    // current gain, linear; 0 = muted
    double  target_ = 0.0;                  // where the ramp is heading
    double  step_ = 0.0;                    // gain change per sample while ramping
    int     ramp_ = 0;                      // samples of ramp remaining

    // ---- the peer boost (10.8)
    double   file_e_[chan::N_SLOTS + 1] = {};       // since process() took it
    uint64_t file_until_[chan::N_SLOTS + 1] = {};   // g its echo lasts until
    double   max_lin_ = 1.0, start_lin_ = 1.0;
    int      pb_src_ = 0;                   // the source the sums are for
    int      pb_peer_ = 0;                  // its peer, held through flicker
    uint64_t pb_peer_at_ = 0;               // g it was last heard
    PathSum  own_, other_;
    bool     measured_ = false;
    bool     fixed_ = false;                // monitor/peer/set a figure
    double   fixed_lin_ = 1.0;              // and that figure, linear
    double   pb_lin_ = 1.0;                 // the boost, linear
    double   pb_target_ = 1.0;              // this period's: pb_lin_ or 1
    double   pb_g_ = 1.0;                   // eased toward it, per sample
};
