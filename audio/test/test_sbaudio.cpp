// test_sbaudio.cpp - the checks that do not need hardware.
//
// Two of them are required rather than optional. audio.md 10.1 asks for a unit
// test comparing the realised stopband at 6000Hz against the requirement,
// because the lowest pilot sits exactly there and 70dB is what keeps it out of
// the loudspeaker. And the detector arithmetic is worth exercising against a
// synthetic signal for the same reason pilot_loopback_test.cpp has -S: the
// alternative is discovering a sign or an off-by-one with a switchboard in
// front of you.
//
//     ctest --test-dir build        or        ./build/sbaudio_test

#include <cmath>
#include <cstdio>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

#include "../src/channels.h"
#include "../src/detector.h"
#include "../src/dsp.h"
#include "../src/ipc.h"
#include "../src/util.h"
#include "../src/vad.h"
#include "../src/alsa.h"
#include "../src/engine.h"
#include "../src/options.h"

// Count of failed checks; main() returns non-zero if any failed.
static int failures = 0;

// check()
//   Prints one result line and counts a failure.
static void check(bool ok, const char* what)
{
    std::printf("  %-58s %s\n", what, ok ? "ok" : "FAIL");
    if (!ok) ++failures;
}

// check_near()
//   As check(), for a number that must be within tol of want; prints both.
static void check_near(double got, double want, double tol, const char* what)
{
    const bool ok = std::fabs(got - want) <= tol;
    std::printf("  %-58s %s  (%.3f, wanted %.3f +-%.3f)\n",
                what, ok ? "ok" : "FAIL", got, want, tol);
    if (!ok) ++failures;
}

// ---------------------------------------------------------------- filters

// test_monitor_filter()
//   Designs the monitor low-pass exactly as the engine does and checks its
//   response at the frequencies that matter; also the Butterworth sections.
static void test_monitor_filter()
{
    std::printf("monitor low-pass (station 8.8: 3.6k pass, 5.6k stop, 70 dB)\n");

    double ripple = 0.0;
    const std::vector<Biquad> lp =
        elliptic_lowpass(8, 3600.0, 5600.0, 70.0, chan::SAMPLE_RATE, ripple);

    check(lp.size() == 4, "eighth order is four second-order sections");
    check(ripple < 0.1, "passband ripple is negligible at this order");

    const double fs = chan::SAMPLE_RATE;
    check_near(cascade_mag_db(lp, 100.0,  fs), 0.0, 0.1, "unity at 100 Hz");
    check_near(cascade_mag_db(lp, 3000.0, fs), 0.0, 0.1, "unity at 3 kHz");
    check(cascade_mag_db(lp, 3600.0, fs) > -0.5, "passband edge is not down");

    // The requirement. The lowest pilot is at 6000.00 Hz exactly.
    // The equiripple peaks sit exactly on the requirement, so the comparison
    // carries a hundredth of a dB for the arithmetic to land in.
    const double TOL = 0.01;
    const double at_6k = cascade_mag_db(lp, 6000.0, fs);
    check(at_6k <= -70.0 + TOL, "6000 Hz (station 1's pilot) is at least 70 dB down");

    // And every pilot above it, to the top of the comb and the operator tone.
    double worst = -1e9;
    int    worst_bin = 0;
    for (int slot = 1; slot <= chan::N_SLOTS; ++slot) {
        const double a = cascade_mag_db(lp, chan::pilot_hz(slot), fs);
        if (a > worst) { worst = a; worst_bin = chan::pilot_bin(slot); }
    }
    const double at_op = cascade_mag_db(lp, chan::OP_BIN * chan::BIN_HZ, fs);
    std::printf("    worst comb pilot %.1f dB (bin %d), operator tone %.1f dB\n",
                worst, worst_bin, at_op);
    check(worst <= -70.0 + TOL, "every comb pilot is at least 70 dB down");
    check(at_op <= -70.0 + TOL, "the operator tone is at least 70 dB down");

    // The passband edge is an option (audio.md 1.1), so the design has to work
    // somewhere else too.
    double r2 = 0.0;
    const std::vector<Biquad> lp2 =
        elliptic_lowpass(8, 3000.0, 5000.0, 80.0, chan::SAMPLE_RATE, r2);
    check(lp2.size() == 4, "a different passband edge designs too");
    check(cascade_mag_db(lp2, 5000.0, fs) <= -80.0 + TOL, "and meets its own stopband");

    std::printf("high-pass and band-pass\n");
    const Biquad hp = butter_highpass(150.0, fs);
    check_near(cascade_mag_db({ hp }, 150.0, fs), -3.0, 0.2, "150 Hz high-pass is -3 dB at 150 Hz");
    check(cascade_mag_db({ hp }, 1000.0, fs) > -0.2, "and flat at 1 kHz");
    const Biquad vlp = butter_lowpass(3400.0, fs);
    check_near(cascade_mag_db({ vlp }, 3400.0, fs), -3.0, 0.2, "3400 Hz low-pass is -3 dB at 3400 Hz");
    // One second-order section is all audio.md 9.2 specifies, and it is worth
    // knowing what that buys: 10.9 dB at the lowest pilot, not rejection. The
    // pilot residual is therefore part of the speech detector's noise floor,
    // and it is the ratiometric floor+margin term that keeps it from counting,
    // never the absolute --vad-floor.
    check(cascade_mag_db({ vlp }, 6000.0, fs) < -10.0,
          "and puts the lowest pilot 10 dB down (not out - see the comment)");
}

// ---------------------------------------------------------------- detector

// Build one channel's block exactly as the engine renders a pilot: one shared
// 4096-entry table, indexed table[(bin * n) & 4095]. If this and the detector
// ever disagree, the whole scheme is broken, and that is what makes it worth
// generating the test signal this way rather than with sin().
static void add_pilot(float* blk, const SineTable& t, int bin, double db)
{
    const float a = (float)db_to_lin(db);
    for (uint32_t n = 0; n < (uint32_t)chan::FFT_N; ++n)
        blk[n] += a * t.at((uint32_t)bin * n);
}

