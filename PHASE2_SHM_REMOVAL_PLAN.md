# Phase 2: Remove SHM Dependency (Breakout V2)

## Current status (Phase 1 complete)

- Separate repo/folder exists outside `RS_PROJECT`
- Separate service runs on `http://localhost:3002`
- Current code still imports breakout modules that read scanner SHM path indirectly

## Goal

Make breakout v2 work without `scanner_shm` / SHM bridge dependency.

## Constraints

- Do not modify runtime behavior of current `RS_PROJECT`
- Keep breakout v2 changes isolated to this repo
- Keep parquet + DB as primary data layers

## Implementation steps

1. Create a local adapter layer in `breakout_dashboard_v2`:
   - `adapters/live_quotes.py`
   - `adapters/history.py`
   - `adapters/symbols.py`
2. Add `DATA_MODE` switch:
   - `DATA_MODE=storage_only` (target)
   - optional fallback: `DATA_MODE=legacy_bridge` during migration
3. Build a v2 engine that uses adapters only:
   - compute rows from parquet + DB + optional cached quote endpoint
   - no SHM imports
4. Rewire v2 states/pages to use v2 engine routes only.
5. Add parity checks against legacy breakout outputs for sample symbols.
6. Cut over default mode to `storage_only`.

## Acceptance checks

- `rg "scanner_shm|SHMBridge" breakout_dashboard_v2` returns no runtime usage in v2 engine path
- v2 dashboard loads on `3002` with daily/weekly timing pages
- universe switch works without touching main dashboard process
- CPU remains bounded under configured polling

