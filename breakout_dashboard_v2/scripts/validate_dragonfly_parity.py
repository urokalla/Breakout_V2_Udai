from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _symbol_candidates(sym: str) -> list[str]:
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
            uniq.append(x)
            seen.add(x)
    return uniq


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
        import redis
    except Exception as e:
        print(f"missing dependency: {e}")
        return 2

    shm_path = os.getenv("SHM_MMAP_PATH", "/app/stock_scanner_sovereign/scanner_results.mmap")
    idx_map_path = os.getenv("SHM_INDEX_MAP_PATH", "/app/stock_scanner_sovereign/symbols_idx_map.json")
    host = os.getenv("DRAGONFLY_HOST", "dragonfly")
    port = int(os.getenv("DRAGONFLY_PORT", "6379"))
    key_prefix = os.getenv("DRAGONFLY_KEY_PREFIX", "live")
    symbols_raw = os.getenv("PARITY_SYMBOLS", "RELIANCE,TCS,INFY,ICICIBANK,HDFCBANK,AXISBANK")
    symbols = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]
    max_rows = int(os.getenv("SHM_BRIDGE_MAX_ROWS", "10000"))

    if not os.path.exists(shm_path) or not os.path.exists(idx_map_path):
        print("missing shm files")
        return 3

    with open(idx_map_path, "r", encoding="utf-8") as f:
        idx_map = json.load(f)
    arr = np.memmap(shm_path, dtype=SIGNAL_DTYPE, mode="r", shape=(max_rows,))

    r = redis.Redis(host=host, port=port, decode_responses=True, socket_timeout=2.0)
    r.ping()

    checked = 0
    mismatches = 0
    missing = 0
    tol = float(os.getenv("PARITY_LTP_TOL", "0.01"))
    mismatch_details: list[dict[str, Any]] = []

    print(f"checking symbols={symbols}")
    for sym in symbols:
        idx = None
        shm_key = None
        for c in _symbol_candidates(sym):
            if c in idx_map:
                idx = int(idx_map[c])
                shm_key = c
                break
        if idx is None:
            print(f"{sym}: missing in SHM index")
            missing += 1
            continue
        row = arr[idx]
        shm_ltp = float(row["ltp"]) if "ltp" in row.dtype.names else 0.0
        shm_chg = float(row["change_pct"]) if "change_pct" in row.dtype.names else 0.0
        shm_rs = int(row["rs_rating"]) if "rs_rating" in row.dtype.names else 0
        shm_mrs = float(row["mrs"]) if "mrs" in row.dtype.names else 0.0
        shm_rv = float(row["rv"]) if "rv" in row.dtype.names else 0.0
        shm_status = _to_status(row["status"]) if "status" in row.dtype.names else ""

        drag_data = {}
        drag_key = ""
        for c in _symbol_candidates(sym):
            k = f"{key_prefix}:{c}"
            h = r.hgetall(k)
            if h:
                drag_data = h
                drag_key = k
                break
        if not drag_data:
            print(f"{sym}: missing in Dragonfly")
            missing += 1
            continue

        d_ltp = float(drag_data.get("ltp") or 0.0)
        d_chg = float(drag_data.get("change_pct") or 0.0)
        d_rs = int(drag_data.get("rs_rating") or 0)
        d_mrs = float(drag_data.get("mrs") or 0.0)
        d_rv = float(drag_data.get("rv") or 0.0)
        d_status = str(drag_data.get("status") or "")

        checked += 1
        ok = (
            abs(shm_ltp - d_ltp) <= tol
            and abs(shm_chg - d_chg) <= 1e-6
            and shm_rs == d_rs
            and abs(shm_mrs - d_mrs) <= 1e-6
            and abs(shm_rv - d_rv) <= 1e-6
            and shm_status == d_status
        )
        if not ok:
            mismatches += 1
            mismatch_details.append(
                {
                    "symbol": sym,
                    "shm_key": shm_key,
                    "dragonfly_key": drag_key,
                    "shm": {
                        "ltp": shm_ltp,
                        "change_pct": shm_chg,
                        "rs_rating": shm_rs,
                        "mrs": shm_mrs,
                        "rv": shm_rv,
                        "status": shm_status,
                    },
                    "dragonfly": {
                        "ltp": d_ltp,
                        "change_pct": d_chg,
                        "rs_rating": d_rs,
                        "mrs": d_mrs,
                        "rv": d_rv,
                        "status": d_status,
                    },
                }
            )
            print(
                f"MISMATCH {sym} shm_key={shm_key} drag_key={drag_key} "
                f"ltp({shm_ltp},{d_ltp}) chg({shm_chg},{d_chg}) rs({shm_rs},{d_rs}) "
                f"mrs({shm_mrs},{d_mrs}) rv({shm_rv},{d_rv}) status({shm_status},{d_status})"
            )
        else:
            print(f"OK {sym} ltp={d_ltp} source={drag_data.get('source')}")

    hb = r.get("live:heartbeat")
    now = time.time()
    hb_age = (now - float(hb)) if hb else None
    summary = {
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "dragonfly_host": host,
        "dragonfly_port": port,
        "symbols_requested": symbols,
        "checked": checked,
        "mismatches": mismatches,
        "missing": missing,
        "heartbeat_age_sec": hb_age,
        "ltp_tolerance": tol,
        "status": "PASS" if mismatches == 0 else "FAIL",
        "mismatch_details": mismatch_details,
    }
    print(
        f"summary checked={checked} mismatches={mismatches} missing={missing} "
        f"heartbeat_age_sec={round(hb_age,3) if hb_age is not None else 'NA'}"
    )
    try:
        out_dir = Path(os.getenv("PARITY_SUMMARY_DIR", "/app/breakout_dashboard_v2/runtime"))
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        out_path = out_dir / f"dragonfly_parity_summary_{ts}.json"
        out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"summary_file={out_path}")
    except Exception as e:
        print(f"summary_file_write_failed={e}")
    return 0 if mismatches == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

