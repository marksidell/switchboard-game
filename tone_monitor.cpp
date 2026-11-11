// tone_monitor.cpp
//
// Drive a tone on one output channel and print the level of that tone on one
// or more input channels, once a second, until interrupted. Built for hunting
// an intermittent connection by hand: flex the cord and watch the numbers.
//
// Each printed interval is split into ten sub-blocks and reported as min/max,
// so a contact that makes for a tenth of a second shows up as a jump in the
// max column instead of being averaged away.
//
// Levels come from a Hann-windowed DFT evaluated at exactly the drive
// frequency, not at a bin centre, so the estimate is exact for the tone
// regardless of how the block length divides the period.
//
// Channel numbers are 1-based, as in docs/audio.md: channel n is ALSA frame
// index n-1.
//
// Build:  g++ -O2 -Wall -Wextra -o tone_monitor tone_monitor.cpp -lasound
//
// Example (drive the trunk, watch the station; hw:1 stands for the card
// number or id in /proc/asound/cards):
//     ./tone_monitor -D hw:1 -p 8 -c 7,8 -f 1000
//
#include "bench_alsa.h"

#include <algorithm>
#include <cmath>
#include <complex>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <csignal>
#include <string>
#include <vector>
#include <unistd.h>

static const int SUBBLOCKS = 10;   // per printed interval

// ---------------------------------------------------------------- options

struct Opts {
    std::string      dev      = "hw:0";
    int              pchan1   = 1;        // 1-based drive channel
    std::vector<int> cchan1;              // 1-based monitored channels
    double           hz       = 1000.0;
    double           amp_dbfs = -12.0;
    double           interval = 1.0;      // seconds per printed line
    double           dur_s    = 0.0;      // 0 = until ^C
    double           mark_db  = -45.0;    // flag the first monitored channel above this
    unsigned         rate     = 48000;
    int              force_p  = 0;
    int              force_c  = 0;
};

static void usage(const char* p) {
    std::fprintf(stderr,
"Usage: %s [options]\n"
"  -D <dev>     ALSA device for both directions (default hw:0)\n"
"  -p <n>       output channel to drive, 1-based (default 1)\n"
"  -c <list>    input channels to watch, 1-based, comma separated (default 1)\n"
"  -f <Hz>      drive frequency, default 1000\n"
"  -a <dBFS>    drive amplitude, default -12\n"
"  -i <sec>     seconds per printed line, default 1.0\n"
"  -d <sec>     stop after this long, default 0 = until ^C\n"
"  -t <dBFS>    flag lines where the first watched channel exceeds this,\n"
"               default -45\n"
"  -X <n>       force playback channel count\n"
"  -Y <n>       force capture channel count\n"
"  -h           this help\n", p);
}

// ---------------------------------------------------------------- interrupt

static volatile sig_atomic_t g_stop = 0;
static void on_signal(int) { g_stop = 1; }

// ---------------------------------------------------------------- main

