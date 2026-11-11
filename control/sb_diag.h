/* =============================================================================
 * sb_diag.h - loop timing and the console banner
 *
 * control.md 9.1. Diagnostic only: nothing here changes what the board does.
 * The console is silent unless something happens - RUN and IDLE are announced
 * as they occur - and the rest is had by pressing Enter, which prints the
 * banner: configuration and live state together, and the loop timing since the
 * last banner.
 * ========================================================================== */

#pragma once

#include <Arduino.h>

/* The sections of a loop pass, timed by TIMED(). T_FAILSAFE includes the I2C
 * rescan; T_I2C_PUB is only the ctl/i2c publish on reconnect. */
enum { T_NET, T_VERIFY, T_INPUTS, T_STATION, T_TRUNK, T_FLUSH, T_BEAT, T_FAILSAFE,
       T_REPUB, T_OTA, T_ENABLE, T_I2C_PUB, T_SERIAL, T_N };

void diagNoteTime(int k, uint32_t us);

#define TIMED(k, stmt) do { const uint32_t _t0 = micros(); stmt; \
                            diagNoteTime(k, micros() - _t0); } while (0)

/* At each poll tick but the first: the interval since the last one. */
void diagPollGap(uint32_t now, uint32_t gap_ms);

/* At the end of every loop pass, before the console is read. */
void diagEndPass(uint32_t pass_start_us);

/* Prints the banner for Enter, at most every BANNER_MIN_MS. */
void diagServiceConsole(uint32_t now);

void printBanner();
