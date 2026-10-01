/* =============================================================================
 * sb_config.h - build configuration, pins and timing constants
 *
 * Every number the firmware's behaviour depends on lives here or in sb_table.cpp,
 * so a reader checking the firmware against control.md does not have to search for
 * the value that implements a given threshold. Each constant carries the section
 * of control.md or mqtt.md it comes from.
 * ========================================================================== */

#pragma once

#include <Arduino.h>

/* ---- Which firmware this is (control.md 9.1, Rev 18) ---------------------
 * The revision of control.md this source implements: raise it with that
 * document whenever a revision has a firmware consequence. The commit and the
 * build time come from sb_version.h, which control/compile writes before it
 * compiles; a build without it says "unknown". Published on ctl/firmware. */
static constexpr unsigned FIRMWARE_SPEC_REV = 18;
#if __has_include("sb_version.h")
#include "sb_version.h"
#else
#define FIRMWARE_COMMIT "unknown"
#define FIRMWARE_BUILT  __DATE__ " " __TIME__
#endif

/* ---- Build configuration -------------------------------------------------
 * control.md 4.2 step 5: the scan list is driven from the configured station
 * board count, not hard-coded to 0x20-0x23. A scan that always looks for four
 * devices logs a phantom missing expander on every boot, which trains whoever
 * reads the log to ignore the one message that matters.
 *
 * Three station boards, so the scan expects 0x20, 0x21, 0x22 and 0x23.
 * ------------------------------------------------------------------------- */
static constexpr uint8_t STATION_BOARDS_FITTED = 3;

static constexpr uint8_t STATIONS_PER_BOARD = 8;

/* Twenty-two stations. The last two positions on the last station board -
 * 0x22, strips 7 and 8, bits 6 and 7 - are the operator tap and the audience
 * monitor output, and neither has a relay or a ring detector fitted (station
 * Rev 3.40, control.md 6.1; mqtt.md 9 numbers stations 1-22). Three boards give
 * 24 positions and two of them are not stations. */
static constexpr uint8_t N_STATIONS = 22;
static constexpr uint8_t N_TRUNKS   = 8;

/* ---- Pins (control.md 3; generator 3.1/3.2 is the authority) ---------------
 * PIN_PWM_A/B, PIN_SD, PIN_ENBL and PIN_SYNC are declared in control.ino, which
 * owns the waveform. The I2C pins and /RESET are here because the expander
 * driver is a separate translation unit and needs them.
 * ------------------------------------------------------------------------- */
static constexpr int PIN_EXP_RESET = 5;     // expander /RESET, active LOW, idles HIGH.
                                            // Strapping pin - must be high at boot.
static constexpr int PIN_I2C_SDA = 13;      // Wire.begin(13, 16) - argument order
static constexpr int PIN_I2C_SCL = 16;
static constexpr uint32_t I2C_CLOCK_HZ = 100000;

/* ---- Poll rate (control.md 6.3) -------------------------------------------
 * 200Hz. Five samples per half-cycle of the 40Hz station ring pulse train, and
 * 5ms granularity for every threshold in 8.1 and 8.2. Everything in the station
 * and trunk logic runs from this sample stream; nothing samples independently.
 * ------------------------------------------------------------------------- */
static constexpr uint32_t POLL_PERIOD_MS = 5;

/* ---- Station ring detection (control.md 7.1) ------------------------------ */
static constexpr uint8_t  RING_TRANSITIONS_TO_DECLARE = 4;    // within the window
static constexpr uint32_t RING_DECLARE_WINDOW_MS      = 150;
static constexpr uint32_t RING_RELEASE_QUIET_MS       = 100;   // no transition
// control.md 7.3 (Rev 17): a station dialling, for the board test. The nominal
// Bell figures, 10pps at 61% break, and a dial's return between digits.
static constexpr uint32_t DIAL_BREAK_MS               = 61;
static constexpr uint32_t DIAL_MAKE_MS                = 39;
static constexpr uint32_t DIAL_INTERDIGIT_MS          = 700;
static constexpr uint8_t  DIAL_MAX_DIGITS             = 16;

