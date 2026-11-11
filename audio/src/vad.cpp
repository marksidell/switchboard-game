// vad.cpp - the speech detector's state machine. See vad.h.

#include "vad.h"

#include <algorithm>
#include <cmath>
#include <cstring>

// history_p10()                                                        [audio]
//   The 10th percentile of the frame levels in the history - the 10th-quietest
//   of the last 100 valid frames. nth_element() finds it without a full sort
//   and without allocating. -120 dBFS if there is no history yet.
double Listener::history_p10() const
{
    if (hist_n_ == 0) return -120.0;
    float tmp[100];
    std::memcpy(tmp, hist_, (size_t)hist_n_ * sizeof(float));
    const int k = hist_n_ / 10;
    std::nth_element(tmp, tmp + k, tmp + hist_n_);
    return tmp[k];
}

// steady()                                                             [audio]
//   Whether the last n frames of the history all lie within STEADY_DB of each
//   other, and the highest of them in `top`. False with fewer than n, and
//   false above STEADY_MAX_DB: a held vowel is steady too, but 40 dB louder
//   than any line's noise.
bool Listener::steady(int n, double& top) const
{
    if (hist_n_ < n) return false;
    float lo = 1e9f, hi = -1e9f;
    for (int i = 1; i <= n; ++i) {
        const float v = hist_[(hist_w_ - i + 100) % 100];
        lo = std::min(lo, v);
        hi = std::max(hi, v);
    }
    top = hi;
    return hi - lo <= STEADY_DB && hi <= STEADY_MAX_DB;
}

// start()                                                              [audio]
//   The floor is the 10th percentile of the second before the command, which
//   is why the history runs at all times. The timeout is counted in frames and
//   rounded up, so any positive number of seconds allows at least one frame.
void Listener::start(double seconds)
{
    phase_        = Phase::Waiting;
    floor_db_     = history_p10();
    elapsed_      = 0;
    start_frames_ = (uint32_t)std::ceil(seconds * FRAMES_PER_S);
    if (start_frames_ == 0) start_frames_ = 1;
    clear_window();
}

// frame()                                                              [audio]
//   In order: an invalid frame restarts the window and counts only as time;
//   a valid one goes into the history; then, if a listen is running, the floor
//   is allowed to creep, the frame is judged against the threshold and shifted
//   into the window, and the phase's rule is applied. Every frame, valid or
//   not, advances the phase's clock: the timeouts are wall-clock bounds, and a
//   stretch of discarded frames is still time the game is waiting.
Listener::Event Listener::frame(float db, bool valid, const VadParams& p, bool keep,
                                double min_db)
{
    if (!valid) {
        // audio.md 9.3: the channel's own programme returns on its receive at
        // full strength. Such frames are discarded, the window restarts, and
        // they are kept out of the history too, or the floor would follow our
        // own file up.
        clear_window();
    } else if (keep) {
        hist_[hist_w_] = db;
        hist_w_ = (hist_w_ + 1) % 100;
        if (hist_n_ < 100) ++hist_n_;
    }

    if (phase_ == Phase::Off) return Event::None;
    ++elapsed_;

    if (valid) {
        // The floor may rise at no more than 1 dB/s - 0.01 dB a frame - and
        // never fall, so a slowly rising room does not trigger and a burst
        // does not lower the bar.
        const double cand = history_p10();
        if (cand > floor_db_) floor_db_ = std::min(cand, floor_db_ + 0.01);
        // But a line that steps up to a new steady noise - a trunk
        // seized as the listen starts, 38 dB louder than before - takes it as
        // the floor at once, and the window starts again. Only a step: a
        // level wandering within STEADY_DB of the floor is left to the creep,
        // or each new high would restart the window. Speech is never
        // that steady for half a second; a word varies 10 dB frame to frame.
        double top;
        if (keep && steady(STEADY_FRAMES, top) && top > floor_db_ + STEADY_DB) {
            floor_db_ = top;
            clear_window();
        }

        const double thr = std::max({ floor_db_ + p.margin_db, p.abs_floor_db, min_db });
        win_ = ((win_ << 1) | (db >= thr ? 1u : 0u)) & ((1u << WIN) - 1u);
        if (win_n_ < WIN) ++win_n_;
    }

    // Decisions need a full window: 30 valid frames since the window last
    // restarted. Until then neither the start nor the end can be declared.
    const bool full  = win_n_ >= WIN;
    const int  above = __builtin_popcount(win_);

    if (phase_ == Phase::Waiting) {
        double top;
        if (valid && full && above >= START_NEEDED && !steady(WIN, top)) {
            // 200 ms of 300 above threshold. A click or a relay is a frame or
            // two; a word is many. Not a steady level, which is noise waiting
            // to become the floor. The maximum speech time runs from here.
            phase_   = Phase::Speaking;
            elapsed_ = 0;
            quiet_   = 0;
            return Event::Speech;
        }
        if (elapsed_ >= start_frames_) { phase_ = Phase::Off; return Event::Timeout; }
        return Event::None;
    }

    // Speaking. Quiet is at most 2 of the last 30 frames above threshold, and
    // speech has ended when that has held for the hangover time. A cough or a
    // chair after the caller stops is a frame or two inside the window and
    // leaves the count running; a second sentence puts three or more in the
    // window and restarts it. An invalid frame restarts it too - it is time
    // in which the program could not hear whether the caller spoke.
    if (valid && full && above <= END_ALLOWED) ++quiet_;
    else                                       quiet_ = 0;

    if (quiet_ >= p.hangover_frames)     { phase_ = Phase::Off; return Event::Silence; }
    if (elapsed_ >= p.max_speech_frames) { phase_ = Phase::Off; return Event::Timeout; }
    return Event::None;
}
