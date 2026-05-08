import reflex as rx

from .state import V2State


def breakout_header() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.text("SOLARIS • BREAKOUT STRATEGY", size="4", color="#00FF00", font_weight="bold"),
                rx.text("V2 STORAGE-ONLY ENGINE", size="1", color="#D1D1D1"),
                rx.link("Open Breakout clock (daily →)", href="/", color="#00E5FF", font_size="11px", padding_top="4px"),
                align_items="start",
                spacing="0",
            ),
            rx.spacer(),
            rx.vstack(
                rx.text("ENGINE STATUS", size="1", color="#D1D1D1", font_weight="bold"),
                rx.hstack(
                    rx.text(V2State.status, color="#FFB000", font_weight="bold", font_size="14px"),
                    rx.text(f"{V2State.total_count} SYMBOLS", color="#00FF00", font_weight="bold", font_size="12px"),
                    spacing="2",
                ),
                align_items="end",
                spacing="0",
            ),
            width="100%",
            padding="10px",
            border_bottom="1px solid #333333",
            background_color="#000000",
        ),
        spacing="0",
        width="100%",
    )


def breakout_sidebar() -> rx.Component:
    return rx.vstack(
        rx.text("TACTICAL / UNIVERSE", size="1", color="#D1D1D1", font_weight="bold", padding="10px 15px"),
        rx.text("NIFTY200 (storage-only)", size="1", color="#888888", padding="0 15px 8px 15px"),
        rx.text("FILTERS", size="1", color="#D1D1D1", font_weight="bold", padding="8px 15px 4px 15px"),
        rx.text("Symbol contains", size="1", color="#888888", padding_left="15px"),
        rx.input(
            placeholder="e.g. RELIANCE",
            value=V2State.search_query,
            on_change=V2State.set_search_query,
            size="1",
            width="100%",
            max_width="260px",
            margin_left="15px",
            margin_right="15px",
            border="1px solid #333333",
            bg="#111111",
            color="white",
            height="32px",
            font_size="12px",
        ),
        rx.text("Mode: storage_only", size="1", color="#777777", padding="10px 15px"),
        width="100%",
        height="100%",
        border_right="1px solid #333333",
        background_color="#000000",
    )


def breakout_data_grid() -> rx.Component:
    header = rx.table.row(
        rx.table.column_header_cell(
            rx.hstack(
                rx.text("SYMBOL", color="white"),
                rx.text(V2State.symbol_sort_arrow, color="#FFB000", font_size="10px"),
                spacing="1",
                cursor="pointer",
                on_click=V2State.toggle_sort("symbol"),
            )
        ),
        rx.table.column_header_cell(
            rx.hstack(
                rx.text("BARS", color="white"),
                rx.text(V2State.bars_sort_arrow, color="#FFB000", font_size="10px"),
                spacing="1",
                cursor="pointer",
                on_click=V2State.toggle_sort("bars"),
            )
        ),
        rx.table.column_header_cell(
            rx.hstack(
                rx.text("LAST", color="white"),
                rx.text(V2State.last_sort_arrow, color="#FFB000", font_size="10px"),
                spacing="1",
                cursor="pointer",
                on_click=V2State.toggle_sort("last"),
            )
        ),
        rx.table.column_header_cell(rx.text("REF", color="white")),
        rx.table.column_header_cell(
            rx.hstack(
                rx.text("FLAG", color="white"),
                rx.text(V2State.breakout_sort_arrow, color="#FFB000", font_size="10px"),
                spacing="1",
                cursor="pointer",
                on_click=V2State.toggle_sort("is_breakout"),
            )
        ),
    )
    body = rx.table.body(
        rx.foreach(
            V2State.paginated_strategy_rows,
            lambda r: rx.table.row(
                rx.table.cell(rx.text(r["symbol"], color="#FFB000", font_weight="bold")),
                rx.table.cell(rx.text(r["bars"], color="#D1D1D1")),
                rx.table.cell(rx.text(r["last"], color="#D1D1D1")),
                rx.table.cell(rx.text(r["ref"], color="#D1D1D1")),
                rx.table.cell(
                    rx.text(
                        rx.cond(r["is_breakout"], "BREAKOUT", "-"),
                        color=rx.cond(r["is_breakout"], "#00FF00", "#888888"),
                    )
                ),
                height="25px",
                border_bottom="1px solid #1f1f1f",
                _odd={"background_color": "#050505"},
                _even={"background_color": "#0b0b0b"},
            ),
        )
    )
    return rx.vstack(
        rx.table.root(rx.table.header(header), body, width="100%", variant="surface", background_color="#000000"),
        rx.hstack(
            rx.button("PREV", on_click=V2State.prev_page, size="1", variant="outline", disabled=V2State.current_page == 1),
            rx.text(f"PAGE {V2State.current_page} / {V2State.total_pages}", size="1", color="#D1D1D1"),
            rx.button(
                "NEXT",
                on_click=V2State.next_page,
                size="1",
                variant="outline",
                disabled=V2State.current_page == V2State.total_pages,
            ),
            spacing="4",
            padding="10px",
            width="100%",
            justify_content="center",
            border_top="1px solid #333333",
        ),
        width="100%",
        flex="1",
        overflow_y="auto",
        spacing="0",
    )


