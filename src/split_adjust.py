"""Split adjustment for leveraged ETFs that have undergone a stock split."""
from __future__ import annotations

from typing import Optional

import pandas as pd


def adjust_for_split(
    df: pd.DataFrame,
    split_date: Optional[pd.Timestamp] = None,
    ratio: float = 1.0,
    price_col: str = "close",
) -> pd.DataFrame:
    """Return a copy of df with pre-split prices divided by `ratio`.

    Convention: on and after `split_date`, prices are at post-split levels.
    Dates strictly before `split_date` are divided by `ratio` so the series
    is continuous across the split. If `split_date` is None (target never
    split), the series is returned unchanged.
    """
    out = df.copy()
    if split_date is None:
        return out
    mask = out["date"] < split_date
    out.loc[mask, price_col] = out.loc[mask, price_col] / ratio
    return out
