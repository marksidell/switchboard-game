// tones.h - the trunk tones (audio.md 8.2), generated a sample at a time on
// the audio thread.
//
// The Bell System tones of the period the 551 belongs to, before the precise
// tone plan replaced them with two-frequency sums. Busy is the dial-tone
// waveform interrupted at 60 IPM, as the period offices made it - one tone
// source, one interrupter - and a listener tells the two apart by the cadence
// alone. Reorder, the fast busy, is the same again at 120 IPM. Ringback is the
// city ring measured from a recording (cityring.h): one period of it in a
// table, played sample by sample.
#pragma once

#include <cstdint>
#include <vector>

#include "channels.h"
#include "dsp.h"
#include "ipc.h"

class TrunkTones {
public:
    // State - one circuit's tone: which, and where it has got to.
    struct State {
        ToneKind tone = ToneKind::Off;
        uint32_t ph   = 0;      // carrier phase, Q32; for ringback, samples into city_
        uint32_t mph  = 0;      // modulation phase, Q32
        uint32_t cad  = 0;      // samples into the cadence period
        uint32_t inc  = 0, minc = 0;    // per-sample increments, set by start()
    };

    explicit TrunkTones(const SineTable& tbl) : tbl_(tbl) {}

    // prepare()                                                      [startup]
    //   The level, the modulation depth and the ringback table.
    void prepare(double tone_db, double mod);

    // start()                                                          [audio]
    //   From the beginning of the on period, so the operator always hears a
    //   burst first.
    void start(State& s, ToneKind k) const;

    // next()                                                           [audio]
    //   One sample of the tone, and advances it.
    float next(State& s) const
    {
        const Spec& t = SPECS[(int)s.tone];
        const bool on = (t.period_samples == 0) || (s.cad < t.on_samples);
        float v = 0.0f;
        if (on && t.table) {
            v = amp_ * city_[s.ph];
        } else if (on) {
            // Carrier times (1 + m sin): the carrier and one sideband either
            // side, all inside the switchboard's passband and clear of the comb.
            const float m = 1.0f + mod_ * tbl_.at_q32(s.mph);
            v = mod_amp_ * tbl_.at_q32(s.ph) * m;
        }
        if (t.table) s.ph = (s.ph + 1) % (uint32_t)city_.size();
        else         s.ph += s.inc;
        s.mph += s.minc;
        if (t.period_samples) s.cad = (s.cad + 1) % t.period_samples;
        return v;
    }

    // name()                                                             [any]
    //   The payload echoed on `tone`; "" for Off clears the topic.
    static const char* name(ToneKind k);

private:
    // One row of the table: carrier and modulation frequency, and the cadence
    // as "on for on_samples out of every period_samples". Indexed by ToneKind.
    struct Spec {
        double carrier_hz, mod_hz;
        unsigned on_samples, period_samples;    // period 0 = continuous
        bool table;                             // city_ in place of carrier and mod
    };
    static constexpr int SR = chan::SAMPLE_RATE;
    static constexpr Spec SPECS[] = {
        { 0.0,   0.0,   0,       0,       false },  // Off
        { 600.0, 120.0, 0,       0,       false },  // Dial, continuous
        { 420.0,  40.0, 2 * SR,  6 * SR,  true  },  // Ringback 2s/4s
        { 600.0, 120.0, SR / 2,  SR,      false },  // Busy 0.5s/0.5s
        { 600.0, 120.0, SR / 4,  SR / 2,  false }   // Reorder 0.25s/0.25s
    };

    const SineTable&   tbl_;
    std::vector<float> city_;           // one period of ringback, peak 1
    float amp_ = 0.0f;                  // peak level, linear
    float mod_ = 1.0f;                  // modulation depth
    float mod_amp_ = 0.0f;              // amp_ / (1 + mod_), so the peak is amp_
};