// add_noise()
//   Adds white noise at `db` (rms, referenced to a full-scale sine) to a
//   4096-sample block, from a simple seeded generator so every run is the
//   same.
static void add_noise(float* blk, double db, unsigned seed)
{
    const double a = db_to_lin(db) * std::sqrt(3.0) * M_SQRT1_2;
    unsigned s = seed;
    for (int n = 0; n < chan::FFT_N; ++n) {
        s = s * 1103515245u + 12345u;
        const double u = ((double)((s >> 16) & 0x7fff) / 16383.5) - 1.0;
        blk[n] += (float)(a * u);
    }
}

// test_detector()
//   Builds one synthetic snapshot - a handful of circuits in known states,
//   everything else silent - runs one hop of the real Detector on it, and
//   checks what it would publish.
static void test_detector()
{
    std::printf("detector (station 8.7, one hop against a synthetic block)\n");

    Shared sh;
    sh.opt.margin_db = 20.0;
    sh.ncap = chan::N_CAP_CH;
    for (int i = 0; i < 2; ++i)
        sh.snap[i].data.assign((size_t)chan::N_CAP_CH * chan::FFT_N, 0.0f);
    sh.snap[0].hop = 1;

    SineTable tbl;
    float* d = sh.snap[0].data.data();
    const double PILOT = -40.0, NOISE = -95.0;

    // Station 5: its own pilot and trunk 2's - a cord joins them.
    float* s5 = d + (size_t)(chan::station_slot(5) - 1) * chan::FFT_N;
    add_pilot(s5, tbl, chan::pilot_bin(chan::station_slot(5)), PILOT);
    add_pilot(s5, tbl, chan::pilot_bin(chan::trunk_slot(2)),   PILOT - 5.0);
    add_noise(s5, NOISE, 1);

    // Trunk 2: the reciprocal.
    float* t2 = d + (size_t)(chan::trunk_slot(2) - 1) * chan::FFT_N;
    add_pilot(t2, tbl, chan::pilot_bin(chan::trunk_slot(2)),   PILOT);
    add_pilot(t2, tbl, chan::pilot_bin(chan::station_slot(5)), PILOT - 5.0);
    add_noise(t2, NOISE, 2);

    // Station 1: idle, its own pilot only, with the operator bridged onto it.
    float* s1 = d + (size_t)(chan::station_slot(1) - 1) * chan::FFT_N;
    add_pilot(s1, tbl, chan::pilot_bin(chan::station_slot(1)), PILOT);
    add_pilot(s1, tbl, chan::OP_BIN, PILOT - 10.0);
    add_noise(s1, NOISE, 3);

    // Station 2: nothing at all - a fault in its own transmit path.
    add_noise(d + (size_t)(chan::station_slot(2) - 1) * chan::FFT_N, NOISE, 4);

    // Station 3: two foreign pilots, which cannot be a topology.
    float* s3 = d + (size_t)(chan::station_slot(3) - 1) * chan::FFT_N;
    add_pilot(s3, tbl, chan::pilot_bin(chan::station_slot(3)), PILOT);
    add_pilot(s3, tbl, chan::pilot_bin(chan::station_slot(7)), PILOT);
    add_pilot(s3, tbl, chan::pilot_bin(chan::trunk_slot(8)),   PILOT);
    add_noise(s3, NOISE, 5);

    // Trunk 4: idle, hearing trunks 2 and 3 at 72dB under its own pilot -
    // the trunk board's strip-to-strip crosstalk (station 8.7, Rev 3.46).
    // Above the noise floor by more than MARGIN_DB, outside PEER_WINDOW_DB.
    const double XTALK = PILOT - 72.0, QUIET = -110.0;
    float* t4 = d + (size_t)(chan::trunk_slot(4) - 1) * chan::FFT_N;
    add_pilot(t4, tbl, chan::pilot_bin(chan::trunk_slot(4)), PILOT);
    add_pilot(t4, tbl, chan::pilot_bin(chan::trunk_slot(2)), XTALK);
    add_pilot(t4, tbl, chan::pilot_bin(chan::trunk_slot(3)), XTALK);
    add_pilot(t4, tbl, chan::OP_BIN, PILOT - 46.0);  // the tap's leak, as station 22's
    add_noise(t4, QUIET, 7);

    // Trunk 6: patched to station 9, with the same crosstalk from trunks 5
    // and 8, and its own pilot 14dB down as it is with the loop closed.
    float* t6 = d + (size_t)(chan::trunk_slot(6) - 1) * chan::FFT_N;
    add_pilot(t6, tbl, chan::pilot_bin(chan::trunk_slot(6)),   PILOT - 14.0);
    add_pilot(t6, tbl, chan::pilot_bin(chan::station_slot(9)), PILOT - 17.0);
    add_pilot(t6, tbl, chan::pilot_bin(chan::trunk_slot(5)),   XTALK);
    add_pilot(t6, tbl, chan::pilot_bin(chan::trunk_slot(8)),   XTALK);
    add_noise(t6, QUIET, 8);

    // Trunk 8: idle, with trunk 7's crosstalk 72dB under its own pilot, and
    // noise close around its own pilot raising that bin's floor 40dB above
    // the others - so measured against each bin's floor the crosstalk looks
    // only 30dB down. The window reads absolute levels (Rev 3.48).
    float* t8 = d + (size_t)(chan::trunk_slot(8) - 1) * chan::FFT_N;
    const int b8 = chan::pilot_bin(chan::trunk_slot(8));
    add_pilot(t8, tbl, b8, PILOT);
    for (int o : {-3, -2, 2, 3}) add_pilot(t8, tbl, b8 + o, PILOT - 35.0);
    add_pilot(t8, tbl, chan::pilot_bin(chan::trunk_slot(7)), XTALK);
    add_noise(t8, QUIET, 9);

    // The tap: its own tone returning on its own channel.
    float* tap = d + (size_t)(chan::TAP_CH - 1) * chan::FFT_N;
    add_pilot(tap, tbl, chan::OP_BIN, -18.0);
    add_noise(tap, NOISE, 6);

    Detector det(sh);
    if (!det.prepare()) { std::printf("  detector prepare FAILED\n"); ++failures; return; }
    det.process_snapshot(0);

    bool f = false;
    Result r;
    std::vector<Result> all;
    while (sh.res_ana.pop(r)) all.push_back(r);
    auto last = [&](Topic t, int idx) {
        std::string v; f = false;
        for (const Result& x : all) if (x.topic == t && x.idx == idx) { v = x.value; f = true; }
        return v;
    };

    check(last(Topic::Peer, chan::station_slot(5)) == "trunk/2" && f,
          "station 5 hears trunk 2");
    check(last(Topic::Peer, chan::trunk_slot(2)) == "station/5" && f,
          "trunk 2 hears station 5 (reciprocity)");
    check(last(Topic::Peer, chan::station_slot(1)) == "" && f,
          "station 1 is idle, and says so with an empty payload");
    check(last(Topic::Op, chan::station_slot(1)) == "on" && f,
          "the operator is bridged to station 1");
    check(last(Topic::Op, chan::station_slot(5)) == "off" && f,
          "and not to station 5");
    check(last(Topic::Peer, chan::station_slot(2)) == "deaf" && f,
          "station 2 cannot hear its own pilot");
    check(last(Topic::Peer, chan::station_slot(3)) == "ambiguous" && f,
          "station 3 hears two foreign pilots");
    check(last(Topic::OpTone, 0) == "ok" && f,
          "the tap hears its own tone");
    check(last(Topic::Peer, chan::trunk_slot(4)) == "" && f,
          "trunk 4 is idle: crosstalk 72dB under its own pilot is not a peer");
    check(last(Topic::Op, chan::trunk_slot(4)) == "off" && f,
          "and the operator tone leaking from the tap is not the operator");
    check(last(Topic::Peer, chan::trunk_slot(8)) == "" && f,
          "trunk 8 is idle though its own floor is raised: the window is absolute");
    check(last(Topic::Peer, chan::trunk_slot(6)) == "station/9" && f,
          "trunk 6 hears station 9 through the same crosstalk");

    // Every other circuit is silence: deaf, and no peer.
    check(last(Topic::Peer, chan::station_slot(10)) == "deaf" && f,
          "an unconnected circuit reads deaf, not idle");

    // Slot 24 has no pilot and no circuit, so nothing may be published for it
    // and nothing may ever be reported as connected to it.
    bool any_noncircuit = false;
    for (const Result& x : all)
        if ((x.topic == Topic::Peer || x.topic == Topic::Op) &&
            (x.idx == chan::TAP_CH || x.idx == chan::MONITOR_CH))
            any_noncircuit = true;
    check(!any_noncircuit,
          "neither the tap nor the monitor publishes a peer or op of its own");
    bool any_station_23 = false;
    for (const Result& x : all)
        if (x.idx > chan::N_STATIONS && x.idx < chan::trunk_slot(1)) any_station_23 = true;
    check(!any_station_23, "nothing is published for a station above 22");
}

