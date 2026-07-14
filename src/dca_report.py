"""DCA (dollar-cost averaging) comparison from 2021 to present.

Four scenarios, all with monthly 20K deposit:
  A. Each month's first traded day → all-in 0050 (broad market ETF, shared benchmark)
  B. Each month's first traded day → all-in the target (2x leveraged ETF)
  C. Strategy I applied to the target continuously (MA-based)
  D. Strategy III applied to the target continuously (daily-drop)
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import pandas as pd

from .backtest import run_backtest
from .fetch_data import request_finmind
from .strategy import MONTHLY_DEPOSIT
from .strategy_iii import run_backtest_iii
from .targets import Target

DCA_START_DATE = pd.Timestamp("2021-01-01")
BENCHMARK_ID = "0050"
BENCHMARK_NAME = "元大台灣50 (追蹤大盤)"


def fetch_0050_dividends(start_date: str = "2021-01-01",
                         end_date: Optional[str] = None,
                         token: Optional[str] = None) -> list[dict]:
    """Fetch 0050 cash dividend records from FinMind. Returns list of {ex_date, cash_per_share}."""
    if end_date is None:
        end_date = pd.Timestamp.today().strftime("%Y-%m-%d")
    try:
        rows = request_finmind("TaiwanStockDividend", BENCHMARK_ID, start_date, end_date, token)
    except Exception as e:
        print(f"  {BENCHMARK_ID} dividend 抓取失敗：{e}")
        return []
    events = []
    for r in rows:
        ex_date_str = r.get("CashExDividendTradingDate")
        cash_div = r.get("CashEarningsDistribution", 0) or 0
        try:
            cash_div = float(cash_div)
        except (TypeError, ValueError):
            cash_div = 0.0
        if not ex_date_str or cash_div <= 0:
            continue
        events.append({
            "ex_date": pd.Timestamp(ex_date_str),
            "cash_per_share": cash_div,
        })
    events.sort(key=lambda e: e["ex_date"])
    return events


def detect_split_events(df: pd.DataFrame, threshold_pct: float = -30.0) -> list[dict]:
    """Detect potential stock splits by scanning for extreme single-day drops.
    Returns list of {date, close, change_pct, ratio} where ratio is inferred split multiplier.
    """
    d = df.sort_values("date").reset_index(drop=True).copy()
    d["change_pct"] = d["close"].pct_change() * 100
    hits = d[d["change_pct"] < threshold_pct]
    events = []
    for _, row in hits.iterrows():
        pct = float(row["change_pct"])
        ratio_float = 1 / (1 + pct / 100) if (1 + pct / 100) > 0 else None
        ratio_int = round(ratio_float) if ratio_float else None
        clean = (ratio_int is not None
                 and ratio_int >= 2
                 and abs(ratio_int - ratio_float) < 0.15)
        events.append({
            "date": row["date"].strftime("%Y-%m-%d"),
            "close": round(float(row["close"]), 4),
            "change_pct": round(pct, 2),
            "ratio": ratio_int if clean else None,
            "ratio_float": round(ratio_float, 3) if ratio_float else None,
        })
    return events


def _buy_and_hold_0050(df: pd.DataFrame,
                       dividend_events: list[dict],
                       split_events: list[dict],
                       deposit: float = MONTHLY_DEPOSIT,
                       start_date: pd.Timestamp = DCA_START_DATE) -> Optional[dict[str, Any]]:
    """A: 每月月初交易日投入 20K + 配息累積到 pending_cash、下月一起投入 + 分割日 shares × ratio。"""
    df = df[df["date"] >= start_date].reset_index(drop=True)
    if len(df) == 0:
        return None

    ex_dates = {e["ex_date"]: e["cash_per_share"] for e in dividend_events}
    # 只取 ratio 為 clean integer 的分割事件
    split_by_date = {
        pd.Timestamp(s["date"]): s["ratio"]
        for s in split_events if s.get("ratio")
    }

    shares = 0.0
    pending_cash = 0.0
    total_deposits = 0.0
    total_dividends_received = 0.0
    last_deposit_month: Optional[tuple[int, int]] = None
    daily: list[dict] = []
    trades: list[dict] = []
    dividends_log: list[dict] = []
    splits_log: list[dict] = []

    for _, row in df.iterrows():
        date = row["date"]
        close = row["close"]

        # 分割日：shares × ratio（實際上真的持有 ETF 會自動增加股數）
        if date in split_by_date and shares > 0:
            ratio = split_by_date[date]
            shares_before = shares
            shares *= ratio
            splits_log.append({
                "date": date.strftime("%Y-%m-%d"),
                "ratio": f"1:{ratio}",
                "shares_before": round(shares_before, 4),
                "shares_after": round(shares, 4),
                "close_after_split": round(close, 4),
            })

        # 除息日：pending_cash += shares × 每股配息
        if date in ex_dates and shares > 0:
            div_amount = shares * ex_dates[date]
            pending_cash += div_amount
            total_dividends_received += div_amount
            dividends_log.append({
                "date": date.strftime("%Y-%m-%d"),
                "cash_per_share": ex_dates[date],
                "shares_at_ex_date": round(shares, 4),
                "dividend_received": round(div_amount, 2),
                "pending_cash_after": round(pending_cash, 2),
            })

        # 月初交易日：投入 (20K + pending_cash)
        ym = (date.year, date.month)
        if ym != last_deposit_month:
            invest = deposit + pending_cash
            new_shares = invest / close
            shares += new_shares
            total_deposits += deposit  # 只計月度入金作為「本金」
            trades.append({
                "date": date.strftime("%Y-%m-%d"),
                "invested": round(invest, 2),
                "of_which_deposit": round(deposit, 2),
                "of_which_dividend": round(pending_cash, 2),
                "price": round(close, 4),
                "shares_bought": round(new_shares, 4),
                "total_shares_after": round(shares, 4),
            })
            pending_cash = 0.0
            last_deposit_month = ym

        market_value = shares * close
        total_assets = pending_cash + market_value
        daily.append({
            "date": date.strftime("%Y-%m-%d"),
            "total_assets": round(total_assets, 2),
        })

    end_close = float(df.iloc[-1]["close"])
    end_market_value = shares * end_close
    end_total_assets = pending_cash + end_market_value

    return {
        "daily": daily,
        "trades": trades,
        "dividends_log": dividends_log,
        "splits_log": splits_log,
        "total_deposits": round(total_deposits, 2),
        "total_dividends_received": round(total_dividends_received, 2),
        "end_close": round(end_close, 4),
        "end_shares": round(shares, 4),
        "end_market_value": round(end_market_value, 2),
        "end_pending_cash": round(pending_cash, 2),
        "end_total_assets": round(end_total_assets, 2),
        "avg_cost_per_share": round(total_deposits / shares, 4) if shares > 0 else 0.0,
        "return_pct": round(
            (end_total_assets - total_deposits) / total_deposits * 100
            if total_deposits > 0 else 0.0, 2
        ),
        "months_invested": len(trades),
        "num_dividend_events": len(dividends_log),
        "num_split_events": len(splits_log),
    }


def _buy_and_hold(df: pd.DataFrame, deposit: float = MONTHLY_DEPOSIT,
                  start_date: pd.Timestamp = DCA_START_DATE) -> Optional[dict[str, Any]]:
    """每月第 1 個交易日將 `deposit` 全額投入該檔標的。回傳 daily equity + summary。"""
    df = df[df["date"] >= start_date].reset_index(drop=True)
    if len(df) == 0:
        return None

    shares = 0.0
    total_deposits = 0.0
    last_deposit_month: Optional[tuple[int, int]] = None
    daily: list[dict] = []
    trades: list[dict] = []

    for _, row in df.iterrows():
        date = row["date"]
        close = row["close"]

        ym = (date.year, date.month)
        if ym != last_deposit_month:
            new_shares = deposit / close
            shares += new_shares
            total_deposits += deposit
            last_deposit_month = ym
            trades.append({
                "date": date.strftime("%Y-%m-%d"),
                "invested": deposit,
                "price": round(close, 4),
                "shares_bought": round(new_shares, 4),
                "total_shares_after": round(shares, 4),
            })

        market_value = shares * close
        daily.append({
            "date": date.strftime("%Y-%m-%d"),
            "total_assets": round(market_value, 2),
        })

    end_close = float(df.iloc[-1]["close"])
    end_market_value = shares * end_close
    end_total_assets = end_market_value

    return {
        "daily": daily,
        "trades": trades,
        "total_deposits": round(total_deposits, 2),
        "end_close": round(end_close, 4),
        "end_shares": round(shares, 4),
        "end_market_value": round(end_market_value, 2),
        "end_total_assets": round(end_total_assets, 2),
        "avg_cost_per_share": round(total_deposits / shares, 4) if shares > 0 else 0.0,
        "return_pct": round(
            (end_total_assets - total_deposits) / total_deposits * 100
            if total_deposits > 0 else 0.0, 2
        ),
        "months_invested": len(trades),
    }


def _strategy_run(df_adjusted: pd.DataFrame, backtest_fn: Callable,
                  start_date: pd.Timestamp = DCA_START_DATE,
                  deposit: float = MONTHLY_DEPOSIT) -> dict[str, Any]:
    """C/D: 用 backtest_fn 從 start_date 跑到今天、不間斷。回傳 daily equity + summary。"""
    result = backtest_fn(
        df_adjusted,
        start_date=start_date,
        initial_capital=0.0,
        monthly_deposit=deposit,
    )

    events = []
    for d in result.deposits:
        events.append((d.date, 0, "deposit", d.amount, None))
    for t in result.trades:
        events.append((t.date, 1, "trade", None, t))
    events.sort(key=lambda e: (e[0], e[1]))

    df_in_range = result.df[result.df["date"] >= pd.Timestamp(start_date)].reset_index(drop=True)

    capital_pool = 0.0
    shares = 0.0
    idx = 0
    daily: list[dict] = []
    for _, row in df_in_range.iterrows():
        d = row["date"]
        while idx < len(events) and events[idx][0] == d:
            _, _, kind, amount, trade = events[idx]
            if kind == "deposit":
                capital_pool += amount
            else:
                capital_pool = trade.capital_after
                shares = trade.shares_after
            idx += 1
        market_value = shares * row["close"] if shares > 0 else 0.0
        daily.append({
            "date": d.strftime("%Y-%m-%d"),
            "total_assets": round(capital_pool + market_value, 2),
        })

    total_deposits = sum(d.amount for d in result.deposits)
    end_close = float(df_in_range.iloc[-1]["close"]) if len(df_in_range) > 0 else 0.0
    end_market_value = result.final_shares * end_close if result.final_shares > 0 else 0.0
    end_total_assets = result.final_capital_pool + end_market_value

    num_buys = sum(1 for t in result.trades if t.action.value in ("BUY_TRANCHE_1", "BUY_TRANCHE_2"))
    num_sells = sum(1 for t in result.trades if t.action.value == "SELL_ALL")

    return {
        "daily": daily,
        "total_deposits": round(total_deposits, 2),
        "end_close": round(end_close, 4),
        "end_shares": round(result.final_shares, 4),
        "end_avg_cost": round(result.final_avg_cost, 4),
        "end_capital_pool": round(result.final_capital_pool, 2),
        "end_market_value": round(end_market_value, 2),
        "end_total_assets": round(end_total_assets, 2),
        "return_pct": round(
            (end_total_assets - total_deposits) / total_deposits * 100
            if total_deposits > 0 else 0.0, 2
        ),
        "months_invested": len(result.deposits),
        "num_buys": num_buys,
        "num_sells": num_sells,
        "num_completed_rounds": len(result.rounds),
    }


def compute_dca_comparison(df_target_adjusted: pd.DataFrame,
                           df_benchmark: pd.DataFrame,
                           target: Target,
                           dividend_events_benchmark: Optional[list[dict]] = None) -> dict[str, Any]:
    """Compute all four scenarios.
    A: 0050 buy-and-hold WITH cash dividends re-invested next month.
    B/C/D: target variants (dividend-neutral: leveraged ETFs pay negligible dividends).
    """
    if dividend_events_benchmark is None:
        dividend_events_benchmark = []

    # 分割 detection：只掃 A 標的（benchmark）
    split_hits_benchmark = detect_split_events(df_benchmark[df_benchmark["date"] >= DCA_START_DATE])

    a = _buy_and_hold_0050(df_benchmark, dividend_events_benchmark, split_hits_benchmark)
    b = _buy_and_hold(df_target_adjusted)
    c = _strategy_run(df_target_adjusted, run_backtest)
    d = _strategy_run(df_target_adjusted, run_backtest_iii)

    scenarios = [
        {
            "key": "A", "name": f"每月全額投入 {BENCHMARK_ID}（含配息再投入）",
            "target": BENCHMARK_ID, "target_name": BENCHMARK_NAME,
            "kind": "buy_and_hold_with_dividends",
            "description": [
                f"每月第 1 個交易日、把 20,000 全部投入 {BENCHMARK_ID}",
                "**配息**於除息日累積為 pending_cash",
                "**下個月月初**跟著月度 20,000 一起投入",
                "**分割日**：實際持有股數自動 × ratio（例如 2025-06-18 1:4 分割 → shares × 4）",
            ],
            **(a or {}),
        },
        {
            "key": "B", "name": f"每月全額投入 {target.id}",
            "target": target.id, "target_name": f"{target.name} (2× 槓桿)",
            "kind": "buy_and_hold",
            "description": [
                f"每月第 1 個交易日、把 20,000 全部投入 {target.id}",
                "不停損、不停利、單純累積持股（分割還原後）",
                "反映「無腦定期定額槓桿 ETF」的表現",
            ],
            **(b or {}),
        },
        {
            "key": "C", "name": "策略 I 持續操作",
            "target": target.id, "target_name": f"策略 I 於 {target.id} 持續操作",
            "kind": "strategy_i",
            "description": [
                f"從 2021 起、按策略 I (MA5/MA20/MA60、+7.5% 出) 持續操作 {target.id}",
                "每月月初入金 20,000 到資本池",
                "不因年底而間斷、跨年連續累積複利",
            ],
            **c,
        },
        {
            "key": "D", "name": "策略 III 持續操作",
            "target": target.id, "target_name": f"策略 III 於 {target.id} 持續操作",
            "kind": "strategy_iii",
            "description": [
                f"從 2021 起、按策略 III (單日跌 1%/3%、+3% 出) 持續操作 {target.id}",
                "每月月初入金 20,000 到資本池",
                "不因年底而間斷、跨年連續累積複利",
            ],
            **d,
        },
    ]

    return {
        "start_date": DCA_START_DATE.strftime("%Y-%m-%d"),
        "monthly_deposit": MONTHLY_DEPOSIT,
        "scenarios": scenarios,
        "split_events_0050": split_hits_benchmark,
    }
