from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Dict, Iterable


@dataclass
class TransitionStoreAdapter:
    mode: str

    @staticmethod
    def _history_retention_months() -> int:
        try:
            return max(1, int(os.getenv("BREAKOUT_V2_HISTORY_RETENTION_MONTHS", "6")))
        except Exception:
            return 6

    def _connect(self):
        try:
            import psycopg2
        except Exception:
            return None
        try:
            return psycopg2.connect(
                host=os.getenv("DB_HOST", "db"),
                port=int(os.getenv("DB_PORT", "5432")),
                user=os.getenv("DB_USER", "fyers_user"),
                password=os.getenv("DB_PASSWORD", "fyers_pass"),
                dbname=os.getenv("DB_NAME", "fyers_db"),
                connect_timeout=2,
            )
        except Exception:
            return None

    @staticmethod
    def _state_meta_for_db(meta: dict | None) -> dict:
        """
        Keep DB state_meta minimal: do not persist session-only live attempt tracking.
        """
        if not isinstance(meta, dict):
            return {}
        drop_keys = {
            "live_attempt_tag",
            "live_attempt_started_at",
            "live_attempt_invalidated_at",
            "live_attempt_status",
            "live_attempt_reason",
        }
        return {k: v for k, v in meta.items() if k not in drop_keys}

    def ensure_tables(self) -> None:
        conn = self._connect()
        if conn is None:
            return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS breakout_v2_live_struct_d_state (
                        symbol TEXT PRIMARY KEY,
                        last_tag_d_structural TEXT NOT NULL DEFAULT '—',
                        live_struct_d_state TEXT NOT NULL DEFAULT '',
                        transition_seq BIGINT NOT NULL DEFAULT 0,
                        last_event_ts TEXT NOT NULL DEFAULT '',
                        last_price_seen DOUBLE PRECISION,
                        state_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS breakout_v2_live_struct_w_state (
                        symbol TEXT PRIMARY KEY,
                        last_tag_w_structural TEXT NOT NULL DEFAULT '—',
                        live_struct_w_state TEXT NOT NULL DEFAULT '',
                        live_struct_w_today_state TEXT NOT NULL DEFAULT '',
                        transition_seq BIGINT NOT NULL DEFAULT 0,
                        last_event_ts_w TEXT NOT NULL DEFAULT '',
                        last_price_seen DOUBLE PRECISION,
                        state_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    ALTER TABLE breakout_v2_live_struct_d_state
                    ADD COLUMN IF NOT EXISTS live_attempt_tag TEXT NOT NULL DEFAULT ''
                    """
                )
                cur.execute(
                    """
                    ALTER TABLE breakout_v2_live_struct_d_state
                    ADD COLUMN IF NOT EXISTS live_attempt_started_at TEXT NOT NULL DEFAULT ''
                    """
                )
                cur.execute(
                    """
                    ALTER TABLE breakout_v2_live_struct_d_state
                    ADD COLUMN IF NOT EXISTS live_attempt_invalidated_at TEXT NOT NULL DEFAULT ''
                    """
                )
                cur.execute(
                    """
                    ALTER TABLE breakout_v2_live_struct_d_state
                    ADD COLUMN IF NOT EXISTS live_attempt_status TEXT NOT NULL DEFAULT ''
                    """
                )
                cur.execute(
                    """
                    ALTER TABLE breakout_v2_live_struct_d_state
                    ADD COLUMN IF NOT EXISTS live_attempt_reason TEXT NOT NULL DEFAULT ''
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS breakout_v2_live_struct_d_history (
                        id BIGSERIAL PRIMARY KEY,
                        symbol TEXT NOT NULL,
                        last_tag_d_structural TEXT NOT NULL DEFAULT '—',
                        live_struct_d_state TEXT NOT NULL DEFAULT '',
                        last_event_ts TEXT NOT NULL DEFAULT '',
                        last_price_seen DOUBLE PRECISION,
                        state_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
                        change_reason TEXT NOT NULL DEFAULT 'state_change',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_breakout_v2_d_hist_symbol_created
                    ON breakout_v2_live_struct_d_history(symbol, created_at DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS breakout_v2_last_tag_d_path_chunks (
                        symbol TEXT NOT NULL,
                        path_seq BIGINT NOT NULL,
                        event_count INT NOT NULL DEFAULT 0,
                        path_string TEXT NOT NULL DEFAULT '',
                        start_ts TEXT NOT NULL DEFAULT '',
                        end_ts TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (symbol, path_seq)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_breakout_v2_last_tag_d_path_chunks_symbol_seq
                    ON breakout_v2_last_tag_d_path_chunks(symbol, path_seq DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS breakout_v2_live_struct_d_eod_path_chunks (
                        symbol TEXT NOT NULL,
                        path_seq BIGINT NOT NULL,
                        event_count INT NOT NULL DEFAULT 0,
                        path_string TEXT NOT NULL DEFAULT '',
                        start_ts TEXT NOT NULL DEFAULT '',
                        end_ts TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (symbol, path_seq)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_breakout_v2_live_struct_d_eod_path_chunks_symbol_seq
                    ON breakout_v2_live_struct_d_eod_path_chunks(symbol, path_seq DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS breakout_v2_live_struct_w_history (
                        id BIGSERIAL PRIMARY KEY,
                        symbol TEXT NOT NULL,
                        last_tag_w_structural TEXT NOT NULL DEFAULT '—',
                        live_struct_w_state TEXT NOT NULL DEFAULT '',
                        live_struct_w_today_state TEXT NOT NULL DEFAULT '',
                        last_event_ts_w TEXT NOT NULL DEFAULT '',
                        last_price_seen DOUBLE PRECISION,
                        change_reason TEXT NOT NULL DEFAULT 'state_change',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_breakout_v2_w_hist_symbol_created
                    ON breakout_v2_live_struct_w_history(symbol, created_at DESC)
                    """
                )
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def load_daily_states(self, symbols: Iterable[str]) -> Dict[str, dict]:
        out: Dict[str, dict] = {}
        syms = [str(s).strip().upper() for s in symbols if str(s).strip()]
        if not syms:
            return out
        conn = self._connect()
        if conn is None:
            return out
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT symbol, last_tag_d_structural, live_struct_d_state, transition_seq, last_event_ts, state_meta
                    FROM breakout_v2_live_struct_d_state
                    WHERE symbol = ANY(%s)
                    """,
                    (syms,),
                )
                for symbol, last_tag, live_struct, seq, last_event_ts, state_meta in cur.fetchall() or []:
                    meta = state_meta or {}
                    out[str(symbol).upper()] = {
                        "last_tag": str(last_tag or "—"),
                        "live_struct_d": str(live_struct or ""),
                        "transition_seq": int(seq or 0),
                        "last_event_dt": str(last_event_ts or ""),
                        "state_meta": meta,
                    }
        except Exception:
            return {}
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return out

    def load_weekly_states(self, symbols: Iterable[str]) -> Dict[str, dict]:
        out: Dict[str, dict] = {}
        syms = [str(s).strip().upper() for s in symbols if str(s).strip()]
        if not syms:
            return out
        conn = self._connect()
        if conn is None:
            return out
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT symbol, last_tag_w_structural, live_struct_w_state, live_struct_w_today_state, transition_seq, last_event_ts_w
                    FROM breakout_v2_live_struct_w_state
                    WHERE symbol = ANY(%s)
                    """,
                    (syms,),
                )
                for symbol, last_tag, live_struct, live_today, seq, last_event_ts in cur.fetchall() or []:
                    out[str(symbol).upper()] = {
                        "last_tag_w": str(last_tag or "—"),
                        "live_struct_w": str(live_struct or ""),
                        "live_struct_w_today": str(live_today or ""),
                        "transition_seq": int(seq or 0),
                        "timing_last_event_dt_w": str(last_event_ts or ""),
                    }
        except Exception:
            return {}
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return out

    def load_last_tag_d_latest_path_chunks(self, symbols: Iterable[str]) -> Dict[str, dict]:
        out: Dict[str, dict] = {}
        syms = [str(s).strip().upper() for s in symbols if str(s).strip()]
        if not syms:
            return out
        conn = self._connect()
        if conn is None:
            return out
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT ON (symbol) symbol, path_seq, event_count, path_string
                    FROM breakout_v2_last_tag_d_path_chunks
                    WHERE symbol = ANY(%s)
                    ORDER BY symbol, path_seq DESC
                    """,
                    (syms,),
                )
                for symbol, path_seq, event_count, path_string in (cur.fetchall() or []):
                    s = str(symbol).upper()
                    path = str(path_string or "").strip()
                    token = ""
                    if path:
                        parts = [x.strip() for x in path.split("->") if x.strip()]
                        if parts:
                            token = parts[-1]
                    out[s] = {
                        "path_seq": int(path_seq or 0),
                        "event_count": int(event_count or 0),
                        "path_string": path,
                        "last_token": token,
                    }
        except Exception:
            return {}
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return out

    def get_daily_last_write_ts(self) -> str:
        conn = self._connect()
        if conn is None:
            return ""
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT MAX(updated_at) FROM breakout_v2_live_struct_d_state")
                row = cur.fetchone()
                if not row:
                    return ""
                val = row[0]
                return str(val) if val is not None else ""
        except Exception:
            return ""
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def upsert_daily_rows(self, rows: Iterable[dict]) -> None:
        try:
            from psycopg2.extras import Json
        except Exception:
            Json = None
        payload = []
        for r in rows:
            sym = str(r.get("symbol", "")).strip().upper()
            if not sym:
                continue
            state_meta_db = self._state_meta_for_db(r.get("_state_meta") or {})
            payload.append(
                (
                    sym,
                    str(r.get("last_tag", "—") or "—"),
                    str(r.get("live_struct_d", "") or ""),
                    str(r.get("last_event_dt", "") or ""),
                    float(r.get("last", 0.0) or 0.0),
                    Json(state_meta_db) if Json is not None else "{}",
                )
            )
        if not payload:
            return
        conn = self._connect()
        if conn is None:
            return
        try:
            with conn.cursor() as cur:
                symbols = [p[0] for p in payload]
                cur.execute(
                    """
                    SELECT symbol, last_tag_d_structural, live_struct_d_state, last_event_ts, state_meta
                    FROM breakout_v2_live_struct_d_state
                    WHERE symbol = ANY(%s)
                    """,
                    (symbols,),
                )
                before = {
                    str(s).upper(): {
                        "last_tag_d_structural": str(t or "—"),
                        "live_struct_d_state": str(ls or ""),
                        "last_event_ts": str(et or ""),
                        "structural_event_key": str((sm or {}).get("structural_event_key", "") if isinstance(sm, dict) else ""),
                    }
                    for s, t, ls, et, sm in (cur.fetchall() or [])
                }

                cur.executemany(
                    """
                    INSERT INTO breakout_v2_live_struct_d_state
                    (symbol, last_tag_d_structural, live_struct_d_state, last_event_ts, last_price_seen, state_meta,
                     transition_seq, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, 1, NOW())
                    ON CONFLICT (symbol) DO UPDATE
                    SET
                        last_tag_d_structural = EXCLUDED.last_tag_d_structural,
                        live_struct_d_state = EXCLUDED.live_struct_d_state,
                        last_event_ts = EXCLUDED.last_event_ts,
                        last_price_seen = EXCLUDED.last_price_seen,
                        state_meta = EXCLUDED.state_meta,
                        transition_seq =
                            CASE
                                WHEN breakout_v2_live_struct_d_state.live_struct_d_state IS DISTINCT FROM EXCLUDED.live_struct_d_state
                                  OR breakout_v2_live_struct_d_state.last_tag_d_structural IS DISTINCT FROM EXCLUDED.last_tag_d_structural
                                THEN breakout_v2_live_struct_d_state.transition_seq + 1
                                ELSE breakout_v2_live_struct_d_state.transition_seq
                            END,
                        updated_at = NOW()
                    """,
                    payload,
                )

                hist_payload = []
                for p in payload:
                    sym, tag, live, evt, last_px, state_meta = p
                    prev = before.get(sym)
                    changed = (
                        prev is None
                        or prev.get("last_tag_d_structural") != tag
                        or prev.get("live_struct_d_state") != live
                        or prev.get("last_event_ts") != evt
                    )
                    if not changed:
                        continue
                    reason = "init" if prev is None else "state_change"
                    hist_payload.append((sym, tag, live, evt, last_px, state_meta, reason))

                if hist_payload:
                    cur.executemany(
                        """
                        INSERT INTO breakout_v2_live_struct_d_history
                        (symbol, last_tag_d_structural, live_struct_d_state, last_event_ts, last_price_seen, state_meta, change_reason, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                        """,
                        hist_payload,
                    )

                cur.execute(
                    """
                    SELECT DISTINCT symbol
                    FROM breakout_v2_last_tag_d_path_chunks
                    WHERE symbol = ANY(%s)
                    """,
                    (symbols,),
                )
                existing_path_symbols = {str(s).upper() for (s,) in (cur.fetchall() or [])}

                # Last Tag D chunked path timeline:
                # - append only when structural tag changes
                # - store 10 events per row, then continue from 11 in next seq row
                for p in payload:
                    sym, tag, _live, evt, _last_px, _state_meta = p
                    if not tag or tag == "—" or not evt:
                        continue
                    prev = before.get(sym)
                    tag_changed = prev is None or prev.get("last_tag_d_structural") != tag
                    needs_init = sym not in existing_path_symbols
                    if (not tag_changed) and (not needs_init):
                        continue
                    token = f"{tag}@{evt}"
                    cur.execute(
                        """
                        SELECT path_seq, event_count, path_string, start_ts, end_ts
                        FROM breakout_v2_last_tag_d_path_chunks
                        WHERE symbol = %s
                        ORDER BY path_seq DESC
                        LIMIT 1
                        FOR UPDATE
                        """,
                        (sym,),
                    )
                    latest = cur.fetchone()
                    if latest is None:
                        cur.execute(
                            """
                            INSERT INTO breakout_v2_last_tag_d_path_chunks
                            (symbol, path_seq, event_count, path_string, start_ts, end_ts, created_at, updated_at)
                            VALUES (%s, 1, 1, %s, %s, %s, NOW(), NOW())
                            """,
                            (sym, token, evt, evt),
                        )
                        continue
                    path_seq, event_count, path_string, start_ts, _end_ts = latest
                    if int(event_count or 0) >= 10:
                        next_seq = int(path_seq or 0) + 1
                        cur.execute(
                            """
                            INSERT INTO breakout_v2_last_tag_d_path_chunks
                            (symbol, path_seq, event_count, path_string, start_ts, end_ts, created_at, updated_at)
                            VALUES (%s, %s, 1, %s, %s, %s, NOW(), NOW())
                            """,
                            (sym, next_seq, token, evt, evt),
                        )
                    else:
                        next_path = f"{str(path_string or '').strip()} -> {token}" if str(path_string or "").strip() else token
                        cur.execute(
                            """
                            UPDATE breakout_v2_last_tag_d_path_chunks
                            SET event_count = %s,
                                path_string = %s,
                                end_ts = %s,
                                updated_at = NOW()
                            WHERE symbol = %s AND path_seq = %s
                            """,
                            (int(event_count or 0) + 1, next_path, evt, sym, int(path_seq or 1)),
                        )

                # Live_struct_d EOD-only chunked path timeline:
                # - append only when structural EOD key advances
                # - token format: LIVE_STRUCT_D@YYYY-MM-DD
                # - 10 events per row, then continue in next seq
                cur.execute(
                    """
                    SELECT DISTINCT symbol
                    FROM breakout_v2_live_struct_d_eod_path_chunks
                    WHERE symbol = ANY(%s)
                    """,
                    (symbols,),
                )
                existing_live_eod_symbols = {str(s).upper() for (s,) in (cur.fetchall() or [])}

                for p in payload:
                    sym, _tag, live, _evt, _last_px, state_meta = p
                    if not live or not isinstance(state_meta, dict):
                        continue
                    eod_key = str(state_meta.get("structural_event_key", "") or "").strip()
                    if not eod_key:
                        continue
                    prev = before.get(sym) or {}
                    prev_eod_key = str(prev.get("structural_event_key", "") or "").strip()
                    eod_advanced = eod_key != prev_eod_key
                    needs_init = sym not in existing_live_eod_symbols
                    if (not eod_advanced) and (not needs_init):
                        continue

                    token = f"{live}@{eod_key}"
                    cur.execute(
                        """
                        SELECT path_seq, event_count, path_string
                        FROM breakout_v2_live_struct_d_eod_path_chunks
                        WHERE symbol = %s
                        ORDER BY path_seq DESC
                        LIMIT 1
                        FOR UPDATE
                        """,
                        (sym,),
                    )
                    latest = cur.fetchone()
                    if latest is None:
                        cur.execute(
                            """
                            INSERT INTO breakout_v2_live_struct_d_eod_path_chunks
                            (symbol, path_seq, event_count, path_string, start_ts, end_ts, created_at, updated_at)
                            VALUES (%s, 1, 1, %s, %s, %s, NOW(), NOW())
                            """,
                            (sym, token, eod_key, eod_key),
                        )
                        continue

                    path_seq, event_count, path_string = latest
                    if int(event_count or 0) >= 10:
                        next_seq = int(path_seq or 0) + 1
                        cur.execute(
                            """
                            INSERT INTO breakout_v2_live_struct_d_eod_path_chunks
                            (symbol, path_seq, event_count, path_string, start_ts, end_ts, created_at, updated_at)
                            VALUES (%s, %s, 1, %s, %s, %s, NOW(), NOW())
                            """,
                            (sym, next_seq, token, eod_key, eod_key),
                        )
                    else:
                        next_path = f"{str(path_string or '').strip()} -> {token}" if str(path_string or "").strip() else token
                        cur.execute(
                            """
                            UPDATE breakout_v2_live_struct_d_eod_path_chunks
                            SET event_count = %s,
                                path_string = %s,
                                end_ts = %s,
                                updated_at = NOW()
                            WHERE symbol = %s AND path_seq = %s
                            """,
                            (int(event_count or 0) + 1, next_path, eod_key, sym, int(path_seq or 1)),
                        )

                retention_months = self._history_retention_months()
                cur.execute(
                    """
                    DELETE FROM breakout_v2_live_struct_d_history
                    WHERE created_at < (NOW() - (%s || ' months')::interval)
                    """,
                    (str(retention_months),),
                )
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def upsert_weekly_rows(self, rows: Iterable[dict]) -> None:
        payload = []
        for r in rows:
            sym = str(r.get("symbol", "")).strip().upper()
            if not sym:
                continue
            payload.append(
                (
                    sym,
                    str(r.get("last_tag_w", "—") or "—"),
                    str(r.get("live_struct_w", "") or ""),
                    str(r.get("live_struct_w_today", "") or ""),
                    str(r.get("timing_last_event_dt_w", "") or ""),
                    float(r.get("last", 0.0) or 0.0),
                )
            )
        if not payload:
            return
        conn = self._connect()
        if conn is None:
            return
        try:
            with conn.cursor() as cur:
                symbols = [p[0] for p in payload]
                cur.execute(
                    """
                    SELECT symbol, last_tag_w_structural, live_struct_w_state, live_struct_w_today_state, last_event_ts_w
                    FROM breakout_v2_live_struct_w_state
                    WHERE symbol = ANY(%s)
                    """,
                    (symbols,),
                )
                before = {
                    str(s).upper(): {
                        "last_tag_w_structural": str(t or "—"),
                        "live_struct_w_state": str(ls or ""),
                        "live_struct_w_today_state": str(lst or ""),
                        "last_event_ts_w": str(et or ""),
                    }
                    for s, t, ls, lst, et in (cur.fetchall() or [])
                }

                cur.executemany(
                    """
                    INSERT INTO breakout_v2_live_struct_w_state
                    (symbol, last_tag_w_structural, live_struct_w_state, live_struct_w_today_state, last_event_ts_w, last_price_seen, transition_seq, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, 1, NOW())
                    ON CONFLICT (symbol) DO UPDATE
                    SET
                        last_tag_w_structural = EXCLUDED.last_tag_w_structural,
                        live_struct_w_state = EXCLUDED.live_struct_w_state,
                        live_struct_w_today_state = EXCLUDED.live_struct_w_today_state,
                        last_event_ts_w = EXCLUDED.last_event_ts_w,
                        last_price_seen = EXCLUDED.last_price_seen,
                        transition_seq =
                            CASE
                                WHEN breakout_v2_live_struct_w_state.live_struct_w_state IS DISTINCT FROM EXCLUDED.live_struct_w_state
                                  OR breakout_v2_live_struct_w_state.live_struct_w_today_state IS DISTINCT FROM EXCLUDED.live_struct_w_today_state
                                  OR breakout_v2_live_struct_w_state.last_tag_w_structural IS DISTINCT FROM EXCLUDED.last_tag_w_structural
                                THEN breakout_v2_live_struct_w_state.transition_seq + 1
                                ELSE breakout_v2_live_struct_w_state.transition_seq
                            END,
                        updated_at = NOW()
                    """,
                    payload,
                )

                hist_payload = []
                for p in payload:
                    sym, tag, live, live_today, evt, last_px = p
                    prev = before.get(sym)
                    changed = (
                        prev is None
                        or prev.get("last_tag_w_structural") != tag
                        or prev.get("live_struct_w_state") != live
                        or prev.get("live_struct_w_today_state") != live_today
                        or prev.get("last_event_ts_w") != evt
                    )
                    if not changed:
                        continue
                    reason = "init" if prev is None else "state_change"
                    hist_payload.append((sym, tag, live, live_today, evt, last_px, reason))

                if hist_payload:
                    cur.executemany(
                        """
                        INSERT INTO breakout_v2_live_struct_w_history
                        (symbol, last_tag_w_structural, live_struct_w_state, live_struct_w_today_state, last_event_ts_w, last_price_seen, change_reason, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                        """,
                        hist_payload,
                    )

                retention_months = self._history_retention_months()
                cur.execute(
                    """
                    DELETE FROM breakout_v2_live_struct_w_history
                    WHERE created_at < (NOW() - (%s || ' months')::interval)
                    """,
                    (str(retention_months),),
                )
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
