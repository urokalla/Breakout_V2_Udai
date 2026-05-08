from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List
import os
import time

from .adapters import HistoryAdapter, LiveQuoteAdapter, SymbolsAdapter, TransitionStoreAdapter
from .config import DATA_MODE, PIPELINE_DATA_DIR
from .logic import compute_live_struct_d, compute_structural_last_tag_d


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
            return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
        except Exception:
            return "-"

    @staticmethod
    def _timing_overlay(universe: str, clock_timeframe: str, page_size: int = 400) -> dict[str, dict]:
        # V2 independence: no legacy timing overlay imports.
        # Durable DB transition rows are used as the fallback overlay source.
        return {}

    def _daily_rows(
        self,
        symbols: list[str],
        quote_map: dict,
        timing_daily: dict[str, dict],
        persisted_daily: dict[str, dict],
        last_tag_path_chunks: dict[str, dict],
    ) -> list[dict]:
        rows: list[dict] = []
        try:
            daily_ohlcv_limit = max(200, int(os.getenv("BREAKOUT_V2_DAILY_OHLCV_LIMIT", "300")))
        except Exception:
            daily_ohlcv_limit = 300
        for sym in symbols:
            ohlcv = self.history.get_ohlcv_time_series(sym, limit=daily_ohlcv_limit)
            if not ohlcv:
                continue
            closes = [x["close"] for x in ohlcv[-120:] if "close" in x]
            if not closes:
                continue
            last_close = float(closes[-1])
            # Keep breakout reference level on 10-bar structural window (not BRK20).
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
            # Structural truth authority for LAST TAG D comes from parquet replay logic.
            s_tag, s_when, s_event_key = compute_structural_last_tag_d(ohlcv, don_len=10)
            if s_tag != "—":
                tag = s_tag
                when_d = s_when
            if s_event_key not in ("", "-"):
                structural_event_key = s_event_key
            is_breakout = str(tag).upper().startswith("B")
            overlay = timing_daily.get(sym, {})
            if overlay:
                # Keep structural truth from replay authoritative; only consume live %/aux fields.
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
            rows.append(
                {
                    "symbol": sym,
                    "bars": len(closes),
                    "last": round(last_live, 2),
                    "ref": round(ref, 2),
                    "is_breakout": is_breakout,
                    "has_quote": bool(q),
                    "last_tag": tag,
                    "last_event_dt": when_d,
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
            )
        rows.sort(key=lambda r: (r["is_breakout"], r["bars"], r["symbol"]), reverse=True)
        return rows

    def _compute_eod_sync(self, symbols: list[str]) -> dict:
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
        with_history = 0
        for sym in symbols:
            ohlcv = self.history.get_ohlcv_time_series(sym, limit=5)
            if not ohlcv:
                continue
            key = self._daily_eod_event_key_from_ohlcv(ohlcv)
            if key in ("", "-"):
                continue
            with_history += 1
            day_keys[sym] = key

        if with_history == 0:
            return {
                "status": "EOD_NOT_STARTED",
                "expected_date": "-",
                "fresh_count": 0,
                "total_count": total,
                "stale_count": total,
                "sync_pct": 0.0,
            }

        expected_date = max(day_keys.values()) if day_keys else "-"
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

    def _weekly_rows(self, symbols: list[str], quote_map: dict, timing_weekly: dict[str, dict]) -> list[dict]:
        rows: list[dict] = []
        for sym in symbols:
            series = self.history.get_close_time_series(sym, limit=260)
            closes = [x["close"] for x in series]
            if len(closes) < 15:
                continue
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
            rows.append(
                {
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
            )
        rows.sort(key=lambda r: (r["is_breakout"], r["bars"], r["symbol"]), reverse=True)
        return rows

    def snapshot(self, universe: str = "NIFTY200") -> Dict[str, object]:
        self.transitions.ensure_tables()
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
        quote_map = self.live_quotes.get_quote_map(sample_symbols)
        timing_daily = self._timing_overlay(universe=universe, clock_timeframe="daily")
        timing_weekly = self._timing_overlay(universe=universe, clock_timeframe="weekly")
        # Phase 1 durability: if timing overlay is unavailable or partial, recover prior persisted states.
        persisted_d = self.transitions.load_daily_states(sample_symbols)
        persisted_w = self.transitions.load_weekly_states(sample_symbols)
        last_tag_path_chunks = self.transitions.load_last_tag_d_latest_path_chunks(sample_symbols)
        if persisted_d:
            for sym, row in persisted_d.items():
                timing_daily.setdefault(sym, row)
        if persisted_w:
            for sym, row in persisted_w.items():
                timing_weekly.setdefault(sym, row)
        daily_rows = self._daily_rows(sample_symbols, quote_map, timing_daily, persisted_d, last_tag_path_chunks)
        weekly_rows = self._weekly_rows(sample_symbols, quote_map, timing_weekly)
        eod_sync = self._compute_eod_sync(sample_symbols)
        # Throttle persistence writes to reduce DB pressure and UI lag on frequent polling.
        # UI still refreshes every cycle; DB writes happen at a controlled cadence.
        try:
            persist_every_sec = max(1.0, float(os.getenv("BREAKOUT_V2_PERSIST_EVERY_SEC", "5")))
        except Exception:
            persist_every_sec = 5.0
        now_ts = time.time()
        if (now_ts - float(self._last_persist_ts or 0.0)) >= persist_every_sec:
            self.transitions.upsert_daily_rows(daily_rows)
            self.transitions.upsert_weekly_rows(weekly_rows)
            self._last_persist_ts = now_ts
        strategy_rows = [r for r in daily_rows if r["is_breakout"]][:20]
        return {
            "mode": self.mode,
            "universe": universe,
            "symbol_count": len(symbol_list),
            "symbol_count_loaded": len(sample_symbols),
            "daily_rows": daily_rows,
            "weekly_rows": weekly_rows,
            "strategy_rows": strategy_rows,
            "eod_sync": eod_sync,
        }


_ENGINE: V2Engine | None = None


def get_engine() -> V2Engine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = V2Engine.build()
    return _ENGINE

