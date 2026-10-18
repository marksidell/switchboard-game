// rec.h - recording the loudspeaker feed to a file, and playing a recording
// back to it (audio.md 10.6, 10.7, Rev 22).
//
// Three pieces, on the two sides of the real-time line:
//
//   SampleRing  a fixed ring of float samples, allocated at startup, one
//               writer and one reader, no locks. Two of them in Shared:
//               rec_ring, audio thread -> MQTT thread, the monitor row while
//               a recording runs; play_ring, MQTT thread -> audio thread, the
//               recording being played back.
//
//   Recorder    MQTT thread. Opens the WAV, empties rec_ring into it every
//               pass of the loop, closes it, and starts `lame` to make the
//               MP3 beside it. Lists the newest recordings.
//
//   Player      MQTT thread. Opens a recording and keeps play_ring topped up
//               from it until the end of the file.
//
// Every file operation is in the last two, none in the audio thread (audio.md
// 3). The audio thread learns what runs from Shared::rec_on and play_on.
#pragma once

#include <sndfile.h>
#include <sys/types.h>

#include <algorithm>
#include <atomic>
#include <cstddef>
#include <string>
#include <vector>

// SampleRing - Spsc (spsc.h) in blocks of samples rather than single entries,
// and with its storage on the heap: 2^20 floats is 4 MB, too much for the
// Shared object on main()'s stack. The same two-index scheme: each index has
// one writer, and the release/acquire pair on it publishes the samples.
class SampleRing {
public:
    static constexpr size_t N = (size_t)1 << 20;   // 21.8 s at 48 kHz

    // allocate()                                                     [startup]
    void allocate() { buf_.assign(N, 0.0f); }

    // write()                                                         [writer]
    //   Appends n samples, or nothing at all if they do not all fit. Returns
    //   false in that case. Never blocks or allocates.
    bool write(const float* s, size_t n)
    {
        const size_t w = wr_.load(std::memory_order_relaxed);
        const size_t r = rd_.load(std::memory_order_acquire);
        if (N - 1 - ((w - r) & (N - 1)) < n) return false;
        for (size_t i = 0; i < n; ++i) buf_[(w + i) & (N - 1)] = s[i];
        wr_.store((w + n) & (N - 1), std::memory_order_release);
        return true;
    }

    // read()                                                          [reader]
    //   Takes up to n of the oldest samples into out. Returns how many.
    size_t read(float* out, size_t n)
    {
        const size_t r = rd_.load(std::memory_order_relaxed);
        const size_t w = wr_.load(std::memory_order_acquire);
        const size_t have = std::min(n, (w - r) & (N - 1));
        for (size_t i = 0; i < have; ++i) out[i] = buf_[(r + i) & (N - 1)];
        rd_.store((r + have) & (N - 1), std::memory_order_release);
        return have;
    }

    // available()                                                [either side]
    //   Samples waiting to be read.
    size_t available() const
    {
        return (wr_.load(std::memory_order_acquire) - rd_.load(std::memory_order_acquire)) & (N - 1);
    }

    // discard()                                                       [reader]
    //   Throws away whatever is waiting: the tail of a period the audio
    //   thread wrote after a recording stopped, before the next one starts;
    //   or, on the audio thread, what is left of a playback that stopped.
    void discard() { rd_.store(wr_.load(std::memory_order_acquire), std::memory_order_release); }

private:
    std::vector<float>  buf_;
    std::atomic<size_t> wr_ { 0 };
    std::atomic<size_t> rd_ { 0 };
};

struct Shared;

class Recorder {
public:
    explicit Recorder(Shared& sh) : sh_(sh) {}
    ~Recorder();

    // prepare()                                                      [startup]
    //   Allocates the ring and the transfer buffer.
    void prepare();

    // start()                                                           [mqtt]
    //   Opens <record-dir>/<local date and time>.wav and sets rec_on. Returns
    //   the base name, or "" if the file could not be opened (logged). A
    //   recording already running is left as it is and its name returned.
    std::string start();

    // stop()                                                            [mqtt]
    //   Clears rec_on, writes what is left in the ring, closes the WAV and,
    //   if `convert`, starts lame on it. Nothing if none is running.
    void stop(bool convert);

    // service()                                                         [mqtt]
    //   Every pass of Net::run(): empties the ring into the file, stops at
    //   --record-max, and reaps a finished lame. Returns true if it stopped
    //   the recording itself, so the caller republishes the state.
    bool service(double now);

    bool        running() const { return snd_ != nullptr; }
    const std::string& name() const { return name_; }

    // list()                                                            [mqtt]
    //   The newest `most` recordings in --record-dir, newest first, one per
    //   line as "<name> <seconds>", leaving out the one being written. What
    //   audio/recordings carries (audio.md 10.7).
    std::string list(int most = 10) const;

private:
    void drain();
    void convert(const std::string& base);

    Shared&            sh_;
    SNDFILE*           snd_ = nullptr;
    std::string        name_;               // base name of the file being written
    double             since_ = 0.0;        // monotonic start time
    double             gain_ = 1.0;         // the makeup gain, linear
    std::vector<float> xfer_;               // ring -> file, one chunk
    std::vector<pid_t> lame_;               // conversions not yet reaped
};

class Player {
public:
    explicit Player(Shared& sh) : sh_(sh) {}
    ~Player();

    // start()                                                           [mqtt]
    //   Plays <record-dir>/<name>.wav on the loudspeaker in place of the
    //   monitor (audio.md 10.7). Returns false, having logged why, if the
    //   name is not a recording's or the file will not open. One already
    //   playing is stopped first, and the new one starts on the next pass,
    //   once the audio thread has let go of the old one's samples.
    bool start(const std::string& name);

    // stop()                                                            [mqtt]
    void stop();

    // service()                                                         [mqtt]
    //   Every pass of Net::run(): starts a pending playback, keeps the ring
    //   two seconds ahead, and ends the playback once the file is read and the
    //   ring has run dry. Returns true when what it reports has changed.
    bool service();

    // What audio/playback says: the name playing or waiting to, or "".
    const std::string& name() const { return name_; }

private:
    bool open(const std::string& name);
    void fill();

    Shared&            sh_;
    SNDFILE*           snd_ = nullptr;
    std::string        name_;
    std::string        pending_;            // to start on the next pass
    bool               eof_ = false;
    double             gain_ = 1.0;         // the inverse of the recording's makeup
    std::vector<float> xfer_;
};
