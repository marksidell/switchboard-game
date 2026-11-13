// monitor.cpp - the audience monitor's chain. See monitor.h.
//
// Every function here runs on the audio thread, except prepare(), which runs
// once at startup before the thread exists.

#include "monitor.h"

#include <algorithm>
#include <cstdio>

#include "util.h"

using chan::SAMPLE_RATE;

// audio.md 10.5: the source's delay ahead of the gate, 10ms, so the gate is
// shut before a click's onset reaches the output; and the gate's band. At
// 100 Hz a man's voice, fundamental near 100-130 Hz, came within a few dB of
// the threshold, so the band stops at 50 Hz.
static constexpr size_t GATE_DELAY = 480;
static constexpr double GATE_LP_HZ = 50.0;
// audio.md 10.8: a file counts as playing until its echo is over, 50ms after
// its last sample; the source's peer is held through 2s of the detector
// hearing anything else.
static constexpr uint64_t PB_ECHO = 2400;
static constexpr uint64_t PB_HOLD = 96000;

// prepare()                                                          [startup]
bool MonitorChain::prepare(unsigned period, unsigned ncap)
{
    const Options& o = sh_.opt;
    period_ = period;
    ncap_   = ncap;
    row_.assign(period_, 0.0f);

    // station_circuit.md §8.8 through audio.md 10.1.
    hp_ = butter_highpass(150.0, SAMPLE_RATE);
    lp_ = elliptic_lowpass(8, o.lp_pass, o.lp_stop, o.lp_att, SAMPLE_RATE, ripple_db_);
    if (lp_.empty()) { log_line("monitor: low-pass design failed"); return false; }
    lp_s_.assign(lp_.size(), BiquadState());
    file_lp_s_.assign(lp_.size(), BiquadState());
    // audio.md 10.4: the file shares the source's ramp, which carries the tap
    // trim while the source is the tap, so the trim is taken back out of the
    // file's share.
    file_lin_    = db_to_lin(o.monitor_file_trim_db);
    file_on_tap_ = db_to_lin(o.monitor_file_trim_db - o.monitor_tap_trim_db);
    // Set just above speech, a switch's click on the line is held to the
    // level of the loudest speech rather than reaching -3dBFS.
    lim_.init(o.monitor_limit_db, 0.100, SAMPLE_RATE);
    log_line("monitor: limiter at %.1f dBFS", o.monitor_limit_db);

    max_lin_   = db_to_lin(o.monitor_peer_max_db);
    start_lin_ = db_to_lin(o.monitor_peer_start_db);
    pb_lin_    = start_lin_;
    if (o.monitor_peer_max_db > 0.0)
        log_line("monitor: peer boost up to %.1f dB, %.1f dB until measured",
                 o.monitor_peer_max_db, o.monitor_peer_start_db);

    duck_down_db_ = -o.monitor_listen_duck_db;
    duck_step_    = o.monitor_listen_duck_db / (0.020 * SAMPLE_RATE);
    if (o.monitor_listen_duck_db > 0.0)
        log_line("monitor: %.0f dB down while a listen runs on the source", o.monitor_listen_duck_db);
    if (!fbx_.prepare(SAMPLE_RATE, o.monitor_fbx)) return false;
    log_line("monitor: feedback eliminator %s", o.monitor_fbx ? "on" : "off");

    // The delay line is there whether or not the gate is on, so the chain's
    // latency does not depend on a setting.
    gate_on_     = o.monitor_gate_db != 0.0;
    gate_lp_     = butter_lowpass(GATE_LP_HZ, SAMPLE_RATE);
    gate_thr_    = db_to_lin(o.monitor_gate_db);
    gate_hold_n_ = (int)(o.monitor_gate_hold * SAMPLE_RATE);
    gate_dly_.assign(GATE_DELAY, 0.0f);
    if (gate_on_)
        log_line("monitor: gate at %.1f dBFS below %.0f Hz, hold %.2f s, delay %.0f ms",
                 o.monitor_gate_db, GATE_LP_HZ, o.monitor_gate_hold,
                 1000.0 * GATE_DELAY / SAMPLE_RATE);

    const double at_6k = cascade_mag_db(lp_, 6000.0, SAMPLE_RATE);
    log_line("monitor: elliptic low-pass order 8, pass %.0f Hz, stop %.0f Hz, "
             "%.1f dB; ripple %.4f dB, %.1f dB at 6000 Hz",
             o.lp_pass, o.lp_stop, o.lp_att, ripple_db_, at_6k);
    if (at_6k > -o.lp_att)
        log_line("monitor: WARNING the lowest pilot at 6000 Hz is only %.1f dB "
                 "down; station_circuit.md §8.8 asks for %.0f", -at_6k, o.lp_att);

    // audio.md 10.3: a source the device does not capture is refused, as
    // --monitor-ch refuses an output it cannot reach. A quiet loudspeaker with
    // nothing pointing at the fault would be worse.
    if (o.monitor_src > (int)ncap_) {
        char name[24];
        chan::monitor_source_name(o.monitor_src, name, sizeof name);
        log_line("--monitor-src %s is capture channel %d, but the device granted "
                 "only %u capture channels", name, o.monitor_src, ncap_);
        return false;
    }
    // audio.md 10.2: on at startup only if --monitor gives a level, and at
    // its target rather than ramped - there is no transient to avoid before
    // the stream runs.
    src_ch_ = o.monitor_src;
    on_     = o.monitor_on;
    cmd_db_ = o.monitor_db;
    target_ = target(src_ch_);
    gain_   = target_;
    return true;
}

