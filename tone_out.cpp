// tone_out.cpp
//
// Continuous sine on one output channel of an ALSA device. A bench probe for
// tracing a signal by hand - through a cord pair, a transformer, a circuit
// board - while metering or listening somewhere downstream.
//
// Channel numbers are 1-based, as in docs/audio.md: channel n is ALSA frame
// index n-1.
//
// Phase is carried in a double accumulator rather than a precomputed loop
// buffer, so any frequency plays seamlessly - no click at the wrap and no
// requirement that the tone complete a whole number of cycles per period.
//
// Build:  g++ -O2 -Wall -Wextra -o tone_out tone_out.cpp -lasound
//
// Examples (hw:1 stands for the card number or id in /proc/asound/cards):
//     ./tone_out -D hw:1 -c 7                 1 kHz on channel 7, until ^C
//     ./tone_out -D hw:1 -c 8 -f 400 -a -20   400 Hz at -20 dBFS
//     ./tone_out -D hw:1 -c 7 -d 30           stop after 30 seconds
//
#include "bench_alsa.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <csignal>
#include <string>
#include <unistd.h>
#include <vector>

// ---------------------------------------------------------------- options

struct Opts {
    std::string         dev   = "hw:0";
    std::vector<int>    chan1;     // 1-based output channels
    std::vector<double> hz;        // one per channel, or one for all
    std::vector<double> amp_dbfs;  // ditto
    double              dur_s    = 0.0;    // 0 = run until interrupted
    unsigned            rate     = 48000;
    int                 force_ch = 0;      // 0 = query the device
    double              sw_lo    = 0.0;    // 0 = no sweep, hold -f instead
    double              sw_hi    = 0.0;
    double              sw_secs  = 2.0;    // seconds for one pass
    double              cyc_secs = 0.0;    // 0 = all channels together
};

// Split "6562.5,6656.25" into its parts. Returns false on anything
// that is not a comma-separated list of numbers.
static bool split_list(const char* arg, std::vector<double>& out)
{
    out.clear();
    const char* p = arg;
    while (*p) {
        char* end = 0;
        double v = std::strtod(p, &end);
        if (end == p) return false;
        out.push_back(v);
        p = end;
        if (*p == ',') ++p;
        else if (*p)   return false;
    }
    return !out.empty();
}

