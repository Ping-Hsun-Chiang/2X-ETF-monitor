"""Fetch historical daily close prices from FinMind for any target ticker."""
from __future__ import annotations

from typing import Optional

import pandas as pd
import requests

FINMIND_API_URL = "https://api.finmindtrade.com/api/v4/data"


def request_finmind(
    dataset: str,
    data_id: str,
    start_date: str,
    end_date: str,
    token: Optional[str] = None,
    timeout: int = 60,
) -> list[dict]:
    """Call FinMind data endpoint and return the `data` list."""
    params = {
        "dataset": dataset,
        "data_id": data_id,
        "start_date": start_date,
        "end_date": end_date,
    }
    if token:
        params["token"] = token
    resp = requests.get(FINMIND_API_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") != 200:
        raise RuntimeError(f"FinMind API error: {payload}")
    return payload.get("data", [])


def fetch_daily_close(
    stock_id: str,
    start_date: str,
    end_date: Optional[str] = None,
    token: Optional[str] = None,
    dataset: str = "TaiwanStockPrice",
) -> pd.DataFrame:
    """Fetch daily close prices for `stock_id` between `start_date` and `end_date`.

    `dataset`:
      - `TaiwanStockPrice` (default) → raw close (no split / dividend adjustment)
      - `TaiwanStockPriceAdj` → dividend-adjusted close (for meaningful long-term DCA comparison)

    Returns a DataFrame with columns `date` (datetime64[ns]) and `close` (float),
    sorted ascending by date. Rows where FinMind reports `close <= 0` are dropped
    (observed on some tickers as missing/bad data with prices continuous
    before/after -- not real trading halts).
    """
    if end_date is None:
        end_date = pd.Timestamp.today().strftime("%Y-%m-%d")
    rows = request_finmind(dataset, stock_id, start_date, end_date, token)
    if not rows:
        raise RuntimeError(
            f"No data returned for {stock_id} between {start_date} and {end_date}"
        )
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"])
    df = df[df["close"] > 0]
    df = df[["date", "close"]].sort_values("date").reset_index(drop=True)
    return df
