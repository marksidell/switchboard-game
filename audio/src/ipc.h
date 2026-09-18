// ipc.h - what crosses between the three threads (audio.md 3).
//
// Two queues. Command: MQTT thread -> audio thread, small fixed-size structs.
// Result: audio thread and analysis thread -> MQTT thread, one topic key and
// one value. Nothing else is shared except a handful of atomics and the hop
// snapshot, all of which live in Shared below.
#pragma once

#include <atomic>
#include <cstdint>
#include <vector>

#include "channels.h"
#include "options.h"
#include "spsc.h"

// A loaded file. The MQTT thread allocates it, the audio thread plays it, and
// when the audio thread stops playing it - end of file, stop, or replacement -
// it hands the pointer back on the result queue for the MQTT thread to free.
// No reference counting, no atomics beyond the queues (audio.md 3).
struct AudioBuffer {
    std::vector<float> samples;
    char               name[32] = { 0 };
};

enum class ToneKind : uint8_t { Off = 0, Dial, Ringback, Busy };

enum class Verb : uint8_t {
    Play,        // slot, buf (nullptr = stop)
    Tone,        // slot, arg = ToneKind
    Listen,      // slot, arg = timeout in seconds, 0 = cancel
    Monitor,     // arg = gain dB, on = false for mute
    Test,        // ch 1-34, on
    StopGame,    // stop every file and tone, cancel every listen (audio.md 13.2)
    Quit
};

struct Command {
    Verb         verb = Verb::Quit;
    int16_t      idx  = 0;          // circuit slot 1-32, or playback channel 1-34
    bool         on   = false;
    float        arg  = 0.0f;
    AudioBuffer* buf  = nullptr;
    char         name[32] = { 0 };  // filename, for the echo on `play`
};

// Which retained topic a result sets. The MQTT thread owns the topic strings;
// the other two threads only ever name the leaf and the value.
enum class Topic : uint8_t {
    Play,       // idx = slot
    Tone,       // idx = slot
    Listen,     // idx = slot
    Monitor,
    Test,       // idx = playback channel 1-34
    Peer,       // idx = slot
    Op,         // idx = slot
    OpTone,
    FreeBuf     // not a topic: a buffer the audio thread has finished with
};

struct Result {
    Topic        topic = Topic::FreeBuf;
    int16_t      idx   = 0;
    char         value[40] = { 0 };
    AudioBuffer* buf   = nullptr;
};

// One hop's worth of capture, handed to the analysis thread. Two of them, so
// the audio thread can fill one while the other is being transformed.
struct Snapshot {
    std::vector<float> data;        // N_CAP_CH * FFT_N, channel-major
    uint64_t           hop = 0;
};

struct Shared {
    Options opt;

    Spsc<Command, 256> cmdq;        // MQTT   -> audio
    Spsc<Result,  512> res_audio;   // audio  -> MQTT
    Spsc<Result,  512> res_ana;     // analysis -> MQTT

    Snapshot          snap[2];
    std::atomic<bool> snap_busy[2] { { false }, { false } };
    std::atomic<int>  snap_ready { -1 };

    std::atomic<bool> running        { true };   // thread lifetime
    std::atomic<bool> quit           { false };  // SIGTERM/SIGINT, or a lost stream
    std::atomic<bool> force_publish  { false };   // republish detector state
    std::atomic<bool> audio_failed   { false };   // stream lost unrecoverably

    std::atomic<unsigned> xruns        { 0 };
    std::atomic<unsigned> hops_lost    { 0 };
    std::atomic<unsigned> clips        { 0 };
    std::atomic<unsigned> limiter_hits { 0 };
    std::atomic<unsigned> res_dropped  { 0 };

    int ncap  = chan::N_CAP_CH;
    int nplay = chan::N_PLAY_CH;
};
