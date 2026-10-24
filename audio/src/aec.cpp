// aec.cpp - the line echo canceller. See aec.h.

#include "aec.h"

#include <cmath>
#include <cstring>

namespace {
constexpr float    MU      = 0.5f;          // NLMS step
constexpr float    EPS     = 1e-5f;         // keeps the step sane in a pause
constexpr uint32_t FORGET  = 30 * 8000;     // off this long: a new call
constexpr int      WORSE_FRAMES = 50;       // the foreground adding echo this long:
                                            // not converged after all
constexpr int      WIN_FRAMES = 3;          // background ahead this many frames
constexpr double   AHEAD   = 0.5;           // by 3 dB
constexpr double   USEFUL  = 0.1;           // and 10 dB below the capture
constexpr double   GOOD    = 0.01;          // 20 dB below: converged
constexpr double   LOST    = 4.0;           // 6 dB behind: put the background back
}

// start()                                                              [audio]
void EchoCanceller::start(uint32_t m)
{
    std::memset(ref_, 0, sizeof ref_);
    if (fresh_ || m - off_at_ > FORGET) {
        std::memset(wf_, 0, sizeof wf_);
        std::memset(wb_, 0, sizeof wb_);
        converged_ = false;
        fresh_ = false;
    }
    better_ = 0;
    worse_ = 0;
    sf_ = sb_ = sy_ = sc_ = 0.0;
    n_ = 0;
    on_ = true;
}

// step()                                                               [audio]
//   One sample of both filters. x[k] is the reference k + delay samples ago.
float EchoCanceller::step(uint32_t m, float c)
{
    float x[TAPS];
    const uint32_t base = m - (uint32_t)delay_;
    float yf = 0.0f, yb = 0.0f, norm = EPS;
    for (int k = 0; k < TAPS; ++k) {
        const float v = ref_[(base - (uint32_t)k) & (RING - 1)];
        x[k] = v;
        yf += wf_[k] * v;
        yb += wb_[k] * v;
        norm += v * v;
    }
    const float ef = c - yf, eb = c - yb;
    const float g = MU * eb / norm;
    for (int k = 0; k < TAPS; ++k) wb_[k] += g * x[k];

    sf_ += (double)ef * ef;
    sb_ += (double)eb * eb;
    sy_ += (double)yf * yf;
    sc_ += (double)c * c;
    ++n_;
    return ef;
}

// end_frame()                                                          [audio]
EchoCanceller::Frame EchoCanceller::end_frame(uint32_t)
{
    Frame f;
    f.full = on_ && n_ == FRAME;
    const double n = n_ > 0 ? (double)n_ : 1.0;
    f.resid_db = 10.0 * std::log10(2.0 * sf_ / n + 1e-20);
    f.echo_db  = 10.0 * std::log10(2.0 * sy_ / n + 1e-20);

    if (n_ > 0) {
        // The two-path rules, once a frame. A background clearly ahead, and
        // doing something useful, for three frames running becomes the
        // foreground; one that has fallen well behind is put back.
        if (sb_ < AHEAD * sf_ && sb_ < USEFUL * sc_) {
            if (++better_ >= WIN_FRAMES) {
                std::memcpy(wf_, wb_, sizeof wf_);
                if (sb_ < GOOD * sc_) converged_ = true;
            }
        } else {
            better_ = 0;
        }
        if (sb_ > LOST * sf_ && sf_ < sc_) std::memcpy(wb_, wf_, sizeof wb_);
        // Converged once a copy has taken 20 dB off; and no longer if the
        // foreground then makes the line louder for half a second, which a
        // caller talking cannot do - the path has changed under it.
        if (sf_ > sc_ && sc_ > 0.0) {
            if (++worse_ >= WORSE_FRAMES) converged_ = false;
        } else {
            worse_ = 0;
        }
    }
    f.valid = f.full && converged_;

    sf_ = sb_ = sy_ = sc_ = 0.0;
    n_ = 0;
    return f;
}
