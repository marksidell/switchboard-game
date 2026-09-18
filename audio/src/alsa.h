// alsa.h - the duplex stream. audio.md 4: one card, both directions, 48kHz,
// S32_LE, playback 34 channels and capture as reported, the two handles linked
// so they share one start and one xrun.
#pragma once

#include <alsa/asoundlib.h>

#include <cmath>
#include <cstdint>

#include "options.h"

class AlsaStream {
public:
    ~AlsaStream() { close(); }

    bool open(const Options& o);
    void close();

    bool start();                 // prepare, prefill silence, start the pair
    bool recover(int err);        // after an xrun: log, re-prepare, restart

    snd_pcm_sframes_t read(int32_t* buf)  { return snd_pcm_readi(cap_, buf, period_); }
    snd_pcm_sframes_t write(const int32_t* buf) { return snd_pcm_writei(play_, buf, period_); }

    unsigned nplay()  const { return nplay_; }
    unsigned ncap()   const { return ncap_; }
    unsigned period() const { return (unsigned)period_; }
    unsigned buffer() const { return (unsigned)buffer_; }

private:
    snd_pcm_t*        play_   = nullptr;
    snd_pcm_t*        cap_    = nullptr;
    unsigned          nplay_  = 0;
    unsigned          ncap_   = 0;
    snd_pcm_uframes_t period_ = 0;
    snd_pcm_uframes_t buffer_ = 0;
    unsigned          prefill_ = 0;
};

// Conversion at the period boundary, audio.md 4: integers to float once on
// capture, float to integers once on playback, and everything between them in
// float.
//
// Full scale is encoded as 2^31 - 256 on the way out so the value survives the
// device truncating to 24 bits, and read back against 2^31, which is what full
// scale means coming in. The 1e-6 dB between the two constants is deliberate;
// pilot_loopback_test.cpp has the same pair for the same reason.
static inline int32_t float_to_s32(float v)
{
    if (v >  1.0f) v =  1.0f;
    if (v < -1.0f) v = -1.0f;
    return (int32_t)std::llrintf(v * 2147483392.0f);
}

static inline float s32_to_float(int32_t s) { return (float)s * (1.0f / 2147483648.0f); }
