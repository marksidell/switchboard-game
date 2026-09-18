// detector.h - the analysis thread (audio.md 3, 6).
//
// Receives 4096-sample blocks per capture channel from the audio thread at the
// 2048-sample hop, runs the FFT and the detector of station 8.7, and hands
// results to the MQTT thread. Normal priority, separate from the audio thread
// so that thirty-two 4096-point FFTs every 43ms - a fraction of a millisecond
// of work, but bursty - never sit inside a period deadline.
#pragma once

#include <fftw3.h>

#include <string>
#include <vector>

#include "ipc.h"

class Detector {
public:
    explicit Detector(Shared& sh) : sh_(sh) {}
    ~Detector();

    bool prepare();
    void run();

    // One hop, synchronously: transform every capture channel in snapshot `w`
    // and post what changed. Public because the unit test drives it directly
    // with a synthetic block, which is the cheapest way to check the detector
    // arithmetic without hardware.
    void process_snapshot(int w);

private:
    struct Confirm {                 // two-hop confirmation, audio.md 6.2
        char last[40]    = { 0 };    // what the broker has been told
        char pending[40] = { 0 };
        int  count       = 0;
        bool seen        = false;
    };

    void   analyse(int cap_index);
    double bin_db(int b) const;
    double bin_power(int b) const;
    void   confirm(Confirm& c, Topic t, int idx, const char* value, bool first);
    void   dump_row(uint64_t hop);

    Shared&        sh_;
    fftwf_plan     plan_ = nullptr;
    float*         in_   = nullptr;
    fftwf_complex* out_  = nullptr;
    std::vector<float>  win_;
    std::vector<double> pw_;          // |X|^2 per bin, for the block in hand

    Confirm peer_[chan::N_SLOTS + 1];
    Confirm op_[chan::N_SLOTS + 1];
    Confirm optone_;

    int    guard_[4] = { 0, 0, 0, 0 };
    int    spread_   = 0;             // bins summed either side of a pilot
    int    dump_slot_ = 0;
    int    dump_hops_ = 0;
    bool   dump_header_ = false;
};
