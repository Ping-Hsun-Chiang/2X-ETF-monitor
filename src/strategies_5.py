"""5-strategy comparison report backend (I / II / III / IV / V) for 2021-2026.

Strategy I : MA-based (existing run_backtest with strategy A logic)
Strategy II~V : Daily single-day drop trigger, four (drop1, drop2, profit_exit) combos.

Shared funding model: 20K monthly deposit, tranche 1 = pool × 0.5, tranche 2 = remaining pool.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .backtest import run_backtest
from .strategy import MONTHLY_DEPOSIT, add_moving_averages

STRATEGIES_META = [
    {
        "key": "I", "name": "策略 I", "subtitle": "MA5 / MA20 · 出場 +7.5%",
        "kind": "MA",
        "params": {"exit_pct": 7.5},
        "description": [
            "空手時，若收盤跌破 MA5 → 第一批進場（投資本池 × 0.5）",
            "半倉時，若收盤跌破 MA20 → 第二批加碼（投剩餘資本池）",
            "有部位時，若 close/avg_cost - 1 ≥ +7.5% → 全數出場",
        ],
    },
    {
        "key": "II", "name": "策略 II", "subtitle": "單日跌 1% / 3% · 出場 +2%",
        "kind": "DAILY_DROP",
        "params": {"drop1": 1.0, "drop2": 3.0, "exit_pct": 2.0},
        "description": [
            "空手時，若今日跌幅 > 1% → 第一批（投池 × 0.5）",
            "半倉時，若今日跌幅 > 3% → 第二批（投剩餘全部）",
            "有部位時，若 close/avg_cost - 1 ≥ +2% → 全數出場",
        ],
    },
    {
        "key": "III", "name": "策略 III", "subtitle": "單日跌 1% / 3% · 出場 +3%",
        "kind": "DAILY_DROP",
        "params": {"drop1": 1.0, "drop2": 3.0, "exit_pct": 3.0},
        "description": [
            "空手時，若今日跌幅 > 1% → 第一批（投池 × 0.5）",
            "半倉時，若今日跌幅 > 3% → 第二批（投剩餘全部）",
            "有部位時，若 close/avg_cost - 1 ≥ +3% → 全數出場",
        ],
    },
    {
        "key": "IV", "name": "策略 IV", "subtitle": "單日跌 1.5% / 3.5% · 出場 +2%",
        "kind": "DAILY_DROP",
        "params": {"drop1": 1.5, "drop2": 3.5, "exit_pct": 2.0},
        "description": [
            "空手時，若今日跌幅 > 1.5% → 第一批（投池 × 0.5）",
            "半倉時，若今日跌幅 > 3.5% → 第二批（投剩餘全部）",
            "有部位時，若 close/avg_cost - 1 ≥ +2% → 全數出場",
        ],
    },
    {
        "key": "V", "name": "策略 V", "subtitle": "單日跌 1.5% / 3.5% · 出場 +3%",
        "kind": "DAILY_DROP",
        "params": {"drop1": 1.5, "drop2": 3.5, "exit_pct": 3.0},
        "description": [
            "空手時，若今日跌幅 > 1.5% → 第一批（投池 × 0.5）",
            "半倉時，若今日跌幅 > 3.5% → 第二批（投剩餘全部）",
            "有部位時，若 close/avg_cost - 1 ≥ +3% → 全數出場",
        ],
    },
]

YEARS = [2021, 2022, 2023, 2024, 2025, 2026]


def _run_strategy_i(df_ma_full: pd.DataFrame, year_df: pd.DataFrame,
                    monthly_deposit: float = MONTHLY_DEPOSIT) -> dict:
    year_start = year_df["date"].iloc[0]
    year_end = year_df["date"].iloc[-1]
    df_for = df_ma_full[df_ma_full["date"] <= year_end].reset_index(drop=True)
    result = run_backtest(
        df_for, start_date=year_start,
        initial_capital=0.0, monthly_deposit=monthly_deposit,
    )

    df_year = result.df[
        (result.df["date"] >= year_start) & (result.df["date"] <= year_end)
    ].reset_index(drop=True)

    events: list = []
    for d in result.deposits:
        events.append((d.date, 0, "deposit", d))
    for t in result.trades:
        events.append((t.date, 1, "trade", t))
    events.sort(key=lambda e: (e[0], e[1]))

    capital_pool = 0.0
    shares = 0.0
    avg_cost = 0.0
    idx = 0
    daily = []
    for _, row in df_year.iterrows():
        d = row["date"]
        while idx < len(events) and events[idx][0] == d:
            _, _, kind, obj = events[idx]
            if kind == "deposit":
                capital_pool += obj.amount
            else:
                capital_pool = obj.capital_after
                shares = obj.shares_after
                avg_cost = obj.avg_cost_after
            idx += 1
        market_value = shares * row["close"] if shares > 0 else 0.0
        daily.append({
            "date": d.strftime("%Y-%m-%d"),
            "total_assets": round(capital_pool + market_value, 2),
        })

    total_deposits = sum(d.amount for d in result.deposits)
    end_close = float(df_year.iloc[-1]["close"])
    end_market_value = result.final_shares * end_close if result.final_shares > 0 else 0.0
    end_total_assets = result.final_capital_pool + end_market_value

    trades = [
        {
            "date": t.date.strftime("%Y-%m-%d"),
            "action": t.action.value,
            "price": round(t.price, 4),
            "invested": round(t.invested_amount, 2),
            "capital_after": round(t.capital_after, 2),
        }
        for t in result.trades
    ]
    rounds = [
        {
            "entry_date": r.entry_date.strftime("%Y-%m-%d"),
            "exit_date": r.exit_date.strftime("%Y-%m-%d"),
            "days_held": r.days_held,
            "entry_avg_cost": round(r.entry_avg_price, 4),
            "exit_price": round(r.exit_price, 4),
            "pnl": round(r.pnl, 2),
            "pnl_pct": round(r.pnl_pct * 100, 2),
            "total_invested": round(r.total_invested, 2),
            "total_proceeds": round(r.total_proceeds, 2),
        }
        for r in result.rounds
    ]
    num_buys = sum(1 for t in trades if t["action"] in ("BUY_TRANCHE_1", "BUY_TRANCHE_2"))
    num_sells = sum(1 for t in trades if t["action"] == "SELL_ALL")
    num_alerts = sum(1 for t in trades if t["action"] == "ALERT_MA60")

    return {
        "trades": trades,
        "rounds": rounds,
        "daily": daily,
        "total_deposits": round(total_deposits, 2),
        "end_close": round(end_close, 4),
        "end_capital_pool": round(result.final_capital_pool, 2),
        "end_shares": round(result.final_shares, 4),
        "end_avg_cost": round(result.final_avg_cost, 4),
        "end_market_value": round(end_market_value, 2),
        "end_total_assets": round(end_total_assets, 2),
        "return_pct": round(
            (end_total_assets - total_deposits) / total_deposits * 100
            if total_deposits > 0 else 0.0, 2
        ),
        "num_trades": num_buys + num_sells,
        "num_buys": num_buys,
        "num_sells": num_sells,
        "num_alerts": num_alerts,
        "num_completed_rounds": len(rounds),
    }


def _run_daily_drop(year_df: pd.DataFrame, drop1: float, drop2: float,
                    exit_pct: float, monthly_deposit: float = MONTHLY_DEPOSIT) -> dict:
    df = year_df.copy().reset_index(drop=True)
    df["prev_close"] = df["close"].shift(1)
    df["drop_pct_today"] = (df["prev_close"] - df["close"]) / df["prev_close"] * 100

    capital_pool = 0.0
    shares = 0.0
    avg_cost = 0.0
    position = "CASH"
    last_deposit_month = None

    trades: list[dict] = []
    rounds: list[dict] = []
    daily: list[dict] = []
    round_entry_date = None
    round_total_invested = 0.0

    for _, row in df.iterrows():
        date = row["date"]
        close = row["close"]
        drop = row["drop_pct_today"] if pd.notna(row["drop_pct_today"]) else 0.0

        ym = (date.year, date.month)
        if ym != last_deposit_month:
            capital_pool += monthly_deposit
            last_deposit_month = ym

        exited_today = False
        if position != "CASH" and avg_cost > 0:
            if (close / avg_cost - 1) * 100 > exit_pct:
                proceeds = shares * close
                capital_pool += proceeds
                pnl = proceeds - round_total_invested
                pnl_pct = pnl / round_total_invested if round_total_invested else 0.0
                rounds.append({
                    "entry_date": round_entry_date.strftime("%Y-%m-%d"),
                    "exit_date": date.strftime("%Y-%m-%d"),
                    "days_held": (date - round_entry_date).days if round_entry_date else 0,
                    "entry_avg_cost": round(avg_cost, 4),
                    "exit_price": round(close, 4),
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct * 100, 2),
                    "total_invested": round(round_total_invested, 2),
                    "total_proceeds": round(proceeds, 2),
                })
                trades.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "action": "SELL_ALL",
                    "price": round(close, 4),
                    "invested": round(-proceeds, 2),
                    "capital_after": round(capital_pool, 2),
                })
                shares = 0.0
                avg_cost = 0.0
                position = "CASH"
                round_entry_date = None
                round_total_invested = 0.0
                exited_today = True

        if not exited_today:
            if position == "HALF" and drop > drop2 and capital_pool > 0:
                invest = capital_pool
                new_shares = invest / close
                cost_pool = avg_cost * shares + invest
                shares += new_shares
                avg_cost = cost_pool / shares
                capital_pool = 0.0
                round_total_invested += invest
                position = "FULL"
                trades.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "action": "BUY_TRANCHE_2",
                    "price": round(close, 4),
                    "invested": round(invest, 2),
                    "capital_after": round(capital_pool, 2),
                })

            if position == "CASH" and drop > drop1 and capital_pool > 0:
                invest = capital_pool * 0.5
                new_shares = invest / close
                shares += new_shares
                avg_cost = close
                capital_pool -= invest
                round_entry_date = date
                round_total_invested = invest
                position = "HALF"
                trades.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "action": "BUY_TRANCHE_1",
                    "price": round(close, 4),
                    "invested": round(invest, 2),
                    "capital_after": round(capital_pool, 2),
                })

                if drop > drop2 and capital_pool > 0:
                    invest = capital_pool
                    new_shares = invest / close
                    cost_pool = avg_cost * shares + invest
                    shares += new_shares
                    avg_cost = cost_pool / shares
                    capital_pool = 0.0
                    round_total_invested += invest
                    position = "FULL"
                    trades.append({
                        "date": date.strftime("%Y-%m-%d"),
                        "action": "BUY_TRANCHE_2",
                        "price": round(close, 4),
                        "invested": round(invest, 2),
                        "capital_after": round(capital_pool, 2),
                    })

        market_value = shares * close if shares > 0 else 0.0
        daily.append({
            "date": date.strftime("%Y-%m-%d"),
            "total_assets": round(capital_pool + market_value, 2),
        })

    end_close = float(df.iloc[-1]["close"])
    end_market_value = shares * end_close if shares > 0 else 0.0
    end_total_assets = capital_pool + end_market_value

    seen_months = set()
    total_deposits_actual = 0.0
    for _, row in df.iterrows():
        ym_ = (row["date"].year, row["date"].month)
        if ym_ not in seen_months:
            total_deposits_actual += monthly_deposit
            seen_months.add(ym_)

    num_buys = sum(1 for t in trades if t["action"] in ("BUY_TRANCHE_1", "BUY_TRANCHE_2"))
    num_sells = sum(1 for t in trades if t["action"] == "SELL_ALL")
    num_alerts = sum(1 for t in trades if t["action"] == "ALERT_MA60")

    return {
        "trades": trades,
        "rounds": rounds,
        "daily": daily,
        "total_deposits": round(total_deposits_actual, 2),
        "end_close": round(end_close, 4),
        "end_capital_pool": round(capital_pool, 2),
        "end_shares": round(shares, 4),
        "end_avg_cost": round(avg_cost, 4),
        "end_market_value": round(end_market_value, 2),
        "end_total_assets": round(end_total_assets, 2),
        "return_pct": round(
            (end_total_assets - total_deposits_actual) / total_deposits_actual * 100
            if total_deposits_actual > 0 else 0.0, 2
        ),
        "num_trades": num_buys + num_sells,
        "num_buys": num_buys,
        "num_sells": num_sells,
        "num_alerts": num_alerts,
        "num_completed_rounds": len(rounds),
    }


def compute_5_strategies(adjusted_df: pd.DataFrame, target_id: str) -> dict:
    df_ma = add_moving_averages(adjusted_df)
    results: dict[str, dict] = {}
    pivot: dict[str, dict[str, float]] = {}

    for year in YEARS:
        year_df = adjusted_df[adjusted_df["date"].dt.year == year].reset_index(drop=True)
        if len(year_df) == 0:
            continue
        year_results: dict[str, Any] = {}
        year_pivot: dict[str, float] = {}
        for meta in STRATEGIES_META:
            if meta["kind"] == "MA":
                r = _run_strategy_i(df_ma, year_df)
            else:
                p = meta["params"]
                r = _run_daily_drop(year_df, p["drop1"], p["drop2"], p["exit_pct"])
            year_results[meta["key"]] = r
            year_pivot[meta["key"]] = r["return_pct"]
        results[str(year)] = year_results
        pivot[str(year)] = year_pivot

    return {
        "stock_id": target_id,
        "years": YEARS,
        "strategies": [
            {
                "key": m["key"],
                "name": m["name"],
                "subtitle": m["subtitle"],
                "params": m["params"],
                "description": m["description"],
            }
            for m in STRATEGIES_META
        ],
        "pivot": pivot,
        "results": results,
    }
