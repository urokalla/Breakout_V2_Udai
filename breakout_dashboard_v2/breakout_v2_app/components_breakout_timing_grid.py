import reflex as rx

from .breakout_timing_state import BreakoutTimingDailyState, BreakoutTimingWeeklyState


def _pagination(S):
    return rx.hstack(
        rx.button("PREV", on_click=S.prev_page, size="1", variant="outline", color_scheme="gray", disabled=S.current_page == 1),
        rx.hstack(
            rx.text("PAGE", size="1", color="#D1D1D1"),
            rx.text(S.current_page, size="1", color="#D1D1D1"),
            rx.text("/", size="1", color="#D1D1D1"),
            rx.text(S.total_pages, size="1", color="#D1D1D1"),
            spacing="2",
            align_items="center",
        ),
        rx.button("NEXT", on_click=S.next_page, size="1", variant="outline", color_scheme="gray", disabled=S.current_page == S.total_pages),
        spacing="4",
        padding="10px",
        width="100%",
        justify_content="center",
        border_top="1px solid #333333",
    )


def breakout_timing_daily_data_grid():
    S = BreakoutTimingDailyState
    header = rx.table.row(
        rx.table.column_header_cell(
            rx.hstack(rx.text("SYMBOL", color="white"), rx.text(S.symbol_sort_arrow, color="#00E5FF", font_size="10px"), spacing="1", cursor="pointer", on_click=S.toggle_sort_symbol)
        ),
        rx.table.column_header_cell(
            rx.hstack(rx.text("PRICE", color="white"), rx.text(S.ltp_sort_arrow, color="#00E5FF", font_size="10px"), spacing="1", cursor="pointer", on_click=S.toggle_sort_ltp)
        ),
        rx.table.column_header_cell(rx.text("SRC", color="#B0BEC5", font_size="9px")),
        rx.table.column_header_cell(
            rx.hstack(rx.text("CHG%", color="white"), rx.text(S.chp_sort_arrow, color="#00E5FF", font_size="10px"), spacing="1", cursor="pointer", on_click=S.toggle_sort_chp)
        ),
        rx.table.column_header_cell(
            rx.hstack(rx.text("RS", color="white"), rx.text(S.rs_rating_sort_arrow, color="#00E5FF", font_size="10px"), spacing="1", cursor="pointer", on_click=S.toggle_sort_rs_rating)
        ),
        rx.table.column_header_cell(
            rx.hstack(rx.text("RVOL", color="white"), rx.text(S.rvol_sort_arrow, color="#00E5FF", font_size="10px"), spacing="1", cursor="pointer", on_click=S.toggle_sort_rvol)
        ),
        rx.table.column_header_cell(
            rx.hstack(rx.text("W_MRS", color="white"), rx.text(S.wmrs_sort_arrow, color="#00E5FF", font_size="10px"), spacing="1", cursor="pointer", on_click=S.toggle_sort_wmrs)
        ),
        rx.table.column_header_cell(
            rx.hstack(rx.text("LAST TAG D", color="white"), rx.text(S.last_tag_d_sort_arrow, color="#00E5FF", font_size="10px"), spacing="1", cursor="pointer", on_click=S.toggle_sort_last_tag_d)
        ),
        rx.table.column_header_cell(rx.text("PATH", color="#B0BEC5", font_size="9px")),
        rx.table.column_header_cell(rx.text("LIVE_STRUCT_D", color="white", font_size="11px")),
        rx.table.column_header_cell(rx.text("LIVE_STATUS", color="#B0BEC5", font_size="10px")),
        rx.table.column_header_cell(
            rx.hstack(rx.text("WHEN (D) IST", color="white"), rx.text(S.when_d_sort_arrow, color="#00E5FF", font_size="10px"), spacing="1", cursor="pointer", on_click=S.toggle_sort_when_d)
        ),
        rx.table.column_header_cell(
            rx.hstack(rx.text("DIST_FROM_REF10% (D)", color="#00E5FF"), rx.text(S.pct_live_d_sort_arrow, color="#00E5FF", font_size="10px"), spacing="1", cursor="pointer", on_click=S.toggle_sort_pct_live_d)
        ),
    )
    body = rx.table.body(
        rx.foreach(
            S.results,
            lambda r: rx.table.row(
                rx.table.cell(
                    rx.link(
                        r["symbol"],
                        href=r.get("tv_href", "#"),
                        is_external=True,
                        color="#FFB000",
                        font_weight="bold",
                        font_size="11px",
                        text_decoration="underline",
                        cursor="pointer",
                        _hover={"opacity": "0.85"},
                    ),
                    padding_y="0",
                ),
                rx.table.cell(rx.text(r.get("ltp", "—"), color=r.get("chp_color", "#D1D1D1"), font_size="11px"), padding_y="0"),
                rx.table.cell(rx.text(r.get("quote_source", "—"), color=r.get("quote_source_color", "#777777"), font_size="9px"), padding_y="0"),
                rx.table.cell(rx.text(r.get("chp", "—"), color=r.get("chp_color", "#D1D1D1"), font_size="11px"), padding_y="0"),
                rx.table.cell(rx.text(r.get("rs_rating", "—"), color=r.get("rs_rating_color", "#D1D1D1"), font_size="11px"), padding_y="0"),
                rx.table.cell(rx.text(r.get("rv", "—"), color=r.get("rv_color", "#D1D1D1"), font_size="11px"), padding_y="0"),
                rx.table.cell(rx.text(r.get("mrs_weekly", "—"), color=r.get("mrs_color", "#D1D1D1"), font_size="11px"), padding_y="0"),
                rx.table.cell(rx.text(r.get("last_tag", "—"), color=r.get("last_tag_color", "#888888"), font_size="11px"), padding_y="0"),
                rx.table.cell(
                    rx.vstack(
                        rx.text(
                            rx.cond(
                                r.get("last_tag_d_path_last_token", "") != "",
                                r.get("last_tag_d_path_last_token", "—"),
                                "VIEW",
                            ),
                            color="#4FD1C5",
                                font_size="9px",
                            cursor="pointer",
                            text_decoration="underline",
                            on_click=S.toggle_path_expand(r["symbol"]),
                        ),
                        rx.cond(
                            S.expanded_path_symbol == r["symbol"],
                            rx.vstack(
                                rx.text(
                                    f"SEQ {r.get('last_tag_d_path_seq', 0)} | CNT {r.get('last_tag_d_path_event_count', 0)}",
                                    color="#90A4AE",
                                    font_size="9px",
                                ),
                                rx.text(
                                    rx.cond(
                                        r.get("last_tag_d_path_string", "") != "",
                                        r.get("last_tag_d_path_string", "—"),
                                        "—",
                                    ),
                                    color="#B0BEC5",
                                    font_size="9px",
                                    white_space="normal",
                                ),
                                spacing="0",
                                align_items="start",
                            ),
                            rx.fragment(),
                        ),
                        spacing="0",
                        align_items="start",
                    ),
                    padding_y="0",
                    max_width="240px",
                ),
                rx.table.cell(
                    rx.hstack(
                        rx.cond(
                            r.get("live_struct_mismatch", False),
                            rx.text("!", color="#FF5252", font_size="10px", font_weight="bold"),
                            rx.fragment(),
                        ),
                        rx.text(r.get("live_struct_d", "—"), color=r.get("live_struct_d_color", "#D1D1D1"), font_size="10px"),
                        spacing="1",
                        align_items="center",
                    ),
                    padding_y="0",
                ),
                rx.table.cell(rx.text(r.get("live_struct_attempt_status", "—"), color="#90A4AE", font_size="10px"), padding_y="0"),
                rx.table.cell(rx.text(r.get("last_event_dt", "—"), color="#E0E0E0", font_size="10px"), padding_y="0"),
                rx.table.cell(rx.text(r.get("brk_move_live_pct", "—"), color=r.get("brk_move_live_color", "#666666"), font_size="10px"), padding_y="0"),
                height="25px",
                border_bottom="1px solid #1f1f1f",
                _odd={"background_color": "#050505"},
                _even={"background_color": "#0b0b0b"},
                _hover={"background_color": "#151515"},
            ),
        ),
    )
    return rx.vstack(
        rx.table.root(rx.table.header(header), body, width="100%", variant="surface", background_color="#000000"),
        _pagination(S),
        width="100%",
        flex="1",
        overflow_y="auto",
        spacing="0",
    )


