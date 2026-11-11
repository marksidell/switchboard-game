// monitor_check.cpp - every prompt through the loudspeaker's chain, offline,
// looking for the line-disturbance gate (audio.md 10.5) shutting on speech.
//
// Each wav is played into the capture channel of the monitor's source, scaled
// by --line-gain to stand for its return on its own line, through the
// program's own Engine: the 150Hz high-pass, the low-pass, the gate and the
// limiter, as sbaudio.service sets them. A file the gate shuts on is cut off
// on the loudspeaker in play. No audio device and no broker.
//
//     ./build/monitor_check                         every file, the service's settings
//     ./build/monitor_check --line-gain 0 v16       files whose name contains "v16"
//
// What it cannot see: anything the line adds. A file that passes here and is
// still cut off in play is being cut off by something on the line itself.

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <memory>
#include <string>
#include <vector>

#include "../src/alsa.h"
#include "../src/channels.h"
#include "../src/dsp.h"
#include "../src/engine.h"
#include "../src/ipc.h"
#include "../src/wav.h"

namespace {

struct Args {
    std::string dir   = "/home/sidell/s/sbgame/wav";    // sbaudio.service's --wav-dir
    double line_gain  = -17.5;  // file to its own receive channel (audio.md 1.19)
    double gate_db    = -70.0;  // sbaudio.service --monitor-gate
    double hold       = 0.25;   // --monitor-gate-hold's default
    double limit_db   = -18.0;  // sbaudio.service --monitor-limit
    double margin     = 6.0;    // list a file this close to the gate, too
    bool   all        = false;
    std::string match;
};

void usage()
{
    std::fprintf(stderr,
        "usage: monitor_check [--dir D] [--line-gain DB] [--gate DB] [--hold S]\n"
        "                     [--limit DB] [--margin DB] [--all] [MATCH]\n"
        "  --line-gain  a file's level on its own receive channel (-17.5)\n"
        "  --gate       --monitor-gate (-70)\n"
        "  --margin     also list files within this of the gate (6)\n"
        "  --all        list every file\n"
        "  MATCH        only files whose name contains it\n");
}

struct FileResult {
    std::string name;
    double   seconds  = 0.0;
    double   lf_db    = -200.0;     // peak below 50Hz at the gate's input
    unsigned shuts    = 0;
    double   muted_ms = 0.0;        // time the gate was more than half shut
};

// One file through a fresh engine, so no file inherits another's gate hold
// or limiter state.
bool run_one(const Args& a, const std::string& base, FileResult& r)
{
    std::unique_ptr<AudioBuffer> own;
    double hf = 0.0;
    const LoadResult lr = load_wav(a.dir, base, 600.0, own, hf);
    if (lr != LoadResult::Ok) {
        std::printf("%s: %s\n", base.c_str(), load_result_text(lr));
        return false;
    }

    constexpr unsigned PERIOD = 48;                 // 1ms, the resolution of muted_ms
    const int src = chan::trunk_slot(1);
    auto sh = std::make_unique<Shared>();
    sh->opt.monitor_on        = true;
    sh->opt.monitor_db        = 0.0;
    sh->opt.monitor_src       = src;
    sh->opt.monitor_limit_db  = a.limit_db;
    sh->opt.monitor_gate_db   = a.gate_db;
    sh->opt.monitor_gate_hold = a.hold;
    AlsaStream st;
    Engine eng(*sh, st);
    if (!eng.prepare_detached(PERIOD, chan::N_PLAY_CH, chan::N_CAP_CH)) return false;

    // The gate's own detector, 50Hz second-order run twice, for the margin.
    const Biquad lp = butter_lowpass(50.0, chan::SAMPLE_RATE);
    BiquadState s1, s2;
    double lf = 0.0;

    const double g = std::pow(10.0, a.line_gain / 20.0);
    const std::vector<float>& x = own->samples;
    const size_t lead = chan::SAMPLE_RATE / 2, tail = chan::SAMPLE_RATE / 2;
    const size_t total = lead + x.size() + tail;
    for (size_t p = 0; p < total; p += PERIOD) {
        float* in = eng.capture_row_for_test(src);
        for (unsigned i = 0; i < PERIOD; ++i) {
            const size_t k = p + i;
            const float v = (k >= lead && k - lead < x.size()) ? (float)(x[k - lead] * g) : 0.0f;
            in[i] = v;
            lf = std::max(lf, std::fabs(s2.run(lp, s1.run(lp, (double)v))));
        }
        eng.capture_for_test();
        if (eng.gate_gain() < 0.5) r.muted_ms += 1000.0 * PERIOD / chan::SAMPLE_RATE;
    }
    r.name    = base;
    r.seconds = (double)x.size() / chan::SAMPLE_RATE;
    r.lf_db   = 20.0 * std::log10(lf + 1e-12);
    r.shuts   = eng.gate_hits_for_test();
    return true;
}

}  // namespace

