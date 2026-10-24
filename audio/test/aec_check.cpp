// aec_check - the echo canceller (audio.md 9.4) run over a --record-line
// recording, for the bench. Not a ctest: it reads a recording.
//
//   aec_check FILE.lineN.wav [PAIR]
//
// PAIR is which slot of the file, 0 for the first. The canceller runs from the
// first sample to the last, with the detector's band-pass on both sides as the
// engine has it. Prints one line per 10 ms frame:
//
//   seconds  full  valid  residual_dB  echo_dB  capture_dB
#include <sndfile.h>

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#include "../src/aec.h"
#include "../src/dsp.h"

int main(int argc, char** argv)
{
    if (argc < 2) { std::fprintf(stderr, "usage: aec_check FILE.lineN.wav [PAIR]\n"); return 2; }
    const int pair = argc > 2 ? std::atoi(argv[2]) : 0;
    SF_INFO info;
    std::memset(&info, 0, sizeof info);
    SNDFILE* f = sf_open(argv[1], SFM_READ, &info);
    if (!f) { std::fprintf(stderr, "%s: %s\n", argv[1], sf_strerror(nullptr)); return 1; }
    if (info.samplerate != 48000 || info.channels < 2 * (pair + 1)) {
        std::fprintf(stderr, "%s: not a --record-line file with pair %d\n", argv[1], pair); return 1; }

    const Biquad hp = butter_highpass(300.0, 48000.0);
    const std::vector<Biquad> lp = butter_lowpass6(3400.0, 48000.0);
    BiquadState rh, rl[3], ch, cl[3];
    EchoCanceller ec;
    ec.configure(80);
    ec.start(0);

    std::vector<float> buf((size_t)info.channels * 4800);
    uint64_t g = 0;
    double acc = 0.0;
    int nacc = 0;
    sf_count_t got;
    while ((got = sf_readf_float(f, buf.data(), 4800)) > 0) {
        for (sf_count_t i = 0; i < got; ++i, ++g) {
            const float* fr = &buf[(size_t)i * info.channels + 2 * pair];
            double r = rh.run(hp, fr[0]);
            double c = ch.run(hp, fr[1]);
            for (int k = 0; k < 3; ++k) { r = rl[k].run(lp[k], r); c = cl[k].run(lp[k], c); }
            acc += c * c;
            if (g % 6 == 0) {
                const uint32_t m = (uint32_t)(g / 6);
                ec.ref(m, (float)r);
                ec.step(m, (float)c);
            }
            if (++nacc < 480) continue;
            const EchoCanceller::Frame e = ec.end_frame((uint32_t)(g / 6));
            std::printf("%.2f %d %d %.1f %.1f %.1f\n", (double)(g + 1) / 48000.0, e.full, e.valid,
                        e.resid_db, e.echo_db, 10.0 * std::log10(2.0 * acc / 480.0 + 1e-20));
            acc = 0.0;
            nacc = 0;
        }
    }
    sf_close(f);
    return 0;
}
