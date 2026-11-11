// ringdet.cpp - ring heard on a circuit. See ringdet.h.

#include "ringdet.h"

#include <algorithm>
#include <cmath>

#include "util.h"

using chan::SAMPLE_RATE;

// audio.md 9.5: 20Hz ring. 4800 samples is 100ms and two cycles, so the
// Goertzel's frequency is bin 2 exactly and DC and 60Hz fall on the Hann
// window's nulls. The amplitude of a sine through the window is 4|X|/N. Ring
// is nearly free of even harmonics and a plug's click is not, so 40Hz (bin 4)
// must be PURE_DB below 20Hz as well.
static const unsigned BLOCK      = 4800;
static const double   HZ         = 20.0;
static const double   ON_DBFS    = -50.0;
static const double   PURE_DB    = 20.0;
static const int      ON_BLOCKS  = 3;                          // 300 ms
static const int      OFF_BLOCKS = 3;                          // 300 ms
static_assert(SAMPLE_RATE % (BLOCK / 2) == 0 && SAMPLE_RATE / (BLOCK / 2) == 20,
              "BLOCK must be two cycles of 20Hz");

// prepare()                                                          [startup]
void RingDetector::prepare()
{
    win_.assign(BLOCK, 0.0f);
    for (unsigned i = 0; i < BLOCK; ++i)
        win_[i] = (float)(0.5 - 0.5 * std::cos(2.0 * M_PI * i / BLOCK));
}

// step()                                                               [audio]
//   At the end of each 100ms block the 20Hz amplitude is judged against
//   ON_DBFS, and `ringing` posted when the debounce turns. The block boundary
//   is shared by every circuit, so one counter serves them all.
void RingDetector::step(const float* capf, unsigned period, int ncap)
{
    const double coeff  = 2.0 * std::cos(2.0 * M_PI * HZ / SAMPLE_RATE);
    const double coeff2 = 2.0 * std::cos(2.0 * M_PI * 2.0 * HZ / SAMPLE_RATE);
    for (int slot = 1; slot <= ncap; ++slot) {
        if (!chan::is_circuit_slot(slot)) continue;
        const float* src = &capf[(size_t)(slot - 1) * period];
        Det& r = det_[slot];
        unsigned n = n_;
        for (unsigned i = 0; i < period; ++i) {
            const double x  = (double)(src[i] * win_[n]);
            const double s0 = x + coeff * r.s1 - r.s2;
            r.s2 = r.s1;
            r.s1 = s0;
            const double h0 = x + coeff2 * r.h1 - r.h2;
            r.h2 = r.h1;
            r.h1 = h0;
            if (++n < BLOCK) continue;
            n = 0;

            const double mag2 = r.s1 * r.s1 + r.s2 * r.s2 - coeff * r.s1 * r.s2;
            const double hag2 = r.h1 * r.h1 + r.h2 * r.h2 - coeff2 * r.h1 * r.h2;
            const double amp  = 4.0 * std::sqrt(std::max(mag2, 0.0)) / BLOCK;
            const double amp2 = 4.0 * std::sqrt(std::max(hag2, 0.0)) / BLOCK;
            r.s1 = r.s2 = r.h1 = r.h2 = 0.0;
            const double db = lin_to_db(amp);
            if (db >= ON_DBFS && db - lin_to_db(amp2) >= PURE_DB) {
                r.below = 0;
                if (r.above < ON_BLOCKS) ++r.above;
            } else {
                r.above = 0;
                if (r.below < OFF_BLOCKS) ++r.below;
            }
            if (!r.on && r.above >= ON_BLOCKS) { r.on = true;  post_result(sh_, Topic::Ringing, slot, "on"); }
            if (r.on && r.below >= OFF_BLOCKS) { r.on = false; post_result(sh_, Topic::Ringing, slot, "off"); }
        }
    }
    n_ = (n_ + period) % BLOCK;
}
