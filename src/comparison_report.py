"""Compare Strategy A (MA-based) vs Strategy B (drop-from-baseline) for 2024, 2025, 2026.

Both strategies run on ADJUSTED prices for fair comparison:
- Strategy A uses full adjusted df for MA rolling window warmup
- Strategy B uses adjusted close of the year's first traded day as baseline
Funding model identical: no initial capital, 20K deposited each month.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .backtest import run_backtest
from .strategy import MONTHLY_DEPOSIT, add_moving_averages
from .strategy_b import DROP_FIRST, DROP_SECOND, run_backtest_b

COMPARISON_YEARS = [2024, 2025, 2026]


def _summarise(result_df_end: pd.DataFrame, final_position, final_shares: float,
               final_avg_cost: float, final_capital_pool: float,
               deposits: list, rounds: list, trades: list) -> dict:
    end_close = float(result_df_end.iloc[-1]["close"]) if len(result_df_end) > 0 else 0.0
    end_market_value = final_shares * end_close
    end_total_assets = final_capital_pool + end_market_value
    total_deposits = sum(d.amount for d in deposits)
    year_gain = end_total_assets - total_deposits
    return_pct = (year_gain / total_deposits * 100) if total_deposits > 0 else 0.0
    realized_pnl = sum(r.pnl for r in rounds)
    unrealized_pnl = (
        end_market_value - (final_avg_cost * final_shares)
        if final_shares > 0 else 0.0
    )
    return {
        "months_deposited": len(deposits),
        "total_deposits": round(total_deposits, 2),
        "end_close": round(end_close, 4),
        "end_capital_pool": round(final_capital_pool, 2),
        "end_shares": round(final_shares, 4),
        "end_avg_cost": round(final_avg_cost, 4),
        "end_market_value": round(end_market_value, 2),
        "end_total_assets": round(end_total_assets, 2),
        "year_gain": round(year_gain, 2),
        "return_pct": round(return_pct, 2),
        "realized_pnl": round(realized_pnl, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "num_trades": len(trades),
        "num_completed_rounds": len(rounds),
    }


def _trades_to_json(trades) -> list[dict]:
    return [
        {
            "date": t.date.strftime("%Y-%m-%d"),
            "action": t.action.value,
            "price": round(t.price, 4),
            "invested_amount": round(t.invested_amount, 2),
            "capital_after": round(t.capital_after, 2),
            "shares_after": round(t.shares_after, 4),
            "avg_cost_after": round(t.avg_cost_after, 4),
        }
        for t in trades
    ]


def _rounds_to_json(rounds) -> list[dict]:
    return [
        {
            "entry_date": r.entry_date.strftime("%Y-%m-%d"),
            "exit_date": r.exit_date.strftime("%Y-%m-%d"),
            "days_held": r.days_held,
            "entry_avg_price": round(r.entry_avg_price, 4),
            "exit_price": round(r.exit_price, 4),
            "total_invested": round(r.total_invested, 2),
            "total_proceeds": round(r.total_proceeds, 2),
            "pnl": round(r.pnl, 2),
            "pnl_pct": round(r.pnl_pct * 100, 2),
            "position_taken": r.position_taken.value,
        }
        for r in rounds
    ]


def compute_comparison(adjusted_df: pd.DataFrame) -> list[dict[str, Any]]:
    """Run A and B for each comparison year using adjusted prices."""
    df_ma = add_moving_averages(adjusted_df)
    reports: list[dict[str, Any]] = []

    for year in COMPARISON_YEARS:
        year_slice = adjusted_df[adjusted_df["date"].dt.year == year]
        if len(year_slice) == 0:
            continue
        year_start = year_slice["date"].iloc[0]
        year_end = year_slice["date"].iloc[-1]
        baseline = float(year_slice["close"].iloc[0])

        # Strategy A: run on adjusted df ended at year_end, iterate from year_start
        df_a_end = df_ma[df_ma["date"] <= year_end].reset_index(drop=True)
        result_a = run_backtest(
            df_a_end,
            start_date=year_start,
            initial_capital=0.0,
            monthly_deposit=MONTHLY_DEPOSIT,
        )
        df_a_year = result_a.df[
            (result_a.df["date"] >= year_start) & (result_a.df["date"] <= year_end)
        ]
        summary_a = _summarise(
            df_a_year,
            result_a.final_position,
            result_a.final_shares,
            result_a.final_avg_cost,
            result_a.final_capital_pool,
            result_a.deposits,
            result_a.rounds,
            result_a.trades,
        )
        summary_a["trades"] = _trades_to_json(result_a.trades)
        summary_a["rounds"] = _rounds_to_json(result_a.rounds)

        # Strategy B: run on adjusted year df only, fixed baseline
        year_df = year_slice.reset_index(drop=True)
        result_b = run_backtest_b(
            year_df,
            baseline=baseline,
            initial_capital=0.0,
            monthly_deposit=MONTHLY_DEPOSIT,
        )
        summary_b = _summarise(
            result_b.df,
            result_b.final_position,
            result_b.final_shares,
            result_b.final_avg_cost,
            result_b.final_capital_pool,
            result_b.deposits,
            result_b.rounds,
            result_b.trades,
        )
        summary_b["trades"] = _trades_to_json(result_b.trades)
        summary_b["rounds"] = _rounds_to_json(result_b.rounds)

        reports.append({
            "year": year,
            "start_date": year_start.strftime("%Y-%m-%d"),
            "end_date": year_end.strftime("%Y-%m-%d"),
            "baseline_adjusted": round(baseline, 4),
            "trigger_first_pct": DROP_FIRST * 100,
            "trigger_second_pct": DROP_SECOND * 100,
            "strategy_a": summary_a,
            "strategy_b": summary_b,
        })

    return reports
