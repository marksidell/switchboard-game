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
// Build:  g++ -O2 -Wall -Wextra -o tone_monitor tone_monitor.cpp -lasound
//
// Example (drive the trunk, watch the station):
//     ./tone_monitor -D hw:1 -p 8 -c 7,8 -f 1000
//
#include <alsa/asoundlib.h>

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
"  -c <list>    input channels to watch, 1-based, comma separated\n"
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

static bool split_ints(const char* arg, std::vector<int>& out) {
    out.clear();
    const char* p = arg;
    while (*p) {
        char* end = 0;
        long v = std::strtol(p, &end, 10);
        if (end == p) return false;
        out.push_back((int)v);
        p = end;
        if (*p == ',') ++p;
        else if (*p)   return false;
    }
    return !out.empty();
}

// ---------------------------------------------------------------- interrupt

static volatile sig_atomic_t g_stop = 0;
static void on_signal(int) { g_stop = 1; }

// ---------------------------------------------------------------- sample I/O

static size_t fmt_bytes(snd_pcm_format_t f) {
    int w = snd_pcm_format_physical_width(f);
    return (w > 0) ? (size_t)(w / 8) : 0;
}

static void put_sample(uint8_t* p, snd_pcm_format_t f, double v) {
    if (v >  1.0) v =  1.0;
    if (v < -1.0) v = -1.0;
    switch (f) {
    case SND_PCM_FORMAT_S32_LE: {
        int32_t s = (int32_t)llrint(v * 2147483392.0);
        std::memcpy(p, &s, 4);
        break;
    }
    case SND_PCM_FORMAT_S24_3LE: {
        int32_t s = (int32_t)lrint(v * 8388607.0);
        p[0] = (uint8_t)(s & 0xff); p[1] = (uint8_t)((s >> 8) & 0xff);
        p[2] = (uint8_t)((s >> 16) & 0xff);
        break;
    }
    case SND_PCM_FORMAT_S16_LE: {
        int16_t s = (int16_t)lrint(v * 32767.0);
        std::memcpy(p, &s, 2);
        break;
    }
    default: break;
    }
}

static double get_sample(const uint8_t* p, snd_pcm_format_t f) {
    switch (f) {
    case SND_PCM_FORMAT_S32_LE: { int32_t s; std::memcpy(&s, p, 4); return (double)s / 2147483648.0; }
    case SND_PCM_FORMAT_S24_3LE: {
        int32_t s = (int32_t)((uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16));
        if (s & 0x800000) s |= (int32_t)0xff000000;
        return (double)s / 8388608.0;
    }
    case SND_PCM_FORMAT_S16_LE: { int16_t s; std::memcpy(&s, p, 2); return (double)s / 32768.0; }
    default: return 0.0;
    }
}

// ---------------------------------------------------------------- ALSA setup

struct Stream {
    snd_pcm_t*        pcm    = 0;
    snd_pcm_format_t  fmt    = SND_PCM_FORMAT_UNKNOWN;
    unsigned          chan   = 0;
    snd_pcm_uframes_t period = 0;
    snd_pcm_uframes_t buffer = 0;
    size_t            fbytes = 0;
};

static int cfg_fail(Stream& st, int err) {
    if (st.pcm) { snd_pcm_close(st.pcm); st.pcm = 0; }
    return err;
}