def breakout_page() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.vstack(breakout_header(), breakout_sidebar(), spacing="0", width="300px", height="100vh"),
            rx.vstack(
                breakout_data_grid(),
                rx.box(
                    rx.text(
                        f"LAST SYNC: {V2State.started_at} | STATUS: {V2State.status}",
                        size="1",
                        color="#00FF00",
                    ),
                    width="100%",
                    padding="4px 15px",
                    background_color="#111111",
                    border_top="1px solid #333333",
                ),
                spacing="0",
                width="100%",
                height="100vh",
                background_color="#000000",
                overflow="hidden",
            ),
            width="100%",
            height="100vh",
            spacing="0",
            background_color="#000000",
            overflow="hidden",
        ),
        width="100%",
        min_height="100vh",
        background_color="#000000",
        overflow="hidden",
        font_family="'JetBrains Mono', monospace",
        style={"WebkitFontSmoothing": "antialiased"},
    )


def _rows_table(rows: rx.Var[list[dict]]) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text("SYMBOL", color="#6B7280", width="120px"),
            rx.text("BARS", color="#6B7280", width="80px"),
            rx.text("LAST", color="#6B7280", width="100px"),
            rx.text("REF", color="#6B7280", width="100px"),
            rx.text("FLAG", color="#6B7280", width="80px"),
            spacing="4",
        ),
        rx.foreach(
            rows,
            lambda row: rx.hstack(
                rx.text(row["symbol"], color="#E5E7EB", width="120px"),
                rx.text(row["bars"], color="#9CA3AF", width="80px"),
                rx.text(row["last"], color="#9CA3AF", width="100px"),
                rx.text(row["ref"], color="#9CA3AF", width="100px"),
                rx.text(
                    rx.cond(row["is_breakout"], "BREAKOUT", "-"),
                    color=rx.cond(row["is_breakout"], "#10B981", "#6B7280"),
                    width="80px",
                ),
                spacing="4",
                width="100%",
            ),
        ),
        align_items="start",
        width="100%",
        spacing="1",
    )


