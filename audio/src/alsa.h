// alsa.h - the duplex stream. audio.md 4: one card, both directions, 48kHz,
// S32_LE, playback 34 channels and capture as reported, the two handles linked
// so they share one start and one xrun.
//
// ALSA vocabulary used here and in engine.cpp:
//   frame     one sample for every channel at one instant: 34 samples on
//             playback, 32 on capture.
//   period    the block of frames moved per read or write - 256 frames, 5.3 ms.
//             The audio thread's whole life is "read one period, write one
//             period".
//   buffer    the driver's ring of periods (3 of them). Playback latency is
//             roughly the buffer length.
//   interleaved  frames stored one after another, channels within a frame:
//             ch1 ch2 ... ch34 ch1 ch2 ... - the layout read() and write()
//             use. The engine converts to one-row-per-channel for processing.
//   xrun      the driver ran out of playback data or capture space because
//             the program was late. Recovered, counted and logged.
#pragma once

#include <alsa/asoundlib.h>

#include <cmath>
#include <cstdint>

#include "options.h"

// AlsaStream - the two PCM handles, playback and capture, on one card, and
// what the driver agreed to when they were configured. Opened in main(), then
// used only by the audio thread.
class AlsaStream {
public:
    // ~AlsaStream()                                                  [startup]
    //   Closes both handles if still open (RAII).
    ~AlsaStream() { close(); }

    // open()                                                         [startup]
    //   Opens and configures both directions on o.device(), links them, and
    //   logs what was negotiated. Returns false, having logged why, if the
    //   card is missing or refuses 48 kHz S32_LE.
    bool open(const Options& o);

    // close()                                                        [startup]
    //   Closes both handles. Safe to call twice.
    void close();

    // start()                                                          [audio]
    //   Prepares both directions, prefills playback with silence so the DACs
    //   never see a gap, and starts the pair running. Also the second half of
    //   recover().
    bool start();

    // recover()                                                        [audio]
    //   After an xrun or other stream error: logs it, stops both directions
    //   and start()s them again. Returns false if that fails, which is fatal.
    bool recover(int err);

    // read()                                                           [audio]
    //   Blocks until one period of capture is available, then copies it into
    //   buf as interleaved 32-bit integers. Returns the number of frames read,
    //   or a negative ALSA error (an xrun is -EPIPE).
    snd_pcm_sframes_t read(int32_t* buf)  { return snd_pcm_readi(cap_, buf, period_); }

    // write()                                                          [audio]
    //   Queues one period of interleaved playback; blocks if the buffer is
    //   full. Same return convention as read().
    snd_pcm_sframes_t write(const int32_t* buf) { return snd_pcm_writei(play_, buf, period_); }

    // What the driver agreed to - the program sizes every buffer from these.
    unsigned nplay()  const { return nplay_; }     // playback channels (34)
    unsigned ncap()   const { return ncap_; }      // capture channels (32)
    unsigned period() const { return (unsigned)period_; }   // frames per period
    unsigned buffer() const { return (unsigned)buffer_; }   // frames in buffer

private:
    snd_pcm_t*        play_   = nullptr;   // playback handle
    snd_pcm_t*        cap_    = nullptr;   // capture handle
    unsigned          nplay_  = 0;
    unsigned          ncap_   = 0;
    snd_pcm_uframes_t period_ = 0;
    snd_pcm_uframes_t buffer_ = 0;
    unsigned          prefill_ = 0;        // periods of silence written by start()
};

// Conversion at the period boundary, audio.md 4: integers to float once on
// capture, float to integers once on playback, and everything between them in
// float.
//
// Full scale is encoded as 2^31 - 256 on the way out so the value survives the
// device truncating to 24 bits, and read back against 2^31, which is what full
// scale means coming in. The 1e-6 dB between the two constants is deliberate;
// pilot_loopback_test.cpp has the same pair for the same reason.
//
// float_to_s32()                                                       [audio]
//   One float sample, nominally -1.0..+1.0, to the driver's 32-bit integer.
//   Clamps anything outside that range rather than letting it wrap.
static inline int32_t float_to_s32(float v)
{
    if (v >  1.0f) v =  1.0f;
    if (v < -1.0f) v = -1.0f;
    return (int32_t)std::llrintf(v * 2147483392.0f);
}

// s32_to_float()                                                       [audio]
//   One captured 32-bit integer to a float in -1.0..+1.0.
static inline float s32_to_float(int32_t s) { return (float)s * (1.0f / 2147483648.0f); }
