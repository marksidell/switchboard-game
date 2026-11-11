// tones.cpp - the trunk tones. See tones.h.

#include "tones.h"

#include <algorithm>
#include <cmath>

#include "cityring.h"
#include "util.h"

// prepare()                                                          [startup]
//   Ringback's one period summed from cityring.h and set to a peak of 1, so
//   the level is its peak as it is the other tones'.
void TrunkTones::prepare(double tone_db, double mod)
{
    amp_     = (float)db_to_lin(tone_db);
    mod_     = (float)mod;
    mod_amp_ = (float)(db_to_lin(tone_db) / (1.0 + mod));

    std::vector<double> w(CITY_RING_PERIOD, 0.0);
    double peak = 0.0;
    for (unsigned i = 0; i < CITY_RING_PERIOD; ++i) {
        const double t = (double)i / SR;
        for (const CityPartial& c : CITY_RING)
            w[i] += c.amp * std::cos(2.0 * M_PI * c.n * 20.0 * t + c.phase);
        peak = std::max(peak, std::fabs(w[i]));
    }
    city_.assign(CITY_RING_PERIOD, 0.0f);
    for (unsigned i = 0; i < CITY_RING_PERIOD; ++i) city_[i] = (float)(w[i] / peak);
}

// start()                                                              [audio]
void TrunkTones::start(State& s, ToneKind k) const
{
    s.tone = k;
    s.ph = s.mph = s.cad = 0;
    s.inc  = SineTable::inc_q32(SPECS[(int)k].carrier_hz, SR);
    s.minc = SineTable::inc_q32(SPECS[(int)k].mod_hz, SR);
}

// name()                                                               [any]
const char* TrunkTones::name(ToneKind k)
{
    static const char* const NAMES[] = { "", "dial", "ringback", "busy", "reorder" };
    return NAMES[(int)k];
}
