# stations — station board

Eight station strips per board: `stations.kicad_sch` is the root and places
`station.kicad_sch` eight times. Three identical boards are built, differing only in
the MCP23017 address strap and the A32 D-Sub they land on. That gives 24 strips: 22
stations, then on board 3, strip 7 is the operator tap and strip 8 station 24, a real
telephone.

Written to `docs/station_circuit.md`; drawn to `docs/archive/station_schematic_guide.md`.
