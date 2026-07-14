"""Backtest engine: monthly-deposit capital-pool model with MA5/MA20/MA60 strategy."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .strategy import (
    Action,
    MONTHLY_DEPOSIT,
    PROFIT_EXIT_THRESHOLD,
    Position,
    add_moving_averages,
    apply_action,
    next_action,
)


@dataclass
class Trade:
    date: pd.Timestamp
    action: Action
    price: float
    capital_before: float
    capital_after: float
    shares_before: float
    shares_after: float
    avg_cost_before: float
    avg_cost_after: float
    invested_amount: float          # 正 = 投入，負 = 出場返還


@dataclass
class Round:
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    days_held: int
    initial_capital: float          # 本輪首次進場前的資本池
    total_invested: float           # 本輪累積實際投入金額
    total_proceeds: float           # 出場返還的現金
    entry_avg_price: float          # 出場時的持股均價
    exit_price: float
    position_taken: Position        # HALF 或 FULL
    pnl: float                      # total_proceeds - total_invested
    pnl_pct: float
    ma60_alerted: bool              # 該輪是否曾跌破 MA60
    capital_after: float            # 出場後資本池


@dataclass
class Deposit:
    date: pd.Timestamp
    year: int
    month: int
    amount: float
    capital_after: float


@dataclass
class BacktestResult:
    df: pd.DataFrame
    trades: list[Trade]
    rounds: list[Round]
    deposits: list[Deposit]
    stats: dict
    final_position: Position
    final_shares: float
    final_avg_cost: float
    final_capital_pool: float
    final_ma60_alerted_this_round: bool
    round_entry_date: Optional[pd.Timestamp] = None
    round_initial_capital: float = 0.0
    round_total_invested: float = 0.0
    round_position_max: Position = Position.CASH


def compute_stats(rounds: list[Round]) -> dict:
    if not rounds:
        return {
            "num_rounds": 0,
            "num_entries": 0,
            "num_exits": 0,
            "avg_days_held": 0.0,
            "avg_pnl_pct": 0.0,
            "win_rate_pct": 0.0,
            "total_pnl": 0.0,
            "num_alerts": 0,
        }
    wins = sum(1 for r in rounds if r.pnl > 0)
    total_pnl = sum(r.pnl for r in rounds)
    num_alerts = sum(1 for r in rounds if r.ma60_alerted)
    num_entries = sum(2 if r.position_taken is Position.FULL else 1 for r in rounds)
    return {
        "num_rounds": len(rounds),
        "num_entries": num_entries,
        "num_exits": len(rounds),
        "avg_days_held": sum(r.days_held for r in rounds) / len(rounds),
        "avg_pnl_pct": sum(r.pnl_pct for r in rounds) / len(rounds) * 100,
        "win_rate_pct": wins / len(rounds) * 100,
        "total_pnl": total_pnl,
        "num_alerts": num_alerts,
    }


def run_backtest(
    df: pd.DataFrame,
    start_date: Optional[pd.Timestamp] = None,
    initial_capital: float = 0.0,
    monthly_deposit: float = MONTHLY_DEPOSIT,
) -> BacktestResult:
    """Iterate df day-by-day and apply the capital-pool strategy.

    - Every month's first traded day: deposit `monthly_deposit` into capital pool.
    - BUY_TRANCHE_1 (CASH → HALF): invest capital_pool × 0.5
    - BUY_TRANCHE_2 (HALF → FULL): invest all remaining capital_pool
    - SELL_ALL: proceeds returned to capital pool
    - Days before `start_date` are used only for MA calculation.
    """
    df = add_moving_averages(df)
    start_ts = pd.Timestamp(start_date) if start_date is not None else None

    capital_pool = initial_capital
    shares = 0.0
    avg_cost = 0.0
    position = Position.CASH

    last_deposit_month: Optional[tuple[int, int]] = None
    ma60_alerted_this_round = False

    round_entry_date: Optional[pd.Timestamp] = None
    round_initial_capital = 0.0
    round_total_invested = 0.0
    round_position_max = Position.CASH

    trades: list[Trade] = []
    rounds: list[Round] = []
    deposits: list[Deposit] = []

    for _, row in df.iterrows():
        date = row["date"]
        if start_ts is not None and date < start_ts:
            continue

        # 每月第一個交易日入金（不論 MA 是否有值，模擬每月固定進錢到資本池）
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
        ma5, ma20, ma60 = row.get("ma5"), row.get("ma20"), row.get("ma60")
        if pd.isna(ma5) or pd.isna(ma20) or pd.isna(ma60):
            continue

        for _ in range(3):
            action = next_action(
                position, close, ma5, ma20, ma60,
                avg_cost, capital_pool,
                ma60_already_alerted=ma60_alerted_this_round,
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
                round_initial_capital = capital_before
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
                    initial_capital=round_initial_capital,
                    total_invested=round_total_invested,
                    total_proceeds=proceeds,
                    entry_avg_price=avg_cost,
                    exit_price=close,
                    position_taken=round_position_max,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    ma60_alerted=ma60_alerted_this_round,
                    capital_after=capital_pool,
                ))
                shares = 0.0
                avg_cost = 0.0
                round_entry_date = None
                round_initial_capital = 0.0
                round_total_invested = 0.0
                round_position_max = Position.CASH
                ma60_alerted_this_round = False

            elif action is Action.ALERT_MA60:
                ma60_alerted_this_round = True

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
            if action is Action.ALERT_MA60:
                break

    stats = compute_stats(rounds)

    return BacktestResult(
        df=df,
        trades=trades,
        rounds=rounds,
        deposits=deposits,
        stats=stats,
        final_position=position,
        final_shares=shares,
        final_avg_cost=avg_cost,
        final_capital_pool=capital_pool,
        final_ma60_alerted_this_round=ma60_alerted_this_round,
        round_entry_date=round_entry_date,
        round_initial_capital=round_initial_capital,
        round_total_invested=round_total_invested,
        round_position_max=round_position_max,
    )
