#!/usr/bin/env python3
"""Run: python experiments/vector_breakout/self_check.py from breakout_dashboard_v2/."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from experiments.vector_breakout.core import (  # noqa: E402
    live_breakout_flags,
    live_pct_vs_ref,
    pack_closes_left_pad,
    reference_levels_donchian_10_excl_last,
    reference_levels_donchian_10_excl_last_dense,
    slow_reference_engine_style,
)


def _assert_close(a: np.ndarray, b: np.ndarray, tol: float = 1e-9) -> None:
    m = np.isfinite(a) & np.isfinite(b)
    assert np.allclose(a[m], b[m], rtol=0, atol=tol), (a, b)


def test_packed_vs_slow() -> None:
    rng = np.random.default_rng(0)
    series = []
    for _ in range(50):
        t = rng.integers(3, 40)
        series.append(rng.random(t) * 100 + 50)
    mat = pack_closes_left_pad(series)
    vec = reference_levels_donchian_10_excl_last(mat)
    slow = np.array([slow_reference_engine_style(s) for s in series], dtype=np.float64)
    _assert_close(vec, slow)


def test_dense_matches() -> None:
    rng = np.random.default_rng(1)
    m = rng.random((100, 30)) * 50 + 100
    a = reference_levels_donchian_10_excl_last_dense(m)
    b = reference_levels_donchian_10_excl_last(m)
    _assert_close(a, b)


def test_live_pct() -> None:
    ref = np.array([100.0, 200.0])
    ltp = np.array([101.0, 190.0])
    p = live_pct_vs_ref(ltp, ref)
    assert abs(p[0] - 1.0) < 1e-12
    assert abs(p[1] - (-5.0)) < 1e-12


def test_breakout_flags() -> None:
    ref = np.array([10.0, 10.0])
    ltp = np.array([10.5, 9.5])
    f = live_breakout_flags(ltp, ref)
    assert f[0] and not f[1]


def bench(n_sym: int = 2000, t_bars: int = 300) -> None:
    rng = np.random.default_rng(42)
    m = rng.random((n_sym, t_bars), dtype=np.float64) * 100 + 50
    t0 = time.perf_counter()
    for _ in range(200):
        reference_levels_donchian_10_excl_last_dense(m)
        ltp = m[:, -1] * 1.001
        ref = reference_levels_donchian_10_excl_last_dense(m)
        live_pct_vs_ref(ltp, ref)
        live_breakout_flags(ltp, ref)
    dt = time.perf_counter() - t0
    per = dt / 200 / n_sym * 1e9
    print(f"bench n={n_sym} T={t_bars} iters=200 total={dt:.3f}s  ~{per:.1f} ns/symbol/iter (dense path)")


def main() -> int:
    test_packed_vs_slow()
    test_dense_matches()
    test_live_pct()
    test_breakout_flags()
    print("vector_breakout self_check: OK")
    bench()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
