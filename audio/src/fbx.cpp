// fbx.cpp - the monitor's feedback eliminator. See fbx.h.

#include "fbx.h"

#include <algorithm>
#include <cmath>

#include "util.h"

FeedbackEliminator::~FeedbackEliminator()
{
    if (plan_) fftwf_destroy_plan(plan_);
    if (in_)   fftwf_free(in_);
    if (out_)  fftwf_free(out_);
}

// prepare()                                                          [startup]
//   FFTW_ESTIMATE: a 512-point plan is cheap either way, and measuring would
//   take minutes the detector's wisdom does not cover.
bool FeedbackEliminator::prepare(double fs, bool on)
{
    fs_ = fs;
    on_ = on;
    ring_.assign(N, 0.0f);
    win_.resize(N);
    for (int i = 0; i < N; ++i) win_[i] = (float)(0.5 - 0.5 * std::cos(2.0 * M_PI * i / N));
    in_  = fftwf_alloc_real(N);
    out_ = fftwf_alloc_complex(N / 2 + 1);
    if (!in_ || !out_) { log_line("fbx: allocation failed"); return false; }
    plan_ = fftwf_plan_dft_r2c_1d(N, in_, out_, FFTW_ESTIMATE);
    if (!plan_) { log_line("fbx: FFT plan failed"); return false; }
    return true;
}

// run()                                                                [audio]
double FeedbackEliminator::run(double x)
{
    if (!on_) return x;
    double y = x;
    for (Notch& n : n_)
        if (n.on) y = n.s.run(n.c, y);
    // The monitor's signal is already held under 3.6 kHz, 70 dB down by 5.6
    // (audio.md 10.1), so taking every 4th sample aliases nothing that matters.
    if (++decim_ == DECIM) {
        decim_ = 0;
        ring_[(size_t)ring_w_] = (float)y;
        ring_w_ = (ring_w_ + 1) % N;
        if (++since_ == HOP) { since_ = 0; analyse(); }
    }
    return y;
}

// analyse()                                                            [audio]
//   One frame: is there a single tone standing far above the rest, and has it
//   held long enough? 512-point FFT, no allocation.
void FeedbackEliminator::analyse()
{
    ++frame_;
    for (int i = 0; i < N; ++i) in_[i] = ring_[(size_t)((ring_w_ + i) % N)] * win_[(size_t)i];
    fftwf_execute(plan_);

    const double fa  = fs_ / DECIM;                     // 12 kHz
    const int    hi  = std::min(N / 2 - 1, (int)std::floor(HIGH_HZ * N / fa));
    auto power = [&](int b) {
        return (double)out_[b][0] * out_[b][0] + (double)out_[b][1] * out_[b][1];
    };
    // One tier's test over the bins from lo up: its loudest bin, and whether
    // it stands `prom` over the rest's mean power and `iso` over the rest's
    // loudest bin - the rest being everything outside the peak's own +-4
    // bins, where a Hann window's leakage is over.
    struct Peak { int k; bool howl; };
    auto test = [&](int lo, double prom, double iso) -> Peak {
        int    k = lo;
        double pk = 0.0;
        for (int b = lo; b <= hi; ++b)
            if (const double p = power(b); p > pk) { pk = p; k = b; }
        // A Hann-windowed sine of amplitude A peaks at A N / 4.
        const double amp_db = 10.0 * std::log10(pk + 1e-30) - 20.0 * std::log10(N / 4.0);
        double other = 0.0, sum = 0.0;
        int    nrest = 0;
        for (int b = lo; b <= hi; ++b) {
            if (std::abs(b - k) <= 4) continue;
            const double p = power(b);
            other = std::max(other, p);
            sum  += p;
            ++nrest;
        }
        const double mean = sum / (double)std::max(nrest, 1);
        return { k, amp_db >= MIN_DBFS
                    && 10.0 * std::log10(pk / (mean + 1e-30)) >= prom
                    && 10.0 * std::log10(pk / (other + 1e-30)) >= iso };
    };
    // The whole band, strictly; and above UPPER_HZ, where the room's howls
    // have been (1.5-2.6 kHz) and the trunk tones and voices' strong low
    // harmonics are not, a howl with a neighbour close in level or wandering
    // two bins - one that rings through the guest's speech.
    const Peak all   = test((int)std::ceil(LOW_HZ * N / fa), PROMINENCE_DB, ISOLATION_DB);
    const Peak upper = test((int)std::ceil(UPPER_HZ * N / fa), UPPER_PROMINENCE_DB, UPPER_ISOLATION_DB);
    int k, drift;
    if (all.howl)        { k = all.k;   drift = 1; }
    else if (upper.howl) { k = upper.k; drift = UPPER_DRIFT; }
    else                 { cand_bin_ = -1; cand_n_ = 0; return; }
    if (cand_bin_ < 0 || std::abs(k - cand_bin_) > drift) { cand_bin_ = k; cand_n_ = 1; return; }
    cand_bin_ = k;
    if (++cand_n_ < HOLD_FRAMES) return;

    // The frequency between bins, from the parabola through the peak and its
    // neighbours in dB: within a few Hz for a steady tone.
    auto db = [&](int b) {
        return 10.0 * std::log10((double)out_[b][0] * out_[b][0] + (double)out_[b][1] * out_[b][1] + 1e-30);
    };
    const double l = db(k - 1), c = db(k), r = db(k + 1);
    const double den = l - 2.0 * c + r;
    const double d = (den != 0.0) ? std::clamp(0.5 * (l - r) / den, -0.5, 0.5) : 0.0;
    place((k + d) * fa / N);
    cand_bin_ = -1;
    cand_n_ = 0;
}

// place()                                                              [audio]
//   A notch on hz: deepen the one it falls in, or take a free one, or move
//   the one least recently used. RBJ peaking section, cut by `db`. Computing
//   coefficients is arithmetic only.
void FeedbackEliminator::place(double hz)
{
    Notch* t = nullptr;
    for (Notch& n : n_)
        if (n.on && std::fabs(hz - n.hz) < std::max(n.hz / Q, 25.0)) { t = &n; break; }
    double db = FIRST_DB;
    if (t) {
        db = std::max(MAX_DB, t->db + STEP_DB);
        hz = t->hz;                     // keep the centre; the state stays good
    } else {
        for (Notch& n : n_) if (!n.on) { t = &n; break; }
        if (!t) {
            t = &n_[0];
            for (Notch& n : n_) if (n.used < t->used) t = &n;
        }
        t->s.reset();
    }
    const double A  = std::pow(10.0, db / 40.0);
    const double w0 = 2.0 * M_PI * hz / fs_;
    const double al = std::sin(w0) / (2.0 * Q);
    const double cw = std::cos(w0);
    const double a0 = 1.0 + al / A;
    t->c.b0 = (1.0 + al * A) / a0;
    t->c.b1 = (-2.0 * cw) / a0;
    t->c.b2 = (1.0 - al * A) / a0;
    t->c.a1 = (-2.0 * cw) / a0;
    t->c.a2 = (1.0 - al / A) / a0;
    t->on   = true;
    t->hz   = hz;
    t->db   = db;
    t->used = frame_;
    ++events_;
    last_hz_ = hz;
    last_db_ = db;
}

FeedbackEliminator::Event FeedbackEliminator::take()
{
    Event e { events_, last_hz_, last_db_ };
    events_ = 0;
    return e;
}

int FeedbackEliminator::active() const
{
    int n = 0;
    for (const Notch& x : n_) n += x.on;
    return n;
}
