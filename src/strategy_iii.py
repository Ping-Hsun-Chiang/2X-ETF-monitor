"""Strategy III backtest engine.

Trigger logic (single-day drop, distinct from strategy I's MA-based rules):
  - CASH & today's drop_pct > drop1 (default 1%)  → BUY_TRANCHE_1 (invest capital_pool × 0.5)
  - HALF & today's drop_pct > drop2 (default 3%)  → BUY_TRANCHE_2 (invest remaining pool)
  - HALF/FULL & (close/avg_cost - 1) ≥ exit_pct (default 3%) → SELL_ALL

Funding model identical to strategy I: monthly 20K deposit into capital pool.
Same BacktestResult shape so the shared helpers (build_latest_state, build_live_trades_payload,
compute_annual_reports) can be reused with backtest_fn=run_backtest_iii.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from .backtest import BacktestResult, Deposit, Round, Trade, compute_stats
from .strategy import (
    Action,
    MONTHLY_DEPOSIT,
    Position,
    add_moving_averages,
    apply_action,
    price_reachable_next_session,
)

DROP_FIRST = 1.0     # 第一批進場門檻（%）
DROP_SECOND = 3.0    # 第二批加碼門檻（%）
PROFIT_EXIT = 3.0    # 累積損益出場門檻（%）


def next_action_iii(
    position: Position,
    close: float,
    drop_pct_today: float,
    avg_cost: float,
    capital_pool: float,
    drop1: float = DROP_FIRST,
    drop2: float = DROP_SECOND,
    exit_pct: float = PROFIT_EXIT,
) -> Optional[Action]:
    """Return next action for strategy III given today's state, or None."""
    if position in (Position.HALF, Position.FULL) and avg_cost > 0:
        if (close / avg_cost - 1) * 100 >= exit_pct:
            return Action.SELL_ALL
    if position is Position.HALF and drop_pct_today > drop2 and capital_pool > 0:
        return Action.BUY_TRANCHE_2
    if position is Position.CASH and drop_pct_today > drop1 and capital_pool > 0:
        return Action.BUY_TRANCHE_1
    return None


def describe_next_actions_iii(
    position: Position,
    close: float,
    avg_cost: float,
    capital_pool: float,
    drop1: float = DROP_FIRST,
    drop2: float = DROP_SECOND,
    exit_pct: float = PROFIT_EXIT,
) -> list[dict]:
    """Describe the trigger(s) the user is currently watching for, restricted to
    ones the next trading day's close could plausibly reach (within the daily
    price-limit band around today's close). The drop triggers are
    day-over-day, so the trigger price is projected from today's close acting
    as tomorrow's "prev_close" -- the actual threshold shifts daily as the
    close moves."""
    hints: list[dict] = []

    if position in (Position.HALF, Position.FULL) and avg_cost > 0:
        target_price = avg_cost * (1 + exit_pct / 100)
        if price_reachable_next_session(close, target_price):
            hints.append({
                "action": Action.SELL_ALL.value,
                "action_zh": "獲利出場",
                "condition_zh": f"累積損益達 +{exit_pct:.1f}%",
                "trigger_price": round(target_price, 4),
                "price_note": "依目前持股均價反推，若之後再加碼、均價與此出場價都會跟著變動",
            })

    if position is Position.HALF and capital_pool > 0:
        trigger_price = close * (1 - drop2 / 100)
        if price_reachable_next_session(close, trigger_price):
            hints.append({
                "action": Action.BUY_TRANCHE_2.value,
                "action_zh": "第二批加碼",
                "condition_zh": f"單日跌幅 > {drop2:.1f}%",
                "trigger_price": round(trigger_price, 4),
                "amount": round(capital_pool, 2),
                "price_note": "以今日收盤為基準推算，此價位每日會依最新收盤價重新調整",
            })

    if position is Position.CASH and capital_pool > 0:
        trigger_price = close * (1 - drop1 / 100)
        if price_reachable_next_session(close, trigger_price):
            hints.append({
                "action": Action.BUY_TRANCHE_1.value,
                "action_zh": "第一批買進",
                "condition_zh": f"單日跌幅 > {drop1:.1f}%",
                "trigger_price": round(trigger_price, 4),
                "amount": round(capital_pool * 0.5, 2),
                "price_note": "以今日收盤為基準推算，此價位每日會依最新收盤價重新調整",
            })

    return hints


def run_backtest_iii(
    df: pd.DataFrame,
    start_date: Optional[pd.Timestamp] = None,
    initial_capital: float = 0.0,
    monthly_deposit: float = MONTHLY_DEPOSIT,
    drop1: float = DROP_FIRST,
    drop2: float = DROP_SECOND,
    exit_pct: float = PROFIT_EXIT,
) -> BacktestResult:
    """Strategy III backtest. Returns BacktestResult compatible with strategy I result."""
    start_ts = pd.Timestamp(start_date) if start_date is not None else None
    df = df.copy().reset_index(drop=True)
    # add MA columns so downstream helpers (build_latest_state) can read df["ma5"], etc.
    df = add_moving_averages(df)
    df["prev_close"] = df["close"].shift(1)
    df["drop_pct_today"] = (df["prev_close"] - df["close"]) / df["prev_close"] * 100

    capital_pool = initial_capital
    shares = 0.0
    avg_cost = 0.0
    position = Position.CASH
    last_deposit_month: Optional[tuple[int, int]] = None

    trades: list[Trade] = []
    rounds: list[Round] = []
    deposits: list[Deposit] = []

    round_entry_date: Optional[pd.Timestamp] = None
    round_initial_capital = 0.0
    round_total_invested = 0.0
    round_position_max = Position.CASH

    for _, row in df.iterrows():
        date = row["date"]
        if start_ts is not None and date < start_ts:
            continue

        year_month = (date.year, date.month)
        if year_month != last_deposit_month:
            if monthly_deposit > 0:
                capital_pool += monthly_deposit
                deposits.append(Deposit(
                    date=date, year=date.year, month=date.month,
                    amount=monthly_deposit, capital_after=capital_pool,
                ))
            last_deposit_month = year_month

        close = row["close"]
        drop = row["drop_pct_today"] if pd.notna(row["drop_pct_today"]) else 0.0

        for _ in range(3):
            action = next_action_iii(
                position, close, drop, avg_cost, capital_pool,
                drop1=drop1, drop2=drop2, exit_pct=exit_pct,
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
                    ma60_alerted=False,
                    capital_after=capital_pool,
                ))
                shares = 0.0
                avg_cost = 0.0
                round_entry_date = None
                round_initial_capital = 0.0
                round_total_invested = 0.0
                round_position_max = Position.CASH

            trades.append(Trade(
                date=date, action=action, price=close,
                capital_before=capital_before, capital_after=capital_pool,
                shares_before=shares_before, shares_after=shares,
                avg_cost_before=avg_cost_before, avg_cost_after=avg_cost,
                invested_amount=invested_amount,
            ))

            position = apply_action(position, action)

            if action is Action.SELL_ALL:
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
        final_ma60_alerted_this_round=False,
        round_entry_date=round_entry_date,
        round_initial_capital=round_initial_capital,
        round_total_invested=round_total_invested,
        round_position_max=round_position_max,
    )
