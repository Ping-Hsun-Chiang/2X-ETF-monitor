"""Strategy B: drop-from-baseline entry / same-baseline reload / +7.5% exit.

Baseline = the year's first traded close (adjusted price), fixed throughout the year.
  - CASH & close <= baseline * (1 - drop_first)  → BUY_TRANCHE_1 (invest capital_pool × 0.5)
  - HALF & close <= baseline * (1 - drop_second) → BUY_TRANCHE_2 (invest remaining pool)
  - HALF/FULL & (close / avg_cost) - 1 >= profit_exit_threshold → SELL_ALL
Funding model matches strategy A: monthly deposit into capital pool, tranche = pool halving.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .backtest import Deposit, Round, Trade
from .strategy import (
    Action,
    MONTHLY_DEPOSIT,
    PROFIT_EXIT_THRESHOLD,
    Position,
    apply_action,
    compute_pnl_pct,
)

DROP_FIRST = 0.05    # 跌 5% 進場
DROP_SECOND = 0.10   # 跌 10% 加碼


def next_action_b(
    position: Position,
    close: float,
    baseline: float,
    avg_cost: float,
    capital_pool: float,
    drop_first: float = DROP_FIRST,
    drop_second: float = DROP_SECOND,
    profit_exit_threshold: float = PROFIT_EXIT_THRESHOLD,
) -> Optional[Action]:
    """Return the next action for strategy B given current state, or None."""
    if position in (Position.HALF, Position.FULL):
        if compute_pnl_pct(close, avg_cost) >= profit_exit_threshold:
            return Action.SELL_ALL

    if position is Position.HALF and close <= baseline * (1 - drop_second) and capital_pool > 0:
        return Action.BUY_TRANCHE_2

    if position is Position.CASH and close <= baseline * (1 - drop_first) and capital_pool > 0:
        return Action.BUY_TRANCHE_1

    return None


@dataclass
class BacktestResultB:
    df: pd.DataFrame
    baseline: float
    trades: list[Trade]
    rounds: list[Round]
    deposits: list[Deposit]
    final_position: Position
    final_shares: float
    final_avg_cost: float
    final_capital_pool: float


def run_backtest_b(
    df: pd.DataFrame,
    baseline: float,
    start_date: Optional[pd.Timestamp] = None,
    initial_capital: float = 0.0,
    monthly_deposit: float = MONTHLY_DEPOSIT,
    drop_first: float = DROP_FIRST,
    drop_second: float = DROP_SECOND,
) -> BacktestResultB:
    """Run strategy B on df with a fixed baseline. Same funding model as strategy A."""
    start_ts = pd.Timestamp(start_date) if start_date is not None else None

    capital_pool = initial_capital
    shares = 0.0
    avg_cost = 0.0
    position = Position.CASH

    last_deposit_month: Optional[tuple[int, int]] = None

    round_entry_date: Optional[pd.Timestamp] = None
    round_total_invested = 0.0
    round_position_max = Position.CASH

    trades: list[Trade] = []
    rounds: list[Round] = []
    deposits: list[Deposit] = []

    for _, row in df.iterrows():
        date = row["date"]
        if start_ts is not None and date < start_ts:
            continue

        year_month = (date.year, date.month)
        if year_month != last_deposit_month:
            if monthly_deposit > 0:
                capital_pool += monthly_deposit
                deposits.append(Deposit(
                    date=date,
                    year=date.year,
                    month=date.month,
                    amount=monthly_deposit,
                    capital_after=capital_pool,
                ))
            last_deposit_month = year_month

        close = row["close"]

        for _ in range(3):
            action = next_action_b(
                position, close, baseline, avg_cost, capital_pool,
                drop_first=drop_first, drop_second=drop_second,
            )
            if action is None:
                break

            capital_before = capital_pool
            shares_before = shares
            avg_cost_before = avg_cost
            invested_amount = 0.0

            if action is Action.BUY_TRANCHE_1:
                invest = capital_pool * 0.5
                new_shares = invest / close
                shares += new_shares
                avg_cost = close
                capital_pool -= invest
                invested_amount = invest
                round_entry_date = date
                round_total_invested = invest
                round_position_max = Position.HALF

            elif action is Action.BUY_TRANCHE_2:
                invest = capital_pool
                new_shares = invest / close
                cost_pool = avg_cost * shares + invest
                shares += new_shares
                avg_cost = cost_pool / shares
                capital_pool = 0.0
                invested_amount = invest
                round_total_invested += invest
                round_position_max = Position.FULL

            elif action is Action.SELL_ALL:
                proceeds = shares * close
                capital_pool += proceeds
                pnl = proceeds - round_total_invested
                pnl_pct = pnl / round_total_invested if round_total_invested else 0.0
                invested_amount = -proceeds
                rounds.append(Round(
                    entry_date=round_entry_date,
                    exit_date=date,
                    days_held=(date - round_entry_date).days if round_entry_date else 0,
                    initial_capital=0.0,  # not tracked for strategy B rounds
                    total_invested=round_total_invested,
                    total_proceeds=proceeds,
                    entry_avg_price=avg_cost,
                    exit_price=close,
                    position_taken=round_position_max,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    ma60_alerted=False,  # not applicable
                    capital_after=capital_pool,
                ))
                shares = 0.0
                avg_cost = 0.0
                round_entry_date = None
                round_total_invested = 0.0
                round_position_max = Position.CASH

            trades.append(Trade(
                date=date,
                action=action,
                price=close,
                capital_before=capital_before,
                capital_after=capital_pool,
                shares_before=shares_before,
                shares_after=shares,
                avg_cost_before=avg_cost_before,
                avg_cost_after=avg_cost,
                invested_amount=invested_amount,
            ))

            position = apply_action(position, action)

            if action is Action.SELL_ALL:
                break

    return BacktestResultB(
        df=df,
        baseline=baseline,
        trades=trades,
        rounds=rounds,
        deposits=deposits,
        final_position=position,
        final_shares=shares,
        final_avg_cost=avg_cost,
        final_capital_pool=capital_pool,
    )
