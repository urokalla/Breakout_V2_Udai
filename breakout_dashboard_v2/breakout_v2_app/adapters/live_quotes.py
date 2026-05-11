from __future__ import annotations

from dataclasses import dataclass
import json
import os
import time
from urllib import parse, request
from typing import Dict

from ..config import SCANNER_API_URL

_SHM_ARR = None
_SHM_IDX = None


@dataclass
class LiveQuoteAdapter:
    """Phase-2 seam: source live quote fields without direct SHM bridge usage."""

    mode: str

    @staticmethod
    def _shm_enabled() -> bool:
        return os.getenv("BREAKOUT_V2_ENABLE_SHM", "1").strip().lower() in ("1", "true", "yes")

    @staticmethod
    def _live_source_mode() -> str:
        # Force Dragonfly as the live source mode.
        mode = os.getenv("BREAKOUT_V2_LIVE_SOURCE", os.getenv("LIVE_SOURCE", "dragonfly")).strip().lower()
        return "dragonfly" if mode != "dragonfly" else mode

    @staticmethod
    def _db_symbol_candidates(sym: str) -> list[str]:
        s = str(sym or "").strip().upper()
        if not s:
            return []
        out = [s]
        if ":" not in s:
            out.append(f"NSE:{s}")
        if "-" not in s:
            out.append(f"{s}-EQ")
        if ":" not in s and "-" not in s:
            out.append(f"NSE:{s}-EQ")
        # preserve order + uniqueness
        seen = set()
        uniq = []
        for x in out:
            if x not in seen:
                seen.add(x)
                uniq.append(x)
        return uniq

    @staticmethod
    def _norm_from_db_symbol(sym: str) -> str:
        s = str(sym or "").strip().upper()
        if s.startswith("NSE:"):
            s = s[4:]
        if "-" in s:
            s = s.split("-", 1)[0]
        return s

    @staticmethod
    def _shm_symbol_candidates(sym: str) -> list[str]:
        s = str(sym or "").strip().upper()
        if not s:
            return []
        out = [s]
        if ":" not in s:
            out.append(f"NSE:{s}")
        if "-" not in s:
            out.append(f"{s}-EQ")
        if ":" not in s and "-" not in s:
            out.append(f"NSE:{s}-EQ")
        seen = set()
        uniq = []
        for x in out:
            if x not in seen:
                seen.add(x)
                uniq.append(x)
        return uniq

    def _ensure_shm_readonly(self):
        global _SHM_ARR, _SHM_IDX
        if _SHM_ARR is not None and _SHM_IDX is not None:
            return (_SHM_ARR, _SHM_IDX)
        try:
            import numpy as np
            from utils.constants import SIGNAL_DTYPE
        except Exception:
            return (None, None)

        shm_path = "/app/stock_scanner_sovereign/scanner_results.mmap"
        map_path = "/app/stock_scanner_sovereign/symbols_idx_map.json"
        if not (os.path.exists(shm_path) and os.path.exists(map_path)):
            return (None, None)
        try:
            with open(map_path, "r", encoding="utf-8") as f:
                idx_map = json.load(f)
            arr = np.memmap(shm_path, dtype=SIGNAL_DTYPE, mode="r", shape=(10000,))
            _SHM_ARR = arr
            _SHM_IDX = idx_map
            return (_SHM_ARR, _SHM_IDX)
        except Exception:
            return (None, None)

    def _fetch_from_shm(self, symbols: list[str]) -> Dict[str, dict]:
        arr, idx_map = self._ensure_shm_readonly()
        if arr is None or idx_map is None or not symbols:
            return {}
        out: Dict[str, dict] = {}
        ts = int(time.time())
        for s in symbols:
            sym = str(s).strip().upper()
            if not sym:
                continue
            idx = None
            for c in self._shm_symbol_candidates(sym):
                idx = idx_map.get(str(c))
                if idx is not None:
                    break
            if idx is None:
                continue
            try:
                row = arr[idx]
                ltp = float(row["ltp"])
                chg = float(row["change_pct"])
                hb = float(row["heartbeat"]) if "heartbeat" in row.dtype.names else 0.0
                mrs = float(row["mrs"]) if "mrs" in row.dtype.names else 0.0
                rs_rating = int(row["rs_rating"]) if "rs_rating" in row.dtype.names else 0
                rv = float(row["rv"]) if "rv" in row.dtype.names else 0.0
                status = (
                    bytes(row["status"]).decode("utf-8", errors="ignore").strip("\x00").strip()
                    if "status" in row.dtype.names
                    else ""
                )
                out[sym] = {
                    "symbol": sym,
                    "ltp": ltp,
                    "change_pct": chg,
                    "mrs": mrs,
                    "rs_rating": rs_rating,
                    "rv": rv,
                    "status": status,
                    "ts": hb if hb > 0 else ts,
                    "source": "scanner_shm",
                }
            except Exception:
                continue
        return out

    def _fetch_from_db(self, symbols: list[str]) -> Dict[str, dict]:
        if not symbols:
            return {}
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except Exception:
            return {}

        host = os.getenv("DB_HOST", "db")
        port = int(os.getenv("DB_PORT", "5432"))
        user = os.getenv("DB_USER", "fyers_user")
        password = os.getenv("DB_PASSWORD", "fyers_pass")
        dbname = os.getenv("DB_NAME", "fyers_db")

        conn = None
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname=dbname,
                connect_timeout=2,
            )
            requested = [str(s).strip().upper() for s in symbols if str(s).strip()]
            candidate_symbols: list[str] = []
            for s in requested:
                candidate_symbols.extend(self._db_symbol_candidates(s))

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT symbol, last_price, mrs, rs_rating, status
                    FROM live_state
                    WHERE symbol = ANY(%s)
                    """,
                    (candidate_symbols,),
                )
                rows = cur.fetchall() or []
            out: Dict[str, dict] = {}
            ts = int(time.time())
            for r in rows:
                raw_sym = str(r.get("symbol", "")).strip().upper()
                sym = self._norm_from_db_symbol(raw_sym)
                if not sym or sym not in requested:
                    continue
                out[sym] = {
                    "symbol": sym,
                    "ltp": float(r.get("last_price") or 0.0),
                    "mrs": float(r.get("mrs") or 0.0),
                    "rs_rating": int(r.get("rs_rating") or 0),
                    "status": str(r.get("status") or ""),
                    "ts": ts,
                    "source": "postgres_live_state",
                }
            return out
        except Exception:
            return {}
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass

    def _fetch_from_api(self, symbols: list[str]) -> Dict[str, dict]:
        if not SCANNER_API_URL or not symbols:
            return {}
        qs = parse.urlencode({"symbols": ",".join(symbols)})
        url = f"{SCANNER_API_URL}?{qs}"
        try:
            with request.urlopen(url, timeout=2.0) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return {}

        # Accept common payload shapes:
        # {"quotes": {"RELIANCE": {...}}}
        # {"data": {"RELIANCE": {...}}}
        # {"data": [{"symbol":"RELIANCE", ...}]}
        if isinstance(payload, dict):
            for key in ("quotes", "data", "result"):
                node = payload.get(key)
                if isinstance(node, dict):
                    return {str(k).upper(): v for k, v in node.items()}
                if isinstance(node, list):
                    out: Dict[str, dict] = {}
                    for item in node:
                        if not isinstance(item, dict):
                            continue
                        sym = str(item.get("symbol", "")).strip().upper()
                        if sym:
                            out[sym] = item
                    return out
        return {}

    def _fetch_from_dragonfly(self, symbols: list[str]) -> Dict[str, dict]:
        if not symbols:
            return {}
        try:
            import redis
        except Exception:
            return {}

        host = os.getenv("DRAGONFLY_HOST", "dragonfly")
        port = int(os.getenv("DRAGONFLY_PORT", "6379"))
        key_prefix = os.getenv("DRAGONFLY_KEY_PREFIX", "live")

        out: Dict[str, dict] = {}
        try:
            r = redis.Redis(host=host, port=port, decode_responses=True, socket_timeout=2.0)
            requested = [str(s).strip().upper() for s in symbols if str(s).strip()]
            for sym in requested:
                payload = None
                for c in self._shm_symbol_candidates(sym):
                    key = f"{key_prefix}:{str(c).upper()}"
                    data = r.hgetall(key)
                    if data:
                        payload = data
                        break
                if not payload:
                    continue
                out[sym] = {
                    "symbol": sym,
                    "ltp": float(payload.get("ltp") or 0.0),
                    "change_pct": float(payload.get("change_pct") or 0.0),
                    "mrs": float(payload.get("mrs") or 0.0),
                    "rs_rating": int(payload.get("rs_rating") or 0),
                    "rv": float(payload.get("rv") or 0.0),
                    "status": str(payload.get("status") or ""),
                    "ts": float(payload.get("ts") or time.time()),
                    "source": "dragonfly_live",
                }
            return out
        except Exception:
            return {}

    def get_quote_map(self, symbols: list[str]) -> Dict[str, dict]:
        source_mode = self._live_source_mode()
        if source_mode == "dragonfly":
            dragonfly_quotes = self._fetch_from_dragonfly(symbols)
            if dragonfly_quotes:
                return dragonfly_quotes

        # Non-SHM fallbacks when Dragonfly data is unavailable.
        db_quotes = self._fetch_from_db(symbols)
        if db_quotes:
            return db_quotes

        api_quotes = self._fetch_from_api(symbols)
        if api_quotes:
            return api_quotes

        # Deterministic fallback shape when API is not configured/reachable.
        ts = int(time.time())
        return {s: {"symbol": s, "ts": ts, "source": "placeholder"} for s in symbols}

