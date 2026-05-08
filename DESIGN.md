# Breakout V2 Design and Execution Plan

## 1) Why this exists

This project exists to prevent transition loss and operational breakage caused by in-memory/ephemeral state paths, while keeping one scanner feed and no dual fetch.

## 2) Target behavior

`Breakout Clock Daily/Weekly` must:
- match known parity behavior,
- update live without page refresh,
- survive restart without losing transition history,
- run without runtime dependency on `RS_PROJECT` source tree.

## 3) Current state snapshot (as of this doc)

- V2 UI and live update loop are running.
- Some timing fields are partially overlaid from timing view.
- Runtime still has coupling points to `RS_PROJECT` mounts/imports.
- Transition durability is not yet fully owned by V2.

This means migration is in progress, not complete.

## 4) Final design

### 4.1 Adapters (owned by V2)
- `adapters/history.py`: parquet/history reads.
- `adapters/live_quotes.py`: scanner live contract reads.
- `adapters/symbols.py`: universe membership reads.
- `adapters/transitions.py` (new): durable transition read/write.

### 4.2 Engine
- Stateless computation from:
  - current live quote input,
  - historical bars,
  - prior durable transition state.
- Emits:
  - UI rows,
  - transition state delta to persist.

### 4.3 Durable state schema (minimum)
- key: `(symbol, timeframe)` where timeframe in `{D, W}`
- fields:
  - `last_tag`
  - `live_struct`
  - `live_struct_today` (weekly)
  - `last_event_ts`
  - counters/flags required by transition logic
  - `updated_at`

## 5) Execution phases

### Phase A: Dependency cleanup
1. Remove all imports from `RS_PROJECT` frontend/backend modules.
2. Replace with V2-owned adapters/interfaces.
3. Keep one scanner producer contract only.

### Phase B: Durable transition layer
1. Add transition storage table/files and repository adapter.
2. Write-through on every transition mutation.
3. Implement boot recovery + replay from persisted state.

### Phase C: Parity and correctness
1. Symbol-by-symbol parity checks for:
   - `LAST TAG D/W`
   - `LIVE_STRUCT_*`
   - `WHEN (D/W)`
   - `% since break` metrics.
2. Fix mismatches with deterministic test fixtures.

### Phase D: Independence gate
1. Start V2 with scanner contract + parquet only.
2. Remove `RS_PROJECT` code mount dependency.
3. Validate app still runs if `RS_PROJECT` folder is absent.

## 6) Acceptance criteria

1. One scanner only; no dual fetch from V2.
2. Transition data survives restart with zero reset-loss.
3. No runtime import/mount dependency on `RS_PROJECT` code.
4. Daily/weekly parity checks pass for agreed sample basket.
5. UI updates live without manual refresh.

## 7) Guardrails for implementation

1. Do not add quick fixes that reintroduce memory-only transition authority.
2. Do not couple V2 to sidecar page internals.
3. Do not use temporary JSON as canonical transition store.
4. Keep rollback path simple: feature-flag new transition store until parity passes.

## 8) Immediate next actions

1. Create `adapters/transitions.py` and schema migration.
2. Move transition computation write-path to durable store.
3. Add parity probe script for 20-symbol daily/weekly sample.
4. Remove remaining RS code imports after parity green.