// target()                                                             [audio]
//   audio.md 10.2, 10.3. The gain the ramp heads for: the commanded gain, plus
//   --monitor-tap-trim while the source is the tap, or silence when muted. The
//   trim is not echoed on `monitor`, which carries what monitor/set asked for.
double MonitorChain::target(int src_ch) const
{
    if (!on_) return 0.0;
    const double db = cmd_db_ + (src_ch == chan::TAP_CH ? sh_.opt.monitor_tap_trim_db : 0.0);
    return db_to_lin(db);
}

// ramp_to()                                                            [audio]
//   A 20ms ramp from wherever the gain is now. A ramp already running is
//   taken over from where it has reached (audio.md 10.3).
void MonitorChain::ramp_to(double t)
{
    target_ = t;
    ramp_   = (int)(0.020 * SAMPLE_RATE);
    step_   = (target_ - gain_) / (double)ramp_;
}

// switch_to()                                                          [audio]
//   The bottom of the ramp: change the input and echo. The filter state is
//   carried across: the step happens at zero gain and has rung out before the
//   ramp up is audible (audio.md 10.3).
void MonitorChain::switch_to(int ch)
{
    src_ch_  = ch;
    pend_ch_ = 0;
    char name[24];
    if (chan::monitor_source_name(ch, name, sizeof name)) post_result(sh_, Topic::MonitorSrc, 0, name);
}

// set_level()                                                          [audio]
//   A 20ms ramp so a level step does not click; "off" is a mute, ramped the
//   same way. The filters keep running, so turning on has no cold transient.
void MonitorChain::set_level(bool on, double db)
{
    on_     = on;
    cmd_db_ = db;
    // A source switch is mid-flight: stay headed for silence, and let the
    // switch ramp back up to this new gain when it lands.
    if (!pend_ch_) ramp_to(target(src_ch_));
    char buf[32];
    if (on) format_db(db, buf, sizeof buf);
    else    std::snprintf(buf, sizeof buf, "off");
    post_result(sh_, Topic::Monitor, 0, buf);
}

