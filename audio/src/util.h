// util.h - logging, time and level helpers.
//
// audio.md 11.2: one line per event, to stderr, with uptime, picked up by the
// journal when run under systemd. Nothing here may be called from the audio
// thread: std::fprintf takes a lock and can block on a full pipe, and nothing
// blocks there (audio.md 3). The audio thread reports through the result
// queue instead.
//
// The exceptions are the pure arithmetic helpers at the bottom (db_to_lin,
// lin_to_db) and monotonic_s(), which is a vDSO clock read and never blocks;
// those are used everywhere, the audio thread included.
//
// Level conventions used throughout the program:
//   dBFS    decibels relative to digital full scale, where a sample of +-1.0 is
//           full scale. -40 dBFS is an amplitude of 0.01.
//   "lin"   a plain amplitude multiplier: 1.0 is unity gain, 0.5 is -6 dB.
#pragma once

#include <cmath>
#include <cstdarg>
#include <cstdio>

// log_start()                                                        [startup]
//   Records "now" as time zero for the uptime column. Called once, first thing
//   in main().
void   log_start();

// uptime_s()                                                             [any]
//   Seconds since log_start().
double uptime_s();

// monotonic_s()                                                          [any]
//   Seconds on CLOCK_MONOTONIC - a clock that never jumps when the wall clock
//   is set, which is what every timeout in the program wants.
double monotonic_s();

// log_line()                                      [any thread but the audio one]
//   printf-style. Writes one line to stderr, prefixed with the uptime, and
//   flushes it so the journal gets it immediately.
void log_line(const char* fmt, ...) __attribute__((format(printf, 1, 2)));

// db_to_lin() / lin_to_db()                                              [any]
//   Convert between decibels and an amplitude ratio (20 log10, not 10 log10:
//   these are amplitudes, not powers). lin_to_db clamps at 1e-30 so silence
//   reads as -600 dB rather than -infinity.
inline double db_to_lin(double db) { return std::pow(10.0, db / 20.0); }
inline double lin_to_db(double v)  { return 20.0 * std::log10(v > 1e-30 ? v : 1e-30); }

// format_db()                                                            [any]
//   A gain in dB as mqtt.md 7 wants it on the wire: signed decimal, no unit, no
//   plus sign, no trailing zeros. "%g" gives exactly that for the values in
//   range: -12.0 prints as "-12", 6.5 as "6.5".
inline void format_db(double db, char* out, size_t n) { std::snprintf(out, n, "%g", db); }
