# Daily and Weekly Transition Design (Breakout V2)

## 1) Purpose

Define a deterministic, durable transition system for:
- `LAST TAG D` + `LIVE_STRUCT_D`
- `LAST TAG W` + `LIVE_STRUCT_W` / `LIVE_STRUCT_W_TODAY`

This document is the execution contract for replacing fragile memory/json behavior.

## 2) Scope and constraints

### In scope
- Transition state semantics for daily and weekly clocks.
- Durable persistence for per-symbol transition state.
- Startup recovery and reconciliation rules.
- Poll/update flow from scanner live feed + parquet structural truth.

### Out of scope
- Pine bar-confirmed parity as primary authority.
- Dual scanner/fetch architecture.
- Changes to `RS_PROJECT` files.

### Hard constraints
1. One scanner process only.
2. V2 is consumer-only.
3. Structural truth comes from parquet/EOD flow.
4. Live transition state must be durable (DB), not memory-only.

## 3) Core truth model

## 3.1 Daily
- `LAST TAG D` is **structural truth**.
- It updates from daily parquet truth cycle (post EOD sync window).
- It does **not** intraday-churn with every tick.

- `LIVE_STRUCT_D` is **intraday live transition state**.
- It captures current live progression against structural baseline.
- Once set for a symbol, it remains non-empty until a valid next transition/reconcile event.

## 3.2 Weekly
- `LAST TAG W` is weekly structural truth.
- `LIVE_STRUCT_W` tracks weekly live transition progression.
- `LIVE_STRUCT_W_TODAY` can represent in-session weekly watch/transition substate.
- Weekly transitions persist and must not reset due to process restart or ephemeral cache loss.

## 4) Known failure modes from legacy behavior

1. In-memory transition authority caused state loss on restart.
2. JSON/temp state deletion reset non-empty transition columns.
3. Weekly live transition state sometimes dropped to empty unexpectedly.
4. Transition persistence logic had inconsistent write ordering and reconciliation timing.

This design removes these failure modes by making DB durable state canonical for live transitions.

## 5) Data inputs and ownership

Inputs:
1. Scanner live feed contract (single producer output; fast tick fields).
2. Structural truth snapshots derived from parquet/EOD logic.
3. Existing durable transition state rows from prior cycles.

Ownership:
- Scanner owns market feed ingestion.
- V2 owns transition persistence and UI rendering from these contracts.

## 6) Persistence schema (v2-owned tables)

## 6.1 Daily transition table
Suggested table: `breakout_v2_live_struct_d_state`

Columns:
- `symbol` (PK)
- `last_tag_d_structural` (text)
- `live_struct_d_state` (text)
- `transition_seq` (bigint)
- `last_event_ts` (timestamptz)
- `last_price_seen` (double precision)
- `state_meta` (jsonb)
- `created_at` (timestamptz default now)
- `updated_at` (timestamptz default now)

## 6.2 Weekly transition table
Suggested table: `breakout_v2_live_struct_w_state`

Columns:
- `symbol` (PK)
- `last_tag_w_structural` (text)
- `live_struct_w_state` (text)
- `live_struct_w_today_state` (text)
- `transition_seq` (bigint)
- `last_event_ts_w` (timestamptz)
- `last_price_seen` (double precision)
- `state_meta` (jsonb)
- `created_at` (timestamptz default now)
- `updated_at` (timestamptz default now)

## 7) Update algorithm

Per poll/tick cycle, for each symbol:

1. Read structural baseline (`LAST TAG D/W`) from structural source.
2. Read current durable live transition row from DB.
3. Read current live quote context from scanner output contract.
4. Compute next transition state with deterministic state machine rules.
5. If state changed:
   - increment `transition_seq`
   - write new state row (upsert)
   - update event timestamps/price snapshot.
6. Render UI from:
   - structural tag columns (truth)
   - durable live transition columns (live truth)
   - market fields (price/chg/rs/rv/mrs).

## 8) Startup/recovery behavior

On service startup:
1. Load all existing transition rows into working cache (optional perf cache).
2. Do not wipe/clear transition tables.
3. Reconcile any structural-tag drift:
   - if structural tag changed due to EOD, apply defined transition reconciliation (not hard reset to empty unless rule says so).
4. Resume live updates and persist deltas.

## 9) Reset and reconciliation policy

Allowed reset conditions (explicit only):
1. Structural cycle indicates canonical reset transition state.
2. Symbol removed from universe for a configured retention window (soft-retain first).
3. Manual operator command with audit flag.

Not allowed:
- process restart reset,
- deleted temp files reset,
- missing in-memory cache reset.

## 10) Daily/Weekly parity requirements

Daily must preserve:
- `LAST TAG D` structural semantics,
- `LIVE_STRUCT_D` persistence and progression.

Weekly must preserve:
- `LAST TAG W` structural semantics,
- `LIVE_STRUCT_W` and `LIVE_STRUCT_W_TODAY` continuity.

Acceptance:
- Non-empty live transition columns do not collapse after restart.
- Weekly non-empty progression is stable across sessions.
- Symbol-level transitions match expected state machine progression.

## 11) Pine script note

Pine is bar-confirmed oriented and is not the direct runtime authority for this transition system.
V2 runtime transition authority is:
- structural truth (parquet/EOD path) + scanner live feed + durable transition store.

Pine can be used as reference for sanity checks, not as canonical intraday state persistence source.

## 12) Execution phases

Phase 1:
- Create daily/weekly transition tables and repository layer.

Phase 2:
- Wire state machine write-through on every transition change.

Phase 3:
- Replace memory/json-ledger path with DB-backed transition authority.

Phase 4:
- Run parity validation on sample basket (daily + weekly).

Phase 5:
- Run restart test: stop/start service, verify non-empty columns remain and continue transitioning.

## 13) Test checklist

1. Intraday transition appears for a symbol and remains non-empty across polls.
2. Service restart does not clear `LIVE_STRUCT_D/W`.
3. Weekly live states continue from persisted sequence after restart.
4. EOD structural update reconciles correctly without destructive wipe.
5. No dependency on temp JSON for transition continuity.

