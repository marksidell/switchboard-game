// util.h - logging, time and level helpers.
//
// audio.md 11.2: one line per event, to stderr, with uptime, picked up by the
// journal when run under systemd. Nothing here may be called from the audio
// thread: std::fprintf takes a lock and can block on a full pipe, which is the
// first invariant CLAUDE.md lists. The audio thread reports through the result
// queue instead.
#pragma once

#include <cmath>
#include <cstdarg>
#include <cstdio>

void   log_start();                 // records t0 for the uptime column
double uptime_s();
double monotonic_s();

void log_line(const char* fmt, ...) __attribute__((format(printf, 1, 2)));

inline double db_to_lin(double db) { return std::pow(10.0, db / 20.0); }
inline double lin_to_db(double v)  { return 20.0 * std::log10(v > 1e-30 ? v : 1e-30); }

// A gain in dB as mqtt.md 7 wants it on the wire: signed decimal, no unit, no
// plus sign, no trailing zeros. "%g" gives exactly that for the values in range.
inline void format_db(double db, char* out, size_t n) { std::snprintf(out, n, "%g", db); }
