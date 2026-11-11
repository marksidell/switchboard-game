// channels.h - the channel plan and the pilot comb.
//
// docs/pilot-map.md is the authoritative slot <-> bin <-> circuit table and
// CLAUDE.md forbids recomputing it inline. This header is that table expressed
// once, in one place, so that the rest of the program asks rather than derives.
//
// Numbering, audio.md 2: circuits, A32 channels and document channels are all
// 1-based and all the same number. Slot n is A32 channel n is document channel
// n; the ALSA frame index is n-1. Stations are slots 1-22 and 24, slot 23 is
// the operator tap strip, trunks are slots 25-32. Station 24 is a real
// telephone (audio.md Rev 24); the audience monitor is on the Digiface's own
// analog pair, 33 and 34.
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
//      slot   1 ... 22    23     24          25 ... 32     33, 34
//             stations    tap    station 24  trunks 1-8    monitor
//      bin    512 ... 680 (688)  696         704 ... 760   -
//
// Slot 23 has no circuit and no pilot: station board 3's strip 7 is the
// operator tap (audio.md 2, Rev 7). Its bin, 688, is never generated, so
// hearing it is a fault rather than a topology. Slot 24 fed the loudspeaker
// from Rev 7 to Rev 23 and is station 24 from Rev 24.
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
constexpr int N_STATIONS  = 22;                    // 1-22; and 24, PHONE_STATION
constexpr int PHONE_STATION = 24;                  // the real telephone, audio.md Rev 24
constexpr int N_TRUNKS    = 8;
constexpr int TAP_CH      = 23;                    // operator tone out, tap receive in
constexpr int TRUNK_SLOT0 = 24;                    // trunk n is slot 24 + n

// The loudspeaker's file (audio.md 10.4) is kept in prog_[MONITOR_PROG] and
// reported under that index: element 0, which no slot uses. It was prog_[24]
// while channel 24 carried the monitor.
constexpr int MONITOR_PROG = 0;

constexpr int N_PLAY_CH   = 34;                    // 32 A32 + the Digiface pair
constexpr int N_CAP_CH    = 32;                    // the four ADAT ports
constexpr int DIGIFACE_CH_A = 33;                  // Digiface analog out:
constexpr int DIGIFACE_CH_B = 34;                  // the monitor

// Guard bins for the ratiometric threshold (station 8.4, 8.7). Offsets of +-2
// and +-3 are clear of the neighbouring pilots, which sit 8 bins away.
constexpr int GUARD_OFFSET[4] = { -3, -2, 2, 3 };

// pilot_bin() / pilot_hz()                                               [any]
//   The FFT bin, and the frequency in Hz, of a slot's pilot: slot 1 is bin
//   512 (6000.00 Hz), each slot eight bins (93.75 Hz) above the last. For
//   slot 23 this returns bin 688, which is never generated.
inline int pilot_bin(int slot) { return PILOT_BIN0 + PILOT_STEP * (slot - 1); }
inline double pilot_hz(int slot) { return pilot_bin(slot) * BIN_HZ; }

// ---- slots <-> circuits

// What sits behind a slot. None is returned for a slot number out of range.
enum class Kind { None, Station, Trunk, Tap };

// A circuit as the documents name it: its kind, and its number within that
// kind. Slot 26 is { Trunk, 2 }; slot 24 is { Station, 24 }; slot 23 is
// { Tap, 0 }, which is not a circuit.
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
    if (slot == PHONE_STATION)                     return { Kind::Station, slot };
    if (slot > TRUNK_SLOT0 && slot <= N_SLOTS)     return { Kind::Trunk, slot - TRUNK_SLOT0 };
    return {};
}

// station_slot() / trunk_slot()                                         [any]
//   The inverse: a station or trunk number to its slot. Station n is slot n;
//   trunk n is slot 24 + n. Neither checks its range - the MQTT thread does,
//   with is_station(), before it ever calls them.
inline int station_slot(int n) { return n; }
inline int trunk_slot(int n)   { return TRUNK_SLOT0 + n; }

// is_station()                                                           [any]
//   True for a station number that exists: 1-22 and 24 (audio.md 12, Rev 24).
inline bool is_station(int n) { return (n >= 1 && n <= N_STATIONS) || n == PHONE_STATION; }

// is_circuit_slot()                                                      [any]
//   True for the 31 slots that are real circuits - stations 1-22 and 24 and
//   trunks 1-8 - and false for the tap and anything out of range. Every
//   loop over "all circuits" in the program is a loop over 1-32 that skips
//   slots for which this is false. A slot with no circuit also has no pilot.
inline bool is_circuit_slot(int slot)
{
    return slot >= 1 && slot <= N_SLOTS && slot != TAP_CH;
}

// monitor_source_channel()                                              [any]
//   audio.md 10.3: the monitor's source names a capture channel. "tap" is 23,
//   "station/n" is n and "trunk/n" is 24 + n - which is to say the circuit's
//   own slot, since a circuit's slot and its capture channel are the same
//   number. Returns 0 for anything else, which is what makes this the one
//   place the accepted set is defined: --monitor-src and monitor/source/set
//   both validate through it, so the option and the topic cannot drift apart.
inline int monitor_source_channel(const char* s)
{
    if (!s) return 0;
    if (std::strcmp(s, "tap") == 0) return TAP_CH;

    const char* rest = nullptr;
    int lo = 0, hi = 0, base = 0;
    if (std::strncmp(s, "station/", 8) == 0) { rest = s + 8;  lo = 1; hi = PHONE_STATION; base = 0; }
    else if (std::strncmp(s, "trunk/", 6) == 0) { rest = s + 6; lo = 1; hi = N_TRUNKS; base = TRUNK_SLOT0; }
    else return 0;

    // Digits only, and at least one: strtol would take " 3", "3x" and "+3".
    if (!*rest) return 0;
    int n = 0;
    for (const char* c = rest; *c; ++c) {
        if (*c < '0' || *c > '9') return 0;
        n = n * 10 + (*c - '0');
        if (n > N_SLOTS) return 0;              // cannot become valid; stop early
    }
    if (n < lo || n > hi) return 0;
    if (base == 0 && !is_station(n)) return 0;  // station/23 is the tap's slot
    return base + n;
}

// monitor_source_name()                                                  [any]
//   The inverse, for the echo on monitor/source and for the log. Writes "tap",
//   "station/n" or "trunk/n" and returns false if ch is not a source.
inline bool monitor_source_name(int ch, char* out, size_t n)
{
    if (ch == TAP_CH)          { std::snprintf(out, n, "tap"); return true; }
    if (!is_circuit_slot(ch))  { return false; }
    const Circuit c = slot_circuit(ch);
    if (c.kind == Kind::Station) { std::snprintf(out, n, "station/%d", c.n); return true; }
    if (c.kind == Kind::Trunk)   { std::snprintf(out, n, "trunk/%d", c.n);   return true; }
    return false;
}

// can_carry_monitor()                                                    [any]
//   The playback channels --monitor-ch may name (audio.md 10.1, 14): the
//   Digiface's own analog pair. A circuit or the tap is refused, so the
//   monitor can never displace a pilot or the operator tone. 24 was accepted
//   until Rev 24 made it a station.
inline bool can_carry_monitor(int ch)
{
    return ch == DIGIFACE_CH_A || ch == DIGIFACE_CH_B;
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
