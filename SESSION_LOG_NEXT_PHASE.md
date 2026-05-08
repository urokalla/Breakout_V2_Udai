# Session Log - Next Phase Handoff

Date: 2026-05-08

## What Is Completed (Current State)

### Core logic and persistence

- `Last Tag D` structural truth is computed from parquet replay (V2-local structural logic).
- `Live_struct_d` reconciliation/state machine implemented with persistence.
- Durable DB state tables are active.
- Last Tag D path chunk storage implemented:
  - `breakout_v2_last_tag_d_path_chunks`
  - 10 events per row, then continue in next `path_seq`.
- Live EOD path table added:
  - `breakout_v2_live_struct_d_eod_path_chunks`
  - appends only when EOD key advances and live state exists.

### UI improvements on Daily page

- `LIVE_STRUCT_ONLY` filter fixed to use non-empty `live_struct_d`.
- top counters aligned with live-struct semantics.
- `SRC` column added (SHM/DB/API/NA style visibility).
- Daily metric label clarified:
  - `DIST_FROM_REF10% (D)`.
- `PATH` column added for Last Tag D latest chunk:
  - click-to-expand path details (`SEQ`, `CNT`, full chunk).
- mismatch highlighting added for resolved reconcile disagreement.
- ops panel added in daily header:
  - snapshot age
  - DB write timestamp
  - source distribution counts

### Performance work done

- DB persistence writes throttled (`BREAKOUT_V2_PERSIST_EVERY_SEC`).
- parquet read cache added in `HistoryAdapter` (TTL-based in-memory).
- daily OHLCV read window made configurable and reduced default.
- All NSE fast-load cap applied; regular universes uncapped.
  - Nifty 500 now fully loaded again.

## Important Current Config/Behavior

- Regular universes (Nifty50/100/500/etc): full symbol load.
- All NSE universe: capped fast-load mode using:
  - `BREAKOUT_V2_ALL_NSE_MAX_SYMBOLS` (default 40).
- Header displays load ratio (`LOAD loaded/total`) for transparency.

## Known Operational Notes

- Reflex UI must avoid Python boolean checks on `Var` inside `rx.foreach`.
  - use `rx.cond(...)` only.
- Container restart can fail with OCI cwd message in some cases:
  - use `docker start sovereign_dashboard_breakout_v2`.

## Next Workstream Approved by User

User requested:

1. Create architecture/design plan for Dragonfly shadow-mode migration with zero break risk.
2. After this, continue work on Weekly breakout page.

Design document created:

- `DRAGONFLY_SHADOW_MODE_ARCHITECTURE_PLAN.md`

## Weekly Page Work Queue (Next)

1. Review current weekly UI parity gaps vs daily.
2. Decide which daily improvements must be mirrored in weekly:
   - clarity labels
   - source visibility
   - optional path/mismatch/ops elements (weekly-specific semantics only).
3. Implement in weekly page incrementally with no daily regressions.
4. Validate load/perf behavior for weekly universes.

## Guardrails for Next Session

- Do not alter SHM read path as production source unless explicitly approved.
- Do not switch to Dragonfly/Redis read path in this phase.
- Keep Postgres as durable transition/audit store.
- Keep updating session log after each substantial step.

