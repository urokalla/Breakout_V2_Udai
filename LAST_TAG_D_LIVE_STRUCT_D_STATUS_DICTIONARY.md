# Last Tag D / Live_struct_d Status Dictionary

This file documents the currently supported status patterns used by Breakout V2.

## Last Tag D (structural truth, EOD/parquet)

`Last Tag D` is computed from parquet structural replay and is treated as EOD truth.

Possible patterns:

- `B<n>`
  - Examples: `B1`, `B2`, `B6`
- `B<n>+E9CT`
  - Example: `B2+E9CT`
- `E9CT<n>`
  - Examples: `E9CT1`, `E9CT5`, `E9CT10`
- `ET9DNWF21C`
- `E21C<n>`
  - Examples: `E21C1`, `E21C2`
- `RST`
- `—` (no valid structural state)

Notes:

- `Last Tag D` updates when structural EOD/parquet truth advances.
- If structural truth does not change, `Last Tag D` remains unchanged.

## Live_struct_d (live/intraday + EOD reconciliation)

`Live_struct_d` is computed from live quote input plus structural truth and prior state.

Possible patterns:

- Empty state:
  - `""` (UI shows this as `—`)

- B-stage intraday:
  - `B<n>_LIVE_WATCH`
  - `B<n>_NO_MORE_VALID`

- E-stage intraday:
  - `E9CT<n>_LIVE_WATCH`
  - `E9CT<n>_NO_MORE_VALID`
  - `ET9DNWF21C_LIVE_WATCH`
  - `ET9DNWF21C_NO_MORE_VALID`
  - `E21C<n>_LIVE_WATCH`
  - `E21C<n>_NO_MORE_VALID`

- RST intraday:
  - `RST_LIVE`

- EOD reconciliation outcomes:
  - `<attempt>_CONFIRMED`
    - Examples: `B2_CONFIRMED`, `E9CT1_CONFIRMED`
  - `<tag>_CONFIRMED(<attempt>_FAILED)`
    - Example: `ET9DNWF21C_CONFIRMED(B2_FAILED)`
  - `<attempt>_FAILED`

## Compare semantics

Per symbol:

- Structural truth: `last_tag_d_structural`
- Live/reconciled state: `live_struct_d_state`

Direct comparison is done per symbol row in:

- `breakout_v2_live_struct_d_state`

