// ipc.h - what crosses between the three threads (audio.md 3).
//
// Two queues. Command: MQTT thread -> audio thread, small fixed-size structs.
// Result: audio thread and analysis thread -> MQTT thread, one topic key and
// one value. Nothing else is shared except a handful of atomics and the hop
// snapshot, all of which live in Shared below.
//
// The whole program's data flow, in one picture:
//
//                       Command (cmdq)
//      +-------------+ -------------------> +--------------+
//      | MQTT thread |                      | audio thread |  <-> ALSA
//      |   net.cpp   | <------------------- |  engine.cpp  |
//      +-------------+   Result (res_audio) +--------------+
//             ^                                    |
//             |                                    | Snapshot (snap[0/1]),
//             | Result (res_ana)                   | every 2048 samples
//             |                             +--------------+
//             +---------------------------- |   analysis   |
//                                           | detector.cpp |
//                                           +--------------+
//
// A command arrives over MQTT; the MQTT thread turns it into a Command and
// pushes it to the audio thread; the audio thread acts on it at the start of
// its next period and pushes back a Result saying what the state now is; the
// MQTT thread publishes that. Meanwhile the audio thread hands a copy of the
// recent capture to the analysis thread every 2048 samples, and the analysis
// thread pushes a Result whenever a circuit's peer or op changes.
#pragma once

#include <atomic>
#include <cstdint>
#include <vector>

#include "channels.h"
#include "options.h"
#include "rec.h"
#include "spsc.h"

// AudioBuffer - a loaded file. The MQTT thread allocates it, the audio thread
// plays it, and when the audio thread stops playing it - end of file, stop, or
// replacement - it hands the pointer back on the result queue for the MQTT
// thread to free. No reference counting, no atomics beyond the queues
// (audio.md 3). At any moment exactly one thread owns a given buffer, and
// ownership moves only by passing the pointer through a queue.
struct AudioBuffer {
    std::vector<float> samples;         // mono, 48 kHz, -1.0..+1.0
    char               name[32] = { 0 };// base filename, for the log
};

// The three trunk tones, and Off. Carried as a float in Command::arg.
enum class ToneKind : uint8_t { Off = 0, Dial, Ringback, Busy, Reorder };

// What a Command asks the audio thread to do. The comment on each says which
// Command fields it uses.
enum class Verb : uint8_t {
    Play,        // slot, buf (nullptr = stop)
    Tone,        // slot, arg = ToneKind
    Listen,      // slot, arg = timeout in seconds, 0 = cancel
    Monitor,     // arg = gain dB, on = false for mute
    MonitorSrc,  // idx = capture channel of the new source (audio.md 10.3)
    MonitorPeer, // on = fixed at arg dB, off = measured (audio.md 10.8, Rev 29)
    Test,        // ch 1-34, on
    StopGame,    // stop every file and tone, cancel every listen (audio.md 13.2)
    Quit
};

// Command - one instruction, MQTT thread -> audio thread. Plain data, copied
// by value through the queue; the only pointer is buf, whose ownership passes
// with it.
struct Command {
    Verb         verb = Verb::Quit;
    int16_t      idx  = 0;          // circuit slot 1-32, playback channel 1-34,
                                    // or MonitorSrc's capture channel
    bool         on   = false;      // Monitor: on or muted. Test: on or off. MonitorPeer: fixed.
    float        arg  = 0.0f;       // Tone: ToneKind. Listen: seconds. Monitor, MonitorPeer: dB.
    AudioBuffer* buf  = nullptr;    // Play: the file, now owned by the audio thread
    char         name[32] = { 0 };  // filename, for the echo on `play`
};

// Which retained topic a result sets. The MQTT thread owns the topic strings;
// the other two threads only ever name the leaf and the value.
enum class Topic : uint8_t {
    Play,       // idx = slot
    Tone,       // idx = slot
    Listen,     // idx = slot
    Monitor,
    MonitorSrc,
    MonitorPeer,
    Test,       // idx = playback channel 1-34
    Peer,       // idx = slot
    Op,         // idx = slot
    OpTone,
    Ringing,    // idx = station slot (audio.md 9.5, Rev 30)
    FreeBuf     // not a topic: a buffer the audio thread has finished with
};

// Result - one piece of news for the MQTT thread: "topic <topic> for slot or
// channel <idx> is now <value>". Topic + idx become a topic string in
// net.cpp's topic_for(); value is published as is, and an empty value clears
// the retained topic. A FreeBuf result carries only buf.
struct Result {
    Topic        topic = Topic::FreeBuf;
    int16_t      idx   = 0;
    char         value[40] = { 0 };
    AudioBuffer* buf   = nullptr;
};

// Snapshot - one hop's worth of capture, handed to the analysis thread: the
// most recent 4096 samples of every capture channel, oldest first, one channel
// after another (channel c starts at data[c * 4096]). Two of them, so the
// audio thread can fill one while the other is being transformed.
struct Snapshot {
    std::vector<float> data;        // N_CAP_CH * FFT_N, channel-major
    uint64_t           hop = 0;     // hop number, 1 upward; for the --dump CSV
};

