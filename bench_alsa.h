// bench_alsa.h - ALSA plumbing shared by the bench tools.
//
// Header-only, so each tool still builds with one g++ line:
//     g++ -O2 -Wall -Wextra -o tone_out tone_out.cpp -lasound
//
// Channel numbers the user types and reads are 1-based, as in docs/audio.md:
// channel n is ALSA frame index n-1. The conversion happens at the point a
// sample is placed in or read from a frame, nowhere else.
#pragma once

#include <alsa/asoundlib.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

// ---------------------------------------------------------------- sample I/O

static inline size_t fmt_bytes(snd_pcm_format_t f) {
    int w = snd_pcm_format_physical_width(f);
    return (w > 0) ? (size_t)(w / 8) : 0;
}

static inline void put_sample(uint8_t* p, snd_pcm_format_t f, double v) {
    if (v >  1.0) v =  1.0;
    if (v < -1.0) v = -1.0;
    switch (f) {
    case SND_PCM_FORMAT_S32_LE: {
        // Encode 1.0 as 2^31 - 256 so the value survives the device truncating
        // to 24 bits. get_sample() divides by 2^31, because that is what full
        // scale means coming back in; the 1.0e-6 dB difference between the two
        // constants is deliberate.
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

static inline double get_sample(const uint8_t* p, snd_pcm_format_t f) {
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

// ---------------------------------------------------------------- channels

// Split "7,8" into its parts. False on anything that is not a comma-separated
// list of integers.
static inline bool split_ints(const char* arg, std::vector<int>& out) {
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

// A 1-based channel number, checked against the device's width once that is
// known; pass 0 for device_chans before the device is open.
static inline bool channel_ok(const char* what, int ch, unsigned device_chans) {
    if (ch < 1) {
        std::fprintf(stderr, "%s channel %d: channels are numbered from 1\n", what, ch);
        return false;
    }
    if (device_chans > 0 && (unsigned)ch > device_chans) {
        std::fprintf(stderr, "%s channel %d out of range: the device has channels 1-%u\n",
                     what, ch, device_chans);
        return false;
    }
    return true;
}

// ---------------------------------------------------------------- ALSA setup

struct Stream {
    snd_pcm_t*        pcm    = nullptr;
    snd_pcm_format_t  fmt    = SND_PCM_FORMAT_UNKNOWN;
    unsigned          chan   = 0;
    snd_pcm_uframes_t period = 0;
    snd_pcm_uframes_t buffer = 0;
    size_t            fbytes = 0;   // bytes per frame

    Stream() = default;
    ~Stream() { close(); }
    Stream(const Stream&) = delete;
    Stream& operator=(const Stream&) = delete;

    void close() {
        if (pcm) { snd_pcm_close(pcm); pcm = nullptr; }
    }
};

// configure() has already opened the device by the time most of its checks
// run, so every failure after that point hands the handle back.
static inline int cfg_fail(Stream& st, int err) {
    st.close();
    return err;
}

// Open dev in one direction, interleaved, at exactly `rate` (no resampling),
// in the widest of S32_LE / S24_3LE / S16_LE the device takes. Channel count:
// forced_chan if positive, else the device's only width if it has one (the
// usual RME case), else at least need_chan. The buffer is four periods.
//
// start_when_full: true lets ALSA start playback once the buffer is full;
// false sets the threshold out of reach so the caller starts the stream
// itself, which a duplex tool needs to start both directions together.
static inline int configure(Stream& st, const char* dev, snd_pcm_stream_t dir,
                            unsigned rate, int forced_chan, unsigned need_chan,
                            snd_pcm_uframes_t want_period, bool start_when_full)
{
    int err = snd_pcm_open(&st.pcm, dev, dir, 0);
    if (err < 0) {
        st.pcm = nullptr;
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

    if ((err = snd_pcm_hw_params_set_rate(st.pcm, hw, rate, 0)) < 0) {
        std::fprintf(stderr, "set rate %u: %s (is the clock locked to %u Hz?)\n",
                     rate, snd_strerror(err), rate);
        return cfg_fail(st, err);
    }

    unsigned cmin = 0, cmax = 0;
    snd_pcm_hw_params_get_channels_min(hw, &cmin);
    snd_pcm_hw_params_get_channels_max(hw, &cmax);
    unsigned want;
    if (forced_chan > 0)   want = (unsigned)forced_chan;
    else if (cmin == cmax) want = cmin;
    else                   want = std::max(cmin, need_chan);
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
    snd_pcm_sw_params_set_start_threshold(st.pcm, sw,
                                          start_when_full ? st.buffer : st.buffer * 2);
    snd_pcm_sw_params_set_avail_min(st.pcm, sw, st.period);
    if ((err = snd_pcm_sw_params(st.pcm, sw)) < 0) {
        std::fprintf(stderr, "sw_params: %s\n", snd_strerror(err));
        return cfg_fail(st, err);
    }
    return 0;
}
