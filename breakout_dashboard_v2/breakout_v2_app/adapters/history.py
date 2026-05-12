from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, List
from datetime import datetime


@dataclass
class HistoryAdapter:
    """Phase-2 seam: source OHLCV history from parquet/DB only."""

    mode: str
    pipeline_data_dir: str
    _symbol_file_index: dict[str, Path] | None = None
    _rows_cache: dict[tuple[str, int], tuple[float, list[dict]]] | None = None
    _cache_lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    @staticmethod
    def _cache_ttl_sec() -> float:
        try:
            # Longer default trades RAM for fewer repeated parquet decodes (same symbol+limit key).
            return max(1.0, float(os.getenv("BREAKOUT_V2_HISTORY_CACHE_SEC", "120")))
        except Exception:
            return 120.0

    @staticmethod
    def _norm_symbol(s: str) -> str:
        return re.sub(r"[^A-Z0-9]+", "_", str(s or "").upper()).strip("_")

    def _ensure_index(self) -> dict[str, Path]:
        if self._symbol_file_index is not None:
            return self._symbol_file_index

        base = Path(self.pipeline_data_dir)
        idx: dict[str, Path] = {}
        if base.exists():
            for p in base.glob("*.parquet"):
                stem = p.stem.upper()
                parts = stem.split("_")
                # Expected common format: NSE_<SYMBOL>_<SERIES>.parquet
                if len(parts) >= 3 and parts[0] == "NSE":
                    sym = parts[1]
                    # Prefer EQ series where duplicates exist.
                    prev = idx.get(sym)
                    if prev is None or stem.endswith("_EQ"):
                        idx[sym] = p
                    continue
                # Fallback format: <SYMBOL>.parquet
                idx[stem] = p

        self._symbol_file_index = idx
        return idx

    def _resolve_symbol_path(self, symbol: str) -> Path | None:
        idx = self._ensure_index()
        raw = str(symbol or "").upper()
        norm = self._norm_symbol(raw)
        if raw in idx:
            return idx[raw]
        if norm in idx:
            return idx[norm]
        return None

    def _read_parquet_rows(self, symbol: str, limit: int) -> list[dict]:
        key = (str(symbol or "").upper(), int(limit))
        with self._cache_lock:
            if self._rows_cache is not None:
                hit = self._rows_cache.get(key)
                if hit is not None:
                    ts_cached, rows_cached = hit
                    if (time.time() - float(ts_cached)) <= self._cache_ttl_sec():
                        return list(rows_cached)

        parquet_path = self._resolve_symbol_path(symbol)
        if parquet_path is None or not parquet_path.exists():
            return []
        try:
            import pandas as pd

            df = pd.read_parquet(parquet_path)
            if df.empty:
                return []
            df = df.tail(limit)
            rows = df.to_dict("records")
            with self._cache_lock:
                if self._rows_cache is None:
                    self._rows_cache = {}
                self._rows_cache[key] = (time.time(), rows)
            return rows
        except Exception:
            return []

    def get_close_series(self, symbol: str, limit: int = 260) -> list[float]:
        rows = self._read_parquet_rows(symbol, limit)
        if not rows:
            return []
        close_keys = ("close", "Close", "c", "CLOSE")
        closes: list[float] = []
        for row in rows:
            v = None
            for k in close_keys:
                if k in row:
                    v = row[k]
                    break
            if v is None:
                continue
            try:
                closes.append(float(v))
            except Exception:
                continue
        return closes

    def get_close_time_series(self, symbol: str, limit: int = 260) -> list[dict]:
        rows = self._read_parquet_rows(symbol, limit)
        if not rows:
            return []
        close_keys = ("close", "Close", "c", "CLOSE")
        ts_keys = ("timestamp", "ts", "datetime", "date", "Date", "time")
        out: list[dict] = []
        for row in rows:
            close_val = None
            ts_val = None
            for k in close_keys:
                if k in row:
                    close_val = row[k]
                    break
            for k in ts_keys:
                if k in row:
                    ts_val = row[k]
                    break
            if close_val is None:
                continue
            try:
                c = float(close_val)
            except Exception:
                continue
            out.append({"close": c, "ts": str(ts_val) if ts_val is not None else "—"})
        return out

    def get_ohlcv_time_series(self, symbol: str, limit: int = 900) -> list[dict]:
        rows = self._read_parquet_rows(symbol, limit)
        if not rows:
            return []
        out: list[dict] = []
        for row in rows:
            row_ci = {str(k).strip().lower(): v for k, v in row.items()}
            try:
                o = float(row_ci.get("open", row_ci.get("o")))
                h = float(row_ci.get("high", row_ci.get("h")))
                l = float(row_ci.get("low", row_ci.get("l")))
                c = float(row_ci.get("close", row_ci.get("c")))
            except Exception:
                continue
            v_raw = row_ci.get("volume", row_ci.get("vol", row_ci.get("v", 0.0)))
            try:
                v = float(v_raw or 0.0)
            except Exception:
                v = 0.0

            ts_raw = (
                row_ci.get("timestamp")
                or row_ci.get("ts")
                or row_ci.get("datetime")
                or row_ci.get("date")
                or row_ci.get("time")
            )
            ts_num = 0.0
            if ts_raw is not None:
                try:
                    ts_num = float(ts_raw)
                    # Convert ms/us epoch to seconds when needed.
                    if ts_num > 1e12:
                        ts_num = ts_num / 1000.0
                    elif ts_num > 1e10:
                        ts_num = ts_num / 1000.0
                except Exception:
                    try:
                        ts_num = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00")).timestamp()
                    except Exception:
                        ts_num = 0.0
            out.append({"ts": ts_num, "open": o, "high": h, "low": l, "close": c, "volume": v})
        return out

    def get_daily_history(self, symbol: str, limit: int = 900) -> List[Any]:
        rows = self._read_parquet_rows(symbol, limit)
        if rows:
            return rows

        sidecar_meta = Path("/app/stock_scanner_sovereign/data/history_cache_index.json")
        if sidecar_meta.exists():
            try:
                data = json.loads(sidecar_meta.read_text(encoding="utf-8"))
                if isinstance(data, dict) and symbol in data:
                    return [{"symbol": symbol, "source": "cache_index"}]
            except Exception:
                return []
        return []

