#include "util.h"

#include <ctime>

static double g_t0 = 0.0;

double monotonic_s()
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

void log_start() { g_t0 = monotonic_s(); }

double uptime_s() { return monotonic_s() - g_t0; }

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
