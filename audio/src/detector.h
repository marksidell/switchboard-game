// detector.h - the analysis thread (audio.md 3, 6).
//
// Receives 4096-sample blocks per capture channel from the audio thread at the
// 2048-sample hop, runs the FFT and the detector of station 8.7, and hands
// results to the MQTT thread. Normal priority, separate from the audio thread
// so that thirty-two 4096-point FFTs every 43ms - a fraction of a millisecond
// of work, but bursty - never sit inside a period deadline.
//
// What the detector asks of each circuit's block, in one paragraph: transform
// it; for each pilot bin (and bin 768, the operator tone) compare the power in
// that bin with the typical power in four nearby "guard" bins that no pilot
// uses; call the pilot present if it is at least MARGIN_DB (20 dB) above them.
// Then:
//     own pilot absent         -> "deaf"        (the circuit's own fault)
//     no other pilot present   -> ""            (idle)
//     exactly one other        -> "trunk/2" etc (patched to that circuit)
//     more than one other      -> "ambiguous"   (a fault somewhere)
//     bin 768 present          -> op "on"       (operator bridged on)
// and the tap's channel is asked only whether it hears its own bin 768.
#pragma once

#include <fftw3.h>

#include <string>
#include <vector>

#include "ipc.h"

class Detector {
public:
    // Detector()                                                     [startup]
    //   Stores the reference; prepare() does the work.
    explicit Detector(Shared& sh) : sh_(sh) {}

    // ~Detector()                                                    [startup]
    //   Frees the FFTW plan and buffers.
    ~Detector();

    // prepare()                                                      [startup]
    //   Allocates the FFT buffers and plans the transform (reusing saved FFTW
    //   "wisdom" if there is any, so planning is instant after the first
    //   run), chooses rectangular or Hann analysis, and parses --dump.
    bool prepare();

    // run()                                                         [analysis]
    //   The thread body: wait for a snapshot, process it, repeat, until
    //   Shared::running goes false.
    void run();

    // process_snapshot()                                            [analysis]
    //   One hop, synchronously: transform every capture channel in snapshot
    //   `w` and post what changed. Public because the unit test drives it
    //   directly with a synthetic block, which is the cheapest way to check
    //   the detector arithmetic without hardware.
    void process_snapshot(int w);

private:
    // Confirm - the publishing state of one topic (one circuit's peer, one
    // circuit's op, or the tap's optone). A value is published only once it
    // has been seen on two consecutive hops, and only if it differs from what
    // was last published (audio.md 6.2). `seen` is false until the first
    // publish, and is reset to force a republish after an MQTT reconnect.
    struct Confirm {                 // two-hop confirmation, audio.md 6.2
        char last[40]    = { 0 };    // what the broker has been told
        char pending[40] = { 0 };    // the candidate value
        int  count       = 0;        // consecutive hops pending has been seen
        bool seen        = false;    // published at least once
    };

    void   analyse(int cap_index);
    double bin_db(int b) const;
    double bin_power(int b) const;
    void   confirm(Confirm& c, Topic t, int idx, const char* value, bool first);
    void   dump_row(uint64_t hop);

    Shared&        sh_;

    // ---- the transform. FFTW computes out_ = FFT(in_) each time the plan is
    // executed; a real 4096-point input gives 2049 complex outputs, bins
    // 0..2048, where bin b is b * 11.71875 Hz.
    fftwf_plan     plan_ = nullptr;
    float*         in_   = nullptr;   // 4096 samples, windowed if Hann
    fftwf_complex* out_  = nullptr;   // 2049 bins, [0] real, [1] imaginary
    std::vector<float>  win_;         // Hann window, empty in rectangular mode
    std::vector<double> pw_;          // |X|^2 per bin, for the block in hand

    // ---- publishing state, indexed by slot (element 0 unused)
    Confirm peer_[chan::N_SLOTS + 1];
    Confirm op_[chan::N_SLOTS + 1];
    Confirm optone_;
    unsigned publish_served_ = 0;     // last Shared::publish_req acted on

    // ---- the "ambiguous" log line, per slot: whether the last hop was
    // ambiguous, and when the pilot list was last logged (monotonic seconds).
    bool   amb_prev_[chan::N_SLOTS + 1]   = { false };
    double amb_logged_[chan::N_SLOTS + 1] = { 0.0 };

    // ---- analysis mode, set in prepare()
    int    guard_[4] = { 0, 0, 0, 0 };  // guard bin offsets from a pilot
    int    spread_   = 0;             // bins summed either side of a pilot:
                                      // 0 rectangular, 1 Hann

    // ---- --dump
    int    dump_slot_ = 0;            // slot being dumped, 0 = none
    int    dump_hops_ = 0;            // hops still to write
    bool   dump_header_ = false;      // CSV header written yet
};