// ---------------------------------------------------------------- pilot map

// test_pilot_map()
//   channels.h against docs/pilot-map.md.
static void test_pilot_map()
{
    std::printf("pilot map (docs/pilot-map.md)\n");
    check(chan::pilot_bin(1) == 512 && chan::pilot_bin(32) == 760,
          "the comb runs from bin 512 to bin 760");
    check_near(chan::pilot_hz(1), 6000.00, 0.005, "slot 1 is 6000.00 Hz");
    check_near(chan::pilot_hz(32), 8906.25, 0.005, "slot 32 is 8906.25 Hz");
    check_near(chan::OP_BIN * chan::BIN_HZ, 9000.00, 0.005, "the operator tone is 9000.00 Hz");
    check(chan::station_slot(22) == 22 && chan::trunk_slot(1) == 25,
          "station 22 is slot 22 and trunk 1 is slot 25");
    check(chan::N_STATIONS == 22, "there are 22 stations (audio.md 2, Rev 7)");
    check(!chan::is_circuit_slot(chan::TAP_CH) &&
          !chan::is_circuit_slot(chan::MONITOR_CH),
          "slots 23 and 24 are the tap and the monitor, not circuits");
    check(chan::TAP_CH == 23 && chan::MONITOR_CH == 24,
          "the tap is channel 23 and the monitor channel 24");
    check(chan::can_carry_monitor(24) && chan::can_carry_monitor(33) &&
          chan::can_carry_monitor(34) && !chan::can_carry_monitor(23) &&
          !chan::can_carry_monitor(1) && !chan::can_carry_monitor(25),
          "only 24, 33 and 34 may carry the monitor");

    char id[24];
    chan::circuit_id(chan::trunk_slot(8), id, sizeof id);
    check(std::strcmp(id, "trunk/8") == 0, "circuit ids are station/<n> and trunk/<n>");

    // Every pilot completes an integer number of cycles per block, which is
    // what makes the rectangular window leakage-free.
    bool integral = true;
    for (int s = 1; s <= chan::N_SLOTS; ++s)
        if (chan::pilot_bin(s) * chan::BIN_HZ * chan::FFT_N / chan::SAMPLE_RATE
            != (double)chan::pilot_bin(s)) integral = false;
    check(integral, "every pilot is an integer number of cycles per block");
}

// ---------------------------------------------------------------- hf meter

