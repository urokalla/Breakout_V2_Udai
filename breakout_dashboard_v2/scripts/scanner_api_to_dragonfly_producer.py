from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from urllib import parse, request
from typing import Any


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_symbol(sym: str) -> str:
    s = str(sym or "").strip().upper()
    if s.startswith("NSE:"):
        s = s[4:]
    if "-" in s:
        s = s.split("-", 1)[0]
    return s


def _to_float(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return d


def _to_int(v: Any, d: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return d


def _fetch_quotes(api_url: str, symbols: list[str]) -> dict[str, dict]:
    if not api_url or not symbols:
        return {}
    qs = parse.urlencode({"symbols": ",".join(symbols)})
    url = f"{api_url}?{qs}"
    try:
        with request.urlopen(url, timeout=3.0) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}

    if not isinstance(payload, dict):
        return {}

    for key in ("quotes", "data", "result"):
        node = payload.get(key)
        if isinstance(node, dict):
            out: dict[str, dict] = {}
            for k, v in node.items():
                out[_norm_symbol(str(k))] = v if isinstance(v, dict) else {}
            return out
        if isinstance(node, list):
            out = {}
            for item in node:
                if not isinstance(item, dict):
                    continue
                s = _norm_symbol(str(item.get("symbol", "")))
                if s:
                    out[s] = item
            return out
    return {}


def main() -> int:
    try:
        import redis
    except Exception as e:
        print(f"[producer] missing redis client: {e}")
        return 2

    scanner_api = os.getenv("SCANNER_API_URL", "").strip()
    if not scanner_api:
        print("[producer] SCANNER_API_URL missing; nothing to do")
        return 3

    symbols_file = os.getenv("SYMBOLS_FILE", "/app/stock_scanner_sovereign/data/NSE_EQ.csv")
    dragonfly_host = os.getenv("DRAGONFLY_HOST", "dragonfly")
    dragonfly_port = _env_int("DRAGONFLY_PORT", 6379)
    key_prefix = os.getenv("DRAGONFLY_KEY_PREFIX", "live")
    heartbeat_key = os.getenv("DRAGONFLY_HEARTBEAT_KEY", "live:heartbeat")
    poll_sec = max(0.1, _env_float("SCANNER_API_TO_DRAGONFLY_POLL_SEC", 1.0))
    batch_size = max(20, _env_int("SCANNER_API_TO_DRAGONFLY_BATCH", 300))

    symbols: list[str] = []
    try:
        with open(symbols_file, "r", encoding="utf-8") as f:
            first = True
            for line in f:
                if first:
                    first = False
                    continue
                s = _norm_symbol(line.split(",")[0])
                if s:
                    symbols.append(s)
    except Exception as e:
        print(f"[producer] failed loading symbols from {symbols_file}: {e}")
        return 4
    if not symbols:
        print("[producer] no symbols loaded")
        return 5

    try:
        r = redis.Redis(host=dragonfly_host, port=dragonfly_port, decode_responses=True, socket_timeout=2.0)
        r.ping()
    except Exception as e:
        print(f"[producer] failed connecting dragonfly: {e}")
        return 6

    print(
        f"[producer] started scanner_api->{dragonfly_host}:{dragonfly_port} "
        f"symbols={len(symbols)} poll={poll_sec}s batch={batch_size}"
    )

    while True:
        t0 = time.time()
        wrote = 0
        errors = 0
        for i in range(0, len(symbols), batch_size):
            chunk = symbols[i : i + batch_size]
            quotes = _fetch_quotes(scanner_api, chunk)
            if not quotes:
                continue
            pipe = r.pipeline(transaction=False)
            for sym in chunk:
                q = quotes.get(sym) or {}
                if not q:
                    continue
                try:
                    key = f"{key_prefix}:NSE:{sym}-EQ"
                    payload = {
                        "symbol": f"NSE:{sym}-EQ",
                        "ltp": f"{_to_float(q.get('ltp', q.get('last_price', 0.0)))}",
                        "change_pct": f"{_to_float(q.get('change_pct', q.get('chg_pct', 0.0)))}",
                        "mrs": f"{_to_float(q.get('mrs', 0.0))}",
                        "rs_rating": f"{_to_int(q.get('rs_rating', 0))}",
                        "rv": f"{_to_float(q.get('rv', q.get('rvol', 0.0)))}",
                        "status": str(q.get("status", "") or ""),
                        "ts": f"{_to_float(q.get('ts', q.get('heartbeat', time.time())), time.time())}",
                        "source": "dragonfly_scanner_api",
                        "updated_at": _now_iso(),
                    }
                    pipe.hset(key, mapping=payload)
                    wrote += 1
                except Exception:
                    errors += 1
            try:
                pipe.set(heartbeat_key, str(time.time()))
                pipe.execute()
            except Exception:
                errors += 1
                continue
        dt = time.time() - t0
        print(f"[producer] cycle wrote={wrote} errors={errors} dt={dt:.3f}s")
        time.sleep(poll_sec)


if __name__ == "__main__":
    raise SystemExit(main())

