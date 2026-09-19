// util.cpp - logging and time. See util.h for what each function is for.

#include "util.h"

#include <ctime>

// The moment log_start() was called, on the monotonic clock. Written once at
// startup, before any other thread exists, and only read afterwards.
static double g_t0 = 0.0;

// monotonic_s()                                                          [any]
//   Reads CLOCK_MONOTONIC and returns it as seconds in a double.
double monotonic_s()
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

// log_start()                                                        [startup]
//   Sets time zero for the log's uptime column.
void log_start() { g_t0 = monotonic_s(); }

// uptime_s()                                                             [any]
//   Seconds since log_start().
double uptime_s() { return monotonic_s() - g_t0; }

// log_line()                                      [any thread but the audio one]
//   Formats the message into a fixed buffer (long messages are truncated at
//   511 characters rather than allocating), then writes it as one line:
//
//       [   17.502] mqtt: station/1 play/set greeting_1 (0.75s, hf -84.6 dBFS)
//
//   Two threads may log at once; stdio's internal lock keeps each fprintf call
//   whole, so lines do not interleave mid-line.
void log_line(const char* fmt, ...)
{
    char msg[512];
    va_list ap;
    va_start(ap, fmt);
    std::vsnprintf(msg, sizeof msg, fmt, ap);
    va_end(ap);
    // Uptime rather than a wall clock: the journal stamps the wall clock
    // already, and what a reader wants from this column is how long after the
    // stream started something happened.
    std::fprintf(stderr, "[%9.3f] %s\n", uptime_s(), msg);
    std::fflush(stderr);
}
