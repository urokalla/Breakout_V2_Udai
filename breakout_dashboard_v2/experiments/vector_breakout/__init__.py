"""
Experimental vectorized live quote vs static ref levels (NumPy).

Not imported by the main Breakout V2 app. Use tests + self_check to validate;
integrate only after parity review.
"""

from .core import (
    chp_vs_prev_close,
    live_breakout_flags,
    live_pct_vs_ref,
    pack_closes_left_pad,
    reference_levels_donchian_10_excl_last,
)

__all__ = [
    "chp_vs_prev_close",
    "live_breakout_flags",
    "live_pct_vs_ref",
    "pack_closes_left_pad",
    "reference_levels_donchian_10_excl_last",
]
