// engine_probe.h - drives the real Engine with no audio device, for
// sbaudio_test and monitor_check. Engine names this struct its friend; nothing
// in the program uses it.
//
//   EngineProbe(eng).prepare_detached(256, chan::N_PLAY_CH, chan::N_CAP_CH);
//   EngineProbe(eng).capture();      // process_capture() on capture_row()s
//   EngineProbe(eng).drain();        // drain_commands()
//   EngineProbe(eng).render();       // render() into playback()
#pragma once

#include <algorithm>
#include <cmath>
#include <vector>

#include "../src/engine.h"

struct EngineProbe {
    Engine& e;
    explicit EngineProbe(Engine& eng) : e(eng) {}

    bool prepare_detached(unsigned period, unsigned nplay, unsigned ncap)
    {
        e.detached_ = true;
        e.det_period_ = period; e.det_nplay_ = nplay; e.det_ncap_ = ncap;
        return e.prepare();
    }
    void capture()      { e.process_capture(); }
    void drain()        { e.drain_commands(); }
    void render()       { e.render(); }
    void check_output() { e.check_output(); }

    // Document channel ch's capture for the next capture().
    float* capture_row(int ch) { return &e.capf_[(size_t)(ch - 1) * e.period_]; }
    // Interleaved: document channel ch, frame f, is [f * nplay + ch - 1].
    std::vector<int32_t>& playback() { return e.obuf_; }
    unsigned out_over(int ch) const  { return e.out_over_[ch]; }

    // The monitor chain.
    std::vector<float>& monitor_row()  { return e.mon_.row_; }
    void set_monitor_row(float v)      { std::fill(e.mon_.row_.begin(), e.mon_.row_.end(), v); }
    double gate_gain() const           { return e.mon_.gate_g_; }
    unsigned gate_hits() const         { return e.mon_.gate_hits_; }
    double peer_boost_db() const       { return 20.0 * std::log10(e.mon_.pb_lin_); }
};