static int configure(Stream& st, const char* dev, snd_pcm_stream_t dir,
                     unsigned rate, int forced_chan, int need_chan)
{
    int err = snd_pcm_open(&st.pcm, dev, dir, 0);
    if (err < 0) {
        std::fprintf(stderr, "open %s (%s): %s\n", dev,
                     dir == SND_PCM_STREAM_PLAYBACK ? "playback" : "capture",
                     snd_strerror(err));
        return err;
    }
    snd_pcm_hw_params_t* hw;
    snd_pcm_hw_params_alloca(&hw);
    snd_pcm_hw_params_any(st.pcm, hw);

    if ((err = snd_pcm_hw_params_set_rate_resample(st.pcm, hw, 0)) < 0) {
        std::fprintf(stderr, "disable resample: %s\n", snd_strerror(err));
        return cfg_fail(st, err);
    }
    if ((err = snd_pcm_hw_params_set_access(st.pcm, hw, SND_PCM_ACCESS_RW_INTERLEAVED)) < 0) {
        std::fprintf(stderr, "set access: %s\n", snd_strerror(err));
        return cfg_fail(st, err);
    }
    static const snd_pcm_format_t cands[] = {
        SND_PCM_FORMAT_S32_LE, SND_PCM_FORMAT_S24_3LE, SND_PCM_FORMAT_S16_LE
    };
    for (size_t i = 0; i < sizeof(cands) / sizeof(cands[0]); ++i)
        if (snd_pcm_hw_params_test_format(st.pcm, hw, cands[i]) == 0) { st.fmt = cands[i]; break; }
    if (st.fmt == SND_PCM_FORMAT_UNKNOWN) {
        std::fprintf(stderr, "no supported sample format on %s\n", dev);
        return cfg_fail(st, -EINVAL);
    }
    if ((err = snd_pcm_hw_params_set_format(st.pcm, hw, st.fmt)) < 0) {
        std::fprintf(stderr, "set format: %s\n", snd_strerror(err));
        return cfg_fail(st, err);
    }
    unsigned r = rate;
    if ((err = snd_pcm_hw_params_set_rate(st.pcm, hw, r, 0)) < 0) {
        std::fprintf(stderr, "set rate %u: %s\n", r, snd_strerror(err));
        return cfg_fail(st, err);
    }
    unsigned cmin = 0, cmax = 0;
    snd_pcm_hw_params_get_channels_min(hw, &cmin);
    snd_pcm_hw_params_get_channels_max(hw, &cmax);
    unsigned want;
    if (forced_chan > 0)   want = (unsigned)forced_chan;
    else if (cmin == cmax) want = cmin;
    else                   want = std::max(cmin, (unsigned)need_chan);
    if ((err = snd_pcm_hw_params_set_channels_near(st.pcm, hw, &want)) < 0) {
        std::fprintf(stderr, "set channels: %s (device allows %u..%u)\n",
                     snd_strerror(err), cmin, cmax);
        return cfg_fail(st, err);
    }
    st.chan = want;

    snd_pcm_uframes_t period = 1024;
    int dir0 = 0;
    if ((err = snd_pcm_hw_params_set_period_size_near(st.pcm, hw, &period, &dir0)) < 0) {
        std::fprintf(stderr, "set period: %s\n", snd_strerror(err));
        return cfg_fail(st, err);
    }
    snd_pcm_uframes_t bufsz = period * 4;
    if ((err = snd_pcm_hw_params_set_buffer_size_near(st.pcm, hw, &bufsz)) < 0) {
        std::fprintf(stderr, "set buffer: %s\n", snd_strerror(err));
        return cfg_fail(st, err);
    }
    if ((err = snd_pcm_hw_params(st.pcm, hw)) < 0) {
        std::fprintf(stderr, "hw_params: %s\n", snd_strerror(err));
        return cfg_fail(st, err);
    }
    snd_pcm_hw_params_get_period_size(hw, &st.period, 0);
    snd_pcm_hw_params_get_buffer_size(hw, &st.buffer);
    st.fbytes = fmt_bytes(st.fmt) * st.chan;

    snd_pcm_sw_params_t* sw;
    snd_pcm_sw_params_alloca(&sw);
    snd_pcm_sw_params_current(st.pcm, sw);
    snd_pcm_sw_params_set_start_threshold(st.pcm, sw, st.buffer * 2);   // start explicitly
    snd_pcm_sw_params_set_avail_min(st.pcm, sw, st.period);
    if ((err = snd_pcm_sw_params(st.pcm, sw)) < 0) {
        std::fprintf(stderr, "sw_params: %s\n", snd_strerror(err));
        return cfg_fail(st, err);
    }
    return 0;
}

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
    if (o.pchan1 < 1)     { std::fprintf(stderr, "channels are 1-based\n"); return 1; }
    if (o.hz <= 0.0 || o.hz >= o.rate / 2.0) {
        std::fprintf(stderr, "frequency must be between 0 and %u Hz\n", o.rate / 2);
        return 1;
    }
    if (o.amp_dbfs > 0.0) { std::fprintf(stderr, "amplitude above 0 dBFS would clip\n"); return 1; }
    if (o.interval < 0.2) { std::fprintf(stderr, "interval must be at least 0.2 s\n"); return 1; }
    for (size_t i = 0; i < o.cchan1.size(); ++i)
        if (o.cchan1[i] < 1) { std::fprintf(stderr, "channels are 1-based\n"); return 1; }

    int cneed = 1;
    for (size_t i = 0; i < o.cchan1.size(); ++i) cneed = std::max(cneed, o.cchan1[i]);

    Stream play, cap;
    if (configure(play, o.dev.c_str(), SND_PCM_STREAM_PLAYBACK, o.rate, o.force_p, o.pchan1) < 0) return 1;
    if (configure(cap,  o.dev.c_str(), SND_PCM_STREAM_CAPTURE,  o.rate, o.force_c, cneed)     < 0) return 1;

    const int pidx = o.pchan1 - 1;
    if (pidx >= (int)play.chan) {
        std::fprintf(stderr, "drive channel %d out of range (device has %u)\n", o.pchan1, play.chan);
        return 1;
    }
    const size_t NM = o.cchan1.size();
    std::vector<int> cidx(NM);
    for (size_t i = 0; i < NM; ++i) {
        cidx[i] = o.cchan1[i] - 1;
        if (cidx[i] >= (int)cap.chan) {
            std::fprintf(stderr, "watch channel %d out of range (device has %u)\n",
                         o.cchan1[i], cap.chan);
            return 1;
        }
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
    snd_pcm_close(play.pcm); snd_pcm_close(cap.pcm);
    return 0;
}
