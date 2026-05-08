from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
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


def _to_status(val: Any) -> str:
    try:
        if isinstance(val, (bytes, bytearray)):
            return bytes(val).decode("utf-8", errors="ignore").strip("\x00").strip()
        return str(val or "").strip()
    except Exception:
        return ""


def main() -> int:
    try:
        import numpy as np
        from utils.constants import SIGNAL_DTYPE
    except Exception as e:
        print(f"[bridge] failed imports (numpy/SIGNAL_DTYPE): {e}")
        return 2

    try:
        import redis
    except Exception as e:
        print(f"[bridge] redis client not installed: {e}")
        return 3

    shm_path = os.getenv("SHM_MMAP_PATH", "/app/stock_scanner_sovereign/scanner_results.mmap")
    idx_map_path = os.getenv("SHM_INDEX_MAP_PATH", "/app/stock_scanner_sovereign/symbols_idx_map.json")
    dragonfly_host = os.getenv("DRAGONFLY_HOST", "dragonfly")
    dragonfly_port = _env_int("DRAGONFLY_PORT", 6379)
    key_prefix = os.getenv("DRAGONFLY_KEY_PREFIX", "live")
    heartbeat_key = os.getenv("DRAGONFLY_HEARTBEAT_KEY", "live:heartbeat")
    sleep_sec = max(0.05, _env_float("SHM_BRIDGE_POLL_SEC", 0.5))
    batch_size = max(50, _env_int("SHM_BRIDGE_BATCH_SIZE", 500))
    max_rows = max(1, _env_int("SHM_BRIDGE_MAX_ROWS", 10000))

    if not (os.path.exists(shm_path) and os.path.exists(idx_map_path)):
        print(f"[bridge] missing SHM inputs: mmap={shm_path} idx={idx_map_path}")
        return 4

    try:
        with open(idx_map_path, "r", encoding="utf-8") as f:
            idx_map = json.load(f)
    except Exception as e:
        print(f"[bridge] failed loading idx map: {e}")
        return 5

    try:
        arr = np.memmap(shm_path, dtype=SIGNAL_DTYPE, mode="r", shape=(max_rows,))
    except Exception as e:
        print(f"[bridge] failed opening mmap: {e}")
        return 6

    try:
        r = redis.Redis(host=dragonfly_host, port=dragonfly_port, decode_responses=True, socket_timeout=2.0)
        r.ping()
    except Exception as e:
        print(f"[bridge] failed connecting dragonfly {dragonfly_host}:{dragonfly_port}: {e}")
        return 7

    symbols = [(str(sym).upper(), int(idx)) for sym, idx in idx_map.items() if str(sym).strip() != ""]
    print(
        f"[bridge] started shm->dragonfly symbols={len(symbols)} host={dragonfly_host}:{dragonfly_port} "
        f"poll={sleep_sec}s batch={batch_size}"
    )

    while True:
        t0 = time.time()
        wrote = 0
        errors = 0
        try:
            pipe = r.pipeline(transaction=False)
            for sym, idx in symbols:
                try:
                    row = arr[idx]
                    ltp = float(row["ltp"]) if "ltp" in row.dtype.names else 0.0
                    chg = float(row["change_pct"]) if "change_pct" in row.dtype.names else 0.0
                    mrs = float(row["mrs"]) if "mrs" in row.dtype.names else 0.0
                    rs_rating = int(row["rs_rating"]) if "rs_rating" in row.dtype.names else 0
                    rv = float(row["rv"]) if "rv" in row.dtype.names else 0.0
                    hb = float(row["heartbeat"]) if "heartbeat" in row.dtype.names else 0.0
                    status = _to_status(row["status"]) if "status" in row.dtype.names else ""
                    ts = hb if hb > 0 else time.time()
                    key = f"{key_prefix}:{sym}"
                    payload = {
                        "symbol": sym,
                        "ltp": f"{ltp}",
                        "change_pct": f"{chg}",
                        "mrs": f"{mrs}",
                        "rs_rating": f"{rs_rating}",
                        "rv": f"{rv}",
                        "status": status,
                        "ts": f"{ts}",
                        "source": "dragonfly_shm_bridge",
                        "updated_at": _now_iso(),
                    }
                    pipe.hset(key, mapping=payload)
                    wrote += 1
                    if wrote % batch_size == 0:
                        pipe.execute()
                        pipe = r.pipeline(transaction=False)
                except Exception:
                    errors += 1
                    continue
            pipe.set(heartbeat_key, str(time.time()))
            pipe.execute()
        except Exception as e:
            print(f"[bridge] write-cycle error: {e}")
            errors += 1

        dt = time.time() - t0
        print(f"[bridge] cycle wrote={wrote} errors={errors} dt={dt:.3f}s")
        time.sleep(sleep_sec)


if __name__ == "__main__":
    raise SystemExit(main())

