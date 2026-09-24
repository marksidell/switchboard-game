// dsp.cpp - the sine table, the filter designs and the limiter. The per-sample
// code (BiquadState::run, Limiter::run, the table lookups) is inline in dsp.h;
// what is here runs once, at startup.

#include "dsp.h"

#include <algorithm>
#include <complex>

// SineTable::SineTable()                                             [startup]
//   One cycle of a unit sine, 4096 points.
SineTable::SineTable()
{
    for (int i = 0; i < N; ++i)
        t_[i] = (float)std::sin(2.0 * M_PI * (double)i / (double)N);
}

// ---------------------------------------------------------------- butterworth

// normalise()                                                        [startup]
//   Filter formulas produce six coefficients with a0 != 1. Divides all of
//   them by a0 and packs the five that remain into a Biquad.
static Biquad normalise(double b0, double b1, double b2,
                        double a0, double a1, double a2)
{
    Biquad q;
    q.b0 = b0 / a0; q.b1 = b1 / a0; q.b2 = b2 / a0;
    q.a1 = a1 / a0; q.a2 = a2 / a0;
    return q;
}

// butter_lowpass()                                                   [startup]
//   Robert Bristow-Johnson's "Audio EQ Cookbook" low-pass with Q = 1/sqrt(2),
//   which is the Butterworth (maximally flat) case. w0 is the cutoff as an
//   angle per sample.
Biquad butter_lowpass(double fc, double fs)
{
    const double w0 = 2.0 * M_PI * fc / fs;
    const double c  = std::cos(w0), s = std::sin(w0);
    const double al = s / (2.0 * M_SQRT1_2);          // Q = 1/sqrt(2)
    return normalise((1.0 - c) / 2.0, 1.0 - c, (1.0 - c) / 2.0,
                     1.0 + al, -2.0 * c, 1.0 - al);
}

// butter_highpass()                                                  [startup]
//   The cookbook high-pass, same Q. Same denominator as the low-pass; only
//   the numerator differs.
Biquad butter_highpass(double fc, double fs)
{
    const double w0 = 2.0 * M_PI * fc / fs;
    const double c  = std::cos(w0), s = std::sin(w0);
    const double al = s / (2.0 * M_SQRT1_2);
    return normalise((1.0 + c) / 2.0, -(1.0 + c), (1.0 + c) / 2.0,
                     1.0 + al, -2.0 * c, 1.0 - al);
}

// ---------------------------------------------------------------- elliptic
//
// The design follows Orfanidis, "Lecture Notes on Elliptic Filter Design": the
// Landen/descending-modulus recursions for the Jacobi elliptic functions, the
// degree equation solved through the nome, and poles and zeros read off cd().
// It is written out here rather than taken from a library because the only
// dependency that would supply it is a large one, and because station 8.8 puts
// a requirement on the realised stopband that a unit test has to check anyway.
//
// Convention: the normalised functions carry the argument in units of K(k), so
// cde(u,k) = cd(u*K(k), k). That is what makes the recursions this tidy.
//
// The design in plain terms, as elliptic_lowpass() does it:
//
//   1. Prewarp the two edge frequencies, so that after the bilinear transform
//      (step 6) they land where they were asked for.
//   2. k = passband edge / stopband edge: how sharp the transition must be.
//   3. For a fixed order N, the "degree equation" ties k to a second number
//      k1 that sets how deep the stopband and how flat the passband can be.
//      Solve it for k1.
//   4. From k1 and the required stopband depth, get the passband ripple.
//   5. Place the zeros (on the frequency axis, in the stopband - these are the
//      notches that make the stopband deep) and the poles (which shape the
//      passband), N/2 of each as conjugate pairs, using the Jacobi elliptic
//      function cd(). Each pole pair plus zero pair is one analog biquad.
//   6. Turn each analog biquad into a digital one with the bilinear transform.
//
// The helper functions below are the elliptic-function machinery that steps 3
// and 5 need. They are standard numerical recipes and can be read as black
// boxes; the unit test checks the result, not the machinery.

typedef std::complex<double> cplx;