int main(int argc, char** argv)
{
    Args a;
    for (int i = 1; i < argc; ++i) {
        const std::string s = argv[i];
        auto num = [&](double& v) {
            if (i + 1 >= argc) { usage(); std::exit(2); }
            v = std::atof(argv[++i]);
        };
        if      (s == "--dir" && i + 1 < argc) a.dir = argv[++i];
        else if (s == "--line-gain") num(a.line_gain);
        else if (s == "--gate")      num(a.gate_db);
        else if (s == "--hold")      num(a.hold);
        else if (s == "--limit")     num(a.limit_db);
        else if (s == "--margin")    num(a.margin);
        else if (s == "--all")       a.all = true;
        else if (s == "-h" || s == "--help") { usage(); return 0; }
        else if (!s.empty() && s[0] == '-') { usage(); return 2; }
        else a.match = s;
    }

    std::vector<std::string> names;
    if (DIR* d = opendir(a.dir.c_str())) {
        while (dirent* e = readdir(d)) {
            std::string n = e->d_name;
            if (n.size() < 5 || n.compare(n.size() - 4, 4, ".wav") != 0) continue;
            n.resize(n.size() - 4);
            if (a.match.empty() || n.find(a.match) != std::string::npos) names.push_back(n);
        }
        closedir(d);
    } else {
        std::fprintf(stderr, "cannot read %s\n", a.dir.c_str());
        return 2;
    }
    std::sort(names.begin(), names.end());
    // prepare() logs the chain's settings to stderr; once per file is noise.
    if (!std::freopen("/dev/null", "w", stderr)) return 2;

    std::printf("%zu files from %s; line gain %.1f dB, gate %.1f dBFS below 50Hz, "
                "hold %.2fs, limiter %.1f dBFS\n\n",
                names.size(), a.dir.c_str(), a.line_gain, a.gate_db, a.hold, a.limit_db);
    std::printf("%-40s %6s %9s %6s %6s %9s\n", "file", "s", "LF dBFS", "margin", "shuts", "muted ms");

    unsigned cut = 0, near = 0;
    double worst = -200.0;
    std::string worst_name;
    for (const std::string& n : names) {
        FileResult r;
        if (!run_one(a, n, r)) continue;
        const double margin = a.gate_db - r.lf_db;
        if (r.shuts) ++cut;
        else if (margin < a.margin) ++near;
        if (r.lf_db > worst) { worst = r.lf_db; worst_name = n; }
        if (a.all || r.shuts || margin < a.margin)
            std::printf("%-40s %6.2f %9.1f %6.1f %6u %9.0f\n", n.c_str(), r.seconds,
                        r.lf_db, margin, r.shuts, r.muted_ms);
    }
    std::printf("\n%u of %zu files shut the gate; %u more within %.0f dB of it. "
                "Loudest below 50Hz: %s, %.1f dBFS, %.1f dB under the gate.\n",
                cut, names.size(), near, a.margin, worst_name.c_str(), worst, a.gate_db - worst);
    return cut ? 1 : 0;
}
