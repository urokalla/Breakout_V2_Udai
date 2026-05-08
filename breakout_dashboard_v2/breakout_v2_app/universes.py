from __future__ import annotations

SYMBOL_GROUPS: dict[str, str] = {
    "Nifty 50": "nifty50.csv",
    "Nifty 100": "nifty100.csv",
    "Nifty 500": "nifty500.csv",
    "Nifty 500 Healthcare": "nifty500_healthcare.csv",
    "Nifty Total Market": "nifty_total_market.csv",
    "Nifty Midcap 100": "nifty_midcap100.csv",
    "Nifty Midcap 150": "nifty_midcap150.csv",
    "Nifty Smallcap 100": "nifty_smallcap100.csv",
    "Nifty Smallcap 250": "nifty_smallcap250.csv",
    "SME List": "sme_list.csv",
    "Nifty IPO": "ind_niftyipo_list.csv",
    "Microcap 250": "microcap250.csv",
    "Bank Nifty": "banknifty.csv",
    "All NSE Stocks": "NSE_EQ.csv",
}

UNIVERSE_OPTIONS: list[str] = list(SYMBOL_GROUPS.keys())