// landen()                                                           [startup]
//   The descending Landen sequence for modulus k: each term is
//   (1 - k') / (1 + k') of the one before, where k' = sqrt(1 - k^2). The
//   terms shrink extremely fast (0.64, 0.13, 0.0044, 5e-6, ...), and an
//   elliptic function at a tiny modulus is simply a sine or cosine, so the
//   sequence is how the functions below are evaluated: start from the cosine
//   and climb back up the sequence. Stops when a term is effectively zero.
static std::vector<double> landen(double k)
{
    std::vector<double> v;
    for (int n = 0; n < 12 && k > 1e-16; ++n) {
        const double kp = std::sqrt(1.0 - k * k);
        k = (1.0 - kp) / (1.0 + kp);
        v.push_back(k);
    }
    if (v.empty()) v.push_back(0.0);
    return v;
}

// ellipk()                                                           [startup]
//   Complete elliptic integral of the first kind, by the arithmetic-geometric
//   mean: K(k) = pi / (2 * AGM(1, k')). The AGM repeatedly replaces a pair
//   with its arithmetic and geometric means until they agree, which takes
//   about five iterations to machine precision.
static double ellipk(double k)
{
    double a = 1.0, b = std::sqrt(1.0 - k * k);
    for (int i = 0; i < 60 && std::fabs(a - b) > 1e-16 * a; ++i) {
        const double an = 0.5 * (a + b);
        b = std::sqrt(a * b);
        a = an;
    }
    return M_PI / (2.0 * a);
}

// nome_to_modulus()                                                  [startup]
//   Modulus from the nome, k = theta2(q)^2 / theta3(q)^2. The nome q is
//   another way of stating an elliptic modulus in which the degree equation
//   becomes simple multiplication (step 3 above); this converts back. The
//   series converge in a handful of terms for the tiny q this design produces.
static double nome_to_modulus(double q)
{
    double num = 0.0, den = 1.0;
    for (int n = 0; n < 24; ++n) num += std::pow(q, (double)n * (n + 1));
    for (int n = 1; n < 24; ++n) den += 2.0 * std::pow(q, (double)n * n);
    const double t2 = 2.0 * std::pow(q, 0.25) * num;
    return (t2 * t2) / (den * den);
}

// cde_impl()                                                         [startup]
//   The Jacobi elliptic function cd(u K, k), given the Landen sequence v for
//   k: start from cos(u pi/2), which is the answer at modulus zero, and apply
//   the ascending recursion once per term, smallest term first. Templated so
//   the same code serves a real argument (for the zeros) and a complex one
//   (for the poles).
template <typename T>
static T cde_impl(T u, const std::vector<double>& v)
{
    T w = std::cos(u * (M_PI / 2.0));
    for (int n = (int)v.size() - 1; n >= 0; --n)
        w = (1.0 + v[n]) * w / (1.0 + v[n] * w * w);
    return w;
}

// cde()                                                              [startup]
//   The real and complex instantiations of cde_impl().
static double cde(double u, const std::vector<double>& v) { return cde_impl<double>(u, v); }
static cplx   cde(cplx   u, const std::vector<double>& v) { return cde_impl<cplx>(u, v); }

// asne()                                                             [startup]
//   Inverse of sne() - the normalised inverse Jacobi sn: given w = sn(u K, k),
//   returns u. Needed once, to find how far off the frequency axis the poles
//   sit. Obtained by inverting the forward recursion one level at a time.
//   Each step solves v*w*x^2 - (1+v)*x + w = 0 for the root that tends to w as
//   v tends to zero; the form below is that root rationalised, which avoids
//   the cancellation the quadratic formula would suffer. At the bottom of the
//   sequence sn is a sine, so the last step is asin().
static cplx asne(cplx w, double k)
{
    const std::vector<double> v = landen(k);
    for (size_t n = 0; n < v.size(); ++n) {
        const double vn = v[n];
        const cplx   r  = std::sqrt(cplx(1.0 + vn, 0.0) * (1.0 + vn) - 4.0 * vn * w * w);
        w = 2.0 * w / ((1.0 + vn) + r);
    }
    return std::asin(w) * (2.0 / M_PI);
}

