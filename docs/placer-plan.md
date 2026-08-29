# Transistor placer v1

General CDL/SPICE netlist → multi-row symbolic stdcell layout.

## CLI / API

```
place --cdl cell.cdl --rows 4 --pattern NPPN
place --cdl cell.cdl --rows 2 --pattern PN
```

- `--rows` is diffusion-row count. `--pattern` is a string over `{N,P}` whose length equals `--rows`.
- `NPPN`: N, P, P, N (shared n-well on the two P rows).
- `PNNP`: P, N, N, P (shared p-well on the two N rows).
- `PN` / `NP`: classic 2-row digital cell.
- Rails are derived: VDD next to P rows, VSS next to N rows.
- Reject the run if the netlist has an NMOS and the pattern has no `N` (same for PMOS / `P`).

## IR

Device: name, type (N|P), gate, source, drain, bulk, W, L.
Netlist: devices, named pins, power nets (VDD/VSS by convention, override later).
Layout skeleton: `rows[i].dtype` from the pattern.

## Search space (SAT / CP-SAT)

Each transistor gets:
- a compatible row (N-device → N-row, P-device → P-row)
- a column (shared grid across all rows)
- source-drain orientation (flip)

At most one device per (row, column). Empty sites are dummies or diffusion breaks.

Same-gate devices in different rows prefer the same column (shared poly).
Adjacent same-row devices share diffusion if the touching terminals are the same net; otherwise a break column is inserted (width cost).

v1 does not fold. One finger per device. Folding is v1.1.

## Cost

Minimize cell width = column count × poly pitch.
Height is fixed by `n_rows` and the tech grid (well-share between adjacent same-type rows).

Secondary (soft): misaligned same-net gates, long internal diffusion jumps.

## Output (symbolic, not GDS)

JSON + an ASCII/SVG stick diagram:
- grid of sites
- device, dummy, or gap per site
- net names on diffusion ends and poly
- rails

## Test ladder (any netlist, several patterns)

1. INV_X1 on `PN` and `NP`
2. NAND2_X1 on `PN`
3. lone TG on `PN` (unpaired N/P gates)
4. SDFFQ_X1 on `PN`, `NPPN`, `PNNP`

Baseline: dump devices left-to-right with no sharing. The SAT result must be strictly narrower on the flop.

## Phases

1. CDL parser + IR + pattern validation
2. Constructive baseline (type → row round-robin, no SAT) so the renderer has something to draw
3. CP-SAT placer (row, column, flip)
4. Stick renderer + width score
5. Tests above