/* ---- Trunk seizure classifier (control.md 8.1, 8.2) ----------------------
 * The thresholds are the table in 8.2 and must be read against it. A break of
 * 25ms is 5 samples and one of 100ms is 20, so a nominal 61ms dial pulse sits
 * at 12 samples with 7 in hand either way.
 * ------------------------------------------------------------------------- */
static constexpr uint32_t SEIZE_DECLARE_MS     = 100;   // asserted from idle
static constexpr uint32_t PULSE_BREAK_MIN_MS   =  25;   // open, counts as a pulse
static constexpr uint32_t PULSE_BREAK_MAX_MS   = 100;   // open, above this is not a pulse
static constexpr uint32_t DIGIT_END_MAKE_MS    = 200;   // closed, after >= 1 pulse
static constexpr uint32_t RELEASE_OPEN_MS      = 250;   // open, trunk released
static constexpr uint32_t RING_BREAK_GAP_MS    =  60;   // successive breaks this close = ring
static constexpr uint8_t  MAX_DIAL_PULSES      =  10;   // ten pulses is "0"; eleven is a fault

/* ---- Trunk ring cadence and guards (control.md 8.4, 8.5) ------------------ */
static constexpr uint32_t CADENCE_ON_MS        =  2000;
static constexpr uint32_t CADENCE_OFF_MS       =  4000;
static constexpr uint32_t RING_HARD_TIMEOUT_MS = 30000;  // 8.5, independent of the host
static constexpr uint8_t  MAX_TRUNKS_RINGING   =     4;  // 8.5 starting value, pending
                                                         // the trunk 7.6 measurements.
                                                         // Leaves headroom for one
                                                         // station ring the firmware
                                                         // cannot see coming.

/* ---- MQTT (mqtt.md 4, 8; control.md 9) ------------------------------------ */
static constexpr const char* TOPIC_PREFIX = "sbgame/";
static constexpr uint16_t    MQTT_PORT    = 1883;
static constexpr int         MQTT_KEEPALIVE_S = 5;       // mqtt.md 8.1
static constexpr uint32_t    ESP_HEARTBEAT_MS = 1000;    // 9.3, from the main loop
static constexpr uint32_t    GAME_HEARTBEAT_TIMEOUT_MS = 2000;  // two missed beats
static constexpr uint32_t    STATE_REPUBLISH_MS = 30000; // 9.2 slow timer
static constexpr uint32_t    MQTT_RECONNECT_MIN_MS = 500;
static constexpr uint32_t    MQTT_RECONNECT_MAX_MS = 8000;

/* ---- Expander /RESET (control.md 6.2) ------------------------------------- */
static constexpr uint32_t EXP_RESET_HOLD_MS   = 2;   // "at least 1ms", chosen safe;
                                                     // the datasheet figure is an
                                                     // open item in control.md 11.
static constexpr uint32_t EXP_RESET_SETTLE_MS = 5;

/* How often a bus fault is retried (control.md 10). An absent expander is
 * polled by nobody, so nothing on the bus can report it back: the retry is
 * timed from the main loop instead. One a second, not one per 5ms tick - a
 * recovery costs a 7ms /RESET pulse plus a probe of every configured address,
 * which at 200Hz would be the whole loop budget. One second is also well
 * inside a human's idea of "I plugged it back in and it came up". */
static constexpr uint32_t I2C_RETRY_MS = 1000;

/* How often the retry is allowed to be a /RESET rather than a probe, in the
 * case where nothing at all answers. /RESET is one line to every chip, so it
 * costs a 7ms stall in the 5ms poll and drops every relay; a bus that is
 * wedged has already dropped them, and is not a fault that anything but a
 * human is going to clear, so a slower knock is enough. The probe still runs
 * once a second in between. Ten seconds, chiefly so that a bench board with no
 * expanders fitted does not spend the rest of the session reporting a 7ms
 * longest-poll-gap that has nothing to do with the loop's real timing. */
static constexpr uint32_t I2C_RESET_RETRY_MS = 10000;