def _shell(title: str, subtitle: str, rows: rx.Var[list[dict]]) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text(title, color="#00E5FF", font_size="20px", font_weight="bold"),
            rx.text(subtitle, color="#A0A0A0", font_size="13px"),
            rx.hstack(
                rx.link("Daily", href="/", color="#FFB000"),
                rx.link("Weekly", href="/breakout-clock-weekly", color="#66CCFF"),
                spacing="4",
            ),
            rx.divider(border_color="#1F1F1F"),
            rx.text("UNIVERSE", color="#888", font_size="11px"),
            rx.select(
                V2State.universe_options,
                value=V2State.universe,
                on_change=V2State.set_universe,
                color="white",
                bg="#111111",
                border="1px solid #333333",
                size="1",
                width="100%",
                max_width="280px",
                height="32px",
                font_size="12px",
            ),
            rx.hstack(
                rx.text("STATUS", color="#888", font_size="11px"),
                rx.text(V2State.status, color="#00FF99", font_size="11px"),
                rx.text("MODE", color="#888", font_size="11px"),
                rx.text(V2State.mode, color="#00E5FF", font_size="11px"),
                rx.text("SYMBOLS", color="#888", font_size="11px"),
                rx.text(V2State.symbol_count, color="#FFB000", font_size="11px"),
                spacing="3",
            ),
            rx.text(f"DB_HOST: {V2State.db_host}", color="#8FA1B3", font_size="11px"),
            rx.text(f"PIPELINE_DATA_DIR: {V2State.pipeline_dir}", color="#8FA1B3", font_size="11px"),
            rx.text(f"STARTED: {V2State.started_at}", color="#8FA1B3", font_size="11px"),
            rx.text(f"NOW: {V2State.now_ts}", color="#8FA1B3", font_size="11px"),
            rx.divider(border_color="#1F1F1F"),
            _rows_table(rows),
            rx.callout(
                "Phase 2 in progress: this v2 app is now detached from legacy SHM startup paths. "
                "Next step wires storage/API adapters for full breakout grid parity.",
                icon="info",
                color_scheme="blue",
                width="100%",
            ),
            align_items="start",
            spacing="3",
            width="100%",
            padding="16px",
        ),
        background_color="#050505",
        min_height="100vh",
    )


def _clock_header(title: str, count_var: rx.Var[int]) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.text(title, size="4", color="#00FF00", font_weight="bold"),
                rx.text("V2 STORAGE-ONLY ENGINE", size="1", color="#D1D1D1"),
                align_items="start",
                spacing="0",
            ),
            rx.spacer(),
            rx.vstack(
                rx.text("ENGINE STATUS", size="1", color="#D1D1D1", font_weight="bold"),
                rx.hstack(
                    rx.text(V2State.status, color="#FFB000", font_weight="bold", font_size="14px"),
                    rx.text(f"{count_var} ROWS", color="#00FF00", font_weight="bold", font_size="12px"),
                    spacing="2",
                    align_items="center",
                ),
                align_items="end",
                spacing="0",
            ),
            width="100%",
            padding="10px",
            border_bottom="1px solid #333333",
            background_color="#000000",
        ),
        spacing="0",
        width="100%",
    )


def _clock_sidebar() -> rx.Component:
    return rx.vstack(
        rx.text("TACTICAL / UNIVERSE", size="1", color="#D1D1D1", font_weight="bold", padding="10px 15px"),
        rx.select(
            V2State.universe_options,
            value=V2State.universe,
            on_change=V2State.set_universe,
            color="white",
            bg="#111111",
            border="1px solid #333333",
            size="1",
            width="100%",
            max_width="260px",
            height="32px",
            font_size="12px",
            margin_left="15px",
            margin_right="15px",
        ),
        rx.box(height="8px"),
        rx.text("FILTERS", size="1", color="#D1D1D1", font_weight="bold", padding="8px 15px 4px 15px"),
        rx.text("Symbol contains", size="1", color="#888888", padding_left="15px"),
        rx.input(
            placeholder="e.g. RELIANCE",
            value=V2State.search_query,
            on_change=V2State.set_search_query,
            size="1",
            width="100%",
            max_width="260px",
            margin_left="15px",
            margin_right="15px",
            border="1px solid #333333",
            bg="#111111",
            color="white",
            height="32px",
            font_size="12px",
        ),
        width="100%",
        height="100%",
        border_right="1px solid #333333",
        background_color="#000000",
    )


