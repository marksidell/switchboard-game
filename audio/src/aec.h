// aec.h - the line echo canceller (audio.md 9.4, Rev 26).
//
// A two-wire circuit has no hybrid, so a file played on it returns on its own
// receive, 14 dB down on the bench, about 12 ms late (audio.md 9.3). While a
// file plays, the canceller learns that echo from what was sent and subtracts
// it, so the speech detector can judge what is left - the caller talking over
// the line - instead of discarding those frames.
//
// It works in the voice band at 8 kHz: the engine feeds it the file and the
// capture each through the detector's own 300-3400 Hz band-pass, taking every
// sixth sample. Two NLMS filters, 128 taps over 10-26 ms of lag:
//
//   background  adapts on every sample, double talk or not
//   foreground  what is subtracted; a copy of the background, taken only when
//               the background has done clearly better for three frames
//
// so the caller's voice can spoil the background, never the one in use, and a
// spoiled background is put back from the foreground. The two-path scheme
// (Ochiai 1977) needs no double-talk detector, which on this line would have
// to tell a caller 15 dB below the echo from the echo.
//
// Samples are addressed by a running 8 kHz index m that the engine keeps, so
// the reference, written during the render, and the capture, read a period
// later, line up however the periods fall. Allocation-free after construction
// and lock-free: safe in the audio thread.
#pragma once

#include <cstdint>

class EchoCanceller {
public:
    static constexpr int TAPS = 128;            // 16 ms at 8 kHz
    static constexpr int RING = 512;            // reference history, power of 2
    static constexpr int FRAME = 80;            // 10 ms at 8 kHz, the detector's frame
    static constexpr int DECIM = 6;             // 48 kHz -> 8 kHz
    // While it runs, a frame counts as speech only this far above the echo
    // it subtracted as well as above the usual threshold: the bench left the
    // residual 31-40 dB under the echo, a caller talking over the line 15-25.
    static constexpr double ECHO_MARGIN_DB = 20.0;

    // What one frame came to, for the speech detector.
    struct Frame {
        bool   full;        // the canceller ran for the whole frame
        bool   valid;       // and it is converged: judge the residual
        double resid_db;    // residual level, dBFS sine-referenced
        double echo_db;     // the echo it subtracted, the same
    };

    // configure()                                                    [startup]
    //   The lag before the first tap, in 8 kHz samples: 80, 10 ms, by
    //   default (--aec-delay). The bench round trip is 11.7 ms at 256 x 3.
    void configure(int delay) { delay_ = delay; }

    // start()                                                          [audio]
    //   A file begins on the circuit at index m. The reference history is
    //   cleared. After 30 s off, the filters are forgotten too: a new call is
    //   a new echo path. Within that, a second line keeps what the first
    //   learnt.
    void start(uint32_t m);

    // stop()                                                           [audio]
    //   The file and its echo are over.
    void stop(uint32_t m) { on_ = false; off_at_ = m; }

    bool on() const { return on_; }

    // ref()                                                            [audio]
    //   The band-passed file sample sent at index m.
    void ref(uint32_t m, float x) { ref_[m & (RING - 1)] = x; }

    // step()                                                           [audio]
    //   The band-passed capture sample at index m. Returns the residual.
    float step(uint32_t m, float c);

    // end_frame()                                                      [audio]
    //   At the detector's frame boundary: the frame's figures, and the
    //   two-path decisions taken on them.
    Frame end_frame(uint32_t m);

private:
    float    wf_[TAPS] = {};        // foreground
    float    wb_[TAPS] = {};        // background
    float    ref_[RING] = {};
    int      delay_ = 80;
    bool     on_ = false;
    bool     fresh_ = true;         // never run, or forgotten
    uint32_t off_at_ = 0;
    bool     converged_ = false;    // a copy has taken 20 dB off, since forgotten
    int      worse_ = 0;            // frames in a row the foreground has added echo
    int      better_ = 0;           // frames in a row the background has won
    // this frame
    double   sf_ = 0.0, sb_ = 0.0, sy_ = 0.0, sc_ = 0.0;
    int      n_ = 0;
};
