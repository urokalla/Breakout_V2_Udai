import reflex as rx
import time
import asyncio
import os
import gc
from datetime import datetime, timezone

from .engine import get_engine


def _nse_cash_session_ist_open() -> bool:
    """Rough NSE cash session Mon–Fri Asia/Kolkata 09:15–15:30. Used to slow polling off-hours."""
    try:
        from zoneinfo import ZoneInfo

        ist = ZoneInfo("Asia/Kolkata")
    except Exception:
        return True
    now = datetime.now(ist)
    if now.weekday() >= 5:
        return False
    m = now.hour * 60 + now.minute
    return (9 * 60 + 15) <= m < (15 * 60 + 31)


class BreakoutClockState(rx.State):
    clock_timeframe: str = "daily"
    universe: str = "Nifty 50"
    search_query: str = ""
    timing_filter: str = "ALL"
    results: list[dict] = []
    total_count: int = 0
    symbol_count_total: int = 0
    symbol_count_loaded: int = 0
    live_struct_rows: int = 0
    live_struct_rows_raw: int = 0
    current_page: int = 1
    page_size: int = 50
    filter_brk_stage: str = "ALL"
    filter_mrs_grid: str = "ALL"
    filter_wmrs_slope: str = "ALL"
    filter_m_rsi2: str = "ALL"
    filter_profile: str = "ALL"
    status_message: str = "Offline"
    last_sync: str = "-"
    eod_sync_status: str = "EOD_SYNC_UNKNOWN"
    eod_expected_date: str = "-"
    eod_fresh_count: int = 0
    eod_total_count: int = 0
    eod_stale_count: int = 0
    eod_sync_pct: float = 0.0
    eod_last_checked_ist: str = "-"
    sort_timing_key: str = "symbol"
    sort_timing_desc: bool = False
    auto_refresh_started: bool = False
    poll_heartbeat: int = 0
    expanded_path_symbol: str = ""
    ops_snapshot_age_sec: int = 0
    ops_db_last_write: str = "-"
    ops_src_shm: int = 0
    ops_src_db: int = 0
    ops_src_api: int = 0
    ops_src_na: int = 0
    structural_today_count: int = 0
    structural_today_b: int = 0
    structural_today_e9ct: int = 0
    structural_today_et9: int = 0
    structural_today_e21c: int = 0
    structural_today_rst: int = 0
    # Daily POST EOD chips: ALL | TODAY | B | E9CT | ET9 | E21C | RST (intersects with other filters).
    structural_today_bucket: str = "ALL"
    _sorted_symbol_cache_key: str = ""
    _sorted_symbols: list[str] = []

    @staticmethod
    def _debug_enabled() -> bool:
        return str(os.getenv("BREAKOUT_V2_DEBUG_TIMING", "") or "").strip().lower() in ("1", "true", "yes")

    @staticmethod
    def _dbg(msg: str) -> None:
        if not BreakoutClockState._debug_enabled():
            return
        try:
            print(f"[breakout_v2_dbg] {msg}", flush=True)
        except Exception:
            pass

    @staticmethod
    def _is_live_struct_mismatch(last_tag: str, live_struct_d: str) -> bool:
        tag = str(last_tag or "").strip().upper()
        live = str(live_struct_d or "").strip().upper()
        if not tag or not live:
            return False
        # Composite structural Bn+E9CT: live_struct often confirms Bn only (B stage), not the full tag string.
        # Example: Last Tag D = B4+E9CT, Live_struct_d = B4_CONFIRMED — not a mismatch.
        b_base = ""
        if "+E9CT" in tag:
            b_base = tag.split("+", 1)[0].strip()
        # Only validate resolved EOD outcomes; intraday watch/invalid states are allowed drift.
        if "_CONFIRMED(" in live:
            lhs = live.split("_CONFIRMED(", 1)[0].strip()
            if not lhs:
                return False
            if b_base and lhs == b_base:
                return False
            return lhs != tag
        if live.endswith("_CONFIRMED"):
            lhs = live[: -len("_CONFIRMED")].strip()
            if not lhs:
                return False
            if b_base and lhs == b_base:
                return False
            return lhs != tag
        return False

    @rx.var
    def total_pages(self) -> int:
        ps = max(1, int(self.page_size))
        return max(1, (int(self.total_count) + ps - 1) // ps)

    async def on_load(self):
        # Always re-arm polling on page load; Reflex can restore state where a previous
        # flag is True but no active background loop exists after reconnect/reload.
        self.auto_refresh_started = False
        self._reload()
        return BreakoutClockState.start_auto_refresh

    @rx.event(background=True)
    async def start_auto_refresh(self):
        async with self:
            if self.auto_refresh_started:
                return
            self.auto_refresh_started = True
        try:
            base_poll_sec = max(0.5, float(os.getenv("DASHBOARD_POLL_INTERVAL_SEC", "1")))
        except Exception:
            base_poll_sec = 1.0

        while True:
            # Nifty500+ can be expensive to snapshot + filter + sort every second.
            # Slow the cadence automatically when universe is large.
            async with self:
                n = int(self.symbol_count_total or 0)
            poll_sec = float(base_poll_sec)
            if n >= 400:
                poll_sec = max(poll_sec, 5.0)
            elif n >= 200:
                poll_sec = max(poll_sec, 3.0)
            # Outside NSE cash hours parquet/quotes barely move — avoid 1s snapshot loops burning 1 CPU.
            if not _nse_cash_session_ist_open():
                try:
                    off_floor = float(os.getenv("BREAKOUT_V2_POLL_SEC_OFFHOURS", "60"))
                except Exception:
                    off_floor = 60.0
                poll_sec = max(poll_sec, max(off_floor, float(base_poll_sec)))
            await asyncio.sleep(poll_sec)
            async with self:
                self.poll_heartbeat += 1
                self._reload()

    def _apply_filters(self, rows: list[dict]) -> list[dict]:
        out = list(rows)
        tf = (self.timing_filter or "ALL").strip().upper()
        if tf == "LIVE_STRUCT_ONLY":
            # Live-only means rows with an actual live_struct_d state value.
            out = [r for r in out if bool(str(r.get("live_struct_d", "")).strip())]
        elif tf in ("D_BRK", "W_BRK", "LIVE", "SUSTAINED", "SUSTAINED_W"):
            out = [r for r in out if bool(r.get("is_breakout"))]
        elif tf in ("NOT_SUSTAINED",):
            out = [r for r in out if not bool(r.get("is_breakout"))]
        elif tf in ("E_TIMING", "E_SUSTAINED"):
            key = "last_tag" if self.clock_timeframe == "daily" else "last_tag_w"
            out = [r for r in out if str(r.get(key, "")).upper().startswith("E")]

        stage = (self.filter_brk_stage or "ALL").strip().upper()
        if stage != "ALL":
            key = "last_tag" if self.clock_timeframe == "daily" else "last_tag_w"
            out = [r for r in out if str(r.get(key, "")).upper().startswith(stage)]

        tag_pref = (self.filter_m_rsi2 or "ALL").strip().upper()
        if tag_pref != "ALL":
            key = "last_tag" if self.clock_timeframe == "daily" else "last_tag_w"
            out = [r for r in out if str(r.get(key, "")).upper().startswith(tag_pref)]

        # Approximate old profile buckets using available storage-only metrics.
        prof = (self.filter_profile or "ALL").strip().upper()
        if prof == "ELITE":
            out = [r for r in out if bool(r.get("is_breakout")) and float(r.get("bars", 0)) >= 80]
        elif prof == "LEADER":
            out = [r for r in out if bool(r.get("is_breakout")) and float(r.get("chp", 0.0)) >= 0]
        elif prof == "RISING":
            out = [r for r in out if float(r.get("chp", 0.0)) > 1.0]
        elif prof == "LAGGARD":
            out = [r for r in out if float(r.get("chp", 0.0)) < -1.0]
        elif prof == "FADING":
            out = [r for r in out if float(r.get("chp", 0.0)) < 0]
        elif prof == "BASELINE":
            out = [r for r in out if -1.0 <= float(r.get("chp", 0.0)) <= 1.0]

        # Trend filters: keep semantics deterministic for storage-only mode.
        if (self.filter_mrs_grid or "ALL").strip().upper() == "TREND_OK":
            out = [r for r in out if bool(r.get("is_breakout")) or float(r.get("chp", 0.0)) >= 0]
        if (self.filter_wmrs_slope or "ALL").strip().upper() == "POS":
            out = [r for r in out if float(r.get("chp", 0.0)) >= 0]

        # POST EOD structural-today chips (daily only; matches sidebar counter logic).
        if self.clock_timeframe == "daily":
            bstk = (self.structural_today_bucket or "ALL").strip().upper()
            lt_key = "last_tag"
            if bstk == "TODAY":
                out = [r for r in out if bool(r.get("last_tag_is_today_event"))]
            elif bstk == "B":
                out = [
                    r
                    for r in out
                    if bool(r.get("last_tag_is_today_event"))
                    and str(r.get(lt_key, "") or "").strip().upper().startswith("B")
                ]
            elif bstk == "E9CT":
                out = [
                    r
                    for r in out
                    if bool(r.get("last_tag_is_today_event"))
                    and str(r.get(lt_key, "") or "").strip().upper().startswith("E9CT")
                ]
            elif bstk == "ET9":
                out = [
                    r
                    for r in out
                    if bool(r.get("last_tag_is_today_event"))
                    and str(r.get(lt_key, "") or "").strip().upper() == "ET9DNWF21C"
                ]
            elif bstk == "E21C":
                out = [
                    r
                    for r in out
                    if bool(r.get("last_tag_is_today_event"))
                    and str(r.get(lt_key, "") or "").strip().upper().startswith("E21C")
                ]
            elif bstk == "RST":
                out = [
                    r
                    for r in out
                    if bool(r.get("last_tag_is_today_event"))
                    and str(r.get(lt_key, "") or "").strip().upper() == "RST"
                ]
        return out

    def _hydrate_from_snapshot(self, snap: dict, t0: float, t1: float) -> None:
        """Apply engine snapshot to UI fields (used by _reload and async universe switch)."""
        if self._debug_enabled():
            phases = snap.get("_debug_snapshot_phases_ms") if isinstance(snap, dict) else None
            if isinstance(phases, dict) and phases:
                self._dbg(
                    "snapshot_phases "
                    + " ".join(f"{k}={int(v)}ms" for k, v in phases.items())
                )
        rows_all = snap.get("daily_rows", []) if self.clock_timeframe == "daily" else snap.get("weekly_rows", [])
        t2 = time.perf_counter()
        sym_map = {str(r.get("symbol", "")).upper(): r for r in rows_all if str(r.get("symbol", "")).strip()}
        # Structural "did something today" counters should be computed on the full universe,
        # after EOD sync, independent of UI filters/search/pagination.
        if self.clock_timeframe == "daily":
            today_rows = [r for r in rows_all if bool(r.get("last_tag_is_today_event"))]
            self.structural_today_count = len(today_rows)
            def _tag(x: dict) -> str:
                return str(x.get("last_tag", "") or "").strip().upper()
            self.structural_today_b = len([r for r in today_rows if _tag(r).startswith("B")])
            self.structural_today_e9ct = len([r for r in today_rows if _tag(r).startswith("E9CT")])
            self.structural_today_et9 = len([r for r in today_rows if _tag(r) == "ET9DNWF21C"])
            self.structural_today_e21c = len([r for r in today_rows if _tag(r).startswith("E21C")])
            self.structural_today_rst = len([r for r in today_rows if _tag(r) == "RST"])
        rows = rows_all
        t3 = time.perf_counter()
        rows = self._apply_filters(rows)
        t4 = time.perf_counter()
        # Counter should represent actual live-struct presence, not breakout tag count.
        live_struct_total = len([r for r in rows if bool(str(r.get("live_struct_d", "")).strip())])
        q = (self.search_query or "").strip().upper()
        if q:
            rows = [r for r in rows if q in str(r.get("symbol", "")).upper()]
        key = self.sort_timing_key or "symbol"
        cache_key = "|".join(
            [
                str(self.clock_timeframe),
                str(self.universe),
                str(self.timing_filter),
                str(self.filter_brk_stage),
                str(self.filter_mrs_grid),
                str(self.filter_wmrs_slope),
                str(self.filter_m_rsi2),
                str(self.filter_profile),
                str(self.structural_today_bucket),
                q,
                str(key),
                "desc" if self.sort_timing_desc else "asc",
            ]
        )
        if cache_key == self._sorted_symbol_cache_key and self._sorted_symbols:
            rows = [sym_map[s] for s in self._sorted_symbols if s in sym_map]
            cache_hit = True
        else:
            try:
                rows = sorted(rows, key=lambda r: r.get(key, ""), reverse=self.sort_timing_desc)
            except Exception:
                pass
            self._sorted_symbol_cache_key = cache_key
            self._sorted_symbols = [str(r.get("symbol", "")).upper() for r in rows if str(r.get("symbol", "")).strip()]
            cache_hit = False
        t5 = time.perf_counter()
        self.total_count = len(rows)
        if self.current_page > self.total_pages:
            self.current_page = self.total_pages
        page_rows = rows[(self.current_page - 1) * self.page_size : self.current_page * self.page_size]
        self.results = [self._format_row(r) for r in page_rows]
        self.live_struct_rows = live_struct_total
        self.live_struct_rows_raw = self.live_struct_rows
        symbol_count = int(snap.get("symbol_count", 0))
        symbol_loaded = int(snap.get("symbol_count_loaded", symbol_count))
        self.symbol_count_total = symbol_count
        self.symbol_count_loaded = symbol_loaded
        if symbol_count == 0:
            self.status_message = "NO_UNIVERSE_SYMBOLS"
        elif not rows:
            self.status_message = "NO_HISTORY_DATA"
        else:
            self.status_message = "READY_PARTIAL" if symbol_loaded < symbol_count else "READY"
        self.last_sync = time.strftime("%Y-%m-%d %H:%M:%S")
        eod = snap.get("eod_sync", {}) if isinstance(snap, dict) else {}
        self.eod_sync_status = str(eod.get("status") or "EOD_SYNC_UNKNOWN")
        self.eod_total_count = int(eod.get("total_count") or 0)
        self.eod_fresh_count = int(eod.get("fresh_count") or 0)
        self.eod_stale_count = int(eod.get("stale_count") or 0)
        self.eod_sync_pct = float(eod.get("sync_pct") or 0.0)
        self.eod_expected_date = str(eod.get("expected_date") or "-")
        self.eod_last_checked_ist = self.last_sync
        # Ops metrics (daily-focused): snapshot age, DB write recency, and quote source distribution.
        if self.clock_timeframe == "daily":
            now_s = time.time()
            ts_vals = [float(r.get("quote_ts", 0.0) or 0.0) for r in rows_all if float(r.get("quote_ts", 0.0) or 0.0) > 0]
            if ts_vals:
                self.ops_snapshot_age_sec = max(0, int(now_s - max(ts_vals)))
            else:
                self.ops_snapshot_age_sec = 0
            self.ops_db_last_write = str(get_engine().transitions.get_daily_last_write_ts() or "-")
            self.ops_src_shm = len([r for r in rows_all if str(r.get("quote_source", "")).strip().lower() == "scanner_shm"])
            self.ops_src_db = len([r for r in rows_all if str(r.get("quote_source", "")).strip().lower() == "postgres_live_state"])
            self.ops_src_api = len([r for r in rows_all if str(r.get("quote_source", "")).strip().lower() not in ("", "scanner_shm", "postgres_live_state", "placeholder")])
            self.ops_src_na = len([r for r in rows_all if str(r.get("quote_source", "")).strip().lower() in ("", "placeholder")])

        # Debug timing + GC pressure hints (no external deps).
        if self._debug_enabled():
            try:
                gc_counts = gc.get_count()
            except Exception:
                gc_counts = (0, 0, 0)
            self._dbg(
                "reload "
                f"universe={self.universe!r} tf={self.timing_filter!r} "
                f"rows_all={len(rows_all)} rows_filtered={len(rows)} "
                f"cache_hit={cache_hit} "
                f"t_snapshot_ms={int((t1-t0)*1000)} "
                f"t_rows_ms={int((t2-t1)*1000)} "
                f"t_filter_ms={int((t4-t3)*1000)} "
                f"t_sort_ms={int((t5-t4)*1000)} "
                f"t_total_ms={int((t5-t0)*1000)} "
                f"gc={gc_counts}"
            )

    def _reload(self):
        t0 = time.perf_counter()
        snap = get_engine().snapshot(universe=self.universe)
        t1 = time.perf_counter()
        self._hydrate_from_snapshot(snap, t0, t1)

    @staticmethod
    def _format_row(r: dict) -> dict:
        sym = r.get("symbol", "")
        sym_tv = str(sym or "").strip().upper()
        tv_href = f"https://www.tradingview.com/chart/?symbol=NSE:{sym_tv}" if sym_tv else "#"
        last = r.get("last", "—")
        ref = r.get("ref", "—")
        is_breakout = bool(r.get("is_breakout"))
        tag_d = str(r.get("last_tag", "—"))
        tag_w = str(r.get("last_tag_w", tag_d))
        tag_today_event = bool(r.get("last_tag_is_today_event"))
        live_struct_d_raw = str(r.get("live_struct_d", "")).strip()
        _st = str(r.get("live_struct_attempt_status", "")).strip()
        _rs = str(r.get("live_struct_attempt_reason", "")).strip()
        if _st and _rs:
            live_struct_attempt_status = f"{_st} · {_rs}"
        elif _st:
            live_struct_attempt_status = _st
        else:
            live_struct_attempt_status = "—"
        live_struct_w_raw = str(r.get("live_struct_w", "")).strip()
        live_struct_d = live_struct_d_raw if live_struct_d_raw else "—"
        live_struct_w = live_struct_w_raw if live_struct_w_raw else "—"
        chp_val = r.get("chp", "—")
        chp_num = float(chp_val) if isinstance(chp_val, (int, float)) else None
        chp_text = f"{chp_num:+.2f}%" if chp_num is not None else "—"
        chp_color = "#00FF00" if (chp_num is not None and chp_num >= 0) else "#FF4D4F"
        pct_d = r.get("brk_move_live_pct", "—")
        pct_w = r.get("brk_move_live_pct_w", "—")
        pct_d_text = f"{float(pct_d):+.2f}%" if isinstance(pct_d, (int, float)) else "—"
        pct_w_text = f"{float(pct_w):+.2f}%" if isinstance(pct_w, (int, float)) else "—"
        src_raw = str(r.get("quote_source", "") or "").strip().lower()
        if src_raw == "scanner_shm":
            src_badge = "SHM"
            src_color = "#00E676"
        elif src_raw == "postgres_live_state":
            src_badge = "DB"
            src_color = "#FFB300"
        elif src_raw == "dragonfly_live":
            src_badge = "DFLY"
            src_color = "#AB47BC"
        elif src_raw:
            src_badge = "API"
            src_color = "#29B6F6"
        else:
            src_badge = "—"
            src_color = "#777777"
        return {
            "symbol": sym,
            "tv_href": tv_href,
            "setup_score_ui": f"{r.get('bars', 0)}",
            "setup_score_color": "#00FF00" if is_breakout else "#D1D1D1",
            "ltp": f"{last}",
            "quote_source": src_badge,
            "quote_source_color": src_color,
            "chp": chp_text,
            "chp_color": chp_color if chp_num is not None else "#D1D1D1",
            "rs_rating": f"{int(r.get('rs_rating', 0))}" if int(r.get("rs_rating", 0)) > 0 else "—",
            "rs_rating_color": "#00FF00" if int(r.get("rs_rating", 0)) >= 80 else ("#FFB000" if int(r.get("rs_rating", 0)) >= 60 else "#D1D1D1"),
            "rv": f"{float(r.get('rv', 0.0)):.2f}" if float(r.get("rv", 0.0)) > 0 else "—",
            "rv_color": "#00FF00" if float(r.get("rv", 0.0)) >= 1.5 else "#D1D1D1",
            "mrs_weekly": f"{float(r.get('mrs', 0.0)):.2f}" if r.get("mrs") is not None else "—",
            "mrs_color": "#00FF00" if float(r.get("mrs", 0.0)) >= 0 else "#FF4D4F",
            "last_tag": tag_d,
            # Blue means structural LAST TAG D event happened on latest EOD day.
            "last_tag_color": "#00E5FF" if tag_today_event else "#888888",
            "last_tag_w": tag_w,
            "last_tag_color_w": "#00E5FF" if is_breakout else "#888888",
            "last_tag_d_path_seq": int(r.get("last_tag_d_path_seq", 0) or 0),
            "last_tag_d_path_event_count": int(r.get("last_tag_d_path_event_count", 0) or 0),
            "last_tag_d_path_last_token": str(r.get("last_tag_d_path_last_token", "") or ""),
            "last_tag_d_path_string": str(r.get("last_tag_d_path_string", "") or ""),
            "live_struct_d": live_struct_d,
            "live_struct_d_color": "#FF5252" if BreakoutClockState._is_live_struct_mismatch(tag_d, live_struct_d_raw) else ("#00E5FF" if is_breakout else "#777777"),
            "live_struct_mismatch": BreakoutClockState._is_live_struct_mismatch(tag_d, live_struct_d_raw),
            "live_struct_attempt_status": live_struct_attempt_status,
            "last_event_dt": r.get("last_event_dt", "—"),
            "brk_move_live_pct": pct_d_text,
            "brk_move_live_color": "#00FF00" if (isinstance(pct_d, (int, float)) and float(pct_d) >= 0) else "#FF4D4F",
            "timing_last_event_dt_w": r.get("timing_last_event_dt_w", "—"),
            "live_struct_w": live_struct_w,
            "live_struct_w_color": "#00E5FF" if is_breakout else "#777777",
            "live_struct_w_today": str(r.get("live_struct_w_today", "—") or "—"),
            "live_struct_w_today_color": "#777777",
            "brk_move_live_pct_w": pct_w_text,
            "brk_move_live_color_w": "#00FF00" if (isinstance(pct_w, (int, float)) and float(pct_w) >= 0) else "#FF4D4F",
        }

    def toggle_path_expand(self, symbol: str):
        s = str(symbol or "").strip().upper()
        if not s:
            return
        self.expanded_path_symbol = "" if self.expanded_path_symbol == s else s

    def set_structural_today_bucket(self, bucket: str):
        b = (bucket or "ALL").strip().upper()
        allowed = {"ALL", "TODAY", "B", "E9CT", "ET9", "E21C", "RST"}
        self.structural_today_bucket = b if b in allowed else "ALL"
        self.current_page = 1
        self._sorted_symbol_cache_key = ""
        self._sorted_symbols = []
        self._reload()

    async def set_universe(self, u: str):
        """Update universe in UI immediately; load snapshot in a worker thread (no multi-second block on click)."""
        u_clean = (u or "Nifty 50").strip()
        self.universe = u_clean
        self.current_page = 1
        self._sorted_symbol_cache_key = ""
        self._sorted_symbols = []
        self.results = []
        self.total_count = 0
        self.symbol_count_total = 0
        self.symbol_count_loaded = 0
        self.structural_today_count = 0
        self.structural_today_b = 0
        self.structural_today_e9ct = 0
        self.structural_today_et9 = 0
        self.structural_today_e21c = 0
        self.structural_today_rst = 0
        self.structural_today_bucket = "ALL"
        self.live_struct_rows = 0
        self.live_struct_rows_raw = 0
        self.status_message = "LOADING"
        yield
        t0 = time.perf_counter()
        snap = await asyncio.to_thread(lambda: get_engine().snapshot(universe=u_clean))
        t1 = time.perf_counter()
        self._hydrate_from_snapshot(snap, t0, t1)

    def set_search_query(self, q: str):
        self.search_query = q or ""
        self.current_page = 1
        self._reload()

    def set_filter_profile(self, v: str):
        self.filter_profile = (v or "ALL").strip().upper()
        self.current_page = 1
        self._reload()

    def set_timing_filter(self, v: str):
        vv = (v or "ALL").strip().upper()
        self.timing_filter = vv if vv in ("ALL", "LIVE_STRUCT_ONLY") else "ALL"
        self.current_page = 1
        self._reload()

    def set_filter_brk_stage(self, v: str):
        self.filter_brk_stage = v or "ALL"
        self.current_page = 1
        self._reload()

    def set_filter_mrs_grid(self, v: str):
        self.filter_mrs_grid = (v or "ALL").strip().upper()
        self.current_page = 1
        self._reload()

    def set_filter_wmrs_slope(self, v: str):
        self.filter_wmrs_slope = (v or "ALL").strip().upper()
        self.current_page = 1
        self._reload()

    def set_filter_m_rsi2(self, v: str):
        self.filter_m_rsi2 = v or "ALL"
        self.current_page = 1
        self._reload()

    def _toggle_sort(self, key: str, desc_default: bool = True):
        if self.sort_timing_key == key:
            self.sort_timing_desc = not self.sort_timing_desc
        else:
            self.sort_timing_key = key
            self.sort_timing_desc = desc_default
        self.current_page = 1
        self._reload()

    def toggle_sort_when_d(self): self._toggle_sort("last_event_dt", True)
    def toggle_sort_when_w(self): self._toggle_sort("timing_last_event_dt_w", True)
    def toggle_sort_rs_rating(self): self._toggle_sort("rs_rating", True)
    def toggle_sort_setup_score(self): self._toggle_sort("bars", True)
    def toggle_sort_symbol(self): self._toggle_sort("symbol", False)
    def toggle_sort_ltp(self): self._toggle_sort("last", True)
    def toggle_sort_chp(self): self._toggle_sort("chp", True)
    def toggle_sort_rvol(self): self._toggle_sort("rv", True)
    def toggle_sort_wmrs(self): self._toggle_sort("mrs_weekly", True)
    def toggle_sort_last_tag_d(self): self._toggle_sort("last_tag", False)
    def toggle_sort_last_tag_w(self): self._toggle_sort("last_tag_w", False)
    def toggle_sort_pct_live_d(self): self._toggle_sort("brk_move_live_pct", True)
    def toggle_sort_pct_live_w(self): self._toggle_sort("brk_move_live_pct_w", True)
    def toggle_sort_pct_from_b_d(self): self._toggle_sort("brk_move_live_pct", True)
    def toggle_sort_pct_from_b_w(self): self._toggle_sort("brk_move_live_pct_w", True)

    @rx.var
    def when_d_sort_arrow(self) -> str: return "▼" if self.sort_timing_desc and self.sort_timing_key == "last_event_dt" else ("▲" if self.sort_timing_key == "last_event_dt" else "")
    @rx.var
    def when_w_sort_arrow(self) -> str: return "▼" if self.sort_timing_desc and self.sort_timing_key == "timing_last_event_dt_w" else ("▲" if self.sort_timing_key == "timing_last_event_dt_w" else "")
    @rx.var
    def rs_rating_sort_arrow(self) -> str: return "▼" if self.sort_timing_desc and self.sort_timing_key == "rs_rating" else ("▲" if self.sort_timing_key == "rs_rating" else "")
    @rx.var
    def setup_score_sort_arrow(self) -> str: return "▼" if self.sort_timing_desc and self.sort_timing_key == "bars" else ("▲" if self.sort_timing_key == "bars" else "")
    @rx.var
    def symbol_sort_arrow(self) -> str: return "▼" if self.sort_timing_desc and self.sort_timing_key == "symbol" else ("▲" if self.sort_timing_key == "symbol" else "")
    @rx.var
    def ltp_sort_arrow(self) -> str: return "▼" if self.sort_timing_desc and self.sort_timing_key == "last" else ("▲" if self.sort_timing_key == "last" else "")
    @rx.var
    def chp_sort_arrow(self) -> str: return "▼" if self.sort_timing_desc and self.sort_timing_key == "chp" else ("▲" if self.sort_timing_key == "chp" else "")
    @rx.var
    def rvol_sort_arrow(self) -> str: return ""
    @rx.var
    def wmrs_sort_arrow(self) -> str: return ""
    @rx.var
    def last_tag_d_sort_arrow(self) -> str: return "▼" if self.sort_timing_desc and self.sort_timing_key == "last_tag" else ("▲" if self.sort_timing_key == "last_tag" else "")
    @rx.var
    def last_tag_w_sort_arrow(self) -> str: return "▼" if self.sort_timing_desc and self.sort_timing_key == "last_tag_w" else ("▲" if self.sort_timing_key == "last_tag_w" else "")
    @rx.var
    def pct_live_d_sort_arrow(self) -> str: return "▼" if self.sort_timing_desc and self.sort_timing_key == "brk_move_live_pct" else ("▲" if self.sort_timing_key == "brk_move_live_pct" else "")
    @rx.var
    def pct_live_w_sort_arrow(self) -> str: return "▼" if self.sort_timing_desc and self.sort_timing_key == "brk_move_live_pct_w" else ("▲" if self.sort_timing_key == "brk_move_live_pct_w" else "")
    @rx.var
    def pct_from_b_d_sort_arrow(self) -> str: return self.pct_live_d_sort_arrow
    @rx.var
    def pct_from_b_w_sort_arrow(self) -> str: return self.pct_live_w_sort_arrow

    def next_page(self):
        self.current_page = min(self.total_pages, self.current_page + 1)
        self._reload()

    def prev_page(self):
        self.current_page = max(1, self.current_page - 1)
        self._reload()

    def download_excel(self):
        return rx.window_alert("Export is not yet enabled in v2 storage-only mode.")


class BreakoutTimingDailyState(BreakoutClockState):
    clock_timeframe: str = "daily"

    async def on_load(self):
        self.clock_timeframe = "daily"
        self.auto_refresh_started = False
        self._reload()
        return BreakoutTimingDailyState.start_auto_refresh


class BreakoutTimingWeeklyState(BreakoutClockState):
    clock_timeframe: str = "weekly"

    async def on_load(self):
        self.clock_timeframe = "weekly"
        self.auto_refresh_started = False
        self._reload()
        return BreakoutTimingWeeklyState.start_auto_refresh


class BreakoutTimingLegacyRedirectState(rx.State):
    async def on_load(self):
        return rx.redirect("/breakout-clock-daily", is_external=False)