int main(int argc, char** argv)
{
    Opts o;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        const char* nx = (i + 1 < argc) ? argv[i + 1] : 0;
        if      (a == "-D" && nx) { o.dev      = nx;       ++i; }
        else if (a == "-p" && nx) { o.pchan1   = atoi(nx); ++i; }
        else if (a == "-c" && nx) {
            if (!split_ints(nx, o.cchan1)) { std::fprintf(stderr, "bad channel list: %s\n", nx); return 1; }
            ++i;
        }
        else if (a == "-f" && nx) { o.hz       = atof(nx); ++i; }
        else if (a == "-a" && nx) { o.amp_dbfs = atof(nx); ++i; }
        else if (a == "-i" && nx) { o.interval = atof(nx); ++i; }
        else if (a == "-d" && nx) { o.dur_s    = atof(nx); ++i; }
        else if (a == "-t" && nx) { o.mark_db  = atof(nx); ++i; }
        else if (a == "-X" && nx) { o.force_p  = atoi(nx); ++i; }
        else if (a == "-Y" && nx) { o.force_c  = atoi(nx); ++i; }
        else if (a == "-h")       { usage(argv[0]); return 0; }
        else { usage(argv[0]); return 1; }
    }
    if (o.cchan1.empty()) o.cchan1.push_back(1);
    if (!channel_ok("drive", o.pchan1, 0)) return 1;
    if (o.hz <= 0.0 || o.hz >= o.rate / 2.0) {
        std::fprintf(stderr, "frequency must be between 0 and %u Hz\n", o.rate / 2);
        return 1;
    }
    if (o.amp_dbfs > 0.0) { std::fprintf(stderr, "amplitude above 0 dBFS would clip\n"); return 1; }
    if (o.interval < 0.2) { std::fprintf(stderr, "interval must be at least 0.2 s\n"); return 1; }
    for (size_t i = 0; i < o.cchan1.size(); ++i)
        if (!channel_ok("watch", o.cchan1[i], 0)) return 1;

    const unsigned cneed = (unsigned)*std::max_element(o.cchan1.begin(), o.cchan1.end());

    Stream play, cap;
    if (configure(play, o.dev.c_str(), SND_PCM_STREAM_PLAYBACK, o.rate,
                  o.force_p, (unsigned)o.pchan1, 1024, false) < 0) return 1;
    if (configure(cap,  o.dev.c_str(), SND_PCM_STREAM_CAPTURE,  o.rate,
                  o.force_c, cneed, 1024, false) < 0) return 1;

    if (!channel_ok("drive", o.pchan1, play.chan)) return 1;
    const int pidx = o.pchan1 - 1;
    const size_t NM = o.cchan1.size();
    std::vector<int> cidx(NM);
    for (size_t i = 0; i < NM; ++i) {
        if (!channel_ok("watch", o.cchan1[i], cap.chan)) return 1;
        cidx[i] = o.cchan1[i] - 1;
    }

    const double amp   = std::pow(10.0, o.amp_dbfs / 20.0);
    const double step  = o.hz / (double)o.rate;
    const size_t psamp = fmt_bytes(play.fmt);
    const size_t csamp = fmt_bytes(cap.fmt);
    const int    Nsub  = (int)(o.interval * (double)o.rate / (double)SUBBLOCKS);

    std::printf("device   %s   playback %u ch, capture %u ch, %s, %u Hz\n",
                o.dev.c_str(), play.chan, cap.chan, snd_pcm_format_name(play.fmt), o.rate);
    std::printf("drive    %.2f Hz at %.1f dBFS on channel %d\n", o.hz, o.amp_dbfs, o.pchan1);
    std::printf("watch    ");
    for (size_t i = 0; i < NM; ++i) std::printf("%s%d", i ? ", " : "", o.cchan1[i]);
    std::printf("   (%d x %.0f ms sub-blocks per line, flagging ch %d above %.1f dBFS)\n\n",
                SUBBLOCKS, 1000.0 * Nsub / o.rate, o.cchan1[0], o.mark_db);

    std::printf("    t  ");
    for (size_t i = 0; i < NM; ++i) std::printf("|   ch%-2d min    max ", o.cchan1[i]);
    std::printf("|\n  -----");
    for (size_t i = 0; i < NM; ++i) std::printf("+--------------------");
    std::printf("+\n");
    std::fflush(stdout);

    std::signal(SIGINT,  on_signal);
    std::signal(SIGTERM, on_signal);

    const snd_pcm_uframes_t per = play.period;
    std::vector<uint8_t> pbuf((size_t)per * play.fbytes);
    std::vector<uint8_t> cbuf((size_t)per * cap.fbytes);

    // Analysis state: one complex accumulator per watched channel per sub-block.
    std::vector<std::complex<double> > acc(NM, std::complex<double>(0.0, 0.0));
    std::vector<double> wsum(1, 0.0);
    std::vector<std::vector<double> > sub(NM);      // levels of completed sub-blocks
    int    j       = 0;                             // sample index inside the sub-block
    double wtot    = 0.0;
    double phase   = 0.0;
    long   written = 0;
    int    xruns   = 0;
    long   line    = 0;
    const long total = (o.dur_s > 0.0) ? (long)(o.dur_s * (double)o.rate) : 0;

    snd_pcm_prepare(play.pcm);
    snd_pcm_prepare(cap.pcm);
    unsigned prefill = (unsigned)(play.buffer / per);
    if (prefill > 1) prefill -= 1; else prefill = 1;
    for (unsigned k = 0; k < prefill; ++k) {
        for (snd_pcm_uframes_t f = 0; f < per; ++f) {
            std::memset(&pbuf[f * play.fbytes], 0, play.fbytes);
            put_sample(&pbuf[f * play.fbytes + (size_t)pidx * psamp], play.fmt,
                       amp * std::sin(2.0 * M_PI * phase));
            phase += step; if (phase >= 1.0) phase -= 1.0;
        }
        snd_pcm_writei(play.pcm, pbuf.data(), per);
    }
    int err;
    if ((err = snd_pcm_start(play.pcm)) < 0) {
        std::fprintf(stderr, "start playback: %s\n", snd_strerror(err)); return 1;
    }
    if ((err = snd_pcm_start(cap.pcm)) < 0) {
        std::fprintf(stderr, "start capture: %s\n", snd_strerror(err)); return 1;
    }

    while (!g_stop && (total == 0 || written < total)) {
        snd_pcm_sframes_t r = snd_pcm_readi(cap.pcm, cbuf.data(), per);
        if (r < 0) {
            ++xruns;
            if (snd_pcm_recover(cap.pcm, (int)r, 1) < 0) {
                std::fprintf(stderr, "capture: %s\n", snd_strerror((int)r)); break;
            }
            snd_pcm_start(cap.pcm);
            continue;
        }
        for (snd_pcm_sframes_t f = 0; f < r; ++f) {
            // Hann-weighted DFT at exactly o.hz, accumulated over the sub-block.
            const double w   = 0.5 * (1.0 - std::cos(2.0 * M_PI * (double)j / (double)Nsub));
            const double ang = -2.0 * M_PI * o.hz * (double)j / (double)o.rate;
            const std::complex<double> rot(std::cos(ang), std::sin(ang));
            const uint8_t* base = &cbuf[(size_t)f * cap.fbytes];
            for (size_t m = 0; m < NM; ++m)
                acc[m] += get_sample(base + (size_t)cidx[m] * csamp, cap.fmt) * w * rot;
            wtot += w;
            if (++j >= Nsub) {
                for (size_t m = 0; m < NM; ++m) {
                    const double a = (wtot > 0.0) ? 2.0 * std::abs(acc[m]) / wtot : 0.0;
                    sub[m].push_back(20.0 * std::log10(a > 1e-12 ? a : 1e-12));
                    acc[m] = std::complex<double>(0.0, 0.0);
                }
                wtot = 0.0; j = 0;

                if ((int)sub[0].size() >= SUBBLOCKS) {
                    ++line;
                    std::printf("  %4ld ", line);
                    bool mark = false;
                    for (size_t m = 0; m < NM; ++m) {
                        double lo = sub[m][0], hi = sub[m][0];
                        for (size_t q = 1; q < sub[m].size(); ++q) {
                            lo = std::min(lo, sub[m][q]);
                            hi = std::max(hi, sub[m][q]);
                        }
                        std::printf("| %7.1f %7.1f ", lo, hi);
                        if (m == 0 && hi > o.mark_db) mark = true;
                        sub[m].clear();
                    }
                    std::printf("|%s\n", mark ? "  <== CONTACT" : "");
                    std::fflush(stdout);
                }
            }
            ++written;
        }

        for (snd_pcm_uframes_t f = 0; f < per; ++f) {
            std::memset(&pbuf[f * play.fbytes], 0, play.fbytes);
            put_sample(&pbuf[f * play.fbytes + (size_t)pidx * psamp], play.fmt,
                       amp * std::sin(2.0 * M_PI * phase));
            phase += step; if (phase >= 1.0) phase -= 1.0;
        }
        snd_pcm_sframes_t w2 = snd_pcm_writei(play.pcm, pbuf.data(), per);
        if (w2 < 0) {
            ++xruns;
            if (snd_pcm_recover(play.pcm, (int)w2, 1) < 0) {
                std::fprintf(stderr, "playback: %s\n", snd_strerror((int)w2)); break;
            }
        }
    }

    std::printf("\n  stopped after %.1f s, %d xrun(s)%s\n",
                (double)written / (double)o.rate, xruns, g_stop ? " (interrupted)" : "");
    snd_pcm_drop(play.pcm); snd_pcm_drop(cap.pcm);
    return 0;
}
