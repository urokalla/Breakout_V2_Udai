# Breakout V2 Architecture (Authoritative)

## 1) Objective

Build `breakout_dashboard_v2` as an independent dashboard service that can survive even if `RS_PROJECT` code is removed, while still using a single market scanner process (Fyers does not allow dual fetch).

## 2) Non-negotiable constraints

1. Exactly one live scanner process owns Fyers connectivity.
2. V2 is consumer-only; it never opens its own market feed.
3. V2 must not depend on `RS_PROJECT` source code at runtime.
4. Transition state (`LAST TAG`, `LIVE_STRUCT`, timing transitions) must be durable, not memory-only.
5. Deleting temporary JSON/memory state must not erase transition history.

## 3) System boundaries

### 3.1 Scanner service (single producer)
- Owns websocket/feed connection and live calculations.
- Publishes normalized live payload through stable contract(s):
  - `scanner_live_quotes` (symbol, ltp, change_pct, rs_rating, mrs, rv, status, tick_ts)
  - optional event stream for transition updates.

### 3.2 Breakout V2 service (consumer)
- Reads:
  - historical parquet data,
  - scanner live contract output,
  - durable transition store.
- Computes breakout/timing UI rows from parquet baseline + live stream updates.
- Never relies on SHM as source-of-truth for transition durability.

### 3.3 Durable transition store
- Stores per-symbol/per-timeframe transition state:
  - `last_tag_d`, `last_tag_w`,
  - `live_struct_d`, `live_struct_w`, `live_struct_w_today`,
  - event timestamps and counters needed to continue state machine after restart.
- Supports restart recovery and deterministic replay.

## 4) Data-plane model

Inputs:
- historical OHLCV parquet (read-only),
- scanner live quote contract (single producer),
- previous durable transition snapshot.

Outputs:
- daily/weekly breakout clock rows,
- transition state updates persisted every cycle/event.

## 5) Independence definition

V2 is considered independent only when all are true:
- no imports from `RS_PROJECT` Python packages,
- no bind-mount dependency on `RS_PROJECT` code tree,
- scanner consumed through explicit contract endpoint/table/stream only,
- v2 starts and serves with `RS_PROJECT` folder absent.

## 6) Reliability rules

1. No in-memory-only transition authority.
2. Every transition mutation is persisted transactionally.
3. On start, V2 reconstructs state from durable store + parquet replay window.
4. If live feed is stale, UI must show explicit `LIVE_FEED_STALE`, not silent READY.

## 7) Performance rules

1. Maintain low-latency update loop (sub-second to 1s configurable).
2. Keep page cap (currently 30) configurable and temporary for rollout safety.
3. Keep scanner producer unaffected by V2 consumer load.

## 8) Out of scope

- Any second scanner instance.
- Any direct Fyers calls from V2.
- Any dependency on sidecar page state.

