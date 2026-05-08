import reflex as rx

from .breakout_timing_page import breakout_clock_daily_page, breakout_clock_weekly_page
from .breakout_timing_state import BreakoutTimingDailyState, BreakoutTimingLegacyRedirectState, BreakoutTimingWeeklyState


app = rx.App(
    theme=rx.theme(
        appearance="dark",
        has_background=True,
        accent_color="amber",
        gray_color="slate",
        radius="none",
    ),
    stylesheets=[
        "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap",
        "/sovereign_select.css",
    ],
)


app.add_page(
    breakout_clock_daily_page,
    route="/",
    title="SOLARIS • BREAKOUT V2",
    on_load=BreakoutTimingDailyState.on_load,
)
app.add_page(
    breakout_clock_daily_page,
    route="/breakout-clock-daily",
    title="BREAKOUT V2 • CLOCK (DAILY)",
    on_load=BreakoutTimingDailyState.on_load,
)
app.add_page(
    breakout_clock_weekly_page,
    route="/breakout-clock-weekly",
    title="BREAKOUT V2 • CLOCK (WEEKLY)",
    on_load=BreakoutTimingWeeklyState.on_load,
)
app.add_page(
    breakout_clock_daily_page,
    route="/breakout-timing",
    title="BREAKOUT V2 • CLOCK",
    on_load=BreakoutTimingLegacyRedirectState.on_load,
)

