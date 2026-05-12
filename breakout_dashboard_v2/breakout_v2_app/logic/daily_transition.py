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

def _live_token_from_live_struct(s: str) -> str:
    """
    Extract the live-truth tag token from an intraday live_struct value.

    Examples:
    - B2_LIVE_WATCH -> B2
    - E9CT1_NO_MORE_VALID -> E9CT1
    - ET9DNWF21C_LIVE_WATCH -> ET9DNWF21C
    - RST_LIVE -> RST
    """
    t = _state_text(s).upper()
    if not t:
        return ""
    if t.endswith("_LIVE_WATCH"):
        return t[: -len("_LIVE_WATCH")].strip()
    if t.endswith("_NO_MORE_VALID"):
        return t[: -len("_NO_MORE_VALID")].strip()
    if t.endswith("_TIC_WATCH"):
        return t[: -len("_TIC_WATCH")].strip()
    if "_CONFIRMED(" in t:
        return t.split("_CONFIRMED", 1)[0].strip()
    if t.endswith("_CONFIRMED"):
        return t[: -len("_CONFIRMED")].strip()
    if t.endswith("_LIVE_FAILED"):
        return t[: -len("_LIVE_FAILED")].strip()
    if t == "RST_LIVE":
        return "RST"
    return ""


def _live_track_redundant_with_last_tag(candidate: str, structural_last_tag_d: str) -> bool:
    """True if LIVE_TRACK would repeat LAST TAG D (same plain token or same B-base on a compound row)."""
    c = _state_text(candidate).strip().upper()
    lt = _state_text(structural_last_tag_d).strip().upper()
    if not c or not lt or lt == "—":
        return False
    if c == lt:
        return True
    if "+" not in lt:
        return c == lt
    base = lt.split("+", 1)[0].strip().upper()
    return c == base


def _infer_live_track_focus(
    structural_tag: str,
    live_struct_d: str,
    ltp: float,
    ema9: float,
    ema21: float,
) -> str:
    """
    When LIVE_STRUCT says ``Bn_NO_MORE_VALID`` (live ticks: not sustaining B vs EMA9), LIVE_TRACK should
    point at **what tape can do next** — E9CT / E21 arms — not repeat ``Bn`` (same idea as LAST TAG D).

    Uses live LTP vs EMA9/EMA21 from the same OHLC the ladder uses in this function.
    """
    t = _state_text(structural_tag).strip().upper()
    ls = _state_text(live_struct_d).strip().upper()
    if not t.startswith("B") or "_NO_MORE_VALID" not in ls:
        return ""
    try:
        px = float(ltp or 0.0)
        e9 = float(ema9 or 0.0)
        e21 = float(ema21 or 0.0)
    except (TypeError, ValueError):
        return ""
    if px <= 0.0 or e9 <= 0.0:
        return ""
    if px >= e9:
        return ""
    # Below EMA9: watch next structural lanes (counts fixed to *1 until cycle counts are plumbed in).
    if e21 > 0.0 and px < e21:
        return "E21C1"
    return "E9CT1"


def live_track_tag_for_ui(
    live_attempt_tag: str,
    live_struct_d: str,
    structural_last_tag_d: str,
) -> str:
    """
    LIVE_TRACK = intraday tag token from the live ledger — **never** the same visible token as LAST TAG D
    (``B6`` vs ``B6`` shows blank here; ``B2+E9CT`` still allows ``E9CT1`` on this column).
    """
    lt_full = _state_text(structural_last_tag_d).strip().upper()

    att = _state_text(live_attempt_tag).upper()
    if att and not _live_track_redundant_with_last_tag(att, structural_last_tag_d):
        return att

    tok = _live_token_from_live_struct(_state_text(live_struct_d))
    if tok:
        u = tok.upper()
        if not _live_track_redundant_with_last_tag(u, structural_last_tag_d):
            return u

    if "+" in lt_full:
        rest = lt_full.split("+", 1)[1].strip().upper()
        if rest and not _live_track_redundant_with_last_tag(rest, structural_last_tag_d):
            return rest

    return ""


def _attempt_is_for_prev_evk(attempt_started_at: str, prev_evk: str) -> bool:
    """
    Guardrail: only treat `live_attempt_tag` as live truth for EOD reconcile
    if it was started on the same structural day key we are reconciling from.
    """
    a = _state_text(attempt_started_at)
    p = _state_text(prev_evk)
    if not a or not p or len(p) < 10:
        return False
    return a[:10] == p[:10]


