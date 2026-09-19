/* =============================================================================
 * sb_table.h - the channel table
 *
 * Twenty-three stations and eight trunks differ only in which expander bit
 * they live on and which of two behaviours they follow. Everything else about
 * them is identical, so they are described by a table rather than by code: one
 * row per circuit, 31 rows, and every loop in the firmware walks the table.
 * Fitting or removing a station board is a change to STATION_BOARDS_FITTED and
 * nothing else. The operator tap bit has no row (control.md 6.1).
 *
 * control.md 6.1 for the port assignments:
 *   Station board  Port A = RING_DET_1..8   Port B = OFFHOOK_1..8
 *   Trunk board    Port A = SEIZE_1..8      Port B = RING_EN_1..8
 *
 * A circuit's input and its relay share a bit index, which is why one `bit`
 * field serves both ports.
 * ========================================================================== */

#pragma once

#include <Arduino.h>
#include "sb_config.h"

enum class Kind : uint8_t { Station, Trunk };

/* ---- Immutable topology ------------------------------------------------- */

struct ExpanderMap {
  uint8_t     addr;           // 7-bit I2C address
  const char* label;          // for the log
  int8_t      station_board;  // 0,1,2 = that station board; -1 = the trunk board
};

struct CircuitMap {
  Kind    kind;
  uint8_t number;   // 1-23 for stations, 1-8 for trunks - the number on the wire
  uint8_t exp;      // index into expanders[]
  uint8_t bit;      // 0-7, in Port A (input) and Port B (relay) alike
};

static constexpr uint8_t N_EXPANDERS = 4;                    // 0x20-0x23
static constexpr uint8_t N_CIRCUITS  = N_STATIONS + N_TRUNKS; // 31 rows

extern const ExpanderMap expanders[N_EXPANDERS];
extern const CircuitMap  circuits[N_CIRCUITS];

/* An expander is *configured* if this build expects it to exist at all, which
 * for a station board means the board is fitted. Distinct from *present*, which
 * means it answered the scan. control.md 4.2 step 5. */
bool expanderConfigured(uint8_t exp_index);

/* ---- Mutable state, one row per expander -------------------------------- */

struct ExpanderState {
  bool    present;       // answered the scan and has not faulted since
  uint8_t inputs;        // last Port A read, 1 = ring or seizure present
  uint8_t relay_shadow;  // what Port B should be; written when dirty
  bool    relay_dirty;
};

extern ExpanderState exp_state[N_EXPANDERS];

/* ---- Lookups ------------------------------------------------------------ */

const CircuitMap* stationCircuit(uint8_t n);   // n = 1-23, nullptr if out of range
const CircuitMap* trunkCircuit(uint8_t n);     // n = 1-8

/* True when this circuit's expander answered the scan. Commands for a circuit
 * whose expander is absent are logged and dropped (control.md 9.4), and state is
 * not published for one whose value the firmware cannot know. */
bool circuitLive(const CircuitMap& c);

/* Reads this circuit's debounced input bit out of the last poll. */
bool circuitInput(const CircuitMap& c);

/* Sets or clears this circuit's relay bit in the shadow. The write happens in
 * expanderFlushRelays(); nothing here touches the bus. */
void circuitSetRelay(const CircuitMap& c, bool on);
bool circuitRelay(const CircuitMap& c);

/* The circuit id of mqtt.md 3 and 7: "station/<n>" or "trunk/<n>". Prefixing it
 * with "sbgame/" gives that circuit's topic root, which is why it is formatted
 * in one place. */
void circuitId(const CircuitMap& c, char* out, size_t n);
