"""Per-segment backtest: each segment starts with an empty capital pool, receives 20K on
the first traded day of every month within the segment, and operates the strategy. Uses
raw (un-adjusted) prices; the split year (if any) is split into pre / post split segments."""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from .backtest import run_backtest as _default_backtest_fn
from .strategy import Action, MONTHLY_DEPOSIT

ACTION_SHORT_ZH = {
    Action.BUY_TRANCHE_1: "第一批買進",
    Action.BUY_TRANCHE_2: "第二批加碼",
    Action.ALERT_MA60: "MA60 警戒",
    Action.SELL_ALL: "獲利出場",
}


def compute_annual_reports(
    raw_df: pd.DataFrame,
    split_date: Optional[pd.Timestamp] = None,
    backtest_fn=None,
) -> list[dict[str, Any]]:
    """Per-year independent backtest, each segment starts with 20K, uses raw prices.

    Pre-split (year < split_date.year) and post-split are grouped so the rolling
    MA window doesn't span the split boundary (where raw prices are discontinuous).
    If `split_date` is None (target never split), the whole history is one group.
    Within each group, each year is a separate backtest run with 20K seed capital
    and no monthly deposit.
    """
    df = raw_df.copy().reset_index(drop=True)

    if split_date is None:
        reports: list[dict[str, Any]] = []
        for year in sorted(df["date"].dt.year.unique()):
            year_df = df[df["date"].dt.year == year]
            if len(year_df) == 0:
                continue
            reports.append(_run_year_segment(
                df,
                start_date=year_df["date"].iloc[0],
                end_date=year_df["date"].iloc[-1],
                key=str(year),
                label=str(year),
                backtest_fn=backtest_fn,
            ))
        return reports

    pre_group = df[df["date"] < split_date].reset_index(drop=True)
    post_group = df[df["date"] >= split_date].reset_index(drop=True)

    reports: list[dict[str, Any]] = []
    all_years = sorted(df["date"].dt.year.unique())
    for year in all_years:
        if year == split_date.year:
            pre_year = pre_group[pre_group["date"].dt.year == year]
            if len(pre_year) > 0:
                reports.append(_run_year_segment(
                    pre_group,
                    start_date=pre_year["date"].iloc[0],
                    end_date=pre_year["date"].iloc[-1],
                    key=f"{year}_pre_split",
                    label=f"{year} 分割前",
                    backtest_fn=backtest_fn,
                ))
            post_year = post_group[post_group["date"].dt.year == year]
            if len(post_year) > 0:
                reports.append(_run_year_segment(
                    post_group,
                    start_date=post_year["date"].iloc[0],
                    end_date=post_year["date"].iloc[-1],
                    key=f"{year}_post_split",
                    label=f"{year} 分割後",
                    backtest_fn=backtest_fn,
                ))
        else:
            year_df = pre_group[pre_group["date"].dt.year == year]
            if len(year_df) == 0:
                continue
            reports.append(_run_year_segment(
                pre_group,
                start_date=year_df["date"].iloc[0],
                end_date=year_df["date"].iloc[-1],
                key=str(year),
                label=str(year),
                backtest_fn=backtest_fn,
            ))
    return reports


def _run_year_segment(
    group_df: pd.DataFrame,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    key: str,
    label: str,
    backtest_fn=None,
) -> dict[str, Any]:
    """One segment run.

    `group_df` is the whole split-group (so MA rolling window is warmed by prior years).
    Iteration is limited to [start_date, end_date] via start_date filter + end-date cutoff on df.
    """
    if backtest_fn is None:
        backtest_fn = _default_backtest_fn
    df_up_to_end = group_df[group_df["date"] <= end_date].reset_index(drop=True)
    result = backtest_fn(
        df_up_to_end,
        start_date=start_date,
        initial_capital=0.0,
        monthly_deposit=MONTHLY_DEPOSIT,
    )

    tail = result.df[result.df["date"] <= end_date]
    end_close = float(tail.iloc[-1]["close"]) if len(tail) > 0 else 0.0
    end_market_value = result.final_shares * end_close
    end_total_assets = result.final_capital_pool + end_market_value
    total_deposits = sum(d.amount for d in result.deposits)
    months_deposited = len(result.deposits)
    year_gain = end_total_assets - total_deposits
    return_pct = (year_gain / total_deposits * 100) if total_deposits > 0 else 0.0
    realized_pnl = sum(r.pnl for r in result.rounds)
    unrealized_pnl = (
        end_market_value - (result.final_avg_cost * result.final_shares)
        if result.final_shares > 0 else 0.0
    )

    return {
        "key": key,
        "label": label,
        "start_date": start_date.strftime("%Y-%m-%d") if hasattr(start_date, "strftime") else str(start_date),
        "end_date": end_date.strftime("%Y-%m-%d") if hasattr(end_date, "strftime") else str(end_date),
        "monthly_deposit": MONTHLY_DEPOSIT,
        "months_deposited": months_deposited,
        "total_deposits": round(total_deposits, 2),
        "end_close": round(end_close, 4),
        "end_capital_pool": round(result.final_capital_pool, 2),
        "end_shares": round(result.final_shares, 4),
        "end_avg_cost": round(result.final_avg_cost, 4),
        "end_market_value": round(end_market_value, 2),
        "end_total_assets": round(end_total_assets, 2),
        "realized_pnl": round(realized_pnl, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "year_gain": round(year_gain, 2),
        "return_pct": round(return_pct, 2),
        "trades": [
            {
                "date": t.date.strftime("%Y-%m-%d"),
                "action": t.action.value,
                "action_zh": ACTION_SHORT_ZH[t.action],
                "price": round(t.price, 4),
                "invested_amount": round(t.invested_amount, 2),
                "capital_after": round(t.capital_after, 2),
                "shares_after": round(t.shares_after, 4),
                "avg_cost_after": round(t.avg_cost_after, 4),
            }
            for t in result.trades
        ],
        "rounds": [
            {
                "entry_date": r.entry_date.strftime("%Y-%m-%d"),
                "exit_date": r.exit_date.strftime("%Y-%m-%d"),
                "days_held": r.days_held,
                "initial_capital": round(r.initial_capital, 2),
                "total_invested": round(r.total_invested, 2),
                "total_proceeds": round(r.total_proceeds, 2),
                "entry_avg_price": round(r.entry_avg_price, 4),
                "exit_price": round(r.exit_price, 4),
                "pnl": round(r.pnl, 2),
                "pnl_pct": round(r.pnl_pct * 100, 2),
                "position_taken": r.position_taken.value,
                "ma60_alerted": r.ma60_alerted,
            }
            for r in result.rounds
        ],
    }
