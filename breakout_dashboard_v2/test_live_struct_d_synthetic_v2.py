from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime as _real_datetime
from unittest.mock import patch

from breakout_v2_app.logic.daily_transition import compute_live_struct_d


def _sample_ohlcv(n: int = 40) -> list[dict]:
    rows: list[dict] = []
    ts0 = 1775000000.0
    px = 100.0
    for i in range(n):
        o = px
        h = px + 1.2
        l = px - 0.8
        c = px + 0.6
        rows.append(
            {
                "ts": ts0 + i * 86400.0,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 1_000_000.0,
            }
        )
        px += 0.5
    return rows


@contextmanager
def _fake_now(iso_ts: str):
    fixed = _real_datetime.fromisoformat(iso_ts)

    class _PatchedDateTime(_real_datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            if tz is not None:
                return fixed.replace(tzinfo=tz)
            return fixed

    with patch("breakout_v2_app.logic.daily_transition.datetime", _PatchedDateTime):
        yield


def _run_case(name: str, fn):
    try:
        fn()
        print(f"PASS | {name}")
    except AssertionError as e:
        print(f"FAIL | {name} | {e}")


def main():
    ohlcv = _sample_ohlcv()

    def case_fresh_start_empty_off_market():
        with _fake_now("2026-05-08T18:45:00"):  # off market
            live, meta = compute_live_struct_d(
                structural_last_tag_d="B1",
                structural_event_key="2026-05-08",
                ltp=120.0,
                quote_ts=0.0,
                ohlcv_series=ohlcv,
                prev_state={},
            )
        assert live == "", f"expected empty, got {live!r}"

    def case_b_live_watch_intraday():
        with _fake_now("2026-05-11T10:00:00"):  # market open
            live, meta = compute_live_struct_d(
                structural_last_tag_d="B2",
                structural_event_key="2026-05-11",
                ltp=500.0,
                quote_ts=10_000_000_000_000.0,  # force-fresh synthetic heartbeat
                ohlcv_series=ohlcv,
                prev_state={},
            )
        assert "B2_LIVE_WATCH" in live, f"expected B2_LIVE_WATCH, got {live!r}"
        assert str(meta.get("live_attempt_status")) == "valid"

    def case_b_no_more_valid_intraday():
        with _fake_now("2026-05-11T10:05:00"):  # market open
            live, meta = compute_live_struct_d(
                structural_last_tag_d="B2",
                structural_event_key="2026-05-11",
                ltp=1.0,  # below ema9
                quote_ts=10_000_000_000_000.0,
                ohlcv_series=ohlcv,
                prev_state={"live_attempt_tag": "B2", "live_struct_d": "B2_LIVE_WATCH"},
            )
        assert "B2_NO_MORE_VALID" in live, f"expected invalidated state, got {live!r}"
        assert str(meta.get("live_attempt_status")) == "invalidated"

    def case_intraday_latches_first_live_struct_d():
        with _fake_now("2026-05-11T10:00:00"):  # market open
            live1, meta1 = compute_live_struct_d(
                structural_last_tag_d="B2",
                structural_event_key="2026-05-11",
                ltp=500.0,  # above ema9
                quote_ts=10_000_000_000_000.0,
                ohlcv_series=ohlcv,
                prev_state={},
            )
        assert live1 == "B2_LIVE_WATCH", f"expected watch, got {live1!r}"
        # Next tick would normally flip, but latch should keep the first value.
        with _fake_now("2026-05-11T10:05:00"):
            live2, meta2 = compute_live_struct_d(
                structural_last_tag_d="B2",
                structural_event_key="2026-05-11",
                ltp=1.0,  # below ema9
                quote_ts=10_000_000_000_000.0,
                ohlcv_series=ohlcv,
                prev_state={
                    "last_tag_d_structural": "B2",
                    "structural_event_key": "2026-05-11",
                    "live_struct_d": live1,
                    "lsd_latch": meta1.get("lsd_latch", ""),
                    "lsd_day_key": meta1.get("lsd_day_key", ""),
                    "lsd_day_status": meta1.get("lsd_day_status", ""),
                },
            )
        assert live2 == live1, f"expected latched value, got {live2!r}"

    def case_b_confirmed_on_eod_reconcile():
        with _fake_now("2026-05-12T18:00:00"):  # off market reconcile
            live, meta = compute_live_struct_d(
                structural_last_tag_d="B2",
                structural_event_key="2026-05-12",
                ltp=120.0,
                quote_ts=0.0,
                ohlcv_series=ohlcv,
                prev_state={
                    "last_tag_d_structural": "B1",
                    "structural_event_key": "2026-05-11",
                    "live_attempt_tag": "B2",
                    "live_attempt_status": "valid",
                    "live_struct_d": "B2_LIVE_WATCH",
                },
            )
        assert live == "B2_CONFIRMED", f"expected B2_CONFIRMED, got {live!r}"

    def case_b_failed_on_eod_reconcile():
        with _fake_now("2026-05-12T18:00:00"):
            live, meta = compute_live_struct_d(
                structural_last_tag_d="ET9DNWF21C",
                structural_event_key="2026-05-12",
                ltp=120.0,
                quote_ts=0.0,
                ohlcv_series=ohlcv,
                prev_state={
                    "last_tag_d_structural": "B1",
                    "structural_event_key": "2026-05-11",
                    "live_attempt_tag": "B2",
                    "live_attempt_status": "valid",
                    "live_struct_d": "B2_LIVE_WATCH",
                },
            )
        assert "B2_LIVE_FAILED" in live, f"expected failed trace, got {live!r}"

    def case_e_live_watch_and_confirmed():
        with _fake_now("2026-05-13T10:15:00"):  # intraday
            live1, meta1 = compute_live_struct_d(
                structural_last_tag_d="E9CT1",
                structural_event_key="2026-05-13",
                ltp=500.0,
                quote_ts=10_000_000_000_000.0,
                ohlcv_series=ohlcv,
                prev_state={},
            )
        assert live1.startswith("E9CT1_LIVE_WATCH"), f"expected E watch, got {live1!r}"
        with _fake_now("2026-05-14T18:00:00"):  # reconcile day
            live2, meta2 = compute_live_struct_d(
                structural_last_tag_d="E9CT1",
                structural_event_key="2026-05-14",
                ltp=100.0,
                quote_ts=0.0,
                ohlcv_series=ohlcv,
                prev_state={
                    "last_tag_d_structural": "E9CT1",
                    "structural_event_key": "2026-05-13",
                    "live_attempt_tag": "E9CT1",
                    "live_attempt_status": "valid",
                    "live_struct_d": "E9CT1_LIVE_WATCH",
                },
            )
        assert live2 == "E9CT1_CONFIRMED", f"expected E9CT1_CONFIRMED, got {live2!r}"

    def case_eod_reconcile_ignores_stale_attempt_without_live_struct():
        # Structural advances, but there is no live_struct evidence for the prev day,
        # and the attempt is stale (started on a different day key). We must not
        # manufacture a failure token from that stale attempt.
        with _fake_now("2026-05-11T18:00:00"):
            live, meta = compute_live_struct_d(
                structural_last_tag_d="ET9DNWF21C",
                structural_event_key="2026-05-11",
                ltp=120.0,
                quote_ts=0.0,
                ohlcv_series=ohlcv,
                prev_state={
                    "last_tag_d_structural": "E21C2",
                    "structural_event_key": "2026-05-08",
                    "live_attempt_tag": "E21C2",
                    "live_attempt_started_at": "2026-05-06 10:00:00",
                    "live_struct_d": "",
                },
            )
        assert live == "", f"expected empty (no live truth), got {live!r}"

    cases = [
        ("fresh start empty off market", case_fresh_start_empty_off_market),
        ("B live watch intraday", case_b_live_watch_intraday),
        ("B no more valid intraday", case_b_no_more_valid_intraday),
        ("intraday latches first live_struct_d", case_intraday_latches_first_live_struct_d),
        ("B confirmed on eod reconcile", case_b_confirmed_on_eod_reconcile),
        ("B failed on eod reconcile", case_b_failed_on_eod_reconcile),
        ("E live watch and confirmed", case_e_live_watch_and_confirmed),
        ("EOD reconcile ignores stale attempt without live_struct", case_eod_reconcile_ignores_stale_attempt_without_live_struct),
    ]

    for name, fn in cases:
        _run_case(name, fn)


if __name__ == "__main__":
    main()