// measure()
//   Runs a signal through a cascade and returns its level in dBFS referenced
//   to a full-scale sine, exactly as wav.cpp's content check does.
static double measure(const std::vector<double>& x, const std::vector<Biquad>& f)
{
    std::vector<BiquadState> st(f.size());
    double acc = 0.0;
    for (double v : x) {
        for (size_t i = 0; i < f.size(); ++i) v = st[i].run(f[i], v);
        acc += v * v;
    }
    return x.empty() ? -200.0 : lin_to_db(std::sqrt(acc / x.size()) * M_SQRT2);
}

// band_limited_noise()
//   Two seconds of noise through the telephone band, 300-3400Hz, with nothing
//   above it - a stand-in for a correctly authored prompt. `tilt` applies two
//   one-pole low-passes at 100Hz first, giving a spectrum falling at about
//   12dB/octave across the band: the difference between a dull voice and a
//   bright one. Normalised to -20dBFS RMS, the level process.py delivers at.
static std::vector<double> band_limited_noise(bool tilt)
{
    const double fs = chan::SAMPLE_RATE;
    std::vector<double> x((size_t)(2.0 * fs));
    unsigned s = 12345;
    for (double& v : x) { s = s * 1103515245u + 12345u; v = ((s >> 16) & 0x7fff) / 16383.5 - 1.0; }

    if (tilt) {
        const double a = std::exp(-2.0 * M_PI * 100.0 / fs);
        double z1 = 0.0, z2 = 0.0;
        for (double& v : x) { z1 = (1 - a) * v + a * z1; z2 = (1 - a) * z1 + a * z2; v = z2; }
    }

    // Band-limited the way tts/process.py does it, which is what makes this a
    // stand-in for a delivered file: a 300Hz high-pass and the same elliptic
    // low-pass, 3400Hz passband edge, 4500Hz stopband edge, 70dB. A gentler
    // low-pass would leave real energy above 5.5kHz, and the meter would be
    // right to report it.
    double lp_ripple = 0.0;
    std::vector<Biquad> band = elliptic_lowpass(8, 3400.0, 4500.0, 70.0, fs, lp_ripple);
    band.push_back(butter_highpass(300.0, fs));
    std::vector<BiquadState> st(band.size());
    for (double& v : x)
        for (size_t i = 0; i < band.size(); ++i) v = st[i].run(band[i], v);

    double acc = 0.0;
    for (double v : x) acc += v * v;
    const double rms = std::sqrt(acc / x.size());
    const double want = db_to_lin(-20.0) / M_SQRT2;
    for (double& v : x) v *= want / rms;
    return x;
}

// test_hf_meter()
//   audio.md 5.3 and 7.2: the content check that asks how much of a delivered
//   file sits above 5.5kHz. The filter has to ignore the telephone band, whose
//   top is only 2kHz below the corner, or it measures the voice instead.
static void test_hf_meter()
{
    std::printf("content check high-pass (audio.md 5.3, 7.2)\n");
    const double fs = chan::SAMPLE_RATE;

    double ripple = 0.0;
    const std::vector<Biquad> hp = elliptic_highpass(8, 5500.0, 4000.0, 80.0, fs, ripple);
    check(hp.size() == 4, "eighth order is four second-order sections");

    const double TOL = 0.2;      // the equiripple peaks sit on the requirement
    bool stop_ok = true;
    for (double f : { 300.0, 1000.0, 2000.0, 2600.0, 3000.0, 3400.0, 4000.0 })
        if (cascade_mag_db(hp, f, fs) > -80.0 + TOL) stop_ok = false;
    check(stop_ok, "at least 80 dB down from 300 Hz to 4 kHz - the whole telephone band");

    bool pass_ok = true;
    for (double f : { 5500.0, 6000.0, 7000.0, 9000.0, 12000.0, 20000.0 })
        if (std::fabs(cascade_mag_db(hp, f, fs)) > 0.5) pass_ok = false;
    check(pass_ok, "flat from 5.5 kHz to Nyquist, where the answer is wanted");

    // The property the change is for: two correctly band-limited files that
    // differ only in brightness must read the same, because neither has
    // anything above the corner.
    const std::vector<double> dull = band_limited_noise(true);
    const std::vector<double> bright = band_limited_noise(false);
    const double new_dull = measure(dull, hp), new_bright = measure(bright, hp);

    const Biquad b = butter_highpass(5500.0, fs);
    const std::vector<Biquad> old { b, b };
    const double old_dull = measure(dull, old), old_bright = measure(bright, old);

    std::printf("    dull voice: old %6.1f dBFS, new %6.1f;  bright: old %6.1f, new %6.1f\n",
                old_dull, new_dull, old_bright, new_bright);
    check(new_dull < -80.0 && new_bright < -80.0,
          "a band-limited file reads at least 20 dB below the -60 dBFS threshold");
    check(old_bright > -60.0,
          "where the old meter tripped on the same file if the voice was bright");

    // The clearest case, and the one that shows what the old meter was really
    // measuring: a full-scale 1kHz sine has nothing above the corner at all.
    // The old meter read it 1dB from the threshold; the new one puts it out of
    // sight, because 1kHz is 99dB down rather than 61dB down.
    // Faded in and out over 20ms at each end. A tone that starts at full scale
    // on the first sample is a step, and a step has energy at every frequency
    // - the meter would be right to report it, and every delivered file begins
    // and ends in silence anyway (process.py keeps 150ms of it).
    std::vector<double> sine(chan::SAMPLE_RATE);
    const size_t fade = chan::SAMPLE_RATE / 50;
    for (size_t i = 0; i < sine.size(); ++i) {
        double g = 1.0;
        if (i < fade)                     g = 0.5 - 0.5 * std::cos(M_PI * i / fade);
        if (i >= sine.size() - fade)      g = 0.5 - 0.5 * std::cos(M_PI * (sine.size() - 1 - i) / fade);
        sine[i] = g * std::sin(2.0 * M_PI * 1000.0 * (double)i / chan::SAMPLE_RATE);
    }
    const double old_sine = measure(sine, old), new_sine = measure(sine, hp);
    std::printf("    full-scale 1 kHz sine: old %6.1f dBFS, new %6.1f\n", old_sine, new_sine);
    check(old_sine > -61.0, "the old meter read a 1 kHz sine within a dB of tripping");
    check(new_sine < -90.0, "the new one reads it 30 dB clear of the threshold");

    // And it still finds what it is for.
    std::vector<double> noisy = bright;
    unsigned s = 999;
    for (double& v : noisy) { s = s * 1103515245u + 12345u;
        v += 0.02 * std::sin(2.0 * M_PI * 7000.0 * (&v - noisy.data()) / fs); }
    check(measure(noisy, hp) > -60.0, "a 7 kHz tone at -34 dBFS still trips it");
}