def _clock_grid(rows: rx.Var[list[dict]]) -> rx.Component:
    header = rx.table.row(
        rx.table.column_header_cell(rx.text("SYMBOL", color="white")),
        rx.table.column_header_cell(rx.text("BARS", color="white")),
        rx.table.column_header_cell(rx.text("LAST", color="white")),
        rx.table.column_header_cell(rx.text("REF", color="white")),
        rx.table.column_header_cell(rx.text("FLAG", color="white")),
    )
    body = rx.table.body(
        rx.foreach(
            rows,
            lambda r: rx.table.row(
                rx.table.cell(rx.text(r["symbol"], color="#FFB000", font_weight="bold"), padding_y="0"),
                rx.table.cell(rx.text(r["bars"], color="#D1D1D1"), padding_y="0"),
                rx.table.cell(rx.text(r["last"], color="#D1D1D1"), padding_y="0"),
                rx.table.cell(rx.text(r["ref"], color="#D1D1D1"), padding_y="0"),
                rx.table.cell(
                    rx.text(rx.cond(r["is_breakout"], "BREAKOUT", "-"), color=rx.cond(r["is_breakout"], "#00FF00", "#888888")),
                    padding_y="0",
                ),
                height="25px",
                border_bottom="1px solid #1f1f1f",
                _odd={"background_color": "#050505"},
                _even={"background_color": "#0b0b0b"},
            ),
        ),
    )
    return rx.table.root(rx.table.header(header), body, width="100%", variant="surface", background_color="#000000")


def _clock_shell(
    title: str,
    count_var: rx.Var[int],
    rows: rx.Var[list[dict]],
    footer: str,
    total_pages: rx.Var[int],
    prev_evt,
    next_evt,
) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.vstack(_clock_header(title, count_var), _clock_sidebar(), spacing="0", width="300px", height="100vh"),
            rx.vstack(
                rx.box(
                    rx.vstack(
                        _clock_grid(rows),
                        rx.hstack(
                            rx.button(
                                "PREV",
                                on_click=prev_evt,
                                size="1",
                                variant="outline",
                                color_scheme="gray",
                                disabled=V2State.current_page == 1,
                            ),
                            rx.text(
                                f"PAGE {V2State.current_page} / {total_pages}",
                                size="1",
                                color="#D1D1D1",
                            ),
                            rx.button(
                                "NEXT",
                                on_click=next_evt,
                                size="1",
                                variant="outline",
                                color_scheme="gray",
                                disabled=V2State.current_page == total_pages,
                            ),
                            spacing="4",
                            padding="8px",
                            width="100%",
                            justify_content="center",
                            border_top="1px solid #333333",
                        ),
                        spacing="0",
                        width="100%",
                    ),
                    width="100%",
                    flex="1",
                    min_height="0",
                    overflow_x="auto",
                    overflow_y="auto",
                ),
                rx.box(
                    rx.text(footer, size="1", color="#00FF00"),
                    width="100%",
                    padding="4px 15px",
                    background_color="#111111",
                    border_top="1px solid #333333",
                ),
                spacing="0",
                width="100%",
                height="100vh",
                background_color="#000000",
                overflow="hidden",
                display="flex",
                flex_direction="column",
            ),
            width="100%",
            height="100vh",
            spacing="0",
            background_color="#000000",
            overflow="hidden",
        ),
        width="100%",
        min_height="100vh",
        background_color="#000000",
        overflow="hidden",
        font_family="'JetBrains Mono', monospace",
        style={"WebkitFontSmoothing": "antialiased"},
    )


def daily_page() -> rx.Component:
    footer = (
        f"LAST SYNC: {V2State.last_sync} | STATUS: {V2State.status} | "
        "Daily clock v2: storage-only breakout timing view."
    )
    return _clock_shell(
        "SOLARIS • BREAKOUT CLOCK (DAILY)",
        V2State.daily_total_count,
        V2State.paginated_daily_rows,
        footer,
        V2State.daily_total_pages,
        V2State.prev_daily_page,
        V2State.next_daily_page,
    )


def weekly_page() -> rx.Component:
    footer = (
        f"LAST SYNC: {V2State.last_sync} | STATUS: {V2State.status} | "
        "Weekly clock v2: storage-only breakout timing view."
    )
    return _clock_shell(
        "SOLARIS • BREAKOUT CLOCK (WEEKLY)",
        V2State.weekly_total_count,
        V2State.paginated_weekly_rows,
        footer,
        V2State.weekly_total_pages,
        V2State.prev_weekly_page,
        V2State.next_weekly_page,
    )