// One section of the normalised analog prototype: a zero pair on the frequency
// axis at +-j*wz, and a conjugate pole pair, with the passband edge at 1.
struct ProtoSection {
    double wz;        // zero frequency, normalised
    cplx   p;         // pole, left half plane
};

// elliptic_prototype()                                               [startup]
//   Steps 2 to 5 of the design at the top of this section, shared by the
//   low-pass and the high-pass: everything except the frequency
//   denormalisation and the bilinear transform. `k` is the selectivity, always
//   less than 1: passband edge over stopband edge for a low-pass, and the
//   reciprocal of that for a high-pass.
static std::vector<ProtoSection> elliptic_prototype(int order, double k,
                                                    double stop_db, double& ripple_db)
{
    const std::vector<double> vk = landen(k);

    // Step 3. Degree equation, N*K'(k)/K(k) = K'(k1)/K(k1), solved for k1 through the
    // nome. The order is fixed by station 8.8 and the stopband by the option,
    // so the free parameter is the passband ripple - which is the right thing
    // to spend the spare order on for a feed that is already band-limited to a
    // telephone.
    const double r  = ellipk(std::sqrt(1.0 - k * k)) / ellipk(k);
    const double q1 = std::exp(-M_PI * (double)order * r);
    const double k1 = nome_to_modulus(q1);

    // Step 4. es and ep are the stopband and passband "ripple factors": the
    // stopband gain is 1/sqrt(1 + es^2), the passband dips to 1/sqrt(1 + ep^2).
    const double es = std::sqrt(std::pow(10.0, stop_db / 10.0) - 1.0);
    const double ep = k1 * es;
    ripple_db = 10.0 * std::log10(1.0 + ep * ep);

    // Step 5. v0 is how far the poles sit from the frequency axis, in the
    // normalised units cde() works in; it comes out real.
    const cplx v0 = -cplx(0.0, 1.0) * asne(cplx(0.0, 1.0 / ep), k1) / (double)order;

    std::vector<ProtoSection> out;
    const int L = order / 2;
    for (int i = 1; i <= L; ++i) {
        const double ui = (2.0 * i - 1.0) / (double)order;

        const double zeta = cde(ui, vk);
        cplx p = cplx(0.0, 1.0) * cde(cplx(ui, 0.0) - cplx(0.0, 1.0) * v0, vk);

        // The pole set is symmetric about the imaginary axis; keep the stable
        // half whichever way the branch of asne() came out.
        if (p.real() > 0.0) p = cplx(-p.real(), p.imag());

        out.push_back({ 1.0 / (k * zeta), p });         // zero at 1/(k*zeta)
    }
    return out;
}

// elliptic_lowpass()                                                 [startup]
//   See dsp.h, and the six steps at the top of this section.
std::vector<Biquad> elliptic_lowpass(int order, double fpass, double fstop,
                                     double stop_db, double fs, double& ripple_db)
{
    std::vector<Biquad> secs;
    if (order < 2 || (order % 2) != 0 || fstop <= fpass) return secs;

    // Step 1. Prewarp both edges, so the bilinear transform lands them where
    // they were asked for rather than where tan() moves them.
    const double c  = 2.0 * fs;
    const double Wp = c * std::tan(M_PI * fpass / fs);
    const double Ws = c * std::tan(M_PI * fstop / fs);

    const std::vector<ProtoSection> proto =
        elliptic_prototype(order, Wp / Ws, stop_db, ripple_db);

    for (const ProtoSection& ps : proto) {
        // Analog section, denormalised to rad/s and scaled to unity at DC:
        //   H(s) = (s^2 + (wz*Wp)^2) / (s^2 - 2 Re(p) Wp s + |p|^2 Wp^2)
        const double wz = ps.wz * Wp;
        const double b2s = 1.0, b1s = 0.0, b0s = wz * wz;
        const double a2s = 1.0;
        const double a1s = -2.0 * ps.p.real() * Wp;
        const double a0s = std::norm(ps.p) * Wp * Wp;
        const double g   = a0s / b0s;                   // unity at DC

        // Step 6. Bilinear transform, s -> c (1 - z^-1) / (1 + z^-1).
        const double cc = c * c;
        secs.push_back(normalise(g * (b2s * cc + b1s * c + b0s),
                                 g * 2.0 * (b0s - b2s * cc),
                                 g * (b2s * cc - b1s * c + b0s),
                                 a2s * cc + a1s * c + a0s,
                                 2.0 * (a0s - a2s * cc),
                                 a2s * cc - a1s * c + a0s));
    }
    return secs;
}