// ---------------------------------------------------------------- listener

// A synthetic caller, one 10 ms frame at a time. Levels: the room at -70 dBFS,
// so the threshold is the absolute -50 (floor + 10 = -60 is below it), and
// speech at -30. Every expected frame number below is worked out from the
// rules in audio.md 9.2, not read off the program.
struct Script {
    Listener  lis;
    VadParams p;
    int       t = 0;                    // frames since start() was called
    int       speech = -1, silence = -1, timeout = -1, events = 0;

    void run(float db, int n, bool valid = true)
    {
        for (int i = 0; i < n; ++i) {
            const Listener::Event e = lis.frame(db, valid, p);
            if (lis.active() || e != Listener::Event::None) ++t;
            if (e == Listener::Event::None) continue;
            ++events;
            if (e == Listener::Event::Speech  && speech  < 0) speech  = t;
            if (e == Listener::Event::Silence && silence < 0) silence = t;
            if (e == Listener::Event::Timeout && timeout < 0) timeout = t;
        }
    }
    void start(double s) { lis.start(s); t = 0; }
};

static const float ROOM = -70.0f, TALK = -30.0f;

// test_listener()
//   The state machine of audio.md 9.2 (Rev 6): start of speech, end of speech
//   after the hangover, the two timeouts, discarded frames and cancel.
static void test_listener()
{
    std::printf("speech detector (audio.md 9.2, Rev 6)\n");

    {   // One sentence. Speech is declared on its 20th frame (20 of 30). Its
        // end: 28 quiet frames bring the window to 2 of 30, which is quiet;
        // 150 frames of that is the 1.5 s hangover. 50 + 150 + 28 + 149.
        Script s; s.run(ROOM, 100); s.start(5.0);
        s.run(ROOM, 50); s.run(TALK, 150); s.run(ROOM, 400);
        check(s.speech == 70,  "one sentence: speech on its 20th frame");
        check(s.silence == 377, "one sentence: silence 1.5 s after the window goes quiet");
        check(s.events == 2 && s.timeout < 0, "one sentence: exactly two reports");
        check(!s.lis.active(), "one sentence: the listen is over");
    }
    {   // A 0.8 s pause inside the sentence is shorter than the hangover.
        Script s; s.run(ROOM, 100); s.start(5.0);
        s.run(ROOM, 50); s.run(TALK, 100); s.run(ROOM, 80); s.run(TALK, 100);
        const int end = s.t;
        s.run(ROOM, 400);
        check(s.silence == end + 177, "a pause inside a sentence does not end it");
        check(s.events == 2, "one speech report for the whole sentence");
    }
    {   // A cough in the hangover: one frame above, the window stays at <= 2,
        // the count runs on.
        Script s; s.run(ROOM, 100); s.start(5.0);
        s.run(ROOM, 50); s.run(TALK, 150);
        const int end = s.t;
        s.run(ROOM, 99); s.run(TALK, 1); s.run(ROOM, 300);
        check(s.silence == end + 177, "a cough after the caller stops does not restart the count");
    }
    {   // A second sentence in the hangover: three frames above restarts it.
        // The oldest of the three leaves the window 28 frames after the last.
        Script s; s.run(ROOM, 100); s.start(5.0);
        s.run(ROOM, 50); s.run(TALK, 150);
        const int end = s.t;
        s.run(ROOM, 99); s.run(TALK, 3); s.run(ROOM, 400);
        check(s.silence == end + 102 + 177, "a second sentence restarts the hangover");
    }
    {   // Nobody speaks: the command's seconds, in frames.
        Script s; s.run(ROOM, 100); s.start(2.0); s.run(ROOM, 400);
        check(s.timeout == 200 && s.speech < 0, "no speech: timeout at the command's 2 s");
    }
    {   // Speech that never stops: declared once the window is full (30 valid
        // frames), then 30 s from that frame.
        Script s; s.run(ROOM, 100); s.start(5.0); s.run(TALK, 3100);
        check(s.speech == 30, "speech from the first frame: declared when the window fills");
        check(s.timeout == 30 + 3000 && s.silence < 0, "endless speech: timeout 30 s after it began");
    }
    {   // Our own file on the channel: discarded frames never count, and the
        // window restarts when the file stops.
        Script s; s.run(ROOM, 100); s.start(5.0);
        s.run(TALK, 100, false);
        check(s.speech < 0, "frames with a source running are not speech");
        s.run(TALK, 100);
        check(s.speech == 130, "speech after the source stops needs a fresh window");
    }
    {   // Discarded frames are still time the game is waiting.
        Script s; s.run(ROOM, 100); s.start(1.0); s.run(TALK, 300, false);
        check(s.timeout == 100, "discarded frames still run the start timeout");
    }
    {   // Cancel: nothing further is reported.
        Script s; s.run(ROOM, 100); s.start(5.0); s.run(ROOM, 10);
        s.lis.cancel(); s.run(TALK, 300);
        check(s.events == 0 && !s.lis.active(), "a cancelled listen reports nothing");
    }
    {   // --vad-hangover reaches the rule: 0.5 s is 50 frames.
        Script s; s.p.hangover_frames = 50; s.run(ROOM, 100); s.start(5.0);
        s.run(ROOM, 50); s.run(TALK, 150);
        const int end = s.t;
        s.run(ROOM, 200);
        check(s.silence == end + 28 + 49, "a shorter --vad-hangover ends speech sooner");
    }
}

