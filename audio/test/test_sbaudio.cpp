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
#include <string>
#include <vector>

#include "../src/channels.h"
#include "../src/detector.h"
#include "../src/dsp.h"
#include "../src/ipc.h"
#include "../src/util.h"

static int failures = 0;

static void check(bool ok, const char* what)
{
    std::printf("  %-58s %s\n", what, ok ? "ok" : "FAIL");
    if (!ok) ++failures;
}

static void check_near(double got, double want, double tol, const char* what)
{
    const bool ok = std::fabs(got - want) <= tol;
    std::printf("  %-58s %s  (%.3f, wanted %.3f +-%.3f)\n",
                what, ok ? "ok" : "FAIL", got, want, tol);
    if (!ok) ++failures;
}

// ---------------------------------------------------------------- filters

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

    // The tap: its own tone returning on its own channel.
    float* tap = d + (size_t)(chan::TAP_SLOT - 1) * chan::FFT_N;
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

    // Every other circuit is silence: deaf, and no peer.
    check(last(Topic::Peer, chan::station_slot(10)) == "deaf" && f,
          "an unconnected circuit reads deaf, not idle");

    // Slot 24 has no pilot and no circuit, so nothing may be published for it
    // and nothing may ever be reported as connected to it.
    bool any24 = false;
    for (const Result& x : all)
        if ((x.topic == Topic::Peer || x.topic == Topic::Op) && x.idx == chan::TAP_SLOT)
            any24 = true;
    check(!any24, "the tap strip publishes no peer or op of its own");
}

// ---------------------------------------------------------------- pilot map

static void test_pilot_map()
{
    std::printf("pilot map (docs/pilot-map.md)\n");
    check(chan::pilot_bin(1) == 512 && chan::pilot_bin(32) == 760,
          "the comb runs from bin 512 to bin 760");
    check_near(chan::pilot_hz(1), 6000.00, 0.005, "slot 1 is 6000.00 Hz");
    check_near(chan::pilot_hz(32), 8906.25, 0.005, "slot 32 is 8906.25 Hz");
    check_near(chan::OP_BIN * chan::BIN_HZ, 9000.00, 0.005, "the operator tone is 9000.00 Hz");
    check(chan::station_slot(23) == 23 && chan::trunk_slot(1) == 25,
          "station 23 is slot 23 and trunk 1 is slot 25");
    check(!chan::is_circuit_slot(chan::TAP_SLOT), "slot 24 is not a circuit");

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

int main()
{
    log_start();
    test_pilot_map();
    test_monitor_filter();
    test_detector();
    std::printf("\n%s\n", failures ? "FAILURES" : "all checks passed");
    return failures ? 1 : 0;
}