// Shared - everything the three threads hold in common. One instance, created
// in main() and passed by reference to each thread's object. Apart from `opt`
// (read-only after startup) and the snapshots (handed over by the protocol
// below), every member is either a lock-free queue or an atomic.
struct Shared {
    Options opt;                    // the command line; read-only once running

    // ---- the queues
    Spsc<Command, 256> cmdq;        // MQTT   -> audio
    Spsc<Result,  512> res_audio;   // audio  -> MQTT
    Spsc<Result,  512> res_ana;     // analysis -> MQTT

    // ---- the snapshot hand-off, audio -> analysis (audio.md 6.1)
    //
    // The audio thread fills snap[0], then snap[1], then snap[0] ... one per
    // hop. snap_ready is a one-slot mailbox holding the index of a filled
    // block, or -1. Each side owns one edge of the busy flag:
    //
    //   audio thread, each hop: if the block due to be filled is busy, skip
    //     the hop (count it in hops_lost) and try the same block next hop.
    //     Otherwise fill it, SET its busy flag, and exchange its index into
    //     the mailbox. If the exchange hands back an older index, that block
    //     was never collected: clear its busy flag and count it lost.
    //
    //   analysis thread: exchange the mailbox to -1. If it held an index,
    //     transform that block and CLEAR its busy flag when done.
    //
    // A block is busy from the moment it is posted until it is either
    // transformed or reclaimed, and only its owner of the moment touches it.
    Snapshot          snap[2];
    std::atomic<bool> snap_busy[2] { { false }, { false } };
    std::atomic<int>  snap_ready { -1 };   // index of a filled snapshot, or -1

    // ---- the loudspeaker recording, audio -> MQTT (audio.md 10.6, Rev 22).
    // The Recorder on the MQTT thread sets rec_on once its file is open and
    // clears it before closing; while it is set the audio thread appends each
    // period's monitor row to rec_ring.
    SampleRing        rec_ring;
    std::atomic<bool> rec_on { false };
    // --record-line's slot, raw, beside it (Rev 25): its output and its
    // capture, interleaved in pairs, while rec_on is set.
    SampleRing        line_ring;
    // Playback of a recording, MQTT -> audio (audio.md 10.7): the Player
    // fills play_ring and sets play_on; while play_on is set the audio thread
    // plays play_ring in place of the monitor, and while it is clear empties
    // it every period.
    SampleRing        play_ring;
    std::atomic<bool> play_on { false };

    // ---- lifetime and signalling
    std::atomic<bool> running        { true };   // thread lifetime
    std::atomic<bool> quit           { false };  // SIGTERM/SIGINT, or a lost stream
    std::atomic<bool> audio_failed   { false };   // stream lost unrecoverably

    // ---- the full detector publish that must precede the birth message
    // (audio.md 12). The MQTT thread increments publish_req to ask for one;
    // the analysis thread notices the new number at the start of a hop,
    // publishes every peer, op and optone that hop regardless of the two-hop
    // rule, and when the hop's results are all queued stores that number in
    // publish_done. The MQTT thread publishes "online" once publish_done has
    // caught up with the request it made. Numbers rather than a flag, so a
    // pass requested for an earlier connection can never be mistaken for the
    // current one.
    std::atomic<unsigned> publish_req  { 0 };
    std::atomic<unsigned> publish_done { 0 };

    // ---- counters for the log. Producers add; net.cpp's report_counters()
    // reads and zeroes them every ten seconds and logs any that are non-zero.
    std::atomic<unsigned> xruns        { 0 };
    std::atomic<unsigned> hops_lost    { 0 };
    std::atomic<unsigned> clips        { 0 };
    std::atomic<unsigned> limiter_hits { 0 };
    std::atomic<unsigned> gate_hits    { 0 };   // audio.md 10.5: times the gate shut
    std::atomic<unsigned> res_dropped  { 0 };
    std::atomic<unsigned> rec_dropped  { 0 };   // periods the recording lost, ring full
    std::atomic<unsigned> play_short   { 0 };   // periods playback ran dry mid-file

    // audio.md 10.8, Rev 28: each circuit's heard peer, by slot, written by
    // the analysis thread every hop - the one circuit heard, or 0 for idle,
    // deaf or ambiguous - and read by the audio thread for the peer boost.
    std::atomic<int> heard_peer[chan::N_SLOTS + 1] {};
    // The boost in use, for the log: hundredths of a dB, the peer's slot and
    // whether it is the start (0), measured (1) or fixed by the game (2),
    // packed by the audio thread as cdb * 1000 + peer * 10 + that; -1 for
    // none. Written once a second.
    std::atomic<int> peer_boost { -1 };

    // Output self-check (audio.md 11.4), per playback channel 1-34, element 0
    // unused: periods whose peak exceeded the channel's ceiling, and the
    // highest such peak in hundredths of a dB above -1000dBFS, so that zero
    // is "none yet" and every real peak raises it. The audio thread adds and
    // raises once a second; report_counters() reads and zeroes them.
    std::atomic<unsigned> out_over[chan::N_PLAY_CH + 1] {};
    std::atomic<int>      out_over_cdb[chan::N_PLAY_CH + 1] {};

    // What the driver actually granted, copied from AlsaStream at startup.
    int ncap  = chan::N_CAP_CH;
    int nplay = chan::N_PLAY_CH;
};
