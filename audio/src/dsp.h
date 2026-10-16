// dsp.h - the arithmetic the audio thread runs: the shared sine table, biquads
// and their designs, and the monitor limiter.
//
// Everything here is allocation-free once constructed and safe to call from the
// audio thread. The filter *designs* allocate and are called at startup only.
//
// Three kinds of thing live here:
//
//   SineTable     4096 samples of one sine cycle. Every oscillator in the
//                 program - pilots, operator tone, trunk tones, test tone -
//                 reads it; none calls sin() at run time.
//   Biquad        one second-order IIR filter section: five coefficients in
//   BiquadState   one object, its two state variables in another, so one set
//                 of coefficients can serve many channels, each with its own
//                 state. Longer filters are a std::vector<Biquad> run in
//                 series ("cascade").
//   Limiter       the monitor's peak limiter.
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
//
// Two ways to read it:
//
//   at(i)          exact lookup, index taken mod 4096. Used for the pilots and
//                  the operator tone, which are an integer number of cycles
//                  per 4096 samples and so land exactly on table entries.
//
//   at_q32(phase)  interpolated lookup for everything else. The phase is a
//                  32-bit unsigned integer covering one full cycle: 0 is 0
//                  degrees, 2^31 is 180, and it wraps from 2^32-1 back to 0 on
//                  its own, which is why integer phase is used at all - no
//                  fmod, no drift. Frequency f is a per-sample phase increment
//                  of f/fs * 2^32 (inc_q32 below); adding that every sample is
//                  the whole oscillator.
class SineTable {
public:
    static constexpr int N = 4096;

    // SineTable()                                                    [startup]
    //   Fills the table with one cycle of sin(), amplitude 1.0.
    SineTable();

    // at()                                                               [any]
    //   Table entry i mod 4096. See the class comment.
    inline float at(uint32_t i) const { return t_[i & (N - 1)]; }

    // at_q32()                                                           [any]
    //   Fractional lookup for the tones, which are not bin-aligned and do not
    //   need to be - they are programme audio, not pilots (audio.md 8.2). Phase
    //   is Q32: the top 12 bits index, the next 20 interpolate linearly
    //   between that entry and the next.
    inline float at_q32(uint32_t ph) const
    {
        const uint32_t i = ph >> 20;
        const float    f = (float)(ph & 0xfffff) * (1.0f / 1048576.0f);
        const float    a = t_[i & (N - 1)], b = t_[(i + 1) & (N - 1)];
        return a + (b - a) * f;
    }
    // inc_q32()                                                          [any]
    //   The Q32 phase increment per sample for a tone of `hz` at sample rate
    //   `fs`: 1000 Hz at 48 kHz is 89478485, about 1/48 of 2^32.
    static inline uint32_t inc_q32(double hz, double fs)
    {
        return (uint32_t)llrint(hz / fs * 4294967296.0);
    }
private:
    float t_[N];                        // one cycle, t_[i] = sin(2 pi i / N)
};

// ---------------------------------------------------------------- biquads

// Biquad - the coefficients of one second-order section,
//
//            b0 + b1 z^-1 + b2 z^-2
//   H(z) = --------------------------
//            1  + a1 z^-1 + a2 z^-2
//
// with a0 already divided through so it is 1 and not stored. The default is a
// wire: output equals input. Produced by the design functions below; never
// changed while running.
struct Biquad {
    double b0 = 1.0, b1 = 0.0, b2 = 0.0, a1 = 0.0, a2 = 0.0;   // a0 normalised
};

// BiquadState - the memory of one section on one channel: two numbers that
// carry the filter's history from one sample to the next. Transposed direct
// form II, double state. One state per channel per section; the coefficients
// are shared.
struct BiquadState {
    double z1 = 0.0, z2 = 0.0;

    // reset()                                                        [owner]
    //   Forgets the history, as if the input had been silent forever.
    inline void reset() { z1 = z2 = 0.0; }

    // run()                                                          [owner]
    //   Filters one sample: takes input x, returns output y, and updates
    //   z1/z2 for the next call. To run a cascade, feed each section's output
    //   to the next section's run().
    inline double run(const Biquad& c, double x)
    {
        const double y = c.b0 * x + z1;
        z1 = c.b1 * x - c.a1 * y + z2;
        z2 = c.b2 * x - c.a2 * y;
        return y;
    }
};

