// pilot_loopback_test.cpp
//
// Per-channel pilot tone loopback test for the 551 switchboard audio path.
//
// Plays one pilot tone on each of 8 consecutive output channels while
// simultaneously capturing 8 consecutive input channels, then runs a 4096-point
// FFT on each captured channel and reports which pilot slot was heard.
//
// Pilot plan (matches the switchboard detection scheme):
//     fs        = 48000 Hz
//     N         = 4096
//     bin width = 11.71875 Hz
//     slot n    -> bin 512 + 8*(n-1)   ->  6000.00 + 93.75*(n-1) Hz
//
// Every pilot completes an integer number of cycles in N samples, so the
// generator buffer is exactly one FFT frame long and repeats seamlessly.
//
// Analysis uses a Hann window throughout. Coherent sampling would make a
// rectangular window leakage-free in principle, and it reads the same level -
// but only while coherence holds exactly. Displace a tone by 0.1 bin (a small
// clock error, or one sample slip anywhere in the window) and rectangular
// leakage puts about -67 dBFS into the neighbouring pilot bin, which is
// indistinguishable from real crosstalk; Hann puts -103 dBFS there.
//
// Build:  g++ -O2 -Wall -o pilot_loopback_test pilot_loopback_test.cpp -lasound
//
// Typical use (optical loopback, ADAT port 1 = channels 1-8):
//     ./pilot_loopback_test -D hw:Digiface
//
#include <alsa/asoundlib.h>

#include <algorithm>
#include <cmath>
#include <complex>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

// ---------------------------------------------------------------- constants

static const unsigned SAMPLE_RATE     = 48000;
static const int      FFT_N           = 4096;
static const double   BIN_HZ          = (double)SAMPLE_RATE / (double)FFT_N;  // 11.71875
static const int      PILOT_BIN_BASE  = 512;   // 6000.00 Hz
static const int      PILOT_BIN_STEP  = 8;     //   93.75 Hz
static const int      NCH             = 8;     // channels under test
static const double   HANN_ENBW       = 1.5;   // equivalent noise bandwidth, bins

static inline int    pilot_bin(int n1) { return PILOT_BIN_BASE + PILOT_BIN_STEP * (n1 - 1); }
static inline double pilot_hz (int n1) { return pilot_bin(n1) * BIN_HZ; }

// The peak search is confined to the neighbourhood of the pilot comb. Over the
// whole spectrum a mains harmonic can outrank the pilot on a channel with heavy
// hum, which then drags the detected bin - and every gain metric taken at it -
// onto a 60 Hz line without anything marking the row as bogus.
static const int PILOT_SEARCH_MARGIN = 16;
static inline int pilot_search_lo() {
    return std::max(1, PILOT_BIN_BASE - PILOT_SEARCH_MARGIN);
}
static inline int pilot_search_hi() {
    return std::min(FFT_N / 2 - 1,
                    PILOT_BIN_BASE + PILOT_BIN_STEP * (NCH - 1) + PILOT_SEARCH_MARGIN);
}

// ---------------------------------------------------------------- options

struct Opts {
    std::string pdev      = "hw:0";
    std::string cdev      = "";      // defaults to pdev
    double      amp_dbfs  = -12.0;
    double      settle_s  = 1.0;
    int         nblocks   = 8;       // FFT frames to average
    int         pfirst    = 0;       // 0-based first playback channel
    int         cfirst    = 0;       // 0-based first capture channel
    int         pchan     = 0;       // 0 = query device
    int         cchan     = 0;
    double      min_dbfs  = -40.0;   // pass threshold for the wanted pilot
    double      mains_hz  = 60.0;    // hum fundamental
    bool        table_only = false;
    bool        selftest   = false;  // synthesise instead of capturing
    bool        listen     = false;  // report every pilot heard, no pass/fail
    bool        tset       = false;  // -t was given explicitly
};

static void usage(const char* p) {
    std::fprintf(stderr,
"Usage: %s [options]\n"
"  -D <dev>     ALSA device for both directions (default hw:0)\n"
"  -P <dev>     playback device (overrides -D)\n"
"  -C <dev>     capture device  (overrides -D)\n"
"  -a <dBFS>    tone amplitude per channel, default -12\n"
"  -s <sec>     settle time before analysis, default 1.0\n"
"  -n <count>   FFT frames to average, default 8\n"
"  -p <idx>     0-based first playback channel, default 0\n"
"  -c <idx>     0-based first capture channel, default 0\n"
"  -X <n>       force playback channel count on the device\n"
"  -Y <n>       force capture channel count on the device\n"
"  -t <dBFS>    minimum level to call a pilot present, default -40\n"
"  -m <Hz>      mains frequency for the hum metric, 50 or 60, default 60\n"
"  -l           listen: list every pilot each input hears, no pass/fail\n"
"               (threshold defaults to -70 dBFS in this mode)\n"
"  -T           print the tone table and exit\n"
"  -S           self-test: synthesise a known signal, no audio hardware used\n"
"  -h           this help\n", p);
}

