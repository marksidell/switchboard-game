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

#include "../src/aec.h"
#include "../src/channels.h"
#include "../src/cityring.h"
#include "../src/detector.h"
#include "../src/dsp.h"
#include "../src/ipc.h"
#include "../src/util.h"
#include "../src/vad.h"
#include "../src/alsa.h"
#include "../src/engine.h"
#include "../src/options.h"
#include "../src/rec.h"

#include <sndfile.h>
#include <stdlib.h>
#include <unistd.h>

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
    // audio.md 9.2, Rev 18: the speech detector's low-pass is sixth-order, so
    // the pilots fall below the line's noise rather than setting the floor.
    const std::vector<Biquad> vlp6 = butter_lowpass6(3400.0, fs);
    check(vlp6.size() == 3, "the speech detector's low-pass is three sections");
    check_near(cascade_mag_db(vlp6, 3400.0, fs), -3.0, 0.2, "-3 dB at 3400 Hz");
    check(cascade_mag_db(vlp6, 1000.0, fs) > -0.1, "flat at 1 kHz");
    check(cascade_mag_db(vlp6, 6000.0, fs) < -29.0, "the lowest pilot 29 dB down or more");
    check(cascade_mag_db(vlp6, 9000.0, fs) < -49.0, "the operator tone 49 dB down or more");
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

    // Slot 23, the tap, has no pilot and no circuit, so no peer or op may be
    // published for it. Slot 24 is station 24 (audio.md Rev 24) and is.
    bool any_tap = false, any_24 = false;
    for (const Result& x : all) {
        if (x.topic != Topic::Peer && x.topic != Topic::Op) continue;
        if (x.idx == chan::TAP_CH) any_tap = true;
        if (x.idx == chan::PHONE_STATION) any_24 = true;
    }
    check(!any_tap, "the tap publishes no peer or op of its own");
    check(any_24, "station 24 publishes a peer and op, as any station");
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
    check(chan::N_STATIONS == 22 && chan::PHONE_STATION == 24,
          "the stations are 1-22 and 24 (audio.md 2, Rev 24)");
    check(!chan::is_circuit_slot(chan::TAP_CH) && chan::is_circuit_slot(24),
          "slot 23 is the tap, not a circuit; slot 24 is station 24");
    check(chan::is_station(24) && !chan::is_station(23) && chan::is_station(22) &&
          !chan::is_station(25), "is_station: 1-22 and 24");
    check(chan::TAP_CH == 23, "the tap is channel 23");
    check(chan::can_carry_monitor(33) && chan::can_carry_monitor(34) &&
          !chan::can_carry_monitor(24) && !chan::can_carry_monitor(23) &&
          !chan::can_carry_monitor(1) && !chan::can_carry_monitor(25),
          "only 33 and 34 may carry the monitor");
    {
        char id24[24];
        chan::circuit_id(24, id24, sizeof id24);
        check(std::strcmp(id24, "station/24") == 0, "slot 24's circuit id is station/24");
    }

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

static const float TALK_MIN = -45.0f;    // levels from here up are a talker

// A synthetic caller, one 10 ms frame at a time. Levels: the room at -70 dBFS,
// so the threshold is the absolute -50 (floor + 10 = -60 is below it), and
// speech at -30. Every expected frame number below is worked out from the
// rules in audio.md 9.2, not read off the program.
struct Script {
    Listener  lis;
    VadParams p;
    int       t = 0;                    // frames since start() was called
    int       speech = -1, silence = -1, timeout = -1, events = 0;