// butter_lowpass() / butter_highpass()                               [startup]
//   Second-order Butterworth, RBJ forms: one section, -3 dB at fc, then
//   falling at 12 dB/octave. Used for the monitor's 150Hz high-pass (station
//   8.8) and the speech detector's 300-3400Hz band-pass (audio.md 9.2).
Biquad butter_lowpass (double fc, double fs);
Biquad butter_highpass(double fc, double fs);

// butter_lowpass6()                                                  [startup]
//   Sixth-order Butterworth low-pass as three sections, Q 0.518, 0.707 and
//   1.932, run in series: -3 dB at fc, then 36 dB/octave. The speech
//   detector's low-pass since audio.md Rev 18, which puts the pilots 30 dB
//   or more down where one section left the lowest only 10.
std::vector<Biquad> butter_lowpass6(double fc, double fs);

// elliptic_lowpass()                                                 [startup]
//   Elliptic low-pass, even order, as cascaded second-order sections (station
//   8.8: passband edge 3.6kHz, stopband edge 5.6kHz, stopband 70dB or better).
//   Returns the sections - order/2 of them, to be run in series - or an empty
//   vector for an odd or too-small order. `ripple_db` reports the passband
//   ripple the design came out with, which is what the spare order buys once
//   the order is fixed.
//
//   An elliptic filter has the steepest possible transition between passband
//   and stopband for its order, at the price of ripple in both. That
//   steepness is why it is used: the gap between 3.6 kHz (keep) and 6 kHz
//   (the lowest pilot, remove by 70 dB) is under an octave.
std::vector<Biquad> elliptic_lowpass(int order, double fpass, double fstop,
                                     double stop_db, double fs, double& ripple_db);

// elliptic_highpass()                                                [startup]
//   The same design mirrored: passes above `fpass`, at least `stop_db` down at
//   and below `fstop`, with fstop < fpass. Used for the content check of
//   audio.md 5.3 and 7.2, which asks how much of a delivered file sits above
//   5.5kHz - a question a gentle filter cannot answer, because the telephone
//   band it must ignore ends only 2kHz below the corner.
std::vector<Biquad> elliptic_highpass(int order, double fpass, double fstop,
                                      double stop_db, double fs, double& ripple_db);

// cascade_mag_db()                                                       [any]
//   Magnitude response of a cascade at one frequency, in dB: 0 is unity, -70
//   is 70 dB down. Evaluates H(z) on the unit circle directly rather than
//   running a signal through, so it is exact. For the startup log line and
//   for the unit test that checks the realised stopband at 6000Hz.
double cascade_mag_db(const std::vector<Biquad>& secs, double hz, double fs);

// ---------------------------------------------------------------- limiter

// Peak limiter, audio.md 10.1: threshold -3dBFS, instant attack, 100ms release.
// It is there so that setting the monitor level by ear cannot produce a clipped
// burst from a ring-trip transient or a shouted line.
//
// How it works: a gain, normally 1.0, multiplies every sample. When a sample
// would exceed the threshold, the gain drops at once to exactly what brings
// that sample down to the threshold (instant attack). After that the gain
// recovers towards 1.0 exponentially with a 100 ms time constant (release).
// There is no look-ahead, so the one sample that triggers it is limited, not
// anticipated - fine for a loudspeaker feed.
class Limiter {
public:
    // init()                                                         [startup]
    //   Sets the threshold (dBFS), the release time constant (seconds) and the
    //   sample rate, and resets the gain to 1.0.
    void  init(double threshold_db, double release_s, double fs);

    // run()                                                            [audio]
    //   Limits one sample and returns it. Counts each time the gain is pulled
    //   down, so the log can say whether the limiter is working.
    inline double run(double x)
    {
        // Release first, then attack, so the sample that sets the gain is
        // never let back up past the threshold (Rev 16: at a threshold well
        // below full scale the other order overshot by about 0.6%).
        if (gain_ < 1.0) {
            gain_ += (1.0 - gain_) * rel_;               // one-pole release
            if (gain_ > 1.0) gain_ = 1.0;
        }
        const double a = std::fabs(x);
        if (a * gain_ > thresh_) {
            gain_ = thresh_ / a;                         // instant attack
            ++active_;
        }
        return x * gain_;
    }
    // take_active()                                                    [audio]
    //   Returns how many times the limiter has acted since the last call, and
    //   zeroes the count.
    unsigned take_active() { const unsigned v = active_; active_ = 0; return v; }
private:
    double   thresh_ = 1.0;             // threshold as a linear amplitude
    double   rel_    = 1.0;             // per-sample release coefficient, 0-1
    double   gain_   = 1.0;             // current gain; 1.0 is not limiting
    unsigned active_ = 0;               // gain reductions since take_active()
};