// ---------------------------------------------------------------- FFT

static void fft_inplace(std::vector<std::complex<double> >& a) {
    const size_t n = a.size();
    for (size_t i = 1, j = 0; i < n; ++i) {
        size_t bit = n >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) std::swap(a[i], a[j]);
    }
    for (size_t len = 2; len <= n; len <<= 1) {
        const double ang = -2.0 * M_PI / (double)len;
        const std::complex<double> wlen(std::cos(ang), std::sin(ang));
        for (size_t i = 0; i < n; i += len) {
            std::complex<double> w(1.0, 0.0);
            for (size_t k = 0; k < len / 2; ++k) {
                const std::complex<double> u = a[i + k];
                const std::complex<double> v = a[i + k + len / 2] * w;
                a[i + k]           = u + v;
                a[i + k + len / 2] = u - v;
                w *= wlen;
            }
        }
    }
}

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
        // Encode 1.0 as 2^31 - 256 so the value survives the device truncating
        // to 24 bits. get_sample() divides by 2^31, because that is what full
        // scale means coming back in; the 1.0e-6 dB difference between the two
        // constants is deliberate, not an oversight.
        int32_t s = (int32_t)llrint(v * 2147483392.0);
        std::memcpy(p, &s, 4);
        break;
    }
    case SND_PCM_FORMAT_S24_3LE: {
        int32_t s = (int32_t)lrint(v * 8388607.0);
        p[0] = (uint8_t)( s        & 0xff);
        p[1] = (uint8_t)((s >>  8) & 0xff);
        p[2] = (uint8_t)((s >> 16) & 0xff);
        break;
    }
    case SND_PCM_FORMAT_S16_LE: {
        int16_t s = (int16_t)lrint(v * 32767.0);
        std::memcpy(p, &s, 2);
        break;
    }
    default:
        break;
    }
}

static double get_sample(const uint8_t* p, snd_pcm_format_t f) {
    switch (f) {
    case SND_PCM_FORMAT_S32_LE: {
        int32_t s; std::memcpy(&s, p, 4);
        return (double)s / 2147483648.0;
    }
    case SND_PCM_FORMAT_S24_3LE: {
        int32_t s = (int32_t)((uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16));
        if (s & 0x800000) s |= (int32_t)0xff000000;
        return (double)s / 8388608.0;
    }
    case SND_PCM_FORMAT_S16_LE: {
        int16_t s; std::memcpy(&s, p, 2);
        return (double)s / 32768.0;
    }
    default:
        return 0.0;
    }
}

// ---------------------------------------------------------------- ALSA setup

struct Stream {
    snd_pcm_t*           pcm    = 0;
    snd_pcm_format_t     fmt    = SND_PCM_FORMAT_UNKNOWN;
    unsigned             chan   = 0;
    snd_pcm_uframes_t    period = 0;
    snd_pcm_uframes_t    buffer = 0;
    size_t               fbytes = 0;   // bytes per frame
};

// configure() has already opened the device by the time most of its checks
// run, so every failure after that point has to hand the handle back.
static int cfg_fail(Stream& st, int err)
{
    if (st.pcm) { snd_pcm_close(st.pcm); st.pcm = 0; }
    return err;
}

