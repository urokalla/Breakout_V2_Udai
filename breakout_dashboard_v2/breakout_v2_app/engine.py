from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional
import json
import os
import threading
import time

from .adapters import HistoryAdapter, LiveQuoteAdapter, SymbolsAdapter, TransitionStoreAdapter
from .config import DATA_MODE, PIPELINE_DATA_DIR
from .logic import compute_live_struct_d, compute_structural_last_tag_d

# Same-universe snapshot reuse (production: burst refresh / poll storm).
_SNAPSHOT_CACHE_BY_UNIVERSE: dict[str, tuple[float, dict[str, object]]] = {}
_SNAPSHOT_CACHE_GUARD = threading.Lock()
_SNAPSHOT_BUILD_SERIAL = threading.Lock()


def _snapshot_cache_ttl_sec() -> float:
    try:
        v = float(os.getenv("BREAKOUT_V2_SNAPSHOT_CACHE_SEC", "0"))
    except Exception:
        v = 0.0
    if v <= 0.0:
        return 0.0
    return min(v, 30.0)


def _clone_snapshot_payload(data: dict[str, object]) -> dict[str, object]:
    out = dict(data)
    out["daily_rows"] = list(data.get("daily_rows") or [])
    out["weekly_rows"] = list(data.get("weekly_rows") or [])
    out["strategy_rows"] = list(data.get("strategy_rows") or [])
    phases = data.get("_debug_snapshot_phases_ms")
    if isinstance(phases, dict):
        out["_debug_snapshot_phases_ms"] = dict(phases)
    else:
        out.pop("_debug_snapshot_phases_ms", None)
    return out