// ---------------------------------------------------------------- options

// opts()
//   Parses a command line, --card supplied since it is required, and says
//   whether it was accepted. The parsed options come back in `o`.
static bool opts(Options& o, std::vector<const char*> args)
{
    std::vector<char*> argv;
    argv.push_back(const_cast<char*>("sbaudio"));
    argv.push_back(const_cast<char*>("--card"));
    argv.push_back(const_cast<char*>("Test"));
    for (const char* a : args) argv.push_back(const_cast<char*>(a));
    bool exit_now = false;
    o = Options{};
    return parse_options((int)argv.size(), argv.data(), o, exit_now);
}

// test_monitor_ch()
//   audio.md 14: the monitor goes to channels from {24, 33, 34}, and anything
//   else is a startup error rather than a clamp.
static void test_monitor_ch()
{
    std::printf("--monitor-ch (audio.md 10.1, 14)\n");
    Options o;

    check(opts(o, {}) && o.monitor_ch == std::vector<int>{ 24 },
          "the default is channel 24, the A32 output to the amplifier");
    check(opts(o, { "--monitor-ch", "24" }) && o.monitor_ch == std::vector<int>{ 24 },
          "24 accepted");
    check(opts(o, { "--monitor-ch", "33,34" }) && o.monitor_ch == (std::vector<int>{ 33, 34 }),
          "33,34 accepted - the Digiface fallback of Rev 1 to Rev 6");
    check(opts(o, { "--monitor-ch", "24,33" }) && o.monitor_ch == (std::vector<int>{ 24, 33 }),
          "24,33 accepted");

    check(!opts(o, { "--monitor-ch", "23" }), "23 refused: it is the operator tap");
    check(!opts(o, { "--monitor-ch", "1" }),  "1 refused: it is a station");
    check(!opts(o, { "--monitor-ch", "25" }), "25 refused: it is a trunk");
    check(!opts(o, { "--monitor-ch", "" }),   "an empty list is refused");
    check(!opts(o, { "--monitor-ch", "24,24" }), "a repeat is refused");
    check(!opts(o, { "--monitor-ch", "24," }), "a trailing comma is refused");
    check(!opts(o, { "--monitor-ch", "twentyfour" }), "a non-number is refused");
    check(!opts(o, { "--monitor-ch", "35" }), "35 refused: there is no such channel");
}

// ---------------------------------------------------------------- render

// render_once()
//   Builds an Engine with no audio device, renders one period with a known
//   value standing in for the monitor chain's output, and returns the whole
//   interleaved period. Document channel ch, frame f, is at
//   [f * N_PLAY_CH + ch - 1].
static std::vector<int32_t> render_once(const Options& o, float monitor_value)
{
    auto sh = std::make_unique<Shared>();   // atomics: not assignable, and large
    sh->opt = o;
    AlsaStream st;                          // never opened
    Engine eng(*sh, st);
    if (!eng.prepare_detached(256, chan::N_PLAY_CH, chan::N_CAP_CH)) return {};
    eng.set_monitor_row_for_test(monitor_value);
    eng.render_for_test();
    return eng.playback();
}

// Does document channel `ch` carry `want` in every frame of the period?
static bool all_frames(const std::vector<int32_t>& buf, int ch, int32_t want)
{
    const int n = (int)buf.size() / chan::N_PLAY_CH;
    for (int f = 0; f < n; ++f)
        if (buf[(size_t)f * chan::N_PLAY_CH + ch - 1] != want) return false;
    return n > 0;
}

// Does it carry anything at all - any frame not zero?
static bool any_signal(const std::vector<int32_t>& buf, int ch)
{
    const int n = (int)buf.size() / chan::N_PLAY_CH;
    for (int f = 0; f < n; ++f)
        if (buf[(size_t)f * chan::N_PLAY_CH + ch - 1] != 0) return true;
    return false;
}

// test_render_map()
//   audio.md 2, Rev 7: which playback channel carries what. The monitor row is
//   set to a value nothing else produces, so the channel carrying it is
//   unmistakable.
static void test_render_map()
{
    std::printf("playback channel map (audio.md 2, Rev 7)\n");
    const float MON = 0.5f;
    const int32_t mon_s32 = float_to_s32(MON);

    Options o;
    check(opts(o, {}), "default options parse");
    std::vector<int32_t> f = render_once(o, MON);
    check(f.size() == 256u * chan::N_PLAY_CH, "a period renders without a device");

    check(all_frames(f, chan::MONITOR_CH, mon_s32),
          "by default the monitor is on document channel 24 (ALSA index 23)");
    check(all_frames(f, chan::DIGIFACE_CH_A, 0) && all_frames(f, chan::DIGIFACE_CH_B, 0),
          "and the Digiface pair (indices 32, 33) is silent");
    check(any_signal(f, chan::TAP_CH) && !all_frames(f, chan::TAP_CH, mon_s32),
          "channel 23 carries the operator tone");

    bool pilots = true, clean = true;
    for (int s = 1; s <= chan::N_SLOTS; ++s) {
        if (!chan::is_circuit_slot(s)) continue;
        if (!any_signal(f, s))                   pilots = false;
        if (all_frames(f, s, mon_s32))           clean = false;
    }
    check(pilots, "every circuit channel carries its pilot");
    check(clean, "no circuit channel carries the monitor");

    check(opts(o, { "--monitor-ch", "33,34" }), "--monitor-ch 33,34 parses");
    f = render_once(o, MON);
    check(all_frames(f, chan::DIGIFACE_CH_A, mon_s32) &&
          all_frames(f, chan::DIGIFACE_CH_B, mon_s32),
          "--monitor-ch 33,34 moves the monitor to the Digiface pair");
    check(all_frames(f, chan::MONITOR_CH, 0),
          "and channel 24 then carries silence");
}

