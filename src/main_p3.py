"""P3 entry point: fetch latest, refresh CSVs, replay state, write latest/history JSON.

Exposes `run_pipeline(target, raw_benchmark, div_events_benchmark)` so
`daily_update.py` can fetch the shared 0050 benchmark once and reuse it across
every target, instead of each target re-fetching it independently.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from .annual_report import compute_annual_reports
from .comparison_report import compute_comparison
from .dca_report import compute_dca_comparison, fetch_0050_dividends
from .strategies_5 import compute_5_strategies
from .backtest import BacktestResult, run_backtest
from .fetch_data import fetch_daily_close
from .split_adjust import adjust_for_split
from .state import LatestState, build_latest_state
from .strategy import Action, LIVE_START_DATE, MONTHLY_DEPOSIT, Position, add_moving_averages
from .strategy_iii import run_backtest_iii
from .targets import BENCHMARK_RAW_CSV, Target, get_target

POSITION_ZH = {
    Position.CASH: "空手",
    Position.HALF: "半倉",
    Position.FULL: "滿倉",
}

SIGNAL_ZH = {
    Action.BUY_TRANCHE_1: "第一批買進（跌破週線 · 投池 × 0.5）",
    Action.BUY_TRANCHE_2: "第二批加碼（跌破月線 · 投剩餘全部）",
    Action.ALERT_MA60: "警戒：跌破季線（考慮是否手動加碼）",
    Action.SELL_ALL: "獲利出場（累積損益達 +7.5%）",
}

SIGNAL_ZH_III = {
    Action.BUY_TRANCHE_1: "第一批買進（今日跌幅 > 1% · 投池 × 0.5）",
    Action.BUY_TRANCHE_2: "第二批加碼（今日跌幅 > 3% · 投剩餘全部）",
    Action.SELL_ALL: "獲利出場（累積損益達 +3%）",
}

ACTION_SHORT_ZH = {
    Action.BUY_TRANCHE_1: "第一批買進",
    Action.BUY_TRANCHE_2: "第二批加碼",
    Action.ALERT_MA60: "MA60 警戒",
    Action.SELL_ALL: "獲利出場",
}


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_csv(path, index=False)


def load_previous_json_date(latest_json: Path) -> Optional[str]:
    if not latest_json.exists():
        return None
    try:
        with latest_json.open("r", encoding="utf-8") as f:
            return json.load(f).get("date")
    except (json.JSONDecodeError, OSError):
        return None


def build_status_payload(state: LatestState, stock_id: str, signal_zh_map: Optional[dict] = None) -> dict:
    if signal_zh_map is None:
        signal_zh_map = SIGNAL_ZH
    signal_key = state.today_signal.value if state.today_signal else "NONE"
    signal_zh = signal_zh_map.get(state.today_signal, "-") if state.today_signal else "無訊號"
    return {
        "stock_id": stock_id,
        "date": state.date.strftime("%Y-%m-%d"),
        "close": round(state.close, 4),
        "ma5": round(state.ma5, 4),
        "ma20": round(state.ma20, 4),
        "ma60": round(state.ma60, 4),
        "position": state.position.value,
        "position_zh": POSITION_ZH[state.position],
        "signal": signal_key,
        "signal_zh": signal_zh,
        "live_start_date": LIVE_START_DATE.strftime("%Y-%m-%d"),
        "shares": round(state.shares, 4),
        "avg_cost": round(state.avg_cost, 4),
        "capital_pool": round(state.capital_pool, 2),
        "total_assets": round(state.total_assets, 2),
        "current_pnl": round(state.current_pnl, 2),
        "current_pnl_pct": round(state.current_pnl_pct * 100, 2),
        "ma60_alerted_this_round": state.ma60_alerted_this_round,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def write_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _num_or_none(v) -> Optional[float]:
    return round(float(v), 4) if not pd.isna(v) else None


def build_live_trades_payload(result: BacktestResult, as_of_date: pd.Timestamp, stock_id: str) -> dict:
    """Build the live-trade log JSON from a backtest result run since LIVE_START_DATE."""
    trades = [
        {
            "date": t.date.strftime("%Y-%m-%d"),
            "action": t.action.value,
            "action_zh": ACTION_SHORT_ZH[t.action],
            "price": round(t.price, 4),
            "capital_before": round(t.capital_before, 2),
            "capital_after": round(t.capital_after, 2),
            "invested_amount": round(t.invested_amount, 2),
            "shares_after": round(t.shares_after, 4),
            "avg_cost_after": round(t.avg_cost_after, 4),
        }
        for t in result.trades
    ]
    rounds = [
        {
            "entry_date": r.entry_date.strftime("%Y-%m-%d"),
            "exit_date": r.exit_date.strftime("%Y-%m-%d"),
            "days_held": r.days_held,
            "initial_capital": round(r.initial_capital, 2),
            "entry_avg_price": round(r.entry_avg_price, 4),
            "exit_price": round(r.exit_price, 4),
            "position_taken": r.position_taken.value,
            "total_invested": round(r.total_invested, 2),
            "total_proceeds": round(r.total_proceeds, 2),
            "pnl": round(r.pnl, 2),
            "pnl_pct": round(r.pnl_pct * 100, 2),
            "capital_after": round(r.capital_after, 2),
            "ma60_alerted": r.ma60_alerted,
        }
        for r in result.rounds
    ]

    current_round: Optional[dict] = None
    if result.final_position is not Position.CASH and result.final_shares > 0:
        close = float(result.df.iloc[-1]["close"])
        market_value = result.final_shares * close
        current_round = {
            "entry_date": result.round_entry_date.strftime("%Y-%m-%d") if result.round_entry_date else None,
            "initial_capital": round(result.round_initial_capital, 2),
            "shares": round(result.final_shares, 4),
            "avg_cost": round(result.final_avg_cost, 4),
            "total_invested": round(result.round_total_invested, 2),
            "market_value": round(market_value, 2),
            "current_pnl": round(market_value - (result.final_avg_cost * result.final_shares), 2),
            "current_pnl_pct": round(
                (close - result.final_avg_cost) / result.final_avg_cost * 100
                if result.final_avg_cost > 0 else 0.0,
                2,
            ),
            "position_taken": result.final_position.value,
            "ma60_alerted": result.final_ma60_alerted_this_round,
        }

    total_realized_pnl = sum(r["pnl"] for r in rounds)
    total_deposits = sum(d.amount for d in result.deposits)
    market_value_now = 0.0
    if result.final_shares > 0:
        close = float(result.df.iloc[-1]["close"])
        market_value_now = result.final_shares * close
    total_assets = result.final_capital_pool + market_value_now

    return {
        "stock_id": stock_id,
        "live_start_date": LIVE_START_DATE.strftime("%Y-%m-%d"),
        "as_of_date": as_of_date.strftime("%Y-%m-%d"),
        "summary": {
            "num_completed_rounds": len(rounds),
            "total_realized_pnl": round(total_realized_pnl, 2),
            "total_deposits": round(total_deposits, 2),
            "capital_pool": round(result.final_capital_pool, 2),
            "market_value": round(market_value_now, 2),
            "total_assets": round(total_assets, 2),
            "current_open_pnl": current_round["current_pnl"] if current_round else 0.0,
        },
        "trades": trades,
        "rounds": rounds,
        "current_round": current_round,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _series_from(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    df["change_pct"] = df["close"].pct_change() * 100
    return [
        {
            "date": row["date"].strftime("%Y-%m-%d"),
            "close": _num_or_none(row["close"]),
            "ma5": _num_or_none(row["ma5"]),
            "ma20": _num_or_none(row["ma20"]),
            "ma60": _num_or_none(row["ma60"]),
            "change_pct": _num_or_none(row["change_pct"]),
        }
        for _, row in df.iterrows()
    ]


def _segment_payload(df: pd.DataFrame, key: str, label: str) -> dict:
    series = _series_from(df)
    return {
        "key": key,
        "label": label,
        "start_date": series[0]["date"] if series else None,
        "end_date": series[-1]["date"] if series else None,
        "count": len(series),
        "series": series,
    }


def build_history_payload(raw_df: pd.DataFrame, stock_id: str, split_date: Optional[pd.Timestamp]) -> dict:
    """One segment per year from listing to now, using raw (un-adjusted) prices.

    Because the chart cleanly separates pre-split and post-split segments, we
    display the original prices without split-adjustment. MA is computed
    independently within each split group so the rolling window never spans
    the split boundary (where raw prices are discontinuous). If the target
    never split, there is a single group covering its whole history.
    """
    if split_date is None:
        with_ma = add_moving_averages(raw_df)
        d = with_ma.copy()
        d["_year"] = d["date"].dt.year
        segments = [
            _segment_payload(d[d["_year"] == year], str(year), str(year))
            for year in sorted(d["_year"].unique())
        ]
        return {"stock_id": stock_id, "segments": segments}

    pre_df = raw_df[raw_df["date"] < split_date].copy()
    post_df = raw_df[raw_df["date"] >= split_date].copy()
    pre_with_ma = add_moving_averages(pre_df)
    post_with_ma = add_moving_averages(post_df)

    def _year_segments(df_with_ma: pd.DataFrame, split_side: str) -> list[dict]:
        out: list[dict] = []
        d = df_with_ma.copy()
        d["_year"] = d["date"].dt.year
        for year in sorted(d["_year"].unique()):
            year_df = d[d["_year"] == year]
            if year == split_date.year:
                suffix = "分割前" if split_side == "pre" else "分割後"
                key = f"{year}_{'pre' if split_side == 'pre' else 'post'}_split"
                out.append(_segment_payload(year_df, key, f"{year} {suffix}"))
            else:
                out.append(_segment_payload(year_df, str(year), str(year)))
        return out

    segments = _year_segments(pre_with_ma, "pre") + _year_segments(post_with_ma, "post")
    return {
        "stock_id": stock_id,
        "segments": segments,
    }


def print_summary(payload: dict, prev_date: Optional[str], latest_json: Path) -> None:
    print("\n=== 最新狀態 ===")
    print(f"日期        : {payload['date']}")
    print(f"收盤價      : {payload['close']}")
    print(f"週線 MA5    : {payload['ma5']}")
    print(f"月線 MA20   : {payload['ma20']}")
    print(f"季線 MA60   : {payload['ma60']}")
    print(f"目前部位    : {payload['position_zh']} ({payload['position']})")
    print(f"今日訊號    : {payload['signal_zh']} ({payload['signal']})")
    print("\n=== 實盤狀態（{} 起算）===".format(payload["live_start_date"]))
    print(f"持股        : {payload['shares']}")
    print(f"成本均價    : {payload['avg_cost']}")
    print(f"資本池      : {payload['capital_pool']:,.0f} TWD")
    print(f"總資產      : {payload['total_assets']:,.0f} TWD（資本池 + 持股市值）")
    print(f"未實現損益  : {payload['current_pnl']:+,.0f} TWD ({payload['current_pnl_pct']:+.2f}%)")
    print(f"MA60 警戒過 : {payload['ma60_alerted_this_round']}")
    print(f"\n輸出檔案    : {latest_json}")
    if prev_date == payload["date"]:
        print(f"提示        : 資料源最新日期 {payload['date']} 與上次執行相同（今日無新交易日資料）")
    elif prev_date is None:
        print("提示        : 首次執行，尚無先前 JSON 記錄")
    else:
        print(f"提示        : 由 {prev_date} 更新至 {payload['date']}")


def run_pipeline(target: Target, raw_benchmark: pd.DataFrame, div_events_benchmark: list[dict]) -> None:
    """Fetch + rebuild everything for a single target, reusing an already-fetched benchmark."""
    docs_dir = target.docs_dir
    latest_json = docs_dir / "latest.json"

    prev_date = load_previous_json_date(latest_json)
    print(f"P3 daily signal update / previous JSON date: {prev_date or '(none)'}")

    print(f"抓取 {target.id} 收盤價（來源：FinMind）...")
    raw = fetch_daily_close(stock_id=target.id, start_date=target.listing_date)
    print(f"資料源筆數: {len(raw)}，最新交易日: {raw['date'].iloc[-1].date()}")

    save_csv(raw, target.raw_csv)
    adjusted = adjust_for_split(raw, split_date=target.split_date_ts, ratio=target.split_ratio)
    save_csv(adjusted, target.adjusted_csv)

    # 策略 I（現有）
    result = run_backtest(adjusted, start_date=LIVE_START_DATE)
    state = build_latest_state(result)
    payload = build_status_payload(state, target.id)
    write_json(payload, latest_json)

    # 策略 III：今日訊號 / 部位
    result_iii = run_backtest_iii(adjusted, start_date=LIVE_START_DATE)
    state_iii = build_latest_state(result_iii)
    payload_iii = build_status_payload(state_iii, target.id, signal_zh_map=SIGNAL_ZH_III)
    payload_iii["strategy"] = "III"
    write_json(payload_iii, docs_dir / "latest_iii.json")

    # 圖表顯示用原始未還原價格（策略仍用還原後的 adjusted 資料）
    history = build_history_payload(raw, target.id, target.split_date_ts)
    write_json(history, docs_dir / "history.json")

    live_trades_payload = build_live_trades_payload(result, state.date, target.id)
    write_json(live_trades_payload, docs_dir / "live_trades.json")

    live_iii = build_live_trades_payload(result_iii, state_iii.date, target.id)
    write_json(live_iii, docs_dir / "live_trades_iii.json")

    # 年度回測：策略 I
    annual_segments = compute_annual_reports(raw, split_date=target.split_date_ts)
    annual_payload = {
        "stock_id": target.id,
        "strategy": "I",
        "monthly_deposit": MONTHLY_DEPOSIT,
        "start_date": annual_segments[0]["start_date"] if annual_segments else None,
        "end_date": annual_segments[-1]["end_date"] if annual_segments else None,
        "segments": annual_segments,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    write_json(annual_payload, docs_dir / "annual_backtest.json")

    # 年度回測：策略 III
    annual_iii_segments = compute_annual_reports(raw, split_date=target.split_date_ts, backtest_fn=run_backtest_iii)
    annual_iii_payload = {
        "stock_id": target.id,
        "strategy": "III",
        "monthly_deposit": MONTHLY_DEPOSIT,
        "start_date": annual_iii_segments[0]["start_date"] if annual_iii_segments else None,
        "end_date": annual_iii_segments[-1]["end_date"] if annual_iii_segments else None,
        "segments": annual_iii_segments,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    write_json(annual_iii_payload, docs_dir / "annual_backtest_iii.json")

    # DCA 對照（0050 vs 本標的），benchmark 資料由呼叫端注入、不重複抓取
    dca_payload = compute_dca_comparison(adjusted, raw_benchmark, target, div_events_benchmark)
    dca_payload["stock_id"] = target.id
    dca_payload["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_json(dca_payload, docs_dir / "dca_comparison.json")

    # 策略對照：I vs II~V 於 2021 ~ 2026
    comparison_reports = compute_comparison(adjusted)
    comparison_payload = {
        "stock_id": target.id,
        "years": comparison_reports,
        "note": "兩策略內部皆用 adjusted (還原後) 價位計算。策略 B 的 baseline = 該年第一個交易日 adjusted close。",
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    write_json(comparison_payload, docs_dir / "comparison.json")

    # 5 策略對照（I / II / III / IV / V）於 2021 ~ 2026
    strategies_5_payload = compute_5_strategies(adjusted, target.id)
    strategies_5_payload["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_json(strategies_5_payload, docs_dir / "strategies_5.json")

    print_summary(payload, prev_date, latest_json)
    print(f"歷史序列    : {docs_dir / 'history.json'}（{len(history['segments'])} 段）")
    for seg in history["segments"]:
        print(f"  {seg['label']:16s}: {seg['count']:>4} 天（{seg['start_date']} ~ {seg['end_date']}）")
    print(f"實盤紀錄    : {docs_dir / 'live_trades.json'}（{len(live_trades_payload['trades'])} 筆交易 / {len(live_trades_payload['rounds'])} 輪完成）")
    print(f"年度回測    : {docs_dir / 'annual_backtest.json'}（{len(annual_segments)} 段，每段月入金 20K）")
    for s in annual_segments:
        print(f"  {s['label']:14s}: 入金 {s['total_deposits']:>7,.0f} ({s['months_deposited']:>2}月) | 期末總資產 {s['end_total_assets']:>9,.0f} TWD | 報酬率 {s['return_pct']:>+7.2f}% | 交易 {len(s['trades']):>2} / 完成輪 {len(s['rounds']):>2}")

    print(f"\n策略對照    : {docs_dir / 'comparison.json'}（{len(comparison_reports)} 年）")
    for c in comparison_reports:
        a, b = c['strategy_a'], c['strategy_b']
        print(f"  {c['year']} (baseline adj={c['baseline_adjusted']}):")
        print(f"    A (MA)      : 期末 {a['end_total_assets']:>9,.0f} 報酬 {a['return_pct']:>+7.2f}% 交易{a['num_trades']:>3} 完成{a['num_completed_rounds']:>2}")
        print(f"    B (drop 5%) : 期末 {b['end_total_assets']:>9,.0f} 報酬 {b['return_pct']:>+7.2f}% 交易{b['num_trades']:>3} 完成{b['num_completed_rounds']:>2}")


def fetch_benchmark_standalone() -> tuple[pd.DataFrame, list[dict]]:
    """Fetch the shared 0050 benchmark (used when running main_p3 for a single target manually)."""
    try:
        print("抓取 0050（大盤 ETF）收盤價（raw · 未含配息）...")
        raw_benchmark = fetch_daily_close(stock_id="0050", start_date="2020-12-01")
        save_csv(raw_benchmark, BENCHMARK_RAW_CSV)
        print(f"  0050 資料 {len(raw_benchmark)} 筆，最新 {raw_benchmark['date'].iloc[-1].date()}")
    except Exception as e:
        print(f"  0050 抓取失敗：{e}")
        if BENCHMARK_RAW_CSV.exists():
            raw_benchmark = pd.read_csv(BENCHMARK_RAW_CSV, parse_dates=["date"])
            print(f"  改用 cache（{len(raw_benchmark)} 筆，最新 {raw_benchmark['date'].iloc[-1].date()}）")
        else:
            raise

    print("抓取 0050 配息記錄...")
    div_events = fetch_0050_dividends(start_date="2021-01-01")
    print(f"  0050 配息事件：{len(div_events)} 筆")
    return raw_benchmark, div_events


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True, help="Target id as defined in targets.json")
    args = parser.parse_args()
    target = get_target(args.ticker)

    raw_benchmark, div_events = fetch_benchmark_standalone()
    run_pipeline(target, raw_benchmark, div_events)


if __name__ == "__main__":
    main()