    // A talker's level varies from frame to frame - 8 dB here, all of it
    // above the threshold - or the detector takes it for a steady noise
    // (Rev 32). Anything else, or a talker run with held, is run as given.
    void run(float db, int n, bool valid = true, bool held = false)
    {
        static const float syllable[4] = { 0.0f, -4.0f, -8.0f, -3.0f };
        for (int i = 0; i < n; ++i) {
            const float lv = db >= TALK_MIN && !held ? db + syllable[i % 4] : db;
            const Listener::Event e = lis.frame(lv, valid, p);
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
    {   // Rev 32, as captured on trunk 1, 2026-10-27, with the installation's
        // -70 bound and 0.5 s hangover: -108 unseized, then seized with the
        // operator's key already in, -69.2 and steady, a listen started at
        // once. The floor from before is -108 and the bar -70, under the
        // noise; the steady level takes the floor at its 50th frame.
        Script s; s.p.abs_floor_db = -70.0; s.p.hangover_frames = 50;
        s.run(-108.0f, 100); s.start(6.0);
        for (int i = 0; i < 300; ++i) s.run(-69.2f + 0.3f * (float)((i * 7) % 3 - 1), 1);
        check(s.speech < 0, "a trunk seized as the listen starts: its noise is not speech");
        check(s.lis.floor_db() > -70.0, "and becomes the floor");
        const int at = s.t;
        s.run(-40.0f, 100);                 // "Number, please"
        check(s.speech > at && s.speech <= at + 30, "then she is heard");
        const int end = s.t;
        for (int i = 0; i < 200; ++i) s.run(-69.2f + 0.3f * (float)((i * 7) % 3 - 1), 1);
        check(s.silence == end + 28 + 49, "and her end, on the seized line");
    }
    {   // The same, and she speaks the moment the trunk is seized: speech
        // when the window fills, the noise before her counting as above the
        // bar. Her end: 50 steady frames take the floor and restart the
        // window, 29 more fill it, and the hangover runs from there.
        Script s; s.p.abs_floor_db = -70.0; s.p.hangover_frames = 50;
        s.run(-108.0f, 100); s.start(6.0);
        s.run(-69.2f, 5); s.run(-40.0f, 100);
        check(s.speech == 30, "she speaks at once on a fresh seizure: heard");
        const int end = s.t;
        s.run(-69.2f, 300);
        check(s.silence == end + 50 + 29 + 49, "her end: 50 steady frames take the floor, then the hangover");
    }
    {   // A held vowel is steady, but at -30 it is far above any line's noise
        // (STEADY_MAX_DB): it starts speech, and a second of it inside a
        // sentence does not become the floor and end it.
        Script s; s.run(ROOM, 100); s.start(5.0);
        s.run(TALK, 100, true, true);
        check(s.speech == 30, "a held vowel at once: speech when the window fills");
        s.run(TALK, 100); s.run(TALK, 100, true, true); s.run(TALK, 50);
        const int end = s.t;
        s.run(ROOM, 400);
        check(s.silence == end + 177, "a held vowel mid-sentence does not end it");
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
//   audio.md 14: the monitor goes to channels from {33, 34}, and anything
//   else is a startup error rather than a clamp. 24 is station 24 (Rev 24).
static void test_monitor_ch()
{
    std::printf("--monitor-ch (audio.md 10.1, 14)\n");
    Options o;

    check(opts(o, {}) && o.monitor_ch == (std::vector<int>{ 33, 34 }),
          "the default is 33,34, the Digiface pair");
    check(opts(o, { "--monitor-ch", "33" }) && o.monitor_ch == std::vector<int>{ 33 },
          "33 accepted");
    check(opts(o, { "--monitor-ch", "34,33" }) && o.monitor_ch == (std::vector<int>{ 34, 33 }),
          "34,33 accepted");
    check(!opts(o, { "--monitor-ch", "24" }), "24 refused: it is station 24");

    check(!opts(o, { "--monitor-ch", "23" }), "23 refused: it is the operator tap");
    check(!opts(o, { "--monitor-ch", "1" }),  "1 refused: it is a station");
    check(!opts(o, { "--monitor-ch", "25" }), "25 refused: it is a trunk");
    check(!opts(o, { "--monitor-ch", "" }),   "an empty list is refused");
    check(!opts(o, { "--monitor-ch", "33,33" }), "a repeat is refused");
    check(!opts(o, { "--monitor-ch", "33," }), "a trailing comma is refused");
    check(!opts(o, { "--monitor-ch", "twentyfour" }), "a non-number is refused");
    check(!opts(o, { "--monitor-ch", "35" }), "35 refused: there is no such channel");
}

// test_options()
//   audio.md 14: a number with anything after it is refused rather than read
//   as far as it goes; and without --card, the one Digiface is found.
static void test_options()
{
    std::printf("numbers and the card (audio.md 4, 14)\n");
    Options o;
    check(opts(o, { "--pilot-db", "-38.5" }) && o.pilot_db == -38.5, "-38.5 accepted");
    check(!opts(o, { "--pilot-db", "-4O" }), "\"-4O\" refused, not read as -4");
    check(!opts(o, { "--monitor-gate", "x" }), "\"x\" refused, not read as 0");
    check(!opts(o, { "--period", "256k" }), "a period with junk after it refused");
    check(!opts(o, { "--period", "8" }), "a period out of range refused");
    check(opts(o, { "--broker", "host:1884" }) && o.port == 1884 && o.broker == "host",
          "the broker's port");
    check(!opts(o, { "--broker", "host:18x3" }), "a port with junk in it refused");
    check(!opts(o, { "--monitor-lp", "3600", "5600", "7O" }), "--monitor-lp checks all three");

    const char* two =
        " 0 [PCH            ]: HDA-Intel - HDA Intel PCH\n"
        "                      HDA Intel PCH at 0xf7f10000 irq 31\n"
        " 1 [USB12345678    ]: USB-Audio - Digiface USB (12345678)\n"
        "                      RME Digiface USB (12345678) at usb-0000:00:14.0-2, high speed\n";
    std::string why;
    check(find_card(two, "Digiface", why) == "USB12345678", "the Digiface's id found");
    check(find_card(" 0 [PCH            ]: HDA-Intel - HDA Intel PCH\n", "Digiface", why).empty()
          && !why.empty(), "none found, and why");
    const std::string twice = std::string(two) +
        " 2 [USB87654321    ]: USB-Audio - Digiface USB (87654321)\n";
    check(find_card(twice, "Digiface", why).empty(), "two Digifaces: neither guessed");
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
//   audio.md 2, Rev 24: which playback channel carries what. The monitor row is
//   set to a value nothing else produces, so the channel carrying it is
//   unmistakable.
static void test_render_map()
{
    std::printf("playback channel map (audio.md 2, Rev 24)\n");
    const float MON = 0.5f;
    const int32_t mon_s32 = float_to_s32(MON);

    Options o;
    check(opts(o, {}), "default options parse");
    std::vector<int32_t> f = render_once(o, MON);
    check(f.size() == 256u * chan::N_PLAY_CH, "a period renders without a device");

    check(all_frames(f, chan::DIGIFACE_CH_A, mon_s32) &&
          all_frames(f, chan::DIGIFACE_CH_B, mon_s32),
          "by default the monitor is on the Digiface pair, 33 and 34 (indices 32, 33)");
    check(any_signal(f, 24) && !all_frames(f, 24, mon_s32),
          "channel 24 carries station 24's pilot, not the monitor");
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

    check(opts(o, { "--monitor-ch", "33" }), "--monitor-ch 33 parses");
    f = render_once(o, MON);
    check(all_frames(f, chan::DIGIFACE_CH_A, mon_s32) && all_frames(f, chan::DIGIFACE_CH_B, 0),
          "--monitor-ch 33 puts the monitor on 33 alone, and 34 is silent");
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
    sh->opt.monitor_ch = { 33 };            // so that 34 is a silent channel
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

// test_stop_game()
//   audio.md 13.2: a lost game stops every file - on a circuit, the tap and
//   the monitor - and every trunk tone and listen, and clears their topics.
static void test_stop_game()
{
    std::printf("stop game (audio.md 13.2)\n");
    auto sh = std::make_unique<Shared>();
    AlsaStream st;                          // never opened
    Engine eng(*sh, st);
    check(eng.prepare_detached(256, chan::N_PLAY_CH, chan::N_CAP_CH), "engine prepares");
    eng.render_for_test();
    // An untouched engine's third period, for the pilots' phase.
    auto sh0 = std::make_unique<Shared>();
    Engine ref(*sh0, st);
    ref.prepare_detached(256, chan::N_PLAY_CH, chan::N_CAP_CH);
    for (int k = 0; k < 3; ++k) ref.render_for_test();
    const std::vector<int32_t> idle = ref.playback();

    const int trunk = chan::trunk_slot(2);
    for (int slot : { 5, (int)chan::TAP_CH, (int)chan::MONITOR_PROG }) {
        Command c;
        c.verb = Verb::Play;
        c.idx  = (int16_t)slot;
        c.buf  = new AudioBuffer;
        c.buf->samples.assign(48000, 0.25f);
        std::snprintf(c.name, sizeof c.name, "long");
        check(sh->cmdq.push(c), "a play command queues");
    }
    Command t;
    t.verb = Verb::Tone; t.idx = (int16_t)trunk; t.arg = (float)(int)ToneKind::Ringback;
    sh->cmdq.push(t);
    Command l;
    l.verb = Verb::Listen; l.idx = 3; l.arg = 10.0f;
    sh->cmdq.push(l);
    eng.drain_for_test();
    eng.render_for_test();
    Result r;
    while (sh->res_audio.pop(r)) {}

    Command s;
    s.verb = Verb::StopGame;
    sh->cmdq.push(s);
    eng.drain_for_test();

    bool play5 = false, tap = false, mon = false, tone = false, listen = false;
    int freed = 0;
    while (sh->res_audio.pop(r)) {
        if (r.topic == Topic::FreeBuf) { delete r.buf; ++freed; continue; }
        if (r.value[0] != '\0') continue;
        if (r.topic == Topic::Play && r.idx == 5)                  play5 = true;
        if (r.topic == Topic::Play && r.idx == chan::TAP_CH)       tap = true;
        if (r.topic == Topic::Play && r.idx == chan::MONITOR_PROG) mon = true;
        if (r.topic == Topic::Tone && r.idx == trunk)              tone = true;
        if (r.topic == Topic::Listen && r.idx == 3)                listen = true;
    }
    check(play5 && tap && mon, "a circuit's, the tap's and the monitor's play clear");
    check(tone && listen, "a trunk's tone and a station's listen clear");
    check(freed == 3, "all three buffers are handed back");

    eng.render_for_test();
    const std::vector<int32_t>& out = eng.playback();
    bool same = out.size() == idle.size();
    for (int ch : { 5, (int)chan::TAP_CH, trunk })
        for (size_t f = 0; same && f < out.size() / chan::N_PLAY_CH; ++f)
            if (out[f * chan::N_PLAY_CH + ch - 1] != idle[f * chan::N_PLAY_CH + ch - 1]) same = false;
    check(same, "station 5, the tap and the trunk carry only their fixed source again");
}

// tone_out()
//   One trunk's tone, alone: `periods` renders with the tone on, less the same
//   renders with it off, so the pilot cancels. Samples of that channel, -1..1.
static std::vector<double> tone_out(ToneKind k, int periods)
{
    const int ch = chan::trunk_slot(1);
    auto render = [&](bool on) {
        std::vector<double> out;
        auto sh = std::make_unique<Shared>();
        AlsaStream st;
        Engine eng(*sh, st);
        if (!eng.prepare_detached(256, chan::N_PLAY_CH, chan::N_CAP_CH)) return out;
        if (on) {
            Command c;
            c.verb = Verb::Tone;
            c.idx  = (int16_t)ch;
            c.arg  = (float)(int)k;
            sh->cmdq.push(c);
            eng.drain_for_test();
        }
        for (int p = 0; p < periods; ++p) {
            eng.render_for_test();
            const std::vector<int32_t> b = eng.playback();
            for (size_t f = 0; f < b.size() / chan::N_PLAY_CH; ++f)
                out.push_back(b[f * chan::N_PLAY_CH + ch - 1] / 2147483648.0);
        }
        return out;
    };
    std::vector<double> a = render(true), b = render(false);
    for (size_t i = 0; i < a.size() && i < b.size(); ++i) a[i] -= b[i];
    return a;
}

// goertzel_db()
//   Level of one frequency in x, in dB relative to full-scale sine.
static double goertzel_db(const std::vector<double>& x, double hz)
{
    double re = 0, im = 0;
    for (size_t i = 0; i < x.size(); ++i) {
        const double w = 2.0 * M_PI * hz * (double)i / chan::SAMPLE_RATE;
        re += x[i] * std::cos(w);
        im += x[i] * std::sin(w);
    }
    return 20.0 * std::log10(2.0 * std::hypot(re, im) / (double)x.size() + 1e-12);
}

// test_trunk_tones()
//   audio.md 8.2: ringback is the city ring of cityring.h (Rev 21) - repeating
//   every 2400 samples, its strongest line at 440Hz and almost nothing at the
//   nominal 420Hz, at the tones' peak level - and reorder runs 0.25s on, 0.25s
//   off (Rev 20).
static void test_trunk_tones()
{
    std::printf("trunk tones (audio.md 8.2, Rev 20, Rev 21)\n");
    const std::vector<double> r = tone_out(ToneKind::Ringback, 2 * chan::SAMPLE_RATE / 256);
    check(r.size() > 4 * CITY_RING_PERIOD, "ringback renders");
    double rep = 0, peak = 0;
    for (size_t i = 0; i + CITY_RING_PERIOD < r.size(); ++i) {
        rep  = std::max(rep, std::fabs(r[i] - r[i + CITY_RING_PERIOD]));
        peak = std::max(peak, std::fabs(r[i]));
    }
    check(rep < 1e-6, "ringback repeats every 2400 samples, 20Hz");
    const double want = std::pow(10.0, Options{}.tone_db / 20.0);
    check(std::fabs(peak - want) < 0.01 * want, "ringback's peak is the tone level");
    const std::vector<double> mid(r.begin(), r.begin() + 24 * CITY_RING_PERIOD / 2);
    const double l440 = goertzel_db(mid, 440), l420 = goertzel_db(mid, 420),
                 l1240 = goertzel_db(mid, 1240), l6000 = goertzel_db(mid, 6000);
    std::printf("    440Hz %.1f, 420Hz %.1f, 1240Hz %.1f, 6000Hz %.1f dBFS\n",
                l440, l420, l1240, l6000);
    check(l440 - l420 > 20, "the 440Hz sideband, not a 420Hz carrier");
    check(l440 - l1240 > 10 && l440 - l1240 < 25, "and the third harmonic's group near 1240Hz");
    check(l440 - l6000 > 80, "nothing near the comb");

    const std::vector<double> o = tone_out(ToneKind::Reorder, chan::SAMPLE_RATE / 256);
    auto rms = [&](size_t a, size_t b) {
        double s = 0;
        for (size_t i = a; i < b; ++i) s += o[i] * o[i];
        return std::sqrt(s / (double)(b - a));
    };
    const size_t q = chan::SAMPLE_RATE / 4;
    check(o.size() >= 4 * q - 256, "reorder renders");
    check(rms(0, q - 100) > 0.02 && rms(q + 100, 2 * q - 100) < 1e-6
          && rms(2 * q + 100, 3 * q - 100) > 0.02, "reorder: 0.25s on, 0.25s off");
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
        c.idx  = (int16_t)chan::MONITOR_PROG;
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
                const size_t i = (size_t)f * chan::N_PLAY_CH + chan::DIGIFACE_CH_A - 1;
                peak = std::max(peak, std::fabs((double)out[i] / 2147483648.0));
            }
            Result r;
            while (sh->res_audio.pop(r))
                if (r.topic == Topic::Play && r.idx == chan::MONITOR_PROG && r.value[0] == '\0')
                    finished = true;
        }
        return peak;
    };

    play(true);
    bool finished = false;
    const double on_peak = peak_over(25, finished);
    check(on_peak > 0.2 && on_peak < 0.3, "channel 33 carries the file at unity, through the low-pass");
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
    check(chan::monitor_source_channel("station/23") == 0, "station/23 is refused - it is the tap");
    check(chan::monitor_source_channel("station/25") == 0, "station/25 is refused");
    check(chan::monitor_source_channel("trunk/0")    == 0, "trunk/0 is refused");
    check(chan::monitor_source_channel("trunk/9")    == 0, "trunk/9 is refused - 8 trunks");

    // Station 24, the real telephone, is a source like any station (Rev 24).
    check(chan::monitor_source_channel("station/24") == 24, "station/24 is channel 24");

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
    check(chan::monitor_source_name(24, n, sizeof n) && std::strcmp(n, "station/24") == 0,
          "channel 24 echoes as station/24");

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

// test_monitor_gate()
//   audio.md 10.5, Rev 17: speech on the monitor's source passes, 10ms late;
//   ringing on the line shuts it, and it opens again after the hold.
static void test_monitor_gate()
{
    std::printf("the monitor's line-disturbance gate (audio.md 10.5, Rev 17)\n");
    auto sh = std::make_unique<Shared>();
    sh->opt.monitor_gate_db   = -60.0;
    sh->opt.monitor_gate_hold = 0.25;
    AlsaStream st;
    Engine eng(*sh, st);
    check(eng.prepare_detached(256, chan::N_PLAY_CH, chan::N_CAP_CH), "engine prepares");
    Command m;
    m.verb = Verb::Monitor; m.on = true; m.arg = 0.0f;
    sh->cmdq.push(m);
    eng.drain_for_test();
    double t = 0.0;
    // Periods with 1 kHz speech-like tone at -20dBFS, and ring at 20 Hz if asked;
    // returns the monitor's peak over them.
    auto run = [&](int periods, bool ring) {
        double peak = 0.0;
        for (int p = 0; p < periods; ++p) {
            float* in = eng.capture_row_for_test(chan::TAP_CH);
            for (int i = 0; i < 256; ++i, t += 1.0 / chan::SAMPLE_RATE)
                in[i] = (float)(0.1 * std::sin(2.0 * M_PI * 1000.0 * t)
                                + (ring ? 0.3 * std::sin(2.0 * M_PI * 20.0 * t) : 0.0));
            eng.capture_for_test();
            eng.render_for_test();
            const std::vector<int32_t>& out = eng.playback();
            const int n = (int)out.size() / chan::N_PLAY_CH;
            for (int f = 0; f < n; ++f) {
                const size_t i = (size_t)f * chan::N_PLAY_CH + chan::DIGIFACE_CH_A - 1;
                peak = std::max(peak, std::fabs((double)out[i] / 2147483648.0));
            }
        }
        return 20.0 * std::log10(peak + 1e-12);
    };
    run(100, false);    // the tone's abrupt start is a step the gate rightly shuts on
    const double speech = run(40, false);
    std::printf("    speech %.1f dBFS\n", speech);
    check(speech > -25.0, "speech passes");
    run(4, true);                                   // the gate shuts on the first
    const double ringing = run(40, true);
    std::printf("    ringing %.1f dBFS\n", ringing);
    check(ringing < speech - 40.0, "while it rings the monitor is shut");
    run(10, false);                                 // 53ms after: still held
    const double held = run(10, false);
    check(held < speech - 40.0, "and stays shut through the hold");
    run(60, false);                                 // the rest of the hold, and 20ms up
    const double after = run(20, false);
    check(after > speech - 1.0, "then opens again");
}

// test_monitor_limit()
//   audio.md 10.1, Rev 16: a limiter set just above speech holds a switch's
//   click to that level, and leaves speech below it alone.
static void test_monitor_limit()
{
    std::printf("monitor limiter at --monitor-limit (audio.md 10.1, Rev 16)\n");
    Limiter lim;
    lim.init(-30.0, 0.100, chan::SAMPLE_RATE);
    const double ceil = db_to_lin(-30.0);
    double worst = 0.0;
    for (int i = 0; i < 480; ++i) {                 // a 10ms click near full scale
        const double y = lim.run((i % 2 ? -0.9 : 0.9));
        worst = std::max(worst, std::fabs(y));
    }
    check(worst <= ceil * 1.0001, "a click at -1dBFS comes out no higher than -30dBFS");
    Limiter quiet;
    quiet.init(-30.0, 0.100, chan::SAMPLE_RATE);
    const double speech = db_to_lin(-36.0);
    bool same = true;
    for (int i = 0; i < 4800; ++i) {
        const double x = speech * std::sin(2.0 * M_PI * 1000.0 * i / chan::SAMPLE_RATE);
        same = same && std::fabs(quiet.run(x) - x) < 1e-12;
    }
    check(same, "speech peaking at -36dBFS passes untouched");
}

// test_recording()
//   audio.md 10.6, Rev 22: the audio thread hands the monitor row over only
//   while a recording runs; the Recorder writes it with the makeup gain that
//   puts --monitor-limit at -1dBFS, to a WAV named for the local time.
static void test_recording()
{
    std::printf("loudspeaker recording (audio.md 10.6, Rev 22)\n");
    char dir[] = "/tmp/sbaudio_rec_XXXXXX";
    if (!mkdtemp(dir)) { check(false, "a temporary directory"); return; }

    auto sh = std::make_unique<Shared>();
    sh->opt.record_dir = dir;
    sh->opt.monitor_limit_db = -30.0;
    AlsaStream st;
    Engine eng(*sh, st);
    Recorder rec(*sh);
    rec.prepare();
    if (!eng.prepare_detached(256, chan::N_PLAY_CH, chan::N_CAP_CH)) { check(false, "engine"); return; }

    std::vector<float> got(4096);
    eng.capture_for_test();
    check(sh->rec_ring.read(got.data(), got.size()) == 0, "not recording: nothing handed over");
    sh->rec_on.store(true);
    for (int i = 0; i < 4; ++i) eng.capture_for_test();
    sh->rec_on.store(false);
    check(sh->rec_ring.read(got.data(), got.size()) == 1024, "recording: every period handed over");

    const std::string name = rec.start();
    check(name.size() == 19 && name[4] == '-' && name[10] == '-' && name[13] == '-'
          && name[16] == '-', "named YYYY-MM-DD-HH-MM-SS");
    check(sh->rec_on.load(), "start sets rec_on");
    const double amp = db_to_lin(-40.0);
    std::vector<float> sig(256 * 188);
    for (size_t i = 0; i < sig.size(); ++i)
        sig[i] = (float)(amp * std::sin(2.0 * M_PI * 1000.0 * (double)i / chan::SAMPLE_RATE));
    for (size_t i = 0; i < sig.size(); i += 256) sh->rec_ring.write(&sig[i], 256);
    rec.service(monotonic_s());
    rec.stop(false);
    check(!sh->rec_on.load() && !rec.running(), "stop clears rec_on");

    const std::string path = std::string(dir) + "/" + name + ".wav";
    SF_INFO info; std::memset(&info, 0, sizeof info);
    SNDFILE* f = sf_open(path.c_str(), SFM_READ, &info);
    check(f != nullptr, "the WAV is there");
    if (f) {
        check(info.frames == 256 * 188 && info.samplerate == 48000 && info.channels == 1
              && (info.format & SF_FORMAT_SUBMASK) == SF_FORMAT_PCM_16,
              "every sample, 48kHz mono 16-bit");
        std::vector<float> back((size_t)info.frames);
        sf_read_float(f, back.data(), info.frames);
        sf_close(f);
        float pk = 0.0f;
        for (float v : back) pk = std::max(pk, std::fabs(v));
        check_near(lin_to_db(pk), -40.0 + 29.0, 0.1, "makeup: -40dBFS in, -11dBFS in the file");
    }

    const std::string again = rec.start();
    rec.stop(false);
    check(!again.empty() && again != name, "a second recording does not overwrite the first");

    // audio.md 10.7: the list, newest first, and playback at the monitor's level.
    check(rec.list() == again + " 0\n" + name + " 1", "the list: newest first, with seconds");
    Player pl(*sh);
    check(!pl.start("../etc/passwd") && !pl.start("2026-10-18-x"), "a name not a recording's is refused");
    check(pl.start(name) && pl.name() == name && !sh->play_on.load(), "start: named, samples next pass");
    pl.service();
    check(sh->play_on.load() && sh->play_ring.available() > 0, "next pass: playing, ring filled");
    float pk = 0.0f;
    for (int i = 0; i < 40; ++i) {
        eng.capture_for_test();
        for (float v : eng.monitor_row()) pk = std::max(pk, std::fabs(v));
    }
    check_near(lin_to_db(pk), -40.0, 0.1, "played back at the level recorded: -40dBFS");
    while (pl.service() == false && sh->play_ring.available() > 0)
        eng.capture_for_test();
    for (int i = 0; i < 300 && !pl.name().empty(); ++i) { eng.capture_for_test(); pl.service(); }
    check(pl.name().empty() && !sh->play_on.load(), "the end of the file ends the playback");
    std::string cmd = std::string("rm -rf ") + dir;
    check(std::system(cmd.c_str()) == 0, "cleaned up");
}

// Speech-like test signal: noise through a 300-3400 Hz band, in 4 Hz
// syllables, at about `db` dBFS while on. Deterministic.
struct Talker {
    uint32_t seed;
    BiquadState h, l[3];
    Biquad hp = butter_highpass(300.0, 48000.0);
    std::vector<Biquad> lp = butter_lowpass6(3400.0, 48000.0);
    double amp;
    uint64_t n = 0;
    Talker(uint32_t s, double db) : seed(s), amp(std::pow(10.0, db / 20.0) * 2.0) {}
    float next()
    {
        seed = seed * 1664525u + 1013904223u;
        double x = ((double)(seed >> 8) / 8388608.0 - 1.0);
        x = h.run(hp, x);
        for (int k = 0; k < 3; ++k) x = l[k].run(lp[k], x);
        const double env = 0.6 + 0.4 * std::sin(2.0 * M_PI * 4.0 * (double)n++ / 48000.0);
        return (float)(amp * env * x);
    }
};

static void test_aec()
{
    std::printf("echo canceller (audio.md 9.4, Rev 26)\n");

    {   // The class alone, at 8 kHz: an echo 12 dB down, 95 samples late
        // through a three-tap path, and a caller 20 dB below the echo for a
        // second in the middle.
        EchoCanceller ec;
        ec.configure(80);
        ec.start(0);
        Talker far(1, -20.0), near(2, -52.0);
        std::vector<float> ref(80000, 0.0f);
        double e_late = 0, c_late = 0, e_dt = 0, n_dt = 0, e_after = 0, c_after = 0;
        bool valid_late = true, valid_dt = true;
        for (uint32_t m = 0; m < 64000; ++m) {
            // Decimate the talker crudely: it is band-limited already.
            float x = 0; for (int k = 0; k < 6; ++k) x = far.next();
            ref[m] = x;
            ec.ref(m, x);
            float echo = 0.25f * (m >= 95 ? ref[m - 95] : 0.0f)
                       + 0.10f * (m >= 96 ? ref[m - 96] : 0.0f)
                       - 0.05f * (m >= 110 ? ref[m - 110] : 0.0f);
            float nr = 0; for (int k = 0; k < 6; ++k) nr = near.next();
            const bool dt = m >= 32000 && m < 40000;
            const float c = echo + (dt ? nr : 0.0f);
            const float e = ec.step(m, c);
            if (m >= 24000 && m < 32000) { e_late += e * e; c_late += c * c; }
            if (dt) { e_dt += (e - nr) * (e - nr); n_dt += nr * nr; }
            if (m >= 48000) { e_after += e * e; c_after += c * c; }
            if ((m + 1) % EchoCanceller::FRAME == 0) {
                const EchoCanceller::Frame f = ec.end_frame(m);
                if (m >= 24000 && m < 32000 && !f.valid) valid_late = false;
                if (dt && !f.valid) valid_dt = false;
            }
        }
        const double erle = 10.0 * std::log10(c_late / e_late);
        const double keep = 10.0 * std::log10(n_dt / e_dt);
        const double erle2 = 10.0 * std::log10(c_after / e_after);
        std::printf("    after 3 s: %.1f dB off; the caller kept to %.1f dB; after: %.1f dB\n",
                    erle, keep, erle2);
        check(erle > 30.0, "converged: the echo 30 dB down within 3 s");
        check(valid_late, "and reported converged");
        check(keep > 10.0, "a caller over the echo comes through: what is left is the caller");
        check(valid_dt, "still converged while the caller talks");
        check(erle2 > 30.0, "the caller did not spoil it: 30 dB off afterwards");
    }

    {   // In the engine: a file on station 5 that comes back 12 dB down, 562
        // samples late, as the bench measured, with a listen started with it.
        for (int talk = 0; talk < 2; ++talk) {
            auto sh = std::make_unique<Shared>();
            sh->opt.vad_floor = -70.0;
            sh->opt.vad_hangover = 0.5;
            AlsaStream st;
            Engine eng(*sh, st);
            eng.prepare_detached(256, chan::N_PLAY_CH, chan::N_CAP_CH);
            const int S = 5;
            Talker file(3, -20.0), caller(4, -50.0);
            Command c;
            c.verb = Verb::Play; c.idx = S; c.buf = new AudioBuffer;
            for (int i = 0; i < 4 * 48000; ++i) c.buf->samples.push_back(file.next());
            std::snprintf(c.name, sizeof c.name, "line");
            sh->cmdq.push(c);
            Command l; l.verb = Verb::Listen; l.idx = S; l.arg = 10.0f;
            sh->cmdq.push(l);
            std::vector<float> sent;
            double speech_at = -1, ended_at = -1;
            for (int per = 0; per < 6 * 48000 / 256; ++per) {
                float* cap = eng.capture_row_for_test(S);
                for (int i = 0; i < 256; ++i) {
                    const size_t t = (size_t)per * 256 + (size_t)i;
                    float v = t >= 562 && t - 562 < sent.size() ? 0.25f * sent[t - 562] : 0.0f;
                    if (talk && t >= 3 * 48000 && t < (size_t)(3.6 * 48000)) v += caller.next();
                    cap[i] = v;
                }
                eng.capture_for_test();
                eng.drain_for_test();
                eng.render_for_test();
                const std::vector<int32_t>& o = eng.playback();
                for (int i = 0; i < 256; ++i)
                    sent.push_back((float)o[(size_t)i * chan::N_PLAY_CH + S - 1] / 2147483648.0f);
                Result r;
                while (sh->res_audio.pop(r)) {
                    if (r.topic == Topic::Listen && r.idx == S && std::strcmp(r.value, "speech") == 0 && speech_at < 0)
                        speech_at = per * 256 / 48000.0;
                    if (r.topic == Topic::Play && r.idx == S && r.value[0] == 0 && ended_at < 0)
                        ended_at = per * 256 / 48000.0;
                    if (r.buf) delete r.buf;
                }
            }
            if (talk) {
                std::printf("    caller from 3.0 s: speech reported at %.2f s, the file ended at %.2f s\n",
                            speech_at, ended_at);
                check(speech_at >= 3.0 && speech_at < 3.5, "a caller talking over the file is heard during it");
            } else {
                std::printf("    no caller: speech reported at %.2f s, the file ended at %.2f s\n",
                            speech_at, ended_at);
                check(speech_at < 0, "no caller: nothing heard, the echo is not speech");
            }
        }
    }
}

// test_peer_boost()
//   audio.md 10.8, Rev 28: the monitor follows station 1, patched to station
//   2. Station 1's file comes back on its own line at 0.5, station 2's
//   through the cord at 0.1, 14dB lower. Lines alternate, 2 s each: after the
//   first of each, the boost is measured and the called party is raised to
//   the caller's level. With no peer heard, nothing is raised. Fixed by the
//   game at 6dB (Rev 29), it is 6dB, and the called party 8dB down.
static void test_peer_boost()
{
    std::printf("the monitor's peer boost (audio.md 10.8, Rev 28, 29)\n");
    for (int heard = 0; heard < 3; ++heard) {
        auto sh = std::make_unique<Shared>();
        AlsaStream st;
        Engine eng(*sh, st);
        eng.prepare_detached(256, chan::N_PLAY_CH, chan::N_CAP_CH);
        Command m; m.verb = Verb::Monitor; m.on = true; m.arg = 0.0f;
        sh->cmdq.push(m);
        Command src; src.verb = Verb::MonitorSrc; src.idx = 1;
        sh->cmdq.push(src);
        if (heard == 2) {
            Command p; p.verb = Verb::MonitorPeer; p.on = true; p.arg = 6.0f;
            sh->cmdq.push(p);
        }
        eng.drain_for_test();
        sh->heard_peer[1].store(heard ? 2 : 0);
        Talker a(5, -20.0), b(6, -20.0);
        std::vector<float> sent1, sent2;
        double lv[4] = { 0, 0, 0, 0 };          // monitor energy, last second of each line
        const int line_p = 2 * 48000 / 256;
        for (int line = 0; line < 4; ++line) {
            const int S = (line % 2 == 0) ? 1 : 2;
            Command c; c.verb = Verb::Play; c.idx = (int16_t)S; c.buf = new AudioBuffer;
            Talker& t = (S == 1) ? a : b;
            for (int i = 0; i < 2 * 48000 - 4800; ++i) c.buf->samples.push_back(t.next());
            const std::vector<float> file = c.buf->samples;
            std::snprintf(c.name, sizeof c.name, "line%d", line);
            sh->cmdq.push(c);
            for (int per = 0; per < line_p; ++per) {
                // The line returns what was sent two periods ago: the file
                // alone, since the pilots are outside the monitor's band.
                float* cap = eng.capture_row_for_test(1);
                for (int i = 0; i < 256; ++i) {
                    const size_t k = sent1.size() + (size_t)i;
                    cap[i] = k >= 512 ? 0.5f * sent1[k - 512] + 0.1f * sent2[k - 512] : 0.0f;
                }
                eng.capture_for_test();
                eng.drain_for_test();
                eng.render_for_test();
                const std::vector<int32_t>& o = eng.playback();
                for (int i = 0; i < 256; ++i) {
                    const size_t j = (size_t)per * 256 + (size_t)i;
                    const float v = j < file.size() ? file[j] : 0.0f;
                    sent1.push_back(S == 1 ? v : 0.0f);
                    sent2.push_back(S == 2 ? v : 0.0f);
                    const double mon = (double)o[(size_t)i * chan::N_PLAY_CH + chan::DIGIFACE_CH_A - 1] / 2147483648.0;
                    if (per >= line_p / 4 && per < line_p * 3 / 4) lv[line] += mon * mon;
                }
                Result r;
                while (sh->res_audio.pop(r)) if (r.buf) delete r.buf;
            }
        }
        const double caller = 10.0 * std::log10(lv[2] + 1e-20), called = 10.0 * std::log10(lv[3] + 1e-20);
        std::printf("    peer %s: caller %.1f dB, called %.1f dB, boost %.1f dB\n",
                    heard == 2 ? "fixed" : heard ? "heard" : "not heard", caller, called,
                    eng.peer_boost_db_for_test());
        if (heard == 2) {
            check(std::fabs(eng.peer_boost_db_for_test() - 6.0) < 0.1, "fixed by the game: 6 dB");
            check(std::fabs(caller - called - 8.0) < 1.5, "and the called party 8 dB down");
        } else if (heard) {
            check(std::fabs(caller - called) < 1.5, "the called party is raised to the caller's level");
            check(std::fabs(eng.peer_boost_db_for_test() - 14.0) < 1.0, "by the 14 dB between the paths");
        } else {
            check(caller - called > 12.0, "no peer heard: the called party is left 14 dB down");
        }
    }
}

static void test_ringing()
{
    std::printf("ring heard on a circuit (audio.md 9.5, Rev 30, Rev 36)\n");
    auto sh = std::make_unique<Shared>();
    AlsaStream st;
    Engine eng(*sh, st);
    eng.prepare_detached(256, chan::N_PLAY_CH, chan::N_CAP_CH);
    // Station 1 rung at the level measured on the switchboard, -25 dBFS rms;
    // station 2 carrying loud speech-band tone and hum, which must not count;
    // trunk 1 rung too, as the public line's ATA rings it; station 3 a plug's contact
    // bouncing, steps that decay through the transformer (Rev 31).
    const double ring = 0.056 * M_SQRT2;
    double ph = 0.0;
    std::vector<std::string> seen;
    double t_on = -1.0, t_off = -1.0;
    const int P = 48000 / 256;                                  // ~1 s of periods
    for (int per = 0; per < 3 * P; ++per) {
        const bool ringing = per >= P / 2 && per < 2 * P;       // 0.5 s to 2 s
        float* s1 = eng.capture_row_for_test(1);
        float* s2 = eng.capture_row_for_test(2);
        float* t1 = eng.capture_row_for_test(chan::trunk_slot(1));
        float* s3 = eng.capture_row_for_test(3);
        for (int i = 0; i < 256; ++i, ph += 1.0 / 48000.0) {
            const float r = ringing ? (float)(ring * std::sin(2 * M_PI * 20.0 * ph)) : 0.0f;
            s1[i] = r + 0.001f;                                 // and a little DC
            s2[i] = (float)(0.5 * std::sin(2 * M_PI * 300.0 * ph) + 0.01 * std::sin(2 * M_PI * 60.0 * ph));
            t1[i] = r;
            // mid-block, every block, sign alternating: a contact bouncing for 1.5 s
            const double tc = std::fmod(ph + 0.05, 0.1);
            const double sg = std::fmod(ph + 0.05, 0.2) >= 0.1 ? -1.0 : 1.0;
            s3[i] = ph >= 0.5 && ph < 2.0 ? (float)(0.3 * sg * std::exp(-tc / 0.02)) : 0.0f;
        }
        eng.capture_for_test();
        Result r;
        while (sh->res_audio.pop(r)) {
            if (r.buf) delete r.buf;
            if (r.topic != Topic::Ringing) continue;
            seen.push_back(std::to_string(r.idx) + " " + r.value);
            const double t = (per + 1) * 256.0 / 48000.0;
            if (r.idx == 1 && !std::strcmp(r.value, "on"))  t_on  = t;
            if (r.idx == 1 && !std::strcmp(r.value, "off")) t_off = t;
        }
    }
    for (const auto& x : seen) std::printf("    %s\n", x.c_str());
    std::printf("    on at %.2f s, off at %.2f s\n", t_on, t_off);
    const std::string t1 = std::to_string(chan::trunk_slot(1));
    check(seen.size() == 4 && seen[0] == "1 on" && seen[1] == t1 + " on"
          && seen[2] == "1 off" && seen[3] == t1 + " off",
          "station 1 and trunk 1 on then off, nothing else");
    check(t_on > 0.5 && t_on < 0.95, "on within 450 ms of the ring starting");
    check(t_off > 2.0 && t_off < 2.45, "off within 450 ms of it stopping");
}

int main()
{
    log_start();
    test_peer_boost();
    test_pilot_map();
    test_monitor_filter();
    test_monitor_limit();
    test_monitor_gate();
    test_detector();
    test_listener();
    test_hf_meter();
    test_monitor_ch();
    test_options();
    test_render_map();
    test_monitor_source();
    test_output_check();
    test_tap_play();
    test_stop_game();
    test_monitor_play();
    test_trunk_tones();
    test_recording();
    test_aec();
    test_ringing();
    std::printf("\n%s\n", failures ? "FAILURES" : "all checks passed");
    return failures ? 1 : 0;
}
