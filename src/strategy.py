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

DAILY_PRICE_LIMIT_PCT = 0.20    # 2x 槓桿 ETF 單日漲跌幅限制為正股的槓桿倍數 × 10% = ±20%，用於判斷提示是否可能於下一交易日觸及


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


def price_reachable_next_session(
    close: float, trigger_price: float, limit_pct: float = DAILY_PRICE_LIMIT_PCT
) -> bool:
    """Whether `trigger_price` could plausibly be hit by the next trading day's
    close, given today's close and the daily price-limit band (±20% for a 2x
    leveraged ETF -- the exchange scales the limit by the leverage multiple)."""
    if close <= 0:
        return True
    return abs(trigger_price - close) / close <= limit_pct


def describe_next_actions(
    position: Position,
    close: float,
    ma5: float,
    ma20: float,
    ma60: float,
    avg_cost: float,
    capital_pool: float,
    ma60_already_alerted: bool = False,
    profit_exit_threshold: float = PROFIT_EXIT_THRESHOLD,
) -> list[dict]:
    """Describe the trigger(s) the user is currently watching for, restricted to
    ones the next trading day's close could plausibly reach (within the daily
    price-limit band around today's close) -- this mirrors the once-daily
    afternoon update cadence: only surface a hint if tomorrow could actually get
    there. Display-only; does not affect backtest/live-trade logic. Ordered
    upside-trigger first, then downside-continuation, then fresh entry, then
    the MA60 alert."""
    hints: list[dict] = []

    if position in (Position.HALF, Position.FULL) and avg_cost > 0:
        target_price = avg_cost * (1 + profit_exit_threshold)
        if price_reachable_next_session(close, target_price):
            hints.append({
                "action": Action.SELL_ALL.value,
                "action_zh": "獲利出場",
                "condition_zh": f"累積損益達 +{profit_exit_threshold * 100:.1f}%",
                "trigger_price": round(target_price, 4),
                "price_note": "依目前持股均價反推，若之後再加碼、均價與此出場價都會跟著變動",
            })

    if position is Position.HALF and capital_pool > 0:
        if price_reachable_next_session(close, ma20):
            hints.append({
                "action": Action.BUY_TRANCHE_2.value,
                "action_zh": "第二批加碼",
                "condition_zh": "收盤跌破 MA20",
                "trigger_price": round(ma20, 4),
                "amount": round(capital_pool, 2),
            })

    if position is Position.CASH and capital_pool > 0:
        if price_reachable_next_session(close, ma5):
            hints.append({
                "action": Action.BUY_TRANCHE_1.value,
                "action_zh": "第一批買進",
                "condition_zh": "收盤跌破 MA5",
                "trigger_price": round(ma5, 4),
                "amount": round(capital_pool * 0.5, 2),
            })

    if position in (Position.HALF, Position.FULL) and not ma60_already_alerted:
        if price_reachable_next_session(close, ma60):
            hints.append({
                "action": Action.ALERT_MA60.value,
                "action_zh": "MA60 警戒（僅提示，不自動加碼）",
                "condition_zh": "收盤跌破 MA60",
                "trigger_price": round(ma60, 4),
            })

    return hints
