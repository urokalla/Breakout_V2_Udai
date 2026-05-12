import numpy as np

from experiments.vector_breakout.core import (
    chp_vs_prev_close,
    live_breakout_flags,
    live_pct_vs_ref,
    pack_closes_left_pad,
    prev_close_from_matrix,
    reference_levels_donchian_10_excl_last,
    reference_levels_donchian_10_excl_last_dense,
    slow_reference_engine_style,
)


def test_ref_short_series():
    s = np.array([10.0, 11.0, 12.0])
    m = pack_closes_left_pad([s])
    r = reference_levels_donchian_10_excl_last(m)
    assert r.shape == (1,)
    assert abs(r[0] - 12.0) < 1e-12


def test_ref_long_series():
    s = np.arange(20.0, 31.0)
    m = pack_closes_left_pad([s])
    r = reference_levels_donchian_10_excl_last(m)
    assert abs(r[0] - float(np.max(s[-11:-1]))) < 1e-12


def test_multi_symbol_parity():
    rng = np.random.default_rng(7)
    series = [rng.random(int(rng.integers(5, 60))) * 10 + 40 for _ in range(120)]
    mat = pack_closes_left_pad(series)
    vec = reference_levels_donchian_10_excl_last(mat)
    slow = np.array([slow_reference_engine_style(np.asarray(x)) for x in series])
    ok = np.isfinite(vec) & np.isfinite(slow)
    assert np.allclose(vec[ok], slow[ok], rtol=0, atol=1e-9)


def test_prev_close_and_chp():
    s = np.array([1.0, 2.0, 4.0])
    m = pack_closes_left_pad([s])
    prev = prev_close_from_matrix(m)
    assert abs(prev[0] - 2.0) < 1e-12
    chp = chp_vs_prev_close(np.array([3.0]), prev[:1])
    assert abs(chp[0] - 50.0) < 1e-9


def test_dense_nan_free():
    m = np.ones((5, 15), dtype=np.float64) * 3
    m[:, -1] = 4.0
    r = reference_levels_donchian_10_excl_last_dense(m)
    assert np.all(r == 3.0)


def test_flags_shape():
    ltp = np.array([1.0, np.nan])
    ref = np.array([0.5, 1.0])
    f = live_breakout_flags(ltp, ref)
    assert f[0] and not f[1]


def test_live_pct_nan_when_bad_ref():
    p = live_pct_vs_ref(np.array([1.0]), np.array([0.0]))
    assert np.isnan(p[0])