static void usage(const char* p) {
    std::fprintf(stderr,
"Usage: %s [options]\n"
"  -D <dev>     ALSA playback device (default hw:0)\n"
"  -c <list>    output channels, 1-based, comma separated (default 1).\n"
"               Repeat a channel to put more than one tone on it, e.g.\n"
"               -c 8,8 -f 6000,6093.75\n"
"  -f <list>    frequencies in Hz, one per channel or one for all (default 1000)\n"
"  -a <list>    amplitudes in dBFS, one per channel or one for all (default -12)\n"
"  -s <lo>,<hi> sweep between these frequencies instead of holding one,\n"
"               repeating; overrides -f on every channel\n"
"  -w <sec>     seconds for one sweep pass, default 2\n"
"  -y <sec>     cycle: play each listed channel alone for this long, in turn,\n"
"               repeating. Prints a timestamped line at each change.\n"
"  -d <sec>     stop after this long, default 0 = until ^C\n"
"  -r <Hz>      sample rate, default 48000\n"
"  -X <n>       force the device channel count\n"
"  -h           this help\n"
"\n"
"All other channels are driven with digital silence.\n"
"\n"
"  %s -D hw:1 -c 8 -f 1000                one tone on channel 8\n"
"  %s -D hw:1 -c 7,8 -f 6562.5,6656.25    both channels driven at once\n"
"  %s -D hw:1 -c 7,8 -f 1000 -a -20       same tone and level on both\n", p, p, p, p);
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
        else if (a == "-c" && nx) {
            if (!split_ints(nx, o.chan1)) { std::fprintf(stderr, "bad channel list: %s\n", nx); return 1; }
            ++i;
        }
        else if (a == "-f" && nx) {
            if (!split_list(nx, o.hz)) { std::fprintf(stderr, "bad frequency list: %s\n", nx); return 1; }
            ++i;
        }
        else if (a == "-a" && nx) {
            if (!split_list(nx, o.amp_dbfs)) { std::fprintf(stderr, "bad amplitude list: %s\n", nx); return 1; }
            ++i;
        }
        else if (a == "-s" && nx) {
            std::vector<double> v;
            if (!split_list(nx, v) || v.size() != 2) {
                std::fprintf(stderr, "sweep wants two frequencies, e.g. -s 300,3000\n");
                return 1;
            }
            o.sw_lo = v[0]; o.sw_hi = v[1];
            ++i;
        }
        else if (a == "-w" && nx) { o.sw_secs  = atof(nx); ++i; }
        else if (a == "-y" && nx) { o.cyc_secs = atof(nx); ++i; }
        else if (a == "-d" && nx) { o.dur_s    = atof(nx); ++i; }
        else if (a == "-r" && nx) { o.rate     = (unsigned)atoi(nx); ++i; }
        else if (a == "-X" && nx) { o.force_ch = atoi(nx); ++i; }
        else if (a == "-h")       { usage(argv[0]); return 0; }
        else { usage(argv[0]); return 1; }
    }
    if (o.chan1.empty())    o.chan1.push_back(1);
    if (o.hz.empty())       o.hz.push_back(1000.0);
    if (o.amp_dbfs.empty()) o.amp_dbfs.push_back(-12.0);

    // One frequency or amplitude stands for all channels; otherwise the lists
    // have to line up, or it is impossible to tell which value meant which pin.
    const size_t NC = o.chan1.size();
    if (o.hz.size() == 1)       o.hz.assign(NC, o.hz[0]);
    if (o.amp_dbfs.size() == 1) o.amp_dbfs.assign(NC, o.amp_dbfs[0]);
    if (o.hz.size() != NC || o.amp_dbfs.size() != NC) {
        std::fprintf(stderr,
                     "gave %zu channel(s) but %zu frequency and %zu amplitude value(s);\n"
                     "pass one of each, or one per channel\n",
                     NC, o.hz.size(), o.amp_dbfs.size());
        return 1;
    }
    if (o.cyc_secs < 0.0 || (o.cyc_secs > 0.0 && o.cyc_secs < 0.05)) {
        std::fprintf(stderr, "cycle dwell must be at least 0.05 s\n"); return 1;
    }
    const bool sweeping = (o.sw_lo > 0.0 || o.sw_hi > 0.0);
    if (sweeping) {
        if (o.sw_lo <= 0.0 || o.sw_hi <= o.sw_lo) {
            std::fprintf(stderr, "sweep needs 0 < lo < hi\n"); return 1;
        }
        if (o.sw_hi >= o.rate / 2.0) {
            std::fprintf(stderr, "%.1f Hz is at or above Nyquist for %u Hz\n", o.sw_hi, o.rate);
            return 1;
        }
        if (o.sw_secs < 0.1) { std::fprintf(stderr, "sweep pass must be at least 0.1 s\n"); return 1; }
    }

    for (size_t i = 0; i < NC; ++i) {
        if (!channel_ok("output", o.chan1[i], 0)) return 1;
        if (!sweeping) {
            if (o.hz[i] <= 0.0) { std::fprintf(stderr, "frequency must be positive\n"); return 1; }
            if (o.hz[i] >= o.rate / 2.0) {
                std::fprintf(stderr, "%.1f Hz is at or above Nyquist for %u Hz\n",
                             o.hz[i], o.rate);
                return 1;
            }
        }
        if (o.amp_dbfs[i] > 0.0) {
            std::fprintf(stderr, "amplitude above 0 dBFS would clip\n");
            return 1;
        }
    }

    const unsigned need = (unsigned)*std::max_element(o.chan1.begin(), o.chan1.end());
    Stream st;
    if (configure(st, o.dev.c_str(), SND_PCM_STREAM_PLAYBACK, o.rate,
                  o.force_ch, need, 1024, true) < 0) return 1;

    std::vector<int>    idx0(NC);          // frame index, channel - 1
    std::vector<double> amp (NC);
    std::vector<double> step(NC);          // cycles advanced per sample
    for (size_t i = 0; i < NC; ++i) {
        if (!channel_ok("output", o.chan1[i], st.chan)) return 1;
        idx0[i] = o.chan1[i] - 1;
        amp [i] = std::pow(10.0, o.amp_dbfs[i] / 20.0);
        step[i] = o.hz[i] / (double)o.rate;
    }
    const size_t psamp = fmt_bytes(st.fmt);

    std::printf("device   %s  %u ch  %s  %u Hz  period %lu  buffer %lu\n",
                o.dev.c_str(), st.chan, snd_pcm_format_name(st.fmt), o.rate,
                (unsigned long)st.period, (unsigned long)st.buffer);
    for (size_t i = 0; i < NC; ++i) {
        if (sweeping)
            std::printf("sweep    %.1f - %.1f Hz over %.2f s, repeating, at %6.1f dBFS"
                        " on channel %d\n",
                        o.sw_lo, o.sw_hi, o.sw_secs, o.amp_dbfs[i], o.chan1[i]);
        else
            std::printf("tone     %9.2f Hz at %6.1f dBFS on channel %d\n",
                        o.hz[i], o.amp_dbfs[i], o.chan1[i]);
    }
    if (o.dur_s > 0.0) std::printf("running  %.1f s\n", o.dur_s);
    else               std::printf("running  until interrupted (^C)\n");
    std::fflush(stdout);

    std::signal(SIGINT,  on_signal);
    std::signal(SIGTERM, on_signal);

    const bool tty = isatty(STDOUT_FILENO) != 0;

    // Sweep state. Position is carried in samples and wrapped, and the tone's
    // phase keeps accumulating across the wrap, so the jump back from hi to lo
    // is a step in frequency but not in phase - it glides rather than clicking.
    // The sweep is logarithmic: equal octaves take equal time, which is how it
    // needs to sound if you are listening for a hole in the response.
    const long   swN   = (long)(o.sw_secs * (double)o.rate);
    const double swLog = sweeping ? std::log(o.sw_hi / o.sw_lo) : 0.0;
    long         swpos = 0;

    // Cycle state: one channel sounds at a time, in the order given to -c.
    // Phases keep running for the silent channels so a channel resumes mid-wave
    // rather than restarting, which stops the switch itself from clicking.
    const bool cycling = (o.cyc_secs > 0.0);
    const long cycN    = cycling ? (long)(o.cyc_secs * (double)o.rate) : 1;
    long       cycpos  = 0;
    int        cur     = -1;

    // Two tones on one channel have to be summed before quantising, so mix in
    // double and convert once per frame rather than writing each tone straight
    // into the frame and overwriting the last.
    std::vector<double> mix((size_t)st.period * st.chan, 0.0);
    {
        std::vector<double> peak(st.chan, 0.0);
        for (size_t c = 0; c < NC; ++c) peak[idx0[c]] += amp[c];
        for (unsigned k = 0; k < st.chan; ++k)
            if (peak[k] > 1.0)
                std::fprintf(stderr,
                    "warning: tones on channel %u sum to %.2f of full scale and will clip;\n"
                    "         drop -a by about %.1f dB\n",
                    k + 1, peak[k], 20.0 * std::log10(peak[k]));
    }

    std::vector<uint8_t> buf((size_t)st.period * st.fbytes, 0);
    std::vector<double>  phase(NC, 0.0);   // in cycles, wrapped to [0,1)
    long    written = 0;
    int     xruns   = 0;
    const long total = (o.dur_s > 0.0) ? (long)(o.dur_s * (double)o.rate) : 0;

    snd_pcm_prepare(st.pcm);

    while (!g_stop && (total == 0 || written < total)) {
        snd_pcm_uframes_t n = st.period;
        if (total != 0 && written + (long)n > total) n = (snd_pcm_uframes_t)(total - written);

        // Silence everything, then write the channels driven. Rewriting
        // the whole period each time keeps stale frames from being replayed.
        std::memset(buf.data(), 0, (size_t)n * st.fbytes);
        std::fill(mix.begin(), mix.begin() + (size_t)n * st.chan, 0.0);
        for (size_t c = 0; c < NC; ++c) {
            double ph = phase[c];
            for (snd_pcm_uframes_t f = 0; f < n; ++f) {
                double st_c = step[c];
                if (sweeping) {
                    const long  q = (swpos + (long)f) % swN;
                    const double u = (double)q / (double)swN;
                    st_c = o.sw_lo * std::exp(swLog * u) / (double)o.rate;
                }
                bool on = true;
                if (cycling) {
                    const long slot = ((cycpos + (long)f) / cycN) % (long)NC;
                    on = ((size_t)slot == c);
                }
                if (on)
                    mix[(size_t)f * st.chan + (size_t)idx0[c]] +=
                        amp[c] * std::sin(2.0 * M_PI * ph);
                ph += st_c;
                if (ph >= 1.0) ph -= 1.0;      // wrap in cycles, so no drift
            }
            phase[c] = ph;
        }
        for (snd_pcm_uframes_t f = 0; f < n; ++f)
            for (unsigned k = 0; k < st.chan; ++k) {
                const double v = mix[(size_t)f * st.chan + k];
                if (v != 0.0)
                    put_sample(&buf[f * st.fbytes + (size_t)k * psamp], st.fmt, v);
            }
        if (sweeping) swpos = (swpos + (long)n) % swN;
        if (cycling) {
            const int slot = (int)((cycpos / cycN) % (long)NC);
            if (slot != cur) {
                cur = slot;
                std::printf("  %7.1f s   channel %d   %.2f Hz\n",
                            (double)written / (double)o.rate, o.chan1[cur], o.hz[cur]);
                std::fflush(stdout);
            }
            cycpos = (cycpos + (long)n) % (cycN * (long)NC);
        }

        snd_pcm_sframes_t w = snd_pcm_writei(st.pcm, buf.data(), n);
        if (w < 0) {
            ++xruns;
            if (snd_pcm_recover(st.pcm, (int)w, 1) < 0) {
                std::fprintf(stderr, "\nplayback: %s\n", snd_strerror((int)w));
                return 1;
            }
            continue;
        }
        written += w;

        // Tick once a second, in place. Redirected to a file the carriage
        // returns would just pile up, so only do it on a terminal.
        if (tty && written % (long)o.rate < (long)st.period) {
            std::printf("\r  %ld s   xruns %d ", written / (long)o.rate, xruns);
            std::fflush(stdout);
        }
    }

    std::printf("%s  stopped after %.1f s, %d xrun(s)%s\n", tty ? "\r" : "",
                (double)written / (double)o.rate, xruns,
                g_stop ? " (interrupted)" : "");

    if (!g_stop) snd_pcm_drain(st.pcm); else snd_pcm_drop(st.pcm);
    return 0;
}
