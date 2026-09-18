// channels.h - the channel plan and the pilot comb.
//
// docs/pilot-map.md is the authoritative slot <-> bin <-> circuit table and
// CLAUDE.md forbids recomputing it inline. This header is that table expressed
// once, in one place, so that the rest of the program asks rather than derives.
//
// Numbering, audio.md 2: circuits, A32 channels and document channels are all
// 1-based and all the same number. Slot n is A32 channel n is document channel
// n; the ALSA frame index is n-1. Stations are slots 1-23, slot 24 is the
// operator tap strip, trunks are slots 25-32.
#pragma once

#include <cstdio>
#include <cstring>

namespace chan {

constexpr int SAMPLE_RATE = 48000;
constexpr int FFT_N       = 4096;
constexpr int FFT_HOP     = 2048;                  // 50% overlap, ~42.7ms
constexpr double BIN_HZ   = (double)SAMPLE_RATE / (double)FFT_N;   // 11.71875

constexpr int PILOT_BIN0  = 512;                   // 6000.00 Hz
constexpr int PILOT_STEP  = 8;                     //   93.75 Hz
constexpr int OP_BIN      = 768;                   // 9000.00 Hz, operator tone

constexpr int N_SLOTS     = 32;
constexpr int N_STATIONS  = 23;                    // station 24 is the tap
constexpr int N_TRUNKS    = 8;
constexpr int TAP_SLOT    = 24;                    // no pilot of its own
constexpr int TRUNK_SLOT0 = 24;                    // trunk n is slot 24 + n

constexpr int N_PLAY_CH   = 34;                    // 32 A32 + monitor pair
constexpr int N_CAP_CH    = 32;                    // the four ADAT ports
constexpr int MON_CH_A    = 33;                    // Digiface analog out, both
constexpr int MON_CH_B    = 34;                    // carry the same mono signal

// Guard bins for the ratiometric threshold (station 8.4, 8.7). Offsets of +-2
// and +-3 are clear of the neighbouring pilots, which sit 8 bins away.
constexpr int GUARD_OFFSET[4] = { -3, -2, 2, 3 };

inline int pilot_bin(int slot) { return PILOT_BIN0 + PILOT_STEP * (slot - 1); }
inline double pilot_hz(int slot) { return pilot_bin(slot) * BIN_HZ; }

enum class Kind { None, Station, Trunk, Tap };

struct Circuit {
    Kind kind = Kind::None;
    int  n    = 0;          // station or trunk number, 1-based
};

inline Circuit slot_circuit(int slot)
{
    if (slot >= 1 && slot <= N_STATIONS)          return { Kind::Station, slot };
    if (slot == TAP_SLOT)                          return { Kind::Tap, 0 };
    if (slot > TRUNK_SLOT0 && slot <= N_SLOTS)     return { Kind::Trunk, slot - TRUNK_SLOT0 };
    return {};
}

inline int station_slot(int n) { return n; }
inline int trunk_slot(int n)   { return TRUNK_SLOT0 + n; }

inline bool is_circuit_slot(int slot)
{
    return slot >= 1 && slot <= N_SLOTS && slot != TAP_SLOT;
}

// A circuit id as it appears on the wire: "station/5", "trunk/2" (mqtt.md 3).
// Written into a caller-owned buffer so this is usable from the audio thread.
inline void circuit_id(int slot, char* out, size_t n)
{
    const Circuit c = slot_circuit(slot);
    switch (c.kind) {
    case Kind::Station: std::snprintf(out, n, "station/%d", c.n); break;
    case Kind::Trunk:   std::snprintf(out, n, "trunk/%d",   c.n); break;
    default:            if (n) out[0] = '\0';                     break;
    }
}

} // namespace chan