def _parse_b_num(tag: str) -> int | None:
    t = _state_text(tag).upper()
    if not t.startswith("B"):
        return None
    digits = []
    for ch in t[1:]:
        if ch.isdigit():
            digits.append(ch)
        else:
            break
    if not digits:
        return None
    try:
        return int("".join(digits))
    except Exception:
        return None


def _parse_e9ct_num(tag: str) -> int | None:
    t = _state_text(tag).upper()
    if not t.startswith("E9CT"):
        return None
    tail = t[4:]
    if not tail or not tail[0].isdigit():
        return None
    digits = []
    for ch in tail:
        if ch.isdigit():
            digits.append(ch)
        else:
            break
    try:
        return int("".join(digits))
    except Exception:
        return None


def _parse_e21c_num(tag: str) -> int | None:
    t = _state_text(tag).upper()
    if not t.startswith("E21C"):
        return None
    tail = t[4:]
    if not tail or not tail[0].isdigit():
        return None
    digits = []
    for ch in tail:
        if ch.isdigit():
            digits.append(ch)
        else:
            break
    try:
        return int("".join(digits))
    except Exception:
        return None


def _eod_failed_attempt_inner_token(new_tag: str, prev_tag: str, attempt_tag: str) -> str:
    """
    Token inside CONFIRMED(<token>_LIVE_FAILED) at EOD mismatch.

    If structural is now ET9DNWF21C after E21Cn, live_attempt often still reads E21Cn from
    tracking that *prior* structural rung — that is not a fresh "E21Cn failed" try; the
    continuation rung is E21C(n+1). (Stale intraday tag off-market reconcile.)
    """
    nt = _state_text(new_tag).upper()
    pt = _state_text(prev_tag).upper()
    at = _state_text(attempt_tag).upper()
    if nt != "ET9DNWF21C":
        return at
    pn = _parse_e21c_num(pt)
    an = _parse_e21c_num(at)
    if pn is not None and an is not None and an == pn:
        return f"E21C{pn + 1}"
    return at


def _is_progression_predecessor(structural_tag: str, failed_attempt_tag: str) -> bool:
    st = _state_text(structural_tag).upper()
    fa = _state_text(failed_attempt_tag).upper()
    if not st or not fa:
        return False

    sb = _parse_b_num(st)
    fb = _parse_b_num(fa)
    if sb is not None and fb is not None and fb == sb - 1:
        return True

    se9 = _parse_e9ct_num(st)
    fe9 = _parse_e9ct_num(fa)
    if se9 is not None and fa.startswith("B"):
        return True
    if se9 is not None and fe9 is not None and fe9 == se9 - 1:
        return True

    if st == "ET9DNWF21C" and (fa.startswith("E9CT") or fa.startswith("B")):
        return True

    se21 = _parse_e21c_num(st)
    fe21 = _parse_e21c_num(fa)
    # Do not treat ET9DNWF21C as a progression predecessor of E21Cn for normalization:
    # E21Cn_CONFIRMED(ET9DNWF21C_FAILED) is a real live-vs-structural story, not legacy B1/B2 noise.
    if se21 is not None and fe21 is not None and fe21 == se21 - 1:
        return True

    return False