def breakout_timing_weekly_data_grid():
    S = BreakoutTimingWeeklyState
    header = rx.table.row(
        rx.table.column_header_cell(
            rx.hstack(rx.text("SYMBOL", color="white"), rx.text(S.symbol_sort_arrow, color="#00E5FF", font_size="10px"), spacing="1", cursor="pointer", on_click=S.toggle_sort_symbol)
        ),
        rx.table.column_header_cell(
            rx.hstack(rx.text("SCORE", color="white"), rx.text(S.setup_score_sort_arrow, color="#00E5FF", font_size="10px"), spacing="1", cursor="pointer", on_click=S.toggle_sort_setup_score)
        ),
        rx.table.column_header_cell(
            rx.hstack(rx.text("PRICE", color="white"), rx.text(S.ltp_sort_arrow, color="#00E5FF", font_size="10px"), spacing="1", cursor="pointer", on_click=S.toggle_sort_ltp)
        ),
        rx.table.column_header_cell(rx.text("SRC", color="#B0BEC5", font_size="10px")),
        rx.table.column_header_cell(
            rx.hstack(rx.text("CHG%", color="white"), rx.text(S.chp_sort_arrow, color="#00E5FF", font_size="10px"), spacing="1", cursor="pointer", on_click=S.toggle_sort_chp)
        ),
        rx.table.column_header_cell(
            rx.hstack(rx.text("RS", color="white"), rx.text(S.rs_rating_sort_arrow, color="#00E5FF", font_size="10px"), spacing="1", cursor="pointer", on_click=S.toggle_sort_rs_rating)
        ),
        rx.table.column_header_cell(
            rx.hstack(rx.text("RVOL", color="white"), rx.text(S.rvol_sort_arrow, color="#00E5FF", font_size="10px"), spacing="1", cursor="pointer", on_click=S.toggle_sort_rvol)
        ),
        rx.table.column_header_cell(
            rx.hstack(rx.text("W_MRS", color="white"), rx.text(S.wmrs_sort_arrow, color="#00E5FF", font_size="10px"), spacing="1", cursor="pointer", on_click=S.toggle_sort_wmrs)
        ),
        rx.table.column_header_cell(
            rx.hstack(rx.text("LAST TAG W", color="white"), rx.text(S.last_tag_w_sort_arrow, color="#00E5FF", font_size="10px"), spacing="1", cursor="pointer", on_click=S.toggle_sort_last_tag_w)
        ),
        rx.table.column_header_cell(rx.text("LIVE_STRUCT_W", color="white")),
        rx.table.column_header_cell(rx.text("LIVE_STRUCT_W_TODAY", color="white")),
        rx.table.column_header_cell(
            rx.hstack(rx.text("WHEN (W) IST", color="white"), rx.text(S.when_w_sort_arrow, color="#00E5FF", font_size="10px"), spacing="1", cursor="pointer", on_click=S.toggle_sort_when_w)
        ),
        rx.table.column_header_cell(
            rx.hstack(rx.text("DIST_FROM_REF12% (W)", color="#00E5FF"), rx.text(S.pct_live_w_sort_arrow, color="#00E5FF", font_size="10px"), spacing="1", cursor="pointer", on_click=S.toggle_sort_pct_live_w)
        ),
    )
    body = rx.table.body(
        rx.foreach(
            S.results,
            lambda r: rx.table.row(
                rx.table.cell(
                    rx.link(
                        r["symbol"],
                        href=r.get("tv_href", "#"),
                        is_external=True,
                        color="#FFB000",
                        font_weight="bold",
                        font_size="11px",
                        text_decoration="underline",
                        cursor="pointer",
                        _hover={"opacity": "0.85"},
                    ),
                    padding_y="0",
                ),
                rx.table.cell(rx.text(r.get("setup_score_ui", "—"), color=r.get("setup_score_color", "#D1D1D1"), font_size="11px"), padding_y="0"),
                rx.table.cell(rx.text(r.get("ltp", "—"), color=r.get("chp_color", "#D1D1D1"), font_size="11px"), padding_y="0"),
                rx.table.cell(rx.text(r.get("quote_source", "—"), color=r.get("quote_source_color", "#777777"), font_size="10px"), padding_y="0"),
                rx.table.cell(rx.text(r.get("chp", "—"), color=r.get("chp_color", "#D1D1D1"), font_size="11px"), padding_y="0"),
                rx.table.cell(rx.text(r.get("rs_rating", "—"), color=r.get("rs_rating_color", "#D1D1D1"), font_size="11px"), padding_y="0"),
                rx.table.cell(rx.text(r.get("rv", "—"), color=r.get("rv_color", "#D1D1D1"), font_size="11px"), padding_y="0"),
                rx.table.cell(rx.text(r.get("mrs_weekly", "—"), color=r.get("mrs_color", "#D1D1D1"), font_size="11px"), padding_y="0"),
                rx.table.cell(rx.text(r.get("last_tag_w", "—"), color=r.get("last_tag_color_w", "#888888"), font_size="11px"), padding_y="0"),
                rx.table.cell(rx.text(r.get("live_struct_w", "—"), color=r.get("live_struct_w_color", "#D1D1D1"), font_size="10px"), padding_y="0"),
                rx.table.cell(rx.text(r.get("live_struct_w_today", "—"), color=r.get("live_struct_w_today_color", "#D1D1D1"), font_size="10px"), padding_y="0"),
                rx.table.cell(rx.text(r.get("timing_last_event_dt_w", "—"), color="#E0E0E0", font_size="10px"), padding_y="0"),
                rx.table.cell(rx.text(r.get("brk_move_live_pct_w", "—"), color=r.get("brk_move_live_color_w", "#666666"), font_size="10px"), padding_y="0"),
                height="25px",
                border_bottom="1px solid #1f1f1f",
                _odd={"background_color": "#050505"},
                _even={"background_color": "#0b0b0b"},
                _hover={"background_color": "#151515"},
            ),
        ),
    )
    return rx.vstack(
        rx.table.root(rx.table.header(header), body, width="100%", variant="surface", background_color="#000000"),
        _pagination(S),
        width="100%",
        flex="1",
        overflow_y="auto",
        spacing="0",
    )

