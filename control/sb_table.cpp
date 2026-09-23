/* =============================================================================
 * sb_table.cpp - the channel table, and the accessors that hide the bit maths
 * ========================================================================== */

#include "sb_table.h"

/* Expander 2 (0x22) carries stations 17-22 on bits 0-5; bit 6 is the operator
 * tap and bit 7 the audience monitor output, neither of which has a row.
 * 0x24-0x27 are reserved for optional second expanders that are not fitted
 * (control.md 6.1) and so have no rows. */
const ExpanderMap expanders[N_EXPANDERS] = {
  { 0x20, "station board 1 (st 1-8)",   0 },
  { 0x21, "station board 2 (st 9-16)",  1 },
  { 0x22, "station board 3 (st 17-22 + tap + monitor)", 2 },
  { 0x23, "trunk board (tr 1-8)",      -1 },
};

/* Every circuit in the design, whether or not its board is fitted. Rows whose
 * expander is unconfigured are inert: not scanned, not polled, not published,
 * and commands for them are dropped. Keeping them in the table means fitting a
 * board is a one-constant change.
 *
 * Station n lives on board (n-1)/8 at bit (n-1)%8; trunk n on 0x23 at bit n-1.
 * Written out rather than computed so the table can be read against control.md
 * 6.1 line by line, and so a future board that breaks the pattern - a spare
 * expander, a circuit moved to a different bit - is a one-row edit. */
const CircuitMap circuits[N_CIRCUITS] = {
  /* kind           num  exp  bit */
  { Kind::Station,   1,   0,   0 },
  { Kind::Station,   2,   0,   1 },
  { Kind::Station,   3,   0,   2 },
  { Kind::Station,   4,   0,   3 },
  { Kind::Station,   5,   0,   4 },
  { Kind::Station,   6,   0,   5 },
  { Kind::Station,   7,   0,   6 },
  { Kind::Station,   8,   0,   7 },
  { Kind::Station,   9,   1,   0 },
  { Kind::Station,  10,   1,   1 },
  { Kind::Station,  11,   1,   2 },
  { Kind::Station,  12,   1,   3 },
  { Kind::Station,  13,   1,   4 },
  { Kind::Station,  14,   1,   5 },
  { Kind::Station,  15,   1,   6 },
  { Kind::Station,  16,   1,   7 },
  { Kind::Station,  17,   2,   0 },
  { Kind::Station,  18,   2,   1 },
  { Kind::Station,  19,   2,   2 },
  { Kind::Station,  20,   2,   3 },
  { Kind::Station,  21,   2,   4 },
  { Kind::Station,  22,   2,   5 },
  /* 0x22 bits 6 and 7 are not stations and have no rows: bit 6 is the operator
   * tap strip and bit 7 is the strip whose A32 output feeds the audience
   * loudspeaker (station Rev 3.40, control.md 6.1). Neither has a relay or a
   * ring detector fitted, so nothing polls them, nothing publishes them and no
   * command can reach them - control.md 6.1 adopts this as its statement of
   * "leave the mapping alone". The shadow leaves both bits 0 for the life of
   * the run. The tap was bit 7 until Rev 3.40 moved it down one strip to free
   * that channel for the monitor. */
  { Kind::Trunk,     1,   3,   0 },
  { Kind::Trunk,     2,   3,   1 },
  { Kind::Trunk,     3,   3,   2 },
  { Kind::Trunk,     4,   3,   3 },
  { Kind::Trunk,     5,   3,   4 },
  { Kind::Trunk,     6,   3,   5 },
  { Kind::Trunk,     7,   3,   6 },
  { Kind::Trunk,     8,   3,   7 },
};

ExpanderState exp_state[N_EXPANDERS];

bool expanderConfigured(uint8_t exp_index) {
  if (exp_index >= N_EXPANDERS) return false;
  const int8_t board = expanders[exp_index].station_board;
  if (board < 0) return true;                       // the trunk board is always fitted
  return board < (int8_t)STATION_BOARDS_FITTED;
}

const CircuitMap* stationCircuit(uint8_t n) {
  if (n < 1 || n > N_STATIONS) return nullptr;
  return &circuits[n - 1];                          // stations occupy rows 0..22
}

const CircuitMap* trunkCircuit(uint8_t n) {
  if (n < 1 || n > N_TRUNKS) return nullptr;
  return &circuits[N_STATIONS + n - 1];             // trunks occupy rows 23..30
}

bool circuitLive(const CircuitMap& c) {
  return expanderConfigured(c.exp) && exp_state[c.exp].present;
}

bool circuitInput(const CircuitMap& c) {
  return (exp_state[c.exp].inputs >> c.bit) & 1;
}

void circuitSetRelay(const CircuitMap& c, bool on) {
  ExpanderState& e = exp_state[c.exp];
  const uint8_t mask = (uint8_t)(1u << c.bit);
  const uint8_t want = on ? (uint8_t)(e.relay_shadow | mask)
                          : (uint8_t)(e.relay_shadow & (uint8_t)~mask);
  if (want != e.relay_shadow) {
    e.relay_shadow = want;
    e.relay_dirty  = true;
  }
}

bool circuitRelay(const CircuitMap& c) {
  return (exp_state[c.exp].relay_shadow >> c.bit) & 1;
}

void circuitId(const CircuitMap& c, char* out, size_t n) {
  snprintf(out, n, "%s/%u", c.kind == Kind::Station ? "station" : "trunk",
           (unsigned)c.number);
}