static int configure(Stream& st, const char* dev, snd_pcm_stream_t dir,
                     int forced_chan, snd_pcm_uframes_t want_period)
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
    st.fmt = SND_PCM_FORMAT_UNKNOWN;
    for (size_t i = 0; i < sizeof(cands) / sizeof(cands[0]); ++i) {
        if (snd_pcm_hw_params_test_format(st.pcm, hw, cands[i]) == 0) { st.fmt = cands[i]; break; }
    }
    if (st.fmt == SND_PCM_FORMAT_UNKNOWN) {
        std::fprintf(stderr, "no supported sample format on %s\n", dev);
        return cfg_fail(st, -EINVAL);
    }
    if ((err = snd_pcm_hw_params_set_format(st.pcm, hw, st.fmt)) < 0) {
        std::fprintf(stderr, "set format: %s\n", snd_strerror(err));
        return cfg_fail(st, err);
    }

    unsigned rate = SAMPLE_RATE;
    if ((err = snd_pcm_hw_params_set_rate(st.pcm, hw, rate, 0)) < 0) {
        std::fprintf(stderr, "set rate %u: %s (is the clock locked to 48k?)\n",
                     rate, snd_strerror(err));
        return cfg_fail(st, err);
    }

    unsigned cmin = 0, cmax = 0;
    snd_pcm_hw_params_get_channels_min(hw, &cmin);
    snd_pcm_hw_params_get_channels_max(hw, &cmax);
    unsigned want;
    if (forced_chan > 0)      want = (unsigned)forced_chan;
    else if (cmin == cmax)    want = cmin;              // fixed-width device (typical RME)
    else                      want = std::max(cmin, (unsigned)NCH);
    if ((err = snd_pcm_hw_params_set_channels_near(st.pcm, hw, &want)) < 0) {
        std::fprintf(stderr, "set channels: %s (device allows %u..%u)\n",
                     snd_strerror(err), cmin, cmax);
        return cfg_fail(st, err);
    }
    st.chan = want;

    snd_pcm_uframes_t period = want_period;
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
    // Never auto-start; we start both directions explicitly.
    snd_pcm_sw_params_set_start_threshold(st.pcm, sw, st.buffer * 2);
    snd_pcm_sw_params_set_avail_min(st.pcm, sw, st.period);
    if ((err = snd_pcm_sw_params(st.pcm, sw)) < 0) {
        std::fprintf(stderr, "sw_params: %s\n", snd_strerror(err));
        return cfg_fail(st, err);
    }
    return 0;
}

// ---------------------------------------------------------------- capture loop

// A dropout in either direction breaks the analysis window: on capture the
// samples are simply missing, and on playback the tone the ADC just heard has
// a splice in it, which smears the spectrum exactly like a clock error. Either
// way the window has to be thrown away and started over. The retry cap is what
// stops a persistently glitching link from spinning here forever - without it
// the program hangs instead of failing.
static const int MAX_RESTARTS = 10;

static bool restart_window(std::vector<std::vector<double> >& rec, int& done, int& restarts)
{
    for (size_t n = 0; n < rec.size(); ++n) rec[n].clear();
    done = 0;
    if (++restarts > MAX_RESTARTS) {
        std::fprintf(stderr,
                     "link kept glitching: %d dropouts, never got a clean window\n",
                     restarts);
        return false;
    }
    return true;
}

// ---------------------------------------------------------------- main

int main(int argc, char** argv)
{
    Opts o;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        const char* nx = (i + 1 < argc) ? argv[i + 1] : 0;
        if      (a == "-D" && nx) { o.pdev = nx; o.cdev = nx; ++i; }
        else if (a == "-P" && nx) { o.pdev = nx; ++i; }
        else if (a == "-C" && nx) { o.cdev = nx; ++i; }
        else if (a == "-a" && nx) { o.amp_dbfs = atof(nx); ++i; }
        else if (a == "-s" && nx) { o.settle_s = atof(nx); ++i; }
        else if (a == "-n" && nx) { o.nblocks  = atoi(nx); ++i; }
        else if (a == "-p" && nx) { o.pfirst   = atoi(nx); ++i; }
        else if (a == "-c" && nx) { o.cfirst   = atoi(nx); ++i; }
        else if (a == "-X" && nx) { o.pchan    = atoi(nx); ++i; }
        else if (a == "-Y" && nx) { o.cchan    = atoi(nx); ++i; }
        else if (a == "-t" && nx) { o.min_dbfs = atof(nx); o.tset = true; ++i; }
        else if (a == "-m" && nx) { o.mains_hz = atof(nx); ++i; }
        else if (a == "-l")       { o.listen = true; }
        else if (a == "-T")       { o.table_only = true; }
        else if (a == "-S")       { o.selftest = true; }
        else if (a == "-h")       { usage(argv[0]); return 0; }
        else { usage(argv[0]); return 1; }
    }
    if (o.cdev.empty()) o.cdev = o.pdev;
    if (o.nblocks < 1) o.nblocks = 1;

    std::printf("Pilot tone table  (fs=%u  N=%d  bin=%.5f Hz)\n",
                SAMPLE_RATE, FFT_N, BIN_HZ);
    std::printf("  ch    bin        Hz     cycles/frame\n");
    for (int n = 1; n <= NCH; ++n)
        std::printf("  %2d   %4d  %9.2f   %6d\n", n, pilot_bin(n), pilot_hz(n), pilot_bin(n));
    std::printf("\n");
    if (o.table_only) return 0;

    const int analyze_frames = o.nblocks * FFT_N;
    std::vector<std::vector<double> > rec(NCH);
    for (int n = 0; n < NCH; ++n) rec[n].reserve(analyze_frames);
    int xruns = 0;