def _normalize_resolved_live_struct(tag: str, live_struct: str) -> str:
    """
    Normalize known invalid legacy reconciliations.
    Example: B2_CONFIRMED(B1_FAILED) -> B2_CONFIRMED.
    Previous structural stage (B1) is progression history, not today's failed live attempt.
    """
    t = _state_text(tag).upper()
    s = _state_text(live_struct).upper()
    if not t or not s:
        return _state_text(live_struct)
    confirmed_prefix = f"{t}_CONFIRMED("
    if s.startswith(confirmed_prefix) and s.endswith(")"):
        inner = s[len(confirmed_prefix) : -1].strip()
        for suf in ("_LIVE_FAILED", "_FAILED"):
            if inner.endswith(suf):
                failed_attempt = inner[: -len(suf)].strip()
                if _is_progression_predecessor(t, failed_attempt):
                    return f"{t}_CONFIRMED"
                break
    return _state_text(live_struct)


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

    reconcile_symptom: Dict[str, Any] | None = None

    # If EOD structural truth changed, reconcile prior live attempt to structural truth.
    structural_changed = (tag != prev_tag) or (evk != prev_evk)
    if structural_changed:
        live_token = _live_token_from_live_struct(prev_live_struct)
        live_token_source = "prev_live_struct"
        if not live_token and attempt_tag and _attempt_is_for_prev_evk(attempt_started_at, prev_evk):
            live_token = _state_text(attempt_tag).upper()
            live_token_source = "attempt_tag_same_day"

        # No live truth for that session day: do not manufacture a failure from stale tags.
        if not live_token:
            if prev_live_struct:
                d["live_struct_d"] = _normalize_resolved_live_struct(tag, prev_live_struct)
            else:
                d["live_struct_d"] = ""
        else:
            now_iso_reconcile = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
            structural_b = _extract_b_stage(tag)
            structural_e = _extract_e_stage(tag)
            failed_attempt = f"{live_token}_LIVE_FAILED"
            if (structural_b and structural_b == live_token) or (structural_e and structural_e == live_token):
                # Example: B2_LIVE_WATCH -> B2_CONFIRMED after EOD structural close.
                d["live_struct_d"] = f"{live_token}_CONFIRMED"
                attempt_status = "confirmed"
                attempt_reason = "eod_reconcile_confirmed"
                reconcile_symptom = {
                    "ts_ist": now_iso_reconcile,
                    "branch": "confirmed_match",
                    "new_tag": tag,
                    "new_evk": evk,
                    "prev_tag": prev_tag,
                    "prev_evk": prev_evk,
                    "live_attempt_tag": attempt_tag,
                    "live_token": live_token,
                    "live_token_source": live_token_source,
                    "prev_live_struct": prev_live_struct,
                    "live_struct_d_out": d.get("live_struct_d", ""),
                }
            else:
                # Example: B6_LIVE_WATCH -> B5_CONFIRMED(B6_LIVE_FAILED)
                if tag and tag != "—":
                    d["live_struct_d"] = f"{tag}_CONFIRMED({failed_attempt})"
                else:
                    d["live_struct_d"] = failed_attempt
                attempt_status = "failed"
                attempt_reason = f"eod_reconcile_to_{tag or 'UNKNOWN'}"
                if not attempt_invalidated_at:
                    attempt_invalidated_at = now_iso_reconcile
                reconcile_symptom = {
                    "ts_ist": now_iso_reconcile,
                    "branch": "failed_mismatch",
                    "new_tag": tag,
                    "new_evk": evk,
                    "prev_tag": prev_tag,
                    "prev_evk": prev_evk,
                    "live_attempt_tag": attempt_tag,
                    "live_token": live_token,
                    "live_token_source": live_token_source,
                    "prev_live_struct": prev_live_struct,
                    "structural_b": structural_b,
                    "structural_e": structural_e,
                    "failed_attempt_token": failed_attempt,
                    "live_struct_d_out": d.get("live_struct_d", ""),
                }
        # (end structural_changed reconcile)
    elif prev_live_struct:
        d["live_struct_d"] = _normalize_resolved_live_struct(tag, prev_live_struct)

    # Restore prior live-struct session fields (durable state) only when structural truth is same.
    pmeta = prev if isinstance(prev, dict) else {}
    if not structural_changed:
        for k in (
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
        # Intraday latch: first live_struct_d observed for the structural day key
        # is treated as the stable filterable truth for that day. Validity can be
        # tracked separately via attempt_status / track day.
        day_key = _state_text(evk)
        prev_day_key = _state_text(d.get("lsd_day_key", ""))
        if day_key and prev_day_key and prev_day_key != day_key:
            d["lsd_latch"] = ""
            d["lsd_day_status"] = ""
            d["lsd_day_key"] = day_key
        elif day_key and not prev_day_key:
            d["lsd_day_key"] = day_key

        latched = _state_text(d.get("lsd_latch", ""))
        if latched:
            d["live_struct_d"] = latched
        else:
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

            # If we produced an intraday state, latch it for the day.
            produced = _state_text(d.get("live_struct_d", ""))
            if produced and not _state_text(d.get("lsd_latch", "")):
                d["lsd_latch"] = produced
                d["lsd_day_status"] = "latched"

    live = _state_text(d.get("live_struct_d", ""))

    try:
        _ltp_f = float(ltp or 0.0)
        _e9_f = float(d.get("ema9_d", 0.0) or 0.0)
        _e21_f = float(d.get("ema21_d", 0.0) or 0.0)
    except (TypeError, ValueError):
        _ltp_f, _e9_f, _e21_f = 0.0, 0.0, 0.0
    live_track_focus = _infer_live_track_focus(tag, live, _ltp_f, _e9_f, _e21_f)

    meta = {
        "last_tag_d_structural": tag,
        "structural_event_key": evk,
        "live_struct_d": live,
        "live_track_focus": live_track_focus,
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
    if reconcile_symptom is not None:
        meta["reconcile_symptom"] = reconcile_symptom
    return (live, meta)

