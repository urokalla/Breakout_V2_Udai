from __future__ import annotations

import os
from datetime import date, datetime, time as dt_time
from zoneinfo import ZoneInfo

import numpy as np

_IST = ZoneInfo("Asia/Kolkata")
TAG_ET9_WAIT_F21C = "ET9DNWF21C"


def _nse_ist_session_date_for_when(ts: float) -> date | None:
    try:
        t = float(ts)
        if t <= 0.0 or not bool(np.isfinite(t)):
            return None
        return datetime.fromtimestamp(t, tz=_IST).date()
    except Exception:
        return None


def _nse_ist_cash_eod_ts_for_session_date(d: date) -> float:
    h = int(os.getenv("STRUCTURAL_EOD_IST_HOUR", "15"))
    m = int(os.getenv("STRUCTURAL_EOD_IST_MINUTE", "30"))
    return float(datetime.combine(d, dt_time(h, m), tzinfo=_IST).timestamp())


def _daily_struct_event_ts(ts_raw: float) -> float:
    try:
        t = float(ts_raw or 0.0)
        if t <= 0.0 or not bool(np.isfinite(t)):
            return 0.0
        d = _nse_ist_session_date_for_when(t)
        if d is None:
            return t
        return _nse_ist_cash_eod_ts_for_session_date(d)
    except Exception:
        return float(ts_raw or 0.0)


def _bar_date_key_from_ts(ts: float) -> str:
    try:
        d = _nse_ist_session_date_for_when(float(ts))
        return d.isoformat() if d is not None else ""
    except Exception:
        return ""


def _tag_e9ct(n: int) -> str:
    return f"E9CT{int(n)}"


def _tag_power_e9ct(base: str) -> str:
    return f"{base}+E9CT"


def _ema_series(values: np.ndarray, n: int) -> np.ndarray:
    v = np.asarray(values, dtype=np.float64)
    if v.size == 0 or n <= 1:
        return v.copy()
    alpha = 2.0 / (float(n) + 1.0)
    out = np.empty_like(v, dtype=np.float64)
    out[:] = np.nan
    if v.size >= n:
        seed = float(np.mean(v[:n]))
        out[n - 1] = seed
        prev = seed
        for i in range(n, v.size):
            prev = alpha * float(v[i]) + (1.0 - alpha) * prev
            out[i] = prev
    return out


