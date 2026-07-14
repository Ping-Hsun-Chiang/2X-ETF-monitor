"""Strategy: MA5/MA20/MA60 fixed-tranche investment with monthly cap."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd

MA_SHORT = 5     # 週線
MA_LONG = 20     # 月線
MA_QUARTER = 60  # 季線

MONTHLY_DEPOSIT = 20_000.0       # 每月第一個交易日入金到資本池
PROFIT_EXIT_THRESHOLD = 0.075    # 累積損益達 +7.5% 全數出場

LIVE_START_DATE = pd.Timestamp("2026-07-13")  # 實盤模擬起始日


class Position(str, Enum):
    CASH = "CASH"
    HALF = "HALF"
    FULL = "FULL"


class Action(str, Enum):
    BUY_TRANCHE_1 = "BUY_TRANCHE_1"   # 空手 → 半倉：跌破週線，投第一批 10,000
    BUY_TRANCHE_2 = "BUY_TRANCHE_2"   # 半倉 → 滿倉：跌破月線，加投第二批 10,000
    ALERT_MA60 = "ALERT_MA60"          # 跌破季線：純訊號，不自動加碼
    SELL_ALL = "SELL_ALL"              # 累積損益達門檻，全數出場


@dataclass
class Signal:
    date: pd.Timestamp
    price: float
    action: Action
    ma5: float
    ma20: float
    ma60: float


def add_moving_averages(df: pd.DataFrame, price_col: str = "close") -> pd.DataFrame:
    """Add MA5, MA20, MA60 columns to a copy of df."""
    out = df.copy()
    out["ma5"] = out[price_col].rolling(MA_SHORT).mean()
    out["ma20"] = out[price_col].rolling(MA_LONG).mean()
    out["ma60"] = out[price_col].rolling(MA_QUARTER).mean()
    return out


def compute_pnl_pct(close: float, avg_cost: float) -> float:
    if avg_cost <= 0:
        return 0.0
    return (close - avg_cost) / avg_cost


def next_action(
    position: Position,
    close: float,
    ma5: float,
    ma20: float,
    ma60: float,
    avg_cost: float,
    capital_pool: float,
    ma60_already_alerted: bool = False,
    profit_exit_threshold: float = PROFIT_EXIT_THRESHOLD,
) -> Optional[Action]:
    """Return the next action to take today given current state, or None."""

    # 1. 出場優先（有部位 & 累積損益達門檻）
    if position in (Position.HALF, Position.FULL):
        if compute_pnl_pct(close, avg_cost) >= profit_exit_threshold:
            return Action.SELL_ALL

    # 2. 加碼 tranche 2：半倉 → 滿倉（將剩餘資本池全部投入）
    if position is Position.HALF and close < ma20 and capital_pool > 0:
        return Action.BUY_TRANCHE_2

    # 3. 進場 tranche 1：空手 → 半倉（投入資本池 × 0.5）
    if position is Position.CASH and close < ma5 and capital_pool > 0:
        return Action.BUY_TRANCHE_1

    # 4. MA60 警戒訊號（有部位 & 本輪尚未報警）
    if position in (Position.HALF, Position.FULL) and close < ma60:
        if not ma60_already_alerted:
            return Action.ALERT_MA60

    return None


def apply_action(position: Position, action: Action) -> Position:
    if action is Action.BUY_TRANCHE_1:
        return Position.HALF
    if action is Action.BUY_TRANCHE_2:
        return Position.FULL
    if action is Action.SELL_ALL:
        return Position.CASH
    # ALERT_MA60 does not change position
    return position
