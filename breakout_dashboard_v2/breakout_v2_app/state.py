import time

import reflex as rx

from .config import DATA_MODE, DB_HOST, PIPELINE_DATA_DIR
from .engine import get_engine
from .universes import UNIVERSE_OPTIONS


class V2State(rx.State):
    started_at: str = "-"
    now_ts: str = "-"
    status: str = "INIT"
    symbol_count: int = 0
    universe: str = "Nifty 50"
    daily_rows: list[dict] = []
    weekly_rows: list[dict] = []
    strategy_rows: list[dict] = []
    search_query: str = ""
    sort_key: str = "symbol"
    sort_desc: bool = False
    current_page: int = 1
    page_size: int = 50
    last_sync: str = "-"

    async def on_load(self):
        async with self:
            self.started_at = time.strftime("%Y-%m-%d %H:%M:%S")
            self.now_ts = self.started_at
            self._reload_snapshot()

    def set_search_query(self, q: str):
        self.search_query = (q or "").strip().upper()
        self.current_page = 1

    def set_universe(self, u: str):
        self.universe = (u or "Nifty 50").strip()
        self.current_page = 1
        self._reload_snapshot()

    def _reload_snapshot(self):
        snap = get_engine().snapshot(universe=self.universe)
        self.symbol_count = int(snap.get("symbol_count", 0))
        self.daily_rows = list(snap.get("daily_rows", []))
        self.weekly_rows = list(snap.get("weekly_rows", []))
        self.strategy_rows = list(snap.get("strategy_rows", []))
        self.status = "READY"
        self.last_sync = time.strftime("%Y-%m-%d %H:%M:%S")

    def toggle_sort(self, key: str):
        if self.sort_key == key:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_key = key
            self.sort_desc = key != "symbol"
        self.current_page = 1

    def next_page(self):
        self.current_page = min(self.total_pages, self.current_page + 1)

    def prev_page(self):
        self.current_page = max(1, self.current_page - 1)

    def next_daily_page(self):
        self.current_page = min(self.daily_total_pages, self.current_page + 1)

    def prev_daily_page(self):
        self.current_page = max(1, self.current_page - 1)

    def next_weekly_page(self):
        self.current_page = min(self.weekly_total_pages, self.current_page + 1)

    def prev_weekly_page(self):
        self.current_page = max(1, self.current_page - 1)

    @rx.var
    def symbol_sort_arrow(self) -> str:
        if self.sort_key != "symbol":
            return ""
        return "▼" if self.sort_desc else "▲"

    @rx.var
    def bars_sort_arrow(self) -> str:
        if self.sort_key != "bars":
            return ""
        return "▼" if self.sort_desc else "▲"

    @rx.var
    def last_sort_arrow(self) -> str:
        if self.sort_key != "last":
            return ""
        return "▼" if self.sort_desc else "▲"

    @rx.var
    def breakout_sort_arrow(self) -> str:
        if self.sort_key != "is_breakout":
            return ""
        return "▼" if self.sort_desc else "▲"

    @rx.var
    def filtered_strategy_rows(self) -> list[dict]:
        rows = list(self.strategy_rows)
        q = self.search_query
        if q:
            rows = [r for r in rows if q in str(r.get("symbol", "")).upper()]
        key = self.sort_key or "symbol"
        try:
            rows.sort(key=lambda r: r.get(key, ""), reverse=self.sort_desc)
        except Exception:
            pass
        return rows

    @rx.var
    def total_count(self) -> int:
        return len(self.filtered_strategy_rows)

    @rx.var
    def total_pages(self) -> int:
        return max(1, (self.total_count + self.page_size - 1) // self.page_size)

    @rx.var
    def paginated_strategy_rows(self) -> list[dict]:
        start = (self.current_page - 1) * self.page_size
        end = start + self.page_size
        return self.filtered_strategy_rows[start:end]

    @rx.var
    def mode(self) -> str:
        return DATA_MODE

    @rx.var
    def pipeline_dir(self) -> str:
        return PIPELINE_DATA_DIR

    @rx.var
    def db_host(self) -> str:
        return DB_HOST

    @rx.var
    def universe_options(self) -> list[str]:
        return UNIVERSE_OPTIONS

    @rx.var
    def filtered_daily_rows(self) -> list[dict]:
        rows = list(self.daily_rows)
        q = self.search_query
        if q:
            rows = [r for r in rows if q in str(r.get("symbol", "")).upper()]
        key = self.sort_key or "symbol"
        try:
            rows.sort(key=lambda r: r.get(key, ""), reverse=self.sort_desc)
        except Exception:
            pass
        return rows

    @rx.var
    def filtered_weekly_rows(self) -> list[dict]:
        rows = list(self.weekly_rows)
        q = self.search_query
        if q:
            rows = [r for r in rows if q in str(r.get("symbol", "")).upper()]
        key = self.sort_key or "symbol"
        try:
            rows.sort(key=lambda r: r.get(key, ""), reverse=self.sort_desc)
        except Exception:
            pass
        return rows

    @rx.var
    def daily_total_count(self) -> int:
        return len(self.filtered_daily_rows)

    @rx.var
    def weekly_total_count(self) -> int:
        return len(self.filtered_weekly_rows)

    @rx.var
    def paginated_daily_rows(self) -> list[dict]:
        start = (self.current_page - 1) * self.page_size
        end = start + self.page_size
        return self.filtered_daily_rows[start:end]

    @rx.var
    def paginated_weekly_rows(self) -> list[dict]:
        start = (self.current_page - 1) * self.page_size
        end = start + self.page_size
        return self.filtered_weekly_rows[start:end]

    @rx.var
    def daily_total_pages(self) -> int:
        return max(1, (self.daily_total_count + self.page_size - 1) // self.page_size)

    @rx.var
    def weekly_total_pages(self) -> int:
        return max(1, (self.weekly_total_count + self.page_size - 1) // self.page_size)