// set_source()                                                         [audio]
//   audio.md 10.3.
void MonitorChain::set_source(int ch)
{
    // Already there: echo and do nothing else.
    if (ch == src_ch_ && !pend_ch_) {
        char name[24];
        if (chan::monitor_source_name(ch, name, sizeof name))
            post_result(sh_, Topic::MonitorSrc, 0, name);
        return;
    }
    // Muted: there is nothing to click, so the input changes at once.
    if (!on_) {
        switch_to(ch);
        target_ = target(src_ch_);              // still 0 while muted
        return;
    }
    // Otherwise ramp to silence and change at the bottom. A second command
    // during the ramp replaces the pending channel and takes the ramp over.
    pend_ch_ = ch;
    ramp_to(0.0);
}

// set_peer()                                                           [audio]
//   audio.md 10.8: a figure from the game, or back to the measurement. Net
//   has clamped it to 0 - --monitor-peer-max.
void MonitorChain::set_peer(bool fixed, double db)
{
    fixed_     = fixed;
    fixed_lin_ = db_to_lin(db);
    char buf[32];
    if (fixed) format_db(db, buf, sizeof buf);
    else       std::snprintf(buf, sizeof buf, "auto");
    post_result(sh_, Topic::MonitorPeer, 0, buf);
}

// stop_game()                                                          [audio]
//   audio.md 13.2: the calls a circuit source was following are gone, and
//   the tap is the one source that is not about a call. Under the 10.3 ramp.
void MonitorChain::stop_game()
{
    if (src_ch_ != chan::TAP_CH || pend_ch_) {
        if (!on_) {
            switch_to(chan::TAP_CH);
            target_ = target(src_ch_);
        } else {
            pend_ch_ = chan::TAP_CH;
            ramp_to(0.0);
        }
    }
    if (fixed_) {
        fixed_ = false;
        post_result(sh_, Topic::MonitorPeer, 0, "auto");
    }
}

// file_sent()                                                          [audio]
void MonitorChain::file_sent(int slot, double energy, uint64_t end)
{
    file_e_[slot]    += energy;
    file_until_[slot] = end + PB_ECHO;
}

// gate_step()                                                          [audio]
//   audio.md 10.5. One sample of the line-disturbance gate: `raw` is the
//   source's capture, `y` the same sample through the filters. A switch on the
//   line, or ringing near it, puts far more below 50 Hz on it than telephone
//   speech ever does. While the low band's peak exceeds the threshold, and for
//   the hold after, the source is shut: 1ms down, 20ms back up. Returns the
//   delayed, gated sample.
double MonitorChain::gate_step(float raw, double y)
{
    const double d = gate_dly_[gate_pos_];
    gate_dly_[gate_pos_] = (float)y;
    if (++gate_pos_ == gate_dly_.size()) gate_pos_ = 0;
    if (!gate_on_) return d;

    const double lf = gate_s2_.run(gate_lp_, gate_s1_.run(gate_lp_, (double)raw));
    if (std::fabs(lf) > gate_thr_) {
        if (gate_left_ == 0) ++gate_hits_;
        gate_left_ = gate_hold_n_;
    } else if (gate_left_ > 0) {
        --gate_left_;
    }
    if (gate_left_ > 0) gate_g_ = std::max(0.0, gate_g_ - 1.0 / (0.001 * SAMPLE_RATE));
    else                gate_g_ = std::min(1.0, gate_g_ + 1.0 / (0.020 * SAMPLE_RATE));
    return d * gate_g_;
}