@dataclass
class V2Engine:
    mode: str
    symbols: SymbolsAdapter
    history: HistoryAdapter
    live_quotes: LiveQuoteAdapter
    transitions: TransitionStoreAdapter
    _last_persist_ts: float = 0.0

    @classmethod
    def build(cls) -> "V2Engine":
        mode = DATA_MODE
        return cls(
            mode=mode,
            symbols=SymbolsAdapter(mode=mode),
            history=HistoryAdapter(mode=mode, pipeline_data_dir=PIPELINE_DATA_DIR),
            live_quotes=LiveQuoteAdapter(mode=mode),
            transitions=TransitionStoreAdapter(mode=mode),
        )

    @staticmethod
    def _breakout_flag(closes: list[float], lookback: int) -> tuple[bool, float, float]:
        if len(closes) < lookback + 1:
            return (False, 0.0, 0.0)
        last_close = closes[-1]
        ref = max(closes[-(lookback + 1) : -1])
        return (last_close > ref, float(last_close), float(ref))

    @staticmethod
    def _norm_symbol(sym: str) -> str:
        s = str(sym or "").strip().upper()
        if s.startswith("NSE:"):
            s = s[4:]
        if "-" in s:
            s = s.split("-", 1)[0]
        return s

    @staticmethod
    def _daily_eod_event_key_from_ohlcv(ohlcv: list[dict]) -> str:
        if not ohlcv:
            return "-"
        last = ohlcv[-1] if isinstance(ohlcv[-1], dict) else {}
        ts_raw = last.get("ts")
        if ts_raw is None:
            return "-"
        try:
            ts = float(ts_raw)
            if ts <= 0:
                return "-"
            # Use UTC day key derived from EOD parquet timestamp.
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            return "-"

    @staticmethod
    def _timing_overlay(universe: str, clock_timeframe: str, page_size: int = 400) -> dict[str, dict]:
        # V2 independence: no legacy timing overlay imports.
        # Durable DB transition rows are used as the fallback overlay source.
        return {}

    @staticmethod
    def _snapshot_parallel_enabled(n_symbols: int) -> bool:
        if str(os.getenv("BREAKOUT_V2_SNAPSHOT_PARALLEL", "1")).strip().lower() not in ("1", "true", "yes"):
            return False
        return n_symbols >= 32

    @staticmethod
    def _snapshot_max_workers() -> int:
        try:
            return max(2, min(int(os.getenv("BREAKOUT_V2_SNAPSHOT_WORKERS", "8")), 24))
        except Exception:
            return 8

    @staticmethod
    def _snapshot_phase_debug_enabled() -> bool:
        """Same flag as UI `[breakout_v2_dbg]` — adds per-phase ms on the snapshot dict."""
        return str(os.getenv("BREAKOUT_V2_DEBUG_TIMING", "") or "").strip().lower() in ("1", "true", "yes")

    def _build_daily_row_from_ohlcv(
        self,
        sym: str,
        ohlcv: list[dict],
        quote_map: dict,
        timing_daily: dict[str, dict],
        persisted_daily: dict[str, dict],
        last_tag_path_chunks: dict[str, dict],
    ) -> Optional[dict]:
        if not ohlcv:
            return None
        closes = [x["close"] for x in ohlcv[-120:] if "close" in x]
        if not closes:
            return None
        last_close = float(closes[-1])
        ref = float(max(closes[-11:-1])) if len(closes) >= 11 else float(closes[-1])
        q = quote_map.get(sym) or {}
        q_ltp = q.get("ltp")
        try:
            last_live = float(q_ltp) if q_ltp is not None else float(last_close)
        except Exception:
            last_live = float(last_close)
        prev = closes[-2] if len(closes) > 1 else closes[-1]
        chp = ((last_live / prev) - 1.0) * 100.0 if prev else 0.0
        pct_live = ((last_live / ref) - 1.0) * 100.0 if ref else 0.0
        when_d = str(ohlcv[-1].get("ts", "—"))
        structural_event_key = self._daily_eod_event_key_from_ohlcv(ohlcv)
        tag = "—"
        s_tag, s_when, s_event_key = compute_structural_last_tag_d(ohlcv, don_len=10)
        if s_tag != "—":
            tag = s_tag
            when_d = s_when
        if s_event_key not in ("", "-"):
            structural_event_key = s_event_key
        is_breakout = str(tag).upper().startswith("B")
        overlay = timing_daily.get(sym, {})
        if overlay:
            try:
                pct_live = float(overlay.get("brk_move_live_pct", pct_live))
            except Exception:
                pass
        prev_state = persisted_daily.get(sym, {}) if persisted_daily else {}
        live_struct_d, state_meta = compute_live_struct_d(
            structural_last_tag_d=tag,
            structural_event_key=structural_event_key,
            ltp=last_live,
            quote_ts=float(q.get("ts", 0.0) or 0.0),
            ohlcv_series=ohlcv,
            prev_state={
                "last_tag_d_structural": (
                    prev_state.get("state_meta", {}).get("last_tag_d_structural")
                    if isinstance(prev_state.get("state_meta"), dict)
                    else prev_state.get("last_tag")
                ),
                "structural_event_key": (
                    prev_state.get("state_meta", {}).get("structural_event_key")
                    if isinstance(prev_state.get("state_meta"), dict)
                    else prev_state.get("last_event_dt")
                ),
                "live_struct_d": prev_state.get("live_struct_d", ""),
                **(prev_state.get("state_meta", {}) if isinstance(prev_state.get("state_meta"), dict) else {}),
            },
        )
        log_path = str(os.getenv("BREAKOUT_V2_RECONCILE_SYMPTOM_LOG", "") or "").strip()
        rs = (state_meta or {}).get("reconcile_symptom") if isinstance(state_meta, dict) else None
        if log_path and isinstance(rs, dict):
            line = json.dumps({"symbol": sym, **rs}, ensure_ascii=False) + "\n"
            try:
                with open(log_path, "a", encoding="utf-8") as fp:
                    fp.write(line)
            except OSError:
                pass
        return {
            "symbol": sym,
            "bars": len(closes),
            "last": round(last_live, 2),
            "ref": round(ref, 2),
            "is_breakout": is_breakout,
            "has_quote": bool(q),
            "last_tag": tag,
            "last_event_dt": when_d,
            "structural_event_key": str(structural_event_key or "").strip(),
            "last_tag_is_today_event": bool(str(when_d)[:10] == str(structural_event_key)),
            "brk_move_live_pct": round(pct_live, 2),
            "live_struct_d": live_struct_d,
            "live_struct_track_day": str((state_meta or {}).get("live_attempt_started_at", "") or "")[:10],
            "live_struct_attempt_status": str((state_meta or {}).get("live_attempt_status", "") or ""),
            "chp": round(chp, 2),
            "rs_rating": int(q.get("rs_rating") or 0),
            "mrs": float(q.get("mrs") or 0.0),
            "rv": float(q.get("rv") or 0.0),
            "status": str(q.get("status") or ""),
            "quote_source": str(q.get("source") or ""),
            "quote_ts": float(q.get("ts", 0.0) or 0.0),
            "last_tag_d_path_seq": int((last_tag_path_chunks.get(sym) or {}).get("path_seq") or 0),
            "last_tag_d_path_event_count": int((last_tag_path_chunks.get(sym) or {}).get("event_count") or 0),
            "last_tag_d_path_last_token": str((last_tag_path_chunks.get(sym) or {}).get("last_token") or ""),
            "last_tag_d_path_string": str((last_tag_path_chunks.get(sym) or {}).get("path_string") or ""),
            "_state_meta": state_meta,
        }

    @staticmethod
    def _snapshot_daily_weekly_limits() -> tuple[int, int]:
        try:
            daily_ohlcv_limit = max(200, int(os.getenv("BREAKOUT_V2_DAILY_OHLCV_LIMIT", "300")))
        except Exception:
            daily_ohlcv_limit = 300
        try:
            weekly_close_limit = max(15, int(os.getenv("BREAKOUT_V2_WEEKLY_CLOSE_LIMIT", "260")))
        except Exception:
            weekly_close_limit = 260
        return (daily_ohlcv_limit, weekly_close_limit)

    def _build_daily_weekly_pair_for_symbol(
        self,
        sym: str,
        daily_limit: int,
        weekly_limit: int,
        quote_map: dict,
        timing_daily: dict[str, dict],
        timing_weekly: dict[str, dict],
        persisted_daily: dict[str, dict],
        last_tag_path_chunks: dict[str, dict],
    ) -> tuple[Optional[dict], Optional[dict]]:
        """One parquet read per symbol (HistoryAdapter cache key is (sym, limit))."""
        L = max(int(daily_limit), int(weekly_limit))
        ohlcv_all = self.history.get_ohlcv_time_series(sym, limit=L)
        if not ohlcv_all:
            return (None, None)
        ohlcv_d = ohlcv_all[-daily_limit:] if len(ohlcv_all) > daily_limit else ohlcv_all
        daily_row = self._build_daily_row_from_ohlcv(
            sym, ohlcv_d, quote_map, timing_daily, persisted_daily, last_tag_path_chunks
        )
        slice_w = ohlcv_all[-weekly_limit:] if len(ohlcv_all) > weekly_limit else ohlcv_all
        series_w = [
            {"close": float(x["close"]), "ts": str(x.get("ts", "—"))}
            for x in slice_w
            if isinstance(x, dict) and "close" in x
        ]
        weekly_row = self._build_weekly_row_from_close_series(sym, series_w, quote_map, timing_weekly)
        return (daily_row, weekly_row)

    def _daily_weekly_rows(
        self,
        symbols: list[str],
        quote_map: dict,
        timing_daily: dict[str, dict],
        timing_weekly: dict[str, dict],
        persisted_daily: dict[str, dict],
        last_tag_path_chunks: dict[str, dict],
    ) -> tuple[list[dict], list[dict]]:
        daily_limit, weekly_limit = self._snapshot_daily_weekly_limits()
        daily_rows: list[dict] = []
        weekly_rows: list[dict] = []
        n = len(symbols)
        if self._snapshot_parallel_enabled(n):
            max_w = self._snapshot_max_workers()
            with ThreadPoolExecutor(max_workers=max_w) as ex:
                futs = {
                    ex.submit(
                        self._build_daily_weekly_pair_for_symbol,
                        sym,
                        daily_limit,
                        weekly_limit,
                        quote_map,
                        timing_daily,
                        timing_weekly,
                        persisted_daily,
                        last_tag_path_chunks,
                    ): sym
                    for sym in symbols
                }
                for fut in as_completed(futs):
                    d_row, w_row = fut.result()
                    if d_row:
                        daily_rows.append(d_row)
                    if w_row:
                        weekly_rows.append(w_row)
        else:
            for sym in symbols:
                d_row, w_row = self._build_daily_weekly_pair_for_symbol(
                    sym,
                    daily_limit,
                    weekly_limit,
                    quote_map,
                    timing_daily,
                    timing_weekly,
                    persisted_daily,
                    last_tag_path_chunks,
                )
                if d_row:
                    daily_rows.append(d_row)
                if w_row:
                    weekly_rows.append(w_row)
        daily_rows.sort(key=lambda r: (r["is_breakout"], r["bars"], r["symbol"]), reverse=True)
        weekly_rows.sort(key=lambda r: (r["is_breakout"], r["bars"], r["symbol"]), reverse=True)
        return (daily_rows, weekly_rows)

    def _compute_eod_sync_from_daily(self, symbols: list[str], daily_rows: list[dict]) -> dict:
        """EOD sync from already-built daily rows — avoids a second parquet pass per symbol."""
        total = len(symbols)
        if total == 0:
            return {
                "status": "EOD_NOT_STARTED",
                "expected_date": "-",
                "fresh_count": 0,
                "total_count": 0,
                "stale_count": 0,
                "sync_pct": 0.0,
            }
        day_keys: dict[str, str] = {}
        for r in daily_rows:
            s = str(r.get("symbol", "")).strip().upper()
            k = str(r.get("structural_event_key", "")).strip()
            if s and k not in ("", "-"):
                day_keys[s] = k
        if not day_keys:
            return {
                "status": "EOD_NOT_STARTED",
                "expected_date": "-",
                "fresh_count": 0,
                "total_count": total,
                "stale_count": total,
                "sync_pct": 0.0,
            }
        expected_date = max(day_keys.values())
        fresh_count = sum(1 for s in symbols if day_keys.get(s) == expected_date)
        stale_count = total - fresh_count
        sync_pct = (fresh_count / total) * 100.0 if total else 0.0
        if fresh_count == total:
            status = "EOD_SYNC_OK"
        elif fresh_count > 0:
            status = "EOD_SYNC_RUNNING"
        else:
            status = "EOD_SYNC_STALE"
        return {
            "status": status,
            "expected_date": expected_date,
            "fresh_count": fresh_count,
            "total_count": total,
            "stale_count": stale_count,
            "sync_pct": sync_pct,
        }

    def _build_weekly_row_from_close_series(
        self, sym: str, series: list[dict], quote_map: dict, timing_weekly: dict[str, dict]
    ) -> Optional[dict]:
        closes = [x["close"] for x in series]
        if len(closes) < 15:
            return None
        weekly = closes[::5]
        weekly_ts = [x["ts"] for x in series][::5]
        brk12, last_close, ref = self._breakout_flag(weekly, lookback=12)
        q = quote_map.get(sym) or {}
        q_ltp = q.get("ltp")
        try:
            last_live = float(q_ltp) if q_ltp is not None else float(last_close)
        except Exception:
            last_live = float(last_close)
        prev = weekly[-2] if len(weekly) > 1 else weekly[-1]
        chp = ((last_live / prev) - 1.0) * 100.0 if prev else 0.0
        pct_live = ((last_live / ref) - 1.0) * 100.0 if ref else 0.0
        when_w = weekly_ts[-1] if weekly_ts else "—"
        tag = "B" if brk12 else "E21C"
        overlay = timing_weekly.get(sym, {})
        if overlay:
            tag = str(overlay.get("last_tag_w") or overlay.get("timing_last_tag_w") or tag)
            when_w = str(overlay.get("timing_last_event_dt_w") or when_w)
            try:
                pct_live = float(overlay.get("brk_move_live_pct_w", pct_live))
            except Exception:
                pass
        return {
            "symbol": sym,
            "bars": len(weekly),
            "last": round(last_live, 2),
            "ref": round(ref, 2),
            "is_breakout": brk12,
            "has_quote": bool(q),
            "last_tag_w": tag,
            "timing_last_event_dt_w": when_w,
            "brk_move_live_pct_w": round(pct_live, 2),
            "live_struct_w": str(overlay.get("live_struct_w") or ""),
            "live_struct_w_today": str(overlay.get("live_struct_w_today") or ""),
            "chp": round(chp, 2),
            "rs_rating": int(q.get("rs_rating") or 0),
            "mrs": float(q.get("mrs") or 0.0),
            "rv": float(q.get("rv") or 0.0),
            "status": str(q.get("status") or ""),
            "quote_source": str(q.get("source") or ""),
            "quote_ts": float(q.get("ts", 0.0) or 0.0),
        }

    def _snapshot_compute(self, universe: str = "NIFTY200") -> Dict[str, object]:
        dbg = self._snapshot_phase_debug_enabled()
        ph: dict[str, int] = {}
        last = time.perf_counter()

        def tick(name: str) -> None:
            nonlocal last
            if not dbg:
                return
            now = time.perf_counter()
            ph[name] = int((now - last) * 1000)
            last = now

        self.transitions.ensure_tables()
        tick("ensure_tables")
        symbol_list = self.symbols.list_symbols(universe)
        uni_key = str(universe or "").strip().upper()
        # Do not cap regular universes (e.g. Nifty 500). Only cap All NSE for fast first paint.
        if uni_key == "ALL NSE STOCKS":
            try:
                max_symbols = int(os.getenv("BREAKOUT_V2_ALL_NSE_MAX_SYMBOLS", "40"))
            except Exception:
                max_symbols = 40
        else:
            max_symbols = 0
        if max_symbols > 0 and len(symbol_list) > max_symbols:
            sample_symbols = symbol_list[:max_symbols]
        else:
            sample_symbols = symbol_list
        tick("list_symbols")
        quote_map = self.live_quotes.get_quote_map(sample_symbols)
        tick("quotes")
        timing_daily = self._timing_overlay(universe=universe, clock_timeframe="daily")
        timing_weekly = self._timing_overlay(universe=universe, clock_timeframe="weekly")
        tick("timing_overlay")
        # Phase 1 durability: if timing overlay is unavailable or partial, recover prior persisted states.
        persisted_d = self.transitions.load_daily_states(sample_symbols)
        tick("load_daily_states")
        persisted_w = self.transitions.load_weekly_states(sample_symbols)
        tick("load_weekly_states")
        last_tag_path_chunks = self.transitions.load_last_tag_d_latest_path_chunks(sample_symbols)
        tick("load_path_chunks")
        if persisted_d:
            for sym, row in persisted_d.items():
                timing_daily.setdefault(sym, row)
        if persisted_w:
            for sym, row in persisted_w.items():
                timing_weekly.setdefault(sym, row)
        tick("merge_overlay")
        daily_rows, weekly_rows = self._daily_weekly_rows(
            sample_symbols, quote_map, timing_daily, timing_weekly, persisted_d, last_tag_path_chunks
        )
        tick("rows_build")
        eod_sync = self._compute_eod_sync_from_daily(sample_symbols, daily_rows)
        tick("eod_sync")
        # Throttle persistence writes to reduce DB pressure and UI lag on frequent polling.
        # UI still refreshes every cycle; DB writes happen at a controlled cadence.
        try:
            persist_every_sec = max(1.0, float(os.getenv("BREAKOUT_V2_PERSIST_EVERY_SEC", "5")))
        except Exception:
            persist_every_sec = 5.0
        now_ts = time.time()
        persist_ms = 0
        if (now_ts - float(self._last_persist_ts or 0.0)) >= persist_every_sec:
            t_p0 = time.perf_counter()
            self.transitions.upsert_daily_rows(daily_rows)
            self.transitions.upsert_weekly_rows(weekly_rows)
            self._last_persist_ts = now_ts
            persist_ms = int((time.perf_counter() - t_p0) * 1000)
        if dbg:
            ph["persist"] = persist_ms
            last = time.perf_counter()
        strategy_rows = [r for r in daily_rows if r["is_breakout"]][:20]
        tick("strategy_tail")
        out: Dict[str, object] = {
            "mode": self.mode,
            "universe": universe,
            "symbol_count": len(symbol_list),
            "symbol_count_loaded": len(sample_symbols),
            "daily_rows": daily_rows,
            "weekly_rows": weekly_rows,
            "strategy_rows": strategy_rows,
            "eod_sync": eod_sync,
        }
        if dbg:
            out["_debug_snapshot_phases_ms"] = ph
        return out

    def snapshot(self, universe: str = "NIFTY200") -> Dict[str, object]:
        ttl = _snapshot_cache_ttl_sec()
        ukey = str(universe or "").strip()
        if ttl <= 0.0:
            return self._snapshot_compute(universe)
        now_m = time.monotonic()
        with _SNAPSHOT_CACHE_GUARD:
            hit = _SNAPSHOT_CACHE_BY_UNIVERSE.get(ukey)
            if hit is not None and now_m < hit[0]:
                return _clone_snapshot_payload(hit[1])
        with _SNAPSHOT_BUILD_SERIAL:
            now_m = time.monotonic()
            with _SNAPSHOT_CACHE_GUARD:
                hit = _SNAPSHOT_CACHE_BY_UNIVERSE.get(ukey)
                if hit is not None and now_m < hit[0]:
                    return _clone_snapshot_payload(hit[1])
            payload = self._snapshot_compute(universe)
            with _SNAPSHOT_CACHE_GUARD:
                _SNAPSHOT_CACHE_BY_UNIVERSE[ukey] = (time.monotonic() + ttl, payload)
        return _clone_snapshot_payload(payload)


_ENGINE: V2Engine | None = None


def get_engine() -> V2Engine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = V2Engine.build()
    return _ENGINE

