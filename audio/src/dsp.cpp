#include "dsp.h"

#include <algorithm>
#include <complex>

SineTable::SineTable()
{
    for (int i = 0; i < N; ++i)
        t_[i] = (float)std::sin(2.0 * M_PI * (double)i / (double)N);
}

// ---------------------------------------------------------------- butterworth

static Biquad normalise(double b0, double b1, double b2,
                        double a0, double a1, double a2)
{
    Biquad q;
    q.b0 = b0 / a0; q.b1 = b1 / a0; q.b2 = b2 / a0;
    q.a1 = a1 / a0; q.a2 = a2 / a0;
    return q;
}

Biquad butter_lowpass(double fc, double fs)
{
    const double w0 = 2.0 * M_PI * fc / fs;
    const double c  = std::cos(w0), s = std::sin(w0);
    const double al = s / (2.0 * M_SQRT1_2);          // Q = 1/sqrt(2)
    return normalise((1.0 - c) / 2.0, 1.0 - c, (1.0 - c) / 2.0,
                     1.0 + al, -2.0 * c, 1.0 - al);
}

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

typedef std::complex<double> cplx;

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

// Complete elliptic integral of the first kind, by the arithmetic-geometric
// mean: K(k) = pi / (2 * AGM(1, k')).
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

// Modulus from the nome, k = theta2(q)^2 / theta3(q)^2. The series converge in
// a handful of terms for the tiny q this design produces.
static double nome_to_modulus(double q)
{
    double num = 0.0, den = 1.0;
    for (int n = 0; n < 24; ++n) num += std::pow(q, (double)n * (n + 1));
    for (int n = 1; n < 24; ++n) den += 2.0 * std::pow(q, (double)n * n);
    const double t2 = 2.0 * std::pow(q, 0.25) * num;
    return (t2 * t2) / (den * den);
}

template <typename T>
static T cde_impl(T u, const std::vector<double>& v)
{
    T w = std::cos(u * (M_PI / 2.0));
    for (int n = (int)v.size() - 1; n >= 0; --n)
        w = (1.0 + v[n]) * w / (1.0 + v[n] * w * w);
    return w;
}

static double cde(double u, const std::vector<double>& v) { return cde_impl<double>(u, v); }
static cplx   cde(cplx   u, const std::vector<double>& v) { return cde_impl<cplx>(u, v); }

// Inverse of sne(), obtained by inverting the forward recursion one level at a
// time. Each step solves v*w*x^2 - (1+v)*x + w = 0 for the root that tends to w
// as v tends to zero; the form below is that root rationalised, which avoids
// the cancellation the quadratic formula would suffer.
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

std::vector<Biquad> elliptic_lowpass(int order, double fpass, double fstop,
                                     double stop_db, double fs, double& ripple_db)
{
    std::vector<Biquad> secs;
    if (order < 2 || (order % 2) != 0) return secs;     // even orders only

    // Prewarp both edges, so the bilinear transform lands them where they were
    // asked for rather than where tan() moves them.
    const double c  = 2.0 * fs;
    const double Wp = c * std::tan(M_PI * fpass / fs);
    const double Ws = c * std::tan(M_PI * fstop / fs);

    const double k  = Wp / Ws;                          // selectivity
    const std::vector<double> vk = landen(k);

    // Degree equation, N*K'(k)/K(k) = K'(k1)/K(k1), solved for k1 through the
    // nome. The order is fixed by station 8.8 and the stopband by the option,
    // so the free parameter is the passband ripple - which is the right thing
    // to spend the spare order on for a feed that is already band-limited to a
    // telephone.
    const double r  = ellipk(std::sqrt(1.0 - k * k)) / ellipk(k);
    const double q1 = std::exp(-M_PI * (double)order * r);
    const double k1 = nome_to_modulus(q1);

    const double es = std::sqrt(std::pow(10.0, stop_db / 10.0) - 1.0);
    const double ep = k1 * es;
    ripple_db = 10.0 * std::log10(1.0 + ep * ep);

    const cplx v0 = -cplx(0.0, 1.0) * asne(cplx(0.0, 1.0 / ep), k1) / (double)order;

    const int L = order / 2;
    for (int i = 1; i <= L; ++i) {
        const double ui = (2.0 * i - 1.0) / (double)order;

        const double zeta = cde(ui, vk);
        const double Oz   = 1.0 / (k * zeta);           // zero, normalised to Wp
        cplx p = cplx(0.0, 1.0) * cde(cplx(ui, 0.0) - cplx(0.0, 1.0) * v0, vk);

        // The pole set is symmetric about the imaginary axis; keep the stable
        // half whichever way the branch of asne() came out.
        if (p.real() > 0.0) p = cplx(-p.real(), p.imag());

        // Analog section, denormalised to rad/s and scaled to unity at DC:
        //   H(s) = (s^2 + (Oz*Wp)^2) / (s^2 - 2 Re(p) Wp s + |p|^2 Wp^2)
        const double wz = Oz * Wp;
        const double b2s = 1.0, b1s = 0.0, b0s = wz * wz;
        const double a2s = 1.0;
        const double a1s = -2.0 * p.real() * Wp;
        const double a0s = std::norm(p) * Wp * Wp;
        const double g   = a0s / b0s;                   // unity at DC

        // Bilinear transform, s -> c (1 - z^-1) / (1 + z^-1).
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

void Limiter::init(double threshold_db, double release_s, double fs)
{
    thresh_ = std::pow(10.0, threshold_db / 20.0);
    rel_    = 1.0 - std::exp(-1.0 / (release_s * fs));
    gain_   = 1.0;
    active_ = 0;
}