// elliptic_highpass()                                                [startup]
//   The same prototype with the low-pass-to-high-pass substitution s -> Wp/s
//   applied before the bilinear transform. That maps the prototype's passband
//   edge to Wp and its stopband edge to Wp * k, so the selectivity handed to
//   the prototype is the stopband edge over the passband edge - the reciprocal
//   of the low-pass case. Per section the substitution turns
//   (s^2 + wz^2) / (s^2 - 2 Re(p) s + |p|^2) into
//   (wz^2 s^2 + Wp^2) / (|p|^2 s^2 - 2 Re(p) Wp s + Wp^2), and the gain is
//   normalised as w -> infinity rather than at DC.
std::vector<Biquad> elliptic_highpass(int order, double fpass, double fstop,
                                      double stop_db, double fs, double& ripple_db)
{
    std::vector<Biquad> secs;
    if (order < 2 || (order % 2) != 0 || fstop >= fpass) return secs;

    const double c  = 2.0 * fs;
    const double Wp = c * std::tan(M_PI * fpass / fs);
    const double Ws = c * std::tan(M_PI * fstop / fs);

    const std::vector<ProtoSection> proto =
        elliptic_prototype(order, Ws / Wp, stop_db, ripple_db);

    for (const ProtoSection& ps : proto) {
        const double b2s = ps.wz * ps.wz, b1s = 0.0, b0s = Wp * Wp;
        const double a2s = std::norm(ps.p);
        const double a1s = -2.0 * ps.p.real() * Wp;
        const double a0s = Wp * Wp;
        const double g   = a2s / b2s;                   // unity as w -> infinity

        const double cc = c * c;
        secs.push_back(normalise(g * (b2s * cc + b1s * c + b0s),
                                 g * 2.0 * (b0s - b2s * cc),
                                 g * (b2s * cc - b1s * c + b0s),
                                 a2s * cc + a1s * c + a0s,
                                 2.0 * (a0s - a2s * cc),
                                 a2s * cc - a1s * c + a0s));
    }
    return secs;
}

// cascade_mag_db()                                                       [any]
//   z is the point on the unit circle for frequency hz. Each section's H(z) is
//   evaluated there (in z^-1 form: the z below is already e^-jw) and the
//   results multiplied; the cascade's response is the product of its
//   sections'.
double cascade_mag_db(const std::vector<Biquad>& secs, double hz, double fs)
{
    const cplx z = std::exp(cplx(0.0, -2.0 * M_PI * hz / fs));
    cplx h(1.0, 0.0);
    for (size_t i = 0; i < secs.size(); ++i) {
        const Biquad& q = secs[i];
        h *= (q.b0 + q.b1 * z + q.b2 * z * z) / (1.0 + q.a1 * z + q.a2 * z * z);
    }
    return 20.0 * std::log10(std::max(std::abs(h), 1e-30));
}

// ---------------------------------------------------------------- limiter

// Limiter::init()                                                    [startup]
//   rel_ is the fraction of the remaining distance to unity gain recovered
//   each sample: 1 - e^(-1/(release * fs)), which for 100 ms at 48 kHz is
//   about 0.0002 - i.e. 63% of the way back in 100 ms.
void Limiter::init(double threshold_db, double release_s, double fs)
{
    thresh_ = std::pow(10.0, threshold_db / 20.0);
    rel_    = 1.0 - std::exp(-1.0 / (release_s * fs));
    gain_   = 1.0;
    active_ = 0;
}
