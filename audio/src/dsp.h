// dsp.h - the arithmetic the audio thread runs: the shared sine table, biquads
// and their designs, and the monitor limiter.
//
// Everything here is allocation-free once constructed and safe to call from the
// audio thread. The filter *designs* allocate and are called at startup only.
#pragma once

#include <cmath>
#include <cstdint>
#include <vector>

// ---------------------------------------------------------------- sine table

// One shared 4096-entry sine table, station 8.8 and audio.md 5.1. For a comb
// bin b, sample n of the 4096-sample cycle is table[(b * n) & 4095]: every
// pilot completes an integer number of cycles per block, so a counter that
// wraps at 4096 is the whole oscillator - no phase accumulator, no rounding,
// no drift, and the pilot is on its bin by construction.
class SineTable {
public:
    static constexpr int N = 4096;
    SineTable();
    inline float at(uint32_t i) const { return t_[i & (N - 1)]; }
    // Fractional lookup for the tones, which are not bin-aligned and do not
    // need to be - they are programme audio, not pilots (audio.md 8.2). Phase
    // is Q32: the top 12 bits index, the next 20 interpolate.
    inline float at_q32(uint32_t ph) const
    {
        const uint32_t i = ph >> 20;
        const float    f = (float)(ph & 0xfffff) * (1.0f / 1048576.0f);
        const float    a = t_[i & (N - 1)], b = t_[(i + 1) & (N - 1)];
        return a + (b - a) * f;
    }
    static inline uint32_t inc_q32(double hz, double fs)
    {
        return (uint32_t)llrint(hz / fs * 4294967296.0);
    }
private:
    float t_[N];
};

// ---------------------------------------------------------------- biquads

struct Biquad {
    double b0 = 1.0, b1 = 0.0, b2 = 0.0, a1 = 0.0, a2 = 0.0;   // a0 normalised
};

// Transposed direct form II, double state. One state per channel per section;
// the coefficients are shared.
struct BiquadState {
    double z1 = 0.0, z2 = 0.0;
    inline void reset() { z1 = z2 = 0.0; }
    inline double run(const Biquad& c, double x)
    {
        const double y = c.b0 * x + z1;
        z1 = c.b1 * x - c.a1 * y + z2;
        z2 = c.b2 * x - c.a2 * y;
        return y;
    }
};

// Second-order Butterworth, RBJ forms. Used for the monitor's 150Hz high-pass
// (station 8.8) and the speech detector's 300-3400Hz band-pass (audio.md 9.2).
Biquad butter_lowpass (double fc, double fs);
Biquad butter_highpass(double fc, double fs);

// Elliptic low-pass, even order, as cascaded second-order sections (station
// 8.8: passband edge 3.6kHz, stopband edge 5.6kHz, stopband 70dB or better).
// Returns the sections; `ripple_db` reports the passband ripple the design came
// out with, which is what the spare order buys once the order is fixed.
std::vector<Biquad> elliptic_lowpass(int order, double fpass, double fstop,
                                     double stop_db, double fs, double& ripple_db);

// Magnitude response of a cascade at one frequency, for the log line and for
// the unit test that checks the realised stopband at 6000Hz.
double cascade_mag_db(const std::vector<Biquad>& secs, double hz, double fs);

// ---------------------------------------------------------------- limiter

// Peak limiter, audio.md 10.1: threshold -3dBFS, instant attack, 100ms release.
// It is there so that setting the monitor level by ear cannot produce a clipped
// burst from a ring-trip transient or a shouted line.
class Limiter {
public:
    void  init(double threshold_db, double release_s, double fs);
    inline double run(double x)
    {
        const double a = std::fabs(x);
        if (a > thresh_) {
            const double g = thresh_ / a;
            if (g < gain_) { gain_ = g; ++active_; }     // instant attack
        }
        if (gain_ < 1.0) {
            gain_ += (1.0 - gain_) * rel_;               // one-pole release
            if (gain_ > 1.0) gain_ = 1.0;
        }
        return x * gain_;
    }
    unsigned take_active() { const unsigned v = active_; active_ = 0; return v; }
private:
    double   thresh_ = 1.0, rel_ = 1.0, gain_ = 1.0;
    unsigned active_ = 0;
};
