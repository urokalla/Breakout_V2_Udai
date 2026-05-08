# Dragonfly Shadow-Mode Architecture Plan (No Break Risk)

## Objective

Introduce DragonflyDB as a portable, low-latency live bus **without changing current production read path** (SHM remains primary for scanner, main dashboard, breakout dashboard).

## Non-Negotiable Safety Rules

- Do not modify scanner core SHM write path in phase 1.
- Do not switch read path in `RS_PROJECT` or Breakout V2 in phase 1.
- Dragonfly integration runs in parallel (shadow mode).
- Rollback must be immediate by stopping bridge/container only.

## Current Baseline

- Scanner writes live state to SHM mmap.
- Main dashboard reads SHM.
- Breakout V2 reads SHM (primary), DB/API fallback.
- Parquet remains structural truth for `Last Tag D`.
- Postgres remains durable truth for `live_struct_d` state/history.

## Target Phase-1 Architecture (Shadow Only)

1. **Dragonfly service**
   - Added as separate container in existing network.
   - No dependency change in scanner/main/breakout yet.

2. **SHM -> Dragonfly bridge service**
   - Separate process/script (not scanner-core code path).
   - Reads SHM (`scanner_results.mmap` + `symbols_idx_map.json`).
   - Publishes latest per-symbol fields into Dragonfly.

3. **No read-path switch**
   - Main dashboard and Breakout V2 continue SHM reads.
   - Dragonfly is write-only shadow sink in phase 1.

## Suggested Data Model in Dragonfly

- Key: `live:{SYMBOL}` (hash)
  - fields:
    - `ltp`
    - `change_pct`
    - `rs_rating`
    - `mrs`
    - `rv`
    - `status`
    - `ts`
    - `source=shadow_shm_bridge`
- Health:
  - key: `live:heartbeat`
  - value: epoch timestamp of last successful bridge cycle

## Bridge Runtime Behavior

- Poll SHM at fixed interval (e.g. 250ms–1000ms based on load).
- Upsert Dragonfly keys in batched pipeline.
- Log cycle stats:
  - symbols processed
  - write duration
  - errors
  - heartbeat timestamp

## Validation Plan (Monday Live Session)

### Correctness

- Sample symbols (e.g. 20/100/500 buckets):
  - compare SHM vs Dragonfly for:
    - `ltp`, `change_pct`, `rs_rating`, `mrs`, `rv`, `status`, `ts`
- Expected mismatch rate near zero.

### Latency

- Measure p50/p95/p99 read latency from Dragonfly.
- Verify no visible UI degradation vs SHM baseline.

### Stability

- Restart Dragonfly during session:
  - bridge reconnects
  - no scanner/dashboard impact
- Restart bridge:
  - scanner/dashboard unaffected
  - heartbeat resumes

### Resource

- Track bridge CPU/memory overhead.
- Confirm scanner CPU not regressed.

## Phase-2 (Optional, Explicit Approval Required)

- Add feature flags for optional read path:
  - `LIVE_SOURCE=shm|dragonfly`
- First enable in Breakout V2 only.
- Main dashboard remains SHM until parity confidence is high.

## Rollback

- Stop bridge container/service.
- Stop Dragonfly container if needed.
- No app behavior change because read path remains SHM.

## Estimated Effort

- Phase-1 setup (shadow-only): ~1 hour feasible.
- Live validation confidence: market session dependent.
- Read-path switch: separate approved phase.