def compute_structural_last_tag_d(ohlcv: list[dict], don_len: int = 10) -> tuple[str, str, str]:
    """
    V2-local structural LAST TAG D calculator, ported from RS minimal cycle replay semantics.
    Returns: (last_tag_d, when_ist_text, structural_event_key_yyyy_mm_dd)
    """
    if not ohlcv or len(ohlcv) < 6:
        return ("—", "—", "-")

    try:
        hv = np.asarray(
            [
                [
                    float(x.get("ts", 0.0) or 0.0),
                    float(x.get("open", 0.0) or 0.0),
                    float(x.get("high", 0.0) or 0.0),
                    float(x.get("low", 0.0) or 0.0),
                    float(x.get("close", 0.0) or 0.0),
                    float(x.get("volume", 0.0) or 0.0),
                ]
                for x in ohlcv
            ],
            dtype=np.float64,
        )
    except Exception:
        return ("—", "—", "-")

    if hv.shape[0] < 6:
        return ("—", "—", "-")

    now_dt = datetime.now(_IST)
    now_date = now_dt.date()
    try:
        last_date = datetime.fromtimestamp(float(hv[-1][0]), tz=_IST).date()
    except Exception:
        return ("—", "—", "-")

    if last_date < now_date:
        i = len(hv) - 1
    elif last_date > now_date:
        i = len(hv) - 2
    else:
        i = len(hv) - 2
        enabled = os.getenv("STRUCTURAL_SAMEDAY_AFTER_EOD_ENABLED", "1").strip().lower() in ("1", "true", "yes")
        eod_h = int(os.getenv("STRUCTURAL_SAMEDAY_AFTER_EOD_IST_HOUR", "15"))
        eod_m = int(os.getenv("STRUCTURAL_SAMEDAY_AFTER_EOD_IST_MINUTE", "30"))
        if enabled and now_dt.weekday() < 5 and (now_dt.hour, now_dt.minute) >= (eod_h, eod_m):
            i = len(hv) - 1

    if i < 3:
        return ("—", "—", "-")

    close_ser = np.asarray(hv[:, 4], dtype=np.float64)
    highs = np.asarray(hv[:, 2], dtype=np.float64)
    lows = np.asarray(hv[:, 3], dtype=np.float64)
    e9_ser = _ema_series(close_ser, 9)
    e21_ser = _ema_series(close_ser, 21)

    if not (np.isfinite(e9_ser[i]) and np.isfinite(e21_ser[i]) and np.isfinite(close_ser[i]) and np.isfinite(lows[i])):
        return ("—", "—", "-")

    bar_key = _bar_date_key_from_ts(float(hv[i][0]))
    if not bar_key:
        return ("—", "—", "-")

    st_state = 0
    st_below21 = 0
    st_b = 0
    st_e9t = 0
    st_e21c = 0
    st_rst = 0
    st_last_tag = "—"
    st_last_ts = 0.0

    try:
        dlen = max(2, int(don_len))
        for j in range(3, i + 1):
            if not (np.isfinite(e9_ser[j]) and np.isfinite(e21_ser[j]) and np.isfinite(close_ser[j])):
                continue
            c = float(close_ser[j])
            pc = float(close_ser[j - 1])
            lo = float(lows[j])
            e9j = float(e9_ser[j])
            e21j = float(e21_ser[j])
            trend = c > e9j and e9j > e21j

            brk = False
            if j >= dlen + 1:
                don_c = float(np.max(highs[(j - dlen) : j]))
                don_p = float(np.max(highs[(j - dlen - 1) : (j - 1)]))
                brk = bool(trend and c > don_c and pc <= don_p)

            st_below21 = st_below21 + 1 if c < e21j else 0

            if st_state > 0 and st_below21 >= 2:
                st_rst += 1
                st_state = 0
                st_b = 0
                st_e9t = 0
                st_e21c = 0
                st_last_tag = "RST"
                st_last_ts = _daily_struct_event_ts(float(hv[j][0]))
            elif brk:
                st_state = 1
                st_b += 1
                st_last_tag = f"B{st_b}"
                if lo <= e9j:
                    st_last_tag = _tag_power_e9ct(st_last_tag)
                st_last_ts = _daily_struct_event_ts(float(hv[j][0]))
            elif st_state > 0:
                if st_state == 1 and lo < e9j and c > e9j and not brk:
                    st_e9t += 1
                    st_last_tag = _tag_e9ct(st_e9t)
                    st_last_ts = _daily_struct_event_ts(float(hv[j][0]))
                elif st_state == 1 and c < e9j:
                    st_state = 2
                    st_last_tag = TAG_ET9_WAIT_F21C
                    st_last_ts = _daily_struct_event_ts(float(hv[j][0]))
                elif st_state == 1 and c >= e9j and not brk:
                    pco = float(close_ser[j - 1])
                    e21_prev = float(e21_ser[j - 1])
                    if pco < e21_prev and c > e21j:
                        st_e21c += 1
                        st_last_tag = f"E21C{st_e21c}"
                        st_last_ts = _daily_struct_event_ts(float(hv[j][0]))

                if st_state == 2 and c > e9j:
                    st_state = 1
                    if c > e21j:
                        st_e21c += 1
                        st_last_tag = f"E21C{st_e21c}"
                    else:
                        st_e9t += 1
                        st_last_tag = _tag_e9ct(st_e9t)
                    st_last_ts = _daily_struct_event_ts(float(hv[j][0]))
    except Exception:
        return ("—", "—", "-")

    if st_last_ts > 0:
        when = datetime.fromtimestamp(st_last_ts, tz=_IST).strftime("%Y-%m-%d %H:%M:%S")
    else:
        when = "—"
    return (str(st_last_tag or "—"), str(when), bar_key or "-")

