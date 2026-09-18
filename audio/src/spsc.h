// spsc.h - single-producer single-consumer queue of POD entries.
//
// audio.md 3: the audio thread communicates only through queues. This is the
// queue: a fixed ring, no allocation after construction, no locks, and a slot
// count that is a power of two so the wrap is a mask.
//
// Capacity is one less than N, which is the usual cost of distinguishing full
// from empty with two indices and no count.
#pragma once

#include <atomic>
#include <cstddef>

template <typename T, size_t N>
class Spsc {
    static_assert((N & (N - 1)) == 0, "capacity must be a power of two");

public:
    // Producer side.
    bool push(const T& v)
    {
        const size_t w = wr_.load(std::memory_order_relaxed);
        const size_t n = (w + 1) & (N - 1);
        if (n == rd_.load(std::memory_order_acquire)) return false;   // full
        buf_[w] = v;
        wr_.store(n, std::memory_order_release);
        return true;
    }

    // Consumer side.
    bool pop(T& out)
    {
        const size_t r = rd_.load(std::memory_order_relaxed);
        if (r == wr_.load(std::memory_order_acquire)) return false;   // empty
        out = buf_[r];
        rd_.store((r + 1) & (N - 1), std::memory_order_release);
        return true;
    }

private:
    T buf_[N] {};
    std::atomic<size_t> wr_ { 0 };
    std::atomic<size_t> rd_ { 0 };
};
