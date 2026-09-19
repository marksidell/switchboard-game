// spsc.h - single-producer single-consumer queue of POD entries.
//
// audio.md 3: the audio thread communicates only through queues. This is the
// queue: a fixed ring, no allocation after construction, no locks, and a slot
// count that is a power of two so the wrap is a mask.
//
// Capacity is one less than N, which is the usual cost of distinguishing full
// from empty with two indices and no count.
//
// How it works
// ------------
// buf_ is a plain array of N entries used as a circle. Two indices chase each
// other round it:
//
//     wr_  the next slot the producer will fill      (written only by producer)
//     rd_  the next slot the consumer will take       (written only by consumer)
//
//          rd_                 wr_
//           v                   v
//     [ . | A | B | C | D | . | . | . ]      A..D are waiting to be popped
//
// Empty is rd_ == wr_. Full is "advancing wr_ would make it equal rd_", so one
// slot is always left unused - that is what lets the two cases be told apart
// without a separate count, and a separate count would be a variable both
// threads write, which is exactly what this design avoids.
//
// Why there is no lock: each index has exactly one writer. The producer writes
// the entry, then publishes it by storing wr_ with release ordering; the
// consumer loads wr_ with acquire ordering before reading the entry, which
// guarantees it sees the entry's contents and not whatever was in the slot
// before. The same pairing in the other direction tells the producer when a
// slot has been freed. Neither side ever waits for the other: push() on a full
// queue and pop() on an empty one simply return false.
//
// Used in three places (ipc.h): commands MQTT -> audio, and two result queues,
// audio -> MQTT and analysis -> MQTT. T is always a small plain struct, copied
// in and out by value.
#pragma once

#include <atomic>
#include <cstddef>

template <typename T, size_t N>
class Spsc {
    static_assert((N & (N - 1)) == 0, "capacity must be a power of two");

public:
    // push()                                                  [producer thread]
    //   Copies v into the next free slot and makes it visible to the consumer.
    //   Returns false, and changes nothing, if the queue is full. Never blocks,
    //   never allocates, so it is safe to call from the audio thread.
    bool push(const T& v)
    {
        const size_t w = wr_.load(std::memory_order_relaxed);
        const size_t n = (w + 1) & (N - 1);
        if (n == rd_.load(std::memory_order_acquire)) return false;   // full
        buf_[w] = v;
        wr_.store(n, std::memory_order_release);
        return true;
    }

    // pop()                                                   [consumer thread]
    //   Copies the oldest entry into `out` and frees its slot. Returns false,
    //   leaving `out` untouched, if the queue is empty. Never blocks.
    bool pop(T& out)
    {
        const size_t r = rd_.load(std::memory_order_relaxed);
        if (r == wr_.load(std::memory_order_acquire)) return false;   // empty
        out = buf_[r];
        rd_.store((r + 1) & (N - 1), std::memory_order_release);
        return true;
    }

private:
    T buf_[N] {};                       // the ring; N entries, N-1 usable
    std::atomic<size_t> wr_ { 0 };      // next slot to fill - producer owns it
    std::atomic<size_t> rd_ { 0 };      // next slot to take - consumer owns it
};