// process()                                                            [audio]
//   Run whether muted or not, so turning on is instant and has no transient
//   from a cold filter state. The monitor's file (audio.md 10.4) is summed
//   after the filter through a second copy of the low-pass, so it is held out
//   of the pilot band as the source is - the loudspeaker is in the room with
//   the operator's microphone. That copy runs with no file too.
void MonitorChain::process(const float* capf, const float* file, unsigned fn, uint64_t g,
                           const bool* listening)
{
    const int pb_mode = peer_boost_begin(g);
    const double duck = duck_target(g, listening);     // dB
    double pb_e = 0.0;
    bool   pb_gated = false;
    if ((int)ncap_ < src_ch_) {
        std::fill(row_.begin(), row_.end(), 0.0f);
        peer_boost_end(pb_mode, pb_e, pb_gated);
        return;
    }
    const float* src = &capf[(size_t)(src_ch_ - 1) * period_];
    for (unsigned i = 0; i < period_; ++i) {
        double y = hp_s_.run(hp_, (double)src[i]);
        for (size_t s = 0; s < lp_.size(); ++s) y = lp_s_[s].run(lp_[s], y);
        y = gate_step(src[i], y);
        pb_e += y * y;
        if (gate_g_ < 1.0) pb_gated = true;
        pb_g_ += (pb_target_ - pb_g_) * (1.0 / (0.020 * SAMPLE_RATE));
        y *= pb_g_;
        if (duck_db_ != duck) {           // 20 ms from end to end, linear in dB
            const double st = duck_step_;
            duck_db_ = (duck < duck_db_) ? std::max(duck, duck_db_ - st) : std::min(duck, duck_db_ + st);
            duck_g_ = db_to_lin(duck_db_);
        }
        y *= duck_g_;
        double f = (i < fn) ? (double)file[i] : 0.0;
        for (size_t s = 0; s < lp_.size(); ++s) f = file_lp_s_[s].run(lp_[s], f);
        if (ramp_ > 0) { gain_ += step_; --ramp_; }
        else           { gain_ = target_; }
        const double fg = (src_ch_ == chan::TAP_CH) ? file_on_tap_ : file_lin_;
        row_[i] = (float)lim_.run(fbx_.run((y + f * fg) * gain_));

        // The bottom of a source ramp, mid-period, so the silence is the 20ms
        // audio.md 10.3 asks for and not 20ms plus the rest of the period.
        // ramp_ reaching 0 is the test, not the gain reaching 0, which by
        // accumulation can sit a float's breadth either side of it; a pending
        // channel is only ever set with a ramp to silence.
        if (pend_ch_ && ramp_ == 0) {
            gain_ = 0.0;
            const int want = pend_ch_;
            if ((int)ncap_ >= want) {
                switch_to(want);
                src = &capf[(size_t)(src_ch_ - 1) * period_];
            } else {
                pend_ch_ = 0;           // not captured; stay where we are
            }
            ramp_to(target(src_ch_));
        }
    }
    peer_boost_end(pb_mode, pb_e, pb_gated);
}

// duck_target()                                                        [audio]
//   audio.md 10.9. The source's gain for this period from the duck, in dB: down
//   while a listen runs on the circuit the monitor plays and nothing plays a
//   file on it or on its peer, 1 otherwise. A listen with a file running is
//   one waiting for someone to talk over the file, and the audience should
//   hear the file. The loudspeaker plays the line the operator talks on, and
//   through her headset microphone it returns on that line and holds the
//   speech detector in speech after she has stopped. 0 is no duck.
double MonitorChain::duck_target(uint64_t g, const bool* listening)
{
    const int src = src_ch_;
    if (duck_down_db_ >= 0.0 || !listening || pend_ch_ || !chan::is_circuit_slot(src) ||
        !listening[src]) return 0.0;
    if (g < file_until_[src]) return 0.0;
    int peer = pb_peer_;
    if (!peer) peer = sh_.heard_peer[src].load(std::memory_order_relaxed);
    if (peer > 0 && peer <= chan::N_SLOTS && g < file_until_[peer]) return 0.0;
    if (duck_db_ == 0.0) ++ducks_;
    return duck_down_db_;
}

