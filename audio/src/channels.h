// channels.h - the channel plan and the pilot comb.
//
// docs/pilot-map.md is the authoritative slot <-> bin <-> circuit table and
// CLAUDE.md forbids recomputing it inline. This header is that table expressed
// once, in one place, so that the rest of the program asks rather than derives.
//
// Numbering, audio.md 2: circuits, A32 channels and document channels are all
// 1-based and all the same number. Slot n is A32 channel n is document channel
// n; the ALSA frame index is n-1. Stations are slots 1-22, slot 23 is the
// operator tap strip, slot 24 is the audience monitor output, trunks are slots
// 25-32.
//
// The one idea to hold on to when reading the rest of the program: almost
// everything is indexed by SLOT, 1-32. A slot is simultaneously a circuit
// (station 5 is slot 5, trunk 2 is slot 26), an output channel, an input
// channel and a pilot frequency. Arrays indexed by slot are therefore sized
// N_SLOTS + 1 and element 0 is unused, so that prog_[5] is station 5 and not
// station 6. The only other numbering is the playback channel 1-34 used by the
// test tone, which is the same as the slot for 1-32 and adds the monitor pair
// 33 and 34.
//
//      slot   1 ... 22    23     24       25 ... 32     33, 34
//             stations    tap    monitor  trunks 1-8    Digiface analog out
//      bin    512 ... 680 (688)  (696)    704 ... 760   -
//
// Slots 23 and 24 have no circuit and no pilot: station board 3's strip 7 is
// the operator tap and strip 8's output is the loudspeaker feed (audio.md 2,
// Rev 7). Their bins, 688 and 696, are never generated, so hearing one is a
// fault rather than a topology.
//
// Everything here is constexpr or inline, so there is no channels.cpp.
#pragma once

#include <cstdio>
#include <cstring>

namespace chan {

// ---- the transform and the comb (station 8.2, docs/pilot-map.md)

constexpr int SAMPLE_RATE = 48000;
constexpr int FFT_N       = 4096;
constexpr int FFT_HOP     = 2048;                  // 50% overlap, ~42.7ms
constexpr double BIN_HZ   = (double)SAMPLE_RATE / (double)FFT_N;   // 11.71875

constexpr int PILOT_BIN0  = 512;                   // 6000.00 Hz
constexpr int PILOT_STEP  = 8;                     //   93.75 Hz
constexpr int OP_BIN      = 768;                   // 9000.00 Hz, operator tone

constexpr int N_SLOTS     = 32;
constexpr int N_STATIONS  = 22;                    // 23 is the tap, 24 the monitor
constexpr int N_TRUNKS    = 8;
constexpr int TAP_CH      = 23;                    // operator tone out, tap receive in
constexpr int MONITOR_CH  = 24;                    // A32 output to the amplifier
constexpr int TRUNK_SLOT0 = 24;                    // trunk n is slot 24 + n

constexpr int N_PLAY_CH   = 34;                    // 32 A32 + the Digiface pair
constexpr int N_CAP_CH    = 32;                    // the four ADAT ports
constexpr int DIGIFACE_CH_A = 33;                  // Digiface analog out: silent,
constexpr int DIGIFACE_CH_B = 34;                  // or the fallback monitor

// Guard bins for the ratiometric threshold (station 8.4, 8.7). Offsets of +-2
// and +-3 are clear of the neighbouring pilots, which sit 8 bins away.
constexpr int GUARD_OFFSET[4] = { -3, -2, 2, 3 };

// pilot_bin() / pilot_hz()                                               [any]
//   The FFT bin, and the frequency in Hz, of a slot's pilot: slot 1 is bin
//   512 (6000.00 Hz), each slot eight bins (93.75 Hz) above the last. For
//   slot 24 this returns bin 696, which is never generated.
inline int pilot_bin(int slot) { return PILOT_BIN0 + PILOT_STEP * (slot - 1); }
inline double pilot_hz(int slot) { return pilot_bin(slot) * BIN_HZ; }

// ---- slots <-> circuits

// What sits behind a slot. None is returned for a slot number out of range.
enum class Kind { None, Station, Trunk, Tap, Monitor };

// A circuit as the documents name it: its kind, and its number within that
// kind. Slot 26 is { Trunk, 2 }; slot 23 is { Tap, 0 } and slot 24 is
// { Monitor, 0 }, neither of which is a circuit.
struct Circuit {
    Kind kind = Kind::None;
    int  n    = 0;          // station or trunk number, 1-based
};

// slot_circuit()                                                         [any]
//   Slot number 1-32 to the circuit behind it.
inline Circuit slot_circuit(int slot)
{
    if (slot >= 1 && slot <= N_STATIONS)          return { Kind::Station, slot };
    if (slot == TAP_CH)                            return { Kind::Tap, 0 };
    if (slot == MONITOR_CH)                        return { Kind::Monitor, 0 };
    if (slot > TRUNK_SLOT0 && slot <= N_SLOTS)     return { Kind::Trunk, slot - TRUNK_SLOT0 };
    return {};
}

// station_slot() / trunk_slot()                                         [any]
//   The inverse: a station or trunk number to its slot. Station n is slot n;
//   trunk n is slot 24 + n. Neither checks its range - the MQTT thread does,
//   before it ever calls them.
inline int station_slot(int n) { return n; }
inline int trunk_slot(int n)   { return TRUNK_SLOT0 + n; }

// is_circuit_slot()                                                      [any]
//   True for the 30 slots that are real circuits - stations 1-22 and trunks
//   1-8 - and false for the tap, the monitor and anything out of range. Every
//   loop over "all circuits" in the program is a loop over 1-32 that skips
//   slots for which this is false. A slot with no circuit also has no pilot.
inline bool is_circuit_slot(int slot)
{
    return slot >= 1 && slot <= N_SLOTS && slot != TAP_CH && slot != MONITOR_CH;
}

// is_read_channel()                                                     [any]
//   True for the capture channels anything reads: the 30 circuits and the tap
//   (channel 23), whose bin 768 is the optone check and whose audio is the
//   monitor source. Capture channel 24 has no receive path fitted and is read
//   by nothing - not the detector, not the monitor, not the speech detector
//   (audio.md 2, Rev 7).
inline bool is_read_channel(int ch)
{
    return is_circuit_slot(ch) || ch == TAP_CH;
}

// can_carry_monitor()                                                    [any]
//   The playback channels --monitor-ch may name (audio.md 10.1, 14): the A32
//   output wired to the amplifier, and the Digiface's own analog pair as the
//   fallback. A circuit or the tap is refused, so the monitor can never
//   displace a pilot or the operator tone.
inline bool can_carry_monitor(int ch)
{
    return ch == MONITOR_CH || ch == DIGIFACE_CH_A || ch == DIGIFACE_CH_B;
}

// circuit_id()                                                           [any]
//   A circuit id as it appears on the wire: "station/5", "trunk/2" (mqtt.md 3).
//   Written into a caller-owned buffer so this is usable from the audio
//   thread; an empty string for the tap or a slot out of range.
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
