// ringdet.h - ring heard on a circuit's capture channel (audio.md 9.5), run by
// the audio thread once a period. Posts `ringing` on and off.
#pragma once

#include <vector>

#include "ipc.h"

class RingDetector {
public:
    explicit RingDetector(Shared& sh) : sh_(sh) {}

    // prepare()                                                      [startup]
    //   The window.
    void prepare();

    // step()                                                           [audio]
    //   One period of every circuit's capture, in capf (channel-major,
    //   `period` samples a channel), for the circuits among the first ncap.
    void step(const float* capf, unsigned period, int ncap);

private:
    // One circuit's state: the two Goertzels' delays and the debounce.
    struct Det {
        double s1 = 0.0, s2 = 0.0;          // 20Hz
        double h1 = 0.0, h2 = 0.0;          // 40Hz, its absent second harmonic
        int    above = 0, below = 0;        // consecutive blocks either side
        bool   on = false;                  // last value posted
    };

    Shared& sh_;
    Det det_[chan::N_SLOTS + 1];
    std::vector<float> win_;                // Hann window, one block
    unsigned n_ = 0;                        // samples into the current block,
                                            // the same for every circuit
};