// test_output_check()
//   audio.md 11.4, Rev 12: a render as designed passes the output self-check
//   on every channel - pilots, the operator tone, the monitor at its limit,
//   silence, the test tone - and a corrupted buffer is caught on the channels
//   corrupted and on no others.
static void test_output_check()
{
    std::printf("output self-check (audio.md 11.4, Rev 12)\n");
    auto sh = std::make_unique<Shared>();
    AlsaStream st;                          // never opened
    Engine eng(*sh, st);
    check(eng.prepare_detached(256, chan::N_PLAY_CH, chan::N_CAP_CH), "engine prepares");

    Command t;
    t.verb = Verb::Test; t.idx = 5; t.on = true;
    check(sh->cmdq.push(t), "a test tone on 5 queues");
    eng.drain_for_test();
    eng.set_monitor_row_for_test(0.70f);    // just under the -3dBFS limit
    for (int k = 0; k < 4; ++k) { eng.render_for_test(); eng.check_output_for_test(); }
    bool clean = true;
    for (int ch = 1; ch <= chan::N_PLAY_CH; ++ch)
        if (eng.out_over_for_test(ch)) clean = false;
    check(clean, "a render as designed exceeds no channel's ceiling");

    eng.render_for_test();
    std::vector<int32_t>& buf = eng.playback_for_test();
    buf[(size_t)7 * chan::N_PLAY_CH + 9 - 1]  = 2000000000;    // a pilot channel
    buf[(size_t)9 * chan::N_PLAY_CH + 34 - 1] = -100000;       // a silent one
    eng.check_output_for_test();
    check(eng.out_over_for_test(9) == 1 && eng.out_over_for_test(34) == 1,
          "a corrupted pilot channel and a corrupted silent channel are caught");
    bool others = true;
    for (int ch = 1; ch <= chan::N_PLAY_CH; ++ch)
        if (ch != 9 && ch != 34 && eng.out_over_for_test(ch)) others = false;
    check(others, "and no other channel is");
}

// test_tap_play()
//   audio.md 7, Rev 10: a file on the operator tap sums over the operator
//   tone, and the tap's play echo is its own topic, not a circuit's.
static void test_tap_play()
{
    std::printf("a file on the operator tap (audio.md 7, Rev 10)\n");
    auto sh = std::make_unique<Shared>();
    AlsaStream st;                          // never opened
    Engine eng(*sh, st);
    check(eng.prepare_detached(256, chan::N_PLAY_CH, chan::N_CAP_CH), "engine prepares");
    eng.render_for_test();
    const std::vector<int32_t> before = eng.playback();

    Command c;
    c.verb = Verb::Play;
    c.idx  = (int16_t)chan::TAP_CH;
    c.buf  = new AudioBuffer;
    c.buf->samples.assign(4096, 0.25f);
    std::snprintf(c.name, sizeof c.name, "diag");
    check(sh->cmdq.push(c), "the play command queues");
    eng.drain_for_test();
    eng.render_for_test();
    const std::vector<int32_t> after = eng.playback();

    bool shifted = true;
    const int n = (int)after.size() / chan::N_PLAY_CH;
    for (int f = 0; f < n; ++f) {
        const size_t i = (size_t)f * chan::N_PLAY_CH + chan::TAP_CH - 1;
        const double d = ((double)after[i] - (double)before[i]) / 2147483648.0;
        if (std::fabs(d - 0.25) > 0.01) shifted = false;
    }
    check(n > 0 && shifted, "channel 23 carries the file summed over the operator tone");

    bool echoed = false;
    Result r;
    while (sh->res_audio.pop(r))
        if (r.topic == Topic::Play && r.idx == chan::TAP_CH && std::strcmp(r.value, "diag") == 0)
            echoed = true;
    check(echoed, "and posts the tap's play echo");
}

// test_monitor_play()
//   audio.md 10.4, Rev 11: a file on the monitor plays through the monitor's
//   gain and low-pass onto channel 24, clears its own play topic when it
//   ends, and is silent while the monitor is off.
static void test_monitor_play()
{
    std::printf("a file on the monitor (audio.md 10.4, Rev 11)\n");
    auto sh = std::make_unique<Shared>();
    AlsaStream st;                          // never opened
    Engine eng(*sh, st);
    check(eng.prepare_detached(256, chan::N_PLAY_CH, chan::N_CAP_CH), "engine prepares");

    // 1 kHz, well inside the passband, for 20 periods.
    const unsigned len = 256 * 20;
    auto file = [&] {
        AudioBuffer* b = new AudioBuffer;
        b->samples.resize(len);
        for (unsigned i = 0; i < len; ++i)
            b->samples[i] = 0.25f * (float)std::sin(2.0 * M_PI * 1000.0 * i / chan::SAMPLE_RATE);
        return b;
    };
    auto play = [&](bool on) {
        Command m;
        m.verb = Verb::Monitor; m.on = on; m.arg = 0.0f;
        check(sh->cmdq.push(m), "the monitor command queues");
        eng.drain_for_test();
        for (int k = 0; k < 10; ++k) { eng.capture_for_test(); eng.render_for_test(); }
        Result r;
        while (sh->res_audio.pop(r)) {}     // let the 20ms ramp and the last file ring out
        Command c;
        c.verb = Verb::Play;
        c.idx  = (int16_t)chan::MONITOR_CH;
        c.buf  = file();
        std::snprintf(c.name, sizeof c.name, "tutor.hello");
        check(sh->cmdq.push(c), "the play command queues");
        eng.drain_for_test();
    };
    auto peak_over = [&](unsigned periods, bool& finished) {
        double peak = 0.0;
        finished = false;
        for (unsigned p = 0; p < periods; ++p) {
            eng.capture_for_test();
            eng.render_for_test();
            const std::vector<int32_t>& out = eng.playback();
            const int n = (int)out.size() / chan::N_PLAY_CH;
            for (int f = 0; f < n; ++f) {
                const size_t i = (size_t)f * chan::N_PLAY_CH + chan::MONITOR_CH - 1;
                peak = std::max(peak, std::fabs((double)out[i] / 2147483648.0));
            }
            Result r;
            while (sh->res_audio.pop(r))
                if (r.topic == Topic::Play && r.idx == chan::MONITOR_CH && r.value[0] == '\0')
                    finished = true;
        }
        return peak;
    };

    play(true);
    bool finished = false;
    const double on_peak = peak_over(25, finished);
    check(on_peak > 0.2 && on_peak < 0.3, "channel 24 carries the file at unity, through the low-pass");
    check(finished, "and play clears when the file ends");

    play(false);
    const double off_peak = peak_over(25, finished);
    check(off_peak < 1e-4, "silent while the monitor is off");
    check(finished, "and still runs out and clears");
}

