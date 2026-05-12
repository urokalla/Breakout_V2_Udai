"""
Vectorized helpers aligned with V2 daily row *numeric* conventions:

- ref = max(closes[-11:-1]) when len(closes) >= 11 else closes[-1]
  (see V2Engine._build_daily_row_from_ohlcv).
- pct_live = (ltp / ref - 1) * 100 when ref > 0
- chp vs previous *EOD* close: (ltp / prev - 1) * 100 (prev = closes[-2] when len>=2)

Structural LAST TAG D / compute_live_struct_d are *not* reproduced here — only
cheap level + live math suitable for nanosecond-class inner loops.
"""

from __future__ import annotations

import numpy as np


def pack_closes_left_pad(closes_per_symbol: list[np.ndarray], max_bars: int | None = None) -> np.ndarray:
    """
    Stack per-symbol 1D close series (oldest → newest) into a 2D matrix.
    Shorter series are left-padded with NaN so column -1 is the latest bar.

    If max_bars is set, each series is truncated to its last max_bars closes
    before packing (saves memory for long histories).
    """
    if not closes_per_symbol:
        return np.zeros((0, 0), dtype=np.float64)
    rows: list[np.ndarray] = []
    for s in closes_per_symbol:
        v = np.asarray(s, dtype=np.float64).ravel()
        if max_bars is not None and v.size > int(max_bars):
            v = v[-int(max_bars) :]
        rows.append(v)
    lengths = [r.size for r in rows]
    t = max(lengths)
    out = np.full((len(rows), t), np.nan, dtype=np.float64)
    for i, v in enumerate(rows):
        if v.size:
            out[i, t - v.size :] = v
    return out


def _strip_trailing_nans_rowwise(close_2d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Return (trimmed, valid_T) where trimmed[i, -valid_T[i]:] are finite closes
    oldest→newest at the right edge; leading columns may be nan (unused).
    """
    n, t = close_2d.shape
    finite = np.isfinite(close_2d)
    counts = finite.sum(axis=1).astype(np.int64)
    max_t = int(counts.max()) if n else 0
    if max_t == 0:
        return np.full((n, 0), np.nan), counts
    out = np.full((n, max_t), np.nan, dtype=np.float64)
    for i in range(n):
        row = close_2d[i]
        vals = row[np.isfinite(row)]
        if vals.size:
            out[i, -vals.size :] = vals
    return out, counts


def reference_levels_donchian_10_excl_last(close_2d: np.ndarray) -> np.ndarray:
    """
    Per row: ref = max(last 10 closes excluding the final bar) if at least 11
    valid closes exist; else ref = last close.

    close_2d: (N, T) — may contain leading NaNs from pack_closes_left_pad; only
    the trailing finite run per row is used.
    """
    trimmed, counts = _strip_trailing_nans_rowwise(np.asarray(close_2d, dtype=np.float64))
    n = trimmed.shape[0]
    if n == 0:
        return np.zeros(0, dtype=np.float64)
    t = trimmed.shape[1]
    ref = np.empty(n, dtype=np.float64)
    ref[:] = np.nan
    if t == 0:
        return ref
    last = trimmed[:, -1]
    ref[:] = last
    ge11 = counts >= 11
    if np.any(ge11):
        win = trimmed[ge11, -11:-1]
        ref[ge11] = np.max(win, axis=1)
    return ref


def reference_levels_donchian_10_excl_last_dense(close_2d: np.ndarray) -> np.ndarray:
    """
    Fast path: (N, T) all finite, T >= 1. No NaNs. Undefined if NaNs present.
    """
    m = np.asarray(close_2d, dtype=np.float64)
    n, t = m.shape
    if n == 0:
        return np.zeros(0, dtype=np.float64)
    if t >= 11:
        return np.max(m[:, -11:-1], axis=1)
    return m[:, -1].copy()


def live_pct_vs_ref(ltp: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """(ltp / ref - 1) * 100 with inf where ref<=0 or non-finite."""
    ltp = np.asarray(ltp, dtype=np.float64)
    ref = np.asarray(ref, dtype=np.float64)
    out = np.full_like(ltp, np.nan, dtype=np.float64)
    ok = np.isfinite(ltp) & np.isfinite(ref) & (ref > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        out[ok] = (ltp[ok] / ref[ok] - 1.0) * 100.0
    return out


def chp_vs_prev_close(ltp: np.ndarray, prev_close: np.ndarray) -> np.ndarray:
    """Change vs previous bar close: (ltp / prev - 1) * 100."""
    ltp = np.asarray(ltp, dtype=np.float64)
    prev_close = np.asarray(prev_close, dtype=np.float64)
    out = np.full_like(ltp, np.nan, dtype=np.float64)
    ok = np.isfinite(ltp) & np.isfinite(prev_close) & (prev_close > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        out[ok] = (ltp[ok] / prev_close[ok] - 1.0) * 100.0
    return out


def live_breakout_flags(ltp: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """Boolean: live price strictly above ref (both finite)."""
    ltp = np.asarray(ltp, dtype=np.float64)
    ref = np.asarray(ref, dtype=np.float64)
    return np.isfinite(ltp) & np.isfinite(ref) & (ltp > ref)


def prev_close_from_matrix(close_2d: np.ndarray) -> np.ndarray:
    """Per row: previous close = closes[-2] if >=2 bars else last close."""
    trimmed, counts = _strip_trailing_nans_rowwise(np.asarray(close_2d, dtype=np.float64))
    n = trimmed.shape[1]
    out = np.full(trimmed.shape[0], np.nan, dtype=np.float64)
    if n == 0:
        return out
    last = trimmed[:, -1]
    out[:] = last
    ge2 = counts >= 2
    if np.any(ge2):
        out[ge2] = trimmed[ge2, -2]
    return out


def slow_reference_engine_style(closes_1d: np.ndarray) -> float:
    """Scalar reference for one symbol — used in tests only."""
    c = np.asarray(closes_1d, dtype=np.float64).ravel()
    c = c[np.isfinite(c)]
    if c.size == 0:
        return float("nan")
    if c.size >= 11:
        return float(np.max(c[-11:-1]))
    return float(c[-1])
