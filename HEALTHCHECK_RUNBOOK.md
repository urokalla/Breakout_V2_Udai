# Breakout V2 Healthcheck Runbook

Use this when something looks wrong in runtime and you need quick checks.

## 1) Container and snapshot sanity

```bash
docker start sovereign_dashboard_breakout_v2
docker exec -i sovereign_dashboard_breakout_v2 python - <<'PY'
from breakout_v2_app.engine import get_engine
snap = get_engine().snapshot(universe='Nifty 500')
print("symbol_count=", snap.get("symbol_count"))
print("eod_sync=", snap.get("eod_sync"))
PY
```

Expected:

- command succeeds
- `symbol_count` is non-zero
- `eod_sync` is present

## 2) DB write health (state table is updating)

```bash
docker exec -i sovereign_dashboard_breakout_v2 python - <<'PY'
import os, psycopg2
conn = psycopg2.connect(
    host=os.getenv("DB_HOST","db"),
    port=int(os.getenv("DB_PORT","5432")),
    user=os.getenv("DB_USER","fyers_user"),
    password=os.getenv("DB_PASSWORD","fyers_pass"),
    dbname=os.getenv("DB_NAME","fyers_db"),
)
cur = conn.cursor()
cur.execute("""
SELECT COUNT(*) AS rows, COUNT(DISTINCT symbol) AS syms, MAX(updated_at) AS latest
FROM breakout_v2_live_struct_d_state
""")
print(cur.fetchone())
cur.close(); conn.close()
PY
```

Expected:

- row count > 0
- `latest` advances after running snapshot

## 3) Live feed source sanity (SHM first)

```bash
docker exec -i sovereign_dashboard_breakout_v2 python - <<'PY'
from breakout_v2_app.adapters.live_quotes import LiveQuoteAdapter
ad = LiveQuoteAdapter(mode="x")
q = ad.get_quote_map(["RELIANCE","TCS","INFY"])
for s,v in q.items():
    print(s, v.get("source"), v.get("ltp"), v.get("change_pct"), v.get("rs_rating"), v.get("mrs"), v.get("rv"))
PY
```

Expected:

- source should usually be `scanner_shm` in normal same-machine setup
- fallback sources can be `postgres_live_state` / API / placeholder

## 4) Structural truth sanity (`Last Tag D`)

```bash
docker exec -i sovereign_dashboard_breakout_v2 python - <<'PY'
from breakout_v2_app.engine import get_engine
rows = get_engine().snapshot(universe="Nifty 50").get("daily_rows", [])
print("rows=", len(rows))
for r in rows[:10]:
    print(r.get("symbol"), r.get("last_tag"), r.get("last_event_dt"), r.get("last_tag_is_today_event"))
PY
```

Expected:

- `last_tag` populated from parquet structural logic
- `last_event_dt` reflects structural event time

## 5) Live/state comparison sanity

```bash
docker exec -i sovereign_dashboard_breakout_v2 python - <<'PY'
import os, psycopg2
conn = psycopg2.connect(
    host=os.getenv("DB_HOST","db"),
    port=int(os.getenv("DB_PORT","5432")),
    user=os.getenv("DB_USER","fyers_user"),
    password=os.getenv("DB_PASSWORD","fyers_pass"),
    dbname=os.getenv("DB_NAME","fyers_db"),
)
cur = conn.cursor()
cur.execute("""
SELECT symbol, last_tag_d_structural, live_struct_d_state, last_event_ts
FROM breakout_v2_live_struct_d_state
ORDER BY symbol
LIMIT 20
""")
for row in cur.fetchall():
    print(row)
cur.close(); conn.close()
PY
```

## 6) Last Tag D path chunks sanity (10-per-row)

```bash
docker exec -i sovereign_dashboard_breakout_v2 python - <<'PY'
import os, psycopg2
conn = psycopg2.connect(
    host=os.getenv("DB_HOST","db"),
    port=int(os.getenv("DB_PORT","5432")),
    user=os.getenv("DB_USER","fyers_user"),
    password=os.getenv("DB_PASSWORD","fyers_pass"),
    dbname=os.getenv("DB_NAME","fyers_db"),
)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM breakout_v2_last_tag_d_path_chunks")
print("rows=", cur.fetchone()[0])
cur.execute("""
SELECT symbol, path_seq, event_count, path_string
FROM breakout_v2_last_tag_d_path_chunks
ORDER BY symbol, path_seq
LIMIT 10
""")
for row in cur.fetchall():
    print(row)
cur.close(); conn.close()
PY
```

Expected:

- rows present for tracked symbols
- `event_count` <= 10 per row

## 7) Live EOD path chunks sanity (EOD-only live state path)

```bash
docker exec -i sovereign_dashboard_breakout_v2 python - <<'PY'
import os, psycopg2
conn = psycopg2.connect(
    host=os.getenv("DB_HOST","db"),
    port=int(os.getenv("DB_PORT","5432")),
    user=os.getenv("DB_USER","fyers_user"),
    password=os.getenv("DB_PASSWORD","fyers_pass"),
    dbname=os.getenv("DB_NAME","fyers_db"),
)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM breakout_v2_live_struct_d_eod_path_chunks")
print("rows=", cur.fetchone()[0])
cur.execute("""
SELECT symbol, path_seq, event_count, path_string
FROM breakout_v2_live_struct_d_eod_path_chunks
ORDER BY symbol, path_seq
LIMIT 10
""")
for row in cur.fetchall():
    print(row)
cur.close(); conn.close()
PY
```

Notes:

- can be `0` when `live_struct_d_state` is empty/no live session transitions yet
- appends happen only when EOD key advances and live state exists

## 8) Synthetic state-machine test

```bash
docker exec -i sovereign_dashboard_breakout_v2 python /app/breakout_dashboard_v2/test_live_struct_d_synthetic_v2.py
```

Expected:

- all scenarios `PASS`

## 9) Common failure patterns and fast action

- Container restart error (OCI cwd/mount message):
  - Use `docker start sovereign_dashboard_breakout_v2` instead of restart.
- State not updating:
  - run snapshot sanity (#1), then DB write check (#2).
- Wrong/missing live quotes:
  - run live feed sanity (#3), verify source and SHM availability.
- Last Tag D looks stale:
  - run structural sanity (#4) + check `eod_sync` in snapshot.
- Path chunk confusion:
  - verify row/seq/event_count using checks #6 and #7.

## 10) Live Source Flag (V2 only)

Switch V2 to Dragonfly read mode:

```bash
BREAKOUT_V2_LIVE_SOURCE=dragonfly \
docker compose -f "/Users/udairokalla/breakout_dashboard_v2_repo/docker-compose.breakout-v2.yml" \
  up -d --force-recreate dashboard_breakout_v2
```

Rollback to SHM read mode (default/safe):

```bash
BREAKOUT_V2_LIVE_SOURCE=shm \
docker compose -f "/Users/udairokalla/breakout_dashboard_v2_repo/docker-compose.breakout-v2.yml" \
  up -d --force-recreate dashboard_breakout_v2
```

Notes:

- `BREAKOUT_V2_LIVE_SOURCE` accepted values: `shm`, `dragonfly`
- default is `shm`
- in `dragonfly` mode, adapter still falls back to SHM if dragonfly data is missing

Parity check command:

```bash
docker exec -i sovereign_dashboard_breakout_v2 \
  python /app/breakout_dashboard_v2/scripts/validate_dragonfly_parity.py
```