static void test_monitor_source()
{
    std::printf("monitor source mapping (audio.md 10.3)\n");

    // The accepted set, and the channels it maps to. audio.md 10.3: the tap is
    // 23, station n is n, trunk n is 24 + n.
    check(chan::monitor_source_channel("tap") == chan::TAP_CH, "tap is channel 23");
    check(chan::monitor_source_channel("station/1") == 1,  "station/1 is channel 1");
    check(chan::monitor_source_channel("station/22") == 22, "station/22 is channel 22");
    check(chan::monitor_source_channel("trunk/1") == 25, "trunk/1 is channel 25");
    check(chan::monitor_source_channel("trunk/8") == 32, "trunk/8 is channel 32");

    // The 0-based capture index the audio thread uses is the channel less one.
    check(chan::monitor_source_channel("tap") - 1 == 22, "tap's capture index is 22");
    check(chan::monitor_source_channel("trunk/3") - 1 == 26, "trunk/3's capture index is 26");

    // Out of range at both ends, on both kinds.
    check(chan::monitor_source_channel("station/0")  == 0, "station/0 is refused");
    check(chan::monitor_source_channel("station/23") == 0, "station/23 is refused - 22 stations");
    check(chan::monitor_source_channel("trunk/0")    == 0, "trunk/0 is refused");
    check(chan::monitor_source_channel("trunk/9")    == 0, "trunk/9 is refused - 8 trunks");

    // The tap and the monitor are not circuits and cannot be named as one.
    check(chan::monitor_source_channel("station/24") == 0, "the monitor channel is not a station");

    // Malformed payloads. strtol would have taken most of these.
    const char* bad[] = { "", " ", "tap/", "Tap", "TAP", "station", "station/",
                          "station/ 1", "station/1 ", "station/+1", "station/-1",
                          "station/01x", "station/1.0", "trunk/1x", "trunks/1",
                          "/station/1", "sbgame/station/1", "off", "0", "23" };
    for (const char* b : bad) {
        if (!b) continue;                       // gcc wants this proof for %s
        char msg[96];
        std::snprintf(msg, sizeof msg, "\"%s\" is refused", b);
        check(chan::monitor_source_channel(b) == 0, msg);
    }
    check(chan::monitor_source_channel(nullptr) == 0, "a null payload is refused");

    // "station/01" is digits only and in range; accepting it is harmless and
    // is what the digit loop does. Recorded so the behaviour is deliberate.
    check(chan::monitor_source_channel("station/01") == 1, "\"station/01\" is taken as station 1");

    // The inverse, which is what the echo carries.
    char n[24];
    check(chan::monitor_source_name(chan::TAP_CH, n, sizeof n) && std::strcmp(n, "tap") == 0,
          "channel 23 echoes as tap");
    check(chan::monitor_source_name(5, n, sizeof n) && std::strcmp(n, "station/5") == 0,
          "channel 5 echoes as station/5");
    check(chan::monitor_source_name(27, n, sizeof n) && std::strcmp(n, "trunk/3") == 0,
          "channel 27 echoes as trunk/3");
    check(!chan::monitor_source_name(chan::MONITOR_CH, n, sizeof n),
          "channel 24 has no source name");

    // audio.md Rev 9 1.9: a source beyond what the device captures is refused
    // at startup rather than echoed against silence. Testable without hardware
    // because prepare_detached() takes the capture count.
    {
        auto refuses = [](int src, unsigned ncap) {
            auto sh = std::make_unique<Shared>();
            sh->opt.monitor_src = src;
            AlsaStream st;                      // never opened
            Engine eng(*sh, st);
            return !eng.prepare_detached(256, chan::N_PLAY_CH, ncap);
        };
        check(refuses(32, 24),  "trunk/8 is refused when the device grants 24 capture channels");
        check(refuses(25, 24),  "trunk/1 is refused when the device grants 24");
        check(!refuses(23, 24), "the tap is accepted when the device grants 24");
        check(!refuses(32, 32), "trunk/8 is accepted when the device grants 32");
    }

    // Round trip: every accepted source names itself back.
    const char* good[] = { "tap", "station/1", "station/11", "station/22",
                           "trunk/1", "trunk/5", "trunk/8" };
    for (const char* g : good) {
        if (!g) continue;                       // as above
        const int ch = chan::monitor_source_channel(g);
        char back[24];
        char msg[96];
        std::snprintf(msg, sizeof msg, "%s round trips", g);
        check(ch != 0 && chan::monitor_source_name(ch, back, sizeof back) &&
              std::strcmp(back, g) == 0, msg);
    }
}

int main()
{
    log_start();
    test_pilot_map();
    test_monitor_filter();
    test_detector();
    test_listener();
    test_hf_meter();
    test_monitor_ch();
    test_render_map();
    test_monitor_source();
    test_output_check();
    test_tap_play();
    test_monitor_play();
    std::printf("\n%s\n", failures ? "FAILURES" : "all checks passed");
    return failures ? 1 : 0;
}
