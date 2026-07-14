"""Compute latest state and live-trade report from LIVE_START_DATE."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .backtest import BacktestResult, run_backtest
from .strategy import LIVE_START_DATE, Action, Position, compute_pnl_pct


@dataclass
class LatestState:
    date: pd.Timestamp
    close: float
    ma5: float
    ma20: float
    ma60: float
    position: Position
    today_signal: Optional[Action]

    shares: float
    avg_cost: float
    capital_pool: float
    total_assets: float             # capital_pool + shares * close
    current_pnl: float              # open position 未實現損益（相對成本）
    current_pnl_pct: float
    ma60_alerted_this_round: bool


def build_latest_state(result: BacktestResult) -> LatestState:
    last_row = result.df.iloc[-1]
    last_date = last_row["date"]

    today_actions = [t.action for t in result.trades if t.date == last_date]
    today_signal = today_actions[-1] if today_actions else None

    close = float(last_row["close"])
    shares = result.final_shares
    avg_cost = result.final_avg_cost
    capital_pool = result.final_capital_pool
    market_value = shares * close
    total_assets = capital_pool + market_value
    current_pnl = market_value - (avg_cost * shares) if shares > 0 else 0.0
    current_pnl_pct = compute_pnl_pct(close, avg_cost) if shares > 0 else 0.0

    return LatestState(
        date=last_date,
        close=close,
        ma5=float(last_row["ma5"]),
        ma20=float(last_row["ma20"]),
        ma60=float(last_row["ma60"]),
        position=result.final_position,
        today_signal=today_signal,
        shares=shares,
        avg_cost=avg_cost,
        capital_pool=capital_pool,
        total_assets=total_assets,
        current_pnl=current_pnl,
        current_pnl_pct=current_pnl_pct,
        ma60_alerted_this_round=result.final_ma60_alerted_this_round,
    )


def compute_latest_state(df: pd.DataFrame) -> LatestState:
    """Convenience wrapper: run backtest from LIVE_START_DATE and build state."""
    result = run_backtest(df, start_date=LIVE_START_DATE)
    return build_latest_state(result)
