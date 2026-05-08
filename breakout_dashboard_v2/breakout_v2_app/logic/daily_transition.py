from __future__ import annotations

from datetime import datetime
from typing import Any, Dict


def _extract_b_stage(tag: str) -> str:
    t = _state_text(tag).upper()
    if not t.startswith("B"):
        return ""
    out = ["B"]
    for ch in t[1:]:
        if ch.isdigit():
            out.append(ch)
        else:
            break
    return "".join(out) if len(out) > 1 else ""


def _extract_e_stage(tag: str) -> str:
    t = _state_text(tag).upper()
    if t.startswith("E9CT"):
        out = ["E", "9", "C", "T"]
        for ch in t[4:]:
            if ch.isdigit():
                out.append(ch)
            else:
                break
        return "".join(out) if len(out) > 4 else "E9CT"
    if t.startswith("E21C"):
        out = ["E", "2", "1", "C"]
        for ch in t[4:]:
            if ch.isdigit():
                out.append(ch)
            else:
                break
        return "".join(out) if len(out) > 4 else "E21C"
    if t.startswith("ET9DNWF21C"):
        return "ET9DNWF21C"
    return ""

def _state_text(x: Any) -> str:
    return str(x or "").strip()


def compute_live_struct_d(
    *,
    structural_last_tag_d: str,
    structural_event_key: str,
    ltp: float | None,
    quote_ts: float | None,
    ohlcv_series: list[dict],
    prev_state: Dict[str, Any] | None,
) -> tuple[str, Dict[str, Any]]:
    """
    Compute LIVE_STRUCT_D using RS parity function path.
    Structural LAST TAG D remains the authority passed by caller.
    """
    tag = _state_text(structural_last_tag_d).upper() or "—"
    evk = _state_text(structural_event_key) or "-"
    prev = prev_state or {}
    prev_tag = _state_text(prev.get("last_tag_d_structural", "")).upper()
    prev_evk = _state_text(prev.get("structural_event_key", ""))
    try:
        from zoneinfo import ZoneInfo
    except Exception:
        # Minimal no-op fallback without external dependencies.
        live = _state_text(prev.get("live_struct_d", "")) if not ((tag != prev_tag) or (evk != prev_evk)) else ""
        return live, {"last_tag_d_structural": tag, "structural_event_key": evk}

    d: dict[str, Any] = {}
    closes: list[float] = []
    for x in ohlcv_series or []:
        try:
            closes.append(float(x.get("close", 0.0) or 0.0))
        except Exception:
            continue
    if closes:
        d["ema9_d"] = sum(closes[-9:]) / float(min(9, len(closes)))
        d["ema21_d"] = sum(closes[-21:]) / float(min(21, len(closes)))

    # Structural truth is authoritative (do not let live path rewrite it).
    d["last_tag"] = tag
    d["ltp"] = float(ltp or 0.0)
    attempt_tag = _state_text(prev.get("live_attempt_tag", ""))
    attempt_started_at = _state_text(prev.get("live_attempt_started_at", ""))
    attempt_invalidated_at = _state_text(prev.get("live_attempt_invalidated_at", ""))
    attempt_status = _state_text(prev.get("live_attempt_status", ""))
    attempt_reason = _state_text(prev.get("live_attempt_reason", ""))

    prev_live_struct = _state_text(prev.get("live_struct_d", ""))

    # If EOD structural truth changed, reconcile prior live attempt to structural truth.
    structural_changed = (tag != prev_tag) or (evk != prev_evk)
    if structural_changed and attempt_tag:
        now_iso_reconcile = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
        structural_b = _extract_b_stage(tag)
        structural_e = _extract_e_stage(tag)
        if (structural_b and structural_b == attempt_tag) or (structural_e and structural_e == attempt_tag):
            # Example: B2_LIVE_WATCH -> B2_CONFIRMED after EOD structural close.
            d["live_struct_d"] = f"{attempt_tag}_CONFIRMED"
            attempt_status = "confirmed"
            attempt_reason = "eod_reconcile_confirmed"
        else:
            # Example: B2_LIVE_WATCH -> ET9DNWF21C_CONFIRMED(B2_FAILED)
            if tag and tag != "—":
                d["live_struct_d"] = f"{tag}_CONFIRMED({attempt_tag}_FAILED)"
            else:
                d["live_struct_d"] = f"{attempt_tag}_FAILED"
            attempt_status = "failed"
            attempt_reason = f"eod_reconcile_to_{tag or 'UNKNOWN'}"
            if not attempt_invalidated_at:
                attempt_invalidated_at = now_iso_reconcile
    elif prev_live_struct:
        d["live_struct_d"] = prev_live_struct

    # Restore prior live-struct session fields (durable state) only when structural truth is same.
    pmeta = prev if isinstance(prev, dict) else {}
    if not structural_changed:
        for k in (
            "live_struct_d",
            "lsd_latch",
            "lsd_ist_day",
            "lsd_ge9",
            "lsd_e9ct_touch",
            "lsd_under9_streak",
            "lsd_eod_key",
            "lsd_prev_ltp",
            "lsd_sticky_confirmed",
            "lsd_day_key",
            "lsd_day_status",
        ):
            if k in pmeta:
                d[k] = pmeta.get(k)

    now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    now_iso = now_ist.strftime("%Y-%m-%d %H:%M:%S")

    # Hard guard: do not create/advance intraday LIVE_STRUCT when market is closed
    # or when the quote heartbeat is stale.
    wd = now_ist.weekday()
    hhmm = (now_ist.hour, now_ist.minute)
    market_open = (wd < 5) and ((hhmm >= (9, 15)) and (hhmm <= (15, 30)))
    qts = float(quote_ts or 0.0)
    quote_fresh = (qts > 0.0) and ((now_ist.timestamp() - qts) <= 120.0)

    # Guardrail from requirements:
    # live_struct_d depends on Last Tag D truth, so do not advance when structural truth is unresolved.
    structural_ready = (tag != "—") and (evk not in ("", "-"))
    if structural_ready and market_open and quote_fresh:
        ema9 = float(d.get("ema9_d", 0.0) or 0.0)
        price = float(ltp or 0.0)
        b_stage = _extract_b_stage(tag)
        e_stage = _extract_e_stage(tag)
        # Independent V2 daily live-struct rule: structural tag + live price regime vs EMA9.
        if tag.startswith("B"):
            if b_stage and attempt_tag != b_stage:
                attempt_tag = b_stage
                attempt_started_at = now_iso
                attempt_invalidated_at = ""
                attempt_status = "valid"
                attempt_reason = "live_watch_started"
            if b_stage:
                if price >= ema9:
                    d["live_struct_d"] = f"{b_stage}_LIVE_WATCH"
                    attempt_status = "valid"
                    attempt_reason = "live_watch_active"
                else:
                    d["live_struct_d"] = f"{b_stage}_NO_MORE_VALID"
                    attempt_status = "invalidated"
                    attempt_reason = "fell_below_ema9"
                    attempt_invalidated_at = now_iso
            else:
                d["live_struct_d"] = "B_LIVE_WATCH" if price >= ema9 else "B_NO_MORE_VALID"
            if price < ema9 and attempt_tag:
                attempt_status = "invalidated"
                attempt_reason = "fell_below_ema9"
                attempt_invalidated_at = now_iso
        elif tag.startswith("E"):
            if e_stage and attempt_tag != e_stage:
                attempt_tag = e_stage
                attempt_started_at = now_iso
                attempt_invalidated_at = ""
                attempt_status = "valid"
                attempt_reason = "e_live_watch_started"
            if e_stage:
                if price >= ema9:
                    d["live_struct_d"] = f"{e_stage}_LIVE_WATCH"
                    attempt_status = "valid"
                    attempt_reason = "e_live_watch_active"
                else:
                    d["live_struct_d"] = f"{e_stage}_NO_MORE_VALID"
                    attempt_status = "invalidated"
                    attempt_reason = "e_fell_below_ema9"
                    attempt_invalidated_at = now_iso
            else:
                d["live_struct_d"] = f"{tag}_LIVE"
        elif tag == "RST":
            d["live_struct_d"] = "RST_LIVE"
            if attempt_tag and attempt_status.lower() == "valid":
                attempt_status = "invalidated"
                attempt_reason = "shifted_to_RST"
                attempt_invalidated_at = now_iso

    live = _state_text(d.get("live_struct_d", ""))

    meta = {
        "last_tag_d_structural": tag,
        "structural_event_key": evk,
        "live_struct_d": live,
        "lsd_latch": d.get("lsd_latch", ""),
        "lsd_ist_day": d.get("lsd_ist_day", ""),
        "lsd_ge9": int(d.get("lsd_ge9", 0) or 0),
        "lsd_e9ct_touch": int(d.get("lsd_e9ct_touch", 0) or 0),
        "lsd_under9_streak": int(d.get("lsd_under9_streak", 0) or 0),
        "lsd_eod_key": d.get("lsd_eod_key", ""),
        "lsd_prev_ltp": float(d.get("lsd_prev_ltp", 0.0) or 0.0),
        "lsd_sticky_confirmed": d.get("lsd_sticky_confirmed", ""),
        "lsd_day_key": d.get("lsd_day_key", ""),
        "lsd_day_status": d.get("lsd_day_status", ""),
        "live_attempt_tag": attempt_tag,
        "live_attempt_started_at": attempt_started_at,
        "live_attempt_invalidated_at": attempt_invalidated_at,
        "live_attempt_status": attempt_status,
        "live_attempt_reason": attempt_reason,
    }
    return (live, meta)