if (o.selftest) {
    // Synthesise a known signal so the metrics below can be checked without
    // hardware: pilot at the requested level, H2 at -60 dBc, mains hum at
    // -70 dBFS, white noise at -90 dBFS rms.
    const double amp   = std::pow(10.0, o.amp_dbfs / 20.0);
    const double h2    = amp * std::pow(10.0, -60.0 / 20.0);
    const double hum   = std::pow(10.0, -70.0 / 20.0);
    // Levels are referenced to a full-scale SINE, so noise reading -90 dBFS has
    // rms of 0.707 * 10^(-90/20). This is the usual audio noise-floor convention
    // and it makes SNR = pilot_dBFS - noise_dBFS come out directly.
    const double nrms  = std::pow(10.0, -90.0 / 20.0) * M_SQRT1_2;
    std::srand(1);
    std::printf("SELF-TEST: synthetic signal, expect THD -60.0 dBc, hum -70.0 dBFS, noise -90.0 dBFS\n"
           "           (noise is a few tenths low: the excluded pilot/hum bins remove a little of it)\n\n");
    for (int n = 0; n < NCH; ++n) {
        const double b = (double)pilot_bin(n + 1);
        for (int i = 0; i < analyze_frames; ++i) {
            double t = (double)i / (double)SAMPLE_RATE;
            double v = amp * std::sin(2.0 * M_PI * b * (double)i / (double)FFT_N)
                     + h2  * std::sin(4.0 * M_PI * b * (double)i / (double)FFT_N)
                     + hum * std::sin(2.0 * M_PI * o.mains_hz * t);
            // uniform noise, scaled to the requested rms
            double u = ((double)std::rand() / (double)RAND_MAX) * 2.0 - 1.0;
            v += nrms * u * std::sqrt(3.0);
            rec[n].push_back(v);
        }
    }
} else {

    // ---- open both directions
    Stream play, cap;
    if (configure(play, o.pdev.c_str(), SND_PCM_STREAM_PLAYBACK, o.pchan, 1024) < 0) return 1;
    if (configure(cap,  o.cdev.c_str(), SND_PCM_STREAM_CAPTURE,  o.cchan, 1024) < 0) return 1;

    std::printf("playback %-14s %u ch  %s  period %lu  buffer %lu\n",
                o.pdev.c_str(), play.chan, snd_pcm_format_name(play.fmt),
                (unsigned long)play.period, (unsigned long)play.buffer);
    std::printf("capture  %-14s %u ch  %s  period %lu  buffer %lu\n\n",
                o.cdev.c_str(), cap.chan, snd_pcm_format_name(cap.fmt),
                (unsigned long)cap.period, (unsigned long)cap.buffer);

    // The whole measurement rests on playback and capture counting samples at
    // the same rate. On one device they share a clock and that is automatic.
    // On two devices it is only true if they are word-clock locked, and if they
    // are not, the pilots drift off their bins and every weak reading becomes
    // window leakage rather than a measurement. The streams are deliberately
    // not snd_pcm_link()ed: linking buys nothing here (each pilot is periodic
    // over exactly one FFT frame, so any contiguous window is coherent
    // regardless of how the two directions line up) and it complicates dropout
    // recovery, which has to restart the analysis window anyway.
    if (o.pdev != o.cdev) {
        std::fprintf(stderr,
            "warning: playback (%s) and capture (%s) are different devices.\n"
            "         Unless they are word-clock locked, coherent sampling does\n"
            "         not hold and levels below roughly -90 dBFS are leakage,\n"
            "         not measurements.\n\n",
            o.pdev.c_str(), o.cdev.c_str());
    }

    if (o.pfirst < 0 || o.pfirst + NCH > (int)play.chan) {
        std::fprintf(stderr, "playback channels %d..%d out of range (device has %u)\n",
                     o.pfirst, o.pfirst + NCH - 1, play.chan);
        return 1;
    }
    if (o.cfirst < 0 || o.cfirst + NCH > (int)cap.chan) {
        std::fprintf(stderr, "capture channels %d..%d out of range (device has %u)\n",
                     o.cfirst, o.cfirst + NCH - 1, cap.chan);
        return 1;
    }

    // ---- build the seamless tone frame (exactly FFT_N frames long)
    const double amp = std::pow(10.0, o.amp_dbfs / 20.0);
    const size_t psamp = fmt_bytes(play.fmt);
    std::vector<uint8_t> tone((size_t)FFT_N * play.fbytes, 0);
    for (int i = 0; i < FFT_N; ++i) {
        for (int n = 1; n <= NCH; ++n) {
            const double cycles = (double)pilot_bin(n);          // integer cycles per frame
            const double v = amp * std::sin(2.0 * M_PI * cycles * (double)i / (double)FFT_N);
            uint8_t* p = &tone[(size_t)i * play.fbytes + (size_t)(o.pfirst + n - 1) * psamp];
            put_sample(p, play.fmt, v);
        }
    }

    // ---- run the duplex loop
    const snd_pcm_uframes_t per = play.period;
    const int settle_frames  = (int)(o.settle_s * SAMPLE_RATE);

    std::vector<uint8_t> pbuf((size_t)per * play.fbytes);
    std::vector<uint8_t> cbuf((size_t)per * cap.fbytes);

    size_t tphase   = 0;   // frame index into the tone frame
    int    done     = 0;   // frames consumed since start
    int    restarts = 0;   // analysis windows discarded after a dropout

    snd_pcm_prepare(play.pcm);
    snd_pcm_prepare(cap.pcm);

    // Prefill playback so the DACs never see a hole. Leave one period free:
    // the stream is not running yet, so filling the buffer completely would
    // make the next writei() block forever waiting for space.
    unsigned prefill = (unsigned)(play.buffer / per);
    if (prefill > 1) prefill -= 1; else prefill = 1;
    for (unsigned k = 0; k < prefill; ++k) {
        for (snd_pcm_uframes_t f = 0; f < per; ++f) {
            std::memcpy(&pbuf[f * play.fbytes], &tone[tphase * play.fbytes], play.fbytes);
            tphase = (tphase + 1) % FFT_N;
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

    std::printf("running: %.1f s settle, %d x %d frames analysed ...\n",
                o.settle_s, o.nblocks, FFT_N);

    while (done < settle_frames + analyze_frames) {
        snd_pcm_sframes_t r = snd_pcm_readi(cap.pcm, cbuf.data(), per);
        if (r < 0) {
            ++xruns;
            if (snd_pcm_recover(cap.pcm, (int)r, 1) < 0) {
                std::fprintf(stderr, "capture: %s\n", snd_strerror((int)r)); return 1;
            }
            if (!restart_window(rec, done, restarts)) return 1;
            snd_pcm_start(cap.pcm);
            continue;
        }
        for (snd_pcm_sframes_t f = 0; f < r; ++f) {
            if (done >= settle_frames && (int)rec[0].size() < analyze_frames) {
                const uint8_t* base = &cbuf[(size_t)f * cap.fbytes];
                const size_t   cs   = fmt_bytes(cap.fmt);
                for (int n = 0; n < NCH; ++n)
                    rec[n].push_back(get_sample(base + (size_t)(o.cfirst + n) * cs, cap.fmt));
            }
            ++done;
        }

        for (snd_pcm_uframes_t f = 0; f < per; ++f) {
            std::memcpy(&pbuf[f * play.fbytes], &tone[tphase * play.fbytes], play.fbytes);
            tphase = (tphase + 1) % FFT_N;
        }
        snd_pcm_sframes_t w = snd_pcm_writei(play.pcm, pbuf.data(), per);
        if (w < 0) {
            // Frames were dropped on the way out, so the tone that reached the
            // ADC has a discontinuity in it. Analysing that window would report
            // leakage skirts as crosstalk, so discard it too.
            ++xruns;
            if (snd_pcm_recover(play.pcm, (int)w, 1) < 0) {
                std::fprintf(stderr, "playback: %s\n", snd_strerror((int)w)); return 1;
            }
            if (!restart_window(rec, done, restarts)) return 1;
        }
    }

    snd_pcm_drop(play.pcm);
    snd_pcm_drop(cap.pcm);
    snd_pcm_close(play.pcm);
    snd_pcm_close(cap.pcm);
}

    // ---- analyse: average the power spectra of nblocks Hann-windowed frames
    const int NB = FFT_N / 2;

    // One spectrum, Hann-windowed, used for every figure below. A rectangular
    // window is leakage-free for a perfectly coherent tone and reads the same
    // level, but it degrades badly the moment coherence slips: 0.1 bin of
    // displacement throws ~-67 dBFS into the neighbouring pilot bin against
    // Hann's ~-103, and reading a weak tone 8 bins from a strong one is exactly
    // what the cross-channel matrix and listen mode do. Hum is not bin-centred
    // either (60 Hz falls at bin 5.12), so it needs a window that confines its
    // skirts regardless. Pilots sit 8 bins apart and the Hann main lobe is
    // +/-2 bins, so neighbouring slots never overlap.
    // Normalised so a full-scale sine reads 1.0 at its peak bin.
    std::vector<std::vector<double> > magw(NCH, std::vector<double>(NB, 0.0));

    std::vector<double> win(FFT_N);
    for (int i = 0; i < FFT_N; ++i)
        win[i] = 0.5 * (1.0 - std::cos(2.0 * M_PI * (double)i / (double)FFT_N));
    const double CG = 0.5;   // Hann coherent gain

    for (int n = 0; n < NCH; ++n) {
        std::vector<double> accw(NB, 0.0);
        int blocks = (int)rec[n].size() / FFT_N;
        if (blocks < 1) { std::fprintf(stderr, "not enough captured audio\n"); return 1; }
        for (int b = 0; b < blocks; ++b) {
            std::vector<std::complex<double> > xw(FFT_N);
            for (int i = 0; i < FFT_N; ++i)
                xw[i] = std::complex<double>(rec[n][(size_t)b * FFT_N + i] * win[i], 0.0);
            fft_inplace(xw);
            for (int k = 0; k < NB; ++k) {
                const double mw = 2.0 * std::abs(xw[k]) / ((double)FFT_N * CG);
                accw[k] += mw * mw;
            }
        }
        for (int k = 0; k < NB; ++k)
            magw[n][k] = std::sqrt(accw[k] / (double)blocks);
    }

    // ---- report
    int failures = 0;
    std::vector<int> heard(NCH, 0);
    std::vector<int> det_bin(NCH, 0);   // bin the metrics below are taken at

    // Listen mode answers a different question from the loopback test: not
    // "did each input hear its own pilot" but "what is each input hearing".
    // A bridged pair - a cord joining a trunk to a station - puts two pilots
    // on both channels, which the pass/fail table cannot express because it
    // only ever reports the single strongest peak.
    if (o.listen) {
        // Real pilots and the crosstalk floor are separated by 50 dB or more,
        // so the gate is not critical; -70 sits in the gap. -t overrides.
        // Levels come from the Hann spectrum: a foreign pilot 8 bins from a
        // strong local one is precisely where rectangular leakage would
        // manufacture a tone that is not there.
        const double lt = o.tset ? o.min_dbfs : -70.0;
        std::printf("\nTones heard per input  (tone amplitude %.1f dBFS, threshold %.1f dBFS)\n\n",
                    o.amp_dbfs, lt);
        std::printf("  in ch | hearing    | level of each tone heard, dBFS\n");
        std::printf("  ------+------------+------------------------------------------------\n");

        for (int n = 0; n < NCH; ++n) {
            std::string list, lev;
            int    strongest = 0;
            double sv        = 0.0;
            for (int s = 1; s <= NCH; ++s) {
                const double m  = magw[n][pilot_bin(s)];
                const double db = 20.0 * std::log10(m > 1e-12 ? m : 1e-12);
                if (db < lt) continue;
                char b[64];
                std::snprintf(b, sizeof b, "%s%d", list.empty() ? "" : ",", s);
                list += b;
                std::snprintf(b, sizeof b, "%s%d:%.1f", lev.empty() ? "" : "   ", s, db);
                lev  += b;
                if (m > sv) { sv = m; strongest = s; }
            }
            if (list.empty()) { list = "none"; lev = "-"; }
            heard[n]   = strongest;
            det_bin[n] = strongest ? pilot_bin(strongest) : 0;
            std::printf("   %2d   | %-10s | %s\n", n + 1, list.c_str(), lev.c_str());
        }
        std::printf("\n  A channel bridged to another by a cord pair should list both\n"
                    "  slots. Levels are read at the pilot bins directly, so every\n"
                    "  tone present is listed, not just the strongest.\n");
    } else {

    std::printf("\nPer-channel result  (tone amplitude %.1f dBFS, threshold %.1f dBFS)\n\n",
                o.amp_dbfs, o.min_dbfs);
    std::printf("  in ch |  peak bin      peak Hz   level dBFS |  heard slot |  result\n");
    std::printf("  ------+----------------------------------------+-------------+---------\n");

    const int klo = pilot_search_lo(), khi = pilot_search_hi();

    for (int n = 0; n < NCH; ++n) {
        // Search only around the pilot comb - see pilot_search_lo(). A channel
        // with hum near the threshold would otherwise peak on a mains bin.
        int    kmax = klo;
        double vmax = 0.0;
        for (int k = klo; k <= khi; ++k)
            if (magw[n][k] > vmax) { vmax = magw[n][k]; kmax = k; }
        const double peak_db = 20.0 * std::log10(vmax > 1e-12 ? vmax : 1e-12);

        // A slot is only "heard" if the peak is strong enough to be a tone at
        // all. Without this gate an open input reports whatever leakage happens
        // to be largest, tens of dB below any real pilot.
        const bool present = (peak_db >= o.min_dbfs);
        int slot = 0;
        if (present)
            for (int s = 1; s <= NCH; ++s)
                if (std::abs(kmax - pilot_bin(s)) <= 2) { slot = s; break; }
        heard[n]   = slot;
        det_bin[n] = present ? kmax : 0;   // metrics follow the tone actually present

        const double want_db = 20.0 * std::log10(
            magw[n][pilot_bin(n + 1)] > 1e-12 ? magw[n][pilot_bin(n + 1)] : 1e-12);

        const bool ok = (slot == n + 1) && (want_db >= o.min_dbfs);
        if (!ok) ++failures;

        char slotstr[16];
        if (slot)          std::snprintf(slotstr, sizeof slotstr, "%d", slot);
        else if (!present) std::snprintf(slotstr, sizeof slotstr, "none");
        else               std::snprintf(slotstr, sizeof slotstr, "--");

        std::printf("   %2d   |   %4d   %10.2f   %10.2f |     %-4s    |  %s\n",
                    n + 1, kmax, kmax * BIN_HZ, peak_db, slotstr, ok ? "PASS" : "FAIL");
    }

    }

    std::printf("\nCross-channel level matrix, dBFS  (rows = input channel, cols = pilot slot)\n\n");
    std::printf("        ");
    for (int s = 1; s <= NCH; ++s) std::printf("   slot%d", s);
    std::printf("\n");
    for (int n = 0; n < NCH; ++n) {
        std::printf("  in %2d ", n + 1);
        for (int s = 1; s <= NCH; ++s) {
            double m = magw[n][pilot_bin(s)];
            double db = 20.0 * std::log10(m > 1e-12 ? m : 1e-12);
            std::printf(" %7.1f", db);
        }
        std::printf("\n");
    }

    // ---- gain-setting metrics: THD, hum and broadband noise, separated.
    // All three are taken from the Hann spectrum. Power in a band is summed and
    // divided by the Hann ENBW (1.5 bins), which is the correct correction for
    // both a spread tone and for broadband noise.
    const int HALF_BAND = 2;   // Hann main lobe is +/-2 bins

    std::printf("\nGain-setting metrics  (mains %.0f Hz; levels referenced to a full-scale sine)\n\n",
                o.mains_hz);
    std::printf("  in ch | slot |  pilot dBFS |  THD dBc  |  hum dBFS |  noise dBFS\n");
    std::printf("  ------+------+-------------+-----------+-----------+------------\n");

    // mains harmonics up to 600 Hz
    std::vector<int> humbins;
    for (int h = 1; h * o.mains_hz <= 600.0; ++h) {
        int k = (int)lrint(h * o.mains_hz / BIN_HZ);
        if (k > 0 && k < NB) humbins.push_back(k);
    }

    int nharm_used = 0;
    for (int h = 2; ; ++h) {
        if (h * pilot_bin(NCH) >= NB) break;
        nharm_used = h - 1;
    }

    // Bin masks. Neither depends on the channel, so build them once.
    //
    // The hum figure has to come off a mask rather than a per-harmonic sum:
    // at 50 Hz the mains harmonics land 4.27 bins apart, so their +/-2 windows
    // overlap and eight bins would be added twice, inflating the result. At
    // 60 Hz the spacing is 5.12 bins and the windows happen not to touch,
    // which is why the bug never showed on a 60 Hz supply.
    std::vector<bool> humask(NB, false);
    for (size_t i = 0; i < humbins.size(); ++i)
        for (int k = humbins[i] - HALF_BAND; k <= humbins[i] + HALF_BAND; ++k)
            if (k > 0 && k < NB) humask[k] = true;

    // Bins excluded from the broadband figure: DC, the hum lines, and every
    // pilot with its harmonics.
    std::vector<bool> skip(NB, false);
    for (int k = 0; k <= 2 && k < NB; ++k) skip[k] = true;
    for (int k = 1; k < NB; ++k) if (humask[k]) skip[k] = true;
    for (int s2 = 1; s2 <= NCH; ++s2) {
        for (int h = 1; h * pilot_bin(s2) < NB; ++h) {
            int c = h * pilot_bin(s2);
            for (int k = c - HALF_BAND; k <= c + HALF_BAND; ++k)
                if (k >= 0 && k < NB) skip[k] = true;
        }
    }

    for (int n = 0; n < NCH; ++n) {
        const std::vector<double>& m = magw[n];

        // fundamental, at the bin where a tone was actually found
        const int fb = det_bin[n] > 0 ? det_bin[n] : pilot_bin(n + 1);
        double pf = 0.0;
        for (int k = fb - HALF_BAND; k <= fb + HALF_BAND; ++k)
            if (k > 0 && k < NB) pf += m[k] * m[k];
        pf /= HANN_ENBW;

        // harmonics of that tone, below Nyquist
        double ph = 0.0;
        for (int h = 2; h * fb < NB; ++h) {
            int c = h * fb;
            for (int k = c - HALF_BAND; k <= c + HALF_BAND; ++k)
                if (k > 0 && k < NB) ph += m[k] * m[k];
        }
        ph /= HANN_ENBW;

        // hum, each masked bin counted exactly once
        double phum = 0.0;
        for (int k = 1; k < NB; ++k) if (humask[k]) phum += m[k] * m[k];
        phum /= HANN_ENBW;

        // Broadband remainder. The shared mask covers the pilot comb; the tone
        // actually found is normally one of those bins but need not be, so add
        // it and its harmonics here rather than leaving them in the noise.
        std::vector<bool> skipn = skip;
        for (int h = 1; h * fb < NB; ++h)
            for (int k = h * fb - HALF_BAND; k <= h * fb + HALF_BAND; ++k)
                if (k > 0 && k < NB) skipn[k] = true;
        double pn = 0.0;
        for (int k = 1; k < NB; ++k) if (!skipn[k]) pn += m[k] * m[k];
        pn /= HANN_ENBW;

        const double fund_db = 10.0 * std::log10(pf   > 1e-30 ? pf   : 1e-30);
        const double thd_db  = 10.0 * std::log10((ph > 1e-30 ? ph : 1e-30) /
                                                 (pf > 1e-30 ? pf : 1e-30));
        const double hum_db  = 10.0 * std::log10(phum > 1e-30 ? phum : 1e-30);
        const double noi_db  = 10.0 * std::log10(pn   > 1e-30 ? pn   : 1e-30);

        char sl[8];
        if (heard[n] == n + 1)   std::snprintf(sl, sizeof sl, "%d ",  heard[n]);
        else if (heard[n] != 0)  std::snprintf(sl, sizeof sl, "%d*", heard[n]);
        else                     std::snprintf(sl, sizeof sl, "--");

        if (det_bin[n] == 0) {
            // no tone found: the level shown is whatever sits at the expected
            // bin, and a harmonic ratio taken on noise means nothing.
            std::printf("   %2d   |  %-3s |   %8.2f  |     --    |  %7.1f  |  %8.1f\n",
                        n + 1, sl, fund_db, hum_db, noi_db);
        } else {
            std::printf("   %2d   |  %-3s |   %8.2f  |  %7.1f  |  %7.1f  |  %8.1f\n",
                        n + 1, sl, fund_db, thd_db, hum_db, noi_db);
        }
    }

    std::printf("\n  Metrics are taken at the bin where a tone was found, so they stay\n"
                "  valid under a mis-wire; * marks a channel carrying another slot's\n"
                "  tone, -- a channel where no pilot was found (its row is noise only).\n");
    std::printf("\n  THD uses %d harmonic(s); at 48 kHz only H2 and H3 of a 6 kHz\n"
                "  pilot fall below Nyquist, so this is a relative indicator for\n"
                "  setting a trim, not a full THD figure.\n", nharm_used);

    std::printf("\nxruns: %d\n", xruns);
    if (o.listen) return 0;
    if (failures == 0) {
        std::printf("RESULT: PASS  - all 8 channels heard their own pilot.\n");
        return 0;
    }
    std::printf("RESULT: FAIL  - %d channel(s) wrong.\n", failures);
    for (int n = 0; n < NCH; ++n) {
        if (heard[n] == n + 1) continue;
        if (heard[n] == 0)
            std::printf("  input %d: no pilot above %.1f dBFS (open, dead or muted)\n",
                        n + 1, o.min_dbfs);
        else
            std::printf("  input %d heard slot %d\n", n + 1, heard[n]);
    }
    return 2;
}
