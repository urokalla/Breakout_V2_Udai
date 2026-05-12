"""Parity: V2Engine vector fastpath vs scalar math (no Reflex UI)."""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

if sys.version_info < (3, 9):
    pytest.skip("V2 engine import requires Python 3.9+ (zoneinfo)", allow_module_level=True)

os.environ["BREAKOUT_V2_VECTOR_FASTPATH"] = "1"

from breakout_v2_app.engine import V2Engine  # noqa: E402


def _scalar_daily(closes: list[float], last_live: float) -> tuple[float, float, float, float]:
    last_close = float(closes[-1])
    ref = float(max(closes[-11:-1])) if len(closes) >= 11 else float(closes[-1])
    prev = closes[-2] if len(closes) > 1 else closes[-1]
    chp = ((last_live / prev) - 1.0) * 100.0 if prev else 0.0
    pct_live = ((last_live / ref) - 1.0) * 100.0 if ref else 0.0
    return last_close, ref, chp, pct_live


def test_daily_vector_matches_scalar():
    rng = np.random.default_rng(99)
    for _ in range(30):
        n = int(rng.integers(5, 80))
        closes = (rng.random(n) * 50 + 100).tolist()
        last_live = float(closes[-1]) * float(rng.uniform(0.98, 1.02))
        sc = _scalar_daily(closes, last_live)
        vn = V2Engine._vector_fastpath_daily_numeric(closes, last_live)
        assert vn is not None
        assert abs(vn[0] - sc[0]) < 1e-9
        assert abs(vn[1] - sc[1]) < 1e-9
        assert abs(vn[3] - sc[2]) < 1e-6
        assert abs(vn[4] - sc[3]) < 1e-6


def test_daily_zero_ref_fallback():
    closes = [1.0] * 15
    closes[-1] = 0.0
    last_live = 0.0
    vn = V2Engine._vector_fastpath_daily_numeric(closes, last_live)
    sc = _scalar_daily(closes, last_live)
    assert vn is not None
    assert abs(vn[4] - sc[3]) < 1e-9
    assert abs(vn[3] - sc[2]) < 1e-9


def test_weekly_pct_chp_vector():
    last_live, prev, ref = 110.0, 100.0, 105.0
    vw = V2Engine._vector_fastpath_pct_chp(last_live, prev, ref)
    assert vw is not None
    pct_live, chp = vw
    assert abs(chp - 10.0) < 1e-9
    assert abs(pct_live - ((110 / 105) - 1) * 100) < 1e-9