// peer_boost_begin()                                                   [audio]
//   audio.md 10.8. Before the monitor's samples: which path this period's
//   source measures - 1 own, 2 peer, 0 neither - and the boost it heads for.
//   The peer is the detector's, held through PB_HOLD of anything else, since a
//   circuit's own playback makes its peer flicker to idle. A new source or
//   peer starts its sums afresh.
int MonitorChain::peer_boost_begin(uint64_t g)
{
    pb_target_ = 1.0;
    const int src = src_ch_;
    if (max_lin_ <= 1.0 || !chan::is_circuit_slot(src) || pend_ch_) {
        pb_src_ = 0;
        return 0;
    }
    if (src != pb_src_) {
        pb_src_  = src;
        pb_peer_ = 0;
        own_     = PathSum();
        other_   = PathSum();
    }
    const int h = sh_.heard_peer[src].load(std::memory_order_relaxed);
    if (h > 0) {
        if (h != pb_peer_) { pb_peer_ = h; other_ = PathSum(); }
        pb_peer_at_ = g;
    } else if (pb_peer_ && g - pb_peer_at_ > PB_HOLD) {
        pb_peer_ = 0;
    }
    const bool own   = g < file_until_[src];
    const bool other = pb_peer_ && g < file_until_[pb_peer_];
    // Fixed by the game: the same moments, nothing measured.
    if (own && !other) return fixed_ ? 0 : 1;
    if (other && !own) { pb_target_ = pb_lin_; return fixed_ ? 0 : 2; }
    return 0;
}

// peer_boost_end()                                                     [audio]
//   After them: this period's source energy, before the boost, against the
//   file energy render() sent on the path measured, unless the gate shut;
//   then the boost from the two sums once each holds a second of file. Every
//   circuit's file energy is consumed here, measured or not.
void MonitorChain::peer_boost_end(int mode, double energy, bool gated)
{
    if (mode && !gated) {
        PathSum& p = (mode == 1) ? own_ : other_;
        const double f = file_e_[mode == 1 ? pb_src_ : pb_peer_];
        if (f > 0.0) {
            p.mon  += energy;
            p.file += f;
            p.n    += period_;
            if (p.n > 10.0 * SAMPLE_RATE) { p.mon *= 0.5; p.file *= 0.5; p.n *= 0.5; }
        }
    }
    for (int s = 1; s <= chan::N_SLOTS; ++s) file_e_[s] = 0.0;

    if (fixed_) {
        pb_lin_   = std::min(fixed_lin_, max_lin_);
        measured_ = false;
        return;
    }
    const bool both = own_.n >= SAMPLE_RATE && other_.n >= SAMPLE_RATE &&
                      own_.file > 0.0 && other_.file > 0.0 &&
                      own_.mon > 0.0 && other_.mon > 0.0;
    measured_ = both;
    if (!both) {
        pb_lin_ = start_lin_;
        return;
    }
    // Energies: the square root gives the amplitude ratio.
    const double r = std::sqrt((own_.mon / own_.file) / (other_.mon / other_.file));
    pb_lin_ = std::min(std::max(r, 1.0), max_lin_);
}

// hand_over()                                                          [audio]
void MonitorChain::hand_over()
{
    if (gate_hits_) { sh_.gate_hits.fetch_add(gate_hits_, std::memory_order_relaxed); gate_hits_ = 0; }
    sh_.peer_boost.store(pb_src_ && pb_peer_
                         ? (int)std::lround(2000.0 * std::log10(pb_lin_)) * 1000
                           + pb_peer_ * 10 + (fixed_ ? 2 : measured_ ? 1 : 0)
                         : -1, std::memory_order_relaxed);
    const FeedbackEliminator::Event e = fbx_.take();
    if (e.count) {
        sh_.fbx_last.store((int)std::lround(e.hz) * 100 + (int)std::lround(-e.db),
                           std::memory_order_relaxed);
        sh_.fbx_events.fetch_add(e.count, std::memory_order_relaxed);
    }
    const unsigned l = lim_.take_active();
    if (l) sh_.limiter_hits.fetch_add(l, std::memory_order_relaxed);
}
